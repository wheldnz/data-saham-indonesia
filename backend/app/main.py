import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="AlphaHunter IDX API - AI-powered Indonesian stock market analysis platform",
)

# Allow all CORS origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
import json
import math
import subprocess
import pandas as pd
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from app.db.database import SessionLocal, Base, engine
from app.models.watchlist import Watchlist, WatchlistItem, WatchlistScore
from app.models.stock import Stock
from app.models.market_data import DailyOHLCV, BrokerSummary
from app.models.portfolio import PortfolioTransaction, PortfolioConfig
from app.services.scoring_service import calculate_all_scores

# Auto-create portfolio tables if not exists
Base.metadata.create_all(bind=engine)


class PortfolioConfigResponse(BaseModel):
    initial_cash: float

class PortfolioConfigRequest(BaseModel):
    initial_cash: float

# Pydantic models for request bodies
class WatchlistCreate(BaseModel):
    name: str
    description: str = ""
    weight_technical: float = 0.30
    weight_fundamental: float = 0.25
    weight_sentiment: float = 0.15
    weight_risk: float = 0.15
    weight_catalyst: float = 0.15

class WatchlistUpdate(BaseModel):
    name: str
    description: str = ""
    weight_technical: float = 0.30
    weight_fundamental: float = 0.25
    weight_sentiment: float = 0.15
    weight_risk: float = 0.15
    weight_catalyst: float = 0.15

class WatchlistItemCreate(BaseModel):
    ticker: str
    notes: str = ""

def sanitize_json_data(obj):
    if isinstance(obj, dict):
        return {k: sanitize_json_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_data(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    return obj

@app.get("/")
def root():
    return {"message": "Welcome to AlphaHunter IDX API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

from app.services import dataset_cache

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

@app.on_event("startup")
def startup_event():
    # Preload the ML dataset cache on app startup
    dataset_cache.load_cache()
    dataset_cache.load_cache_adaptive()

    # Clean up stale retraining status in retraining_history.json
    history_path = os.path.join(DATA_DIR, 'retraining_history.json')
    if os.path.exists(history_path):
        try:
            import json
            with open(history_path, 'r') as f:
                history = json.load(f)
            modified = False
            for run in history:
                if run.get('status') == 'running':
                    run['status'] = 'failed'
                    run['error'] = 'Server restarted or process terminated during training'
                    modified = True
            if modified:
                with open(history_path, 'w') as f:
                    json.dump(history, f, indent=2)
                print("[Startup] Cleaned up stale retraining status in retraining_history.json")
        except Exception as e:
            print("[Startup] Error cleaning up stale retraining history:", e)

@app.post("/api/cache/reload")
def reload_cache():
    success = dataset_cache.load_cache(force_reload=True)
    success_adaptive = dataset_cache.load_cache_adaptive(force_reload=True)
    if success or success_adaptive:
        return {
            "status": "success", 
            "message": f"In-memory caches reloaded. Standard: {'success' if success else 'failed'}, Adaptive: {'success' if success_adaptive else 'failed'}"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to reload caches")

# ─────────────────────────────────────────────────────────────
# [EOD Scheduler Service]
# ─────────────────────────────────────────────────────────────
import threading
import time
from datetime import datetime

SCHEDULER_CONFIG_PATH = os.path.join(DATA_DIR, 'scheduler_config.json')

def load_scheduler_config():
    if os.path.exists(SCHEDULER_CONFIG_PATH):
        try:
            with open(SCHEDULER_CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": True}

def save_scheduler_config(config):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SCHEDULER_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Error saving scheduler config: {e}")

def save_pipeline_pid(pid: int):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        pid_path = os.path.join(DATA_DIR, 'pipeline.pid')
        with open(pid_path, 'w') as f:
            f.write(str(pid))
    except Exception as e:
        print(f"Error saving pipeline PID: {e}")

def is_process_running(pid: int) -> bool:
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            h_process = kernel32.OpenProcess(0x1000, False, pid)
            if h_process:
                exit_code = ctypes.c_ulong()
                kernel32.GetExitCodeProcess(h_process, ctypes.byref(exit_code))
                kernel32.CloseHandle(h_process)
                return exit_code.value == 259 # STILL_ACTIVE
            else:
                err = kernel32.GetLastError()
                if err == 5: # Access Denied
                    return True
                return False
        except Exception:
            pass
            
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def trigger_pipeline_background():
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'run_pipeline.py')
    python_exe = sys.executable
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'venv', 'Scripts', 'python.exe')
    if os.path.exists(venv_python):
        python_exe = venv_python
    print(f"[Scheduler] Triggering pipeline via: {python_exe} {script_path}")
    try:
        proc = subprocess.Popen(
            [python_exe, "-u", script_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        save_pipeline_pid(proc.pid)
    except Exception as e:
        print(f"[Scheduler] Failed to start pipeline: {e}")

def scheduler_worker():
    print("[Scheduler] Background scheduler worker thread started.")
    
    last_trigger_date = ""
    
    while True:
        try:
            cfg = load_scheduler_config()
            if cfg.get("enabled", True):
                now = datetime.now()
                # Run Monday to Friday
                if now.weekday() < 5:
                    today_str = now.strftime("%Y-%m-%d")
                    time_str = now.strftime("%H:%M")
                    
                    if time_str in ["12:30", "18:30"]:
                        trigger_key = f"{today_str}_{time_str}"
                        if last_trigger_date != trigger_key:
                            # Verify if pipeline is already running first
                            status_path = os.path.join(DATA_DIR, 'status.json')
                            is_running = False
                            if os.path.exists(status_path):
                                try:
                                    with open(status_path, 'r') as f:
                                        status = json.load(f)
                                        is_running = status.get("is_running", False)
                                except Exception:
                                    pass
                            
                            if not is_running:
                                print(f"[Scheduler] Scheduled time reached: {time_str}. Running EOD pipeline...")
                                trigger_pipeline_background()
                                last_trigger_date = trigger_key
                            else:
                                print(f"[Scheduler] Scheduled time reached: {time_str}, but pipeline is already running. Skipping trigger.")
                                last_trigger_date = trigger_key
        except Exception as e:
            print(f"[Scheduler] Error in worker: {e}")
        time.sleep(15) # Check every 15 seconds

# Start background scheduler thread
scheduler_thread = threading.Thread(target=scheduler_worker)
scheduler_thread.daemon = True
scheduler_thread.start()


@app.get("/api/predictions")
def get_predictions(min_liquidity: float = 1000000000.0):
    csv_path = os.path.join(DATA_DIR, 'daily_ranking.csv')
    if not os.path.exists(csv_path):
        return {"data": []}
    
    df = pd.read_csv(csv_path)
    effective_liquidity = min_liquidity
    if 'value' in df.columns:
        df = df[df['value'] >= effective_liquidity]
    df = df.replace([float('inf'), float('-inf')], None).fillna('')
    data = df.to_dict(orient="records")
    
    # Inject latest Bandarologi accumulation status
    import sqlite3
    db_path = os.path.join(DATA_DIR, '..', 'alphahunter.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            query = '''
                SELECT ticker, acum_status, acum_score, net_foreign_value
                FROM broker_summaries
                WHERE (ticker, date) IN (
                    SELECT ticker, MAX(date)
                    FROM broker_summaries
                    GROUP BY ticker
                )
            '''
            df_bs = pd.read_sql_query(query, conn)
            status_map = {row['ticker']: (row['acum_status'], row['acum_score'], row['net_foreign_value']) for _, row in df_bs.iterrows()}
            
            for record in data:
                ticker_val = record.get("Ticker") or record.get("ticker")
                if ticker_val:
                    acum_status, acum_score, net_foreign = status_map.get(ticker_val, ("Neutral", 50.0, 0.0))
                    record["bandarologi_status"] = acum_status
                    record["bandarologi_score"] = acum_score
                    record["net_foreign_value"] = net_foreign
        except Exception as e:
            print("Error injecting bandarologi in predictions:", e)
        finally:
            conn.close()
            
    return {"data": sanitize_json_data(data)}


@app.get("/api/predictions/tech")
def get_technical_predictions(min_liquidity: float = 1000000000.0):
    csv_path = os.path.join(DATA_DIR, 'daily_ranking_tech.csv')
    if not os.path.exists(csv_path):
        return {"data": []}
    
    df = pd.read_csv(csv_path)
    effective_liquidity = min_liquidity
    if 'value' in df.columns:
        df = df[df['value'] >= effective_liquidity]
    df = df.replace([float('inf'), float('-inf')], None).fillna('')
    data = df.to_dict(orient="records")
    
    # Inject latest Bandarologi accumulation status
    import sqlite3
    db_path = os.path.join(DATA_DIR, '..', 'alphahunter.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            query = '''
                SELECT ticker, acum_status, acum_score, net_foreign_value
                FROM broker_summaries
                WHERE (ticker, date) IN (
                    SELECT ticker, MAX(date)
                    FROM broker_summaries
                    GROUP BY ticker
                )
            '''
            df_bs = pd.read_sql_query(query, conn)
            status_map = {row['ticker']: (row['acum_status'], row['acum_score'], row['net_foreign_value']) for _, row in df_bs.iterrows()}
            
            for record in data:
                ticker_val = record.get("Ticker") or record.get("ticker")
                if ticker_val:
                    acum_status, acum_score, net_foreign = status_map.get(ticker_val, ("Neutral", 50.0, 0.0))
                    record["bandarologi_status"] = acum_status
                    record["bandarologi_score"] = acum_score
                    record["net_foreign_value"] = net_foreign
        except Exception as e:
            print("Error injecting bandarologi in technical predictions:", e)
        finally:
            conn.close()
            
    return {"data": sanitize_json_data(data)}



@app.get("/api/bandarologi/{ticker}")
def get_bandarologi_data(ticker: str):
    import sqlite3
    db_path = os.path.join(DATA_DIR, '..', 'alphahunter.db')
    if not os.path.exists(db_path):
        return {"top_buyers": [], "top_sellers": [], "net_foreign_value": 0.0, "acum_ratio": 0.0, "acum_status": "Neutral", "acum_score": 50.0, "history": []}
        
    conn = sqlite3.connect(db_path)
    try:
        # Fetch the latest broker summary
        query_latest = '''
            SELECT b.top_buyers, b.top_sellers, b.net_foreign_value, b.acum_ratio, b.acum_status, b.acum_score, b.date, o.value as total_value
            FROM broker_summaries b
            LEFT JOIN daily_ohlcv o ON b.ticker = o.ticker AND b.date = o.date
            WHERE b.ticker = ?
            ORDER BY b.date DESC
            LIMIT 1
        '''
        df_latest = pd.read_sql_query(query_latest, conn, params=(ticker,))
        
        # Fetch last 15 days of Bandarologi scores for trend chart
        query_history = '''
            SELECT date, acum_score, acum_status
            FROM broker_summaries
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT 15
        '''
        df_history = pd.read_sql_query(query_history, conn, params=(ticker,))
        
        if df_latest.empty:
            return {
                "top_buyers": [],
                "top_sellers": [],
                "net_foreign_value": 0.0,
                "acum_ratio": 0.0,
                "acum_status": "Neutral",
                "acum_score": 50.0,
                "total_value": 0.0,
                "foreign_ratio": 0.0,
                "history": []
            }
            
        latest_rec = df_latest.iloc[0]
        
        try:
            top_buyers = json.loads(latest_rec['top_buyers'])
        except Exception:
            top_buyers = []
            
        try:
            top_sellers = json.loads(latest_rec['top_sellers'])
        except Exception:
            top_sellers = []
            
        # Reverse history so it goes chronologically for the chart
        df_history = df_history.sort_values('date', ascending=True)
        df_history['date'] = pd.to_datetime(df_history['date']).dt.strftime('%Y-%m-%d')
        history_list = df_history.to_dict(orient="records")
        
        total_val = float(latest_rec['total_value'] or 0)
        net_foreign_val = float(latest_rec['net_foreign_value'] or 0)
        foreign_ratio = (net_foreign_val / total_val) if total_val > 0 else 0.0
        
        return sanitize_json_data({
            "top_buyers": top_buyers,
            "top_sellers": top_sellers,
            "net_foreign_value": net_foreign_val,
            "acum_ratio": float(latest_rec['acum_ratio'] or 0),
            "acum_status": str(latest_rec['acum_status'] or "Neutral"),
            "acum_score": float(latest_rec['acum_score'] or 50.0),
            "total_value": total_val,
            "foreign_ratio": foreign_ratio,
            "history": history_list
        })
    finally:
        conn.close()

@app.get("/api/update-status")
def get_update_status():
    status_path = os.path.join(DATA_DIR, 'status.json')
    if not os.path.exists(status_path):
        return {"message": "Idle", "progress": 0, "is_running": False}
        
    try:
        with open(status_path, 'r') as f:
            status = json.load(f)
    except Exception:
        return {"message": "Idle", "progress": 0, "is_running": False}
        
    # Self-healing logic: Check if the process is actually running
    if status.get("is_running", False):
        # If status.json was recently modified (within 120 seconds), trust it.
        # The pipeline updates status.json frequently during each step.
        try:
            mtime = os.path.getmtime(status_path)
            age_seconds = time.time() - mtime
        except Exception:
            age_seconds = 9999  # If we can't read mtime, assume stale
        
        if age_seconds > 120:
            # status.json is stale (>2 min old), check PID to confirm
            pid_path = os.path.join(DATA_DIR, 'pipeline.pid')
            process_alive = False
            if os.path.exists(pid_path):
                try:
                    with open(pid_path, 'r') as f:
                        pid = int(f.read().strip())
                    process_alive = is_process_running(pid)
                except Exception:
                    pass
            
            if not process_alive:
                status["is_running"] = False
                status["message"] = "Pipeline completed or stopped"
                try:
                    with open(status_path, 'w') as f:
                        json.dump(status, f)
                except Exception:
                    pass
                
    return status

@app.post("/api/trigger-update")
def trigger_update(background_tasks: BackgroundTasks):
    # Check if already running
    status = get_update_status()
    if status.get("is_running", False):
        return {"status": "already running"}
        
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'run_pipeline.py')
    
    # Determine the python executable (prefer venv python if exists)
    python_exe = sys.executable
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'venv', 'Scripts', 'python.exe')
    if os.path.exists(venv_python):
        python_exe = venv_python
        
    # Run pipeline in background using subprocess
    def run_script():
        try:
            proc = subprocess.Popen(
                [python_exe, "-u", script_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            save_pipeline_pid(proc.pid)
        except Exception as e:
            print(f"Failed to start pipeline: {e}")
        
    background_tasks.add_task(run_script)
    
    # Initialize status file immediately
    status_path = os.path.join(DATA_DIR, 'status.json')
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(status_path, 'w') as f:
        json.dump({"message": "Initializing update...", "progress": 1, "is_running": True}, f)
        
    return {"status": "started"}

@app.get("/api/scheduler")
def get_scheduler_status():
    cfg = load_scheduler_config()
    return {"enabled": cfg.get("enabled", True), "next_runs": ["12:30 WIB", "18:30 WIB"]}

@app.post("/api/scheduler/toggle")
def toggle_scheduler():
    cfg = load_scheduler_config()
    cfg["enabled"] = not cfg.get("enabled", True)
    save_scheduler_config(cfg)
    return {"enabled": cfg["enabled"]}


@app.get("/api/chart/{ticker}")
def get_chart_data(ticker: str):
    import sqlite3
    db_path = os.path.join(DATA_DIR, '..', 'alphahunter.db')
    if not os.path.exists(db_path):
        return {"data": []}
        
    conn = sqlite3.connect(db_path)
    try:
        # Fetch last 100 days with technical features
        query = '''
            SELECT o.date as time, o.open, o.high, o.low, o.close, o.volume,
                   f.sma_5, f.sma_20, f.sma_50, f.bb_upper, f.bb_middle, f.bb_lower
            FROM daily_ohlcv o
            LEFT JOIN technical_features f ON o.ticker = f.ticker AND o.date = f.date
            WHERE o.ticker = ? 
            ORDER BY o.date DESC 
            LIMIT 100
        '''
        df = pd.read_sql_query(query, conn, params=(ticker,))
        if df.empty:
            return {"data": []}
            
        # Lightweight charts needs ascending time order
        df = df.sort_values('time', ascending=True)
        
        # Convert date to string format YYYY-MM-DD
        df['time'] = pd.to_datetime(df['time']).dt.strftime('%Y-%m-%d')
        
        # Clean potential NaN/inf values
        df = df.replace([float('inf'), float('-inf')], None).fillna(0.0)
        data = df.to_dict(orient="records")
        return {"data": sanitize_json_data(data)}
    finally:
        conn.close()

@app.get("/api/backtest")
def run_backtest_api(days: int = 100, capital: float = 100000000.0, strategy: str = "T1_top5", sl: float = 5.0, tp: float = 10.0, max_positions: int = 5, min_liquidity: float = 1000000000.0):
    try:
        from backtest_engine import run_backtest
        result = run_backtest(days_back=days, initial_capital=capital, strategy=strategy, stop_loss_pct=sl, take_profit_pct=tp, max_positions=max_positions, min_liquidity=min_liquidity)
        return sanitize_json_data(result)
    except Exception as e:
        return {"error": str(e)}

# --- Adaptive AI Endpoints ---
@app.get("/api/predictions/adaptive")
def get_adaptive_predictions(min_liquidity: float = 1000000000.0):
    csv_path = os.path.join(DATA_DIR, 'daily_ranking_adaptive.csv')
    if not os.path.exists(csv_path):
        return {"data": []}
    
    df = pd.read_csv(csv_path)
    effective_liquidity = min_liquidity
    if 'value' in df.columns:
        df = df[df['value'] >= effective_liquidity]
    df = df.replace([float('inf'), float('-inf')], None).fillna('')
    data = df.to_dict(orient="records")
    
    # Inject latest Bandarologi accumulation status
    import sqlite3
    db_path = os.path.join(DATA_DIR, '..', 'alphahunter.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            query = '''
                SELECT ticker, acum_status, acum_score, net_foreign_value
                FROM broker_summaries
                WHERE (ticker, date) IN (
                    SELECT ticker, MAX(date)
                    FROM broker_summaries
                    GROUP BY ticker
                )
            '''
            df_bs = pd.read_sql_query(query, conn)
            status_map = {row['ticker']: (row['acum_status'], row['acum_score'], row['net_foreign_value']) for _, row in df_bs.iterrows()}
            
            for record in data:
                ticker_val = record.get("Ticker") or record.get("ticker")
                if ticker_val:
                    acum_status, acum_score, net_foreign = status_map.get(ticker_val, ("Neutral", 50.0, 0.0))
                    record["bandarologi_status"] = acum_status
                    record["bandarologi_score"] = acum_score
                    record["net_foreign_value"] = net_foreign
        except Exception as e:
            print("Error injecting bandarologi in adaptive predictions:", e)
        finally:
            conn.close()
            
    return {"data": sanitize_json_data(data)}


@app.get("/api/predictions/adaptive/tech")
def get_adaptive_technical_predictions(min_liquidity: float = 1000000000.0):
    csv_path = os.path.join(DATA_DIR, 'daily_ranking_tech_adaptive.csv')
    if not os.path.exists(csv_path):
        return {"data": []}
    
    df = pd.read_csv(csv_path)
    effective_liquidity = min_liquidity
    if 'value' in df.columns:
        df = df[df['value'] >= effective_liquidity]
    df = df.replace([float('inf'), float('-inf')], None).fillna('')
    data = df.to_dict(orient="records")
    
    # Inject latest Bandarologi accumulation status
    import sqlite3
    db_path = os.path.join(DATA_DIR, '..', 'alphahunter.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            query = '''
                SELECT ticker, acum_status, acum_score, net_foreign_value
                FROM broker_summaries
                WHERE (ticker, date) IN (
                    SELECT ticker, MAX(date)
                    FROM broker_summaries
                    GROUP BY ticker
                )
            '''
            df_bs = pd.read_sql_query(query, conn)
            status_map = {row['ticker']: (row['acum_status'], row['acum_score'], row['net_foreign_value']) for _, row in df_bs.iterrows()}
            
            for record in data:
                ticker_val = record.get("Ticker") or record.get("ticker")
                if ticker_val:
                    acum_status, acum_score, net_foreign = status_map.get(ticker_val, ("Neutral", 50.0, 0.0))
                    record["bandarologi_status"] = acum_status
                    record["bandarologi_score"] = acum_score
                    record["net_foreign_value"] = net_foreign
        except Exception as e:
            print("Error injecting bandarologi in adaptive tech predictions:", e)
        finally:
            conn.close()
            
    return {"data": sanitize_json_data(data)}


@app.get("/api/backtest/adaptive")
def run_backtest_adaptive_api(days: int = 100, capital: float = 100000000.0, strategy: str = "T1_top5", sl: float = 5.0, tp: float = 10.0, max_positions: int = 5, min_liquidity: float = 1000000000.0, dynamic_sizing: bool = False, prob_threshold: float = 0.0):
    try:
        from backtest_engine_adaptive import run_backtest_adaptive
        result = run_backtest_adaptive(
            days_back=days,
            initial_capital=capital,
            strategy=strategy,
            stop_loss_pct=sl,
            take_profit_pct=tp,
            max_positions=max_positions,
            min_liquidity=min_liquidity,
            dynamic_sizing=dynamic_sizing,
            prob_threshold=prob_threshold
        )
        return sanitize_json_data(result)
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/regime/latest")
def get_latest_regime():
    try:
        import sqlite3
        import numpy as np
        db_path = os.path.join(DATA_DIR, '..', 'alphahunter.db')
        if not os.path.exists(db_path):
            return {"regime": "Unknown", "ihsg_trend": 1.0, "market_breadth": 50.0, "ihsg_volatility": 1.0}
            
        conn = sqlite3.connect(db_path)
        max_date_row = conn.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()
        if not max_date_row or not max_date_row[0]:
            conn.close()
            return {"regime": "Unknown", "ihsg_trend": 1.0, "market_breadth": 50.0, "ihsg_volatility": 1.0}
            
        latest_date = max_date_row[0]
        
        query_breadth = '''
            SELECT o.close, f.sma_20 
            FROM daily_ohlcv o
            INNER JOIN technical_features f ON o.ticker = f.ticker AND o.date = f.date
            WHERE o.date = ? AND o.volume > 0
        '''
        df_breadth = pd.read_sql_query(query_breadth, conn, params=(latest_date,))
        conn.close()
        
        if not df_breadth.empty:
            above_sma20 = np.where(
                (df_breadth['sma_20'] > 0) & (df_breadth['close'] > df_breadth['sma_20']),
                1.0, 0.0
            ).mean() * 100.0
            market_breadth = float(above_sma20)
        else:
            market_breadth = 50.0
            
        from app.services.yfinance_client import yfinance_client
        from datetime import datetime, timedelta
        end_fetch_str = latest_date
        start_fetch_dt = datetime.strptime(latest_date, '%Y-%m-%d') - timedelta(days=150)
        start_fetch_str = start_fetch_dt.strftime('%Y-%m-%d')
        
        df_ihsg = yfinance_client.fetch_historical_data('^JKSE', start_fetch_str, end_fetch_str)
        if df_ihsg.empty:
            ihsg_trend = 1.0
            ihsg_vol = 1.0
        else:
            df_ihsg['Close'] = pd.to_numeric(df_ihsg['Close'])
            df_ihsg['ihsg_sma50'] = df_ihsg['Close'].rolling(50).mean()
            df_ihsg['ihsg_trend'] = np.where(df_ihsg['Close'] > df_ihsg['ihsg_sma50'], 1.0, 0.0)
            df_ihsg['ihsg_return'] = df_ihsg['Close'].pct_change() * 100.0
            df_ihsg['ihsg_volatility'] = df_ihsg['ihsg_return'].rolling(14).std().fillna(1.0)
            
            latest_row = df_ihsg.iloc[-1]
            ihsg_trend = float(latest_row['ihsg_trend'])
            ihsg_vol = float(latest_row['ihsg_volatility'])
            
        if ihsg_trend == 0.0 and market_breadth < 35.0:
            regime = "Bear Market / Extreme Fear"
        elif ihsg_trend == 0.0:
            regime = "Correction / Risk-Off"
        elif market_breadth > 65.0:
            regime = "Bull Market / Risk-On"
        else:
            regime = "Sideways / Normal"
            
        return {
            "date": latest_date,
            "regime": regime,
            "ihsg_trend": ihsg_trend,
            "market_breadth": round(market_breadth, 2),
            "ihsg_volatility": round(ihsg_vol, 4)
        }
    except Exception as e:
        print("Error in get_latest_regime API:", e)
        return {"regime": "Error", "ihsg_trend": 1.0, "market_breadth": 50.0, "ihsg_volatility": 1.0, "detail": str(e)}

# --- Watchlist API ---
@app.get("/api/watchlists")
def get_watchlists():
    db = SessionLocal()
    try:
        watchlists = db.query(Watchlist).all()
        return [{"id": w.id, "name": w.name, "description": w.description, "weight_technical": w.weight_technical, "weight_fundamental": w.weight_fundamental, "weight_sentiment": w.weight_sentiment, "weight_risk": w.weight_risk, "weight_catalyst": w.weight_catalyst} for w in watchlists]
    finally:
        db.close()

@app.post("/api/watchlists")
def create_watchlist(wl: WatchlistCreate):
    db = SessionLocal()
    try:
        import uuid
        new_wl = Watchlist(
            id=str(uuid.uuid4()),
            name=wl.name,
            description=wl.description,
            weight_technical=wl.weight_technical,
            weight_fundamental=wl.weight_fundamental,
            weight_sentiment=wl.weight_sentiment,
            weight_risk=wl.weight_risk,
            weight_catalyst=wl.weight_catalyst
        )
        db.add(new_wl)
        db.commit()
        db.refresh(new_wl)
        return {"status": "success", "watchlist_id": new_wl.id}
    finally:
        db.close()

@app.get("/api/watchlists/{watchlist_id}")
def get_watchlist(watchlist_id: str):
    db = SessionLocal()
    try:
        w = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
        if not w:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        return {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "weight_technical": w.weight_technical,
            "weight_fundamental": w.weight_fundamental,
            "weight_sentiment": w.weight_sentiment,
            "weight_risk": w.weight_risk,
            "weight_catalyst": w.weight_catalyst
        }
    finally:
        db.close()

@app.put("/api/watchlists/{watchlist_id}")
def update_watchlist(watchlist_id: str, wl: WatchlistUpdate):
    db = SessionLocal()
    try:
        w = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
        if not w:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        w.name = wl.name
        w.description = wl.description
        w.weight_technical = wl.weight_technical
        w.weight_fundamental = wl.weight_fundamental
        w.weight_sentiment = wl.weight_sentiment
        w.weight_risk = wl.weight_risk
        w.weight_catalyst = wl.weight_catalyst
        db.commit()
        return {"status": "success"}
    finally:
        db.close()

@app.delete("/api/watchlists/{watchlist_id}")
def delete_watchlist(watchlist_id: str):
    db = SessionLocal()
    try:
        w = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
        if not w:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        db.delete(w)
        db.commit()
        return {"status": "success"}
    finally:
        db.close()

@app.post("/api/watchlists/{watchlist_id}/items")
def add_watchlist_item(watchlist_id: str, item: WatchlistItemCreate):
    db = SessionLocal()
    try:
        ticker = item.ticker.upper()
        # Verify watchlist exists
        w = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
        if not w:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        # Verify stock exists
        stock = db.query(Stock).filter(Stock.ticker == ticker).first()
        if not stock:
            raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
        
        # Check if already in watchlist
        existing = db.query(WatchlistItem).filter(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.ticker == ticker
        ).first()
        
        if existing:
            existing.notes = item.notes
        else:
            new_item = WatchlistItem(
                watchlist_id=watchlist_id,
                ticker=ticker,
                notes=item.notes
            )
            db.add(new_item)
        db.commit()
        return {"status": "success"}
    finally:
        db.close()

@app.delete("/api/watchlists/{watchlist_id}/items/{ticker}")
def delete_watchlist_item(watchlist_id: str, ticker: str):
    db = SessionLocal()
    try:
        ticker = ticker.upper()
        item = db.query(WatchlistItem).filter(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.ticker == ticker
        ).first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found in watchlist")
        db.delete(item)
        db.commit()
        return {"status": "success"}
    finally:
        db.close()

@app.get("/api/watchlists/{watchlist_id}/scores")
def get_watchlist_scores(watchlist_id: str):
    db = SessionLocal()
    try:
        # Get watchlist items
        items = db.query(WatchlistItem).filter(WatchlistItem.watchlist_id == watchlist_id).all()
        tickers = [item.ticker for item in items]
        notes_map = {item.ticker: item.notes for item in items}
        
        if not tickers:
            return {"data": []}
            
        # Get latest scores for these tickers
        scores = db.query(WatchlistScore).filter(WatchlistScore.ticker.in_(tickers)).all()
        scores_map = {s.ticker: s for s in scores}
        
        # Get company names and sectors from stocks table
        stocks = db.query(Stock).filter(Stock.ticker.in_(tickers)).all()
        stocks_map = {stock.ticker: stock for stock in stocks}
        
        # Get current close price
        # Join latest OHLCV
        latest_ohlcv_subquery = db.query(
            DailyOHLCV.ticker,
            func.max(DailyOHLCV.date).label("max_date")
        ).filter(DailyOHLCV.ticker.in_(tickers)).group_by(DailyOHLCV.ticker).subquery()
        
        latest_ohlcvs = db.query(DailyOHLCV).join(
            latest_ohlcv_subquery,
            (DailyOHLCV.ticker == latest_ohlcv_subquery.c.ticker) &
            (DailyOHLCV.date == latest_ohlcv_subquery.c.max_date)
        ).all()
        price_map = {o.ticker: o.close for o in latest_ohlcvs}

        # Get latest broker summaries
        latest_bs_subquery = db.query(
            BrokerSummary.ticker,
            func.max(BrokerSummary.date).label("max_date")
        ).filter(BrokerSummary.ticker.in_(tickers)).group_by(BrokerSummary.ticker).subquery()

        latest_bs = db.query(BrokerSummary).join(
            latest_bs_subquery,
            (BrokerSummary.ticker == latest_bs_subquery.c.ticker) &
            (BrokerSummary.date == latest_bs_subquery.c.max_date)
        ).all()
        bs_map = {b.ticker: b for b in latest_bs}
        
        result = []
        for ticker in tickers:
            stock = stocks_map.get(ticker)
            score = scores_map.get(ticker)
            price = price_map.get(ticker, 0.0)
            bs = bs_map.get(ticker)
            
            if not score:
                tech_score = 50.0
                fund_score = 50.0
                sent_score = 50.0
                risk_score = 50.0
                cat_score = 50.0
                total_score = 50.0
                classification = "Neutral"
                details = {}
            else:
                tech_score = score.technical_score
                fund_score = score.fundamental_score
                sent_score = score.sentiment_score
                risk_score = score.risk_score
                cat_score = score.catalyst_score
                total_score = score.total_score
                classification = score.classification
                details = score.score_details
                
            result.append({
                "ticker": ticker,
                "name": stock.company_name if stock else f"{ticker} Tbk.",
                "sector": stock.sector if stock else "General",
                "notes": notes_map.get(ticker, ""),
                "price": price,
                "total_score": total_score,
                "technical_score": tech_score,
                "fundamental_score": fund_score,
                "sentiment_score": sent_score,
                "risk_score": risk_score,
                "catalyst_score": cat_score,
                "classification": classification,
                "details": details,
                "bandarologi_status": bs.acum_status if bs else "Neutral",
                "bandarologi_score": bs.acum_score if bs else 50.0
            })
            
        return {"data": sanitize_json_data(result)}
    finally:
        db.close()

@app.post("/api/trigger-scoring")
def trigger_scoring(background_tasks: BackgroundTasks):
    def run_scoring():
        db = SessionLocal()
        try:
            calculate_all_scores(db)
        finally:
            db.close()
    background_tasks.add_task(run_scoring)
    return {"status": "scoring started"}

@app.get("/api/stocks/search")
def search_stocks(q: str = ""):
    db = SessionLocal()
    try:
        q_clean = q.strip().upper()
        if not q_clean:
            stocks = db.query(Stock).filter(Stock.is_active == True).limit(20).all()
        else:
            stocks = db.query(Stock).filter(
                Stock.is_active == True,
                (Stock.ticker.like(f"%{q_clean}%") | Stock.company_name.like(f"%{q}%"))
            ).limit(20).all()
        return [{"ticker": s.ticker, "name": s.company_name, "sector": s.sector} for s in stocks]
    finally:
        db.close()

# --- Learning Engine API ---
@app.get("/api/learning/performance")
def get_learning_performance():
    from app.services.learning_engine import load_json_log, PERFORMANCE_LOG_PATH
    data = load_json_log(PERFORMANCE_LOG_PATH)
    # Sort by date ascending
    data = sorted(data, key=lambda x: x.get('date', ''))
    return {"data": data}

@app.get("/api/learning/regime")
def get_learning_regime():
    from app.services.learning_engine import load_json_log, REGIME_LOG_PATH
    data = load_json_log(REGIME_LOG_PATH)
    data = sorted(data, key=lambda x: x.get('date', ''))
    
    current_regime = {}
    if data:
        current_regime = data[-1]
        
    return {
        "current": current_regime,
        "history": data
    }

@app.get("/api/learning/retrain-history")
def get_learning_retrain_history():
    from app.services.learning_engine import load_json_log, RETRAIN_HISTORY_PATH, get_feature_importances
    history = load_json_log(RETRAIN_HISTORY_PATH)
    # Sort descending by timestamp
    history = sorted(history, key=lambda x: x.get('timestamp', ''), reverse=True)
    
    importances = get_feature_importances()
    
    return {
        "history": history,
        "feature_importances": importances
    }

@app.post("/api/learning/trigger-retrain")
def trigger_learning_retrain(background_tasks: BackgroundTasks):
    from app.services.learning_engine import trigger_background_retraining
    background_tasks.add_task(trigger_background_retraining)
    return {"status": "retraining started"}

class ScenarioRequest(BaseModel):
    watchlist_id: str
    scenario: str

@app.post("/api/predictions/scenario")
def get_watchlist_scenario_simulation(req: ScenarioRequest):
    db = SessionLocal()
    try:
        from app.services.scenario_analysis import simulate_scenario
        res = simulate_scenario(req.watchlist_id, req.scenario, db)
        if "error" in res:
            raise HTTPException(status_code=404, detail=res["error"])
        return sanitize_json_data(res)
    finally:
        db.close()

# --- Paper Trading & Portfolio API ---
class TradeRequest(BaseModel):
    ticker: str
    action: str  # BUY or SELL
    quantity: int
    notes: str = ""

@app.get("/api/portfolio")
def get_portfolio():
    db = SessionLocal()
    try:
        from app.models.stock import Stock
        
        # Fetch all transactions
        txs = db.query(PortfolioTransaction).order_by(PortfolioTransaction.date.asc()).all()
        
        # Calculate cash and holdings
        portfolio_config = db.query(PortfolioConfig).first()
        initial_cash = portfolio_config.initial_cash if portfolio_config else 100000000.0
        cash = initial_cash
        
        holdings = {}
        realized_pnl = 0.0
        
        for tx in txs:
            ticker = tx.ticker
            price = tx.price
            qty = tx.quantity
            action = tx.action.upper()
            
            if action == "BUY":
                cost = qty * price
                cash -= cost
                if ticker not in holdings:
                    holdings[ticker] = {"qty": 0, "total_cost": 0.0}
                holdings[ticker]["qty"] += qty
                holdings[ticker]["total_cost"] += cost
            elif action == "SELL":
                revenue = qty * price
                cash += revenue
                if ticker in holdings and holdings[ticker]["qty"] > 0:
                    avg_buy_price = holdings[ticker]["total_cost"] / holdings[ticker]["qty"]
                    realized_pnl += (price - avg_buy_price) * qty
                    
                    # Reduce quantity and proportional cost
                    holdings[ticker]["qty"] -= qty
                    holdings[ticker]["total_cost"] -= avg_buy_price * qty
                    if holdings[ticker]["qty"] <= 0:
                        del holdings[ticker]
        
        # Get current prices of held stocks
        held_tickers = list(holdings.keys())
        current_prices = {}
        stock_names = {}
        stock_sectors = {}
        
        if held_tickers:
            stocks = db.query(Stock).filter(Stock.ticker.in_(held_tickers)).all()
            for s in stocks:
                stock_names[s.ticker] = s.company_name
                stock_sectors[s.ticker] = s.sector
                
            latest_ohlcv_subquery = db.query(
                DailyOHLCV.ticker,
                func.max(DailyOHLCV.date).label("max_date")
            ).filter(DailyOHLCV.ticker.in_(held_tickers)).group_by(DailyOHLCV.ticker).subquery()
            
            latest_ohlcvs = db.query(DailyOHLCV).join(
                latest_ohlcv_subquery,
                (DailyOHLCV.ticker == latest_ohlcv_subquery.c.ticker) &
                (DailyOHLCV.date == latest_ohlcv_subquery.c.max_date)
            ).all()
            
            for o in latest_ohlcvs:
                current_prices[o.ticker] = o.high
                
        holdings_list = []
        total_holdings_value = 0.0
        total_unrealized_pnl = 0.0
        
        for ticker, h in holdings.items():
            qty = h["qty"]
            total_cost = h["total_cost"]
            avg_buy_price = total_cost / qty if qty > 0 else 0.0
            curr_price = current_prices.get(ticker, avg_buy_price)
            market_value = qty * curr_price
            unrealized_pnl = market_value - total_cost
            
            total_holdings_value += market_value
            total_unrealized_pnl += unrealized_pnl
            
            holdings_list.append({
                "ticker": ticker,
                "name": stock_names.get(ticker, f"{ticker} Tbk."),
                "sector": stock_sectors.get(ticker, "General"),
                "quantity": qty,
                "avg_buy_price": round(avg_buy_price, 2),
                "current_price": curr_price,
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_percent": round((unrealized_pnl / total_cost * 100), 2) if total_cost > 0 else 0.0
            })
            
        total_portfolio_value = cash + total_holdings_value
        
        # Calculate win rate
        wins = 0
        losses = 0
        temp_holdings = {}
        for tx in txs:
            t = tx.ticker
            p = tx.price
            q = tx.quantity
            act = tx.action.upper()
            if act == "BUY":
                if t not in temp_holdings:
                    temp_holdings[t] = {"qty": 0, "total_cost": 0.0}
                temp_holdings[t]["qty"] += q
                temp_holdings[t]["total_cost"] += q * p
            elif act == "SELL":
                if t in temp_holdings and temp_holdings[t]["qty"] > 0:
                    avg_buy = temp_holdings[t]["total_cost"] / temp_holdings[t]["qty"]
                    if p > avg_buy:
                        wins += 1
                    else:
                        losses += 1
                    temp_holdings[t]["qty"] -= q
                    temp_holdings[t]["total_cost"] -= avg_buy * q
                    if temp_holdings[t]["qty"] <= 0:
                        del temp_holdings[t]
                        
        total_closed_trades = wins + losses
        win_rate = (wins / total_closed_trades * 100) if total_closed_trades > 0 else 0.0
        
        txs_list = [{
            "id": tx.id,
            "ticker": tx.ticker,
            "action": tx.action,
            "price": tx.price,
            "quantity": tx.quantity,
            "date": tx.date.strftime('%Y-%m-%d %H:%M:%S') if tx.date else "",
            "notes": tx.notes
        } for tx in reversed(txs)]
        
        return {
            "cash": round(cash, 2),
            "holdings_value": round(total_holdings_value, 2),
            "total_value": round(total_portfolio_value, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(total_unrealized_pnl, 2),
            "win_rate": round(win_rate, 2),
            "total_trades": total_closed_trades,
            "holdings": holdings_list,
            "transactions": txs_list
        }
    finally:
        db.close()

@app.post("/api/portfolio/trade")
def execute_trade(req: TradeRequest):
    db = SessionLocal()
    try:
        from app.models.stock import Stock
        
        ticker = req.ticker.upper().strip()
        action = req.action.upper().strip()
        qty = req.quantity
        
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be greater than zero.")
        if action not in ["BUY", "SELL"]:
            raise HTTPException(status_code=400, detail="Action must be BUY or SELL.")
            
        stock = db.query(Stock).filter(Stock.ticker == ticker, Stock.is_active == True).first()
        if not stock:
            raise HTTPException(status_code=404, detail=f"Stock {ticker} not found or is suspended.")
            
        latest_price_record = db.query(DailyOHLCV).filter(DailyOHLCV.ticker == ticker).order_by(DailyOHLCV.date.desc()).first()
        if not latest_price_record:
            raise HTTPException(status_code=404, detail=f"No price data available for {ticker}.")
            
        price = float(latest_price_record.close)
        
        # Calculate cash and holdings to validate trade
        txs = db.query(PortfolioTransaction).all()
        portfolio_config = db.query(PortfolioConfig).first()
        initial_cash = portfolio_config.initial_cash if portfolio_config else 100000000.0
        cash = initial_cash
        held_qty = 0
        
        for tx in txs:
            if tx.ticker == ticker:
                if tx.action.upper() == "BUY":
                    held_qty += tx.quantity
                elif tx.action.upper() == "SELL":
                    held_qty -= tx.quantity
            
            tx_cost = tx.quantity * tx.price
            if tx.action.upper() == "BUY":
                cash -= tx_cost
            elif tx.action.upper() == "SELL":
                cash += tx_cost
                
        trade_cost = qty * price
        if action == "BUY":
            if cash < trade_cost:
                raise HTTPException(status_code=400, detail=f"Insufficient funds. Required: Rp {trade_cost:,.2f}, Available: Rp {cash:,.2f}")
        elif action == "SELL":
            if held_qty < qty:
                raise HTTPException(status_code=400, detail=f"Insufficient holdings. You own {held_qty} shares of {ticker}, but tried to sell {qty}.")
                
        new_tx = PortfolioTransaction(
            ticker=ticker,
            action=action,
            price=price,
            quantity=qty,
            notes=req.notes
        )
        db.add(new_tx)
        db.commit()
        
        return {
            "status": "success",
            "message": f"Successfully virtual {action} {qty} shares of {ticker} at Rp {price:,.2f}",
            "transaction_id": new_tx.id
        }
    finally:
        db.close()

# --- Exporter & Comparison API ---
from fastapi.responses import StreamingResponse
import io

@app.get("/api/reports/daily/csv")
def download_daily_csv():
    csv_path = os.path.join(DATA_DIR, 'daily_ranking.csv')
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="Daily ranking predictions not found. Update predictions first.")
        
    db = SessionLocal()
    try:
        from app.models.stock import Stock
        from app.models.watchlist import WatchlistScore
        
        df = pd.read_csv(csv_path)
        
        tickers = df['ticker'].tolist()
        stocks = db.query(Stock).filter(Stock.ticker.in_(tickers)).all()
        stock_map = {s.ticker: s for s in stocks}
        
        scores = db.query(WatchlistScore).filter(WatchlistScore.ticker.in_(tickers)).all()
        score_map = {s.ticker: s for s in scores}
        
        report_data = []
        for idx, row in df.iterrows():
            ticker = row['ticker']
            s = stock_map.get(ticker)
            sc = score_map.get(ticker)
            
            report_data.append({
                "Rank": row['rank'],
                "Ticker": ticker,
                "Company Name": s.company_name if s else f"{ticker} Tbk.",
                "Sector": s.sector if s else "General",
                "Close Price (Rp)": row['close'],
                "Probability Up": row['prob_up'],
                "Technical Patterns": row['patterns'] if pd.notnull(row['patterns']) else "-",
                "AI Composite Score": sc.total_score if sc else 50.0,
                "Technical Score": sc.technical_score if sc else 50.0,
                "Fundamental Score": sc.fundamental_score if sc else 50.0,
                "Sentiment Score": sc.sentiment_score if sc else 50.0,
                "Risk Score": sc.risk_score if sc else 50.0,
                "Catalyst Score": sc.catalyst_score if sc else 50.0,
                "Classification": sc.classification if sc else "Neutral"
            })
            
        report_df = pd.DataFrame(report_data)
        
        stream = io.StringIO()
        report_df.to_csv(stream, index=False)
        response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=AlphaHunter_IDX_Daily_Report.csv"
        return response
    finally:
        db.close()

@app.get("/api/stocks/compare")
def compare_stocks(tickers: str):
    db = SessionLocal()
    try:
        from app.models.stock import Stock
        from app.models.watchlist import WatchlistScore
        
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        if not ticker_list:
            return {"data": []}
            
        stocks = db.query(Stock).filter(Stock.ticker.in_(ticker_list)).all()
        stocks_map = {s.ticker: s for s in stocks}
        
        scores = db.query(WatchlistScore).filter(WatchlistScore.ticker.in_(ticker_list)).all()
        scores_map = {s.ticker: s for s in scores}
        
        latest_ohlcv_subquery = db.query(
            DailyOHLCV.ticker,
            func.max(DailyOHLCV.date).label("max_date")
        ).filter(DailyOHLCV.ticker.in_(ticker_list)).group_by(DailyOHLCV.ticker).subquery()
        
        latest_ohlcvs = db.query(DailyOHLCV).join(
            latest_ohlcv_subquery,
            (DailyOHLCV.ticker == latest_ohlcv_subquery.c.ticker) &
            (DailyOHLCV.date == latest_ohlcv_subquery.c.max_date)
        ).all()
        price_map = {o.ticker: o.close for o in latest_ohlcvs}
        
        results = []
        for ticker in ticker_list:
            s = stocks_map.get(ticker)
            sc = scores_map.get(ticker)
            price = price_map.get(ticker, 0.0)
            
            if not s:
                continue
                
            results.append({
                "ticker": ticker,
                "name": s.company_name,
                "sector": s.sector,
                "price": price,
                "total_score": sc.total_score if sc else 50.0,
                "technical_score": sc.technical_score if sc else 50.0,
                "fundamental_score": sc.fundamental_score if sc else 50.0,
                "sentiment_score": sc.sentiment_score if sc else 50.0,
                "risk_score": sc.risk_score if sc else 50.0,
                "catalyst_score": sc.catalyst_score if sc else 50.0,
                "classification": sc.classification if sc else "Neutral",
                "details": sc.score_details if sc else {}
            })
            
        return {"data": sanitize_json_data(results)}
    finally:
        db.close()


@app.get("/api/portfolio/config", response_model=PortfolioConfigResponse)
def get_portfolio_config():
    db = SessionLocal()
    try:
        config = db.query(PortfolioConfig).first()
        if not config:
            config = PortfolioConfig(initial_cash=100000000.0)
            db.add(config)
            db.commit()
            db.refresh(config)
        return {"initial_cash": config.initial_cash}
    finally:
        db.close()

@app.post("/api/portfolio/config")
def update_portfolio_config(req: PortfolioConfigRequest):
    db = SessionLocal()
    try:
        config = db.query(PortfolioConfig).first()
        if not config:
            config = PortfolioConfig(initial_cash=req.initial_cash)
            db.add(config)
        else:
            config.initial_cash = req.initial_cash
        db.commit()
        return {"message": "Modal awal berhasil diperbarui", "initial_cash": config.initial_cash}
    finally:
        db.close()


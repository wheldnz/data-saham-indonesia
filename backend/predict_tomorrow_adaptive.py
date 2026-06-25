import sys
import os
import json
import pandas as pd
import numpy as np
import joblib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.models.market_data import DailyOHLCV, TechnicalFeature
from app.services.yfinance_client import yfinance_client
from pattern_scanner import detect_candlestick_patterns

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
MODEL_T1_PATH = os.path.join(DATA_DIR, 'xgb_model_t1_adaptive.joblib')
MODEL_T3_PATH = os.path.join(DATA_DIR, 'xgb_model_t3_adaptive.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list_adaptive.joblib')
OUTPUT_PATH = os.path.join(DATA_DIR, 'daily_ranking_adaptive.csv')
OUTPUT_TECH_PATH = os.path.join(DATA_DIR, 'daily_ranking_tech_adaptive.csv')
PRED_HISTORY_PATH = os.path.join(DATA_DIR, 'predictions_history_adaptive.json')

def predict_tomorrow_adaptive():
    if not os.path.exists(MODEL_T1_PATH) or not os.path.exists(MODEL_T3_PATH) or not os.path.exists(FEATURES_LIST_PATH):
        print("Adaptive model files not found. Please run train_model_adaptive.py first.")
        return
        
    print("Loading Adaptive XGBoost Models (T+1 and T+3)...")
    model_t1 = joblib.load(MODEL_T1_PATH)
    model_t3 = joblib.load(MODEL_T3_PATH)
    features_list = joblib.load(FEATURES_LIST_PATH)
    
    print("Connecting to database using sqlite3...")
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alphahunter.db')
    conn = sqlite3.connect(db_path, timeout=30)
    
    try:
        print("Fetching latest market data...")
        # Load last 100 days per ticker to calculate relative indicators and trends
        df_ohlcv = pd.read_sql_query('''
            SELECT o.ticker, o.date, o.open, o.high, o.low, o.close, o.volume, o.value
            FROM daily_ohlcv o
            INNER JOIN (
                SELECT ticker, MAX(date) as max_date FROM daily_ohlcv GROUP BY ticker
            ) m ON o.ticker = m.ticker AND o.date >= date(m.max_date, '-100 days')
        ''', conn)
        
        df_features = pd.read_sql_query('''
            SELECT f.* FROM technical_features f
            INNER JOIN (
                SELECT ticker, MAX(date) as max_date FROM technical_features GROUP BY ticker
            ) m ON f.ticker = m.ticker AND f.date >= date(m.max_date, '-100 days')
        ''', conn)
        
        df_broker = pd.read_sql_query('''
            SELECT b.ticker, b.date, b.net_foreign_value, b.acum_ratio, b.acum_score, b.acum_status
            FROM broker_summaries b
            INNER JOIN (
                SELECT ticker, MAX(date) as max_date FROM broker_summaries GROUP BY ticker
            ) m ON b.ticker = m.ticker AND b.date >= date(m.max_date, '-100 days')
        ''', conn)
        
        if df_ohlcv.empty or df_features.empty:
            print("No data available.")
            return
            
        df_merged = pd.merge(df_ohlcv, df_features, on=['ticker', 'date'], how='inner')
        
        df_merged['date'] = pd.to_datetime(df_merged['date'])
        df_broker['date'] = pd.to_datetime(df_broker['date'])
        df_merged = pd.merge(df_merged, df_broker, on=['ticker', 'date'], how='left')
        
        # Fill missing Bandarologi values with neutral defaults
        df_merged['net_foreign_value'] = df_merged['net_foreign_value'].fillna(0.0)
        df_merged['acum_ratio'] = df_merged['acum_ratio'].fillna(0.0)
        df_merged['acum_score'] = df_merged['acum_score'].fillna(50.0)
        df_merged['acum_status'] = df_merged['acum_status'].fillna('Neutral')
        
        df_merged = df_merged.sort_values(['ticker', 'date'])
        df_merged['patterns'] = detect_candlestick_patterns(df_merged)
        
        # --- Relative features engineering ---
        df_merged['prev_close'] = df_merged.groupby('ticker')['close'].shift(1)
        df_merged['return_1d'] = np.where(
            df_merged['prev_close'] > 0,
            (df_merged['close'] / df_merged['prev_close'] - 1.0) * 100.0,
            0.0
        )
        
        df_merged['close_vs_sma20_pct'] = np.where(
            df_merged['sma_20'] > 0,
            (df_merged['close'] / df_merged['sma_20'] - 1.0) * 100.0,
            0.0
        )
        
        df_merged['volume_ratio'] = np.where(
            df_merged['volume_sma_20'] > 0,
            df_merged['volume'] / df_merged['volume_sma_20'],
            1.0
        )
        
        daily_rsi_median = df_merged.groupby('date')['rsi_14'].transform('median')
        df_merged['rsi_relative'] = df_merged['rsi_14'] - daily_rsi_median
        df_merged['is_active'] = 1.0

        # ─────────────────────────────────────────────────────────────
        # Fetch and Calculate Macro Features for Latest Date
        # ─────────────────────────────────────────────────────────────
        max_market_date = df_merged['date'].max()
        print(f"Latest market date in database: {max_market_date.strftime('%Y-%m-%d')}")
        
        # Fetch IHSG data (last 100 days)
        start_fetch_dt = max_market_date - pd.Timedelta(days=150)
        start_fetch_str = start_fetch_dt.strftime('%Y-%m-%d')
        max_market_str = max_market_date.strftime('%Y-%m-%d')
        
        print(f"Fetching IHSG data from {start_fetch_str} to {max_market_str}...")
        df_ihsg = yfinance_client.fetch_historical_data('^JKSE', start_fetch_str, max_market_str)
        
        if df_ihsg.empty:
            print("[Warning] IHSG data is empty! Fallback used.")
            latest_ihsg_trend = 1.0
            latest_ihsg_vol = 1.0
        else:
            df_ihsg['Date'] = pd.to_datetime(df_ihsg['Date'])
            df_ihsg = df_ihsg.sort_values('Date').reset_index(drop=True)
            df_ihsg['ihsg_close'] = df_ihsg['Close']
            df_ihsg['ihsg_sma50'] = df_ihsg['ihsg_close'].rolling(50).mean()
            df_ihsg['ihsg_trend'] = np.where(df_ihsg['ihsg_close'] > df_ihsg['ihsg_sma50'], 1.0, 0.0)
            df_ihsg['ihsg_return'] = df_ihsg['ihsg_close'].pct_change() * 100.0
            df_ihsg['ihsg_volatility'] = df_ihsg['ihsg_return'].rolling(14).std().fillna(1.0)
            
            # Get latest values
            latest_row = df_ihsg.iloc[-1]
            latest_ihsg_trend = float(latest_row['ihsg_trend'])
            latest_ihsg_vol = float(latest_row['ihsg_volatility'])
            print(f"  Latest IHSG Trend: {latest_ihsg_trend} | IHSG Volatility: {latest_ihsg_vol:.4f}")
            
        # Calculate market breadth for the latest day
        df_latest_day_all = df_merged[df_merged['date'] == max_market_date]
        if not df_latest_day_all.empty:
            above_sma20_pct = np.where(
                (df_latest_day_all['sma_20'] > 0) & (df_latest_day_all['close'] > df_latest_day_all['sma_20']),
                1.0, 0.0
            ).mean() * 100.0
            latest_breadth = float(above_sma20_pct)
        else:
            latest_breadth = 50.0
        print(f"  Latest Market Breadth: {latest_breadth:.2f}%")

        # Assign macro features to all rows of df_merged (they will be sliced for max_market_date)
        df_merged['ihsg_trend'] = latest_ihsg_trend
        df_merged['ihsg_volatility'] = latest_ihsg_vol
        df_merged['market_breadth'] = latest_breadth

        # Settle latest active trading rows
        df_latest = df_merged.groupby('ticker').tail(1).copy()
        df_latest = df_latest[(df_latest['date'] == max_market_date) & (df_latest['volume'] > 0)].copy()
        print(f"Filtered out {len(df_merged.groupby('ticker').tail(1)) - len(df_latest)} suspended/stale stocks.")
        
        # Drop rows with NaN features
        df_latest = df_latest.dropna(subset=features_list)
        print(f"Generating adaptive predictions for {len(df_latest)} active stocks...")
        
        # Predict Probabilities
        X_latest = df_latest[features_list].values
        probs_t1 = model_t1.predict_proba(X_latest)[:, 1]
        probs_t3 = model_t3.predict_proba(X_latest)[:, 1]
        
        # Blend ML probability with Bandarologi acum_score
        acum_score_val = df_latest['acum_score'].values
        blended_prob_t1 = 0.6 * probs_t1 + 0.4 * (acum_score_val / 100.0)
        blended_prob_t3 = 0.6 * probs_t3 + 0.4 * (acum_score_val / 100.0)
        
        df_latest['prob_up'] = blended_prob_t1
        df_latest['prob_up_t3'] = blended_prob_t3
        
        # Save Blended Rankings
        df_ranked = df_latest[['ticker', 'date', 'close', 'prob_up', 'prob_up_t3', 'patterns', 'value', 'net_foreign_value', 'acum_score', 'acum_status']].copy()
        df_ranked['prob_up_raw'] = probs_t1
        df_ranked['prob_up_t3_raw'] = probs_t3
        df_ranked.sort_values(by='prob_up', ascending=False, inplace=True)
        df_ranked['rank'] = range(1, len(df_ranked) + 1)
        
        # Save Technical-Only Rankings
        df_ranked_tech = df_latest[['ticker', 'date', 'close', 'patterns', 'value', 'net_foreign_value', 'acum_score', 'acum_status']].copy()
        df_ranked_tech['prob_up'] = probs_t1
        df_ranked_tech['prob_up_t3'] = probs_t3
        df_ranked_tech['prob_up_raw'] = probs_t1
        df_ranked_tech['prob_up_t3_raw'] = probs_t3
        df_ranked_tech.sort_values(by='prob_up', ascending=False, inplace=True)
        df_ranked_tech['rank'] = range(1, len(df_ranked_tech) + 1)
        
        # Predict target date based on current market time:
        # If it is a weekday and before 16:00 (4:00 PM) WIB, we are predicting for today's EOD close (T+0).
        # Otherwise (market closed or weekend), we are predicting for the next business day (T+1).
        import datetime as dt
        from datetime import timedelta
        
        last_date_dt = max_market_date.to_pydatetime().date()
        now_local = dt.datetime.now()
        # If the latest data in the database is in the past (before today),
        # then the prediction is for the next business day after that data date.
        if last_date_dt < now_local.date():
            next_bd = last_date_dt + timedelta(days=1)
            while next_bd.weekday() >= 5:
                next_bd += timedelta(days=1)
            pred_date_str = next_bd.strftime('%Y-%m-%d')
        else:
            # If the data date is today (or in the future), check the current time.
            if now_local.hour < 16:
                pred_date_str = last_date_dt.strftime('%Y-%m-%d')
            else:
                next_bd = last_date_dt + timedelta(days=1)
                while next_bd.weekday() >= 5:
                    next_bd += timedelta(days=1)
                pred_date_str = next_bd.strftime('%Y-%m-%d')
            
        print(f"Data date: {last_date_dt.strftime('%Y-%m-%d')} -> Prediction for: {pred_date_str}")
        
        # Override date to prediction_date before saving
        df_ranked['date'] = pred_date_str
        df_ranked_tech['date'] = pred_date_str
        
        # Save to CSV
        os.makedirs(DATA_DIR, exist_ok=True)
        df_ranked.to_csv(OUTPUT_PATH, index=False)
        df_ranked_tech.to_csv(OUTPUT_TECH_PATH, index=False)
        print(f"Adaptive Blended rankings saved to {OUTPUT_PATH}")
        print(f"Adaptive Technical-only rankings saved to {OUTPUT_TECH_PATH}")
        
        # Append to adaptive history JSON
        history = []
        if os.path.exists(PRED_HISTORY_PATH):
            try:
                with open(PRED_HISTORY_PATH, 'r') as f:
                    history = json.load(f)
            except:
                pass
                
        # Remove old duplicate date if exists
        history = [h for h in history if h.get('date') != pred_date_str]
        
        new_record = {
            "date": pred_date_str,
            "predictions": [
                {
                    "ticker": row['ticker'],
                    "close": float(row['close']),
                    "prob_up": f"{float(row['prob_up'])*100:.2f}%",
                    "prob_up_t3": f"{float(row['prob_up_t3'])*100:.2f}%"
                }
                for _, row in df_ranked.head(10).iterrows()
            ]
        }
        history.append(new_record)
        
        with open(PRED_HISTORY_PATH, 'w') as f:
            json.dump(history, f, indent=2)
        print(f"Saved EOD adaptive predictions history for target date: {pred_date_str}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    predict_tomorrow_adaptive()

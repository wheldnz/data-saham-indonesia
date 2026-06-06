import sys
import os
import subprocess
import json

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
STATUS_FILE = os.path.join(DATA_DIR, 'status.json')
os.makedirs(DATA_DIR, exist_ok=True)

def update_status(message, progress, is_running=True):
    with open(STATUS_FILE, 'w') as f:
        json.dump({
            "message": message, 
            "progress": progress, 
            "is_running": is_running
        }, f)

def run_pipeline():
    try:
        update_status("Starting Engine Pipeline...", 2)
        
        # 1. Ingest Data
        update_status("Checking and ingesting latest market data...", 5)
        print("Running ingest_data.py...")
        res = subprocess.run([sys.executable, "ingest_data.py"], capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Ingestion failed: {err_msg}", 0, False)
            sys.exit(1)
            
        # 2. Feature Store
        update_status("Calculating Technical Indicators...", 60)
        print("Running calculate_features.py...")
        res = subprocess.run([sys.executable, "calculate_features.py"], capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Feature calculation failed: {err_msg}", 0, False)
            sys.exit(1)
            
        # 2b. Bandarologi Engine
        update_status("Calculating Bandarologi (Broker Summaries)...", 70)
        print("Calculating EOD Broker Summaries & accumulation status...")
        res = subprocess.run([
            sys.executable, "-c", 
            "from app.services.bandarologi_service import calculate_broker_summaries; from app.db.database import SessionLocal; db = SessionLocal(); calculate_broker_summaries(db); db.close()"
        ], capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Bandarologi calculation failed: {err_msg}", 0, False)
            sys.exit(1)
            
        # 3. Predict
        update_status("AI is generating Top 10 Predictions...", 80)
        print("Running predict_tomorrow.py...")
        res = subprocess.run([sys.executable, "predict_tomorrow.py"], capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Prediction failed: {err_msg}", 0, False)
            sys.exit(1)
            
        # 4. Watchlist & Scoring Engine
        update_status("AI is calculating Watchlist scores...", 85)
        print("Calculating Technical, Fundamental, Sentiment, Risk and Catalyst scores...")
        res = subprocess.run([
            sys.executable, "-c", 
            "from app.services.scoring_service import calculate_all_scores; from app.db.database import SessionLocal; db = SessionLocal(); calculate_all_scores(db); db.close()"
        ], capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Watchlist scoring failed: {err_msg}", 0, False)
            sys.exit(1)
            
        # 5. AI Learning Engine Feedback Loop
        update_status("Running AI Learning Engine loops...", 92)
        print("Running evaluations, regime detection, and trigger checks...")
        res = subprocess.run([
            sys.executable, "-c", 
            "from app.services.learning_engine import evaluate_predictions, detect_market_regime, check_and_trigger_retraining; evaluate_predictions(); detect_market_regime(); check_and_trigger_retraining()"
        ], capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Learning engine loops failed: {err_msg}", 0, False)
            sys.exit(1)
            
        update_status("Update Complete!", 100, False)
        print("Engine Pipeline Completed Successfully!")
        
    except Exception as e:
        update_status(f"Pipeline error: {str(e)}", 0, False)
        print(f"Pipeline error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run_pipeline()

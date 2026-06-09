import sys
import os
import subprocess
import json

# Ensure we run in the backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(os.getcwd(), 'data')
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
        # Determine the python executable (prefer venv python if exists)
        python_exe = sys.executable
        venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv', 'Scripts', 'python.exe')
        if os.path.exists(venv_python):
            python_exe = venv_python
            
        update_status("Starting Engine Pipeline...", 2)
        
        # 1. Ingest Data
        update_status("Checking and ingesting latest market data...", 5)
        print(f"Running ingest_data.py with {python_exe}...")
        res = subprocess.run([python_exe, "ingest_data.py"], capture_output=True, text=True, timeout=900)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Ingestion failed: {err_msg}", 0, False)
            sys.exit(1)
            
        # 2. Feature Store
        update_status("Calculating Technical Indicators...", 60)
        print(f"Running calculate_features.py with {python_exe}...")
        res = subprocess.run([python_exe, "calculate_features.py"], capture_output=True, text=True, timeout=1200)
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
            python_exe, "-c", 
            "from app.services.bandarologi_service import calculate_broker_summaries; from app.db.database import SessionLocal; db = SessionLocal(); calculate_broker_summaries(db); db.close()"
        ], capture_output=True, text=True, timeout=600)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Bandarologi calculation failed: {err_msg}", 0, False)
            sys.exit(1)
            
        # 3. Predict
        update_status("AI is generating Top 10 Predictions...", 80)
        print(f"Running predict_tomorrow.py with {python_exe}...")
        res = subprocess.run([python_exe, "predict_tomorrow.py"], capture_output=True, text=True, timeout=600)
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
            python_exe, "-c", 
            "from app.services.scoring_service import calculate_all_scores; from app.db.database import SessionLocal; db = SessionLocal(); calculate_all_scores(db); db.close()"
        ], capture_output=True, text=True, timeout=600)
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
            python_exe, "-c", 
            "from app.services.learning_engine import evaluate_predictions, detect_market_regime, check_and_trigger_retraining; evaluate_predictions(); detect_market_regime(); check_and_trigger_retraining()"
        ], capture_output=True, text=True, timeout=600)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            err_msg = res.stderr.strip().split('\n')[-1] if res.stderr else "Unknown error"
            update_status(f"Learning engine loops failed: {err_msg}", 0, False)
            sys.exit(1)
            
        # Read the prediction date from daily_ranking.csv to display in the UI status
        pred_date_str = "Complete"
        try:
            import csv
            csv_path = os.path.join(DATA_DIR, 'daily_ranking.csv')
            if os.path.exists(csv_path):
                with open(csv_path, 'r') as f:
                    reader = csv.DictReader(f)
                    first_row = next(reader, None)
                    if first_row and 'date' in first_row:
                        pred_date_str = f"Complete (Pred untuk {first_row['date']})"
        except Exception as ec:
            print(f"Error reading prediction date for status: {ec}")
            
        update_status(f"Update Complete! {pred_date_str}", 100, False)
        print("Engine Pipeline Completed Successfully!")
        
    except Exception as e:
        update_status(f"Pipeline error: {str(e)}", 0, False)
        print(f"Pipeline error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run_pipeline()

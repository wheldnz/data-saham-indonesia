import sys
import os
import subprocess
import json

# Ensure we run in the backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(os.getcwd(), 'data')
STATUS_FILE = os.path.join(DATA_DIR, 'status.json')
os.makedirs(DATA_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# Headless-safe: redirect stdout/stderr to log file.
# When launched with CREATE_NO_WINDOW, sys.stdout may be None
# or an invalid handle that crashes on write(). We redirect
# both streams to a persistent log file immediately.
# ─────────────────────────────────────────────────────────────
LOG_PATH = os.path.join(DATA_DIR, 'pipeline.log')

def _setup_logging():
    """Redirect stdout and stderr to the pipeline log file."""
    try:
        log_file = open(LOG_PATH, 'w', encoding='utf-8', buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception:
        # Last resort: redirect to devnull so nothing crashes
        devnull = open(os.devnull, 'w')
        sys.stdout = devnull
        sys.stderr = devnull

_setup_logging()


def update_status(message, progress, is_running=True):
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump({
                "message": message, 
                "progress": progress, 
                "is_running": is_running
            }, f)
    except Exception:
        pass

def prevent_sleep():
    pass

def restore_sleep():
    pass

def run_subprocess_stream(args, status_msg, progress_val, timeout_sec=1200):
    update_status(status_msg, progress_val)
    script_name = " ".join(args[1:]) if len(args) > 1 and args[1] != "-c" else args[0]
    if len(args) > 2 and args[1] == "-c":
        script_name = "python inline: " + args[2].split(";")[0][:60] + "..."
        
    print(f"\n==========================================")
    print(f" Running: {script_name}")
    print(f"==========================================")
    sys.stdout.flush()
    
    # Start subprocess with stdout/stderr combined
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
        universal_newlines=True
    )
    
    # Stream output line-by-line to our log (which is sys.stdout)
    try:
        for line in iter(process.stdout.readline, ''):
            sys.stdout.write(line)
            sys.stdout.flush()
    except Exception as e_stream:
        print(f"\n[Error] Streaming output failed: {e_stream}")
        
    process.stdout.close()
    try:
        return_code = process.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        process.kill()
        print(f"\n--- [TIMEOUT] {script_name} timed out after {timeout_sec} seconds ---")
        sys.stdout.flush()
        update_status(f"Pipeline timeout at {script_name.split()[0]}", 0, False)
        sys.exit(1)
        
    print(f"--- [FINISHED] {script_name} with exit code {return_code} ---")
    sys.stdout.flush()
    
    if return_code != 0:
        print(f"\n[Error] Script {script_name} failed with exit code {return_code}")
        update_status(f"Pipeline failed at {script_name.split()[0]}", 0, False)
        sys.exit(return_code)

def run_pipeline():
    prevent_sleep()
    try:
        # Write PID file to allow backend to check if we are running
        pid_path = os.path.join(DATA_DIR, 'pipeline.pid')
        try:
            with open(pid_path, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as ep:
            print(f"Warning: Could not write pipeline PID file: {ep}")

        # Determine the python executable (prefer venv python if exists)
        python_exe = sys.executable
        venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv', 'Scripts', 'python.exe')
        if os.path.exists(venv_python):
            python_exe = venv_python
            
        print("=== ALPHA HUNTER PIPELINE RUN LOG ===")
        update_status("Starting Engine Pipeline...", 2)
        
        # 1. Ingest Data
        run_subprocess_stream([python_exe, "-u", "ingest_data.py"], "Checking and ingesting latest market data...", 5, timeout_sec=900)
            
        # 2. Feature Store
        run_subprocess_stream([python_exe, "-u", "calculate_features.py"], "Calculating Technical Indicators...", 60, timeout_sec=1200)
            
        # 2b. Bandarologi Engine
        run_subprocess_stream([
            python_exe, "-u", "-c", 
            "from app.services.bandarologi_service import calculate_broker_summaries; from app.db.database import SessionLocal; db = SessionLocal(); calculate_broker_summaries(db); db.close()"
        ], "Calculating Bandarologi (Broker Summaries)...", 70, timeout_sec=600)
            
        # 3. Predict
        run_subprocess_stream([python_exe, "-u", "predict_tomorrow.py"], "AI is generating Top 10 Predictions...", 80, timeout_sec=600)
            
        # 4. Watchlist & Scoring Engine
        run_subprocess_stream([
            python_exe, "-u", "-c", 
            "from app.services.scoring_service import calculate_all_scores; from app.db.database import SessionLocal; db = SessionLocal(); calculate_all_scores(db); db.close()"
        ], "AI is calculating Watchlist scores...", 85, timeout_sec=600)
            
        # 5. AI Learning Engine Feedback Loop
        run_subprocess_stream([
            python_exe, "-u", "-c", 
            "from app.services.learning_engine import evaluate_predictions, detect_market_regime, check_and_trigger_retraining; evaluate_predictions(); detect_market_regime(); check_and_trigger_retraining(blocking=True)"
        ], "Running AI Learning Engine loops...", 92, timeout_sec=600)
            
        # 5b. Prepare ML Dataset for Backtesting
        run_subprocess_stream([python_exe, "-u", "prepare_ml_data.py"], "Compiling ML Dataset for Backtesting...", 96, timeout_sec=600)
            
        # 5c. Prepare Adaptive ML Dataset for Backtesting
        run_subprocess_stream([python_exe, "-u", "prepare_ml_data_adaptive.py"], "Compiling Adaptive ML Dataset...", 98, timeout_sec=600)
            
        # 5d. Generate Adaptive AI Predictions
        run_subprocess_stream([python_exe, "-u", "predict_tomorrow_adaptive.py"], "Generating Adaptive AI Predictions...", 99, timeout_sec=600)
            
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
        print("\nEngine Pipeline Completed Successfully!")
        
        # Trigger cache reload in backend FastAPI server
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://localhost:8000/api/cache/reload",
                method="POST"
            )
            # Short timeout so it doesn't block if server isn't listening on 8000
            with urllib.request.urlopen(req, timeout=3) as response:
                print(f"Cache reload request sent: {response.status}")
        except Exception as e:
            print(f"Warning: Could not trigger cache reload via API: {e}")
            
        
    except Exception as e:
        update_status(f"Pipeline error: {str(e)}", 0, False)
        print(f"Pipeline error: {e}")
        sys.exit(1)
    finally:
        restore_sleep()

if __name__ == "__main__":
    run_pipeline()

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

def prevent_sleep():
    if sys.platform == 'win32':
        try:
            import ctypes
            # ES_CONTINUOUS = 0x80000000
            # ES_SYSTEM_REQUIRED = 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
            print("[System] Windows Sleep prevention activated for pipeline.")
        except Exception as e:
            print(f"[System] Failed to activate sleep prevention: {e}")

def restore_sleep():
    if sys.platform == 'win32':
        try:
            import ctypes
            # ES_CONTINUOUS
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            print("[System] Windows Sleep prevention deactivated.")
        except Exception as e:
            print(f"[System] Failed to deactivate sleep prevention: {e}")

def run_subprocess_stream(args, status_msg, progress_val, timeout_sec=1200):
    update_status(status_msg, progress_val)
    script_name = " ".join(args[1:]) if len(args) > 1 and args[1] != "-c" else args[0]
    if len(args) > 2 and args[1] == "-c":
        # Extract a short summary of the python inline script for display
        script_name = "python inline: " + args[2].split(";")[0][:60] + "..."
        
    print(f"\n==========================================")
    print(f" Running: {script_name}")
    print(f"==========================================")
    sys.stdout.flush()
    
    log_path = os.path.join(DATA_DIR, 'pipeline.log')
    
    with open(log_path, 'a', encoding='utf-8') as log_file:
        log_file.write(f"\n--- [START] {script_name} ---\n")
        log_file.flush()
        
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
        
        # Stream output line-by-line
        try:
            for line in iter(process.stdout.readline, ''):
                sys.stdout.write(line)
                sys.stdout.flush()
                log_file.write(line)
                log_file.flush()
        except Exception as e_stream:
            print(f"\n[Error] Streaming output failed: {e_stream}", file=sys.stderr)
            log_file.write(f"\n[Error] Streaming output failed: {e_stream}\n")
            log_file.flush()
            
        process.stdout.close()
        try:
            return_code = process.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            process.kill()
            log_file.write(f"\n--- [TIMEOUT] {script_name} timed out after {timeout_sec} seconds ---\n")
            log_file.flush()
            update_status(f"Pipeline timeout at {script_name.split()[0]}", 0, False)
            sys.exit(1)
            
        log_file.write(f"--- [FINISHED] {script_name} with exit code {return_code} ---\n")
        log_file.flush()
        
        if return_code != 0:
            print(f"\n[Error] Script {script_name} failed with exit code {return_code}", file=sys.stderr)
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
            
        # Initialize log file
        log_path = os.path.join(DATA_DIR, 'pipeline.log')
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("=== ALPHA HUNTER PIPELINE RUN LOG ===\n")
            
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
            "from app.services.learning_engine import evaluate_predictions, detect_market_regime, check_and_trigger_retraining; evaluate_predictions(); detect_market_regime(); check_and_trigger_retraining()"
        ], "Running AI Learning Engine loops...", 92, timeout_sec=600)
            
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
        
    except Exception as e:
        update_status(f"Pipeline error: {str(e)}", 0, False)
        print(f"Pipeline error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        restore_sleep()

if __name__ == "__main__":
    run_pipeline()

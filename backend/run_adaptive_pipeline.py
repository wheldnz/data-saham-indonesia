import subprocess
import sys
import os

def run_script(script_name):
    print(f"\n==========================================")
    print(f" Running: {script_name}")
    print(f"==========================================")
    
    python_exe = sys.executable
    process = subprocess.run([python_exe, script_name], capture_output=False, text=True)
    
    if process.returncode != 0:
        print(f"[ERROR] {script_name} failed with exit code {process.returncode}!")
        sys.exit(process.returncode)
    else:
        print(f"[SUCCESS] {script_name} completed successfully.")

def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(backend_dir)
    
    print("=== STARTING ADAPTIVE / REGIME-AWARE PIPELINE RUN ===")
    
    # 1. Prepare Data
    run_script("prepare_ml_data_adaptive.py")
    
    # 2. Train Models
    run_script("train_model_adaptive.py")
    
    # 3. Generate Predictions
    run_script("predict_tomorrow_adaptive.py")
    
    # 4. Run Backtests
    run_script("backtest_engine_adaptive.py")
    
    print("\n==========================================")
    print(" ADAPTIVE PIPELINE VERIFIED SUCCESSFULLY!")
    print("==========================================")

if __name__ == "__main__":
    main()

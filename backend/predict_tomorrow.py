import sys
import os
import pandas as pd
import joblib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.models.market_data import DailyOHLCV, TechnicalFeature
from pattern_scanner import detect_candlestick_patterns

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
MODEL_PATH = os.path.join(DATA_DIR, 'xgb_model_t1.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list.joblib')
OUTPUT_PATH = os.path.join(DATA_DIR, 'daily_ranking.csv')

def update_pipeline_status(message, progress, is_running=True):
    import json
    status_file = os.path.join(DATA_DIR, 'status.json')
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(status_file, 'w') as f:
            json.dump({
                "message": message,
                "progress": progress,
                "is_running": is_running
            }, f)
    except Exception as e:
        print(f"Error writing status file: {e}")

def predict_tomorrow():
    if not os.path.exists(MODEL_PATH) or not os.path.exists(FEATURES_LIST_PATH):
        print("Model not found. Please run train_model.py first.")
        update_pipeline_status("Model files not found. Run training first.", 0, False)
        return
        
    print("Loading XGBoost Model...")
    update_pipeline_status("AI is generating Top 10 Predictions...", 80)
    model = joblib.load(MODEL_PATH)
    features_list = joblib.load(FEATURES_LIST_PATH)
    
    print("Connecting to database using sqlite3...")
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alphahunter.db')
    conn = sqlite3.connect(db_path)
    
    try:
        # Load the latest date available in the database
        print("Fetching latest market data...")
        
        # We fetch all OHLCV and Features, then group by ticker to get the latest
        df_ohlcv = pd.read_sql_query('SELECT ticker, date, open, high, low, close, volume, value FROM daily_ohlcv', conn)
        df_features = pd.read_sql_query('SELECT * FROM technical_features', conn)
        
        if df_ohlcv.empty or df_features.empty:
            print("No data available.")
            return
            
        df_merged = pd.merge(df_ohlcv, df_features, on=['ticker', 'date'], how='inner')
        df_merged['date'] = pd.to_datetime(df_merged['date'])
        
        # Sort by ticker and date for pattern detection (which relies on shifting)
        df_merged = df_merged.sort_values(['ticker', 'date'])
        
        # Calculate patterns
        df_merged['patterns'] = detect_candlestick_patterns(df_merged)
        
        # Get the latest row for each ticker
        df_latest = df_merged.groupby('ticker').tail(1).copy()
        
        # Drop rows with NaN features
        df_latest = df_latest.dropna()
        print(f"Generating predictions for {len(df_latest)} active stocks...")
        
        # Ensure columns match exactly what the model expects
        X_latest = df_latest[features_list]
        
        # Predict Probabilities
        # predict_proba returns [[prob_0, prob_1], ...]
        probs = model.predict_proba(X_latest)
        prob_up = probs[:, 1] # Probability of class 1 (Up)
        
        df_latest['prob_up'] = prob_up
        
        # Rank the stocks
        df_ranked = df_latest[['ticker', 'date', 'close', 'prob_up', 'patterns']].copy()
        df_ranked.sort_values(by='prob_up', ascending=False, inplace=True)
        df_ranked['rank'] = range(1, len(df_ranked) + 1)
        
        # Save predictions history for Learning Engine
        try:
            import json
            pred_date_str = df_ranked['date'].iloc[0].strftime('%Y-%m-%d')
            history_file = os.path.join(DATA_DIR, 'predictions_history.json')
            
            # Load existing
            history = []
            if os.path.exists(history_file):
                with open(history_file, 'r') as f:
                    try:
                        history = json.load(f)
                    except:
                        pass
            
            # Remove existing record for the same date if it exists
            history = [h for h in history if h.get('date') != pred_date_str]
            
            # Add new record
            day_predictions = []
            for idx, row in df_ranked.iterrows():
                day_predictions.append({
                    "ticker": row['ticker'],
                    "close": float(row['close']),
                    "prob_up": f"{round(float(row['prob_up']) * 100, 2)}%",
                    "patterns": str(row['patterns']) if row['patterns'] else "",
                    "rank": int(row['rank'])
                })
                
            history.append({
                "date": pred_date_str,
                "predictions": day_predictions
            })
            
            # Keep only last 100 dates of predictions history to manage storage size
            history = history[-100:]
            
            with open(history_file, 'w') as f:
                json.dump(history, f, indent=2)
                
            print(f"Appended EOD predictions for {pred_date_str} to predictions history.")
        except Exception as eh:
            print(f"Error logging predictions history: {eh}")
            
        # Format the output
        df_ranked['prob_up'] = (df_ranked['prob_up'] * 100).round(2).astype(str) + '%'
        
        print("\n==========================================")
        print("  ML RANKING ENGINE: TOP 10 BUYS FOR T+1  ")
        print("==========================================")
        print(df_ranked.head(10).to_string(index=False))
        print("==========================================\n")
        
        df_ranked.to_csv(OUTPUT_PATH, index=False)
        print(f"Full ranking saved to {OUTPUT_PATH}")
        
    except Exception as e:
        print(f"Error predicting: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    predict_tomorrow()

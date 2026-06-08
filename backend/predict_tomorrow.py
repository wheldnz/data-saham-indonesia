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
    conn = sqlite3.connect(db_path, timeout=30)
    
    try:
        # Load the latest date available in the database
        print("Fetching latest market data...")
        
        # Optimized: only load last 30 days per ticker (not full table)
        df_ohlcv = pd.read_sql_query('''
            SELECT o.ticker, o.date, o.open, o.high, o.low, o.close, o.volume, o.value
            FROM daily_ohlcv o
            INNER JOIN (
                SELECT ticker, MAX(date) as max_date FROM daily_ohlcv GROUP BY ticker
            ) m ON o.ticker = m.ticker AND o.date >= date(m.max_date, '-30 days')
        ''', conn)
        df_features = pd.read_sql_query('''
            SELECT f.* FROM technical_features f
            INNER JOIN (
                SELECT ticker, MAX(date) as max_date FROM technical_features GROUP BY ticker
            ) m ON f.ticker = m.ticker AND f.date >= date(m.max_date, '-30 days')
        ''', conn)
        
        if df_ohlcv.empty or df_features.empty:
            print("No data available.")
            return
            
        df_merged = pd.merge(df_ohlcv, df_features, on=['ticker', 'date'], how='inner')
        df_merged['date'] = pd.to_datetime(df_merged['date'])
        
        # Sort by ticker and date for pattern detection (which relies on shifting)
        df_merged = df_merged.sort_values(['ticker', 'date'])
        
        # Calculate patterns
        df_merged['patterns'] = detect_candlestick_patterns(df_merged)
        
        # --- Market-Neutral Feature Engineering ---
        # Harus sama persis dengan yang ada di prepare_ml_data.py
        # Fitur-fitur ini dihitung relatif terhadap median pasar pada hari yang sama.
        df_latest = df_merged.groupby('ticker').tail(1).copy()
        
        # return_1d: persentase perubahan harga dari open ke close
        df_latest['return_1d'] = (df_latest['close'] - df_latest['open']) / df_latest['open'].replace(0, float('nan'))
        
        # close_vs_sma20_pct: posisi close relatif terhadap SMA20
        df_latest['close_vs_sma20_pct'] = (df_latest['close'] - df_latest['sma_20']) / df_latest['sma_20'].replace(0, float('nan'))
        
        # volume_ratio: volume relatif terhadap SMA volume 20-hari
        df_latest['volume_ratio'] = df_latest['volume'] / df_latest['volume_sma_20'].replace(0, float('nan'))
        
        # rsi_relative: RSI14 relatif terhadap median RSI14 semua saham hari ini
        rsi_median = df_latest['rsi_14'].median()
        df_latest['rsi_relative'] = df_latest['rsi_14'] - rsi_median
        
        # is_active: semua saham di inference dianggap aktif (=1)
        df_latest['is_active'] = 1.0
        
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
            from datetime import timedelta
            
            # Tanggal data terakhir (mis. 2026-06-05 Jumat)
            last_data_date = df_ranked['date'].iloc[0]
            
            # Prediksi adalah untuk T+1 (hari kerja berikutnya)
            # Skip weekend: Sabtu → Senin (+2), Minggu → Senin (+1), hari kerja → +1
            next_day = last_data_date + timedelta(days=1)
            while next_day.weekday() >= 5:  # 5=Sabtu, 6=Minggu
                next_day += timedelta(days=1)
            pred_date_str = next_day.strftime('%Y-%m-%d')
            
            print(f"Data date: {last_data_date.strftime('%Y-%m-%d')} -> Prediction for: {pred_date_str}")
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
        
        # Override date ke T+1 (prediction_date) sebelum disimpan
        # Kolom 'date' berisi tanggal data terakhir (mis. Jumat 05-06),
        # tapi prediksi ini UNTUK hari berikutnya (Senin 08-06).
        try:
            from datetime import timedelta
            last_date = df_ranked['date'].iloc[0]
            next_bd = last_date + timedelta(days=1)
            while next_bd.weekday() >= 5:
                next_bd += timedelta(days=1)
            df_ranked['date'] = next_bd.strftime('%Y-%m-%d')
        except Exception:
            pass  # Keep original date if any error
        
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

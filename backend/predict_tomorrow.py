import sys
import os
import pandas as pd
import numpy as np
import joblib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.models.market_data import DailyOHLCV, TechnicalFeature
from pattern_scanner import detect_candlestick_patterns

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
MODEL_T1_PATH = os.path.join(DATA_DIR, 'xgb_model_t1.joblib')
MODEL_T3_PATH = os.path.join(DATA_DIR, 'xgb_model_t3.joblib')
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
    if not os.path.exists(MODEL_T1_PATH) or not os.path.exists(MODEL_T3_PATH) or not os.path.exists(FEATURES_LIST_PATH):
        print("Model files not found. Please run train_model.py first.")
        update_pipeline_status("Model files not found. Run training first.", 0, False)
        return
        
    print("Loading XGBoost Models (T+1 and T+3)...")
    update_pipeline_status("AI is generating Top 10 Predictions...", 80)
    model_t1 = joblib.load(MODEL_T1_PATH)
    model_t3 = joblib.load(MODEL_T3_PATH)
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
        
        df_broker = pd.read_sql_query('''
            SELECT b.ticker, b.date, b.net_foreign_value, b.acum_ratio, b.acum_score, b.acum_status
            FROM broker_summaries b
            INNER JOIN (
                SELECT ticker, MAX(date) as max_date FROM broker_summaries GROUP BY ticker
            ) m ON b.ticker = m.ticker AND b.date >= date(m.max_date, '-30 days')
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
        
        # Sort by ticker and date for pattern detection (which relies on shifting)
        df_merged = df_merged.sort_values(['ticker', 'date'])
        
        # Calculate patterns
        df_merged['patterns'] = detect_candlestick_patterns(df_merged)
        
        # --- Market-Neutral Feature Engineering ---
        # Harus sama persis dengan yang ada di prepare_ml_data.py
        # 1. return_1d (close-to-close percentage)
        df_merged['prev_close'] = df_merged.groupby('ticker')['close'].shift(1)
        df_merged['return_1d'] = np.where(
            df_merged['prev_close'] > 0,
            (df_merged['close'] / df_merged['prev_close'] - 1.0) * 100.0,
            0.0
        )
        
        # 2. close_vs_sma20_pct (close vs SMA20 percentage)
        df_merged['close_vs_sma20_pct'] = np.where(
            df_merged['sma_20'] > 0,
            (df_merged['close'] / df_merged['sma_20'] - 1.0) * 100.0,
            0.0
        )
        
        # 3. volume_ratio (volume vs volume_sma_20)
        df_merged['volume_ratio'] = np.where(
            df_merged['volume_sma_20'] > 0,
            df_merged['volume'] / df_merged['volume_sma_20'],
            1.0
        )
        
        # 4. rsi_relative (RSI14 relative to daily median)
        daily_rsi_median = df_merged.groupby('date')['rsi_14'].transform('median')
        df_merged['rsi_relative'] = df_merged['rsi_14'] - daily_rsi_median
        
        # 5. is_active (inference stocks default to 1.0)
        df_merged['is_active'] = 1.0

        # Filter out suspended, delisted, or stale stocks that did not trade on the latest market date
        # or had 0 trading volume on the latest day.
        max_market_date = df_merged['date'].max()
        df_latest = df_merged.groupby('ticker').tail(1).copy()
        df_latest = df_latest[(df_latest['date'] == max_market_date) & (df_latest['volume'] > 0)].copy()
        print(f"Latest market date in database: {max_market_date.strftime('%Y-%m-%d')}")
        print(f"Filtered out {len(df_merged.groupby('ticker').tail(1)) - len(df_latest)} suspended/stale/zero-volume stocks.")
        
        # Drop rows with NaN features
        df_latest = df_latest.dropna(subset=features_list)
        print(f"Generating predictions for {len(df_latest)} active stocks...")
        
        # Ensure columns match exactly what the model expects
        X_latest = df_latest[features_list]
        
        # Predict Probabilities
        probs_t1 = model_t1.predict_proba(X_latest)[:, 1]
        probs_t3 = model_t3.predict_proba(X_latest)[:, 1]
        
        # Blend ML probability with Bandarologi acum_score
        # formula: Blended_Score = 0.6 * Prob_ML + 0.4 * (acum_score / 100.0)
        # Note: acum_score defaults to 50.0 when not present
        acum_score_val = df_latest['acum_score'].values
        blended_prob_t1 = 0.6 * probs_t1 + 0.4 * (acum_score_val / 100.0)
        
        df_latest['prob_up'] = blended_prob_t1
        df_latest['prob_up_t3'] = probs_t3
        
        # Create ranking DataFrame for Blended
        df_ranked = df_latest[['ticker', 'date', 'close', 'prob_up', 'prob_up_t3', 'patterns']].copy()
        df_ranked['prob_up_raw'] = df_ranked['prob_up']
        df_ranked['prob_up_t3_raw'] = df_ranked['prob_up_t3']
        df_ranked.sort_values(by='prob_up', ascending=False, inplace=True)
        df_ranked['rank'] = range(1, len(df_ranked) + 1)
        
        # Create ranking DataFrame for Pure Technical (no blending)
        df_ranked_tech = df_latest[['ticker', 'date', 'close', 'patterns']].copy()
        df_ranked_tech['prob_up'] = probs_t1
        df_ranked_tech['prob_up_t3'] = probs_t3
        df_ranked_tech['prob_up_raw'] = probs_t1
        df_ranked_tech['prob_up_t3_raw'] = probs_t3
        df_ranked_tech.sort_values(by='prob_up', ascending=False, inplace=True)
        df_ranked_tech['rank'] = range(1, len(df_ranked_tech) + 1)
        
        # Determine prediction date based on current market time:
        # If it is a weekday and before 16:00 (4:00 PM) WIB, we are predicting for today's EOD close (T+0).
        # Otherwise (market closed or weekend), we are predicting for the next business day (T+1).
        import datetime as dt
        from datetime import timedelta
        
        last_data_date = df_ranked['date'].iloc[0]
        if isinstance(last_data_date, str):
            last_date_dt = dt.datetime.strptime(last_data_date, '%Y-%m-%d').date()
        elif isinstance(last_data_date, pd.Timestamp):
            last_date_dt = last_data_date.to_pydatetime().date()
        else:
            last_date_dt = last_data_date
            
        now_local = dt.datetime.now()
        if now_local.weekday() < 5 and now_local.hour < 16:
            # Predict for today (T+0)
            pred_date_str = last_date_dt.strftime('%Y-%m-%d')
        else:
            # Predict for next business day (T+1)
            next_bd = last_date_dt + timedelta(days=1)
            while next_bd.weekday() >= 5:
                next_bd += timedelta(days=1)
            pred_date_str = next_bd.strftime('%Y-%m-%d')
            
        # Save predictions history for Learning Engine (using Blended)
        try:
            import json
            print(f"Data date: {last_date_dt.strftime('%Y-%m-%d')} -> Prediction for: {pred_date_str}")
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
            
            # Add new record (only keep top 100 to save space and speed up learning engine)
            day_predictions = []
            for idx, row in df_ranked.head(100).iterrows():
                day_predictions.append({
                    "ticker": row['ticker'],
                    "close": float(row['close']),
                    "prob_up": f"{round(float(row['prob_up_raw']) * 100, 2)}%",
                    "prob_up_t3": f"{round(float(row['prob_up_t3_raw']) * 100, 2)}%",
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
            
        # Format the output for Blended
        df_ranked['prob_up'] = (df_ranked['prob_up'] * 100).round(2).astype(str) + '%'
        df_ranked['prob_up_t3'] = (df_ranked['prob_up_t3'] * 100).round(2).astype(str) + '%'
        
        # Format the output for Pure Technical
        df_ranked_tech['prob_up'] = (df_ranked_tech['prob_up'] * 100).round(2).astype(str) + '%'
        df_ranked_tech['prob_up_t3'] = (df_ranked_tech['prob_up_t3'] * 100).round(2).astype(str) + '%'
        
        # Override date ke prediction_date sebelum disimpan
        df_ranked['date'] = pred_date_str
        df_ranked_tech['date'] = pred_date_str
        
        print("\n==========================================")
        print("  ML RANKING ENGINE: TOP 10 BUYS FOR T+1  ")
        print("==========================================")
        print(df_ranked.head(10).to_string(index=False))
        print("==========================================\n")
        
        df_ranked.to_csv(OUTPUT_PATH, index=False)
        print(f"Full blended ranking saved to {OUTPUT_PATH}")
        
        TECH_OUTPUT_PATH = os.path.join(DATA_DIR, 'daily_ranking_tech.csv')
        df_ranked_tech.to_csv(TECH_OUTPUT_PATH, index=False)
        print(f"Full technical-only ranking saved to {TECH_OUTPUT_PATH}")


        
    except Exception as e:
        print(f"Error predicting: {e}")
        import sys
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    predict_tomorrow()

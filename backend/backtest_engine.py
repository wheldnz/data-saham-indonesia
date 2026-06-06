import sqlite3
import pandas as pd
import numpy as np
import joblib
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alphahunter.db')
MODEL_PATH = os.path.join(DATA_DIR, 'xgb_model_t1.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list.joblib')

def run_backtest(days_back=100):
    if not os.path.exists(MODEL_PATH) or not os.path.exists(FEATURES_LIST_PATH):
        return {"error": "Model or features DB not found. Please run update first."}
        
    model = joblib.load(MODEL_PATH)
    features_list = joblib.load(FEATURES_LIST_PATH)
    
    try:
        print("Loading dataset from CSV...")
        dataset_path = os.path.join(DATA_DIR, 'ml_dataset.csv')
        if not os.path.exists(dataset_path):
            return {"error": "ML dataset not found. Run update first."}
            
        df_merged = pd.read_csv(dataset_path)
        df_merged['date'] = pd.to_datetime(df_merged['date']).dt.strftime('%Y-%m-%d')
        
        # Filter for the last N dates
        unique_dates = sorted(df_merged['date'].unique(), reverse=True)
        if len(unique_dates) == 0:
            return {"error": "No data in dataset."}
            
        target_dates = unique_dates[:days_back+15]
        min_date = target_dates[-1]
        
        df_merged = df_merged[df_merged['date'] >= min_date].copy()
        print(f"Loaded {len(df_merged)} rows from {min_date}")
        
        df_merged = df_merged.dropna(subset=features_list)
        print(f"Clean size: {len(df_merged)}")
        
        if df_merged.empty:
            return {"error": "No valid feature rows found."}
            
        # Predict probabilities
        print("Predicting probabilities...")
        X = df_merged[features_list]
        probs = model.predict_proba(X)[:, 1]
        df_merged['prob_up'] = probs
        print("Ranking top 5...")
        
        # Rank top 5 per date
        df_merged['rank'] = df_merged.groupby('date')['prob_up'].rank(ascending=False, method='first')
        top5_df = df_merged[df_merged['rank'] <= 5].copy()
        
        # Get prices to calculate T+1, T+3, T+5, T+10
        prices_df = df_merged[['ticker', 'date', 'close']].sort_values(['ticker', 'date']).reset_index(drop=True)
        
        prices_df['close_t0'] = prices_df['close']
        prices_df['close_t1'] = prices_df.groupby('ticker')['close'].shift(-1)
        prices_df['close_t3'] = prices_df.groupby('ticker')['close'].shift(-3)
        prices_df['close_t5'] = prices_df.groupby('ticker')['close'].shift(-5)
        prices_df['close_t10'] = prices_df.groupby('ticker')['close'].shift(-10)
        
        # Merge top5 predictions with future prices
        merged = pd.merge(top5_df[['ticker', 'date', 'prob_up']], prices_df, on=['ticker', 'date'], how='left')
        
        # Calculate returns (Buy at Close T+0, Sell at Close T+N)
        merged['ret_t1'] = (merged['close_t1'] - merged['close_t0']) / merged['close_t0']
        merged['ret_t3'] = (merged['close_t3'] - merged['close_t0']) / merged['close_t0']
        merged['ret_t5'] = (merged['close_t5'] - merged['close_t0']) / merged['close_t0']
        merged['ret_t10'] = (merged['close_t10'] - merged['close_t0']) / merged['close_t0']
        
        # Aggregate daily portfolio return (average of top 5)
        daily_returns = merged.groupby('date').agg({
            'ret_t1': 'mean',
            'ret_t3': 'mean',
            'ret_t5': 'mean',
            'ret_t10': 'mean'
        }).reset_index()
        
        # Keep only the requested days_back dates
        daily_returns = daily_returns.sort_values('date', ascending=False).head(days_back).sort_values('date', ascending=True)
        
        # Calculate Metrics
        results = {}
        for horizon, col in zip(['T+1', 'T+3', 'T+5', 'T+10'], ['ret_t1', 'ret_t3', 'ret_t5', 'ret_t10']):
            ret_series = daily_returns[col].dropna()
            if len(ret_series) == 0:
                results[horizon] = {"win_rate": 0, "total_return": 0, "max_drawdown": 0}
                continue
                
            win_rate = (ret_series > 0).mean() * 100
            compounded_return = ((1 + ret_series).prod() - 1) * 100
            cum_ret = (1 + ret_series).cumprod()
            drawdown = (cum_ret / cum_ret.cummax() - 1).min() * 100
            
            results[horizon] = {
                "win_rate": round(win_rate, 2),
                "total_return": round(compounded_return, 2),
                "max_drawdown": round(drawdown, 2)
            }
            
        return {
            "days_back": days_back,
            "metrics": results
        }
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    res = run_backtest(100)
    print(res)

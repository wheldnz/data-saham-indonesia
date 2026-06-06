import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.models.market_data import DailyOHLCV, TechnicalFeature

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DATASET_PATH = os.path.join(DATA_DIR, 'ml_dataset.csv')

def prepare_ml_data():
    print("Connecting to database using sqlite3...")
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alphahunter.db')
    conn = sqlite3.connect(db_path)
    
    try:
        # Load all OHLCV data into a pandas dataframe
        print("Loading OHLCV data...")
        df_ohlcv = pd.read_sql_query('SELECT ticker, date, close, volume, value FROM daily_ohlcv', conn)
        
        # Load all Technical Features
        print("Loading Technical Features...")
        df_features = pd.read_sql_query('SELECT * FROM technical_features', conn)
        
        if df_ohlcv.empty or df_features.empty:
            print("Not enough data to prepare dataset.")
            return

        # Ensure datetime format
        df_ohlcv['date'] = pd.to_datetime(df_ohlcv['date'])
        df_features['date'] = pd.to_datetime(df_features['date'])
        
        # Merge OHLCV and Features on ticker and date
        print("Merging datasets...")
        df_merged = pd.merge(df_ohlcv, df_features, on=['ticker', 'date'], how='inner')
        
        # Sort by ticker and date
        df_merged.sort_values(by=['ticker', 'date'], inplace=True)
        
        # Calculate Target T+1 (Classification: 1 if tomorrow's close > today's close, else 0)
        print("Calculating Target T+1...")
        # Create column for tomorrow's close per ticker
        df_merged['next_close'] = df_merged.groupby('ticker')['close'].shift(-1)
        
        # Target = 1 if next_close > close
        df_merged['target_1d_up'] = (df_merged['next_close'] > df_merged['close']).astype(int)
        
        # Drop rows where we don't have tomorrow's data (the last row for each ticker)
        df_final = df_merged.dropna(subset=['next_close'])
        
        # Drop rows that have NaN in the technical features (early days of stocks)
        df_final = df_final.dropna()
        
        # Drop non-feature columns that aren't needed for ML (but keep ticker and date for reference)
        # We drop next_close because it's a future leak.
        df_final = df_final.drop(columns=['next_close'])
        
        print(f"Final dataset shape: {df_final.shape}")
        
        # Save to CSV
        print(f"Saving dataset to {DATASET_PATH}...")
        df_final.to_csv(DATASET_PATH, index=False)
        print("Dataset preparation complete!")
        
    except Exception as e:
        print(f"Error preparing ML data: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    prepare_ml_data()

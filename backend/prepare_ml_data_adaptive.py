import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.yfinance_client import yfinance_client

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DATASET_PATH = os.path.join(DATA_DIR, 'ml_dataset_adaptive.csv')

def prepare_ml_data_adaptive():
    print("Connecting to database using sqlite3...")
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alphahunter.db')
    conn = sqlite3.connect(db_path, timeout=30)

    try:
        # Load raw data
        print("Loading OHLCV data...")
        df_ohlcv = pd.read_sql_query(
            'SELECT ticker, date, open, high, low, close, volume, value FROM daily_ohlcv', conn
        )

        print("Loading Technical Features...")
        df_features = pd.read_sql_query(
            'SELECT * FROM technical_features', conn
        )

        print("Loading stock active status (for survivorship correction)...")
        df_stocks = pd.read_sql_query(
            'SELECT ticker, is_active FROM stocks', conn
        )
        inactive_tickers = set(
            df_stocks.loc[df_stocks['is_active'] == 0, 'ticker'].tolist()
        )
        print(f"  Found {len(inactive_tickers)} inactive/delisted tickers for correction.")

        if df_ohlcv.empty or df_features.empty:
            print("Not enough data to prepare dataset.")
            return

        # Filter out rows where volume is 0 or NaN (holidays, weekends, suspensions)
        df_ohlcv = df_ohlcv[df_ohlcv['volume'] > 0].copy()

        df_ohlcv['date']    = pd.to_datetime(df_ohlcv['date'])
        df_features['date'] = pd.to_datetime(df_features['date'])

        print("Merging datasets...")
        df_merged = pd.merge(df_ohlcv, df_features, on=['ticker', 'date'], how='inner')
        df_merged.sort_values(by=['ticker', 'date'], inplace=True)
        df_merged.reset_index(drop=True, inplace=True)

        # ─────────────────────────────────────────────────────────────
        # [1] Fetch and Calculate IHSG Macro Features
        # ─────────────────────────────────────────────────────────────
        print("Fetching IHSG (^JKSE) index historical data...")
        # Get start and end date from df_merged
        min_date_str = df_merged['date'].min().strftime('%Y-%m-%d')
        max_date_str = df_merged['date'].max().strftime('%Y-%m-%d')
        
        # We start yfinance fetch 150 days earlier to ensure rolling indicators (like SMA50) are populated
        start_fetch_dt = df_merged['date'].min() - pd.Timedelta(days=150)
        start_fetch_str = start_fetch_dt.strftime('%Y-%m-%d')
        
        client = yfinance_client
        df_ihsg = client.fetch_historical_data('^JKSE', start_fetch_str, max_date_str)
        
        if df_ihsg.empty:
            print("[Warning] IHSG data is empty! Creating fallback macro features.")
            df_merged['ihsg_trend'] = 1.0
            df_merged['ihsg_volatility'] = 1.0
        else:
            print("Calculating IHSG trend and volatility...")
            df_ihsg['Date'] = pd.to_datetime(df_ihsg['Date'])
            df_ihsg = df_ihsg.sort_values('Date').reset_index(drop=True)
            
            # SMA50 of IHSG Close
            df_ihsg['ihsg_close'] = df_ihsg['Close']
            df_ihsg['ihsg_sma50'] = df_ihsg['ihsg_close'].rolling(50).mean()
            df_ihsg['ihsg_trend'] = np.where(df_ihsg['ihsg_close'] > df_ihsg['ihsg_sma50'], 1.0, 0.0)
            
            # Volatility of IHSG (14-day rolling standard deviation of daily percentage return)
            df_ihsg['ihsg_return'] = df_ihsg['ihsg_close'].pct_change() * 100.0
            df_ihsg['ihsg_volatility'] = df_ihsg['ihsg_return'].rolling(14).std().fillna(1.0)
            
            # Filter to original date range of df_merged to avoid extra rows
            df_ihsg = df_ihsg[df_ihsg['Date'] >= df_merged['date'].min()]
            
            # Map back to df_merged
            ihsg_trend_map = df_ihsg.set_index('Date')['ihsg_trend'].to_dict()
            ihsg_vol_map = df_ihsg.set_index('Date')['ihsg_volatility'].to_dict()
            
            df_merged['ihsg_trend'] = df_merged['date'].map(ihsg_trend_map).fillna(1.0)
            df_merged['ihsg_volatility'] = df_merged['date'].map(ihsg_vol_map).fillna(1.0)
            print("  IHSG Macro features merged successfully.")

        # ─────────────────────────────────────────────────────────────
        # [2] Calculate Daily Market Breadth
        # ─────────────────────────────────────────────────────────────
        print("Calculating daily market breadth...")
        # Check if close is above sma_20 for each ticker-date
        df_merged['above_sma20'] = np.where(
            (df_merged['sma_20'] > 0) & (df_merged['close'] > df_merged['sma_20']),
            1.0, 0.0
        )
        
        # Calculate daily breadth
        daily_breadth = df_merged.groupby('date')['above_sma20'].mean() * 100.0
        df_merged['market_breadth'] = df_merged['date'].map(daily_breadth).fillna(50.0)
        df_merged.drop(columns=['above_sma20'], inplace=True)
        print("  Market breadth calculated successfully.")

        # ─────────────────────────────────────────────────────────────
        # [3] Target Creation (T+1 and T+3)
        # ─────────────────────────────────────────────────────────────
        print("Calculating Target T+1 and T+3...")
        df_merged['next_close'] = df_merged.groupby('ticker')['close'].shift(-1)
        df_merged['close_t3'] = df_merged.groupby('ticker')['close'].shift(-3)
        df_merged['target_1d_up'] = np.where(df_merged['next_close'].isna(), np.nan, (df_merged['next_close'] > df_merged['close']).astype(float))
        df_merged['target_3d_up'] = np.where(df_merged['close_t3'].isna(), np.nan, (df_merged['close_t3'] > df_merged['close']).astype(float))

        # Survivorship label correction
        if inactive_tickers:
            print(f"  Applying survivorship correction to {len(inactive_tickers)} inactive tickers...")
            corrected_count = 0
            for ticker in inactive_tickers:
                mask = df_merged['ticker'] == ticker
                ticker_indices = df_merged.index[mask].tolist()
                if len(ticker_indices) >= 5:
                    last_n = min(20, len(ticker_indices))
                    last_indices = ticker_indices[-last_n:]
                    df_merged.loc[last_indices, 'target_1d_up'] = 0.0
                    df_merged.loc[last_indices, 'target_3d_up'] = 0.0
                    corrected_count += last_n
            print(f"  Survivorship correction: {corrected_count} rows overridden to target=0 (T+1 and T+3).")

        df_final = df_merged.copy()
        df_final = df_final.drop(columns=['next_close', 'close_t3'])

        # ─────────────────────────────────────────────────────────────
        # [4] Engineering Market-Neutral Relative Features
        # ─────────────────────────────────────────────────────────────
        print("Engineering relative features...")
        df_final['prev_close'] = df_final.groupby('ticker')['close'].shift(1)
        df_final['return_1d'] = np.where(
            df_final['prev_close'] > 0,
            (df_final['close'] / df_final['prev_close'] - 1.0) * 100.0,
            0.0
        )
        df_final = df_final.drop(columns=['prev_close'])

        df_final['close_vs_sma20_pct'] = np.where(
            df_final['sma_20'] > 0,
            (df_final['close'] / df_final['sma_20'] - 1.0) * 100.0,
            0.0
        )

        df_final['volume_ratio'] = np.where(
            df_final['volume_sma_20'] > 0,
            df_final['volume'] / df_final['volume_sma_20'],
            1.0
        )

        daily_rsi_median = df_final.groupby('date')['rsi_14'].transform('median')
        df_final['rsi_relative'] = df_final['rsi_14'] - daily_rsi_median

        df_final['is_active'] = df_final['ticker'].apply(
            lambda t: 0.0 if t in inactive_tickers else 1.0
        )

        # ─────────────────────────────────────────────────────────────
        # [5] Final cleanup
        # ─────────────────────────────────────────────────────────────
        feature_cols_to_check = [c for c in df_final.columns if c not in ['target_1d_up', 'target_3d_up']]
        df_final = df_final.dropna(subset=feature_cols_to_check)
        df_final = df_final.replace([np.inf, -np.inf], np.nan)
        df_final = df_final.dropna(subset=feature_cols_to_check)

        print(f"\nFinal adaptive dataset shape: {df_final.shape}")
        print(f"Date range: {df_final['date'].min()} to {df_final['date'].max()}")
        print(f"Unique tickers: {df_final['ticker'].nunique()}")

        # Save dataset
        print(f"\nSaving adaptive dataset to {DATASET_PATH}...")
        df_final.to_csv(DATASET_PATH, index=False)
        print("Adaptive dataset preparation complete!")

    except Exception as e:
        import traceback
        print(f"Error preparing adaptive ML data: {e}")
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    prepare_ml_data_adaptive()

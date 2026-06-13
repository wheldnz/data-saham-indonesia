import sys
import os
import pandas as pd
import pandas_ta as ta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.models.market_data import DailyOHLCV, TechnicalFeature

def update_pipeline_status(message, progress, is_running=True):
    import json
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
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

def calculate_technical_features():
    print("Connecting to database...")
    db = SessionLocal()
    raw_conn = None
    
    try:
        # Delete the last 3 days of technical features to force recalculation of EOD values
        # (This handles updates for days that were partially ingested during Sesi 1)
        print("Cleaning up recent features to force fresh calculations...")
        from datetime import datetime, timedelta
        three_days_ago = (datetime.now() - timedelta(days=3)).date()
        db.query(TechnicalFeature).filter(TechnicalFeature.date >= three_days_ago).delete(synchronize_session=False)
        db.commit()

        from sqlalchemy import func
        # Get all distinct tickers
        tickers = [row[0] for row in db.query(DailyOHLCV.ticker).distinct().all()]
        print(f"Found {len(tickers)} tickers to process.")
        update_pipeline_status("Checking database for features...", 60)
        
        # Load max dates in bulk to optimize sync checks
        print("Checking feature synchronization status...")
        max_ohlcv_query = db.query(DailyOHLCV.ticker, func.max(DailyOHLCV.date)).group_by(DailyOHLCV.ticker).all()
        max_ohlcv_dates = {ticker: max_date for ticker, max_date in max_ohlcv_query}
        
        max_feat_query = db.query(TechnicalFeature.ticker, func.max(TechnicalFeature.date)).group_by(TechnicalFeature.ticker).all()
        max_feat_dates = {ticker: max_date for ticker, max_date in max_feat_query}
        
        # Open sqlite3 connection once for high-performance bulk insertions
        import sqlite3 as _sqlite3
        raw_conn = _sqlite3.connect(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alphahunter.db')
        )
        raw_cur = raw_conn.cursor()
        
        # Standardize dates to YYYY-MM-DD strings to ensure safe comparison across types
        max_ohlcv_dates_str = {}
        for t, d_val in max_ohlcv_dates.items():
            max_ohlcv_dates_str[t] = d_val.strftime('%Y-%m-%d') if hasattr(d_val, 'strftime') else str(d_val) if d_val else None
            
        max_feat_dates_str = {}
        for t, d_val in max_feat_dates.items():
            max_feat_dates_str[t] = d_val.strftime('%Y-%m-%d') if hasattr(d_val, 'strftime') else str(d_val) if d_val else None
            
        print("Loading all market data from database in bulk...")
        df_all = pd.read_sql_query("SELECT ticker, date, open, high, low, close, volume FROM daily_ohlcv ORDER BY date ASC", raw_conn)
        
        # Group by ticker in memory
        grouped = df_all.groupby('ticker')
        print(f"Grouped OHLCV data for {len(grouped)} tickers in memory.")
        
        for idx, ticker in enumerate(tickers):
            progress_pct = int(60 + (idx / len(tickers)) * 20)
            
            # Skip calculation if features are already up-to-date with OHLCV data
            max_ohlcv = max_ohlcv_dates_str.get(ticker)
            max_feat = max_feat_dates_str.get(ticker)
            if max_ohlcv is not None and max_ohlcv == max_feat:
                continue
                
            if idx % 50 == 0 or idx == len(tickers) - 1:
                print(f"Processing {idx}/{len(tickers)}: {ticker}...")
                update_pipeline_status(f"Calculating features for {ticker} ({idx}/{len(tickers)})...", progress_pct)
                
            if ticker not in grouped.groups:
                continue
                
            df_ticker_raw = grouped.get_group(ticker)
            if len(df_ticker_raw) < 20: # Need at least some data to calculate features
                continue
                
            df = df_ticker_raw.copy()
            df['date_dt'] = pd.to_datetime(df['date'])
            df.set_index(pd.DatetimeIndex(df['date_dt']), inplace=True)
            
            # --- Calculate Features using pandas-ta ---
            # Helper to safely extract series and avoid pandas-ta DataFrame fallbacks on short histories
            def get_series(val):
                if isinstance(val, pd.DataFrame) and len(val.columns) > 1:
                    return None
                return val

            # Trend: SMA
            df['sma_5'] = get_series(df.ta.sma(length=5))
            df['sma_20'] = get_series(df.ta.sma(length=20))
            df['sma_50'] = get_series(df.ta.sma(length=50))
            df['sma_200'] = get_series(df.ta.sma(length=200))
            
            # Momentum: RSI (7 and 14)
            df['rsi_7'] = get_series(df.ta.rsi(length=7))
            df['rsi_14'] = get_series(df.ta.rsi(length=14))
            
            # Momentum: MACD (12, 26, 9)
            macd = df.ta.macd(fast=12, slow=26, signal=9)
            if macd is not None and not macd.empty and 'MACD_12_26_9' in macd:
                df['macd'] = macd['MACD_12_26_9']
                df['macd_histogram'] = macd['MACDh_12_26_9']
                df['macd_signal'] = macd['MACDs_12_26_9']
            else:
                df['macd'] = None
                df['macd_histogram'] = None
                df['macd_signal'] = None
                
            # Momentum: Stochastic (14, 3, 3)
            stoch = df.ta.stoch(high=df['high'], low=df['low'], close=df['close'], k=14, d=3, smooth_k=3)
            if stoch is not None and not stoch.empty and 'STOCHk_14_3_3' in stoch:
                df['stoch_k'] = stoch['STOCHk_14_3_3']
                df['stoch_d'] = stoch['STOCHd_14_3_3']
            else:
                df['stoch_k'] = None
                df['stoch_d'] = None
            
            # Volatility: Bollinger Bands (20, 2)
            bbands = df.ta.bbands(length=20, std=2)
            if bbands is not None and not bbands.empty and len(bbands.columns) >= 3:
                # pandas-ta 0.4.71b0 names columns like BBL_20_2.0_2.0
                df['bb_lower'] = bbands.iloc[:, 0]
                df['bb_middle'] = bbands.iloc[:, 1]
                df['bb_upper'] = bbands.iloc[:, 2]
            else:
                df['bb_lower'] = None
                df['bb_middle'] = None
                df['bb_upper'] = None
                
            # Volatility: ATR (14)
            df['atr_14'] = get_series(df.ta.atr(length=14))
            
            # Trend Strength: ADX (14)
            adx = df.ta.adx(length=14)
            if adx is not None and not adx.empty and 'ADX_14' in adx:
                df['adx_14'] = adx['ADX_14']
            else:
                df['adx_14'] = None
                
            # Volume: OBV
            df['obv'] = get_series(df.ta.obv())
            
            # Volume: SMA 20
            df['volume_sma_20'] = get_series(df.ta.sma(close=df['volume'], length=20))
            
            # --- Save to Database using INSERT OR IGNORE ---
            # Menggunakan raw SQL INSERT OR IGNORE agar tidak crash
            # saat ada duplikat (bisa terjadi jika script dijalankan ulang).
            # Ini jauh lebih robust daripada SQLAlchemy ORM add_all().
            rows_to_insert = []
            max_feat_str = max_feat.strftime('%Y-%m-%d') if hasattr(max_feat, 'strftime') else str(max_feat) if max_feat else None
            for _, row in df.iterrows():
                r = row.where(pd.notnull(row), None)
                date_val = r['date']
                date_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val)
                
                # Only insert new feature rows to avoid SQLite processing massive duplicate histories
                if max_feat_str and date_str <= max_feat_str:
                    continue
                    
                rows_to_insert.append((
                    ticker, date_str,
                    r.get('sma_5'), r.get('sma_20'), r.get('sma_50'), r.get('sma_200'),
                    r.get('rsi_7'), r.get('rsi_14'),
                    r.get('stoch_k'), r.get('stoch_d'),
                    r.get('macd'), r.get('macd_signal'), r.get('macd_histogram'),
                    r.get('bb_upper'), r.get('bb_middle'), r.get('bb_lower'),
                    r.get('atr_14'), r.get('adx_14'), r.get('obv'), r.get('volume_sma_20')
                ))
            
            if rows_to_insert:
                raw_cur.executemany(
                    """INSERT OR IGNORE INTO technical_features
                       (ticker, date, sma_5, sma_20, sma_50, sma_200,
                        rsi_7, rsi_14, stoch_k, stoch_d,
                        macd, macd_signal, macd_histogram,
                        bb_upper, bb_middle, bb_lower,
                        atr_14, adx_14, obv, volume_sma_20)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    rows_to_insert
                )
                # Commit in batches of 50 to keep it fast
                if idx % 50 == 0 or idx == len(tickers) - 1:
                    raw_conn.commit()
                
        if raw_conn:
            raw_conn.commit()
            raw_conn.close()
            raw_conn = None
            
        print("Feature Calculation Pipeline Complete!")
        update_pipeline_status("Feature Calculation Complete!", 80)
        
    except Exception as e:
        db.rollback()
        if raw_conn:
            try:
                raw_conn.rollback()
                raw_conn.close()
            except:
                pass
        print(f"Error calculating features: {e}")
        import sys
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    calculate_technical_features()

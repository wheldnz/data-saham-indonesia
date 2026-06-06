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
    
    try:
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
        
        for idx, ticker in enumerate(tickers):
            progress_pct = int(60 + (idx / len(tickers)) * 20)
            
            # Skip calculation if features are already up-to-date with OHLCV data
            max_ohlcv = max_ohlcv_dates.get(ticker)
            max_feat = max_feat_dates.get(ticker)
            if max_ohlcv is not None and max_ohlcv == max_feat:
                continue
                
            if idx % 10 == 0 or idx == len(tickers) - 1:
                print(f"Processing {idx}/{len(tickers)}: {ticker}...")
                update_pipeline_status(f"Calculating features for {ticker} ({idx}/{len(tickers)})...", progress_pct)
                
            # Query all OHLCV for the ticker ordered by date ascending
            data = db.query(DailyOHLCV).filter(DailyOHLCV.ticker == ticker).order_by(DailyOHLCV.date.asc()).all()
            if len(data) < 20: # Need at least some data to calculate features
                continue
                
            # Convert to Pandas DataFrame
            df = pd.DataFrame([{
                'date': d.date,
                'open': d.open,
                'high': d.high,
                'low': d.low,
                'close': d.close,
                'volume': d.volume
            } for d in data])
            
            # Ensure index is datetime for pandas-ta
            df.set_index(pd.DatetimeIndex(df['date']), inplace=True)
            
            # --- Calculate Features using pandas-ta ---
            # Trend: SMA
            df['sma_5'] = df.ta.sma(length=5)
            df['sma_20'] = df.ta.sma(length=20)
            df['sma_50'] = df.ta.sma(length=50)
            df['sma_200'] = df.ta.sma(length=200)
            
            # Momentum: RSI (7 and 14)
            df['rsi_7'] = df.ta.rsi(length=7)
            df['rsi_14'] = df.ta.rsi(length=14)
            
            # Momentum: MACD (12, 26, 9)
            macd = df.ta.macd(fast=12, slow=26, signal=9)
            if macd is not None and not macd.empty:
                df['macd'] = macd['MACD_12_26_9']
                df['macd_histogram'] = macd['MACDh_12_26_9']
                df['macd_signal'] = macd['MACDs_12_26_9']
            else:
                df['macd'] = None
                df['macd_histogram'] = None
                df['macd_signal'] = None
                
            # Momentum: Stochastic (14, 3, 3)
            stoch = df.ta.stoch(high=df['high'], low=df['low'], close=df['close'], k=14, d=3, smooth_k=3)
            if stoch is not None and not stoch.empty:
                df['stoch_k'] = stoch['STOCHk_14_3_3']
                df['stoch_d'] = stoch['STOCHd_14_3_3']
            else:
                df['stoch_k'] = None
                df['stoch_d'] = None
            
            # Volatility: Bollinger Bands (20, 2)
            bbands = df.ta.bbands(length=20, std=2)
            if bbands is not None and not bbands.empty:
                # pandas-ta 0.4.71b0 names columns like BBL_20_2.0_2.0
                df['bb_lower'] = bbands.iloc[:, 0]
                df['bb_middle'] = bbands.iloc[:, 1]
                df['bb_upper'] = bbands.iloc[:, 2]
            else:
                df['bb_lower'] = None
                df['bb_middle'] = None
                df['bb_upper'] = None
                
            # Volatility: ATR (14)
            df['atr_14'] = df.ta.atr(length=14)
            
            # Trend Strength: ADX (14)
            adx = df.ta.adx(length=14)
            if adx is not None and not adx.empty:
                df['adx_14'] = adx['ADX_14']
            else:
                df['adx_14'] = None
                
            # Volume: OBV
            df['obv'] = df.ta.obv()
            
            # Volume: SMA 20
            df['volume_sma_20'] = df.ta.sma(close=df['volume'], length=20)
            
            # --- Save to Database ---
            features_to_add = []
            
            # Optimize DB queries: load all existing dates for this ticker at once
            existing_records = db.query(TechnicalFeature.date).filter(TechnicalFeature.ticker == ticker).all()
            existing_dates = set(row[0].strftime('%Y-%m-%d') for row in existing_records if row[0] is not None)
            
            for _, row in df.iterrows():
                r = row.where(pd.notnull(row), None)
                
                # Check date conversion safely
                date_val = r['date']
                date_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val)
                
                if date_str not in existing_dates:
                    feat = TechnicalFeature(
                        ticker=ticker,
                        date=r['date'],
                        sma_5=r.get('sma_5'),
                        sma_20=r.get('sma_20'),
                        sma_50=r.get('sma_50'),
                        sma_200=r.get('sma_200'),
                        rsi_7=r.get('rsi_7'),
                        rsi_14=r.get('rsi_14'),
                        stoch_k=r.get('stoch_k'),
                        stoch_d=r.get('stoch_d'),
                        macd=r.get('macd'),
                        macd_signal=r.get('macd_signal'),
                        macd_histogram=r.get('macd_histogram'),
                        bb_upper=r.get('bb_upper'),
                        bb_middle=r.get('bb_middle'),
                        bb_lower=r.get('bb_lower'),
                        atr_14=r.get('atr_14'),
                        adx_14=r.get('adx_14'),
                        obv=r.get('obv'),
                        volume_sma_20=r.get('volume_sma_20')
                    )
                    features_to_add.append(feat)
            
            if features_to_add:
                db.add_all(features_to_add)
                
            # Commit in batches of 50 to minimize disk I/O overhead
            if idx % 50 == 0 or idx == len(tickers) - 1:
                db.commit()
                
        print("Feature Calculation Pipeline Complete!")
        update_pipeline_status("Feature Calculation Complete!", 80)
        
    except Exception as e:
        db.rollback()
        print(f"Error calculating features: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    calculate_technical_features()

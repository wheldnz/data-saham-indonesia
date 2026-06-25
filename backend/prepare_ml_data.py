import sys
import os
import pandas as pd
import numpy as np

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
    conn = sqlite3.connect(db_path, timeout=30)

    try:
        # ─────────────────────────────────────────────────────────────
        # [1] Load raw data
        # ─────────────────────────────────────────────────────────────
        print("Loading OHLCV data...")
        df_ohlcv = pd.read_sql_query(
            'SELECT ticker, date, open, high, low, close, volume, value FROM daily_ohlcv', conn
        )

        print("Loading Technical Features...")
        df_features = pd.read_sql_query(
            'SELECT * FROM technical_features', conn
        )

        # ── FIX 3: Survivorship Correction ──────────────────────────
        # Load stock active status. Saham yang is_active=False
        # (suspend/delisting) tetap diikutsertakan dalam training,
        # dan baris-baris terakhir sebelum delisting mendapat
        # label koreksi (target=0) untuk mengajarkan model pola
        # bahaya mendekati delisting.
        print("Loading stock active status (for survivorship correction)...")
        df_stocks = pd.read_sql_query(
            'SELECT ticker, is_active FROM stocks', conn
        )
        inactive_tickers = set(
            df_stocks.loc[df_stocks['is_active'] == 0, 'ticker'].tolist()
        )
        print(f"  Found {len(inactive_tickers)} inactive/delisted tickers for correction.")
        # ─────────────────────────────────────────────────────────────

        if df_ohlcv.empty or df_features.empty:
            print("Not enough data to prepare dataset.")
            return

        # Filter out rows where volume is 0 or NaN (holidays, weekends, suspensions)
        # to ensure they are not treated as active trading days.
        df_ohlcv = df_ohlcv[df_ohlcv['volume'] > 0].copy()

        # ─────────────────────────────────────────────────────────────
        # [2] Merge OHLCV + Technical Features
        # ─────────────────────────────────────────────────────────────
        df_ohlcv['date']    = pd.to_datetime(df_ohlcv['date'])
        df_features['date'] = pd.to_datetime(df_features['date'])

        print("Merging datasets...")
        df_merged = pd.merge(df_ohlcv, df_features, on=['ticker', 'date'], how='inner')
        df_merged.sort_values(by=['ticker', 'date'], inplace=True)
        df_merged.reset_index(drop=True, inplace=True)

        # ─────────────────────────────────────────────────────────────
        # [3] Calculate Target T+1 and T+3
        # Target T+1 = 1 jika harga besok > harga hari ini, else 0.
        # Target T+3 = 1 jika harga T+3 > harga hari ini, else 0.
        # Kolom masa depan langsung dihapus setelah label dibuat
        # untuk menghindari future leakage.
        # ─────────────────────────────────────────────────────────────
        print("Calculating Target T+1 and T+3...")
        df_merged['next_close'] = df_merged.groupby('ticker')['close'].shift(-1)
        df_merged['close_t3'] = df_merged.groupby('ticker')['close'].shift(-3)
        df_merged['target_1d_up'] = np.where(df_merged['next_close'].isna(), np.nan, (df_merged['next_close'] > df_merged['close'] * 1.01).astype(float))
        df_merged['target_3d_up'] = np.where(df_merged['close_t3'].isna(), np.nan, (df_merged['close_t3'] > df_merged['close'] * 1.01).astype(float))

        # ── FIX 3: Survivorship label correction ────────────────────
        # Untuk saham yang sudah tidak aktif (suspend/delisting),
        # 20 baris terakhir per ticker di-override ke target=0.
        # Logika: pola menjelang delisting hampir selalu negatif,
        # mengajari model menghindari saham bermasalah.
        if inactive_tickers:
            print(f"  Applying survivorship correction to {len(inactive_tickers)} inactive tickers...")
            corrected_count = 0
            for ticker in inactive_tickers:
                mask = df_merged['ticker'] == ticker
                ticker_indices = df_merged.index[mask].tolist()
                if len(ticker_indices) >= 5:
                    # Override 20 baris terakhir (atau semua jika < 20)
                    last_n = min(20, len(ticker_indices))
                    last_indices = ticker_indices[-last_n:]
                    df_merged.loc[last_indices, 'target_1d_up'] = 0.0
                    df_merged.loc[last_indices, 'target_3d_up'] = 0.0
                    corrected_count += last_n
            print(f"  Survivorship correction: {corrected_count} rows overridden to target=0 (T+1 and T+3).")
        # ─────────────────────────────────────────────────────────────

        # Preserve all rows including the last day (where next_close/targets are NaN)
        # so that backtesting can resolve the trades of preceding days.
        df_final = df_merged.copy()

        # Hapus data masa depan — JANGAN pernah masuk ke fitur
        df_final = df_final.drop(columns=['next_close', 'close_t3'])

        # ─────────────────────────────────────────────────────────────
        # [4] FIX 2: Market-Neutral & Relative Features
        #
        # Tambah fitur yang mencerminkan kekuatan RELATIF saham
        # dibanding pasar, bukan nilai absolut. Ini mengurangi
        # cross-sectional correlation di mana model belajar pola
        # "IHSG hari ini naik" ketimbang pola individual saham.
        # ─────────────────────────────────────────────────────────────
        print("Engineering market-neutral relative features...")

        # 4a. Return 1 hari (%)
        #     Menggambarkan momentum harian saham itu sendiri.
        #     Dihitung dari data hari ini vs kemarin (backward-looking, aman).
        df_final['prev_close'] = df_final.groupby('ticker')['close'].shift(1)
        df_final['return_1d'] = np.where(
            df_final['prev_close'] > 0,
            (df_final['close'] / df_final['prev_close'] - 1.0) * 100.0,
            0.0
        )
        df_final = df_final.drop(columns=['prev_close'])

        # 4b. Posisi close terhadap SMA20 (%)
        #     Mengukur seberapa jauh harga dari rata-rata 20 hari.
        #     Nilai positif = di atas MA (bullish), negatif = di bawah.
        df_final['close_vs_sma20_pct'] = np.where(
            df_final['sma_20'] > 0,
            (df_final['close'] / df_final['sma_20'] - 1.0) * 100.0,
            0.0
        )

        # 4c. Volume ratio (volume hari ini / SMA volume 20 hari)
        #     Nilai > 1 = volume di atas rata-rata (unusual activity).
        #     Menggantikan volume absolut yang berkorelasi dengan market cap.
        df_final['volume_ratio'] = np.where(
            df_final['volume_sma_20'] > 0,
            df_final['volume'] / df_final['volume_sma_20'],
            1.0
        )

        # 4d. RSI relatif terhadap median pasar per tanggal
        #     Mengukur kekuatan momentum saham RELATIF terhadap
        #     semua saham lain pada tanggal yang sama.
        #     RSI > 0 = lebih kuat dari median pasar.
        daily_rsi_median = df_final.groupby('date')['rsi_14'].transform('median')
        df_final['rsi_relative'] = df_final['rsi_14'] - daily_rsi_median

        # 4e. is_active flag (sinyal fundamentals)
        df_final['is_active'] = df_final['ticker'].apply(
            lambda t: 0.0 if t in inactive_tickers else 1.0
        )

        print(f"  Added features: return_1d, close_vs_sma20_pct, volume_ratio, rsi_relative, is_active")

        # 4f. Multi-timeframe returns
        df_final['return_5d'] = df_final.groupby('ticker')['close'].pct_change(5) * 100
        df_final['return_10d'] = df_final.groupby('ticker')['close'].pct_change(10) * 100
        df_final['return_20d'] = df_final.groupby('ticker')['close'].pct_change(20) * 100

        # 4g. Bollinger Band %B (position within bands)
        df_final['bb_pct_b'] = np.where(
            (df_final['bb_upper'] - df_final['bb_lower']) > 0,
            (df_final['close'] - df_final['bb_lower']) / (df_final['bb_upper'] - df_final['bb_lower']),
            0.5
        )

        # 4h. MACD histogram momentum (change in histogram)
        df_final['macd_hist_change'] = df_final.groupby('ticker')['macd_histogram'].diff()

        # 4i. Volume surge 5-day (today vs 5-day avg)
        vol_5d_avg = df_final.groupby('ticker')['volume'].transform(
            lambda x: x.rolling(5, min_periods=1).mean()
        )
        df_final['volume_surge_5d'] = np.where(vol_5d_avg > 0, df_final['volume'] / vol_5d_avg, 1.0)

        # 4j. Gap analysis (open vs prev close)
        prev_close_gap = df_final.groupby('ticker')['close'].shift(1)
        df_final['gap_pct'] = np.where(
            prev_close_gap > 0,
            (df_final['open'] / prev_close_gap - 1) * 100,
            0.0
        )

        # 4k. Candle body ratio and shadow ratios
        total_range = df_final['high'] - df_final['low']
        df_final['body_ratio'] = np.where(
            total_range > 0,
            abs(df_final['close'] - df_final['open']) / total_range,
            0.0
        )
        df_final['upper_shadow_ratio'] = np.where(
            total_range > 0,
            (df_final['high'] - np.maximum(df_final['close'], df_final['open'])) / total_range,
            0.0
        )

        # 4l. ATR percentage (volatility normalized by price)
        df_final['atr_pct'] = np.where(
            df_final['close'] > 0,
            (df_final['atr_14'] / df_final['close']) * 100,
            0.0
        )

        # 4m. Bullish divergence signal (price down but RSI up over 5 days)
        price_chg_5d = df_final.groupby('ticker')['close'].pct_change(5)
        rsi_chg_5d = df_final.groupby('ticker')['rsi_14'].diff(5)
        df_final['bullish_divergence'] = np.where(
            (price_chg_5d < -0.02) & (rsi_chg_5d > 2), 1.0, 0.0
        )

        # 4n. Temporal / calendar features
        df_final['day_of_week'] = df_final['date'].dt.dayofweek  # 0=Mon, 4=Fri
        df_final['month'] = df_final['date'].dt.month
        df_final['is_month_end'] = df_final['date'].dt.is_month_end.astype(float)
        df_final['is_quarter_end'] = df_final['month'].isin([3, 6, 9, 12]).astype(float)

        print(f"  Added enhanced features: multi-TF returns, BB%B, MACD momentum, volume surge, gap, candle ratios, divergence, temporal")
        # ─────────────────────────────────────────────────────────────

        # ─────────────────────────────────────────────────────────────
        # [5] Final cleanup
        # ─────────────────────────────────────────────────────────────
        # Drop rows with NaN di technical features (awal historis data)
        feature_cols_to_check = [c for c in df_final.columns if c not in ['target_1d_up', 'target_3d_up']]
        df_final = df_final.dropna(subset=feature_cols_to_check)

        # Pastikan tidak ada inf
        df_final = df_final.replace([np.inf, -np.inf], np.nan)
        df_final = df_final.dropna(subset=feature_cols_to_check)

        print(f"\nFinal dataset shape: {df_final.shape}")
        print(f"Date range: {df_final['date'].min()} to {df_final['date'].max()}")
        print(f"Unique tickers: {df_final['ticker'].nunique()}")
        print(f"Target T+1 distribution:\n{df_final['target_1d_up'].value_counts(normalize=True).round(3)}")
        print(f"Target T+3 distribution:\n{df_final['target_3d_up'].value_counts(normalize=True).round(3)}")

        # ─────────────────────────────────────────────────────────────
        # [6] Save dataset
        # ─────────────────────────────────────────────────────────────
        print(f"\nSaving dataset to {DATASET_PATH}...")
        df_final.to_csv(DATASET_PATH, index=False)
        print("Dataset preparation complete!")

    except Exception as e:
        import traceback
        print(f"Error preparing ML data: {e}")
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    prepare_ml_data()

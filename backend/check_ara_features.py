import sqlite3
import pandas as pd

db_path = r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend\alphahunter.db"
conn = sqlite3.connect(db_path)

tickers = ['BABY', 'KBLV', 'FOLK', 'ASLI', 'LCKM', 'RGAS', 'RAAM', 'ATAP', 'FORU', 'ROCK', 'RMKO', 'RISE']

results = []
for t in tickers:
    cursor = conn.cursor()
    cursor.execute('''
        SELECT open, high, low, close, volume, value 
        FROM daily_ohlcv 
        WHERE ticker = ? AND date = '2026-06-09'
    ''', (t,))
    row_ohlcv = cursor.fetchone()
    
    cursor.execute('''
        SELECT rsi_14, sma_20, volume_sma_20, macd, macd_signal, macd_histogram
        FROM technical_features 
        WHERE ticker = ? AND date = '2026-06-09'
    ''', (t,))
    row_tech = cursor.fetchone()

    cursor.execute('''
        SELECT acum_status, acum_ratio 
        FROM broker_summaries 
        WHERE ticker = ? AND date = '2026-06-09'
    ''', (t,))
    row_broker = cursor.fetchone()
    
    if row_ohlcv:
        o, h, l, c, vol, val = row_ohlcv
        rsi = row_tech[0] if row_tech else None
        sma20 = row_tech[1] if row_tech else None
        vol_sma20 = row_tech[2] if row_tech else None
        vol_ratio = vol / vol_sma20 if vol_sma20 and vol_sma20 > 0 else 1.0
        
        acum_status = row_broker[0] if row_broker else "N/A"
        acum_ratio = row_broker[1] if row_broker else 0
        
        results.append({
            "ticker": t,
            "close": c,
            "volume": vol,
            "value_jt": round(val / 1000000, 2) if val else 0,
            "rsi": round(rsi, 2) if rsi else None,
            "vol_ratio": round(vol_ratio, 2),
            "acum_status": acum_status,
            "acum_ratio": round(acum_ratio, 3) if acum_ratio else 0
        })

df = pd.DataFrame(results)
print("=== OHLCV & TECHNICAL FEATURES FOR 2026-06-09 (PRE-ARA DAY) ===")
print(df.to_string(index=False))
conn.close()

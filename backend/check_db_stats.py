import sqlite3
import pandas as pd

db_path = r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend\alphahunter.db"
conn = sqlite3.connect(db_path)

print("Row counts in database tables:")
for table in ["daily_ohlcv", "technical_features", "broker_summaries"]:
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f" - {table}: {count:,} rows")

print("\nDate range for broker_summaries:")
min_date, max_date = conn.execute("SELECT MIN(date), MAX(date) FROM broker_summaries").fetchone()
print(f" - Min date: {min_date}, Max date: {max_date}")

print("\nCheck overlapping dates between all three tables:")
overlap_count = conn.execute("""
    SELECT COUNT(*) 
    FROM daily_ohlcv o
    INNER JOIN technical_features t ON o.ticker = t.ticker AND o.date = t.date
    INNER JOIN broker_summaries b ON o.ticker = b.ticker AND o.date = b.date
""").fetchone()[0]
print(f" - Overlapping rows: {overlap_count:,} rows")

print("\nSample records from broker_summaries:")
df_sample = pd.read_sql_query("SELECT * FROM broker_summaries LIMIT 5", conn)
print(df_sample)

conn.close()

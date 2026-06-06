import pandas_datareader.data as web
from datetime import datetime, timedelta

def test_stooq():
    ticker = "BBCA.ID"  # Stooq uses .ID for Indonesian stocks
    end = datetime.now()
    start = end - timedelta(days=5)
    
    print(f"Testing real data fetch from Stooq for {ticker}...")
    try:
        df = web.DataReader(ticker, 'stooq', start, end)
        if not df.empty:
            print("SUCCESS! Real data fetched from Stooq:")
            print(df.head())
        else:
            print("Failed. DataFrame is empty.")
    except Exception as e:
        print(f"Error fetching data from Stooq: {e}")

if __name__ == "__main__":
    test_stooq()

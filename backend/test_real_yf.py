import yfinance as yf
import pandas as pd
import time

def test_real_data():
    ticker = "BBCA.JK"
    print(f"Attempting to fetch real data for {ticker} without mock fallback...")
    
    try:
        stock = yf.Ticker(ticker)
        # Try fetching just the last 5 days
        df = stock.history(period="5d")
        
        if df.empty:
            print("Failed to get data. DataFrame is empty.")
        else:
            print("Successfully fetched real data!")
            print(df[['Open', 'High', 'Low', 'Close', 'Volume']])
    except Exception as e:
        print(f"Exception occurred: {e}")

if __name__ == "__main__":
    test_real_data()

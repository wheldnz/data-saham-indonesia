import requests
import pandas as pd
from typing import Optional
from datetime import datetime

class YFinanceClient:
    """Client wrapper for Yahoo Finance API specifically tailored for IDX stocks."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    @staticmethod
    def _format_ticker(ticker: str) -> str:
        if ticker.startswith('^'):
            return ticker
        if not ticker.endswith('.JK'):
            return f"{ticker}.JK"
        return ticker

    def fetch_historical_data(self, ticker: str, start_date: str, end_date: Optional[str] = None) -> pd.DataFrame:
        """Fetch historical OHLCV data using raw Yahoo Finance Chart API."""
        yf_ticker = self._format_ticker(ticker)
        
        try:
            # Convert dates to unix timestamps
            period1 = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
            if end_date:
                # Add 86399 seconds (23h 59m 59s) to make the end_date inclusive
                period2 = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp()) + 86399
            else:
                period2 = int(datetime.now().timestamp())
                
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{yf_ticker}?period1={period1}&period2={period2}&interval=1d"
            
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                print(f"Error fetching real data for {ticker}: HTTP {response.status_code}")
                return pd.DataFrame()
                
            data = response.json()
            result = data.get('chart', {}).get('result', [])
            
            if not result:
                return pd.DataFrame()
                
            timestamps = result[0].get('timestamp', [])
            indicators = result[0].get('indicators', {}).get('quote', [{}])[0]
            
            if not timestamps or not indicators:
                return pd.DataFrame()
                
            df = pd.DataFrame({
                'Date': [datetime.fromtimestamp(t).date() for t in timestamps],
                'Open': indicators.get('open', []),
                'High': indicators.get('high', []),
                'Low': indicators.get('low', []),
                'Close': indicators.get('close', []),
                'Volume': indicators.get('volume', [])
            })
            
            # Add Adj Close (simplification for MVP: just use Close if adjclose not in API response)
            adjclose = result[0].get('indicators', {}).get('adjclose', [{}])
            if adjclose:
                df['Adj Close'] = adjclose[0].get('adjclose', df['Close'])
            else:
                df['Adj Close'] = df['Close']
                
            # Drop rows with NaN (days where market was closed but returned null)
            df = df.dropna(subset=['Close'])
            return df
            
        except Exception as e:
            print(f"Exception fetching data for {ticker}: {e}")
            return pd.DataFrame()

    def fetch_company_info(self, ticker: str) -> dict:
        """Fetch general company information. We mock this for now to avoid strict rate limits."""
        return {
            "company_name": f"{ticker} Tbk.",
            "sector": "General",
            "sub_sector": "General",
            "market_cap": 0,
            "shares_outstanding": 0
        }

yfinance_client = YFinanceClient()

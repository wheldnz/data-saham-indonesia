import requests

def extract_unique_tickers():
    url = "https://gist.githubusercontent.com/SeptiyanAndika/2941e872798cea3bfb2e550106b8ad28/raw/index-saham.json"
    response = requests.get(url)
    data = response.json()
    
    unique_tickers = set()
    for category, tickers in data.items():
        if isinstance(tickers, list):
            for t in tickers:
                unique_tickers.add(t)
                
    print(f"Total unique tickers: {len(unique_tickers)}")
    print("Sample:", list(unique_tickers)[:10])

if __name__ == "__main__":
    extract_unique_tickers()

import requests

def test_raw_api():
    url = "https://query2.finance.yahoo.com/v8/finance/chart/BBCA.JK?interval=1d&range=5d"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    print(f"Fetching from {url}...")
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        result = data.get('chart', {}).get('result', [])
        if result:
            print("SUCCESS! Got data:")
            timestamps = result[0].get('timestamp', [])
            close_prices = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
            for t, c in zip(timestamps, close_prices):
                print(f"Timestamp: {t}, Close: {c}")
        else:
            print("Result is empty.")
    else:
        print("Failed to fetch.")
        print(response.text[:200])

if __name__ == "__main__":
    test_raw_api()

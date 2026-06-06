import requests

def test_idx_api():
    url = "https://idx.co.id/primary/ListedCompany/GetCompanyProfiles?length=9999"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
        'Referer': 'https://idx.co.id/'
    }
    
    print(f"Fetching from {url}...")
    try:
        response = requests.get(url, headers=headers)
        print("Status:", response.status_code)
        if response.status_code == 200:
            data = response.json()
            profiles = data.get('data', [])
            print(f"Found {len(profiles)} stocks!")
            if profiles:
                print("First stock:", profiles[0]['TickerSymbol'])
        else:
            print("Failed.")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_idx_api()

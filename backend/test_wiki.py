import pandas as pd
import requests

def test_wiki_scrape():
    url = "https://en.wikipedia.org/wiki/List_of_companies_listed_on_the_Indonesia_Stock_Exchange"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    print(f"Fetching from {url}...")
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            tables = pd.read_html(response.text)
            print(f"Found {len(tables)} tables")
            
            for i, df in enumerate(tables):
                if len(df) > 100:  
                    print(f"Table {i} has {len(df)} rows.")
                    print("Columns:", df.columns)
                    return df
        else:
            print("Failed, HTTP", response.status_code)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    df = test_wiki_scrape()
    if df is not None:
        print(df.head())

import yfinance as yf
import requests

def test_yf_with_agent():
    print("Testing yfinance with custom session and user-agent...")
    session = requests.Session()
    # Use a standard Chrome user-agent
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # Try downloading BBCA.JK
    try:
        data = yf.download("BBCA.JK", period="5d", session=session)
        if not data.empty:
            print("SUCCESS! Got real data using custom user-agent.")
            print(data)
        else:
            print("Failed. Dataframe is empty.")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_yf_with_agent()

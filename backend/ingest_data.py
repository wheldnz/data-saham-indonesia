import sys
import os
import time
import requests
import pandas as pd
import re
import io
from datetime import datetime, timedelta

# Ensure app can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.models.stock import Stock
from app.models.market_data import DailyOHLCV
from app.services.yfinance_client import yfinance_client

def fetch_all_idx_tickers() -> list[dict]:
    """Fetch all IDX stock tickers from Wikipedia, with fallback to the Gist."""
    wiki_url = 'https://id.wikipedia.org/wiki/Daftar_perusahaan_yang_tercatat_di_Bursa_Efek_Indonesia'
    gist_url = "https://gist.githubusercontent.com/SeptiyanAndika/2941e872798cea3bfb2e550106b8ad28/raw/index-saham.json"
    
    print("Fetching complete IDX ticker list from Wikipedia...")
    try:
        response = requests.get(wiki_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
        if response.status_code == 200:
            html = response.text
            dfs = pd.read_html(io.StringIO(html))
            tickers = []
            
            for df in dfs:
                code_col = None
                name_col = None
                sector_col = None
                
                for col in df.columns:
                    col_str = str(col).lower()
                    if 'kode' in col_str:
                        code_col = col
                    elif 'nama' in col_str:
                        name_col = col
                    elif 'sektor' in col_str or 'bidang' in col_str:
                        sector_col = col
                        
                if code_col is not None:
                    for _, row in df.iterrows():
                        raw_code = str(row[code_col]).strip()
                        # Extract 4-letter uppercase code
                        match = re.search(r'\b([A-Z]{4})\b', raw_code)
                        if match:
                            code = match.group(1)
                            name = str(row[name_col]).strip() if name_col is not None else f"{code} Tbk"
                            name = re.sub(r'\[\d+\]', '', name).strip()
                            sector = str(row[sector_col]).strip() if sector_col is not None else "General"
                            tickers.append({
                                "ticker": code,
                                "name": name,
                                "sector": sector
                            })
            if tickers:
                print(f"Successfully scraped {len(tickers)} tickers from Wikipedia.")
                # Deduplicate and sort by ticker code
                seen = set()
                deduped_tickers = []
                for t in tickers:
                    if t["ticker"] not in seen:
                        seen.add(t["ticker"])
                        deduped_tickers.append(t)
                deduped_tickers.sort(key=lambda x: x["ticker"])
                print(f"Unique tickers from Wikipedia: {len(deduped_tickers)}")
                return deduped_tickers
            
            print("No tickers parsed from Wikipedia, falling back to Gist...")
        else:
            print(f"Failed to fetch Wikipedia. Status code: {response.status_code}. Falling back to Gist...")
    except Exception as e:
        print(f"Error scraping Wikipedia: {e}. Falling back to Gist...")
        
    print(f"Fetching backup ticker list from {gist_url}...")
    try:
        response = requests.get(gist_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            unique_tickers = set()
            for category, tickers in data.items():
                if isinstance(tickers, list):
                    for t in tickers:
                        # Ensure we only include 4-letter tickers (exclude warrants/rights)
                        if len(t) == 4 and t.isalpha():
                            unique_tickers.add(t)
            
            return [{"ticker": t, "name": f"{t} Tbk", "sector": "General"} for t in sorted(list(unique_tickers))]
        else:
            print(f"Failed to fetch Gist. Status code: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching backup ticker list: {e}")
        return []

def seed_stocks(db, stocks_info: list[dict]):
    print(f"--- Seeding {len(stocks_info)} Stocks Master Data ---")
    added = 0
    for info in stocks_info:
        ticker = info["ticker"]
        existing = db.query(Stock).filter(Stock.ticker == ticker).first()
        if not existing:
            new_stock = Stock(
                ticker=ticker,
                yahoo_ticker=f"{ticker}.JK",
                company_name=info['name'][:255],
                sector=info['sector'][:100],
                sub_sector="General",
                market_cap_category="unknown",
                shares_outstanding=0,
                is_active=True
            )
            db.add(new_stock)
            added += 1
            if added % 100 == 0:
                print(f"Inserted {added} stocks...")
                db.commit()
    db.commit()
    print(f"Total new stocks added: {added}")

def update_pipeline_status(message, progress, is_running=True):
    import json
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    status_file = os.path.join(DATA_DIR, 'status.json')
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(status_file, 'w') as f:
            json.dump({
                "message": message,
                "progress": progress,
                "is_running": is_running
            }, f)
    except Exception as e:
        print(f"Error writing status file: {e}")

def ingest_daily_data(db, tickers: list[str]):
    from sqlalchemy import func
    
    print("Checking database for existing market data dates...")
    update_pipeline_status("Checking database for existing market data...", 5)
    
    # Query all max dates in one query to optimize startup check
    max_dates_query = db.query(DailyOHLCV.ticker, func.max(DailyOHLCV.date)).group_by(DailyOHLCV.ticker).all()
    max_dates = {ticker: max_date for ticker, max_date in max_dates_query}
    
    # fallback_start digunakan untuk saham yang belum punya data di DB.
    # 5 tahun dipilih agar mencakup siklus pasar penuh:
    #   2020: COVID crash (dominan class 0 / turun)
    #   2021: Post-COVID bull run (dominan class 1 / naik)
    #   2022: Rate hike global (koreksi bearish)
    #   2023-2024: Recovery & sideways
    # Siklus yang beragam = distribusi target lebih seimbang ~50/50
    fallback_start = (datetime.now() - timedelta(days=5 * 365)).date()
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    print(f"\n--- Ingesting Incremental Data up to {today_str} for {len(tickers)} stocks ---")
    
    for idx, ticker in enumerate(tickers):
        latest_date = max_dates.get(ticker)
        
        # Calculate dynamic start_date
        if latest_date:
            # Fetch from 7 days before to prevent missing candles from weekend/timezone offsets
            start_date = (latest_date - timedelta(days=7)).strftime('%Y-%m-%d')
        else:
            start_date = fallback_start.strftime('%Y-%m-%d')
            
        progress_pct = int(5 + (idx / len(tickers)) * 55)
        
        if idx % 10 == 0 or idx == len(tickers) - 1:
            print(f"Processed {idx}/{len(tickers)} stocks. Current: {ticker}...")
            update_pipeline_status(f"Ingesting {ticker} ({idx}/{len(tickers)})...", progress_pct)
            
        df = yfinance_client.fetch_historical_data(ticker, start_date=start_date, end_date=today_str)
        
        # Determine active status dynamically
        is_active = True
        latest_trade_date = None
        
        if df.empty:
            if latest_date:
                days_since_last_db_trade = (datetime.now().date() - latest_date).days
                if days_since_last_db_trade > 30:
                    is_active = False
                    latest_trade_date = latest_date
            else:
                is_active = False
        else:
            latest_trade_date = df['Date'].max()
            days_since_last_trade = (datetime.now().date() - latest_trade_date).days
            if days_since_last_trade > 30:
                is_active = False
                
        # Update stock active status in the database
        stock_record = db.query(Stock).filter(Stock.ticker == ticker).first()
        if stock_record:
            if stock_record.is_active != is_active:
                stock_record.is_active = is_active
                status_str = "Active" if is_active else "Inactive/Suspended"
                last_date_str = str(latest_trade_date) if latest_trade_date else "Never"
                print(f"Updated status of {ticker} to {status_str} (Last trade: {last_date_str})")
                
        if df.empty:
            db.commit()
            continue
            
        # Optimize DB queries: If we have a latest_date, query only dates >= start_date to check for duplicates in memory
        if latest_date:
            existing_records = db.query(DailyOHLCV.date).filter(
                DailyOHLCV.ticker == ticker,
                DailyOHLCV.date >= latest_date - timedelta(days=8)
            ).all()
            existing_dates = set(row[0] for row in existing_records if row[0] is not None)
        else:
            existing_dates = set()
            
        records_added = 0
        for _, row in df.iterrows():
            record_date = row['Date']
            # If the record_date is not in our set of existing dates, insert it
            if record_date not in existing_dates:
                ohlcv = DailyOHLCV(
                    ticker=ticker,
                    date=record_date,
                    open=row['Open'],
                    high=row['High'],
                    low=row['Low'],
                    close=row['Close'],
                    adj_close=row.get('Adj Close', row['Close']),
                    volume=row['Volume'],
                    value=row['Close'] * row['Volume'],
                    frequency=0,
                    foreign_buy=0,
                    foreign_sell=0
                )
                db.add(ohlcv)
                records_added += 1
                
        db.commit()
        # Sleep for a tiny duration (50ms) to maintain politeness without stalling the pipeline
        time.sleep(0.05)

if __name__ == "__main__":
    db = SessionLocal()
    try:
        # 1. Fetch all IDX stocks
        all_stocks = fetch_all_idx_tickers()
        
        # Fallback if fetch fails
        if not all_stocks:
            print("Fallback to major stocks...")
            all_stocks = [
                {"ticker": "BBCA", "name": "Bank Central Asia Tbk", "sector": "Finance"},
                {"ticker": "BBRI", "name": "Bank Rakyat Indonesia Tbk", "sector": "Finance"},
                {"ticker": "TLKM", "name": "Telkom Indonesia Tbk", "sector": "Infrastructure"},
                {"ticker": "BMRI", "name": "Bank Mandiri Tbk", "sector": "Finance"},
                {"ticker": "ASII", "name": "Astra International Tbk", "sector": "Consumer"}
            ]
            
        seed_stocks(db, all_stocks)
        
        # Extract just the ticker strings for historical download
        target_tickers = [s["ticker"] for s in all_stocks]
        
        print(f"Starting incremental ingestion for {len(target_tickers)} tickers...")
        ingest_daily_data(db, target_tickers)
        
        print("\nIngestion pipeline complete for all stocks!")
        update_pipeline_status("Ingestion Complete!", 60)
    finally:
        db.close()

import json
import hashlib
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.stock import Stock
from app.models.market_data import DailyOHLCV, BrokerSummary

# Broker list definition
INSTITUTIONAL_BROKERS = ["OD", "DX", "RX", "KZ", "BK", "CG", "CC", "ZP", "CS"]
RETAIL_BROKERS = ["YP", "XC", "PD", "NI", "KK", "AZ", "GR"]

def get_deterministic_value(seed: str, min_val: float, max_val: float) -> float:
    """Generates a stable, deterministic float value based on a seed string."""
    hash_val = int(hashlib.md5(seed.encode('utf-8')).hexdigest(), 16)
    val_range = max_val - min_val
    return min_val + (hash_val % 10000) / 10000.0 * val_range

def calculate_broker_summaries(db: Session, limit_days: int = 15):
    """
    Calculates EOD broker summaries and accumulation status for all active stocks.
    Generates realistic broker buy/sell lists and net foreign flows based on price-volume dynamics.
    Optimized: uses bulk pre-load instead of N+1 queries (1 SELECT per ticker vs 1 per row).
    """
    print(f"--- Running Bandarologi Engine: Seeding last {limit_days} days ---")
    active_stocks = db.query(Stock).filter(Stock.is_active == True).all()
    print(f"Processing Bandarologi for {len(active_stocks)} active stocks...")

    count = 0
    for stock in active_stocks:
        ticker = stock.ticker
        
        # Get latest DailyOHLCV records
        ohlcv_records = db.query(DailyOHLCV).filter(
            DailyOHLCV.ticker == ticker
        ).order_by(DailyOHLCV.date.desc()).limit(limit_days).all()

        # Reverse so we process in chronological order
        ohlcv_records.reverse()

        # --- OPTIMIZED: Bulk pre-load existing BrokerSummary records ---
        # Mengganti N+1 query (1 SELECT per baris) dengan 1 SELECT per ticker.
        # Untuk 937 saham × 15 hari, ini mengurangi dari 14,055 queries → 937 queries.
        dates_in_window = [r.date for r in ohlcv_records]
        existing_summaries = {}
        if dates_in_window:
            existing_qs = db.query(BrokerSummary).filter(
                BrokerSummary.ticker == ticker,
                BrokerSummary.date.in_(dates_in_window)
            ).all()
            existing_summaries = {s.date: s for s in existing_qs}

        for ohlcv in ohlcv_records:
            date = ohlcv.date
            close = ohlcv.close or 100.0
            open_p = ohlcv.open or close
            volume = ohlcv.volume or 0
            
            # Daily total value (in Rupiah)
            total_value = ohlcv.value or (volume * close)
            if total_value <= 0:
                # Default fallback for inactive or low volume days
                total_value = 500_000_000.0
            
            change_pct = (close - open_p) / open_p if open_p else 0
            
            # Deterministic noise based on ticker and date
            seed = f"{ticker}_{date.isoformat()}"
            h_val = int(hashlib.md5(seed.encode('utf-8')).hexdigest(), 16)
            noise = ((h_val % 200) - 100) / 1000.0 # -10% to +10%
            
            combined_metric = change_pct + noise
            
            # Classify accumulation status
            if combined_metric >= 0.04:
                status = "Big Accumulation"
                acum_ratio = get_deterministic_value(f"{seed}_ratio", 0.40, 0.65)
                acum_score = get_deterministic_value(f"{seed}_score", 85.0, 99.0)
            elif combined_metric >= 0.01:
                status = "Accumulation"
                acum_ratio = get_deterministic_value(f"{seed}_ratio", 0.15, 0.40)
                acum_score = get_deterministic_value(f"{seed}_score", 65.0, 84.0)
            elif combined_metric <= -0.04:
                status = "Big Distribution"
                acum_ratio = get_deterministic_value(f"{seed}_ratio", -0.65, -0.40)
                acum_score = get_deterministic_value(f"{seed}_score", 5.0, 24.0)
            elif combined_metric <= -0.01:
                status = "Distribution"
                acum_ratio = get_deterministic_value(f"{seed}_ratio", -0.40, -0.15)
                acum_score = get_deterministic_value(f"{seed}_score", 25.0, 44.0)
            else:
                status = "Neutral"
                acum_ratio = get_deterministic_value(f"{seed}_ratio", -0.10, 0.15)
                acum_score = get_deterministic_value(f"{seed}_score", 45.0, 64.0)

            # Generate top buyers and sellers
            # We deterministically select which brokers participate for this stock to simulate realistic market behaviors
            stock_hash = int(hashlib.md5(ticker.encode('utf-8')).hexdigest(), 16)
            
            # Select 4 buyers and 4 sellers from pool
            all_buyers = INSTITUTIONAL_BROKERS if "Accum" in status else RETAIL_BROKERS
            all_sellers = RETAIL_BROKERS if "Accum" in status else INSTITUTIONAL_BROKERS
            
            if status == "Neutral":
                # Mix them
                all_buyers = INSTITUTIONAL_BROKERS[:4] + RETAIL_BROKERS[:3]
                all_sellers = RETAIL_BROKERS[3:] + INSTITUTIONAL_BROKERS[4:]

            buyers = []
            sellers = []
            
            # Deterministically select brokers
            for i in range(5):
                b_idx = (stock_hash + i) % len(all_buyers)
                s_idx = (stock_hash + i + 7) % len(all_sellers)
                
                b_code = all_buyers[b_idx]
                s_code = all_sellers[s_idx]
                
                if b_code not in buyers:
                    buyers.append(b_code)
                if s_code not in sellers:
                    sellers.append(s_code)

            # Distribute net buy and sell amounts (in Rupiah)
            # Buyer net values are positive, Seller net values are negative
            net_traded_value = total_value * abs(acum_ratio)
            
            top_buyers_list = []
            top_sellers_list = []
            
            # Weight distribution: 45%, 25%, 15%, 10%, 5%
            weights = [0.45, 0.25, 0.15, 0.10, 0.05]
            
            for idx, b_code in enumerate(buyers[:5]):
                weight = weights[idx] if idx < len(weights) else 0.05
                top_buyers_list.append({
                    "broker": b_code,
                    "net_value": round(net_traded_value * weight, 1)
                })
                
            for idx, s_code in enumerate(sellers[:5]):
                weight = weights[idx] if idx < len(weights) else 0.05
                top_sellers_list.append({
                    "broker": s_code,
                    "net_value": round(-net_traded_value * weight, 1)
                })

            # Calculate Net Foreign Flow (Foreign Buy - Foreign Sell in IDR)
            if "Accum" in status:
                net_foreign = total_value * get_deterministic_value(f"{seed}_foreign", 0.05, 0.25)
            elif "Dist" in status:
                net_foreign = total_value * get_deterministic_value(f"{seed}_foreign", -0.25, -0.05)
            else:
                net_foreign = total_value * get_deterministic_value(f"{seed}_foreign", -0.05, 0.05)
            
            # Keep foreign flow rounded
            net_foreign = round(net_foreign, 1)

            # Update DailyOHLCV record with simulated foreign buy/sell
            # Convert IDR value to volume equivalent
            foreign_vol_net = net_foreign / close
            if foreign_vol_net > 0:
                ohlcv.foreign_buy = round(foreign_vol_net)
                ohlcv.foreign_sell = 0
            else:
                ohlcv.foreign_buy = 0
                ohlcv.foreign_sell = round(abs(foreign_vol_net))

            # --- OPTIMIZED: dict lookup instead of individual SELECT ---
            existing = existing_summaries.get(date)
            
            if existing:
                existing.top_buyers = json.dumps(top_buyers_list)
                existing.top_sellers = json.dumps(top_sellers_list)
                existing.net_foreign_value = net_foreign
                existing.acum_ratio = round(acum_ratio, 3)
                existing.acum_status = status
                existing.acum_score = round(acum_score, 1)
            else:
                new_summary = BrokerSummary(
                    ticker=ticker,
                    date=date,
                    top_buyers=json.dumps(top_buyers_list),
                    top_sellers=json.dumps(top_sellers_list),
                    net_foreign_value=net_foreign,
                    acum_ratio=round(acum_ratio, 3),
                    acum_status=status,
                    acum_score=round(acum_score, 1)
                )
                db.add(new_summary)

        count += 1
        if count % 100 == 0:
            print(f"Calculated broker summaries for {count} stocks...")
            db.commit()

    db.commit()
    print(f"Bandarologi calculations complete! Processed {count} stocks.")

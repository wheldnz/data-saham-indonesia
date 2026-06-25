import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Ensure parent directory is in path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
MODEL_T1_PATH = os.path.join(DATA_DIR, 'xgb_model_t1_adaptive.joblib')
MODEL_T3_PATH = os.path.join(DATA_DIR, 'xgb_model_t3_adaptive.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list_adaptive.joblib')

# In-memory benchmark cache
_benchmark_cache = {}

def get_benchmark_curve(start_date_str, end_date_str, initial_capital, cron_dates):
    """Fetches IHSG (^JKSE) historical index data and maps it to a baseline index."""
    cache_key = (start_date_str, end_date_str, initial_capital)
    if cache_key in _benchmark_cache:
        if len(_benchmark_cache[cache_key]) == len(cron_dates):
            return _benchmark_cache[cache_key]
            
    try:
        from app.services.yfinance_client import yfinance_client
        df_ihsg = yfinance_client.fetch_historical_data('^JKSE', start_date_str, end_date_str)
        
        benchmark_curve = []
        if df_ihsg.empty:
            for dt in cron_dates:
                benchmark_curve.append({"time": dt, "value": initial_capital})
            return benchmark_curve
            
        df_ihsg['date_str'] = pd.to_datetime(df_ihsg['Date']).dt.strftime('%Y-%m-%d')
        ihsg_map = {row.date_str: row.Close for row in df_ihsg.itertuples()}
        
        first_val = None
        for dt in cron_dates:
            if dt in ihsg_map:
                first_val = ihsg_map[dt]
                break
        
        if not first_val:
            first_val = list(ihsg_map.values())[0] if ihsg_map else 7000.0
            
        last_val = first_val
        for dt in cron_dates:
            close_val = ihsg_map.get(dt, last_val)
            if close_val is None or pd.isna(close_val):
                close_val = last_val
            last_val = close_val
            
            indexed_val = initial_capital * (close_val / first_val)
            benchmark_curve.append({"time": dt, "value": round(float(indexed_val), 2)})
            
        _benchmark_cache[cache_key] = benchmark_curve
        return benchmark_curve
    except Exception as e:
        print(f"[Backtest] Error fetching benchmark index: {e}")
        return [{"time": dt, "value": initial_capital} for dt in cron_dates]

def run_backtest_adaptive(days_back=100, initial_capital=100000000.0, strategy='T1_top5', stop_loss_pct=5.0, take_profit_pct=10.0, max_positions=5, min_liquidity=1000000000.0, dynamic_sizing=False, prob_threshold=0.0):
    """
    Simulates portfolio trading using predictions from the Adaptive model.
    Supports:
    - SL/TP, custom capital
    - Dynamic Position Sizing ( Point D: reducing slots in bearish / weak breadth regimes )
    - Minimum Probability Threshold ( Point C: only buys if probability exceeds cutoff )
    """
    from app.services import dataset_cache
    
    if dataset_cache.is_loaded_adaptive():
        print("[Backtest Adaptive] Using in-memory cached dataset.")
        df = dataset_cache.get_df_adaptive()
        prices_lookup = dataset_cache.get_prices_lookup_adaptive()
        features_list = dataset_cache.get_features_list_adaptive()
        if strategy == 'T1_top5' or strategy == 'T1_blended_top5':
            model = dataset_cache.get_model_t1_adaptive()
            holding_days = 1
        else:
            model = dataset_cache.get_model_t3_adaptive()
            holding_days = 3
    else:
        print("[Backtest Adaptive] Cache not loaded. Loading from disk...")
        if strategy == 'T1_top5' or strategy == 'T1_blended_top5':
            holding_days = 1
            model_path = MODEL_T1_PATH
        else:
            holding_days = 3
            model_path = MODEL_T3_PATH
            
        if not os.path.exists(model_path) or not os.path.exists(FEATURES_LIST_PATH):
            return {"error": "Adaptive Model files or features list not found. Run training first."}
            
        model = joblib.load(model_path)
        features_list = joblib.load(FEATURES_LIST_PATH)
        
        dataset_path = os.path.join(DATA_DIR, 'ml_dataset_adaptive.csv')
        if not os.path.exists(dataset_path):
            return {"error": "Adaptive ML dataset file not found."}
            
        df = pd.read_csv(dataset_path)
        df['date'] = pd.to_datetime(df['date'])
        df.sort_values(by=['date', 'ticker'], inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # Load prices lookup dictionary
        prices_df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'ihsg_trend']].copy()
        prices_df['date_str'] = prices_df['date'].dt.strftime('%Y-%m-%d')
        
        prices_lookup = {}
        for row in prices_df.itertuples():
            if row.ticker not in prices_lookup:
                prices_lookup[row.ticker] = {}
            prices_lookup[row.ticker][row.date_str] = {
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "ihsg_trend": float(row.ihsg_trend)
            }
            
    if dataset_cache.is_loaded_adaptive():
        all_dates = dataset_cache.get_all_dates_adaptive()
    else:
        all_dates = sorted(df['date'].unique())
        
    if len(all_dates) < days_back:
        days_back = len(all_dates)
        
    # Get simulated date range
    test_dates = all_dates[-days_back:]
    start_date = test_dates[0]
    end_date = test_dates[-1]
    
    start_date_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else str(start_date)
    end_date_str = end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else str(end_date)
    
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)
    
    cron_dates = [d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d) for d in test_dates]
    
    # Run ML predictions for test dates
    start_idx = df['date'].searchsorted(start_dt)
    end_idx = df['date'].searchsorted(end_dt + pd.Timedelta(days=1))
    df_test = df.iloc[start_idx:end_idx].copy()
    df_test = df_test.dropna(subset=features_list)
    
    # Apply liquidity filter (minimum Rp 1 Billion is mandatory)
    effective_liquidity = min_liquidity
    df_test = df_test[df_test['value'] >= effective_liquidity].copy()
    
    if df_test.empty:
        return {"error": "No data matching strategy conditions in backtest period."}
        
    df_test['date_str'] = df_test['date'].dt.strftime('%Y-%m-%d')
    
    # Load Bandarologi data for blending
    if strategy == 'T1_blended_top5':
        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alphahunter.db')
            conn = sqlite3.connect(db_path, timeout=30)
            test_dates_str = [d.strftime('%Y-%m-%d') for d in test_dates]
            placeholders = ','.join('?' for _ in test_dates_str)
            df_broker = pd.read_sql_query(f'''
                SELECT ticker, date, acum_score, acum_status 
                FROM broker_summaries 
                WHERE date IN ({placeholders})
            ''', conn, params=test_dates_str)
            conn.close()
            
            df_broker['date_str'] = pd.to_datetime(df_broker['date']).dt.strftime('%Y-%m-%d')
            df_test = pd.merge(df_test, df_broker[['ticker', 'date_str', 'acum_score', 'acum_status']], on=['ticker', 'date_str'], how='left')
            df_test['acum_score'] = df_test['acum_score'].fillna(50.0)
            df_test['acum_status'] = df_test['acum_status'].fillna('Neutral')
        except Exception as e_br:
            print(f"[Backtest] Error loading broker summaries: {e_br}")
            df_test['acum_score'] = 50.0
            df_test['acum_status'] = 'Neutral'
            
    X = df_test[features_list].values
    probs_tech = model.predict_proba(X)[:, 1]
    
    if strategy == 'T1_blended_top5':
        acum_score_val = df_test['acum_score'].values
        df_test['prob_up'] = 0.6 * probs_tech + 0.4 * (acum_score_val / 100.0)
    else:
        df_test['prob_up'] = probs_tech
    
    # Group candidates by date (include macro properties)
    df_test_small = df_test[['ticker', 'date_str', 'prob_up', 'close', 'ihsg_trend', 'market_breadth']].sort_values(by='prob_up', ascending=False)
    tickers = df_test_small['ticker'].tolist()
    date_strs = df_test_small['date_str'].tolist()
    prob_ups = df_test_small['prob_up'].tolist()
    closes = df_test_small['close'].tolist()
    ihsg_trends = df_test_small['ihsg_trend'].tolist()
    market_breadths = df_test_small['market_breadth'].tolist()
    
    candidates_by_date = {}
    for i in range(len(tickers)):
        d = date_strs[i]
        if d not in candidates_by_date:
            candidates_by_date[d] = []
        candidates_by_date[d].append({
            "ticker": tickers[i],
            "prob_up": float(prob_ups[i]),
            "close": float(closes[i]),
            "ihsg_trend": float(ihsg_trends[i]),
            "market_breadth": float(market_breadths[i])
        })
        
    # Initialize portfolio state
    cash = initial_capital
    portfolio_value = initial_capital
    equity_curve = []
    trades_log = []
    active_trades = []
    
    for today_str in cron_dates:
        # Check if today_str is today's date and the market is still open/not fully closed
        from datetime import datetime, timezone, timedelta
        tz_wib = timezone(timedelta(hours=7))
        now_wib = datetime.now(timezone.utc).astimezone(tz_wib)
        today_wib_str = now_wib.strftime('%Y-%m-%d')
        
        is_today_incomplete = False
        if today_str == today_wib_str:
            if now_wib.hour < 16 or (now_wib.hour == 16 and now_wib.minute < 15):
                is_today_incomplete = True

        # 1. Update Open Positions & Check Exits
        still_active = []
        for t in active_trades:
            if is_today_incomplete:
                today_prices = prices_lookup.get(t["ticker"], {}).get(today_str)
                if today_prices:
                    t["last_close"] = today_prices["close"]
                still_active.append(t)
                continue

            t["days_held"] += 1
            ticker = t["ticker"]
            shares = t["shares"]
            buy_price = t["entry_price"]
            
            today_prices = prices_lookup.get(ticker, {}).get(today_str)
            if not today_prices:
                # If stock is suspended or data missing, check if holding period expired
                if t["days_held"] >= holding_days:
                    # Force close at last known close price
                    exit_price = t["last_close"]
                    exit_value = shares * exit_price
                    cash += exit_value
                    profit_nominal = exit_value - (shares * buy_price)
                    trades_log.append({
                        "ticker": ticker,
                        "entry_date": t["entry_date"],
                        "exit_date": today_str,
                        "entry_price": round(buy_price, 2),
                        "exit_price": round(exit_price, 2),
                        "return_pct": round((exit_price / buy_price - 1) * 100, 2),
                        "profit_nominal": round(profit_nominal, 2),
                        "status": "SUSPENDED_FORCE_CLOSE",
                        "days_held": t["days_held"]
                    })
                else:
                    still_active.append(t)
                continue
                
            low_p = today_prices["low"]
            high_p = today_prices["high"]
            close_p = today_prices["close"]
            open_p = today_prices["open"]
            
            t["last_close"] = close_p
            sl_price = t["sl_price"]
            tp_price = t["tp_price"]
            
            # Check Stop Loss
            if stop_loss_pct > 0 and low_p <= sl_price:
                exit_price = min(sl_price, open_p)
                exit_value = shares * exit_price
                cash += exit_value
                profit_nominal = exit_value - (shares * buy_price)
                trades_log.append({
                    "ticker": ticker,
                    "entry_date": t["entry_date"],
                    "exit_date": today_str,
                    "entry_price": round(buy_price, 2),
                    "exit_price": round(exit_price, 2),
                    "return_pct": round((exit_price / buy_price - 1) * 100, 2),
                    "profit_nominal": round(profit_nominal, 2),
                    "status": "SL",
                    "days_held": t["days_held"]
                })
            # Check Take Profit
            elif take_profit_pct > 0 and high_p >= tp_price:
                exit_price = max(tp_price, open_p)
                exit_value = shares * exit_price
                cash += exit_value
                profit_nominal = exit_value - (shares * buy_price)
                trades_log.append({
                    "ticker": ticker,
                    "entry_date": t["entry_date"],
                    "exit_date": today_str,
                    "entry_price": round(buy_price, 2),
                    "exit_price": round(exit_price, 2),
                    "return_pct": round((exit_price / buy_price - 1) * 100, 2),
                    "profit_nominal": round(profit_nominal, 2),
                    "status": "TP",
                    "days_held": t["days_held"]
                })
            # Check Holding Period Expiry
            elif t["days_held"] >= holding_days:
                exit_value = shares * close_p
                cash += exit_value
                profit_nominal = exit_value - (shares * buy_price)
                trades_log.append({
                    "ticker": ticker,
                    "entry_date": t["entry_date"],
                    "exit_date": today_str,
                    "entry_price": round(buy_price, 2),
                    "exit_price": round(close_p, 2),
                    "return_pct": round((close_p / buy_price - 1) * 100, 2),
                    "profit_nominal": round(profit_nominal, 2),
                    "status": "EXPIRED",
                    "days_held": t["days_held"]
                })
            else:
                still_active.append(t)
                
        active_trades = still_active
        
        # Calculate valuation
        holdings_value = 0.0
        for t in active_trades:
            ticker = t["ticker"]
            today_prices = prices_lookup.get(ticker, {}).get(today_str)
            current_price = today_prices["close"] if today_prices else t.get("last_close", t["entry_price"])
            holdings_value += t["shares"] * current_price
            
        portfolio_value = cash + holdings_value
        equity_curve.append({"time": today_str, "value": round(portfolio_value, 2)})
        
        # 2. Enter New Trades
        if is_today_incomplete:
            continue
        # Get today's macro conditions from the first candidate
        today_candidates = candidates_by_date.get(today_str, [])
        if today_candidates:
            first_cand = today_candidates[0]
            ihsg_trend = first_cand.get("ihsg_trend", 1.0)
            market_breadth = first_cand.get("market_breadth", 50.0)
        else:
            ihsg_trend = 1.0
            market_breadth = 50.0
            
        # Determine dynamic max positions (Point D)
        if dynamic_sizing:
            # Bearish trend (IHSG < SMA50) or extremely weak breadth (< 35% stocks above SMA20)
            if ihsg_trend == 0.0 or market_breadth < 35.0:
                effective_max_positions = 1  # Restrict to 1 defensive position
            else:
                effective_max_positions = max_positions
        else:
            effective_max_positions = max_positions
            
        slots_available = effective_max_positions - len(active_trades)
        if slots_available > 0 and today_candidates:
            # Apply probability threshold (Point C)
            if prob_threshold > 0.0:
                valid_candidates = [c for c in today_candidates if c["prob_up"] >= prob_threshold]
            else:
                valid_candidates = today_candidates
                
            held_tickers = set(t["ticker"] for t in active_trades)
            valid_candidates = [c for c in valid_candidates if c["ticker"] not in held_tickers]
            
            to_buy = valid_candidates[:slots_available]
            if to_buy:
                buy_power_per_slot = portfolio_value / effective_max_positions
                total_needed = buy_power_per_slot * len(to_buy)
                if total_needed > cash:
                    buy_power_per_slot = cash / len(to_buy)
                    
                for c in to_buy:
                    ticker = c["ticker"]
                    buy_price = c["close"]
                    if buy_price <= 0:
                        continue
                        
                    shares = buy_power_per_slot / buy_price
                    cash -= buy_power_per_slot
                    
                    sl_price = buy_price * (1 - stop_loss_pct / 100) if stop_loss_pct > 0 else 0.0
                    tp_price = buy_price * (1 + take_profit_pct / 100) if take_profit_pct > 0 else float('inf')
                    
                    active_trades.append({
                        "ticker": ticker,
                        "entry_date": today_str,
                        "entry_price": buy_price,
                        "shares": shares,
                        "days_held": 0,
                        "last_close": buy_price,
                        "sl_price": sl_price,
                        "tp_price": tp_price
                    })
                    
    # forced exit
    final_date = cron_dates[-1]
    for t in active_trades:
        ticker = t["ticker"]
        today_prices = prices_lookup.get(ticker, {}).get(final_date)
        exit_price = today_prices["close"] if today_prices else t.get("last_close", t["entry_price"])
        exit_value = t["shares"] * exit_price
        profit_nominal = exit_value - (t["shares"] * t["entry_price"])
        
        trades_log.append({
            "ticker": ticker,
            "entry_date": t["entry_date"],
            "exit_date": final_date,
            "entry_price": round(t["entry_price"], 2),
            "exit_price": round(exit_price, 2),
            "return_pct": round((exit_price / t["entry_price"] - 1) * 100, 2),
            "profit_nominal": round(profit_nominal, 2),
            "status": "OPEN",
            "days_held": t["days_held"]
        })
        
    total_trades = len(trades_log)
    wins = sum(1 for t in trades_log if t["return_pct"] > 0)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    compounded_return = (portfolio_value / initial_capital - 1) * 100
    
    # Max Drawdown
    values = [pt["value"] for pt in equity_curve]
    peak = values[0]
    max_dd = 0.0
    for val in values:
        if val > peak:
            peak = val
        dd = (val / peak - 1) * 100
        if dd < max_dd:
            max_dd = dd
            
    # Sharpe Ratio
    daily_pct_changes = []
    for t in range(1, len(values)):
        daily_pct_changes.append(values[t] / values[t-1] - 1)
        
    sharpe = 0.0
    if len(daily_pct_changes) > 1:
        mean_ret = np.mean(daily_pct_changes)
        std_ret = np.std(daily_pct_changes)
        if std_ret > 0:
            sharpe = (mean_ret / std_ret) * np.sqrt(252)
            
    benchmark_curve = get_benchmark_curve(start_date_str, end_date_str, initial_capital, cron_dates)
    
    return {
        "strategy": strategy,
        "days_back": days_back,
        "final_value": round(portfolio_value, 2),
        "total_return_pct": round(compounded_return, 2),
        "win_rate": round(win_rate, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "total_trades": total_trades,
        "equity_curve": equity_curve,
        "benchmark_curve": benchmark_curve,
        "trades": trades_log
    }

if __name__ == "__main__":
    print("=== TESTING ADAPTIVE BACKTEST ENGINE ===")
    
    # 1. Run Standard T+1 Blended
    print("\n[Case 1] Standard T+1 Blended (No Threshold, No Dynamic Sizing):")
    res1 = run_backtest_adaptive(days_back=50, strategy='T1_blended_top5', max_positions=5, stop_loss_pct=3, take_profit_pct=6)
    print(f"  Return: {res1.get('total_return_pct')}%")
    print(f"  Win Rate: {res1.get('win_rate')}%")
    print(f"  Max Drawdown: {res1.get('max_drawdown_pct')}%")
    print(f"  Total Trades: {res1.get('total_trades')}")
    
    # 2. Run Adaptive T+1 Blended (with threshold + dynamic sizing)
    print("\n[Case 2] Adaptive T+1 Blended (Threshold 58%, Dynamic Sizing Enabled):")
    res2 = run_backtest_adaptive(days_back=50, strategy='T1_blended_top5', max_positions=5, stop_loss_pct=3, take_profit_pct=6, dynamic_sizing=True, prob_threshold=0.58)
    print(f"  Return: {res2.get('total_return_pct')}%")
    print(f"  Win Rate: {res2.get('win_rate')}%")
    print(f"  Max Drawdown: {res2.get('max_drawdown_pct')}%")
    print(f"  Total Trades: {res2.get('total_trades')}")
    
    # 3. Run Adaptive T+1 Blended Concentrated (Threshold 55%, Dynamic Sizing Enabled, 2 slots)
    print("\n[Case 3] Adaptive Concentrated Blended (Slots=2, Threshold 55%, Dynamic Sizing Enabled):")
    res3 = run_backtest_adaptive(days_back=50, strategy='T1_blended_top5', max_positions=2, stop_loss_pct=3, take_profit_pct=6, dynamic_sizing=True, prob_threshold=0.55)
    print(f"  Return: {res3.get('total_return_pct')}%")
    print(f"  Win Rate: {res3.get('win_rate')}%")
    print(f"  Max Drawdown: {res3.get('max_drawdown_pct')}%")
    print(f"  Total Trades: {res3.get('total_trades')}")

import os
import sys
import json
import joblib
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime

# Setup paths
BACKEND_DIR = r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend"
DATA_DIR = os.path.join(BACKEND_DIR, 'data')
MODEL_T1_PATH = os.path.join(DATA_DIR, 'xgb_model_t1_adaptive.joblib') # Check adaptive paths!
MODEL_T3_PATH = os.path.join(DATA_DIR, 'xgb_model_t3_adaptive.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list_adaptive.joblib')
DATASET_PATH = os.path.join(DATA_DIR, 'ml_dataset_adaptive.csv')
DB_PATH = os.path.join(BACKEND_DIR, 'alphahunter.db')

print("--- Pre-loading Data and Models ---")

# Load models and features list
model_t1 = joblib.load(MODEL_T1_PATH)
model_t3 = joblib.load(MODEL_T3_PATH)
features_list = joblib.load(FEATURES_LIST_PATH)

# Load dataset
df = pd.read_csv(DATASET_PATH)
df['date'] = pd.to_datetime(df['date'])
df.sort_values(by=['date', 'ticker'], inplace=True)
df.reset_index(drop=True, inplace=True)

# Build prices lookup
prices_df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'ihsg_trend', 'value']].copy()
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
        "ihsg_trend": float(row.ihsg_trend),
        "value": float(row.value)
    }

all_dates = sorted(df['date'].unique())
days_back = 100
test_dates = all_dates[-days_back:]
start_date = test_dates[0]
end_date = test_dates[-1]

start_dt = pd.Timestamp(start_date)
end_dt = pd.Timestamp(end_date)
cron_dates = [d.strftime('%Y-%m-%d') for d in test_dates]

# Slice test dataset
start_idx = df['date'].searchsorted(start_dt)
end_idx = df['date'].searchsorted(end_dt + pd.Timedelta(days=1))
df_test = df.iloc[start_idx:end_idx].copy()
df_test = df_test.dropna(subset=features_list)
df_test['date_str'] = df_test['date'].dt.strftime('%Y-%m-%d')

# Load Bandarologi for blending
try:
    conn = sqlite3.connect(DB_PATH)
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
except Exception as e:
    print(f"Error loading broker summaries: {e}")
    df_test['acum_score'] = 50.0

# Pre-calculate predictions
X = df_test[features_list].values
probs_t1_tech = model_t1.predict_proba(X)[:, 1]
probs_t3_tech = model_t3.predict_proba(X)[:, 1]

df_test['prob_tech_t1'] = probs_t1_tech
df_test['prob_tech_t3'] = probs_t3_tech
df_test['prob_blended_t1'] = 0.6 * probs_t1_tech + 0.4 * (df_test['acum_score'].values / 100.0)

print(f"Dataset preloaded. Slices rows: {len(df_test)} from {cron_dates[0]} to {cron_dates[-1]}")

def run_simulation(strategy, stop_loss_pct, take_profit_pct, max_positions, min_liquidity, dynamic_sizing, prob_threshold):
    # Select probability column based on strategy
    if strategy == 'T1_blended_top5':
        prob_col = 'prob_blended_t1'
        holding_days = 1
    elif strategy == 'T1_top5':
        prob_col = 'prob_tech_t1'
        holding_days = 1
    elif strategy == 'T3_top5':
        prob_col = 'prob_tech_t3'
        holding_days = 3
    else:
        return None

    # Filter candidates based on liquidity
    df_cand = df_test[df_test['value'] >= min_liquidity].copy()
    
    # Sort and group candidates by date
    df_cand_small = df_cand[['ticker', 'date_str', prob_col, 'close', 'ihsg_trend', 'market_breadth']].sort_values(by=prob_col, ascending=False)
    tickers = df_cand_small['ticker'].tolist()
    date_strs = df_cand_small['date_str'].tolist()
    prob_ups = df_cand_small[prob_col].tolist()
    closes = df_cand_small['close'].tolist()
    ihsg_trends = df_cand_small['ihsg_trend'].tolist()
    market_breadths = df_cand_small['market_breadth'].tolist()
    
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

    # Portfolio simulation parameters
    initial_capital = 100000000.0
    cash = initial_capital
    portfolio_value = initial_capital
    equity_curve = []
    trades_log = []
    active_trades = []
    
    for today_str in cron_dates:
        # 1. Update Open Positions & Check Exits
        still_active = []
        for t in active_trades:
            t["days_held"] += 1
            ticker = t["ticker"]
            shares = t["shares"]
            buy_price = t["entry_price"]
            
            today_prices = prices_lookup.get(ticker, {}).get(today_str)
            if not today_prices:
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
                    "return_pct": (exit_price / buy_price - 1) * 100,
                    "status": "SL"
                })
            # Check Take Profit
            elif take_profit_pct > 0 and high_p >= tp_price:
                exit_price = max(tp_price, open_p)
                exit_value = shares * exit_price
                cash += exit_value
                profit_nominal = exit_value - (shares * buy_price)
                trades_log.append({
                    "return_pct": (exit_price / buy_price - 1) * 100,
                    "status": "TP"
                })
            # Check Holding Period Expiry
            elif t["days_held"] >= holding_days:
                exit_value = shares * close_p
                cash += exit_value
                profit_nominal = exit_value - (shares * buy_price)
                trades_log.append({
                    "return_pct": (close_p / buy_price - 1) * 100,
                    "status": "EXPIRED"
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
        equity_curve.append(portfolio_value)
        
        # 2. Enter New Trades
        today_candidates = candidates_by_date.get(today_str, [])
        if today_candidates:
            first_cand = today_candidates[0]
            ihsg_trend = first_cand.get("ihsg_trend", 1.0)
            market_breadth = first_cand.get("market_breadth", 50.0)
        else:
            ihsg_trend = 1.0
            market_breadth = 50.0
            
        if dynamic_sizing:
            if ihsg_trend == 0.0 or market_breadth < 35.0:
                effective_max_positions = 1
            else:
                effective_max_positions = max_positions
        else:
            effective_max_positions = max_positions
            
        slots_available = effective_max_positions - len(active_trades)
        if slots_available > 0 and today_candidates:
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
                    
    # Force exit remaining
    for t in active_trades:
        ticker = t["ticker"]
        today_prices = prices_lookup.get(ticker, {}).get(cron_dates[-1])
        exit_price = today_prices["close"] if today_prices else t.get("last_close", t["entry_price"])
        trades_log.append({
            "return_pct": (exit_price / t["entry_price"] - 1) * 100,
            "status": "OPEN"
        })

    # Calculate metrics
    total_trades = len(trades_log)
    if total_trades == 0:
        return None
        
    wins = sum(1 for t in trades_log if t["return_pct"] > 0)
    win_rate = (wins / total_trades) * 100
    compounded_return = (portfolio_value / initial_capital - 1) * 100
    
    # Max Drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (val / peak - 1) * 100
        if dd < max_dd:
            max_dd = dd
            
    # Sharpe Ratio
    daily_pct_changes = []
    for t in range(1, len(equity_curve)):
        daily_pct_changes.append(equity_curve[t] / equity_curve[t-1] - 1)
        
    sharpe = 0.0
    if len(daily_pct_changes) > 1:
        mean_ret = np.mean(daily_pct_changes)
        std_ret = np.std(daily_pct_changes)
        if std_ret > 0:
            sharpe = (mean_ret / std_ret) * np.sqrt(252)

    return {
        "return_pct": compounded_return,
        "win_rate": win_rate,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "total_trades": total_trades
    }

# Parameters grids
strategies = ['T1_blended_top5', 'T1_top5', 'T3_top5']
sltp_pairs = [
    (0, 0),
    (2, 4),
    (3, 6),
    (5, 10),
    (7, 14)
]
liquidities = [
    0.0,
    1_000_000_000.0,
    5_000_000_000.0,
    10_000_000_000.0
]
max_pos_list = [1, 3, 5]
thresholds = [0.0, 0.55, 0.58, 0.60]
dynamic_sizings = [True, False]

results = []
total_runs = len(strategies) * len(sltp_pairs) * len(liquidities) * len(max_pos_list) * len(thresholds) * len(dynamic_sizings)
print(f"Running grid search over {total_runs} combinations...")

count = 0
for strategy in strategies:
    for sl, tp in sltp_pairs:
        for liq in liquidities:
            for max_pos in max_pos_list:
                for thresh in thresholds:
                    for dyn_size in dynamic_sizings:
                        sim_res = run_simulation(strategy, sl, tp, max_pos, liq, dyn_size, thresh)
                        count += 1
                        if sim_res:
                            results.append({
                                "strategy": strategy,
                                "sl": sl,
                                "tp": tp,
                                "min_liquidity_m": liq / 1e9,
                                "max_positions": max_pos,
                                "threshold": thresh,
                                "dynamic_sizing": dyn_size,
                                "return_pct": round(sim_res["return_pct"], 2),
                                "win_rate": round(sim_res["win_rate"], 2),
                                "max_drawdown": round(sim_res["max_drawdown"], 2),
                                "sharpe": round(sim_res["sharpe"], 2),
                                "total_trades": sim_res["total_trades"]
                            })
                        if count % 200 == 0:
                            print(f"Processed {count}/{total_runs}...")

# Create DataFrame
res_df = pd.DataFrame(results)

# Calculate a utility score to find the most worth-it strategy
# Score = Return% / (abs(MaxDrawdown%) + 1.0) * (Sharpe + 1.0 if Sharpe > 0 else 1.0)
res_df['score'] = res_df['return_pct'] / (res_df['max_drawdown'].abs() + 1.0)
res_df['score'] = res_df.apply(lambda r: r['score'] * (r['sharpe'] + 1.0) if r['sharpe'] > 0 else r['score'], axis=1)

# Sort
res_df.sort_values(by='score', ascending=False, inplace=True)

# Save full results
res_df.to_csv("grid_search_results.csv", index=False)
print("Grid search finished! Full results saved to grid_search_results.csv")

# Print top 15 results
print("\n--- TOP 15 PARAMETER COMBINATIONS ---")
print(res_df.head(15)[["strategy", "sl", "tp", "min_liquidity_m", "max_positions", "threshold", "dynamic_sizing", "return_pct", "win_rate", "max_drawdown", "sharpe", "score"]].to_string(index=False))

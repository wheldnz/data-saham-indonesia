import os
import sqlite3
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

db_path = r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend\alphahunter.db"
conn = sqlite3.connect(db_path)

print("1. Loading raw data...")
# Load OHLCV, Technical Features, and Broker Summaries
df_ohlcv = pd.read_sql_query('SELECT ticker, date, open, high, low, close, volume, value FROM daily_ohlcv', conn)
df_features = pd.read_sql_query('SELECT * FROM technical_features', conn)
df_broker = pd.read_sql_query('SELECT ticker, date, net_foreign_value, acum_ratio, acum_score FROM broker_summaries', conn)

df_ohlcv['date'] = pd.to_datetime(df_ohlcv['date'])
df_features['date'] = pd.to_datetime(df_features['date'])
df_broker['date'] = pd.to_datetime(df_broker['date'])

print("2. Merging datasets (INNER JOIN on overlapping dates since 2026-05-15)...")
df_merged = pd.merge(df_ohlcv, df_features, on=['ticker', 'date'], how='inner')
df_merged = pd.merge(df_merged, df_broker, on=['ticker', 'date'], how='inner')

df_merged.sort_values(by=['ticker', 'date'], inplace=True)
df_merged.reset_index(drop=True, inplace=True)

print(f"Total merged records: {len(df_merged)}")

# Target variables (T+1 upward price movement)
df_merged['next_close'] = df_merged.groupby('ticker')['close'].shift(-1)
df_merged['target_1d_up'] = (df_merged['next_close'] > df_merged['close']).astype(int)

# Drop rows without future close data (last day per ticker)
df_clean = df_merged.dropna(subset=['next_close']).copy()

# Feature engineering relative features (exactly as in prepare_ml_data.py)
df_clean['prev_close'] = df_clean.groupby('ticker')['close'].shift(1)
df_clean['return_1d'] = np.where(df_clean['prev_close'] > 0, (df_clean['close'] / df_clean['prev_close'] - 1.0) * 100.0, 0.0)

df_clean['close_vs_sma20_pct'] = np.where(df_clean['sma_20'] > 0, (df_clean['close'] / df_clean['sma_20'] - 1.0) * 100.0, 0.0)
df_clean['volume_ratio'] = np.where(df_clean['volume_sma_20'] > 0, df_clean['volume'] / df_clean['volume_sma_20'], 1.0)

daily_rsi_median = df_clean.groupby('date')['rsi_14'].transform('median')
df_clean['rsi_relative'] = df_clean['rsi_14'] - daily_rsi_median
df_clean['is_active'] = 1.0

# Drop NaNs after shifts
df_clean = df_clean.dropna().copy()

# Define feature groups
tech_features = [
    'sma_5', 'sma_20', 'sma_50', 'sma_200',
    'rsi_7', 'rsi_14', 'stoch_k', 'stoch_d',
    'macd', 'macd_signal', 'macd_histogram',
    'bb_upper', 'bb_middle', 'bb_lower',
    'atr_14', 'adx_14', 'obv', 'volume_sma_20',
    'return_1d', 'close_vs_sma20_pct', 'volume_ratio', 'rsi_relative'
]

bandar_features = [
    'acum_ratio', 'acum_score', 'net_foreign_value'
]

combined_features = tech_features + bandar_features

print(f"Technical Features count: {len(tech_features)}")
print(f"Bandarologi Features count: {len(bandar_features)}")

# Temporal Split (Train: 2026-05-15 to 2026-06-03, Test: 2026-06-04 to 2026-06-10)
train_mask = df_clean['date'] <= '2026-06-03'
test_mask = df_clean['date'] >= '2026-06-04'

df_train = df_clean[train_mask].copy()
df_test = df_clean[test_mask].copy()

print(f"Train set size: {len(df_train)} rows ({df_train['date'].min().strftime('%Y-%m-%d')} to {df_train['date'].max().strftime('%Y-%m-%d')})")
print(f"Test set size: {len(df_test)} rows ({df_test['date'].min().strftime('%Y-%m-%d')} to {df_test['date'].max().strftime('%Y-%m-%d')})")

y_train = df_train['target_1d_up'].values
y_test = df_test['target_1d_up'].values

# Common model parameters
model_params = dict(
    n_estimators=100,
    learning_rate=0.05,
    max_depth=4,
    subsample=0.75,
    colsample_bytree=0.75,
    min_child_weight=5,
    random_state=42,
    eval_metric='logloss'
)

# 1. Model Tech
print("\n--- Training Model Tech ---")
X_train_tech = df_train[tech_features].values
X_test_tech = df_test[tech_features].values
model_tech = xgb.XGBClassifier(**model_params)
model_tech.fit(X_train_tech, y_train)
probs_tech = model_tech.predict_proba(X_test_tech)[:, 1]

# 2. Model Bandar
print("--- Training Model Bandar ---")
X_train_bandar = df_train[bandar_features].values
X_test_bandar = df_test[bandar_features].values
model_bandar = xgb.XGBClassifier(**model_params)
model_bandar.fit(X_train_bandar, y_train)
probs_bandar = model_bandar.predict_proba(X_test_bandar)[:, 1]

# 3. Model Combined
print("--- Training Model Combined ---")
X_train_comb = df_train[combined_features].values
X_test_comb = df_test[combined_features].values
model_comb = xgb.XGBClassifier(**model_params)
model_comb.fit(X_train_comb, y_train)
probs_comb = model_comb.predict_proba(X_test_comb)[:, 1]

# 4. Ensemble (Average of Tech and Bandar)
probs_ensemble = 0.5 * probs_tech + 0.5 * probs_bandar

# Evaluation functions
def evaluate(y_true, y_probs, name):
    y_pred = (y_probs >= 0.5).astype(int)
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    auc = roc_auc_score(y_true, y_probs)
    return {
        "Model": name,
        "Accuracy": f5(acc),
        "Precision": f5(prec),
        "Recall": f5(rec),
        "F1-Score": f5(f1),
        "AUC": f5(auc)
    }

def f5(val):
    return round(float(val) * 100, 2)

results_metrics = [
    evaluate(y_test, probs_tech, "Technical Only"),
    evaluate(y_test, probs_bandar, "Bandarologi Only"),
    evaluate(y_test, probs_comb, "Combined (Tech+Bandar)"),
    evaluate(y_test, probs_ensemble, "Ensemble (50% Tech + 50% Bandar)")
]

df_metrics = pd.DataFrame(results_metrics)
print("\n=== CLASSIFICATION METRICS COMPARISON (TEST SET) ===")
print(df_metrics.to_string(index=False))

# ----------------- BACKTEST SIMULATION -----------------
# For each model, we run a daily backtest on the test set.
# Each day, we select the top 5 tickers with the highest probability.
# We calculate the next day return: return = (next_close - close) / close
test_dates = sorted(df_test['date'].unique())

def run_simulated_backtest(df_predictions, prob_col):
    portfolio_value = 100.0  # Starting capital
    equity_curve = [portfolio_value]
    daily_returns = []
    
    for dt in test_dates:
        day_data = df_predictions[df_predictions['date'] == dt].copy()
        if day_data.empty:
            equity_curve.append(portfolio_value)
            continue
            
        # Select top 5
        top_5 = day_data.sort_values(by=prob_col, ascending=False).head(5)
        
        # Calculate daily returns (weighted equally)
        returns = []
        for r in top_5.itertuples():
            ret = (r.next_close - r.close) / r.close
            returns.append(ret)
            
        avg_ret = np.mean(returns) if returns else 0.0
        portfolio_value = portfolio_value * (1.0 + avg_ret)
        equity_curve.append(portfolio_value)
        daily_returns.append(avg_ret)
        
    cum_ret = portfolio_value - 100.0
    win_days = sum(1 for r in daily_returns if r > 0)
    win_rate = (win_days / len(daily_returns) * 100) if daily_returns else 0.0
    return round(cum_ret, 2), round(win_rate, 2)

# Attach probabilities to df_test
df_test['prob_tech'] = probs_tech
df_test['prob_bandar'] = probs_bandar
df_test['prob_comb'] = probs_comb
df_test['prob_ensemble'] = probs_ensemble

backtest_results = []
for name, col in [
    ("Technical Only", "prob_tech"),
    ("Bandarologi Only", "prob_bandar"),
    ("Combined (Tech+Bandar)", "prob_comb"),
    ("Ensemble (50/50)", "prob_ensemble")
]:
    cum_ret, win_rate = run_simulated_backtest(df_test, col)
    backtest_results.append({
        "Model": name,
        "Cumulative Return (%)": cum_ret,
        "Winning Days Rate (%)": win_rate
    })
    
df_backtest = pd.DataFrame(backtest_results)
print("\n=== SIMULATED DAILY PORTFOLIO BACKTEST (JUNE 4 - JUNE 10, 2026) ===")
print(df_backtest.to_string(index=False))

# Re-check how the 12 ARA stocks ranked in the Combined model vs others for 2026-06-10
ara_tickers = ['BABY', 'KBLV', 'FOLK', 'ASLI', 'LCKM', 'RGAS', 'RAAM', 'ATAP', 'FORU', 'ROCK', 'RMKO', 'RISE']
print("\n=== COMPARISON OF ARA TICKERS RANKINGS ON 2026-06-10 ===")
df_target_day = df_test[df_test['date'] == '2026-06-09'].copy()  # prediction for June 10 is made using June 9 data

for t in ara_tickers:
    row = df_target_day[df_target_day['ticker'] == t]
    if not row.empty:
        r = row.iloc[0]
        # Calculate ranks in target day
        rank_tech = df_target_day['prob_tech'].rank(ascending=False).loc[row.index[0]]
        rank_bandar = df_target_day['prob_bandar'].rank(ascending=False).loc[row.index[0]]
        rank_comb = df_target_day['prob_comb'].rank(ascending=False).loc[row.index[0]]
        rank_ens = df_target_day['prob_ensemble'].rank(ascending=False).loc[row.index[0]]
        
        print(f"Ticker: {t:5} | Close: {r['close']:7.1f} | Next Close: {r['next_close']:7.1f} | Tech Rank: {int(rank_tech):3d} | Bandar Rank: {int(rank_bandar):3d} | Combined Rank: {int(rank_comb):3d} | Ensemble Rank: {int(rank_ens):3d}")
    else:
        print(f"Ticker: {t:5} | Data missing for 2026-06-09")

conn.close()

import pandas as pd

df = pd.read_csv("grid_search_results.csv")

print("=== TOP COMBINATIONS WITH LIQUIDITY >= Rp 1 BILLION (1 M) ===")
df_liq1 = df[df['min_liquidity_m'] >= 1.0].copy()
print(df_liq1.head(10)[["strategy", "sl", "tp", "min_liquidity_m", "max_positions", "threshold", "dynamic_sizing", "return_pct", "win_rate", "max_drawdown", "sharpe", "score"]].to_string(index=False))

print("\n=== TOP COMBINATIONS WITH LIQUIDITY >= Rp 5 BILLION (5 M) ===")
df_liq5 = df[df['min_liquidity_m'] >= 5.0].copy()
print(df_liq5.head(10)[["strategy", "sl", "tp", "min_liquidity_m", "max_positions", "threshold", "dynamic_sizing", "return_pct", "win_rate", "max_drawdown", "sharpe", "score"]].to_string(index=False))

print("\n=== TOP T+3 STRATEGIES ===")
df_t3 = df[df['strategy'].str.contains('T3')].copy()
print(df_t3.head(10)[["strategy", "sl", "tp", "min_liquidity_m", "max_positions", "threshold", "dynamic_sizing", "return_pct", "win_rate", "max_drawdown", "sharpe", "score"]].to_string(index=False))

import sys
import os

sys.path.insert(0, r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend")
from backtest_engine import run_backtest

print("=== BACKTEST RUN FOR T1_blended_top5 (20 DAYS, SL 2%, TP 6%) ===")
res = run_backtest(days_back=20, strategy='T1_blended_top5', stop_loss_pct=2.0, take_profit_pct=6.0)
if "error" in res:
    print(f"Error: {res['error']}")
else:
    print(f"Return: {res['total_return_pct']}% | Win Rate: {res['win_rate']}% | Trades: {res['total_trades']}")

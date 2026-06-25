import sys
import os

sys.path.insert(0, r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend")
from backtest_engine import run_backtest

strategies = ['T1_top5', 'T3_top5']

print("=== BACKTEST RUN (20 DAYS, SL 2%, TP 6%) ===")
for s in strategies:
    res = run_backtest(days_back=20, strategy=s, stop_loss_pct=2.0, take_profit_pct=6.0)
    if "error" in res:
        print(f"Strategy: {s} | Error: {res['error']}")
    else:
        print(f"Strategy: {s:15} | Return: {res['total_return_pct']:6}% | Win Rate: {res['win_rate']:5}% | Trades: {res['total_trades']:3d}")

print("\n=== BACKTEST RUN (20 DAYS, NO SL, NO TP) ===")
for s in strategies:
    res = run_backtest(days_back=20, strategy=s, stop_loss_pct=0.0, take_profit_pct=0.0)
    if "error" in res:
        print(f"Strategy: {s} | Error: {res['error']}")
    else:
        print(f"Strategy: {s:15} | Return: {res['total_return_pct']:6}% | Win Rate: {res['win_rate']:5}% | Trades: {res['total_trades']:3d}")

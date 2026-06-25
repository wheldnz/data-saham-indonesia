import json

history_file = r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend\data\predictions_history.json"
with open(history_file, 'r') as f:
    history = json.load(f)

tickers = ['BABY', 'KBLV', 'FOLK', 'ASLI', 'LCKM', 'RGAS', 'RAAM', 'ATAP', 'FORU', 'ROCK', 'RMKO', 'RISE']

for h in history:
    if h.get('date') == '2026-06-10':
        print("Predictions for 2026-06-10:")
        preds = {p['ticker']: p for p in h.get('predictions', [])}
        for t in tickers:
            if t in preds:
                print(f"Ticker: {t:5} | Prob Up: {preds[t]['prob_up']:7} | Prob Up T+3: {preds[t]['prob_up_t3']:7} | Rank: {preds[t]['rank']:4}")
            else:
                print(f"Ticker: {t:5} | Not in prediction history")

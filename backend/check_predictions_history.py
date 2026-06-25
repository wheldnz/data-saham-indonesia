import json
import os

history_file = r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend\data\predictions_history.json"
if os.path.exists(history_file):
    with open(history_file, 'r') as f:
        history = json.load(f)
    print("Found history dates:", [h.get('date') for h in history])
    # Print predictions for June 10 if exists
    for h in history:
        if h.get('date') == '2026-06-10':
            print("\nPredictions for 2026-06-10 (Top 15):")
            for p in h.get('predictions', [])[:15]:
                print(f"Ticker: {p['ticker']}, Prob Up: {p['prob_up']}, Prob Up T+3: {p['prob_up_t3']}, Rank: {p['rank']}")
else:
    print("No predictions history file found.")

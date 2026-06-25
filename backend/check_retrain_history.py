import json
import os

history_path = r"c:\Users\USER\Documents\present\Data Saham Indonesia\backend\data\retraining_history.json"
if os.path.exists(history_path):
    with open(history_path, 'r') as f:
        data = json.load(f)
    print("Retraining History:")
    for log in data:
        print(f"Timestamp: {log.get('timestamp')} | Status: {log.get('status')} | Error: {log.get('error')}")
else:
    print("No retraining history found.")

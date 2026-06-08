import sys
import os
import json
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
import joblib

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DATASET_PATH = os.path.join(DATA_DIR, 'ml_dataset.csv')
MODEL_PATH = os.path.join(DATA_DIR, 'xgb_model_t1.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list.joblib')
CV_REPORT_PATH = os.path.join(DATA_DIR, 'cv_report.json')

def train_model():
    if not os.path.exists(DATASET_PATH):
        print(f"Dataset not found at {DATASET_PATH}. Please run prepare_ml_data.py first.")
        return

    print(f"Loading dataset from {DATASET_PATH}...")
    df = pd.read_csv(DATASET_PATH)

    # Sort by date — critical for temporal integrity
    df['date'] = pd.to_datetime(df['date'])
    df.sort_values(by='date', inplace=True)
    df.reset_index(drop=True, inplace=True)

    print(f"Dataset loaded. Total rows: {len(df)}")
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")

    # ─────────────────────────────────────────────────────────────
    # Define Features (X) and Target (y)
    # ─────────────────────────────────────────────────────────────
    drop_cols = ['ticker', 'date', 'target_1d_up']
    feature_cols = [c for c in df.columns if c not in drop_cols]

    print(f"\nUsing {len(feature_cols)} features: {feature_cols}")

    X = df[feature_cols].values
    y = df['target_1d_up'].values
    dates = df['date'].values

    # Baseline (majority class)
    baseline_acc = 1 - y.mean() if y.mean() < 0.5 else y.mean()
    print(f"Baseline Accuracy (always guessing majority class): {baseline_acc:.2%}")

    # ─────────────────────────────────────────────────────────────
    # Walk-Forward Cross-Validation
    #
    # Menggunakan TimeSeriesSplit dengan purge gap 5 hari trading.
    # Purge gap menghilangkan potensi cross-sectional correlation:
    # data T-5 hingga T-1 sebelum test window dikeluarkan dari train
    # agar saham A dan B yang datanya berdampingan tidak menciptakan
    # kebocoran informasi antar-ticker.
    #
    # n_splits=5 = 5 fold expanding window
    # gap=5      = 5-hari buffer antara train dan test (purge)
    # ─────────────────────────────────────────────────────────────
    N_SPLITS = 5
    PURGE_GAP = 5  # hari trading

    tscv = TimeSeriesSplit(n_splits=N_SPLITS, gap=PURGE_GAP)

    model_params = dict(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=4,          # Diturunkan dari 5 ke 4 untuk mengurangi overfitting
        subsample=0.75,       # Diturunkan dari 0.8 ke 0.75
        colsample_bytree=0.75,
        min_child_weight=5,   # Minimum sampel per leaf (regularisasi ekstra)
        reg_alpha=0.1,        # L1 regularization
        reg_lambda=1.5,       # L2 regularization
        random_state=42,
        eval_metric='logloss'
    )

    fold_results = []
    all_y_true = []
    all_y_pred = []

    print(f"\n{'='*60}")
    print(f"  WALK-FORWARD CROSS-VALIDATION ({N_SPLITS} FOLDS, GAP={PURGE_GAP})")
    print(f"{'='*60}")

    for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(X), start=1):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        train_start = pd.Timestamp(dates[train_idx[0]]).date()
        train_end   = pd.Timestamp(dates[train_idx[-1]]).date()
        test_start  = pd.Timestamp(dates[test_idx[0]]).date()
        test_end    = pd.Timestamp(dates[test_idx[-1]]).date()

        print(f"\n[Fold {fold_idx}/{N_SPLITS}]")
        print(f"  Train: {train_start} to {train_end} ({len(X_train):,} samples)")
        print(f"  Test:  {test_start} to {test_end} ({len(X_test):,} samples)")

        model_cv = xgb.XGBClassifier(**model_params)
        model_cv.fit(X_train, y_train, verbose=False)

        y_pred = model_cv.predict(X_test)
        acc  = accuracy_score(y_test, y_pred)
        f1   = f1_score(y_test, y_pred, average='weighted')
        fold_baseline = 1 - y_test.mean() if y_test.mean() < 0.5 else y_test.mean()

        print(f"  Accuracy: {acc:.2%}  |  F1: {f1:.4f}  |  Fold Baseline: {fold_baseline:.2%}")

        fold_results.append({
            "fold": fold_idx,
            "train_start": str(train_start),
            "train_end": str(train_end),
            "test_start": str(test_start),
            "test_end": str(test_end),
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
            "accuracy": round(float(acc), 4),
            "f1_weighted": round(float(f1), 4),
            "fold_baseline": round(float(fold_baseline), 4)
        })

        all_y_true.extend(y_test.tolist())
        all_y_pred.extend(y_pred.tolist())

    # ─────────────────────────────────────────────────────────────
    # Aggregate CV Results
    # ─────────────────────────────────────────────────────────────
    accs = [r['accuracy'] for r in fold_results]
    f1s  = [r['f1_weighted'] for r in fold_results]

    mean_acc = float(np.mean(accs))
    std_acc  = float(np.std(accs))
    mean_f1  = float(np.mean(f1s))
    std_f1   = float(np.std(f1s))

    print(f"\n{'='*60}")
    print(f"  CV SUMMARY ({N_SPLITS}-FOLD WALK-FORWARD)")
    print(f"{'='*60}")
    print(f"  Mean Accuracy : {mean_acc:.2%} ± {std_acc:.2%}")
    print(f"  Mean F1       : {mean_f1:.4f} ± {std_f1:.4f}")
    print(f"  Baseline Acc  : {baseline_acc:.2%}")
    print(f"  Lift vs Base  : {(mean_acc - baseline_acc)*100:+.2f} pp")
    print(f"\n  Aggregated Classification Report (all folds):")
    print(classification_report(all_y_true, all_y_pred))
    print(f"  Aggregated Confusion Matrix:")
    print(confusion_matrix(all_y_true, all_y_pred))

    # ─────────────────────────────────────────────────────────────
    # Train Final Model on ALL data
    # Model ini yang dipakai untuk inferensi production.
    # CV hanya untuk estimasi metrik yang jujur, bukan untuk
    # memilih model — final model dilatih pada semua data agar
    # mendapatkan sinyal terbanyak.
    # ─────────────────────────────────────────────────────────────
    print(f"\n[Final Model] Melatih model pada seluruh {len(X):,} sampel...")
    final_model = xgb.XGBClassifier(**model_params)
    final_model.fit(X, y, verbose=False)
    print("[Final Model] Pelatihan selesai.")

    # Feature Importance
    importances = final_model.feature_importances_
    feat_imp = pd.DataFrame({'Feature': feature_cols, 'Importance': importances})
    feat_imp = feat_imp.sort_values(by='Importance', ascending=False)
    print("\nTop 10 Important Features:")
    print(feat_imp.head(10).to_string(index=False))

    # ─────────────────────────────────────────────────────────────
    # Save CV Report to JSON
    # ─────────────────────────────────────────────────────────────
    cv_report = {
        "method": "Walk-Forward Cross-Validation (Purged)",
        "n_splits": N_SPLITS,
        "purge_gap_days": PURGE_GAP,
        "dataset_rows": int(len(df)),
        "n_features": int(len(feature_cols)),
        "baseline_accuracy": round(baseline_acc, 4),
        "mean_accuracy": round(mean_acc, 4),
        "std_accuracy": round(std_acc, 4),
        "mean_f1_weighted": round(mean_f1, 4),
        "std_f1_weighted": round(std_f1, 4),
        "lift_vs_baseline_pp": round((mean_acc - baseline_acc) * 100, 2),
        "folds": fold_results,
        "feature_importances": [
            {"feature": row['Feature'], "importance": round(float(row['Importance']), 4)}
            for _, row in feat_imp.iterrows()
        ]
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CV_REPORT_PATH, 'w') as f:
        json.dump(cv_report, f, indent=2)
    print(f"\nCV report saved to {CV_REPORT_PATH}")

    # ─────────────────────────────────────────────────────────────
    # Save Final Model and Feature List
    # ─────────────────────────────────────────────────────────────
    print(f"Saving final model to {MODEL_PATH}...")
    joblib.dump(final_model, MODEL_PATH)
    joblib.dump(feature_cols, FEATURES_LIST_PATH)
    print("Training pipeline complete!")

if __name__ == "__main__":
    train_model()

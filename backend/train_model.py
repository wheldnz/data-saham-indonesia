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
MODEL_T1_PATH = os.path.join(DATA_DIR, 'xgb_model_t1.joblib')
MODEL_T3_PATH = os.path.join(DATA_DIR, 'xgb_model_t3.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list.joblib')
CV_REPORT_T1_PATH = os.path.join(DATA_DIR, 'cv_report_t1.json')
CV_REPORT_T3_PATH = os.path.join(DATA_DIR, 'cv_report_t3.json')

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
    # Define Features (X)
    # ─────────────────────────────────────────────────────────────
    drop_cols = ['ticker', 'date', 'target_1d_up', 'target_3d_up', 'open', 'high', 'low']
    feature_cols = [c for c in df.columns if c not in drop_cols]

    print(f"\nUsing {len(feature_cols)} features: {feature_cols}")

    X = df[feature_cols].values
    dates = df['date'].values

    # Save features list once (it's the same for both models)
    os.makedirs(DATA_DIR, exist_ok=True)
    joblib.dump(feature_cols, FEATURES_LIST_PATH)
    print(f"Features list saved to {FEATURES_LIST_PATH}")

    # Configurations for the targets
    targets_config = {
        'T+1': {
            'col': 'target_1d_up',
            'model_path': MODEL_T1_PATH,
            'report_path': CV_REPORT_T1_PATH
        },
        'T+3': {
            'col': 'target_3d_up',
            'model_path': MODEL_T3_PATH,
            'report_path': CV_REPORT_T3_PATH
        }
    }

    for horizon, cfg in targets_config.items():
        target_col = cfg['col']
        model_save_path = cfg['model_path']
        report_save_path = cfg['report_path']

        print(f"\n{'='*60}")
        print(f"  STARTING TRAINING FOR HORIZON: {horizon} (Target: {target_col})")
        print(f"{'='*60}")

        y = df[target_col].values

        # Baseline (majority class)
        baseline_acc = 1 - y.mean() if y.mean() < 0.5 else y.mean()
        print(f"Baseline Accuracy (always guessing majority class): {baseline_acc:.2%}")

        # Class Imbalance Correction via scale_pos_weight
        n_class0 = int((y == 0).sum())
        n_class1 = int((y == 1).sum())
        scale_pos_weight = n_class0 / n_class1 if n_class1 > 0 else 1.0
        print(f"Class distribution — 0 (Down): {n_class0:,} ({n_class0/len(y):.1%}) | 1 (Up): {n_class1:,} ({n_class1/len(y):.1%})")
        print(f"scale_pos_weight = {scale_pos_weight:.4f} (applied to XGBoost)")

        # Walk-Forward Cross-Validation
        N_SPLITS = 5
        PURGE_GAP = 5  # hari trading
        tscv = TimeSeriesSplit(n_splits=N_SPLITS, gap=PURGE_GAP)

        model_params = dict(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.75,
            colsample_bytree=0.75,
            min_child_weight=5,
            reg_alpha=0.1,
            reg_lambda=1.5,
            scale_pos_weight=scale_pos_weight,  # Class imbalance correction
            random_state=42,
            eval_metric='logloss'
        )

        fold_results = []
        all_y_true = []
        all_y_pred = []

        print(f"\n[Walk-Forward CV ({N_SPLITS} Folds, Gap={PURGE_GAP})]")

        for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(X), start=1):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            train_start = pd.Timestamp(dates[train_idx[0]]).date()
            train_end   = pd.Timestamp(dates[train_idx[-1]]).date()
            test_start  = pd.Timestamp(dates[test_idx[0]]).date()
            test_end    = pd.Timestamp(dates[test_idx[-1]]).date()

            model_cv = xgb.XGBClassifier(**model_params)
            model_cv.fit(X_train, y_train, verbose=False)

            y_pred = model_cv.predict(X_test)
            acc  = accuracy_score(y_test, y_pred)
            f1   = f1_score(y_test, y_pred, average='weighted')
            fold_baseline = 1 - y_test.mean() if y_test.mean() < 0.5 else y_test.mean()

            print(f"  Fold {fold_idx}: Train {train_start} to {train_end} | Test {test_start} to {test_end}")
            print(f"    Accuracy: {acc:.2%}  |  F1: {f1:.4f}  |  Fold Baseline: {fold_baseline:.2%}")

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

        # Aggregate CV Results
        accs = [r['accuracy'] for r in fold_results]
        f1s  = [r['f1_weighted'] for r in fold_results]

        mean_acc = float(np.mean(accs))
        std_acc  = float(np.std(accs))
        mean_f1  = float(np.mean(f1s))
        std_f1   = float(np.std(f1s))

        print(f"\n  CV Summary for {horizon}:")
        print(f"    Mean Accuracy : {mean_acc:.2%} ± {std_acc:.2%}")
        print(f"    Mean F1       : {mean_f1:.4f} ± {std_f1:.4f}")
        print(f"    Baseline Acc  : {baseline_acc:.2%}")
        print(f"    Lift vs Base  : {(mean_acc - baseline_acc)*100:+.2f} pp")
        print(f"    Classification Report (Aggregated):")
        print(classification_report(all_y_true, all_y_pred, digits=4))

        # Train Final Model on ALL data
        print(f"\n  [Final Model] Melatih model {horizon} pada seluruh {len(X):,} sampel...")
        final_model = xgb.XGBClassifier(**model_params)
        final_model.fit(X, y, verbose=False)
        print(f"  [Final Model] Pelatihan selesai. Menyimpan ke {model_save_path}...")
        joblib.dump(final_model, model_save_path)

        # Feature Importance
        importances = final_model.feature_importances_
        feat_imp = pd.DataFrame({'Feature': feature_cols, 'Importance': importances})
        feat_imp = feat_imp.sort_values(by='Importance', ascending=False)
        print(f"\n  Top 10 Features for {horizon}:")
        print(feat_imp.head(10).to_string(index=False))

        # Save CV Report to JSON
        cv_report = {
            "horizon": horizon,
            "target_column": target_col,
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
        with open(report_save_path, 'w') as f:
            json.dump(cv_report, f, indent=2)
        print(f"  CV report saved to {report_save_path}")

    print("\nAll training pipelines complete!")

if __name__ == "__main__":
    train_model()

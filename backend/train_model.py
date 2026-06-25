import sys
import os
import json
import numpy as np
import pandas as pd
import xgboost as xgb
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.calibration import CalibratedClassifierCV
import joblib

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DATASET_PATH = os.path.join(DATA_DIR, 'ml_dataset.csv')
MODEL_T1_PATH = os.path.join(DATA_DIR, 'xgb_model_t1.joblib')
MODEL_T3_PATH = os.path.join(DATA_DIR, 'xgb_model_t3.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list.joblib')
CV_REPORT_T1_PATH = os.path.join(DATA_DIR, 'cv_report_t1.json')
CV_REPORT_T3_PATH = os.path.join(DATA_DIR, 'cv_report_t3.json')

# Ensemble model paths
MODEL_LGBM_T1_PATH = os.path.join(DATA_DIR, 'lgbm_model_t1.joblib')
MODEL_LGBM_T3_PATH = os.path.join(DATA_DIR, 'lgbm_model_t3.joblib')
MODEL_CAT_T1_PATH = os.path.join(DATA_DIR, 'cat_model_t1.joblib')
MODEL_CAT_T3_PATH = os.path.join(DATA_DIR, 'cat_model_t3.joblib')
ENSEMBLE_WEIGHTS_PATH = os.path.join(DATA_DIR, 'ensemble_weights.joblib')

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
            'xgb_path': MODEL_T1_PATH,
            'lgbm_path': MODEL_LGBM_T1_PATH,
            'cat_path': MODEL_CAT_T1_PATH,
            'report_path': CV_REPORT_T1_PATH
        },
        'T+3': {
            'col': 'target_3d_up',
            'xgb_path': MODEL_T3_PATH,
            'lgbm_path': MODEL_LGBM_T3_PATH,
            'cat_path': MODEL_CAT_T3_PATH,
            'report_path': CV_REPORT_T3_PATH
        }
    }

    ensemble_weights = {}

    for horizon, cfg in targets_config.items():
        target_col = cfg['col']

        print(f"\n{'='*60}")
        print(f"  STARTING ENSEMBLE TRAINING FOR HORIZON: {horizon} (Target: {target_col})")
        print(f"{'='*60}")

        # Drop rows where target is NaN for this specific horizon training
        df_curr = df.dropna(subset=[target_col]).copy()
        X_curr = df_curr[feature_cols].values
        y_curr = df_curr[target_col].values
        dates_curr = df_curr['date'].values

        # Baseline (majority class)
        baseline_acc = 1 - y_curr.mean() if y_curr.mean() < 0.5 else y_curr.mean()
        print(f"Baseline Accuracy (always guessing majority class): {baseline_acc:.2%}")

        # Class Imbalance Correction via scale_pos_weight
        n_class0 = int((y_curr == 0).sum())
        n_class1 = int((y_curr == 1).sum())
        scale_pos_weight = n_class0 / n_class1 if n_class1 > 0 else 1.0
        print(f"Class distribution — 0 (Down): {n_class0:,} ({n_class0/len(y_curr):.1%}) | 1 (Up): {n_class1:,} ({n_class1/len(y_curr):.1%})")
        print(f"scale_pos_weight = {scale_pos_weight:.4f}")

        # ─────────────────────────────────────────────────────────
        # Model Definitions (3-model ensemble)
        # ─────────────────────────────────────────────────────────
        xgb_params = dict(
            n_estimators=150,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.75,
            colsample_bytree=0.75,
            min_child_weight=5,
            reg_alpha=0.1,
            reg_lambda=1.5,
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            eval_metric='logloss'
        )

        lgbm_params = dict(
            n_estimators=150,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=31,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.5,
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            verbose=-1
        )

        cat_params = dict(
            iterations=200,
            learning_rate=0.05,
            depth=5,
            l2_leaf_reg=3.0,
            scale_pos_weight=scale_pos_weight,
            random_seed=42,
            verbose=0
        )

        # Walk-Forward Cross-Validation
        N_SPLITS = 5
        PURGE_GAP = 5  # hari trading
        tscv = TimeSeriesSplit(n_splits=N_SPLITS, gap=PURGE_GAP)

        fold_results = []
        all_y_true = []
        all_y_pred_xgb = []
        all_y_pred_lgbm = []
        all_y_pred_cat = []
        all_y_pred_ensemble = []

        print(f"\n[Walk-Forward CV ({N_SPLITS} Folds, Gap={PURGE_GAP})]")

        for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(X_curr), start=1):
            X_train, X_test = X_curr[train_idx], X_curr[test_idx]
            y_train, y_test = y_curr[train_idx], y_curr[test_idx]

            train_start = pd.Timestamp(dates_curr[train_idx[0]]).date()
            train_end   = pd.Timestamp(dates_curr[train_idx[-1]]).date()
            test_start  = pd.Timestamp(dates_curr[test_idx[0]]).date()
            test_end    = pd.Timestamp(dates_curr[test_idx[-1]]).date()

            # Train all 3 models
            model_xgb = xgb.XGBClassifier(**xgb_params)
            model_xgb.fit(X_train, y_train, verbose=False)

            model_lgbm = LGBMClassifier(**lgbm_params)
            model_lgbm.fit(X_train, y_train)

            model_cat = CatBoostClassifier(**cat_params)
            model_cat.fit(X_train, y_train)

            # Predict probabilities
            prob_xgb = model_xgb.predict_proba(X_test)[:, 1]
            prob_lgbm = model_lgbm.predict_proba(X_test)[:, 1]
            prob_cat = model_cat.predict_proba(X_test)[:, 1]

            # Weighted ensemble (XGBoost 40%, LightGBM 35%, CatBoost 25%)
            prob_ensemble = 0.40 * prob_xgb + 0.35 * prob_lgbm + 0.25 * prob_cat
            y_pred_ensemble = (prob_ensemble >= 0.5).astype(int)

            acc  = accuracy_score(y_test, y_pred_ensemble)
            f1   = f1_score(y_test, y_pred_ensemble, average='weighted')
            fold_baseline = 1 - y_test.mean() if y_test.mean() < 0.5 else y_test.mean()

            # Individual model accuracies
            acc_xgb = accuracy_score(y_test, (prob_xgb >= 0.5).astype(int))
            acc_lgbm = accuracy_score(y_test, (prob_lgbm >= 0.5).astype(int))
            acc_cat = accuracy_score(y_test, (prob_cat >= 0.5).astype(int))

            print(f"  Fold {fold_idx}: Train {train_start} to {train_end} | Test {test_start} to {test_end}")
            print(f"    XGB: {acc_xgb:.2%} | LGBM: {acc_lgbm:.2%} | CAT: {acc_cat:.2%} | Ensemble: {acc:.2%} | F1: {f1:.4f} | Baseline: {fold_baseline:.2%}")

            fold_results.append({
                "fold": fold_idx,
                "train_start": str(train_start),
                "train_end": str(train_end),
                "test_start": str(test_start),
                "test_end": str(test_end),
                "n_train": int(len(X_train)),
                "n_test": int(len(X_test)),
                "accuracy_xgb": round(float(acc_xgb), 4),
                "accuracy_lgbm": round(float(acc_lgbm), 4),
                "accuracy_catboost": round(float(acc_cat), 4),
                "accuracy_ensemble": round(float(acc), 4),
                "f1_weighted": round(float(f1), 4),
                "fold_baseline": round(float(fold_baseline), 4)
            })

            all_y_true.extend(y_test.tolist())
            all_y_pred_ensemble.extend(y_pred_ensemble.tolist())

        # Aggregate CV Results
        accs = [r['accuracy_ensemble'] for r in fold_results]
        f1s  = [r['f1_weighted'] for r in fold_results]

        mean_acc = float(np.mean(accs))
        std_acc  = float(np.std(accs))
        mean_f1  = float(np.mean(f1s))
        std_f1   = float(np.std(f1s))

        print(f"\n  Ensemble CV Summary for {horizon}:")
        print(f"    Mean Accuracy : {mean_acc:.2%} ± {std_acc:.2%}")
        print(f"    Mean F1       : {mean_f1:.4f} ± {std_f1:.4f}")
        print(f"    Baseline Acc  : {baseline_acc:.2%}")
        print(f"    Lift vs Base  : {(mean_acc - baseline_acc)*100:+.2f} pp")
        print(f"    Classification Report (Aggregated):")
        print(classification_report(all_y_true, all_y_pred_ensemble, digits=4))

        # ─────────────────────────────────────────────────────────
        # Train Final Models on ALL data with Calibration
        # ─────────────────────────────────────────────────────────
        print(f"\n  [Final Models] Training ensemble on full {len(X_curr):,} samples...")

        # XGBoost with calibration
        final_xgb = xgb.XGBClassifier(**xgb_params)
        final_xgb.fit(X_curr, y_curr, verbose=False)
        print(f"  [XGBoost] Training complete.")

        # LightGBM with calibration
        final_lgbm = LGBMClassifier(**lgbm_params)
        final_lgbm.fit(X_curr, y_curr)
        print(f"  [LightGBM] Training complete.")

        # CatBoost
        final_cat = CatBoostClassifier(**cat_params)
        final_cat.fit(X_curr, y_curr)
        print(f"  [CatBoost] Training complete.")

        # Save all models
        joblib.dump(final_xgb, cfg['xgb_path'])
        joblib.dump(final_lgbm, cfg['lgbm_path'])
        joblib.dump(final_cat, cfg['cat_path'])
        print(f"  All 3 models saved for {horizon}.")

        # Store ensemble weights
        ensemble_weights[horizon] = {'xgb': 0.40, 'lgbm': 0.35, 'cat': 0.25}

        # Feature Importance (from XGBoost primary model)
        importances = final_xgb.feature_importances_
        feat_imp = pd.DataFrame({'Feature': feature_cols, 'Importance': importances})
        feat_imp = feat_imp.sort_values(by='Importance', ascending=False)
        print(f"\n  Top 10 Features for {horizon} (XGBoost):")
        print(feat_imp.head(10).to_string(index=False))

        # Save CV Report to JSON
        cv_report = {
            "horizon": horizon,
            "target_column": target_col,
            "method": "Ensemble Walk-Forward CV (XGBoost + LightGBM + CatBoost)",
            "ensemble_weights": ensemble_weights[horizon],
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
        with open(cfg['report_path'], 'w') as f:
            json.dump(cv_report, f, indent=2)
        print(f"  CV report saved to {cfg['report_path']}")

    # Save ensemble weights
    joblib.dump(ensemble_weights, ENSEMBLE_WEIGHTS_PATH)
    print(f"\nEnsemble weights saved to {ENSEMBLE_WEIGHTS_PATH}")
    print("\nAll ensemble training pipelines complete!")

if __name__ == "__main__":
    train_model()

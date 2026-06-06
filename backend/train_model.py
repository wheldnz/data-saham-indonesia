import sys
import os
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import joblib

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DATASET_PATH = os.path.join(DATA_DIR, 'ml_dataset.csv')
MODEL_PATH = os.path.join(DATA_DIR, 'xgb_model_t1.joblib')
FEATURES_LIST_PATH = os.path.join(DATA_DIR, 'features_list.joblib')

def train_model():
    if not os.path.exists(DATASET_PATH):
        print(f"Dataset not found at {DATASET_PATH}. Please run prepare_ml_data.py first.")
        return
        
    print(f"Loading dataset from {DATASET_PATH}...")
    df = pd.read_csv(DATASET_PATH)
    
    # Sort by date just to be sure
    df['date'] = pd.to_datetime(df['date'])
    df.sort_values(by='date', inplace=True)
    
    print(f"Dataset loaded. Total rows: {len(df)}")
    
    # Define Features (X) and Target (y)
    # We drop non-predictive columns: ticker, date, and the target itself
    # Also 'value' might be highly correlated with volume and close, but let's keep it or drop it.
    drop_cols = ['ticker', 'date', 'target_1d_up']
    feature_cols = [c for c in df.columns if c not in drop_cols]
    
    print(f"Using {len(feature_cols)} features: {feature_cols}")
    
    X = df[feature_cols]
    y = df['target_1d_up']
    
    # Temporal Train-Test Split (80% train, 20% test)
    # Since it's time series, we shouldn't shuffle randomly if we want to simulate real world
    # But for a quick robust baseline, train_test_split without shuffle simulates a time-cutoff
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, shuffle=False)
    
    print(f"Training on {len(X_train)} samples, Testing on {len(X_test)} samples.")
    
    # Calculate baseline (if we always guessed 0, what would the accuracy be?)
    baseline_acc = 1 - y.mean() if y.mean() < 0.5 else y.mean()
    print(f"Baseline Accuracy (always guessing majority class): {baseline_acc:.2%}")
    
    # Initialize XGBoost Classifier
    print("Training XGBoost model...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss'
    )
    
    # Train
    model.fit(X_train, y_train)
    
    # Predict on test set
    print("Evaluating model...")
    y_pred = model.predict(X_test)
    
    # Metrics
    acc = accuracy_score(y_test, y_pred)
    print(f"\nModel Accuracy: {acc:.2%}")
    
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))
    
    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    
    # Feature Importance
    importances = model.feature_importances_
    feat_imp = pd.DataFrame({'Feature': feature_cols, 'Importance': importances})
    feat_imp = feat_imp.sort_values(by='Importance', ascending=False)
    print("\nTop 5 Important Features:")
    print(feat_imp.head(5))
    
    # Save model and feature list
    print(f"\nSaving model to {MODEL_PATH}...")
    joblib.dump(model, MODEL_PATH)
    joblib.dump(feature_cols, FEATURES_LIST_PATH)
    print("Training pipeline complete!")

if __name__ == "__main__":
    train_model()

import os
import joblib
import pandas as pd

# Find data dir
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
if not os.path.exists(DATA_DIR):
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')

# Global cache variables
_df = None
_prices_lookup = None
_model_t1 = None
_model_t3 = None
_features_list = None
_all_dates = None
_is_loaded = False

def load_cache(force_reload=False):
    global _df, _prices_lookup, _model_t1, _model_t3, _features_list, _all_dates, _is_loaded
    if _is_loaded and not force_reload:
        return True
        
    print("=== LOADING DATASET CACHE IN-MEMORY ===")
    dataset_path = os.path.join(DATA_DIR, 'ml_dataset.csv')
    model_t1_path = os.path.join(DATA_DIR, 'xgb_model_t1.joblib')
    model_t3_path = os.path.join(DATA_DIR, 'xgb_model_t3.joblib')
    features_list_path = os.path.join(DATA_DIR, 'features_list.joblib')
    
    if not os.path.exists(dataset_path):
        print(f"[Cache Error] {dataset_path} not found.")
        return False
        
    try:
        # Load and sort data
        temp_df = pd.read_csv(dataset_path)
        temp_df['date'] = pd.to_datetime(temp_df['date'])
        temp_df.sort_values(by=['date', 'ticker'], inplace=True)
        temp_df.reset_index(drop=True, inplace=True)
        
        # Build prices lookup
        print("Building cached prices lookup...")
        prices_df = temp_df[['ticker', 'date', 'open', 'high', 'low', 'close']].copy()
        prices_df['date_str'] = prices_df['date'].dt.strftime('%Y-%m-%d')
        
        temp_lookup = {}
        for row in prices_df.itertuples():
            if row.ticker not in temp_lookup:
                temp_lookup[row.ticker] = {}
            temp_lookup[row.ticker][row.date_str] = {
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close)
            }
            
        # Extract and sort unique dates
        print("Extracting unique dates list...")
        temp_all_dates = list(temp_df['date'].unique())
        temp_all_dates.sort()
        
        # Load models
        temp_t1 = joblib.load(model_t1_path) if os.path.exists(model_t1_path) else None
        temp_t3 = joblib.load(model_t3_path) if os.path.exists(model_t3_path) else None
        temp_features = joblib.load(features_list_path) if os.path.exists(features_list_path) else None
        
        # Atomic swap
        _df = temp_df
        _prices_lookup = temp_lookup
        _model_t1 = temp_t1
        _model_t3 = temp_t3
        _features_list = temp_features
        _all_dates = temp_all_dates
        _is_loaded = True
        print("=== DATASET CACHE LOADED SUCCESSFULLY ===")
        return True
    except Exception as e:
        print(f"[Cache Error] Failed to load cache: {e}")
        return False

def get_df():
    return _df

def get_prices_lookup():
    return _prices_lookup

def get_model_t1():
    return _model_t1

def get_model_t3():
    return _model_t3

def get_features_list():
    return _features_list

def get_all_dates():
    return _all_dates

def is_loaded():
    return _is_loaded


# ─────────────────────────────────────────────────────────────
# Adaptive global cache variables
# ─────────────────────────────────────────────────────────────
_df_adaptive = None
_prices_lookup_adaptive = None
_model_t1_adaptive = None
_model_t3_adaptive = None
_features_list_adaptive = None
_all_dates_adaptive = None
_is_loaded_adaptive = False

def load_cache_adaptive(force_reload=False):
    global _df_adaptive, _prices_lookup_adaptive, _model_t1_adaptive, _model_t3_adaptive, _features_list_adaptive, _all_dates_adaptive, _is_loaded_adaptive
    if _is_loaded_adaptive and not force_reload:
        return True
        
    print("=== LOADING ADAPTIVE DATASET CACHE IN-MEMORY ===")
    dataset_path = os.path.join(DATA_DIR, 'ml_dataset_adaptive.csv')
    model_t1_path = os.path.join(DATA_DIR, 'xgb_model_t1_adaptive.joblib')
    model_t3_path = os.path.join(DATA_DIR, 'xgb_model_t3_adaptive.joblib')
    features_list_path = os.path.join(DATA_DIR, 'features_list_adaptive.joblib')
    
    if not os.path.exists(dataset_path):
        print(f"[Cache Error] {dataset_path} not found.")
        return False
        
    try:
        # Load and sort data
        temp_df = pd.read_csv(dataset_path)
        temp_df['date'] = pd.to_datetime(temp_df['date'])
        temp_df.sort_values(by=['date', 'ticker'], inplace=True)
        temp_df.reset_index(drop=True, inplace=True)
        
        # Build prices lookup
        print("Building cached adaptive prices lookup...")
        prices_df = temp_df[['ticker', 'date', 'open', 'high', 'low', 'close', 'ihsg_trend']].copy()
        prices_df['date_str'] = prices_df['date'].dt.strftime('%Y-%m-%d')
        
        temp_lookup = {}
        for row in prices_df.itertuples():
            if row.ticker not in temp_lookup:
                temp_lookup[row.ticker] = {}
            temp_lookup[row.ticker][row.date_str] = {
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "ihsg_trend": float(row.ihsg_trend)
            }
            
        # Extract and sort unique dates
        print("Extracting unique dates list...")
        temp_all_dates = list(temp_df['date'].unique())
        temp_all_dates.sort()
        
        # Load models
        temp_t1 = joblib.load(model_t1_path) if os.path.exists(model_t1_path) else None
        temp_t3 = joblib.load(model_t3_path) if os.path.exists(model_t3_path) else None
        temp_features = joblib.load(features_list_path) if os.path.exists(features_list_path) else None
        
        # Atomic swap
        _df_adaptive = temp_df
        _prices_lookup_adaptive = temp_lookup
        _model_t1_adaptive = temp_t1
        _model_t3_adaptive = temp_t3
        _features_list_adaptive = temp_features
        _all_dates_adaptive = temp_all_dates
        _is_loaded_adaptive = True
        print("=== ADAPTIVE DATASET CACHE LOADED SUCCESSFULLY ===")
        return True
    except Exception as e:
        print(f"[Cache Error] Failed to load adaptive cache: {e}")
        return False

def get_df_adaptive():
    return _df_adaptive

def get_prices_lookup_adaptive():
    return _prices_lookup_adaptive

def get_model_t1_adaptive():
    return _model_t1_adaptive

def get_model_t3_adaptive():
    return _model_t3_adaptive

def get_features_list_adaptive():
    return _features_list_adaptive

def get_all_dates_adaptive():
    return _all_dates_adaptive

def is_loaded_adaptive():
    return _is_loaded_adaptive

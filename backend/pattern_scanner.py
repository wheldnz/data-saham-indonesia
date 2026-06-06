import pandas as pd
import numpy as np

def detect_candlestick_patterns(df):
    """
    Takes a DataFrame with columns: open, high, low, close
    Returns a pandas Series of strings containing comma-separated detected patterns.
    """
    
    # Calculate basic candle components
    body_size = abs(df['close'] - df['open'])
    upper_shadow = np.maximum(df['high'] - np.maximum(df['close'], df['open']), 0)
    lower_shadow = np.maximum(np.minimum(df['close'], df['open']) - df['low'], 0)
    total_size = df['high'] - df['low']
    total_size = total_size.replace(0, 0.0001) # prevent division by zero
    
    is_bullish = df['close'] > df['open']
    is_bearish = df['close'] < df['open']
    
    # 1. Doji (Body is very small compared to total range)
    is_doji = body_size <= (total_size * 0.1)
    
    # 2. Hammer (Small body, long lower shadow, very small upper shadow)
    is_hammer = (lower_shadow >= (2 * body_size)) & (upper_shadow <= (0.1 * total_size)) & (body_size > 0)
    
    # Create shifted columns using groupby
    grouped = df.groupby('ticker')
    prev_close = grouped['close'].shift(1)
    prev_open = grouped['open'].shift(1)
    prev_high = grouped['high'].shift(1)
    prev_low = grouped['low'].shift(1)
    
    prev2_close = grouped['close'].shift(2)
    prev2_open = grouped['open'].shift(2)
    
    # 3. Engulfing Patterns
    prev_is_bullish = prev_close > prev_open
    prev_is_bearish = prev_close < prev_open
    
    is_bullish_engulfing = is_bullish & prev_is_bearish & (df['close'] > prev_open) & (df['open'] < prev_close)
    is_bearish_engulfing = is_bearish & prev_is_bullish & (df['close'] < prev_open) & (df['open'] > prev_close)
    
    # 4. Morning Star (3 candle pattern)
    prev2_is_bearish = prev2_close < prev2_open
    
    prev_is_doji = (abs(prev_close - prev_open) <= (prev_high - prev_low) * 0.1)
    
    is_morning_star = prev2_is_bearish & prev_is_doji & is_bullish & (df['close'] > (prev2_open + prev2_close)/2)
    
    # 5. Advanced Chart Patterns (Rolling windows)
    # 5.1 Resistance Breakout
    high_20_max = grouped['high'].transform(lambda x: x.shift(1).rolling(20, min_periods=5).max())
    vol_20_sma = grouped['volume'].transform(lambda x: x.rolling(20, min_periods=5).mean())
    is_resistance_breakout = (df['close'] > high_20_max) & (df['volume'] > 1.5 * vol_20_sma) & (high_20_max > 0)
    
    # 5.2 Double Bottom (Two recent troughs of similar depth)
    low_w1 = grouped['low'].transform(lambda x: x.rolling(15, min_periods=5).min())
    low_w2 = grouped['low'].transform(lambda x: x.shift(20).rolling(15, min_periods=5).min())
    high_between = grouped['high'].transform(lambda x: x.shift(10).rolling(10, min_periods=3).max())
    
    is_double_bottom = (
        (abs(low_w1 - low_w2) / np.maximum(low_w2, 1) < 0.04) &
        (high_between > 1.06 * low_w1) &
        (df['close'] > low_w1 * 1.02) &
        (df['close'] < high_between * 1.1)
    )
    
    # 5.3 Double Top (Two recent peaks of similar height)
    high_w1 = grouped['high'].transform(lambda x: x.rolling(15, min_periods=5).max())
    high_w2 = grouped['high'].transform(lambda x: x.shift(20).rolling(15, min_periods=5).max())
    low_between = grouped['low'].transform(lambda x: x.shift(10).rolling(10, min_periods=3).min())
    
    is_double_top = (
        (abs(high_w1 - high_w2) / np.maximum(high_w2, 1) < 0.04) &
        (low_between < 0.94 * high_w1) &
        (df['close'] < high_w1 * 0.98) &
        (df['close'] > low_between * 0.9)
    )
    
    # Compile patterns into a list of strings
    patterns = pd.Series(index=df.index, dtype=object)
    patterns[:] = ''
    
    # Vectorized string concatenation
    patterns = np.where(is_doji, patterns + 'Doji|', patterns)
    patterns = np.where(is_hammer, patterns + 'Hammer|', patterns)
    patterns = np.where(is_bullish_engulfing, patterns + 'Bullish Engulfing|', patterns)
    patterns = np.where(is_bearish_engulfing, patterns + 'Bearish Engulfing|', patterns)
    patterns = np.where(is_morning_star, patterns + 'Morning Star|', patterns)
    patterns = np.where(is_resistance_breakout, patterns + 'Resistance Breakout|', patterns)
    patterns = np.where(is_double_bottom, patterns + 'Double Bottom|', patterns)
    patterns = np.where(is_double_top, patterns + 'Double Top|', patterns)
    
    # Clean up trailing pipes
    patterns = pd.Series(patterns, index=df.index).astype(str)
    patterns = np.where(patterns.str.endswith('|'), patterns.str[:-1], patterns)
    
    return pd.Series(patterns, index=df.index)


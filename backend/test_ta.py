import pandas as pd
import pandas_ta as ta

df = pd.DataFrame({
    'close': [100 + i for i in range(30)],
    'high': [102 + i for i in range(30)],
    'low': [98 + i for i in range(30)],
    'open': [100 + i for i in range(30)],
    'volume': [1000 + i for i in range(30)]
})

bb = df.ta.bbands(length=20, std=2)
print("Bollinger Bands columns:", bb.columns.tolist())

macd = df.ta.macd(fast=12, slow=26, signal=9)
print("MACD columns:", macd.columns.tolist())

stoch = df.ta.stoch(high=df['high'], low=df['low'], close=df['close'], k=14, d=3, smooth_k=3)
print("Stoch columns:", stoch.columns.tolist())

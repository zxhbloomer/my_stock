import pandas as pd
import sys

parquet = r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2\output\stock_data\300308.SZ.parquet'
df = pd.read_parquet(parquet)
df.index = pd.to_datetime(df['trade_date'])
df = df.sort_index()

# focus on 2026
df26 = df[df.index >= '2026-01-01'].copy()

# vol_ma20
df['vol_ma20'] = df['vol'].rolling(20).mean()

# recompute for 2026 with full history
df26 = df[df.index >= '2026-01-01'].copy()
df26['vol_ma20'] = df['vol_ma20'][df.index >= '2026-01-01']

# BBI slope: bbi_line[0] > bbi_line[-5]  (5 bars ago)
df['bbi_slope5'] = df['bbi_qfq'] > df['bbi_qfq'].shift(5)

# cross_up: prev close < prev bbi AND cur close > cur bbi
df['cross_up'] = (df['close_qfq'].shift(1) < df['bbi_qfq'].shift(1)) & (df['close_qfq'] > df['bbi_qfq'])

# above_ma60
df['above_ma60'] = df['close_qfq'] > df['ma60']

# vol_surge x1.5
df['vol_surge'] = df['vol'] > df['vol_ma20'] * 1.5

df26 = df[df.index >= '2026-01-01'].copy()

cols = ['close_qfq','bbi_qfq','ma60','vol','vol_ma20','cross_up','bbi_slope5','above_ma60','vol_surge']
print(df26[cols].to_string())

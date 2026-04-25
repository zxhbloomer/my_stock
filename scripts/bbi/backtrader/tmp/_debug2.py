import pandas as pd

parquet = r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2\output\stock_data\300308.SZ.parquet'
df = pd.read_parquet(parquet)
df.index = pd.to_datetime(df['trade_date'])
df = df.sort_index()

df['vol_ma20'] = df['vol'].rolling(20).mean()
df['bbi_slope5'] = df['bbi_qfq'] > df['bbi_qfq'].shift(5)
df['cross_up'] = (df['close_qfq'].shift(1) < df['bbi_qfq'].shift(1)) & (df['close_qfq'] > df['bbi_qfq'])
df['above_ma60'] = df['close_qfq'] > df['ma60']
df['vol_surge'] = df['vol'] > df['vol_ma20'] * 1.5
df['close_above_bbi'] = df['close_qfq'] > df['bbi_qfq']

# 2026-01 to 2026-04, show all conditions
df26 = df['2026-01-01':'2026-04-24']
cols = ['close_qfq','bbi_qfq','ma60','cross_up','close_above_bbi','bbi_slope5','above_ma60','vol_surge']
print(df26[cols].to_string())

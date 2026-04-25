import sys
sys.path.insert(0, '.')
from config import STOCK_DATA_DIR, INIT_CASH, ATR_PERIOD, ATR_MULTIPLIER
import pandas as pd
import backtrader as bt

p = sorted(STOCK_DATA_DIR.glob('*.parquet'))[0]
print(f'Smoke test stock: {p.stem}')

df = pd.read_parquet(p)
df.index = pd.to_datetime(df['trade_date'])
df = df.sort_index()
print(f'Rows: {len(df)}, columns: {list(df.columns)}')
print(f'ATR indicator available: {hasattr(bt.indicators, "ATR")}')

# Run single stock
from run_single import run_single_stock
stats, trades = run_single_stock((p.stem, 'test', p))
if stats:
    print(f'trade_count={stats["trade_count"]}, win_rate={stats["win_rate"]:.2%}, calmar={stats["calmar_ratio"]:.3f}')
else:
    print('No stats returned')

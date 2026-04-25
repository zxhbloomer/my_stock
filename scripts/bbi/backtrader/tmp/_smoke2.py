from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import STOCK_DATA_DIR, INIT_CASH, ATR_PERIOD, ATR_MULTIPLIER
from config import MACD_FAST, MACD_SLOW, MACD_SIGNAL, PYRAMID_FIRST_RATIO, PYRAMID_ADD_TRIGGER
import pandas as pd
import backtrader as bt

# inline the run_single_stock function for smoke test
exec(open(Path(__file__).parent / '20_run_backtest.py').read().split('def main():')[0])

p = sorted(STOCK_DATA_DIR.glob('*.parquet'))[0]
print(f'Smoke test: {p.stem}')
df_meta = pd.read_parquet(p, columns=['name'])
name = df_meta['name'].iloc[0]
stats, trades = run_single_stock((p.stem, name, p))
if stats:
    print(f'trade_count={stats["trade_count"]}, win_rate={stats["win_rate"]:.2%}, calmar={stats["calmar_ratio"]:.3f}, max_dd={stats["max_drawdown_pct"]:.2f}%')
    print(f'trades: {len(trades)}')
else:
    print('ERROR: no stats')

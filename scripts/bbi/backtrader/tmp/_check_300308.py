import pandas as pd

trades = pd.read_csv(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\output\trades_detail.csv')
t = trades[trades['ts_code'] == '300308.SZ']
if len(t) == 0:
    print('300308.SZ: no trades found in tmp output')
else:
    print(t[['ts_code','name','buy_date','sell_date','return_pct','hold_days']].to_string())
    print(f'\nLast trade sell_date: {t["sell_date"].iloc[-1]}')

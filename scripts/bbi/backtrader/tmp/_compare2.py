import pandas as pd

v2  = pd.read_csv(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2\output\stats_summary.csv')
tmp = pd.read_csv(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\output\stats_summary.csv')

def summary(df, label):
    active = df[df['trade_count'] > 0]
    print(f'=== {label} ===')
    print(f'  active stocks : {len(active)} / {len(df)}')
    print(f'  total trades  : {active["trade_count"].sum():.0f}')
    print(f'  avg win_rate  : {active["win_rate"].mean()*100:.2f}%')
    print(f'  avg annual_ret: {active["annual_return_pct"].mean():.4f}%')
    print(f'  avg max_dd    : {active["max_drawdown_pct"].mean():.2f}%')
    print(f'  avg calmar    : {active["calmar_ratio"].mean():.4f}')
    print(f'  avg hold_days : {active["avg_hold_days"].mean():.1f}')
    print()

summary(v2,  'v2  baseline (above_ma60, no vol filter)')
summary(tmp, 'tmp (ma60_rising 5d, vol_surge 1.2x, bbi_slope 5d)')

# check 300308.SZ specifically
print('=== 300308.SZ trades in tmp ===')
trades = pd.read_csv(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\output\trades_detail.csv')
t = trades[trades['ts_code'] == '300308.SZ']
print(t[['buy_date','sell_date','return_pct','hold_days']].to_string())

import pandas as pd
import numpy as np
import json

nav = pd.read_csv(
    r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan\output\nav_series.csv',
    parse_dates=['date']
)

with open(
    r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan\output\weekly_records.json',
    encoding='utf-8'
) as f:
    weekly = json.load(f)

nav_arr = nav['nav'].values
years = (nav['date'].iloc[-1] - nav['date'].iloc[0]).days / 365.25
annual = (nav_arr[-1] / nav_arr[0]) ** (1 / years) - 1

daily_ret = pd.Series(nav_arr).pct_change().dropna()
sharpe = daily_ret.mean() / daily_ret.std() * (252 ** 0.5)
peak = nav['nav'].cummax()
dd = ((nav['nav'] - peak) / peak).min() * 100
calmar = annual * 100 / abs(dd)

start = nav['date'].iloc[0].date()
end   = nav['date'].iloc[-1].date()
print(f'期间: {start} ~ {end}  ({years:.1f}年)')
print(f'初始NAV:  {nav_arr[0]:>18,.0f}')
print(f'期末NAV:  {nav_arr[-1]:>18,.0f}')
print(f'总收益:   {(nav_arr[-1]/nav_arr[0]-1)*100:>+.1f}%')
print(f'年化收益: {annual*100:>+.2f}%')
print(f'最大回撤: {dd:.2f}%')
print(f'Sharpe:   {sharpe:.3f}')
print(f'Calmar:   {calmar:.3f}')

rows = []
for w in weekly:
    total = w['total_nav'] or 1
    rows.append({'date': w['date'], 'cash_pct': w['cash'] / total * 100})
df = pd.DataFrame(rows)
df['date'] = pd.to_datetime(df['date'])

print()
print('现金占比（按年）:')
for yr in range(2018, 2027):
    sub = df[df['date'].dt.year == yr]
    if len(sub) > 0:
        print(f'  {yr}: {sub["cash_pct"].mean():.1f}%')

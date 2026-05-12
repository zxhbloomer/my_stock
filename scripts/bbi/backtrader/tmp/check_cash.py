import pandas as pd
import json

nav = pd.read_csv(
    r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan_1\output\nav_series.csv',
    parse_dates=['date']
)

with open(
    r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan_1\output\weekly_records.json',
    encoding='utf-8'
) as f:
    weekly = json.load(f)

rows = []
for w in weekly:
    total    = w['total_nav']
    cash     = w['cash']
    invested = total - cash
    cash_pct = cash / total * 100 if total > 0 else 0
    rows.append({'date': w['date'], 'total_nav': total, 'cash': cash,
                 'invested': invested, 'cash_pct': cash_pct})

df = pd.DataFrame(rows)
df['date'] = pd.to_datetime(df['date'])

print('=== 现金占比统计（按年）===')
for yr in range(2018, 2027):
    sub = df[df['date'].dt.year == yr]
    if len(sub) == 0:
        continue
    avg_cash_pct = sub['cash_pct'].mean()
    max_nav      = sub['total_nav'].max()
    max_cash     = sub['cash'].max()
    print(f'{yr}: 平均现金占比={avg_cash_pct:.1f}%  最大NAV={max_nav:>12,.0f}  最大现金={max_cash:>12,.0f}')

print()
print(f'全期平均现金占比: {df["cash_pct"].mean():.1f}%')
print(f'全期最大现金占比: {df["cash_pct"].max():.1f}%')

last = df.iloc[-1]
print()
print(f'最终状态: NAV={last["total_nav"]:,.0f}  现金={last["cash"]:,.0f}  持仓={last["invested"]:,.0f}  现金占比={last["cash_pct"]:.1f}%')

# 买入金额分布
trd = pd.read_csv(
    r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan_1\output\trade_records.csv'
)
buys = trd[trd['action'] == '买入']['amount'].astype(float)
print()
print('=== 买入金额分布 ===')
print(buys.describe(percentiles=[.25, .5, .75, .9, .99]))
print(f'固定上限 INIT_CASH/TOP_N*1.2 = {500000/5*1.2:,.0f}')

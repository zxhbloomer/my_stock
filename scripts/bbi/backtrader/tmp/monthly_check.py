import pandas as pd
import json

nav = pd.read_csv(
    r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan\output\nav_series.csv',
    parse_dates=['date']
)

trd = pd.read_csv(
    r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan\output\trade_records.csv'
)

with open(
    r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan\output\weekly_records.json',
    encoding='utf-8'
) as f:
    weekly = json.load(f)

# 每月末 NAV
nav['ym'] = nav['date'].dt.to_period('M')
monthly = nav.groupby('ym').last().reset_index()
monthly['prev_nav'] = monthly['nav'].shift(1)
monthly['mom_ret'] = (monthly['nav'] / monthly['prev_nav'] - 1) * 100

print('=== 逐月 NAV 及月度涨幅 ===')
print(f"{'月份':<10} {'月末NAV':>15} {'月度涨幅':>10}")
print('-' * 38)
for _, row in monthly.iterrows():
    chg = f"{row['mom_ret']:>+.1f}%" if pd.notna(row['mom_ret']) else '  首月'
    print(f"{str(row['ym']):<10} {row['nav']:>15,.0f} {chg:>10}")

# 找月度涨幅超过 30% 的月份，详查
print()
print('=== 月度涨幅超过 30% 的月份（需重点核查）===')
big = monthly[monthly['mom_ret'] > 30]
for _, row in big.iterrows():
    ym = str(row['ym'])
    print(f"\n{ym}: NAV {row['prev_nav']:,.0f} -> {row['nav']:,.0f}  (+{row['mom_ret']:.1f}%)")
    # 该月卖出记录
    sells = trd[(trd['action']=='卖出') & (trd['date'].str.startswith(ym))]
    sells = sells.copy()
    sells['pnl_pct'] = pd.to_numeric(sells['pnl_pct'], errors='coerce')
    if len(sells) > 0:
        print(f"  卖出笔数={len(sells)}, 平均收益={sells['pnl_pct'].mean():.1f}%, 最大={sells['pnl_pct'].max():.1f}%")
        top = sells.nlargest(3, 'pnl_pct')[['date','name','price','amount','pnl_pct']]
        for _, t in top.iterrows():
            print(f"    {t['date']} {t['name']}: 成交{t['amount']:,.0f}元 收益{t['pnl_pct']:.1f}%")

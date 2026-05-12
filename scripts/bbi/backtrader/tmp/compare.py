import pandas as pd

v3  = pd.read_csv(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v3\output\stats_summary.csv')
enh = pd.read_csv(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\output\stats_summary.csv')

v3_active  = v3[v3['trade_count'] > 0]
enh_active = enh[enh['trade_count'] > 0]

metrics = ['trade_count','win_rate','avg_return_pct','profit_loss_ratio',
           'annual_return_pct','max_drawdown_pct','calmar_ratio','avg_hold_days']

print('=== 整体对比（有交易的股票均值）===')
print(f"{'指标':<24} {'v3':>10} {'enhanced':>12} {'变化':>10}")
print('-'*60)
for m in metrics:
    v3_val  = v3_active[m].mean()
    enh_val = enh_active[m].mean()
    delta   = enh_val - v3_val
    sign    = '+' if delta >= 0 else ''
    print(f'{m:<24} {v3_val:>10.4f} {enh_val:>12.4f} {sign}{delta:>9.4f}')

print()
print(f'有交易股票数: v3={len(v3_active)}, enhanced={len(enh_active)}')
print(f'总交易笔数:   v3={int(v3_active["trade_count"].sum())}, enhanced={int(enh_active["trade_count"].sum())}')

print()
print('=== 年化收益分布 ===')
for label, df in [('v3', v3_active), ('enhanced', enh_active)]:
    pos = int((df['annual_return_pct'] > 0).sum())
    neg = int((df['annual_return_pct'] <= 0).sum())
    med = df['annual_return_pct'].median()
    p25 = df['annual_return_pct'].quantile(0.25)
    p75 = df['annual_return_pct'].quantile(0.75)
    print(f'{label:<10}: 正收益={pos}, 负收益={neg}, 中位数={med:.2f}%, P25={p25:.2f}%, P75={p75:.2f}%')

print()
print('=== enhanced 表现最好的 10 只（按 Calmar 排序）===')
top10 = enh_active.nlargest(10, 'calmar_ratio')[
    ['ts_code','name','trade_count','win_rate','annual_return_pct','max_drawdown_pct','calmar_ratio']
]
print(top10.to_string(index=False))

import pandas as pd

v1  = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/v1/output/stats_summary.csv')
v24 = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/v2/output/stats_summary.csv')
v5a = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/tmp/output/v5a/stats_summary.csv')

metrics = ['trade_count','win_rate','avg_return_pct','profit_loss_ratio',
           'annual_return_pct','max_drawdown_pct','calmar_ratio','avg_hold_days']

print('=== 全市场平均指标对比 ===')
print(f'{"指标":<22} {"v1":>8} {"v2.4":>8} {"v5a":>8} {"v5a vs v2.4":>12}')
print('-'*62)
for m in metrics:
    v1v  = v1[m].mean()  if m in v1.columns  else float('nan')
    v24v = v24[m].mean() if m in v24.columns else float('nan')
    v5av = v5a[m].mean() if m in v5a.columns else float('nan')
    diff = (v5av - v24v) / abs(v24v) * 100 if v24v != 0 else 0
    print(f'{m:<22} {v1v:>8.4f} {v24v:>8.4f} {v5av:>8.4f} {diff:>+11.1f}%')

# 持仓天数分布
trades = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/tmp/output/v5a/trades_detail.csv')
closed = trades[trades['sell_date'] != '持仓中']
hard_stop = closed[closed['return_pct'] <= -8.0]
print(f'\n=== v5a 交易分析 ===')
print(f'总交易: {len(closed)}, 硬止损: {len(hard_stop)} ({len(hard_stop)/len(closed)*100:.1f}%)')

bins   = [0,5,10,20,30,60,999]
labels = ['1-5d','6-10d','11-20d','21-30d','31-60d','60d+']
closed2 = closed.copy()
closed2['bucket'] = pd.cut(closed2['hold_days'], bins=bins, labels=labels)
for label in labels:
    b = closed2[closed2['bucket']==label]
    if len(b):
        wr  = len(b[b['return_pct']>0]) / len(b) * 100
        avg = b['return_pct'].mean()
        print(f'  {label}: {len(b):5d}笔, 胜率{wr:5.1f}%, 均收益{avg:+6.2f}%')

import pandas as pd
import sys

v1 = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/v1/output/stats_summary.csv')
v2 = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/v2/output/stats_summary.csv')
v4a = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/tmp/output/v4a/stats_summary.csv')

metrics = ['trade_count','win_rate','avg_return_pct','profit_loss_ratio','annual_return_pct','max_drawdown_pct','calmar_ratio','avg_hold_days']
print('=== v1 vs v2.4 vs v4a 全市场平均 ===')
print(f'{"指标":<22} {"v1":>10} {"v2.4":>10} {"v4a":>10}')
print('-'*55)
for m in metrics:
    v1v = v1[m].mean() if m in v1.columns else float('nan')
    v2v = v2[m].mean() if m in v2.columns else float('nan')
    v4v = v4a[m].mean() if m in v4a.columns else float('nan')
    print(f'{m:<22} {v1v:>10.4f} {v2v:>10.4f} {v4v:>10.4f}')

# v2 trades deep analysis
trades = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/v2/output/trades_detail.csv')
closed = trades[trades['sell_date'] != '持仓中']
hard_stop = closed[closed['return_pct'] <= -8.0]
winners = closed[closed['return_pct'] > 0]
losers = closed[closed['return_pct'] <= 0]

print(f'\n=== v2.4 交易深度分析 ===')
print(f'总交易: {len(closed)}')
print(f'硬止损(-8%): {len(hard_stop)} ({len(hard_stop)/len(closed)*100:.1f}%)')
print(f'盈利交易: {len(winners)} ({len(winners)/len(closed)*100:.1f}%)')
print(f'亏损交易: {len(losers)} ({len(losers)/len(closed)*100:.1f}%)')
print(f'平均收益(盈): {winners["return_pct"].mean():.2f}%')
print(f'平均收益(亏): {losers["return_pct"].mean():.2f}%')
print(f'盈亏比: {winners["return_pct"].mean() / abs(losers["return_pct"].mean()):.3f}')

# hold days distribution
print(f'\n=== 持仓天数分布 ===')
bins = [0,5,10,20,30,60,999]
labels = ['1-5d','6-10d','11-20d','21-30d','31-60d','60d+']
closed2 = closed.copy()
closed2['hold_bucket'] = pd.cut(closed2['hold_days'], bins=bins, labels=labels)
for label in labels:
    bucket = closed2[closed2['hold_bucket']==label]
    if len(bucket) > 0:
        wr = len(bucket[bucket['return_pct']>0])/len(bucket)*100
        avg_r = bucket['return_pct'].mean()
        print(f'  {label}: {len(bucket):5d}笔, 胜率{wr:5.1f}%, 均收益{avg_r:+6.2f}%')

import pandas as pd

v24 = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/v2/output/stats_summary.csv')
v5a = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/tmp/output/v5a/stats_summary.csv')
v5c = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/tmp/output/v5c/stats_summary.csv')

metrics = ['trade_count','win_rate','avg_return_pct','profit_loss_ratio',
           'annual_return_pct','max_drawdown_pct','calmar_ratio','avg_hold_days']

print('=== v2.4 vs v5a vs v5c ===')
print(f'{"指标":<22} {"v2.4":>8} {"v5a":>8} {"v5c":>8} {"v5c vs v2.4":>12}')
print('-'*62)
for m in metrics:
    v24v = v24[m].mean()
    v5av = v5a[m].mean()
    v5cv = v5c[m].mean()
    diff = (v5cv - v24v) / abs(v24v) * 100 if v24v != 0 else 0
    print(f'{m:<22} {v24v:>8.4f} {v5av:>8.4f} {v5cv:>8.4f} {diff:>+11.1f}%')

# 硬止损分析
for label, path in [('v5a', 'D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/tmp/output/v5a/trades_detail.csv'),
                    ('v5c', 'D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/tmp/output/v5c/trades_detail.csv')]:
    t = pd.read_csv(path)
    c = t[t['sell_date'] != '持仓中']
    hs = c[c['return_pct'] <= -6.0] if label == 'v5c' else c[c['return_pct'] <= -8.0]
    print(f'\n{label}: 总{len(c)}笔, 硬止损{len(hs)}笔({len(hs)/len(c)*100:.1f}%), 均收益{c["return_pct"].mean():.3f}%')

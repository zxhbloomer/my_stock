import pandas as pd
import numpy as np

v2 = pd.read_csv(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2\output\stats_summary.csv')
trades = pd.read_csv(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2\output\trades_detail.csv')

active = v2[v2['trade_count'] > 0]

# 1. 盈亏比分布
print("=== 盈亏比 (profit_loss_ratio) 分布 ===")
print(active['profit_loss_ratio'].describe())
print(f"  中位数: {active['profit_loss_ratio'].median():.4f}")
print()

# 2. 持仓天数 vs 收益率
t = trades.copy()
t['return_pct'] = pd.to_numeric(t['return_pct'], errors='coerce')
t['hold_days']  = pd.to_numeric(t['hold_days'],  errors='coerce')
t = t.dropna(subset=['return_pct','hold_days'])

bins = [0,3,7,14,30,60,999]
labels = ['1-3天','4-7天','8-14天','15-30天','31-60天','60天+']
t['hold_bucket'] = pd.cut(t['hold_days'], bins=bins, labels=labels)
grp = t.groupby('hold_bucket', observed=True)['return_pct'].agg(['mean','median','count',
    lambda x: (x>0).mean()])
grp.columns = ['avg_ret','median_ret','count','win_rate']
print("=== 持仓天数 vs 收益率 ===")
print(grp.to_string())
print()

# 3. 亏损交易的平均亏损 vs 盈利交易的平均盈利
wins  = t[t['return_pct'] > 0]['return_pct']
loses = t[t['return_pct'] <= 0]['return_pct']
print(f"=== 盈亏不对称分析 ===")
print(f"  盈利笔数: {len(wins)}, 平均盈利: {wins.mean():.2f}%,  最大盈利: {wins.max():.2f}%")
print(f"  亏损笔数: {len(loses)}, 平均亏损: {loses.mean():.2f}%, 最大亏损: {loses.min():.2f}%")
print(f"  盈亏比 (avg_win/avg_loss): {wins.mean()/abs(loses.mean()):.3f}")
print()

# 4. ATR止盈 vs 信号止盈 触发比例
if 'exit_reason' in t.columns:
    print("=== 出场原因分布 ===")
    print(t['exit_reason'].value_counts())
else:
    print("(trades_detail 无 exit_reason 列)")

# v4g_compare.py
# 对比 v4_plan_1（基准）、v4f（MA5>MA20过滤）和 v4g（MA20>MA60过滤）的回测结果
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np

INIT_CASH = 500_000.0
RISK_FREE  = 0.02

BASE = Path(__file__).parent

V1_NAV   = BASE.parent / "v4_plan_1" / "output" / "nav_series.csv"
V4F_NAV  = BASE / "v4f_output" / "nav_series.csv"
V4G_NAV  = BASE / "v4g_output" / "nav_series.csv"

V1_TRADES  = BASE.parent / "v4_plan_1" / "output" / "trade_records.csv"
V4F_TRADES = BASE / "v4f_output" / "trade_records.csv"
V4G_TRADES = BASE / "v4g_output" / "trade_records.csv"


def calc_metrics(nav_path, label):
    df = pd.read_csv(nav_path, parse_dates=['date'])
    df['equity'] = df['nav'] / INIT_CASH
    df['pct_chg'] = df['equity'].pct_change().fillna(0)
    df['max2here'] = df['equity'].expanding().max()
    df['drawdown'] = df['equity'] / df['max2here'] - 1

    total_days = (df['date'].iloc[-1] - df['date'].iloc[0]).days
    total_ret  = df['equity'].iloc[-1] - 1
    annual_ret = (1 + total_ret) ** (365 / total_days) - 1
    max_dd     = df['drawdown'].min()

    excess = df['pct_chg'] - RISK_FREE / 252
    sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0
    calmar = annual_ret / abs(max_dd) if max_dd != 0 else 0

    df2 = df.set_index('date')
    year_ret = df2['pct_chg'].resample('YE').apply(lambda x: (1 + x).prod() - 1)

    return {
        'label': label,
        '累积净值': round(df['equity'].iloc[-1], 3),
        '年化收益': f'{annual_ret*100:.2f}%',
        '最大回撤': f'{max_dd*100:.2f}%',
        '夏普比率': round(sharpe, 3),
        '卡玛比率': round(calmar, 3),
        '最终资产(元)': f'{df["nav"].iloc[-1]:,.0f}',
        '盈利(元)': f'{(df["nav"].iloc[-1] - INIT_CASH):,.0f}',
    }, year_ret


def calc_trade_stats(trade_path, label):
    df = pd.read_csv(trade_path)
    sells = df[df['action'].isin(['卖出']) | df['action'].str.startswith('止损')]
    sells = sells[sells['pnl'].notna() & (sells['pnl'] != 'None')]
    sells['pnl'] = pd.to_numeric(sells['pnl'], errors='coerce')
    sells = sells.dropna(subset=['pnl'])

    if len(sells) == 0:
        return {'label': label, '总交易次数': len(df), '胜率': 'N/A', '平均盈亏': 'N/A'}

    win_rate = (sells['pnl'] > 0).mean()
    avg_pnl  = sells['pnl'].mean()
    stop_loss_cnt = df[df['action'].str.startswith('止损')].shape[0] if 'action' in df.columns else 0

    return {
        'label': label,
        '总交易次数': len(df),
        '卖出次数': len(sells),
        '止损次数': stop_loss_cnt,
        '胜率': f'{win_rate*100:.1f}%',
        '平均每笔盈亏(元)': f'{avg_pnl:,.0f}',
    }


def main():
    print("=" * 70)
    print("  v4_plan_1 vs v4f（MA5>MA20）vs v4g（MA20>MA60）回测对比报告")
    print("=" * 70)

    paths = [(V1_NAV, 'v4_plan_1'), (V4F_NAV, 'v4f'), (V4G_NAV, 'v4g')]
    for p, name in paths:
        if not p.exists():
            print(f"❌ 文件不存在: {p} ({name})")
            return

    m1, yr1 = calc_metrics(V1_NAV,  'v4_plan_1（基准）')
    m2, yr2 = calc_metrics(V4F_NAV, 'v4f（MA5>MA20）')
    m3, yr3 = calc_metrics(V4G_NAV, 'v4g（MA20>MA60）')

    print("\n【核心指标对比】")
    keys = ['累积净值', '年化收益', '最大回撤', '夏普比率', '卡玛比率', '最终资产(元)', '盈利(元)']
    print(f"{'指标':<16} {'v4_plan_1':>16} {'v4f':>16} {'v4g':>16}")
    print("-" * 66)
    for k in keys:
        print(f"{k:<16} {str(m1[k]):>16} {str(m2[k]):>16} {str(m3[k]):>16}")

    print("\n【交易统计对比】")
    t1 = calc_trade_stats(V1_TRADES,  'v4_plan_1')
    t2 = calc_trade_stats(V4F_TRADES, 'v4f')
    t3 = calc_trade_stats(V4G_TRADES, 'v4g')
    tkeys = ['总交易次数', '卖出次数', '止损次数', '胜率', '平均每笔盈亏(元)']
    print(f"{'指标':<20} {'v4_plan_1':>14} {'v4f':>14} {'v4g':>14}")
    print("-" * 64)
    for k in tkeys:
        v1 = str(t1.get(k, 'N/A'))
        v2 = str(t2.get(k, 'N/A'))
        v3 = str(t3.get(k, 'N/A'))
        print(f"{k:<20} {v1:>14} {v2:>14} {v3:>14}")

    print("\n【逐年收益对比】")
    all_years = sorted(set(yr1.index.year) | set(yr2.index.year) | set(yr3.index.year))
    yr1_map = {d.year: v for d, v in yr1.items()}
    yr2_map = {d.year: v for d, v in yr2.items()}
    yr3_map = {d.year: v for d, v in yr3.items()}
    print(f"{'年份':<8} {'v4_plan_1':>12} {'v4f':>12} {'v4g':>12} {'v4g-v1差':>10}")
    print("-" * 58)
    for yr in all_years:
        v1 = yr1_map.get(yr, float('nan'))
        v2 = yr2_map.get(yr, float('nan'))
        v3 = yr3_map.get(yr, float('nan'))
        diff = v3 - v1 if not (pd.isna(v3) or pd.isna(v1)) else float('nan')
        v1s = f'{v1*100:.2f}%' if not pd.isna(v1) else 'N/A'
        v2s = f'{v2*100:.2f}%' if not pd.isna(v2) else 'N/A'
        v3s = f'{v3*100:.2f}%' if not pd.isna(v3) else 'N/A'
        ds  = f'{diff*100:+.2f}%' if not pd.isna(diff) else 'N/A'
        print(f"{yr:<8} {v1s:>12} {v2s:>12} {v3s:>12} {ds:>10}")

    print("\n" + "=" * 70)
    print("结论：")
    v1_ann = float(m1['年化收益'].replace('%', ''))
    v3_ann = float(m3['年化收益'].replace('%', ''))
    v1_dd  = float(m1['最大回撤'].replace('%', ''))
    v3_dd  = float(m3['最大回撤'].replace('%', ''))
    v1_sh  = float(m1['夏普比率'])
    v3_sh  = float(m3['夏普比率'])

    ann_better = v3_ann > v1_ann
    dd_better  = v3_dd > v1_dd
    sh_better  = v3_sh > v1_sh

    print(f"  年化收益: v4g {'↑' if ann_better else '↓'} {abs(v3_ann - v1_ann):.2f}pp vs v4_plan_1")
    print(f"  最大回撤: v4g {'改善' if dd_better else '恶化'} {abs(v3_dd - v1_dd):.2f}pp")
    print(f"  夏普比率: v4g {'↑' if sh_better else '↓'} {abs(v3_sh - v1_sh):.3f}")
    print("=" * 70)


if __name__ == "__main__":
    main()

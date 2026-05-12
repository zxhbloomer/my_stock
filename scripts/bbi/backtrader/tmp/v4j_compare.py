# v4j_compare.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np

INIT_CASH = 500_000.0
BASE = Path(__file__).parent

V1_NAV  = BASE.parent / "v4_plan_1" / "output" / "nav_series.csv"
V4H_NAV = BASE / "v4h_output" / "nav_series.csv"
V4J_NAV = BASE / "v4j_output" / "nav_series.csv"

V1_TRADES  = BASE.parent / "v4_plan_1" / "output" / "trade_records.csv"
V4H_TRADES = BASE / "v4h_output" / "trade_records.csv"
V4J_TRADES = BASE / "v4j_output" / "trade_records.csv"


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

    excess = df['pct_chg'] - 0.02 / 252
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
    }, year_ret


def calc_trade_stats(trade_path, label):
    df = pd.read_csv(trade_path)
    sells = df[df['action'].isin(['卖出']) | df['action'].str.startswith('止损')]
    sells = sells[sells['pnl'].notna() & (sells['pnl'] != 'None')]
    sells['pnl'] = pd.to_numeric(sells['pnl'], errors='coerce')
    sells = sells.dropna(subset=['pnl'])
    if len(sells) == 0:
        return {'label': label, '总交易次数': len(df), '胜率': 'N/A'}
    win_rate = (sells['pnl'] > 0).mean()
    avg_pnl  = sells['pnl'].mean()
    stop_cnt = df[df['action'].str.startswith('止损')].shape[0]
    return {
        'label': label,
        '总交易次数': len(df),
        '卖出次数': len(sells),
        '止损次数': stop_cnt,
        '胜率': f'{win_rate*100:.1f}%',
        '平均每笔盈亏(元)': f'{avg_pnl:,.0f}',
    }


def main():
    print("=" * 72)
    print("  v4_plan_1 vs v4h（收紧止损）vs v4j（+市场降仓）最终对比报告")
    print("=" * 72)

    for p, name in [(V1_NAV, 'v4_plan_1'), (V4H_NAV, 'v4h'), (V4J_NAV, 'v4j')]:
        if not p.exists():
            print(f"❌ 文件不存在: {p} ({name})")
            return

    m1, yr1 = calc_metrics(V1_NAV,  'v4_plan_1')
    m2, yr2 = calc_metrics(V4H_NAV, 'v4h')
    m3, yr3 = calc_metrics(V4J_NAV, 'v4j')

    print("\n【核心指标对比】")
    keys = ['累积净值', '年化收益', '最大回撤', '夏普比率', '卡玛比率', '最终资产(元)']
    print(f"{'指标':<16} {'v4_plan_1':>16} {'v4h':>16} {'v4j':>16}")
    print("-" * 66)
    for k in keys:
        print(f"{k:<16} {str(m1[k]):>16} {str(m2[k]):>16} {str(m3[k]):>16}")

    print("\n【交易统计对比】")
    t1 = calc_trade_stats(V1_TRADES, 'v4_plan_1')
    t2 = calc_trade_stats(V4H_TRADES, 'v4h')
    t3 = calc_trade_stats(V4J_TRADES, 'v4j')
    tkeys = ['总交易次数', '卖出次数', '止损次数', '胜率', '平均每笔盈亏(元)']
    print(f"{'指标':<20} {'v4_plan_1':>14} {'v4h':>14} {'v4j':>14}")
    print("-" * 64)
    for k in tkeys:
        print(f"{k:<20} {str(t1.get(k,'N/A')):>14} {str(t2.get(k,'N/A')):>14} {str(t3.get(k,'N/A')):>14}")

    print("\n【逐年收益对比】")
    all_years = sorted(set(yr1.index.year) | set(yr2.index.year) | set(yr3.index.year))
    yr1_map = {d.year: v for d, v in yr1.items()}
    yr2_map = {d.year: v for d, v in yr2.items()}
    yr3_map = {d.year: v for d, v in yr3.items()}
    print(f"{'年份':<8} {'v4_plan_1':>12} {'v4h':>12} {'v4j':>12} {'v4j-v1':>10}")
    print("-" * 58)
    for yr in all_years:
        v1 = yr1_map.get(yr, float('nan'))
        v2 = yr2_map.get(yr, float('nan'))
        v3 = yr3_map.get(yr, float('nan'))
        diff = v3 - v1 if not (pd.isna(v3) or pd.isna(v1)) else float('nan')
        print(f"{yr:<8} "
              f"{'N/A' if pd.isna(v1) else f'{v1*100:.2f}%':>12} "
              f"{'N/A' if pd.isna(v2) else f'{v2*100:.2f}%':>12} "
              f"{'N/A' if pd.isna(v3) else f'{v3*100:.2f}%':>12} "
              f"{'N/A' if pd.isna(diff) else f'{diff*100:+.2f}%':>10}")

    print("\n" + "=" * 72)
    v1_dd  = float(m1['最大回撤'].replace('%', ''))
    v3_dd  = float(m3['最大回撤'].replace('%', ''))
    v1_ann = float(m1['年化收益'].replace('%', ''))
    v3_ann = float(m3['年化收益'].replace('%', ''))
    v1_sh  = float(m1['夏普比率'])
    v3_sh  = float(m3['夏普比率'])
    print(f"结论: v4j 年化 {'↑' if v3_ann>v1_ann else '↓'}{abs(v3_ann-v1_ann):.2f}pp，"
          f"回撤 {'改善' if v3_dd>v1_dd else '恶化'}{abs(v3_dd-v1_dd):.2f}pp，"
          f"夏普 {'↑' if v3_sh>v1_sh else '↓'}{abs(v3_sh-v1_sh):.3f} vs v4_plan_1")
    print("=" * 72)


if __name__ == "__main__":
    main()

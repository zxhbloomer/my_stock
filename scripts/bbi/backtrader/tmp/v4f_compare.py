# v4f_compare.py
# 对比 v4_plan_1（基准）和 v4f（条件B趋势过滤版）的回测结果
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np

INIT_CASH = 500_000.0
RISK_FREE  = 0.02

V1_NAV  = Path(__file__).parent.parent / "v4_plan_1" / "output" / "nav_series.csv"
V4F_NAV = Path(__file__).parent / "v4f_output" / "nav_series.csv"

V1_TRADES  = Path(__file__).parent.parent / "v4_plan_1" / "output" / "trade_records.csv"
V4F_TRADES = Path(__file__).parent / "v4f_output" / "trade_records.csv"


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

    # 年度收益
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
    print("=" * 60)
    print("  v4_plan_1 vs v4f（条件B趋势过滤）回测对比报告")
    print("=" * 60)

    # 检查文件是否存在
    for p, name in [(V1_NAV, 'v4_plan_1 nav'), (V4F_NAV, 'v4f nav')]:
        if not p.exists():
            print(f"❌ 文件不存在: {p} ({name})")
            return

    m1, yr1 = calc_metrics(V1_NAV,  'v4_plan_1（基准）')
    m2, yr2 = calc_metrics(V4F_NAV, 'v4f（条件B过滤）')

    # 核心指标对比
    print("\n【核心指标对比】")
    keys = ['累积净值', '年化收益', '最大回撤', '夏普比率', '卡玛比率', '最终资产(元)', '盈利(元)']
    print(f"{'指标':<16} {'v4_plan_1':>18} {'v4f':>18}")
    print("-" * 54)
    for k in keys:
        print(f"{k:<16} {str(m1[k]):>18} {str(m2[k]):>18}")

    # 交易统计
    print("\n【交易统计对比】")
    t1 = calc_trade_stats(V1_TRADES,  'v4_plan_1')
    t2 = calc_trade_stats(V4F_TRADES, 'v4f')
    tkeys = ['总交易次数', '卖出次数', '止损次数', '胜率', '平均每笔盈亏(元)']
    print(f"{'指标':<20} {'v4_plan_1':>16} {'v4f':>16}")
    print("-" * 54)
    for k in tkeys:
        v1 = str(t1.get(k, 'N/A'))
        v2 = str(t2.get(k, 'N/A'))
        print(f"{k:<20} {v1:>16} {v2:>16}")

    # 逐年收益对比
    print("\n【逐年收益对比】")
    all_years = sorted(set(yr1.index.year) | set(yr2.index.year))
    yr1_map = {d.year: v for d, v in yr1.items()}
    yr2_map = {d.year: v for d, v in yr2.items()}
    print(f"{'年份':<8} {'v4_plan_1':>14} {'v4f':>14} {'差值':>10}")
    print("-" * 48)
    for yr in all_years:
        v1 = yr1_map.get(yr, float('nan'))
        v2 = yr2_map.get(yr, float('nan'))
        diff = v2 - v1 if not (pd.isna(v1) or pd.isna(v2)) else float('nan')
        v1s = f'{v1*100:.2f}%' if not pd.isna(v1) else 'N/A'
        v2s = f'{v2*100:.2f}%' if not pd.isna(v2) else 'N/A'
        ds  = f'{diff*100:+.2f}%' if not pd.isna(diff) else 'N/A'
        print(f"{yr:<8} {v1s:>14} {v2s:>14} {ds:>10}")

    print("\n" + "=" * 60)
    print("结论：")
    # 自动生成结论
    v1_ann = float(m1['年化收益'].replace('%', ''))
    v2_ann = float(m2['年化收益'].replace('%', ''))
    v1_dd  = float(m1['最大回撤'].replace('%', ''))
    v2_dd  = float(m2['最大回撤'].replace('%', ''))
    v1_sh  = m1['夏普比率']
    v2_sh  = m2['夏普比率']

    ann_better = v2_ann > v1_ann
    dd_better  = v2_dd > v1_dd  # 回撤越小越好（负数，越接近0越好）
    sh_better  = v2_sh > v1_sh

    print(f"  年化收益: v4f {'↑' if ann_better else '↓'} {abs(v2_ann - v1_ann):.2f}pp vs v4_plan_1")
    print(f"  最大回撤: v4f {'改善' if dd_better else '恶化'} {abs(v2_dd - v1_dd):.2f}pp")
    print(f"  夏普比率: v4f {'↑' if sh_better else '↓'} {abs(float(v2_sh) - float(v1_sh)):.3f}")
    print("=" * 60)


if __name__ == "__main__":
    main()

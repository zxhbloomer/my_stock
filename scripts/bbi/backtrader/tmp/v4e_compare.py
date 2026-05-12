import pandas as pd
import numpy as np

V4_NAV  = r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan_1\output\nav_series.csv'
V4E_NAV = r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\v4e_output\nav_series.csv'
V4_TRD  = r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v4_plan_1\output\trade_records.csv'
V4E_TRD = r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\v4e_output\trade_records.csv'

INIT_CASH = 500_000.0


def load_nav(path):
    df = pd.read_csv(path, parse_dates=['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df


def calc_metrics(nav_df, label):
    nav = nav_df['nav'].values
    dates = nav_df['date'].values

    total_ret = (nav[-1] - nav[0]) / nav[0] * 100
    years = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    annual_ret = ((nav[-1] / nav[0]) ** (1 / years) - 1) * 100 if years > 0 else 0

    # daily returns
    daily_ret = np.diff(nav) / nav[:-1]
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0

    # max drawdown
    peak = np.maximum.accumulate(nav)
    dd = (nav - peak) / peak
    max_dd = abs(dd.min()) * 100

    calmar = annual_ret / max_dd if max_dd > 0 else 0

    print(f'\n=== {label} ===')
    print(f'  期间:         {pd.Timestamp(dates[0]).date()} ~ {pd.Timestamp(dates[-1]).date()}  ({years:.1f}年)')
    print(f'  期末净值:     {nav[-1]:,.0f}  (初始 {nav[0]:,.0f})')
    print(f'  总收益:       {total_ret:+.2f}%')
    print(f'  年化收益:     {annual_ret:+.2f}%')
    print(f'  最大回撤:     {max_dd:.2f}%')
    print(f'  Sharpe:       {sharpe:.3f}')
    print(f'  Calmar:       {calmar:.3f}')
    return dict(total_ret=total_ret, annual_ret=annual_ret, max_dd=max_dd, sharpe=sharpe, calmar=calmar)


def trade_stats(path, label):
    df = pd.read_csv(path)
    # v4e uses pnl_pct column; filter to sell records only
    sells = df[df['action'] == '卖出'] if 'action' in df.columns else df
    total = len(sells)
    if total == 0:
        print(f'\n{label} 无卖出交易')
        return
    pct_col = 'pnl_pct' if 'pnl_pct' in sells.columns else ('return_pct' if 'return_pct' in sells.columns else None)
    if pct_col:
        pcts = pd.to_numeric(sells[pct_col], errors='coerce').dropna()
        wins = (pcts > 0).sum()
        win_rate = wins / len(pcts) * 100
        avg_ret = pcts.mean()
    else:
        win_rate = avg_ret = 0
    print(f'\n  {label}')
    print(f'  卖出笔数:     {total}')
    print(f'  胜率:         {win_rate:.1f}%')
    print(f'  平均单笔收益: {avg_ret:.2f}%')


v4_nav  = load_nav(V4_NAV)
v4e_nav = load_nav(V4E_NAV)

m4  = calc_metrics(v4_nav,  'v4_plan_1 (基线)')
m4e = calc_metrics(v4e_nav, 'v4_plan_1_enhanced (MA60+ATR)')

trade_stats(V4_TRD,  'v4_plan_1')
trade_stats(V4E_TRD, 'v4_plan_1_enhanced')

print('\n=== 对比汇总 ===')
print(f"{'指标':<20} {'v4_plan_1':>14} {'v4e':>14} {'变化':>12}")
print('-' * 62)
metrics = [
    ('总收益%',   'total_ret'),
    ('年化收益%', 'annual_ret'),
    ('最大回撤%', 'max_dd'),
    ('Sharpe',    'sharpe'),
    ('Calmar',    'calmar'),
]
for name, key in metrics:
    v = m4[key]; e = m4e[key]
    delta = e - v
    sign = '+' if delta >= 0 else ''
    print(f'{name:<20} {v:>14.3f} {e:>14.3f} {sign}{delta:>11.3f}')

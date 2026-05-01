"""
BBI周度Top-N轮动策略回测
支持3种选股方法：A=BBI突破, B=历史胜率, C=近期涨幅
"""
import pandas as pd
import numpy as np
from pathlib import Path
import os

# ── 路径配置 ──────────────────────────────────────────────
BASE_DIR   = Path(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v3')
STOCK_DIR  = BASE_DIR / 'output' / 'stock_data'
TRADES_CSV = BASE_DIR / 'output' / 'trades_detail.csv'
STOCK_LIST = BASE_DIR / 'output' / 'stock_list.csv'
OUT_DIR    = Path(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\results')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 回测参数 ──────────────────────────────────────────────
INIT_CASH      = 500_000.0
TOP_N          = 5
COMM_BUY       = 0.0005
COMM_SELL      = 0.0015   # 含印花税
MIN_COMM       = 5.0
START_DATE     = '2018-01-01'
END_DATE       = '2026-04-24'
RISK_FREE_RATE = 0.02      # 年化无风险利率


def load_all_stocks():
    """加载所有非688股票数据，返回 dict[ts_code -> DataFrame]"""
    stock_list = pd.read_csv(STOCK_LIST)
    valid_codes = set(stock_list[~stock_list['ts_code'].str.startswith('688')]['ts_code'])

    data = {}
    files = list(STOCK_DIR.glob('*.parquet'))
    print(f'Loading {len(files)} parquet files...')
    for f in files:
        code = f.stem
        if code not in valid_codes:
            continue
        df = pd.read_parquet(f)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        df = df[(df['trade_date'] >= START_DATE) & (df['trade_date'] <= END_DATE)]
        if len(df) < 60:
            continue
        data[code] = df
    print(f'Loaded {len(data)} stocks (non-688, sufficient history)')
    return data


def build_panel(data: dict) -> pd.DataFrame:
    """合并所有股票为面板数据"""
    frames = []
    for code, df in data.items():
        tmp = df[['trade_date', 'close_qfq', 'bbi_qfq']].copy()
        tmp['ts_code'] = code
        frames.append(tmp)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(['trade_date', 'ts_code']).reset_index(drop=True)
    return panel


def get_weekly_mondays(panel: pd.DataFrame) -> list:
    """获取所有交易日中的周一（或该周第一个交易日）"""
    dates = sorted(panel['trade_date'].unique())
    dates_df = pd.DataFrame({'date': dates})
    dates_df['weekday'] = dates_df['date'].dt.weekday  # 0=Monday
    dates_df['week'] = dates_df['date'].dt.isocalendar().week.astype(int)
    dates_df['year'] = dates_df['date'].dt.year
    # 每周第一个交易日
    mondays = dates_df.groupby(['year', 'week'])['date'].min().sort_values().tolist()
    return mondays


def compute_rolling_winrate(trades_df: pd.DataFrame, as_of_date: pd.Timestamp) -> dict:
    """计算截至as_of_date的各股票历史胜率（无前视偏差）"""
    past = trades_df[
        (pd.to_datetime(trades_df['buy_date']) < as_of_date) &
        (trades_df['sell_date'] != '持仓中')
    ].copy()
    if len(past) == 0:
        return {}
    past['win'] = past['return_pct'] > 0
    wr = past.groupby('ts_code')['win'].mean().to_dict()
    return wr


def select_stocks_A(panel_day: pd.DataFrame, prev_day: pd.DataFrame) -> list:
    """方法A: BBI突破 — 今日close>bbi 且 昨日close<=bbi"""
    if prev_day is None or len(prev_day) == 0:
        return []
    merged = panel_day.merge(
        prev_day[['ts_code', 'close_qfq', 'bbi_qfq']].rename(
            columns={'close_qfq': 'prev_close', 'bbi_qfq': 'prev_bbi'}),
        on='ts_code', how='inner'
    )
    # 过滤NaN
    merged = merged.dropna(subset=['close_qfq', 'bbi_qfq', 'prev_close', 'prev_bbi'])
    # 突破条件
    cond = (merged['close_qfq'] > merged['bbi_qfq']) & (merged['prev_close'] <= merged['prev_bbi'])
    candidates = merged[cond].copy()
    if len(candidates) == 0:
        return []
    candidates['score'] = candidates['close_qfq'] / candidates['bbi_qfq'] - 1
    return candidates.nlargest(TOP_N, 'score')['ts_code'].tolist()


def select_stocks_B(panel_day: pd.DataFrame, winrate_map: dict) -> list:
    """方法B: 历史胜率 — 在BBI上方，按历史胜率排序"""
    day = panel_day.dropna(subset=['close_qfq', 'bbi_qfq'])
    above = day[day['close_qfq'] > day['bbi_qfq']].copy()
    if len(above) == 0:
        return []
    above['wr'] = above['ts_code'].map(winrate_map).fillna(0)
    return above.nlargest(TOP_N, 'wr')['ts_code'].tolist()


def select_stocks_C(panel_day: pd.DataFrame, panel_hist: pd.DataFrame,
                    current_date: pd.Timestamp) -> list:
    """方法C: 近期涨幅 — 在BBI上方，按过去5日涨幅排序"""
    day = panel_day.dropna(subset=['close_qfq', 'bbi_qfq'])
    above = day[day['close_qfq'] > day['bbi_qfq']].copy()
    if len(above) == 0:
        return []
    # 计算5日涨幅
    codes = above['ts_code'].tolist()
    hist5 = panel_hist[
        (panel_hist['ts_code'].isin(codes)) &
        (panel_hist['trade_date'] <= current_date)
    ].copy()
    def calc_5d_ret(grp):
        grp = grp.sort_values('trade_date').tail(6)
        if len(grp) < 2:
            return 0.0
        return grp['close_qfq'].iloc[-1] / grp['close_qfq'].iloc[0] - 1
    ret5 = hist5.groupby('ts_code').apply(calc_5d_ret, include_groups=False)
    above['ret5'] = above['ts_code'].map(ret5).fillna(0)
    return above.nlargest(TOP_N, 'ret5')['ts_code'].tolist()


def calc_commission(amount: float, is_buy: bool) -> float:
    rate = COMM_BUY if is_buy else COMM_SELL
    return max(amount * rate, MIN_COMM)


def precompute_winrates(trades_df: pd.DataFrame, mondays: list) -> dict:
    """预计算每个换仓日的滚动胜率，避免重复扫描"""
    print('Precomputing rolling win rates...')
    trades_df = trades_df[trades_df['sell_date'] != '持仓中'].copy()
    trades_df['buy_date'] = pd.to_datetime(trades_df['buy_date'])
    trades_df['win'] = trades_df['return_pct'] > 0
    trades_sorted = trades_df.sort_values('buy_date')

    result = {}
    for monday in mondays:
        past = trades_sorted[trades_sorted['buy_date'] < monday]
        if len(past) == 0:
            result[monday] = {}
        else:
            result[monday] = past.groupby('ts_code')['win'].mean().to_dict()
    print(f'Precomputed win rates for {len(result)} dates')
    return result


def run_backtest(method: str, data: dict, panel: pd.DataFrame,
                 trades_df: pd.DataFrame,
                 winrate_cache: dict = None) -> pd.DataFrame:
    """
    执行回测，返回每日净值序列
    method: 'A' | 'B' | 'C'
    """
    print(f'\n=== Running Method {method} ===')
    mondays = get_weekly_mondays(panel)
    all_dates = sorted(panel['trade_date'].unique())

    cash = INIT_CASH
    holdings = {}   # ts_code -> {'shares': int, 'cost': float}
    nav_series = []  # (date, nav)

    # 预计算每日面板快照
    panel_by_date = {d: panel[panel['trade_date'] == d] for d in all_dates}

    prev_date = None
    monday_set = set(mondays)

    for date in all_dates:
        day_panel = panel_by_date[date]

        # 换仓日（周一）
        if date in monday_set:
            # 1. 选股
            if method == 'A':
                prev_panel = panel_by_date.get(prev_date) if prev_date else None
                new_picks = select_stocks_A(day_panel, prev_panel)
            elif method == 'B':
                wr_map = winrate_cache.get(date, {}) if winrate_cache else compute_rolling_winrate(trades_df, date)
                new_picks = select_stocks_B(day_panel, wr_map)
            else:  # C
                new_picks = select_stocks_C(day_panel, panel, date)

            new_picks_set = set(new_picks)
            current_set = set(holdings.keys())

            # 2. 卖出不在新选股中的持仓
            to_sell = current_set - new_picks_set
            for code in to_sell:
                price_row = day_panel[day_panel['ts_code'] == code]
                if len(price_row) == 0:
                    continue
                price = float(price_row['close_qfq'].iloc[0])
                shares = holdings[code]['shares']
                proceeds = price * shares
                comm = calc_commission(proceeds, is_buy=False)
                cash += proceeds - comm
                del holdings[code]

            # 3. 买入新选股（不在当前持仓中的）
            to_buy = new_picks_set - current_set
            if to_buy:
                alloc_per = cash / max(len(to_buy), 1)
                # 但不超过目标仓位
                target_per = INIT_CASH / TOP_N
                alloc_per = min(alloc_per, target_per * 1.2)
                for code in to_buy:
                    price_row = day_panel[day_panel['ts_code'] == code]
                    if len(price_row) == 0:
                        continue
                    price = float(price_row['close_qfq'].iloc[0])
                    if price <= 0:
                        continue
                    shares = int(alloc_per / price / 100) * 100
                    if shares <= 0:
                        continue
                    cost = price * shares
                    comm = calc_commission(cost, is_buy=True)
                    if cash < cost + comm:
                        shares = int((cash - MIN_COMM) / price / 100) * 100
                        if shares <= 0:
                            continue
                        cost = price * shares
                        comm = calc_commission(cost, is_buy=True)
                    cash -= cost + comm
                    holdings[code] = {'shares': shares, 'cost': price}

        # 计算当日净值
        portfolio_value = cash
        for code, pos in holdings.items():
            price_row = day_panel[day_panel['ts_code'] == code]
            if len(price_row) > 0:
                price = float(price_row['close_qfq'].iloc[0])
                portfolio_value += price * pos['shares']
            else:
                portfolio_value += pos['cost'] * pos['shares']

        nav_series.append({'date': date, 'nav': portfolio_value})
        prev_date = date

    nav_df = pd.DataFrame(nav_series)
    nav_df['method'] = method
    print(f'Method {method} done. Final NAV: {nav_df["nav"].iloc[-1]:,.0f}')
    return nav_df


def calc_metrics(nav_df: pd.DataFrame) -> dict:
    """计算回测指标"""
    nav = nav_df['nav'].values
    dates = pd.to_datetime(nav_df['date'].values)

    total_days = (dates[-1] - dates[0]).days
    total_return = nav[-1] / nav[0] - 1
    annual_return = (1 + total_return) ** (365 / total_days) - 1

    # 最大回撤
    peak = np.maximum.accumulate(nav)
    drawdown = (nav - peak) / peak
    max_dd = drawdown.min()

    # 夏普比率（日度）
    daily_ret = pd.Series(nav).pct_change().dropna()
    excess = daily_ret - RISK_FREE_RATE / 252
    sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0

    # 卡玛比率
    calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

    return {
        'total_return_pct': round(total_return * 100, 2),
        'annual_return_pct': round(annual_return * 100, 2),
        'max_drawdown_pct': round(max_dd * 100, 2),
        'sharpe_ratio': round(sharpe, 3),
        'calmar_ratio': round(calmar, 3),
        'final_nav': round(nav[-1], 0),
    }


def main():
    print('Loading data...')
    data = load_all_stocks()
    panel = build_panel(data)
    trades_df = pd.read_csv(TRADES_CSV)
    trades_df['buy_date'] = pd.to_datetime(trades_df['buy_date'])

    results = {}
    nav_frames = []

    # 预计算方法B的滚动胜率
    panel_tmp = build_panel(data)
    mondays_all = get_weekly_mondays(panel_tmp)
    winrate_cache = precompute_winrates(trades_df, mondays_all)

    for method in ['A', 'B', 'C']:
        nav_df = run_backtest(method, data, panel, trades_df, winrate_cache)
        nav_df.to_csv(OUT_DIR / f'method_{method}_nav.csv', index=False)
        metrics = calc_metrics(nav_df)
        results[f'方法{method}'] = metrics
        nav_frames.append(nav_df)
        print(f'Method {method} metrics: {metrics}')

    # 汇总对比
    summary = pd.DataFrame(results).T
    summary.index.name = 'method'
    summary.to_csv(OUT_DIR / 'comparison.csv')
    print('\n=== Summary ===')
    print(summary.to_string())

    # 与v3对比
    v3_stats = pd.read_csv(
        r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v3\output\stats_summary.csv'
    )
    v3_annual = v3_stats['annual_return_pct'].median()
    v3_maxdd  = v3_stats['max_drawdown_pct'].median()
    print(f'\nv3 median annual_return: {v3_annual:.2f}%')
    print(f'v3 median max_drawdown:  {v3_maxdd:.2f}%')

    return summary


if __name__ == '__main__':
    main()

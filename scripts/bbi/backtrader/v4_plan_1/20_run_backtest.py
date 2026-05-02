# v4_plan_1/20_run_backtest.py
# BBI 周度轮动策略回测 — 增强版
# 在 v4_plan 基础上新增逐日止损检查：
#   硬止损 8% / ATR 追踪止损 / BBI 死叉 / MACD 死叉 / 筹码胜率过高
import json
import csv
import pandas as pd
import numpy as np
from pathlib import Path
from config import (
    START_DATE, END_DATE,
    INIT_CASH, TOP_N,
    COMM_BUY, COMM_SELL, MIN_COMM,
    STOCK_DATA_DIR, OUTPUT_DIR,
    ATR_MULTIPLIER, HARD_STOP_LOSS,
    CHIP_EXIT_THRESHOLD, MIN_HOLD_DAYS,
)
import datetime


def calc_comm(amount, is_buy):
    return max(amount * (COMM_BUY if is_buy else COMM_SELL), MIN_COMM)


def check_stop_loss(code, date, df_indexed, pos):
    """
    检查持仓是否触发止损。
    返回 (triggered: bool, reason: str or None)
    df_indexed: 以 trade_date 为索引的 DataFrame
    pos: holdings[code] 字典（会被原地修改以更新追踪止损状态）
    """
    if date not in df_indexed.index:
        return False, None

    row = df_indexed.loc[date]
    close = float(row['close_qfq'])
    cost  = pos['cost_price']

    # 更新追踪止损峰值
    if close > pos['peak_close']:
        pos['peak_close'] = close
    atr = row.get('atr14', float('nan'))
    if pd.notna(atr) and atr > 0:
        new_stop = pos['peak_close'] - ATR_MULTIPLIER * atr
        pos['trail_stop'] = max(pos['trail_stop'], new_stop)

    # 1. 硬止损（无持仓天数限制）
    if (close - cost) / cost <= -HARD_STOP_LOSS:
        return True, '硬止损'

    # 2. ATR 追踪止损（无持仓天数限制）
    if pos['trail_stop'] > 0 and close < pos['trail_stop']:
        return True, 'ATR追踪止损'

    # 信号类止损需持仓 >= MIN_HOLD_DAYS
    if pos['hold_days'] < MIN_HOLD_DAYS:
        return False, None

    # 3. BBI 死叉 + 4. MACD 死叉（共用 iloc 定位，避免线性扫描）
    bbi_now = float(row['bbi_qfq'])
    try:
        loc = df_indexed.index.get_loc(date)
    except KeyError:
        loc = 0

    if loc >= 1:
        prev_row   = df_indexed.iloc[loc - 1]
        prev_close = float(prev_row['close_qfq'])
        prev_bbi   = float(prev_row['bbi_qfq'])
        if prev_close > prev_bbi and close < bbi_now:
            return True, 'BBI死叉'

    # 4. MACD 死叉 + BBI 3日下行
    macd   = row.get('macd', float('nan'))
    signal = row.get('macd_signal', float('nan'))
    if pd.notna(macd) and pd.notna(signal) and macd < signal and macd < 0:
        if loc >= 3:
            bbi_3d_ago = float(df_indexed.iloc[loc - 3]['bbi_qfq'])
            if bbi_now < bbi_3d_ago:
                return True, 'MACD死叉'

    # 5. 筹码胜率过高（winner_rate 已在 prepare_data 中 shift(1)，是 T-1 数据）
    wr = row.get('winner_rate', float('nan'))
    if pd.notna(wr) and wr > CHIP_EXIT_THRESHOLD:
        return True, '筹码胜率过高'

    return False, None


def load_stocks():
    stock_list_path = OUTPUT_DIR / "stock_list.csv"
    stock_list = pd.read_csv(stock_list_path)
    # 排除科创板
    valid = set(stock_list[~stock_list['ts_code'].str.startswith('688')]['ts_code'])
    name_map = dict(zip(stock_list['ts_code'], stock_list['name']))

    end_date = END_DATE or datetime.date.today().strftime("%Y-%m-%d")
    data = {}
    data_indexed = {}  # 以 trade_date 为索引，供 check_stop_loss 快速查询
    for f in STOCK_DATA_DIR.glob('*.parquet'):
        code = f.stem
        if code not in valid:
            continue
        df = pd.read_parquet(f)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        df = df[(df['trade_date'] >= START_DATE) & (df['trade_date'] <= end_date)]
        if len(df) < 60:
            continue
        data[code] = df
        data_indexed[code] = df.set_index('trade_date')
    print(f'Loaded {len(data)} stocks')
    return data, data_indexed, name_map


def build_panel(data):
    frames = []
    for code, df in data.items():
        tmp = df[['trade_date', 'close_qfq', 'bbi_qfq']].copy()
        tmp['ts_code'] = code
        frames.append(tmp)
    return pd.concat(frames, ignore_index=True).sort_values(['trade_date', 'ts_code']).reset_index(drop=True)


def get_weekly_mondays(panel):
    dates = pd.DataFrame({'date': sorted(panel['trade_date'].unique())})
    dates['year'] = dates['date'].dt.isocalendar().year.astype(int)
    dates['week'] = dates['date'].dt.isocalendar().week.astype(int)
    return dates.groupby(['year', 'week'])['date'].min().sort_values().tolist()


def run_backtest(data, data_indexed, panel, name_map):
    print('Running backtest...')
    mondays = get_weekly_mondays(panel)
    all_dates = sorted(panel['trade_date'].unique())
    panel_by_date = {d: panel[panel['trade_date'] == d].set_index('ts_code') for d in all_dates}

    cash = INIT_CASH
    holdings = {}   # code -> {shares, cost_price, buy_date, name, peak_close, trail_stop, hold_days}
    nav_series = []
    weekly_records = []
    trade_records = []
    monday_set = set(mondays)
    prev_date = None

    for date in all_dates:
        day_panel = panel_by_date[date]

        # 逐日止损检查（非周一也执行）
        for code in list(holdings.keys()):
            pos = holdings[code]
            pos['hold_days'] += 1  # 每日递增持仓天数

            if code not in data_indexed:
                continue
            triggered, reason = check_stop_loss(code, date, data_indexed[code], pos)
            if not triggered:
                continue

            # 止损卖出
            if code not in day_panel.index:
                continue
            price = float(day_panel.loc[code, 'close_qfq'])
            shares = pos['shares']
            proceeds = price * shares
            comm = calc_comm(proceeds, False)
            pnl = proceeds - comm - pos['cost_price'] * shares
            pnl_pct = pnl / (pos['cost_price'] * shares) * 100
            cash += proceeds - comm
            trade_records.append({
                'date': str(date)[:10], 'ts_code': code,
                'name': name_map.get(code, code),
                'action': f'止损卖出({reason})',
                'price': round(price, 3), 'shares': shares,
                'amount': round(proceeds, 0), 'comm': round(comm, 1),
                'pnl': round(pnl, 0), 'pnl_pct': round(pnl_pct, 2),
            })
            del holdings[code]

        if date in monday_set:
            # 选股：BBI 上方 + 5日涨幅最强
            above = day_panel[day_panel['close_qfq'] > day_panel['bbi_qfq']].copy()

            if prev_date is not None:
                ret5_list = []
                for code in above.index:
                    if code in data:
                        hist = data[code][data[code]['trade_date'] <= date].tail(6)
                        r = hist['close_qfq'].iloc[-1] / hist['close_qfq'].iloc[0] - 1 if len(hist) >= 2 else 0.0
                        ret5_list.append((code, r))
                if ret5_list:
                    ret5_df = pd.DataFrame(ret5_list, columns=['ts_code', 'ret5']).set_index('ts_code')
                    above = above.join(ret5_df, how='left').fillna(0)
                    new_picks = above.nlargest(TOP_N, 'ret5').index.tolist()
                else:
                    new_picks = []
            else:
                new_picks = above.index.tolist()[:TOP_N]

            new_set = set(new_picks)
            cur_set = set(holdings.keys())

            # 卖出
            for code in cur_set - new_set:
                if code not in day_panel.index:
                    continue
                price = float(day_panel.loc[code, 'close_qfq'])
                shares = holdings[code]['shares']
                proceeds = price * shares
                comm = calc_comm(proceeds, False)
                pnl = proceeds - comm - holdings[code]['cost_price'] * shares
                pnl_pct = pnl / (holdings[code]['cost_price'] * shares) * 100
                cash += proceeds - comm
                trade_records.append({
                    'date': str(date)[:10], 'ts_code': code,
                    'name': name_map.get(code, code),
                    'action': '卖出',
                    'price': round(price, 3), 'shares': shares,
                    'amount': round(proceeds, 0), 'comm': round(comm, 1),
                    'pnl': round(pnl, 0), 'pnl_pct': round(pnl_pct, 2),
                })
                del holdings[code]

            # 买入
            alloc = min(cash / max(len(new_set - cur_set), 1), INIT_CASH / TOP_N * 1.2)
            for code in new_set - cur_set:
                if code not in day_panel.index:
                    continue
                price = float(day_panel.loc[code, 'close_qfq'])
                if price <= 0:
                    continue
                shares = int(alloc / price / 100) * 100
                if shares <= 0:
                    continue
                cost = price * shares
                comm = calc_comm(cost, True)
                if cash < cost + comm:
                    shares = int((cash - MIN_COMM) / price / 100) * 100
                    if shares <= 0:
                        continue
                    cost = price * shares
                    comm = calc_comm(cost, True)
                cash -= cost + comm
                holdings[code] = {
                    'shares': shares, 'cost_price': price,
                    'buy_date': str(date)[:10], 'name': name_map.get(code, code),
                    'peak_close': price,   # 追踪止损：初始峰值 = 买入价
                    'trail_stop': 0.0,     # 追踪止损线，0 表示未激活
                    'hold_days': 0,        # 持仓天数
                }
                trade_records.append({
                    'date': str(date)[:10], 'ts_code': code,
                    'name': name_map.get(code, code),
                    'action': '买入',
                    'price': round(price, 3), 'shares': shares,
                    'amount': round(cost, 0), 'comm': round(comm, 1),
                    'pnl': None, 'pnl_pct': None,
                })

            # 本周持仓快照
            week_val = cash
            week_pos = []
            for code, pos in holdings.items():
                p = float(day_panel.loc[code, 'close_qfq']) if code in day_panel.index else pos['cost_price']
                mv = p * pos['shares']
                week_val += mv
                week_pos.append({
                    'date': str(date)[:10], 'ts_code': code, 'name': pos['name'],
                    'cost': round(pos['cost_price'], 3), 'price': round(p, 3),
                    'shares': pos['shares'], 'market_value': round(mv, 0),
                    'float_pnl_pct': round((p / pos['cost_price'] - 1) * 100, 2),
                })
            weekly_records.append({
                'date': str(date)[:10],
                'positions': week_pos,
                'cash': round(cash, 0),
                'total_nav': round(week_val, 0),
            })

        # 日净值
        pv = cash
        for code, pos in holdings.items():
            p = float(day_panel.loc[code, 'close_qfq']) if code in day_panel.index else pos['cost_price']
            pv += p * pos['shares']
        nav_series.append({'date': str(date)[:10], 'nav': round(pv, 2)})
        prev_date = date

    print(f'Backtest done. Final NAV: {nav_series[-1]["nav"]:,.0f}')
    return nav_series, weekly_records, trade_records, holdings


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data, data_indexed, name_map = load_stocks()
    panel = build_panel(data)

    nav_series, weekly_records, trade_records, last_holdings = run_backtest(
        data, data_indexed, panel, name_map
    )

    # 保存 nav
    with open(OUTPUT_DIR / 'nav_series.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['date', 'nav'])
        w.writeheader()
        w.writerows(nav_series)

    # 保存 weekly_records
    with open(OUTPUT_DIR / 'weekly_records.json', 'w', encoding='utf-8') as f:
        json.dump(weekly_records, f, ensure_ascii=False)

    # 保存 trade_records
    fields = ['date', 'ts_code', 'name', 'action', 'price', 'shares', 'amount', 'comm', 'pnl', 'pnl_pct']
    with open(OUTPUT_DIR / 'trade_records.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(trade_records)

    # 保存最后一周持仓（供报表生成下周计划）
    last_holdings_list = list(last_holdings.keys())
    with open(OUTPUT_DIR / 'last_holdings.json', 'w', encoding='utf-8') as f:
        json.dump(last_holdings_list, f, ensure_ascii=False)

    print(f'Results saved to {OUTPUT_DIR}')


if __name__ == "__main__":
    main()

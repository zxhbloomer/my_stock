# v4_plan BBI Timing Portfolio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite v4_plan from a weekly rotation strategy into a BBI timing portfolio that manages 5-10 stocks simultaneously using the same entry/add/exit logic as v3.

**Architecture:** Pure pandas event-driven simulation. Each trading day: scan all stocks for BBI golden-cross entry signals, check existing holdings for add-position triggers and stop-loss conditions, then execute next-day open-price orders. Capital pool with rolling allocation enables compounding.

**Tech Stack:** Python, pandas, numpy, pathlib; reads parquet files from v4_plan_1/output/stock_data/

---

## File Structure

- Modify: `scripts/bbi/backtrader/v4_plan/config.py` — replace weekly params with portfolio/position params
- Rewrite: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py` — BBI timing portfolio backtest engine
- No change: `scripts/bbi/backtrader/v4_plan/10_prepare_data.py` — already points to v4_plan_1 parquet data

---

### Task 1: Update config.py

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/config.py`

- [ ] **Step 1: Replace config.py content**

Replace the entire file with:

```python
from pathlib import Path

START_DATE = "2018-01-01"
END_DATE   = None  # None = today

FILTER_MIN_LIST_DAYS  = 365
FILTER_MIN_CIRC_MV    = 1_000_000  # 万元 = 100亿元
FILTER_MIN_AMOUNT     = 50_000     # 千元 = 5000万元

COMMISSION_BUY        = 0.0005
COMMISSION_SELL       = 0.0015
MIN_COMMISSION        = 5.0

INIT_CASH             = 500_000.0

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

BBI_PERIODS = (5, 10, 20, 60)
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

# Portfolio slot management
SLOT_PER_100K        = 1      # 1 slot per 100k total assets
MIN_SLOTS            = 5
MAX_SLOTS            = 10

# ATR trailing stop
ATR_PERIOD           = 14
ATR_MULTIPLIER       = 4.5

# Stop loss
HARD_STOP_LOSS       = 0.08   # 8% hard stop, no hold day limit
MIN_HOLD_DAYS        = 20     # signal-based exits require >= 20 days held

# Chip distribution exit
CHIP_EXIT_THRESHOLD  = 80.0   # winner_rate > 80 triggers exit

# Pyramid add positions (based on entry_alloc snapshot)
PYRAMID_ADD_TRIGGER  = 0.03   # 1st add: profit >= 3%
PYRAMID_ADD1_RATIO   = 0.50   # 1st add = entry_alloc * 50%
PYRAMID_ADD2_RATIO   = 0.25   # 2nd add = entry_alloc * 25%

# Limit-up/down thresholds
LIMIT_UP_THRESHOLD   =  0.095
LIMIT_DOWN_THRESHOLD = -0.095

# Data source: reuse v4_plan_1 parquet files (already contain BBI, ATR14, MACD, winner_rate)
OUTPUT_DIR     = Path(__file__).parent / "output"
V4PLAN1_DATA_DIR = Path(__file__).parent.parent / "v4_plan_1" / "output" / "stock_data"
STOCK_DATA_DIR = V4PLAN1_DATA_DIR
```

- [ ] **Step 2: Verify config loads**

```bash
cd scripts/bbi/backtrader/v4_plan
python -X utf8 -c "import config; print('INIT_CASH:', config.INIT_CASH, 'MIN_SLOTS:', config.MIN_SLOTS)"
```

Expected output: `INIT_CASH: 500000.0 MIN_SLOTS: 5`


---

### Task 2: Rewrite 20_run_backtest.py — Data Loading and Panel Building

**Files:**
- Rewrite: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

This task writes the skeleton and data loading functions. The file will be built incrementally across Tasks 2-4.

- [ ] **Step 1: Write the data loading skeleton**

Replace the entire `scripts/bbi/backtrader/v4_plan/20_run_backtest.py` with:

```python
# v4_plan/20_run_backtest.py
# BBI 择时组合策略回测
# 每日收盘后扫描全市场，发现 BBI 金叉则次日开盘建仓
# 持仓期间逐日检查加仓/止损条件；死叉或止损触发则次日开盘清仓
import json
import csv
import pandas as pd
import numpy as np
from pathlib import Path
import datetime
from config import (
    START_DATE, END_DATE,
    INIT_CASH,
    COMMISSION_BUY, COMMISSION_SELL, MIN_COMMISSION,
    STOCK_DATA_DIR, OUTPUT_DIR,
    SLOT_PER_100K, MIN_SLOTS, MAX_SLOTS,
    ATR_PERIOD, ATR_MULTIPLIER,
    HARD_STOP_LOSS, MIN_HOLD_DAYS, CHIP_EXIT_THRESHOLD,
    PYRAMID_ADD_TRIGGER, PYRAMID_ADD1_RATIO, PYRAMID_ADD2_RATIO,
    LIMIT_UP_THRESHOLD, LIMIT_DOWN_THRESHOLD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
)


def calc_comm(amount, is_buy):
    return max(amount * (COMMISSION_BUY if is_buy else COMMISSION_SELL), MIN_COMMISSION)


def load_stocks():
    """Load all parquet files, compute prev_close and MACD, return dict of DataFrames."""
    stock_list_path = Path(__file__).parent.parent / "v4_plan_1" / "output" / "stock_list.csv"
    stock_list = pd.read_csv(stock_list_path)
    valid = set(stock_list[~stock_list['ts_code'].str.startswith('688')]['ts_code'])
    name_map = dict(zip(stock_list['ts_code'], stock_list['name']))

    end_date = END_DATE or datetime.date.today().strftime("%Y-%m-%d")
    data = {}
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
        df['prev_close'] = df['close_qfq'].shift(1)
        # MACD: EMA-based, computed from close_qfq
        ema_fast = df['close_qfq'].ewm(span=MACD_FAST, adjust=False).mean()
        ema_slow = df['close_qfq'].ewm(span=MACD_SLOW, adjust=False).mean()
        df['macd'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=MACD_SIGNAL, adjust=False).mean()
        data[code] = df
    print(f'Loaded {len(data)} stocks')
    return data, name_map


def build_panel(data):
    """Build a multi-stock panel indexed by (trade_date, ts_code)."""
    frames = []
    for code, df in data.items():
        cols = ['trade_date', 'open_qfq', 'close_qfq', 'bbi_qfq', 'prev_close',
                'atr14', 'macd', 'macd_signal', 'winner_rate']
        available = [c for c in cols if c in df.columns]
        tmp = df[available].copy()
        tmp['ts_code'] = code
        frames.append(tmp)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(['trade_date', 'ts_code']).reset_index(drop=True)
    return panel
```

- [ ] **Step 2: Verify data loads without error**

```bash
cd scripts/bbi/backtrader/v4_plan
python -X utf8 -c "
import sys; sys.path.insert(0, '.')
from 20_run_backtest import load_stocks, build_panel
data, name_map = load_stocks()
panel = build_panel(data)
print('panel shape:', panel.shape)
print('columns:', list(panel.columns))
print('date range:', panel.trade_date.min(), 'to', panel.trade_date.max())
"
```

Expected: panel shape with 8+ columns, date range 2018-01-01 to today.


---

### Task 3: Implement Signal Detection Functions

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py` (append after build_panel)

- [ ] **Step 1: Add signal detection helpers**

Append these functions after `build_panel` in `20_run_backtest.py`:

```python
def is_limit_up(row):
    """True if next-day open is a one-way limit-up board (can't buy)."""
    prev = row.get('prev_close', float('nan'))
    if pd.isna(prev) or prev <= 0:
        return False
    pct = (row['close_qfq'] - prev) / prev
    return (abs(row['open_qfq'] - row['close_qfq']) < row['close_qfq'] * 0.001
            and pct >= LIMIT_UP_THRESHOLD)


def is_limit_down(row):
    """True if next-day open is a one-way limit-down board (sell at close price)."""
    prev = row.get('prev_close', float('nan'))
    if pd.isna(prev) or prev <= 0:
        return False
    pct = (row['close_qfq'] - prev) / prev
    return (abs(row['open_qfq'] - row['close_qfq']) < row['close_qfq'] * 0.001
            and pct <= LIMIT_DOWN_THRESHOLD)


def golden_cross(today_row, prev_row):
    """BBI golden cross: close crossed from below BBI to above BBI."""
    return (prev_row['close_qfq'] < prev_row['bbi_qfq']
            and today_row['close_qfq'] > today_row['bbi_qfq'])


def bbi_slope_up(today_row, row_3ago):
    """BBI 3-day slope is positive."""
    return today_row['bbi_qfq'] > row_3ago['bbi_qfq']


def macd_ok(row):
    """MACD confirmation: MACD > signal OR MACD > 0."""
    m, s = row.get('macd', float('nan')), row.get('macd_signal', float('nan'))
    if pd.isna(m):
        return False
    return m > s or m > 0


def death_cross(today_row, prev_row):
    """BBI death cross: close crossed from above BBI to below BBI."""
    return (prev_row['close_qfq'] > prev_row['bbi_qfq']
            and today_row['close_qfq'] < today_row['bbi_qfq'])


def macd_death(today_row, row_3ago):
    """MACD death cross with BBI declining."""
    m = today_row.get('macd', float('nan'))
    s = today_row.get('macd_signal', float('nan'))
    if pd.isna(m) or pd.isna(s):
        return False
    bbi_declining = today_row['bbi_qfq'] < row_3ago['bbi_qfq']
    return m < s and m < 0 and bbi_declining


def chip_exit(today_row):
    """Chip distribution exit: winner_rate (T-1, already shifted) > threshold."""
    wr = today_row.get('winner_rate', float('nan'))
    return not pd.isna(wr) and wr > CHIP_EXIT_THRESHOLD


def calc_max_slots(total_assets):
    return min(MAX_SLOTS, max(MIN_SLOTS, int(total_assets / 100_000)))


def ret5(data_dict, code, today_date):
    """5-day return for ranking: (close[0] - close[-5]) / close[-5], excludes current day."""
    df = data_dict[code]
    hist = df[df['trade_date'] < today_date].tail(6)  # 6 rows → 5-bar return (T-6 to T-1)
    if len(hist) < 2:
        return 0.0
    return float(hist['close_qfq'].iloc[-1] / hist['close_qfq'].iloc[0] - 1)
```

- [ ] **Step 2: Verify signal functions are importable**

```bash
cd scripts/bbi/backtrader/v4_plan
python -X utf8 -c "
import sys; sys.path.insert(0, '.')
import importlib.util, types
spec = importlib.util.spec_from_file_location('bt', '20_run_backtest.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('golden_cross:', mod.golden_cross)
print('calc_max_slots(500000):', mod.calc_max_slots(500000))
print('calc_max_slots(1000000):', mod.calc_max_slots(1000000))
"
```

Expected: `calc_max_slots(500000): 5`, `calc_max_slots(1000000): 10`


---

### Task 4: Implement Main Backtest Loop

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py` (append after signal functions)

The backtest loop runs day-by-day. On each day T (using T's closing data), it:
1. Updates ATR trailing stops for all holdings
2. Checks exit conditions → marks pending sells for T+1 open
3. Checks add-position conditions → marks pending adds for T+1 open
4. Scans for new golden-cross entries → marks pending buys for T+1 open
5. At T+1 open: executes all pending orders at open price

- [ ] **Step 1: Add the main run_backtest function**

Append after the signal functions in `20_run_backtest.py`:

```python
def run_backtest(data, panel, name_map):
    print('Running backtest...')
    all_dates = sorted(panel['trade_date'].unique())
    panel_by_date = {d: panel[panel['trade_date'] == d].set_index('ts_code') for d in all_dates}

    cash = INIT_CASH
    # holdings[code] = {
    #   'shares': int, 'cost_price': float (weighted avg),
    #   'entry_alloc': float (snapshot at entry, basis for add sizing),
    #   'add_count': int (0, 1, or 2),
    #   'add1_close': float or None (close when 1st add triggered),
    #   'peak_close': float, 'trail_stop': float or None,
    #   'hold_days': int, 'buy_date': str, 'name': str,
    #   'pending_sell': bool, 'pending_add': int (0=none,1=add1,2=add2),
    #   'pending_buy': bool,
    # }
    holdings = {}
    # pending_buys: list of (code, alloc) to execute at next open
    pending_buys = []
    nav_series = []
    trade_records = []
    skipped_limit_up = 0
    limit_down_sells = 0

    for i, date in enumerate(all_dates):
        day_panel = panel_by_date[date]
        prev_date = all_dates[i - 1] if i > 0 else None
        prev_panel = panel_by_date[prev_date] if prev_date else None
        date_3ago = all_dates[i - 3] if i >= 3 else None
        panel_3ago = panel_by_date[date_3ago] if date_3ago else None

        # ── EXECUTE PENDING ORDERS AT TODAY'S OPEN ──
        # 1. Execute pending sells
        for code in list(holdings.keys()):
            pos = holdings[code]
            if not pos.get('pending_sell'):
                continue
            if code not in day_panel.index:
                continue
            row = day_panel.loc[code]
            if is_limit_down(row):
                # Cannot sell today — retry tomorrow, do NOT credit cash
                limit_down_sells += 1
                continue  # pending_sell stays True

            # Non-limit-down: execute the sell at open price
            price = float(row['open_qfq']) if row['open_qfq'] > 0 else float(row['close_qfq'])
            pos['pending_sell'] = False
            shares = pos['shares']
            proceeds = price * shares
            comm = calc_comm(proceeds, False)
            pnl = proceeds - comm - pos['cost_price'] * shares
            pnl_pct = pnl / (pos['cost_price'] * shares) * 100
            cash += proceeds - comm
            trade_records.append({
                'date': str(date)[:10], 'ts_code': code,
                'name': pos['name'],
                'action': '卖出',
                'price': round(price, 3), 'shares': shares,
                'amount': round(proceeds, 0), 'comm': round(comm, 1),
                'pnl': round(pnl, 0), 'pnl_pct': round(pnl_pct, 2),
            })
            del holdings[code]

        # 2. Execute pending add positions
        for code in list(holdings.keys()):
            pos = holdings[code]
            if pos.get('pending_add', 0) == 0:
                continue
            if code not in day_panel.index:
                continue
            row = day_panel.loc[code]
            if is_limit_up(row):
                skipped_limit_up += 1
                pos['pending_add'] = 0
                continue
            add_num = pos['pending_add']
            ratio = PYRAMID_ADD1_RATIO if add_num == 1 else PYRAMID_ADD2_RATIO
            add_amount = pos['entry_alloc'] * ratio
            price = float(row['open_qfq']) if row['open_qfq'] > 0 else float(row['close_qfq'])
            shares = int(add_amount / price / 100) * 100
            if shares <= 0 or cash < price * shares + MIN_COMMISSION:
                pos['pending_add'] = 0
                continue
            cost = price * shares
            comm = calc_comm(cost, True)
            if cash < cost + comm:
                pos['pending_add'] = 0
                continue
            cash -= cost + comm
            # Update weighted average cost
            total_shares = pos['shares'] + shares
            new_cost = (pos['cost_price'] * pos['shares'] + price * shares) / total_shares
            pos['shares'] = total_shares
            pos['cost_price'] = new_cost
            # Update trail_stop: take higher of ATR stop and new avg cost (breakeven protection)
            if pos['trail_stop'] is not None:
                pos['trail_stop'] = max(pos['trail_stop'], new_cost)
            pos['add_count'] = add_num
            if add_num == 1:
                pos['add1_close'] = price  # execution open price — known at order time, no look-ahead
            pos['pending_add'] = 0
            trade_records.append({
                'date': str(date)[:10], 'ts_code': code,
                'name': pos['name'],
                'action': f'加仓{add_num}',
                'price': round(price, 3), 'shares': shares,
                'amount': round(cost, 0), 'comm': round(comm, 1),
                'pnl': None, 'pnl_pct': None,
            })

        # 3. Execute pending new buys
        for code, alloc in pending_buys:
            if code in holdings:
                continue  # already holding
            if code not in day_panel.index:
                continue
            row = day_panel.loc[code]
            if is_limit_up(row):
                skipped_limit_up += 1
                continue
            price = float(row['open_qfq']) if row['open_qfq'] > 0 else float(row['close_qfq'])
            if price <= 0:
                continue
            shares = int(alloc / price / 100) * 100
            if shares <= 0:
                continue
            cost = price * shares
            comm = calc_comm(cost, True)
            if cash < cost + comm:
                shares = int((cash - MIN_COMMISSION) / price / 100) * 100
                if shares <= 0:
                    continue
                cost = price * shares
                comm = calc_comm(cost, True)
            cash -= cost + comm
            holdings[code] = {
                'shares': shares, 'cost_price': price,
                'entry_alloc': alloc,
                'add_count': 0, 'add1_close': None,
                'peak_close': price, 'trail_stop': None,
                'hold_days': 0, 'buy_date': str(date)[:10],
                'name': name_map.get(code, code),
                'pending_sell': False, 'pending_add': 0,
            }
            trade_records.append({
                'date': str(date)[:10], 'ts_code': code,
                'name': name_map.get(code, code),
                'action': '买入',
                'price': round(price, 3), 'shares': shares,
                'amount': round(cost, 0), 'comm': round(comm, 1),
                'pnl': None, 'pnl_pct': None,
            })
        pending_buys = []

        # ── EVALUATE TODAY'S CLOSING DATA → GENERATE TOMORROW'S ORDERS ──
        # Update hold_days and ATR trailing stop for all holdings
        for code, pos in holdings.items():
            if code not in day_panel.index:
                continue
            row = day_panel.loc[code]
            pos['hold_days'] += 1
            close = float(row['close_qfq'])
            if close > pos['peak_close']:
                pos['peak_close'] = close
            atr = row.get('atr14', float('nan'))
            if not pd.isna(atr) and atr > 0:
                new_stop = pos['peak_close'] - ATR_MULTIPLIER * float(atr)
                if pos['trail_stop'] is None or new_stop > pos['trail_stop']:
                    pos['trail_stop'] = new_stop

        # Check exit conditions for each holding
        for code, pos in holdings.items():
            if pos.get('pending_sell'):
                continue
            if code not in day_panel.index:
                continue
            row = day_panel.loc[code]
            close = float(row['close_qfq'])
            loss_pct = (close - pos['cost_price']) / pos['cost_price']

            # Hard stop: always fires regardless of hold days
            if loss_pct <= -HARD_STOP_LOSS:
                pos['pending_sell'] = True
                continue

            # ATR trailing stop: always fires
            if pos['trail_stop'] is not None and close < pos['trail_stop']:
                pos['pending_sell'] = True
                continue

            # Signal-based exits: require >= MIN_HOLD_DAYS
            if pos['hold_days'] < MIN_HOLD_DAYS:
                continue

            if prev_panel is not None and code in prev_panel.index:
                prev_row = prev_panel.loc[code]
                if death_cross(row, prev_row):
                    pos['pending_sell'] = True
                    continue

            if panel_3ago is not None and code in panel_3ago.index:
                row_3 = panel_3ago.loc[code]
                if macd_death(row, row_3):
                    pos['pending_sell'] = True
                    continue

            if chip_exit(row):
                pos['pending_sell'] = True
                continue

        # Check add-position conditions for each holding
        for code, pos in holdings.items():
            if pos.get('pending_sell') or pos.get('pending_add', 0) > 0:
                continue
            if code not in day_panel.index:
                continue
            row = day_panel.loc[code]
            close = float(row['close_qfq'])
            m = row.get('macd', float('nan'))

            if pos['add_count'] == 0:
                profit_pct = (close - pos['cost_price']) / pos['cost_price']
                if profit_pct >= PYRAMID_ADD_TRIGGER and not pd.isna(m) and m > 0:
                    pos['pending_add'] = 1

            elif pos['add_count'] == 1 and pos['add1_close'] is not None:
                atr = row.get('atr14', float('nan'))
                if not pd.isna(atr) and close >= pos['add1_close'] + float(atr):
                    if not pd.isna(m) and m > 0:
                        pos['pending_add'] = 2

        # Scan for new golden-cross entries
        total_assets = cash + sum(
            float(day_panel.loc[c, 'close_qfq']) * p['shares']
            if c in day_panel.index else p['cost_price'] * p['shares']
            for c, p in holdings.items()
        )
        max_slots = calc_max_slots(total_assets)
        empty_slots = max_slots - len(holdings)

        if empty_slots > 0 and prev_panel is not None and panel_3ago is not None:
            candidates = []
            for code in day_panel.index:
                if code in holdings:
                    continue
                if code.startswith('688'):
                    continue
                row = day_panel.loc[code]
                if code not in prev_panel.index or code not in panel_3ago.index:
                    continue
                prev_row = prev_panel.loc[code]
                row_3 = panel_3ago.loc[code]
                if (golden_cross(row, prev_row)
                        and bbi_slope_up(row, row_3)
                        and macd_ok(row)):
                    r5 = ret5(data, code, date)
                    candidates.append((code, r5))

            # Sort by 5-day return descending, take top empty_slots
            candidates.sort(key=lambda x: x[1], reverse=True)
            available_cash = cash
            for code, _ in candidates[:empty_slots]:
                current_empty = max_slots - len(holdings) - len(pending_buys)
                if current_empty <= 0:
                    break
                alloc = available_cash / current_empty
                pending_buys.append((code, alloc))
                available_cash -= alloc  # rolling deduction

        # Daily NAV (mark-to-market at close)
        pv = cash
        for code, pos in holdings.items():
            p = float(day_panel.loc[code, 'close_qfq']) if code in day_panel.index else pos['cost_price']
            pv += p * pos['shares']
        nav_series.append({'date': str(date)[:10], 'nav': round(pv, 2)})

    print(f'Backtest done. Final NAV: {nav_series[-1]["nav"]:,.0f}')
    print(f'Skipped limit-up buys: {skipped_limit_up}')
    print(f'Limit-down sells: {limit_down_sells}')
    return nav_series, trade_records, holdings
```

- [ ] **Step 2: Add main() function**

Append after `run_backtest` in `20_run_backtest.py`:

```python
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data, name_map = load_stocks()
    panel = build_panel(data)

    nav_series, trade_records, last_holdings = run_backtest(data, panel, name_map)

    with open(OUTPUT_DIR / 'nav_series.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['date', 'nav'])
        w.writeheader()
        w.writerows(nav_series)

    fields = ['date', 'ts_code', 'name', 'action', 'price', 'shares', 'amount', 'comm', 'pnl', 'pnl_pct']
    with open(OUTPUT_DIR / 'trade_records.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(trade_records)

    last_holdings_out = {
        code: {
            'shares': pos['shares'],
            'cost_price': round(pos['cost_price'], 4),
            'add_count': pos['add_count'],
            'hold_days': pos['hold_days'],
            'name': pos['name'],
        }
        for code, pos in last_holdings.items()
    }
    with open(OUTPUT_DIR / 'last_holdings.json', 'w', encoding='utf-8') as f:
        json.dump(last_holdings_out, f, ensure_ascii=False, indent=2)

    print(f'Results saved to {OUTPUT_DIR}')


if __name__ == "__main__":
    main()
```


---

### Task 5: Run Backtest and Verify Results

**Files:**
- Run: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

- [ ] **Step 1: Run the backtest**

```bash
cd scripts/bbi/backtrader/v4_plan
python -X utf8 20_run_backtest.py
```

Expected output (approximate):
```
Loaded ~3000 stocks
Running backtest...
Backtest done. Final NAV: X,XXX,XXX
Skipped limit-up buys: N
Limit-down sells: N
Results saved to .../v4_plan/output
```

- [ ] **Step 2: Verify output files exist**

```bash
python -X utf8 -c "
from pathlib import Path
out = Path('output')
for f in ['nav_series.csv', 'trade_records.csv', 'last_holdings.json']:
    p = out / f
    print(f, 'exists:', p.exists(), 'size:', p.stat().st_size if p.exists() else 0)
"
```

Expected: all 3 files exist with non-zero size.

- [ ] **Step 3: Sanity-check NAV series**

```bash
python -X utf8 -c "
import pandas as pd
nav = pd.read_csv('output/nav_series.csv')
print('rows:', len(nav))
print('start NAV:', nav.iloc[0]['nav'])
print('end NAV:', nav.iloc[-1]['nav'])
print('max NAV:', nav['nav'].max())
print('min NAV:', nav['nav'].min())
init = 500_000
final = nav.iloc[-1]['nav']
total_ret = (final - init) / init * 100
years = len(nav) / 252
annual = ((final / init) ** (1 / years) - 1) * 100
print(f'Total return: {total_ret:.1f}%')
print(f'Annual return (CAGR): {annual:.1f}%')
"
```

Expected: start NAV ~500000, final NAV > 500000 (strategy should be profitable), CAGR > 0%.

- [ ] **Step 4: Sanity-check trade records**

```bash
python -X utf8 -c "
import pandas as pd
tr = pd.read_csv('output/trade_records.csv')
print('Total records:', len(tr))
print('Actions:', tr['action'].value_counts().to_dict())
buys = tr[tr['action'] == '买入']
sells = tr[tr['action'] == '卖出']
print('Buy count:', len(buys))
print('Sell count:', len(sells))
closed = tr[tr['pnl'].notna()]
if len(closed) > 0:
    win = (closed['pnl'] > 0).sum()
    print(f'Win rate: {win}/{len(closed)} = {win/len(closed)*100:.1f}%')
    print(f'Avg PnL per trade: {closed["pnl"].mean():.0f}')
"
```

Expected: buy count > 100, sell count similar to buy count, win rate > 30% (v3 baseline is 35.7%).

- [ ] **Step 5: Check last holdings**

```bash
python -X utf8 -c "
import json
with open('output/last_holdings.json') as f:
    h = json.load(f)
print(f'Open positions at end: {len(h)}')
for code, pos in h.items():
    print(f'  {code} {pos["name"]}: {pos["shares"]} shares @ {pos["cost_price"]:.3f}, held {pos["hold_days"]} days, adds: {pos["add_count"]}')
"
```

Expected: 0-10 open positions, each with reasonable hold_days and cost_price.


---

## Pre-flight Check

Before running Task 2, verify the v4_plan_1 parquet files contain the required columns:

```bash
python -X utf8 -c "
import pandas as pd
from pathlib import Path
p = next(Path('../v4_plan_1/output/stock_data').glob('*.parquet'))
df = pd.read_parquet(p)
print('columns:', list(df.columns))
required = ['close_qfq', 'open_qfq', 'bbi_qfq', 'atr14', 'winner_rate']
missing = [c for c in required if c not in df.columns]
print('missing:', missing if missing else 'none - all present')
"
```

If `atr14` is missing, run `scripts/bbi/backtrader/v4_plan_1/10_prepare_data.py` first to regenerate the parquet files.

---

## Notes

- The `10_prepare_data.py` in v4_plan does NOT need modification — it already points to v4_plan_1 data via the updated `config.py` `STOCK_DATA_DIR`.
- MACD is computed in `load_stocks()` from `close_qfq` because v4_plan_1 parquet files may not include pre-computed MACD columns. If they do, the computed values will be identical.
- The `pending_sell` flag stays `True` on limit-down days, so the sell retries on the next trading day automatically.
- `entry_alloc` is snapshotted at buy time and never changes — this is the basis for all add-position sizing regardless of subsequent price moves.

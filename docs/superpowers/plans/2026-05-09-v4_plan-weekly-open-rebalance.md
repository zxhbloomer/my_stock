# v4_plan Weekly Open Rebalance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `scripts/bbi/backtrader/v4_plan` into a weekly open rebalance portfolio backtest that uses the v3 entry signal, realistic open-price limit/suspension constraints, rolling candidate-observation ranking, and no stop-loss or add-position logic.

**Architecture:** Keep `10_prepare_data.py` as the data producer and rewrite `20_run_backtest.py` as a focused weekly state machine. Add explicit output files for real fills (`trade_records.csv`), non-fill events (`trade_events.csv`), and candidate ranking plus observation trades (`candidate_rank_records.csv`). Update `30_generate_report.py` to present the new weekly strategy surface and remove old stop/add assumptions.

**Tech Stack:** Python 3.8-compatible scripts, pandas, parquet files from `output/stock_data`, Plotly HTML report. Do not operate git.

---

## File Structure

- Modify: `scripts/bbi/backtrader/v4_plan/config.py`
  - Add output paths for `candidate_rank_records.csv` and `trade_events.csv`.
  - Add ranking constants for observation minimum samples and Calmar clipping.

- Rewrite: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`
  - Keep CLI arguments and data loading shape.
  - Remove old daily entry, stop-loss, ATR, death-cross, chip-exit, and add-position logic.
  - Implement weekly calendar state machine, v3 entry signal, rolling candidate observation ranking, real fills, event logging, NAV, and holdings output.

- Modify: `scripts/bbi/backtrader/v4_plan/30_generate_report.py`
  - Load new output files.
  - Update strategy descriptions and quality/event statistics.
  - Display true trade records separately from non-fill events and candidate ranking summary.

- Already modified: `scripts/bbi/backtrader/v4_plan/README.md`
  - Keep it aligned after implementation if code output fields differ.

---

### Task 1: Configuration Surface

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/config.py`

- [ ] **Step 1: Add output and ranking constants**

Insert near the existing output path constants:

```python
CANDIDATE_RANK_PATH = OUTPUT_DIR / "candidate_rank_records.csv"
TRADE_EVENTS_PATH   = OUTPUT_DIR / "trade_events.csv"

OBS_MIN_TRADES      = 5
CALMAR_DD_FLOOR     = 0.01
CALMAR_CLIP         = 10.0
```

- [ ] **Step 2: Verify config imports**

Run:

```powershell
python -X utf8 -m py_compile scripts/bbi/backtrader/v4_plan/config.py
```

Expected: command exits with code `0`.

---

### Task 2: Rewrite Backtest Imports and Core Helpers

**Files:**
- Rewrite: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

- [ ] **Step 1: Replace imports**

Use this import block:

```python
# v4_plan/20_run_backtest.py
# Weekly open rebalance portfolio backtest.
import argparse
import csv
import datetime
import json
import math
from collections import defaultdict

import pandas as pd

from config import (
    START_DATE, END_DATE,
    INIT_CASH,
    COMMISSION_BUY, COMMISSION_SELL, MIN_COMMISSION,
    STOCK_DATA_DIR, OUTPUT_DIR, RUN_STATS_PATH,
    CANDIDATE_RANK_PATH, TRADE_EVENTS_PATH,
    MIN_SLOTS, MAX_SLOTS,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    OBS_MIN_TRADES, CALMAR_DD_FLOOR, CALMAR_CLIP,
)
```

- [ ] **Step 2: Keep CLI and basic utilities**

Define these functions near the top:

```python
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=START_DATE, help="YYYY-MM-DD")
    parser.add_argument("--end", default=END_DATE, help="YYYY-MM-DD")
    parser.add_argument("--codes", default="", help="Comma-separated ts_code list for quick validation")
    return parser.parse_args()


def calc_comm(amount, is_buy):
    rate = COMMISSION_BUY if is_buy else COMMISSION_SELL
    return max(amount * rate, MIN_COMMISSION)


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def calc_max_slots(total_assets):
    return min(MAX_SLOTS, max(MIN_SLOTS, int(total_assets / 100_000)))
```

- [ ] **Step 3: Add MACD-compatible loader helpers**

Use this data loading behavior:

```python
def ensure_macd(df):
    if "macd" in df.columns and "macd_signal" in df.columns:
        return df
    ema_fast = df["close_qfq"].ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = df["close_qfq"].ewm(span=MACD_SLOW, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    return df


def load_stocks(start_date, end_date, requested_codes=None):
    stock_list_path = OUTPUT_DIR / "stock_list.csv"
    if not stock_list_path.exists():
        raise FileNotFoundError(f"Missing {stock_list_path}. Run 10_prepare_data.py first.")

    stock_list = pd.read_csv(stock_list_path)
    if requested_codes:
        stock_list = stock_list[stock_list["ts_code"].isin(requested_codes)].reset_index(drop=True)
    valid = set(stock_list["ts_code"])
    name_map = dict(zip(stock_list["ts_code"], stock_list["name"]))

    data = {}
    for f in STOCK_DATA_DIR.glob("*.parquet"):
        code = f.stem
        if code not in valid:
            continue
        df = pd.read_parquet(f)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.sort_values("trade_date").reset_index(drop=True)
        df = df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)]
        if len(df) < 60:
            continue

        for col in ["is_suspended", "is_st", "is_eligible", "is_liquid", "is_listed_long_enough"]:
            if col not in df.columns:
                df[col] = False
            df[col] = df[col].fillna(False).astype(bool)

        df = ensure_macd(df)
        data[code] = df

    print(f"Loaded {len(data)} stocks")
    return data, name_map
```

- [ ] **Step 4: Add panel builder**

Use this function:

```python
def build_panel(data):
    frames = []
    cols = [
        "trade_date",
        "open", "close",
        "open_qfq", "close_qfq", "bbi_qfq",
        "macd", "macd_signal",
        "up_limit", "down_limit", "adj_factor",
        "is_suspended", "is_eligible", "is_liquid", "is_st",
    ]
    for code, df in data.items():
        available = [c for c in cols if c in df.columns]
        tmp = df[available].copy()
        tmp["ts_code"] = code
        frames.append(tmp)
    if not frames:
        raise RuntimeError("No stock parquet files loaded.")
    panel = pd.concat(frames, ignore_index=True)
    return panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
```

- [ ] **Step 5: Compile**

Run:

```powershell
python -X utf8 -m py_compile scripts/bbi/backtrader/v4_plan/20_run_backtest.py
```

Expected: may fail only if later functions referenced by `main` are not yet added. If so, continue to Task 3 before compiling again.

---

### Task 3: Trading Constraint and Signal Helpers

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

- [ ] **Step 1: Add open-price constraint helpers**

Add:

```python
def is_suspended_or_missing(row):
    return bool(row.get("is_suspended", False))


def get_open_price(row):
    price = safe_float(row.get("open"))
    return price if not pd.isna(price) and price > 0 else None


def is_limit_up_at_open(row):
    price = safe_float(row.get("open"))
    up_limit = safe_float(row.get("up_limit"))
    if pd.isna(price) or pd.isna(up_limit) or up_limit <= 0:
        return False
    return price >= up_limit - 1e-6


def is_limit_down_at_open(row):
    price = safe_float(row.get("open"))
    down_limit = safe_float(row.get("down_limit"))
    if pd.isna(price) or pd.isna(down_limit) or down_limit <= 0:
        return False
    return price <= down_limit + 1e-6


def can_buy_open(row, stats):
    if is_suspended_or_missing(row):
        stats["suspended_trade_skips"] += 1
        return False, "suspended"
    if pd.isna(row.get("up_limit")) or pd.isna(row.get("down_limit")):
        stats["missing_limit_rows"] += 1
    if is_limit_up_at_open(row):
        stats["skipped_limit_up_buys"] += 1
        return False, "limit_up"
    if get_open_price(row) is None:
        stats["suspended_trade_skips"] += 1
        return False, "missing_open"
    return True, ""


def can_sell_open(row, stats):
    if is_suspended_or_missing(row):
        stats["suspended_trade_skips"] += 1
        return False, "suspended"
    if pd.isna(row.get("up_limit")) or pd.isna(row.get("down_limit")):
        stats["missing_limit_rows"] += 1
    if is_limit_down_at_open(row):
        stats["limit_down_sell_delays"] += 1
        return False, "limit_down"
    if get_open_price(row) is None:
        stats["suspended_trade_skips"] += 1
        return False, "missing_open"
    return True, ""
```

- [ ] **Step 2: Add v3 entry signal helpers**

Add:

```python
def v3_entry_signal(today_row, prev_row, row_3ago):
    return (
        safe_float(prev_row["close_qfq"]) < safe_float(prev_row["bbi_qfq"])
        and safe_float(today_row["close_qfq"]) > safe_float(today_row["bbi_qfq"])
        and safe_float(today_row["bbi_qfq"]) > safe_float(row_3ago["bbi_qfq"])
        and (
            safe_float(today_row.get("macd")) > safe_float(today_row.get("macd_signal"))
            or safe_float(today_row.get("macd")) > 0
        )
    )


def ret5(data_dict, code, signal_date):
    df = data_dict[code]
    hist = df[df["trade_date"] <= signal_date].tail(6)
    if len(hist) < 2:
        return 0.0
    return float(hist["close_qfq"].iloc[-1] / hist["close_qfq"].iloc[0] - 1)
```

- [ ] **Step 3: Add weekly calendar helpers**

Add:

```python
def build_week_map(all_dates):
    week_map = {}
    by_week = defaultdict(list)
    for d in all_dates:
        iso = pd.Timestamp(d).isocalendar()
        by_week[(int(iso.year), int(iso.week))].append(d)
    for week_key, dates in by_week.items():
        ordered = sorted(dates)
        for d in ordered:
            week_map[d] = {
                "week_key": week_key,
                "first": ordered[0],
                "last": ordered[-1],
                "single_day": len(ordered) == 1,
            }
    return week_map
```

- [ ] **Step 4: Compile**

Run:

```powershell
python -X utf8 -m py_compile scripts/bbi/backtrader/v4_plan/20_run_backtest.py
```

Expected: no syntax errors once all references are present, or continue to next tasks if `run_backtest` is still missing.

---

### Task 4: Rolling Candidate Observation Ranking

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

- [ ] **Step 1: Add rolling metric helpers**

Add:

```python
def calc_observation_metrics(done_observations):
    if not done_observations:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "calmar": 0.0,
        }

    returns = [float(o["return_pct"]) for o in done_observations]
    wins = [r for r in returns if r > 0]
    avg_return = sum(returns) / len(returns)
    win_rate = len(wins) / len(returns)

    equity = 1.0
    curve = []
    for r in returns:
        equity *= 1 + r / 100.0
        curve.append(equity)
    peak = -float("inf")
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        dd = value / peak - 1.0
        max_dd = min(max_dd, dd)

    first_buy = pd.Timestamp(done_observations[0]["buy_date"])
    last_sell = pd.Timestamp(done_observations[-1]["sell_date"])
    span_days = max((last_sell - first_buy).days, 1)
    annual_return = equity ** (365.0 / span_days) - 1.0
    calmar = annual_return / max(abs(max_dd), CALMAR_DD_FLOOR)
    calmar = max(-CALMAR_CLIP, min(CALMAR_CLIP, calmar))

    return {
        "trade_count": len(returns),
        "win_rate": win_rate,
        "avg_return_pct": avg_return,
        "calmar": calmar,
    }
```

- [ ] **Step 2: Add candidate rank builder**

Add:

```python
def build_candidates(data, name_map, panel_by_date, signal_date, buy_date, observations_done):
    signal_panel = panel_by_date[signal_date]
    all_dates = sorted(panel_by_date.keys())
    idx = all_dates.index(signal_date)
    if idx < 3:
        return []
    prev_panel = panel_by_date[all_dates[idx - 1]]
    panel_3ago = panel_by_date[all_dates[idx - 3]]

    rows = []
    for code in signal_panel.index:
        row = signal_panel.loc[code]
        if not bool(row.get("is_eligible", False)):
            continue
        if code not in prev_panel.index or code not in panel_3ago.index:
            continue
        if not v3_entry_signal(row, prev_panel.loc[code], panel_3ago.loc[code]):
            continue

        metrics = calc_observation_metrics(observations_done.get(code, []))
        r5 = ret5(data, code, signal_date)
        score_group = "performance" if metrics["trade_count"] >= OBS_MIN_TRADES else "ret5_fallback"
        rows.append({
            "signal_date": str(signal_date)[:10],
            "buy_date": str(buy_date)[:10],
            "ts_code": code,
            "name": name_map.get(code, code),
            "ret5": r5,
            "trade_count": metrics["trade_count"],
            "win_rate": metrics["win_rate"],
            "avg_return_pct": metrics["avg_return_pct"],
            "calmar": metrics["calmar"],
            "score_group": score_group,
            "selected": False,
            "skip_reason": "",
            "observed": False,
            "observation_buy_price": "",
            "observation_sell_date": "",
            "observation_sell_price": "",
            "observation_return_pct": "",
            "observation_status": "",
        })

    def sort_key(item):
        if item["score_group"] == "performance":
            return (0, -item["avg_return_pct"], -item["calmar"], -item["win_rate"], -item["ret5"], item["ts_code"])
        return (1, -item["ret5"], item["ts_code"])

    rows.sort(key=sort_key)
    for rank, item in enumerate(rows, start=1):
        item["rank"] = rank
    return rows
```

- [ ] **Step 3: Add observation simulator**

Add:

```python
def simulate_candidate_observation(candidate, panel_by_date, all_dates, week_map, stats):
    buy_date = pd.Timestamp(candidate["buy_date"])
    if buy_date not in panel_by_date:
        candidate["observation_status"] = "unbuyable_missing_day"
        return None
    buy_panel = panel_by_date[buy_date]
    code = candidate["ts_code"]
    if code not in buy_panel.index:
        candidate["observation_status"] = "unbuyable_suspended"
        return None
    buy_row = buy_panel.loc[code]
    ok, reason = can_buy_open(buy_row, stats)
    if not ok:
        candidate["observation_status"] = f"unbuyable_{reason}"
        return None
    buy_price = get_open_price(buy_row)
    week_info = week_map[buy_date]
    sell_start = week_info["last"]
    sell_idx = all_dates.index(sell_start)
    sell_date = None
    sell_price = None
    for d in all_dates[sell_idx:]:
        panel = panel_by_date[d]
        if code not in panel.index:
            continue
        sell_row = panel.loc[code]
        ok, _ = can_sell_open(sell_row, stats)
        if ok:
            sell_date = d
            sell_price = get_open_price(sell_row)
            break
    if sell_date is None or sell_price is None:
        candidate["observed"] = True
        candidate["observation_buy_price"] = round(buy_price, 4)
        candidate["observation_status"] = "open"
        return None

    return_pct = (sell_price - buy_price) / buy_price * 100.0
    candidate["observed"] = True
    candidate["observation_buy_price"] = round(buy_price, 4)
    candidate["observation_sell_date"] = str(sell_date)[:10]
    candidate["observation_sell_price"] = round(sell_price, 4)
    candidate["observation_return_pct"] = round(return_pct, 4)
    candidate["observation_status"] = "completed"
    return {
        "buy_date": str(buy_date)[:10],
        "sell_date": str(sell_date)[:10],
        "return_pct": return_pct,
    }
```

Note: `simulate_candidate_observation` reuses open constraints and increments stats; if this pollutes real run stats too much, isolate observation stats in implementation by passing a copy or a separate observation stats dict. The final run stats should clearly distinguish real trading constraints from observation constraints.

---

### Task 5: Real Portfolio State Machine

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

- [ ] **Step 1: Add adjustment and valuation helpers**

Add:

```python
def apply_adj_factor(pos, row, stats):
    adj = safe_float(row.get("adj_factor"))
    if pd.isna(adj) or adj <= 0:
        stats["missing_adj_factor_rows"] += 1
        return
    last = pos.get("last_adj_factor")
    if last is None or pd.isna(last) or last <= 0:
        pos["last_adj_factor"] = adj
        return
    if abs(adj - last) / last < 1e-8:
        return
    ratio = adj / last
    if ratio <= 0:
        stats["missing_adj_factor_rows"] += 1
        return
    pos["shares"] *= ratio
    pos["cost_price"] /= ratio
    pos["last_adj_factor"] = adj
    stats["adj_factor_adjustments"] += 1


def mark_to_market(code, pos, day_panel, stats, count_missing=True):
    if code in day_panel.index:
        row = day_panel.loc[code]
        close = safe_float(row.get("close"))
        if not pd.isna(close) and close > 0:
            pos["last_close"] = close
            return close
    if count_missing:
        stats["missing_quote_valuations"] += 1
    return pos.get("last_close", pos["cost_price"])
```

- [ ] **Step 2: Add real sell executor**

Add:

```python
def execute_sell(date, code, pos, row, cash, trade_records, trade_events, stats, reason):
    ok, block_reason = can_sell_open(row, stats)
    if not ok:
        pos["pending_sell"] = True
        pos.setdefault("pending_since", str(date)[:10])
        pending_days = (pd.Timestamp(date) - pd.Timestamp(pos["pending_since"])).days
        trade_events.append({
            "date": str(date)[:10],
            "ts_code": code,
            "name": pos["name"],
            "event": "sell_delay",
            "reason": block_reason,
            "price": round(safe_float(row.get("open"), 0.0), 4),
            "up_limit": round(safe_float(row.get("up_limit"), 0.0), 4),
            "down_limit": round(safe_float(row.get("down_limit"), 0.0), 4),
            "pending_days": pending_days,
        })
        return cash, False

    price = get_open_price(row)
    shares = pos["shares"]
    proceeds = price * shares
    comm = calc_comm(proceeds, False)
    cost_basis = pos["cost_price"] * shares
    pnl = proceeds - comm - cost_basis
    pnl_pct = pnl / cost_basis * 100 if cost_basis > 0 else 0.0
    cash += proceeds - comm
    trade_records.append({
        "date": str(date)[:10],
        "ts_code": code,
        "name": pos["name"],
        "action": "卖出",
        "price": round(price, 3),
        "shares": round(shares, 4),
        "amount": round(proceeds, 0),
        "comm": round(comm, 1),
        "pnl": round(pnl, 0),
        "pnl_pct": round(pnl_pct, 2),
        "reason": reason,
    })
    return cash, True
```

- [ ] **Step 3: Add real buy executor**

Add:

```python
def execute_buy(date, code, row, alloc, cash, holdings, name_map, trade_records, trade_events, stats):
    ok, reason = can_buy_open(row, stats)
    if not ok:
        trade_events.append({
            "date": str(date)[:10],
            "ts_code": code,
            "name": name_map.get(code, code),
            "event": "buy_skip",
            "reason": reason,
            "price": round(safe_float(row.get("open"), 0.0), 4),
            "up_limit": round(safe_float(row.get("up_limit"), 0.0), 4),
            "down_limit": round(safe_float(row.get("down_limit"), 0.0), 4),
            "pending_days": 0,
        })
        return cash, False
    price = get_open_price(row)
    shares = int(alloc / price / 100) * 100
    if shares <= 0:
        return cash, False
    cost = price * shares
    comm = calc_comm(cost, True)
    if cash < cost + comm:
        shares = int((cash - MIN_COMMISSION) / price / 100) * 100
        if shares <= 0:
            return cash, False
        cost = price * shares
        comm = calc_comm(cost, True)
    cash -= cost + comm
    close = safe_float(row.get("close"), price)
    holdings[code] = {
        "shares": float(shares),
        "cost_price": price,
        "buy_date": str(date)[:10],
        "name": name_map.get(code, code),
        "pending_sell": False,
        "pending_since": "",
        "last_close": close,
        "last_adj_factor": safe_float(row.get("adj_factor"), None),
    }
    trade_records.append({
        "date": str(date)[:10],
        "ts_code": code,
        "name": name_map.get(code, code),
        "action": "买入",
        "price": round(price, 3),
        "shares": shares,
        "amount": round(cost, 0),
        "comm": round(comm, 1),
        "pnl": None,
        "pnl_pct": None,
        "reason": "weekly_buy",
    })
    return cash, True
```

- [ ] **Step 4: Implement `run_backtest` loop**

Use the state machine from the design:

```python
def run_backtest(data, panel, name_map):
    print("Running weekly open rebalance backtest...")
    all_dates = sorted(panel["trade_date"].unique())
    panel_by_date = {d: panel[panel["trade_date"] == d].set_index("ts_code") for d in all_dates}
    week_map = build_week_map(all_dates)

    cash = INIT_CASH
    holdings = {}
    nav_series = []
    trade_records = []
    trade_events = []
    candidate_records = []
    observations_done = defaultdict(list)
    delayed_buy_pending = False

    stats = {
        "candidate_rows": 0,
        "selected_rows": 0,
        "skipped_limit_up_buys": 0,
        "limit_down_sell_delays": 0,
        "suspended_trade_skips": 0,
        "pending_sell_successes": 0,
        "buy_days": 0,
        "sell_days": 0,
        "max_pending_sell_days": 0,
        "avg_pending_sell_days": 0.0,
        "missing_quote_valuations": 0,
        "missing_limit_rows": 0,
        "missing_adj_factor_rows": 0,
        "adj_factor_adjustments": 0,
    }
    pending_days_done = []

    for i, date in enumerate(all_dates):
        day_panel = panel_by_date[date]
        week_info = week_map[date]
        is_week_first = date == week_info["first"]
        is_week_last = date == week_info["last"]
        is_single_day_week = bool(week_info["single_day"])
        skip_buy_today = False

        for code, pos in list(holdings.items()):
            if code in day_panel.index:
                apply_adj_factor(pos, day_panel.loc[code], stats)

        for code in list(holdings.keys()):
            pos = holdings[code]
            if not pos.get("pending_sell"):
                continue
            if code not in day_panel.index:
                continue
            cash, sold = execute_sell(date, code, pos, day_panel.loc[code], cash, trade_records, trade_events, stats, "pending_sell_exit")
            if sold:
                pending_since = pos.get("pending_since")
                if pending_since:
                    pending_days_done.append((pd.Timestamp(date) - pd.Timestamp(pending_since)).days)
                del holdings[code]
                stats["pending_sell_successes"] += 1
                skip_buy_today = True

        if is_week_last:
            sold_any = False
            for code in list(holdings.keys()):
                pos = holdings[code]
                if pos.get("pending_sell"):
                    continue
                if code not in day_panel.index:
                    pos["pending_sell"] = True
                    pos["pending_since"] = str(date)[:10]
                    continue
                cash, sold = execute_sell(date, code, pos, day_panel.loc[code], cash, trade_records, trade_events, stats, "weekly_exit")
                if sold:
                    del holdings[code]
                    sold_any = True
            if sold_any:
                stats["sell_days"] += 1
            if any(p.get("pending_sell") for p in holdings.values()):
                delayed_buy_pending = True

        total_assets = cash + sum(
            mark_to_market(c, p, day_panel, stats, count_missing=False) * p["shares"]
            for c, p in holdings.items()
        )
        max_slots = calc_max_slots(total_assets)
        available_slots = max_slots - len(holdings)
        can_buy = (
            (is_week_first or delayed_buy_pending)
            and not is_week_last
            and not is_single_day_week
            and not skip_buy_today
            and available_slots > 0
            and cash >= MIN_COMMISSION
            and i > 0
        )

        if can_buy:
            signal_date = all_dates[i - 1]
            candidates = build_candidates(data, name_map, panel_by_date, signal_date, date, observations_done)
            stats["candidate_rows"] += len(candidates)

            for cand in candidates:
                obs = simulate_candidate_observation(cand, panel_by_date, all_dates, week_map, stats)
                if obs is not None:
                    observations_done[cand["ts_code"]].append(obs)

            selected = candidates[:available_slots]
            for cand in selected:
                cand["selected"] = True
            stats["selected_rows"] += len(selected)
            candidate_records.extend(candidates)

            if selected:
                target_amount = total_assets / max_slots
                for cand in selected:
                    code = cand["ts_code"]
                    if code in holdings or code not in day_panel.index:
                        continue
                    alloc = min(target_amount, cash)
                    cash, bought = execute_buy(date, code, day_panel.loc[code], alloc, cash, holdings, name_map, trade_records, trade_events, stats)
                    if not bought:
                        cand["skip_reason"] = "buy_failed"
                stats["buy_days"] += 1
                delayed_buy_pending = False

        pv = cash
        for code, pos in holdings.items():
            pv += mark_to_market(code, pos, day_panel, stats) * pos["shares"]
        nav_series.append({"date": str(date)[:10], "nav": round(pv, 2)})

    if pending_days_done:
        stats["max_pending_sell_days"] = max(pending_days_done)
        stats["avg_pending_sell_days"] = round(sum(pending_days_done) / len(pending_days_done), 2)

    print(f'Backtest done. Final NAV: {nav_series[-1]["nav"]:,.0f}')
    return nav_series, trade_records, trade_events, candidate_records, holdings, stats
```

- [ ] **Step 5: Review observation stats pollution**

If `simulate_candidate_observation` inflates real trading stats, split stats into `real_stats` and `observation_stats`. The expected final `run_stats.json` should make this explicit, for example `observation_limit_up_skips` separate from `skipped_limit_up_buys`.

---

### Task 6: Output Writers and Main

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

- [ ] **Step 1: Add output writers**

Use explicit field lists:

```python
def write_outputs(nav_series, trade_records, trade_events, candidate_records, last_holdings, run_stats):
    with open(OUTPUT_DIR / "nav_series.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "nav"])
        w.writeheader()
        w.writerows(nav_series)

    trade_fields = ["date", "ts_code", "name", "action", "price", "shares", "amount", "comm", "pnl", "pnl_pct", "reason"]
    with open(OUTPUT_DIR / "trade_records.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=trade_fields)
        w.writeheader()
        w.writerows(trade_records)

    event_fields = ["date", "ts_code", "name", "event", "reason", "price", "up_limit", "down_limit", "pending_days"]
    with open(TRADE_EVENTS_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=event_fields)
        w.writeheader()
        w.writerows(trade_events)

    candidate_fields = [
        "signal_date", "buy_date", "rank", "ts_code", "name", "selected",
        "ret5", "trade_count", "win_rate", "avg_return_pct", "calmar",
        "score_group", "skip_reason", "observed", "observation_buy_price",
        "observation_sell_date", "observation_sell_price", "observation_return_pct",
        "observation_status",
    ]
    with open(CANDIDATE_RANK_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=candidate_fields)
        w.writeheader()
        w.writerows(candidate_records)

    holdings_out = {
        code: {
            "shares": round(pos["shares"], 4),
            "cost_price": round(pos["cost_price"], 4),
            "last_close": round(pos.get("last_close", pos["cost_price"]), 4),
            "name": pos["name"],
            "pending_sell": bool(pos.get("pending_sell", False)),
            "pending_since": pos.get("pending_since", ""),
            "buy_date": pos.get("buy_date", ""),
        }
        for code, pos in last_holdings.items()
    }
    with open(OUTPUT_DIR / "last_holdings.json", "w", encoding="utf-8") as f:
        json.dump(holdings_out, f, ensure_ascii=False, indent=2)

    with open(RUN_STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(run_stats, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 2: Update `main`**

Use:

```python
def main():
    args = parse_args()
    start_date = args.start or START_DATE
    end_date = args.end or END_DATE or datetime.date.today().strftime("%Y-%m-%d")
    requested_codes = {c.strip() for c in args.codes.split(",") if c.strip()}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data, name_map = load_stocks(start_date, end_date, requested_codes)
    panel = build_panel(data)
    nav_series, trade_records, trade_events, candidate_records, last_holdings, run_stats = run_backtest(data, panel, name_map)
    write_outputs(nav_series, trade_records, trade_events, candidate_records, last_holdings, run_stats)
    print(f"Results saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Compile**

Run:

```powershell
python -X utf8 -m py_compile scripts/bbi/backtrader/v4_plan/20_run_backtest.py
```

Expected: exits `0`.

---

### Task 7: Report Update

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/30_generate_report.py`

- [ ] **Step 1: Load new files**

Update `load_results()` to also read:

```python
candidate_df = pd.read_csv(OUTPUT_DIR / "candidate_rank_records.csv") if (OUTPUT_DIR / "candidate_rank_records.csv").exists() else pd.DataFrame()
events_df = pd.read_csv(OUTPUT_DIR / "trade_events.csv") if (OUTPUT_DIR / "trade_events.csv").exists() else pd.DataFrame()
```

Return them with the existing return tuple.

- [ ] **Step 2: Update current holdings columns**

Replace `加仓次数` with pending fields:

```python
rows.append({
    '代码': code,
    '名称': pos['name'],
    '持仓股数': pos['shares'],
    '成本价': round(pos['cost_price'], 3),
    '最新价': round(last_price, 3),
    '信号价(qfq)': '-' if signal_price is None else round(signal_price, 3),
    '浮盈%': f"{float_pnl_pct:+.2f}%",
    '买入日期': pos.get('buy_date', '-'),
    '待卖出': '是' if pos.get('pending_sell') else '否',
    '待卖出起始': pos.get('pending_since') or '-',
})
```

- [ ] **Step 3: Update quality/event figure**

Add rows for:

```python
('候选排序文件行数', len(candidate_df) if candidate_df is not None else 0)
('交易事件文件行数', len(events_df) if events_df is not None else 0)
('真实买入日数', run_stats.get('buy_days', 0))
('真实卖出日数', run_stats.get('sell_days', 0))
('pending卖出成功', run_stats.get('pending_sell_successes', 0))
('pending最大延迟天数', run_stats.get('max_pending_sell_days', 0))
('pending平均延迟天数', run_stats.get('avg_pending_sell_days', 0))
```

- [ ] **Step 4: Update HTML text**

Replace strategy wording with:

```html
<p>策略口径：每周第一个实际交易日开盘买入，每周最后一个实际交易日开盘卖出；买入信号严格参考 v3 BBI 上穿入场；不止损、不加仓；涨停开盘买不了，跌停/停牌开盘卖不出并延迟处理。</p>
```

- [ ] **Step 5: Compile**

Run:

```powershell
python -X utf8 -m py_compile scripts/bbi/backtrader/v4_plan/30_generate_report.py
```

Expected: exits `0`.

---

### Task 8: Documentation Alignment

**Files:**
- Modify if needed: `scripts/bbi/backtrader/v4_plan/README.md`
- Modify if needed: `docs/superpowers/specs/2026-05-09-v4_plan-weekly-open-rebalance-design.md`

- [ ] **Step 1: Verify output filenames**

Run:

```powershell
rg -n "candidate_rank_records|trade_events|加仓|止损|ATR|death_cross|chip_exit|PYRAMID" scripts/bbi/backtrader/v4_plan/README.md docs/superpowers/specs/2026-05-09-v4_plan-weekly-open-rebalance-design.md
```

Expected:

- `candidate_rank_records` appears in both docs.
- `trade_events` appears in both docs.
- Old strategy terms only appear as “not used” or validation exclusions.

- [ ] **Step 2: Update README if implementation changed field names**

If code uses different field names than the current README, update README to match the implemented output exactly.

---

### Task 9: Verification

**Files:**
- No planned source edits unless verification exposes a bug.

- [ ] **Step 1: Compile all touched scripts**

Run:

```powershell
python -X utf8 -m py_compile scripts/bbi/backtrader/v4_plan/config.py scripts/bbi/backtrader/v4_plan/20_run_backtest.py scripts/bbi/backtrader/v4_plan/30_generate_report.py
```

Expected: exits `0`.

- [ ] **Step 2: Static old-logic search**

Run:

```powershell
rg -n "HARD_STOP_LOSS|PYRAMID|trail_stop|chip_exit|death_cross|pending_add|v4_plan_1" scripts/bbi/backtrader/v4_plan
```

Expected:

- No matches in `20_run_backtest.py`.
- README/spec matches are acceptable only if they describe removed logic or validation.

- [ ] **Step 3: Run full prepared-output backtest**

Run:

```powershell
cd scripts/bbi/backtrader/v4_plan
python -X utf8 20_run_backtest.py
```

Expected:

- Exits `0`.
- Writes `output/nav_series.csv`.
- Writes `output/trade_records.csv`.
- Writes `output/trade_events.csv`.
- Writes `output/candidate_rank_records.csv`.
- Writes `output/run_stats.json`.

- [ ] **Step 4: Run report**

Run:

```powershell
cd scripts/bbi/backtrader/v4_plan
python -X utf8 30_generate_report.py
```

Expected:

- Exits `0`.
- Writes `output/report.html`.

- [ ] **Step 5: Validate buy/sell weekdays and no add trades**

Run:

```powershell
$env:PYTHONIOENCODING='utf-8'; @'
import pandas as pd
from pathlib import Path
base = Path('scripts/bbi/backtrader/v4_plan/output')
tr = pd.read_csv(base/'trade_records.csv', parse_dates=['date'])
print(tr['action'].value_counts(dropna=False).to_string())
assert not tr['action'].astype(str).str.contains('加仓').any()
print('No add trades')
'@ | python -X utf8 -
```

Expected:

- Prints only `买入` and `卖出` actions.
- Prints `No add trades`.

- [ ] **Step 6: Validate output files are nonempty and columns exist**

Run:

```powershell
$env:PYTHONIOENCODING='utf-8'; @'
import pandas as pd
from pathlib import Path
base = Path('scripts/bbi/backtrader/v4_plan/output')
checks = {
    'trade_records.csv': ['date','ts_code','action','reason'],
    'trade_events.csv': ['date','ts_code','event','reason'],
    'candidate_rank_records.csv': ['signal_date','buy_date','rank','ts_code','selected','score_group','observation_status'],
}
for name, cols in checks.items():
    df = pd.read_csv(base/name)
    print(name, len(df))
    missing = [c for c in cols if c not in df.columns]
    assert not missing, (name, missing)
print('Output schema OK')
'@ | python -X utf8 -
```

Expected:

- Each file prints row count.
- Prints `Output schema OK`.

- [ ] **Step 7: Validate no future signal date**

Run:

```powershell
$env:PYTHONIOENCODING='utf-8'; @'
import pandas as pd
from pathlib import Path
base = Path('scripts/bbi/backtrader/v4_plan/output')
c = pd.read_csv(base/'candidate_rank_records.csv', parse_dates=['signal_date','buy_date'])
assert (c['signal_date'] < c['buy_date']).all()
print('Signal dates precede buy dates')
'@ | python -X utf8 -
```

Expected: prints `Signal dates precede buy dates`.

- [ ] **Step 8: Inspect final summary**

Run:

```powershell
Get-Content -LiteralPath 'scripts\bbi\backtrader\v4_plan\output\run_stats.json'
```

Expected:

- JSON includes buy/sell day counts.
- JSON includes pending sell delay stats.
- JSON includes candidate and selected row counts.

---

### Task 10: Review Checkpoint

**Files:**
- No edits unless review finds issues.

- [ ] **Step 1: Perform implementation review**

Review these areas before declaring done:

- Does `20_run_backtest.py` read only `v4_plan/output` and not `v4_plan_1`?
- Does `v3_entry_signal` match v3 `_entry_signal()` exactly?
- Does `can_buy` match the design boolean expression?
- Are true fills separated from non-fill events?
- Does rolling performance use only completed candidate observations available before the signal date?
- Are pending sell holdings counted in available slots?
- Is there no add-position code?

- [ ] **Step 2: Report residual risks**

In the final implementation response, mention:

- Whether full backtest and report generation passed.
- Final NAV and max drawdown from the run, if computed.
- Any known remaining modeling limits, especially candidate observation simplifications and `adj_factor` validation.

---

## Notes for Executor

- Do not operate git.
- Do not edit `v4_plan_1`.
- Do not run `10_prepare_data.py` unless the user explicitly asks; current prepared data should be used.
- If the full backtest is too slow, report where it stopped and which smaller verification commands passed, but do not substitute a small sample result for the full output unless the user approves.

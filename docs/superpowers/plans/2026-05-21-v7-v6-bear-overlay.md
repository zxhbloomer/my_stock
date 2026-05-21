# v7 v6 Bear Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild v7 as an independent full copy of v6, then enable the copied tmp bear-market exposure overlay only when v7's copied v6 market regime says `bear`.

**Architecture:** v7 keeps v6's normal strategy path unchanged for non-bear regimes. A new v7-local bear overlay table calculates `target_exposure` from historical market trend, drawdown, and breadth, using the tmp `hysteresis_fast_reentry` logic. During `market_regime == "bear"`, v7 uses the previous trading day's target exposure to clear risk-off holdings and size bear probe entries; v7 does not import v6 or read v6 outputs.

**Tech Stack:** Python 3.8-compatible scripts, pandas, existing BBI/backtrader script layout, unittest for lightweight contract checks.

---

### Task 1: Replace v7 Baseline With v6 Copy

**Files:**
- Modify: `scripts/bbi/backtrader/v7/10_prepare_data.py`
- Modify: `scripts/bbi/backtrader/v7/20_run_backtest.py`
- Modify: `scripts/bbi/backtrader/v7/30_generate_report.py`
- Modify: `scripts/bbi/backtrader/v7/config.py`
- Modify: `scripts/bbi/backtrader/v7/README.md`

- [ ] **Step 1: Copy v6 files into v7**

Run:

```powershell
Copy-Item -LiteralPath scripts\bbi\backtrader\v6\10_prepare_data.py -Destination scripts\bbi\backtrader\v7\10_prepare_data.py -Force
Copy-Item -LiteralPath scripts\bbi\backtrader\v6\20_run_backtest.py -Destination scripts\bbi\backtrader\v7\20_run_backtest.py -Force
Copy-Item -LiteralPath scripts\bbi\backtrader\v6\30_generate_report.py -Destination scripts\bbi\backtrader\v7\30_generate_report.py -Force
Copy-Item -LiteralPath scripts\bbi\backtrader\v6\config.py -Destination scripts\bbi\backtrader\v7\config.py -Force
```

Expected: v7 source files now match v6 strategy structure, with paths resolved from `Path(__file__).parent`, so output data is isolated under `v7/output`.

- [ ] **Step 2: Add v7 README describing isolation**

Write `scripts/bbi/backtrader/v7/README.md` with these facts:

```markdown
# v7 v6 Bear Overlay

v7 is an independent copy of v6 plus a v7-local bear-market exposure overlay.

- Non-bear regimes execute the copied v6 logic.
- Bear regimes use the copied tmp `hysteresis_fast_reentry` exposure rules.
- v7 does not import v6 and does not read v6 output files.
- Trading decisions use the previous completed trading day as `signal_date`.
```

### Task 2: Add v7-Local Bear Overlay Helpers

**Files:**
- Modify: `scripts/bbi/backtrader/v7/config.py`
- Modify: `scripts/bbi/backtrader/v7/20_run_backtest.py`

- [ ] **Step 1: Add constants to config**

Add:

```python
BEAR_OVERLAY_ENABLED = True
BEAR_OVERLAY_REENTRY_CONFIRM_DAYS = 2
BEAR_OVERLAY_FULL_CONFIRM_DAYS = 4
BEAR_OVERLAY_COOLDOWN_DAYS = 3
BEAR_OVERLAY_PROBE_MIN_EXPOSURE = 0.2
```

- [ ] **Step 2: Import constants in `20_run_backtest.py`**

Add the new constants to the existing `from config import (...)` block.

- [ ] **Step 3: Add helper functions copied/adapted from tmp**

Add v7-local functions:

```python
def safe_number(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default

def safe_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default

def compute_bear_overlay_risk_points(row):
    points = 0
    if safe_int(row.get("close_below_ma120"), 0) == 1:
        points += 1
    if safe_number(row.get("ma60_slope_20"), 0.0) < 0:
        points += 1
    dd = safe_number(row.get("market_drawdown_120"), 0.0)
    if dd <= -0.10:
        points += 1
    if dd <= -0.15:
        points += 1
    if safe_number(row.get("breadth_above_ma20"), 0.0) < 0.35:
        points += 1
    if safe_number(row.get("breadth_above_ma60"), 0.0) < 0.30:
        points += 1
    return points
```

Add `bear_overlay_base_target_exposure_from_row`, `apply_bear_overlay_hysteresis`, `build_bear_overlay_regime`, and `get_bear_overlay_snapshot` using tmp thresholds.

### Task 3: Integrate Bear Overlay Into v6 Trading Loop

**Files:**
- Modify: `scripts/bbi/backtrader/v7/20_run_backtest.py`

- [ ] **Step 1: Build overlay table after v6 market regime**

After:

```python
market_regime = build_market_regime(market, panel)
```

add:

```python
bear_overlay_regime = build_bear_overlay_regime(market, panel) if BEAR_OVERLAY_ENABLED else None
```

- [ ] **Step 2: Add stats**

Add counters:

```python
"bear_overlay_enabled": bool(BEAR_OVERLAY_ENABLED),
"bear_overlay_risk_off_days": 0,
"bear_overlay_risk_off_exit_signals": 0,
"bear_overlay_risk_off_exit_fills": 0,
"bear_overlay_probe_days": 0,
"bear_overlay_probe_buys": 0,
```

- [ ] **Step 3: Add risk-off exit in bear regime**

In the existing holdings exit block that uses `signal_date = all_dates[i - 1]`, read:

```python
bear_overlay_snapshot = get_bear_overlay_snapshot(bear_overlay_regime, signal_date)
bear_overlay_target = bear_overlay_snapshot.get("target_exposure", 1.0)
```

If `market_regime_name == "bear"` and `bear_overlay_target <= 0.0`, sell all holdings with reason `bear_overlay_risk_off_exit`.

- [ ] **Step 4: Replace bear buy behavior only when bear**

In the existing buy block:

```python
regime_blocked = MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
```

keep v6 behavior for `not regime_blocked`. For `regime_blocked`, use the overlay target:

```python
bear_overlay_probe_open = (
    BEAR_OVERLAY_ENABLED
    and regime_blocked
    and not short_drop_blocked
    and bear_overlay_target >= BEAR_OVERLAY_PROBE_MIN_EXPOSURE
)
```

When probe is open, allow only `bear_probe_stock_ok` candidates and size initial buys with:

```python
target_amount = min(
    calc_bear_probe_target_amount(...),
    INIT_CASH * bear_overlay_target,
)
```

When overlay target is `0.0`, no buys occur.

- [ ] **Step 5: Add diagnostics to rebalance log**

Include:

```python
"bear_overlay_target_exposure": round(bear_overlay_target, 4),
"bear_overlay_base_target_exposure": round(bear_overlay_snapshot.get("base_target_exposure", float("nan")), 4),
"bear_overlay_risk_points": bear_overlay_snapshot.get("risk_points", float("nan")),
```

### Task 4: Report and Documentation

**Files:**
- Modify: `scripts/bbi/backtrader/v7/README.md`
- Modify: `scripts/bbi/backtrader/v7/30_generate_report.py`

- [ ] **Step 1: Add README details**

Document exact bear overlay source, thresholds, and anti-lookahead rule.

- [ ] **Step 2: Keep v6 report compatible**

Do not rewrite report layout unless it crashes. Existing v6 report should read v7 output paths through v7 `config.py`.

### Task 5: Verification and QA Review

**Files:**
- Test: `scripts/bbi/backtrader/v7/test_v7_bear_overlay_contract.py`

- [ ] **Step 1: Add lightweight tests**

Test these pure functions:

```python
def test_bear_overlay_base_target_risk_off_on_large_drawdown()
def test_bear_overlay_base_target_probe_on_medium_drawdown()
def test_bear_overlay_hysteresis_requires_reentry_confirmation()
def test_bear_overlay_non_bear_default_snapshot_is_full_exposure()
```

- [ ] **Step 2: Run syntax and tests**

Run:

```powershell
python -X utf8 -m py_compile scripts\bbi\backtrader\v7\20_run_backtest.py scripts\bbi\backtrader\v7\30_generate_report.py scripts\bbi\backtrader\v7\10_prepare_data.py
python -X utf8 -m unittest scripts.bbi.backtrader.v7.test_v7_bear_overlay_contract -v
```

Expected: exit code 0.

- [ ] **Step 3: QA review checklist**

Confirm:

- v7 files do not import from `scripts.bbi.backtrader.v6`.
- v7 config outputs to `scripts/bbi/backtrader/v7/output`.
- Bear overlay uses `signal_date = all_dates[i - 1]`.
- No full backtest is required unless the user runs it.

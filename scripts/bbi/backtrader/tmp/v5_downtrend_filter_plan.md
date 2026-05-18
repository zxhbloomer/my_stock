# v5 Downtrend Buy Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a tmp v5-derived backtest that blocks new buys in quantified individual-stock downtrends.

**Architecture:** The tmp experiment imports v5 `20_run_backtest.py`, enriches a local panel copy with downtrend flags, wraps `score_candidates`, and compares each case against v4 and v5 summaries. Production v5 files remain unchanged.

**Tech Stack:** Python 3.8-compatible code, pandas, numpy, unittest, existing v5 parquet outputs.

---

### Task 1: Unit Tests

**Files:**
- Create: `scripts/bbi/backtrader/tmp/test_v5_downtrend_filter.py`
- Create later: `scripts/bbi/backtrader/tmp/v5_downtrend_filter_experiment.py`

- [ ] **Step 1: Write failing tests**

Test behaviors:

```python
def test_slope_pct_normalizes_by_window():
    series = pd.Series([100.0, 110.0, 121.0])
    result = exp.slope_pct(series, 2)
    assert round(float(result.iloc[2]), 6) == 0.105

def test_add_downtrend_features_flags_slope_and_structure_downtrend():
    # two 63-day blocks: first block higher range, second block lower range
    close = [120.0] * 63 + [100.0] * 63 + [80.0] * 80
    df = pd.DataFrame({
        "ts_code": ["000001.SZ"] * len(close),
        "trade_date": pd.date_range("2020-01-01", periods=len(close), freq="D"),
        "close_qfq": close,
    })
    enriched = exp.add_downtrend_features(df)
    last = enriched.iloc[-1]
    assert bool(last["slope_downtrend"])
    assert bool(last["structure_downtrend"])
    assert bool(last["strict_downtrend"])

def test_filter_downtrend_candidates_blocks_selected_flag():
    candidates = pd.DataFrame([
        {"ts_code": "keep", "slope_downtrend": False, "structure_downtrend": False},
        {"ts_code": "drop", "slope_downtrend": True, "structure_downtrend": False},
    ])
    filtered, diagnostics = exp.filter_downtrend_candidates(candidates, "slope_downtrend")
    assert filtered["ts_code"].tolist() == ["keep"]
    assert diagnostics["blocked_candidates"] == 1
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m unittest scripts\bbi\backtrader\tmp\test_v5_downtrend_filter.py -v
```

Expected: fail because `v5_downtrend_filter_experiment.py` does not exist or functions are missing.

### Task 2: Experiment Implementation

**Files:**
- Create: `scripts/bbi/backtrader/tmp/v5_downtrend_filter_experiment.py`

- [ ] **Step 1: Implement downtrend feature functions**

Functions:

- `slope_pct(series, window)`
- `rolling_mean_by_code(panel, column, window)`
- `rolling_max_by_code(panel, column, window)`
- `rolling_min_by_code(panel, column, window)`
- `add_downtrend_features(panel)`
- `filter_downtrend_candidates(candidates, flag_col)`

- [ ] **Step 2: Run unit tests to verify GREEN**

Run:

```powershell
python -m unittest scripts\bbi\backtrader\tmp\test_v5_downtrend_filter.py -v
```

Expected: all tests pass.

### Task 3: Backtest Harness

**Files:**
- Modify: `scripts/bbi/backtrader/tmp/v5_downtrend_filter_experiment.py`

- [ ] **Step 1: Add v5 import and case runner**

Implement:

- `load_v5_module()`
- `make_score_candidates(original_score_candidates, case, diagnostics)`
- `run_case(v5, panel, market, case)`
- `calc_nav_stats(nav_df)`
- `summarize_period(nav_df, trades_df, start, end)`
- `assert_baseline_matches_v5(results, v5_summary)`

- [ ] **Step 2: Add outputs**

Write:

- `scripts/bbi/backtrader/tmp/v5_downtrend_filter_output/results.csv`
- `scripts/bbi/backtrader/tmp/v5_downtrend_filter_output/summary.md`

### Task 4: Verification and Review

**Files:**
- Modify: `scripts/bbi/backtrader/tmp/v5_downtrend_filter_README.md`

- [ ] **Step 1: Compile**

Run:

```powershell
python -m py_compile scripts\bbi\backtrader\tmp\v5_downtrend_filter_experiment.py
```

- [ ] **Step 2: Run tests**

Run:

```powershell
python -m unittest scripts\bbi\backtrader\tmp\test_v5_downtrend_filter.py -v
```

- [ ] **Step 3: Run backtest**

Run:

```powershell
python -X utf8 scripts\bbi\backtrader\tmp\v5_downtrend_filter_experiment.py
```

- [ ] **Step 4: Review result**

Confirm:

- `baseline_v5` matches `scripts/bbi/backtrader/v5/output/summary.json`.
- results include v4/v5 baseline comparison.
- no case is recommended unless it beats v5 return with acceptable drawdown.

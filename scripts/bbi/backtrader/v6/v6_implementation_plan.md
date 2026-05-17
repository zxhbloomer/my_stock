# v6 Downtrend Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create isolated v6 from v5 and integrate the verified early weakness downtrend candidate filter.

**Architecture:** v6 is a physical copy of v5 with localized configuration, v6 branding, and an added feature/filter path. v6 reads source data from the database and writes only to `v6/output`; it does not consume v5 output.

**Tech Stack:** Python 3.8-compatible scripts, pandas, numpy, SQLAlchemy, unittest, existing BBI workflow.

---

### Task 1: TDD Guard Tests

**Files:**
- Create: `scripts/bbi/backtrader/v6/test_v6_downtrend_filter.py`

- [ ] Write tests that fail before implementation:
  - `add_strength_features` creates `early_weakness_downtrend`.
  - `score_candidates` removes early weakness rows.
  - v6 `OUTPUT_DIR` path is under v6, not v5.

- [ ] Run:

```powershell
python -m unittest discover scripts\bbi\backtrader\v6 -p "test_*.py" -v
```

Expected before implementation: failure because v6 modules are missing.

### Task 2: Copy v5 Into v6

**Files:**
- Create from v5: `config.py`
- Create from v5: `10_prepare_data.py`
- Create from v5: `20_run_backtest.py`
- Create from v5: `30_generate_report.py`
- Create from v5: `README.md`
- Create empty: `__init__.py`

- [ ] Copy only source files, not `v5/output`.
- [ ] Do not read or copy any v5 output files.

### Task 3: Implement v6 Filter

**Files:**
- Modify: `scripts/bbi/backtrader/v6/config.py`
- Modify: `scripts/bbi/backtrader/v6/10_prepare_data.py`
- Modify: `scripts/bbi/backtrader/v6/20_run_backtest.py`
- Modify: `scripts/bbi/backtrader/v6/30_generate_report.py`
- Modify: `scripts/bbi/backtrader/v6/README.md`

- [ ] Add config:

```python
DOWNTREND_BUY_FILTER_ENABLED = True
DOWNTREND_FILTER_NAME = "early_weakness_downtrend"
DOWNTREND_MA_WINDOW = 20
DOWNTREND_SLOPE_WINDOW = 10
DOWNTREND_RET_WINDOW = 21
```

- [ ] Add prepare features:

```python
panel["ma20_qfq"] = rolling_mean_by_code(panel, "close_qfq", DOWNTREND_MA_WINDOW)
panel["ma20_slope_10"] = grouped["ma20_qfq"].transform(
    lambda s: s.pct_change(DOWNTREND_SLOPE_WINDOW, fill_method=None) / DOWNTREND_SLOPE_WINDOW
)
panel["early_weakness_downtrend"] = (
    (panel["close_qfq"] < panel["ma20_qfq"])
    & (panel["ma20_slope_10"] < 0)
    & (panel["ret_21"] < 0)
)
```

- [ ] Extend runtime columns and filter candidates:

```python
if DOWNTREND_BUY_FILTER_ENABLED:
    blocked = candidates[DOWNTREND_FILTER_NAME].fillna(False).astype(bool)
    candidates = candidates[~blocked].copy()
```

- [ ] Track blocked count in stats and report.
- [ ] Replace visible v5 report labels with v6 labels.

### Task 4: Verification

- [ ] Run compile:

```powershell
python -m py_compile scripts\bbi\backtrader\v6\10_prepare_data.py scripts\bbi\backtrader\v6\20_run_backtest.py scripts\bbi\backtrader\v6\30_generate_report.py
```

- [ ] Run tests:

```powershell
python -m unittest discover scripts\bbi\backtrader\v6 -p "test_*.py" -v
```

- [ ] Run workflow:

```powershell
cd scripts\bbi\backtrader\v6
python -X utf8 10_prepare_data.py
python -X utf8 20_run_backtest.py
python -X utf8 30_generate_report.py
```

- [ ] Confirm output files exist only under `v6/output`.

### Task 5: Review

- [ ] Review for v5-output references.
- [ ] Review anti-lookahead behavior.
- [ ] Review report wording and metrics.

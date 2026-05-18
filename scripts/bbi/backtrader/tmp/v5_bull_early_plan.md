# v5 Bull Early Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Execute task-by-task in `tmp`. Do not modify v5 production code and do not operate git.

**Goal:** Test whether adding a `bull_early` market state improves strong-market returns while preserving v5 drawdown control.

**Architecture:** A standalone tmp script loads v5 backtest code and data, monkeypatches market regime construction and selected runtime rules per case, runs backtests, and writes comparison artifacts. v4/v5 production folders remain unchanged.

**Tech Stack:** Python, pandas, v5 backtest module, local parquet/csv output.

---

### Task 1: Script Skeleton And Baseline

**Files:**
- Create: `scripts/bbi/backtrader/tmp/v5_bull_early_experiment.py`

- [x] Create script with `main()`.
- [x] Implement loader for v5 `20_run_backtest.py`.
- [x] Implement baseline run.
- [x] Assert `baseline_v5` matches `v5/output/summary.json`.

### Task 2: Bull Early State

**Definition:**

```text
bull_early =
  close > ma120
  ma120_slope_20 > 0
  market_ret_63 > 0
  breadth_above_bbi >= 0.55
```

- [x] Build a market regime table from v5 logic plus `market_ret_63`.
- [x] Preserve v5 `bear`, `bull`, `neutral` definitions.
- [x] Add `bull_early` only when original v5 state is `neutral`.
- [x] Record backtest-window state counts.

### Task 3: Cases

Run:

- `baseline_v5`
- `bull_early_as_bull`
- `bull_early_v4_drawdown`
- `bull_early_exposure600`
- `bull_fast_no_slope_as_bull`
- `bull_recent20_as_bull`
- `bull_recent20_v4_drawdown`

For each case, summarize:

- full period
- every year from 2018 through 2026

### Task 4: Review And Reporting

- [x] Write `results.csv`.
- [x] Write `summary.md`.
- [x] Request QA review for future-function and monkeypatch restoration.
- [x] Update `v5_bull_early_README.md`.

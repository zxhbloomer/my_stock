# v5 Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or execute task-by-task inline. This plan is executed in `tmp`; do not modify v5 production code and do not operate git.

**Goal:** Test whether explicit uptrend filters and limited bull-market exposure expansion improve v5 returns without unacceptable drawdown.

**Architecture:** Create a standalone tmp experiment that loads v5 modules and output data, monkeypatches candidate scoring and risk limits per case, runs v5 `run_backtest`, and writes comparison artifacts. Keep v5 code unchanged.

**Tech Stack:** Python, pandas, v5 backtest module, local parquet/csv outputs.

---

### Task 1: Add Tmp Experiment Script

**Files:**
- Create: `scripts/bbi/backtrader/tmp/v5_trend_evolution_experiment.py`

- [ ] Write a small import smoke test by compiling the new script.
- [ ] Implement `load_v5_module()` from `scripts/bbi/backtrader/v5/20_run_backtest.py`.
- [ ] Implement `make_score_candidates()` wrapper that applies case filters after original `score_candidates`.
- [ ] Implement `run_case()` that temporarily overrides:
  - `score_candidates`
  - `LONG_MAX_HOLDINGS`
  - `LONG_MAX_TOTAL_EXPOSURE`
- [ ] Implement period summaries for `2018`, `2022`, `2025`, and `full`.
- [ ] Implement buy-time diagnostics:
  - number of buys with `ret_126 <= 0`
  - number of buys with `above_ratio_63 < 0.60`
- [ ] Write outputs:
  - `scripts/bbi/backtrader/tmp/v5_trend_evolution_output/results.csv`
  - `scripts/bbi/backtrader/tmp/v5_trend_evolution_output/summary.md`

### Task 2: Run And Verify

**Commands:**

```powershell
python -m py_compile scripts/bbi/backtrader/tmp/v5_trend_evolution_experiment.py
python -X utf8 scripts/bbi/backtrader/tmp/v5_trend_evolution_experiment.py
```

Expected:

- Script exits with code 0.
- `baseline_v5` matches v5 output summary.
- No tested case uses future data: filters only inspect `signal_panel`.

### Task 3: Review

**Files:**
- Review: `scripts/bbi/backtrader/tmp/v5_trend_evolution_experiment.py`
- Review: generated summary and results.

- [ ] Quant review: compare returns, drawdown, Calmar proxy, yearly segments.
- [ ] QA review: check future function risk and monkeypatch restoration.
- [ ] Update `v5_evolution_README.md` with final results and conclusion.

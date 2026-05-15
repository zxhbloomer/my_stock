# v4 Bull Hold Exit Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tmp-only experiment runner that compares 4 strong-trend hold/exit variants against the current v4 baseline.

**Architecture:** Reuse the existing tmp copy of the v4 backtest, add a `--mode` switch, derive the extra daily and weekly hold features from existing `v4/output/panel.parquet`, then run 2018-only comparisons and write per-mode outputs plus a combined comparison file.

**Tech Stack:** Python, pandas, existing v4 parquet outputs.

---

### Task 1: Add experiment records

**Files:**
- Create: `docs/superpowers/specs/2026-05-15-v4-bull-hold-exit-experiment-design.md`
- Create: `docs/superpowers/plans/2026-05-15-v4-bull-hold-exit-experiment.md`
- Modify: `scripts/bbi/backtrader/tmp/results.md`

- [ ] Write the experiment design and scope.
- [ ] Write the implementation plan.
- [ ] Append a short execution record after results are produced.

### Task 2: Implement tmp experiment runner

**Files:**
- Modify: `scripts/bbi/backtrader/tmp/v4_bull_hold_exit_experiment.py`

- [ ] Add CLI options for `--mode`, `--start`, and `--end`.
- [ ] Load the extra columns needed for hold-line logic: `close_qfq`, `bbi_qfq`.
- [ ] Derive daily `ma20_qfq`, `ma50_qfq`.
- [ ] Derive completed-week `ma10w_qfq`, `ma20w_qfq` from daily `close_qfq`.
- [ ] Add position state for highest close / highest profit / observe state.
- [ ] Implement `current`, `trend_line`, `profit_cushion`, `strict_observe`, and `weekly_hold`.
- [ ] Keep all decisions based on `T-1` signal data only.

### Task 3: Verify runner correctness

**Files:**
- Use: `scripts/bbi/backtrader/tmp/v4_bull_hold_exit_experiment.py`

- [ ] Run syntax check with `py_compile`.
- [ ] Run `current` mode on 2018 and ensure it completes.
- [ ] Run the other 4 modes on 2018 and ensure outputs are written separately.
- [ ] Build a combined comparison table from the generated `summary.json`.

### Task 4: QA review and summary

**Files:**
- Modify: `scripts/bbi/backtrader/tmp/results.md`

- [ ] Review for future-function risk in daily and weekly signal usage.
- [ ] Review for state-machine bugs in `strict_observe`.
- [ ] Record the 2018 comparison result and note whether any mode is clearly better than `current`.

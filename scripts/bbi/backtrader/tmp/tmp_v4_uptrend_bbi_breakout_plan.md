# tmp_v4 Uptrend BBI Breakout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a temporary BBI breakout plus uptrend experiment that compares against v4, v5, and v6.

**Architecture:** Reuse the existing v6 engine. Add feature calculation and candidate filtering in a tmp experiment script, then generate report tables from baseline and experiment outputs.

**Tech Stack:** Python 3.8-compatible code, pandas, existing v6 backtest module, unittest.

---

### Task 1: Tests

**Files:**
- Create: `scripts/bbi/backtrader/tmp/test_tmp_v4_uptrend_bbi_breakout.py`

- [x] **Step 1: Write tests first**

Tests cover BBI breakout calculation, anti-lookahead behavior, variant filtering, and baseline loading.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest scripts.bbi.backtrader.tmp.test_tmp_v4_uptrend_bbi_breakout -v`

Expected before implementation: import/file failure.

### Task 2: Experiment Script

**Files:**
- Create: `scripts/bbi/backtrader/tmp/tmp_v4_uptrend_bbi_breakout_experiment.py`

- [ ] **Step 1: Implement feature functions**

Add rolling MA, rolling high, short BBI breakout, mid BBI, slopes, RPS, market return merge.

- [ ] **Step 2: Implement variant filters**

Apply the four variants without mutating v6 strategy code.

- [ ] **Step 3: Implement run loop and report**

Monkey-patch v6 `score_candidates`, run each variant, save CSV/JSON/HTML output.

### Task 3: Verification

**Files:**
- Modify: `scripts/bbi/backtrader/tmp/tmp_v4_uptrend_bbi_breakout_README.md`

- [ ] **Step 1: Run unit tests**

Run: `python -m unittest scripts.bbi.backtrader.tmp.test_tmp_v4_uptrend_bbi_breakout -v`

- [ ] **Step 2: Run experiment**

Run: `python -X utf8 scripts/bbi/backtrader/tmp/tmp_v4_uptrend_bbi_breakout_experiment.py`

- [ ] **Step 3: Open report**

Open `tmp_v4_uptrend_bbi_breakout_output/report.html`.

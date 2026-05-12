# v4_plan Market BBI Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an anti-lookahead 上证指数 BBI market filter to `scripts/bbi/backtrader/v4_plan`.

**Architecture:** `10_prepare_data.py` exports market index data to output. `20_run_backtest.py` consumes that prepared file and blocks new buys when the previous completed trading day's index close is not above BBI. `30_generate_report.py` surfaces the rule and skip counts.

**Tech Stack:** Python 3.8, pandas, SQLAlchemy, local PostgreSQL/Tushare tables, static HTML report.

---

### Task 1: Configuration And Prepared Data

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/config.py`
- Modify: `scripts/bbi/backtrader/v4_plan/10_prepare_data.py`

- [ ] Add market filter constants to `config.py`: enabled flag, index code/name, output parquet path.
- [ ] Query `tushare_v2."137_idx_factor_pro"` in `10_prepare_data.py` for `trade_date`, `close`, `bbi_bfq` where `ts_code = "000001.SH"`.
- [ ] Save the result to `output/market_index.parquet`.
- [ ] Add index factor max date and market filter metadata to `data_quality.json`.

### Task 2: Backtest Buy Gate

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

- [ ] Load `output/market_index.parquet` once at startup.
- [ ] Add a helper that returns allow/block/missing for `signal_date`.
- [ ] Before building candidates on a buy day, check `signal_date` index state.
- [ ] If `close <= bbi_bfq` or data is missing, skip candidate building and do not buy that day.
- [ ] Count blocked and missing market signal days in `run_stats.json`.

### Task 3: Report And Documentation

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/30_generate_report.py`
- Modify: `scripts/bbi/backtrader/v4_plan/README.md`

- [ ] Show the market filter rule in the report header.
- [ ] Show skipped buy days and missing index signal days.
- [ ] Document the new data source and anti-lookahead timing in README.

### Task 4: Verification

**Files:**
- Verify generated output under `scripts/bbi/backtrader/v4_plan/output/`

- [ ] Run Python compile checks for the four v4_plan scripts.
- [ ] Run a small date-window pipeline to verify prepared data, backtest, and report generation.
- [ ] Inspect `run_stats.json` and `data_quality.json` for market filter fields.

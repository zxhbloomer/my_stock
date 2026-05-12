# Tushare 龙虎榜接口同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `top_list` and `top_inst` synchronization without inventing a business primary key.

**Architecture:** Reuse the existing `data/手动执行/20260425` script pattern, `sync_status`, trade calendar iteration, and table checks. Add a shared `replace_date_df` helper so these detail tables use database auto-increment IDs and replace one trading day at a time.

**Tech Stack:** Python 3.8-compatible scripts, pandas, SQLAlchemy, PostgreSQL, Tushare Pro API.

---

### Task 1: Add tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_tushare_top_sync_scripts.py`

- [x] Write tests that assert both new scripts use `id BIGSERIAL PRIMARY KEY`, call `replace_date_df`, and do not use `PRIMARY KEY (trade_date, ts_code)`.
- [x] Run tests and confirm they fail before implementation because `088_top_list.py` does not exist.

### Task 2: Add shared date replacement helper

**Files:**
- Modify: `data/手动执行/20260425/_common.py`

- [x] Add `replace_date_df(engine, df, table, cols, trade_date)`.
- [x] Delete rows for the target `trade_date` and insert the fetched full-day DataFrame in the same transaction.

### Task 3: Add sync scripts

**Files:**
- Create: `data/手动执行/20260425/088_top_list.py`
- Create: `data/手动执行/20260425/089_top_inst.py`

- [x] Define fields from local Tushare HTML docs.
- [x] Use `id BIGSERIAL PRIMARY KEY`.
- [x] Convert date and numeric columns.
- [x] Drop rows missing `trade_date` or `ts_code`.
- [x] Replace each trading date through `replace_date_df`.

### Task 4: Register scripts

**Files:**
- Modify: `data/手动执行/20260425/run_all.py`
- Modify: `data/手动执行/20260425/run_all-041~139.py`
- Modify: `data/手动执行/20260425/_check_status.py`
- Modify: `data/手动执行/20260425/_check_status2.py`
- Modify: `data/手动执行/20260425/_check_status3.py`
- Modify: `data/手动执行/20260425/_check_dates.py`
- Modify: `data/手动执行/20260425/_check_dates2.py`
- Modify: `data/手动执行/20260425/new_readme.md`

- [x] Add both scripts after `087_moneyflow_hsgt.py`.
- [x] Add both tables to status and date check maps.
- [x] Document the sync strategy as per-day replacement.

### Task 5: Verify

**Files:**
- All changed files.

- [ ] Run static tests.
- [ ] Compile changed Python files.
- [ ] Run a one-day dry script execution if database and Tushare credentials are available.

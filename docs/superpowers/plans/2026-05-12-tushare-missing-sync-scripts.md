# Missing Tushare Sync Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add backend-only incremental sync scripts for missing Tushare interfaces 021, 022, 082-086, 091, and 092.

**Architecture:** Follow the existing `data/手动执行/20260425` one-script-per-interface pattern. Each script owns table DDL, field conversions, incremental loop, and `sync_status` updates while reusing `_common.py`.

**Tech Stack:** Python 3.8-compatible scripts, pandas, SQLAlchemy helpers from `_common.py`, PostgreSQL schema `tushare_v2`, local Tushare mirror docs.

---

### Task 1: Static Verification Gate

**Files:**
- Create: `data/手动执行/20260425/_test_new_sync_scripts_static.py`

- [ ] Write a static verification script that checks all expected files, table constants, field constants, primary keys, API calls, runner entries, status-check entries, and readme entries.
- [ ] Run it before implementation and confirm it fails because the new scripts are missing.

### Task 2: Add 021 and 022 Weekly/Monthly Scripts

**Files:**
- Create: `data/手动执行/20260425/021_stk_weekly_monthly.py`
- Create: `data/手动执行/20260425/022_stk_week_month_adj.py`

- [ ] Implement both scripts with `freq in ["week", "month"]`, table creation, type conversion, upsert, and incremental status updates.
- [ ] Compile both scripts.

### Task 3: Add 082-086 Moneyflow Scripts

**Files:**
- Create: `data/手动执行/20260425/082_moneyflow_dc.py`
- Create: `data/手动执行/20260425/083_moneyflow_cnt_ths.py`
- Create: `data/手动执行/20260425/084_moneyflow_ind_ths.py`
- Create: `data/手动执行/20260425/085_moneyflow_ind_dc.py`
- Create: `data/手动执行/20260425/086_moneyflow_mkt_dc.py`

- [ ] Implement per-date incremental scripts for each interface.
- [ ] Loop `085` over `content_type in ["行业", "概念", "地域"]`.
- [ ] Compile the scripts.

### Task 4: Add 091 and 092 Limit Scripts

**Files:**
- Create: `data/手动执行/20260425/091_limit_list_d.py`
- Create: `data/手动执行/20260425/092_limit_step.py`

- [ ] Implement `091` with `limit_type in ["U", "D", "Z"]`.
- [ ] Implement `092` as a per-date incremental upsert.
- [ ] Compile both scripts.

### Task 5: Integrate Runners, Checks, and Docs

**Files:**
- Modify: `data/手动执行/20260425/run_all.py`
- Modify: `data/手动执行/20260425/run_all-001~040.py`
- Modify: `data/手动执行/20260425/run_all-041~139.py`
- Modify: `data/手动执行/20260425/_check_status.py`
- Modify: `data/手动执行/20260425/_check_status2.py`
- Modify: `data/手动执行/20260425/_check_status3.py`
- Modify: `data/手动执行/20260425/_check_dates.py`
- Modify: `data/手动执行/20260425/_check_dates2.py`
- Modify: `data/手动执行/20260425/new_readme.md`

- [ ] Add all new scripts to the appropriate runner order.
- [ ] Add all new tables to status/date checks.
- [ ] Update `new_readme.md` completed-interface list and file tree.
- [ ] Run static verification until it passes.

### Task 6: Runtime Verification and Review

- [ ] Run `python -m py_compile` over all new and modified Python files.
- [ ] Run narrow date-range smoke tests where permissions allow.
- [ ] Query table existence and `sync_status` for new interfaces if smoke tests run.
- [ ] Perform code review focused on field fidelity, primary keys, incremental behavior, empty-date handling, and no frontend impact.


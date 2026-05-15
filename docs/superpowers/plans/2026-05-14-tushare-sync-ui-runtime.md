# Tushare Sync UI Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show total script count in the UI title and persist/display per-script runtime using start/end timestamps.

**Architecture:** Extend `sync_status` with `last_start_at` and `last_end_at`, update these timestamps around UI-launched subprocess execution, return them through `/api/jobs`, and format durations in the vanilla JavaScript table.

**Tech Stack:** Python 3.8, FastAPI, SQLAlchemy text SQL, vanilla HTML/CSS/JavaScript, `unittest`.

---

### Task 1: Backend Runtime Persistence

**Files:**
- Modify: `data/ui/test_sync_service.py`
- Modify: `data/ui/sync_service.py`

- [ ] **Step 1: Write failing tests**

Add tests for:
- `_format_status_row` includes `last_start_at` and `last_end_at`.
- `record_script_runtime_start` updates existing rows without inserting new rows.
- `record_script_runtime_finish` writes end time and preserves sync date/status.

- [ ] **Step 2: Run focused tests**

Run: `python -m unittest data.ui.test_sync_service.SyncServiceDateEditTest data.ui.test_sync_service.SyncServiceExecutionTest -v`

Expected: fail because runtime helpers and fields are not implemented.

- [ ] **Step 3: Implement schema migration and runtime helpers**

Add:
- `ensure_sync_status_table`
- `record_script_runtime_start`
- `record_script_runtime_finish`

Update `load_sync_status_map` query and `_format_status_row`.

- [ ] **Step 4: Wire helpers around `_run_script`**

Call start before subprocess launch and finish in `_run_script` `finally`, using the same captured start timestamp.

- [ ] **Step 5: Run backend tests**

Run: `python -m unittest data.ui.test_sync_service -v`

Expected: all tests pass.

### Task 2: Frontend Title and Runtime Display

**Files:**
- Modify: `data/ui/static/index.html`

- [ ] **Step 1: Split topbar into title row and toolbar row**

Render `数据同步窗口（X）` in the first row and move target date/buttons to the second row.

- [ ] **Step 2: Add runtime formatting helpers**

Add JS helpers to compute runtime from:
- active task script status when running
- `last_start_at` and `last_end_at` from job row

Format:
- `< 60`: `xx秒`
- `< 3600`: `99.99分钟`
- `>= 3600`: `99.99小时`

- [ ] **Step 3: Update table rendering**

Use the new runtime display for the existing “运行时间” column and update the title count after each `/api/jobs` load.

- [ ] **Step 4: Static checks**

Run: `Select-String -Path data\ui\static\index.html -Pattern 'jobCount','formatDuration','last_start_at','last_end_at','数据同步窗口（'`

Expected: all patterns found.

### Task 3: Final Verification and Review

**Files:**
- Inspect: `data/ui/sync_service.py`
- Inspect: `data/ui/run_sync_ui.py`
- Inspect: `data/ui/static/index.html`
- Inspect: `data/ui/test_sync_service.py`

- [ ] **Step 1: Run full tests**

Run: `python -m unittest data.ui.test_sync_service -v`

Expected: all tests pass.

- [ ] **Step 2: Compile Python files**

Run: `python -m py_compile data\ui\sync_service.py data\ui\run_sync_ui.py data\ui\test_sync_service.py`

Expected: exit code 0.

- [ ] **Step 3: Static UI checks**

Run: `Select-String -Path data\ui\static\index.html -Pattern 'jobCount','formatDuration','last_start_at','last_end_at','数据同步窗口（'`

Expected: all patterns found.

- [ ] **Step 4: Code review**

Review:
- runtime migration is additive only
- runtime start does not insert a new row that could alter sync start
- runtime finish can fill start/end after the script creates a row
- frontend title count is derived from loaded jobs
- runtime formatting matches requested thresholds

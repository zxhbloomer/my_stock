# Tushare Sync UI Concurrent Stop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow different Tushare sync scripts to run concurrently while locking duplicate script execution and providing row-level force stop.

**Architecture:** Replace the single global task lock with in-memory task records and script-level locks in `SyncService`. Add task-list and stop-script APIs, then update the vanilla JavaScript UI to enable actions by script lock state instead of one global running flag.

**Tech Stack:** Python 3.8, FastAPI, Pydantic, vanilla HTML/CSS/JavaScript, `unittest`.

---

### Task 1: Backend Script-Level Task Model

**Files:**
- Modify: `data/ui/test_sync_service.py`
- Modify: `data/ui/sync_service.py`

- [ ] **Step 1: Write failing backend tests**

Add tests proving different scripts can start together, duplicate scripts are rejected, completed tasks release locks, pending scripts can be stopped, and running scripts call `terminate()`.

- [ ] **Step 2: Run focused tests**

Run: `python -m unittest data.ui.test_sync_service.SyncServiceTaskStateTest data.ui.test_sync_service.SyncServiceExecutionTest -v`

Expected: new tests fail because task-list and stop-script behavior does not exist yet.

- [ ] **Step 3: Implement task records and script locks**

Extend `TaskState` with task id, script list, script statuses, per-script timestamps, stop flag, and process handle. Add `_tasks`, `_script_locks`, `_task_seq`, and a thread-local task id to `SyncService`.

- [ ] **Step 4: Update workers**

Make single, selected, and full sync workers operate against task ids. Keep selected and full sync sequential internally, but allow other non-overlapping scripts to run in separate tasks.

- [ ] **Step 5: Run backend tests**

Run: `python -m unittest data.ui.test_sync_service -v`

Expected: all tests pass.

### Task 2: Stop Script API

**Files:**
- Modify: `data/ui/run_sync_ui.py`
- Modify: `data/ui/sync_service.py`

- [ ] **Step 1: Add API model and routes**

Add `/api/tasks` and `/api/stop-script`. `/api/tasks` returns task records plus active script locks. `/api/stop-script` accepts `script_name`.

- [ ] **Step 2: Compile check**

Run: `python -m py_compile data\ui\sync_service.py data\ui\run_sync_ui.py`

Expected: exit code 0.

### Task 3: Frontend Script-Level Locking

**Files:**
- Modify: `data/ui/static/index.html`

- [ ] **Step 1: Add task polling state**

Add `tasks`, `activeScripts`, and helpers to map backend statuses to Chinese feedback text.

- [ ] **Step 2: Update button disabling**

Disable only buttons for scripts currently locked. Keep unblocked row actions clickable while other scripts run.

- [ ] **Step 3: Add row stop button**

Render a small stop button in the execution feedback column when the script status is `pending` or `running`. It calls `/api/stop-script`.

- [ ] **Step 4: Poll tasks**

Poll `/api/tasks` along with `/api/task`, and use backend task state as the source of truth for row feedback.

- [ ] **Step 5: Static checks**

Run: `Select-String -Path data\ui\static\index.html -Pattern '/api/tasks','/api/stop-script','停止','activeScripts','isScriptLocked'`

Expected: all patterns are found.

### Task 4: Verification and Code Review

**Files:**
- Inspect: `data/ui/sync_service.py`
- Inspect: `data/ui/run_sync_ui.py`
- Inspect: `data/ui/static/index.html`

- [ ] **Step 1: Run full tests**

Run: `python -m unittest data.ui.test_sync_service -v`

Expected: all tests pass.

- [ ] **Step 2: Compile Python files**

Run: `python -m py_compile data\ui\sync_service.py data\ui\run_sync_ui.py data\ui\test_sync_service.py`

Expected: exit code 0.

- [ ] **Step 3: Review behavior**

Check that unknown scripts are still rejected, duplicate script execution is locked, non-overlapping scripts can run concurrently, force stop is best-effort, and frontend no longer globally disables every row action during a selected run.

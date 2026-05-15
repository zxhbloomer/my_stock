# Tushare Sync UI Layout Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the sync UI full-screen with a fixed top table, bottom logs, selectable script batch execution, row-level execution feedback, and automatic browser opening.

**Architecture:** Extend the existing FastAPI service with a selected-sync endpoint and service method. Keep UI state in the existing vanilla JavaScript page, with selected rows and per-run feedback stored in browser memory only.

**Tech Stack:** Python 3.8, FastAPI, Pydantic, vanilla HTML/CSS/JavaScript, `unittest`.

---

### Task 1: Backend Selected Sync

**Files:**
- Modify: `data/ui/test_sync_service.py`
- Modify: `data/ui/sync_service.py`
- Modify: `data/ui/run_sync_ui.py`

- [ ] **Step 1: Write failing tests**

Add tests to `SyncServiceExecutionTest`:

```python
def test_selected_sync_worker_runs_selected_scripts_in_whitelist_order(self):
    class SelectedScriptService(SyncService):
        def __init__(self):
            super().__init__()
            self.calls = []

        def load_script_names(self):
            return ["001_first.py", "002_second.py", "003_third.py"]

        def _run_script(self, script_name):
            self.calls.append(script_name)
            return 0

    service = SelectedScriptService()
    service._start_task("selected_sync")

    service._run_selected_sync_worker(["003_third.py", "001_first.py"])
    state = service.get_task_state()

    self.assertEqual(service.calls, ["001_first.py", "003_third.py"])
    self.assertEqual(state["status"], "completed")
    self.assertEqual(state["return_code"], 0)
    self.assertEqual(state["current_script"], "003_third.py")

def test_selected_sync_worker_stops_after_first_failure(self):
    class FailingSelectedService(SyncService):
        def __init__(self):
            super().__init__()
            self.calls = []

        def load_script_names(self):
            return ["001_first.py", "002_fail.py", "003_skip.py"]

        def _run_script(self, script_name):
            self.calls.append(script_name)
            return 7 if script_name == "002_fail.py" else 0

    service = FailingSelectedService()
    service._start_task("selected_sync")

    service._run_selected_sync_worker(["001_first.py", "002_fail.py", "003_skip.py"])
    state = service.get_task_state()

    self.assertEqual(service.calls, ["001_first.py", "002_fail.py"])
    self.assertEqual(state["status"], "failed")
    self.assertEqual(state["return_code"], 7)
    self.assertEqual(state["current_script"], "002_fail.py")

def test_selected_sync_rejects_unknown_script_before_starting_task(self):
    class SelectedScriptService(SyncService):
        def load_script_names(self):
            return ["001_first.py"]

    service = SelectedScriptService()

    with self.assertRaises(UnknownScriptError):
        service.run_selected_sync_background(["001_first.py", "evil.py"])

    self.assertEqual(service.get_task_state()["status"], "idle")
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m unittest data.ui.test_sync_service.SyncServiceExecutionTest -v`

Expected: failures or errors because `run_selected_sync_background` and `_run_selected_sync_worker` do not exist.

- [ ] **Step 3: Implement selected sync service and route**

Add `run_selected_sync_background(script_names)` and `_run_selected_sync_worker(script_names)` to `SyncService`. Validate all selected scripts before starting the task. Order selected scripts by `load_script_names()`.

Add this request model and route to `run_sync_ui.py`:

```python
class SelectedScriptsRequest(BaseModel):
    script_names: list


@app.post("/api/sync-selected")
def api_sync_selected(payload: SelectedScriptsRequest):
    try:
        service.run_selected_sync_background(payload.script_names)
        return {"ok": True}
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)
```

- [ ] **Step 4: Run backend tests**

Run: `python -m unittest data.ui.test_sync_service -v`

Expected: all tests pass.

### Task 2: Frontend Layout, Selection, Feedback

**Files:**
- Modify: `data/ui/static/index.html`

- [ ] **Step 1: Update CSS layout**

Set `html, body` height to `100%`, hide body overflow, make `.app` a `100vh` grid, and make the content area two equal rows. Make `th` sticky within `.table-wrap`.

- [ ] **Step 2: Add selection and feedback state**

Extend JavaScript state with:

```javascript
selectedScripts: new Set(),
feedback: {},
selectedRunActive: false
```

Add helpers for timestamp, selected count, feedback updates, and selected script list.

- [ ] **Step 3: Add checkbox column, feedback column, and selected button**

Add a top button `选择脚本执行（0）`. Add table columns for checkbox and execution feedback. Render selected rows with a `selected` class. Update button text and class based on selected count.

- [ ] **Step 4: Implement selected run polling feedback**

When selected execution starts, clear feedback and set selected scripts to `待执行`. During `/api/task` polling for kind `selected_sync`, mark `current_script` as `执行中`. When task finishes, mark scripts before the failed script as `执行完毕`, the failed script as `有错误`, and otherwise all selected scripts as `执行完毕`.

- [ ] **Step 5: Run static checks**

Run: `Select-String -Path data\ui\static\index.html -Pattern '选择脚本执行','执行反馈','position: sticky','/api/sync-selected'`

Expected: all patterns are found.

### Task 3: Auto Open Browser

**Files:**
- Modify: `data/ui/run_sync_ui.py`

- [ ] **Step 1: Add auto-open helper**

Use `threading.Timer` and `webbrowser.open` inside `main()` so direct execution opens `http://127.0.0.1:8008` shortly after uvicorn starts.

- [ ] **Step 2: Compile check**

Run: `python -m py_compile data\ui\sync_service.py data\ui\run_sync_ui.py data\ui\test_sync_service.py`

Expected: exit code 0.

### Task 4: Final Verification and Review

**Files:**
- Inspect: `data/ui/sync_service.py`
- Inspect: `data/ui/run_sync_ui.py`
- Inspect: `data/ui/static/index.html`

- [ ] **Step 1: Run full unit tests**

Run: `python -m unittest data.ui.test_sync_service -v`

Expected: all tests pass.

- [ ] **Step 2: Compile Python files**

Run: `python -m py_compile data\ui\sync_service.py data\ui\run_sync_ui.py data\ui\test_sync_service.py`

Expected: exit code 0.

- [ ] **Step 3: Perform code review**

Review for:
- unknown script validation before task starts
- no real sync script execution in tests
- no page-level scrollbar
- sticky table header
- selected row highlight and count sync
- selected execution disabled while task runs
- browser auto-open only in direct script execution

- [ ] **Step 4: Report outcome**

Summarize changed files and verification output. Do not mention commits because git operations are out of scope.

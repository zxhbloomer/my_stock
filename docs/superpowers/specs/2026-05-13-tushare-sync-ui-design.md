# Tushare Sync UI Design

## Goal

Build a local web page under `data/ui` that shows all Tushare data sync jobs needed by the current `data/手动执行/20260425` workflow, reads existing sync status from PostgreSQL, and lets the operator run single-job syncs, full syncs, and today-sync checks from one page.

## Scope

In scope:

- Add a local FastAPI web module under `data/ui`.
- Start it with `python -X utf8 data/ui/run_sync_ui.py`.
- Show one compact operations table similar to the provided screenshot.
- Use `data/手动执行/20260425/run_all.py` as the sync job whitelist and execution order.
- Read `tushare_v2.sync_status` and merge those rows into the displayed job list.
- Edit a row's `sync_date` and persist it to `tushare_v2.sync_status`.
- Run a single sync script for one row.
- Run all whitelisted sync scripts in `run_all.py` order.
- Run a full today-sync check.
- Run a single-row today-sync check with structured results.
- Show current task status and live task logs.
- Prevent concurrent sync/check tasks inside the running UI process.

Out of scope for version 1:

- Git operations.
- Authentication, multi-user access, or remote deployment.
- Persistent job queue across server restarts.
- Changing the existing Tushare sync script behavior.
- Adding historical runtime columns to `tushare_v2.sync_status`.
- Editing arbitrary database fields other than the whitelisted row's `sync_date`.
- Showing scripts that are present in the directory but intentionally not listed in `run_all.py`.

## Assumptions

- The intended source directory is `data/手动执行/20260425`; `data/手动执行/20260425代码` does not exist in the current workspace.
- `run_all.py` is the authority for "all required sync data" because it already excludes unsupported or intentionally skipped scripts.
- Existing environment variables in `.env` remain the source of database and Tushare configuration.
- The UI runs locally for one operator.
- Python 3.8 compatibility is required.
- `fastapi` and `uvicorn` may be added to project dependencies.

## Architecture

The feature has three small layers:

- `data/ui/run_sync_ui.py`: command-line entry point that starts uvicorn.
- `data/ui/sync_service.py`: backend service code for reading job definitions, reading `sync_status`, running subprocess tasks, collecting logs, and exposing structured task state.
- `data/ui/static/index.html`: single-page HTML/CSS/JS UI that calls backend JSON APIs and renders the operations table and log panel.

The backend is intentionally local and process-based. It does not import and call each sync script's `main()` function. Instead, it executes scripts with the same process boundary operators already use:

```powershell
python -X utf8 <script>.py
```

This keeps each sync script's current `sys.path`, argparse, stdout, and failure behavior intact.

## Data Sources

### Job List

The UI reads `SCRIPTS` from:

```text
data/手动执行/20260425/run_all.py
```

Only entries in that list are executable from the UI. This avoids accidentally exposing helper scripts such as `_check_status.py` or unsupported sync scripts such as scripts commented out of `run_all.py`.

For each script, table name is derived from the file stem:

```text
014_daily.py -> 014_daily
```

This matches the current scripts' `TABLE` constants.

### Sync Status

The UI reads:

```sql
SELECT script_name, table_name, sync_date, status, updated_at
FROM tushare_v2.sync_status
```

Displayed rows always come from the `run_all.py` whitelist. If a whitelisted script has no `sync_status` row, the UI displays it with a status like `not_synced`.

The UI allows editing `sync_date` for a whitelisted row. Saving the edit upserts the row in `tushare_v2.sync_status` with:

- `script_name`: the whitelisted script name, such as `014_daily.py`.
- `table_name`: the table name derived from the script stem, such as `014_daily`.
- `sync_date`: the operator-entered date.
- `status`: `ing`.
- `updated_at`: current database timestamp.

The save behavior intentionally uses `status='ing'` because the existing sync scripts treat `ing` as "resume from this exact date". This makes the edit useful for forcing a rerun from the selected date. The UI must show a short confirmation prompt before saving because this changes the next sync start point.

### Today Check

The UI reuses the existing structured logic in:

```text
data/手动执行/20260425/run_check_today_sync.py
```

It imports and calls the existing `TABLE_SPECS` and `collect_results()` logic, rather than parsing printed stdout. A full check returns all results. A row check returns the result matching that row's script/table. If the existing module cannot be imported because of path setup, the backend must add `data/手动执行/20260425` to `sys.path` before importing it.

Some scripts in `run_all.py` are not currently present in `run_check_today_sync.py.TABLE_SPECS`. For those rows, the first version must display the row but mark the check action as `未配置`; clicking it returns a structured `not_configured` result instead of failing. Full checks return configured table checks plus a separate list of whitelisted scripts that have no check spec.

## UI Design

The first version uses the compact status-table layout.

Top toolbar:

- `全部同步`: starts the full `run_all.py` sequence.
- `校验今日同步`: checks all configured table specs for the selected date.
- `刷新`: reloads job status and task state.
- Date input: defaults to today's date in `YYYYMMDD`.
- Current task indicator: idle/running/failed/completed plus current script if any.

Main table columns:

- 脚本名称
- 表名
- 同步日期
- 状态
- 更新时间
- 运行时间
- 操作

Operation column:

- `同步`: runs only this script.
- `编辑日期`: opens inline edit for `sync_date` and saves to `sync_status`.
- `校验`: runs structured check for this row when a check spec exists.
- `未配置`: replaces the check button when the row has no `TABLE_SPECS` entry.

Log area:

- Shows current task stdout/stderr.
- Auto-refreshes while a task is running.
- Keeps the most recent log lines in memory.
- Displays structured check output in the log area after a check task completes.

## Task Execution

The backend maintains one in-memory task state:

- `idle`
- `running`
- `completed`
- `failed`

Only one task can run at a time. If a task is running, new sync/check requests return HTTP 409 with a clear message.

Single sync:

```powershell
python -X utf8 <script>.py
```

Full sync:

- Iterates over the `run_all.py` whitelist in order.
- Runs each script with the same single-script command.
- Stops on the first non-zero exit code.
- Records the failed script in task state and logs.

Check:

- Uses database reads and existing `run_check_today_sync.py` logic.
- Does not auto-run repair commands.
- Returns suggested rerun commands for failed/missing tables.
- Returns `not_configured` for whitelisted scripts that do not have a `TABLE_SPECS` entry.

Sync date edit:

- Validates the date format as `YYYYMMDD`.
- Rejects unknown scripts that are not in the `run_all.py` whitelist.
- Upserts only the target script's `sync_status` row.
- Sets `status='ing'` so the next single sync or full sync resumes from the selected date.
- Refreshes the table after a successful save.

## Runtime Display

The existing `sync_status` table does not store duration. Version 1 displays:

- Current running task duration when a task is active.
- Blank or `-` for rows that are not currently running.

Historical per-script runtime is not included in version 1 because it would require a new local history store or a schema change.

## Error Handling

Database unavailable:

- The page still renders the whitelisted script list.
- Status fields show unknown/error.
- The toolbar or status banner shows the database error.

Script failure:

- The task moves to `failed`.
- Logs keep stdout/stderr from the failed script.
- Buttons become usable again after the task exits.
- Full sync stops at the failed script.

Unknown script request:

- The backend rejects it because it is not in the `run_all.py` whitelist.

Invalid sync date edit:

- The backend rejects dates that are not valid `YYYYMMDD` calendar dates.
- The UI keeps the old displayed value and shows the validation error.

Server restart:

- In-memory task state and logs reset.
- The UI can still rebuild the table from `run_all.py` and `sync_status`.
- Running subprocess recovery is not supported in version 1.

## Dependencies

Add runtime dependencies:

```text
fastapi
uvicorn
```

No frontend build system is required.

## Verification

Minimum verification for version 1:

- Start server with `python -X utf8 data/ui/run_sync_ui.py`.
- Open the local URL and confirm all `run_all.py` scripts appear.
- Confirm rows merge `sync_status` values when the database is reachable.
- Confirm rows still appear with a database error banner when the database read fails.
- Run one low-risk single script and confirm logs appear.
- Trigger full sync while another task is running and confirm the second request is rejected.
- Run today check and confirm structured results appear.
- Confirm a row without a check spec displays `未配置` and returns `not_configured`.
- Edit one row's sync date with a valid `YYYYMMDD` value and confirm the saved `sync_status` row has `status='ing'`.
- Try an invalid sync date and confirm the UI shows a validation error without changing the row.
- Confirm no Git command is needed or used.

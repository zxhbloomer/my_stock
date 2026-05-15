# Tushare Sync UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI web page under `data/ui` for viewing and operating the `data/手动执行/20260425` Tushare sync workflow.

**Architecture:** Implement a small Python service layer that reads the existing `run_all.py` whitelist, merges PostgreSQL `sync_status`, runs whitelisted scripts in subprocesses, and reuses `run_check_today_sync.py` for structured checks. Expose that service through a FastAPI app and a single static HTML page with table operations and a log panel.

**Tech Stack:** Python 3.8, FastAPI, uvicorn, SQLAlchemy already used by `_common.py`, vanilla HTML/CSS/JS, standard-library `unittest` for focused service tests.

**Git:** Do not run git commands. Use implementation checkpoints instead of commits.

---

## File Structure

- Create `data/ui/__init__.py`: package marker for the new UI module.
- Create `data/ui/sync_service.py`: sync workflow service, job discovery, DB status reads/writes, structured checks, task state, subprocess execution.
- Create `data/ui/run_sync_ui.py`: FastAPI app, API routes, static file mounting, uvicorn entry point.
- Create `data/ui/static/index.html`: compact operations table, toolbar, inline date editing, polling, and log panel.
- Create `data/ui/test_sync_service.py`: standard-library unit tests for job loading, check-spec mapping, date validation, whitelist rejection, and task lock behavior.
- Modify `requirements.txt`: add `fastapi` and `uvicorn`.

---

### Task 1: Service Models And Job Discovery

**Files:**
- Create: `data/ui/__init__.py`
- Create: `data/ui/sync_service.py`
- Create: `data/ui/test_sync_service.py`

- [ ] **Step 1: Create failing tests for job discovery and check-spec mapping**

Add `data/ui/test_sync_service.py`:

```python
import tempfile
import textwrap
import unittest
from pathlib import Path

from data.ui.sync_service import SyncService


class SyncServiceDiscoveryTest(unittest.TestCase):
    def test_load_jobs_from_run_all_whitelist(self):
        with tempfile.TemporaryDirectory() as tmp:
            sync_dir = Path(tmp)
            (sync_dir / "run_all.py").write_text(
                textwrap.dedent(
                    '''
                    SCRIPTS = [
                        "003_trade_cal.py",
                        "014_daily.py",
                    ]
                    '''
                ),
                encoding="utf-8",
            )
            (sync_dir / "run_check_today_sync.py").write_text(
                "TABLE_SPECS = []\n",
                encoding="utf-8",
            )

            service = SyncService(sync_dir=sync_dir)
            jobs = service.load_jobs()

            self.assertEqual([job["script_name"] for job in jobs], ["003_trade_cal.py", "014_daily.py"])
            self.assertEqual([job["table_name"] for job in jobs], ["003_trade_cal", "014_daily"])

    def test_check_specs_are_mapped_by_script_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            sync_dir = Path(tmp)
            (sync_dir / "run_all.py").write_text('SCRIPTS = ["014_daily.py", "082_moneyflow_dc.py"]\n', encoding="utf-8")
            (sync_dir / "run_check_today_sync.py").write_text(
                textwrap.dedent(
                    '''
                    from typing import NamedTuple
                    class TableSpec(NamedTuple):
                        script: str
                        table: str
                        date_col: str
                        category: str
                    TABLE_SPECS = [TableSpec("014_daily.py", "014_daily", "trade_date", "required_daily")]
                    '''
                ),
                encoding="utf-8",
            )

            service = SyncService(sync_dir=sync_dir)
            jobs = service.load_jobs()

            by_script = {job["script_name"]: job for job in jobs}
            self.assertTrue(by_script["014_daily.py"]["has_check_spec"])
            self.assertFalse(by_script["082_moneyflow_dc.py"]["has_check_spec"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: FAIL because `data.ui.sync_service` does not exist yet.

- [ ] **Step 3: Implement minimal service discovery**

Create `data/ui/__init__.py` as an empty file.

Create `data/ui/sync_service.py`:

```python
import importlib.util
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYNC_DIR = PROJECT_ROOT / "data" / "手动执行" / "20260425"


@dataclass
class TaskState:
    status: str = "idle"
    kind: Optional[str] = None
    current_script: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)


class TaskBusyError(RuntimeError):
    pass


class UnknownScriptError(ValueError):
    pass


class InvalidSyncDateError(ValueError):
    pass


class SyncService:
    def __init__(self, sync_dir: Path = DEFAULT_SYNC_DIR):
        self.sync_dir = Path(sync_dir)
        self._task = TaskState()
        self._lock = threading.Lock()

    def _load_module(self, module_name: str, file_name: str):
        module_path = self.sync_dir / file_name
        if not module_path.exists():
            raise FileNotFoundError(str(module_path))
        inserted = False
        sync_path = str(self.sync_dir)
        if sync_path not in sys.path:
            sys.path.insert(0, sync_path)
            inserted = True
        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            if inserted:
                try:
                    sys.path.remove(sync_path)
                except ValueError:
                    pass

    def load_script_names(self) -> List[str]:
        module = self._load_module("tushare_sync_run_all", "run_all.py")
        return list(module.SCRIPTS)

    def load_check_specs(self) -> Dict[str, object]:
        module = self._load_module("tushare_sync_check", "run_check_today_sync.py")
        return {spec.script: spec for spec in getattr(module, "TABLE_SPECS", [])}

    def load_jobs(self) -> List[dict]:
        check_specs = self.load_check_specs()
        jobs = []
        for script_name in self.load_script_names():
            table_name = Path(script_name).stem
            jobs.append({
                "script_name": script_name,
                "table_name": table_name,
                "has_check_spec": script_name in check_specs,
            })
        return jobs

    def ensure_whitelisted(self, script_name: str) -> None:
        if script_name not in self.load_script_names():
            raise UnknownScriptError(script_name)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: PASS for the two discovery tests.

- [ ] **Step 5: Checkpoint**

Record: service can read `run_all.py`, derive table names, and identify missing check specs. Do not run git.

---

### Task 2: Sync Status Reads And Date Editing

**Files:**
- Modify: `data/ui/sync_service.py`
- Modify: `data/ui/test_sync_service.py`

- [ ] **Step 1: Add failing tests for date validation and whitelist rejection**

Append to `data/ui/test_sync_service.py` before the `if __name__ == "__main__"` block:

```python

class SyncServiceDateEditTest(unittest.TestCase):
    def test_validate_sync_date_accepts_real_yyyymmdd(self):
        self.assertEqual(SyncService.validate_sync_date("20260513"), "2026-05-13")

    def test_validate_sync_date_rejects_bad_dates(self):
        with self.assertRaises(ValueError):
            SyncService.validate_sync_date("20260230")
        with self.assertRaises(ValueError):
            SyncService.validate_sync_date("2026-05-13")

    def test_unknown_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            sync_dir = Path(tmp)
            (sync_dir / "run_all.py").write_text('SCRIPTS = ["014_daily.py"]\n', encoding="utf-8")
            (sync_dir / "run_check_today_sync.py").write_text("TABLE_SPECS = []\n", encoding="utf-8")
            service = SyncService(sync_dir=sync_dir)

            with self.assertRaises(Exception):
                service.ensure_whitelisted("evil.py")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: FAIL because `validate_sync_date()` does not exist.

- [ ] **Step 3: Implement sync status read/write helpers**

Update `data/ui/sync_service.py`:

```python
import os
import subprocess
import time
from datetime import date, datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
```

Add near constants:

```python
load_dotenv(PROJECT_ROOT / ".env")
SCHEMA = "tushare_v2"
```

Add methods inside `SyncService`:

```python
    @staticmethod
    def validate_sync_date(value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y%m%d")
        except ValueError as exc:
            raise InvalidSyncDateError("同步日期必须是有效 YYYYMMDD 日期") from exc
        return parsed.strftime("%Y-%m-%d")

    def get_engine(self):
        db_url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://", 1)
        return create_engine(db_url)

    def load_sync_status_map(self) -> Dict[str, dict]:
        rows = {}
        engine = self.get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(
                f"SELECT script_name, table_name, sync_date, status, updated_at "
                f"FROM {SCHEMA}.sync_status"
            ))
            for row in result:
                rows[row.script_name] = {
                    "script_name": row.script_name,
                    "table_name": row.table_name,
                    "sync_date": row.sync_date.strftime("%Y-%m-%d") if row.sync_date else None,
                    "status": row.status,
                    "updated_at": row.updated_at.strftime("%Y-%m-%d %H:%M:%S") if row.updated_at else None,
                }
        return rows

    def load_job_rows(self) -> dict:
        jobs = self.load_jobs()
        try:
            status_map = self.load_sync_status_map()
            db_error = None
        except Exception as exc:
            status_map = {}
            db_error = str(exc)

        rows = []
        for job in jobs:
            status = status_map.get(job["script_name"], {})
            rows.append({
                **job,
                "sync_date": status.get("sync_date"),
                "status": status.get("status", "not_synced" if not db_error else "unknown"),
                "updated_at": status.get("updated_at"),
                "runtime": "-",
            })
        return {"rows": rows, "db_error": db_error}

    def update_sync_date(self, script_name: str, sync_date: str) -> dict:
        self.ensure_whitelisted(script_name)
        saved_date = self.validate_sync_date(sync_date)
        table_name = Path(script_name).stem
        engine = self.get_engine()
        with engine.begin() as conn:
            conn.execute(text(f"""
                INSERT INTO {SCHEMA}.sync_status
                    (script_name, table_name, sync_date, status, updated_at)
                VALUES (:script_name, :table_name, :sync_date, 'ing', CURRENT_TIMESTAMP)
                ON CONFLICT (script_name) DO UPDATE SET
                    table_name = EXCLUDED.table_name,
                    sync_date = EXCLUDED.sync_date,
                    status = 'ing',
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "script_name": script_name,
                "table_name": table_name,
                "sync_date": saved_date,
            })
        return {
            "script_name": script_name,
            "table_name": table_name,
            "sync_date": saved_date,
            "status": "ing",
        }
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: PASS. The DB methods are not called by unit tests.

- [ ] **Step 5: Checkpoint**

Record: service validates `YYYYMMDD`, rejects unknown scripts, reads `sync_status`, and upserts edited dates with `status='ing'`. Do not run git.

---

### Task 3: Structured Check And Task Lock

**Files:**
- Modify: `data/ui/sync_service.py`
- Modify: `data/ui/test_sync_service.py`

- [ ] **Step 1: Add failing tests for task lock and unconfigured checks**

Append to `data/ui/test_sync_service.py` before the `if __name__ == "__main__"` block:

```python

class SyncServiceTaskStateTest(unittest.TestCase):
    def test_start_task_rejects_when_running(self):
        service = SyncService()
        service._task.status = "running"
        with self.assertRaises(Exception):
            service._start_task("single_sync", "014_daily.py")

    def test_row_check_without_spec_returns_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            sync_dir = Path(tmp)
            (sync_dir / "run_all.py").write_text('SCRIPTS = ["082_moneyflow_dc.py"]\n', encoding="utf-8")
            (sync_dir / "run_check_today_sync.py").write_text("TABLE_SPECS = []\n", encoding="utf-8")
            service = SyncService(sync_dir=sync_dir)

            result = service.check_one("082_moneyflow_dc.py", "20260513")

            self.assertEqual(result["status"], "not_configured")
            self.assertEqual(result["script_name"], "082_moneyflow_dc.py")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: FAIL because `_start_task()` and `check_one()` do not exist.

- [ ] **Step 3: Implement task state, structured check, and task snapshots**

Add methods inside `SyncService`:

```python
    def _append_log(self, line: str) -> None:
        with self._lock:
            self._task.logs.append(line.rstrip())
            self._task.logs = self._task.logs[-2000:]

    def _start_task(self, kind: str, current_script: Optional[str] = None) -> None:
        with self._lock:
            if self._task.status == "running":
                raise TaskBusyError("已有任务正在运行")
            self._task = TaskState(
                status="running",
                kind=kind,
                current_script=current_script,
                started_at=datetime.now(),
                logs=[],
            )

    def _finish_task(self, status: str, return_code: int = 0, error: Optional[str] = None) -> None:
        with self._lock:
            self._task.status = status
            self._task.finished_at = datetime.now()
            self._task.return_code = return_code
            self._task.error = error

    def get_task_state(self) -> dict:
        with self._lock:
            started = self._task.started_at
            finished = self._task.finished_at
            if started:
                end = finished or datetime.now()
                elapsed_seconds = int((end - started).total_seconds())
            else:
                elapsed_seconds = 0
            return {
                "status": self._task.status,
                "kind": self._task.kind,
                "current_script": self._task.current_script,
                "started_at": started.strftime("%Y-%m-%d %H:%M:%S") if started else None,
                "finished_at": finished.strftime("%Y-%m-%d %H:%M:%S") if finished else None,
                "elapsed_seconds": elapsed_seconds,
                "return_code": self._task.return_code,
                "error": self._task.error,
                "logs": list(self._task.logs),
            }

    def _check_module(self):
        return self._load_module("tushare_sync_check_runtime", "run_check_today_sync.py")

    def check_all(self, target_date: str) -> dict:
        self.validate_sync_date(target_date)
        module = self._check_module()
        configured_scripts = {spec.script for spec in module.TABLE_SPECS}
        unconfigured = [
            {"script_name": script, "table_name": Path(script).stem, "status": "not_configured"}
            for script in self.load_script_names()
            if script not in configured_scripts
        ]
        engine = self.get_engine()
        with engine.connect() as conn:
            if hasattr(module, "is_open_trade_date") and not module.is_open_trade_date(conn, SCHEMA, target_date):
                return {
                    "target_date": target_date,
                    "status": "non_trade_date",
                    "message": "{} 不是 SSE 交易日，跳过今日数据完整性检查。".format(target_date),
                    "results": [],
                    "unconfigured": unconfigured,
                }
            results = module.collect_results(conn, SCHEMA, target_date, module.LOW_COUNT_RATIO)
        return {
            "target_date": target_date,
            "results": [self._check_result_to_dict(result) for result in results],
            "unconfigured": unconfigured,
        }

    def check_one(self, script_name: str, target_date: str) -> dict:
        self.ensure_whitelisted(script_name)
        self.validate_sync_date(target_date)
        module = self._check_module()
        specs = {spec.script: spec for spec in module.TABLE_SPECS}
        if script_name not in specs:
            return {
                "script_name": script_name,
                "table_name": Path(script_name).stem,
                "target_date": target_date,
                "status": "not_configured",
                "message": "该脚本未配置今日同步校验",
            }
        engine = self.get_engine()
        with engine.connect() as conn:
            if hasattr(module, "is_open_trade_date") and not module.is_open_trade_date(conn, SCHEMA, target_date):
                return {
                    "script_name": script_name,
                    "table_name": Path(script_name).stem,
                    "target_date": target_date,
                    "status": "non_trade_date",
                    "message": "{} 不是 SSE 交易日，跳过今日数据完整性检查。".format(target_date),
                }
            results = module.collect_results(conn, SCHEMA, target_date, module.LOW_COUNT_RATIO)
        for result in results:
            if result.spec.script == script_name:
                data = self._check_result_to_dict(result)
                data["target_date"] = target_date
                return data
        return {
            "script_name": script_name,
            "table_name": Path(script_name).stem,
            "target_date": target_date,
            "status": "not_configured",
            "message": "该脚本未返回校验结果",
        }

    @staticmethod
    def _check_result_to_dict(result) -> dict:
        return {
            "script_name": result.spec.script,
            "table_name": result.spec.table,
            "date_col": result.spec.date_col,
            "category": result.spec.category,
            "status": result.status,
            "today_count": result.today_count,
            "previous_count": result.previous_count,
            "command": result.command,
            "message": result.message,
        }
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: PASS. `check_one()` unconfigured path does not connect to the database.

- [ ] **Step 5: Checkpoint**

Record: task locking exists, task snapshots are serializable, structured checks return `not_configured` without failing. Do not run git.

---

### Task 4: Subprocess Sync Execution

**Files:**
- Modify: `data/ui/sync_service.py`

- [ ] **Step 1: Add subprocess execution methods**

Add methods inside `SyncService`:

```python
    def run_single_sync_background(self, script_name: str) -> None:
        self.ensure_whitelisted(script_name)
        self._start_task("single_sync", script_name)
        thread = threading.Thread(target=self._run_single_sync_worker, args=(script_name,), daemon=True)
        thread.start()

    def run_full_sync_background(self) -> None:
        self._start_task("full_sync", None)
        thread = threading.Thread(target=self._run_full_sync_worker, daemon=True)
        thread.start()

    def run_check_all_background(self, target_date: str) -> None:
        self.validate_sync_date(target_date)
        self._start_task("check_all", None)
        thread = threading.Thread(target=self._run_check_all_worker, args=(target_date,), daemon=True)
        thread.start()

    def run_check_one_background(self, script_name: str, target_date: str) -> None:
        self.ensure_whitelisted(script_name)
        self.validate_sync_date(target_date)
        self._start_task("check_one", script_name)
        thread = threading.Thread(target=self._run_check_one_worker, args=(script_name, target_date), daemon=True)
        thread.start()

    def _run_single_sync_worker(self, script_name: str) -> None:
        try:
            code = self._run_script(script_name)
            self._finish_task("completed" if code == 0 else "failed", code)
        except Exception as exc:
            self._append_log("ERROR: {}".format(exc))
            self._finish_task("failed", 1, str(exc))

    def _run_full_sync_worker(self) -> None:
        try:
            for script_name in self.load_script_names():
                with self._lock:
                    self._task.current_script = script_name
                code = self._run_script(script_name)
                if code != 0:
                    self._finish_task("failed", code, "{} failed".format(script_name))
                    return
            self._finish_task("completed", 0)
        except Exception as exc:
            self._append_log("ERROR: {}".format(exc))
            self._finish_task("failed", 1, str(exc))

    def _run_check_all_worker(self, target_date: str) -> None:
        try:
            result = self.check_all(target_date)
            self._append_log(self._format_check_payload(result))
            self._finish_task("completed", 0)
        except Exception as exc:
            self._append_log("ERROR: {}".format(exc))
            self._finish_task("failed", 1, str(exc))

    def _run_check_one_worker(self, script_name: str, target_date: str) -> None:
        try:
            result = self.check_one(script_name, target_date)
            self._append_log(self._format_check_payload(result))
            self._finish_task("completed", 0)
        except Exception as exc:
            self._append_log("ERROR: {}".format(exc))
            self._finish_task("failed", 1, str(exc))

    def _run_script(self, script_name: str) -> int:
        self.ensure_whitelisted(script_name)
        script_path = self.sync_dir / script_name
        self._append_log("=" * 60)
        self._append_log("[RUN] {}".format(script_name))
        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(script_path)],
            cwd=str(self.sync_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            self._append_log(line)
        return process.wait()

    @staticmethod
    def _format_check_payload(payload: dict) -> str:
        lines = ["校验结果:"]
        if "results" in payload:
            for item in payload["results"]:
                lines.append("{status:16} {script:24} {table:20} 今日={today} 上日={prev} {msg}".format(
                    status=item["status"],
                    script=item["script_name"],
                    table=item["table_name"],
                    today="-" if item["today_count"] is None else item["today_count"],
                    prev="-" if item["previous_count"] is None else item["previous_count"],
                    msg=item["message"],
                ))
            if payload.get("unconfigured"):
                lines.append("未配置校验:")
                for item in payload["unconfigured"]:
                    lines.append("not_configured   {script:24} {table}".format(
                        script=item["script_name"],
                        table=item["table_name"],
                    ))
        else:
            lines.append("{status} {script} {table} {message}".format(
                status=payload.get("status"),
                script=payload.get("script_name"),
                table=payload.get("table_name"),
                message=payload.get("message", ""),
            ))
        return "\n".join(lines)
```

- [ ] **Step 2: Run tests**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: PASS.

- [ ] **Step 3: Inspect subprocess command safety**

Check that `_run_script()` calls `ensure_whitelisted()` and uses `[sys.executable, "-X", "utf8", str(script_path)]` without `shell=True`.

- [ ] **Step 4: Checkpoint**

Record: service can run whitelisted scripts in background threads, capture logs, and stop full sync on first failure. Do not run git.

---

### Task 5: FastAPI App And Routes

**Files:**
- Create: `data/ui/run_sync_ui.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Update dependencies**

Add under GUI or web dependencies in `requirements.txt`:

```text
fastapi>=0.110.0          # 本地Web同步控制台
uvicorn>=0.27.0           # FastAPI开发服务器
```

- [ ] **Step 2: Create FastAPI app**

Create `data/ui/run_sync_ui.py`:

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from data.ui.sync_service import (
    InvalidSyncDateError,
    SyncService,
    TaskBusyError,
    UnknownScriptError,
)


HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"

app = FastAPI(title="Tushare Sync UI")
service = SyncService()


class ScriptRequest(BaseModel):
    script_name: str


class CheckRequest(BaseModel):
    target_date: str


class CheckOneRequest(BaseModel):
    script_name: str
    target_date: str


class SyncDateRequest(BaseModel):
    script_name: str
    sync_date: str


def api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TaskBusyError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (UnknownScriptError, InvalidSyncDateError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/jobs")
def jobs():
    return service.load_job_rows()


@app.get("/api/task")
def task():
    return service.get_task_state()


@app.post("/api/sync-one")
def sync_one(payload: ScriptRequest):
    try:
        service.run_single_sync_background(payload.script_name)
        return {"ok": True}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/sync-all")
def sync_all():
    try:
        service.run_full_sync_background()
        return {"ok": True}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/check-all")
def check_all(payload: CheckRequest):
    try:
        service.run_check_all_background(payload.target_date)
        return {"ok": True}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/check-one")
def check_one(payload: CheckOneRequest):
    try:
        service.run_check_one_background(payload.script_name, payload.target_date)
        return {"ok": True}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/sync-date")
def sync_date(payload: SyncDateRequest):
    try:
        return service.update_sync_date(payload.script_name, payload.sync_date)
    except Exception as exc:
        raise api_error(exc)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main():
    print("Tushare Sync UI: http://127.0.0.1:8008")
    uvicorn.run("data.ui.run_sync_ui:app", host="127.0.0.1", port=8008, reload=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run import check**

Run:

```powershell
python -c "from data.ui.run_sync_ui import app; print(app.title)"
```

Expected output includes:

```text
Tushare Sync UI
```

- [ ] **Step 4: Run unit tests**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Record: API routes exist and import cleanly. Do not run git.

---

### Task 6: Static Web UI

**Files:**
- Create: `data/ui/static/index.html`

- [ ] **Step 1: Create the single-page UI**

Create `data/ui/static/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tushare 数据同步</title>
  <style>
    body { margin: 0; font-family: "Microsoft YaHei", Arial, sans-serif; color: #1f2933; background: #f6f8fa; }
    header { height: 40px; display: flex; align-items: center; justify-content: center; background: #ffffff; border-bottom: 1px solid #d9dee5; font-weight: 600; }
    main { padding: 14px 18px 18px; }
    .toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
    button { border: 1px solid #b8c1cc; background: #ffffff; border-radius: 4px; padding: 5px 10px; cursor: pointer; font-size: 13px; }
    button:hover:not(:disabled) { background: #edf4ff; border-color: #6aa0dc; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    input { border: 1px solid #b8c1cc; border-radius: 4px; padding: 5px 8px; font-size: 13px; }
    .status { margin-left: auto; font-size: 13px; color: #435569; }
    .banner { display: none; margin-bottom: 10px; padding: 8px 10px; border: 1px solid #d8a33f; background: #fff8e6; color: #6f4d00; border-radius: 4px; }
    table { width: 100%; border-collapse: collapse; background: #ffffff; table-layout: fixed; border: 1px solid #c9d1d9; }
    th, td { border: 1px solid #c9d1d9; padding: 5px 6px; font-size: 12px; vertical-align: middle; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    th { background: #eef2f6; text-align: left; font-weight: 600; }
    .col-script { width: 15%; }
    .col-table { width: 15%; }
    .col-date { width: 11%; }
    .col-status { width: 9%; }
    .col-updated { width: 15%; }
    .col-runtime { width: 8%; }
    .col-actions { width: 27%; }
    .actions { display: flex; gap: 4px; align-items: center; }
    .date-edit { width: 86px; }
    .log-title { margin: 12px 0 4px; font-size: 13px; font-weight: 600; }
    pre { height: 260px; overflow: auto; margin: 0; padding: 10px; background: #111827; color: #d1d5db; border-radius: 4px; font-size: 12px; line-height: 1.45; }
  </style>
</head>
<body>
  <header>数据同步窗口</header>
  <main>
    <div class="toolbar">
      <button id="syncAllBtn">全部同步</button>
      <button id="checkAllBtn">校验今日同步</button>
      <button id="refreshBtn">刷新</button>
      <label>检查日期 <input id="targetDate" maxlength="8"></label>
      <span id="taskStatus" class="status">状态：加载中</span>
    </div>
    <div id="banner" class="banner"></div>
    <table>
      <thead>
        <tr>
          <th class="col-script">脚本名称</th>
          <th class="col-table">表名</th>
          <th class="col-date">同步日期</th>
          <th class="col-status">状态</th>
          <th class="col-updated">更新时间</th>
          <th class="col-runtime">运行时间</th>
          <th class="col-actions">操作</th>
        </tr>
      </thead>
      <tbody id="jobsBody"></tbody>
    </table>
    <div class="log-title">日志</div>
    <pre id="logPanel"></pre>
  </main>
  <script>
    const jobsBody = document.getElementById("jobsBody");
    const logPanel = document.getElementById("logPanel");
    const banner = document.getElementById("banner");
    const taskStatus = document.getElementById("taskStatus");
    const targetDate = document.getElementById("targetDate");

    function todayYmd() {
      const now = new Date();
      const mm = String(now.getMonth() + 1).padStart(2, "0");
      const dd = String(now.getDate()).padStart(2, "0");
      return `${now.getFullYear()}${mm}${dd}`;
    }

    targetDate.value = todayYmd();

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: {"Content-Type": "application/json"},
        ...options,
      });
      if (!response.ok) {
        let detail = response.statusText;
        try {
          const data = await response.json();
          detail = data.detail || detail;
        } catch (e) {}
        throw new Error(detail);
      }
      return response.json();
    }

    function setBanner(message) {
      banner.textContent = message || "";
      banner.style.display = message ? "block" : "none";
    }

    function formatElapsed(seconds) {
      const m = Math.floor(seconds / 60);
      const s = seconds % 60;
      return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    function disableActions(disabled) {
      document.querySelectorAll("button").forEach(button => {
        if (button.id !== "refreshBtn") button.disabled = disabled;
      });
    }

    async function refreshJobs() {
      const data = await api("/api/jobs");
      setBanner(data.db_error ? `数据库状态读取失败：${data.db_error}` : "");
      jobsBody.innerHTML = "";
      data.rows.forEach(row => {
        const tr = document.createElement("tr");
        const syncDate = row.sync_date ? row.sync_date.replaceAll("-", "") : "";
        const checkButton = row.has_check_spec
          ? `<button data-action="check" data-script="${row.script_name}">校验</button>`
          : `<button data-action="not-configured" data-script="${row.script_name}">未配置</button>`;
        tr.innerHTML = `
          <td title="${row.script_name}">${row.script_name}</td>
          <td title="${row.table_name}">${row.table_name}</td>
          <td><input class="date-edit" value="${syncDate}" maxlength="8"></td>
          <td>${row.status || "-"}</td>
          <td>${row.updated_at || "-"}</td>
          <td>${row.runtime || "-"}</td>
          <td>
            <div class="actions">
              <button data-action="sync" data-script="${row.script_name}">同步</button>
              <button data-action="save-date" data-script="${row.script_name}">保存日期</button>
              ${checkButton}
            </div>
          </td>
        `;
        jobsBody.appendChild(tr);
      });
    }

    async function refreshTask() {
      const task = await api("/api/task");
      const running = task.status === "running";
      const current = task.current_script ? ` ${task.current_script}` : "";
      taskStatus.textContent = `状态：${task.status}${current} 耗时 ${formatElapsed(task.elapsed_seconds || 0)}`;
      disableActions(running);
      logPanel.textContent = (task.logs || []).join("\n");
      logPanel.scrollTop = logPanel.scrollHeight;
    }

    async function postTask(path, payload) {
      try {
        await api(path, {method: "POST", body: JSON.stringify(payload || {})});
        await refreshTask();
      } catch (e) {
        alert(e.message);
      }
    }

    jobsBody.addEventListener("click", async event => {
      const button = event.target.closest("button");
      if (!button) return;
      const script = button.dataset.script;
      const action = button.dataset.action;
      const row = button.closest("tr");
      if (action === "sync") {
        await postTask("/api/sync-one", {script_name: script});
      } else if (action === "check") {
        await postTask("/api/check-one", {script_name: script, target_date: targetDate.value});
      } else if (action === "not-configured") {
        await postTask("/api/check-one", {script_name: script, target_date: targetDate.value});
      } else if (action === "save-date") {
        const value = row.querySelector(".date-edit").value;
        if (!confirm(`保存 ${script} 的同步日期为 ${value}？保存后下次同步会从该日期重跑。`)) return;
        try {
          await api("/api/sync-date", {method: "POST", body: JSON.stringify({script_name: script, sync_date: value})});
          await refreshJobs();
        } catch (e) {
          alert(e.message);
        }
      }
    });

    document.getElementById("syncAllBtn").addEventListener("click", () => postTask("/api/sync-all"));
    document.getElementById("checkAllBtn").addEventListener("click", () => postTask("/api/check-all", {target_date: targetDate.value}));
    document.getElementById("refreshBtn").addEventListener("click", async () => {
      await refreshJobs();
      await refreshTask();
    });

    async function poll() {
      try {
        await refreshTask();
      } catch (e) {
        taskStatus.textContent = `状态读取失败：${e.message}`;
      }
    }

    async function init() {
      await refreshJobs();
      await refreshTask();
      setInterval(poll, 1500);
      setInterval(refreshJobs, 10000);
    }

    init().catch(e => setBanner(e.message));
  </script>
</body>
</html>
```

- [ ] **Step 2: Start local server**

Run:

```powershell
python -X utf8 data/ui/run_sync_ui.py
```

Expected: server starts and prints:

```text
Tushare Sync UI: http://127.0.0.1:8008
```

- [ ] **Step 3: Open page and inspect first render**

Open:

```text
http://127.0.0.1:8008
```

Expected: compact table appears, buttons fit, `未配置` appears on rows missing `TABLE_SPECS`.

- [ ] **Step 4: Checkpoint**

Record: first UI renders and can call API routes. Do not run git.

---

### Task 7: Verification And Fixes

**Files:**
- Modify as needed: `data/ui/sync_service.py`
- Modify as needed: `data/ui/run_sync_ui.py`
- Modify as needed: `data/ui/static/index.html`

- [ ] **Step 1: Run unit tests**

Run:

```powershell
python -m unittest data.ui.test_sync_service -v
```

Expected: PASS.

- [ ] **Step 2: Run import check**

Run:

```powershell
python -c "from data.ui.run_sync_ui import app; print(app.title)"
```

Expected:

```text
Tushare Sync UI
```

- [ ] **Step 3: Start server**

Run:

```powershell
python -X utf8 data/ui/run_sync_ui.py
```

Expected: server runs on `http://127.0.0.1:8008`.

- [ ] **Step 4: Verify job table**

In the browser, confirm:

- Every script listed in `data/手动执行/20260425/run_all.py` appears exactly once.
- Helper scripts like `_check_status.py` do not appear.
- `082_moneyflow_dc.py`, `083_moneyflow_cnt_ths.py`, `084_moneyflow_ind_ths.py`, `085_moneyflow_ind_dc.py`, `086_moneyflow_mkt_dc.py`, and `092_limit_step.py` show `未配置` unless their check specs are later added.

- [ ] **Step 5: Verify DB status behavior**

With DB configured, confirm:

- Existing `sync_status` rows show `sync_date`, `status`, and `updated_at`.
- Missing rows show `not_synced`.

If DB is unavailable, confirm:

- The job list still renders.
- The banner shows the DB error.

- [ ] **Step 6: Verify sync date edit**

Pick a low-risk row and enter a valid date such as:

```text
20260501
```

Click `保存日期`.

Expected:

- Browser confirmation appears before saving.
- Row refreshes after save.
- Database row for that `script_name` has `status='ing'`.

Then try:

```text
20260230
```

Expected: UI shows validation error and does not update the row.

- [ ] **Step 7: Verify structured checks**

Click top-level `校验今日同步`.

Expected:

- Task state changes to running.
- Logs show configured table results.
- Logs include unconfigured scripts under `未配置校验`.

Click a row-level `未配置`.

Expected: logs show `not_configured` for that row.

- [ ] **Step 8: Verify task lock**

Start a long-running single sync or full sync. While it is running, trigger another sync/check API action.

Expected:

- The second request returns HTTP 409.
- UI buttons are disabled except refresh.
- Running logs continue to update.

- [ ] **Step 9: Verify subprocess logs**

Run one low-risk single script from the UI.

Expected:

- Logs show `[RUN] <script>`.
- Script stdout/stderr appears in the log panel.
- Task ends as `completed` for exit code 0 or `failed` for non-zero exit code.

- [ ] **Step 10: Final checkpoint**

Record:

- Commands run.
- Whether DB-backed checks were verified.
- Any limitations, especially if no real sync was run to avoid expensive Tushare calls.
- No git commands were used.

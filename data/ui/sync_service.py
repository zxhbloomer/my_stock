import importlib.util
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYNC_DIR = PROJECT_ROOT / "data" / "手动执行" / "20260425"
_IMPORT_LOCK = threading.Lock()
SCHEMA = "tushare_v2"
SYNC_STATUS_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.sync_status (
    script_name  VARCHAR(64)  NOT NULL,
    table_name   VARCHAR(64)  NOT NULL,
    sync_date    DATE         NOT NULL,
    status       VARCHAR(8)   NOT NULL CHECK (status IN ('ing', 'ok')),
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    last_start_at TIMESTAMP,
    last_end_at   TIMESTAMP,
    PRIMARY KEY (script_name)
)
"""

load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class TaskState:
    task_id: str = ""
    status: str = "idle"
    kind: str = ""
    current_script: str = ""
    script_names: list = field(default_factory=list)
    script_status: dict = field(default_factory=dict)
    script_updated_at: dict = field(default_factory=dict)
    started_at: object = None
    finished_at: object = None
    return_code: object = None
    error: str = ""
    result: object = None
    logs: list = field(default_factory=list)
    stop_requested: bool = False
    process: object = None


class TaskBusyError(Exception):
    pass


class UnknownScriptError(Exception):
    pass


class InvalidSyncDateError(ValueError):
    pass


class SyncService:
    def __init__(self, sync_dir=DEFAULT_SYNC_DIR):
        self.sync_dir = Path(sync_dir)
        self.state = TaskState()
        self._lock = threading.Lock()
        self._tasks = {}
        self._script_locks = {}
        self._task_seq = 0
        self._thread_context = threading.local()

    def _load_module(self, module_name, file_name):
        with _IMPORT_LOCK:
            module_path = self.sync_dir / file_name
            spec = importlib.util.spec_from_file_location(module_name, str(module_path))
            module = importlib.util.module_from_spec(spec)
            sync_path = str(self.sync_dir)
            old_module = sys.modules.get(module_name)
            old_path = list(sys.path)

            if sync_path not in sys.path:
                sys.path.insert(0, sync_path)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
                return module
            finally:
                if old_module is None:
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = old_module
                sys.path[:] = old_path

    def load_script_names(self):
        module = self._load_module("tushare_sync_run_all", "run_all.py")
        return list(module.SCRIPTS)

    def load_check_specs(self):
        module = self._load_module("tushare_sync_check_today", "run_check_today_sync.py")
        return {spec.script: spec for spec in module.TABLE_SPECS}

    def load_jobs(self):
        check_specs = self.load_check_specs()
        jobs = []
        for script_name in self.load_script_names():
            jobs.append(
                {
                    "script_name": script_name,
                    "table_name": Path(script_name).stem,
                    "has_check_spec": script_name in check_specs,
                }
            )
        return jobs

    def ensure_whitelisted(self, script_name):
        if script_name not in self.load_script_names():
            raise UnknownScriptError(script_name)
        self._resolve_script_path(script_name)
        return script_name

    def order_selected_script_names(self, script_names):
        selected = set(script_names)
        whitelist = self.load_script_names()
        for script_name in selected:
            if script_name not in whitelist:
                raise UnknownScriptError(script_name)
            self._resolve_script_path(script_name)
        return [script_name for script_name in whitelist if script_name in selected]

    def _append_log(self, line):
        stripped = str(line).strip()
        with self._lock:
            task = self._get_task_locked(self._current_task_id())
            if task is None:
                task = self.state
            task.logs.append(stripped)
            task.logs = task.logs[-2000:]
            if task is not self.state and task.task_id == self.state.task_id:
                self.state = task

    def _current_task_id(self):
        return getattr(self._thread_context, "task_id", None) or getattr(self, "_last_task_id", "")

    def _get_task_locked(self, task_id):
        if task_id:
            return self._tasks.get(task_id)
        return None

    def _next_task_id_locked(self):
        self._task_seq += 1
        return "task-{}".format(self._task_seq)

    def _set_thread_task(self, task_id):
        self._thread_context.task_id = task_id

    def _start_task(self, kind, current_script=None, script_names=None):
        script_names = list(script_names or ([current_script] if current_script else []))
        now = datetime.now()
        with self._lock:
            for script_name in script_names:
                locked_by = self._script_locks.get(script_name)
                if locked_by:
                    raise TaskBusyError("{} 已在运行或等待执行".format(script_name))

            task_id = self._next_task_id_locked()
            task = TaskState(
                task_id=task_id,
                status="running",
                kind=kind,
                current_script=current_script,
                script_names=script_names,
                script_status={script_name: "pending" for script_name in script_names},
                script_updated_at={script_name: now for script_name in script_names},
                started_at=now,
                logs=[],
            )
            self._tasks[task_id] = task
            for script_name in script_names:
                self._script_locks[script_name] = task_id
            self._last_task_id = task_id
            self.state = task
            return task_id

    def _finish_task(self, status, return_code=0, error=None, task_id=None):
        task_id = task_id or self._current_task_id()
        with self._lock:
            task = self._get_task_locked(task_id) or self.state
            task.status = status
            task.finished_at = datetime.now()
            task.return_code = return_code
            task.error = error or ""
            task.process = None
            if status in ("failed", "stopped"):
                now = datetime.now()
                for script_name, script_status in list(task.script_status.items()):
                    if script_status == "pending":
                        task.script_status[script_name] = "stopped"
                        task.script_updated_at[script_name] = now
            for script_name in list(task.script_names):
                if self._script_locks.get(script_name) == task.task_id:
                    self._script_locks.pop(script_name, None)
            if task.task_id:
                self._tasks[task.task_id] = task
            if not self.state.task_id or self.state.task_id == task.task_id:
                self.state = task

    def _set_script_status(self, task_id, script_name, status):
        with self._lock:
            task = self._get_task_locked(task_id)
            if task is None:
                return
            task.script_status[script_name] = status
            task.script_updated_at[script_name] = datetime.now()
            if status == "running":
                task.current_script = script_name
            if self.state.task_id == task.task_id:
                self.state = task

    def _is_script_stopped(self, task_id, script_name):
        with self._lock:
            task = self._get_task_locked(task_id)
            return bool(task and task.script_status.get(script_name) == "stopped")

    def _release_script_lock(self, task_id, script_name):
        with self._lock:
            if self._script_locks.get(script_name) == task_id:
                self._script_locks.pop(script_name, None)

    def _task_to_dict_locked(self, task):
        started_at = task.started_at
        finished_at = task.finished_at
        if started_at and finished_at:
            elapsed_seconds = (finished_at - started_at).total_seconds()
        elif started_at and task.status == "running":
            elapsed_seconds = (datetime.now() - started_at).total_seconds()
        else:
            elapsed_seconds = 0
        return {
            "task_id": task.task_id,
            "status": task.status,
            "kind": task.kind,
            "current_script": task.current_script,
            "script_names": list(task.script_names),
            "script_status": dict(task.script_status),
            "script_updated_at": {
                script_name: self._format_datetime(updated_at)
                for script_name, updated_at in task.script_updated_at.items()
            },
            "started_at": self._format_datetime(started_at),
            "finished_at": self._format_datetime(finished_at),
            "elapsed_seconds": elapsed_seconds,
            "return_code": task.return_code,
            "error": task.error,
            "result": task.result,
            "logs": list(task.logs),
        }

    def get_task_state(self):
        with self._lock:
            tasks = list(self._tasks.values())
            if not tasks:
                return self._task_to_dict_locked(self.state)
            running_tasks = [task for task in tasks if task.status == "running"]
            latest_task = tasks[-1]
            if running_tasks:
                aggregate = TaskState(
                    status="running",
                    kind="multi" if len(running_tasks) > 1 else running_tasks[0].kind,
                    current_script=", ".join(task.current_script for task in running_tasks if task.current_script),
                    started_at=min(task.started_at for task in running_tasks if task.started_at),
                    logs=[],
                )
                for task in tasks:
                    aggregate.logs.extend(task.logs)
                aggregate.logs = aggregate.logs[-2000:]
                return self._task_to_dict_locked(aggregate)
            return self._task_to_dict_locked(latest_task)

    def get_tasks_state(self):
        with self._lock:
            tasks = [self._task_to_dict_locked(task) for task in self._tasks.values()]
            active_scripts = {}
            for script_name, task_id in self._script_locks.items():
                task = self._tasks.get(task_id)
                if task is None:
                    continue
                active_scripts[script_name] = {
                    "task_id": task_id,
                    "kind": task.kind,
                    "status": task.script_status.get(script_name, task.status),
                    "updated_at": self._format_datetime(task.script_updated_at.get(script_name)),
                }
            return {
                "tasks": tasks,
                "active_scripts": active_scripts,
            }

    def stop_script(self, script_name):
        self.ensure_whitelisted(script_name)
        process = None
        with self._lock:
            task_id = self._script_locks.get(script_name)
            if not task_id:
                raise TaskBusyError("{} 未在运行或等待执行".format(script_name))
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskBusyError("{} 未在运行或等待执行".format(script_name))
            current_status = task.script_status.get(script_name, "")
            task.script_status[script_name] = "stopped"
            task.script_updated_at[script_name] = datetime.now()
            if current_status == "pending":
                self._script_locks.pop(script_name, None)
            elif current_status == "running":
                process = task.process
            if self.state.task_id == task.task_id:
                self.state = task

        if process is not None:
            self._terminate_process(process)
        return {"script_name": script_name, "task_id": task_id, "status": "stopped"}

    def _terminate_process(self, process):
        try:
            if process.poll() is None:
                process.terminate()
                threading.Thread(target=self._kill_process_later, args=(process,), daemon=True).start()
        except Exception as exc:
            self._append_log("ERROR: 停止进程失败 {}".format(exc))

    @staticmethod
    def _kill_process_later(process):
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        except Exception:
            pass

    def _check_module(self):
        return self._load_module("tushare_sync_check_today", "run_check_today_sync.py")

    def check_all(self, target_date):
        self.validate_sync_date(target_date)
        module = self._check_module()
        specs_by_script = {spec.script: spec for spec in module.TABLE_SPECS}
        unconfigured = [
            script_name
            for script_name in self.load_script_names()
            if script_name not in specs_by_script
        ]

        with self.get_engine().connect() as conn:
            is_open_trade_date = getattr(module, "is_open_trade_date", None)
            if is_open_trade_date and not is_open_trade_date(conn, SCHEMA, target_date):
                return {
                    "target_date": target_date,
                    "status": "non_trade_date",
                    "results": [],
                    "unconfigured": unconfigured,
                    "message": "非交易日，跳过今日数据完整性检查",
                }
            results = module.collect_results(conn, SCHEMA, target_date, module.LOW_COUNT_RATIO)

        return {
            "target_date": target_date,
            "results": [self._check_result_to_dict(result) for result in results],
            "unconfigured": unconfigured,
        }

    def check_one(self, script_name, target_date):
        self.ensure_whitelisted(script_name)
        self.validate_sync_date(target_date)
        module = self._check_module()
        specs_by_script = {spec.script: spec for spec in module.TABLE_SPECS}
        if script_name not in specs_by_script:
            return {
                "script_name": script_name,
                "table_name": Path(script_name).stem,
                "date_col": None,
                "category": "",
                "status": "not_configured",
                "today_count": None,
                "previous_count": None,
                "command": None,
                "message": "脚本未配置检查规则",
            }

        with self.get_engine().connect() as conn:
            is_open_trade_date = getattr(module, "is_open_trade_date", None)
            if is_open_trade_date and not is_open_trade_date(conn, SCHEMA, target_date):
                spec = specs_by_script[script_name]
                return {
                    "script_name": script_name,
                    "table_name": spec.table,
                    "date_col": spec.date_col,
                    "category": spec.category,
                    "status": "non_trade_date",
                    "today_count": None,
                    "previous_count": None,
                    "command": None,
                    "message": "非交易日，跳过今日数据完整性检查",
                }
            results = module.collect_results(conn, SCHEMA, target_date, module.LOW_COUNT_RATIO)

        for result in results:
            if result.spec.script == script_name:
                return self._check_result_to_dict(result)

        spec = specs_by_script[script_name]
        return {
            "script_name": script_name,
            "table_name": spec.table,
            "date_col": spec.date_col,
            "category": spec.category,
            "status": "not_configured",
            "today_count": None,
            "previous_count": None,
            "command": None,
            "message": "未找到检查结果",
        }

    def run_single_sync_background(self, script_name):
        self.ensure_whitelisted(script_name)
        task_id = self._start_task("single_sync", script_name, [script_name])
        thread = threading.Thread(target=self._run_single_sync_worker, args=(script_name, task_id), daemon=True)
        thread.start()
        return self.get_task_state()

    def run_full_sync_background(self):
        script_names = self.load_script_names()
        task_id = self._start_task("full_sync", None, script_names)
        thread = threading.Thread(target=self._run_full_sync_worker, args=(task_id,), daemon=True)
        thread.start()
        return self.get_task_state()

    def run_selected_sync_background(self, script_names):
        ordered_script_names = self.order_selected_script_names(script_names)
        task_id = self._start_task("selected_sync", None, ordered_script_names)
        thread = threading.Thread(target=self._run_selected_sync_worker, args=(ordered_script_names, task_id), daemon=True)
        thread.start()
        return self.get_task_state()

    def run_check_all_background(self, target_date):
        self.validate_sync_date(target_date)
        task_id = self._start_task("check_all", None)
        thread = threading.Thread(target=self._run_check_all_worker, args=(target_date, task_id), daemon=True)
        thread.start()
        return self.get_task_state()

    def run_check_one_background(self, script_name, target_date):
        self.ensure_whitelisted(script_name)
        self.validate_sync_date(target_date)
        task_id = self._start_task("check_one", script_name)
        thread = threading.Thread(target=self._run_check_one_worker, args=(script_name, target_date, task_id), daemon=True)
        thread.start()
        return self.get_task_state()

    def _run_single_sync_worker(self, script_name, task_id=None):
        task_id = task_id or self._current_task_id()
        self._set_thread_task(task_id)
        try:
            self._set_script_status(task_id, script_name, "running")
            return_code = self._run_script(script_name)
            if self._is_script_stopped(task_id, script_name):
                self._finish_task("stopped", return_code, task_id=task_id)
            elif return_code == 0:
                self._set_script_status(task_id, script_name, "completed")
                self._finish_task("completed", return_code, task_id=task_id)
            else:
                self._set_script_status(task_id, script_name, "failed")
                error = "{} exited with code {}".format(script_name, return_code)
                self._append_log("ERROR: {}".format(error))
                self._finish_task("failed", return_code, error, task_id=task_id)
        except Exception as exc:
            error = str(exc)
            self._set_script_status(task_id, script_name, "failed")
            self._append_log("ERROR: {}".format(error))
            self._finish_task("failed", 1, error, task_id=task_id)

    def _run_full_sync_worker(self, task_id=None):
        task_id = task_id or self._current_task_id()
        self._set_thread_task(task_id)
        try:
            for script_name in self.load_script_names():
                if self._is_script_stopped(task_id, script_name):
                    continue
                self._set_script_status(task_id, script_name, "running")
                return_code = self._run_script(script_name)
                if self._is_script_stopped(task_id, script_name):
                    continue
                if return_code != 0:
                    self._set_script_status(task_id, script_name, "failed")
                    error = "{} exited with code {}".format(script_name, return_code)
                    self._append_log("ERROR: {}".format(error))
                    self._finish_task("failed", return_code, error, task_id=task_id)
                    return
                self._set_script_status(task_id, script_name, "completed")
            self._finish_task("completed", 0, task_id=task_id)
        except Exception as exc:
            error = str(exc)
            self._append_log("ERROR: {}".format(error))
            self._finish_task("failed", 1, error, task_id=task_id)

    def _run_selected_sync_worker(self, script_names, task_id=None):
        task_id = task_id or self._current_task_id()
        self._set_thread_task(task_id)
        try:
            for script_name in self.order_selected_script_names(script_names):
                if self._is_script_stopped(task_id, script_name):
                    continue
                self._set_script_status(task_id, script_name, "running")
                return_code = self._run_script(script_name)
                if self._is_script_stopped(task_id, script_name):
                    continue
                if return_code != 0:
                    self._set_script_status(task_id, script_name, "failed")
                    error = "{} exited with code {}".format(script_name, return_code)
                    self._append_log("ERROR: {}".format(error))
                    self._finish_task("failed", return_code, error, task_id=task_id)
                    return
                self._set_script_status(task_id, script_name, "completed")
            self._finish_task("completed", 0, task_id=task_id)
        except Exception as exc:
            error = str(exc)
            self._append_log("ERROR: {}".format(error))
            self._finish_task("failed", 1, error, task_id=task_id)

    def _run_check_all_worker(self, target_date, task_id=None):
        task_id = task_id or self._current_task_id()
        self._set_thread_task(task_id)
        try:
            payload = self.check_all(target_date)
            with self._lock:
                task = self._get_task_locked(task_id) or self.state
                task.result = payload
                if self.state.task_id == task.task_id:
                    self.state = task
            self._append_log(self._format_check_payload(payload))
            self._finish_task("completed", 0, task_id=task_id)
        except Exception as exc:
            error = str(exc)
            self._append_log("ERROR: {}".format(error))
            self._finish_task("failed", 1, error, task_id=task_id)

    def _run_check_one_worker(self, script_name, target_date, task_id=None):
        task_id = task_id or self._current_task_id()
        self._set_thread_task(task_id)
        try:
            payload = self.check_one(script_name, target_date)
            with self._lock:
                task = self._get_task_locked(task_id) or self.state
                task.result = payload
                if self.state.task_id == task.task_id:
                    self.state = task
            self._append_log(self._format_check_payload(payload))
            self._finish_task("completed", 0, task_id=task_id)
        except Exception as exc:
            error = str(exc)
            self._append_log("ERROR: {}".format(error))
            self._finish_task("failed", 1, error, task_id=task_id)

    def _run_script(self, script_name):
        self.ensure_whitelisted(script_name)
        script_path = self._resolve_script_path(script_name)
        runtime_started_at = datetime.now()
        runtime_engine = self._safe_record_runtime_start(script_name, runtime_started_at)
        self._append_log("-" * 80)
        self._append_log("[RUN] {}".format(script_name))
        task_id = self._current_task_id()
        process = None
        try:
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
            if task_id:
                with self._lock:
                    task = self._get_task_locked(task_id)
                    if task is not None:
                        task.process = process
            if process.stdout is not None:
                for line in process.stdout:
                    self._append_log(line)
            return process.wait()
        finally:
            self._safe_record_runtime_finish(runtime_engine, script_name, runtime_started_at, datetime.now())
            if task_id and process is not None:
                with self._lock:
                    task = self._get_task_locked(task_id)
                    if task is not None and task.process is process:
                        task.process = None

    def _resolve_script_path(self, script_name):
        script_part = Path(script_name)
        if script_part.is_absolute() or ".." in script_part.parts:
            raise UnknownScriptError(script_name)

        sync_root = self.sync_dir.resolve()
        script_path = (self.sync_dir / script_part).resolve()
        try:
            script_path.relative_to(sync_root)
        except ValueError:
            raise UnknownScriptError(script_name)
        return script_path

    @staticmethod
    def _format_check_payload(payload):
        lines = []
        if "target_date" in payload:
            lines.append("[CHECK] {}".format(payload["target_date"]))

        if "results" in payload:
            message = payload.get("message")
            if message:
                lines.append(str(message))
            for result in payload.get("results") or []:
                lines.append(
                    "{status} | {script} | {table} | today={today} | prev={prev} | {message}".format(
                        status=result.get("status", ""),
                        script=result.get("script_name", ""),
                        table=result.get("table_name", ""),
                        today=SyncService._format_count(result.get("today_count")),
                        prev=SyncService._format_count(result.get("previous_count")),
                        message=result.get("message", ""),
                    )
                )
            unconfigured = payload.get("unconfigured") or []
            if unconfigured:
                lines.append("未配置校验")
                lines.extend(str(script_name) for script_name in unconfigured)
            return "\n".join(lines)

        lines.append(
            "{status} | {script} | {table} | today={today} | prev={prev} | {message}".format(
                status=payload.get("status", ""),
                script=payload.get("script_name", ""),
                table=payload.get("table_name", ""),
                today=SyncService._format_count(payload.get("today_count")),
                prev=SyncService._format_count(payload.get("previous_count")),
                message=payload.get("message", ""),
            )
        )
        return "\n".join(lines)

    @staticmethod
    def _check_result_to_dict(result):
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

    @staticmethod
    def validate_sync_date(value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y%m%d")
        except ValueError:
            raise InvalidSyncDateError("同步日期必须是有效 YYYYMMDD 日期")
        if parsed.strftime("%Y%m%d") != value:
            raise InvalidSyncDateError("同步日期必须是有效 YYYYMMDD 日期")
        return parsed.strftime("%Y-%m-%d")

    def get_engine(self):
        db_url = os.environ.get("DATABASE_URL", "")
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return create_engine(db_url)

    def ensure_sync_status_table(self, engine=None):
        engine = engine or self.get_engine()
        with engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
            conn.execute(text(SYNC_STATUS_SQL))
            conn.execute(text(f"ALTER TABLE {SCHEMA}.sync_status ADD COLUMN IF NOT EXISTS last_start_at TIMESTAMP"))
            conn.execute(text(f"ALTER TABLE {SCHEMA}.sync_status ADD COLUMN IF NOT EXISTS last_end_at TIMESTAMP"))

    def record_script_runtime_start(self, engine, script_name, started_at):
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    UPDATE {SCHEMA}.sync_status
                    SET last_start_at = :started_at,
                        last_end_at = NULL
                    WHERE script_name = :script_name
                    """
                ),
                {"script_name": script_name, "started_at": started_at},
            )

    def record_script_runtime_finish(self, engine, script_name, started_at, ended_at):
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    UPDATE {SCHEMA}.sync_status
                    SET last_start_at = :started_at,
                        last_end_at = :ended_at
                    WHERE script_name = :script_name
                    """
                ),
                {
                    "script_name": script_name,
                    "started_at": started_at,
                    "ended_at": ended_at,
                },
            )

    def _safe_record_runtime_start(self, script_name, started_at):
        try:
            engine = self.get_engine()
            self.ensure_sync_status_table(engine)
            self.record_script_runtime_start(engine, script_name, started_at)
            return engine
        except Exception as exc:
            self._append_log("[WARN] 记录开始耗时失败: {}".format(exc))
            return None

    def _safe_record_runtime_finish(self, engine, script_name, started_at, ended_at):
        try:
            engine = engine or self.get_engine()
            self.ensure_sync_status_table(engine)
            self.record_script_runtime_finish(engine, script_name, started_at, ended_at)
        except Exception as exc:
            self._append_log("[WARN] 记录结束耗时失败: {}".format(exc))

    def load_sync_status_map(self):
        self.ensure_sync_status_table()
        query = text(
            f"""
            SELECT script_name, table_name, sync_date, status, updated_at, last_start_at, last_end_at
            FROM {SCHEMA}.sync_status
            """
        )
        with self.get_engine().connect() as conn:
            rows = conn.execute(query)
            return {row.script_name: self._format_status_row(row) for row in rows}

    def load_job_rows(self):
        jobs = self.load_jobs()
        db_error = None
        try:
            status_map = self.load_sync_status_map()
        except Exception as exc:
            status_map = {}
            db_error = str(exc)

        rows = []
        for job in jobs:
            status = status_map.get(job["script_name"])
            row = dict(job)
            if status is None:
                row["status"] = "unknown" if db_error else "not_synced"
                row["sync_date"] = ""
                row["updated_at"] = ""
                row["last_start_at"] = ""
                row["last_end_at"] = ""
            else:
                row.update(status)
            row["runtime"] = "-"
            rows.append(row)
        return {"rows": rows, "db_error": db_error}

    def update_sync_date(self, script_name, sync_date):
        self.ensure_whitelisted(script_name)
        formatted_date = self.validate_sync_date(sync_date)
        table_name = Path(script_name).stem
        self.ensure_sync_status_table()
        query = text(
            f"""
            INSERT INTO {SCHEMA}.sync_status (script_name, table_name, sync_date, status, updated_at)
            VALUES (:script_name, :table_name, :sync_date, 'ing', CURRENT_TIMESTAMP)
            ON CONFLICT (script_name)
            DO UPDATE SET
                table_name = EXCLUDED.table_name,
                sync_date = EXCLUDED.sync_date,
                status = EXCLUDED.status,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        with self.get_engine().begin() as conn:
            conn.execute(
                query,
                {
                    "script_name": script_name,
                    "table_name": table_name,
                    "sync_date": formatted_date,
                },
            )
        return {
            "script_name": script_name,
            "table_name": table_name,
            "sync_date": formatted_date,
            "status": "ing",
        }

    @staticmethod
    def _format_count(value):
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _format_status_row(row):
        return {
            "script_name": row.script_name,
            "table_name": row.table_name,
            "sync_date": SyncService._format_date(row.sync_date),
            "status": row.status,
            "updated_at": SyncService._format_datetime(row.updated_at),
            "last_start_at": SyncService._format_datetime(getattr(row, "last_start_at", None)),
            "last_end_at": SyncService._format_datetime(getattr(row, "last_end_at", None)),
        }

    @staticmethod
    def _format_date(value):
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return str(value)

    @staticmethod
    def _format_datetime(value):
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

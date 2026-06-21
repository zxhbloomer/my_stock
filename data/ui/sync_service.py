import importlib.util
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYNC_DIR = PROJECT_ROOT / "data" / "手动执行" / "20260425"
_IMPORT_LOCK = threading.Lock()
SCHEMA = "tushare_v2"
LIMITED_DAILY_WINDOWS = {
    "078_slb_sec_detail.py": ("20190722", "20240710"),
}
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
    script_processes: dict = field(default_factory=dict)


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

    def load_script_default_starts(self):
        defaults = {}
        for script_name in self.load_script_names():
            script_path = self._resolve_script_path(script_name)
            try:
                source = script_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                source = script_path.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r'DEFAULT_START\s*=\s*["\'](\d{8})["\']', source)
            if match:
                defaults[script_name] = match.group(1)
        return defaults

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
                process = task.script_processes.get(script_name) or task.process
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

    def smart_incremental_check(self, mode):
        if mode not in {"all", "today"}:
            raise InvalidSyncDateError("智能增量模式必须是 all 或 today")

        module = self._check_module()
        target_date = datetime.now().strftime("%Y%m%d")
        base_start = "20100101"
        specs_by_script = {spec.script: spec for spec in module.TABLE_SPECS}
        script_names = self.load_script_names()
        script_defaults = self.load_script_default_starts()
        issues = []
        unconfigured = []

        with self.get_engine().connect() as conn:
            all_tables = module.get_all_tables(conn, SCHEMA)
            if mode == "today":
                if not module.is_open_trade_date(conn, SCHEMA, target_date):
                    return {
                        "mode": mode,
                        "start_date": target_date,
                        "end_date": target_date,
                        "issues": [],
                        "unconfigured": [],
                        "message": "{} 不是 SSE 交易日，跳过今日日期检查".format(target_date),
                    }
                expected_dates_by_start = {target_date: [target_date]}
            else:
                expected_dates_by_start = {}

            for script_name in script_names:
                spec = specs_by_script.get(script_name)
                if spec is None:
                    unconfigured.append({
                        "script_name": script_name,
                        "table_name": Path(script_name).stem,
                        "category": "not_configured",
                        "status": "not_configured",
                        "message": "脚本未配置检查规则",
                        "syncable": False,
                    })
                    continue

                check_end_date = self._effective_check_end_date(conn, module, spec, target_date)
                start_date = check_end_date if mode == "today" else self._effective_full_start(
                    base_start,
                    script_defaults.get(script_name),
                )
                issue = self._scan_smart_issue_for_spec(
                    conn=conn,
                    module=module,
                    spec=spec,
                    all_tables=all_tables,
                    mode=mode,
                    start_date=start_date,
                    end_date=check_end_date,
                    expected_dates_by_start=expected_dates_by_start,
                )
                if issue:
                    issues.append(issue)

        return {
            "mode": mode,
            "start_date": target_date if mode == "today" else base_start,
            "end_date": target_date,
            "issues": issues,
            "unconfigured": unconfigured,
            "message": "发现 {} 个问题脚本，{} 个未配置脚本".format(len(issues), len(unconfigured)),
        }

    def _effective_check_end_date(self, conn, module, spec, target_date):
        if spec.script != "061_cyq_perf.py":
            return target_date
        if datetime.now().hour >= 19:
            return target_date
        previous_date = module.get_previous_trade_date(conn, SCHEMA, target_date)
        return previous_date or target_date

    def _scan_smart_issue_for_spec(self, conn, module, spec, all_tables, mode, start_date, end_date, expected_dates_by_start):
        table_exists = spec.table in all_tables
        if not table_exists:
            return self._build_smart_issue(
                spec=spec,
                status="missing_table",
                start_date=start_date,
                end_date=end_date,
                missing_dates=[],
                low_count_dates=[],
                today_count=None,
                previous_count=None,
                syncable=True,
                message="表不存在",
            )

        if spec.category == "static":
            count = module.count_table(conn, SCHEMA, spec.table)
            if count == 0:
                return self._build_smart_issue(
                    spec=spec,
                    status="empty_static",
                    start_date=start_date,
                    end_date=end_date,
                    missing_dates=[],
                    low_count_dates=[],
                    today_count=count,
                    previous_count=None,
                    syncable=True,
                    message="静态表为空",
                )
            return None

        if spec.category == "periodic":
            if mode == "today":
                return self._build_smart_issue(
                    spec=spec,
                    status="skipped_periodic",
                    start_date=start_date,
                    end_date=end_date,
                    missing_dates=[],
                    low_count_dates=[],
                    today_count=None,
                    previous_count=None,
                    syncable=False,
                    message="周/月频表不按今日逐日检查",
                )
            return self._scan_periodic_issue_for_spec(
                conn=conn,
                spec=spec,
                start_date=start_date,
                end_date=end_date,
            )

        if spec.category == "stopped":
            window = LIMITED_DAILY_WINDOWS.get(spec.script)
            if not window:
                return self._build_smart_issue(
                    spec=spec,
                    status="skipped_stopped",
                    start_date=start_date,
                    end_date=end_date,
                    missing_dates=[],
                    low_count_dates=[],
                    today_count=None,
                    previous_count=None,
                    syncable=False,
                    message="接口已停止更新，缺少有效检查窗口配置",
                )
            window_start, window_end = window
            if mode == "today":
                return self._build_smart_issue(
                    spec=spec,
                    status="skipped_stopped",
                    start_date=start_date,
                    end_date=end_date,
                    missing_dates=[],
                    low_count_dates=[],
                    today_count=None,
                    previous_count=None,
                    syncable=False,
                    message="接口已停止更新，仅检查 {}~{} 历史窗口".format(window_start, window_end),
                )
            scan_start_date = max(start_date, window_start)
            scan_end_date = min(end_date, window_end)
            if scan_start_date > scan_end_date:
                return None
            return self._scan_required_daily_issue_for_spec(
                conn=conn,
                module=module,
                spec=spec,
                start_date=scan_start_date,
                end_date=scan_end_date,
                expected_dates_by_start=expected_dates_by_start,
                message_prefix="接口有效历史窗口 {}~{}".format(window_start, window_end),
                check_low_count=False,
            )

        if not spec.date_col:
            return None

        if spec.category == "report_period_sparse":
            period_start, period_end = self._recent_report_period_window(end_date)
            return self._build_smart_issue(
                spec=spec,
                status="report_period_refresh",
                start_date=period_start,
                end_date=period_end,
                missing_dates=[],
                low_count_dates=[],
                today_count=None,
                previous_count=None,
                syncable=True,
                message="报告期滚动刷新",
            )

        if spec.category == "holiday_refresh":
            if module.is_open_trade_date(conn, SCHEMA, end_date):
                return None
            return self._build_smart_issue(
                spec=spec,
                status="holiday_refresh",
                start_date=end_date,
                end_date=end_date,
                missing_dates=[],
                low_count_dates=[],
                today_count=None,
                previous_count=None,
                syncable=True,
                message="非交易日建议刷新，脚本内部自动选择公告窗口",
            )

        if spec.category == "sparse":
            if mode == "all":
                return self._build_smart_issue(
                    spec=spec,
                    status="skipped_sparse",
                    start_date=start_date,
                    end_date=end_date,
                    missing_dates=[],
                    low_count_dates=[],
                    today_count=None,
                    previous_count=None,
                    syncable=False,
                    message="事件类表不做全历史逐日强校验，仅支持今天日期提示",
                )
            if mode == "today":
                today_count = module.count_date(conn, SCHEMA, spec.table, spec.date_col, end_date)
                if today_count == 0:
                    return self._build_smart_issue(
                        spec=spec,
                        status="sparse_empty",
                        start_date=end_date,
                        end_date=end_date,
                        missing_dates=[end_date],
                        low_count_dates=[],
                        today_count=today_count,
                        previous_count=None,
                        syncable=False,
                        message="事件类表今日为空，仅提示",
                    )
            return None

        if spec.script == "062_cyq_chips.py":
            return self._scan_cyq_chips_issue_for_spec(
                conn=conn,
                module=module,
                spec=spec,
                start_date=start_date,
                end_date=end_date,
                expected_dates_by_start=expected_dates_by_start,
            )

        if spec.script == "066_hk_hold.py":
            return self._scan_hk_hold_issue_for_spec(
                conn=conn,
                module=module,
                spec=spec,
                start_date=start_date,
                end_date=end_date,
                expected_dates_by_start=expected_dates_by_start,
            )

        return self._scan_required_daily_issue_for_spec(
            conn=conn,
            module=module,
            spec=spec,
            start_date=start_date,
            end_date=end_date,
            expected_dates_by_start=expected_dates_by_start,
        )

    def _scan_required_daily_issue_for_spec(
        self,
        conn,
        module,
        spec,
        start_date,
        end_date,
        expected_dates_by_start,
        message_prefix=None,
        check_low_count=True,
    ):
        expected_dates = self._get_expected_trade_dates(conn, start_date, end_date, expected_dates_by_start)
        if not expected_dates:
            return self._build_smart_issue(
                spec=spec,
                status="no_trade_dates",
                start_date=start_date,
                end_date=end_date,
                missing_dates=[],
                low_count_dates=[],
                today_count=None,
                previous_count=None,
                syncable=False,
                message="扫描区间内没有 SSE 交易日",
            )

        counts = self._count_dates(conn, spec.table, spec.date_col, start_date, end_date)
        missing_dates = []
        low_count_dates = []
        previous_count = None
        for trade_date in expected_dates:
            count = counts.get(trade_date, 0)
            if count == 0:
                missing_dates.append(trade_date)
            elif check_low_count and previous_count and count < previous_count * module.LOW_COUNT_RATIO:
                low_count_dates.append(trade_date)
            if count > 0:
                previous_count = count

        if missing_dates or low_count_dates:
            status = "missing" if missing_dates else "low_count"
            parts = []
            if message_prefix:
                parts.append(message_prefix)
            if missing_dates:
                parts.append("缺失 {} 个交易日".format(len(missing_dates)))
            if low_count_dates:
                parts.append("可疑低行数 {} 个交易日".format(len(low_count_dates)))
            today_count = counts.get(end_date)
            return self._build_smart_issue(
                spec=spec,
                status=status,
                start_date=start_date,
                end_date=end_date,
                missing_dates=missing_dates,
                low_count_dates=low_count_dates,
                today_count=today_count,
                previous_count=previous_count,
                syncable=True,
                message="；".join(parts),
                expected_dates=expected_dates,
            )
        return None

    def _scan_cyq_chips_issue_for_spec(self, conn, module, spec, start_date, end_date, expected_dates_by_start):
        expected_dates = self._get_expected_trade_dates(conn, start_date, end_date, expected_dates_by_start)
        if not expected_dates:
            return self._build_smart_issue(
                spec=spec,
                status="no_trade_dates",
                start_date=start_date,
                end_date=end_date,
                missing_dates=[],
                low_count_dates=[],
                today_count=None,
                previous_count=None,
                syncable=False,
                message="扫描区间内没有 SSE 交易日",
            )

        row_counts = self._count_dates(conn, spec.table, spec.date_col, start_date, end_date)
        stock_counts = self._count_distinct_by_date(
            conn, spec.table, spec.date_col, "ts_code", start_date, end_date
        )
        missing_dates = []
        low_count_dates = []
        previous_positive = None

        for index, trade_date in enumerate(expected_dates):
            row_count = row_counts.get(trade_date, 0)
            stock_count = stock_counts.get(trade_date, 0)
            if row_count == 0:
                missing_dates.append(trade_date)
                continue

            next_positive = None
            for next_date in expected_dates[index + 1:]:
                value = stock_counts.get(next_date, 0)
                if value > 0:
                    next_positive = value
                    break

            low_by_previous = previous_positive and stock_count < previous_positive * module.LOW_COUNT_RATIO
            low_by_next = next_positive and stock_count < next_positive * module.LOW_COUNT_RATIO
            if low_by_previous or low_by_next:
                low_count_dates.append(trade_date)
            if stock_count > 0:
                previous_positive = stock_count

        if missing_dates or low_count_dates:
            status = "missing" if missing_dates else "low_count"
            parts = []
            if missing_dates:
                parts.append("缺失 {} 个交易日".format(len(missing_dates)))
            if low_count_dates:
                parts.append("覆盖股票数可疑偏低 {} 个交易日".format(len(low_count_dates)))
            return self._build_smart_issue(
                spec=spec,
                status=status,
                start_date=start_date,
                end_date=end_date,
                missing_dates=missing_dates,
                low_count_dates=low_count_dates,
                today_count=row_counts.get(end_date),
                previous_count=previous_positive,
                syncable=True,
                message="；".join(parts),
                expected_dates=expected_dates,
            )
        return None

    def _scan_hk_hold_issue_for_spec(self, conn, module, spec, start_date, end_date, expected_dates_by_start):
        expected_dates = self._get_expected_trade_dates(conn, start_date, end_date, expected_dates_by_start)
        if not expected_dates:
            return self._build_smart_issue(
                spec=spec,
                status="no_trade_dates",
                start_date=start_date,
                end_date=end_date,
                missing_dates=[],
                low_count_dates=[],
                today_count=None,
                previous_count=None,
                syncable=False,
                message="扫描区间内没有 SSE 交易日",
            )

        row_counts = self._count_dates(conn, spec.table, spec.date_col, start_date, end_date)
        exchanges_by_date = self._count_values_by_date(
            conn, spec.table, spec.date_col, "exchange", start_date, end_date
        )
        exchange_counts = self._count_date_value_rows(
            conn, spec.table, spec.date_col, "exchange", start_date, end_date
        )
        low_count_dates = []
        previous_exchange_counts = {}

        for trade_date in expected_dates:
            count = row_counts.get(trade_date, 0)
            # hk_hold 历史上存在真实空交易日，例如 20160701；不能按SSE交易日强制补齐。
            if count == 0:
                continue

            exchanges = exchanges_by_date.get(trade_date, set())
            if trade_date < "20161205":
                required_exchanges = {"SH"}
            elif trade_date <= "20240819":
                required_exchanges = {"SH", "SZ"}
            else:
                # 2024-08-20起官方说明停止发布日度北向持股，实测接口仍返回HK南向持股。
                required_exchanges = {"HK"}
            if not required_exchanges.issubset(exchanges):
                low_count_dates.append(trade_date)
            else:
                for exchange in required_exchanges:
                    exchange_count = exchange_counts.get((trade_date, exchange), 0)
                    previous_count = previous_exchange_counts.get(exchange)
                    if previous_count and exchange_count < previous_count * module.LOW_COUNT_RATIO:
                        low_count_dates.append(trade_date)
                        break

            for exchange in exchanges:
                exchange_count = exchange_counts.get((trade_date, exchange), 0)
                if exchange_count > 0:
                    previous_exchange_counts[exchange] = exchange_count

        if low_count_dates:
            parts = []
            parts.append("交易所覆盖或单市场行数可疑 {} 个交易日".format(len(set(low_count_dates))))
            return self._build_smart_issue(
                spec=spec,
                status="low_count",
                start_date=start_date,
                end_date=end_date,
                missing_dates=[],
                low_count_dates=sorted(set(low_count_dates)),
                today_count=row_counts.get(end_date),
                previous_count=None,
                syncable=True,
                message="；".join(parts),
                expected_dates=expected_dates,
            )
        return None

    def _scan_periodic_issue_for_spec(self, conn, spec, start_date, end_date):
        period_kind = self._period_kind_for_script(spec.script)
        if period_kind is None:
            return self._build_smart_issue(
                spec=spec,
                status="skipped_periodic",
                start_date=start_date,
                end_date=end_date,
                missing_dates=[],
                low_count_dates=[],
                today_count=None,
                previous_count=None,
                syncable=False,
                message="周/月频表未配置周期类型",
            )

        if period_kind in {"week", "month"}:
            expected_dates = self._get_periodic_expected_dates(conn, start_date, end_date, period_kind)
            if not expected_dates:
                return None
            counts = self._count_dates(conn, spec.table, spec.date_col, start_date, end_date)
            missing_dates = [trade_date for trade_date in expected_dates if counts.get(trade_date, 0) == 0]
            if not missing_dates:
                return None
            return self._build_smart_issue(
                spec=spec,
                status="missing",
                start_date=start_date,
                end_date=end_date,
                missing_dates=missing_dates,
                low_count_dates=[],
                today_count=None,
                previous_count=None,
                syncable=True,
                message="缺失 {} 个周期结束日".format(len(missing_dates)),
                expected_dates=expected_dates,
            )

        if period_kind == "week_month_reference":
            return None

        week_dates = self._get_periodic_expected_dates(conn, start_date, end_date, "week")
        month_dates = self._get_periodic_expected_dates(conn, start_date, end_date, "month")
        if not week_dates and not month_dates:
            return None
        counts = self._count_date_freqs(conn, spec.table, spec.date_col, start_date, end_date)
        missing_dates = []
        expected_dates = sorted(set(week_dates + month_dates))
        for trade_date in week_dates:
            if counts.get((trade_date, "week"), 0) == 0:
                missing_dates.append(trade_date)
        for trade_date in month_dates:
            if counts.get((trade_date, "month"), 0) == 0:
                missing_dates.append(trade_date)
        if not missing_dates:
            return None
        return self._build_smart_issue(
            spec=spec,
            status="missing",
            start_date=start_date,
            end_date=end_date,
            missing_dates=missing_dates,
            low_count_dates=[],
            today_count=None,
            previous_count=None,
            syncable=True,
            message="缺失 {} 个周/月周期".format(len(missing_dates)),
            expected_dates=expected_dates,
        )

    @staticmethod
    def _period_kind_for_script(script_name):
        if script_name == "018_weekly.py":
            return "week"
        if script_name == "019_monthly.py":
            return "month"
        if script_name in {"021_stk_weekly_monthly.py", "022_stk_week_month_adj.py"}:
            return "week_month_reference"
        return None

    def _get_expected_trade_dates(self, conn, start_date, end_date, cache):
        cache_key = "{}:{}".format(start_date, end_date)
        if cache_key in cache:
            return cache[cache_key]
        rows = conn.execute(text(f"""
            SELECT cal_date
            FROM {SCHEMA}."003_trade_cal"
            WHERE exchange='SSE'
              AND is_open=1
              AND cal_date BETWEEN :start_date AND :end_date
            ORDER BY cal_date
        """), {"start_date": start_date, "end_date": end_date}).fetchall()
        dates = [self._format_compact_date(row[0]) for row in rows if row and row[0]]
        cache[cache_key] = dates
        return dates

    def _get_periodic_expected_dates(self, conn, start_date, end_date, period):
        extended_end = (datetime.strptime(end_date, "%Y%m%d") + timedelta(days=40)).strftime("%Y%m%d")
        rows = conn.execute(text(f"""
            SELECT cal_date
            FROM {SCHEMA}."003_trade_cal"
            WHERE exchange='SSE'
              AND is_open=1
              AND cal_date BETWEEN :start_date AND :end_date
            ORDER BY cal_date
        """), {"start_date": start_date, "end_date": extended_end}).fetchall()
        dates = [self._format_compact_date(row[0]) for row in rows if row and row[0]]
        return self._select_period_end_dates(dates, end_date, period)

    def _count_dates(self, conn, table, date_col, start_date, end_date):
        rows = conn.execute(text(
            f"""
            SELECT "{date_col}", COUNT(*)
            FROM {SCHEMA}."{table}"
            WHERE "{date_col}" BETWEEN :start_date AND :end_date
            GROUP BY "{date_col}"
            """
        ), {"start_date": start_date, "end_date": end_date}).fetchall()
        return {self._format_compact_date(row[0]): int(row[1]) for row in rows if row and row[0]}

    def _count_distinct_by_date(self, conn, table, date_col, value_col, start_date, end_date):
        rows = conn.execute(text(
            f"""
            SELECT "{date_col}", COUNT(DISTINCT "{value_col}")
            FROM {SCHEMA}."{table}"
            WHERE "{date_col}" BETWEEN :start_date AND :end_date
            GROUP BY "{date_col}"
            """
        ), {"start_date": start_date, "end_date": end_date}).fetchall()
        return {self._format_compact_date(row[0]): int(row[1]) for row in rows if row and row[0]}

    def _count_date_value_rows(self, conn, table, date_col, value_col, start_date, end_date):
        rows = conn.execute(text(
            f"""
            SELECT "{date_col}", "{value_col}", COUNT(*)
            FROM {SCHEMA}."{table}"
            WHERE "{date_col}" BETWEEN :start_date AND :end_date
            GROUP BY "{date_col}", "{value_col}"
            """
        ), {"start_date": start_date, "end_date": end_date}).fetchall()
        return {
            (self._format_compact_date(row[0]), str(row[1])): int(row[2])
            for row in rows
            if row and row[0] and row[1] is not None
        }

    def _count_values_by_date(self, conn, table, date_col, value_col, start_date, end_date):
        rows = conn.execute(text(
            f"""
            SELECT "{date_col}", "{value_col}"
            FROM {SCHEMA}."{table}"
            WHERE "{date_col}" BETWEEN :start_date AND :end_date
            GROUP BY "{date_col}", "{value_col}"
            """
        ), {"start_date": start_date, "end_date": end_date}).fetchall()
        values_by_date = {}
        for row in rows:
            if not row or not row[0] or row[1] is None:
                continue
            values_by_date.setdefault(self._format_compact_date(row[0]), set()).add(str(row[1]))
        return values_by_date

    def _count_date_freqs(self, conn, table, date_col, start_date, end_date):
        rows = conn.execute(text(
            f"""
            SELECT "{date_col}", freq, COUNT(*)
            FROM {SCHEMA}."{table}"
            WHERE "{date_col}" BETWEEN :start_date AND :end_date
            GROUP BY "{date_col}", freq
            """
        ), {"start_date": start_date, "end_date": end_date}).fetchall()
        return {
            (self._format_compact_date(row[0]), str(row[1])): int(row[2])
            for row in rows
            if row and row[0] and row[1]
        }

    @staticmethod
    def _effective_full_start(base_start, script_default_start):
        if not script_default_start:
            return base_start
        return max(base_start, script_default_start)

    @staticmethod
    def _recent_report_period_window(end_date, quarters=6):
        current = datetime.strptime(str(end_date), "%Y%m%d")
        quarter_month = ((current.month - 1) // 3) * 3 + 3
        quarter_end = datetime(current.year, quarter_month, 1)
        if quarter_month == 3:
            quarter_end = datetime(current.year, 3, 31)
        elif quarter_month == 6:
            quarter_end = datetime(current.year, 6, 30)
        elif quarter_month == 9:
            quarter_end = datetime(current.year, 9, 30)
        else:
            quarter_end = datetime(current.year, 12, 31)

        if current < quarter_end:
            if quarter_month == 3:
                quarter_end = datetime(current.year - 1, 12, 31)
            elif quarter_month == 6:
                quarter_end = datetime(current.year, 3, 31)
            elif quarter_month == 9:
                quarter_end = datetime(current.year, 6, 30)
            else:
                quarter_end = datetime(current.year, 9, 30)

        periods = []
        year = quarter_end.year
        month = quarter_end.month
        for _ in range(max(1, quarters)):
            day = 31 if month in {3, 12} else 30
            periods.append(datetime(year, month, day))
            month -= 3
            if month <= 0:
                month += 12
                year -= 1

        return periods[-1].strftime("%Y%m%d"), periods[0].strftime("%Y%m%d")

    @staticmethod
    def _build_smart_issue(
        spec,
        status,
        start_date,
        end_date,
        missing_dates,
        low_count_dates,
        today_count,
        previous_count,
        syncable,
        message,
        expected_dates=None,
    ):
        missing_dates = list(missing_dates or [])
        low_count_dates = list(low_count_dates or [])
        problem_dates = sorted(set(missing_dates + low_count_dates))
        run_ranges = SyncService._build_problem_ranges(problem_dates, expected_dates)
        if problem_dates:
            run_start = run_ranges[0]["start"]
            run_end = run_ranges[-1]["end"]
            date_range = "{} 个问题日期，{} 段".format(len(problem_dates), len(run_ranges))
        elif spec.date_col:
            run_start = start_date
            run_end = end_date
            date_range = "{} ~ {}".format(start_date, end_date)
            run_ranges = [{"start": run_start, "end": run_end}]
        else:
            run_start = ""
            run_end = ""
            date_range = "-"

        if spec.script == "043_fina_audit.py":
            command = "python -X utf8 {}".format(spec.script)
        elif spec.date_col:
            commands = [
                "python -X utf8 {} --start {} --end {}".format(spec.script, item["start"], item["end"])
                for item in run_ranges
            ]
            command = "; ".join(commands)
        else:
            command = "python -X utf8 {}".format(spec.script)

        return {
            "script_name": spec.script,
            "table_name": spec.table,
            "date_col": spec.date_col,
            "category": spec.category,
            "status": status,
            "start_date": start_date,
            "end_date": end_date,
            "run_start": run_start,
            "run_end": run_end,
            "run_ranges": run_ranges,
            "date_range": date_range,
            "problem_date_summary": SyncService._format_range_summary(run_ranges),
            "missing_dates": missing_dates[:200],
            "low_count_dates": low_count_dates[:200],
            "missing_count": len(missing_dates),
            "low_count_count": len(low_count_dates),
            "today_count": today_count,
            "previous_count": previous_count,
            "syncable": bool(syncable),
            "command": command,
            "message": message,
        }

    @staticmethod
    def _build_problem_ranges(problem_dates, expected_dates=None):
        dates = sorted(set(problem_dates or []))
        if not dates:
            return []

        expected_order = {date: index for index, date in enumerate(expected_dates or [])}
        ranges = []
        current_start = dates[0]
        current_end = dates[0]

        for date in dates[1:]:
            previous_index = expected_order.get(current_end)
            current_index = expected_order.get(date)
            if previous_index is not None and current_index == previous_index + 1:
                current_end = date
            else:
                ranges.append({"start": current_start, "end": current_end})
                current_start = date
                current_end = date
        ranges.append({"start": current_start, "end": current_end})
        return ranges

    @staticmethod
    def _format_range_summary(ranges):
        parts = []
        for item in ranges or []:
            start = item["start"]
            end = item["end"]
            parts.append(start if start == end else "{}~{}".format(start, end))
        return ", ".join(parts)

    @staticmethod
    def _select_period_end_dates(trade_dates, end_date, period):
        if period not in {"week", "month"}:
            raise ValueError("period must be week or month")
        end_date = str(end_date)
        rows = []
        for value in trade_dates or []:
            compact = SyncService._format_compact_date(value)
            if len(compact) != 8:
                continue
            dt = datetime.strptime(compact, "%Y%m%d")
            if period == "week":
                iso = dt.isocalendar()
                key = (iso.year, iso.week)
            else:
                key = (dt.year, dt.month)
            rows.append((compact, key))

        max_by_period = {}
        for compact, key in rows:
            if key not in max_by_period or compact > max_by_period[key]:
                max_by_period[key] = compact

        selected = [
            compact
            for compact, key in rows
            if compact <= end_date and max_by_period.get(key) == compact
        ]
        return sorted(set(selected))

    @staticmethod
    def _format_compact_date(value):
        if hasattr(value, "strftime"):
            return value.strftime("%Y%m%d")
        return str(value).replace("-", "")[:8]

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

    def run_smart_incremental_sync_background(self, items):
        sync_items = self._normalize_smart_sync_items(items)
        script_names = [item["script_name"] for item in sync_items]
        task_id = self._start_task("smart_incremental_sync", None, script_names)
        thread = threading.Thread(target=self._run_smart_incremental_sync_worker, args=(sync_items, task_id), daemon=True)
        thread.start()
        return self.get_task_state()

    def _normalize_smart_sync_items(self, items):
        if not items:
            raise UnknownScriptError("未选择需要同步的脚本")
        normalized = []
        seen = set()
        specs = self.load_check_specs()
        for item in items:
            script_name = str(item.get("script_name", "")).strip()
            if not script_name or script_name in seen:
                continue
            self.ensure_whitelisted(script_name)
            spec = specs.get(script_name)
            if spec is None:
                raise UnknownScriptError("{} 未配置智能增量检查规则".format(script_name))
            args = []
            arg_sets = []
            run_start = str(item.get("run_start") or "").strip()
            run_end = str(item.get("run_end") or "").strip()
            if spec.script == "043_fina_audit.py":
                arg_sets.append([])
            elif spec.date_col:
                run_ranges = item.get("run_ranges") or []
                if run_ranges:
                    for run_range in run_ranges:
                        range_start = str(run_range.get("start") or "").strip()
                        range_end = str(run_range.get("end") or "").strip()
                        if not range_start or not range_end:
                            raise InvalidSyncDateError("{} 缺少同步起止日期".format(script_name))
                        self.validate_sync_date(range_start)
                        self.validate_sync_date(range_end)
                        arg_sets.append(["--start", range_start, "--end", range_end])
                else:
                    if not run_start or not run_end:
                        raise InvalidSyncDateError("{} 缺少同步起止日期".format(script_name))
                    self.validate_sync_date(run_start)
                    self.validate_sync_date(run_end)
                    arg_sets.append(["--start", run_start, "--end", run_end])
            else:
                arg_sets.append([])
            normalized.append({
                "script_name": script_name,
                "arg_sets": arg_sets,
            })
            seen.add(script_name)
        if not normalized:
            raise UnknownScriptError("未选择需要同步的脚本")
        return normalized

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

    def _run_smart_incremental_sync_worker(self, items, task_id=None):
        task_id = task_id or self._current_task_id()
        self._set_thread_task(task_id)
        failures = []
        threads = []
        result_lock = threading.Lock()

        def run_item(item):
            self._set_thread_task(task_id)
            script_name = item["script_name"]
            try:
                if self._is_script_stopped(task_id, script_name):
                    return
                self._set_script_status(task_id, script_name, "running")
                arg_sets = item.get("arg_sets") or [item.get("args") or []]
                for args in arg_sets:
                    return_code = self._run_script(script_name, args)
                    if self._is_script_stopped(task_id, script_name):
                        return
                    if return_code != 0:
                        self._set_script_status(task_id, script_name, "failed")
                        error = "{} exited with code {}".format(script_name, return_code)
                        self._append_log("ERROR: {}".format(error))
                        with result_lock:
                            failures.append(error)
                        return
                self._set_script_status(task_id, script_name, "completed")
            except Exception as exc:
                error = "{} failed: {}".format(script_name, exc)
                self._set_script_status(task_id, script_name, "failed")
                self._append_log("ERROR: {}".format(error))
                with result_lock:
                    failures.append(error)
            finally:
                self._release_script_lock(task_id, script_name)

        try:
            for item in items:
                thread = threading.Thread(target=run_item, args=(item,), daemon=True)
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join()
            if failures:
                self._finish_task("failed", 1, "; ".join(failures), task_id=task_id)
            else:
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

    def _run_script(self, script_name, args=None):
        args = list(args or [])
        self.ensure_whitelisted(script_name)
        script_path = self._resolve_script_path(script_name)
        runtime_started_at = datetime.now()
        runtime_engine = self._safe_record_runtime_start(script_name, runtime_started_at)
        self._append_log("-" * 80)
        command = [sys.executable, "-X", "utf8", str(script_path)] + args
        display_command = "python -X utf8 {}{}".format(
            script_name,
            "" if not args else " " + " ".join(args),
        )
        self._append_log("[RUN] {}".format(display_command))
        task_id = self._current_task_id()
        process = None
        try:
            process = subprocess.Popen(
                command,
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
                        task.script_processes[script_name] = process
            if process.stdout is not None:
                for line in process.stdout:
                    self._append_log("[{}] {}".format(script_name, line.rstrip()))
            return process.wait()
        finally:
            self._safe_record_runtime_finish(runtime_engine, script_name, runtime_started_at, datetime.now())
            if task_id and process is not None:
                with self._lock:
                    task = self._get_task_locked(task_id)
                    if task is not None and task.process is process:
                        task.process = None
                    if task is not None and task.script_processes.get(script_name) is process:
                        task.script_processes.pop(script_name, None)

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

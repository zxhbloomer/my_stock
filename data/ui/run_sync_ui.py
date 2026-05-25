from pathlib import Path
import sys
import threading
from typing import List
import webbrowser

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
DOMAIN_ERRORS = (TaskBusyError, UnknownScriptError, InvalidSyncDateError)


class ScriptRequest(BaseModel):
    script_name: str


class SelectedScriptsRequest(BaseModel):
    script_names: List[str]


class SmartIncrementalCheckRequest(BaseModel):
    mode: str


class SmartIncrementalSyncItem(BaseModel):
    script_name: str
    run_start: str = ""
    run_end: str = ""
    run_ranges: List[dict] = []


class SmartIncrementalSyncRequest(BaseModel):
    items: List[SmartIncrementalSyncItem]


class CheckRequest(BaseModel):
    target_date: str


class CheckOneRequest(BaseModel):
    script_name: str
    target_date: str


class SyncDateRequest(BaseModel):
    script_name: str
    sync_date: str


class StopScriptRequest(BaseModel):
    script_name: str


def api_error(exc):
    if isinstance(exc, TaskBusyError):
        status_code = 409
    elif isinstance(exc, (UnknownScriptError, InvalidSyncDateError)):
        status_code = 400
    else:
        raise exc
    return HTTPException(status_code=status_code, detail=str(exc))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/jobs")
def api_jobs():
    try:
        return service.load_job_rows()
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.get("/api/task")
def api_task():
    try:
        return service.get_task_state()
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.get("/api/tasks")
def api_tasks():
    try:
        return service.get_tasks_state()
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/sync-one")
def api_sync_one(payload: ScriptRequest):
    try:
        service.run_single_sync_background(payload.script_name)
        return {"ok": True}
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/sync-all")
def api_sync_all():
    try:
        service.run_full_sync_background()
        return {"ok": True}
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/sync-selected")
def api_sync_selected(payload: SelectedScriptsRequest):
    try:
        service.run_selected_sync_background(payload.script_names)
        return {"ok": True}
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/smart-incremental-check")
def api_smart_incremental_check(payload: SmartIncrementalCheckRequest):
    try:
        return service.smart_incremental_check(payload.mode)
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/smart-incremental-sync")
def api_smart_incremental_sync(payload: SmartIncrementalSyncRequest):
    try:
        service.run_smart_incremental_sync_background([item.dict() for item in payload.items])
        return {"ok": True}
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/check-all")
def api_check_all(payload: CheckRequest):
    try:
        service.run_check_all_background(payload.target_date)
        return {"ok": True}
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/check-one")
def api_check_one(payload: CheckOneRequest):
    try:
        service.run_check_one_background(payload.script_name, payload.target_date)
        return {"ok": True}
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/sync-date")
def api_sync_date(payload: SyncDateRequest):
    try:
        return service.update_sync_date(payload.script_name, payload.sync_date)
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


@app.post("/api/stop-script")
def api_stop_script(payload: StopScriptRequest):
    try:
        return service.stop_script(payload.script_name)
    except DOMAIN_ERRORS as exc:
        raise api_error(exc)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main():
    import uvicorn

    url = "http://127.0.0.1:8008"
    print("Tushare Sync UI: {}".format(url))
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        "data.ui.run_sync_ui:app",
        host="127.0.0.1",
        port=8008,
        reload=False,
    )


if __name__ == "__main__":
    main()

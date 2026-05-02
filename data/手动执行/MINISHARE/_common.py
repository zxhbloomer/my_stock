"""
公共配置和工具函数 — new 目录脚本共用
目标 schema: tushare_v2
数据源: Minishare API (POST /api/v1/query, X-API-Key 鉴权)
"""
import json
import os
import threading
import time
from datetime import datetime
from functools import partial
from pathlib import Path

import pandas as pd
import pytz
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

# 加载项目根目录的 .env
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# ── 配置 ──────────────────────────────────────────────
MINISHARE_KEY  = os.environ["MINISHARE_KEY"]
MINISHARE_BASE = os.environ["MINISHARE_BASE"].rstrip("/")
DB_URL         = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://", 1)
SCHEMA         = "tushare_v2"
TODAY          = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y%m%d")
# ──────────────────────────────────────────────────────


def get_engine():
    return create_engine(DB_URL)


class _TokenBucket:
    """令牌桶限速器：按 IO cost points 控速。
    budget: 每分钟最大 cost points（服务端上限 1500，默认留余量用 1400）
    cost_per_call: 每次请求消耗的 cost points（默认 52，可通过 MINISHARE_COST 环境变量覆盖）
    """
    def __init__(self, budget: int = 1400, per: int = 60, cost_per_call: int = 52):
        self._budget        = budget
        self._per           = per
        self._cost          = cost_per_call
        self._points        = 0.0          # 当前可用 points
        self._last          = time.monotonic()
        self._lock          = threading.Lock()
        self._count         = 0
        self._points_used   = 0
        self._window        = time.monotonic()

    def acquire(self):
        while True:
            with self._lock:
                now     = time.monotonic()
                elapsed = now - self._last
                self._last   = now
                self._points = min(self._budget, self._points + elapsed * (self._budget / self._per))
                if self._points >= self._cost:
                    self._points      -= self._cost
                    self._count       += 1
                    self._points_used += self._cost
                    if now - self._window >= 60:
                        print(f"  [限速] 过去1分钟调用 {self._count} 次，消耗 {self._points_used} points（上限{self._budget}）", flush=True)
                        self._count       = 0
                        self._points_used = 0
                        self._window      = now
                    return
                wait = (self._cost - self._points) / (self._budget / self._per)
            time.sleep(wait)


_BUDGET       = int(os.environ.get("MINISHARE_BUDGET", "1400"))
_COST_PER_CALL = int(os.environ.get("MINISHARE_COST",   "52"))
_bucket = _TokenBucket(budget=_BUDGET, per=60, cost_per_call=_COST_PER_CALL)


class _MiniShareClient:
    """模拟 tushare pro 对象，所有 pro.xxx() 调用转发到 Minishare POST /api/v1/query。"""

    _MAX_RETRY  = 30
    _RETRY_WAIT = 20
    _TIMEOUT    = 120

    def __call__(self, api_name: str, fields: str = "", **params) -> pd.DataFrame:
        return self._query(api_name, fields, **params)

    def __getattr__(self, api_name: str):
        return partial(self._query, api_name)

    def _query(self, api_name: str, fields: str = "", **params) -> pd.DataFrame:
        payload = {
            "api_name": api_name,
            "params":   params,
            "fields":   [f.strip() for f in fields.split(",") if f.strip()] if fields else [],
            "use_cache": True,
        }
        headers = {
            "X-API-Key":    MINISHARE_KEY,
            "Content-Type": "application/json",
        }
        url      = f"{MINISHARE_BASE}/api/v1/query"
        last_err = None
        _id      = params.get("ts_code") or params.get("trade_date") or params.get("start_date", "")

        for attempt in range(1, self._MAX_RETRY + 1):
            _bucket.acquire()
            try:
                res = requests.post(url, json=payload, headers=headers, timeout=self._TIMEOUT)

                if res.status_code == 403:
                    # 接口未注册，无需重试
                    print(f"  [403] {api_name} 未授权: {res.text[:200]}", flush=True)
                    return pd.DataFrame()

                if res.status_code == 429:
                    wait = self._RETRY_WAIT
                    print(f"  [429] {api_name} 尝试{attempt}/{self._MAX_RETRY}，等待{wait}秒... 服务端响应: {res.text}")
                    last_err = "HTTP 429"
                    time.sleep(wait)
                    continue

                if res.status_code != 200:
                    last_err = f"HTTP {res.status_code}"
                    print(f"  [HTTP {res.status_code}] {api_name} body={res.text[:200]} 尝试{attempt}/{self._MAX_RETRY}，{self._RETRY_WAIT}秒后重试...")
                    time.sleep(self._RETRY_WAIT)
                    continue

                try:
                    result = json.loads(res.text)
                except json.JSONDecodeError as e:
                    last_err = f"JSON解析失败: {e}"
                    print(f"  [JSON ERR] {api_name} 尝试{attempt}/{self._MAX_RETRY}，{self._RETRY_WAIT}秒后重试...")
                    time.sleep(self._RETRY_WAIT)
                    continue

                # Minishare 响应：{code, msg, data: {columns, rows, ...}}
                code = result.get("code", -1)
                if code == 0:
                    data = result.get("data", {})
                    cols = data.get("columns", [])
                    rows = data.get("rows", [])
                    print(f"  [OK] {api_name} {_id} row_count={data.get('row_count', len(rows))}", flush=True)
                    if not rows:
                        return pd.DataFrame(columns=cols)
                    # rows 可能是字典列表 [{col:val}] 或数组列表 [[v1,v2]]
                    if isinstance(rows[0], dict):
                        return pd.DataFrame(rows)
                    return pd.DataFrame(rows, columns=cols)

                # 业务错误
                detail = result.get("msg", result.get("detail", "unknown"))
                last_err = f"code={code} {detail}"
                print(f"  [ERR] {api_name} {_id} {last_err} 尝试{attempt}/{self._MAX_RETRY}，{self._RETRY_WAIT}秒后重试...")
                time.sleep(self._RETRY_WAIT)

            except requests.RequestException as e:
                last_err = str(e)
                print(f"  [NET ERR] {api_name} 尝试{attempt}/{self._MAX_RETRY}: {e}，{self._RETRY_WAIT}秒后重试...")
                time.sleep(self._RETRY_WAIT)

        raise Exception(f"{api_name} 重试{self._MAX_RETRY}次仍失败，最后错误: {last_err}")


def init_tushare() -> _MiniShareClient:
    """返回 Minishare 客户端，接口与原 tushare pro 对象兼容。"""
    return _MiniShareClient()


def ensure_schema(engine):
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))

SYNC_STATUS_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.sync_status (
    script_name  VARCHAR(64)  NOT NULL,
    table_name   VARCHAR(64)  NOT NULL,
    sync_date    DATE         NOT NULL,
    status       VARCHAR(8)   NOT NULL CHECK (status IN ('ing', 'ok')),
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (script_name)
);
"""

def ensure_sync_status_table(engine):
    with engine.begin() as conn:
        conn.execute(text(SYNC_STATUS_SQL))


def get_sync_start(engine, script_name: str, default_start: str) -> str:
    """
    读取 sync_status，返回本次应从哪天开始同步。
    - 无记录（首次）→ default_start（全量）
    - status=ing    → sync_date（从中断日重跑）
    - status=ok     → sync_date + 1天（精确增量，无 LOOKBACK）
    """
    try:
        with engine.connect() as conn:
            r = conn.execute(text(
                f"SELECT sync_date, status FROM {SCHEMA}.sync_status WHERE script_name=:s"
            ), {"s": script_name}).fetchone()
    except Exception as e:
        print(f"[WARN] get_sync_start({script_name}) 查询失败: {e}，回退到 default_start={default_start}")
        return default_start
    if r is None:
        return default_start
    if r[1] == 'ing':
        return pd.Timestamp(r[0]).strftime("%Y%m%d")
    # status='ok'，从下一个自然日开始（trade_cal 会过滤非交易日）
    return (pd.Timestamp(r[0]) + pd.Timedelta(days=1)).strftime("%Y%m%d")


def mark_sync(engine, script_name: str, table_name: str, date, status: str):
    """
    upsert 一条 sync_status 记录。
    date 可以是 'YYYYMMDD' 字符串或 datetime/Timestamp。
    updated_at 显式赋值，不依赖 DEFAULT（DEFAULT 只在 INSERT 时生效）。
    """
    if isinstance(date, str):
        date = pd.Timestamp(date)
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {SCHEMA}.sync_status
                (script_name, table_name, sync_date, status, updated_at)
            VALUES (:s, :t, :d, :st, CURRENT_TIMESTAMP)
            ON CONFLICT (script_name) DO UPDATE SET
                table_name = EXCLUDED.table_name,
                sync_date  = EXCLUDED.sync_date,
                status     = EXCLUDED.status,
                updated_at = CURRENT_TIMESTAMP
        """), {"s": script_name, "t": table_name, "d": date.date() if hasattr(date, 'date') else date, "st": status})



def check_or_create_table(engine, table: str, create_sql: str, expected_cols: list[str]):
    """
    表不存在 → 自动建表。
    表已存在 → 比对字段，不一致则报错中断。
    """
    insp = inspect(engine)
    if not insp.has_table(table, schema=SCHEMA):
        with engine.begin() as conn:
            conn.execute(text(create_sql))
        print(f"[建表] {SCHEMA}.{table}")
        return
    # 表已存在，比对字段
    existing = {c['name'] for c in insp.get_columns(table, schema=SCHEMA)}
    expected = set(expected_cols)
    missing  = expected - existing
    extra    = existing - expected - {'update_time'}
    if missing or extra:
        raise RuntimeError(
            f"[字段不一致] {SCHEMA}.{table}\n"
            f"  缺少字段: {missing}\n"
            f"  多余字段: {extra}\n"
            f"请手动处理后重新运行。"
        )
    print(f"[字段一致] {SCHEMA}.{table} ✓")


def _qt(table: str) -> str:
    """给表名加双引号，避免以数字开头的表名被 PostgreSQL 解析器报错。"""
    return f'"{table}"'


def _qc(col: str) -> str:
    """给列名加双引号，避免 desc/name 等保留字被 PostgreSQL 解析器报错。"""
    return f'"{col}"'


def get_stock_codes(pro) -> list[str]:
    """取全市场股票代码。
    Minishare 默认上限5000，传 limit=10000 确保取到全量（当前约5835只）。
    """
    df = pro.stock_basic(fields="ts_code", limit=10000)
    if df is None or df.empty or "ts_code" not in df.columns:
        raise RuntimeError("stock_basic 返回异常，未获取到任何股票代码")
    return df["ts_code"].tolist()


def get_trade_dates(pro, start: str, end: str, exchange: str = "SSE") -> list[str]:
    """查询交易日列表，返回空列表而不是抛异常（start > end 或未来日期时）。"""
    cal = pro.trade_cal(exchange=exchange, start_date=start, end_date=end,
                        is_open="1", fields="cal_date")
    if cal is None or cal.empty or "cal_date" not in cal.columns:
        return []
    return sorted(cal["cal_date"].tolist())


def get_max_date(engine, table: str, date_col: str = "trade_date") -> str | None:
    try:
        with engine.connect() as conn:
            r = conn.execute(text(
                f"SELECT MAX({date_col}) FROM {SCHEMA}.{_qt(table)}"
            )).fetchone()
            if r and r[0]:
                return pd.Timestamp(r[0]).strftime("%Y%m%d")
    except Exception:
        pass
    return None


def save_df(engine, df: pd.DataFrame, table: str, cols: list[str]) -> int:
    if df is None or df.empty:
        return 0
    df[cols].to_sql(table, engine, schema=SCHEMA, if_exists="append",
                    index=False, method="multi", chunksize=5000)
    return len(df)


def upsert_df(engine, df: pd.DataFrame, table: str, cols: list[str], pk: list[str]) -> int:
    if df is None or df.empty:
        return 0
    tmp = f"_tmp_{table}"
    set_clause = ", ".join(f"{_qc(c)}=EXCLUDED.{_qc(c)}" for c in cols if c not in pk)
    pk_clause  = ", ".join(_qc(c) for c in pk)
    with engine.begin() as conn:
        # 临时表与 INSERT 在同一事务，失败时一起回滚，不会留下孤立临时表
        df[cols].to_sql(tmp, conn, schema=SCHEMA, if_exists="replace",
                        index=False, method="multi", chunksize=5000)
        conn.execute(text(f"""
            INSERT INTO {SCHEMA}.{_qt(table)} ({','.join(_qc(c) for c in cols)})
            SELECT {','.join(_qc(c) for c in cols)} FROM {SCHEMA}.{_qt(tmp)}
            ON CONFLICT ({pk_clause}) DO UPDATE SET {set_clause}
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {SCHEMA}.{_qt(tmp)}"))
    return len(df)


def truncate_and_insert(engine, df: pd.DataFrame, table: str, cols: list[str]) -> int:
    """全删全插，用于无日期维度、无法增量的接口。TRUNCATE 与 INSERT 在同一事务中，避免中途崩溃导致表为空。
    注意：to_sql 的 name 参数传原始表名（不加引号），SQLAlchemy psycopg2 方言会自动处理引号。
    但为保险起见，先写入临时表再 INSERT SELECT，确保以数字开头的表名不出问题。
    """
    if df is None or df.empty:
        return 0
    tmp = f"_tmp_{table}"
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {SCHEMA}.{_qt(table)}"))
        df[cols].to_sql(tmp, conn, schema=SCHEMA, if_exists="replace",
                        index=False, method="multi", chunksize=5000)
        conn.execute(text(f"""
            INSERT INTO {SCHEMA}.{_qt(table)} ({','.join(_qc(c) for c in cols)})
            SELECT {','.join(_qc(c) for c in cols)} FROM {SCHEMA}.{_qt(tmp)}
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {SCHEMA}.{_qt(tmp)}"))
    return len(df)

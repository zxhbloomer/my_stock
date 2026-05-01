"""
公共配置和工具函数 — new 目录脚本共用
目标 schema: tushare_v2
"""
import json
import os
import time
from datetime import datetime
import pytz
from functools import partial
from pathlib import Path

import pandas as pd
import requests
import tushare as ts
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

# 加载项目根目录的 .env
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# ── 配置 ──────────────────────────────────────────────
TOKEN    = os.environ["TUSHARE_TOKEN"]
HTTP_URL = os.environ["TUSHARE_HTTP_URL"]
DB_URL   = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://", 1)
SCHEMA   = "tushare_v2"
TODAY    = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y%m%d")
# ──────────────────────────────────────────────────────


def get_engine():
    return create_engine(DB_URL)


def init_tushare():
    pro = ts.pro_api(TOKEN, timeout=120)
    pro._DataApi__http_url = HTTP_URL
    _patch_query(pro)
    return pro


def _patch_query(pro, max_retry: int = 30, retry_wait: int = 20):
    def patched_query(self, api_name, fields='', **kwargs):
        req_params = {
            'api_name': api_name,
            'token': self._DataApi__token,
            'params': kwargs,
            'fields': fields,
        }
        url = f"{self._DataApi__http_url}/{api_name}"
        last_err = None
        for attempt in range(1, max_retry + 1):
            try:
                res = requests.post(url, json=req_params, timeout=self._DataApi__timeout)
                if res.status_code != 200:
                    last_err = f"HTTP {res.status_code}"
                    print(f"  [HTTP {res.status_code}] {api_name} 尝试{attempt}/{max_retry}，{retry_wait}秒后重试...")
                    time.sleep(retry_wait)
                    continue
                try:
                    result = json.loads(res.text)
                except json.JSONDecodeError as e:
                    last_err = f"JSON解析失败(响应体可能被截断): {e}"
                    print(f"  [JSON ERR] {api_name} 尝试{attempt}/{max_retry}，{retry_wait}秒后重试...")
                    time.sleep(retry_wait)
                    continue
                biz_code = result.get('code', -1)
                _id = (kwargs.get('ts_code') or kwargs.get('trade_date')
                       or kwargs.get('start_date', ''))
                print(f"  [HTTP 200|code={biz_code}] {api_name} {_id}", flush=True)
                if biz_code != 0:
                    last_err = f"biz_code={biz_code} msg={result.get('msg','')}"
                    if biz_code == 502:
                        # 数据不存在，无需重试
                        return pd.DataFrame()
                    print(f"  [BIZ ERR] {last_err} 尝试{attempt}/{max_retry}，{retry_wait}秒后重试...")
                    time.sleep(retry_wait)
                    continue
                data = result['data']
                return pd.DataFrame(data['items'], columns=data['fields'])
            except requests.RequestException as e:
                last_err = str(e)
                print(f"  [NET ERR] {api_name} 尝试{attempt}/{max_retry}: {e}，{retry_wait}秒后重试...")
                time.sleep(retry_wait)
        raise Exception(f"{api_name} 重试{max_retry}次仍失败，最后错误: {last_err}")

    pro.__class__.query = patched_query
    pro.__class__.__getattr__ = lambda self, name: partial(self.query, name)


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

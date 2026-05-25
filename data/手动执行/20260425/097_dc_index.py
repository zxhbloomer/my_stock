"""
接口：dc_index，可以通过数据工具调试和查看数据
描述：获取东方财富每个交易日的概念板块数据，支持按日期查询
限量：单次最大可获取5000条数据，历史数据可根据日期循环获取
权限：6000积分
接口文档: https://tushare.pro/document/2?doc_id=362
本地文档: docs/tushare/tushare.pro/document/23a35.html

同步策略：按交易日增量（ts_code+trade_date 为主键，upsert），按小段交易日批量拉取
表名：097_dc_index
用法: python 097_dc_index.py [--start YYYYMMDD] [--end YYYYMMDD] [--batch-days 8]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "097_dc_index"
# Tushare ChangeLog 写明 2025-01-05 上线“东方财富概念板块数据”。
# dc_index 文档未明确历史起点；本地真实 API 验证 2024-12-19 及以前为空，
# 2024-12-20 开始有 458 条板块列表，因此同步和 UI 全量检查从该日开始。
DEFAULT_START = "20241220"
DATA_START    = DEFAULT_START
FIELDS = "ts_code,trade_date,name,leading,leading_code,pct_change,leading_pct,total_mv,turnover_rate,up_num,down_num,idx_type,level"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code       VARCHAR(15) NOT NULL,
    trade_date    DATE        NOT NULL,
    name          VARCHAR(100),
    "leading"     VARCHAR(80),
    leading_code  VARCHAR(15),
    pct_change    FLOAT,
    leading_pct   FLOAT,
    total_mv      FLOAT,
    turnover_rate FLOAT,
    up_num        INT,
    down_num      INT,
    idx_type      VARCHAR(30),
    level         VARCHAR(20),
    update_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = ["pct_change", "leading_pct", "total_mv", "turnover_rate"]
INT_COLS = ["up_num", "down_num"]


def effective_start(start: str) -> str:
    return max(start, DATA_START)


def get_start(engine):
    start = effective_start(get_sync_start(engine, f"{TABLE}.py", DEFAULT_START))
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def chunks(items, size):
    if size <= 0:
        raise ValueError("--batch-days 必须大于 0")
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_date_range(pro, start_date, end_date):
    return pro.dc_index(start_date=start_date, end_date=end_date, fields=FIELDS)


def normalize_df(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    for col in FLOAT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in INT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df.dropna(subset=PK).drop_duplicates(subset=PK)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--batch-days", type=int, default=8)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = effective_start(args.start) if args.start else get_start(engine)
    dates = get_trade_dates(pro, start, args.end)

    total_rows, t0 = 0, datetime.now()
    done = 0
    for batch in chunks(dates, args.batch_days):
        for d in batch:
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ing")

        df = normalize_df(fetch_date_range(pro, batch[0], batch[-1]))
        if df is not None and not df.empty:
            rows = upsert_df(engine, df, TABLE, COLS, PK)
            total_rows += rows
        else:
            rows = 0
        for d in batch:
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
        done += len(batch)
        elapsed = (datetime.now() - t0).seconds
        print(
            f"  [{done:4d}/{len(dates)}] {batch[0]}~{batch[-1]}  {rows}条  {elapsed//60}分{elapsed%60}秒",
            flush=True,
        )

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()

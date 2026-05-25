"""
接口：dc_member，可以通过数据工具调试和查看数据
描述：获取东方财富板块每日成分数据，可以根据概念板块代码和交易日期获取历史成分
限量：单次最大获取5000条数据，可以通过日期和代码循环获取
权限：6000积分
接口文档: https://tushare.pro/document/2?doc_id=363
本地文档: docs/tushare/tushare.pro/document/29fb4.html

同步策略：按交易日分页增量（trade_date+ts_code+con_code 为主键，upsert）
表名：098_dc_member
用法: python 098_dc_member.py [--start YYYYMMDD] [--end YYYYMMDD] [--page-size 5000]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "098_dc_member"
# Tushare ChangeLog 写明 2025-01-05 上线“东方财富概念板块数据”，包含东方财富板块成分。
# dc_member 文档未明确历史起点，但官方示例使用 2025-01-02；
# 本地真实 API 验证 2024 年年初 SSE 交易日、2024-12-31 及以前为空，
# 2025-01-02 开始有成分数据。
DEFAULT_START = "20250102"
DATA_START    = DEFAULT_START
FIELDS = "trade_date,ts_code,con_code,name"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "con_code"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(15) NOT NULL,
    con_code    VARCHAR(15) NOT NULL,
    name        VARCHAR(80),
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, con_code)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_con ON {SCHEMA}."{TABLE}" (con_code);
"""


def effective_start(start: str) -> str:
    return max(start, DATA_START)


def get_start(engine):
    start = effective_start(get_sync_start(engine, f"{TABLE}.py", DEFAULT_START))
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def fetch_trade_date_pages(pro, trade_date, page_size):
    frames = []
    offset = 0
    while True:
        df = pro.dc_member(trade_date=trade_date, fields=FIELDS, limit=page_size, offset=offset)
        if df is None or df.empty:
            break
        frames.append(df)
        if len(df) < page_size:
            break
        offset += page_size
    if not frames:
        return pd.DataFrame(columns=COLS)
    return pd.concat(frames, ignore_index=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--page-size", type=int, default=5000)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = effective_start(args.start) if args.start else get_start(engine)
    dates = get_trade_dates(pro, start, args.end)

    total_rows, t0 = 0, datetime.now()
    for i, d in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, d, "ing")
        df = fetch_trade_date_pages(pro, d, args.page_size)
        if df is not None and not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
            df = df.dropna(subset=PK).drop_duplicates(subset=PK)
            rows = upsert_df(engine, df, TABLE, COLS, PK)
            total_rows += rows
        else:
            rows = 0
        mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()

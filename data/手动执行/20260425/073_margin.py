"""
接口：margin，可以通过数据工具调试和查看数据
描述：获取融资融券每日交易汇总数据
限量：单次请求最大返回4000行数据，可根据日期循环
权限：2000积分可获得本接口权限，积分越高权限越大
接口文档: https://tushare.pro/document/2?doc_id=58
本地文档: docs/tushare/tushare.pro/document/2ab9c.html

输入参数：trade_date(str,N,交易日期), start_date(str,N,开始日期),
          end_date(str,N,结束日期), exchange_id(str,N,交易所代码SSE/SZSE/BSE)
输出字段：trade_date,exchange_id,rzye,rzmre,rzche,rqye,rqmcl,rzrqye,rqyl

同步策略：按交易日增量（trade_date+exchange_id 为主键，upsert）
表名：073_margin
迁移说明：tushare schema 中无此表，无需迁移
用法: python 073_margin.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "073_margin"
DEFAULT_START = "20100331"  # 融资融券2010年3月31日开始
FIELDS = "trade_date,exchange_id,rzye,rzmre,rzche,rqye,rqmcl,rzrqye,rqyl"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "exchange_id"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date  DATE        NOT NULL,
    exchange_id VARCHAR(10) NOT NULL,
    rzye        FLOAT,
    rzmre       FLOAT,
    rzche       FLOAT,
    rqye        FLOAT,
    rqmcl       FLOAT,
    rzrqye      FLOAT,
    rqyl        FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, exchange_id)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = ["rzye","rzmre","rzche","rqye","rqmcl","rzrqye","rqyl"]


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)
    dates = get_trade_dates(pro, start, args.end)

    total_rows, t0 = 0, datetime.now()
    for i, d in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, d, "ing")
        try:
            df = pro.margin(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                for col in FLOAT_COLS:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=PK).drop_duplicates(subset=PK)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
        except Exception as e:
            print(f"  [SKIP] {d}: {e}")
            rows = 0
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        time.sleep(0.3)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()

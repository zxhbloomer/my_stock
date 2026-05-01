"""
接口：margin_secs，可以通过数据工具调试和查看数据
描述：获取沪深京三大交易所融资融券标的（包括ETF），每天盘前更新
限量：单次最大6000行数据，可根据股票代码、交易日期、交易所代码循环提取
权限：2000积分可调取，5000积分无总量限制
接口文档: https://tushare.pro/document/2?doc_id=326
本地文档: docs/tushare/tushare.pro/document/22b54.html

输入参数：ts_code(str,N,标的代码), trade_date(str,N,交易日),
          exchange(str,N,交易所SSE/SZSE/BSE),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：trade_date,ts_code,name,exchange

同步策略：按交易日增量（trade_date+ts_code+exchange 为主键，upsert）
表名：075_margin_secs
迁移说明：tushare schema 中无此表，无需迁移
用法: python 075_margin_secs.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "075_margin_secs"
DEFAULT_START = "20100331"
FIELDS = "trade_date,ts_code,name,exchange"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "exchange"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(15) NOT NULL,
    name        VARCHAR(50),
    exchange    VARCHAR(10) NOT NULL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, exchange)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""


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
            df = pro.margin_secs(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
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

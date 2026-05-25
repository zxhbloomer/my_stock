"""
接口：dc_daily，可以通过数据工具调试和查看数据
描述：获取东财概念板块、行业指数板块、地域板块行情数据，历史数据开始于2020年
限量：单次最大2000条数据，可根据日期参数循环获取
权限：6000积分
接口文档: https://tushare.pro/document/2?doc_id=382
本地文档: docs/tushare/tushare.pro/document/2a955.html

同步策略：按交易日增量（ts_code+trade_date 为主键，upsert）
表名：099_dc_daily
用法: python 099_dc_daily.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "099_dc_daily"
DEFAULT_START = "20200101"
FIELDS = "ts_code,trade_date,close,open,high,low,change,pct_change,vol,amount,swing,turnover_rate"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code       VARCHAR(15) NOT NULL,
    trade_date    DATE        NOT NULL,
    close         FLOAT,
    open          FLOAT,
    high          FLOAT,
    low           FLOAT,
    change        FLOAT,
    pct_change    FLOAT,
    vol           FLOAT,
    amount        FLOAT,
    swing         FLOAT,
    turnover_rate FLOAT,
    update_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = [c for c in COLS if c not in {"ts_code", "trade_date"}]


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
        df = pro.dc_daily(trade_date=d, fields=FIELDS)
        if df is not None and not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
            for col in FLOAT_COLS:
                df[col] = pd.to_numeric(df[col], errors="coerce")
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

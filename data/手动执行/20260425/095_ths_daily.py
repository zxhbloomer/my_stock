"""
接口：ths_daily，可以通过数据工具调试和查看数据
描述：获取同花顺板块指数行情
限量：单次最大3000行数据，可根据指数代码、日期参数循环提取
权限：6000积分
接口文档: https://tushare.pro/document/2?doc_id=260
本地文档: docs/tushare/tushare.pro/document/2af19.html

同步策略：按交易日增量（ts_code+trade_date 为主键，upsert）
表名：095_ths_daily
用法: python 095_ths_daily.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "095_ths_daily"
DEFAULT_START = "20100101"
FIELDS = "ts_code,trade_date,close,open,high,low,pre_close,avg_price,change,pct_change,vol,turnover_rate,total_mv,float_mv"
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
    pre_close     FLOAT,
    avg_price     FLOAT,
    change        FLOAT,
    pct_change    FLOAT,
    vol           FLOAT,
    turnover_rate FLOAT,
    total_mv      FLOAT,
    float_mv      FLOAT,
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
        df = pro.ths_daily(trade_date=d, fields=FIELDS)
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

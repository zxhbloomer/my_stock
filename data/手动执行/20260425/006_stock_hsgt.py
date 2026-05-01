"""
接口：stock_hsgt，可以通过数据工具调试和查看数据。
描述：获取沪深港通股票列表
限量：单次请求最大返回2000行数据，可根据类型循环提取，数据从20250812开始
权限：3000积分起
接口文档: https://tushare.pro/document/2?doc_id=398
本地文档: docs/tushare/tushare.pro/document/2400f.html

状态：PASS — 自定义 HTTP 服务端（8.136.22.187:8010）不支持此接口，调用超时。
      如需使用，改用官方 tushare.pro 直连。

同步策略：按交易日增量（trade_date 为主键维度）
表名：006_stock_hsgt
迁移说明：tushare schema 中无此表，无需迁移
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "006_stock_hsgt"
DEFAULT_START = "20250812"   # 接口数据起始日期
FIELDS = "ts_code,trade_date,type,name,type_name"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "type"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code    VARCHAR(15) NOT NULL,
    trade_date DATE        NOT NULL,
    type       VARCHAR(10) NOT NULL,
    name       VARCHAR(50),
    type_name  VARCHAR(50),
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, type)
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
            df = pro.stock_hsgt(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
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
        if rows > 0 or i % 20 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        time.sleep(0.3)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()

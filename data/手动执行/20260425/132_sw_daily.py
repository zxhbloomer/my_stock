"""
接口：sw_daily，可以通过数据工具调试和查看数据
描述：获取申万行业日线行情（默认是申万2021版行情）
限量：单次最大4000行数据，可通过指数代码和日期参数循环提取
权限：5000积分可调取
接口文档: https://tushare.pro/document/2?doc_id=327
本地文档: docs/tushare/tushare.pro/document/278a7.html
实测说明：
  - 数据库已有 2011-03-07~2017-05-12 的旧申万历史数据。
  - 2018-2020 抽样调用 sw_daily 返回0条；2021-01-04 起默认申万2021版数据连续可用。
  - 因此 2018-2020 的空档不是本地漏同步，智能检查不应按必补缺口处理。

输入参数：ts_code(str,N,行业代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,name,open,low,high,close,change,pct_change,
          vol,amount,pe,pb,float_mv,total_mv

同步策略：按交易日增量（ts_code+trade_date 为主键，upsert）
表名：132_sw_daily
迁移说明：tushare schema 中无可用源表，无需迁移
用法: python 132_sw_daily.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "132_sw_daily"
DEFAULT_START = "20100104"
FIELDS = "ts_code,trade_date,name,open,low,high,close,change,pct_change,vol,amount,pe,pb,float_mv,total_mv"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(20) NOT NULL,
    trade_date  DATE        NOT NULL,
    name        VARCHAR(100),
    open        FLOAT,
    low         FLOAT,
    high        FLOAT,
    close       FLOAT,
    change      FLOAT,
    pct_change  FLOAT,
    vol         FLOAT,
    amount      FLOAT,
    pe          FLOAT,
    pb          FLOAT,
    float_mv    FLOAT,
    total_mv    FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = ["open","low","high","close","change","pct_change",
              "vol","amount","pe","pb","float_mv","total_mv"]


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
        df = pro.sw_daily(trade_date=d, fields=FIELDS)
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

        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()

"""
接口：limit_step，可以通过数据工具调试和查看数据
描述：获取每天连板个数晋级的股票，可以分析出每天连续涨停进阶个数，判断强势热度
限量：单次最大2000行数据，可根据股票代码或者日期循环提取全部
权限：8000积分以上每分钟500次，每天总量不限制
接口文档: https://tushare.pro/document/2?doc_id=299
本地文档: docs/tushare/tushare.pro/document/2f5ab.html

输入参数：trade_date(str,N,交易日期), ts_code(str,N,股票代码),
          start_date(str,N,开始日期), end_date(str,N,结束日期),
          nums(str,N,连板次数，支持多个输入)
输出字段：ts_code,name,trade_date,nums

同步策略：按交易日增量（trade_date+ts_code+nums 为主键，upsert）
表名：092_limit_step
迁移说明：新接口脚本，目标表不存在，无需迁移
用法: python 092_limit_step.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "092_limit_step"
DEFAULT_START = "20200101"
FIELDS = "ts_code,name,trade_date,nums"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "nums"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(15) NOT NULL,
    name        VARCHAR(50),
    trade_date  DATE        NOT NULL,
    nums        VARCHAR(20) NOT NULL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, nums)
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
            df = pro.limit_step(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                df = df.dropna(subset=PK).drop_duplicates(subset=PK)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
        except Exception:
            raise
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        # time.sleep(0.3)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()


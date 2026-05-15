"""
接口：limit_list_d，可以通过数据工具调试和查看数据
描述：获取A股每日涨跌停、炸板数据情况，数据从2020年开始（不提供ST股票的统计）
限量：单次最大可以获取2500条数据，可通过日期或者股票循环提取
权限：5000积分每分钟可以请求200次每天总量1万次，8000积分以上每分钟500次每天总量不限制
接口文档: https://tushare.pro/document/2?doc_id=298
本地文档: docs/tushare/tushare.pro/document/256a1.html

输入参数：trade_date(str,N,交易日期), ts_code(str,N,股票代码),
          limit_type(str,N,涨跌停类型 U涨停/D跌停/Z炸板), exchange(str,N,交易所),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：trade_date,ts_code,industry,name,close,pct_chg,amount,limit_amount,
          float_mv,total_mv,turnover_ratio,fd_amount,first_time,last_time,
          open_times,up_stat,limit_times,limit

同步策略：按交易日增量，同时同步 U/D/Z 三种类型（trade_date+ts_code+limit 为主键，upsert）
表名：091_limit_list_d
迁移说明：新接口脚本，目标表不存在，无需迁移
用法: python 091_limit_list_d.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "091_limit_list_d"
DEFAULT_START = "20200101"
FIELDS = "trade_date,ts_code,industry,name,close,pct_chg,amount,limit_amount,float_mv,total_mv,turnover_ratio,fd_amount,first_time,last_time,open_times,up_stat,limit_times,limit"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "limit"]
LIMIT_TYPES = ["U", "D", "Z"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date      DATE        NOT NULL,
    ts_code         VARCHAR(15) NOT NULL,
    industry        VARCHAR(100),
    name            VARCHAR(50),
    close           FLOAT,
    pct_chg         FLOAT,
    amount          FLOAT,
    limit_amount    FLOAT,
    float_mv        FLOAT,
    total_mv        FLOAT,
    turnover_ratio  FLOAT,
    fd_amount       FLOAT,
    first_time      VARCHAR(20),
    last_time       VARCHAR(20),
    open_times      INT,
    up_stat         VARCHAR(20),
    limit_times     INT,
    "limit"         VARCHAR(5)  NOT NULL,
    update_time     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, "limit")
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date_limit ON {SCHEMA}."{TABLE}" (trade_date, "limit");
"""

INT_COLS = ["open_times", "limit_times"]
FLOAT_COLS = ["close","pct_chg","amount","limit_amount","float_mv","total_mv",
              "turnover_ratio","fd_amount"]


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
            day_rows = 0
            for limit_type in LIMIT_TYPES:
                df = pro.limit_list_d(trade_date=d, limit_type=limit_type, fields=FIELDS)
                if df is not None and not df.empty:
                    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                    for col in INT_COLS:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                    for col in FLOAT_COLS:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                    df = df.dropna(subset=PK).drop_duplicates(subset=PK)
                    rows = upsert_df(engine, df, TABLE, COLS, PK)
                    day_rows += rows
                    total_rows += rows
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
        except Exception:
            raise
        elapsed = (datetime.now() - t0).seconds
        if day_rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {day_rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        # time.sleep(0.3)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()

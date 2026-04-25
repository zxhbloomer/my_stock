"""
接口：ci_daily，可以通过数据工具调试和查看数据
描述：获取中信行业指数日线行情
限量：单次最大4000条，可循环提取
权限：5000积分可调取，可通过指数代码和日期参数循环获取所有数据
接口文档: https://tushare.pro/document/2?doc_id=308
本地文档: docs/tushare/tushare.pro/document/27d0f.html

输入参数：ts_code(str,N,行业代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,open,low,high,close,pre_close,change,pct_change,vol,amount

同步策略：按交易日增量（ts_code+trade_date 为主键，upsert）
表名：135_ci_daily
迁移说明：tushare schema 中无此表，无需迁移
用法: python 135_ci_daily.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "135_ci_daily"
DEFAULT_START = "20050104"
LOOKBACK_DAYS = 7

FIELDS = "ts_code,trade_date,open,low,high,close,pre_close,change,pct_change,vol,amount"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(20) NOT NULL,
    trade_date  DATE        NOT NULL,
    open        FLOAT,
    low         FLOAT,
    high        FLOAT,
    close       FLOAT,
    pre_close   FLOAT,
    change      FLOAT,
    pct_change  FLOAT,
    vol         FLOAT,
    amount      FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = ["open","low","high","close","pre_close","change","pct_change","vol","amount"]


def get_start(engine):
    max_d = get_max_date(engine, TABLE)
    if max_d:
        start = (pd.Timestamp(max_d) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
        print(f"[增量] {TABLE} 最新={max_d}，从 {start} 开始")
        return start
    return DEFAULT_START


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)
    cal = pro.trade_cal(exchange="SSE", start_date=start, end_date=args.end,
                        is_open="1", fields="cal_date")
    dates = sorted(cal["cal_date"].tolist())

    total_rows, t0 = 0, datetime.now()
    for i, d in enumerate(dates, 1):
        try:
            df = pro.ci_daily(trade_date=d, fields=FIELDS)
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

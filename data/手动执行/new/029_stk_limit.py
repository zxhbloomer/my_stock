"""
接口：stk_limit，可以通过数据工具调试和查看数据
描述：获取全市场（包含A/B股和基金）每日涨跌停价格，包括涨停价格，跌停价格等，
      每个交易日8点40左右更新当日股票涨跌停价格。
限量：单次最多提取5800条记录，可循环调取，总量不限制
权限：用户积2000积分可调取，单位分钟有流控，积分越高流量越大
接口文档: https://tushare.pro/document/2?doc_id=183
本地文档: docs/tushare/tushare.pro/document/2692d.html

输入参数：ts_code(str,N,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：trade_date,ts_code,pre_close,up_limit,down_limit

同步策略：按交易日增量（trade_date 为主键维度，upsert）
表名：029_stk_limit
迁移说明：tushare schema 中无此表，无需迁移
用法: python 029_stk_limit.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "029_stk_limit"
DEFAULT_START = "20100729"
LOOKBACK_DAYS = 3
FIELDS = "trade_date,ts_code,pre_close,up_limit,down_limit"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(15) NOT NULL,
    pre_close   FLOAT,
    up_limit    FLOAT,
    down_limit  FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""

FLOAT_COLS = ["pre_close", "up_limit", "down_limit"]


def get_start(engine):
    max_d = get_max_date(engine, TABLE, date_col="trade_date")
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
            df = pro.stk_limit(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
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

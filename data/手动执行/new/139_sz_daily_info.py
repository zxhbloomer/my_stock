"""
接口：sz_daily_info，可以通过数据工具调试和查看数据
描述：获取深圳市场每日交易概况
限量：单次最大2000，可循环获取，总量不限制
权限：用户积2000积分可调取，频次有限制，积分越高每分钟调取频次越高，
      5000积分以上频次相对较高
接口文档: https://tushare.pro/document/2?doc_id=216
本地文档: docs/tushare/tushare.pro/document/299cd.html

输入参数：trade_date(str,N,交易日期), ts_code(str,N,板块代码),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：trade_date,ts_code,count,amount,vol,total_share,total_mv,float_share,float_mv

板块代码（ts_code）：股票, 主板A股, 主板B股, 创业板A股, 基金, ETF, LOF,
                     封闭式基金, 基础设施基金, 债券, 债券现券, 债券回购, ABS, 期权
数据开始日期：20080102

同步策略：按交易日增量（trade_date+ts_code 为主键，upsert）
          注意：count 为 INT 类型；vol 文档标注 None 类型，实际为数值，存为 FLOAT
表名：139_sz_daily_info
迁移说明：tushare schema 中无此表，无需迁移
用法: python 139_sz_daily_info.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "139_sz_daily_info"
DEFAULT_START = "20080102"
LOOKBACK_DAYS = 7

FIELDS = "trade_date,ts_code,count,amount,vol,total_share,total_mv,float_share,float_mv"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(30) NOT NULL,
    count       INT,
    amount      FLOAT,
    vol         FLOAT,
    total_share FLOAT,
    total_mv    FLOAT,
    float_share FLOAT,
    float_mv    FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

INT_COLS   = ["count"]
FLOAT_COLS = ["amount","vol","total_share","total_mv","float_share","float_mv"]


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
            df = pro.sz_daily_info(trade_date=d, fields=FIELDS)
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

"""
接口：stk_weekly_monthly，可以通过数据工具调试和查看数据
描述：股票周/月线行情(每日更新)
限量：单次最大6000，可使用交易日期循环提取，总量不限制
权限：用户需要至少2000积分才可以调取
接口文档: https://tushare.pro/document/2?doc_id=229
本地文档: docs/tushare/tushare.pro/document/26e60.html

输入参数：ts_code(str,N,TS代码), trade_date(str,N,交易日期),
          start_date(str,N,开始交易日期), end_date(str,N,结束交易日期),
          freq(str,Y,频率 week周/month月)
输出字段：ts_code,trade_date,end_date,freq,open,high,low,close,pre_close,vol,amount,change,pct_chg

同步策略：按交易日增量，同时同步 week/month 两种频率（ts_code+trade_date+freq 为主键，upsert）
表名：021_stk_weekly_monthly
迁移说明：新接口脚本，目标表不存在，无需迁移
用法: python 021_stk_weekly_monthly.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "021_stk_weekly_monthly"
DEFAULT_START = "20100104"
FIELDS = "ts_code,trade_date,end_date,freq,open,high,low,close,pre_close,vol,amount,change,pct_chg"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date", "freq"]
FREQS  = ["week", "month"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(15) NOT NULL,
    trade_date  DATE        NOT NULL,
    end_date    DATE,
    freq        VARCHAR(10) NOT NULL,
    open        FLOAT,
    high        FLOAT,
    low         FLOAT,
    close       FLOAT,
    pre_close   FLOAT,
    vol         FLOAT,
    amount      FLOAT,
    change      FLOAT,
    pct_chg     FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date, freq)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

DATE_COLS = ["trade_date", "end_date"]
FLOAT_COLS = ["open","high","low","close","pre_close","vol","amount","change","pct_chg"]


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
    week_dates = set(get_period_trade_dates(pro, start, args.end, "week"))
    month_dates = set(get_period_trade_dates(pro, start, args.end, "month"))
    dates = sorted(week_dates | month_dates)
    if not dates:
        print("[已是最新] 当前区间没有已完成的周/月周期结束日")
        return

    total_rows, t0 = 0, datetime.now()
    for i, d in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, d, "ing")
        try:
            day_rows = 0
            freqs = []
            if d in week_dates:
                freqs.append("week")
            if d in month_dates:
                freqs.append("month")
            for freq in freqs:
                df = pro.stk_weekly_monthly(trade_date=d, freq=freq, fields=FIELDS)
                if df is not None and not df.empty:
                    for col in DATE_COLS:
                        if col in df.columns:
                            df[col] = pd.to_datetime(df[col], errors="coerce")
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

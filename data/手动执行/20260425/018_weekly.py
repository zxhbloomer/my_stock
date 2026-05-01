"""
接口：weekly，可以通过数据工具调试和查看数据
描述：获取A股周线行情，本接口每周最后一个交易日更新
限量：单次最大6000行，可使用交易日期循环提取，总量不限制
权限：用户需要至少2000积分才可以调取
接口文档: https://tushare.pro/document/2?doc_id=144
本地文档: docs/tushare/tushare.pro/document/293db.html

输入参数：ts_code(str,N,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount

同步策略：按交易日增量（trade_date 为主键维度，upsert）
表名：018_weekly
迁移说明：tushare schema 中无此表，无需迁移
用法: python 018_weekly.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "018_weekly"
DEFAULT_START = "20100729"
FIELDS = "ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code    VARCHAR(15) NOT NULL,
    trade_date DATE        NOT NULL,
    close      FLOAT,
    open       FLOAT,
    high       FLOAT,
    low        FLOAT,
    pre_close  FLOAT,
    change     FLOAT,
    pct_chg    FLOAT,
    vol        FLOAT,
    amount     FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = ["close","open","high","low","pre_close","change","pct_chg","vol","amount"]


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
    _cal_dates = get_trade_dates(pro, start, args.end)
    if not _cal_dates:
        print("[已是最新] 无需同步")
        return
    # 周线只在每周最后一个交易日有数据，按周分组取最大日期
    cal = pd.DataFrame({"cal_date": pd.to_datetime(_cal_dates)})
    cal["week"] = cal["cal_date"].dt.isocalendar().week.astype(str) + "-" + cal["cal_date"].dt.year.astype(str)
    dates = sorted(cal.groupby("week")["cal_date"].max().dt.strftime("%Y%m%d").tolist())

    total_rows, t0 = 0, datetime.now()
    for i, d in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, d, "ing")
        try:
            df = pro.weekly(trade_date=d, fields=FIELDS)
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
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
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

"""
接口：hk_hold，可以通过数据工具调试和查看数据
描述：获取沪深港股通持股明细，数据来源港交所
      说明：交易所于从2024年8月20开始停止发布日度北向资金数据，改为季度披露
限量：单次最多提取3800条记录，可循环调取，总量不限制
积分：用户积120积分可调取试用，2000积分可正常使用
接口文档: https://tushare.pro/document/2?doc_id=188
本地文档: docs/tushare/tushare.pro/document/20f4f.html

输入参数：code(str,N,交易所代码), ts_code(str,N,TS股票代码),
          trade_date(str,N,交易日期), start_date(str,N,开始日期),
          end_date(str,N,结束日期), exchange(str,N,类型SH/SZ/HK)
输出字段：code,trade_date,ts_code,name,vol,ratio,exchange

同步策略：按交易日增量（trade_date+ts_code+exchange 为主键，upsert）
表名：066_hk_hold
迁移说明：tushare schema 中无此表，无需迁移
用法: python 066_hk_hold.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "066_hk_hold"
DEFAULT_START = "20141117"  # 沪股通2014-11-17开通
LOOKBACK_DAYS = 3

FIELDS = "code,trade_date,ts_code,name,vol,ratio,exchange"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "exchange"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    code        VARCHAR(20),
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(15) NOT NULL,
    name        TEXT,
    vol         BIGINT,
    ratio       FLOAT,
    exchange    VARCHAR(5)  NOT NULL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, exchange)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""


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
            df = pro.hk_hold(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                if "vol" in df.columns:
                    df["vol"] = pd.to_numeric(df["vol"], errors="coerce").astype("Int64")
                if "ratio" in df.columns:
                    df["ratio"] = pd.to_numeric(df["ratio"], errors="coerce")
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

"""
接口：moneyflow_cnt_ths，可以通过数据工具调试和查看数据
描述：获取同花顺概念板块每日资金流向
限量：单次最大可调取5000条数据，可以根据日期和代码循环提取全部数据
权限：6000积分可以调取
接口文档: https://tushare.pro/document/2?doc_id=350
本地文档: docs/tushare/tushare.pro/document/2bd32.html

输入参数：ts_code(str,N,代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：trade_date,ts_code,name,lead_stock,close_price,pct_change,industry_index,
          company_num,pct_change_stock,net_buy_amount,net_sell_amount,net_amount

同步策略：按交易日增量（trade_date+ts_code 为主键，upsert）
表名：083_moneyflow_cnt_ths
迁移说明：新接口脚本，目标表不存在，无需迁移
用法: python 083_moneyflow_cnt_ths.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "083_moneyflow_cnt_ths"
DEFAULT_START = "20240901"
FIELDS = "trade_date,ts_code,name,lead_stock,close_price,pct_change,industry_index,company_num,pct_change_stock,net_buy_amount,net_sell_amount,net_amount"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date        DATE        NOT NULL,
    ts_code           VARCHAR(20) NOT NULL,
    name              VARCHAR(100),
    lead_stock        VARCHAR(100),
    close_price       FLOAT,
    pct_change        FLOAT,
    industry_index    FLOAT,
    company_num       INT,
    pct_change_stock  FLOAT,
    net_buy_amount    FLOAT,
    net_sell_amount   FLOAT,
    net_amount        FLOAT,
    update_time       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""

INT_COLS = ["company_num"]
FLOAT_COLS = ["close_price","pct_change","industry_index","pct_change_stock",
              "net_buy_amount","net_sell_amount","net_amount"]


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
            df = pro.moneyflow_cnt_ths(trade_date=d, fields=FIELDS)
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


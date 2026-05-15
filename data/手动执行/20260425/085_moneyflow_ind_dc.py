"""
接口：moneyflow_ind_dc，可以通过数据工具调试和查看数据
描述：获取东方财富板块资金流向，每天盘后更新
限量：单次最大可调取5000条数据，可以根据日期和代码循环提取全部数据
权限：6000积分可以调取
接口文档: https://tushare.pro/document/2?doc_id=352
本地文档: docs/tushare/tushare.pro/document/2aa61.html

输入参数：ts_code(str,N,代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期),
          content_type(str,N,资金类型：行业、概念、地域)
输出字段：trade_date,content_type,ts_code,name,pct_change,close,net_amount,net_amount_rate,
          buy_elg_amount,buy_elg_amount_rate,buy_lg_amount,buy_lg_amount_rate,
          buy_md_amount,buy_md_amount_rate,buy_sm_amount,buy_sm_amount_rate,
          buy_sm_amount_stock,rank

同步策略：按交易日增量，同时同步 行业/概念/地域（trade_date+content_type+ts_code 为主键，upsert）
表名：085_moneyflow_ind_dc
迁移说明：新接口脚本，目标表不存在，无需迁移
用法: python 085_moneyflow_ind_dc.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "085_moneyflow_ind_dc"
DEFAULT_START = "20240901"
FIELDS = "trade_date,content_type,ts_code,name,pct_change,close,net_amount,net_amount_rate,buy_elg_amount,buy_elg_amount_rate,buy_lg_amount,buy_lg_amount_rate,buy_md_amount,buy_md_amount_rate,buy_sm_amount,buy_sm_amount_rate,buy_sm_amount_stock,rank"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "content_type", "ts_code"]
CONTENT_TYPES = ["行业", "概念", "地域"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date           DATE         NOT NULL,
    content_type         VARCHAR(20)  NOT NULL,
    ts_code              VARCHAR(30)  NOT NULL,
    name                 VARCHAR(100),
    pct_change           FLOAT,
    close                FLOAT,
    net_amount           FLOAT,
    net_amount_rate      FLOAT,
    buy_elg_amount       FLOAT,
    buy_elg_amount_rate  FLOAT,
    buy_lg_amount        FLOAT,
    buy_lg_amount_rate   FLOAT,
    buy_md_amount        FLOAT,
    buy_md_amount_rate   FLOAT,
    buy_sm_amount        FLOAT,
    buy_sm_amount_rate   FLOAT,
    buy_sm_amount_stock  VARCHAR(100),
    rank                 INT,
    update_time          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, content_type, ts_code)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date_type ON {SCHEMA}."{TABLE}" (trade_date, content_type);
"""

INT_COLS = ["rank"]
FLOAT_COLS = ["pct_change","close","net_amount","net_amount_rate",
              "buy_elg_amount","buy_elg_amount_rate","buy_lg_amount","buy_lg_amount_rate",
              "buy_md_amount","buy_md_amount_rate","buy_sm_amount","buy_sm_amount_rate"]


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
            for content_type in CONTENT_TYPES:
                df = pro.moneyflow_ind_dc(trade_date=d, content_type=content_type, fields=FIELDS)
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


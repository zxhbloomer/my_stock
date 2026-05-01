"""
接口：moneyflow，可以通过数据工具调试和查看数据
描述：获取沪深A股票资金流向数据，分析大单小单成交情况，用于判别资金动向，数据开始于2010年
限量：单次最大提取6000行记录，总量不限制
权限：用户需要至少2000积分才可以调取，积分越多权限越大
接口文档: https://tushare.pro/document/2?doc_id=170
本地文档: docs/tushare/tushare.pro/document/2c865.html

输入参数：ts_code(str,N,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,buy_sm_vol,buy_sm_amount,sell_sm_vol,sell_sm_amount,
          buy_md_vol,buy_md_amount,sell_md_vol,sell_md_amount,
          buy_lg_vol,buy_lg_amount,sell_lg_vol,sell_lg_amount,
          buy_elg_vol,buy_elg_amount,sell_elg_vol,sell_elg_amount,
          net_mf_vol,net_mf_amount

同步策略：按交易日增量（ts_code+trade_date 为主键，upsert）
          注意：tushare.moneyflow 只有amount字段无vol字段，字段不匹配，无法迁移，需重新拉取
表名：080_moneyflow
迁移说明：tushare.moneyflow 字段不匹配（缺少 *_vol 字段），无法迁移，需重新拉取
用法: python 080_moneyflow.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "080_moneyflow"
DEFAULT_START = "20100104"
FIELDS = "ts_code,trade_date,buy_sm_vol,buy_sm_amount,sell_sm_vol,sell_sm_amount,buy_md_vol,buy_md_amount,sell_md_vol,sell_md_amount,buy_lg_vol,buy_lg_amount,sell_lg_vol,sell_lg_amount,buy_elg_vol,buy_elg_amount,sell_elg_vol,sell_elg_amount,net_mf_vol,net_mf_amount"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code          VARCHAR(15) NOT NULL,
    trade_date       DATE        NOT NULL,
    buy_sm_vol       BIGINT,
    buy_sm_amount    FLOAT,
    sell_sm_vol      BIGINT,
    sell_sm_amount   FLOAT,
    buy_md_vol       BIGINT,
    buy_md_amount    FLOAT,
    sell_md_vol      BIGINT,
    sell_md_amount   FLOAT,
    buy_lg_vol       BIGINT,
    buy_lg_amount    FLOAT,
    sell_lg_vol      BIGINT,
    sell_lg_amount   FLOAT,
    buy_elg_vol      BIGINT,
    buy_elg_amount   FLOAT,
    sell_elg_vol     BIGINT,
    sell_elg_amount  FLOAT,
    net_mf_vol       BIGINT,
    net_mf_amount    FLOAT,
    update_time      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

INT_COLS   = ["buy_sm_vol","sell_sm_vol","buy_md_vol","sell_md_vol",
              "buy_lg_vol","sell_lg_vol","buy_elg_vol","sell_elg_vol","net_mf_vol"]
FLOAT_COLS = ["buy_sm_amount","sell_sm_amount","buy_md_amount","sell_md_amount",
              "buy_lg_amount","sell_lg_amount","buy_elg_amount","sell_elg_amount","net_mf_amount"]


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
            df = pro.moneyflow(trade_date=d, fields=FIELDS)
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
        except Exception as e:
            print(f"  [SKIP] {d}: {e}")
            rows = 0
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()

"""
接口：moneyflow_hsgt，可以通过数据工具调试和查看数据
描述：获取沪股通、深股通、港股通每日资金流向数据，每次最多返回300条记录，总量不限制
权限：2000积分起，5000积分每分钟可提取500次
接口文档: https://tushare.pro/document/2?doc_id=47
本地文档: docs/tushare/tushare.pro/document/2696b.html

输入参数：trade_date(str,N,交易日期), start_date(str,N,开始日期),
          end_date(str,N,结束日期)
输出字段：trade_date,ggt_ss,ggt_sz,hgt,sgt,north_money,south_money

同步策略：按交易日增量（trade_date 为主键，upsert）
          注意：tushare.moneyflow_hsgt 字段完全匹配，可以迁移历史数据
表名：087_moneyflow_hsgt
迁移说明：tushare.moneyflow_hsgt 字段匹配，可迁移历史数据到 tushare_v2
用法: python 087_moneyflow_hsgt.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "087_moneyflow_hsgt"
DEFAULT_START = "20141117"  # 沪股通2014-11-17开通
FIELDS = "trade_date,ggt_ss,ggt_sz,hgt,sgt,north_money,south_money"
COLS   = FIELDS.split(",")
PK     = ["trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date   DATE  NOT NULL,
    ggt_ss       FLOAT,
    ggt_sz       FLOAT,
    hgt          FLOAT,
    sgt          FLOAT,
    north_money  FLOAT,
    south_money  FLOAT,
    update_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date)
);
"""

FLOAT_COLS = ["ggt_ss","ggt_sz","hgt","sgt","north_money","south_money"]


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

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    try:
        df = pro.moneyflow_hsgt(start_date=start, end_date=args.end, fields=FIELDS)
        if df is not None and not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
            for col in FLOAT_COLS:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=PK).drop_duplicates(subset=PK)
            rows = upsert_df(engine, df, TABLE, COLS, PK)
            mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
            print(f"\n[完成] upsert {rows:,} 条")
        else:
            mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
            print("[完成] 无数据")
    except Exception as e:
        print(f"[ERROR] {e}")
        raise


if __name__ == "__main__":
    main()

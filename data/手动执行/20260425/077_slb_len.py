"""
接口：slb_len，可以通过数据工具调试和查看数据
描述：转融通融资汇总
限量：单次最大可以提取5000行数据，可循环获取所有历史
权限：2000积分每分钟请求200次，5000积分500次请求
接口文档: https://tushare.pro/document/2?doc_id=331
本地文档: docs/tushare/tushare.pro/document/230ae.html

输入参数：trade_date(str,N,交易日期), start_date(str,N,开始日期),
          end_date(str,N,结束日期)
输出字段：trade_date,ob,auc_amount,repo_amount,repay_amount,cb

同步策略：按交易日增量（trade_date 为主键，upsert）
表名：077_slb_len
迁移说明：tushare schema 中无此表，无需迁移
用法: python 077_slb_len.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "077_slb_len"
DEFAULT_START = "20130201"
FIELDS = "trade_date,ob,auc_amount,repo_amount,repay_amount,cb"
COLS   = FIELDS.split(",")
PK     = ["trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date   DATE  NOT NULL,
    ob           FLOAT,
    auc_amount   FLOAT,
    repo_amount  FLOAT,
    repay_amount FLOAT,
    cb           FLOAT,
    update_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date)
);
"""

FLOAT_COLS = ["ob","auc_amount","repo_amount","repay_amount","cb"]


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
        df = pro.slb_len(start_date=start, end_date=args.end, fields=FIELDS)
        if df is not None and not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
            for col in FLOAT_COLS:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=PK).drop_duplicates(subset=PK)
            rows = upsert_df(engine, df, TABLE, COLS, PK)
            print(f"\n[完成] upsert {rows:,} 条")
        else:
            rows = 0
            print("[完成] 无数据")
        mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")  # 统一在 try 末尾
    except Exception as e:
        print(f"[ERROR] {e}")
        raise


if __name__ == "__main__":
    main()

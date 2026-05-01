"""
接口：cyq_perf，可以通过数据工具调试和查看数据
描述：获取A股每日筹码平均成本和胜率情况，每天18~19点左右更新，数据从2018年开始
来源：Tushare社区
限量：单次最大5000条，可以分页或者循环提取
积分：5000积分每天20000次，10000积分每天200000次，15000积分每天不限总量
接口文档: https://tushare.pro/document/2?doc_id=293
本地文档: docs/tushare/tushare.pro/document/22879.html

输入参数：ts_code(str,Y,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,his_low,his_high,cost_5pct,cost_15pct,cost_50pct,
          cost_85pct,cost_95pct,weight_avg,winner_rate

同步策略：按股票循环增量（ts_code+trade_date 为主键，upsert）
表名：061_cyq_perf
迁移说明：tushare.stock_chips 有数据，但字段不同（stock_chips是筹码分布，cyq_perf是胜率），无需迁移
用法: python 061_cyq_perf.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "061_cyq_perf"
DEFAULT_START = "20180101"  # 数据从2018年开始

FIELDS = "ts_code,trade_date,his_low,his_high,cost_5pct,cost_15pct,cost_50pct,cost_85pct,cost_95pct,weight_avg,winner_rate"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code      VARCHAR(15) NOT NULL,
    trade_date   DATE        NOT NULL,
    his_low      FLOAT,
    his_high     FLOAT,
    cost_5pct    FLOAT,
    cost_15pct   FLOAT,
    cost_50pct   FLOAT,
    cost_85pct   FLOAT,
    cost_95pct   FLOAT,
    weight_avg   FLOAT,
    winner_rate  FLOAT,
    update_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = ["his_low","his_high","cost_5pct","cost_15pct","cost_50pct",
              "cost_85pct","cost_95pct","weight_avg","winner_rate"]


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

    # 获取股票列表
    codes = get_stock_codes(pro)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        try:
            df = pro.cyq_perf(ts_code=code, start_date=start, end_date=args.end, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                for col in FLOAT_COLS:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=PK).drop_duplicates(subset=PK)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
        except Exception as e:
            print(f"  [SKIP] {code}: {e}")
            rows = 0
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 200 == 0:
            print(f"  [{i:4d}/{len(codes)}] {code}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()

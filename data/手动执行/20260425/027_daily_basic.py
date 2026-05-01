"""
接口：daily_basic，可以通过数据工具调试和查看数据
描述：获取全部股票每日重要的基本面指标，可用于选股分析、报表展示等。
      单次请求最大返回6000条数据，可按日线循环提取全部历史。
限量：单次最多返回6000条数据
权限：至少2000积分才可以调取，5000积分无总量限制
接口文档: https://tushare.pro/document/2?doc_id=32
本地文档: docs/tushare/tushare.pro/document/26cf6.html

输入参数：ts_code(str,N,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,
          pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,
          free_share,total_mv,circ_mv

同步策略：按交易日增量（trade_date 为主键维度，upsert）
表名：027_daily_basic
迁移说明：tushare.daily_basic 有数据，字段完全一致，可直接迁移
用法: python 027_daily_basic.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "027_daily_basic"
DEFAULT_START = "20100729"
FIELDS = "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code        VARCHAR(15) NOT NULL,
    trade_date     DATE        NOT NULL,
    close          FLOAT,
    turnover_rate  FLOAT,
    turnover_rate_f FLOAT,
    volume_ratio   FLOAT,
    pe             FLOAT,
    pe_ttm         FLOAT,
    pb             FLOAT,
    ps             FLOAT,
    ps_ttm         FLOAT,
    dv_ratio       FLOAT,
    dv_ttm         FLOAT,
    total_share    FLOAT,
    float_share    FLOAT,
    free_share     FLOAT,
    total_mv       FLOAT,
    circ_mv        FLOAT,
    update_time    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = ["close","turnover_rate","turnover_rate_f","volume_ratio","pe","pe_ttm",
              "pb","ps","ps_ttm","dv_ratio","dv_ttm","total_share","float_share",
              "free_share","total_mv","circ_mv"]


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
            df = pro.daily_basic(trade_date=d, fields=FIELDS)
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

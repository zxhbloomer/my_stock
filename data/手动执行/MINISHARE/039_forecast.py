"""
接口：forecast，可以通过数据工具调试和查看数据
描述：获取业绩预告数据
限量：用户需要至少2000积分才可以调取；当前接口只能按单只股票获取其历史数据，
      如需获取某一季度全部上市公司数据，请使用forecast_vip接口（需5000积分）
权限：2000积分以上可以调取
接口文档: https://tushare.pro/document/2?doc_id=45
本地文档: docs/tushare/tushare.pro/document/24e95.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          start_date(str,N,公告开始日期), end_date(str,N,公告结束日期),
          period(str,N,报告期), type(str,N,预告类型)
输出字段：ts_code,ann_date,end_date,type,p_change_min,p_change_max,
          net_profit_min,net_profit_max,last_parent_net,first_ann_date,
          summary,change_reason

同步策略：按股票循环增量（ts_code+ann_date+end_date 为主键，upsert）
表名：039_forecast
迁移说明：tushare.forecast 有数据，字段完全一致，可直接迁移
用法: python 039_forecast.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "039_forecast"
DEFAULT_START = "20100101"
FIELDS = "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,last_parent_net,first_ann_date,summary,change_reason"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "ann_date", "end_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code         VARCHAR(15) NOT NULL,
    ann_date        DATE        NOT NULL,
    end_date        DATE        NOT NULL,
    type            VARCHAR(20),
    p_change_min    FLOAT,
    p_change_max    FLOAT,
    net_profit_min  FLOAT,
    net_profit_max  FLOAT,
    last_parent_net FLOAT,
    first_ann_date  DATE,
    summary         TEXT,
    change_reason   TEXT,
    update_time     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, ann_date, end_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_end ON {SCHEMA}."{TABLE}" (end_date);
"""

DATE_COLS  = ["ann_date", "end_date", "first_ann_date"]
FLOAT_COLS = ["p_change_min","p_change_max","net_profit_min","net_profit_max","last_parent_net"]


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

    codes = get_stock_codes(pro)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        try:
            df = pro.forecast(ts_code=code, start_date=start, end_date=args.end, fields=FIELDS)
            if df is not None and not df.empty:
                for col in DATE_COLS:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors="coerce")
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

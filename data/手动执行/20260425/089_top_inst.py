"""
接口：top_inst，可以通过数据工具调试和查看数据
描述：龙虎榜机构成交明细
限量：单次请求最大返回10000行数据，可根据参数循环获取全部历史
权限：用户需要至少5000积分才可以调取
接口文档: https://tushare.pro/document/2?doc_id=107
本地文档: docs/tushare/tushare.pro/document/2d1f6.html

输入参数：trade_date(str,Y,交易日期), ts_code(str,N,TS代码)
输出字段：trade_date,ts_code,exalter,side,buy,buy_rate,sell,sell_rate,net_buy,reason

同步策略：按交易日增量；表使用数据库自增主键，按 trade_date 整日删除后重插，避免臆造业务唯一键
表名：089_top_inst
迁移说明：tushare schema 中无此表，无需迁移
用法: python 089_top_inst.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "089_top_inst"
DEFAULT_START = "20050101"
FIELDS = "trade_date,ts_code,exalter,side,buy,buy_rate,sell,sell_rate,net_buy,reason"
COLS   = FIELDS.split(",")

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    id          BIGSERIAL PRIMARY KEY,
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(15) NOT NULL,
    exalter     TEXT,
    side        VARCHAR(5),
    buy         FLOAT,
    buy_rate    FLOAT,
    sell        FLOAT,
    sell_rate   FLOAT,
    net_buy     FLOAT,
    reason      TEXT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_089_top_inst_date_ts ON {SCHEMA}."{TABLE}" (trade_date, ts_code);
CREATE INDEX IF NOT EXISTS idx_089_top_inst_date_exalter ON {SCHEMA}."{TABLE}" (trade_date, exalter);
"""

FLOAT_COLS = ["buy","buy_rate","sell","sell_rate","net_buy"]


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
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS, allow_extra_cols={"id"})

    start = args.start or get_start(engine)
    dates = get_trade_dates(pro, start, args.end)

    total_rows, t0 = 0, datetime.now()
    for i, d in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, d, "ing")
        try:
            df = pro.top_inst(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                for col in FLOAT_COLS:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["trade_date", "ts_code"])
                rows = replace_date_df(engine, df, TABLE, COLS, d)
                total_rows += rows
            else:
                rows = replace_date_df(engine, df, TABLE, COLS, d)
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
        except Exception:
            raise
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        # time.sleep(0.3)

    print(f"\n[完成] replace {total_rows:,} 条")


if __name__ == "__main__":
    main()

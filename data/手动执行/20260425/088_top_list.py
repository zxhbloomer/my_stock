"""
接口：top_list，可以通过数据工具调试和查看数据
描述：龙虎榜每日交易明细
数据历史：2005年至今
限量：单次请求返回最大10000行数据，可通过参数循环获取全部历史
权限：用户需要至少2000积分才可以调取
接口文档: https://tushare.pro/document/2?doc_id=106
本地文档: docs/tushare/tushare.pro/document/2eb1a.html

输入参数：trade_date(str,Y,交易日期), ts_code(str,N,股票代码)
输出字段：trade_date,ts_code,name,close,pct_change,turnover_rate,amount,
          l_sell,l_buy,l_amount,net_amount,net_rate,amount_rate,float_values,reason

同步策略：按交易日增量；表使用数据库自增主键，按 trade_date 整日删除后重插，避免臆造业务唯一键
表名：088_top_list
迁移说明：tushare schema 中无此表，无需迁移
用法: python 088_top_list.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "088_top_list"
DEFAULT_START = "20050101"
FIELDS = "trade_date,ts_code,name,close,pct_change,turnover_rate,amount,l_sell,l_buy,l_amount,net_amount,net_rate,amount_rate,float_values,reason"
COLS   = FIELDS.split(",")

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    id          BIGSERIAL PRIMARY KEY,
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(15) NOT NULL,
    name        VARCHAR(50),
    close       FLOAT,
    pct_change  FLOAT,
    turnover_rate FLOAT,
    amount      FLOAT,
    l_sell      FLOAT,
    l_buy       FLOAT,
    l_amount    FLOAT,
    net_amount  FLOAT,
    net_rate    FLOAT,
    amount_rate FLOAT,
    float_values FLOAT,
    reason      TEXT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_088_top_list_date_ts ON {SCHEMA}."{TABLE}" (trade_date, ts_code);
"""

FLOAT_COLS = ["close","pct_change","turnover_rate","amount","l_sell","l_buy",
              "l_amount","net_amount","net_rate","amount_rate","float_values"]


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
            df = pro.top_list(trade_date=d, fields=FIELDS)
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

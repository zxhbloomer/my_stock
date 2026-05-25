"""
接口：ths_index，可以通过数据工具调试和查看数据
描述：获取同花顺板块指数，包括概念、行业、特色指数
限量：单次最大返回5000行数据，一次可提取全部数据，请勿循环提取
权限：6000积分
接口文档: https://tushare.pro/document/2?doc_id=259
本地文档: docs/tushare/tushare.pro/document/29dff.html

同步策略：静态全量（全删全插）
表名：094_ths_index
用法: python 094_ths_index.py
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "094_ths_index"
FIELDS = "ts_code,name,count,exchange,list_date,type"
COLS   = FIELDS.split(",")
PK     = ["ts_code"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(15) NOT NULL,
    name        VARCHAR(100),
    count       INT,
    exchange    VARCHAR(10),
    list_date   DATE,
    type        VARCHAR(10),
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_type ON {SCHEMA}."{TABLE}" (type);
"""


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ing")
    df = pro.ths_index(fields=FIELDS)
    if df is not None and not df.empty:
        df["list_date"] = pd.to_datetime(df["list_date"], errors="coerce")
        df["count"] = pd.to_numeric(df["count"], errors="coerce").astype("Int64")
        df = df.dropna(subset=PK).drop_duplicates(subset=PK)
        rows = truncate_and_insert(engine, df, TABLE, COLS)
    else:
        rows = 0
    mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ok")
    print(f"\n[完成] 全量插入 {rows:,} 条")


if __name__ == "__main__":
    main()

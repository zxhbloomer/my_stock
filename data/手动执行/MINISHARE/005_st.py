"""
接口：st（ST风险警示板股票）
描述：ST风险警示板股票列表
限量：单次最大1000，可根据股票代码循环获取历史数据
权限：6000积分可提取数据
接口文档: https://tushare.pro/document/2?doc_id=423
本地文档: docs/tushare/tushare.pro/document/22ddb.html

同步策略：全删全插（无明确日期主键，数据量小，直接全量刷新）
表名：005_st
迁移说明：tushare schema 中无此表，无需迁移
用法: python 005_st.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE  = "005_st"
FIELDS = "ts_code,name,pub_date,imp_date,st_tpye,st_reason,st_explain"
COLS   = FIELDS.split(",")

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code    VARCHAR(15) NOT NULL,
    name       VARCHAR(50),
    pub_date   DATE,
    imp_date   DATE,
    st_tpye    VARCHAR(20),
    st_reason  TEXT,
    st_explain TEXT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, imp_date)
);
"""


def main():
    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    df = pro.st(fields=FIELDS)
    if df is None or df.empty:
        print("[WARN] 返回空数据")
        return

    for col in ["pub_date", "imp_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df.dropna(subset=["ts_code", "imp_date"]).drop_duplicates(subset=["ts_code", "imp_date"])

    rows = truncate_and_insert(engine, df, TABLE, COLS)
    print(f"[完成] {rows:,} 条")


if __name__ == "__main__":
    main()

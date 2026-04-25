"""
接口：index_basic，可以通过数据工具调试和查看数据
描述：获取指数基础信息
权限：无积分要求
接口文档: https://tushare.pro/document/2?doc_id=94
本地文档: docs/tushare/tushare.pro/document/2353a.html

输入参数：ts_code(str,N,指数代码), name(str,N,指数简称),
          market(str,N,交易所或服务商默认SSE), publisher(str,N,发布商),
          category(str,N,指数类别)
输出字段：ts_code,name,fullname,market,publisher,index_type,category,
          base_date,base_point,list_date,weight_rule,desc,exp_date

同步策略：全量删除重新插入（无日期维度，参考数据）
          market 包括：MSCI/CSI/SSE/SZSE/CICC/SW/OTH
表名：121_index_basic
迁移说明：tushare schema 中无此表，无需迁移
用法: python 121_index_basic.py
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE  = "121_index_basic"
FIELDS = "ts_code,name,fullname,market,publisher,index_type,category,base_date,base_point,list_date,weight_rule,desc,exp_date"
COLS   = FIELDS.split(",")
PK     = ["ts_code"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(20)  NOT NULL,
    name        VARCHAR(100),
    fullname    VARCHAR(200),
    market      VARCHAR(20),
    publisher   VARCHAR(100),
    index_type  VARCHAR(50),
    category    VARCHAR(50),
    base_date   VARCHAR(10),
    base_point  FLOAT,
    list_date   VARCHAR(10),
    weight_rule VARCHAR(100),
    "desc"      TEXT,
    exp_date    VARCHAR(10),
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_market ON {SCHEMA}."{TABLE}" (market);
"""

MARKETS = ["MSCI", "CSI", "SSE", "SZSE", "CICC", "SW", "OTH"]


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    all_dfs = []
    for market in MARKETS:
        try:
            df = pro.index_basic(market=market, fields=FIELDS)
            if df is not None and not df.empty:
                all_dfs.append(df)
                print(f"  {market}: {len(df)} 条")
        except Exception as e:
            print(f"  [SKIP] {market}: {e}")

    if not all_dfs:
        print("[完成] 无数据")
        return

    df_all = pd.concat([df.astype(object) for df in all_dfs], ignore_index=True)
    if "base_point" in df_all.columns:
        df_all["base_point"] = pd.to_numeric(df_all["base_point"], errors="coerce")
    df_all = df_all.drop_duplicates(subset=PK)

    rows = truncate_and_insert(engine, df_all, TABLE, COLS)
    print(f"\n[完成] 全量插入 {rows:,} 条")


if __name__ == "__main__":
    main()

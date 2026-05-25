"""
接口：index_member_all，可以通过数据工具调试和查看数据
描述：按三级分类提取申万行业成分，可提供某个分类的所有成分，也可按股票代码提取所属分类
限量：单次最大2000行，总量不限制
权限：用户需2000积分可调取
接口文档: https://tushare.pro/document/2?doc_id=335
本地文档: docs/tushare/tushare.pro/document/23bd0.html

输入参数：l1_code(str,N,一级行业代码), l2_code(str,N,二级行业代码),
          l3_code(str,N,三级行业代码), ts_code(str,N,股票代码),
          is_new(str,N,是否最新默认Y)
输出字段：l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,
          ts_code,name,in_date,out_date,is_new

同步策略：按申万2021版一级行业分片拉取最新行业归属后全删全插。
          不直接全市场拉取，避免触发单次2000行上限。
          主键：ts_code+l3_code+in_date
表名：131_index_member_all
迁移说明：tushare schema 中无可用源表，无需迁移
用法: python 131_index_member_all.py
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE  = "131_index_member_all"
FIELDS = "l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,ts_code,name,in_date,out_date,is_new"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "l3_code", "in_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    l1_code     VARCHAR(20),
    l1_name     VARCHAR(50),
    l2_code     VARCHAR(20),
    l2_name     VARCHAR(50),
    l3_code     VARCHAR(20) NOT NULL,
    l3_name     VARCHAR(100),
    ts_code     VARCHAR(15) NOT NULL,
    name        VARCHAR(100),
    in_date     VARCHAR(10) NOT NULL,
    out_date    VARCHAR(10),
    is_new      VARCHAR(5),
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, l3_code, in_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_l1 ON {SCHEMA}."{TABLE}" (l1_code);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_l3 ON {SCHEMA}."{TABLE}" (l3_code);
"""


def fetch_sw2021_l1_codes(pro):
    df = pro.index_classify(
        level="L1",
        src="SW2021",
        fields="index_code,industry_name,parent_code,level,industry_code,is_pub,src",
    )
    if df is None or df.empty or "index_code" not in df.columns:
        raise RuntimeError("index_classify(level='L1', src='SW2021') 未返回行业代码")
    return df["index_code"].dropna().astype(str).drop_duplicates().tolist()


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ing")
    codes = fetch_sw2021_l1_codes(pro)
    print(f"共 {len(codes)} 个申万2021一级行业")

    all_dfs = []
    for i, code in enumerate(codes, 1):
        df = pro.index_member_all(l1_code=code, is_new="Y", fields=FIELDS)
        rows = 0 if df is None else len(df)
        if df is not None and not df.empty:
            all_dfs.append(df)
        print(f"  [{i:2d}/{len(codes)}] {code}  {rows}条", flush=True)

    if not all_dfs:
        mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ok")
        print("[完成] 无数据")
        return

    df_all = pd.concat(all_dfs, ignore_index=True)
    df_all["in_date"] = df_all["in_date"].fillna("19900101").astype(str)
    if "out_date" in df_all.columns:
        df_all["out_date"] = df_all["out_date"].where(df_all["out_date"].notna(), None)
    df_all = df_all.dropna(subset=["ts_code","l3_code"]).drop_duplicates(subset=PK)

    rows = truncate_and_insert(engine, df_all, TABLE, COLS)
    mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ok")
    print(f"\n[完成] 全量插入 {rows:,} 条")


if __name__ == "__main__":
    main()

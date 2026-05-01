"""
接口：ci_index_member，可以通过数据工具调试和查看数据
描述：按三级分类提取中信行业成分，可提供某个分类的所有成分，也可按股票代码提取所属分类
限量：单次最大5000行，总量不限制
权限：用户需5000积分可调取
接口文档: https://tushare.pro/document/2?doc_id=373
本地文档: docs/tushare/tushare.pro/document/2d57d.html

输入参数：l1_code(str,N,一级行业代码), l2_code(str,N,二级行业代码),
          l3_code(str,N,三级行业代码), ts_code(str,N,股票代码),
          is_new(str,N,是否最新默认Y)
输出字段：l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,
          ts_code,name,in_date,out_date,is_new

同步策略：全量删除重新插入（成分股变动不频繁，全量更新保证准确性）
          主键：ts_code+l3_code+in_date
表名：134_ci_index_member
迁移说明：tushare schema 中无此表，无需迁移
用法: python 134_ci_index_member.py
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE  = "134_ci_index_member"
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
    l3_name     VARCHAR(50),
    ts_code     VARCHAR(15) NOT NULL,
    name        VARCHAR(50),
    in_date     VARCHAR(10) NOT NULL,
    out_date    VARCHAR(10),
    is_new      VARCHAR(5),
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, l3_code, in_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_l3 ON {SCHEMA}."{TABLE}" (l3_code);
"""


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    # 获取所有成分（is_new=N 包含历史，默认只返回最新）
    all_dfs = []
    for is_new in ["Y", "N"]:
        try:
            df = pro.ci_index_member(is_new=is_new, fields=FIELDS)
            if df is not None and not df.empty:
                all_dfs.append(df)
                print(f"  is_new={is_new}: {len(df)} 条")
        except Exception as e:
            print(f"  [SKIP] is_new={is_new}: {e}")

    if not all_dfs:
        print("[完成] 无数据")
        return

    df_all = pd.concat(all_dfs, ignore_index=True)
    # in_date 可能为空，填充默认值
    if "in_date" in df_all.columns:
        df_all["in_date"] = df_all["in_date"].fillna("19900101").astype(str)
    df_all = df_all.dropna(subset=["ts_code","l3_code"]).drop_duplicates(subset=PK)

    rows = truncate_and_insert(engine, df_all, TABLE, COLS)
    print(f"\n[完成] 全量插入 {rows:,} 条")


if __name__ == "__main__":
    main()

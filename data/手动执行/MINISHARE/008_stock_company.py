"""
接口：stock_company，可以通过数据工具调试和查看数据。
描述：获取上市公司基础信息，单次提取4500条，可以根据交易所分批提取
限量：单次提取4500条，按交易所分批
权限：用户需要至少120积分才可以调取
接口文档: https://tushare.pro/document/2?doc_id=112
本地文档: docs/tushare/tushare.pro/document/2cf26.html

同步策略：全删全插（公司基础信息，静态数据，按交易所分批全量刷新）
表名：008_stock_company
迁移说明：tushare schema 中无此表，无需迁移
用法: python 008_stock_company.py
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE  = "008_stock_company"
FIELDS = "ts_code,com_name,com_id,exchange,chairman,manager,secretary,reg_capital,setup_date,province,city,introduction,website,email,office,employees,main_business,business_scope"
COLS   = FIELDS.split(",")

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code        VARCHAR(15) NOT NULL PRIMARY KEY,
    com_name       VARCHAR(100),
    com_id         VARCHAR(30),
    exchange       VARCHAR(10),
    chairman       VARCHAR(50),
    manager        VARCHAR(50),
    secretary      VARCHAR(50),
    reg_capital    FLOAT,
    setup_date     DATE,
    province       VARCHAR(20),
    city           VARCHAR(20),
    introduction   TEXT,
    website        VARCHAR(100),
    email          VARCHAR(100),
    office         VARCHAR(200),
    employees      FLOAT,
    main_business  TEXT,
    business_scope TEXT,
    update_time    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def main():
    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    all_dfs = []
    for exchange in ["SSE", "SZSE", "BSE"]:
        try:
            df = pro.stock_company(exchange=exchange, fields=FIELDS)
            if df is not None and not df.empty:
                all_dfs.append(df)
                print(f"  {exchange}: {len(df)} 条")
        except Exception as e:
            print(f"  [SKIP] {exchange}: {e}")

    if not all_dfs:
        print("[WARN] 返回空数据")
        return

    result = pd.concat(all_dfs, ignore_index=True)
    result["setup_date"] = pd.to_datetime(result["setup_date"], errors="coerce")
    result["reg_capital"] = pd.to_numeric(result["reg_capital"], errors="coerce")
    result["employees"]   = pd.to_numeric(result["employees"],   errors="coerce")
    result = result.drop_duplicates(subset=["ts_code"])

    rows = truncate_and_insert(engine, result, TABLE, COLS)
    print(f"[完成] {rows:,} 条")


if __name__ == "__main__":
    main()

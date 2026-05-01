"""
接口：stock_basic，可以通过数据工具调试和查看数据
描述：获取基础信息数据，包括股票代码、名称、上市日期、退市日期等
限量：每次最多返回6000行数据（覆盖全市场A股，会随股票总数增长而增加）
权限：2000积分起，每分钟请求50次。此接口是基础信息，调取一次就可以拉取完，建议保存到本地存储后使用
接口文档: https://tushare.pro/document/2?doc_id=25
本地文档: docs/tushare/tushare.pro/document/240cd.html

同步策略：全删全插（静态基础信息，无日期维度，每次全量刷新）
表名：001_stock_basic
迁移说明：tushare.stock_basic 已有数据，首次运行前执行迁移（见脚本末尾注释）
用法: python 001_stock_basic.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE  = "001_stock_basic"
FIELDS = "ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type"
COLS   = FIELDS.split(",")

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code      VARCHAR(15) NOT NULL PRIMARY KEY,
    symbol       VARCHAR(10),
    name         VARCHAR(50),
    area         VARCHAR(20),
    industry     VARCHAR(50),
    fullname     VARCHAR(100),
    enname       VARCHAR(200),
    cnspell      VARCHAR(20),
    market       VARCHAR(20),
    exchange     VARCHAR(10),
    curr_type    VARCHAR(10),
    list_status  VARCHAR(5),
    list_date    DATE,
    delist_date  DATE,
    is_hs        VARCHAR(5),
    act_name     VARCHAR(100),
    act_ent_type VARCHAR(20),
    update_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def main():
    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    # Minishare 默认上限5000，传 limit=10000 确保取到全量（当前约5835只）
    result = pro.stock_basic(fields=FIELDS, limit=10000)
    if result is None or result.empty:
        print("[WARN] 返回空数据")
        return
    for col in ['list_date', 'delist_date']:
        result[col] = pd.to_datetime(result[col], errors='coerce')

    rows = truncate_and_insert(engine, result, TABLE, COLS)
    print(f"[完成] {rows:,} 条（含上市L/退市D/暂停P）")


if __name__ == "__main__":
    main()

# ── 迁移说明 ──────────────────────────────────────────
# tushare.stock_basic 已有数据，可用以下 SQL 一次性迁移：
#
# INSERT INTO tushare_v2."001_stock_basic"
#   (ts_code,symbol,name,area,industry,cnspell,market,exchange,
#    curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type)
# SELECT ts_code,symbol,name,area,industry,cnspell,market,exchange,
#        curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type
# FROM tushare.stock_basic
# ON CONFLICT (ts_code) DO NOTHING;
#
# 注：tushare.stock_basic 缺少 fullname/enname 字段，迁移后建议重新全量拉取覆盖。
# ─────────────────────────────────────────────────────

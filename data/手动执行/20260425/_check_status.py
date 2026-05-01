"""临时脚本：检查sync_status表状态 + 所有业务表数据清单"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import get_engine, SCHEMA
from sqlalchemy import text
import pandas as pd

engine = get_engine()

# 1. 检查 sync_status 表
with engine.connect() as conn:
    r = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        f"WHERE table_schema='{SCHEMA}' AND table_name='sync_status'"
    )).fetchone()
    exists = r[0] == 1
    print(f"sync_status表存在: {exists}")
    if exists:
        rows = conn.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.sync_status")).fetchone()
        print(f"sync_status记录数: {rows[0]}")
        if rows[0] > 0:
            data = conn.execute(text(
                f"SELECT script_name, table_name, sync_date, status, updated_at "
                f"FROM {SCHEMA}.sync_status ORDER BY updated_at DESC"
            )).fetchall()
            print("\n--- sync_status 内容 ---")
            for row in data:
                print(row)

# 2. 所有业务表清单
# 脚本名 -> (表名, 日期列)
SCRIPT_TABLE_MAP = [
    ("001_stock_basic.py",    "001_stock_basic",    None),
    ("003_trade_cal.py",      "003_trade_cal",      "cal_date"),
    ("004_stock_st.py",       "004_stock_st",       "trade_date"),
    ("005_st.py",             "005_st",             None),
    ("006_stock_hsgt.py",     "006_stock_hsgt",     "trade_date"),
    ("008_stock_company.py",  "008_stock_company",  None),
    ("014_daily.py",          "014_daily",          "trade_date"),
    ("018_weekly.py",         "018_weekly",         "trade_date"),
    ("019_monthly.py",        "019_monthly",        "trade_date"),
    ("023_adj_factor.py",     "023_adj_factor",     "trade_date"),
    ("027_daily_basic.py",    "027_daily_basic",    "trade_date"),
    ("029_stk_limit.py",      "029_stk_limit",      "trade_date"),
    ("030_suspend_d.py",      "030_suspend_d",      "trade_date"),
    ("031_hsgt_top10.py",     "031_hsgt_top10",     "trade_date"),
    ("032_ggt_top10.py",      "032_ggt_top10",      "trade_date"),
    ("036_income.py",         "036_income",         "ann_date"),
    ("037_balancesheet.py",   "037_balancesheet",   "ann_date"),
    ("038_cashflow.py",       "038_cashflow",       "ann_date"),
    ("039_forecast.py",       "039_forecast",       "ann_date"),
    ("040_express.py",        "040_express",        "ann_date"),
    ("041_dividend.py",       "041_dividend",       "ann_date"),
    ("042_fina_indicator.py", "042_fina_indicator", "ann_date"),
    ("043_fina_audit.py",     "043_fina_audit",     "ann_date"),
    ("061_cyq_perf.py",       "061_cyq_perf",       "trade_date"),
    ("062_cyq_chips.py",      "062_cyq_chips",      "trade_date"),
    ("063_stk_factor_pro.py", "063_stk_factor_pro", "trade_date"),
    ("066_hk_hold.py",        "066_hk_hold",        "trade_date"),
    ("068_stk_auction_c.py",  "068_stk_auction_c",  "trade_date"),
    ("069_stk_nineturn.py",   "069_stk_nineturn",   "trade_date"),
    ("073_margin.py",         "073_margin",         "trade_date"),
    ("074_margin_detail.py",  "074_margin_detail",  "trade_date"),
    ("075_margin_secs.py",    "075_margin_secs",    "trade_date"),
    ("076_slb_sec.py",        "076_slb_sec",        "trade_date"),
    ("077_slb_len.py",        "077_slb_len",        "trade_date"),
    ("078_slb_sec_detail.py", "078_slb_sec_detail", "trade_date"),
    ("080_moneyflow.py",      "080_moneyflow",      "trade_date"),
    ("081_moneyflow_ths.py",  "081_moneyflow_ths",  "trade_date"),
    ("087_moneyflow_hsgt.py", "087_moneyflow_hsgt", "trade_date"),
    ("121_index_basic.py",    "121_index_basic",    None),
    ("122_index_daily.py",    "122_index_daily",    "trade_date"),
    ("129_index_dailybasic.py","129_index_dailybasic","trade_date"),
    ("134_ci_index_member.py","134_ci_index_member",None),
    ("135_ci_daily.py",       "135_ci_daily",       "trade_date"),
    ("137_idx_factor_pro.py", "137_idx_factor_pro", "trade_date"),
    ("138_daily_info.py",     "138_daily_info",     "trade_date"),
    ("139_sz_daily_info.py",  "139_sz_daily_info",  "trade_date"),
]

print(f"\n{'脚本名称':<30} {'表名称':<25} {'最新数据':<12} {'数据条数':>10}")
print("-" * 82)

with engine.connect() as conn:
    for script, table, date_col in SCRIPT_TABLE_MAP:
        try:
            cnt = conn.execute(text(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')).fetchone()[0]
            if date_col:
                max_d = conn.execute(text(f'SELECT MAX("{date_col}") FROM {SCHEMA}."{table}"')).fetchone()[0]
                max_d = str(max_d)[:10] if max_d else "NULL"
            else:
                max_d = "N/A"
            print(f"{script:<30} {table:<25} {max_d:<12} {cnt:>10,}")
        except Exception as e:
            print(f"{script:<30} {table:<25} {'表不存在':<12} {'—':>10}")

"""查询所有脚本对应表的最新数据日期"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import get_engine, SCHEMA
from sqlalchemy import text

engine = get_engine()

# 脚本 -> (实际表名, 日期列)  — 表名以数据库实际为准
SCRIPT_TABLE_MAP = [
    ("001_stock_basic.py",     "001_stock_basic",     None),
    ("003_trade_cal.py",       "003_trade_cal",       "cal_date"),
    ("004_stock_st.py",        "004_stock_st",        "trade_date"),
    ("005_st.py",              "005_st",              None),
    ("006_stock_hsgt.py",      "006_stock_hsgt",      "trade_date"),
    ("008_stock_company.py",   "008_stock_company",   None),
    ("014_daily.py",           "014_daily",           "trade_date"),
    ("018_weekly.py",          "018_weekly",          "trade_date"),
    ("019_monthly.py",         "019_monthly",         "trade_date"),
    ("023_adj_factor.py",      "023_adj_factor",      "trade_date"),
    ("027_daily_basic.py",     "027_daily_basic",     "trade_date"),
    ("029_stk_limit.py",       "029_stk_limit",       "trade_date"),
    ("030_suspend_d.py",       "030_suspend_d",       "trade_date"),
    ("031_hsgt_top10.py",      "031_hsgt_top10",      "trade_date"),
    ("032_ggt_top10.py",       "032_ggt_top10",       "trade_date"),
    ("036_income.py",          "036_income",          "ann_date"),
    ("037_balancesheet.py",    "037_balancesheet",    "ann_date"),
    ("038_cashflow.py",        "038_cashflow",        "ann_date"),
    ("039_forecast.py",        "039_forecast",        "ann_date"),
    ("040_express.py",         "040_express",         "ann_date"),
    ("041_dividend.py",        "041_dividend",        "ann_date"),
    ("042_fina_indicator.py",  "042_fina_indicator",  "ann_date"),
    ("043_fina_audit.py",      "043_fina_audit",      "ann_date"),
    ("061_cyq_perf.py",        "061_cyq_perf",        "trade_date"),
    ("062_cyq_chips.py",       "062_cyq_chips",       "trade_date"),
    ("063_stk_factor_pro.py",  "063_stk_factor_pro",  "trade_date"),
    ("066_hk_hold.py",         "066_hk_hold",         "trade_date"),
    ("068_stk_auction_c.py",   "067_stk_auction_o",   "trade_date"),  # 表名不同
    ("069_stk_nineturn.py",    "069_stk_nineturn",    "trade_date"),
    ("073_margin.py",          "073_margin",          "trade_date"),
    ("074_margin_detail.py",   "074_margin_detail",   "trade_date"),
    ("075_margin_secs.py",     "075_margin_secs",     "trade_date"),
    ("076_slb_sec.py",         "076_slb_sec",         "trade_date"),
    ("077_slb_len.py",         "077_slb_len",         "trade_date"),
    ("078_slb_sec_detail.py",  "078_slb_sec_detail",  "trade_date"),
    ("080_moneyflow.py",       "080_moneyflow",       "trade_date"),
    ("081_moneyflow_ths.py",   "081_moneyflow_ths",   "trade_date"),
    ("087_moneyflow_hsgt.py",  "087_moneyflow_hsgt",  "trade_date"),
    ("121_index_basic.py",     "121_index_basic",     None),
    ("122_index_daily.py",     "122_index_daily",     "trade_date"),
    ("129_index_dailybasic.py","129_index_dailybasic","trade_date"),
    ("134_ci_index_member.py", "134_ci_index_member", None),
    ("135_ci_daily.py",        "135_ci_daily",        "trade_date"),
    ("137_idx_factor_pro.py",  "137_idx_factor_pro",  "trade_date"),
    ("138_daily_info.py",      "138_daily_info",      "trade_date"),
    ("139_sz_daily_info.py",   "139_sz_daily_info",   "trade_date"),
]

print(f"{'脚本名称':<30} {'表名称':<25} {'最新数据':<12} {'数据条数':>12}")
print("-" * 85)

with engine.connect() as conn:
    all_tables = {r[0] for r in conn.execute(text(
        f"SELECT table_name FROM information_schema.tables WHERE table_schema='{SCHEMA}'"
    )).fetchall()}

    for script, table, date_col in SCRIPT_TABLE_MAP:
        if table not in all_tables:
            print(f"{script:<30} {table:<25} {'表不存在':<12} {'—':>12}")
            continue
        cnt = conn.execute(text(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')).fetchone()[0]
        if date_col and cnt > 0:
            max_d = conn.execute(text(f'SELECT MAX("{date_col}") FROM {SCHEMA}."{table}"')).fetchone()[0]
            max_d = str(max_d)[:10] if max_d else "NULL"
        elif cnt == 0:
            max_d = "空表"
        else:
            max_d = "N/A"
        print(f"{script:<30} {table:<25} {max_d:<12} {cnt:>12,}")

    print(f"\nsync_status 表存在: {'sync_status' in all_tables}")

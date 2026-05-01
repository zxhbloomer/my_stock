"""查询每个表最新2个日期的数据条数，用于验证数据完整性"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import get_engine, SCHEMA
from sqlalchemy import text

engine = get_engine()

# (脚本名, 表名, 日期列)  — 无日期列的A类跳过
SCRIPT_TABLE_MAP = [
    ("003_trade_cal.py",       "003_trade_cal",       "cal_date"),
    ("004_stock_st.py",        "004_stock_st",        "trade_date"),
    ("006_stock_hsgt.py",      "006_stock_hsgt",      "trade_date"),
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
    ("122_index_daily.py",     "122_index_daily",     "trade_date"),
    ("129_index_dailybasic.py","129_index_dailybasic","trade_date"),
    ("135_ci_daily.py",        "135_ci_daily",        "trade_date"),
]

print(f"{'脚本':<30} {'表名':<25} {'日期1':<12} {'条数1':>8}  {'日期2':<12} {'条数2':>8}")
print("-" * 105)

with engine.connect() as conn:
    all_tables = {r[0] for r in conn.execute(text(
        f"SELECT table_name FROM information_schema.tables WHERE table_schema='{SCHEMA}'"
    )).fetchall()}

    for script, table, date_col in SCRIPT_TABLE_MAP:
        if table not in all_tables:
            print(f"{script:<30} {table:<25} {'表不存在'}")
            continue

        # 取最新2个不同日期
        dates = conn.execute(text(
            f'SELECT DISTINCT "{date_col}" FROM {SCHEMA}."{table}" '
            f'ORDER BY "{date_col}" DESC LIMIT 2'
        )).fetchall()

        if not dates:
            print(f"{script:<30} {table:<25} {'空表'}")
            continue

        results = []
        for (d,) in dates:
            cnt = conn.execute(text(
                f'SELECT COUNT(*) FROM {SCHEMA}."{table}" WHERE "{date_col}"=:d'
            ), {"d": d}).fetchone()[0]
            results.append((str(d)[:10], cnt))

        # 补齐到2条
        while len(results) < 2:
            results.append(("—", "—"))

        d1, c1 = results[0]
        d2, c2 = results[1]
        c1_str = f"{c1:,}" if isinstance(c1, int) else c1
        c2_str = f"{c2:,}" if isinstance(c2, int) else c2
        print(f"{script:<30} {table:<25} {d1:<12} {c1_str:>8}  {d2:<12} {c2_str:>8}")

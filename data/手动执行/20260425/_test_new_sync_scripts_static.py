"""Static checks for newly added Tushare sync scripts.

This avoids importing the sync modules because importing _common requires local
environment variables and database settings.
"""
from pathlib import Path


HERE = Path(__file__).parent

EXPECTED = {
    "021_stk_weekly_monthly.py": {
        "table": 'TABLE         = "021_stk_weekly_monthly"',
        "api": "pro.stk_weekly_monthly",
        "pk": 'PK     = ["ts_code", "trade_date", "freq"]',
        "fields": ["ts_code", "trade_date", "end_date", "freq", "open", "pct_chg"],
    },
    "022_stk_week_month_adj.py": {
        "table": 'TABLE         = "022_stk_week_month_adj"',
        "api": "pro.stk_week_month_adj",
        "pk": 'PK     = ["ts_code", "trade_date", "freq"]',
        "fields": ["open_qfq", "close_qfq", "open_hfq", "close_hfq"],
    },
    "082_moneyflow_dc.py": {
        "table": 'TABLE         = "082_moneyflow_dc"',
        "api": "pro.moneyflow_dc",
        "pk": 'PK     = ["trade_date", "ts_code"]',
        "fields": ["net_amount_rate", "buy_elg_amount_rate", "buy_sm_amount_rate"],
    },
    "083_moneyflow_cnt_ths.py": {
        "table": 'TABLE         = "083_moneyflow_cnt_ths"',
        "api": "pro.moneyflow_cnt_ths",
        "pk": 'PK     = ["trade_date", "ts_code"]',
        "fields": ["lead_stock", "company_num", "net_sell_amount"],
    },
    "084_moneyflow_ind_ths.py": {
        "table": 'TABLE         = "084_moneyflow_ind_ths"',
        "api": "pro.moneyflow_ind_ths",
        "pk": 'PK     = ["trade_date", "ts_code"]',
        "fields": ["industry", "close_price", "pct_change_stock"],
    },
    "085_moneyflow_ind_dc.py": {
        "table": 'TABLE         = "085_moneyflow_ind_dc"',
        "api": "pro.moneyflow_ind_dc",
        "pk": 'PK     = ["trade_date", "content_type", "ts_code"]',
        "fields": ["content_type", "buy_sm_amount_stock", "rank"],
    },
    "086_moneyflow_mkt_dc.py": {
        "table": 'TABLE         = "086_moneyflow_mkt_dc"',
        "api": "pro.moneyflow_mkt_dc",
        "pk": 'PK     = ["trade_date"]',
        "fields": ["close_sh", "pct_change_sh", "close_sz", "pct_change_sz"],
    },
    "091_limit_list_d.py": {
        "table": 'TABLE         = "091_limit_list_d"',
        "api": "pro.limit_list_d",
        "pk": 'PK     = ["trade_date", "ts_code", "limit"]',
        "fields": ["limit_amount", "open_times", "limit_times", "limit"],
    },
    "092_limit_step.py": {
        "table": 'TABLE         = "092_limit_step"',
        "api": "pro.limit_step",
        "pk": 'PK     = ["trade_date", "ts_code", "nums"]',
        "fields": ["ts_code", "name", "trade_date", "nums"],
    },
    "094_ths_index.py": {
        "table": 'TABLE         = "094_ths_index"',
        "api": "pro.ths_index",
        "pk": 'PK     = ["ts_code"]',
        "fields": ["ts_code", "name", "count", "exchange", "list_date", "type"],
        "requires_sync_start": False,
    },
    "095_ths_daily.py": {
        "table": 'TABLE         = "095_ths_daily"',
        "api": "pro.ths_daily",
        "pk": 'PK     = ["ts_code", "trade_date"]',
        "fields": ["pre_close", "avg_price", "turnover_rate", "total_mv", "float_mv"],
    },
    "096_ths_member.py": {
        "table": 'TABLE         = "096_ths_member"',
        "api": "pro.ths_member",
        "pk": 'PK     = ["ts_code", "con_code", "is_new_key"]',
        "fields": ["con_code", "con_name", "weight", "in_date", "out_date", "is_new"],
        "requires_sync_start": False,
    },
    "097_dc_index.py": {
        "table": 'TABLE         = "097_dc_index"',
        "api": "pro.dc_index",
        "pk": 'PK     = ["ts_code", "trade_date"]',
        "fields": ["leading", "leading_code", "leading_pct", "up_num", "down_num", "idx_type", "level"],
    },
    "098_dc_member.py": {
        "table": 'TABLE         = "098_dc_member"',
        "api": "pro.dc_member",
        "pk": 'PK     = ["trade_date", "ts_code", "con_code"]',
        "fields": ["trade_date", "ts_code", "con_code", "name"],
    },
    "099_dc_daily.py": {
        "table": 'TABLE         = "099_dc_daily"',
        "api": "pro.dc_daily",
        "pk": 'PK     = ["ts_code", "trade_date"]',
        "fields": ["change", "pct_change", "vol", "amount", "swing", "turnover_rate"],
    },
    "131_index_member_all.py": {
        "table": 'TABLE  = "131_index_member_all"',
        "api": "pro.index_member_all",
        "pk": 'PK     = ["ts_code", "l3_code", "in_date"]',
        "fields": ["index_classify", "l1_code", "l2_code", "l3_code", "out_date", "is_new"],
        "requires_sync_start": False,
    },
    "132_sw_daily.py": {
        "table": 'TABLE         = "132_sw_daily"',
        "api": "pro.sw_daily",
        "pk": 'PK     = ["ts_code", "trade_date"]',
        "fields": ["pct_change", "float_mv", "total_mv"],
    },
}


RUNNER_FILES = ["run_all.py", "run_all-001~040.py", "run_all-041~139.py"]
CHECK_FILES = [
    "_check_status.py",
    "_check_status2.py",
    "_check_status3.py",
    "_check_dates.py",
    "_check_dates2.py",
]


def read(name: str) -> str:
    path = HERE / name
    assert path.exists(), f"missing file: {name}"
    return path.read_text(encoding="utf-8")


def test_scripts_exist_and_match_metadata():
    for script, spec in EXPECTED.items():
        text = read(script)
        assert spec["table"] in text, f"{script}: TABLE mismatch"
        assert spec["api"] in text, f"{script}: API call missing"
        assert spec["pk"] in text, f"{script}: PK mismatch"
        assert "check_or_create_table" in text, f"{script}: missing table check"
        if spec.get("requires_sync_start", True):
            assert "get_sync_start" in text, f"{script}: missing sync start"
        assert "mark_sync" in text, f"{script}: missing sync status update"
        for field in spec["fields"]:
            assert field in text, f"{script}: missing field {field}"


def test_runner_and_check_integration():
    runners = {name: read(name) for name in RUNNER_FILES}
    checks = {name: read(name) for name in CHECK_FILES}
    readme = read("new_readme.md")

    for script in EXPECTED:
        no = script[:3]
        assert script in runners["run_all.py"], f"run_all.py missing {script}"
        if int(no) <= 40:
            assert script in runners["run_all-001~040.py"], f"run_all-001~040.py missing {script}"
        else:
            assert script in runners["run_all-041~139.py"], f"run_all-041~139.py missing {script}"
        assert script in checks["_check_status.py"], f"_check_status.py missing {script}"
        for check_name in ["_check_status2.py", "_check_status3.py", "_check_dates.py", "_check_dates2.py"]:
            assert "SCRIPT_TABLE_MAP" in checks[check_name] or "from _check_status import main" in checks[check_name], (
                f"{check_name} does not reuse restored check mapping"
            )
        assert f"| {no} |" in readme, f"new_readme.md missing row {no}"
        assert script in readme, f"new_readme.md missing file tree entry {script}"


if __name__ == "__main__":
    test_scripts_exist_and_match_metadata()
    test_runner_and_check_integration()
    print("static checks passed")

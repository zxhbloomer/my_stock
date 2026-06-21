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
    "041_dividend.py": {
        "table": 'TABLE         = "041_dividend"',
        "api": "pro.dividend",
        "pk": 'PK     = ["ts_code", "end_date", "ann_date"]',
        "fields": ["ann_date", "record_date", "imp_ann_date", "fetch_ann_date_pages", "page-size"],
    },
    "042_fina_indicator.py": {
        "table": 'TABLE         = "042_fina_indicator"',
        "api": "pro.fina_indicator_vip",
        "pk": 'PK   = ["ts_code", "ann_date", "end_date"]',
        "fields": ["fina_indicator_vip", "fetch_vip_pages", "page-size"],
    },
    "049_top10_holders.py": {
        "table": 'TABLE         = "049_top10_holders"',
        "api": "pro.top10_holders",
        "pk": 'PK     = ["ts_code", "ann_date", "end_date", "holder_name"]',
        "requires_sync_start": False,
        "fields": ["hold_amount", "hold_ratio", "hold_float_ratio", "hold_change", "holder_type", "recent_report_period_window"],
    },
    "050_top10_floatholders.py": {
        "table": 'TABLE         = "050_top10_floatholders"',
        "api": "pro.top10_floatholders",
        "pk": 'PK     = ["ts_code", "ann_date", "end_date", "holder_name"]',
        "requires_sync_start": False,
        "fields": ["hold_amount", "hold_ratio", "hold_float_ratio", "hold_change", "holder_type", "recent_report_period_window"],
    },
    "051_pledge_stat.py": {
        "table": 'TABLE         = "051_pledge_stat"',
        "api": "pro.pledge_stat",
        "pk": 'PK     = ["ts_code", "end_date"]',
        "fields": ["pledge_count", "unrest_pledge", "rest_pledge", "total_share", "pledge_ratio"],
    },
    "058_stk_holdernumber.py": {
        "table": 'TABLE         = "058_stk_holdernumber"',
        "api": "pro.stk_holdernumber",
        "pk": 'PK     = ["ts_code", "ann_date", "end_date"]',
        "fields": ["ts_code", "ann_date", "end_date", "holder_num"],
    },
    "060_report_rc.py": {
        "table": 'TABLE         = "060_report_rc"',
        "api": "pro.report_rc",
        "pk": 'PK     = ["ts_code", "report_date", "report_title", "org_name", "author_name", "quarter"]',
        "fields": ["report_type", "classify", "op_rt", "eps", "pe", "create_time", "replace_report_date_df"],
    },
    "062_cyq_chips.py": {
        "table": 'TABLE         = "062_cyq_chips"',
        "api": "pro.cyq_chips",
        "pk": 'PK     = ["ts_code", "trade_date", "price"]',
        "fields": ["window-days", "page-size", "start-code", "end-code", "upsert_with_reconnect"],
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
    "121_index_basic.py": {
        "table": 'TABLE  = "121_index_basic"',
        "api": "pro.index_basic",
        "pk": 'PK     = ["ts_code"]',
        "fields": ["fullname", "index_type", "weight_rule", "desc", "exp_date"],
        "requires_sync_start": False,
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

    for runner_name in ["run_all.py", "run_all-041~139.py"]:
        scripts = []
        for line in runners[runner_name].splitlines():
            line = line.strip()
            if line.startswith('"') and line.endswith('",'):
                scripts.append(line.strip('",'))
        assert scripts[-1] == "043_fina_audit.py", f"{runner_name}: 043_fina_audit.py should run last"

    check_today = read("run_check_today_sync.py")
    assert "HOLIDAY_REFRESH" in check_today
    assert 'TableSpec("043_fina_audit.py", "043_fina_audit", "ann_date", HOLIDAY_REFRESH)' in check_today


def test_run_all_records_child_runtime():
    common = read("_common.py")
    assert "def record_script_runtime_start" in common
    assert "def record_script_runtime_finish" in common
    for runner_name in RUNNER_FILES:
        text = read(runner_name)
        assert "record_script_runtime_start" in text, f"{runner_name}: missing runtime start recording"
        assert "record_script_runtime_finish" in text, f"{runner_name}: missing runtime finish recording"


def test_bulk_paged_sparse_scripts_do_not_loop_all_stocks():
    expectations = {
        "041_dividend.py": ["fetch_ann_date_pages", "ann_date=", "limit=page_size", "offset=offset"],
        "042_fina_indicator.py": ["fetch_vip_pages", "start_date=", "end_date=", "limit=page_size", "offset=offset"],
        "049_top10_holders.py": ["fetch_period_pages", "period=", "limit=page_size", "offset=offset"],
        "050_top10_floatholders.py": ["fetch_period_pages", "period=", "limit=page_size", "offset=offset"],
        "051_pledge_stat.py": ["fetch_end_date_pages", "end_date=", "limit=page_size", "offset=offset"],
        "058_stk_holdernumber.py": ["fetch_ann_date_pages", "start_date=", "end_date=", "limit=page_size", "offset=offset"],
        "069_stk_nineturn.py": ["fetch_range_pages", "start_date=", "end_date=", "limit=page_size", "offset=offset"],
    }
    for script, required in expectations.items():
        text = read(script)
        assert "stock_basic(" not in text, f"{script}: should not loop all stock_basic codes"
        for needle in required:
            assert needle in text, f"{script}: missing bulk paging marker {needle}"


if __name__ == "__main__":
    test_scripts_exist_and_match_metadata()
    test_runner_and_check_integration()
    test_run_all_records_child_runtime()
    test_bulk_paged_sparse_scripts_do_not_loop_all_stocks()
    print("static checks passed")

"""检查今日同步完整性，并打印建议补跑命令。

默认只读数据库，不自动执行补跑命令。
"""
import argparse
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))


class TableSpec(NamedTuple):
    script: str
    table: str
    date_col: Optional[str]
    category: str


class CheckResult(NamedTuple):
    spec: TableSpec
    status: str
    today_count: Optional[int]
    previous_count: Optional[int]
    command: Optional[str]
    message: str


REQUIRED_DAILY = "required_daily"
SPARSE = "sparse"
STATIC = "static"
PERIODIC = "periodic"

LOW_COUNT_RATIO = 0.8

# Keep this aligned with run_all.py SCRIPTS.
TABLE_SPECS = [
    TableSpec("003_trade_cal.py", "003_trade_cal", "cal_date", STATIC),
    TableSpec("001_stock_basic.py", "001_stock_basic", None, STATIC),
    TableSpec("004_stock_st.py", "004_stock_st", "trade_date", SPARSE),
    TableSpec("005_st.py", "005_st", None, STATIC),
    TableSpec("008_stock_company.py", "008_stock_company", None, STATIC),
    TableSpec("014_daily.py", "014_daily", "trade_date", REQUIRED_DAILY),
    TableSpec("018_weekly.py", "018_weekly", "trade_date", PERIODIC),
    TableSpec("019_monthly.py", "019_monthly", "trade_date", PERIODIC),
    TableSpec("021_stk_weekly_monthly.py", "021_stk_weekly_monthly", "trade_date", REQUIRED_DAILY),
    TableSpec("022_stk_week_month_adj.py", "022_stk_week_month_adj", "trade_date", REQUIRED_DAILY),
    TableSpec("023_adj_factor.py", "023_adj_factor", "trade_date", REQUIRED_DAILY),
    TableSpec("027_daily_basic.py", "027_daily_basic", "trade_date", REQUIRED_DAILY),
    TableSpec("029_stk_limit.py", "029_stk_limit", "trade_date", REQUIRED_DAILY),
    TableSpec("030_suspend_d.py", "030_suspend_d", "trade_date", SPARSE),
    TableSpec("031_hsgt_top10.py", "031_hsgt_top10", "trade_date", REQUIRED_DAILY),
    TableSpec("032_ggt_top10.py", "032_ggt_top10", "trade_date", REQUIRED_DAILY),
    TableSpec("036_income.py", "036_income", "ann_date", SPARSE),
    TableSpec("037_balancesheet.py", "037_balancesheet", "ann_date", SPARSE),
    TableSpec("038_cashflow.py", "038_cashflow", "ann_date", SPARSE),
    TableSpec("039_forecast.py", "039_forecast", "ann_date", SPARSE),
    TableSpec("040_express.py", "040_express", "ann_date", SPARSE),
    TableSpec("041_dividend.py", "041_dividend", "ann_date", SPARSE),
    TableSpec("042_fina_indicator.py", "042_fina_indicator", "ann_date", SPARSE),
    TableSpec("043_fina_audit.py", "043_fina_audit", "ann_date", SPARSE),
    TableSpec("061_cyq_perf.py", "061_cyq_perf", "trade_date", REQUIRED_DAILY),
    TableSpec("062_cyq_chips.py", "062_cyq_chips", "trade_date", REQUIRED_DAILY),
    TableSpec("063_stk_factor_pro.py", "063_stk_factor_pro", "trade_date", REQUIRED_DAILY),
    TableSpec("066_hk_hold.py", "066_hk_hold", "trade_date", REQUIRED_DAILY),
    TableSpec("069_stk_nineturn.py", "069_stk_nineturn", "trade_date", REQUIRED_DAILY),
    TableSpec("073_margin.py", "073_margin", "trade_date", REQUIRED_DAILY),
    TableSpec("074_margin_detail.py", "074_margin_detail", "trade_date", REQUIRED_DAILY),
    TableSpec("075_margin_secs.py", "075_margin_secs", "trade_date", REQUIRED_DAILY),
    TableSpec("076_slb_sec.py", "076_slb_sec", "trade_date", REQUIRED_DAILY),
    TableSpec("077_slb_len.py", "077_slb_len", "trade_date", REQUIRED_DAILY),
    TableSpec("078_slb_sec_detail.py", "078_slb_sec_detail", "trade_date", REQUIRED_DAILY),
    TableSpec("080_moneyflow.py", "080_moneyflow", "trade_date", REQUIRED_DAILY),
    TableSpec("081_moneyflow_ths.py", "081_moneyflow_ths", "trade_date", REQUIRED_DAILY),
    TableSpec("082_moneyflow_dc.py", "082_moneyflow_dc", "trade_date", REQUIRED_DAILY),
    TableSpec("083_moneyflow_cnt_ths.py", "083_moneyflow_cnt_ths", "trade_date", REQUIRED_DAILY),
    TableSpec("084_moneyflow_ind_ths.py", "084_moneyflow_ind_ths", "trade_date", REQUIRED_DAILY),
    TableSpec("085_moneyflow_ind_dc.py", "085_moneyflow_ind_dc", "trade_date", REQUIRED_DAILY),
    TableSpec("086_moneyflow_mkt_dc.py", "086_moneyflow_mkt_dc", "trade_date", REQUIRED_DAILY),
    TableSpec("087_moneyflow_hsgt.py", "087_moneyflow_hsgt", "trade_date", REQUIRED_DAILY),
    TableSpec("088_top_list.py", "088_top_list", "trade_date", SPARSE),
    TableSpec("089_top_inst.py", "089_top_inst", "trade_date", SPARSE),
    TableSpec("091_limit_list_d.py", "091_limit_list_d", "trade_date", SPARSE),
    TableSpec("092_limit_step.py", "092_limit_step", "trade_date", SPARSE),
    TableSpec("121_index_basic.py", "121_index_basic", None, STATIC),
    TableSpec("122_index_daily.py", "122_index_daily", "trade_date", REQUIRED_DAILY),
    TableSpec("129_index_dailybasic.py", "129_index_dailybasic", "trade_date", REQUIRED_DAILY),
    TableSpec("134_ci_index_member.py", "134_ci_index_member", None, STATIC),
    TableSpec("135_ci_daily.py", "135_ci_daily", "trade_date", REQUIRED_DAILY),
    TableSpec("137_idx_factor_pro.py", "137_idx_factor_pro", "trade_date", REQUIRED_DAILY),
    TableSpec("138_daily_info.py", "138_daily_info", "trade_date", REQUIRED_DAILY),
    TableSpec("139_sz_daily_info.py", "139_sz_daily_info", "trade_date", REQUIRED_DAILY),
]


def build_command(script: str, target_date: str, date_col: Optional[str]) -> str:
    if date_col is None:
        return "python -X utf8 {}".format(script)
    return "python -X utf8 {} --start {} --end {}".format(script, target_date, target_date)


def evaluate_table(
    spec: TableSpec,
    target_date: str,
    today_count: Optional[int],
    previous_count: Optional[int],
    table_exists: bool,
    low_count_ratio: float = LOW_COUNT_RATIO,
) -> CheckResult:
    if not table_exists:
        return CheckResult(
            spec, "missing_table", today_count, previous_count,
            build_command(spec.script, target_date, spec.date_col),
            "表不存在",
        )

    if spec.category == STATIC:
        if today_count == 0:
            return CheckResult(
                spec, "empty_static", today_count, previous_count,
                build_command(spec.script, target_date, spec.date_col),
                "静态表为空",
            )
        return CheckResult(spec, "ok", today_count, previous_count, None, "静态表非空")

    if spec.category == PERIODIC:
        return CheckResult(spec, "skipped_periodic", today_count, previous_count, None, "周/月频表不按今日检查")

    if spec.category == SPARSE:
        if today_count == 0:
            return CheckResult(spec, "sparse_empty", today_count, previous_count, None, "事件类表今日为空，仅提示")
        return CheckResult(spec, "ok", today_count, previous_count, None, "事件类表今日有数据")

    if today_count == 0:
        return CheckResult(
            spec, "missing", today_count, previous_count,
            build_command(spec.script, target_date, spec.date_col),
            "今日数据缺失",
        )

    if previous_count and today_count < previous_count * low_count_ratio:
        return CheckResult(
            spec, "low_count", today_count, previous_count,
            build_command(spec.script, target_date, spec.date_col),
            "今日行数低于上一交易日的 {:.0%}".format(low_count_ratio),
        )

    return CheckResult(spec, "ok", today_count, previous_count, None, "今日数据存在")


def get_all_tables(conn, schema: str):
    rows = conn.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema=:schema"
    ), {"schema": schema}).fetchall()
    return {r[0] for r in rows}


def is_open_trade_date(conn, schema: str, target_date: str) -> bool:
    row = conn.execute(text(f"""
        SELECT is_open
        FROM {schema}."003_trade_cal"
        WHERE exchange='SSE' AND cal_date=:d
    """), {"d": target_date}).fetchone()
    return bool(row and row[0] == 1)


def get_previous_trade_date(conn, schema: str, target_date: str) -> Optional[str]:
    row = conn.execute(text(f"""
        SELECT cal_date
        FROM {schema}."003_trade_cal"
        WHERE exchange='SSE' AND is_open=1 AND cal_date < :d
        ORDER BY cal_date DESC
        LIMIT 1
    """), {"d": target_date}).fetchone()
    if not row or not row[0]:
        return None
    return row[0].strftime("%Y%m%d")


def count_table(conn, schema: str, table: str) -> int:
    return conn.execute(text(f'SELECT COUNT(*) FROM {schema}."{table}"')).fetchone()[0]


def count_date(conn, schema: str, table: str, date_col: str, target_date: str) -> int:
    return conn.execute(text(
        f'SELECT COUNT(*) FROM {schema}."{table}" WHERE "{date_col}"=:d'
    ), {"d": target_date}).fetchone()[0]


def collect_results(conn, schema: str, target_date: str, low_count_ratio: float) -> List[CheckResult]:
    all_tables = get_all_tables(conn, schema)
    previous_date = get_previous_trade_date(conn, schema, target_date)
    results = []

    for spec in TABLE_SPECS:
        table_exists = spec.table in all_tables
        today_count = None
        previous_count = None

        if table_exists:
            if spec.date_col:
                today_count = count_date(conn, schema, spec.table, spec.date_col, target_date)
                if previous_date:
                    previous_count = count_date(conn, schema, spec.table, spec.date_col, previous_date)
            else:
                today_count = count_table(conn, schema, spec.table)

        results.append(evaluate_table(
            spec=spec,
            target_date=target_date,
            today_count=today_count,
            previous_count=previous_count,
            table_exists=table_exists,
            low_count_ratio=low_count_ratio,
        ))

    return results


def print_results(results: List[CheckResult]) -> None:
    print("{:<22} {:<24} {:<16} {:>10} {:>10}  {}".format(
        "状态", "脚本", "表", "今日", "上日", "说明"
    ))
    print("-" * 100)
    for r in results:
        today = "-" if r.today_count is None else "{:,}".format(r.today_count)
        prev = "-" if r.previous_count is None else "{:,}".format(r.previous_count)
        print("{:<22} {:<24} {:<16} {:>10} {:>10}  {}".format(
            r.status, r.spec.script, r.spec.table, today, prev, r.message
        ))

    commands = [r.command for r in results if r.command]
    print("\n建议补跑命令:")
    if not commands:
        print("  无")
    else:
        print("  # 请先 cd 到 {}".format(Path(__file__).parent))
        for cmd in commands:
            print("  {}".format(cmd))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="检查日期，格式 YYYYMMDD，默认今天")
    parser.add_argument("--threshold", type=float, default=LOW_COUNT_RATIO,
                        help="今日行数低于上一交易日比例时判为可疑，默认 0.8")
    args = parser.parse_args()

    from _common import get_engine, SCHEMA, TODAY

    target_date = args.date or TODAY
    engine = get_engine()

    with engine.connect() as conn:
        if not is_open_trade_date(conn, SCHEMA, target_date):
            print("{} 不是 SSE 交易日，跳过今日数据完整性检查。".format(target_date))
            return

        results = collect_results(conn, SCHEMA, target_date, args.threshold)

    print("检查日期: {}".format(target_date))
    print_results(results)


if __name__ == "__main__":
    main()

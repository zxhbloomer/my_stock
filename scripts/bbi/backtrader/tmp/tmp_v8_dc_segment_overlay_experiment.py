import csv
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from tmp_v8_dc_segment_overlay_lib import (
    apply_dc_segment_score_boost,
    build_dc_segment_features,
    filter_dc_segment_crash_candidates,
    stock_has_crash_segment,
    validate_complete_trade_dates,
)


ROOT = Path(__file__).resolve().parents[4]
V8_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v8"
TMP_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "tmp"
OUTPUT_DIR = TMP_DIR / "tmp_v8_dc_segment_overlay_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v8_dc_segment_overlay_README.md"

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"
START_DATE = "2025-01-02"


def load_v8_module():
    sys.path.insert(0, str(V8_DIR))
    sys.modules.pop("config", None)
    spec = importlib.util.spec_from_file_location("v8_dc_segment_base", V8_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_sql(conn, sql, params=None):
    return pd.read_sql(text(sql), conn, params=params)


def fetch_open_dates(conn, start_date, end_date):
    return pd.to_datetime(read_sql(
        conn,
        f"""
        SELECT cal_date::date AS trade_date
        FROM {SCHEMA}."003_trade_cal"
        WHERE exchange = 'SSE'
          AND is_open = 1
          AND cal_date >= :start_date
          AND cal_date <= :end_date
        ORDER BY cal_date
        """,
        {"start_date": start_date, "end_date": end_date},
    )["trade_date"])


def validate_required_tables(conn, start_date, end_date):
    open_dates = fetch_open_dates(conn, start_date, end_date)
    failures = {}
    for table in ["098_dc_member", "099_dc_daily", "091_limit_list_d"]:
        data_dates = pd.to_datetime(read_sql(
            conn,
            f"""
            SELECT DISTINCT trade_date::date AS trade_date
            FROM {SCHEMA}."{table}"
            WHERE trade_date >= :start_date
              AND trade_date <= :end_date
            ORDER BY trade_date
            """,
            {"start_date": start_date, "end_date": end_date},
        )["trade_date"])
        missing = validate_complete_trade_dates(open_dates, data_dates)
        if missing:
            failures[table] = missing
    if failures:
        details = "; ".join(f"{table}: {dates[:10]}" for table, dates in failures.items())
        raise RuntimeError(f"DC segment required table completeness failed: {details}")


def load_segment_inputs(start_date, end_date):
    engine = create_engine(DB_URL, poolclass=NullPool)
    with engine.connect() as conn:
        validate_required_tables(conn, start_date, end_date)
        dc_daily = read_sql(
            conn,
            f"""
            SELECT ts_code, trade_date, close, amount
            FROM {SCHEMA}."099_dc_daily"
            WHERE trade_date >= DATE '2024-10-01'
              AND trade_date <= :end_date
            """,
            {"end_date": end_date},
        )
        members = read_sql(
            conn,
            f"""
            SELECT trade_date, ts_code, con_code, name
            FROM {SCHEMA}."098_dc_member"
            WHERE trade_date >= :start_date
              AND trade_date <= :end_date
            """,
            {"start_date": start_date, "end_date": end_date},
        )
        limit_daily = read_sql(
            conn,
            f"""
            SELECT trade_date, "limit", COUNT(*) AS count
            FROM {SCHEMA}."091_limit_list_d"
            WHERE trade_date >= :start_date
              AND trade_date <= :end_date
            GROUP BY trade_date, "limit"
            """,
            {"start_date": start_date, "end_date": end_date},
        )
    dc_daily["trade_date"] = pd.to_datetime(dc_daily["trade_date"])
    members["trade_date"] = pd.to_datetime(members["trade_date"])
    limit_daily["trade_date"] = pd.to_datetime(limit_daily["trade_date"])
    return dc_daily, members, limit_daily


def signal_date_from_candidates(candidates):
    if candidates.empty or "trade_date" not in candidates.columns:
        return None
    return pd.Timestamp(candidates["trade_date"].iloc[0])


def run_variant(v8, panel, market, members, segment_features, variant, member_lag_days=0):
    original_score_candidates = v8.score_candidates
    original_can_add_position = v8.can_add_position
    counters = {"segment_candidate_blocks": 0, "segment_add_blocks": 0}

    def score_boost(signal_panel, diagnostics=None):
        candidates = original_score_candidates(signal_panel, diagnostics=diagnostics)
        signal_date = signal_date_from_candidates(candidates)
        if signal_date is None:
            return candidates
        return apply_dc_segment_score_boost(
            candidates,
            signal_date,
            members,
            segment_features,
            member_lag_days=member_lag_days,
        )

    def score_no_crash(signal_panel, diagnostics=None):
        candidates = original_score_candidates(signal_panel, diagnostics=diagnostics)
        signal_date = signal_date_from_candidates(candidates)
        if signal_date is None:
            return candidates
        filtered = filter_dc_segment_crash_candidates(
            candidates,
            signal_date,
            members,
            segment_features,
            member_lag_days=member_lag_days,
        )
        counters["segment_candidate_blocks"] += int(len(candidates) - len(filtered))
        return filtered

    def score_boost_no_crash(signal_panel, diagnostics=None):
        candidates = score_no_crash(signal_panel, diagnostics=diagnostics)
        signal_date = signal_date_from_candidates(candidates)
        if signal_date is None:
            return candidates
        return apply_dc_segment_score_boost(
            candidates,
            signal_date,
            members,
            segment_features,
            weight=0.08,
            mainline_bonus=0.04,
            member_lag_days=member_lag_days,
        )

    def can_add_guard(code, pos, signal_panel):
        if not original_can_add_position(code, pos, signal_panel):
            return False
        if code not in signal_panel.index:
            return False
        signal_date = pd.Timestamp(signal_panel.loc[code].get("trade_date"))
        if stock_has_crash_segment(code, signal_date, members, segment_features, member_lag_days=member_lag_days):
            counters["segment_add_blocks"] += 1
            return False
        return True

    try:
        if variant == "dc_segment_score_boost":
            v8.score_candidates = score_boost
        elif variant == "dc_segment_no_buy_on_crash":
            v8.score_candidates = score_no_crash
        elif variant == "dc_segment_no_add_on_crash":
            v8.can_add_position = can_add_guard
        elif variant == "dc_segment_mainline_boost_no_crash":
            v8.score_candidates = score_boost_no_crash
            v8.can_add_position = can_add_guard

        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v8.run_backtest(
            panel.copy(),
            market.copy() if market is not None else None,
            START_DATE,
            None,
        )
        stats.update(counters)
        stats["member_lag_days"] = int(member_lag_days)
        return nav_df, trades_df, rebalance_df, scores_df, holdings, stats
    finally:
        v8.score_candidates = original_score_candidates
        v8.can_add_position = original_can_add_position


def write_variant_output(name, nav_df, trades_df, rebalance_df, scores_df, holdings, stats):
    out_dir = OUTPUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    nav_df.to_csv(out_dir / "nav_series.csv", index=False)
    trades_df.to_csv(out_dir / "trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    rebalance_df.to_csv(out_dir / "rebalance_log.csv", index=False)
    scores_df.to_csv(out_dir / "strength_scores.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def read_variant_output(name):
    out_dir = OUTPUT_DIR / name
    nav_path = out_dir / "nav_series.csv"
    summary_path = out_dir / "summary.json"
    if not nav_path.exists() or not summary_path.exists():
        return None
    return {
        "nav": pd.read_csv(nav_path),
        "stats": json.loads(summary_path.read_text(encoding="utf-8")),
    }


def period_returns(nav, freq):
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values("date")
    data["period"] = data["date"].dt.to_period(freq).astype(str)
    period_end = data.groupby("period")["nav"].last()
    prior_end = period_end.shift(1)
    first_nav = float(data["nav"].iloc[0])
    rows = []
    for period, group in data.groupby("period"):
        start = float(prior_end.loc[period]) if pd.notna(prior_end.loc[period]) else first_nav
        end = float(period_end.loc[period])
        rows.append({"period": period, "return_pct": (end / start - 1.0) * 100.0 if start else 0.0})
    return pd.DataFrame(rows)


def make_report(results, limit_daily):
    summary_rows = []
    for name, payload in results.items():
        stats = payload["stats"]
        summary_rows.append({
            "name": name,
            "total_return_pct": stats.get("total_return_pct"),
            "annual_return_pct": stats.get("annual_return_pct"),
            "max_drawdown_pct": stats.get("max_drawdown_pct"),
            "final_nav": stats.get("final_nav"),
            "trade_records": stats.get("trade_records"),
            "segment_candidate_blocks": stats.get("segment_candidate_blocks", 0),
            "segment_add_blocks": stats.get("segment_add_blocks", 0),
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df["member_lag_days"] = [
        int(results[row["name"]]["stats"].get("member_lag_days", 0))
        for _, row in summary_df.iterrows()
    ]
    for col in ["total_return_pct", "annual_return_pct", "max_drawdown_pct", "final_nav"]:
        summary_df[col] = pd.to_numeric(summary_df[col], errors="coerce").round(2)

    annual = []
    monthly = []
    for name, payload in results.items():
        a = period_returns(payload["nav"], "Y")
        a["name"] = name
        annual.append(a)
        m = period_returns(payload["nav"], "M")
        m["name"] = name
        monthly.append(m)
    annual_df = pd.concat(annual, ignore_index=True).pivot(index="period", columns="name", values="return_pct").round(2).reset_index()
    monthly_df = pd.concat(monthly, ignore_index=True).pivot(index="period", columns="name", values="return_pct").round(2).reset_index()

    limit_pivot = limit_daily.pivot_table(index="trade_date", columns="limit", values="count", aggfunc="sum").fillna(0)
    for col in ["D", "U", "Z"]:
        if col not in limit_pivot.columns:
            limit_pivot[col] = 0
    risk_days = limit_pivot.sort_values("D", ascending=False).head(12).reset_index()
    risk_days["trade_date"] = risk_days["trade_date"].dt.strftime("%Y-%m-%d")

    baseline = summary_df[summary_df["name"].eq("baseline_2025_replay")].iloc[0]
    best = summary_df[~summary_df["name"].eq("baseline_2025_replay")].sort_values(
        ["total_return_pct", "max_drawdown_pct"], ascending=[False, False]
    ).head(1).iloc[0]
    if float(best["total_return_pct"]) > float(baseline["total_return_pct"]):
        recommendation = f"候选推进：{best['name']} 跑赢 baseline，但仍需扩展到更多年份或等待 098 历史延长后再合并。"
    else:
        recommendation = "本轮东财板块 overlay 未跑赢 2025+ baseline，不建议合并。"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v8 DC Segment Overlay</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #222; }}
.note {{ padding: 12px 14px; background: #f6f8fb; border-left: 4px solid #345995; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0 24px; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #f0f0f0; }}
</style>
</head>
<body>
<h1>v8 DC Segment Overlay</h1>
<div class="note">实验区间：2025-01-02 起。使用 099_dc_daily + 098_dc_member，今天未完成数据不纳入。lag1 表示板块成分滞后一交易日使用。</div>
<h2>结论</h2>
<p>{recommendation}</p>
<h2>总体结果</h2>
{summary_df.to_html(index=False, escape=False)}
<h2>年度收益 (%)</h2>
{annual_df.to_html(index=False, escape=False)}
<h2>月度收益 (%)</h2>
{monthly_df.to_html(index=False, escape=False)}
<h2>跌停风险日</h2>
{risk_days.to_html(index=False, escape=False)}
<h2>说明</h2>
<p>该实验只验证 2025+，因为 098_dc_member 从 2025-01-02 才有可用每日成分。099_dc_daily 板块行情按 signal_date 收盘使用，交易发生在下一交易日开盘；098_dc_member 的 lag1 版本用上一可用成分日，降低成分发布时间/PIT 风险。</p>
</body>
</html>
"""
    REPORT_PATH.write_text(html, encoding="utf-8")


def update_readme_result(summary):
    lines = ["\n## Run Result\n", "\n| variant | total_return_pct | annual_return_pct | max_drawdown_pct | trades |\n", "|---|---:|---:|---:|---:|\n"]
    for name, stats in summary.items():
        lines.append(
            f"| {name} | {stats['total_return_pct']:.2f} | {stats['annual_return_pct']:.2f} | {stats['max_drawdown_pct']:.2f} | {stats['trade_records']} |\n"
        )
    with README_PATH.open("a", encoding="utf-8") as f:
        f.writelines(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v8 = load_v8_module()
    panel = pd.read_parquet(v8.PANEL_PATH, columns=v8.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = v8.load_market_index()
    end_date = str(panel["trade_date"].max())[:10]

    dc_daily, members, limit_daily = load_segment_inputs(START_DATE, end_date)
    segment_features = build_dc_segment_features(dc_daily)
    segment_features.to_csv(OUTPUT_DIR / "dc_segment_features.csv", index=False)

    variants = [
        ("baseline_2025_replay", "baseline", 0),
        ("dc_segment_score_boost", "dc_segment_score_boost", 0),
        ("dc_segment_no_add_on_crash", "dc_segment_no_add_on_crash", 0),
        ("dc_segment_no_buy_on_crash", "dc_segment_no_buy_on_crash", 0),
        ("dc_segment_mainline_boost_no_crash", "dc_segment_mainline_boost_no_crash", 0),
        ("dc_segment_no_buy_on_crash_lag1", "dc_segment_no_buy_on_crash", 1),
        ("dc_segment_mainline_boost_no_crash_lag1", "dc_segment_mainline_boost_no_crash", 1),
    ]
    results = {}
    summary = {}
    for name, variant, member_lag_days in variants:
        cached = read_variant_output(name)
        if cached is not None:
            cached["stats"]["member_lag_days"] = int(cached["stats"].get("member_lag_days", member_lag_days))
            results[name] = cached
            summary[name] = cached["stats"]
            print(f"[dc-segment] reuse {name}", flush=True)
            continue

        print(f"[dc-segment] running {name}", flush=True)
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = run_variant(
            v8,
            panel,
            market,
            members,
            segment_features,
            variant,
            member_lag_days=member_lag_days,
        )
        write_variant_output(name, nav_df, trades_df, rebalance_df, scores_df, holdings, stats)
        results[name] = {"nav": nav_df, "stats": stats}
        summary[name] = stats
        print(
            f"[dc-segment] {name}: total={stats['total_return_pct']:.2f}% "
            f"dd={stats['max_drawdown_pct']:.2f}% trades={stats['trade_records']}",
            flush=True,
        )

    make_report(results, limit_daily)
    update_readme_result(summary)
    print(f"[dc-segment] report: {REPORT_PATH}")


if __name__ == "__main__":
    main()

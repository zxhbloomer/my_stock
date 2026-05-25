import csv
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from tmp_v8_dc_segment_overlay_experiment import load_segment_inputs, read_sql
from tmp_v8_dc_segment_overlay_lib import (
    apply_dc_segment_score_boost,
    build_dc_segment_features,
    filter_dc_segment_crash_candidates,
    stock_has_crash_segment,
)


ROOT = Path(__file__).resolve().parents[4]
V8_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v8"
TMP_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "tmp"
OUTPUT_DIR = TMP_DIR / "tmp_v8_dc_segment_full_cycle_output"
REPORT_PATH = OUTPUT_DIR / "report.html"

BACKTEST_START_DATE = "2018-01-02"
OVERLAY_ACTIVE_FROM = "2025-01-02"
END_DATE = "2026-05-22"
MEMBER_LAG_DAYS = 1


def load_v8_module():
    sys.path.insert(0, str(V8_DIR))
    sys.modules.pop("config", None)
    spec = importlib.util.spec_from_file_location("v8_dc_segment_full_cycle", V8_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signal_date_from_candidates(candidates):
    if candidates.empty or "trade_date" not in candidates.columns:
        return None
    return pd.Timestamp(candidates["trade_date"].iloc[0])


def overlay_enabled(signal_date):
    return signal_date is not None and pd.Timestamp(signal_date) >= pd.Timestamp(OVERLAY_ACTIVE_FROM)


def run_variant(v8, panel, market, members, segment_features, variant):
    original_score_candidates = v8.score_candidates
    original_can_add_position = v8.can_add_position
    counters = {"segment_candidate_blocks": 0, "segment_add_blocks": 0, "segment_active_signal_days": 0}

    def score_no_crash(signal_panel, diagnostics=None):
        candidates = original_score_candidates(signal_panel, diagnostics=diagnostics)
        signal_date = signal_date_from_candidates(candidates)
        if not overlay_enabled(signal_date):
            return candidates
        counters["segment_active_signal_days"] += 1
        filtered = filter_dc_segment_crash_candidates(
            candidates,
            signal_date,
            members,
            segment_features,
            member_lag_days=MEMBER_LAG_DAYS,
        )
        counters["segment_candidate_blocks"] += int(len(candidates) - len(filtered))
        return filtered

    def score_boost_no_crash(signal_panel, diagnostics=None):
        candidates = score_no_crash(signal_panel, diagnostics=diagnostics)
        signal_date = signal_date_from_candidates(candidates)
        if not overlay_enabled(signal_date):
            return candidates
        return apply_dc_segment_score_boost(
            candidates,
            signal_date,
            members,
            segment_features,
            weight=0.08,
            mainline_bonus=0.04,
            member_lag_days=MEMBER_LAG_DAYS,
        )

    def can_add_guard(code, pos, signal_panel):
        if not original_can_add_position(code, pos, signal_panel):
            return False
        if code not in signal_panel.index:
            return False
        signal_date = pd.Timestamp(signal_panel.loc[code].get("trade_date"))
        if not overlay_enabled(signal_date):
            return True
        if stock_has_crash_segment(code, signal_date, members, segment_features, member_lag_days=MEMBER_LAG_DAYS):
            counters["segment_add_blocks"] += 1
            return False
        return True

    try:
        if variant == "no_buy_on_crash_lag1_active2025":
            v8.score_candidates = score_no_crash
        elif variant == "mainline_boost_no_crash_lag1_active2025":
            v8.score_candidates = score_boost_no_crash
            v8.can_add_position = can_add_guard

        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v8.run_backtest(
            panel.copy(),
            market.copy() if market is not None else None,
            BACKTEST_START_DATE,
            END_DATE,
        )
        stats.update(counters)
        stats["member_lag_days"] = MEMBER_LAG_DAYS if variant != "baseline_full_cycle" else 0
        stats["overlay_active_from"] = OVERLAY_ACTIVE_FROM if variant != "baseline_full_cycle" else ""
        return nav_df, trades_df, rebalance_df, scores_df, holdings, stats
    finally:
        v8.score_candidates = original_score_candidates
        v8.can_add_position = original_can_add_position


def write_variant_output(name, nav_df, trades_df, rebalance_df, scores_df, stats):
    out_dir = OUTPUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    nav_df.to_csv(out_dir / "nav_series.csv", index=False)
    trades_df.to_csv(out_dir / "trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    rebalance_df.to_csv(out_dir / "rebalance_log.csv", index=False)
    scores_df.to_csv(out_dir / "strength_scores.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def period_returns(nav, freq, start_date=None):
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    if start_date is not None:
        data = data[data["date"] >= pd.Timestamp(start_date)].copy()
    data = data.sort_values("date")
    data["period"] = data["date"].dt.to_period(freq).astype(str)
    period_end = data.groupby("period")["nav"].last()
    prior_end = period_end.shift(1)
    first_nav = float(data["nav"].iloc[0])
    rows = []
    for period, _ in data.groupby("period"):
        start = float(prior_end.loc[period]) if pd.notna(prior_end.loc[period]) else first_nav
        end = float(period_end.loc[period])
        rows.append({"period": period, "return_pct": (end / start - 1.0) * 100.0 if start else 0.0})
    return pd.DataFrame(rows)


def make_report(results):
    summary_rows = []
    for name, payload in results.items():
        stats = payload["stats"]
        nav = payload["nav"].copy()
        nav["date"] = pd.to_datetime(nav["date"])
        nav_2025 = nav[(nav["date"] >= pd.Timestamp("2025-01-01")) & (nav["date"] <= pd.Timestamp("2025-12-31"))]
        ret_2025 = 0.0
        if not nav_2025.empty:
            ret_2025 = (float(nav_2025["nav"].iloc[-1]) / float(nav_2025["nav"].iloc[0]) - 1.0) * 100.0
        nav_active = nav[nav["date"] >= pd.Timestamp(OVERLAY_ACTIVE_FROM)]
        ret_active = 0.0
        if not nav_active.empty:
            ret_active = (float(nav_active["nav"].iloc[-1]) / float(nav_active["nav"].iloc[0]) - 1.0) * 100.0
        summary_rows.append({
            "name": name,
            "total_return_pct": stats.get("total_return_pct"),
            "annual_return_pct": stats.get("annual_return_pct"),
            "max_drawdown_pct": stats.get("max_drawdown_pct"),
            "final_nav": stats.get("final_nav"),
            "return_2025_pct": ret_2025,
            "return_active_to_end_pct": ret_active,
            "trade_records": stats.get("trade_records"),
            "candidate_blocks": stats.get("segment_candidate_blocks", 0),
            "active_signal_days": stats.get("segment_active_signal_days", 0),
        })
    summary_df = pd.DataFrame(summary_rows)
    for col in ["total_return_pct", "annual_return_pct", "max_drawdown_pct", "final_nav", "return_2025_pct", "return_active_to_end_pct"]:
        summary_df[col] = pd.to_numeric(summary_df[col], errors="coerce").round(2)

    annual = []
    monthly = []
    for name, payload in results.items():
        a = period_returns(payload["nav"], "Y")
        a["name"] = name
        annual.append(a)
        m = period_returns(payload["nav"], "M", start_date="2025-01-01")
        m["name"] = name
        monthly.append(m)
    annual_df = pd.concat(annual, ignore_index=True).pivot(index="period", columns="name", values="return_pct").round(2).reset_index()
    monthly_df = pd.concat(monthly, ignore_index=True).pivot(index="period", columns="name", values="return_pct").round(2).reset_index()

    best = summary_df.sort_values("return_2025_pct", ascending=False).iloc[0]
    recommendation = (
        f"候选推进：{best['name']} 的 2025 年收益最高。"
        " 该结果为全周期 carry-over 口径，overlay 仅从 2025-01-02 后启用。"
    )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v8 DC Segment Full Cycle</title>
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
<h1>v8 DC Segment Full Cycle</h1>
<div class="note">全周期从 {BACKTEST_START_DATE} 跑到 {END_DATE}；板块 overlay 只从 {OVERLAY_ACTIVE_FROM} 起启用，098_dc_member 使用 lag1。</div>
<h2>结论</h2>
<p>{recommendation}</p>
<h2>总体结果</h2>
{summary_df.to_html(index=False, escape=False)}
<h2>年度收益 (%)</h2>
{annual_df.to_html(index=False, escape=False)}
<h2>2025 起月度收益 (%)</h2>
{monthly_df.to_html(index=False, escape=False)}
</body>
</html>
"""
    REPORT_PATH.write_text(html, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v8 = load_v8_module()
    panel = pd.read_parquet(v8.PANEL_PATH, columns=v8.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[panel["trade_date"] <= pd.Timestamp(END_DATE)].copy()
    market = v8.load_market_index()
    if market is not None:
        market = market[market.index <= pd.Timestamp(END_DATE)].copy()

    dc_daily, members, _ = load_segment_inputs(OVERLAY_ACTIVE_FROM, END_DATE)
    segment_features = build_dc_segment_features(dc_daily)

    variants = [
        ("baseline_full_cycle", "baseline_full_cycle"),
        ("no_buy_on_crash_lag1_active2025", "no_buy_on_crash_lag1_active2025"),
        ("mainline_boost_no_crash_lag1_active2025", "mainline_boost_no_crash_lag1_active2025"),
    ]
    results = {}
    for name, variant in variants:
        print(f"[full-cycle] running {name}", flush=True)
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = run_variant(
            v8,
            panel,
            market,
            members,
            segment_features,
            variant,
        )
        write_variant_output(name, nav_df, trades_df, rebalance_df, scores_df, stats)
        results[name] = {"nav": nav_df, "stats": stats}
        print(
            f"[full-cycle] {name}: total={stats['total_return_pct']:.2f}% "
            f"dd={stats['max_drawdown_pct']:.2f}% trades={stats['trade_records']}",
            flush=True,
        )

    make_report(results)
    print(f"[full-cycle] report: {REPORT_PATH}")


if __name__ == "__main__":
    main()

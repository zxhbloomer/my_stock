import csv
from contextlib import contextmanager
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v5").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V5_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v5"
V4_SUMMARY_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v4" / "output" / "summary.json"
OUTPUT_DIR = Path(__file__).parent / "v5_downtrend_filter_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


CASES = [
    {"name": "baseline_v5", "flag_col": None, "scope": "all_candidates"},
    {"name": "block_early_weakness_initial_only", "flag_col": "early_weakness_downtrend", "scope": "initial_only"},
    {"name": "block_early_weakness", "flag_col": "early_weakness_downtrend", "scope": "all_candidates"},
    {"name": "block_mid_weakness", "flag_col": "mid_weakness_downtrend", "scope": "all_candidates"},
    {"name": "block_bbi_breakdown", "flag_col": "bbi_breakdown_downtrend", "scope": "all_candidates"},
    {"name": "block_bbi_breakdown_initial_only", "flag_col": "bbi_breakdown_downtrend", "scope": "initial_only"},
    {"name": "block_ma20_rollover", "flag_col": "ma20_rollover_downtrend", "scope": "all_candidates"},
    {"name": "block_slope_downtrend", "flag_col": "slope_downtrend", "scope": "all_candidates"},
    {"name": "block_structure_downtrend", "flag_col": "structure_downtrend", "scope": "all_candidates"},
    {"name": "block_strict_downtrend", "flag_col": "strict_downtrend", "scope": "all_candidates"},
    {"name": "block_strong_downtrend", "flag_col": "strong_downtrend", "scope": "all_candidates"},
    {"name": "block_slope_or_structure", "flag_col": "slope_or_structure_downtrend", "scope": "all_candidates"},
]


def slope_pct(series: pd.Series, window: int) -> pd.Series:
    return series.pct_change(window, fill_method=None) / float(window)


def rolling_mean_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .mean()
        .reset_index(level=0, drop=True)
    )


def rolling_max_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .max()
        .reset_index(level=0, drop=True)
    )


def rolling_min_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .min()
        .reset_index(level=0, drop=True)
    )


def add_downtrend_features(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = panel.groupby("ts_code", sort=False)

    panel["ma20"] = rolling_mean_by_code(panel, "close_qfq", 20)
    panel["ma60"] = rolling_mean_by_code(panel, "close_qfq", 60)
    panel["ma120"] = rolling_mean_by_code(panel, "close_qfq", 120)
    panel["ma20_slope_10"] = grouped["ma20"].transform(lambda s: slope_pct(s, 10))
    panel["ma60_slope_20"] = grouped["ma60"].transform(lambda s: slope_pct(s, 20))
    panel["ma120_slope_30"] = grouped["ma120"].transform(lambda s: slope_pct(s, 30))
    panel["ret_21_local"] = grouped["close_qfq"].pct_change(21, fill_method=None)
    panel["ret_63_local"] = grouped["close_qfq"].pct_change(63, fill_method=None)

    panel["high_63"] = rolling_max_by_code(panel, "close_qfq", 63)
    panel["low_63"] = rolling_min_by_code(panel, "close_qfq", 63)
    panel["prev_high_63"] = grouped["high_63"].shift(63)
    panel["prev_low_63"] = grouped["low_63"].shift(63)
    panel["lower_high_63"] = panel["high_63"] < panel["prev_high_63"]
    panel["lower_low_63"] = panel["low_63"] < panel["prev_low_63"]

    panel["slope_downtrend"] = (
        (panel["close_qfq"] < panel["ma120"])
        & (panel["ma60"] < panel["ma120"])
        & (panel["ma120_slope_30"] < 0)
    )
    panel["early_weakness_downtrend"] = (
        (panel["close_qfq"] < panel["ma20"])
        & (panel["ma20_slope_10"] < 0)
        & (panel["ret_21_local"] < 0)
    )
    panel["mid_weakness_downtrend"] = (
        (panel["close_qfq"] < panel["ma60"])
        & (panel["ma60_slope_20"] < 0)
        & (panel["ret_63_local"] < 0)
    )
    panel["ma20_rollover_downtrend"] = (
        (panel["close_qfq"] < panel["ma20"])
        & (panel["ma20"] < panel["ma60"])
        & (panel["ma20_slope_10"] < 0)
    )
    if "bbi_qfq" in panel.columns:
        panel["bbi_breakdown_downtrend"] = (
            (panel["close_qfq"] < panel["bbi_qfq"])
            & (panel["ret_21_local"] < 0)
            & (panel["ma20_slope_10"] < 0)
        )
    else:
        panel["bbi_breakdown_downtrend"] = False
    panel["structure_downtrend"] = (
        panel["lower_high_63"].fillna(False)
        & panel["lower_low_63"].fillna(False)
        & (panel["close_qfq"] < panel["ma60"])
    )
    panel["strict_downtrend"] = panel["slope_downtrend"] & panel["structure_downtrend"]
    panel["strong_downtrend"] = (
        (panel["close_qfq"] < panel["ma120"])
        & (panel["ma20"] < panel["ma60"])
        & (panel["ma60"] < panel["ma120"])
        & (panel["ma60_slope_20"] < -0.001)
        & (panel["ma120_slope_30"] < -0.0005)
    )
    panel["slope_or_structure_downtrend"] = (
        panel["slope_downtrend"] | panel["structure_downtrend"]
    )
    return panel


def filter_downtrend_candidates(candidates: pd.DataFrame, flag_col):
    if flag_col is None or candidates.empty or flag_col not in candidates.columns:
        return candidates.copy(), {"blocked_candidates": 0, "input_candidates": int(len(candidates))}
    flags = candidates[flag_col].fillna(False).astype(bool)
    filtered = candidates[~flags].copy()
    return filtered, {
        "blocked_candidates": int(flags.sum()),
        "input_candidates": int(len(candidates)),
    }


def load_v5_module():
    if str(V5_DIR) not in sys.path:
        sys.path.insert(0, str(V5_DIR))
    spec = importlib.util.spec_from_file_location("v5_run_backtest_downtrend_filter", V5_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def patched_buy_filter(v5, case, diagnostics):
    original_score_candidates = v5.score_candidates
    original_execute_buy = v5.execute_buy
    blocked_codes_for_signal = set()

    def wrapped_score_candidates(signal_panel):
        nonlocal blocked_codes_for_signal
        candidates = original_score_candidates(signal_panel)
        filtered, diag = filter_downtrend_candidates(candidates, case["flag_col"])
        diagnostics["candidate_rows"] += diag["input_candidates"]
        diagnostics["blocked_candidate_rows"] += diag["blocked_candidates"]
        diagnostics["signal_calls"] += 1
        if case.get("scope") == "initial_only" and case["flag_col"] in candidates.columns:
            flags = candidates[case["flag_col"]].fillna(False).astype(bool)
            blocked_codes_for_signal = set(candidates.loc[flags, "ts_code"])
            return candidates
        blocked_codes_for_signal = set()
        return filtered

    def wrapped_execute_buy(date, row, target_amount, cash, holdings, trades, reason):
        code = row.get("ts_code")
        if (
            case.get("scope") == "initial_only"
            and reason == "long_initial_buy"
            and code in blocked_codes_for_signal
        ):
            diagnostics["blocked_initial_attempts"] += 1
            return cash, False, "downtrend_filter"
        return original_execute_buy(date, row, target_amount, cash, holdings, trades, reason)

    try:
        v5.score_candidates = wrapped_score_candidates
        v5.execute_buy = wrapped_execute_buy
        yield
    finally:
        v5.score_candidates = original_score_candidates
        v5.execute_buy = original_execute_buy


def calc_nav_stats(nav_df):
    nav_df = nav_df.copy()
    nav_df["date"] = pd.to_datetime(nav_df["date"])
    total_ret = nav_df["nav"].iloc[-1] / nav_df["nav"].iloc[0] - 1.0
    days = max((nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    curve = nav_df["nav"] / nav_df["nav"].iloc[0]
    dd = curve / curve.cummax() - 1.0
    max_dd = float(dd.min() * 100.0)
    annual_pct = float(annual_ret * 100.0)
    return {
        "start_date": str(nav_df["date"].iloc[0])[:10],
        "end_date": str(nav_df["date"].iloc[-1])[:10],
        "final_nav": round(float(nav_df["nav"].iloc[-1]), 2),
        "total_return_pct": round(float(total_ret * 100.0), 4),
        "annual_return_pct": round(annual_pct, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "calmar_ratio": round(annual_pct / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "avg_cash_pct": round(float((nav_df["cash"] / nav_df["nav"]).mean() * 100.0), 4),
        "avg_holdings": round(float(nav_df["holdings"].mean()), 4),
        "zero_holdings_days": int((nav_df["holdings"] == 0).sum()),
    }


def summarize_period(nav_df, trades_df, start, end):
    nav_dates = pd.to_datetime(nav_df["date"])
    nav_sub = nav_df[(nav_dates >= pd.Timestamp(start)) & (nav_dates <= pd.Timestamp(end))]
    if nav_sub.empty:
        return {}
    row = calc_nav_stats(nav_sub)
    if trades_df.empty:
        row.update({"trade_records": 0, "buy_fills": 0, "sell_fills": 0})
        return row
    trade_dates = pd.to_datetime(trades_df["date"])
    period_trades = trades_df[(trade_dates >= pd.Timestamp(start)) & (trade_dates <= pd.Timestamp(end))]
    row.update({
        "trade_records": int(len(period_trades)),
        "buy_fills": int((period_trades["action"] == "buy").sum()) if not period_trades.empty else 0,
        "sell_fills": int((period_trades["action"] == "sell").sum()) if not period_trades.empty else 0,
    })
    return row


def assert_baseline_matches_v5(results, v5_summary):
    baseline = results[(results["case"] == "baseline_v5") & (results["period"] == "full")]
    if baseline.empty:
        raise AssertionError("baseline_v5 full-period result is missing")
    row = baseline.iloc[0]
    for key, tolerance in [
        ("final_nav", 1e-2),
        ("total_return_pct", 1e-4),
        ("annual_return_pct", 1e-4),
        ("max_drawdown_pct", 1e-4),
        ("calmar_ratio", 1e-4),
        ("trade_records", 0),
    ]:
        actual = float(row[key])
        expected = float(v5_summary[key])
        if abs(actual - expected) > tolerance:
            raise AssertionError(f"baseline_v5 {key}={actual} does not match v5 summary {expected}")


def run_case(v5, panel, market, case):
    periods = {str(year): (f"{year}-01-01", f"{year}-12-31") for year in range(2018, 2027)}
    periods["full"] = ("2018-01-01", "2026-05-14")
    diagnostics = {
        "signal_calls": 0,
        "candidate_rows": 0,
        "blocked_candidate_rows": 0,
        "blocked_initial_attempts": 0,
    }
    with patched_buy_filter(v5, case, diagnostics):
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v5.run_backtest(
            panel,
            market,
            "2018-01-01",
            None,
        )
    rows = []
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "period": period_name,
            "flag_col": case["flag_col"] or "",
            "scope": case.get("scope", "all_candidates"),
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        if period_name == "full":
            row.update({
                "signal_calls": diagnostics["signal_calls"],
                "candidate_rows": diagnostics["candidate_rows"],
                "blocked_candidate_rows": diagnostics["blocked_candidate_rows"],
                "blocked_initial_attempts": diagnostics["blocked_initial_attempts"],
                "blocked_candidate_pct": round(
                    diagnostics["blocked_candidate_rows"] / max(diagnostics["candidate_rows"], 1) * 100.0,
                    4,
                ),
                "market_block_days": int(stats.get("market_block_days", 0)),
                "regime_bear_block_days": int(stats.get("regime_bear_block_days", 0)),
                "regime_bear_exit_fills": int(stats.get("regime_bear_exit_fills", 0)),
            })
        rows.append(row)
    return rows


def write_summary(results, v5_summary, v4_summary):
    full = results[results["period"] == "full"].sort_values(
        ["annual_return_pct", "max_drawdown_pct"],
        ascending=[False, False],
    )
    period_map = {
        case: {row["period"]: row for _, row in group.iterrows()}
        for case, group in results.groupby("case")
    }
    lines = [
        "# v5 Downtrend Buy Filter Experiment",
        "",
        "## Baselines",
        f"- v4 total return: {v4_summary['total_return_pct']}%",
        f"- v4 annual return: {v4_summary['annual_return_pct']}%",
        f"- v4 max drawdown: {v4_summary['max_drawdown_pct']}%",
        f"- v5 total return: {v5_summary['total_return_pct']}%",
        f"- v5 annual return: {v5_summary['annual_return_pct']}%",
        f"- v5 max drawdown: {v5_summary['max_drawdown_pct']}%",
        "",
        "## Full Period",
        "| case | total | annual | max dd | Calmar | 2018 | 2022 | 2024 | 2025 | 2026 | avg cash | avg holdings | trades | blocked candidates |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.iterrows():
        rows = period_map[row["case"]]
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | "
            f"{rows['2018']['total_return_pct']:.2f}% | {rows['2022']['total_return_pct']:.2f}% | "
            f"{rows['2024']['total_return_pct']:.2f}% | {rows['2025']['total_return_pct']:.2f}% | "
            f"{rows['2026']['total_return_pct']:.2f}% | {row['avg_cash_pct']:.2f}% | "
            f"{row['avg_holdings']:.2f} | {int(row['trade_records'])} | "
            f"{int(row.get('blocked_candidate_rows', 0))} ({row.get('blocked_candidate_pct', 0):.2f}%), "
            f"initial attempts {int(row.get('blocked_initial_attempts', 0))} |"
        )

    best = full.iloc[0]
    baseline = full[full["case"] == "baseline_v5"].iloc[0]
    lines.extend([
        "",
        "## Initial Assessment",
    ])
    if best["case"] != "baseline_v5" and best["total_return_pct"] > baseline["total_return_pct"]:
        dd_worsening = best["max_drawdown_pct"] - baseline["max_drawdown_pct"]
        if dd_worsening >= -3.0:
            lines.append(f"- Candidate `{best['case']}` beats baseline v5 on total return without breaching the drawdown guardrail.")
        else:
            lines.append(f"- Candidate `{best['case']}` beats return but worsens drawdown beyond the guardrail.")
    else:
        lines.append("- No downtrend-filter case beats baseline v5 on full-period return.")
    lines.append("- v4 is retained as a historical lower reference; primary comparison is against `baseline_v5`.")
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment():
    v5 = load_v5_module()
    import config as v5_config

    panel_columns = list(dict.fromkeys([*v5.PANEL_COLUMNS, "close_qfq", "bbi_qfq"]))
    panel = pd.read_parquet(v5.PANEL_PATH, columns=panel_columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = add_downtrend_features(panel)
    market = v5.load_market_index()
    if v5_config.END_DATE:
        panel = panel[panel["trade_date"] <= pd.Timestamp(v5_config.END_DATE)].copy()

    rows = []
    for case in CASES:
        rows.extend(run_case(v5, panel, market, case))

    results = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    v5_summary = json.loads(v5.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert_baseline_matches_v5(results, v5_summary)
    v4_summary = json.loads(V4_SUMMARY_PATH.read_text(encoding="utf-8"))
    write_summary(results, v5_summary, v4_summary)
    return results


def main():
    results = run_experiment()
    full = results[results["period"] == "full"].sort_values("annual_return_pct", ascending=False)
    print(full[[
        "case",
        "total_return_pct",
        "annual_return_pct",
        "max_drawdown_pct",
        "calmar_ratio",
        "avg_cash_pct",
        "avg_holdings",
        "trade_records",
        "blocked_candidate_rows",
        "blocked_initial_attempts",
        "blocked_candidate_pct",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

import csv
from contextlib import contextmanager
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v5").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V5_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v5"
OUTPUT_DIR = Path(__file__).parent / "v5_bull_early_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


CASES = [
    {
        "name": "baseline_v5",
        "bull_early_mode": "none",
        "use_v4_drawdown": False,
        "max_holdings": None,
        "max_total_exposure": None,
    },
    {
        "name": "bull_early_as_bull",
        "bull_early_mode": "strict",
        "use_v4_drawdown": False,
        "max_holdings": None,
        "max_total_exposure": None,
    },
    {
        "name": "bull_early_v4_drawdown",
        "bull_early_mode": "strict",
        "use_v4_drawdown": True,
        "max_holdings": None,
        "max_total_exposure": None,
    },
    {
        "name": "bull_early_exposure600",
        "bull_early_mode": "strict",
        "use_v4_drawdown": False,
        "max_holdings": 6,
        "max_total_exposure": 600_000.0,
    },
    {
        "name": "bull_fast_no_slope_as_bull",
        "bull_early_mode": "fast_no_slope",
        "use_v4_drawdown": False,
        "max_holdings": None,
        "max_total_exposure": None,
    },
    {
        "name": "bull_recent20_as_bull",
        "bull_early_mode": "breadth_recent20",
        "use_v4_drawdown": False,
        "max_holdings": None,
        "max_total_exposure": None,
    },
    {
        "name": "bull_recent20_v4_drawdown",
        "bull_early_mode": "breadth_recent20",
        "use_v4_drawdown": True,
        "max_holdings": None,
        "max_total_exposure": None,
    },
]


def load_v5_module():
    if str(V5_DIR) not in sys.path:
        sys.path.insert(0, str(V5_DIR))
    spec = importlib.util.spec_from_file_location("v5_run_backtest", V5_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        "low_holdings_days": int((nav_df["holdings"] < 5).sum()),
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


def build_bull_early_regime(v5, market, panel):
    regime = v5.build_market_regime(market, panel)
    if regime is None:
        return None
    regime = regime.copy()
    regime["market_ret_63"] = regime["close"] / regime["close"].shift(63) - 1.0
    regime["breadth_max20"] = regime["breadth_above_bbi"].rolling(20, min_periods=1).max()
    regime["bull_early_strict"] = (
        (regime["regime"] == "neutral")
        & (regime["close"] > regime["ma120"])
        & (regime["ma120_slope_20"] > 0)
        & (regime["market_ret_63"] > 0)
        & (regime["breadth_above_bbi"] >= 0.55)
    )
    regime["bull_early_fast_no_slope"] = (
        (regime["regime"] == "neutral")
        & (regime["close"] > regime["ma120"])
        & (regime["market_ret_63"] > 0)
        & (regime["breadth_above_bbi"] >= 0.55)
    )
    regime["bull_early_breadth_recent20"] = (
        (regime["regime"] == "neutral")
        & (regime["close"] > regime["ma120"])
        & (regime["ma120_slope_20"] > 0)
        & (regime["market_ret_63"] > 0)
        & (regime["breadth_max20"] >= 0.55)
    )
    return regime


def get_regime_router(regime_table, signal_date, bull_early_mode):
    if regime_table is None or signal_date not in regime_table.index:
        return "disabled"
    row = regime_table.loc[signal_date]
    if bull_early_mode == "strict" and bool(row.get("bull_early_strict", False)):
        return "bull_early"
    if bull_early_mode == "fast_no_slope" and bool(row.get("bull_early_fast_no_slope", False)):
        return "bull_early"
    if bull_early_mode == "breadth_recent20" and bool(row.get("bull_early_breadth_recent20", False)):
        return "bull_early"
    return str(row.get("regime", "unknown"))


def make_market_regime_hooks(v5, original_regime_pullback_thresholds, original_get_market_regime, regime_table, case):
    def wrapped_get_market_regime(market_regime, signal_date):
        regime_name, snapshot = original_get_market_regime(market_regime, signal_date)
        router = get_regime_router(regime_table, pd.Timestamp(signal_date), case["bull_early_mode"])
        if router == "bull_early":
            snapshot = dict(snapshot or {})
            snapshot["market_regime"] = "bull_early"
            snapshot["bull_early"] = True
            return "bull_early", snapshot
        return regime_name, snapshot

    def wrapped_regime_pullback_thresholds(market_regime_name):
        if case["bull_early_mode"] != "none" and market_regime_name in {"bull", "bull_early"}:
            if case["use_v4_drawdown"]:
                return -0.05, -0.03
            return -0.04, -0.026
        if case["use_v4_drawdown"] and market_regime_name in {"bull", "bull_early"}:
            return -0.05, -0.03
        return original_regime_pullback_thresholds(market_regime_name)

    return wrapped_get_market_regime, wrapped_regime_pullback_thresholds


@contextmanager
def apply_case_hooks(v5, case, regime_table):
    original_max_holdings = v5.LONG_MAX_HOLDINGS
    original_max_total_exposure = v5.LONG_MAX_TOTAL_EXPOSURE
    original_get_market_regime = v5.get_market_regime
    original_regime_pullback_thresholds = v5.regime_pullback_thresholds

    wrapped_get_market_regime, wrapped_regime_pullback_thresholds = make_market_regime_hooks(
        v5,
        original_regime_pullback_thresholds,
        original_get_market_regime,
        regime_table,
        case,
    )

    try:
        v5.get_market_regime = wrapped_get_market_regime
        v5.regime_pullback_thresholds = wrapped_regime_pullback_thresholds
        if case["max_holdings"] is not None:
            v5.LONG_MAX_HOLDINGS = int(case["max_holdings"])
        if case["max_total_exposure"] is not None:
            v5.LONG_MAX_TOTAL_EXPOSURE = float(case["max_total_exposure"])
        yield
    finally:
        v5.get_market_regime = original_get_market_regime
        v5.regime_pullback_thresholds = original_regime_pullback_thresholds
        v5.LONG_MAX_HOLDINGS = original_max_holdings
        v5.LONG_MAX_TOTAL_EXPOSURE = original_max_total_exposure


def build_trade_feature_index(panel, all_dates):
    feature_cols = ["ret_126", "above_ratio_63", "above_ratio_126", "ret_63", "pullback_63"]
    if len(all_dates) < 2:
        return pd.DataFrame(columns=["rebalance_date", "ts_code", *feature_cols])
    next_date_by_signal_date = {
        all_dates[i - 1]: all_dates[i]
        for i in range(1, len(all_dates))
    }
    features = panel.loc[
        panel["trade_date"].isin(next_date_by_signal_date),
        ["trade_date", "ts_code", *feature_cols],
    ].copy()
    features["rebalance_date"] = features["trade_date"].map(next_date_by_signal_date)
    return features.drop(columns=["trade_date"])


def build_buy_diagnostics(trades_df, trade_feature_index):
    empty = {
        "buy_ret_126_le_0": 0,
        "buy_above_ratio_63_lt_60": 0,
        "buy_missing_signal_features": 0,
    }
    if trades_df.empty or trade_feature_index.empty:
        return empty
    buys = trades_df[trades_df["action"] == "buy"].copy()
    if buys.empty:
        return empty
    features = trade_feature_index.copy()
    features["rebalance_date"] = pd.to_datetime(features["rebalance_date"])
    buys["date"] = pd.to_datetime(buys["date"])
    merged = buys.merge(
        features,
        left_on=["date", "ts_code"],
        right_on=["rebalance_date", "ts_code"],
        how="left",
    )
    diagnostic_cols = ["ret_126", "above_ratio_63", "above_ratio_126", "ret_63", "pullback_63"]
    missing_signal_features = merged[diagnostic_cols].isna().any(axis=1)
    return {
        "buy_ret_126_le_0": int((pd.to_numeric(merged["ret_126"], errors="coerce") <= 0).sum()),
        "buy_above_ratio_63_lt_60": int((pd.to_numeric(merged["above_ratio_63"], errors="coerce") < 0.60).sum()),
        "buy_missing_signal_features": int(missing_signal_features.sum()),
    }


def assert_baseline_matches_v5(results, v5_summary):
    baseline = results[(results["case"] == "baseline_v5") & (results["period"] == "full")]
    if baseline.empty:
        raise AssertionError("baseline_v5 full-period result is missing")
    row = baseline.iloc[0]
    checks = [
        ("final_nav", 1e-2),
        ("total_return_pct", 1e-4),
        ("annual_return_pct", 1e-4),
        ("max_drawdown_pct", 1e-4),
        ("calmar_ratio", 1e-4),
        ("trade_records", 0),
    ]
    for key, tolerance in checks:
        actual = float(row[key])
        expected = float(v5_summary[key])
        if abs(actual - expected) > tolerance:
            raise AssertionError(f"baseline_v5 {key}={actual} does not match v5 summary {expected}")


def run_case(v5, panel, market, trade_feature_index, regime_table, case):
    periods = {str(year): (f"{year}-01-01", f"{year}-12-31") for year in range(2018, 2027)}
    periods["full"] = ("2018-01-01", "2026-05-14")
    rows = []
    with apply_case_hooks(v5, case, regime_table):
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v5.run_backtest(
            panel,
            market,
            "2018-01-01",
            None,
        )
    buy_diag = build_buy_diagnostics(trades_df, trade_feature_index)
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "period": period_name,
            "bull_early_mode": case["bull_early_mode"],
            "use_v4_drawdown": case["use_v4_drawdown"],
            "max_holdings": case["max_holdings"] or v5.LONG_MAX_HOLDINGS,
            "max_total_exposure": case["max_total_exposure"] or v5.LONG_MAX_TOTAL_EXPOSURE,
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        if period_name == "full":
            row.update(buy_diag)
            mode = case["bull_early_mode"]
            col = {
                "strict": "bull_early_strict",
                "fast_no_slope": "bull_early_fast_no_slope",
                "breadth_recent20": "bull_early_breadth_recent20",
            }.get(mode)
            if col and regime_table is not None:
                start = pd.Timestamp("2018-01-01")
                end = pd.Timestamp(row["end_date"])
                regime_sub = regime_table[(regime_table.index >= start) & (regime_table.index <= end)]
                row["bull_early_days"] = int(regime_sub[col].sum())
            else:
                row["bull_early_days"] = 0
        rows.append(row)
    return rows, nav_df, trades_df, scores_df


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
        "# v5 Bull Early Experiment",
        "",
        "## Baseline",
        f"- v5 total return: {v5_summary['total_return_pct']}%",
        f"- v5 annual return: {v5_summary['annual_return_pct']}%",
        f"- v5 max drawdown: {v5_summary['max_drawdown_pct']}%",
        f"- v4 total return: {v4_summary['total_return_pct']}%",
        f"- v4 annual return: {v4_summary['annual_return_pct']}%",
        f"- v4 max drawdown: {v4_summary['max_drawdown_pct']}%",
        "",
        "## Notes",
        "- All trading decisions use signal_date data and execute on the next trading day open.",
        "- Yearly return uses each year's first available NAV as the denominator, so it is an in-period comparison metric rather than prior-year-end calendar return.",
        "- `bull_early_days` counts only dates inside the 2018-01-01 to backtest end window.",
        "",
        "## Full Period",
        "| case | total | annual | max dd | Calmar | 2019 | 2022 | 2025 | 2026 | avg cash | avg holdings | trades | ret126<=0 | above63<0.60 | missing | bull_early_days |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.iterrows():
        rows = period_map[row["case"]]
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | "
            f"{rows['2019']['total_return_pct']:.2f}% | {rows['2022']['total_return_pct']:.2f}% | "
            f"{rows['2025']['total_return_pct']:.2f}% | {rows['2026']['total_return_pct']:.2f}% | "
            f"{row['avg_cash_pct']:.2f}% | {row['avg_holdings']:.2f} | {int(row['trade_records'])} | "
            f"{int(row.get('buy_ret_126_le_0', 0))} | {int(row.get('buy_above_ratio_63_lt_60', 0))} | "
            f"{int(row.get('buy_missing_signal_features', 0))} | {int(row.get('bull_early_days', 0))} |"
        )
    lines.extend([
        "",
        "## Yearly In-Period Return",
        "| case | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for _, row in full.iterrows():
        rows = period_map[row["case"]]
        yearly = " | ".join(f"{rows[str(year)]['total_return_pct']:.2f}%" for year in range(2018, 2027))
        lines.append(f"| {row['case']} | {yearly} |")
    lines.extend([
        "",
        "## Conclusion",
        "",
        "Do not merge these bull-early variants into v5 now. No tested variant improves full-period return and max drawdown at the same time versus baseline v5.",
    ])
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_v4_summary():
    path = V5_DIR.parent / "v4" / "output" / "summary.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_experiment():
    v5 = load_v5_module()
    import config as v5_config

    panel = pd.read_parquet(v5.PANEL_PATH, columns=v5.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = v5.load_market_index()
    panel_for_dates = panel.copy()
    if v5_config.END_DATE:
        panel_for_dates = panel_for_dates[panel_for_dates["trade_date"] <= pd.Timestamp(v5_config.END_DATE)].copy()
    panel_for_dates = panel_for_dates[panel_for_dates["trade_date"] >= pd.Timestamp(v5_config.BACKTEST_START_DATE)].copy()
    all_dates = sorted(panel_for_dates["trade_date"].drop_duplicates())
    trade_feature_index = build_trade_feature_index(panel, all_dates)
    regime_table = build_bull_early_regime(v5, market, panel)

    rows = []
    last_nav_df = None
    last_trades_df = None
    last_scores_df = None
    for case in CASES:
        case_rows, nav_df, trades_df, scores_df = run_case(v5, panel, market, trade_feature_index, regime_table, case)
        rows.extend(case_rows)
        if case["name"] == "baseline_v5":
            last_nav_df = nav_df
            last_trades_df = trades_df
            last_scores_df = scores_df

    results = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    v5_summary = json.loads(v5.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert_baseline_matches_v5(results, v5_summary)
    v4_summary = load_v4_summary()
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
        "trade_records",
        "buy_ret_126_le_0",
        "buy_above_ratio_63_lt_60",
        "buy_missing_signal_features",
        "bull_early_days",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

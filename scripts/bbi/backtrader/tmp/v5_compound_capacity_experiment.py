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
V4_SUMMARY_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v4" / "output" / "summary.json"
V1_STATS_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v1" / "output" / "stats_summary.csv"
OUTPUT_DIR = Path(__file__).parent / "v5_compound_capacity_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


CASES = [
    {"name": "baseline_v5", "max_holdings": 5, "max_total_exposure": 500_000.0},
    {"name": "capacity_6_600k", "max_holdings": 6, "max_total_exposure": 600_000.0},
    {"name": "capacity_7_700k", "max_holdings": 7, "max_total_exposure": 700_000.0},
    {"name": "capacity_8_800k", "max_holdings": 8, "max_total_exposure": 800_000.0},
]


def load_v5_module():
    if str(V5_DIR) not in sys.path:
        sys.path.insert(0, str(V5_DIR))
    spec = importlib.util.spec_from_file_location("v5_run_backtest_capacity", V5_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def apply_capacity_case(v5, case):
    old_max_holdings = v5.LONG_MAX_HOLDINGS
    old_max_total_exposure = v5.LONG_MAX_TOTAL_EXPOSURE
    try:
        v5.LONG_MAX_HOLDINGS = int(case["max_holdings"])
        v5.LONG_MAX_TOTAL_EXPOSURE = float(case["max_total_exposure"])
        yield
    finally:
        v5.LONG_MAX_HOLDINGS = old_max_holdings
        v5.LONG_MAX_TOTAL_EXPOSURE = old_max_total_exposure


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


def summarize_v1():
    stats = pd.read_csv(V1_STATS_PATH)
    return {
        "stock_count": int(len(stats)),
        "avg_annual_return_pct": round(float(stats["annual_return_pct"].mean()), 4),
        "median_annual_return_pct": round(float(stats["annual_return_pct"].median()), 4),
        "best_annual_return_pct": round(float(stats["annual_return_pct"].max()), 4),
        "avg_max_drawdown_pct": round(float(stats["max_drawdown_pct"].mean()), 4),
    }


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
    with apply_capacity_case(v5, case):
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v5.run_backtest(panel, market, "2018-01-01", None)
    rows = []
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "period": period_name,
            "max_holdings": case["max_holdings"],
            "max_total_exposure": case["max_total_exposure"],
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        if period_name == "full":
            row.update({
                "market_block_days": int(stats.get("market_block_days", 0)),
                "regime_bear_block_days": int(stats.get("regime_bear_block_days", 0)),
                "regime_bear_exit_fills": int(stats.get("regime_bear_exit_fills", 0)),
            })
        rows.append(row)
    return rows


def write_summary(results, v5_summary, v4_summary, v1_summary):
    full = results[results["period"] == "full"].sort_values(
        ["annual_return_pct", "max_drawdown_pct"],
        ascending=[False, False],
    )
    period_map = {
        case: {row["period"]: row for _, row in group.iterrows()}
        for case, group in results.groupby("case")
    }
    lines = [
        "# v5 Compound Capacity Experiment",
        "",
        "## Baselines",
        f"- v1 avg annual return: {v1_summary['avg_annual_return_pct']}%",
        f"- v1 median annual return: {v1_summary['median_annual_return_pct']}%",
        f"- v1 best annual return: {v1_summary['best_annual_return_pct']}%",
        f"- v1 avg max drawdown: {v1_summary['avg_max_drawdown_pct']}%",
        f"- v4 total return: {v4_summary['total_return_pct']}%",
        f"- v4 annual return: {v4_summary['annual_return_pct']}%",
        f"- v4 max drawdown: {v4_summary['max_drawdown_pct']}%",
        f"- v5 total return: {v5_summary['total_return_pct']}%",
        f"- v5 annual return: {v5_summary['annual_return_pct']}%",
        f"- v5 max drawdown: {v5_summary['max_drawdown_pct']}%",
        "",
        "## Full Period",
        "| case | total | annual | max dd | Calmar | 2018 | 2022 | 2024 | 2025 | 2026 | avg cash | avg holdings | trades | bear exits |",
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
            f"{int(row.get('regime_bear_exit_fills', 0))} |"
        )
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment():
    v5 = load_v5_module()
    import config as v5_config

    panel = pd.read_parquet(v5.PANEL_PATH, columns=v5.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
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
    v1_summary = summarize_v1()
    write_summary(results, v5_summary, v4_summary, v1_summary)
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
        "regime_bear_exit_fills",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()


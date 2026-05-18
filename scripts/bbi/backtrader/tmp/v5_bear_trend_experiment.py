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
OUTPUT_DIR = Path(__file__).parent / "v5_bear_trend_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


CASES = [
    {
        "name": "baseline_v5",
        "bear_mode": "raw",
        "clear_all_on_bear": False,
    },
    {
        "name": "bear_2of3_confirmed",
        "bear_mode": "2of3",
        "clear_all_on_bear": False,
    },
    {
        "name": "bear_3of5_confirmed",
        "bear_mode": "3of5",
        "clear_all_on_bear": False,
    },
    {
        "name": "bear_3of5_clear_all",
        "bear_mode": "3of5",
        "clear_all_on_bear": True,
    },
    {
        "name": "bear_state_6of10_exit_6of10",
        "bear_mode": "state_6of10",
        "clear_all_on_bear": False,
    },
]


def load_v5_module():
    if str(V5_DIR) not in sys.path:
        sys.path.insert(0, str(V5_DIR))
    spec = importlib.util.spec_from_file_location("v5_run_backtest_bear_trend", V5_DIR / "20_run_backtest.py")
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


def apply_bear_confirmation(regime, mode):
    regime = regime.copy()
    raw_bear = regime["regime"].eq("bear")
    if mode == "raw":
        regime["bear_raw"] = raw_bear
        regime["bear_confirmed"] = raw_bear
        return regime
    if mode == "state_6of10":
        return apply_bear_state_machine(regime)
    if mode == "2of3":
        confirmed = raw_bear.rolling(3, min_periods=3).sum() >= 2
    elif mode == "3of5":
        confirmed = raw_bear.rolling(5, min_periods=5).sum() >= 3
    else:
        raise ValueError(f"unknown bear mode {mode}")
    regime["bear_raw"] = raw_bear
    regime["bear_confirmed"] = confirmed.fillna(False)
    regime.loc[raw_bear & ~regime["bear_confirmed"], "regime"] = "neutral"
    return regime


def apply_bear_state_machine(regime):
    regime = regime.copy()
    raw_bear = regime["regime"].eq("bear")
    exit_raw = (
        (regime["close"] > regime["ma120"])
        & (regime["ma120_slope_20"] > 0)
        & (regime["breadth_above_bbi"] > 0.55)
        & (regime["dd_252"] > -0.10)
    )
    entry_confirmed = raw_bear.rolling(10, min_periods=10).sum() >= 6
    exit_confirmed = exit_raw.rolling(10, min_periods=10).sum() >= 6

    in_bear = False
    states = []
    for date in regime.index:
        if in_bear:
            if bool(exit_confirmed.loc[date]):
                in_bear = False
        elif bool(entry_confirmed.loc[date]):
            in_bear = True
        states.append(in_bear)

    regime["bear_raw"] = raw_bear
    regime["bear_exit_raw"] = exit_raw
    regime["bear_confirmed"] = pd.Series(states, index=regime.index)
    regime.loc[regime["bear_confirmed"], "regime"] = "bear"
    regime.loc[raw_bear & ~regime["bear_confirmed"], "regime"] = "neutral"
    return regime


@contextmanager
def apply_case_hooks(v5, case):
    original_build_market_regime = v5.build_market_regime
    original_bear_exit_loss_threshold = v5.REGIME_BEAR_EXIT_LOSS_THRESHOLD

    def wrapped_build_market_regime(market, panel):
        regime = original_build_market_regime(market, panel)
        if regime is None:
            return None
        return apply_bear_confirmation(regime, case["bear_mode"])

    try:
        v5.build_market_regime = wrapped_build_market_regime
        if case["clear_all_on_bear"]:
            v5.REGIME_BEAR_EXIT_LOSS_THRESHOLD = 999.0
        yield
    finally:
        v5.build_market_regime = original_build_market_regime
        v5.REGIME_BEAR_EXIT_LOSS_THRESHOLD = original_bear_exit_loss_threshold


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


def run_case(v5, panel, market, case):
    periods = {str(year): (f"{year}-01-01", f"{year}-12-31") for year in range(2018, 2027)}
    periods["full"] = ("2018-01-01", "2026-05-14")
    rows = []
    with apply_case_hooks(v5, case):
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v5.run_backtest(
            panel,
            market,
            "2018-01-01",
            None,
        )
    bear_days = 0
    bear_block_days = int(stats.get("regime_bear_block_days", 0))
    if not rebalance_df.empty and "market_regime" in rebalance_df:
        bear_days = int((rebalance_df["market_regime"] == "bear").sum())
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "period": period_name,
            "bear_mode": case["bear_mode"],
            "clear_all_on_bear": case["clear_all_on_bear"],
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        if period_name == "full":
            row.update({
                "market_block_days": int(stats.get("market_block_days", 0)),
                "regime_bear_block_days": bear_block_days,
                "regime_bear_exit_signals": int(stats.get("regime_bear_exit_signals", 0)),
                "regime_bear_exit_fills": int(stats.get("regime_bear_exit_fills", 0)),
                "bear_rebalance_days": bear_days,
            })
        rows.append(row)
    return rows


def load_v4_summary():
    path = V5_DIR.parent / "v4" / "output" / "summary.json"
    return json.loads(path.read_text(encoding="utf-8"))


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
        "# v5 Bear Trend Confirmation Experiment",
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
        "- `bear_2of3_confirmed` and `bear_3of5_confirmed` convert raw one-day bear signals back to neutral until the confirmation window is met.",
        "- `bear_3of5_clear_all` is a stress test: using v5's previous confirmed bear state, holdings with computable profit become sell candidates through a high bear-exit threshold; execution can still be delayed by suspension, limit-down open, or missing data.",
        "- `bear_state_6of10_exit_6of10` is a true state-machine test: 6 of 10 raw bear days enter bear state, and 6 of 10 recovery days exit bear state.",
        "",
        "## Full Period",
        "| case | total | annual | max dd | Calmar | 2018 | 2022 | 2025 | 2026 | avg cash | avg holdings | zero days | trades | bear block | bear exits | bear rebalance days |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.iterrows():
        rows = period_map[row["case"]]
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | "
            f"{rows['2018']['total_return_pct']:.2f}% | {rows['2022']['total_return_pct']:.2f}% | "
            f"{rows['2025']['total_return_pct']:.2f}% | {rows['2026']['total_return_pct']:.2f}% | "
            f"{row['avg_cash_pct']:.2f}% | {row['avg_holdings']:.2f} | {int(row['zero_holdings_days'])} | "
            f"{int(row['trade_records'])} | {int(row.get('regime_bear_block_days', 0))} | "
            f"{int(row.get('regime_bear_exit_fills', 0))} | {int(row.get('bear_rebalance_days', 0))} |"
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
        "zero_holdings_days",
        "trade_records",
        "regime_bear_block_days",
        "regime_bear_exit_fills",
        "bear_rebalance_days",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

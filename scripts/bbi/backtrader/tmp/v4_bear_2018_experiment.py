import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v4").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V4_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v4"
V4_OUTPUT = V4_DIR / "output"
V1_OUTPUT = ROOT / "scripts" / "bbi" / "backtrader" / "v1" / "output"
OUTPUT_DIR = Path(__file__).parent / "v4_bear_2018_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


def load_v4_module():
    if str(V4_DIR) not in sys.path:
        sys.path.insert(0, str(V4_DIR))
    spec = importlib.util.spec_from_file_location("v4_run_backtest", V4_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_market_features(market):
    market = market.copy().sort_index()
    close = pd.to_numeric(market["close"], errors="coerce")
    market["ma120"] = close.rolling(120, min_periods=120).mean()
    market["ma200"] = close.rolling(200, min_periods=200).mean()
    market["bbi_5_20_60_120"] = (
        close.rolling(5, min_periods=5).mean()
        + close.rolling(20, min_periods=20).mean()
        + close.rolling(60, min_periods=60).mean()
        + close.rolling(120, min_periods=120).mean()
    ) / 4.0
    market["ret_5"] = close / close.shift(5) - 1.0
    market["ret_20"] = close / close.shift(20) - 1.0
    market["dd_20"] = close / close.rolling(20, min_periods=20).max() - 1.0
    return market


def make_market_gate_fn(original_short_drop, market, gate_name):
    # run_backtest() passes the previous completed trading day as signal_date.
    # This gate only uses data up to that completed day, so it stays aligned with
    # the existing no-lookahead timing model.
    def gate(signal_date):
        if gate_name == "none":
            return False, "market_gate_none", {}
        if signal_date not in market.index:
            return True, "missing_market", {}
        row = market.loc[signal_date]
        close = float(row.get("close", np.nan))
        ma120 = float(row.get("ma120", np.nan))
        ma200 = float(row.get("ma200", np.nan))
        bbi = float(row.get("bbi_5_20_60_120", np.nan))
        snapshot = {
            "market_close": close,
            "market_ma120": ma120,
            "market_ma200": ma200,
            "market_bbi": bbi,
            "market_ret_5": float(row.get("ret_5", np.nan)),
            "market_ret_20": float(row.get("ret_20", np.nan)),
            "market_dd_20": float(row.get("dd_20", np.nan)),
        }

        if gate_name == "ma120":
            if not np.isfinite(ma120):
                return True, "market_gate_warmup", snapshot
            if close <= ma120:
                return True, "market_below_ma120", snapshot
        elif gate_name == "ma200":
            if not np.isfinite(ma200):
                return True, "market_gate_warmup", snapshot
            if close <= ma200:
                return True, "market_below_ma200", snapshot
        elif gate_name == "bbi_5_20_60_120":
            if not np.isfinite(bbi):
                return True, "market_gate_warmup", snapshot
            if close <= bbi:
                return True, "market_below_bbi", snapshot
        elif gate_name == "ma120_or_bbi":
            if not np.isfinite(ma120) or not np.isfinite(bbi):
                return True, "market_gate_warmup", snapshot
            if close <= ma120 and close <= bbi:
                return True, "market_below_ma120_and_bbi", snapshot
        else:
            raise ValueError(f"Unknown market gate: {gate_name}")

        return False, f"market_gate_{gate_name}_ok", snapshot

    def wrapped_market_short_drop_blocks_buy(current_market, signal_date):
        blocked, reason, snapshot = original_short_drop(current_market, signal_date)
        if blocked:
            return blocked, reason, snapshot
        gate_blocked, gate_reason, gate_snapshot = gate(signal_date)
        snapshot.update(gate_snapshot)
        return gate_blocked, gate_reason, snapshot

    return wrapped_market_short_drop_blocks_buy


def compute_v4_2018_benchmark():
    nav = pd.read_csv(V4_OUTPUT / "nav_series.csv", parse_dates=["date"])
    nav_2018 = nav[(nav["date"] >= "2018-01-01") & (nav["date"] <= "2018-12-31")].copy()
    if nav_2018.empty:
        return {}
    nav_2018["curve"] = nav_2018["nav"] / nav_2018["nav"].iloc[0]
    dd = nav_2018["curve"] / nav_2018["curve"].cummax() - 1.0
    total_ret = nav_2018["nav"].iloc[-1] / nav_2018["nav"].iloc[0] - 1.0
    days = max((nav_2018["date"].iloc[-1] - nav_2018["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    max_dd = float(dd.min())
    return {
        "v4_2018_start_nav": float(nav_2018["nav"].iloc[0]),
        "v4_2018_end_nav": float(nav_2018["nav"].iloc[-1]),
        "v4_2018_return_pct": round(total_ret * 100.0, 4),
        "v4_2018_annual_return_pct": round(annual_ret * 100.0, 4),
        "v4_2018_max_drawdown_pct": round(max_dd * 100.0, 4),
        "v4_2018_calmar": round((annual_ret * 100.0) / abs(max_dd * 100.0), 4) if max_dd < 0 else 0.0,
    }


def compute_v1_reference():
    stats = pd.read_csv(V1_OUTPUT / "stats_summary.csv")
    annual = pd.to_numeric(stats["annual_return_pct"], errors="coerce")
    calmar = pd.to_numeric(stats["calmar_ratio"], errors="coerce")
    top = stats.loc[pd.to_numeric(stats["calmar_ratio"], errors="coerce").idxmax()]
    return {
        "v1_median_annual_return_pct": round(float(annual.median()), 4),
        "v1_median_calmar_ratio": round(float(calmar.median()), 4),
        "v1_top_calmar_ts_code": str(top["ts_code"]),
        "v1_top_calmar_name": str(top["name"]),
        "v1_top_calmar_ratio": round(float(top["calmar_ratio"]), 4),
        "v1_top_annual_return_pct": round(float(top["annual_return_pct"]), 4),
    }


def run_grid():
    v4 = load_v4_module()
    panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=v4.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[(panel["trade_date"] >= "2017-01-01") & (panel["trade_date"] <= "2018-12-31")].copy()
    market = pd.read_parquet(V4_OUTPUT / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")
    market = build_market_features(market)
    market = market[(market.index >= "2017-01-01") & (market.index <= "2018-12-31")].copy()

    pullback_thresholds = [-0.05, -0.06, -0.07, -0.08, -0.09, -0.12, -0.15]
    market_gates = ["none", "ma120", "ma200", "bbi_5_20_60_120", "ma120_or_bbi"]
    baseline = compute_v4_2018_benchmark()
    v1_ref = compute_v1_reference()
    original_market_short_drop = v4.market_short_drop_blocks_buy
    original_pullback_threshold = v4.LONG_PULLBACK_THRESHOLD
    rows = []

    try:
        for gate_name in market_gates:
            v4.market_short_drop_blocks_buy = make_market_gate_fn(original_market_short_drop, market, gate_name)
            for threshold in pullback_thresholds:
                v4.LONG_PULLBACK_THRESHOLD = threshold
                nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v4.run_backtest(
                    panel,
                    market,
                    "2018-01-01",
                    "2018-12-31",
                )

                sell_pnl = pd.to_numeric(trades_df.loc[trades_df["action"] == "sell", "pnl"], errors="coerce").fillna(0.0).sum()
                buy_count = int((trades_df["action"] == "buy").sum()) if not trades_df.empty else 0
                sell_count = int((trades_df["action"] == "sell").sum()) if not trades_df.empty else 0
                rows.append({
                    "market_gate": gate_name,
                    "pullback_threshold": threshold,
                    "start_date": stats["start_date"],
                    "end_date": stats["end_date"],
                    "final_nav": round(float(stats["final_nav"]), 2),
                    "total_return_pct": round(float(stats["total_return_pct"]), 4),
                    "annual_return_pct": round(float(stats["annual_return_pct"]), 4),
                    "max_drawdown_pct": round(float(stats["max_drawdown_pct"]), 4),
                    "calmar_ratio": round(float(stats["calmar_ratio"]), 4),
                    "trade_records": int(stats["trade_records"]),
                    "buy_fills": int(stats["buy_fills"]),
                    "add_buy_fills": int(stats["add_buy_fills"]),
                    "sell_fills": int(stats["sell_fills"]),
                    "buy_count": buy_count,
                    "sell_count": sell_count,
                    "sell_pnl_sum": round(float(sell_pnl), 2),
                    "market_block_days": int(stats["market_block_days"]),
                    "stop_loss_fills": int(stats["stop_loss_fills"]),
                    "limit_down_exit_fills": int(stats["limit_down_exit_fills"]),
                    "bearish_volume_exit_fills": int(stats["bearish_volume_exit_fills"]),
                })
    finally:
        v4.market_short_drop_blocks_buy = original_market_short_drop
        v4.LONG_PULLBACK_THRESHOLD = original_pullback_threshold

    results = pd.DataFrame(rows)
    results = results.sort_values(
        ["total_return_pct", "max_drawdown_pct", "trade_records"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    results.insert(0, "rank", np.arange(1, len(results) + 1))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)

    best = results.iloc[0].to_dict() if not results.empty else {}
    summary_lines = [
        "# v4 熊市参数实验结果",
        "",
        "## 结论",
        f"- v4 2018 基准收益: {baseline.get('v4_2018_return_pct', float('nan')):.2f}%",
        f"- v4 2018 基准最大回撤: {baseline.get('v4_2018_max_drawdown_pct', float('nan')):.2f}%",
        f"- v1 参考中位年化收益: {v1_ref['v1_median_annual_return_pct']:.2f}%",
        f"- v1 参考中位 Calmar: {v1_ref['v1_median_calmar_ratio']:.4f}",
        "",
        "## 最优参数",
    ]
    if best:
        summary_lines.extend([
            f"- market_gate: {best['market_gate']}",
            f"- pullback_threshold: {best['pullback_threshold']:.2%}",
            f"- 2018 annual_return_pct: {best['annual_return_pct']:.2f}%",
            f"- 2018 max_drawdown_pct: {best['max_drawdown_pct']:.2f}%",
            f"- calmar_ratio: {best['calmar_ratio']:.4f}",
            f"- trade_records: {int(best['trade_records'])}",
            f"- sell_pnl_sum: {best['sell_pnl_sum']:.2f}",
            "",
            "## v1 参考",
            f"- top calmar stock: {v1_ref['v1_top_calmar_ts_code']} {v1_ref['v1_top_calmar_name']}",
            f"- top calmar ratio: {v1_ref['v1_top_calmar_ratio']:.4f}",
            f"- top annual return: {v1_ref['v1_top_annual_return_pct']:.4f}%",
        ])

    SUMMARY_PATH.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return results, baseline, v1_ref


def main():
    results, baseline, v1_ref = run_grid()
    if results.empty:
        print("No experiment results.")
        return
    best = results.iloc[0]
    print(f"Best gate={best['market_gate']}, threshold={best['pullback_threshold']:.2%}")
    print(
        f"2018 annual return={best['annual_return_pct']:.2f}% "
        f"maxDD={best['max_drawdown_pct']:.2f}% "
        f"Calmar={best['calmar_ratio']:.4f}"
    )
    print(
        f"Baseline v4 2018 return={baseline['v4_2018_return_pct']:.2f}% "
        f"maxDD={baseline['v4_2018_max_drawdown_pct']:.2f}%"
    )
    print(
        f"v1 median annual return={v1_ref['v1_median_annual_return_pct']:.2f}% "
        f"median Calmar={v1_ref['v1_median_calmar_ratio']:.4f}"
    )


if __name__ == "__main__":
    main()

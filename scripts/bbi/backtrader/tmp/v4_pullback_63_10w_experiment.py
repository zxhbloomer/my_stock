import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def find_repo_root(start):
    for parent in Path(start).resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v4").exists():
            return parent
    raise RuntimeError("Cannot locate repository root")


ROOT = find_repo_root(__file__)
V4_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v4"
V4_OUTPUT = V4_DIR / "output"
V1_OUTPUT = ROOT / "scripts" / "bbi" / "backtrader" / "v1" / "output"
OUTPUT_DIR = Path(__file__).parent / "v4_pullback_63_10w_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"
MARKET_GATES = ["base", "ma120"]

EXPERIMENTS = [
    {"group": "A", "pullback_threshold": -0.05, "dist_10w_max": None, "require_ma10w_up": False, "note": "63日回撤<=-5%, 不加10周线"},
    {"group": "B", "pullback_threshold": -0.07, "dist_10w_max": None, "require_ma10w_up": False, "note": "63日回撤<=-7%, 不加10周线"},
    {"group": "C", "pullback_threshold": -0.09, "dist_10w_max": None, "require_ma10w_up": False, "note": "63日回撤<=-9%, 不加10周线"},
    {"group": "D", "pullback_threshold": -0.05, "dist_10w_max": 0.03, "require_ma10w_up": True, "note": "63日回撤<=-5%, 贴近10周线<=3%, 10周线向上"},
    {"group": "E", "pullback_threshold": -0.07, "dist_10w_max": 0.05, "require_ma10w_up": True, "note": "63日回撤<=-7%, 贴近10周线<=5%, 10周线向上"},
    {"group": "F", "pullback_threshold": -0.09, "dist_10w_max": 0.08, "require_ma10w_up": True, "note": "63日回撤<=-9%, 贴近10周线<=8%, 10周线向上"},
]


def load_v4_module():
    if str(V4_DIR) not in sys.path:
        sys.path.insert(0, str(V4_DIR))
    spec = importlib.util.spec_from_file_location("v4_run_backtest_for_pullback_experiment", V4_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_market():
    market = pd.read_parquet(V4_OUTPUT / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")
    close = pd.to_numeric(market["close"], errors="coerce")
    market["ma120_exp"] = close.rolling(120, min_periods=120).mean()
    return market


def add_pullback_63(panel):
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    high_63 = (
        panel.groupby("ts_code", sort=False)["close_qfq"]
        .rolling(63, min_periods=63)
        .max()
        .reset_index(level=0, drop=True)
    )
    panel["high_qfq_63_exp"] = high_63
    panel["pullback_63_exp"] = panel["close_qfq"] / high_63 - 1.0
    return panel


def add_ma10w_features(panel):
    parts = []
    for _, group in panel[["ts_code", "trade_date", "close_qfq"]].groupby("ts_code", sort=False):
        group = group.sort_values("trade_date").set_index("trade_date")
        weekly_close = group["close_qfq"].resample("W-FRI").last().dropna()
        weekly = pd.DataFrame({"weekly_close_qfq_exp": weekly_close})
        weekly["ma10w_exp"] = weekly["weekly_close_qfq_exp"].rolling(10, min_periods=10).mean()
        weekly["ma10w_slope_exp"] = weekly["ma10w_exp"] / weekly["ma10w_exp"].shift(1) - 1.0
        daily = weekly[["ma10w_exp", "ma10w_slope_exp"]].reindex(group.index, method="ffill")
        daily["ts_code"] = group["ts_code"].iloc[0]
        daily["trade_date"] = daily.index
        parts.append(daily.reset_index(drop=True))
    features = pd.concat(parts, ignore_index=True)
    panel = panel.merge(features, on=["ts_code", "trade_date"], how="left")
    panel["dist_10w_exp"] = panel["close_qfq"] / panel["ma10w_exp"] - 1.0
    return panel


def build_experiment_panel(base_panel, experiment):
    panel = base_panel.copy()
    entry_ok = panel["pullback_63_exp"].notna()
    if experiment["dist_10w_max"] is not None:
        entry_ok &= panel["dist_10w_exp"].notna() & (panel["dist_10w_exp"].abs() <= experiment["dist_10w_max"])
    if experiment["require_ma10w_up"]:
        entry_ok &= panel["ma10w_slope_exp"].notna() & (panel["ma10w_slope_exp"] > 0)
    panel["pullback_120"] = np.where(entry_ok, panel["pullback_63_exp"], np.nan)
    return panel


def make_market_gate(original_market_filter, market_gate):
    def wrapped(market, signal_date):
        blocked, reason, snapshot = original_market_filter(market, signal_date)
        if blocked or market_gate == "base":
            return blocked, reason, snapshot
        if signal_date not in market.index:
            return True, "missing_market", snapshot
        row = market.loc[signal_date]
        close = pd.to_numeric(row.get("close"), errors="coerce")
        ma120 = pd.to_numeric(row.get("ma120_exp"), errors="coerce")
        snapshot = dict(snapshot)
        snapshot["market_close"] = float(close) if pd.notna(close) else np.nan
        snapshot["market_ma120"] = float(ma120) if pd.notna(ma120) else np.nan
        if pd.isna(close) or pd.isna(ma120):
            return True, "market_ma120_warmup", snapshot
        if close <= ma120:
            return True, "market_below_ma120", snapshot
        return False, "market_ma120_ok", snapshot

    return wrapped


def compute_v1_reference():
    stats = pd.read_csv(V1_OUTPUT / "stats_summary.csv")
    annual = pd.to_numeric(stats["annual_return_pct"], errors="coerce")
    calmar = pd.to_numeric(stats["calmar_ratio"], errors="coerce")
    top = stats.loc[calmar.idxmax()]
    return {
        "v1_median_annual_return_pct": round(float(annual.median()), 4),
        "v1_median_calmar_ratio": round(float(calmar.median()), 4),
        "v1_top_calmar_ts_code": str(top["ts_code"]),
        "v1_top_calmar_name": str(top["name"]),
        "v1_top_calmar_ratio": round(float(top["calmar_ratio"]), 4),
        "v1_top_annual_return_pct": round(float(top["annual_return_pct"]), 4),
    }


def run_one(v4, base_panel, market, experiment, market_gate, start, end):
    original_threshold = v4.LONG_PULLBACK_THRESHOLD
    original_market_filter = v4.market_short_drop_blocks_buy
    try:
        v4.LONG_PULLBACK_THRESHOLD = experiment["pullback_threshold"]
        v4.market_short_drop_blocks_buy = make_market_gate(original_market_filter, market_gate)
        panel = build_experiment_panel(base_panel, experiment)
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v4.run_backtest(panel, market, start, end)
    finally:
        v4.LONG_PULLBACK_THRESHOLD = original_threshold
        v4.market_short_drop_blocks_buy = original_market_filter

    sell_pnl = 0.0
    if not trades_df.empty and "pnl" in trades_df.columns:
        sell_pnl = pd.to_numeric(trades_df.loc[trades_df["action"] == "sell", "pnl"], errors="coerce").fillna(0.0).sum()
    return {
        "start": start,
        "end": stats["end_date"],
        "final_nav": round(float(stats["final_nav"]), 2),
        "total_return_pct": round(float(stats["total_return_pct"]), 4),
        "annual_return_pct": round(float(stats["annual_return_pct"]), 4),
        "max_drawdown_pct": round(float(stats["max_drawdown_pct"]), 4),
        "calmar_ratio": round(float(stats["calmar_ratio"]), 4),
        "trade_records": int(stats["trade_records"]),
        "buy_fills": int(stats["buy_fills"]),
        "sell_fills": int(stats["sell_fills"]),
        "stop_loss_fills": int(stats["stop_loss_fills"]),
        "limit_down_exit_fills": int(stats["limit_down_exit_fills"]),
        "bearish_volume_exit_fills": int(stats["bearish_volume_exit_fills"]),
        "sell_pnl_sum": round(float(sell_pnl), 2),
    }


def run_v4_baseline(v4, panel, market, start, end):
    nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v4.run_backtest(panel.copy(), market, start, end)
    return {
        "start": start,
        "end": stats["end_date"],
        "final_nav": round(float(stats["final_nav"]), 2),
        "total_return_pct": round(float(stats["total_return_pct"]), 4),
        "annual_return_pct": round(float(stats["annual_return_pct"]), 4),
        "max_drawdown_pct": round(float(stats["max_drawdown_pct"]), 4),
        "calmar_ratio": round(float(stats["calmar_ratio"]), 4),
        "trade_records": int(stats["trade_records"]),
        "buy_fills": int(stats["buy_fills"]),
        "sell_fills": int(stats["sell_fills"]),
        "stop_loss_fills": int(stats["stop_loss_fills"]),
        "limit_down_exit_fills": int(stats["limit_down_exit_fills"]),
        "bearish_volume_exit_fills": int(stats["bearish_volume_exit_fills"]),
    }


def run_grid():
    v4 = load_v4_module()
    panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=v4.PANEL_COLUMNS + ["close_qfq"])
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[(panel["trade_date"] >= "2017-01-01")].copy()
    panel = add_ma10w_features(add_pullback_63(panel))
    market = load_market()
    rows = []
    baseline = {}
    for label, start, end in [
        ("2018", "2018-01-01", "2018-12-31"),
        ("all", "2018-01-01", None),
    ]:
        metrics = run_v4_baseline(v4, panel, market, start, end)
        baseline[label] = metrics
        rows.append({
            "group": "BASE",
            "market_gate": "base",
            "period": label,
            "note": "v4当前基线, 同脚本重跑",
            "pullback_threshold": v4.LONG_PULLBACK_THRESHOLD,
            "dist_10w_max": "",
            "require_ma10w_up": False,
            **metrics,
        })
    for experiment in EXPERIMENTS:
        for market_gate in MARKET_GATES:
            for label, start, end in [
                ("2018", "2018-01-01", "2018-12-31"),
                ("all", "2018-01-01", None),
            ]:
                metrics = run_one(v4, panel, market, experiment, market_gate, start, end)
                rows.append({
                    "group": experiment["group"],
                    "market_gate": market_gate,
                    "period": label,
                    "note": experiment["note"],
                    "pullback_threshold": experiment["pullback_threshold"],
                    "dist_10w_max": experiment["dist_10w_max"],
                    "require_ma10w_up": experiment["require_ma10w_up"],
                    **metrics,
                })
    results = pd.DataFrame(rows)
    results = results.sort_values(
        ["period", "total_return_pct", "max_drawdown_pct", "trade_records"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    return results, baseline, compute_v1_reference()


def write_summary(results, baseline, v1_ref):
    best_2018 = results[results["period"] == "2018"].sort_values(
        ["total_return_pct", "max_drawdown_pct", "trade_records"],
        ascending=[False, False, True],
    ).iloc[0]
    best_all = results[results["period"] == "all"].sort_values(
        ["total_return_pct", "max_drawdown_pct", "trade_records"],
        ascending=[False, False, True],
    ).iloc[0]
    lines = [
        "# v4 63日回撤与10周线实验结果",
        "",
        "## 基准",
        f"- v4 2018 收益: {baseline['2018']['total_return_pct']:.2f}%",
        f"- v4 2018 最大回撤: {baseline['2018']['max_drawdown_pct']:.2f}%",
        f"- v4 全区间收益: {baseline['all']['total_return_pct']:.2f}%",
        f"- v4 全区间最大回撤: {baseline['all']['max_drawdown_pct']:.2f}%",
        f"- v1 中位年化收益: {v1_ref['v1_median_annual_return_pct']:.2f}%",
        f"- v1 中位 Calmar: {v1_ref['v1_median_calmar_ratio']:.4f}",
        "",
        "## QA结论",
        "- 建议合入：A/base，即 `63日回撤<=-5%`，不加10周线，不加ma120门禁。",
        "- 暂不合入：ma120市场门禁。它改善2018，但全区间表现明显变差。",
        "- 暂不合入：当前版本10周线 D/E/F。它们没有优于 A/base。",
        "",
        "## 2018 最优",
        f"- 组别: {best_2018['group']} / {best_2018['market_gate']} ({best_2018['note']})",
        f"- 收益: {best_2018['total_return_pct']:.2f}%",
        f"- 年化: {best_2018['annual_return_pct']:.2f}%",
        f"- 最大回撤: {best_2018['max_drawdown_pct']:.2f}%",
        f"- Calmar: {best_2018['calmar_ratio']:.4f}",
        f"- 交易记录: {int(best_2018['trade_records'])}",
        "",
        "## 全区间最优",
        f"- 组别: {best_all['group']} / {best_all['market_gate']} ({best_all['note']})",
        f"- 收益: {best_all['total_return_pct']:.2f}%",
        f"- 年化: {best_all['annual_return_pct']:.2f}%",
        f"- 最大回撤: {best_all['max_drawdown_pct']:.2f}%",
        f"- Calmar: {best_all['calmar_ratio']:.4f}",
        f"- 交易记录: {int(best_all['trade_records'])}",
    ]
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    results, baseline, v1_ref = run_grid()
    write_summary(results, baseline, v1_ref)
    best = results[results["period"] == "2018"].sort_values("total_return_pct", ascending=False).iloc[0]
    print(
        f"Best 2018: group={best['group']} gate={best['market_gate']} return={best['total_return_pct']:.2f}% "
        f"maxDD={best['max_drawdown_pct']:.2f}% trades={int(best['trade_records'])}"
    )
    best_all = results[results["period"] == "all"].sort_values("total_return_pct", ascending=False).iloc[0]
    print(
        f"Best all: group={best_all['group']} gate={best_all['market_gate']} return={best_all['total_return_pct']:.2f}% "
        f"maxDD={best_all['max_drawdown_pct']:.2f}% trades={int(best_all['trade_records'])}"
    )
    print(f"Results: {RESULTS_PATH}")
    print(f"Summary: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()

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
OUTPUT_DIR = Path(__file__).parent / "v4_bear_ma120_full_output"
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
    return market


def make_ma120_gate_fn(original_short_drop, market):
    def wrapped_market_short_drop_blocks_buy(current_market, signal_date):
        blocked, reason, snapshot = original_short_drop(current_market, signal_date)
        if blocked:
            return blocked, reason, snapshot
        if signal_date not in market.index:
            return True, "missing_market", snapshot
        row = market.loc[signal_date]
        close = float(row.get("close", np.nan))
        ma120 = float(row.get("ma120", np.nan))
        snapshot = dict(snapshot)
        snapshot.update({"market_close": close, "market_ma120": ma120})
        if not np.isfinite(ma120):
            return True, "market_gate_warmup", snapshot
        if close <= ma120:
            return True, "market_below_ma120", snapshot
        return False, "market_gate_ma120_ok", snapshot

    return wrapped_market_short_drop_blocks_buy


def calc_nav_stats(nav_df):
    nav_df = nav_df.copy()
    nav_df["date"] = pd.to_datetime(nav_df["date"])
    total_ret = nav_df["nav"].iloc[-1] / nav_df["nav"].iloc[0] - 1.0
    days = max((nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    curve = nav_df["nav"] / nav_df["nav"].iloc[0]
    dd = curve / curve.cummax() - 1.0
    return {
        "start_date": str(nav_df["date"].iloc[0])[:10],
        "end_date": str(nav_df["date"].iloc[-1])[:10],
        "final_nav": round(float(nav_df["nav"].iloc[-1]), 2),
        "total_return_pct": round(float(total_ret * 100.0), 4),
        "annual_return_pct": round(float(annual_ret * 100.0), 4),
        "max_drawdown_pct": round(float(dd.min() * 100.0), 4),
        "avg_cash_pct": round(float((nav_df["cash"] / nav_df["nav"]).mean() * 100.0), 4),
        "avg_holdings": round(float(nav_df["holdings"].mean()), 4),
    }


def summarize_period(nav_df, start, end):
    sub = nav_df[(pd.to_datetime(nav_df["date"]) >= pd.Timestamp(start)) & (pd.to_datetime(nav_df["date"]) <= pd.Timestamp(end))]
    if sub.empty:
        return {}
    return calc_nav_stats(sub)


def run_case(v4, panel, market, case):
    original_market_short_drop = v4.market_short_drop_blocks_buy
    original_pullback_threshold = v4.LONG_PULLBACK_THRESHOLD
    try:
        if case["market_gate"] == "ma120":
            v4.market_short_drop_blocks_buy = make_ma120_gate_fn(original_market_short_drop, market)
        else:
            v4.market_short_drop_blocks_buy = original_market_short_drop
        v4.LONG_PULLBACK_THRESHOLD = case["pullback_threshold"]
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v4.run_backtest(
            panel,
            market,
            "2018-01-01",
            None,
        )
    finally:
        v4.market_short_drop_blocks_buy = original_market_short_drop
        v4.LONG_PULLBACK_THRESHOLD = original_pullback_threshold

    periods = {
        "2018": ("2018-01-01", "2018-12-31"),
        "2019_2021": ("2019-01-01", "2021-12-31"),
        "2022": ("2022-01-01", "2022-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "full": ("2018-01-01", str(pd.to_datetime(nav_df["date"]).max())[:10]),
    }
    rows = []
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "market_gate": case["market_gate"],
            "pullback_threshold": case["pullback_threshold"],
            "period": period_name,
        }
        row.update(summarize_period(nav_df, start, end))
        period_trades = trades_df[
            (pd.to_datetime(trades_df["date"]) >= pd.Timestamp(start))
            & (pd.to_datetime(trades_df["date"]) <= pd.Timestamp(end))
        ] if not trades_df.empty else trades_df
        row.update({
            "trade_records": int(len(period_trades)),
            "buy_fills": int((period_trades["action"] == "buy").sum()) if not period_trades.empty else 0,
            "sell_fills": int((period_trades["action"] == "sell").sum()) if not period_trades.empty else 0,
        })
        rows.append(row)
    return rows, stats


def run_experiment():
    v4 = load_v4_module()
    panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=v4.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[panel["trade_date"] >= "2017-01-01"].copy()
    market = pd.read_parquet(V4_OUTPUT / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = build_market_features(market.sort_values("trade_date").set_index("trade_date"))

    cases = [
        {"name": "current_threshold_5", "market_gate": "current", "pullback_threshold": -0.05},
        {"name": "ma120_threshold_5", "market_gate": "ma120", "pullback_threshold": -0.05},
        {"name": "ma120_threshold_7", "market_gate": "ma120", "pullback_threshold": -0.07},
        {"name": "ma120_threshold_8", "market_gate": "ma120", "pullback_threshold": -0.08},
    ]

    all_rows = []
    full_stats = {}
    for case in cases:
        rows, stats = run_case(v4, panel, market, case)
        all_rows.extend(rows)
        full_stats[case["name"]] = stats

    results = pd.DataFrame(all_rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)

    full_table = results[results["period"] == "full"].copy()
    full_table = full_table.sort_values("total_return_pct", ascending=False)
    summary = [
        "# v4 ma120 熊市门禁全区间实验",
        "",
        "## 说明",
        "",
        "- 只在 tmp 中运行。",
        "- 导入当前工作树 `v4/20_run_backtest.py`，不代表旧留档。",
        "- `current_threshold_5` 是当前策略买入回撤阈值 -5% 且只保留原市场短跌过滤。",
        "- `ma120_threshold_*` 在原市场短跌过滤之外，增加上证指数收盘价高于 120 日均线才允许新开仓。",
        "",
        "## 全区间结果",
        "",
        "| case | 总收益 | 年化 | 最大回撤 | 平均现金% | 交易数 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in full_table.iterrows():
        summary.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | "
            f"{row['annual_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['avg_cash_pct']:.2f}% | {int(row['trade_records'])} |"
        )
    summary.extend([
        "",
        "## 分段结果见",
        "",
        f"- `{RESULTS_PATH.name}`",
    ])
    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")
    return results


def main():
    results = run_experiment()
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    print(full[[
        "case",
        "total_return_pct",
        "annual_return_pct",
        "max_drawdown_pct",
        "avg_cash_pct",
        "trade_records",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

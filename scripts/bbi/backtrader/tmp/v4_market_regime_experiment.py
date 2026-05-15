import csv
import importlib.util
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
OUTPUT_DIR = Path(__file__).parent / "v4_market_regime_output"
REGIME_PATH = OUTPUT_DIR / "market_regime.csv"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


def load_v4_module():
    if str(V4_DIR) not in sys.path:
        sys.path.insert(0, str(V4_DIR))
    spec = importlib.util.spec_from_file_location("v4_run_backtest", V4_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify_regime_row(row):
    close = float(row.get("close", np.nan))
    ma120 = float(row.get("ma120", np.nan))
    ma200 = float(row.get("ma200", np.nan))
    ma120_slope_20 = float(row.get("ma120_slope_20", np.nan))
    dd_252 = float(row.get("dd_252", np.nan))
    breadth = float(row.get("breadth_above_bbi", np.nan))

    values = [close, ma120, ma200, ma120_slope_20, dd_252, breadth]
    if any(not np.isfinite(v) for v in values):
        return "unknown"

    if dd_252 <= -0.20:
        return "bear"
    if close < ma120 and ma120_slope_20 < 0 and breadth < 0.45:
        return "bear"
    if close > ma120 and close > ma200 and ma120_slope_20 > 0 and dd_252 > -0.10 and breadth >= 0.55:
        return "bull"
    return "neutral"


def build_market_regime(market, panel):
    market = market.copy().sort_values("trade_date")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    close = pd.to_numeric(market["close"], errors="coerce")
    market["ma120"] = close.rolling(120, min_periods=120).mean()
    market["ma200"] = close.rolling(200, min_periods=200).mean()
    market["ma120_slope_20"] = market["ma120"] / market["ma120"].shift(20) - 1.0
    market["dd_252"] = close / close.rolling(252, min_periods=120).max() - 1.0

    breadth = panel.copy()
    breadth["trade_date"] = pd.to_datetime(breadth["trade_date"])
    breadth = breadth[breadth["is_eligible"].fillna(False)].copy()
    breadth["above_bbi_num"] = breadth["above_bbi"].fillna(False).astype(float)
    breadth["strong_bbi_num"] = (pd.to_numeric(breadth["above_ratio_63"], errors="coerce") >= 0.55).astype(float)
    breadth_daily = breadth.groupby("trade_date").agg(
        breadth_above_bbi=("above_bbi_num", "mean"),
        breadth_strong_bbi=("strong_bbi_num", "mean"),
        breadth_count=("ts_code", "count"),
    ).reset_index()

    regime = market.merge(breadth_daily, on="trade_date", how="left")
    regime["regime"] = regime.apply(classify_regime_row, axis=1)
    return regime


def make_regime_gate_and_stop_fn(v4, original_gate, original_stop_loss, regime_by_date):
    current = {"bear": False}

    def wrapped_gate(current_market, signal_date):
        blocked, reason, snapshot = original_gate(current_market, signal_date)
        snapshot = dict(snapshot or {})
        regime = regime_by_date.get(pd.Timestamp(signal_date), "unknown")
        current["bear"] = regime == "bear"
        snapshot["market_regime"] = regime
        if blocked:
            return blocked, reason, snapshot
        if current["bear"]:
            return True, "market_regime_bear", snapshot
        return False, reason, snapshot

    def wrapped_stop_loss(code, pos, signal_panel):
        if original_stop_loss(code, pos, signal_panel):
            return True
        if not current["bear"]:
            return False
        profit_pct = v4.calc_position_profit_pct(code, pos, signal_panel)
        return profit_pct is not None and profit_pct <= 0.0

    return wrapped_gate, wrapped_stop_loss


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


def run_case(v4, panel, market_for_bt, regime_by_date, case):
    original_gate = v4.market_short_drop_blocks_buy
    original_stop_loss = v4.has_stop_loss_signal
    original_pullback_threshold = v4.LONG_PULLBACK_THRESHOLD
    try:
        v4.LONG_PULLBACK_THRESHOLD = float(case["pullback_threshold"])
        if case["use_regime"]:
            gate_fn, stop_fn = make_regime_gate_and_stop_fn(v4, original_gate, original_stop_loss, regime_by_date)
            v4.market_short_drop_blocks_buy = gate_fn
            v4.has_stop_loss_signal = stop_fn
        else:
            v4.market_short_drop_blocks_buy = original_gate
            v4.has_stop_loss_signal = original_stop_loss

        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v4.run_backtest(
            panel,
            market_for_bt,
            "2018-01-01",
            None,
        )
    finally:
        v4.market_short_drop_blocks_buy = original_gate
        v4.has_stop_loss_signal = original_stop_loss
        v4.LONG_PULLBACK_THRESHOLD = original_pullback_threshold

    periods = {
        "2018": ("2018-01-01", "2018-12-31"),
        "2019_2021": ("2019-01-01", "2021-12-31"),
        "2022": ("2022-01-01", "2022-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "full": ("2018-01-01", str(pd.to_datetime(nav_df["date"]).max())[:10]),
    }
    bear_blocks = int(
        (rebalance_df["market_reason"] == "market_regime_bear").sum()
    ) if not rebalance_df.empty and "market_reason" in rebalance_df.columns else 0
    rows = []
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "use_regime": bool(case["use_regime"]),
            "pullback_threshold": float(case["pullback_threshold"]),
            "period": period_name,
            "bear_block_days_full": bear_blocks,
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        rows.append(row)
    return rows


def run_experiment():
    v4 = load_v4_module()
    panel_cols = ["ts_code", "trade_date", "is_eligible", "above_bbi", "above_ratio_63"]
    regime_panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=panel_cols)
    market = pd.read_parquet(V4_OUTPUT / "market_index.parquet")
    regime = build_market_regime(market, regime_panel)

    panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=v4.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[panel["trade_date"] >= "2017-01-01"].copy()
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market_for_bt = market.sort_values("trade_date").set_index("trade_date")
    regime_by_date = dict(zip(pd.to_datetime(regime["trade_date"]), regime["regime"]))

    cases = [
        {"name": "current_pb5", "use_regime": False, "pullback_threshold": -0.05},
        {"name": "regime_pb5", "use_regime": True, "pullback_threshold": -0.05},
        {"name": "regime_pb7", "use_regime": True, "pullback_threshold": -0.07},
    ]

    rows = []
    for case in cases:
        rows.extend(run_case(v4, panel, market_for_bt, regime_by_date, case))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    regime.to_csv(REGIME_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    results = pd.DataFrame(rows)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    write_summary(results, regime)
    return results, regime


def write_summary(results, regime):
    regime_counts = regime[regime["trade_date"] >= pd.Timestamp("2018-01-01")]["regime"].value_counts()
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    p2018 = results[results["period"] == "2018"].sort_values("total_return_pct", ascending=False)
    lines = [
        "# v4 市场牛熊状态实验",
        "",
        "## 牛熊定义",
        "",
        "- `bear`: 上证指数距 252 日高点回撤 <= -20%，或 `close < ma120` 且 `ma120_slope_20 < 0` 且 BBI 市场宽度 < 45%。",
        "- `bull`: `close > ma120` 且 `close > ma200` 且 `ma120_slope_20 > 0` 且 252 日回撤 > -10% 且 BBI 市场宽度 >= 55%。",
        "- 其余为 `neutral`；预热不足为 `unknown`。",
        "- BBI 市场宽度 = 当日可交易股票中 `close_qfq > bbi_qfq` 的比例。",
        "",
        "## 状态天数",
        "",
    ]
    for name, count in regime_counts.items():
        lines.append(f"- {name}: {int(count)}")
    lines.extend([
        "",
        "## 策略接法",
        "",
        "- 当前 v4 原规则不变。",
        "- 若 signal_date 被判断为 `bear`，则不新开仓，并把浮亏持仓按次日开盘退出；盈利持仓继续按原规则处理。",
        "",
        "## 全区间结果",
        "",
        "| case | 总收益 | 年化 | 最大回撤 | 平均现金% | 交易数 | 熊市阻断日 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for _, row in full.iterrows():
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | "
            f"{row['annual_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['avg_cash_pct']:.2f}% | {int(row['trade_records'])} | "
            f"{int(row['bear_block_days_full'])} |"
        )
    lines.extend([
        "",
        "## 2018 结果",
        "",
        "| case | 2018收益 | 年化 | 最大回撤 | 平均现金% | 交易数 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for _, row in p2018.iterrows():
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | "
            f"{row['annual_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['avg_cash_pct']:.2f}% | {int(row['trade_records'])} |"
        )
    lines.extend([
        "",
        "## 输出",
        "",
        f"- `{REGIME_PATH.name}`",
        f"- `{RESULTS_PATH.name}`",
    ])
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    results, regime = run_experiment()
    print(regime[regime["trade_date"] >= pd.Timestamp("2018-01-01")]["regime"].value_counts().to_string())
    print()
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    print(full[[
        "case", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
        "avg_cash_pct", "trade_records", "bear_block_days_full",
    ]].to_string(index=False))
    print()
    p2018 = results[results["period"] == "2018"].sort_values("total_return_pct", ascending=False)
    print(p2018[[
        "case", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
        "avg_cash_pct", "trade_records",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

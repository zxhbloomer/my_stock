import csv
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from v4_market_regime_experiment import build_market_regime


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v4").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V4_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v4"
V4_OUTPUT = V4_DIR / "output"
OUTPUT_DIR = Path(__file__).parent / "v4_regime_split_strategy_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


def load_v4_module():
    if str(V4_DIR) not in sys.path:
        sys.path.insert(0, str(V4_DIR))
    spec = importlib.util.spec_from_file_location("v4_run_backtest", V4_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def choose_regime_params(regime, case):
    if regime == "bear":
        return {
            "block_buy": True,
            "pullback_threshold": case["neutral_pullback"],
            "exit_loss_threshold": case["bear_exit_loss_threshold"],
        }
    if regime == "bull":
        return {
            "block_buy": False,
            "pullback_threshold": case["bull_pullback"],
            "exit_loss_threshold": None,
        }
    return {
        "block_buy": False,
        "pullback_threshold": case["neutral_pullback"],
        "exit_loss_threshold": None,
    }


def make_regime_split_hooks(v4, original_gate, original_stop_loss, regime_by_date, case):
    state = {"regime": "unknown", "exit_loss_threshold": None}

    def wrapped_gate(current_market, signal_date):
        regime = regime_by_date.get(pd.Timestamp(signal_date), "unknown")
        params = choose_regime_params(regime, case)
        state["regime"] = regime
        state["exit_loss_threshold"] = params["exit_loss_threshold"]
        v4.LONG_PULLBACK_THRESHOLD = float(params["pullback_threshold"])

        blocked, reason, snapshot = original_gate(current_market, signal_date)
        snapshot = dict(snapshot or {})
        snapshot.update({
            "market_regime": regime,
            "regime_pullback_threshold": params["pullback_threshold"],
        })
        if blocked:
            return blocked, reason, snapshot
        if params["block_buy"]:
            return True, "market_regime_bear", snapshot
        return False, reason, snapshot

    def wrapped_stop_loss(code, pos, signal_panel):
        if original_stop_loss(code, pos, signal_panel):
            return True
        threshold = state["exit_loss_threshold"]
        if threshold is None:
            return False
        profit_pct = v4.calc_position_profit_pct(code, pos, signal_panel)
        return profit_pct is not None and profit_pct <= float(threshold)

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
    original_strong_pullback_threshold = v4.LONG_STRONG_TREND_PULLBACK_THRESHOLD
    try:
        v4.LONG_PULLBACK_THRESHOLD = float(case["neutral_pullback"])
        v4.LONG_STRONG_TREND_PULLBACK_THRESHOLD = float(case["strong_pullback"])
        if case["use_split"]:
            gate_fn, stop_fn = make_regime_split_hooks(v4, original_gate, original_stop_loss, regime_by_date, case)
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
        v4.LONG_STRONG_TREND_PULLBACK_THRESHOLD = original_strong_pullback_threshold

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
            "use_split": bool(case["use_split"]),
            "bull_pullback": float(case["bull_pullback"]),
            "neutral_pullback": float(case["neutral_pullback"]),
            "strong_pullback": float(case["strong_pullback"]),
            "bear_exit_loss_threshold": case["bear_exit_loss_threshold"],
            "period": period_name,
            "bear_block_days_full": bear_blocks,
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        rows.append(row)
    return rows


def load_inputs():
    v4 = load_v4_module()
    panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=v4.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[panel["trade_date"] >= "2017-01-01"].copy()

    market = pd.read_parquet(V4_OUTPUT / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market_for_bt = market.sort_values("trade_date").set_index("trade_date")

    regime_panel_cols = ["ts_code", "trade_date", "is_eligible", "above_bbi", "above_ratio_63"]
    regime_panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=regime_panel_cols)
    regime = build_market_regime(market.copy(), regime_panel)
    regime_by_date = dict(zip(pd.to_datetime(regime["trade_date"]), regime["regime"]))
    return v4, panel, market_for_bt, regime_by_date, regime


def run_experiment():
    v4, panel, market_for_bt, regime_by_date, regime = load_inputs()
    cases = [
        {
            "name": "current",
            "use_split": False,
            "bull_pullback": -0.05,
            "neutral_pullback": -0.05,
            "strong_pullback": -0.03,
            "bear_exit_loss_threshold": None,
        },
        {
            "name": "split_bull5_neutral7_bear0",
            "use_split": True,
            "bull_pullback": -0.05,
            "neutral_pullback": -0.07,
            "strong_pullback": -0.03,
            "bear_exit_loss_threshold": 0.0,
        },
        {
            "name": "split_bull5_neutral8_bear0",
            "use_split": True,
            "bull_pullback": -0.05,
            "neutral_pullback": -0.08,
            "strong_pullback": -0.03,
            "bear_exit_loss_threshold": 0.0,
        },
        {
            "name": "split_bull4_neutral7_bear0",
            "use_split": True,
            "bull_pullback": -0.04,
            "neutral_pullback": -0.07,
            "strong_pullback": -0.025,
            "bear_exit_loss_threshold": 0.0,
        },
        {
            "name": "split_bull5_neutral7_bear_m2",
            "use_split": True,
            "bull_pullback": -0.05,
            "neutral_pullback": -0.07,
            "strong_pullback": -0.03,
            "bear_exit_loss_threshold": -0.02,
        },
    ]

    rows = []
    for case in cases:
        rows.extend(run_case(v4, panel, market_for_bt, regime_by_date, case))

    results = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    write_summary(results, regime)
    return results, regime


def write_summary(results, regime):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    p2018 = results[results["period"] == "2018"].sort_values("total_return_pct", ascending=False)
    counts = regime[regime["trade_date"] >= pd.Timestamp("2018-01-01")]["regime"].value_counts()
    lines = [
        "# v4 牛熊分策略实验",
        "",
        "## 状态依据",
        "",
        "- 牛市/熊市/震荡状态来自 `v4_market_regime_experiment.py`。",
        "- 牛市：允许较浅回撤进攻。",
        "- 震荡：首买回撤阈值收紧。",
        "- 熊市：不新开仓，并按浮亏阈值退出弱仓。",
        "",
        "## 状态天数",
        "",
    ]
    for name, count in counts.items():
        lines.append(f"- {name}: {int(count)}")
    lines.extend([
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

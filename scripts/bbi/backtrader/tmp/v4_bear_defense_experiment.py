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
OUTPUT_DIR = Path(__file__).parent / "v4_bear_defense_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


def load_v4_module():
    if str(V4_DIR) not in sys.path:
        sys.path.insert(0, str(V4_DIR))
    spec = importlib.util.spec_from_file_location("v4_run_backtest", V4_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_defense_gate_fn(original_gate, defense_days, trigger_reasons):
    remaining = {"days": 0}

    def wrapped(current_market, signal_date):
        blocked, reason, snapshot = original_gate(current_market, signal_date)
        snapshot = dict(snapshot or {})
        if blocked:
            if reason in trigger_reasons:
                remaining["days"] = int(defense_days)
                snapshot["bear_defense_days_left"] = remaining["days"]
            return blocked, reason, snapshot

        if remaining["days"] > 0:
            snapshot["bear_defense_days_left"] = remaining["days"]
            remaining["days"] -= 1
            return True, "bear_defense_cooldown", snapshot

        return False, reason, snapshot

    return wrapped


def make_defense_gate_and_stop_fn(v4, original_gate, original_stop_loss, defense_days, trigger_reasons):
    remaining = {"days": 0}

    def wrapped_gate(current_market, signal_date):
        blocked, reason, snapshot = original_gate(current_market, signal_date)
        snapshot = dict(snapshot or {})
        if blocked:
            if reason in trigger_reasons:
                remaining["days"] = int(defense_days)
                snapshot["bear_defense_days_left"] = remaining["days"]
            return blocked, reason, snapshot

        if remaining["days"] > 0:
            snapshot["bear_defense_days_left"] = remaining["days"]
            remaining["days"] -= 1
            return True, "bear_defense_cooldown", snapshot

        return False, reason, snapshot

    def wrapped_stop_loss(code, pos, signal_panel):
        if original_stop_loss(code, pos, signal_panel):
            return True
        if remaining["days"] <= 0:
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


def run_case(v4, panel, market, case):
    original_gate = v4.market_short_drop_blocks_buy
    original_stop_loss = v4.has_stop_loss_signal
    original_pullback_threshold = v4.LONG_PULLBACK_THRESHOLD
    try:
        v4.LONG_PULLBACK_THRESHOLD = float(case["pullback_threshold"])
        if case["defense_days"] > 0 and case["mode"] == "block_buys":
            v4.market_short_drop_blocks_buy = make_defense_gate_fn(
                original_gate,
                defense_days=int(case["defense_days"]),
                trigger_reasons={"market_5d_drop", "market_20d_drawdown"},
            )
            v4.has_stop_loss_signal = original_stop_loss
        elif case["defense_days"] > 0 and case["mode"] == "sell_losers":
            gate_fn, stop_fn = make_defense_gate_and_stop_fn(
                v4,
                original_gate,
                original_stop_loss,
                defense_days=int(case["defense_days"]),
                trigger_reasons={"market_5d_drop", "market_20d_drawdown"},
            )
            v4.market_short_drop_blocks_buy = gate_fn
            v4.has_stop_loss_signal = stop_fn
        else:
            v4.market_short_drop_blocks_buy = original_gate
            v4.has_stop_loss_signal = original_stop_loss

        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v4.run_backtest(
            panel,
            market,
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
    rows = []
    defense_blocks = int(
        (rebalance_df["market_reason"] == "bear_defense_cooldown").sum()
    ) if not rebalance_df.empty and "market_reason" in rebalance_df.columns else 0
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "mode": case["mode"],
            "defense_days": int(case["defense_days"]),
            "pullback_threshold": float(case["pullback_threshold"]),
            "period": period_name,
            "defense_block_days_full": defense_blocks,
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        rows.append(row)
    return rows


def run_experiment():
    v4 = load_v4_module()
    panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=v4.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[panel["trade_date"] >= "2017-01-01"].copy()

    market = pd.read_parquet(V4_OUTPUT / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")

    cases = [
        {"name": "current", "mode": "current", "defense_days": 0, "pullback_threshold": -0.05},
        {"name": "block20_pb5", "mode": "block_buys", "defense_days": 20, "pullback_threshold": -0.05},
        {"name": "block30_pb5", "mode": "block_buys", "defense_days": 30, "pullback_threshold": -0.05},
        {"name": "block40_pb5", "mode": "block_buys", "defense_days": 40, "pullback_threshold": -0.05},
        {"name": "block20_pb7", "mode": "block_buys", "defense_days": 20, "pullback_threshold": -0.07},
        {"name": "block30_pb7", "mode": "block_buys", "defense_days": 30, "pullback_threshold": -0.07},
        {"name": "block40_pb7", "mode": "block_buys", "defense_days": 40, "pullback_threshold": -0.07},
        {"name": "sell_losers20_pb5", "mode": "sell_losers", "defense_days": 20, "pullback_threshold": -0.05},
        {"name": "sell_losers30_pb5", "mode": "sell_losers", "defense_days": 30, "pullback_threshold": -0.05},
        {"name": "sell_losers40_pb5", "mode": "sell_losers", "defense_days": 40, "pullback_threshold": -0.05},
        {"name": "sell_losers20_pb7", "mode": "sell_losers", "defense_days": 20, "pullback_threshold": -0.07},
        {"name": "sell_losers30_pb7", "mode": "sell_losers", "defense_days": 30, "pullback_threshold": -0.07},
        {"name": "sell_losers40_pb7", "mode": "sell_losers", "defense_days": 40, "pullback_threshold": -0.07},
    ]

    rows = []
    for case in cases:
        rows.extend(run_case(v4, panel, market, case))

    results = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    write_summary(results)
    return results


def write_summary(results):
    full = results[results["period"] == "full"].copy()
    full = full.sort_values("total_return_pct", ascending=False)
    p2018 = results[results["period"] == "2018"].copy()
    p2018 = p2018.sort_values("total_return_pct", ascending=False)

    lines = [
        "# v4 熊市防守期实验",
        "",
        "## 算法",
        "",
        "- 沿用当前 v4 原始买卖、止损、BBI 强势评分。",
        "- 当原市场过滤触发 `market_5d_drop` 或 `market_20d_drawdown` 时，进入 N 个信号日防守期。",
        "- `block_buys`: 防守期内不新开仓；已有持仓仍按当前 v4 的止损、跌停、放量大阴线规则处理。",
        "- `sell_losers`: 防守期内不新开仓，并把浮亏持仓按次日开盘退出；盈利持仓继续按当前 v4 规则处理。",
        "- 本实验不修改正式 v4。",
        "",
        "## 全区间排序",
        "",
        "| case | mode | 总收益 | 年化 | 最大回撤 | 平均现金% | 交易数 | 防守阻断日 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.iterrows():
        lines.append(
            f"| {row['case']} | {row['mode']} | {row['total_return_pct']:.2f}% | "
            f"{row['annual_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['avg_cash_pct']:.2f}% | {int(row['trade_records'])} | "
            f"{int(row['defense_block_days_full'])} |"
        )

    lines.extend([
        "",
        "## 2018 排序",
        "",
        "| case | mode | 2018收益 | 年化 | 最大回撤 | 平均现金% | 交易数 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for _, row in p2018.iterrows():
        lines.append(
            f"| {row['case']} | {row['mode']} | {row['total_return_pct']:.2f}% | "
            f"{row['annual_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['avg_cash_pct']:.2f}% | {int(row['trade_records'])} |"
        )
    lines.extend([
        "",
        "## 明细",
        "",
        f"- `{RESULTS_PATH.name}`",
    ])
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    results = run_experiment()
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    print(full[[
        "case",
        "mode",
        "total_return_pct",
        "annual_return_pct",
        "max_drawdown_pct",
        "avg_cash_pct",
        "trade_records",
        "defense_block_days_full",
    ]].to_string(index=False))
    print()
    p2018 = results[results["period"] == "2018"].sort_values("total_return_pct", ascending=False)
    print(p2018[[
        "case",
        "mode",
        "total_return_pct",
        "annual_return_pct",
        "max_drawdown_pct",
        "avg_cash_pct",
        "trade_records",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

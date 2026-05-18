import csv
import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v4").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V4_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v4"
V4_OUTPUT = V4_DIR / "output"
SOURCE_PATH = V4_DIR / "20_run_backtest.py"
OUTPUT_DIR = Path(__file__).parent / "v4_regime_exit_timing_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


EXIT_CONDITION = 'and previous_market_regime_name == "bear"'
STRICT_CONDITION = 'and market_regime_name == "bear"'
TWO_DAY_CONDITION = (
    'and previous_market_regime_name == "bear"\n'
    '                    and market_regime_name == "bear"'
)


def load_v4_variant(name):
    if str(V4_DIR) not in sys.path:
        sys.path.insert(0, str(V4_DIR))
    source = SOURCE_PATH.read_text(encoding="utf-8")
    if name == "bear_confirmed_loss_exit":
        variant_source = source
    elif name == "strict_yesterday":
        variant_source = source.replace(EXIT_CONDITION, STRICT_CONDITION, 1)
    elif name == "two_day_confirm":
        variant_source = source.replace(EXIT_CONDITION, TWO_DAY_CONDITION, 1)
    else:
        raise ValueError(f"unknown variant={name}")
    module = types.ModuleType(f"v4_run_backtest_{name}")
    module.__file__ = str(SOURCE_PATH)
    exec(compile(variant_source, str(SOURCE_PATH), "exec"), module.__dict__)
    return module


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
        row.update({"trade_records": 0, "buy_fills": 0, "sell_fills": 0, "bear_exit_sells": 0})
        return row
    trade_dates = pd.to_datetime(trades_df["date"])
    period_trades = trades_df[(trade_dates >= pd.Timestamp(start)) & (trade_dates <= pd.Timestamp(end))]
    row.update({
        "trade_records": int(len(period_trades)),
        "buy_fills": int((period_trades["action"] == "buy").sum()) if not period_trades.empty else 0,
        "sell_fills": int((period_trades["action"] == "sell").sum()) if not period_trades.empty else 0,
        "bear_exit_sells": int((period_trades["reason"] == "long_regime_bear_exit").sum()) if not period_trades.empty else 0,
    })
    return row


def run_variant(name):
    v4 = load_v4_variant(name)
    panel = pd.read_parquet(v4.PANEL_PATH, columns=v4.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = v4.load_market_index()
    nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v4.run_backtest(
        panel,
        market,
        "2018-01-01",
        None,
    )
    periods = {
        "2018": ("2018-01-01", "2018-12-31"),
        "2022": ("2022-01-01", "2022-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "full": ("2018-01-01", str(pd.to_datetime(nav_df["date"]).max())[:10]),
    }
    rows = []
    for period_name, (start, end) in periods.items():
        row = {
            "case": name,
            "period": period_name,
            "regime_bear_exit_signals": stats.get("regime_bear_exit_signals", 0),
            "regime_bear_exit_fills": stats.get("regime_bear_exit_fills", 0),
            "regime_bear_block_days": stats.get("regime_bear_block_days", 0),
            "market_block_days": stats.get("market_block_days", 0),
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        rows.append(row)
    return rows


def write_summary(results):
    full = results[results["period"] == "full"].sort_values("annual_return_pct", ascending=False)
    period_map = {
        case: {row["period"]: row for _, row in group.iterrows()}
        for case, group in results.groupby("case")
    }
    lines = [
        "# v4 熊市确认后浮亏卖出时点实验",
        "",
        "固定开仓规则：`T-1` 判熊，`T` 开盘不新开仓。",
        "",
        "只比较浮亏持仓退出时点：",
        "",
        "- `bear_confirmed_loss_exit`: 当前 v4 的“熊市确认后浮亏卖出”。",
        "- `strict_yesterday`: `T-1` 判熊，`T` 开盘卖浮亏仓。",
        "- `two_day_confirm`: `T-2` 与 `T-1` 连续熊市，`T` 开盘卖浮亏仓。",
        "",
        "## 全区间",
        "",
        "| case | 总收益 | 年化 | 最大回撤 | 2018 | 2022 | 2025 | 熊市退出成交 | 交易数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.iterrows():
        case = row["case"]
        rows = period_map[case]
        lines.append(
            f"| {case} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {rows['2018']['total_return_pct']:.2f}% | "
            f"{rows['2022']['total_return_pct']:.2f}% | {rows['2025']['total_return_pct']:.2f}% | "
            f"{int(row['regime_bear_exit_fills'])} | {int(row['trade_records'])} |"
        )
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment():
    rows = []
    for name in ["bear_confirmed_loss_exit", "strict_yesterday", "two_day_confirm"]:
        rows.extend(run_variant(name))
    results = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    write_summary(results)
    return results


def main():
    results = run_experiment()
    full = results[results["period"] == "full"].sort_values("annual_return_pct", ascending=False)
    print(full[[
        "case", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
        "regime_bear_exit_fills", "trade_records", "regime_bear_block_days",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

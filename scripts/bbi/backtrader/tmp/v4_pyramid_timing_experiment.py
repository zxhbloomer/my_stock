import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
V4_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v4"
OUT_DIR = Path(__file__).resolve().parent / "v4_pyramid_timing_output"


def load_v4_module():
    sys.path.insert(0, str(V4_DIR))
    sys.modules.pop("config", None)
    spec = importlib.util.spec_from_file_location("v4_backtest_exp", V4_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trading_day_diff(trade_index, left_date, right_date):
    left = trade_index.get(pd.Timestamp(left_date))
    right = trade_index.get(pd.Timestamp(right_date))
    if left is None or right is None:
        return 0
    return left - right


def patch_variant(module, panel, thresholds, min_days_by_step=None, rank_limit=None):
    module.LONG_ADD_PROFIT_THRESHOLDS = thresholds
    original_execute_buy = module.execute_buy
    original_score_candidates = module.score_candidates

    dates = sorted(panel["trade_date"].dropna().unique())
    trade_index = {pd.Timestamp(date): idx for idx, date in enumerate(dates)}
    rank_cache = {}

    def rank_for(code, signal_panel):
        if rank_limit is None:
            return True
        signal_date = pd.Timestamp(signal_panel["trade_date"].iloc[0])
        if signal_date not in rank_cache:
            candidates = original_score_candidates(signal_panel).reset_index(drop=True)
            candidates["rank"] = range(1, len(candidates) + 1)
            rank_cache[signal_date] = dict(zip(candidates["ts_code"], candidates["rank"]))
        rank = rank_cache[signal_date].get(code)
        return rank is not None and rank <= rank_limit

    def can_add_position(code, pos, signal_panel):
        step_index = int(pos.get("step_index", 0))
        if step_index <= 0 or step_index >= len(module.LONG_POSITION_STEPS):
            return False
        threshold_index = step_index - 1
        if threshold_index >= len(module.LONG_ADD_PROFIT_THRESHOLDS):
            return False
        if min_days_by_step:
            signal_date = pd.Timestamp(signal_panel["trade_date"].iloc[0])
            ref_date = pos.get("last_add_date") or pos.get("buy_date")
            min_days = int(min_days_by_step[min(threshold_index, len(min_days_by_step) - 1)])
            if trading_day_diff(trade_index, signal_date, ref_date) < min_days:
                return False
        if not rank_for(code, signal_panel):
            return False
        profit_pct = module.calc_position_profit_pct(code, pos, signal_panel)
        if profit_pct is None:
            return False
        return profit_pct >= module.LONG_ADD_PROFIT_THRESHOLDS[threshold_index]

    def execute_buy(date, row, target_amount, cash, holdings, trades, reason):
        code = row["ts_code"]
        existed = code in holdings
        cash, bought, skip_reason = original_execute_buy(date, row, target_amount, cash, holdings, trades, reason)
        if bought and code in holdings:
            if existed:
                holdings[code]["last_add_date"] = str(date)[:10]
            else:
                holdings[code]["last_add_date"] = str(date)[:10]
        return cash, bought, skip_reason

    module.can_add_position = can_add_position
    module.execute_buy = execute_buy


def summarize(name, nav_df, trades_df, stats):
    buys = trades_df[trades_df["action"] == "buy"] if not trades_df.empty else pd.DataFrame()
    sells = trades_df[trades_df["action"] == "sell"] if not trades_df.empty else pd.DataFrame()
    add_buys = buys[buys["reason"] == "long_add_buy"] if not buys.empty else pd.DataFrame()
    pnl = float(sells["pnl"].sum()) if "pnl" in sells else 0.0
    return {
        "variant": name,
        "start_date": stats["start_date"],
        "end_date": stats["end_date"],
        "final_nav": round(float(stats["final_nav"]), 2),
        "total_return_pct": stats["total_return_pct"],
        "annual_return_pct": stats["annual_return_pct"],
        "max_drawdown_pct": stats["max_drawdown_pct"],
        "calmar_ratio": stats["calmar_ratio"],
        "trade_records": int(stats["trade_records"]),
        "buy_records": int(len(buys)),
        "add_buy_records": int(len(add_buys)),
        "sell_records": int(len(sells)),
        "realized_pnl": round(pnl, 2),
        "stop_loss_fills": int(stats.get("stop_loss_fills", 0)),
        "limit_down_exit_fills": int(stats.get("limit_down_exit_fills", 0)),
        "bearish_volume_exit_fills": int(stats.get("bearish_volume_exit_fills", 0)),
    }


def run_variant(name, thresholds, min_days_by_step=None, rank_limit=None):
    module = load_v4_module()
    panel = pd.read_parquet(module.PANEL_PATH, columns=module.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[
        (panel["trade_date"] >= pd.Timestamp("2018-01-01"))
        & (panel["trade_date"] <= pd.Timestamp("2018-12-31"))
    ].copy()
    market = module.load_market_index()
    patch_variant(module, panel, thresholds, min_days_by_step=min_days_by_step, rank_limit=rank_limit)
    nav_df, trades_df, rebalance_df, scores_df, holdings, stats = module.run_backtest(
        panel, market, "2018-01-01", "2018-12-31"
    )
    variant_dir = OUT_DIR / name
    variant_dir.mkdir(parents=True, exist_ok=True)
    nav_df.to_csv(variant_dir / "nav_series.csv", index=False)
    trades_df.to_csv(variant_dir / "trade_records.csv", index=False)
    rebalance_df.to_csv(variant_dir / "rebalance_log.csv", index=False)
    scores_df.to_csv(variant_dir / "strength_scores.csv", index=False)
    return summarize(name, nav_df, trades_df, stats)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    variants = [
        {
            "name": "baseline_current_3_6_10",
            "thresholds": (0.03, 0.06, 0.10),
            "min_days_by_step": None,
            "rank_limit": None,
        },
        {
            "name": "threshold_5_10_15_only",
            "thresholds": (0.05, 0.10, 0.15),
            "min_days_by_step": None,
            "rank_limit": None,
        },
        {
            "name": "timed_3_5_5_no_rank",
            "thresholds": (0.05, 0.10, 0.15),
            "min_days_by_step": (3, 5, 5),
            "rank_limit": None,
        },
        {
            "name": "timed_5_5_5_no_rank",
            "thresholds": (0.05, 0.10, 0.15),
            "min_days_by_step": (5, 5, 5),
            "rank_limit": None,
        },
        {
            "name": "timed_5_10_15_no_rank",
            "thresholds": (0.05, 0.10, 0.15),
            "min_days_by_step": (5, 10, 10),
            "rank_limit": None,
        },
        {
            "name": "timed_5_10_15_rank50",
            "thresholds": (0.05, 0.10, 0.15),
            "min_days_by_step": (5, 10, 10),
            "rank_limit": 50,
        },
    ]
    rows = [run_variant(**variant) for variant in variants]
    result = pd.DataFrame(rows)
    result.to_csv(OUT_DIR / "summary.csv", index=False)
    (OUT_DIR / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(result.to_string(index=False))
    print(f"Saved: {OUT_DIR}")


if __name__ == "__main__":
    main()

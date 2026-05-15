import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
V4_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v4"
OUT_DIR = Path(__file__).resolve().parent / "v4_strong_trend_exception_output"
TARGET_CODE = "300308.SZ"


def load_v4_module():
    sys.path.insert(0, str(V4_DIR))
    sys.modules.pop("config", None)
    spec = importlib.util.spec_from_file_location("v4_backtest_strong_exp", V4_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def patch_score_candidates(module, enable_exception, hybrid_pullback=False):
    if not enable_exception:
        return

    def score_candidates(signal_panel):
        candidates = signal_panel[signal_panel["is_eligible"].fillna(False)].copy()
        required_cols = ["high_pos_21", "high_pos_63", "range_pos_63", "recent_limit_down_20"]
        if module.HOT_MONEY_RISK_ENABLED:
            required_cols.extend([
                "recent_limit_up_20",
                "recent_limit_up_63",
                "turnover_rate_ma20",
                "turnover_rate_max20",
                "volume_ratio_max20",
                "lhb_count_20",
                "hot_money_risk_hits",
            ])
        missing_cols = [col for col in required_cols if col not in candidates.columns]
        if missing_cols:
            raise ValueError(f"panel missing candidate filter columns {missing_cols}. Run 10_prepare_data.py again.")

        hot_money_risk_ok = pd.Series(True, index=candidates.index)
        if module.HOT_MONEY_RISK_ENABLED:
            hot_money_risk_ok = (
                candidates["hot_money_risk_hits"].notna()
                & (candidates["hot_money_risk_hits"] < module.HOT_MONEY_RISK_MIN_HITS)
            )

        candidates["strong_trend_exception"] = (
            (candidates["above_ratio_63"] >= 0.80)
            & (candidates["above_ratio_126"] >= 0.60)
            & (candidates["ret_63"] >= 0.80)
            & hot_money_risk_ok
            & (candidates["recent_limit_down_20"] == 0)
        )
        recent_high_risk = (candidates["high_pos_21"] >= module.MAX_HIGH_POS_21) & ~candidates["strong_trend_exception"]
        ret_21_ok = (candidates["ret_21"] <= module.MAX_RET_21) | candidates["strong_trend_exception"]

        candidates = candidates[
            (candidates["above_ratio_63"] >= 0.55)
            & (candidates["above_ratio_126"] >= 0.50)
            & (candidates["ret_63"] >= module.MIN_RET_63)
            & ret_21_ok
            & (candidates["avg_distance_63"] <= module.MAX_AVG_DISTANCE_63)
            & candidates["high_pos_21"].notna()
            & candidates["high_pos_63"].notna()
            & candidates["range_pos_63"].notna()
            & candidates["recent_limit_down_20"].notna()
            & (candidates["recent_limit_down_20"] == 0)
            & hot_money_risk_ok
            & ~recent_high_risk
            & candidates["ret_63"].notna()
            & candidates["volatility_63"].notna()
            & candidates["amount_ma20"].notna()
        ].copy()
        if candidates.empty:
            candidates["score"] = []
            return candidates

        candidates["score"] = (
            0.30 * module.zscore(candidates["above_ratio_63"])
            + 0.25 * module.zscore(candidates["above_ratio_126"])
            + 0.15 * module.zscore(candidates["ret_63"])
            + 0.10 * module.zscore(candidates["avg_distance_63"])
            - 0.15 * module.zscore(candidates["volatility_63"])
            + 0.05 * module.zscore(np.log(candidates["amount_ma20"].clip(lower=1.0)))
        )
        candidates = candidates[candidates["score"] >= module.MIN_SCORE].copy()
        if hybrid_pullback:
            ordinary_not_ready = (
                ~candidates["strong_trend_exception"]
                & candidates["pullback_63"].notna()
                & (candidates["pullback_63"] > -0.05)
            )
            candidates.loc[ordinary_not_ready, "pullback_63"] = np.nan
        return candidates.sort_values(
            ["score", "above_ratio_63", "ret_63", "amount_ma20"],
            ascending=[False, False, False, False],
        )

    module.score_candidates = score_candidates


def summarize(name, nav_df, trades_df, scores_df, stats):
    buys = trades_df[trades_df["action"] == "buy"] if not trades_df.empty else pd.DataFrame()
    sells = trades_df[trades_df["action"] == "sell"] if not trades_df.empty else pd.DataFrame()
    target_trades = trades_df[trades_df["ts_code"] == TARGET_CODE] if not trades_df.empty else pd.DataFrame()
    target_scores = scores_df[scores_df["ts_code"] == TARGET_CODE] if not scores_df.empty else pd.DataFrame()
    target_2025_scores = target_scores[
        target_scores["rebalance_date"].astype(str).str.startswith("2025-")
    ] if not target_scores.empty else pd.DataFrame()
    first_target_score = ""
    best_target_rank_2025 = None
    if not target_2025_scores.empty:
        first_target_score = str(target_2025_scores.sort_values("rebalance_date").iloc[0]["rebalance_date"])
        best_target_rank_2025 = int(pd.to_numeric(target_2025_scores["rank"]).min())

    return {
        "variant": name,
        "final_nav": round(float(stats["final_nav"]), 2),
        "total_return_pct": stats["total_return_pct"],
        "annual_return_pct": stats["annual_return_pct"],
        "max_drawdown_pct": stats["max_drawdown_pct"],
        "calmar_ratio": stats["calmar_ratio"],
        "trade_records": int(stats["trade_records"]),
        "buy_records": int(len(buys)),
        "sell_records": int(len(sells)),
        "target_trade_records": int(len(target_trades)),
        "target_buy_records": int(len(target_trades[target_trades["action"] == "buy"])) if not target_trades.empty else 0,
        "target_first_score_2025": first_target_score,
        "target_best_rank_2025": best_target_rank_2025,
    }


def run_variant(name, enable_exception, pullback_threshold, hybrid_pullback=False):
    module = load_v4_module()
    module.LONG_PULLBACK_THRESHOLD = pullback_threshold
    patch_score_candidates(module, enable_exception, hybrid_pullback=hybrid_pullback)

    panel = pd.read_parquet(module.PANEL_PATH, columns=module.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = module.load_market_index()
    nav_df, trades_df, rebalance_df, scores_df, holdings, stats = module.run_backtest(
        panel, market, "2018-01-01", None
    )

    variant_dir = OUT_DIR / name
    variant_dir.mkdir(parents=True, exist_ok=True)
    nav_df.to_csv(variant_dir / "nav_series.csv", index=False)
    trades_df.to_csv(variant_dir / "trade_records.csv", index=False)
    rebalance_df.to_csv(variant_dir / "rebalance_log.csv", index=False)
    scores_df.to_csv(variant_dir / "strength_scores.csv", index=False)
    target_trades = trades_df[trades_df["ts_code"] == TARGET_CODE] if not trades_df.empty else pd.DataFrame()
    target_scores = scores_df[scores_df["ts_code"] == TARGET_CODE] if not scores_df.empty else pd.DataFrame()
    target_trades.to_csv(variant_dir / "target_300308_trades.csv", index=False)
    target_scores.to_csv(variant_dir / "target_300308_scores.csv", index=False)
    return summarize(name, nav_df, trades_df, scores_df, stats)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    variants = [
        {
            "name": "baseline_current",
            "enable_exception": False,
            "pullback_threshold": -0.05,
        },
        {
            "name": "strong_exception_pullback_5",
            "enable_exception": True,
            "pullback_threshold": -0.05,
        },
        {
            "name": "strong_exception_pullback_3",
            "enable_exception": True,
            "pullback_threshold": -0.03,
            "hybrid_pullback": False,
        },
        {
            "name": "strong_3_ordinary_5",
            "enable_exception": True,
            "pullback_threshold": -0.03,
            "hybrid_pullback": True,
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

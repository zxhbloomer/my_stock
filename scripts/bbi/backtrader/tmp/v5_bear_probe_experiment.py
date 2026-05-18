import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v5").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V5_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v5"
V4_SUMMARY_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v4" / "output" / "summary.json"
V1_STATS_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v1" / "output" / "stats_summary.csv"
OUTPUT_DIR = Path(__file__).parent / "v5_bear_probe_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


CASES = [
    {
        "name": "baseline_v5",
        "allow_bear_probe": False,
        "probe_total_exposure": 0.0,
        "probe_ticket_amount": 0.0,
        "repair_only": False,
        "min_above_ratio_63": 0.0,
        "min_above_ratio_126": 0.0,
        "min_ret_63": 0.0,
        "min_ret_126": 0.0,
        "max_hot_money_hits": 99,
        "max_volatility_quantile": 1.0,
        "probe_pullback_threshold": 0.0,
        "repair_breadth": 0.35,
        "repair_slope_floor": -0.02,
    },
    {
        "name": "bear_probe_10_no_add",
        "allow_bear_probe": True,
        "probe_total_exposure": 50_000.0,
        "probe_ticket_amount": 25_000.0,
        "repair_only": False,
        "min_above_ratio_63": 0.75,
        "min_above_ratio_126": 0.70,
        "min_ret_63": 0.0,
        "min_ret_126": 0.0,
        "max_hot_money_hits": 0,
        "max_volatility_quantile": 0.70,
        "probe_pullback_threshold": 0.0,
        "repair_breadth": 0.35,
        "repair_slope_floor": -0.02,
    },
    {
        "name": "bear_probe_20_no_add",
        "allow_bear_probe": True,
        "probe_total_exposure": 100_000.0,
        "probe_ticket_amount": 25_000.0,
        "repair_only": False,
        "min_above_ratio_63": 0.75,
        "min_above_ratio_126": 0.70,
        "min_ret_63": 0.0,
        "min_ret_126": 0.0,
        "max_hot_money_hits": 0,
        "max_volatility_quantile": 0.70,
        "probe_pullback_threshold": 0.0,
        "repair_breadth": 0.35,
        "repair_slope_floor": -0.02,
    },
    {
        "name": "bear_probe_10_strict_pullback",
        "allow_bear_probe": True,
        "probe_total_exposure": 50_000.0,
        "probe_ticket_amount": 25_000.0,
        "repair_only": False,
        "min_above_ratio_63": 0.75,
        "min_above_ratio_126": 0.70,
        "min_ret_63": 0.0,
        "min_ret_126": 0.0,
        "max_hot_money_hits": 0,
        "max_volatility_quantile": 0.70,
        "probe_pullback_threshold": -0.07,
        "repair_breadth": 0.35,
        "repair_slope_floor": -0.02,
    },
    {
        "name": "bear_probe_10_relaxed",
        "allow_bear_probe": True,
        "probe_total_exposure": 50_000.0,
        "probe_ticket_amount": 25_000.0,
        "repair_only": False,
        "min_above_ratio_63": 0.65,
        "min_above_ratio_126": 0.60,
        "min_ret_63": 0.0,
        "min_ret_126": 0.0,
        "max_hot_money_hits": 1,
        "max_volatility_quantile": 0.80,
        "probe_pullback_threshold": 0.0,
        "repair_breadth": 0.35,
        "repair_slope_floor": -0.02,
    },
    {
        "name": "bear_probe_20_relaxed",
        "allow_bear_probe": True,
        "probe_total_exposure": 100_000.0,
        "probe_ticket_amount": 25_000.0,
        "repair_only": False,
        "min_above_ratio_63": 0.65,
        "min_above_ratio_126": 0.60,
        "min_ret_63": 0.0,
        "min_ret_126": 0.0,
        "max_hot_money_hits": 1,
        "max_volatility_quantile": 0.80,
        "probe_pullback_threshold": 0.0,
        "repair_breadth": 0.35,
        "repair_slope_floor": -0.02,
    },
]


def load_v5_module():
    if str(V5_DIR) not in sys.path:
        sys.path.insert(0, str(V5_DIR))
    spec = importlib.util.spec_from_file_location("v5_run_backtest_bear_probe", V5_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def classify_bear_bucket(row, repair_breadth=0.35, repair_slope_floor=-0.02):
    if row.get("market_regime") != "bear":
        return str(row.get("market_regime", "unknown"))
    dd_252 = safe_float(row.get("market_dd_252"))
    breadth = safe_float(row.get("breadth_above_bbi"))
    slope = safe_float(row.get("market_ma120_slope_20"))
    if dd_252 <= -0.20 or breadth <= 0.20:
        return "deep_bear"
    if breadth >= repair_breadth and slope >= repair_slope_floor:
        return "bear_repair"
    return "bear"


def calc_probe_available_exposure(holdings, case):
    invested = sum(
        float(pos.get("invested_amount", 0.0))
        for pos in holdings.values()
        if pos.get("probe_origin")
    )
    return max(float(case["probe_total_exposure"]) - invested, 0.0)


def count_probe_positions(holdings):
    return sum(1 for pos in holdings.values() if pos.get("probe_origin"))


def filter_probe_candidates(candidates, case):
    if candidates.empty:
        return candidates.copy()
    filtered = candidates[
        (candidates["above_ratio_63"] >= case["min_above_ratio_63"])
        & (candidates["above_ratio_126"] >= case["min_above_ratio_126"])
        & (candidates["ret_63"] >= case["min_ret_63"])
        & (candidates["ret_126"] >= case["min_ret_126"])
        & (candidates["recent_limit_down_20"] == 0)
        & (candidates["hot_money_risk_hits"] <= case["max_hot_money_hits"])
    ].copy()
    if filtered.empty:
        return filtered
    if case["probe_pullback_threshold"] < 0:
        filtered = filtered[filtered["pullback_63"] <= case["probe_pullback_threshold"]].copy()
    if filtered.empty:
        return filtered
    volatility_cutoff = candidates["volatility_63"].quantile(case["max_volatility_quantile"])
    filtered = filtered[filtered["volatility_63"] <= volatility_cutoff].copy()
    return filtered


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
    trade_dates = pd.to_datetime(trades_df["date"]) if not trades_df.empty else pd.Series([], dtype="datetime64[ns]")
    period_trades = trades_df[(trade_dates >= pd.Timestamp(start)) & (trade_dates <= pd.Timestamp(end))] if not trades_df.empty else trades_df
    row.update({
        "trade_records": int(len(period_trades)),
        "buy_fills": int((period_trades["action"] == "buy").sum()) if not period_trades.empty else 0,
        "sell_fills": int((period_trades["action"] == "sell").sum()) if not period_trades.empty else 0,
    })
    return row


def run_backtest_case(v5, panel, market, case, start_date="2018-01-01", end_date=None):
    market_regime = v5.build_market_regime(market, panel)
    if end_date:
        panel = panel[panel["trade_date"] <= pd.Timestamp(end_date)].copy()
    panel = panel[panel["trade_date"] >= pd.Timestamp(start_date)].copy()
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    panel_by_date = v5.build_panel_by_date(panel)
    all_dates = sorted(panel_by_date)

    cash = v5.INIT_CASH
    holdings = {}
    trades = []
    rebalance_log = []
    score_rows = []
    nav_rows = []
    stats = {
        "signal_days": 0,
        "market_block_days": 0,
        "missing_market_days": 0,
        "buy_fills": 0,
        "add_buy_fills": 0,
        "sell_fills": 0,
        "buy_skips": 0,
        "sell_delays": 0,
        "limit_down_exit_signals": 0,
        "limit_down_exit_fills": 0,
        "stop_loss_signals": 0,
        "stop_loss_fills": 0,
        "bearish_volume_exit_signals": 0,
        "bearish_volume_exit_fills": 0,
        "regime_bear_exit_signals": 0,
        "regime_bear_exit_fills": 0,
        "regime_bear_block_days": 0,
        "bear_probe_days": 0,
        "bear_probe_candidate_days": 0,
        "bear_probe_buy_fills": 0,
        "deep_bear_block_days": 0,
    }
    previous_market_regime_name = "unknown"

    for i, date in enumerate(all_dates):
        day_panel = v5.get_day_panel(panel, panel_by_date, date)
        risk_exit_codes = set()

        for code in list(holdings):
            if holdings[code].get("pending_sell"):
                pending_reason = holdings[code].get("pending_reason", "pending_sell")
                cash, sold, reason = v5.execute_sell(date, code, holdings[code], day_panel, cash, trades, pending_reason)
                if sold:
                    del holdings[code]
                    risk_exit_codes.add(code)
                    stats["sell_fills"] += 1
                else:
                    stats["sell_delays"] += 1

        market_regime_name = "disabled"
        regime_snapshot = {}
        if i > 0 and holdings:
            signal_date = all_dates[i - 1]
            signal_panel = v5.get_day_panel(panel, panel_by_date, signal_date)
            market_regime_name, regime_snapshot = v5.get_market_regime(market_regime, signal_date)
            exit_reasons = {}
            for code in list(holdings):
                pos = holdings[code]
                if pos.get("pending_sell"):
                    continue
                profit_pct = v5.calc_position_profit_pct(code, pos, signal_panel)
                if (
                    v5.MARKET_REGIME_FILTER_ENABLED
                    and previous_market_regime_name == "bear"
                    and profit_pct is not None
                    and profit_pct <= v5.REGIME_BEAR_EXIT_LOSS_THRESHOLD
                ):
                    exit_reasons[code] = "long_regime_bear_exit"
                    stats["regime_bear_exit_signals"] += 1
                elif profit_pct is not None and profit_pct <= v5.LONG_STOP_LOSS_PCT:
                    exit_reasons[code] = "long_stop_loss"
                    stats["stop_loss_signals"] += 1
                elif v5.has_limit_down_signal(code, pos, signal_panel):
                    exit_reasons[code] = "long_limit_down_exit"
                    stats["limit_down_exit_signals"] += 1
                elif v5.has_bearish_volume_signal(code, pos, signal_panel):
                    exit_reasons[code] = "long_bearish_volume_exit"
                    stats["bearish_volume_exit_signals"] += 1
            for code, exit_reason in exit_reasons.items():
                cash, sold, reason = v5.execute_sell(date, code, holdings[code], day_panel, cash, trades, exit_reason)
                if sold:
                    del holdings[code]
                    risk_exit_codes.add(code)
                    stats["sell_fills"] += 1
                    if exit_reason == "long_stop_loss":
                        stats["stop_loss_fills"] += 1
                    elif exit_reason == "long_limit_down_exit":
                        stats["limit_down_exit_fills"] += 1
                    elif exit_reason == "long_bearish_volume_exit":
                        stats["bearish_volume_exit_fills"] += 1
                    elif exit_reason == "long_regime_bear_exit":
                        stats["regime_bear_exit_fills"] += 1
                else:
                    stats["sell_delays"] += 1

        if i > 0:
            signal_date = all_dates[i - 1]
            stats["signal_days"] += 1
            market_regime_name, regime_snapshot = v5.get_market_regime(market_regime, signal_date)
            short_drop_blocked, short_drop_reason, short_drop_snapshot = v5.market_short_drop_blocks_buy(market, signal_date)
            regime_blocked = v5.MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
            bear_bucket = classify_bear_bucket(
                regime_snapshot,
                repair_breadth=case["repair_breadth"],
                repair_slope_floor=case["repair_slope_floor"],
            )
            allow_probe = (
                case["allow_bear_probe"]
                and regime_blocked
                and not short_drop_blocked
                and bear_bucket != "deep_bear"
                and (not case["repair_only"] or bear_bucket == "bear_repair")
            )
            if regime_blocked:
                stats["regime_bear_block_days"] += 1
            if bear_bucket == "deep_bear":
                stats["deep_bear_block_days"] += 1

            if short_drop_blocked or (regime_blocked and not allow_probe):
                stats["market_block_days"] += 1
                if short_drop_reason in {"missing_market", "missing_market_history"}:
                    stats["missing_market_days"] += 1
                market_reason = "market_regime_bear" if regime_blocked and not short_drop_blocked else short_drop_reason
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": market_reason,
                    "market_regime": market_regime_name,
                    "bear_bucket": bear_bucket,
                    "candidate_count": 0,
                    "bought_count": 0,
                    "market_ret_5": round(short_drop_snapshot.get("market_ret_5", float("nan")), 4),
                    "market_dd_20": round(short_drop_snapshot.get("market_dd_20", float("nan")), 4),
                    "market_dd_252": round(regime_snapshot.get("market_dd_252", float("nan")), 4),
                    "breadth_above_bbi": round(regime_snapshot.get("breadth_above_bbi", float("nan")), 4),
                    "cash": round(cash, 2),
                })
            else:
                signal_panel = v5.get_day_panel(panel, panel_by_date, signal_date)
                candidates = v5.score_candidates(signal_panel).reset_index(drop=True)
                candidates["rank"] = np.arange(1, len(candidates) + 1)
                candidates["signal_date"] = str(signal_date)[:10]
                candidates["rebalance_date"] = str(date)[:10]
                score_cols = [
                    "signal_date", "rebalance_date", "rank", "ts_code", "name", "score",
                    "above_ratio_21", "above_ratio_63", "above_ratio_126",
                    "avg_distance_63", "high_pos_21", "high_pos_63", "range_pos_63",
                    "recent_limit_down_20", "recent_limit_up_20", "recent_limit_up_63",
                    "turnover_rate_ma20", "turnover_rate_max20", "volume_ratio_max20",
                    "lhb_count_20", "hot_money_risk_hits",
                    "hm_limit_up_20_flag", "hm_limit_up_63_flag", "hm_turnover_ma20_flag",
                    "hm_turnover_max20_flag", "hm_volume_ratio_max20_flag", "hm_lhb_count20_flag",
                    "ret_21", "ret_63", "ret_126",
                    "volatility_63", "amount_ma20", "circ_mv_ma20", "pullback_63", "strong_trend",
                ]
                score_rows.extend(candidates[score_cols].head(100).to_dict("records"))
                bought_count = 0

                if not regime_blocked:
                    candidate_by_code = candidates.set_index("ts_code", drop=False)
                    for code in list(holdings):
                        if code in risk_exit_codes or code not in candidate_by_code.index or code not in day_panel.index:
                            continue
                        pos = holdings[code]
                        if pos.get("pending_sell") or not v5.can_add_position(code, pos, signal_panel):
                            continue
                        target_amount = v5.next_position_step(pos)
                        if target_amount is None:
                            continue
                        available_exposure = v5.LONG_MAX_TOTAL_EXPOSURE - v5.calc_total_exposure(holdings)
                        target_amount = min(target_amount, available_exposure)
                        if target_amount < 100:
                            continue
                        cash, bought, reason = v5.execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, "long_add_buy")
                        if bought:
                            bought_count += 1
                            stats["buy_fills"] += 1
                            stats["add_buy_fills"] += 1
                        else:
                            stats["buy_skips"] += 1

                pullback_threshold, strong_pullback_threshold = v5.regime_pullback_thresholds(market_regime_name)
                entry_candidates = candidates[
                    candidates["pullback_63"].notna()
                    & (
                        (
                            candidates["strong_trend"].fillna(False)
                            & (candidates["pullback_63"] <= strong_pullback_threshold)
                        )
                        | (
                            ~candidates["strong_trend"].fillna(False)
                            & (candidates["pullback_63"] <= pullback_threshold)
                        )
                    )
                ]
                if allow_probe:
                    stats["bear_probe_days"] += 1
                    entry_candidates = filter_probe_candidates(entry_candidates, case)
                    if not entry_candidates.empty:
                        stats["bear_probe_candidate_days"] += 1
                target_codes = list(entry_candidates["ts_code"].head(v5.KEEP_TOP_N))
                for code in target_codes:
                    max_holdings = v5.LONG_MAX_HOLDINGS if not allow_probe else max(1, int(case["probe_total_exposure"] // case["probe_ticket_amount"]))
                    current_holdings = len(holdings) if not allow_probe else count_probe_positions(holdings)
                    if current_holdings >= max_holdings:
                        break
                    if code in holdings or code in risk_exit_codes or code not in day_panel.index:
                        continue
                    if allow_probe:
                        available_exposure = calc_probe_available_exposure(holdings, case)
                        target_amount = min(float(case["probe_ticket_amount"]), available_exposure)
                    else:
                        available_exposure = v5.LONG_MAX_TOTAL_EXPOSURE - v5.calc_total_exposure(holdings)
                        target_amount = min(float(v5.LONG_POSITION_STEPS[0]), available_exposure)
                    if target_amount < 100:
                        break
                    reason_name = "bear_probe_buy" if allow_probe else "long_initial_buy"
                    cash, bought, reason = v5.execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, reason_name)
                    if bought:
                        holdings[code]["probe_origin"] = bool(allow_probe)
                        bought_count += 1
                        stats["buy_fills"] += 1
                        if allow_probe:
                            stats["bear_probe_buy_fills"] += 1
                    else:
                        stats["buy_skips"] += 1
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": short_drop_reason if not allow_probe else "bear_probe_allowed",
                    "market_regime": market_regime_name,
                    "bear_bucket": bear_bucket,
                    "candidate_count": int(len(candidates)),
                    "entry_candidate_count": int(len(entry_candidates)),
                    "bought_count": int(bought_count),
                    "market_ret_5": round(short_drop_snapshot.get("market_ret_5", float("nan")), 4),
                    "market_dd_20": round(short_drop_snapshot.get("market_dd_20", float("nan")), 4),
                    "market_dd_252": round(regime_snapshot.get("market_dd_252", float("nan")), 4),
                    "breadth_above_bbi": round(regime_snapshot.get("breadth_above_bbi", float("nan")), 4),
                    "pullback_threshold": round(pullback_threshold, 4),
                    "strong_pullback_threshold": round(strong_pullback_threshold, 4),
                    "cash": round(cash, 2),
                })
            previous_market_regime_name = market_regime_name

        nav = cash + sum(v5.mark_position(c, p, day_panel) for c, p in holdings.items())
        nav_rows.append({"date": str(date)[:10], "nav": round(nav, 2), "cash": round(cash, 2), "holdings": len(holdings)})

    nav_df = pd.DataFrame(nav_rows)
    total_ret = nav_df["nav"].iloc[-1] / v5.INIT_CASH - 1.0
    days = max((pd.Timestamp(nav_df["date"].iloc[-1]) - pd.Timestamp(nav_df["date"].iloc[0])).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    max_dd = v5.calc_max_drawdown(nav_df)
    stats.update({
        "start_date": str(nav_df["date"].iloc[0]),
        "end_date": str(nav_df["date"].iloc[-1]),
        "init_cash": v5.INIT_CASH,
        "final_nav": float(nav_df["nav"].iloc[-1]),
        "total_return_pct": round(total_ret * 100.0, 4),
        "annual_return_pct": round(annual_ret * 100.0, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "calmar_ratio": round((annual_ret * 100.0) / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "trade_records": len(trades),
    })
    return nav_df, pd.DataFrame(trades), pd.DataFrame(rebalance_log), pd.DataFrame(score_rows), holdings, stats


def summarize_v1():
    stats = pd.read_csv(V1_STATS_PATH)
    return {
        "stock_count": int(len(stats)),
        "avg_annual_return_pct": round(float(stats["annual_return_pct"].mean()), 4),
        "median_annual_return_pct": round(float(stats["annual_return_pct"].median()), 4),
        "best_annual_return_pct": round(float(stats["annual_return_pct"].max()), 4),
        "avg_max_drawdown_pct": round(float(stats["max_drawdown_pct"].mean()), 4),
        "avg_calmar_ratio": round(float(stats["calmar_ratio"].mean()), 4),
    }


def assert_baseline_matches_v5(results, v5_summary):
    baseline = results[(results["case"] == "baseline_v5") & (results["period"] == "full")]
    if baseline.empty:
        raise AssertionError("baseline_v5 full-period result is missing")
    row = baseline.iloc[0]
    for key, tolerance in [
        ("final_nav", 1e-2),
        ("total_return_pct", 1e-4),
        ("annual_return_pct", 1e-4),
        ("max_drawdown_pct", 1e-4),
        ("calmar_ratio", 1e-4),
        ("trade_records", 0),
    ]:
        actual = float(row[key])
        expected = float(v5_summary[key])
        if abs(actual - expected) > tolerance:
            raise AssertionError(f"baseline_v5 {key}={actual} does not match v5 summary {expected}")


def run_case(v5, panel, market, case):
    periods = {str(year): (f"{year}-01-01", f"{year}-12-31") for year in range(2018, 2027)}
    periods["full"] = ("2018-01-01", "2026-05-14")
    nav_df, trades_df, rebalance_df, scores_df, holdings, stats = run_backtest_case(v5, panel, market, case)
    rows = []
    bear_days = int((rebalance_df["market_regime"] == "bear").sum()) if not rebalance_df.empty else 0
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "period": period_name,
            "probe_total_exposure": case["probe_total_exposure"],
            "probe_ticket_amount": case["probe_ticket_amount"],
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        if period_name == "full":
            row.update({
                "market_block_days": int(stats.get("market_block_days", 0)),
                "regime_bear_block_days": int(stats.get("regime_bear_block_days", 0)),
                "regime_bear_exit_fills": int(stats.get("regime_bear_exit_fills", 0)),
                "bear_rebalance_days": bear_days,
                "bear_probe_days": int(stats.get("bear_probe_days", 0)),
                "bear_probe_candidate_days": int(stats.get("bear_probe_candidate_days", 0)),
                "bear_probe_buy_fills": int(stats.get("bear_probe_buy_fills", 0)),
                "deep_bear_block_days": int(stats.get("deep_bear_block_days", 0)),
            })
        rows.append(row)
    return rows


def write_summary(results, v5_summary, v4_summary, v1_summary):
    full = results[results["period"] == "full"].sort_values(
        ["annual_return_pct", "max_drawdown_pct"],
        ascending=[False, False],
    )
    period_map = {
        case: {row["period"]: row for _, row in group.iterrows()}
        for case, group in results.groupby("case")
    }
    lines = [
        "# v5 Bear Probe Evolution Experiment",
        "",
        "## Baselines",
        f"- v1 avg annual return: {v1_summary['avg_annual_return_pct']}%",
        f"- v1 median annual return: {v1_summary['median_annual_return_pct']}%",
        f"- v1 best annual return: {v1_summary['best_annual_return_pct']}%",
        f"- v1 avg max drawdown: {v1_summary['avg_max_drawdown_pct']}%",
        f"- v4 total return: {v4_summary['total_return_pct']}%",
        f"- v4 annual return: {v4_summary['annual_return_pct']}%",
        f"- v4 max drawdown: {v4_summary['max_drawdown_pct']}%",
        f"- v5 total return: {v5_summary['total_return_pct']}%",
        f"- v5 annual return: {v5_summary['annual_return_pct']}%",
        f"- v5 max drawdown: {v5_summary['max_drawdown_pct']}%",
        "",
        "## Full Period",
        "| case | total | annual | max dd | Calmar | 2018 | 2022 | 2024 | 2025 | 2026 | avg cash | zero days | trades | bear block | probe buys | probe days |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.iterrows():
        rows = period_map[row["case"]]
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | "
            f"{rows['2018']['total_return_pct']:.2f}% | {rows['2022']['total_return_pct']:.2f}% | "
            f"{rows['2024']['total_return_pct']:.2f}% | {rows['2025']['total_return_pct']:.2f}% | "
            f"{rows['2026']['total_return_pct']:.2f}% | {row['avg_cash_pct']:.2f}% | "
            f"{int(row['zero_holdings_days'])} | {int(row['trade_records'])} | "
            f"{int(row.get('regime_bear_block_days', 0))} | {int(row.get('bear_probe_buy_fills', 0))} | "
            f"{int(row.get('bear_probe_days', 0))} |"
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
    v4_summary = json.loads(V4_SUMMARY_PATH.read_text(encoding="utf-8"))
    v1_summary = summarize_v1()
    write_summary(results, v5_summary, v4_summary, v1_summary)
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
        "bear_probe_buy_fills",
        "bear_probe_days",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import html
import importlib.util
import json
import math
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "v6_warning_regime_evolution_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
README_PATH = TMP_DIR / "v6_warning_regime_evolution_README.md"
DESIGN_PATH = TMP_DIR / "v6_warning_regime_evolution_design.md"
PLAN_PATH = TMP_DIR / "v6_warning_regime_evolution_plan.md"
REPORT_PATH = OUTPUT_DIR / "report.html"

SOURCE_NOTES = [
    {
        "topic": "趋势风控",
        "source": "Trend Following, Stop Losses, and the Frequency of Trading",
        "url": "https://www.york.ac.uk/media/economics/documents/discussionpapers/2012/1211.pdf",
        "note": "移动均线类趋势规则常用于降低大回撤；月度或低频确认可减少过度交易。",
    },
    {
        "topic": "分层降风险",
        "source": "Avoiding the Big Drawdown with Trend-Following Investment Strategies",
        "url": "https://alphaarchitect.com/wp-content/uploads/2021/08/Avoiding_the_Big_Drawdown_with_Trend-Following_Investment_Strategies.pdf",
        "note": "简单模型可用多个风险规则分层降仓：触发一项降低风险，触发多项再完全防守。",
    },
    {
        "topic": "市场宽度",
        "source": "Investopedia advances and declines",
        "url": "https://www.investopedia.com/terms/a/advances-and-declines.asp",
        "note": "涨跌家数和宽度指标用于观察市场内部参与度；多数股票走弱可作为风控信号。",
    },
    {
        "topic": "复杂模型",
        "source": "QuantStart HMM regime detection",
        "url": "https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/",
        "note": "HMM 可做 regime filter，但工程复杂、需滚动训练；本轮先用可解释的规则实验。",
    },
]

CASES = [
    {
        "name": "baseline_v6",
        "warning_enabled": False,
        "warning_buy_fraction": 1.0,
        "warning_pullback_extra": 0.0,
        "warning_strong_pullback_extra": 0.0,
        "description": "当前 v6：熊市确认后不开仓。",
    },
    {
        "name": "warning_half_buy",
        "warning_enabled": True,
        "warning_buy_fraction": 0.50,
        "warning_pullback_extra": 0.00,
        "warning_strong_pullback_extra": 0.00,
        "description": "预熊期不加仓，首买金额减半，其他候选条件保持 v6。",
    },
    {
        "name": "warning_no_new_buy",
        "warning_enabled": True,
        "warning_buy_fraction": 0.0,
        "warning_pullback_extra": 0.00,
        "warning_strong_pullback_extra": 0.00,
        "description": "预熊期不加仓、不新开仓，但不强制卖出现有持仓。",
    },
    {
        "name": "warning_half_buy_strict",
        "warning_enabled": True,
        "warning_buy_fraction": 0.50,
        "warning_pullback_extra": -0.02,
        "warning_strong_pullback_extra": -0.01,
        "description": "预熊期不加仓，首买金额减半，并要求更深回撤。",
    },
    {
        "name": "warning_tiny_buy_strict",
        "warning_enabled": True,
        "warning_buy_fraction": 0.25,
        "warning_pullback_extra": -0.02,
        "warning_strong_pullback_extra": -0.01,
        "description": "预熊期不加仓，首买金额降到 25%，并要求更深回撤。",
    },
]


def load_module_from_path(module_name: str, path: Path):
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_path


def load_v6_module():
    return load_module_from_path("v6_run_backtest_warning_regime", V6_DIR / "20_run_backtest.py")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_warning_market_features(market_regime: pd.DataFrame) -> pd.DataFrame:
    out = market_regime.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("trade_date").set_index("trade_date", drop=False)
    close = pd.to_numeric(out["close"], errors="coerce")
    breadth = pd.to_numeric(out["breadth_above_bbi"], errors="coerce")
    ma120 = pd.to_numeric(out["ma120"], errors="coerce")
    ma120_slope = pd.to_numeric(out["ma120_slope_20"], errors="coerce")
    dd_252 = pd.to_numeric(out["dd_252"], errors="coerce")
    dd_120 = close / close.rolling(120, min_periods=60).max() - 1.0
    dd_60 = close / close.rolling(60, min_periods=40).max() - 1.0
    out["warning_dd_120"] = dd_120
    out["warning_dd_60"] = dd_60
    out["warning_market_ok"] = (
        ~out["regime"].eq("bear")
        & (
            (dd_252 <= -0.10)
            | (dd_120 <= -0.10)
            | (dd_60 <= -0.08)
            | ((close < ma120) & (ma120_slope < 0))
            | (breadth < 0.45)
        )
    )
    return out


def add_stock_probe_features(panel: pd.DataFrame, bbi_slope_window=5) -> pd.DataFrame:
    out = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = out.groupby("ts_code", sort=False)
    close = pd.to_numeric(out["close_qfq"], errors="coerce")
    bbi = pd.to_numeric(out["bbi_qfq"], errors="coerce")
    out["bbi_slope_5"] = grouped["bbi_qfq"].pct_change(bbi_slope_window, fill_method=None)
    out["ret_5_probe"] = grouped["close_qfq"].pct_change(5, fill_method=None)
    risk = out.get("accel_exhaustion_forbid_buy", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    out["bear_probe_stock_ok"] = (
        (close > bbi)
        & (out["bbi_slope_5"] > 0)
        & (out["ret_5_probe"] > 0)
        & ~risk
    )
    return out


def calc_bear_probe_target_amount(
    normal_first_step: float,
    cash: float,
    current_probe_exposure: float,
    max_total_probe_exposure: float,
    fraction: float,
) -> float:
    target = normal_first_step * fraction
    remaining_probe = max_total_probe_exposure - current_probe_exposure
    return max(0.0, min(target, cash, remaining_probe))


def calc_nav_metrics(nav: pd.DataFrame, trades: pd.DataFrame | None = None) -> dict:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date")
    daily_ret = frame["nav"].pct_change().dropna()
    total_ret = frame["nav"].iloc[-1] / frame["nav"].iloc[0] - 1.0
    days = max((frame["date"].iloc[-1] - frame["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    drawdown = frame["nav"] / frame["nav"].cummax() - 1.0
    max_dd = float(drawdown.min())
    sharpe = 0.0
    if daily_ret.std(ddof=0) > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std(ddof=0) * math.sqrt(252))
    return {
        "final_nav": float(frame["nav"].iloc[-1]),
        "total_return_pct": total_ret * 100.0,
        "annual_return_pct": annual_ret * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "calmar_ratio": (annual_ret / abs(max_dd)) if max_dd < 0 else 0.0,
        "sharpe": sharpe,
        "trade_records": int(len(trades)) if trades is not None else 0,
    }


def build_warning_table(v6, market, panel):
    regime = v6.build_market_regime(market, panel).reset_index()
    return add_warning_market_features(regime)


def run_warning_backtest(v6, panel, market, case, start_date, end_date):
    market_regime = v6.build_market_regime(market, panel)
    warning_table = build_warning_table(v6, market, panel)
    if end_date:
        panel = panel[panel["trade_date"] <= pd.Timestamp(end_date)].copy()
    panel = panel[panel["trade_date"] >= pd.Timestamp(start_date)].copy()
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    panel_by_date = v6.build_panel_by_date(panel)
    all_dates = sorted(panel_by_date)

    cash = v6.INIT_CASH
    holdings = {}
    trades = []
    rebalance_log = []
    score_rows = []
    nav_rows = []
    stats = {
        "signal_days": 0,
        "market_block_days": 0,
        "bear_probe_signal_days": 0,
        "bear_probe_buys": 0,
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
        "warning_signal_days": 0,
        "warning_initial_buys": 0,
        "downtrend_filter_enabled": bool(v6.DOWNTREND_BUY_FILTER_ENABLED),
        "downtrend_filter_candidate_blocks": 0,
        "downtrend_filter_signal_days": 0,
    }
    previous_market_regime_name = "unknown"

    for i, date in enumerate(all_dates):
        day_panel = v6.get_day_panel(panel, panel_by_date, date)
        risk_exit_codes = set()

        for code in list(holdings):
            if holdings[code].get("pending_sell"):
                cash, sold, reason = v6.execute_sell(
                    date, code, holdings[code], day_panel, cash, trades, holdings[code].get("pending_reason", "pending_sell")
                )
                if sold:
                    del holdings[code]
                    risk_exit_codes.add(code)
                    stats["sell_fills"] += 1
                else:
                    stats["sell_delays"] += 1

        if i > 0 and holdings:
            signal_date = all_dates[i - 1]
            signal_panel = v6.get_day_panel(panel, panel_by_date, signal_date)
            market_regime_name, _ = v6.get_market_regime(market_regime, signal_date)
            exit_reasons = {}
            for code in list(holdings):
                pos = holdings[code]
                if pos.get("pending_sell"):
                    continue
                profit_pct = v6.calc_position_profit_pct(code, pos, signal_panel)
                if (
                    v6.MARKET_REGIME_FILTER_ENABLED
                    and previous_market_regime_name == "bear"
                    and profit_pct is not None
                    and profit_pct <= v6.REGIME_BEAR_EXIT_LOSS_THRESHOLD
                ):
                    exit_reasons[code] = "long_regime_bear_exit"
                    stats["regime_bear_exit_signals"] += 1
                elif profit_pct is not None and profit_pct <= v6.LONG_STOP_LOSS_PCT:
                    exit_reasons[code] = "long_stop_loss"
                    stats["stop_loss_signals"] += 1
                elif v6.has_limit_down_signal(code, pos, signal_panel):
                    exit_reasons[code] = "long_limit_down_exit"
                    stats["limit_down_exit_signals"] += 1
                elif v6.has_bearish_volume_signal(code, pos, signal_panel):
                    exit_reasons[code] = "long_bearish_volume_exit"
                    stats["bearish_volume_exit_signals"] += 1
            for code, exit_reason in exit_reasons.items():
                cash, sold, reason = v6.execute_sell(date, code, holdings[code], day_panel, cash, trades, exit_reason)
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
            market_regime_name, regime_snapshot = v6.get_market_regime(market_regime, signal_date)
            short_drop_blocked, short_drop_reason, short_drop_snapshot = v6.market_short_drop_blocks_buy(market, signal_date)
            regime_blocked = v6.MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
            if regime_blocked:
                stats["regime_bear_block_days"] += 1
            warning_open = (
                bool(case["warning_enabled"])
                and not short_drop_blocked
                and not regime_blocked
                and signal_date in warning_table.index
                and bool(warning_table.loc[signal_date, "warning_market_ok"])
            )
            normal_open = not short_drop_blocked and not regime_blocked
            probe_open = (
                bool(v6.BEAR_PROBE_BUY_ENABLED)
                and regime_blocked
                and not short_drop_blocked
                and bool(regime_snapshot.get("bear_probe_market_ok", False))
            )

            if not normal_open and not probe_open:
                stats["market_block_days"] += 1
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": "market_regime_bear" if regime_blocked else short_drop_reason,
                    "market_regime": market_regime_name,
                    "candidate_count": 0,
                    "bought_count": 0,
                    "warning_market_ok": warning_open,
                    "bear_probe_market_ok": bool(regime_snapshot.get("bear_probe_market_ok", False)),
                    "cash": round(cash, 2),
                })
            else:
                signal_panel = v6.get_day_panel(panel, panel_by_date, signal_date)
                candidates = v6.score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)
                candidates["rank"] = np.arange(1, len(candidates) + 1)
                candidates["signal_date"] = str(signal_date)[:10]
                candidates["rebalance_date"] = str(date)[:10]
                bought_count = 0

                if normal_open and not warning_open:
                    candidate_by_code = candidates.set_index("ts_code", drop=False)
                    for code in list(holdings):
                        if code in risk_exit_codes or code not in candidate_by_code.index or code not in day_panel.index:
                            continue
                        pos = holdings[code]
                        if pos.get("pending_sell") or not v6.can_add_position(code, pos, signal_panel):
                            continue
                        target_amount = v6.next_position_step(pos)
                        if target_amount is None:
                            continue
                        available_exposure = v6.LONG_MAX_TOTAL_EXPOSURE - v6.calc_total_exposure(holdings)
                        target_amount = min(target_amount, available_exposure)
                        if target_amount < 100:
                            continue
                        cash, bought, reason = v6.execute_buy(
                            date, day_panel.loc[code], target_amount, cash, holdings, trades, "long_add_buy"
                        )
                        if bought:
                            bought_count += 1
                            stats["buy_fills"] += 1
                            stats["add_buy_fills"] += 1
                        else:
                            stats["buy_skips"] += 1

                pullback_threshold, strong_pullback_threshold = v6.regime_pullback_thresholds(market_regime_name)
                if warning_open:
                    stats["warning_signal_days"] += 1
                    pullback_threshold += float(case["warning_pullback_extra"])
                    strong_pullback_threshold += float(case["warning_strong_pullback_extra"])
                if probe_open:
                    stats["bear_probe_signal_days"] += 1
                    candidates = candidates[candidates["bear_probe_stock_ok"].fillna(False)].copy()
                    pullback_threshold = min(pullback_threshold, -0.02)
                    strong_pullback_threshold = min(strong_pullback_threshold, -0.015)

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
                target_codes = list(entry_candidates["ts_code"].head(v6.KEEP_TOP_N))
                for code in target_codes:
                    if len(holdings) >= v6.LONG_MAX_HOLDINGS:
                        break
                    if code in holdings or code in risk_exit_codes or code not in day_panel.index:
                        continue
                    available_exposure = v6.LONG_MAX_TOTAL_EXPOSURE - v6.calc_total_exposure(holdings)
                    if probe_open:
                        target_amount = v6.calc_bear_probe_target_amount(
                            float(v6.LONG_POSITION_STEPS[0]),
                            cash,
                            v6.calc_bear_probe_exposure(holdings),
                        )
                    elif warning_open:
                        target_amount = min(
                            float(v6.LONG_POSITION_STEPS[0]) * float(case["warning_buy_fraction"]),
                            available_exposure,
                        )
                    else:
                        target_amount = min(float(v6.LONG_POSITION_STEPS[0]), available_exposure)
                    target_amount = min(target_amount, available_exposure)
                    if target_amount < 100:
                        continue
                    if probe_open:
                        reason = "bear_probe_initial_buy"
                    elif warning_open:
                        reason = "warning_initial_buy"
                    else:
                        reason = "long_initial_buy"
                    cash, bought, buy_reason = v6.execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, reason)
                    if bought:
                        bought_count += 1
                        stats["buy_fills"] += 1
                        if probe_open:
                            holdings[code]["probe_entry"] = True
                            stats["bear_probe_buys"] += 1
                        if warning_open:
                            stats["warning_initial_buys"] += 1
                    else:
                        stats["buy_skips"] += 1

                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": short_drop_reason,
                    "market_regime": market_regime_name,
                    "candidate_count": int(len(candidates)),
                    "entry_candidate_count": int(len(entry_candidates)),
                    "bought_count": int(bought_count),
                    "warning_market_ok": warning_open,
                    "bear_probe_market_ok": bool(regime_snapshot.get("bear_probe_market_ok", False)),
                    "cash": round(cash, 2),
                })
            previous_market_regime_name = market_regime_name

        nav = cash + sum(v6.mark_position(c, p, day_panel) for c, p in holdings.items())
        nav_rows.append({"date": str(date)[:10], "nav": round(nav, 2), "cash": round(cash, 2), "holdings": len(holdings)})

    nav_df = pd.DataFrame(nav_rows)
    metrics = calc_nav_metrics(nav_df, pd.DataFrame(trades))
    stats.update({
        "start_date": str(nav_df["date"].iloc[0]),
        "end_date": str(nav_df["date"].iloc[-1]),
        "init_cash": v6.INIT_CASH,
        "final_nav": metrics["final_nav"],
        "total_return_pct": round(metrics["total_return_pct"], 4),
        "annual_return_pct": round(metrics["annual_return_pct"], 4),
        "max_drawdown_pct": round(metrics["max_drawdown_pct"], 4),
        "calmar_ratio": round(metrics["calmar_ratio"], 4),
        "trade_records": len(trades),
    })
    return nav_df, pd.DataFrame(trades), pd.DataFrame(rebalance_log), pd.DataFrame(score_rows), holdings, stats


@contextmanager
def no_patch():
    yield


def run_case(v6, panel, market, case):
    if case["name"] == "baseline_v6":
        nav, trades, rebalance, scores, holdings, stats = v6.run_backtest(panel, market, "2018-01-01", "2026-05-14")
    else:
        nav, trades, rebalance, scores, holdings, stats = run_warning_backtest(v6, panel, market, case, "2018-01-01", "2026-05-14")
    rows = []
    full_metrics = calc_nav_metrics(nav, trades)
    rows.append(_result_row(case, "full", full_metrics, stats, trades))
    for period, start, end in [
        ("train_2018_2021", "2018-01-01", "2021-12-31"),
        ("validate_2022_2024", "2022-01-01", "2024-12-31"),
        ("confirm_2025_2026", "2025-01-01", "2026-05-14"),
    ]:
        rows.append(_result_row(case, period, segment_metrics_from_nav(nav, start, end), stats, trades, start, end))
    return rows, nav, trades


def _result_row(case, period, metrics, stats, trades, start=None, end=None):
    trade_count = int(len(trades))
    warning_buys = int(stats.get("warning_initial_buys", 0))
    warning_signal_days = int(stats.get("warning_signal_days", 0))
    bear_probe_signal_days = int(stats.get("bear_probe_signal_days", 0))
    bear_probe_buys = int(stats.get("bear_probe_buys", 0))
    market_block_days = int(stats.get("market_block_days", 0))
    if start is not None and end is not None and not trades.empty:
        trade_frame = trades.copy()
        trade_frame["date"] = pd.to_datetime(trade_frame["date"])
        segment_trades = trade_frame[(trade_frame["date"] >= pd.Timestamp(start)) & (trade_frame["date"] <= pd.Timestamp(end))]
        trade_count = int(len(segment_trades))
        warning_buys = int((segment_trades["reason"] == "warning_initial_buy").sum()) if "reason" in segment_trades.columns else 0
        bear_probe_buys = int((segment_trades["reason"] == "bear_probe_initial_buy").sum()) if "reason" in segment_trades.columns else 0
        warning_signal_days = float("nan")
        bear_probe_signal_days = float("nan")
        market_block_days = float("nan")
    return {
        "case": case["name"],
        "period": period,
        "description": case["description"],
        "final_nav": metrics["final_nav"],
        "total_return_pct": metrics["total_return_pct"],
        "annual_return_pct": metrics["annual_return_pct"],
        "max_drawdown_pct": metrics["max_drawdown_pct"],
        "calmar_ratio": metrics["calmar_ratio"],
        "sharpe": metrics.get("sharpe", float("nan")),
        "trade_records": trade_count,
        "warning_signal_days": warning_signal_days,
        "warning_initial_buys": warning_buys,
        "bear_probe_signal_days": bear_probe_signal_days,
        "bear_probe_buys": bear_probe_buys,
        "market_block_days": market_block_days,
    }


def segment_metrics_from_nav(nav, start, end):
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date")
    end_rows = frame[frame["date"] <= pd.Timestamp(end)]
    period_rows = frame[(frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))]
    base_rows = frame[frame["date"] < pd.Timestamp(start)]
    if end_rows.empty or period_rows.empty:
        return {"final_nav": float("nan"), "total_return_pct": float("nan"), "annual_return_pct": float("nan"), "max_drawdown_pct": float("nan"), "calmar_ratio": float("nan")}
    base_nav = float(base_rows["nav"].iloc[-1]) if not base_rows.empty else float(frame["nav"].iloc[0])
    segment = pd.concat(
        [
            pd.DataFrame([{"date": pd.Timestamp(start), "nav": base_nav}]),
            period_rows[["date", "nav"]],
        ],
        ignore_index=True,
    )
    segment = segment.drop_duplicates("date", keep="last").sort_values("date")
    return calc_nav_metrics(segment)


def assert_baseline_matches_v6(results, v6_summary):
    baseline = results[(results["case"] == "baseline_v6") & (results["period"] == "full")].iloc[0]
    for key, tolerance in [("final_nav", 0.01), ("total_return_pct", 0.01), ("annual_return_pct", 0.01), ("max_drawdown_pct", 0.01), ("calmar_ratio", 0.001), ("trade_records", 0.0)]:
        if abs(float(baseline[key]) - float(v6_summary[key])) > tolerance:
            raise AssertionError(f"baseline mismatch {key}: {baseline[key]} != {v6_summary[key]}")


def select_walk_forward_best(results):
    train = results[results["period"] == "train_2018_2021"].copy()
    selected = train.sort_values(["calmar_ratio", "total_return_pct", "max_drawdown_pct"], ascending=[False, False, False]).iloc[0]
    validate = results[(results["case"] == selected["case"]) & (results["period"] == "validate_2022_2024")].iloc[0]
    confirm = results[(results["case"] == selected["case"]) & (results["period"] == "confirm_2025_2026")].iloc[0]
    return {
        "selected_case": selected["case"],
        "train_total_return_pct": float(selected["total_return_pct"]),
        "train_calmar_ratio": float(selected["calmar_ratio"]),
        "validate_total_return_pct": float(validate["total_return_pct"]),
        "validate_calmar_ratio": float(validate["calmar_ratio"]),
        "confirm_total_return_pct": float(confirm["total_return_pct"]),
        "confirm_calmar_ratio": float(confirm["calmar_ratio"]),
    }


def recommendation_for(best, baseline, walk, results=None):
    if results is not None and best["case"] != "baseline_v6":
        validate_best = results[(results["case"] == best["case"]) & (results["period"] == "validate_2022_2024")].iloc[0]
        validate_base = results[(results["case"] == "baseline_v6") & (results["period"] == "validate_2022_2024")].iloc[0]
        confirm_best = results[(results["case"] == best["case"]) & (results["period"] == "confirm_2025_2026")].iloc[0]
        confirm_base = results[(results["case"] == "baseline_v6") & (results["period"] == "confirm_2025_2026")].iloc[0]
        if (
            best["total_return_pct"] > baseline["total_return_pct"]
            and best["max_drawdown_pct"] >= baseline["max_drawdown_pct"] - 3.0
            and validate_best["total_return_pct"] >= validate_base["total_return_pct"]
            and confirm_best["total_return_pct"] >= confirm_base["total_return_pct"]
        ):
            return "建议进入合并候选：全周期、验证期和确认期均优于当前 v6，回撤没有明显恶化；合并前继续做参数邻域压力测试。"
        return (
            "暂不建议直接合并：全周期收益更高，但验证/确认分段没有同时跑赢当前 v6。"
            f"验证期 {best['case']} {validate_best['total_return_pct']:.2f}% vs v6 {validate_base['total_return_pct']:.2f}%；"
            f"确认期 {best['case']} {confirm_best['total_return_pct']:.2f}% vs v6 {confirm_base['total_return_pct']:.2f}%。"
        )
    return "暂不建议合并：本轮预熊降风险没有同时提升收益和控制回撤，当前 v6 仍是更稳基线。"


def annual_return_table(nav_by_label):
    rows = []
    for label, nav in nav_by_label.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        yearly = frame.set_index("date")["nav"].resample("YE").last().dropna()
        previous = yearly.shift(1)
        previous.iloc[0] = float(frame["nav"].iloc[0])
        for date, value in (yearly / previous - 1.0).items():
            rows.append({"strategy": label, "year": int(date.year), "return_pct": float(value * 100.0)})
    return pd.DataFrame(rows)


def monthly_return_table(nav_by_label):
    rows = []
    for label, nav in nav_by_label.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        monthly = frame.set_index("date")["nav"].resample("ME").last().dropna()
        previous = monthly.shift(1)
        previous.iloc[0] = float(frame["nav"].iloc[0])
        for date, value in (monthly / previous - 1.0).items():
            rows.append({"strategy": label, "month": date.strftime("%Y-%m"), "return_pct": float(value * 100.0)})
    return pd.DataFrame(rows)


def write_design_and_plan():
    design = """# v6 Warning Regime Evolution Design

## Brainstorming Expert
2018 年 3 月下旬才确认熊市不算晚于 20% 回撤定义，但作为风控开始偏晚。新增 warning 状态，不等同熊市，只提前降低新买风险。

## Data Expert
本轮只使用 v6 已准备的上证指数、市场宽度和股票技术面字段。Tushare 061/080/138 暂不新增，避免盘后数据时点问题和归因混乱。

## Quant Design Expert
新增 `warning_market_ok`。当市场尚未确认熊市，但出现 60/120/252 日回撤、跌破 MA120 且 MA120 转弱、或市场宽度低于 45% 时，进入预熊。预熊期不加仓，只允许减小首买金额，必要时提高回撤要求。

## Review Expert
实验只写 tmp，不改 v4/v5/v6 生产代码；baseline_v6 必须复现 v6 summary；重点检查 warning 只使用 signal_date 及以前数据。
"""
    plan = """# v6 Warning Regime Evolution Plan

1. 写测试：预熊信号由历史回撤、MA120 和市场宽度触发；熊市时不重复标记 warning。
2. 实现 tmp 实验脚本，复用 v6 回测引擎和交易函数。
3. 运行单元测试和 py_compile。
4. 运行全周期回测，输出 results.csv、README、HTML。
5. 打开 HTML 报表，给出是否合并建议。
"""
    DESIGN_PATH.write_text(design, encoding="utf-8")
    PLAN_PATH.write_text(plan, encoding="utf-8")


def html_escape(value):
    return html.escape(str(value), quote=True)


def return_matrix_html(frame, first_col):
    rows = []
    for _, row in frame.iterrows():
        cells = [f"<td>{html_escape(row[first_col])}</td>"]
        for col in frame.columns[1:]:
            cells.append(f"<td>{row[col]:.2f}%</td>" if pd.notna(row[col]) else "<td>-</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(rows)


def write_outputs(results, v4_summary, v5_summary, v6_summary, walk, nav_by_label):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    baseline = full[full["case"] == "baseline_v6"].iloc[0]
    in_sample_best = full.iloc[0]
    walk_case = str(walk["selected_case"])
    walk_full = full[full["case"] == walk_case].iloc[0]
    advice = recommendation_for(walk_full, baseline, walk, results)
    labels = ["v4", "v5", "v6", walk_case]
    annual = annual_return_table(nav_by_label).pivot(index="year", columns="strategy", values="return_pct").reset_index()
    monthly = monthly_return_table(nav_by_label).pivot(index="month", columns="strategy", values="return_pct").reset_index()
    annual = annual[[col for col in ["year", *labels] if col in annual.columns]]
    monthly = monthly[[col for col in ["month", *labels] if col in monthly.columns]]

    full_rows = []
    for _, row in full.iterrows():
        klass = "best" if row["case"] == walk_case else ("baseline" if row["case"] == "baseline_v6" else "")
        full_rows.append(
            f"<tr class='{klass}'><td>{html_escape(row['case'])}</td><td>{row['total_return_pct']:.2f}%</td>"
            f"<td>{row['annual_return_pct']:.2f}%</td><td>{row['max_drawdown_pct']:.2f}%</td>"
            f"<td>{row['calmar_ratio']:.4f}</td><td>{int(row['trade_records'])}</td>"
            f"<td>{'-' if pd.isna(row['warning_signal_days']) else int(row['warning_signal_days'])}</td><td>{int(row['warning_initial_buys'])}</td>"
            f"<td>{html_escape(row['description'])}</td></tr>"
        )
    source_rows = "".join(
        f"<tr><td>{html_escape(note['topic'])}</td><td>{html_escape(note['note'])}</td><td><a href='{note['url']}'>{html_escape(note['source'])}</a></td></tr>"
        for note in SOURCE_NOTES
    )

    readme = [
        "# v6 Warning Regime Evolution",
        "",
        "## 工作推进进度",
        "- 头脑风暴专家：预熊不是熊市确认，只提前降低新买风险。",
        "- 数据专家：使用 v6 已落地指数、宽度和技术面字段，不新增 Tushare 盘后字段。",
        "- 设计专家：预熊期不加仓，首买金额降低，必要时提高回撤要求。",
        "- 开发专家：只在 tmp 新增实验，不修改生产 v6。",
        "- Review 专家：baseline_v6 复现 v6 summary 后才比较候选。",
        "",
        "## 全周期结果",
        "| case | 总收益 | 年化 | 最大回撤 | Calmar | 预熊买入 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.iterrows():
        readme.append(f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | {int(row['warning_initial_buys'])} |")
    readme.extend([
        "",
        "## 口径说明",
        "- baseline_v6 由本脚本复跑 v6 引擎并断言匹配 v6 summary。",
        "- v4/v5 仅读取现有 output 作为背景比较，未在本脚本内重跑。",
        "- 分段行的交易数和预熊买入数按分段日期重新统计。",
        "",
        "## 建议",
        f"- {advice}",
        f"- Walk-forward 训练选择：{walk['selected_case']}。",
    ])
    README_PATH.write_text("\n".join(readme), encoding="utf-8")

    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>v6 预熊降风险实验</title>
<style>
body{{margin:0;font-family:Arial,"Microsoft YaHei",sans-serif;background:#f5f7fa;color:#1f2937}}header{{background:#263238;color:white;padding:22px 30px}}main{{padding:24px 30px}}section{{background:white;border:1px solid #d7dee8;padding:18px;margin-bottom:18px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px}}.metric{{background:#fafafa;border:1px solid #d7dee8;padding:12px}}.metric strong{{display:block;font-size:24px;margin-top:6px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #d7dee8;padding:7px 8px;text-align:right}}th:first-child,td:first-child,th:last-child,td:last-child{{text-align:left}}th{{background:#34495e;color:white}}tr.best{{background:#fff7d6;font-weight:700}}tr.baseline{{background:#e0f2fe;font-weight:700}}.advice{{background:#fff7ed;border-color:#fed7aa}}.sources td{{text-align:left}}
</style></head><body><header><h1>v6 预熊降风险实验</h1><p>在熊市确认前增加 warning 状态：不强制卖出，只减少新买和加仓风险。</p></header><main>
<section><h2>核心结果</h2><div class="grid">
<div class="metric"><span>v4 总收益</span><strong>{v4_summary['total_return_pct']:.2f}%</strong><span>回撤 {v4_summary['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>v5 总收益</span><strong>{v5_summary['total_return_pct']:.2f}%</strong><span>回撤 {v5_summary['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>当前 v6</span><strong>{baseline['total_return_pct']:.2f}%</strong><span>回撤 {baseline['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>Walk-forward 选择</span><strong>{walk_full['total_return_pct']:.2f}%</strong><span>{html_escape(walk_case)}</span></div>
</div></section>
<section class="advice"><h2>是否合并</h2><p><strong>{html_escape(advice)}</strong></p><p>Walk-forward 训练选择：{html_escape(walk['selected_case'])}；样本内最高收益：{html_escape(in_sample_best['case'])} {in_sample_best['total_return_pct']:.2f}%。验证期收益 {walk['validate_total_return_pct']:.2f}%，确认期收益 {walk['confirm_total_return_pct']:.2f}%。</p><p>口径：baseline_v6 由本脚本复跑并断言匹配 v6 summary；v4/v5 读取既有 output，仅作背景比较。</p></section>
<section><h2>全周期候选对比</h2><table><thead><tr><th>case</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>Calmar</th><th>交易数</th><th>预熊信号日</th><th>预熊买入</th><th>说明</th></tr></thead><tbody>{''.join(full_rows)}</tbody></table></section>
<section><h2>年度收益</h2><table><thead><tr>{''.join(f'<th>{html_escape(col)}</th>' for col in annual.columns)}</tr></thead><tbody>{return_matrix_html(annual, 'year')}</tbody></table></section>
<section><h2>月度收益</h2><table><thead><tr>{''.join(f'<th>{html_escape(col)}</th>' for col in monthly.columns)}</tr></thead><tbody>{return_matrix_html(monthly, 'month')}</tbody></table></section>
<section><h2>依据与定义</h2><table class="sources"><thead><tr><th>主题</th><th>程序化处理</th><th>来源</th></tr></thead><tbody>{source_rows}</tbody></table></section>
<section><h2>下一步</h2><ol><li>若候选超过 v6：继续做参数邻域压力测试。</li><li>若没有超过 v6：保留 v6，转向熊市退出或试探条件优化。</li><li>不要把预熊低价直接等同买点。</li></ol></section>
</main></body></html>"""
    REPORT_PATH.write_text(page, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_design_and_plan()
    v6 = load_v6_module()
    import config as v6_config

    v4_summary = load_json(V4_DIR / "output" / "summary.json")
    v5_summary = load_json(V5_DIR / "output" / "summary.json")
    v6_summary = load_json(v6_config.SUMMARY_PATH)

    columns = list(dict.fromkeys([*v6.PANEL_COLUMNS, "close_qfq", "bbi_qfq", "amount"]))
    panel = pd.read_parquet(v6_config.PANEL_PATH, columns=columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = v6.add_bear_probe_stock_features(panel)
    market = v6.load_market_index()

    rows = []
    navs = {}
    for case in CASES:
        print(f"running {case['name']}", flush=True)
        case_rows, nav, trades = run_case(v6, panel, market, case)
        rows.extend(case_rows)
        navs[case["name"]] = nav

    results = pd.DataFrame(rows)
    assert_baseline_matches_v6(results, v6_summary)
    walk = select_walk_forward_best(results)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)

    best_case = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False).iloc[0]["case"]
    nav_by_label = {
        "v4": pd.read_csv(V4_DIR / "output" / "nav_series.csv"),
        "v5": pd.read_csv(V5_DIR / "output" / "nav_series.csv"),
        "v6": pd.read_csv(V6_DIR / "output" / "nav_series.csv"),
        str(best_case): navs[str(best_case)],
    }
    write_outputs(results, v4_summary, v5_summary, v6_summary, walk, nav_by_label)
    print(f"Results saved: {RESULTS_PATH}")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()

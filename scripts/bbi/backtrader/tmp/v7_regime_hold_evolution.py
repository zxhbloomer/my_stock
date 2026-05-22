import html
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
BACKTRADER_DIR = ROOT / "scripts" / "bbi" / "backtrader"
V7_DIR = BACKTRADER_DIR / "v7"
RUN_DIR = Path(__file__).resolve().parent / "v7_regime_hold_evolution_output"
REPORT_PATH = RUN_DIR / "report.html"
RESULTS_PATH = RUN_DIR / "results.csv"


def load_v7_module():
    if str(V7_DIR) not in sys.path:
        sys.path.insert(0, str(V7_DIR))
    spec = importlib.util.spec_from_file_location("v7_run_backtest_for_regime_hold", V7_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v7 = load_v7_module()


VARIANTS = [
    {
        "name": "baseline_v7_replay",
        "label": "v7 replay",
        "description": "复用 v7 逻辑重新回放，校验实验脚本可复现 v7。",
    },
    {
        "name": "bull_wide_stop",
        "label": "牛市宽止损",
        "description": "bull 状态止损从 -5% 放宽到 -8%，其他规则不变。",
    },
    {
        "name": "bull_weak_repair_hold",
        "label": "牛市+弱修复持有",
        "description": "bull 止损 -8%；weak_repair 强趋势持仓止损 -7%，并保护强趋势盈利仓不被单日放量阴线卖出。",
    },
    {
        "name": "score_quality_momentum",
        "label": "质量动量重排",
        "description": "不放宽止损；候选排序强化 126 日收益、上涨天数占比、低波动和中期趋势。",
    },
    {
        "name": "score_ret126_posratio",
        "label": "长期动量重排",
        "description": "不放宽止损；在 v7 原分数上叠加 ret_126 和 positive_ret_ratio_63。",
    },
    {
        "name": "bull_early_entry",
        "label": "牛市提前入场",
        "description": "不放宽止损；bull 状态下回撤买入阈值放松，尝试减少牛市漏买。",
    },
]


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def classify_trade_state(market_regime_name, regime_snapshot):
    if market_regime_name in {"bull", "bear"}:
        return market_regime_name
    if market_regime_name != "neutral" or not regime_snapshot:
        return market_regime_name
    market_dd = safe_float(regime_snapshot.get("market_dd_252"), 0.0)
    breadth = safe_float(regime_snapshot.get("breadth_above_bbi"), 1.0)
    breadth_change = safe_float(regime_snapshot.get("breadth_change_5"), 0.0)
    if market_dd <= -0.10 and breadth <= 0.55 and breadth_change > 0.0:
        return "weak_repair"
    return "neutral"


def is_strong_trend_hold_candidate(row):
    return (
        safe_float(row.get("above_ratio_63"), 0.0) >= 0.70
        and safe_float(row.get("above_ratio_126"), 0.0) >= 0.55
        and safe_float(row.get("close_qfq"), 0.0) > safe_float(row.get("bbi_qfq"), float("inf"))
        and safe_float(row.get("ret_63"), 0.0) > 0.0
        and safe_float(row.get("recent_limit_down_20"), 1.0) == 0.0
        and safe_float(row.get("hot_money_risk_hits"), 99.0) < 2.0
    )


def state_stop_loss_pct(trade_state, variant_name, strong_hold):
    if variant_name in {"baseline_v7_replay", "baseline_v7", "score_quality_momentum", "score_ret126_posratio", "bull_early_entry"}:
        return v7.LONG_STOP_LOSS_PCT
    if variant_name == "bull_wide_stop":
        return -0.08 if trade_state == "bull" else v7.LONG_STOP_LOSS_PCT
    if variant_name == "bull_weak_repair_hold":
        if trade_state == "bull":
            return -0.08
        if trade_state == "weak_repair" and strong_hold:
            return -0.07
        return v7.LONG_STOP_LOSS_PCT
    raise ValueError(f"unknown variant: {variant_name}")


def zscore(series):
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return (values - values.mean()) / std


def rerank_candidates(candidates, variant_name):
    if candidates.empty or variant_name in {"baseline_v7_replay", "bull_wide_stop", "bull_weak_repair_hold", "bull_early_entry"}:
        return candidates
    data = candidates.copy()
    for col, default in {
        "ret_126": 0.0,
        "positive_ret_ratio_63": 0.0,
        "volatility_63": data.get("volatility_63", pd.Series(0.0, index=data.index)).median()
        if "volatility_63" in data else 0.0,
        "amount_ma20": 1.0,
        "above_ratio_63": 0.0,
        "above_ratio_126": 0.0,
        "ret_63": 0.0,
    }.items():
        if col not in data.columns:
            data[col] = default
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(default)
    if variant_name == "score_quality_momentum":
        data["score"] = (
            0.20 * zscore(data["above_ratio_63"])
            + 0.18 * zscore(data["above_ratio_126"])
            + 0.18 * zscore(data["ret_63"])
            + 0.16 * zscore(data["ret_126"])
            + 0.14 * zscore(data["positive_ret_ratio_63"])
            - 0.10 * zscore(data["volatility_63"])
            + 0.04 * zscore(np.log(data["amount_ma20"].clip(lower=1.0)))
        )
    elif variant_name == "score_ret126_posratio":
        data["score"] = (
            pd.to_numeric(data["score"], errors="coerce").fillna(0.0)
            + 0.12 * zscore(data["ret_126"])
            + 0.08 * zscore(data["positive_ret_ratio_63"])
            - 0.04 * zscore(data["volatility_63"])
        )
    else:
        raise ValueError(f"unknown rerank variant: {variant_name}")
    sort_cols = [col for col in ["score", "above_ratio_63", "ret_63", "amount_ma20"] if col in data.columns]
    return data.sort_values(sort_cols, ascending=[False] * len(sort_cols)).reset_index(drop=True)


def score_candidates_for_variant(signal_panel, variant_name, diagnostics):
    candidates = v7.score_candidates(signal_panel, diagnostics=diagnostics).reset_index(drop=True)
    return rerank_candidates(candidates, variant_name)


def entry_thresholds_for_variant(market_regime_name, variant_name):
    pullback_threshold, strong_pullback_threshold = v7.regime_pullback_thresholds(market_regime_name)
    if variant_name == "bull_early_entry" and market_regime_name == "bull":
        return -0.025, -0.012
    return pullback_threshold, strong_pullback_threshold


def run_backtest_variant(panel, market, start_date, end_date, variant_name):
    if "positive_ret_ratio_63" not in panel.columns:
        panel = v7.add_positive_return_ratio(panel)
    if "market_ret_63" not in panel.columns:
        panel = v7.add_market_ret_63(panel, market)
    if v7.BEAR_PROBE_BUY_ENABLED and "bear_probe_stock_ok" not in panel.columns:
        panel = v7.add_bear_probe_stock_features(panel)
    market_regime = v7.build_market_regime(market, panel)
    if end_date:
        panel = panel[panel["trade_date"] <= pd.Timestamp(end_date)].copy()
    panel = panel[panel["trade_date"] >= pd.Timestamp(start_date)].copy()
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    panel_by_date = v7.build_panel_by_date(panel)
    all_dates = sorted(panel_by_date)

    cash = v7.INIT_CASH
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
        "bear_probe_enabled": bool(v7.BEAR_PROBE_BUY_ENABLED),
        "bear_probe_signal_days": 0,
        "bear_probe_buys": 0,
        "downtrend_filter_enabled": bool(v7.DOWNTREND_BUY_FILTER_ENABLED),
        "downtrend_filter_candidate_blocks": 0,
        "downtrend_filter_signal_days": 0,
        "weak_lowvol_mom_enabled": True,
        "weak_lowvol_mom_signal_days": 0,
        "weak_lowvol_mom_candidate_blocks": 0,
        "wide_stop_variant": variant_name,
        "bull_wide_stop_checks": 0,
        "weak_repair_stop_checks": 0,
        "protected_bearish_volume_exits": 0,
    }
    previous_market_regime_name = "unknown"

    for i, date in enumerate(all_dates):
        day_panel = v7.get_day_panel(panel, panel_by_date, date)
        risk_exit_codes = set()

        for code in list(holdings):
            if holdings[code].get("pending_sell"):
                pending_reason = holdings[code].get("pending_reason", "pending_sell")
                cash, sold, reason = v7.execute_sell(date, code, holdings[code], day_panel, cash, trades, pending_reason)
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
            signal_panel = v7.get_day_panel(panel, panel_by_date, signal_date)
            market_regime_name, regime_snapshot = v7.get_market_regime(market_regime, signal_date)
            trade_state = classify_trade_state(market_regime_name, regime_snapshot)
            exit_reasons = {}
            for code in list(holdings):
                pos = holdings[code]
                if pos.get("pending_sell"):
                    continue
                profit_pct = v7.calc_position_profit_pct(code, pos, signal_panel)
                strong_hold = code in signal_panel.index and is_strong_trend_hold_candidate(signal_panel.loc[code])
                stop_loss_pct = state_stop_loss_pct(trade_state, variant_name, strong_hold)
                if trade_state == "bull" and stop_loss_pct < v7.LONG_STOP_LOSS_PCT:
                    stats["bull_wide_stop_checks"] += 1
                if trade_state == "weak_repair" and stop_loss_pct < v7.LONG_STOP_LOSS_PCT:
                    stats["weak_repair_stop_checks"] += 1
                if (
                    v7.MARKET_REGIME_FILTER_ENABLED
                    and previous_market_regime_name == "bear"
                    and profit_pct is not None
                    and profit_pct <= v7.REGIME_BEAR_EXIT_LOSS_THRESHOLD
                ):
                    exit_reasons[code] = "long_regime_bear_exit"
                    stats["regime_bear_exit_signals"] += 1
                elif profit_pct is not None and profit_pct <= stop_loss_pct:
                    exit_reasons[code] = "long_stop_loss"
                    stats["stop_loss_signals"] += 1
                elif v7.has_limit_down_signal(code, pos, signal_panel):
                    exit_reasons[code] = "long_limit_down_exit"
                    stats["limit_down_exit_signals"] += 1
                elif v7.has_bearish_volume_signal(code, pos, signal_panel):
                    if variant_name == "bull_weak_repair_hold" and strong_hold and trade_state in {"bull", "weak_repair"}:
                        stats["protected_bearish_volume_exits"] += 1
                    else:
                        exit_reasons[code] = "long_bearish_volume_exit"
                        stats["bearish_volume_exit_signals"] += 1
            for code, exit_reason in exit_reasons.items():
                cash, sold, reason = v7.execute_sell(
                    date,
                    code,
                    holdings[code],
                    day_panel,
                    cash,
                    trades,
                    exit_reason,
                )
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
            market_regime_name, regime_snapshot = v7.get_market_regime(market_regime, signal_date)
            short_drop_blocked, short_drop_reason, short_drop_snapshot = v7.market_short_drop_blocks_buy(market, signal_date)
            regime_blocked = v7.MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
            if regime_blocked:
                stats["regime_bear_block_days"] += 1
            probe_open = (
                v7.BEAR_PROBE_BUY_ENABLED
                and regime_blocked
                and not short_drop_blocked
                and bool(regime_snapshot.get("bear_probe_market_ok", False))
            )
            if short_drop_blocked or (regime_blocked and not probe_open):
                stats["market_block_days"] += 1
                if short_drop_reason in {"missing_market", "missing_market_history"}:
                    stats["missing_market_days"] += 1
                market_reason = "market_regime_bear" if regime_blocked and not short_drop_blocked else short_drop_reason
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": market_reason,
                    "market_regime": market_regime_name,
                    "trade_state": classify_trade_state(market_regime_name, regime_snapshot),
                    "candidate_count": 0,
                    "bought_count": 0,
                    "market_ret_5": round(short_drop_snapshot.get("market_ret_5", float("nan")), 4),
                    "market_dd_20": round(regime_snapshot.get("market_dd_20", short_drop_snapshot.get("market_dd_20", float("nan"))), 4),
                    "market_dd_252": round(regime_snapshot.get("market_dd_252", float("nan")), 4),
                    "breadth_above_bbi": round(regime_snapshot.get("breadth_above_bbi", float("nan")), 4),
                    "breadth_change_5": round(regime_snapshot.get("breadth_change_5", float("nan")), 4),
                    "bear_probe_market_ok": bool(regime_snapshot.get("bear_probe_market_ok", False)),
                    "cash": round(cash, 2),
                })
            else:
                signal_panel = v7.get_day_panel(panel, panel_by_date, signal_date)
                candidates = score_candidates_for_variant(signal_panel, variant_name, stats).reset_index(drop=True)
                candidates = v7.apply_weak_lowvol_mom_filter(
                    candidates,
                    market_regime_name,
                    regime_snapshot,
                    diagnostics=stats,
                ).reset_index(drop=True)
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
                    "ma20_qfq", "ma20_slope_10", "early_weakness_downtrend",
                    "up_accel_exhaustion", "bear_down_accel_risk", "accel_exhaustion_forbid_buy",
                    "bbi_slope_5", "ret_5_probe", "bear_probe_stock_ok",
                    "positive_ret_ratio_63", "market_ret_63",
                    "volatility_63", "amount_ma20", "circ_mv_ma20", "pullback_63", "strong_trend",
                ]
                score_rows.extend(candidates[score_cols].head(100).to_dict("records"))
                bought_count = 0
                candidate_by_code = candidates.set_index("ts_code", drop=False)
                if not probe_open:
                    for code in list(holdings):
                        if code in risk_exit_codes or code not in candidate_by_code.index or code not in day_panel.index:
                            continue
                        pos = holdings[code]
                        if pos.get("pending_sell") or not v7.can_add_position(code, pos, signal_panel):
                            continue
                        target_amount = v7.next_position_step(pos)
                        if target_amount is None:
                            continue
                        available_exposure = v7.LONG_MAX_TOTAL_EXPOSURE - v7.calc_total_exposure(holdings)
                        target_amount = min(target_amount, available_exposure)
                        if target_amount < 100:
                            continue
                        cash, bought, reason = v7.execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, "long_add_buy")
                        if bought:
                            bought_count += 1
                            stats["buy_fills"] += 1
                            stats["add_buy_fills"] += 1
                        else:
                            stats["buy_skips"] += 1

                pullback_threshold, strong_pullback_threshold = entry_thresholds_for_variant(market_regime_name, variant_name)
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
                target_codes = list(entry_candidates["ts_code"].head(v7.KEEP_TOP_N))
                for code in target_codes:
                    if len(holdings) >= v7.LONG_MAX_HOLDINGS:
                        break
                    if code in holdings or code in risk_exit_codes or code not in day_panel.index:
                        continue
                    available_exposure = v7.LONG_MAX_TOTAL_EXPOSURE - v7.calc_total_exposure(holdings)
                    if probe_open:
                        target_amount = v7.calc_bear_probe_target_amount(
                            float(v7.LONG_POSITION_STEPS[0]),
                            cash,
                            v7.calc_bear_probe_exposure(holdings),
                        )
                    else:
                        target_amount = min(float(v7.LONG_POSITION_STEPS[0]), available_exposure)
                    target_amount = min(target_amount, available_exposure)
                    if target_amount < 100:
                        break
                    buy_reason = "bear_probe_initial_buy" if probe_open else "long_initial_buy"
                    cash, bought, reason = v7.execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, buy_reason)
                    if bought:
                        bought_count += 1
                        stats["buy_fills"] += 1
                        if probe_open:
                            holdings[code]["probe_entry"] = True
                            stats["bear_probe_buys"] += 1
                    else:
                        stats["buy_skips"] += 1
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": short_drop_reason,
                    "market_regime": market_regime_name,
                    "trade_state": classify_trade_state(market_regime_name, regime_snapshot),
                    "candidate_count": int(len(candidates)),
                    "entry_candidate_count": int(len(entry_candidates)),
                    "bought_count": int(bought_count),
                    "market_ret_5": round(short_drop_snapshot.get("market_ret_5", float("nan")), 4),
                    "market_dd_20": round(short_drop_snapshot.get("market_dd_20", float("nan")), 4),
                    "market_dd_252": round(regime_snapshot.get("market_dd_252", float("nan")), 4),
                    "breadth_above_bbi": round(regime_snapshot.get("breadth_above_bbi", float("nan")), 4),
                    "breadth_change_5": round(regime_snapshot.get("breadth_change_5", float("nan")), 4),
                    "bear_probe_market_ok": bool(regime_snapshot.get("bear_probe_market_ok", False)),
                    "pullback_threshold": round(pullback_threshold, 4),
                    "strong_pullback_threshold": round(strong_pullback_threshold, 4),
                    "cash": round(cash, 2),
                })
            previous_market_regime_name = market_regime_name

        nav = cash + sum(v7.mark_position(c, p, day_panel) for c, p in holdings.items())
        nav_rows.append({"date": str(date)[:10], "nav": round(nav, 2), "cash": round(cash, 2), "holdings": len(holdings)})

    nav_df = pd.DataFrame(nav_rows)
    total_ret = nav_df["nav"].iloc[-1] / v7.INIT_CASH - 1.0
    days = max((pd.Timestamp(nav_df["date"].iloc[-1]) - pd.Timestamp(nav_df["date"].iloc[0])).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    max_dd = v7.calc_max_drawdown(nav_df)
    stats.update({
        "start_date": str(nav_df["date"].iloc[0]),
        "end_date": str(nav_df["date"].iloc[-1]),
        "init_cash": v7.INIT_CASH,
        "final_nav": float(nav_df["nav"].iloc[-1]),
        "total_return_pct": round(total_ret * 100.0, 4),
        "annual_return_pct": round(annual_ret * 100.0, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "calmar_ratio": round((annual_ret * 100.0) / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "trade_records": len(trades),
    })
    return nav_df, pd.DataFrame(trades), pd.DataFrame(rebalance_log), pd.DataFrame(score_rows), holdings, stats


def period_return_table(nav_by_name, freq):
    rows = []
    for name, nav in nav_by_name.items():
        if nav is None or nav.empty:
            continue
        data = nav.copy()
        data["date"] = pd.to_datetime(data["date"])
        data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
        data = data.dropna(subset=["date", "nav"]).sort_values("date")
        data["period"] = data["date"].dt.to_period(freq)
        period_last = data.groupby("period", sort=True).tail(1).copy()
        period_last["prev_nav"] = period_last["nav"].shift(1)
        if not period_last.empty:
            period_last.loc[period_last.index[0], "prev_nav"] = float(data["nav"].iloc[0])
        for _, row in period_last.iterrows():
            start_nav = float(row["prev_nav"])
            end_nav = float(row["nav"])
            rows.append({
                "period": str(row["period"]),
                "strategy": name,
                "return_pct": round((end_nav / start_nav - 1.0) * 100.0, 2) if start_nav > 0 else np.nan,
            })
    return pd.DataFrame(rows)


def pivot_period_returns(period_rows):
    if period_rows.empty:
        return pd.DataFrame()
    return period_rows.pivot(index="period", columns="strategy", values="return_pct").reset_index()


def table_html(title, df, max_rows=None):
    if df is None or df.empty:
        return f"<section><h2>{html.escape(title)}</h2><p>无数据</p></section>"
    view = df.head(max_rows) if max_rows else df
    return f"<section><h2>{html.escape(title)}</h2>{view.to_html(index=False, escape=True, classes='data')}</section>"


def load_summary(version):
    path = BACKTRADER_DIR / version / "output" / "summary.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    data["strategy"] = version
    return data


def load_nav(version):
    path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def summarize_replay_delta(results):
    rows = []
    v7_summary = load_summary("v7") or {}
    replay = results[results["strategy"] == "baseline_v7_replay"]
    if replay.empty:
        return pd.DataFrame()
    replay_row = replay.iloc[0].to_dict()
    for field in ["total_return_pct", "annual_return_pct", "max_drawdown_pct", "trade_records"]:
        rows.append({
            "field": field,
            "v7_output": v7_summary.get(field),
            "replay": replay_row.get(field),
            "delta": round(float(replay_row.get(field, 0)) - float(v7_summary.get(field, 0)), 6),
        })
    v7_nav = load_nav("v7")
    replay_nav_path = RUN_DIR / "baseline_v7_replay" / "nav_series.csv"
    if replay_nav_path.exists() and not v7_nav.empty:
        replay_nav = pd.read_csv(replay_nav_path)
        merged = v7_nav[["date", "nav"]].merge(
            replay_nav[["date", "nav"]],
            on="date",
            how="outer",
            suffixes=("_v7", "_replay"),
        )
        merged["nav_abs_delta"] = (
            pd.to_numeric(merged["nav_replay"], errors="coerce")
            - pd.to_numeric(merged["nav_v7"], errors="coerce")
        ).abs()
        rows.append({
            "field": "nav_rows",
            "v7_output": len(v7_nav),
            "replay": len(replay_nav),
            "delta": int(len(replay_nav) - len(v7_nav)),
        })
        rows.append({
            "field": "nav_max_abs_delta",
            "v7_output": 0,
            "replay": round(float(merged["nav_abs_delta"].max()), 6),
            "delta": round(float(merged["nav_abs_delta"].max()), 6),
        })
    v7_trades_path = BACKTRADER_DIR / "v7" / "output" / "trade_records.csv"
    replay_trades_path = RUN_DIR / "baseline_v7_replay" / "trade_records.csv"
    if v7_trades_path.exists() and replay_trades_path.exists():
        v7_trades = pd.read_csv(v7_trades_path)
        replay_trades = pd.read_csv(replay_trades_path)
        rows.append({
            "field": "trade_rows",
            "v7_output": len(v7_trades),
            "replay": len(replay_trades),
            "delta": int(len(replay_trades) - len(v7_trades)),
        })
    return pd.DataFrame(rows)


def render_report(results, yearly, monthly, replay_delta, notes):
    best = results.sort_values(["total_return_pct", "calmar_ratio"], ascending=[False, False]).iloc[0]
    replay_ok = bool(
        replay_delta is not None
        and not replay_delta.empty
        and pd.to_numeric(replay_delta["delta"], errors="coerce").abs().fillna(0).max() == 0
    )
    recommendation = (
        f"有条件候选：{best['strategy']}。"
        "只建议抽取该思想做 v7 小补丁；合并前需单独复跑 v7，并确认数据区间、NAV、交易记录复现一致。"
        if replay_ok
        else "不建议合并：baseline replay 未通过 NAV/交易级校验，应先修复实验口径。"
    )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>v7 Regime Hold Evolution Report</title>
  <style>
    body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; margin: 24px; color: #222; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    h2 {{ margin-top: 28px; font-size: 18px; }}
    .note {{ background: #f6f8fa; border-left: 4px solid #2f6feb; padding: 12px; margin: 16px 0; }}
    table.data {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    table.data th, table.data td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
    table.data th:first-child, table.data td:first-child {{ text-align: left; }}
    table.data th {{ background: #f0f3f6; }}
    .bad {{ color: #b42318; }}
    .good {{ color: #067647; }}
  </style>
</head>
<body>
  <h1>v7 Regime Hold Evolution Report</h1>
  <div class="note">
    <div><b>运行结论：</b>{html.escape(recommendation)}</div>
    <div><b>最佳总收益：</b>{html.escape(str(best['strategy']))}，{best['total_return_pct']:.2f}%；最大回撤 {best['max_drawdown_pct']:.2f}%。</div>
    <div><b>说明：</b>本轮只验证状态化止损/持有保护，未接入新板块表。</div>
  </div>
  {table_html("Summary 对比", results)}
  {table_html("v7 replay 复现误差", replay_delta)}
  {table_html("年度收益对比（%）", yearly)}
  {table_html("月度收益对比（%）", monthly, max_rows=140)}
  {table_html("专家流程与建议", notes)}
</body>
</html>
"""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def run_experiment():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    panel = pd.read_parquet(V7_DIR / "output" / "panel.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = pd.read_parquet(V7_DIR / "output" / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")

    nav_by_name = {}
    summary_rows = []
    for version in ["v4", "v5", "v6", "v7"]:
        summary = load_summary(version)
        if summary:
            summary_rows.append({
                "strategy": version,
                "total_return_pct": summary.get("total_return_pct"),
                "annual_return_pct": summary.get("annual_return_pct"),
                "max_drawdown_pct": summary.get("max_drawdown_pct"),
                "calmar_ratio": summary.get("calmar_ratio"),
                "trade_records": summary.get("trade_records"),
                "stop_loss_fills": summary.get("stop_loss_fills"),
                "bearish_volume_exit_fills": summary.get("bearish_volume_exit_fills"),
                "protected_bearish_volume_exits": "",
                "bull_wide_stop_checks": "",
                "weak_repair_stop_checks": "",
            })
        nav_by_name[version] = load_nav(version)

    for variant in VARIANTS:
        print(f"[v7-regime-hold] running {variant['name']}", flush=True)
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = run_backtest_variant(
            panel.copy(),
            market.copy(),
            v7.BACKTEST_START_DATE,
            None,
            variant["name"],
        )
        variant_dir = RUN_DIR / variant["name"]
        variant_dir.mkdir(parents=True, exist_ok=True)
        nav_df.to_csv(variant_dir / "nav_series.csv", index=False, encoding="utf-8-sig")
        trades_df.to_csv(variant_dir / "trade_records.csv", index=False, encoding="utf-8-sig")
        rebalance_df.to_csv(variant_dir / "rebalance_log.csv", index=False, encoding="utf-8-sig")
        scores_df.to_csv(variant_dir / "strength_scores.csv", index=False, encoding="utf-8-sig")
        (variant_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        nav_by_name[variant["name"]] = nav_df
        summary_rows.append({
            "strategy": variant["name"],
            "total_return_pct": stats.get("total_return_pct"),
            "annual_return_pct": stats.get("annual_return_pct"),
            "max_drawdown_pct": stats.get("max_drawdown_pct"),
            "calmar_ratio": stats.get("calmar_ratio"),
            "trade_records": stats.get("trade_records"),
            "stop_loss_fills": stats.get("stop_loss_fills"),
            "bearish_volume_exit_fills": stats.get("bearish_volume_exit_fills"),
            "protected_bearish_volume_exits": stats.get("protected_bearish_volume_exits"),
            "bull_wide_stop_checks": stats.get("bull_wide_stop_checks"),
            "weak_repair_stop_checks": stats.get("weak_repair_stop_checks"),
        })

    results = pd.DataFrame(summary_rows)
    results.to_csv(RESULTS_PATH, index=False, encoding="utf-8-sig")
    yearly = pivot_period_returns(period_return_table(nav_by_name, "Y"))
    monthly = pivot_period_returns(period_return_table(nav_by_name, "M"))
    yearly.to_csv(RUN_DIR / "yearly_returns.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(RUN_DIR / "monthly_returns.csv", index=False, encoding="utf-8-sig")
    replay_delta = summarize_replay_delta(results)
    replay_delta.to_csv(RUN_DIR / "replay_delta.csv", index=False, encoding="utf-8-sig")
    notes = pd.DataFrame(
        [
            {"role": "量化定义专家", "conclusion": "趋势跟踪和行业轮动可用中期动量/相对强弱刻画；本轮优先验证持有逻辑。"},
            {"role": "设计专家", "conclusion": "bear 不扩大交易；bull 和 weak_repair 才允许宽止损。"},
            {"role": "开发专家", "conclusion": "仅在 tmp 复制 v7 主循环，正式 v7 不变。"},
            {"role": "代码审阅专家", "conclusion": "重点检查 replay 是否复现 v7、盘后字段未新增、信号仍使用上一交易日。"},
            {"role": "运行确认专家", "conclusion": "以 summary、年度、月度和 replay_delta 判断是否值得合并。"},
        ]
    )
    render_report(results, yearly, monthly, replay_delta, notes)
    return REPORT_PATH


if __name__ == "__main__":
    print(run_experiment())

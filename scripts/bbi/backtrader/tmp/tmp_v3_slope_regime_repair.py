import csv
from dataclasses import dataclass
from html import escape
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "tmp_v3_slope_regime_repair_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
README_PATH = TMP_DIR / "tmp_v3_slope_regime_repair_README.md"


@dataclass(frozen=True)
class CaseConfig:
    name: str
    description: str
    bear_repair_enabled: bool = False
    bear_repair_max_exposure: float = 0.0
    bear_repair_max_holdings: int = 0
    allow_bear_repair_add_buy: bool = False
    bull_accel_relax: bool = False
    blowoff_guard: bool = False


CASES = [
    CaseConfig("baseline_v6_replay", "v6 PIT baseline replay."),
    CaseConfig(
        "bear_repair_20",
        "Bear repair allows small trial entries with max 20% exposure.",
        bear_repair_enabled=True,
        bear_repair_max_exposure=0.20,
        bear_repair_max_holdings=2,
    ),
    CaseConfig(
        "bear_repair_40",
        "Bear repair allows trial entries with max 40% exposure.",
        bear_repair_enabled=True,
        bear_repair_max_exposure=0.40,
        bear_repair_max_holdings=2,
    ),
    CaseConfig(
        "bear_repair_40_bull_accel",
        "Bear repair plus relaxed pullback in healthy bull/neutral acceleration.",
        bear_repair_enabled=True,
        bear_repair_max_exposure=0.40,
        bear_repair_max_holdings=2,
        bull_accel_relax=True,
    ),
    CaseConfig(
        "bear_repair_40_blowoff_guard",
        "Bear repair plus no-buy guard for extreme blowoff acceleration.",
        bear_repair_enabled=True,
        bear_repair_max_exposure=0.40,
        bear_repair_max_holdings=2,
        blowoff_guard=True,
    ),
]
CASES_BY_NAME = {case.name: case for case in CASES}


SOURCE_NOTES = [
    {
        "topic": "Momentum crashes",
        "url": "https://www.chicagobooth.edu/review/understanding-momentum-crashes",
        "note": "Bear-market rebounds can reverse classic momentum leadership; volatility and market stress matter.",
    },
    {
        "topic": "Slow momentum with fast reversion",
        "url": "https://arxiv.org/pdf/2105.13727",
        "note": "Trend systems can be slow at turning points; fast repair/change signals may improve responsiveness.",
    },
    {
        "topic": "Moving average slope",
        "url": "https://ptgmedia.pearsoncmg.com/images/0131479024/samplechapter/0131479024_ch03.pdf",
        "note": "Accelerating slopes can confirm trend continuation; deceleration can warn of reversal.",
    },
    {
        "topic": "Tushare data",
        "url": "docs/tushare/接口清单.md",
        "note": "Use v6 prepared PIT daily tables only: stock_basic, stock_st, stk_factor_pro, stk_limit, top_list, idx_factor_pro.",
    },
]


def load_module_from_path(module_name, path):
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


def load_v6():
    return load_module_from_path("v6_run_backtest_for_slope_repair", V6_DIR / "20_run_backtest.py")


def prepare_market_index(market):
    out = market.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    return out.sort_values("trade_date").set_index("trade_date", drop=False)


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def add_market_repair_features(market_regime):
    out = market_regime.copy()
    if "trade_date" in out.columns:
        out = out.drop(columns=["trade_date"])
    out = out.reset_index().rename(columns={"index": "trade_date"})
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("trade_date").reset_index(drop=True)
    close = pd.to_numeric(out["close"], errors="coerce")
    out["market_ret_20"] = close / close.shift(20) - 1.0
    out["dd_252_min_60"] = pd.to_numeric(out["dd_252"], errors="coerce").rolling(60, min_periods=20).min()
    out["dd_252_repair"] = pd.to_numeric(out["dd_252"], errors="coerce") - out["dd_252_min_60"]
    out["ma120_slope_20_delta_10"] = (
        pd.to_numeric(out["ma120_slope_20"], errors="coerce")
        - pd.to_numeric(out["ma120_slope_20"], errors="coerce").shift(10)
    )
    out["breadth_delta_10"] = (
        pd.to_numeric(out["breadth_above_bbi"], errors="coerce")
        - pd.to_numeric(out["breadth_above_bbi"], errors="coerce").shift(10)
    )
    out["bull_accel"] = (
        out["regime"].isin(["bull", "neutral"])
        & (pd.to_numeric(out["ma120_slope_20"], errors="coerce") > 0)
        & (out["ma120_slope_20_delta_10"] > 0)
        & (pd.to_numeric(out["breadth_above_bbi"], errors="coerce") >= 0.55)
        & (out["breadth_delta_10"] >= 0)
    )
    out["bear_repair"] = (
        (out["regime"] == "bear")
        & (out["dd_252_repair"] >= 0.05)
        & (out["ma120_slope_20_delta_10"] > 0)
        & (out["breadth_delta_10"] >= 0.15)
        & (out["market_ret_20"] > 0)
    )
    out = out.set_index("trade_date", drop=False)
    return out


def add_stock_slope_features(panel):
    out = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = out.groupby("ts_code", sort=False)
    out["ret_5_slope"] = grouped["close_qfq"].pct_change(5, fill_method=None)
    out["ret_10_slope"] = grouped["close_qfq"].pct_change(10, fill_method=None)
    out["slope_5"] = out["ret_5_slope"] / 5.0
    out["slope_10"] = out["ret_10_slope"] / 10.0
    out["ma20_distance"] = out["close_qfq"] / out["ma20_qfq"] - 1.0
    out["amount_ma5_slope"] = (
        grouped["amount"]
        .rolling(5, min_periods=5)
        .mean()
        .reset_index(level=0, drop=True)
    )
    out["amount_ratio_5_20"] = out["amount_ma5_slope"] / out["amount_ma20"]
    return out


def is_stock_blowoff(row):
    return (
        safe_float(row.get("ret_10_slope")) >= 0.18
        and safe_float(row.get("slope_5")) > safe_float(row.get("slope_10")) * 1.8
        and safe_float(row.get("ma20_distance")) > 0.18
        and safe_float(row.get("amount_ratio_5_20")) >= 1.5
    )


def build_market_regime_with_repair(v6, market, panel):
    regime = v6.build_market_regime(market, panel)
    return add_market_repair_features(regime)


def run_case(case, panel, market, start_date, end_date):
    v6 = load_v6()
    panel = add_stock_slope_features(panel)
    market = prepare_market_index(market)
    market_regime = build_market_regime_with_repair(v6, market, panel)
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
        "bear_repair_days": 0,
        "bear_repair_buy_fills": 0,
        "bull_accel_days": 0,
        "blowoff_candidate_blocks": 0,
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
                pending_reason = holdings[code].get("pending_reason", "pending_sell")
                cash, sold, _ = v6.execute_sell(date, code, holdings[code], day_panel, cash, trades, pending_reason)
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
                cash, sold, _ = v6.execute_sell(date, code, holdings[code], day_panel, cash, trades, exit_reason)
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
            signal_regime_row = market_regime.loc[signal_date] if signal_date in market_regime.index else pd.Series(dtype=object)
            bear_repair = bool(signal_regime_row.get("bear_repair", False))
            bull_accel = bool(signal_regime_row.get("bull_accel", False))
            short_drop_blocked, short_drop_reason, short_drop_snapshot = v6.market_short_drop_blocks_buy(market, signal_date)
            regime_blocked = v6.MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
            repair_override = case.bear_repair_enabled and regime_blocked and not short_drop_blocked and bear_repair
            buy_blocked = short_drop_blocked or (regime_blocked and not repair_override)
            if regime_blocked:
                stats["regime_bear_block_days"] += 1
            if repair_override:
                stats["bear_repair_days"] += 1
            if bull_accel:
                stats["bull_accel_days"] += 1

            if buy_blocked:
                stats["market_block_days"] += 1
                market_reason = "market_regime_bear" if regime_blocked and not short_drop_blocked else short_drop_reason
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": market_reason,
                    "market_regime": market_regime_name,
                    "bear_repair": bear_repair,
                    "bull_accel": bull_accel,
                    "candidate_count": 0,
                    "entry_candidate_count": 0,
                    "bought_count": 0,
                    "cash": round(cash, 2),
                })
            else:
                signal_panel = v6.get_day_panel(panel, panel_by_date, signal_date)
                candidates = v6.score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)
                if case.blowoff_guard and not candidates.empty:
                    blowoff = candidates.apply(is_stock_blowoff, axis=1)
                    stats["blowoff_candidate_blocks"] += int(blowoff.sum())
                    candidates = candidates[~blowoff].copy()
                candidates["rank"] = np.arange(1, len(candidates) + 1)
                candidates["signal_date"] = str(signal_date)[:10]
                candidates["rebalance_date"] = str(date)[:10]
                for col in ["bear_repair", "bull_accel"]:
                    candidates[col] = bear_repair if col == "bear_repair" else bull_accel
                score_cols = [
                    "signal_date", "rebalance_date", "rank", "ts_code", "name", "score",
                    "ret_21", "ret_63", "ret_126", "pullback_63", "strong_trend",
                    "ma20_slope_10", "accel_exhaustion_forbid_buy", "bear_repair", "bull_accel",
                ]
                score_rows.extend(candidates[[c for c in score_cols if c in candidates.columns]].head(100).to_dict("records"))

                bought_count = 0
                candidate_by_code = candidates.set_index("ts_code", drop=False) if not candidates.empty else pd.DataFrame()
                allow_adds = not (repair_override and not case.allow_bear_repair_add_buy)
                if allow_adds and not candidates.empty:
                    for code in list(holdings):
                        if code in risk_exit_codes or code not in candidate_by_code.index or code not in day_panel.index:
                            continue
                        pos = holdings[code]
                        if pos.get("pending_sell") or not v6.can_add_position(code, pos, signal_panel):
                            continue
                        target_amount = v6.next_position_step(pos)
                        if target_amount is None:
                            continue
                        max_exposure = v6.LONG_MAX_TOTAL_EXPOSURE
                        if repair_override:
                            max_exposure = min(max_exposure, v6.INIT_CASH * case.bear_repair_max_exposure)
                        available_exposure = max_exposure - v6.calc_total_exposure(holdings)
                        target_amount = min(target_amount, available_exposure)
                        if target_amount < 100:
                            continue
                        cash, bought, _ = v6.execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, "long_add_buy")
                        if bought:
                            bought_count += 1
                            stats["buy_fills"] += 1
                            stats["add_buy_fills"] += 1
                        else:
                            stats["buy_skips"] += 1

                pullback_threshold, strong_pullback_threshold = v6.regime_pullback_thresholds(market_regime_name)
                if repair_override:
                    pullback_threshold = v6.REGIME_NEUTRAL_PULLBACK_THRESHOLD
                    strong_pullback_threshold = v6.REGIME_STRONG_TREND_PULLBACK_THRESHOLD
                elif case.bull_accel_relax and bull_accel:
                    pullback_threshold = min(pullback_threshold + 0.02, -0.02)
                    strong_pullback_threshold = min(strong_pullback_threshold + 0.01, -0.015)
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
                ].copy()
                if repair_override:
                    entry_candidates = entry_candidates[entry_candidates["strong_trend"].fillna(False)].copy()

                target_codes = list(entry_candidates["ts_code"].head(v6.KEEP_TOP_N))
                for code in target_codes:
                    max_holdings = v6.LONG_MAX_HOLDINGS
                    max_exposure = v6.LONG_MAX_TOTAL_EXPOSURE
                    reason = "long_initial_buy"
                    if repair_override:
                        max_holdings = case.bear_repair_max_holdings
                        max_exposure = min(max_exposure, v6.INIT_CASH * case.bear_repair_max_exposure)
                        reason = "long_bear_repair_buy"
                    if len(holdings) >= max_holdings:
                        break
                    if code in holdings or code in risk_exit_codes or code not in day_panel.index:
                        continue
                    available_exposure = max_exposure - v6.calc_total_exposure(holdings)
                    target_amount = min(float(v6.LONG_POSITION_STEPS[0]), available_exposure)
                    if target_amount < 100:
                        break
                    cash, bought, _ = v6.execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, reason)
                    if bought:
                        bought_count += 1
                        stats["buy_fills"] += 1
                        if repair_override:
                            stats["bear_repair_buy_fills"] += 1
                    else:
                        stats["buy_skips"] += 1
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": "bear_repair_override" if repair_override else short_drop_reason,
                    "market_regime": market_regime_name,
                    "bear_repair": bear_repair,
                    "bull_accel": bull_accel,
                    "candidate_count": int(len(candidates)),
                    "entry_candidate_count": int(len(entry_candidates)),
                    "bought_count": int(bought_count),
                    "market_dd_252": round(regime_snapshot.get("market_dd_252", float("nan")), 4),
                    "breadth_above_bbi": round(regime_snapshot.get("breadth_above_bbi", float("nan")), 4),
                    "pullback_threshold": round(pullback_threshold, 4),
                    "strong_pullback_threshold": round(strong_pullback_threshold, 4),
                    "cash": round(cash, 2),
                })
            previous_market_regime_name = market_regime_name

        nav = cash + sum(v6.mark_position(c, p, day_panel) for c, p in holdings.items())
        nav_rows.append({"date": str(date)[:10], "nav": round(nav, 2), "cash": round(cash, 2), "holdings": len(holdings)})

    nav_df = pd.DataFrame(nav_rows)
    total_ret = nav_df["nav"].iloc[-1] / v6.INIT_CASH - 1.0
    days = max((pd.Timestamp(nav_df["date"].iloc[-1]) - pd.Timestamp(nav_df["date"].iloc[0])).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    max_dd = v6.calc_max_drawdown(nav_df)
    stats.update({
        "case": case.name,
        "description": case.description,
        "start_date": str(nav_df["date"].iloc[0]),
        "end_date": str(nav_df["date"].iloc[-1]),
        "init_cash": v6.INIT_CASH,
        "final_nav": float(nav_df["nav"].iloc[-1]),
        "total_return_pct": round(total_ret * 100.0, 4),
        "annual_return_pct": round(annual_ret * 100.0, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "calmar_ratio": round((annual_ret * 100.0) / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "trade_records": len(trades),
    })
    return nav_df, pd.DataFrame(trades), pd.DataFrame(rebalance_log), pd.DataFrame(score_rows), stats


def load_v6_data():
    panel = pd.read_parquet(V6_DIR / "output" / "panel.parquet")
    market = pd.read_parquet(V6_DIR / "output" / "market_index.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    return panel, market


def load_summary(label, directory):
    path = directory / "output" / "summary.json"
    if not path.exists():
        return {"case": label, "missing": True}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["case"] = label
    data["description"] = f"Official {label} output"
    return data


def period_returns(nav_df, freq):
    nav = nav_df.copy()
    nav["date"] = pd.to_datetime(nav["date"])
    nav["period"] = nav["date"].dt.to_period(freq).astype(str)
    grouped = nav.groupby("period")["nav"].agg(["first", "last"])
    return ((grouped["last"] / grouped["first"] - 1.0) * 100.0).round(2)


def write_outputs(results, navs, trades, rebalances, scores):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    for name, df in navs.items():
        df.to_csv(OUTPUT_DIR / f"{name}_nav.csv", index=False)
    for name, df in trades.items():
        df.to_csv(OUTPUT_DIR / f"{name}_trades.csv", index=False)
    for name, df in rebalances.items():
        df.to_csv(OUTPUT_DIR / f"{name}_rebalance.csv", index=False)
    for name, df in scores.items():
        df.to_csv(OUTPUT_DIR / f"{name}_scores.csv", index=False)


def render_report(results, navs):
    result_df = pd.DataFrame(results)
    baseline = result_df[result_df["case"] == "v6_official"].iloc[0]
    best = result_df[~result_df["case"].isin(["v4_official", "v5_official", "v6_official"])].sort_values(
        ["total_return_pct", "calmar_ratio"], ascending=[False, False]
    ).head(1)
    best_case = best.iloc[0] if not best.empty else baseline
    dd_worse = float(best_case["max_drawdown_pct"]) < float(baseline["max_drawdown_pct"]) - 5.0
    total_lift = float(best_case["total_return_pct"]) - float(baseline["total_return_pct"])
    annual_lift = float(best_case["annual_return_pct"]) - float(baseline["annual_return_pct"])
    bear_repair_fills = float(best_case.get("bear_repair_buy_fills", 0) or 0)
    recommend = (
        "暂不合并，收益提升不足或回撤代价过大。"
        if total_lift < 2.0 or annual_lift < 0.2 or dd_worse
        else "建议进入下一轮小心合并评审：实验版收益提升达到阈值，且回撤没有超过 5 个百分点的额外恶化。"
    )
    if bear_repair_fills <= 0:
        recommend = "暂不合并。主假设“熊市修复买点”没有产生实际买入；最佳结果只来自极端加速过滤的很小改善，需要下一轮重设熊市修复入场条件。"

    annual = pd.DataFrame({name: period_returns(df, "Y") for name, df in navs.items()}).fillna("")
    monthly = pd.DataFrame({name: period_returns(df, "M") for name, df in navs.items()}).fillna("")
    recent_monthly = monthly.tail(36)

    def table(df):
        return df.to_html(index=True, border=0, classes="tbl", escape=True)

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>tmp_v3 slope regime repair report</title>
<style>
body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; margin: 24px; color: #222; }}
h1 {{ font-size: 24px; }}
h2 {{ margin-top: 28px; font-size: 18px; }}
.note {{ padding: 12px; background: #f4f6f8; border-left: 4px solid #4472c4; margin: 12px 0; }}
.bad {{ border-left-color: #c44; }}
table.tbl {{ border-collapse: collapse; font-size: 13px; width: 100%; }}
.tbl th, .tbl td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
.tbl th:first-child, .tbl td:first-child {{ text-align: left; }}
.src li {{ margin: 6px 0; }}
</style>
</head>
<body>
<h1>v6 斜率/熊市修复实验报告</h1>
<div class="note"><b>结论：</b>{escape(recommend)}</div>
<p>最佳实验：{escape(str(best_case['case']))}。总收益 {best_case['total_return_pct']}%，年化 {best_case['annual_return_pct']}%，最大回撤 {best_case['max_drawdown_pct']}%。v6 基线总收益 {baseline['total_return_pct']}%，最大回撤 {baseline['max_drawdown_pct']}%。收益提升 {total_lift:.4f} 个百分点，年化提升 {annual_lift:.4f} 个百分点。</p>
<h2>汇总对比</h2>
{result_df[['case','description','final_nav','total_return_pct','annual_return_pct','max_drawdown_pct','calmar_ratio','trade_records','bear_repair_days','bear_repair_buy_fills','blowoff_candidate_blocks']].fillna('').to_html(index=False, border=0, classes='tbl', escape=True)}
<h2>年度收益差异</h2>
{table(annual)}
<h2>最近 36 个月月度收益</h2>
{table(recent_monthly)}
<h2>研究来源</h2>
<ul class="src">
{''.join(f"<li><a href='{escape(s['url'])}'>{escape(s['topic'])}</a>：{escape(s['note'])}</li>" for s in SOURCE_NOTES)}
</ul>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")
    README_PATH.write_text(
        "# tmp_v3_slope_regime_repair\n\n"
        "目的：验证 v6 在熊市修复和斜率加速条件下是否可以提高收益。\n\n"
        f"最佳实验：{best_case['case']}\n\n"
        f"合并建议：{recommend}\n\n"
        f"报告：{REPORT_PATH}\n",
        encoding="utf-8",
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    panel, market = load_v6_data()
    summaries = [
        load_summary("v4_official", V4_DIR),
        load_summary("v5_official", V5_DIR),
        load_summary("v6_official", V6_DIR),
    ]
    navs = {}
    for label, directory in [("v4_official", V4_DIR), ("v5_official", V5_DIR), ("v6_official", V6_DIR)]:
        nav_path = directory / "output" / "nav_series.csv"
        if nav_path.exists():
            navs[label] = pd.read_csv(nav_path)

    trades = {}
    rebalances = {}
    scores = {}
    results = summaries.copy()
    for case in CASES:
        nav_df, trades_df, rebalance_df, scores_df, stats = run_case(
            case,
            panel,
            market,
            start_date="2018-01-01",
            end_date=None,
        )
        results.append(stats)
        navs[case.name] = nav_df
        trades[case.name] = trades_df
        rebalances[case.name] = rebalance_df
        scores[case.name] = scores_df
        print(
            f"{case.name}: total={stats['total_return_pct']:.2f}% "
            f"annual={stats['annual_return_pct']:.2f}% dd={stats['max_drawdown_pct']:.2f}% "
            f"trades={stats['trade_records']}"
        )
    write_outputs(results, navs, trades, rebalances, scores)
    render_report(results, navs)
    print(f"Report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()

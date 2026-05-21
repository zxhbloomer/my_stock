from __future__ import annotations

import html
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V6_DIR = BACKTRADER_DIR / "v6"
V7_DIR = BACKTRADER_DIR / "v7"
OUTPUT_DIR = TMP_DIR / "tmp_v7_extreme_risk_off_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_extreme_risk_off_README.md"

START_DATE = "2018-01-01"
END_DATE = None


HELPER_SOURCE = r'''
BEAR_GATE_ENABLED = True
BEAR_GATE_PROBE_MIN_EXPOSURE = 0.2
BEAR_GATE_MIN_RISK_POINTS = 5
BEAR_GATE_USE_DD20 = True
BEAR_GATE_USE_BREADTH_CRASH = True


def bear_gate_number(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(result):
        return default
    return result


def bear_gate_int(value, default=0):
    number = bear_gate_number(value, default)
    if pd.isna(number):
        return default
    return int(number)


def bear_gate_risk_points(row):
    points = 0
    if bear_gate_int(row.get("close_below_ma120"), 0) == 1:
        points += 1
    if bear_gate_number(row.get("ma60_slope_20"), 0.0) < 0:
        points += 1
    dd = bear_gate_number(row.get("market_drawdown_120"), 0.0)
    if dd <= -0.10:
        points += 1
    if dd <= -0.15:
        points += 1
    if bear_gate_number(row.get("breadth_above_ma20"), 0.0) < 0.35:
        points += 1
    if bear_gate_number(row.get("breadth_above_ma60"), 0.0) < 0.30:
        points += 1
    return points


def bear_gate_base_target_exposure(row):
    dd = bear_gate_number(row.get("market_drawdown_120"), 0.0)
    b20 = bear_gate_number(row.get("breadth_above_ma20"), 0.5)
    b60 = bear_gate_number(row.get("breadth_above_ma60"), 0.5)
    below120 = bear_gate_int(row.get("close_below_ma120"), 0)
    below200 = bear_gate_int(row.get("close_below_ma200"), 0)
    risk_points = bear_gate_risk_points(row)
    dd20_risk = BEAR_GATE_USE_DD20 and dd <= -0.20
    breadth_crash = BEAR_GATE_USE_BREADTH_CRASH and (
        (below120 == 1 and b20 < 0.25)
        or (below200 == 1 and b60 < 0.25)
    )
    if dd20_risk or breadth_crash or risk_points >= BEAR_GATE_MIN_RISK_POINTS:
        return 0.0
    return 1.0


def apply_bear_gate_hysteresis(regime_frame):
    out = regime_frame.copy().sort_values("trade_date").reset_index(drop=True)
    out["target_exposure"] = pd.to_numeric(out["base_target_exposure"], errors="coerce").fillna(1.0).clip(0.0, 1.0)
    out["risk_points"] = out.apply(bear_gate_risk_points, axis=1)
    return out


def build_bear_gate_regime(market, panel):
    if not BEAR_GATE_ENABLED or market is None:
        return None
    regime = market.copy().sort_index()
    if "trade_date" in regime.columns:
        regime["trade_date"] = pd.to_datetime(regime["trade_date"])
        regime = regime.sort_values("trade_date").set_index("trade_date", drop=False)
    else:
        regime["trade_date"] = pd.to_datetime(regime.index)
    close = pd.to_numeric(regime["close"], errors="coerce")
    regime["ma20"] = close.rolling(20, min_periods=15).mean()
    regime["ma60"] = close.rolling(60, min_periods=40).mean()
    regime["ma120"] = close.rolling(120, min_periods=80).mean()
    regime["ma200"] = close.rolling(200, min_periods=120).mean()
    regime["ma60_slope_20"] = regime["ma60"] / regime["ma60"].shift(20) - 1.0
    regime["market_drawdown_120"] = close / close.rolling(120, min_periods=60).max() - 1.0
    regime["close_below_ma120"] = (close < regime["ma120"]).astype(int)
    regime["close_below_ma200"] = (close < regime["ma200"]).astype(int)
    regime["ma20_above_ma60"] = (regime["ma20"] > regime["ma60"]).astype(int)

    breadth = panel[["trade_date", "ts_code", "is_eligible", "close_qfq"]].copy()
    breadth = breadth[breadth["is_eligible"].fillna(False)].sort_values(["ts_code", "trade_date"])
    grouped = breadth.groupby("ts_code", sort=False)
    breadth["ma20_stock"] = grouped["close_qfq"].transform(lambda s: s.rolling(20, min_periods=15).mean())
    breadth["ma60_stock"] = grouped["close_qfq"].transform(lambda s: s.rolling(60, min_periods=40).mean())
    close_qfq = pd.to_numeric(breadth["close_qfq"], errors="coerce")
    breadth["above_ma20"] = (close_qfq > pd.to_numeric(breadth["ma20_stock"], errors="coerce")).astype(float)
    breadth["above_ma60"] = (close_qfq > pd.to_numeric(breadth["ma60_stock"], errors="coerce")).astype(float)
    breadth_daily = breadth.groupby("trade_date", sort=True).agg(
        breadth_above_ma20=("above_ma20", "mean"),
        breadth_above_ma60=("above_ma60", "mean"),
    )
    regime = regime.join(breadth_daily, how="left")
    regime["breadth_above_ma20"] = regime["breadth_above_ma20"].fillna(0.0)
    regime["breadth_above_ma60"] = regime["breadth_above_ma60"].fillna(0.0)
    regime["base_target_exposure"] = regime.apply(bear_gate_base_target_exposure, axis=1)
    regime = apply_bear_gate_hysteresis(regime.reset_index(drop=True))
    return regime.set_index("trade_date", drop=False)


def get_bear_gate_snapshot(bear_gate_regime, signal_date):
    if not BEAR_GATE_ENABLED or bear_gate_regime is None or signal_date not in bear_gate_regime.index:
        return {
            "target_exposure": 1.0,
            "base_target_exposure": 1.0,
            "risk_points": 0,
        }
    row = bear_gate_regime.loc[signal_date]
    return {
        "target_exposure": bear_gate_number(row.get("target_exposure"), 1.0),
        "base_target_exposure": bear_gate_number(row.get("base_target_exposure"), 1.0),
        "risk_points": bear_gate_int(row.get("risk_points"), 0),
        "market_drawdown_120": bear_gate_number(row.get("market_drawdown_120"), float("nan")),
        "breadth_above_ma20": bear_gate_number(row.get("breadth_above_ma20"), float("nan")),
        "breadth_above_ma60": bear_gate_number(row.get("breadth_above_ma60"), float("nan")),
    }
'''


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def load_v7_module(module_name: str, bear_gate_mode: str):
    sys.path.insert(0, str(V7_DIR))
    old_config = sys.modules.get("config")
    config_spec = importlib.util.spec_from_file_location("config", V7_DIR / "config.py")
    config_mod = importlib.util.module_from_spec(config_spec)
    assert config_spec.loader is not None
    config_spec.loader.exec_module(config_mod)
    sys.modules["config"] = config_mod
    try:
        source = (V7_DIR / "20_run_backtest.py").read_text(encoding="utf-8")
        if bear_gate_mode != "off":
            source = inject_bear_gate(source)
            source = source.replace(
                """            if bear_gate_active and bear_gate_target >= 1.0:
                regime_blocked = False
                stats["bear_gate_full_recovery_days"] += 1
""",
                """            if False:
                regime_blocked = False
                stats["bear_gate_full_recovery_days"] += 1
""",
            )
            if bear_gate_mode == "risk6":
                source = source.replace("BEAR_GATE_MIN_RISK_POINTS = 5", "BEAR_GATE_MIN_RISK_POINTS = 6")
            elif bear_gate_mode == "dd20_only":
                source = source.replace("BEAR_GATE_MIN_RISK_POINTS = 5", "BEAR_GATE_MIN_RISK_POINTS = 99")
                source = source.replace("BEAR_GATE_USE_BREADTH_CRASH = True", "BEAR_GATE_USE_BREADTH_CRASH = False")
            elif bear_gate_mode == "breadth_crash_only":
                source = source.replace("BEAR_GATE_MIN_RISK_POINTS = 5", "BEAR_GATE_MIN_RISK_POINTS = 99")
                source = source.replace("BEAR_GATE_USE_DD20 = True", "BEAR_GATE_USE_DD20 = False")
            elif bear_gate_mode == "probe_block_only":
                source = source.replace("BEAR_GATE_MIN_RISK_POINTS = 5", "BEAR_GATE_MIN_RISK_POINTS = 99")
                source = source.replace("BEAR_GATE_USE_BREADTH_CRASH = True", "BEAR_GATE_USE_BREADTH_CRASH = False")
                source = source.replace(
                    """                    and market_regime_name == "bear"
                    and bear_gate_target <= 0.0
                ):
                    exit_reasons[code] = "bear_gate_risk_off_exit"
                    stats["bear_gate_risk_off_exit_signals"] += 1
                elif code in reduce_codes:
""",
                    """                    and False
                    and bear_gate_target <= 0.0
                ):
                    exit_reasons[code] = "bear_gate_risk_off_exit"
                    stats["bear_gate_risk_off_exit_signals"] += 1
                elif code in reduce_codes:
""",
                )
        module = types.ModuleType(module_name)
        module.__file__ = str(V7_DIR / "20_run_backtest.py")
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        return module
    finally:
        sys.path.pop(0)
        if old_config is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = old_config


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"Patch anchor not found:\n{old}")
    return source.replace(old, new, 1)


def inject_bear_gate(source: str) -> str:
    source = replace_once(source, "\ndef regime_pullback_thresholds(market_regime_name):", HELPER_SOURCE + "\n\ndef regime_pullback_thresholds(market_regime_name):")
    source = replace_once(
        source,
        "    market_regime = build_market_regime(market, panel)\n",
        "    market_regime = build_market_regime(market, panel)\n    bear_gate_regime = build_bear_gate_regime(market, panel)\n",
    )
    source = replace_once(
        source,
        '        "bear_probe_buys": 0,\n',
        '        "bear_probe_buys": 0,\n        "bear_gate_enabled": bool(BEAR_GATE_ENABLED),\n        "bear_gate_risk_off_days": 0,\n        "bear_gate_reduce_exit_signals": 0,\n        "bear_gate_reduce_exit_fills": 0,\n        "bear_gate_risk_off_exit_signals": 0,\n        "bear_gate_risk_off_exit_fills": 0,\n        "bear_gate_probe_days": 0,\n        "bear_gate_full_recovery_days": 0,\n',
    )
    source = replace_once(
        source,
        "            market_regime_name, regime_snapshot = get_market_regime(market_regime, signal_date)\n            exit_reasons = {}\n            for code in list(holdings):\n",
        """            market_regime_name, regime_snapshot = get_market_regime(market_regime, signal_date)
            bear_gate_snapshot = get_bear_gate_snapshot(bear_gate_regime, signal_date)
            bear_gate_target = float(bear_gate_snapshot.get("target_exposure", 1.0))
            exit_reasons = {}
            profit_by_code = {}
            for code in list(holdings):
                if not holdings[code].get("pending_sell"):
                    profit_by_code[code] = calc_position_profit_pct(code, holdings[code], signal_panel)
            reduce_codes = set()
            if (
                BEAR_GATE_ENABLED
                and MARKET_REGIME_FILTER_ENABLED
                and market_regime_name == "bear"
                and 0.0 < bear_gate_target < 1.0
            ):
                target_exposure_amount = INIT_CASH * bear_gate_target
                projected_exposure = calc_total_exposure(holdings)
                ranked_codes = sorted(
                    [code for code in holdings if not holdings[code].get("pending_sell")],
                    key=lambda code: -1e9 if profit_by_code.get(code) is None else float(profit_by_code[code]),
                )
                for code in ranked_codes:
                    if projected_exposure <= target_exposure_amount:
                        break
                    reduce_codes.add(code)
                    projected_exposure -= float(holdings[code].get("invested_amount", calc_position_cost(holdings[code])))
            for code in list(holdings):
""",
    )
    source = replace_once(
        source,
        "                profit_pct = calc_position_profit_pct(code, pos, signal_panel)\n                if (\n                    MARKET_REGIME_FILTER_ENABLED\n",
        """                profit_pct = profit_by_code.get(code)
                if (
                    BEAR_GATE_ENABLED
                    and MARKET_REGIME_FILTER_ENABLED
                    and market_regime_name == "bear"
                    and bear_gate_target <= 0.0
                ):
                    exit_reasons[code] = "bear_gate_risk_off_exit"
                    stats["bear_gate_risk_off_exit_signals"] += 1
                elif code in reduce_codes:
                    exit_reasons[code] = "bear_gate_reduce_exit"
                    stats["bear_gate_reduce_exit_signals"] += 1
                elif (
                    MARKET_REGIME_FILTER_ENABLED
""",
    )
    source = replace_once(
        source,
        '                    elif exit_reason == "long_regime_bear_exit":\n                        stats["regime_bear_exit_fills"] += 1\n',
        '                    elif exit_reason == "long_regime_bear_exit":\n                        stats["regime_bear_exit_fills"] += 1\n                    elif exit_reason == "bear_gate_risk_off_exit":\n                        stats["bear_gate_risk_off_exit_fills"] += 1\n                    elif exit_reason == "bear_gate_reduce_exit":\n                        stats["bear_gate_reduce_exit_fills"] += 1\n',
    )
    source = replace_once(
        source,
        "            regime_blocked = MARKET_REGIME_FILTER_ENABLED and market_regime_name == \"bear\"\n            if regime_blocked:\n                stats[\"regime_bear_block_days\"] += 1\n            probe_open = (\n                BEAR_PROBE_BUY_ENABLED\n                and regime_blocked\n                and not short_drop_blocked\n                and bool(regime_snapshot.get(\"bear_probe_market_ok\", False))\n            )\n",
        """            regime_blocked = MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
            bear_gate_snapshot = get_bear_gate_snapshot(bear_gate_regime, signal_date)
            bear_gate_target = float(bear_gate_snapshot.get("target_exposure", 1.0))
            bear_gate_active = BEAR_GATE_ENABLED and regime_blocked
            if bear_gate_active and bear_gate_target >= 1.0:
                regime_blocked = False
                stats["bear_gate_full_recovery_days"] += 1
            if regime_blocked:
                stats["regime_bear_block_days"] += 1
                if bear_gate_active and bear_gate_target <= 0.0:
                    stats["bear_gate_risk_off_days"] += 1
                elif bear_gate_active and bear_gate_target >= BEAR_GATE_PROBE_MIN_EXPOSURE:
                    stats["bear_gate_probe_days"] += 1
            probe_open = (
                BEAR_PROBE_BUY_ENABLED
                and regime_blocked
                and not short_drop_blocked
                and bool(regime_snapshot.get("bear_probe_market_ok", False))
                and (not bear_gate_active or bear_gate_target >= BEAR_GATE_PROBE_MIN_EXPOSURE)
            )
""",
    )
    source = source.replace(
        '                    "bear_probe_market_ok": bool(regime_snapshot.get("bear_probe_market_ok", False)),\n                    "cash": round(cash, 2),\n',
        '                    "bear_probe_market_ok": bool(regime_snapshot.get("bear_probe_market_ok", False)),\n                    "bear_gate_target_exposure": round(bear_gate_target, 4),\n                    "bear_gate_base_target_exposure": round(bear_gate_snapshot.get("base_target_exposure", float("nan")), 4),\n                    "bear_gate_risk_points": bear_gate_snapshot.get("risk_points", float("nan")),\n                    "cash": round(cash, 2),\n',
    )
    source = replace_once(
        source,
        "                    if probe_open:\n                        target_amount = calc_bear_probe_target_amount(\n                            float(LONG_POSITION_STEPS[0]),\n                            cash,\n                            calc_bear_probe_exposure(holdings),\n                        )\n                    else:\n",
        """                    if probe_open:
                        target_amount = calc_bear_probe_target_amount(
                            float(LONG_POSITION_STEPS[0]),
                            cash,
                            calc_bear_probe_exposure(holdings),
                        )
                        if bear_gate_active:
                            bear_gate_capacity = max(0.0, INIT_CASH * bear_gate_target - calc_total_exposure(holdings))
                            target_amount = min(target_amount, bear_gate_capacity)
                    else:
""",
    )
    return source


def max_drawdown(nav: pd.Series) -> float:
    values = pd.to_numeric(nav, errors="coerce").dropna()
    if values.empty:
        return 0.0
    return float((values / values.cummax() - 1.0).min() * 100.0)


def annual_return(start_nav: float, end_nav: float, days: int) -> float:
    if start_nav <= 0 or end_nav <= 0 or days <= 0:
        return 0.0
    return float(((end_nav / start_nav) ** (365.25 / days) - 1.0) * 100.0)


def summarize_nav(name: str, nav: pd.DataFrame, trades: pd.DataFrame, stats: dict | None = None) -> dict:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
    start_nav = float(data.iloc[0]["nav"])
    end_nav = float(data.iloc[-1]["nav"])
    days = max((data.iloc[-1]["date"] - data.iloc[0]["date"]).days, 1)
    row = {
        "strategy": name,
        "start_date": str(data.iloc[0]["date"].date()),
        "end_date": str(data.iloc[-1]["date"].date()),
        "start_nav": round(start_nav, 2),
        "end_nav": round(end_nav, 2),
        "return_pct": round((end_nav / start_nav - 1.0) * 100.0, 4),
        "annual_pct": round(annual_return(start_nav, end_nav, days), 4),
        "max_dd_pct": round(max_drawdown(data["nav"]), 4),
        "trade_records": int(len(trades)),
    }
    if not trades.empty and "action" in trades.columns:
        row["buy_trades"] = int(trades["action"].eq("buy").sum())
        row["sell_trades"] = int(trades["action"].eq("sell").sum())
    if stats:
        for key in [
            "regime_bear_block_days",
            "bear_probe_signal_days",
            "bear_probe_buys",
            "bear_gate_risk_off_days",
            "bear_gate_probe_days",
            "bear_gate_full_recovery_days",
            "bear_gate_risk_off_exit_fills",
            "bear_gate_reduce_exit_fills",
        ]:
            if key in stats:
                row[key] = stats[key]
    return row


def period_returns(nav_map: dict[str, pd.DataFrame], freq: str) -> pd.DataFrame:
    rows = []
    for name, nav in nav_map.items():
        data = nav.copy()
        data["date"] = pd.to_datetime(data["date"])
        data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
        data["period"] = data["date"].dt.strftime("%Y" if freq == "Y" else "%Y-%m")
        prev_nav = None
        for period, group in data.groupby("period", sort=True):
            start_nav = float(group.iloc[0]["nav"]) if prev_nav is None else prev_nav
            end_nav = float(group.iloc[-1]["nav"])
            prev_nav = end_nav
            rows.append(
                {
                    "period": period,
                    "strategy": name,
                    "return_pct": round((end_nav / start_nav - 1.0) * 100.0, 2),
                    "end_nav": round(end_nav, 2),
                }
            )
    return pd.DataFrame(rows)


def reason_counts(trade_map: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, trades in trade_map.items():
        if trades.empty or "reason" not in trades.columns:
            continue
        for reason, count in trades["reason"].value_counts().items():
            rows.append({"strategy": name, "reason": reason, "count": int(count)})
    return pd.DataFrame(rows)


def table_html(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>无数据</p>"
    return df.to_html(index=False, escape=True)


def write_report(results: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame, reasons: pd.DataFrame) -> None:
    yearly_view = yearly.pivot(index="period", columns="strategy", values="return_pct").reset_index()
    monthly_view = monthly.pivot(index="period", columns="strategy", values="return_pct").reset_index()
    conclusion = "待人工复核"
    if "v7_extreme_risk5" in set(results["strategy"]) and "v7_baseline" in set(results["strategy"]):
        gate = results.set_index("strategy").loc["v7_extreme_risk5"]
        base = results.set_index("strategy").loc["v7_baseline"]
        if gate["return_pct"] > base["return_pct"] and gate["max_dd_pct"] >= base["max_dd_pct"]:
            conclusion = "候选可继续推进：收益高于 v7_baseline，且最大回撤没有变差。"
        else:
            conclusion = "暂不建议合入：收益或最大回撤没有同时优于 v7_baseline。"
    text = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>v7 极端熊市保险丝实验</title>
<style>
body{{font-family:Arial,'Microsoft YaHei',sans-serif;margin:20px;background:#f6f8fb;color:#222}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:24px}}
table{{border-collapse:collapse;background:#fff;width:100%;font-size:13px}}
th,td{{border:1px solid #d8dee9;padding:6px 8px;text-align:right}}
th:first-child,td:first-child,td:nth-child(2){{text-align:left}}
.note{{background:#fff;border:1px solid #d8dee9;padding:10px 12px;line-height:1.7}}
.scroll{{overflow:auto;max-height:520px;border:1px solid #d8dee9}}
</style></head><body>
<h1>v7 极端熊市保险丝实验</h1>
<div class="note">
<b>策略：</b>保住 v6/v7 牛市收益，只在 v7 已判熊且风险极端时触发清仓/禁买。非极端熊市仍保持 v7 原本熊市阻断和严格 bear_probe。<br>
<b>执行：</b>risk5 表示风险分数 >=5 或 120日回撤 <=-20% 或广度崩塌；risk6 更严格；dd20_only 只看 120日回撤；breadth_crash_only 只看均线下破+广度崩塌。<br>
<b>反前视：</b>交易日 T 使用 T-1 signal_date 的 regime 和 risk_off 信号。<br>
<b>结论：</b>{html.escape(conclusion)}
</div>
<h2>总体结果</h2>{table_html(results)}
<h2>年度收益率</h2>{table_html(yearly_view)}
<h2>月度收益率</h2><div class="scroll">{table_html(monthly_view)}</div>
<h2>交易原因统计</h2>{table_html(reasons)}
</body></html>"""
    REPORT_PATH.write_text(text, encoding="utf-8")


def run_case(name: str, bear_gate_mode: str, panel: pd.DataFrame, market: pd.DataFrame, end_date: str):
    module = load_v7_module(f"tmp_{name}", bear_gate_mode=bear_gate_mode)
    nav, trades, rebalance, scores, holdings, stats = module.run_backtest(panel.copy(), market.copy(), START_DATE, end_date)
    nav.to_csv(OUTPUT_DIR / f"{name}_nav_series.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(OUTPUT_DIR / f"{name}_trade_records.csv", index=False, encoding="utf-8-sig")
    rebalance.to_csv(OUTPUT_DIR / f"{name}_rebalance_log.csv", index=False, encoding="utf-8-sig")
    (OUTPUT_DIR / f"{name}_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return nav, trades, rebalance, stats


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text(
        "# tmp_v7 极端熊市保险丝实验进度\n\n"
        "目标：不改 v7 正式代码，只在 v7 判熊且风险极端时清仓/禁买，验证能否保住 v6 牛市收益并减少熊市亏损。\n\n"
        "设计 review：量化风控专家建议不要再用 20/50/100 阶梯仓位，因为上一轮全周期显著拖累牛市；本轮只测极端 risk_off。\n"
        "开发 review：数据 QA 要求交易日 T 只能使用 T-1 signal_date 的 risk_off 信号；脚本通过动态加载 v7 内存副本实现，不修改 v7 正式代码。\n\n",
        encoding="utf-8",
    )
    append_progress("开始：加载 v7 本地 panel/market 数据。")
    panel = pd.read_parquet(V7_DIR / "output" / "panel.parquet")
    market = pd.read_parquet(V7_DIR / "output" / "market_index.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")
    end_date = str(pd.to_datetime(panel["trade_date"]).max().date()) if END_DATE is None else END_DATE
    append_progress(f"数据完成：panel_rows={len(panel)} market_rows={len(market)} end={end_date}。")

    nav_map: dict[str, pd.DataFrame] = {}
    trade_map: dict[str, pd.DataFrame] = {}
    rows = []

    for baseline in ["v4", "v5", "v6", "v7"]:
        append_progress(f"读取 {baseline} 输出基线。")
        base_dir = BACKTRADER_DIR / baseline / "output"
        base_nav = pd.read_csv(base_dir / "nav_series.csv")
        base_trades = pd.read_csv(base_dir / "trade_records.csv")
        name = f"{baseline}_output"
        rows.append(summarize_nav(name, base_nav, base_trades))
        nav_map[name] = base_nav
        trade_map[name] = base_trades

    append_progress("运行 case=v7_baseline。")
    nav, trades, _, stats = run_case("v7_baseline", "off", panel, market, end_date)
    rows.append(summarize_nav("v7_baseline", nav, trades, stats))
    nav_map["v7_baseline"] = nav
    trade_map["v7_baseline"] = trades

    for case_name, mode in [
        ("v7_extreme_risk5", "risk5"),
        ("v7_extreme_risk6", "risk6"),
        ("v7_extreme_dd20_only", "dd20_only"),
        ("v7_extreme_breadth_crash_only", "breadth_crash_only"),
        ("v7_extreme_probe_block_only", "probe_block_only"),
    ]:
        append_progress(f"运行 case={case_name}。")
        nav, trades, _, stats = run_case(case_name, mode, panel, market, end_date)
        rows.append(summarize_nav(case_name, nav, trades, stats))
        nav_map[case_name] = nav
        trade_map[case_name] = trades

    results = pd.DataFrame(rows)
    yearly = period_returns(nav_map, "Y")
    monthly = period_returns(nav_map, "M")
    reasons = reason_counts(trade_map)
    results.to_csv(OUTPUT_DIR / "results.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "monthly.csv", index=False, encoding="utf-8-sig")
    reasons.to_csv(OUTPUT_DIR / "reasons.csv", index=False, encoding="utf-8-sig")
    write_report(results, yearly, monthly, reasons)
    append_progress(f"完成：报告 {REPORT_PATH}")
    try:
        subprocess.Popen(["cmd", "/c", "start", "", str(REPORT_PATH)], shell=False)
    except Exception as exc:
        append_progress(f"自动打开失败：{exc}")
    print(f"report={REPORT_PATH}")
    print(results.to_string(index=False))


if __name__ == "__main__":
    main()

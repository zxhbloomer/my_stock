from __future__ import annotations

import html
import importlib.util
import json
import sys
import types
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V7_DIR = BACKTRADER_DIR / "v7"
OUTPUT_DIR = TMP_DIR / "v7_strict_bear_probe_2022_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
MONTHLY_PATH = OUTPUT_DIR / "monthly.csv"
YEARLY_PATH = OUTPUT_DIR / "yearly.csv"


STRICT_SEARCH = """probe_open = (
                    BEAR_PROBE_BUY_ENABLED
                    and not short_drop_blocked
                    and bear_overlay_target >= BEAR_OVERLAY_PROBE_MIN_EXPOSURE
                )"""

STRICT_REPLACE = """probe_open = (
                    BEAR_PROBE_BUY_ENABLED
                    and not short_drop_blocked
                    and bear_overlay_target >= BEAR_OVERLAY_PROBE_MIN_EXPOSURE
                    and bool(regime_snapshot.get("bear_probe_market_ok", False))
                )"""


GATE_SEARCH = """regime_blocked = MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
            bear_overlay_snapshot = get_bear_overlay_snapshot(bear_overlay_regime, signal_date)
            bear_overlay_target = float(bear_overlay_snapshot.get("target_exposure", 1.0))"""

GATE_REPLACE = """bear_overlay_snapshot = get_bear_overlay_snapshot(bear_overlay_regime, signal_date)
            bear_overlay_target = float(bear_overlay_snapshot.get("target_exposure", 1.0))
            regime_blocked = (
                (MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear")
                or (BEAR_OVERLAY_ENABLED and bear_overlay_target < 1.0)
            )"""


def load_v7_module(name: str, strict_probe: bool, overlay_gate: bool = False):
    sys.path.insert(0, str(V7_DIR))
    config_spec = importlib.util.spec_from_file_location("config", V7_DIR / "config.py")
    config_mod = importlib.util.module_from_spec(config_spec)
    assert config_spec.loader is not None
    config_spec.loader.exec_module(config_mod)
    old_config = sys.modules.get("config")
    sys.modules["config"] = config_mod
    try:
        source = (V7_DIR / "20_run_backtest.py").read_text(encoding="utf-8")
        if strict_probe:
            if STRICT_SEARCH not in source:
                raise RuntimeError("Cannot find current v7 bear overlay probe condition to patch.")
            source = source.replace(STRICT_SEARCH, STRICT_REPLACE)
        if overlay_gate:
            if GATE_SEARCH not in source:
                raise RuntimeError("Cannot find current v7 regime gate block to patch.")
            source = source.replace(GATE_SEARCH, GATE_REPLACE)
            source = source.replace(
                """and market_regime_name == "bear"
                    and bear_overlay_target <= 0.0""",
                """and bear_overlay_target <= 0.0""",
            )
            source = source.replace(
                """and market_regime_name == "bear"
                and 0.0 < bear_overlay_target < 1.0""",
                """and 0.0 < bear_overlay_target < 1.0""",
            )
        module = types.ModuleType(name)
        module.__file__ = str(V7_DIR / "20_run_backtest.py")
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        return module
    finally:
        if old_config is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = old_config


def max_drawdown(nav: pd.Series) -> float:
    values = pd.to_numeric(nav, errors="coerce").dropna()
    if values.empty:
        return 0.0
    return float((values / values.cummax() - 1.0).min() * 100.0)


def annual_return(start_nav: float, end_nav: float, days: int) -> float:
    if start_nav <= 0 or end_nav <= 0 or days <= 0:
        return 0.0
    return float(((end_nav / start_nav) ** (365.25 / days) - 1.0) * 100.0)


def slice_2022_nav(nav: pd.DataFrame) -> pd.DataFrame:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    return data[(data["date"] >= "2022-01-01") & (data["date"] <= "2022-12-31")].copy()


def slice_2022_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "date" not in trades.columns:
        return pd.DataFrame()
    data = trades.copy()
    data["date"] = pd.to_datetime(data["date"])
    return data[(data["date"] >= "2022-01-01") & (data["date"] <= "2022-12-31")].copy()


def slice_period_nav(nav: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    return data[(data["date"] >= start_date) & (data["date"] <= end_date)].copy()


def slice_period_trades(trades: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if trades.empty or "date" not in trades.columns:
        return pd.DataFrame()
    data = trades.copy()
    data["date"] = pd.to_datetime(data["date"])
    return data[(data["date"] >= start_date) & (data["date"] <= end_date)].copy()


def summarize_nav(name: str, nav: pd.DataFrame, trades: pd.DataFrame) -> dict:
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
    if not trades.empty and "reason" in trades.columns:
        row["bear_probe_buys"] = int(trades["reason"].eq("bear_probe_initial_buy").sum())
        row["overlay_reduce_exits"] = int(trades["reason"].eq("bear_overlay_reduce_exit").sum())
        row["overlay_risk_off_exits"] = int(trades["reason"].eq("bear_overlay_risk_off_exit").sum())
    return row


def period_table(nav_map: dict[str, pd.DataFrame], freq: str) -> pd.DataFrame:
    rows = []
    for name, nav in nav_map.items():
        data = nav.copy()
        data["date"] = pd.to_datetime(data["date"])
        data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
        data["period"] = data["date"].dt.strftime("%Y" if freq == "Y" else "%Y-%m")
        previous = None
        for period, group in data.groupby("period", sort=True):
            start_nav = float(group.iloc[0]["nav"]) if previous is None else previous
            end_nav = float(group.iloc[-1]["nav"])
            previous = end_nav
            rows.append({"period": period, "strategy": name, "return_pct": round((end_nav / start_nav - 1.0) * 100.0, 2), "end_nav": round(end_nav, 2)})
    return pd.DataFrame(rows)


def reason_table(trade_map: dict[str, pd.DataFrame]) -> pd.DataFrame:
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
    text = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>v7 2022 strict probe experiment</title>
<style>
body{{font-family:Arial,'Microsoft YaHei',sans-serif;margin:20px;background:#f6f8fb;color:#222}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:24px}}
table{{border-collapse:collapse;background:#fff;width:100%;font-size:13px}}
th,td{{border:1px solid #d8dee9;padding:6px 8px;text-align:right}}
th:first-child,td:first-child,td:nth-child(2){{text-align:left}}
.note{{background:#fff;border:1px solid #d8dee9;padding:10px 12px;line-height:1.7}}
</style></head><body>
<h1>v7 2022 熊市试探收紧实验</h1>
<div class="note">
当前 v7：熊市 target_exposure >= 20% 即可试探买入。<br>
strict_probe：必须同时满足 v6 的 bear_probe_market_ok，才允许熊市试探买入。<br>
strict_probe_overlay_gate：target_exposure < 100% 时禁止普通首买，只允许严格试探。<br>
本实验跑全周期，不改正式 v7 文件。
</div>
<h2>总体结果</h2>{table_html(results)}
<h2>年度收益</h2>{table_html(yearly.pivot(index="period", columns="strategy", values="return_pct").reset_index())}
<h2>月度收益</h2>{table_html(monthly.pivot(index="period", columns="strategy", values="return_pct").reset_index())}
<h2>交易原因统计</h2>{table_html(reasons)}
</body></html>"""
    REPORT_PATH.write_text(text, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = pd.read_parquet(V7_DIR / "output" / "panel.parquet")
    market = pd.read_parquet(V7_DIR / "output" / "market_index.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")
    full_start = "2018-01-01"
    full_end = str(pd.to_datetime(panel["trade_date"]).max().date())

    rows = []
    nav_map = {}
    trade_map = {}
    v6_nav = pd.read_csv(BACKTRADER_DIR / "v6" / "output" / "nav_series.csv")
    v6_trades = pd.read_csv(BACKTRADER_DIR / "v6" / "output" / "trade_records.csv")
    v6_nav_full = slice_period_nav(v6_nav, full_start, full_end)
    v6_trades_full = slice_period_trades(v6_trades, full_start, full_end)
    rows.append(summarize_nav("v6_output", v6_nav_full, v6_trades_full))
    nav_map["v6_output"] = v6_nav_full
    trade_map["v6_output"] = v6_trades_full
    cases = [
        ("current_v7", False, False),
        ("strict_probe", True, False),
        ("strict_probe_overlay_gate", True, True),
    ]
    for name, strict, overlay_gate in cases:
        mod = load_v7_module(f"v7_{name}", strict_probe=strict, overlay_gate=overlay_gate)
        nav, trades, rebalance, scores, holdings, stats = mod.run_backtest(panel, market, full_start, full_end)
        nav_full = slice_period_nav(nav, full_start, full_end)
        trades_full = slice_period_trades(trades, full_start, full_end)
        nav.to_csv(OUTPUT_DIR / f"{name}_nav.csv", index=False)
        trades.to_csv(OUTPUT_DIR / f"{name}_trades.csv", index=False)
        rebalance.to_csv(OUTPUT_DIR / f"{name}_rebalance_log.csv", index=False)
        rows.append({**summarize_nav(name, nav_full, trades_full), **{f"stat_{k}": v for k, v in stats.items() if k.startswith("bear_overlay") or k.startswith("bear_probe")}})
        nav_map[name] = nav_full
        trade_map[name] = trades_full

    results = pd.DataFrame(rows)
    yearly = period_table(nav_map, "Y")
    monthly = period_table(nav_map, "M")
    reasons = reason_table(trade_map)
    results.to_csv(RESULTS_PATH, index=False, encoding="utf-8-sig")
    monthly.to_csv(MONTHLY_PATH, index=False, encoding="utf-8-sig")
    yearly.to_csv(YEARLY_PATH, index=False, encoding="utf-8-sig")
    reasons.to_csv(OUTPUT_DIR / "reasons.csv", index=False, encoding="utf-8-sig")
    write_report(results, yearly, monthly, reasons)
    print(json.dumps({"results": str(RESULTS_PATH), "yearly": str(YEARLY_PATH), "monthly": str(MONTHLY_PATH), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))
    print(results.to_string(index=False))


if __name__ == "__main__":
    main()

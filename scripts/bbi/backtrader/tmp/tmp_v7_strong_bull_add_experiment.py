from __future__ import annotations

import html
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V7_DIR = BACKTRADER_DIR / "v7"

OUTPUT_DIR = TMP_DIR / "tmp_v7_strong_bull_add_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_strong_bull_add_README.md"

START_DATE = "2018-01-01"
END_DATE = None

BASE_LONG_MAX_TOTAL_EXPOSURE = 500_000.0
BASE_LONG_ADD_PROFIT_THRESHOLDS = (0.05, 0.10, 0.15)

CASES = [
    {
        "case": "当前v7复现",
        "mode": "baseline",
    },
    {
        "case": "强牛提前加仓",
        "mode": "early_threshold",
        "early_thresholds": (0.03, 0.07, 0.12),
        "strong_breadth": 0.62,
        "strong_slope": 0.02,
        "strong_dd": -0.08,
    },
    {
        "case": "强牛加仓1.3_总仓55",
        "mode": "boost_size",
        "add_multiplier": 1.30,
        "strong_total_exposure": 550_000.0,
        "strong_breadth": 0.62,
        "strong_slope": 0.02,
        "strong_dd": -0.08,
    },
    {
        "case": "强牛提前加仓1.3_总仓55",
        "mode": "early_boost",
        "early_thresholds": (0.03, 0.07, 0.12),
        "add_multiplier": 1.30,
        "strong_total_exposure": 550_000.0,
        "strong_breadth": 0.62,
        "strong_slope": 0.02,
        "strong_dd": -0.08,
    },
    {
        "case": "严格强牛提前加仓1.3_总仓55",
        "mode": "early_boost",
        "early_thresholds": (0.03, 0.07, 0.12),
        "add_multiplier": 1.30,
        "strong_total_exposure": 550_000.0,
        "strong_breadth": 0.68,
        "strong_slope": 0.03,
        "strong_dd": -0.06,
    },
]


def append_progress(message: str) -> None:
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def safe_float(value, default=float("nan")) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def is_strong_bull(market_regime_name: str, regime_snapshot: dict, case: dict) -> bool:
    if market_regime_name != "bull":
        return False
    breadth = safe_float(regime_snapshot.get("breadth_above_bbi"))
    slope = safe_float(regime_snapshot.get("market_ma120_slope_20"))
    dd = safe_float(regime_snapshot.get("market_dd_252"))
    return (
        breadth >= float(case.get("strong_breadth", 0.62))
        and slope >= float(case.get("strong_slope", 0.02))
        and dd >= float(case.get("strong_dd", -0.08))
    )


def add_profit_thresholds(market_regime_name: str, regime_snapshot: dict, case: dict) -> tuple[float, ...]:
    if case.get("mode") in {"early_threshold", "early_boost"} and is_strong_bull(market_regime_name, regime_snapshot, case):
        return tuple(float(v) for v in case.get("early_thresholds", BASE_LONG_ADD_PROFIT_THRESHOLDS))
    return BASE_LONG_ADD_PROFIT_THRESHOLDS


def add_target_amount(base_amount: float | None, market_regime_name: str, regime_snapshot: dict, case: dict) -> float | None:
    if base_amount is None:
        return None
    if case.get("mode") in {"boost_size", "early_boost"} and is_strong_bull(market_regime_name, regime_snapshot, case):
        return float(base_amount) * float(case.get("add_multiplier", 1.0))
    return float(base_amount)


def total_exposure_limit(market_regime_name: str, regime_snapshot: dict, case: dict) -> float:
    if case.get("mode") in {"boost_size", "early_boost"} and is_strong_bull(market_regime_name, regime_snapshot, case):
        return float(case.get("strong_total_exposure", BASE_LONG_MAX_TOTAL_EXPOSURE))
    return BASE_LONG_MAX_TOTAL_EXPOSURE


def normalize_market_frame(market: pd.DataFrame) -> pd.DataFrame:
    out = market.copy()
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"])
        out = out.sort_values("trade_date").set_index("trade_date")
    else:
        out.index = pd.to_datetime(out.index)
        out = out.sort_index()
    return out


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"patch anchor not found: {old[:100]}")
    return source.replace(old, new, 1)


def load_v7_backtest_module(module_name: str, case: dict):
    sys.path.insert(0, str(V7_DIR))
    old_config = sys.modules.get("config")
    config_spec = importlib.util.spec_from_file_location("config", V7_DIR / "config.py")
    config_mod = importlib.util.module_from_spec(config_spec)
    assert config_spec.loader is not None
    config_spec.loader.exec_module(config_mod)
    sys.modules["config"] = config_mod
    try:
        source = (V7_DIR / "20_run_backtest.py").read_text(encoding="utf-8")
        source = replace_once(
            source,
            '        "weak_lowvol_mom_candidate_blocks": 0,\n',
            '        "weak_lowvol_mom_candidate_blocks": 0,\n'
            '        "strong_bull_add_case": STRONG_BULL_ADD_CASE.get("case", "baseline"),\n'
            '        "strong_bull_add_fills": 0,\n',
        )
        source = replace_once(
            source,
            "                        if pos.get(\"pending_sell\") or not can_add_position(code, pos, signal_panel):\n",
            "                        if pos.get(\"pending_sell\") or not __can_add_position_tier(code, pos, signal_panel, market_regime_name, regime_snapshot):\n",
        )
        source = replace_once(
            source,
            "                        target_amount = next_position_step(pos)\n",
            "                        target_amount = __tier_next_position_step(pos, market_regime_name, regime_snapshot)\n",
        )
        source = replace_once(
            source,
            "                        available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n"
            "                        target_amount = min(target_amount, available_exposure)\n",
            "                        available_exposure = __tier_total_exposure_limit(market_regime_name, regime_snapshot) - calc_total_exposure(holdings)\n"
            "                        target_amount = min(target_amount, available_exposure)\n",
        )
        source = replace_once(
            source,
            '                            stats["add_buy_fills"] += 1\n',
            '                            stats["add_buy_fills"] += 1\n'
            '                            if __is_strong_bull_case(market_regime_name, regime_snapshot):\n'
            '                                stats["strong_bull_add_fills"] += 1\n',
        )

        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.STRONG_BULL_ADD_CASE = dict(case)

        def _is_strong(market_regime_name, regime_snapshot):
            if module.STRONG_BULL_ADD_CASE.get("mode") == "baseline":
                return False
            return is_strong_bull(market_regime_name, regime_snapshot, module.STRONG_BULL_ADD_CASE)

        def _can_add(code, pos, signal_panel, market_regime_name, regime_snapshot):
            if module.STRONG_BULL_ADD_CASE.get("mode") == "baseline":
                return module.can_add_position(code, pos, signal_panel)
            step_index = int(pos.get("step_index", 0))
            if step_index <= 0 or step_index >= len(module.LONG_POSITION_STEPS):
                return False
            profit_pct = module.calc_position_profit_pct(code, pos, signal_panel)
            if profit_pct is None:
                return False
            thresholds = add_profit_thresholds(market_regime_name, regime_snapshot, module.STRONG_BULL_ADD_CASE)
            threshold_index = step_index - 1
            if threshold_index >= len(thresholds):
                return False
            return profit_pct >= thresholds[threshold_index]

        def _next_step(pos, market_regime_name, regime_snapshot):
            base = module.next_position_step(pos)
            return add_target_amount(base, market_regime_name, regime_snapshot, module.STRONG_BULL_ADD_CASE)

        def _total_limit(market_regime_name, regime_snapshot):
            return total_exposure_limit(market_regime_name, regime_snapshot, module.STRONG_BULL_ADD_CASE)

        module.__is_strong_bull_case = _is_strong
        module.__can_add_position_tier = _can_add
        module.__tier_next_position_step = _next_step
        module.__tier_total_exposure_limit = _total_limit
        return module
    finally:
        if old_config is not None:
            sys.modules["config"] = old_config
        else:
            sys.modules.pop("config", None)
        try:
            sys.path.remove(str(V7_DIR))
        except ValueError:
            pass


def load_existing_nav(version: str) -> pd.DataFrame | None:
    path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
    if not path.exists():
        return None
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    return nav[nav["date"] >= pd.Timestamp(START_DATE)].copy()


def load_existing_summary(version: str) -> dict:
    path = BACKTRADER_DIR / version / "output" / "summary.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["case"] = version
    data["mode"] = "published"
    return data


def calc_nav_stats(nav: pd.DataFrame, init_cash: float = 500_000.0) -> dict:
    curve = nav["nav"] / float(init_cash)
    dd = curve / curve.cummax() - 1.0
    total_ret = curve.iloc[-1] - 1.0
    days = max((nav["date"].iloc[-1] - nav["date"].iloc[0]).days, 1)
    annual = (1.0 + total_ret) ** (365.0 / days) - 1.0
    return {
        "final_nav": float(nav["nav"].iloc[-1]),
        "total_return_pct": float(total_ret * 100.0),
        "annual_return_pct": float(annual * 100.0),
        "max_drawdown_pct": float(dd.min() * 100.0),
        "avg_cash_ratio": float((nav["cash"] / nav["nav"]).mean()) if "cash" in nav else np.nan,
        "avg_holdings": float(nav["holdings"].mean()) if "holdings" in nav else np.nan,
    }


def monthly_returns(nav: pd.DataFrame) -> pd.Series:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["nav"].sort_index().resample("ME").last().pct_change()


def yearly_returns(nav: pd.DataFrame) -> pd.Series:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["nav"].sort_index().resample("YE").last().pct_change()


def run_case(case: dict, panel: pd.DataFrame, market: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    module = load_v7_backtest_module("tmp_v7_strong_bull_add_" + case["case"], case)
    nav, trades, rebalance_log, score_rows, holdings, stats = module.run_backtest(
        panel.copy(),
        market.copy(),
        START_DATE,
        END_DATE,
    )
    stats["case"] = case["case"]
    stats["mode"] = case["mode"]
    stats["avg_cash_ratio"] = float((nav["cash"] / nav["nav"]).mean())
    stats["avg_holdings"] = float(nav["holdings"].mean())
    return stats, nav, trades


def format_pct(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def table_html(df: pd.DataFrame, title: str) -> str:
    headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, row in df.iterrows():
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row.tolist()) + "</tr>")
    return f"<h2>{html.escape(title)}</h2><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def best_experiment(all_stats: list[dict]) -> dict | None:
    experiments = [
        s for s in all_stats
        if s.get("mode") not in {"published", "baseline"}
        and int(s.get("strong_bull_add_fills", 0) or 0) > 0
    ]
    if not experiments:
        return None
    return max(experiments, key=lambda s: float(s.get("total_return_pct", -999999)))


def build_report(all_stats: list[dict], nav_by_case: dict[str, pd.DataFrame]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for stats in all_stats:
        summary_rows.append({
            "策略": stats["case"],
            "总收益": format_pct(stats.get("total_return_pct")),
            "年化": format_pct(stats.get("annual_return_pct")),
            "最大回撤": format_pct(stats.get("max_drawdown_pct")),
            "Calmar": f"{float(stats.get('calmar_ratio', 0.0)):.2f}",
            "交易数": stats.get("trade_records", "-"),
            "加仓成交": stats.get("add_buy_fills", "-"),
            "强牛加仓": stats.get("strong_bull_add_fills", "-"),
            "平均现金占比": format_pct(float(stats.get("avg_cash_ratio", np.nan)) * 100.0),
            "平均持股数": f"{float(stats.get('avg_holdings', np.nan)):.2f}" if not pd.isna(stats.get("avg_holdings", np.nan)) else "-",
        })
    summary_df = pd.DataFrame(summary_rows)

    yearly = {}
    monthly = {}
    for name, nav in nav_by_case.items():
        yearly[name] = yearly_returns(nav) * 100.0
        monthly[name] = monthly_returns(nav) * 100.0
    yearly_df = pd.DataFrame(yearly).round(2).reset_index()
    yearly_df["date"] = yearly_df["date"].dt.strftime("%Y")
    yearly_df = yearly_df.rename(columns={"date": "年份"}).fillna("-")
    monthly_df = pd.DataFrame(monthly).round(2).tail(36).reset_index()
    monthly_df["date"] = monthly_df["date"].dt.strftime("%Y-%m")
    monthly_df = monthly_df.rename(columns={"date": "月份"}).fillna("-")

    v7 = next((s for s in all_stats if s["case"] == "v7"), None)
    best = best_experiment(all_stats)
    advice = "暂不合并"
    reason = "实验未同时超过 v7 收益并控制回撤。"
    if best and v7:
        improves_return = float(best.get("total_return_pct", -999)) > float(v7.get("total_return_pct", -999)) + 1e-6
        drawdown_ok = float(best.get("max_drawdown_pct", -999)) >= float(v7.get("max_drawdown_pct", -999)) - 5.0
        if improves_return and drawdown_ok:
            advice = "建议进入正式合入候选"
            reason = "最佳实验总收益超过 v7，最大回撤恶化不超过 5 个百分点。"
    display_best = best or {"case": "无实验", "total_return_pct": np.nan, "max_drawdown_pct": np.nan}

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 强牛分层加仓实验报告</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #1f2937; }}
h1 {{ font-size: 24px; margin-bottom: 6px; }}
h2 {{ font-size: 18px; margin-top: 24px; }}
.note {{ padding: 12px 14px; background: #f3f4f6; border-left: 4px solid #2563eb; margin: 16px 0; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 8px; font-size: 13px; }}
th, td {{ border: 1px solid #d1d5db; padding: 7px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #374151; color: white; position: sticky; top: 0; }}
.small {{ color: #6b7280; font-size: 12px; }}
</style>
</head>
<body>
<h1>v7 强牛分层加仓实验报告</h1>
<div class="note"><b>合并建议：{html.escape(advice)}</b><br>{html.escape(reason)}<br>最佳实验：{html.escape(display_best["case"])}，总收益 {format_pct(display_best.get("total_return_pct"))}，最大回撤 {format_pct(display_best.get("max_drawdown_pct"))}。</div>
<p class="small">实验只修改 tmp 注入逻辑，正式 v4/v5/v6/v7 文件未修改。强牛加仓使用 signal_date 已知市场状态，不使用调仓日收盘价。</p>
{table_html(summary_df, "核心指标对比")}
{table_html(yearly_df, "年度收益对比（%）")}
{table_html(monthly_df, "最近36个月月度收益对比（%）")}
<h2>下一步建议</h2>
<ol>
<li>若本轮仍弱于 v7，不继续放大加仓，转向失败买入过滤。</li>
<li>若收益超过 v7 且回撤可控，再拆分验证强牛判定和加仓倍数。</li>
<li>强牛定义后续可加入行业广度，但应独立实验，避免归因混杂。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_progress("开始运行强牛分层加仓实验。")
    panel = pd.read_parquet(V7_DIR / "output" / "panel.parquet")
    market = pd.read_parquet(V7_DIR / "output" / "market_index.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = normalize_market_frame(market)
    append_progress(f"加载 v7 panel rows={len(panel):,}。")

    all_stats = []
    nav_by_case = {}
    for version in ["v4", "v5", "v6", "v7"]:
        stats = load_existing_summary(version)
        nav = load_existing_nav(version)
        if nav is not None:
            stats.update(calc_nav_stats(nav))
            nav_by_case[version] = nav
        all_stats.append(stats)

    for case in CASES:
        stats, nav, trades = run_case(case, panel, market)
        nav.to_csv(OUTPUT_DIR / f"{case['case']}_nav_series.csv", index=False, encoding="utf-8-sig")
        trades.to_csv(OUTPUT_DIR / f"{case['case']}_trade_records.csv", index=False, encoding="utf-8-sig")
        (OUTPUT_DIR / f"{case['case']}_summary.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        all_stats.append(stats)
        nav_by_case[case["case"]] = nav.copy()
        append_progress(
            f"完成 {case['case']}：total_return={stats['total_return_pct']:.2f}%，"
            f"max_dd={stats['max_drawdown_pct']:.2f}%，trades={stats['trade_records']}。"
        )

    build_report(all_stats, nav_by_case)
    append_progress(f"生成 HTML 报表：{REPORT_PATH}")
    append_progress("设计 review：本轮只验证强牛分层加仓，不改变新开仓数量、止损和候选排序。")
    append_progress("开发 review：正式 v4-v7 文件未修改；强牛判定和加仓规则有单元测试；输出写入 tmp。")


if __name__ == "__main__":
    main()

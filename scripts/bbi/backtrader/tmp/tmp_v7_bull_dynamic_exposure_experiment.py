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

OUTPUT_DIR = TMP_DIR / "tmp_v7_bull_dynamic_exposure_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_bull_dynamic_exposure_README.md"

START_DATE = "2018-01-01"
END_DATE = None

BASE_LONG_MAX_HOLDINGS = 5
BASE_LONG_MAX_TOTAL_EXPOSURE = 500_000.0

CASES = [
    {
        "case": "当前v7复现",
        "mode": "baseline",
        "bull_exposure_ratio": None,
        "bull_max_holdings": BASE_LONG_MAX_HOLDINGS,
        "bull_max_single_ratio": None,
    },
    {
        "case": "牛市80仓位_8只_单票18",
        "mode": "dynamic",
        "bull_exposure_ratio": 0.80,
        "bull_max_holdings": 8,
        "bull_max_single_ratio": 0.18,
    },
    {
        "case": "牛市90仓位_10只_单票15",
        "mode": "dynamic",
        "bull_exposure_ratio": 0.90,
        "bull_max_holdings": 10,
        "bull_max_single_ratio": 0.15,
    },
    {
        "case": "牛市95仓位_12只_单票12",
        "mode": "dynamic",
        "bull_exposure_ratio": 0.95,
        "bull_max_holdings": 12,
        "bull_max_single_ratio": 0.12,
    },
    {
        "case": "牛市只加仓70_5只_单票25",
        "mode": "dynamic_add_only",
        "bull_exposure_ratio": 0.70,
        "bull_max_holdings": BASE_LONG_MAX_HOLDINGS,
        "bull_max_single_ratio": 0.25,
    },
    {
        "case": "牛市只加仓85_5只_单票22",
        "mode": "dynamic_add_only",
        "bull_exposure_ratio": 0.85,
        "bull_max_holdings": BASE_LONG_MAX_HOLDINGS,
        "bull_max_single_ratio": 0.22,
    },
]


def is_dynamic_case(case: dict) -> bool:
    return case.get("mode") in {"dynamic", "dynamic_add_only"} or case.get("bull_exposure_ratio") is not None


def append_progress(message: str) -> None:
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def max_holdings_for_regime(market_regime_name: str, case: dict) -> int:
    if not is_dynamic_case(case) or market_regime_name != "bull":
        return BASE_LONG_MAX_HOLDINGS
    if case.get("mode") == "dynamic_add_only":
        return BASE_LONG_MAX_HOLDINGS
    return int(case.get("bull_max_holdings") or BASE_LONG_MAX_HOLDINGS)


def total_exposure_limit(market_regime_name: str, case: dict, nav: float) -> float:
    if not is_dynamic_case(case) or market_regime_name != "bull":
        return BASE_LONG_MAX_TOTAL_EXPOSURE
    ratio = float(case.get("bull_exposure_ratio") or 0.0)
    if ratio <= 0:
        return BASE_LONG_MAX_TOTAL_EXPOSURE
    return max(BASE_LONG_MAX_TOTAL_EXPOSURE, nav * ratio)


def single_position_limit(market_regime_name: str, case: dict, nav: float) -> float:
    if not is_dynamic_case(case) or market_regime_name != "bull":
        return BASE_LONG_MAX_TOTAL_EXPOSURE
    ratio = float(case.get("bull_max_single_ratio") or 0.0)
    if ratio <= 0:
        return BASE_LONG_MAX_TOTAL_EXPOSURE
    return nav * ratio


def cap_target_amount(
    requested_amount: float,
    market_regime_name: str,
    case: dict,
    nav: float,
    cash: float,
    current_total_exposure: float,
    current_position_exposure: float = 0.0,
) -> float:
    if not is_dynamic_case(case) or market_regime_name != "bull":
        return max(0.0, min(float(requested_amount), BASE_LONG_MAX_TOTAL_EXPOSURE - current_total_exposure))
    total_remaining = total_exposure_limit(market_regime_name, case, nav) - current_total_exposure
    single_remaining = single_position_limit(market_regime_name, case, nav) - current_position_exposure
    capped = min(float(requested_amount), float(cash), total_remaining, single_remaining)
    return max(0.0, capped)


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
            '        "bull_dynamic_case": BULL_DYNAMIC_CASE.get("case", "baseline"),\n'
            '        "bull_dynamic_signal_days": 0,\n'
            '        "bull_dynamic_capacity_blocks": 0,\n',
        )
        source = replace_once(
            source,
            "                        available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n"
            "                        target_amount = min(target_amount, available_exposure)\n",
            "                        current_nav = __calc_current_nav(cash, holdings, signal_panel)\n"
            "                        current_position_exposure = float(pos.get(\"invested_amount\", calc_position_cost(pos)))\n"
            "                        target_amount = __cap_dynamic_target_amount(\n"
            "                            target_amount,\n"
            "                            market_regime_name,\n"
            "                            current_nav,\n"
            "                            cash,\n"
            "                            calc_total_exposure(holdings),\n"
            "                            current_position_exposure,\n"
            "                        )\n",
        )
        source = replace_once(
            source,
            "                    if len(holdings) >= LONG_MAX_HOLDINGS:\n",
            "                    if len(holdings) >= __max_dynamic_holdings(market_regime_name):\n",
        )
        source = replace_once(
            source,
            "                    available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n"
            "                    if probe_open:\n"
            "                        target_amount = calc_bear_probe_target_amount(\n"
            "                            float(LONG_POSITION_STEPS[0]),\n"
            "                            cash,\n"
            "                            calc_bear_probe_exposure(holdings),\n"
            "                        )\n"
            "                    else:\n"
            "                        target_amount = min(float(LONG_POSITION_STEPS[0]), available_exposure)\n"
            "                    target_amount = min(target_amount, available_exposure)\n",
            "                    current_nav = __calc_current_nav(cash, holdings, signal_panel)\n"
            "                    if probe_open:\n"
            "                        target_amount = calc_bear_probe_target_amount(\n"
            "                            float(LONG_POSITION_STEPS[0]),\n"
            "                            cash,\n"
            "                            calc_bear_probe_exposure(holdings),\n"
            "                        )\n"
            "                    else:\n"
            "                        target_amount = __cap_dynamic_target_amount(\n"
            "                            float(LONG_POSITION_STEPS[0]),\n"
            "                            market_regime_name,\n"
            "                            current_nav,\n"
            "                            cash,\n"
            "                            calc_total_exposure(holdings),\n"
            "                            0.0,\n"
            "                        )\n",
        )

        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.BULL_DYNAMIC_CASE = dict(case)

        def _calc_current_nav(cash, holdings, day_panel):
            return float(cash) + sum(module.mark_position(c, p, day_panel) for c, p in holdings.items())

        def _max_dynamic_holdings(market_regime_name):
            return max_holdings_for_regime(market_regime_name, module.BULL_DYNAMIC_CASE)

        def _cap_dynamic_target_amount(
            requested_amount,
            market_regime_name,
            nav,
            cash,
            current_total_exposure,
            current_position_exposure,
        ):
            amount = cap_target_amount(
                requested_amount,
                market_regime_name,
                module.BULL_DYNAMIC_CASE,
                nav,
                cash,
                current_total_exposure,
                current_position_exposure,
            )
            if (
                is_dynamic_case(module.BULL_DYNAMIC_CASE)
                and market_regime_name == "bull"
                and amount < float(requested_amount)
            ):
                return amount
            return amount

        module.__calc_current_nav = _calc_current_nav
        module.__max_dynamic_holdings = _max_dynamic_holdings
        module.__cap_dynamic_target_amount = _cap_dynamic_target_amount
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
    if not path.exists():
        return {"case": version, "missing": True}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["case"] = version
    return data


def normalize_market_frame(market: pd.DataFrame) -> pd.DataFrame:
    out = market.copy()
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"])
        out = out.sort_values("trade_date").set_index("trade_date")
    else:
        out.index = pd.to_datetime(out.index)
        out = out.sort_index()
    return out


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
    indexed = frame.set_index("date")["nav"].sort_index()
    return indexed.resample("ME").last().pct_change()


def yearly_returns(nav: pd.DataFrame) -> pd.Series:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    indexed = frame.set_index("date")["nav"].sort_index()
    return indexed.resample("YE").last().pct_change()


def run_case(case: dict, panel: pd.DataFrame, market: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    module = load_v7_backtest_module("tmp_v7_bull_dynamic_" + case["case"], case)
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


def format_num(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.0f}"


def table_html(df: pd.DataFrame, title: str) -> str:
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{html.escape(str(v))}</td>" for v in row.tolist())
        rows.append(f"<tr>{cells}</tr>")
    headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    return f"<h2>{html.escape(title)}</h2><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def build_report(all_stats: list[dict], nav_by_case: dict[str, pd.DataFrame]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for stats in all_stats:
        summary_rows.append({
            "策略": stats["case"],
            "总收益": format_pct(stats.get("total_return_pct")),
            "年化": format_pct(stats.get("annual_return_pct")),
            "最大回撤": format_pct(stats.get("max_drawdown_pct")),
            "Calmar": f"{float(stats.get('calmar_ratio', 0.0)):.2f}" if stats.get("calmar_ratio") is not None else "-",
            "交易数": stats.get("trade_records", "-"),
            "止损": stats.get("stop_loss_fills", "-"),
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

    best = best_dynamic_experiment(all_stats)
    v7 = next((s for s in all_stats if s["case"] == "v7"), None)
    advice = "暂不合并"
    reason = "所有动态仓位实验均未同时超过 v7 收益并控制回撤。"
    if best is not None and v7:
        improves_return = float(best.get("total_return_pct", -999)) > float(v7.get("total_return_pct", -999))
        drawdown_ok = float(best.get("max_drawdown_pct", -999)) >= float(v7.get("max_drawdown_pct", -999)) - 5.0
        if improves_return and drawdown_ok:
            advice = "建议进入正式合入候选"
            reason = "最佳实验总收益超过 v7，最大回撤恶化不超过 5 个百分点。"
    display_best = best or {"case": "无动态实验", "total_return_pct": np.nan, "max_drawdown_pct": np.nan}

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 牛市动态仓位实验报告</title>
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
<h1>v7 牛市动态仓位实验报告</h1>
<div class="note"><b>合并建议：{html.escape(advice)}</b><br>{html.escape(reason)}<br>最佳动态实验：{html.escape(display_best["case"])}，总收益 {format_pct(display_best.get("total_return_pct"))}，最大回撤 {format_pct(display_best.get("max_drawdown_pct"))}。</div>
<p class="small">实验只修改 tmp 注入逻辑，正式 v4/v5/v6/v7 文件未修改。比较基于各版本 output 中已有结果与本轮新跑实验。</p>
{table_html(summary_df, "核心指标对比")}
{table_html(yearly_df, "年度收益对比（%）")}
{table_html(monthly_df, "最近36个月月度收益对比（%）")}
<h2>下一步建议</h2>
<ol>
<li>若动态仓位收益提升但回撤可控，下一轮只测试 bull 入场后的加仓节奏，不同时改止损。</li>
<li>若回撤明显恶化，保留 v7，改研究 bull 分层：强牛扩仓、弱牛不扩仓。</li>
<li>财务/价值数据暂不合入本实验；此前 value-quality 实验弱于 v7，应作为独立路线继续研究。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def best_dynamic_experiment(all_stats: list[dict]) -> dict | None:
    dynamic_stats = [
        stats for stats in all_stats
        if stats.get("mode") in {"dynamic", "dynamic_add_only"}
    ]
    if not dynamic_stats:
        return None
    return max(dynamic_stats, key=lambda s: float(s.get("total_return_pct", -999999)))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_progress("开始运行牛市动态仓位实验。")
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
            stats["case"] = version
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
    append_progress("设计 review：本轮只验证 bull 动态仓位，不混入行业、价值、止损改动。")
    append_progress("开发 review：正式 v4-v7 文件未修改；测试覆盖动态上限和单票限制；输出写入 tmp。")


if __name__ == "__main__":
    main()

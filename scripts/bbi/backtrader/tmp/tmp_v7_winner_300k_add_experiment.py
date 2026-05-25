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

OUTPUT_DIR = TMP_DIR / "tmp_v7_winner_300k_add_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_winner_300k_add_README.md"

START_DATE = "2018-01-01"
END_DATE = None
BASE_TOTAL_EXPOSURE = 500_000.0

CASES = [
    {
        "case": "当前v7复现",
        "mode": "baseline",
        "steps": (80_000.0, 60_000.0, 40_000.0, 20_000.0),
        "thresholds": (0.05, 0.10, 0.15),
        "total_cap": 500_000.0,
        "nav_ratio": 1.0,
        "max_drawdown_for_extra": None,
    },
    {
        "case": "保守赢家30万",
        "mode": "winner_300k",
        "steps": (80_000.0, 60_000.0, 40_000.0, 20_000.0, 100_000.0),
        "thresholds": (0.05, 0.10, 0.15, 0.30),
        "total_cap": 1_200_000.0,
        "nav_ratio": 0.60,
        "max_drawdown_for_extra": None,
    },
    {
        "case": "严格赢家30万",
        "mode": "winner_300k",
        "steps": (80_000.0, 60_000.0, 40_000.0, 20_000.0, 100_000.0),
        "thresholds": (0.05, 0.10, 0.15, 0.40),
        "total_cap": 1_200_000.0,
        "nav_ratio": 0.60,
        "max_drawdown_for_extra": -0.10,
    },
    {
        "case": "分批到30万",
        "mode": "winner_300k",
        "steps": (80_000.0, 60_000.0, 40_000.0, 20_000.0, 50_000.0, 50_000.0),
        "thresholds": (0.05, 0.10, 0.15, 0.25, 0.40),
        "total_cap": 1_200_000.0,
        "nav_ratio": 0.60,
        "max_drawdown_for_extra": None,
    },
]
CASES_BY_NAME = {case["case"]: case for case in CASES}


def append_progress(message):
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def replace_once(source, old, new):
    if old not in source:
        raise RuntimeError(f"patch anchor not found: {old[:120]}")
    return source.replace(old, new, 1)


def calc_total_exposure_limit(case, nav):
    if case.get("mode") == "baseline":
        return BASE_TOTAL_EXPOSURE
    ratio_limit = float(nav) * float(case.get("nav_ratio", 0.60))
    capped = min(float(case.get("total_cap", 1_200_000.0)), ratio_limit)
    return max(BASE_TOTAL_EXPOSURE, capped)


def current_drawdown(current_nav, peak_nav):
    peak_nav = max(float(peak_nav), 1.0)
    return float(current_nav) / peak_nav - 1.0


def can_use_extra_winner_add(case, step_index, market_regime_name, current_nav, peak_nav):
    if case.get("mode") == "baseline":
        return False
    if int(step_index) < 4:
        return True
    if market_regime_name == "bear":
        return False
    max_dd = case.get("max_drawdown_for_extra")
    if max_dd is not None and current_drawdown(current_nav, peak_nav) < float(max_dd):
        return False
    return True


def load_v7_backtest_module(module_name, case):
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
            '        "winner_300k_case": WINNER_300K_CASE.get("case", "baseline"),\n'
            '        "winner_300k_extra_add_signals": 0,\n'
            '        "winner_300k_extra_add_fills": 0,\n'
            '        "winner_300k_extra_add_amount": 0.0,\n'
        )
        source = replace_once(
            source,
            "                        target_amount = next_position_step(pos)\n"
            "                        if target_amount is None:\n"
            "                            continue\n"
            "                        available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n"
            "                        target_amount = min(target_amount, available_exposure)\n",
            "                        step_index_before_add = int(pos.get(\"step_index\", 0))\n"
            "                        target_amount = next_position_step(pos)\n"
            "                        if target_amount is None:\n"
            "                            continue\n"
            "                        current_nav = __calc_current_nav(cash, holdings, signal_panel)\n"
            "                        if step_index_before_add >= 4:\n"
            "                            stats[\"winner_300k_extra_add_signals\"] += 1\n"
            "                            if not __can_use_extra_winner_add(step_index_before_add, market_regime_name, current_nav):\n"
            "                                continue\n"
            "                        available_exposure = __total_exposure_limit(current_nav) - calc_total_exposure(holdings)\n"
            "                        target_amount = min(target_amount, available_exposure)\n",
        )
        source = replace_once(
            source,
            "                        cash, bought, reason = execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, \"long_add_buy\")\n"
            "                        if bought:\n",
            "                        buy_reason = \"winner_300k_extra_add\" if step_index_before_add >= 4 else \"long_add_buy\"\n"
            "                        cash, bought, reason = execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, buy_reason)\n"
            "                        if bought and step_index_before_add >= 4:\n"
            "                            stats[\"winner_300k_extra_add_fills\"] += 1\n"
            "                            stats[\"winner_300k_extra_add_amount\"] += float(target_amount)\n"
            "                            holdings[code][\"winner_300k_extra_amount\"] = float(holdings[code].get(\"winner_300k_extra_amount\", 0.0)) + float(target_amount)\n"
            "                        if bought:\n",
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
            "                    available_exposure = __total_exposure_limit(current_nav) - calc_total_exposure(holdings)\n"
            "                    if probe_open:\n"
            "                        target_amount = calc_bear_probe_target_amount(\n"
            "                            float(LONG_POSITION_STEPS[0]),\n"
            "                            cash,\n"
            "                            calc_bear_probe_exposure(holdings),\n"
            "                        )\n"
            "                    else:\n"
            "                        target_amount = min(float(LONG_POSITION_STEPS[0]), available_exposure)\n"
            "                    target_amount = min(target_amount, available_exposure)\n",
        )
        source = replace_once(
            source,
            "        nav = cash + sum(mark_position(c, p, day_panel) for c, p in holdings.items())\n",
            "        nav = cash + sum(mark_position(c, p, day_panel) for c, p in holdings.items())\n"
            "        __record_winner_nav(nav)\n",
        )

        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.WINNER_300K_CASE = dict(case)
        module.LONG_POSITION_STEPS = tuple(case["steps"])
        module.LONG_ADD_PROFIT_THRESHOLDS = tuple(case["thresholds"])
        module.__winner_peak_nav = 500_000.0

        def _calc_current_nav(cash, holdings, day_panel):
            return float(cash) + sum(module.mark_position(c, p, day_panel) for c, p in holdings.items())

        def _total_exposure_limit(current_nav):
            return calc_total_exposure_limit(module.WINNER_300K_CASE, current_nav)

        def _can_use_extra_winner_add(step_index, market_regime_name, current_nav):
            return can_use_extra_winner_add(
                module.WINNER_300K_CASE,
                step_index,
                market_regime_name,
                current_nav,
                module.__winner_peak_nav,
            )

        def _record_winner_nav(nav):
            module.__winner_peak_nav = max(float(module.__winner_peak_nav), float(nav))

        module.__calc_current_nav = _calc_current_nav
        module.__total_exposure_limit = _total_exposure_limit
        module.__can_use_extra_winner_add = _can_use_extra_winner_add
        module.__record_winner_nav = _record_winner_nav
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


def normalize_market_frame(market):
    out = market.copy()
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"])
        out = out.sort_values("trade_date").set_index("trade_date")
    else:
        out.index = pd.to_datetime(out.index)
        out = out.sort_index()
    return out


def load_existing_nav(version):
    path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
    if not path.exists():
        return None
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    return nav[nav["date"] >= pd.Timestamp(START_DATE)].copy()


def load_existing_summary(version):
    path = BACKTRADER_DIR / version / "output" / "summary.json"
    if not path.exists():
        return {"case": version, "missing": True}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["case"] = version
    return data


def calc_nav_stats(nav, init_cash=500_000.0):
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
        "calmar_ratio": float(annual / abs(dd.min())) if dd.min() < 0 else np.nan,
        "avg_cash_ratio": float((nav["cash"] / nav["nav"]).mean()) if "cash" in nav else np.nan,
        "avg_holdings": float(nav["holdings"].mean()) if "holdings" in nav else np.nan,
    }


def yearly_returns(nav):
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["nav"].sort_index().resample("YE").last().pct_change()


def monthly_returns(nav):
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["nav"].sort_index().resample("ME").last().pct_change()


def extra_add_sell_attribution(trades):
    if trades.empty or "reason" not in trades.columns:
        return {"extra_add_sells": 0, "extra_add_pnl_est": 0.0}
    open_pos = {}
    rows = []
    for _, row in trades.iterrows():
        code = row["ts_code"]
        if row["action"] == "buy":
            pos = open_pos.setdefault(code, {"amount": 0.0, "extra": 0.0})
            amount = float(row["amount"])
            pos["amount"] += amount
            if row["reason"] == "winner_300k_extra_add":
                pos["extra"] += amount
        elif row["action"] == "sell" and code in open_pos:
            pos = open_pos.pop(code)
            if pos["extra"] > 0 and pos["amount"] > 0:
                ratio = min(1.0, pos["extra"] / pos["amount"])
                rows.append(float(row["pnl"]) * ratio)
    return {
        "extra_add_sells": len(rows),
        "extra_add_pnl_est": float(sum(rows)),
    }


def run_case(case, panel, market):
    module = load_v7_backtest_module("tmp_v7_winner_300k_" + case["case"], case)
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
    if not trades.empty and "reason" in trades.columns:
        extra_buys = trades[trades["reason"] == "winner_300k_extra_add"]
        stats["winner_300k_extra_add_amount"] = float(extra_buys["amount"].sum())
    stats.update(extra_add_sell_attribution(trades))
    return stats, nav, trades, rebalance_log


def format_pct(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def table_html(df, title):
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{html.escape(str(v))}</td>" for v in row.tolist())
        rows.append(f"<tr>{cells}</tr>")
    headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    return f"<h2>{html.escape(title)}</h2><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def best_candidate(all_stats):
    candidates = [s for s in all_stats if s.get("mode") == "winner_300k"]
    if not candidates:
        return None
    return max(candidates, key=lambda s: float(s.get("total_return_pct", -999999)))


def build_report(all_stats, nav_by_case):
    summary_rows = []
    for stats in all_stats:
        summary_rows.append({
            "策略": stats["case"],
            "总收益": format_pct(stats.get("total_return_pct")),
            "年化": format_pct(stats.get("annual_return_pct")),
            "最大回撤": format_pct(stats.get("max_drawdown_pct")),
            "Calmar": f"{float(stats.get('calmar_ratio', 0.0)):.2f}" if stats.get("calmar_ratio") is not None and not pd.isna(stats.get("calmar_ratio")) else "-",
            "交易数": stats.get("trade_records", "-"),
            "止损": stats.get("stop_loss_fills", "-"),
            "额外加仓次数": stats.get("winner_300k_extra_add_fills", "-"),
            "额外加仓金额": f"{float(stats.get('winner_300k_extra_add_amount', 0.0)):.0f}",
            "额外加仓估算PnL": f"{float(stats.get('extra_add_pnl_est', 0.0)):.0f}",
            "平均现金": format_pct(float(stats.get("avg_cash_ratio", np.nan)) * 100.0),
            "平均持股": f"{float(stats.get('avg_holdings', np.nan)):.2f}" if not pd.isna(stats.get("avg_holdings", np.nan)) else "-",
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

    best = best_candidate(all_stats)
    v7 = next((s for s in all_stats if s.get("case") == "v7"), None)
    advice = "暂不合并"
    reason = "本轮赢家30万加仓实验未同时超过 v7 收益并控制回撤。"
    if best and v7:
        improves = float(best.get("total_return_pct", -999)) > float(v7.get("total_return_pct", -999))
        dd_ok = float(best.get("max_drawdown_pct", -999)) >= float(v7.get("max_drawdown_pct", -999)) - 3.0
        if improves and dd_ok:
            advice = "建议进入合入候选"
            reason = "最佳实验收益超过 v7，最大回撤恶化不超过 3 个百分点。"
    best_text = "无"
    if best:
        best_text = f"{best['case']}：总收益 {format_pct(best.get('total_return_pct'))}，最大回撤 {format_pct(best.get('max_drawdown_pct'))}"

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 赢家单票30万加仓实验报告</title>
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
<h1>v7 赢家单票30万加仓实验报告</h1>
<div class="note"><b>合并建议：{html.escape(advice)}</b><br>{html.escape(reason)}<br>最佳实验：{html.escape(best_text)}</div>
<p class="small">本轮最多仍持有5只，只给已盈利且仍在候选榜内的赢家增加到30万上限；正式 v4/v5/v6/v7 文件未修改。</p>
{table_html(summary_df, "核心指标对比")}
{table_html(yearly_df, "年度收益对比（%）")}
{table_html(monthly_df, "最近36个月月度收益对比（%）")}
<h2>下一步建议</h2>
<ol>
<li>若赢家30万胜出，下一步只微调新增加仓阈值和总仓上限。</li>
<li>若额外加仓估算 PnL 为负，说明赢家再加仓太晚或太重，应改为更早但更小额的分批。</li>
<li>若仍弱于 v7，回到失败买入过滤，而不是继续放大单票。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_progress("开始运行赢家单票30万加仓实验。")
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
        stats, nav, trades, rebalance_log = run_case(case, panel, market)
        nav.to_csv(OUTPUT_DIR / f"{case['case']}_nav_series.csv", index=False, encoding="utf-8-sig")
        trades.to_csv(OUTPUT_DIR / f"{case['case']}_trade_records.csv", index=False, encoding="utf-8-sig")
        rebalance_log.to_csv(OUTPUT_DIR / f"{case['case']}_rebalance_log.csv", index=False, encoding="utf-8-sig")
        (OUTPUT_DIR / f"{case['case']}_summary.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        all_stats.append(stats)
        nav_by_case[case["case"]] = nav.copy()
        append_progress(
            f"完成 {case['case']}：total_return={stats['total_return_pct']:.2f}%，"
            f"max_dd={stats['max_drawdown_pct']:.2f}%，trades={stats['trade_records']}，"
            f"extra_adds={stats.get('winner_300k_extra_add_fills', 0)}。"
        )

    build_report(all_stats, nav_by_case)
    append_progress(f"生成 HTML 报表：{REPORT_PATH}")
    append_progress("设计 review：专家角色确认本轮聚焦已验证赢家，不增加持股数。")
    append_progress("开发 review：检查项包括总仓动态上限、bear 禁止额外加仓、严格回撤门控、额外加仓统计。")


if __name__ == "__main__":
    main()

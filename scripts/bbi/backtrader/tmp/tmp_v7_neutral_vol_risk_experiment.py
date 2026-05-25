from __future__ import annotations

import html
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V7_DIR = BACKTRADER_DIR / "v7"

OUTPUT_DIR = TMP_DIR / "tmp_v7_neutral_vol_risk_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_neutral_vol_risk_README.md"

START_DATE = "2018-01-01"
END_DATE = None
BASE_TOTAL_EXPOSURE = 500_000.0

CASES = [
    {"case": "当前v7复现", "mode": "baseline"},
    {"case": "波动率目标仓位", "mode": "vol_target"},
    {"case": "净值曲线风险预算", "mode": "equity_budget"},
    {"case": "波动率+净值组合预算", "mode": "combined"},
]


def append_progress(message):
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def replace_once(source, old, new):
    if old not in source:
        raise RuntimeError(f"patch anchor not found: {old[:120]}")
    return source.replace(old, new, 1)


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def classify_regime_detail(market_regime_name, snapshot):
    if market_regime_name != "neutral":
        return market_regime_name
    breadth = safe_float(snapshot.get("breadth_above_bbi"))
    slope = safe_float(snapshot.get("market_ma120_slope_20"))
    dd_252 = safe_float(snapshot.get("market_dd_252"))
    breadth_change_5 = safe_float(snapshot.get("breadth_change_5"))
    if any(pd.isna(v) for v in [breadth, slope, dd_252, breadth_change_5]):
        return "neutral_chop"
    if breadth >= 0.50 and slope > 0 and dd_252 > -0.15:
        return "neutral_up"
    if breadth < 0.45 or slope < 0 or dd_252 <= -0.15:
        return "neutral_down"
    if breadth_change_5 >= 0.08:
        return "neutral_repair"
    return "neutral_chop"


def calc_vol_target_multiplier(nav_values, target_annual_vol=0.18, min_mult=0.70, max_mult=1.30):
    if len(nav_values) < 8:
        return 1.0
    nav = pd.Series(nav_values, dtype="float64")
    returns = nav.pct_change().dropna().tail(20)
    if len(returns) < 6:
        return 1.0
    daily_vol = float(returns.std(ddof=0))
    if not math.isfinite(daily_vol) or daily_vol <= 0:
        return max_mult
    target_daily_vol = float(target_annual_vol) / math.sqrt(244.0)
    mult = target_daily_vol / daily_vol
    return max(min_mult, min(max_mult, mult))


def calc_equity_budget_multiplier(current_nav, peak_nav):
    current_nav = float(current_nav)
    peak_nav = max(float(peak_nav), 1.0)
    dd = current_nav / peak_nav - 1.0
    if dd >= -0.05:
        return 1.20
    if dd >= -0.10:
        return 1.00
    if dd >= -0.15:
        return 0.80
    return 0.60


def apply_regime_gate(multiplier, regime_detail):
    multiplier = float(multiplier)
    if regime_detail == "bull":
        return multiplier
    if regime_detail == "neutral_up":
        return multiplier
    if regime_detail == "neutral_repair":
        return min(multiplier, 1.15)
    if regime_detail == "neutral_chop":
        return min(multiplier, 1.0)
    if regime_detail == "neutral_down":
        return min(multiplier, 0.85)
    if regime_detail == "bear":
        return min(multiplier, 0.60)
    return min(multiplier, 1.0)


def calc_case_multiplier(case, regime_detail, current_nav, peak_nav, nav_history):
    mode = case.get("mode", "baseline")
    if mode == "baseline":
        return 1.0
    if mode == "vol_target":
        raw = calc_vol_target_multiplier(nav_history)
    elif mode == "equity_budget":
        raw = calc_equity_budget_multiplier(current_nav, peak_nav)
    elif mode == "combined":
        raw = min(
            calc_vol_target_multiplier(nav_history),
            calc_equity_budget_multiplier(current_nav, peak_nav),
        )
    else:
        raw = 1.0
    return apply_regime_gate(raw, regime_detail)


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
            '        "neutral_vol_risk_case": NEUTRAL_VOL_RISK_CASE.get("case", "baseline"),\n'
            '        "dynamic_budget_signal_days": 0,\n'
            '        "dynamic_budget_capacity_blocks": 0,\n',
        )
        source = replace_once(
            source,
            "                        available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n"
            "                        target_amount = min(target_amount, available_exposure)\n",
            "                        dynamic_total_limit = __dynamic_total_exposure_limit(\n"
            "                            market_regime_name, regime_snapshot, cash, holdings, signal_panel\n"
            "                        )\n"
            "                        available_exposure = dynamic_total_limit - calc_total_exposure(holdings)\n"
            "                        target_amount = min(target_amount, available_exposure)\n",
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
            "                    dynamic_total_limit = __dynamic_total_exposure_limit(\n"
            "                        market_regime_name, regime_snapshot, cash, holdings, signal_panel\n"
            "                    )\n"
            "                    available_exposure = dynamic_total_limit - calc_total_exposure(holdings)\n"
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
            "        __record_nav_for_budget(nav)\n",
        )

        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.NEUTRAL_VOL_RISK_CASE = dict(case)
        module.__budget_nav_history = []
        module.__budget_peak_nav = 500_000.0

        def _calc_current_nav(cash, holdings, day_panel):
            return float(cash) + sum(module.mark_position(c, p, day_panel) for c, p in holdings.items())

        def _dynamic_total_exposure_limit(market_regime_name, regime_snapshot, cash, holdings, signal_panel):
            current_nav = _calc_current_nav(cash, holdings, signal_panel)
            peak_nav = max(float(module.__budget_peak_nav), current_nav)
            detail = classify_regime_detail(market_regime_name, regime_snapshot)
            mult = calc_case_multiplier(
                module.NEUTRAL_VOL_RISK_CASE,
                detail,
                current_nav,
                peak_nav,
                module.__budget_nav_history,
            )
            if module.NEUTRAL_VOL_RISK_CASE.get("mode") != "baseline":
                module.__dict__.setdefault("__budget_mult_samples", []).append(mult)
            return BASE_TOTAL_EXPOSURE * mult

        def _record_nav_for_budget(nav):
            nav = float(nav)
            module.__budget_nav_history.append(nav)
            module.__budget_peak_nav = max(float(module.__budget_peak_nav), nav)

        module.__dynamic_total_exposure_limit = _dynamic_total_exposure_limit
        module.__record_nav_for_budget = _record_nav_for_budget
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


def build_regime_detail_frame(market, panel):
    regime = market.copy().sort_index()
    close = pd.to_numeric(regime["close"], errors="coerce")
    regime["ma120"] = close.rolling(120, min_periods=120).mean()
    regime["ma200"] = close.rolling(200, min_periods=200).mean()
    regime["market_ma120_slope_20"] = regime["ma120"] / regime["ma120"].shift(20) - 1.0
    regime["market_dd_252"] = close / close.rolling(252, min_periods=120).max() - 1.0

    breadth = panel[["trade_date", "ts_code", "is_eligible", "above_bbi"]].copy()
    breadth = breadth[breadth["is_eligible"].fillna(False)]
    breadth["above_bbi_num"] = breadth["above_bbi"].fillna(False).astype(float)
    breadth_daily = breadth.groupby("trade_date").agg(
        breadth_above_bbi=("above_bbi_num", "mean"),
    )
    regime = regime.join(breadth_daily, how="left")
    regime["breadth_change_5"] = regime["breadth_above_bbi"] - regime["breadth_above_bbi"].shift(5)

    def coarse(row):
        values = [
            safe_float(row.get("close")),
            safe_float(row.get("ma120")),
            safe_float(row.get("ma200")),
            safe_float(row.get("market_ma120_slope_20")),
            safe_float(row.get("market_dd_252")),
            safe_float(row.get("breadth_above_bbi")),
        ]
        if any(pd.isna(v) for v in values):
            return "unknown"
        close_v, ma120, ma200, slope, dd_252, breadth_v = values
        if dd_252 <= -0.20:
            return "bear"
        if close_v < ma120 and slope < 0 and breadth_v < 0.45:
            return "bear"
        if close_v > ma120 and close_v > ma200 and slope > 0 and dd_252 > -0.10 and breadth_v >= 0.55:
            return "bull"
        return "neutral"

    regime["market_regime"] = regime.apply(coarse, axis=1)
    regime["regime_detail"] = regime.apply(
        lambda row: classify_regime_detail(
            row["market_regime"],
            {
                "breadth_above_bbi": row.get("breadth_above_bbi"),
                "market_ma120_slope_20": row.get("market_ma120_slope_20"),
                "market_dd_252": row.get("market_dd_252"),
                "breadth_change_5": row.get("breadth_change_5"),
            },
        ),
        axis=1,
    )
    # Signals observed on day T are tradable on the next trading day in v7.
    out = regime[["market_regime", "regime_detail"]].reset_index()
    out = out.rename(columns={out.columns[0]: "date"})
    out["date"] = out["date"].shift(-1)
    out = out[out["date"].notna()].copy()
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


def regime_detail_contrib(nav, detail_frame):
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["ret"] = frame["nav"].pct_change().fillna(0.0)
    frame["logret"] = np.log1p(frame["ret"])
    merged = frame.merge(detail_frame, on="date", how="left")
    out = merged.groupby("regime_detail").agg(
        days=("date", "count"),
        avg_holdings=("holdings", "mean"),
        avg_cash_ratio=("cash", lambda s: float((s / merged.loc[s.index, "nav"]).mean())),
        log_sum=("logret", "sum"),
    )
    out["compound_pct"] = (np.exp(out["log_sum"]) - 1.0) * 100.0
    return out.reset_index()[["regime_detail", "days", "avg_holdings", "avg_cash_ratio", "compound_pct"]]


def run_case(case, panel, market):
    module = load_v7_backtest_module("tmp_v7_neutral_vol_risk_" + case["case"], case)
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
    samples = module.__dict__.get("__budget_mult_samples", [])
    stats["avg_budget_multiplier"] = float(np.mean(samples)) if samples else 1.0
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
    candidates = [s for s in all_stats if s.get("mode") in {"vol_target", "equity_budget", "combined"}]
    if not candidates:
        return None
    return max(candidates, key=lambda s: float(s.get("total_return_pct", -999999)))


def build_report(all_stats, nav_by_case, detail_frame):
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
            "平均现金": format_pct(float(stats.get("avg_cash_ratio", np.nan)) * 100.0),
            "平均持股": f"{float(stats.get('avg_holdings', np.nan)):.2f}" if not pd.isna(stats.get("avg_holdings", np.nan)) else "-",
            "平均预算系数": f"{float(stats.get('avg_budget_multiplier', 1.0)):.2f}",
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

    contrib_tables = []
    for name in ["v7", "当前v7复现", "波动率目标仓位", "净值曲线风险预算", "波动率+净值组合预算"]:
        if name in nav_by_case:
            contrib = regime_detail_contrib(nav_by_case[name], detail_frame).round(4)
            contrib.insert(0, "策略", name)
            contrib_tables.append(contrib)
    contrib_df = pd.concat(contrib_tables, ignore_index=True) if contrib_tables else pd.DataFrame()
    if not contrib_df.empty:
        contrib_df["avg_cash_ratio"] = (contrib_df["avg_cash_ratio"] * 100.0).round(2).astype(str) + "%"
        contrib_df["compound_pct"] = contrib_df["compound_pct"].round(2).astype(str) + "%"

    best = best_candidate(all_stats)
    v7 = next((s for s in all_stats if s.get("case") == "v7"), None)
    advice = "暂不合并"
    reason = "本轮仓位预算实验未同时超过 v7 收益并控制回撤。"
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
<title>v7 neutral 拆分与风险预算仓位实验报告</title>
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
<h1>v7 neutral 拆分与风险预算仓位实验报告</h1>
<div class="note"><b>合并建议：{html.escape(advice)}</b><br>{html.escape(reason)}<br>最佳实验：{html.escape(best_text)}</div>
<p class="small">本轮不新增 Tushare 盘后数据，只使用 v7 已有市场状态、广度、净值。正式 v4/v5/v6/v7 文件未修改。</p>
{table_html(summary_df, "核心指标对比")}
{table_html(yearly_df, "年度收益对比（%）")}
{table_html(monthly_df, "最近36个月月度收益对比（%）")}
{table_html(contrib_df, "细分市场状态收益贡献")}
<h2>下一步建议</h2>
<ol>
<li>若仓位预算未超过 v7，说明 v7 的收益瓶颈不在总仓位，而在买入质量和状态识别。</li>
<li>优先分析 neutral_up / neutral_repair / neutral_down 中哪些买入贡献亏损。</li>
<li>下一轮做失败买入过滤：按状态细分、候选排名、买入后 20/63 日收益筛掉拖累交易。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_progress("开始运行 neutral 拆分与风险预算仓位实验。")
    panel = pd.read_parquet(V7_DIR / "output" / "panel.parquet")
    market = pd.read_parquet(V7_DIR / "output" / "market_index.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = normalize_market_frame(market)
    detail_frame = build_regime_detail_frame(market, panel)
    detail_frame["date"] = pd.to_datetime(detail_frame["date"])
    append_progress(f"加载 v7 panel rows={len(panel):,}，生成状态细分 rows={len(detail_frame):,}。")

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
            f"avg_budget={stats.get('avg_budget_multiplier', 1.0):.2f}"
        )

    build_report(all_stats, nav_by_case, detail_frame)
    append_progress(f"生成 HTML 报表：{REPORT_PATH}")
    append_progress("设计 review：专家角色确认本轮先拆 neutral，再测试风险预算，不继续粗暴扩持股数。")
    append_progress("开发 review：检查项包括 signal_date 口径、最多5只约束、预算系数门控、状态细分贡献。")


if __name__ == "__main__":
    main()

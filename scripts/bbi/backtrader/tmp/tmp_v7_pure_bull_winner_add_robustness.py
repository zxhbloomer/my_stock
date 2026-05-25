from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V7_DIR = BACKTRADER_DIR / "v7"
SOURCE_EXPERIMENT = TMP_DIR / "tmp_v7_pure_bull_winner_add_experiment.py"
SOURCE_OUTPUT = TMP_DIR / "tmp_v7_pure_bull_winner_add_output"
OUTPUT_DIR = TMP_DIR / "tmp_v7_pure_bull_winner_add_robustness_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_pure_bull_winner_add_robustness_README.md"
TRUNCATION_RESULTS_PATH = TMP_DIR / "tmp_v7_pure_bull_winner_add_truncation_recompute_output" / "truncation_recompute_results.csv"

START_DATE = pd.Timestamp("2018-01-01")
BEST_CASE = "纯牛市小额最后加仓"
BASELINE_CASE = "当前v7复现"


def append_progress(message):
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def load_nav(path):
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    return nav[nav["date"] >= START_DATE].copy()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


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
        "worst_month_pct": float(period_return_table({"x": nav}, "ME")["x"].min()),
    }


def period_return_table(nav_map, freq):
    series_by_name = {}
    for name, nav in nav_map.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        period_nav = frame.set_index("date")["nav"].sort_index().resample(freq).last().dropna()
        returns = period_nav.pct_change().dropna() * 100.0
        series_by_name[name] = returns
    table = pd.DataFrame(series_by_name).round(2).reset_index()
    if table.empty:
        return pd.DataFrame(columns=["period", *nav_map.keys()])
    if freq.upper().startswith("Y"):
        table["date"] = table["date"].dt.strftime("%Y")
    else:
        table["date"] = table["date"].dt.strftime("%Y-%m")
    return table.rename(columns={"date": "period"})


def annual_return_table(nav_map):
    rows_by_name = {}
    for name, nav in nav_map.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.sort_values("date")
        year_end_nav = frame.set_index("date")["nav"].resample("YE").last().dropna()
        if year_end_nav.empty:
            rows_by_name[name] = pd.Series(dtype=float)
            continue
        previous = year_end_nav.shift(1)
        previous.iloc[0] = float(frame["nav"].iloc[0])
        rows_by_name[name] = (year_end_nav / previous - 1.0) * 100.0
    table = pd.DataFrame(rows_by_name).round(2).reset_index()
    if table.empty:
        return pd.DataFrame(columns=["period", *nav_map.keys()])
    table["date"] = table["date"].dt.strftime("%Y")
    return table.rename(columns={"date": "period"})


def validate_extra_add_audit(audit, require_evidence=False):
    required_cols = {"date", "signal_date", "market_regime"}
    if audit.empty:
        missing_evidence = 1 if require_evidence else 0
        return {
            "rows": 0,
            "non_bull_rows": 0,
            "lookahead_rows": 0,
            "missing_evidence": missing_evidence,
            "passed": missing_evidence == 0,
        }
    missing = required_cols - set(audit.columns)
    if missing:
        return {
            "rows": int(len(audit)),
            "non_bull_rows": int(len(audit)),
            "lookahead_rows": int(len(audit)),
            "missing_evidence": int(len(audit)),
            "passed": False,
            "missing_cols": ",".join(sorted(missing)),
        }
    frame = audit.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["signal_date"] = pd.to_datetime(frame["signal_date"])
    non_bull_rows = int((frame["market_regime"] != "bull").sum())
    signal_date_out_of_bounds = int((frame["signal_date"] >= frame["date"]).sum())
    return {
        "rows": int(len(frame)),
        "non_bull_rows": non_bull_rows,
        "lookahead_rows": signal_date_out_of_bounds,
        "missing_evidence": 0,
        "passed": non_bull_rows == 0 and signal_date_out_of_bounds == 0,
    }


def extra_add_contribution_stats(trades):
    if trades.empty or "reason" not in trades.columns:
        return {
            "extra_add_sells": 0,
            "extra_add_pnl_est": 0.0,
            "top_contribution_ratio": 0.0,
            "passed": False,
        }
    open_pos = {}
    contributions = []
    for _, row in trades.iterrows():
        code = row.get("ts_code")
        action = row.get("action")
        if action == "buy":
            amount = float(row.get("amount", 0.0) or 0.0)
            pos = open_pos.setdefault(code, {"amount": 0.0, "extra": 0.0})
            pos["amount"] += amount
            if row.get("reason") == "pure_bull_extra_add":
                pos["extra"] += amount
        elif action == "sell" and code in open_pos:
            pos = open_pos.pop(code)
            if pos["extra"] > 0 and pos["amount"] > 0:
                pnl = pd.to_numeric(pd.Series([row.get("pnl")]), errors="coerce").iloc[0]
                pnl = 0.0 if pd.isna(pnl) else float(pnl)
                contributions.append(pnl * min(1.0, pos["extra"] / pos["amount"]))
    total_abs = float(sum(abs(v) for v in contributions))
    top_ratio = float(max((abs(v) for v in contributions), default=0.0) / total_abs) if total_abs > 0 else 0.0
    return {
        "extra_add_sells": int(len(contributions)),
        "extra_add_pnl_est": float(sum(contributions)),
        "top_contribution_ratio": top_ratio,
        "passed": len(contributions) >= 3 and top_ratio <= 0.70,
    }


def scan_no_lookahead_precheck(source):
    has_signal_lag = "signal_date = all_dates[i - 1]" in source
    uses_signal_regime = "get_market_regime(market_regime, signal_date)" in source
    uses_current_regime = "get_market_regime(market_regime, date)" in source
    return {
        "has_signal_lag": bool(has_signal_lag),
        "uses_signal_regime": bool(uses_signal_regime),
        "uses_current_regime": bool(uses_current_regime),
        "passed": bool(has_signal_lag and uses_signal_regime and not uses_current_regime),
    }


def regime_return_table(nav, rebalance_log):
    if nav.empty or rebalance_log.empty:
        return pd.DataFrame(columns=["market_regime", "days", "return_pct", "worst_day_pct"])
    nav_frame = nav[["date", "nav"]].copy().sort_values("date")
    nav_frame["daily_ret"] = nav_frame["nav"].pct_change()
    log = rebalance_log[["date", "market_regime"]].copy()
    log["date"] = pd.to_datetime(log["date"])
    merged = nav_frame.merge(log, on="date", how="left")
    merged["market_regime"] = merged["market_regime"].fillna("unknown")
    rows = []
    for regime, group in merged.dropna(subset=["daily_ret"]).groupby("market_regime"):
        returns = group["daily_ret"].dropna()
        rows.append(
            {
                "market_regime": regime,
                "days": int(len(returns)),
                "return_pct": float(((1.0 + returns).prod() - 1.0) * 100.0),
                "worst_day_pct": float(returns.min() * 100.0),
            }
        )
    return pd.DataFrame(rows).sort_values("market_regime").reset_index(drop=True)


def html_table(df, title, max_rows=None):
    frame = df.copy()
    if max_rows is not None and len(frame) > max_rows:
        frame = frame.tail(max_rows)
    headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in frame.columns)
    body = []
    for _, row in frame.iterrows():
        body.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row.tolist()) + "</tr>")
    return f"<h2>{html.escape(title)}</h2><table><thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def fmt_pct(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def collect_inputs():
    nav_by_name = {}
    summary_rows = []
    for version in ["v4", "v5", "v6", "v7"]:
        nav_path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
        summary_path = BACKTRADER_DIR / version / "output" / "summary.json"
        if not nav_path.exists() or not summary_path.exists():
            continue
        nav = load_nav(nav_path)
        stats = calc_nav_stats(nav)
        stats.update(load_json(summary_path))
        stats["case"] = version
        nav_by_name[version] = nav
        summary_rows.append(stats)
    for name in [BASELINE_CASE, "纯牛市赢家30万", "严格纯牛市赢家30万", BEST_CASE]:
        nav_path = SOURCE_OUTPUT / f"{name}_nav_series.csv"
        summary_path = SOURCE_OUTPUT / f"{name}_summary.json"
        if not nav_path.exists() or not summary_path.exists():
            continue
        nav = load_nav(nav_path)
        stats = calc_nav_stats(nav)
        stats.update(load_json(summary_path))
        stats["case"] = name
        nav_by_name[name] = nav
        summary_rows.append(stats)
    return nav_by_name, summary_rows


def build_summary_table(summary_rows):
    rows = []
    for stats in summary_rows:
        rows.append(
            {
                "策略": stats.get("case"),
                "总收益": fmt_pct(stats.get("total_return_pct")),
                "年化": fmt_pct(stats.get("annual_return_pct")),
                "最大回撤": fmt_pct(stats.get("max_drawdown_pct")),
                "最差月": fmt_pct(stats.get("worst_month_pct")),
                "交易数": stats.get("trade_records", "-"),
                "额外加仓": stats.get("pure_bull_extra_add_fills", "-"),
            }
        )
    return pd.DataFrame(rows)


def build_audit_table():
    rows = []
    for name in [BASELINE_CASE, "纯牛市赢家30万", "严格纯牛市赢家30万", BEST_CASE]:
        audit_path = SOURCE_OUTPUT / f"{name}_extra_add_audit.csv"
        trades_path = SOURCE_OUTPUT / f"{name}_trade_records.csv"
        audit = pd.read_csv(audit_path) if audit_path.exists() else pd.DataFrame()
        trades = pd.read_csv(trades_path) if trades_path.exists() else pd.DataFrame()
        gate = validate_extra_add_audit(audit, require_evidence=name != BASELINE_CASE)
        contrib = extra_add_contribution_stats(trades)
        rows.append(
            {
                "策略": name,
                "额外买入": gate["rows"],
                "非bull": gate["non_bull_rows"],
                "信号日期越界": gate["lookahead_rows"],
                "缺少证据": gate.get("missing_evidence", 0),
                "审计通过": "是" if gate["passed"] else "否",
                "卖出归因数": contrib["extra_add_sells"],
                "粗估PnL": round(contrib["extra_add_pnl_est"], 0),
                "最大单笔占比": f"{contrib['top_contribution_ratio'] * 100.0:.1f}%",
                "集中度通过": "是" if contrib["passed"] else "否",
            }
        )
    return pd.DataFrame(rows)


def signal_fill_table():
    rows = []
    for name in ["纯牛市赢家30万", "严格纯牛市赢家30万", BEST_CASE]:
        summary_path = SOURCE_OUTPUT / f"{name}_summary.json"
        audit_path = SOURCE_OUTPUT / f"{name}_extra_add_audit.csv"
        if not summary_path.exists():
            continue
        summary = load_json(summary_path)
        audit = pd.read_csv(audit_path) if audit_path.exists() else pd.DataFrame()
        signals = int(summary.get("pure_bull_extra_add_signals", 0))
        fills = int(summary.get("pure_bull_extra_add_fills", 0))
        rows.append(
            {
                "策略": name,
                "额外信号": signals,
                "实际成交": fills,
                "未成交": max(0, signals - fills),
                "成交率": f"{(fills / signals * 100.0):.1f}%" if signals else "-",
                "当前解释": "候选仍在榜且盈利达标后，还会受现金、总敞口、涨跌停、100股约束影响；需逐日截断重算确认。",
            }
        )
    return pd.DataFrame(rows)


def load_truncation_results():
    if not TRUNCATION_RESULTS_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(TRUNCATION_RESULTS_PATH)


def truncation_gate(truncation_df):
    if truncation_df.empty or "passed" not in truncation_df.columns:
        return False
    passed = truncation_df["passed"].astype(str).str.lower().isin(["true", "1", "yes", "是"])
    return bool(len(truncation_df) > 0 and passed.all())


def build_regime_tables():
    tables = []
    for name in [BASELINE_CASE, BEST_CASE]:
        nav_path = SOURCE_OUTPUT / f"{name}_nav_series.csv"
        rebalance_path = SOURCE_OUTPUT / f"{name}_rebalance_log.csv"
        if not nav_path.exists() or not rebalance_path.exists():
            continue
        regime = regime_return_table(load_nav(nav_path), pd.read_csv(rebalance_path))
        regime.insert(0, "策略", name)
        tables.append(regime)
    if not tables:
        return pd.DataFrame()
    return pd.concat(tables, ignore_index=True).round(2)


def build_decision(summary_rows, audit_df, source_scan, annual_df, truncation_df=None):
    truncation_df = pd.DataFrame() if truncation_df is None else truncation_df
    by_case = {row.get("case"): row for row in summary_rows}
    if BEST_CASE not in by_case or "v7" not in by_case:
        gates = {
            "数据完整": False,
            "收益超过v7": False,
            "回撤不恶化3pct": False,
            "源码时序初筛": False,
            "额外加仓审计": False,
            "单笔集中度": False,
            "年度不过度单点": False,
            "截断重算": truncation_gate(truncation_df),
            "参数邻域稳定": False,
            "成本压力": False,
        }
        return "数据不完整，无法判断", gates
    best = by_case[BEST_CASE]
    v7 = by_case["v7"]
    best_ret = float(best.get("total_return_pct"))
    v7_ret = float(v7.get("total_return_pct"))
    best_dd = float(best.get("max_drawdown_pct"))
    v7_dd = float(v7.get("max_drawdown_pct"))
    audit_row = audit_df[audit_df["策略"].eq(BEST_CASE)]
    audit_ok = bool(not audit_row.empty and audit_row.iloc[0]["审计通过"] == "是")
    concentration_ok = bool(not audit_row.empty and audit_row.iloc[0]["集中度通过"] == "是")
    annual_ok = False
    if not annual_df.empty and "v7" in annual_df and BEST_CASE in annual_df:
        delta = pd.to_numeric(annual_df[BEST_CASE], errors="coerce") - pd.to_numeric(annual_df["v7"], errors="coerce")
        annual_ok = int((delta > 0).sum()) >= max(2, int(delta.notna().sum() * 0.4))
    gates = {
        "数据完整": True,
        "收益超过v7": best_ret > v7_ret,
        "回撤不恶化3pct": best_dd >= v7_dd - 3.0,
        "源码时序初筛": source_scan["passed"],
        "额外加仓审计": audit_ok,
        "单笔集中度": concentration_ok,
        "年度不过度单点": annual_ok,
        "截断重算": truncation_gate(truncation_df),
        "参数邻域稳定": False,
        "成本压力": False,
    }
    passed_count = sum(1 for ok in gates.values() if ok)
    if all(gates.values()):
        advice = "建议进入正式v7合入候选"
    elif passed_count >= 4 and best_ret > v7_ret:
        advice = "继续观察，不直接合并"
    else:
        advice = "暂不合并"
    return advice, gates


def render_report(summary_df, annual_df, monthly_df, audit_df, regime_df, truncation_df, source_scan, advice, gates):
    gate_df = pd.DataFrame([{"检查项": key, "是否通过": "是" if value else "否"} for key, value in gates.items()])
    source_df = pd.DataFrame([source_scan])
    signal_df = signal_fill_table()
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7纯牛市赢家加仓稳健性验证</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #1f2937; }}
h1 {{ font-size: 24px; margin: 0 0 8px; }}
h2 {{ font-size: 18px; margin-top: 22px; }}
.note {{ background: #f3f4f6; border-left: 4px solid #2563eb; padding: 12px 14px; margin: 14px 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 8px; }}
th, td {{ border: 1px solid #d1d5db; padding: 7px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #374151; color: white; }}
.small {{ color: #6b7280; font-size: 12px; }}
</style>
</head>
<body>
<h1>v7纯牛市赢家加仓稳健性验证</h1>
<div class="note"><b>合并建议：{html.escape(advice)}</b><br>本报告是初筛摘要，不是无未来函数证明。参数邻域和成本压力未完成前，不合并正式 v7。</div>
<p class="small">时序口径：交易发生在 rebalance date，信号和市场状态应来自前一交易日 signal_date；当前仅做源码时序字符串初筛和 audit 日期检查，不能替代逐笔截断重算。</p>
{html_table(gate_df, "合并门槛检查")}
{html_table(summary_df, "核心指标对比")}
{html_table(audit_df, "额外加仓审计")}
{html_table(signal_df, "额外信号到成交")}
{html_table(truncation_df, "截断重算结果")}
{html_table(source_df, "源码时序初筛")}
{html_table(regime_df, "按市场状态拆解")}
{html_table(annual_df, "年度收益对比（%）")}
{html_table(monthly_df, "最近36个月月度收益对比（%）", max_rows=36)}
<h2>下一步</h2>
<ol>
<li>补做参数邻域：阈值 0.45/0.50/0.55，金额 3万/5万/7万。</li>
<li>补做成本压力：当前成本、双倍成本、20bps滑点。</li>
<li>若参数邻域或成本压力未通过，保持在 tmp，不合入正式 v7。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_progress("开始稳健性验证，不重新选择规则。")
    nav_by_name, summary_rows = collect_inputs()
    summary_df = build_summary_table(summary_rows)
    annual_df = annual_return_table(nav_by_name)
    monthly_df = period_return_table(nav_by_name, "ME")
    audit_df = build_audit_table()
    regime_df = build_regime_tables()
    truncation_df = load_truncation_results()
    source_text = (V7_DIR / "20_run_backtest.py").read_text(encoding="utf-8") + "\n" + SOURCE_EXPERIMENT.read_text(encoding="utf-8")
    source_scan = scan_no_lookahead_precheck(source_text)
    advice, gates = build_decision(summary_rows, audit_df, source_scan, annual_df, truncation_df)

    summary_df.to_csv(OUTPUT_DIR / "summary_compare.csv", index=False, encoding="utf-8-sig")
    annual_df.to_csv(OUTPUT_DIR / "annual_returns.csv", index=False, encoding="utf-8-sig")
    monthly_df.to_csv(OUTPUT_DIR / "monthly_returns.csv", index=False, encoding="utf-8-sig")
    audit_df.to_csv(OUTPUT_DIR / "extra_add_audit_summary.csv", index=False, encoding="utf-8-sig")
    regime_df.to_csv(OUTPUT_DIR / "regime_returns.csv", index=False, encoding="utf-8-sig")
    truncation_df.to_csv(OUTPUT_DIR / "truncation_recompute_results.csv", index=False, encoding="utf-8-sig")
    (OUTPUT_DIR / "decision.json").write_text(
        json.dumps({"advice": advice, "gates": gates, "source_scan": source_scan}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_report(summary_df, annual_df, monthly_df, audit_df, regime_df, truncation_df, source_scan, advice, gates)
    append_progress(f"生成稳健性报表：{REPORT_PATH}")
    append_progress(f"合并建议：{advice}")


if __name__ == "__main__":
    main()

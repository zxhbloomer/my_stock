import csv
from contextlib import contextmanager
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v6").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V4_SUMMARY_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v4" / "output" / "summary.json"
V5_SUMMARY_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v5" / "output" / "summary.json"
V6_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v6"
OUTPUT_DIR = Path(__file__).parent / "v6_moneyflow_evolution_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"
REPORT_PATH = OUTPUT_DIR / "report.html"


POST_CLOSE_COLUMNS = [
    "net_mf_amount",
    "buy_lg_amount",
    "sell_lg_amount",
    "buy_elg_amount",
    "sell_elg_amount",
    "winner_rate",
    "weight_avg",
]


CASES = [
    {"name": "baseline_v6", "type": "baseline"},
    {"name": "flow_net_ma5_positive", "type": "filter_positive", "column": "flow_net_amount_ma5"},
    {"name": "flow_big_ma5_positive", "type": "filter_positive", "column": "flow_big_amount_ma5"},
    {"name": "flow_net_rank_top70", "type": "rank_top_pct", "column": "flow_net_rate_ma5", "keep_pct": 0.70},
    {"name": "cyq_winner_mid", "type": "cyq_winner_mid"},
    {"name": "flow_score_boost_015", "type": "score_boost", "column": "flow_net_rate_ma5", "weight": 0.15},
    {"name": "flow_big_score_boost_015", "type": "score_boost", "column": "flow_big_rate_ma5", "weight": 0.15},
    {"name": "flow_and_cyq_combo", "type": "combo"},
]


def load_module_from_path(module_name, path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_v6_module():
    return load_module_from_path("v6_run_backtest_moneyflow_evolution", V6_DIR / "20_run_backtest.py")


def shift_post_close_features(df, columns):
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    for col in columns:
        if col in out.columns:
            out[col] = out.groupby("ts_code", sort=False)[col].shift(1)
    return out


def rolling_mean_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .mean()
        .reset_index(level=0, drop=True)
    )


def zscore(series):
    series = pd.to_numeric(series, errors="coerce")
    std = series.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def load_extra_features_from_db(v6_config, start_date, end_date):
    engine = create_engine(v6_config.DB_URL)
    params = {"start_date": start_date, "end_date": end_date}
    with engine.connect() as conn:
        moneyflow = pd.read_sql_query(
            text(f"""
                select
                    ts_code,
                    trade_date,
                    net_mf_amount,
                    buy_lg_amount,
                    sell_lg_amount,
                    buy_elg_amount,
                    sell_elg_amount
                from {v6_config.SCHEMA}."080_moneyflow"
                where trade_date >= :start_date and trade_date <= :end_date
            """),
            conn,
            params=params,
        )
        cyq = pd.read_sql_query(
            text(f"""
                select
                    ts_code,
                    trade_date,
                    winner_rate,
                    weight_avg
                from {v6_config.SCHEMA}."061_cyq_perf"
                where trade_date >= :start_date and trade_date <= :end_date
            """),
            conn,
            params=params,
        )
    extra = moneyflow.merge(cyq, on=["ts_code", "trade_date"], how="outer")
    return shift_post_close_features(extra, POST_CLOSE_COLUMNS)


def add_moneyflow_features(panel, extra):
    panel = panel.copy()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    extra = extra.copy()
    extra["trade_date"] = pd.to_datetime(extra["trade_date"])
    merged = panel.merge(extra, on=["ts_code", "trade_date"], how="left")
    merged = merged.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    merged["flow_big_amount"] = (
        pd.to_numeric(merged["buy_lg_amount"], errors="coerce").fillna(0.0)
        + pd.to_numeric(merged["buy_elg_amount"], errors="coerce").fillna(0.0)
        - pd.to_numeric(merged["sell_lg_amount"], errors="coerce").fillna(0.0)
        - pd.to_numeric(merged["sell_elg_amount"], errors="coerce").fillna(0.0)
    )
    amount_base = pd.to_numeric(merged["amount"], errors="coerce").replace(0, np.nan)
    merged["flow_net_rate"] = pd.to_numeric(merged["net_mf_amount"], errors="coerce") / amount_base
    merged["flow_big_rate"] = merged["flow_big_amount"] / amount_base
    merged["flow_net_amount_ma5"] = rolling_mean_by_code(merged, "net_mf_amount", 5)
    merged["flow_big_amount_ma5"] = rolling_mean_by_code(merged, "flow_big_amount", 5)
    merged["flow_net_rate_ma5"] = rolling_mean_by_code(merged, "flow_net_rate", 5)
    merged["flow_big_rate_ma5"] = rolling_mean_by_code(merged, "flow_big_rate", 5)
    merged["flow_net_rate_ma20"] = rolling_mean_by_code(merged, "flow_net_rate", 20)
    merged["cyq_price_vs_weight_avg"] = (
        pd.to_numeric(merged["close_qfq"], errors="coerce")
        / pd.to_numeric(merged["weight_avg"], errors="coerce")
        - 1.0
    )
    return merged


def apply_case_to_candidates(candidates, case):
    candidates = candidates.copy()
    diagnostics = {
        "input_candidates": int(len(candidates)),
        "blocked_candidates": 0,
        "missing_feature_rows": 0,
    }
    if candidates.empty or case["type"] == "baseline":
        return candidates, diagnostics

    if case["type"] == "filter_positive":
        col = case["column"]
        values = pd.to_numeric(candidates.get(col), errors="coerce")
        mask = values.notna() & (values > 0)
        diagnostics["missing_feature_rows"] = int(values.isna().sum())
        diagnostics["blocked_candidates"] = int((~mask).sum())
        return candidates[mask].copy(), diagnostics

    if case["type"] == "rank_top_pct":
        col = case["column"]
        values = pd.to_numeric(candidates.get(col), errors="coerce")
        diagnostics["missing_feature_rows"] = int(values.isna().sum())
        if values.notna().sum() == 0:
            diagnostics["blocked_candidates"] = int(len(candidates))
            return candidates.iloc[0:0].copy(), diagnostics
        cutoff = values.quantile(1.0 - float(case["keep_pct"]))
        mask = values.notna() & (values >= cutoff)
        diagnostics["blocked_candidates"] = int((~mask).sum())
        return candidates[mask].copy(), diagnostics

    if case["type"] == "cyq_winner_mid":
        winner = pd.to_numeric(candidates.get("winner_rate"), errors="coerce")
        price_vs_cost = pd.to_numeric(candidates.get("cyq_price_vs_weight_avg"), errors="coerce")
        mask = winner.between(35.0, 85.0, inclusive="both") & (price_vs_cost > 0)
        diagnostics["missing_feature_rows"] = int((winner.isna() | price_vs_cost.isna()).sum())
        diagnostics["blocked_candidates"] = int((~mask).sum())
        return candidates[mask].copy(), diagnostics

    if case["type"] == "score_boost":
        col = case["column"]
        values = pd.to_numeric(candidates.get(col), errors="coerce")
        diagnostics["missing_feature_rows"] = int(values.isna().sum())
        candidates["score"] = candidates["score"] + float(case["weight"]) * zscore(values.fillna(values.median()))
        sort_cols = [col for col in ["score", "above_ratio_63", "ret_63", "amount_ma20"] if col in candidates.columns]
        return candidates.sort_values(
            sort_cols,
            ascending=[False] * len(sort_cols),
        ), diagnostics

    if case["type"] == "combo":
        flow = pd.to_numeric(candidates.get("flow_net_rate_ma5"), errors="coerce")
        big = pd.to_numeric(candidates.get("flow_big_rate_ma5"), errors="coerce")
        winner = pd.to_numeric(candidates.get("winner_rate"), errors="coerce")
        price_vs_cost = pd.to_numeric(candidates.get("cyq_price_vs_weight_avg"), errors="coerce")
        mask = (
            (flow > 0)
            & (big > 0)
            & winner.between(35.0, 85.0, inclusive="both")
            & (price_vs_cost > 0)
        )
        diagnostics["missing_feature_rows"] = int((flow.isna() | big.isna() | winner.isna() | price_vs_cost.isna()).sum())
        diagnostics["blocked_candidates"] = int((~mask).sum())
        return candidates[mask].copy(), diagnostics

    raise ValueError(f"Unknown case type: {case['type']}")


@contextmanager
def patched_score_candidates(v6, case, diagnostics):
    original_score_candidates = v6.score_candidates

    def wrapped_score_candidates(signal_panel, diagnostics=None):
        candidates = original_score_candidates(signal_panel, diagnostics=diagnostics)
        filtered, case_diag = apply_case_to_candidates(candidates, case)
        for key, value in case_diag.items():
            diagnostics_key = f"case_{key}"
            if diagnostics is not None:
                diagnostics[diagnostics_key] = diagnostics.get(diagnostics_key, 0) + int(value)
        return filtered

    try:
        v6.score_candidates = wrapped_score_candidates
        yield
    finally:
        v6.score_candidates = original_score_candidates


def calc_nav_stats(nav_df):
    nav_df = nav_df.copy()
    nav_df["date"] = pd.to_datetime(nav_df["date"])
    total_ret = nav_df["nav"].iloc[-1] / nav_df["nav"].iloc[0] - 1.0
    days = max((nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    curve = nav_df["nav"] / nav_df["nav"].iloc[0]
    dd = curve / curve.cummax() - 1.0
    max_dd = float(dd.min() * 100.0)
    annual_pct = float(annual_ret * 100.0)
    return {
        "start_date": str(nav_df["date"].iloc[0])[:10],
        "end_date": str(nav_df["date"].iloc[-1])[:10],
        "final_nav": round(float(nav_df["nav"].iloc[-1]), 2),
        "total_return_pct": round(float(total_ret * 100.0), 4),
        "annual_return_pct": round(annual_pct, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "calmar_ratio": round(annual_pct / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "avg_cash_pct": round(float((nav_df["cash"] / nav_df["nav"]).mean() * 100.0), 4),
        "avg_holdings": round(float(nav_df["holdings"].mean()), 4),
    }


def summarize_period(nav_df, trades_df, start, end):
    nav_dates = pd.to_datetime(nav_df["date"])
    nav_sub = nav_df[(nav_dates >= pd.Timestamp(start)) & (nav_dates <= pd.Timestamp(end))]
    if nav_sub.empty:
        return {}
    row = calc_nav_stats(nav_sub)
    if trades_df.empty:
        row.update({"trade_records": 0, "buy_fills": 0, "sell_fills": 0})
        return row
    trade_dates = pd.to_datetime(trades_df["date"])
    period_trades = trades_df[(trade_dates >= pd.Timestamp(start)) & (trade_dates <= pd.Timestamp(end))]
    row.update({
        "trade_records": int(len(period_trades)),
        "buy_fills": int((period_trades["action"] == "buy").sum()) if not period_trades.empty else 0,
        "sell_fills": int((period_trades["action"] == "sell").sum()) if not period_trades.empty else 0,
    })
    return row


def run_case(v6, panel, market, case):
    with patched_score_candidates(v6, case, {}):
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v6.run_backtest(
            panel,
            market,
            "2018-01-01",
            None,
        )
    row = calc_nav_stats(nav_df)
    row.update({
        "case": case["name"],
        "period": "full",
        "trade_records": int(len(trades_df)),
        "case_input_candidates": int(stats.get("case_input_candidates", 0)),
        "case_blocked_candidates": int(stats.get("case_blocked_candidates", 0)),
        "case_missing_feature_rows": int(stats.get("case_missing_feature_rows", 0)),
    })
    periods = [("2018", "2018-01-01", "2018-12-31"), ("2022", "2022-01-01", "2022-12-31"), ("2024", "2024-01-01", "2024-12-31"), ("2025", "2025-01-01", "2025-12-31"), ("2026", "2026-01-01", "2026-12-31")]
    period_rows = []
    for label, start, end in periods:
        item = summarize_period(nav_df, trades_df, start, end)
        if item:
            item.update({"case": case["name"], "period": label})
            period_rows.append(item)
    return row, period_rows


def assert_baseline_matches_v6(full_rows, v6_summary):
    baseline = [row for row in full_rows if row["case"] == "baseline_v6"]
    if not baseline:
        raise AssertionError("baseline_v6 full-period result is missing")
    row = baseline[0]
    for key, tolerance in [
        ("final_nav", 1e-2),
        ("total_return_pct", 1e-4),
        ("annual_return_pct", 1e-4),
        ("max_drawdown_pct", 1e-4),
        ("calmar_ratio", 1e-4),
        ("trade_records", 0),
    ]:
        actual = float(row[key])
        expected = float(v6_summary[key])
        if abs(actual - expected) > tolerance:
            raise AssertionError(f"baseline_v6 {key}={actual} does not match v6 summary {expected}")


def fmt_pct(value):
    return f"{float(value):.2f}%"


def write_summary(full, period_rows, v4_summary, v5_summary, v6_summary):
    full_sorted = sorted(full, key=lambda row: row["total_return_pct"], reverse=True)
    lines = [
        "# v6 Moneyflow/CYQ Evolution Experiment",
        "",
        "## Baselines",
        f"- v4 total return: {v4_summary['total_return_pct']}%",
        f"- v5 total return: {v5_summary['total_return_pct']}%",
        f"- v6 total return: {v6_summary['total_return_pct']}%",
        "",
        "## Full Period",
        "| case | total | annual | max dd | Calmar | trades | blocked | missing features |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in full_sorted:
        lines.append(
            f"| {row['case']} | {fmt_pct(row['total_return_pct'])} | {fmt_pct(row['annual_return_pct'])} | "
            f"{fmt_pct(row['max_drawdown_pct'])} | {row['calmar_ratio']:.4f} | {int(row['trade_records'])} | "
            f"{int(row.get('case_blocked_candidates', 0))} | {int(row.get('case_missing_feature_rows', 0))} |"
        )
    best = full_sorted[0]
    recommendation = "合并候选" if (
        best["case"] != "baseline_v6"
        and best["total_return_pct"] > float(v6_summary["total_return_pct"])
        and best["max_drawdown_pct"] >= float(v6_summary["max_drawdown_pct"]) - 3.0
    ) else "暂不合并"
    lines.extend([
        "",
        "## Recommendation",
        f"- Best case: {best['case']}",
        f"- Recommendation: {recommendation}",
        "- Note: moneyflow and cyq fields are post-close data and are shifted by one trading row per stock before use.",
    ])
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_html_report(full, period_rows, v4_summary, v5_summary, v6_summary):
    full_sorted = sorted(full, key=lambda row: row["total_return_pct"], reverse=True)
    best = full_sorted[0]
    should_merge = (
        best["case"] != "baseline_v6"
        and best["total_return_pct"] > float(v6_summary["total_return_pct"])
        and best["max_drawdown_pct"] >= float(v6_summary["max_drawdown_pct"]) - 3.0
    )
    rows_html = []
    for row in full_sorted:
        klass = "best" if row is best else ""
        rows_html.append(
            f"<tr class=\"{klass}\"><td>{html_escape(row['case'])}</td>"
            f"<td>{row['total_return_pct']:.2f}%</td><td>{row['annual_return_pct']:.2f}%</td>"
            f"<td>{row['max_drawdown_pct']:.2f}%</td><td>{row['calmar_ratio']:.4f}</td>"
            f"<td>{int(row['trade_records'])}</td><td>{int(row.get('case_blocked_candidates', 0))}</td>"
            f"<td>{int(row.get('case_missing_feature_rows', 0))}</td></tr>"
        )
    period_map = {(row["case"], row["period"]): row for row in period_rows}
    period_html = []
    for row in full_sorted:
        cells = [f"<td>{html_escape(row['case'])}</td>"]
        for period in ["2018", "2022", "2024", "2025", "2026"]:
            value = period_map.get((row["case"], period), {}).get("total_return_pct")
            cells.append(f"<td>{value:.2f}%</td>" if value is not None else "<td>-</td>")
        period_html.append("<tr>" + "".join(cells) + "</tr>")
    recommendation = "建议进入下一轮合并评审" if should_merge else "暂不建议合并"
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>v6 moneyflow/cyq evolution report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 0; background: #f5f7fa; color: #1f2937; }}
header {{ background: #233142; color: white; padding: 20px 28px; }}
main {{ padding: 24px 28px; }}
section {{ background: white; border: 1px solid #d8dee9; margin-bottom: 18px; padding: 18px; }}
h1, h2 {{ margin: 0 0 12px; }}
.grid {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 12px; }}
.metric {{ border: 1px solid #d8dee9; padding: 12px; background: #fafafa; }}
.metric strong {{ display: block; font-size: 24px; margin-top: 6px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #d8dee9; padding: 7px 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #34495e; color: white; }}
tr.best {{ background: #fff7d6; font-weight: bold; }}
.warn {{ background: #fff7ed; border-color: #fed7aa; }}
.ok {{ background: #ecfdf5; border-color: #bbf7d0; }}
code {{ background: #eef2f7; padding: 1px 4px; }}
</style>
</head>
<body>
<header>
<h1>v6 资金流/筹码确认自动进化实验</h1>
<p>实验目录：scripts/bbi/backtrader/tmp。正式 v4/v5/v6 代码和 output 不修改。</p>
</header>
<main>
<section>
<h2>基线对比</h2>
<div class="grid">
<div class="metric"><span>v4 总收益</span><strong>{v4_summary['total_return_pct']:.2f}%</strong></div>
<div class="metric"><span>v5 总收益</span><strong>{v5_summary['total_return_pct']:.2f}%</strong></div>
<div class="metric"><span>v6 总收益</span><strong>{v6_summary['total_return_pct']:.2f}%</strong></div>
<div class="metric"><span>本轮最佳</span><strong>{best['total_return_pct']:.2f}%</strong><span>{html_escape(best['case'])}</span></div>
</div>
</section>
<section class="{'ok' if should_merge else 'warn'}">
<h2>合并建议</h2>
<p><strong>{recommendation}</strong>。判断标准：必须超过 v6 总收益，且最大回撤不能比 v6 恶化超过 3 个百分点。</p>
<p>本轮所有 moneyflow / cyq 盘后字段均按股票 <code>shift(1)</code> 后使用，避免 signal_date 直接使用当日盘后才可得的数据。</p>
</section>
<section>
<h2>全周期结果</h2>
<table>
<thead><tr><th>case</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>Calmar</th><th>交易数</th><th>过滤候选</th><th>缺失特征</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
</section>
<section>
<h2>关键年份切片</h2>
<table>
<thead><tr><th>case</th><th>2018</th><th>2022</th><th>2024</th><th>2025</th><th>2026</th></tr></thead>
<tbody>{''.join(period_html)}</tbody>
</table>
</section>
<section>
<h2>下一步</h2>
<ol>
<li>如果本轮没有稳定超过 v6，不合并，优先做 v6 参数稳健性和成本压力测试。</li>
<li>如果出现候选超过 v6，下一步单独做 walk-forward 与滑点压力测试。</li>
<li>若资金流数据覆盖不足或缺失特征过多，后续改为只用 v6 已有量价字段，避免数据质量引入假信号。</li>
</ol>
</section>
</main>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v6 = load_v6_module()
    import config as v6_config

    v4_summary = json.loads(V4_SUMMARY_PATH.read_text(encoding="utf-8"))
    v5_summary = json.loads(V5_SUMMARY_PATH.read_text(encoding="utf-8"))
    v6_summary = json.loads(v6_config.SUMMARY_PATH.read_text(encoding="utf-8"))

    panel = pd.read_parquet(v6_config.PANEL_PATH, columns=list(dict.fromkeys([*v6.PANEL_COLUMNS, "close_qfq"])))
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    start_date = str(panel["trade_date"].min())[:10]
    end_date = str(panel["trade_date"].max())[:10]
    extra = load_extra_features_from_db(v6_config, start_date, end_date)
    panel = add_moneyflow_features(panel, extra)
    market = v6.load_market_index()

    full_rows = []
    period_rows = []
    for case in CASES:
        print(f"running {case['name']}", flush=True)
        full, periods = run_case(v6, panel, market, case)
        full_rows.append(full)
        period_rows.extend(periods)

    assert_baseline_matches_v6(full_rows, v6_summary)
    all_rows = full_rows + period_rows
    pd.DataFrame(all_rows).to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    write_summary(full_rows, period_rows, v4_summary, v5_summary, v6_summary)
    write_html_report(full_rows, period_rows, v4_summary, v5_summary, v6_summary)
    print(f"Results saved: {RESULTS_PATH}")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()

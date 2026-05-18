import csv
from contextlib import contextmanager
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v6").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V4_SUMMARY_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v4" / "output" / "summary.json"
V5_SUMMARY_PATH = ROOT / "scripts" / "bbi" / "backtrader" / "v5" / "output" / "summary.json"
V6_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v6"
OUTPUT_DIR = Path(__file__).parent / "v6_downtrend_robustness_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"
REPORT_PATH = OUTPUT_DIR / "report.html"

GRID = [
    {"ma": ma, "slope": slope, "ret": ret}
    for ma in (10, 20, 30)
    for slope in (5, 10, 20)
    for ret in (10, 21, 42)
]

PERIODS = {
    "full": ("2018-01-01", "2026-05-14"),
    "train_2018_2021": ("2018-01-01", "2021-12-31"),
    "validate_2022_2024": ("2022-01-01", "2024-12-31"),
    "confirm_2025_2026": ("2025-01-01", "2026-12-31"),
    "2018": ("2018-01-01", "2018-12-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026": ("2026-01-01", "2026-12-31"),
}


def case_name(case):
    return f"ma{case['ma']}_slope{case['slope']}_ret{case['ret']}"


def flag_name(case):
    return f"downtrend_{case_name(case)}"


def load_module_from_path(module_name, path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_v6_module():
    return load_module_from_path("v6_run_backtest_downtrend_robustness", V6_DIR / "20_run_backtest.py")


def rolling_mean_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .mean()
        .reset_index(level=0, drop=True)
    )


def add_param_downtrend_features(panel, cases):
    out = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = out.groupby("ts_code", sort=False)
    ma_windows = sorted({case["ma"] for case in cases})
    for ma in ma_windows:
        ma_col = f"_robust_ma{ma}"
        out[ma_col] = rolling_mean_by_code(out, "close_qfq", ma)
    for case in cases:
        ma_col = f"_robust_ma{case['ma']}"
        slope_col = f"_robust_{case_name(case)}_slope"
        ret_col = f"_robust_{case_name(case)}_ret"
        out[slope_col] = grouped[ma_col].pct_change(case["slope"], fill_method=None) / float(case["slope"])
        out[ret_col] = grouped["close_qfq"].pct_change(case["ret"], fill_method=None)
        out[flag_name(case)] = (
            (out["close_qfq"] < out[ma_col])
            & (out[slope_col] < 0)
            & (out[ret_col] < 0)
        )
    drop_cols = [col for col in out.columns if col.startswith("_robust_")]
    return out.drop(columns=drop_cols)


@contextmanager
def patched_downtrend_flag(v6, flag_col):
    original_enabled = v6.DOWNTREND_BUY_FILTER_ENABLED
    original_name = v6.DOWNTREND_FILTER_NAME
    try:
        v6.DOWNTREND_BUY_FILTER_ENABLED = True
        v6.DOWNTREND_FILTER_NAME = flag_col
        yield
    finally:
        v6.DOWNTREND_BUY_FILTER_ENABLED = original_enabled
        v6.DOWNTREND_FILTER_NAME = original_name


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
    name = case_name(case)
    with patched_downtrend_flag(v6, flag_name(case)):
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v6.run_backtest(panel, market, "2018-01-01", None)
    rows = []
    for period, (start, end) in PERIODS.items():
        row = {
            "case": name,
            "period": period,
            "ma": case["ma"],
            "slope": case["slope"],
            "ret": case["ret"],
            "flag_col": flag_name(case),
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        if period == "full":
            row.update({
                "downtrend_filter_candidate_blocks": int(stats.get("downtrend_filter_candidate_blocks", 0)),
                "downtrend_filter_signal_days": int(stats.get("downtrend_filter_signal_days", 0)),
            })
        rows.append(row)
    return rows


def select_walk_forward_best(results):
    train = results[results["period"] == "train_2018_2021"].copy()
    train = train.sort_values(["calmar_ratio", "total_return_pct", "max_drawdown_pct"], ascending=[False, False, False])
    selected = train.iloc[0]
    validate = results[(results["case"] == selected["case"]) & (results["period"] == "validate_2022_2024")].iloc[0]
    confirm_rows = results[(results["case"] == selected["case"]) & (results["period"] == "confirm_2025_2026")]
    confirm = confirm_rows.iloc[0] if not confirm_rows.empty else None
    return {
        "selected_case": selected["case"],
        "train_total_return_pct": float(selected["total_return_pct"]),
        "train_calmar_ratio": float(selected["calmar_ratio"]),
        "validate_total_return_pct": float(validate["total_return_pct"]),
        "validate_calmar_ratio": float(validate["calmar_ratio"]),
        "confirm_total_return_pct": float(confirm["total_return_pct"]) if confirm is not None else float("nan"),
        "confirm_calmar_ratio": float(confirm["calmar_ratio"]) if confirm is not None else float("nan"),
    }


def assert_current_v6_case_matches(results, v6_summary):
    current = results[(results["case"] == "ma20_slope10_ret21") & (results["period"] == "full")]
    if current.empty:
        raise AssertionError("current v6 case ma20_slope10_ret21 is missing")
    row = current.iloc[0]
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
            raise AssertionError(f"current v6 case {key}={actual} does not match v6 summary {expected}")


def write_summary(results, v4_summary, v5_summary, v6_summary, walk):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    lines = [
        "# v6 Downtrend Robustness Experiment",
        "",
        "## Baselines",
        f"- v4 total return: {v4_summary['total_return_pct']}%",
        f"- v5 total return: {v5_summary['total_return_pct']}%",
        f"- current v6 total return: {v6_summary['total_return_pct']}%",
        "",
        "## Full Period Top 10",
        "| case | total | annual | max dd | Calmar | trades | blocked |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.head(10).iterrows():
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | {int(row['trade_records'])} | "
            f"{int(row.get('downtrend_filter_candidate_blocks', 0))} |"
        )
    best = full.iloc[0]
    current = full[full["case"] == "ma20_slope10_ret21"].iloc[0]
    recommendation = "合并候选" if (
        best["case"] != current["case"]
        and best["total_return_pct"] > current["total_return_pct"]
        and best["max_drawdown_pct"] >= current["max_drawdown_pct"] - 3.0
    ) else "暂不替换v6当前参数"
    lines.extend([
        "",
        "## Walk-forward",
        f"- selected on train: {walk['selected_case']}",
        f"- train total: {walk['train_total_return_pct']:.2f}%, Calmar {walk['train_calmar_ratio']:.4f}",
        f"- validate total: {walk['validate_total_return_pct']:.2f}%, Calmar {walk['validate_calmar_ratio']:.4f}",
        f"- confirm total: {walk['confirm_total_return_pct']:.2f}%, Calmar {walk['confirm_calmar_ratio']:.4f}",
        "",
        "## Recommendation",
        f"- Best full-period case: {best['case']}",
        f"- Current v6 case: {current['case']}",
        f"- Recommendation: {recommendation}",
    ])
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_html_report(results, v4_summary, v5_summary, v6_summary, walk):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    best = full.iloc[0]
    current = full[full["case"] == "ma20_slope10_ret21"].iloc[0]
    should_replace = (
        best["case"] != current["case"]
        and best["total_return_pct"] > current["total_return_pct"]
        and best["max_drawdown_pct"] >= current["max_drawdown_pct"] - 3.0
    )
    rows = []
    for _, row in full.iterrows():
        klass = "best" if row["case"] == best["case"] else ("current" if row["case"] == current["case"] else "")
        rows.append(
            f"<tr class=\"{klass}\"><td>{html_escape(row['case'])}</td><td>{row['total_return_pct']:.2f}%</td>"
            f"<td>{row['annual_return_pct']:.2f}%</td><td>{row['max_drawdown_pct']:.2f}%</td>"
            f"<td>{row['calmar_ratio']:.4f}</td><td>{int(row['trade_records'])}</td>"
            f"<td>{int(row.get('downtrend_filter_candidate_blocks', 0))}</td></tr>"
        )
    period_map = {(row["case"], row["period"]): row for _, row in results.iterrows()}
    top_cases = list(full.head(10)["case"])
    period_rows = []
    for case in top_cases:
        cells = [f"<td>{html_escape(case)}</td>"]
        for period in ["train_2018_2021", "validate_2022_2024", "confirm_2025_2026", "2018", "2022", "2025", "2026"]:
            value = period_map.get((case, period), {}).get("total_return_pct")
            cells.append(f"<td>{value:.2f}%</td>" if value is not None else "<td>-</td>")
        period_rows.append("<tr>" + "".join(cells) + "</tr>")
    recommendation = "建议替换 v6 参数并进入成本压力测试" if should_replace else "暂不替换 v6 当前参数，先做成本压力测试"
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>v6 downtrend robustness report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 0; background: #f5f7fa; color: #1f2937; }}
header {{ background: #263238; color: white; padding: 20px 28px; }}
main {{ padding: 24px 28px; }}
section {{ background: white; border: 1px solid #d8dee9; margin-bottom: 18px; padding: 18px; }}
.grid {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 12px; }}
.metric {{ border: 1px solid #d8dee9; padding: 12px; background: #fafafa; }}
.metric strong {{ display: block; font-size: 24px; margin-top: 6px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #d8dee9; padding: 7px 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #34495e; color: white; }}
tr.best {{ background: #fff7d6; font-weight: bold; }}
tr.current {{ background: #e0f2fe; font-weight: bold; }}
.warn {{ background: #fff7ed; border-color: #fed7aa; }}
.ok {{ background: #ecfdf5; border-color: #bbf7d0; }}
</style>
</head>
<body>
<header>
<h1>v6 下降趋势参数稳健性实验</h1>
<p>27 个参数组合：MA 10/20/30，斜率窗口 5/10/20，收益窗口 10/21/42。只写 tmp 输出。</p>
</header>
<main>
<section>
<h2>基线与最佳</h2>
<div class="grid">
<div class="metric"><span>v4 总收益</span><strong>{v4_summary['total_return_pct']:.2f}%</strong></div>
<div class="metric"><span>v5 总收益</span><strong>{v5_summary['total_return_pct']:.2f}%</strong></div>
<div class="metric"><span>当前 v6</span><strong>{current['total_return_pct']:.2f}%</strong><span>{current['case']}</span></div>
<div class="metric"><span>全周期最佳</span><strong>{best['total_return_pct']:.2f}%</strong><span>{best['case']}</span></div>
</div>
</section>
<section class="{'ok' if should_replace else 'warn'}">
<h2>合并建议</h2>
<p><strong>{recommendation}</strong>。判断标准：全周期收益超过当前 v6，且最大回撤不恶化超过 3 个百分点；同时参考 walk-forward。</p>
<p>Walk-forward 训练选择：{html_escape(walk['selected_case'])}；验证期收益 {walk['validate_total_return_pct']:.2f}%；确认期收益 {walk['confirm_total_return_pct']:.2f}%。</p>
</section>
<section>
<h2>全周期结果</h2>
<table>
<thead><tr><th>case</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>Calmar</th><th>交易数</th><th>过滤候选</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</section>
<section>
<h2>分段表现</h2>
<table>
<thead><tr><th>case</th><th>训练2018-2021</th><th>验证2022-2024</th><th>确认2025-2026</th><th>2018</th><th>2022</th><th>2025</th><th>2026</th></tr></thead>
<tbody>{''.join(period_rows)}</tbody>
</table>
</section>
<section>
<h2>下一步</h2>
<ol>
<li>如果当前 v6 不是稳健最优，不要立即替换；先看 walk-forward 是否支持。</li>
<li>对当前 v6 和候选最优做 +5bp/+10bp 滑点压力测试。</li>
<li>如果参数邻域普遍优秀，才考虑把参数选择写入 v6 设计记录。</li>
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
    panel = add_param_downtrend_features(panel, GRID)
    market = v6.load_market_index()

    rows = []
    for case in GRID:
        print(f"running {case_name(case)}", flush=True)
        rows.extend(run_case(v6, panel, market, case))

    results = pd.DataFrame(rows)
    assert_current_v6_case_matches(results, v6_summary)
    walk = select_walk_forward_best(results)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    write_summary(results, v4_summary, v5_summary, v6_summary, walk)
    write_html_report(results, v4_summary, v5_summary, v6_summary, walk)
    print(f"Results saved: {RESULTS_PATH}")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()

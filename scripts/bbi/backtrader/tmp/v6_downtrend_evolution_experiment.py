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
OUTPUT_DIR = Path(__file__).parent / "v6_downtrend_evolution_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "README.md"
REPORT_PATH = OUTPUT_DIR / "report.html"

SOURCE_NOTES = [
    {
        "topic": "长期趋势",
        "source": "Investopedia 200-day SMA",
        "url": "https://www.investopedia.com/ask/answers/013015/why-200-simple-moving-average-sma-so-common-traders-and-analysts.asp",
        "note": "200 日均线常用于区分长期上升/下降趋势，并与 50 日均线交叉判断趋势强弱。",
    },
    {
        "topic": "斜率",
        "source": "StockCharts Slope",
        "url": "https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/slope",
        "note": "Slope 是线性回归的 rise-over-run；正值代表上升趋势，负值代表下降趋势。",
    },
    {
        "topic": "多窗口趋势",
        "source": "StockCharts Trend Quantification",
        "url": "https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/trend-quantification-and-asset-allocation",
        "note": "多个斜率窗口同时为负可视为更强下降趋势。",
    },
    {
        "topic": "脉冲顶部",
        "source": "EBC blow-off top",
        "url": "https://www.ebc.com/forex/what-is-a-blow-off-top-in-the-stock-market",
        "note": "快速上涨、成交量放大后快速下跌，是典型顶部/风险反转结构。",
    },
    {
        "topic": "量能确认",
        "source": "LuxAlgo volume analysis",
        "url": "https://www.luxalgo.com/blog/volume-analysis-techniques-to-confirm-setups/",
        "note": "上涨后放量可能代表衰竭，下降中放量确认卖压。",
    },
]

CASES = [
    {
        "name": "baseline_v6",
        "flag_col": None,
        "description": "当前 v6：early_weakness_downtrend 过滤。",
    },
    {
        "name": "long_downtrend_only",
        "flag_col": "long_downtrend_risk",
        "description": "长期下降：收盘价 < MA200，MA200 40 日斜率为负。",
    },
    {
        "name": "quarter_downtrend_only",
        "flag_col": "quarter_downtrend_risk",
        "description": "季度级下降：收盘价 < MA60，MA60 20 日斜率为负，63 日收益为负。",
    },
    {
        "name": "pulse_up_then_down_only",
        "flag_col": "pulse_up_then_down_risk",
        "description": "脉冲上涨后下跌：近 20 日高低振幅 >= 30%，从 20 日高点回撤 >= 12%，成交额/量能 >= 1.5 倍均值。",
    },
    {
        "name": "monthly_downtrend_only",
        "flag_col": "monthly_downtrend_risk",
        "description": "月级别下降：收盘价 < MA20，MA20 10 日斜率为负，21 日收益为负。",
    },
    {
        "name": "monthly_or_pulse",
        "flag_col": "monthly_or_pulse_downtrend_risk",
        "description": "月级别下降 OR 脉冲上涨后下跌。",
    },
    {
        "name": "long_or_quarter",
        "flag_col": "long_or_quarter_downtrend_risk",
        "description": "长期下降或季度级下降。",
    },
    {
        "name": "evolution_combo_without_v6_early",
        "flag_col": "downtrend_evolution_forbid_buy",
        "description": "长期下降、季度级下降、脉冲上涨后下跌三类风险 OR。",
    },
    {
        "name": "evolution_combo_with_v6_early",
        "flag_col": "downtrend_evolution_plus_v6_early",
        "description": "三类新风险 OR 当前 v6 early_weakness_downtrend。",
    },
]

PERIODS = {
    "full": ("2018-01-01", "2026-05-14"),
    "train_2018_2021": ("2018-01-01", "2021-12-31"),
    "validate_2022_2024": ("2022-01-01", "2024-12-31"),
    "confirm_2025_2026": ("2025-01-01", "2026-05-14"),
    "2018": ("2018-01-01", "2018-12-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026": ("2026-01-01", "2026-05-14"),
}


def load_module_from_path(module_name, path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_v6_module():
    return load_module_from_path("v6_run_backtest_downtrend_evolution", V6_DIR / "20_run_backtest.py")


def rolling_mean_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .mean()
        .reset_index(level=0, drop=True)
    )


def rolling_max_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .max()
        .reset_index(level=0, drop=True)
    )


def add_downtrend_evolution_features(panel):
    out = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = out.groupby("ts_code", sort=False)

    activity_col = "amount" if "amount" in out.columns else ("vol" if "vol" in out.columns else "volume")
    if activity_col not in out.columns:
        out[activity_col] = np.nan

    out["_ma20_evo"] = rolling_mean_by_code(out, "close_qfq", 20)
    out["_ma60_evo"] = rolling_mean_by_code(out, "close_qfq", 60)
    out["_ma200_evo"] = rolling_mean_by_code(out, "close_qfq", 200)
    out["_ma60_slope_20_evo"] = grouped["_ma60_evo"].pct_change(20, fill_method=None) / 20.0
    out["_ma200_slope_40_evo"] = grouped["_ma200_evo"].pct_change(40, fill_method=None) / 40.0

    out["_ret_5_evo"] = grouped["close_qfq"].pct_change(5, fill_method=None)
    out["_ret_10_evo"] = grouped["close_qfq"].pct_change(10, fill_method=None)
    out["_ret_20_evo"] = grouped["close_qfq"].pct_change(20, fill_method=None)
    out["_ret_63_evo"] = grouped["close_qfq"].pct_change(63, fill_method=None)
    out["_activity_ma20_evo"] = rolling_mean_by_code(out, activity_col, 20)
    out["_activity_ma5_evo"] = rolling_mean_by_code(out, activity_col, 5)
    out["_activity_ratio_5_20_evo"] = out["_activity_ma5_evo"] / out["_activity_ma20_evo"]
    out["_high_20_evo"] = rolling_max_by_code(out, "close_qfq", 20)
    out["_low_20_evo"] = (
        out.groupby("ts_code", sort=False)["close_qfq"]
        .rolling(20, min_periods=20)
        .min()
        .reset_index(level=0, drop=True)
    )
    out["_range_20_evo"] = out["_high_20_evo"] / out["_low_20_evo"] - 1.0
    out["_drop_from_20_high_evo"] = out["close_qfq"] / out["_high_20_evo"] - 1.0

    out["long_downtrend_risk"] = (
        (out["close_qfq"] < out["_ma200_evo"])
        & (out["_ma200_slope_40_evo"] < 0)
    )
    out["quarter_downtrend_risk"] = (
        (out["close_qfq"] < out["_ma60_evo"])
        & (out["_ma60_slope_20_evo"] < 0)
        & (out["_ret_63_evo"] < 0)
    )
    out["pulse_up_then_down_risk"] = (
        (out["_range_20_evo"] >= 0.30)
        & (out["_drop_from_20_high_evo"] <= -0.12)
        & (out["_activity_ratio_5_20_evo"] >= 1.5)
    )
    out["monthly_downtrend_risk"] = (
        (out["close_qfq"] < out["_ma20_evo"])
        & (grouped["_ma20_evo"].pct_change(10, fill_method=None) / 10.0 < 0)
        & (out["_ret_20_evo"] < 0)
    )
    out["monthly_or_pulse_downtrend_risk"] = (
        out["monthly_downtrend_risk"] | out["pulse_up_then_down_risk"]
    )
    out["long_or_quarter_downtrend_risk"] = (
        out["long_downtrend_risk"] | out["quarter_downtrend_risk"]
    )
    out["downtrend_evolution_forbid_buy"] = (
        out["long_downtrend_risk"]
        | out["quarter_downtrend_risk"]
        | out["pulse_up_then_down_risk"]
    )
    current_v6 = (
        out["early_weakness_downtrend"].fillna(False).astype(bool)
        if "early_weakness_downtrend" in out.columns
        else pd.Series(False, index=out.index)
    )
    out["downtrend_evolution_plus_v6_early"] = (
        out["downtrend_evolution_forbid_buy"] | current_v6
    )
    drop_cols = [col for col in out.columns if col.endswith("_evo")]
    return out.drop(columns=drop_cols)


@contextmanager
def patched_v6_downtrend_filter(v6, flag_col):
    original_enabled = v6.DOWNTREND_BUY_FILTER_ENABLED
    original_name = v6.DOWNTREND_FILTER_NAME
    try:
        if flag_col is None:
            v6.DOWNTREND_BUY_FILTER_ENABLED = True
            v6.DOWNTREND_FILTER_NAME = "early_weakness_downtrend"
        else:
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
    with patched_v6_downtrend_filter(v6, case["flag_col"]):
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v6.run_backtest(panel, market, "2018-01-01", None)
    rows = []
    for period, (start, end) in PERIODS.items():
        row = {
            "case": case["name"],
            "period": period,
            "flag_col": case["flag_col"] or "early_weakness_downtrend",
            "description": case["description"],
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        if period == "full":
            row.update({
                "downtrend_filter_candidate_blocks": int(stats.get("downtrend_filter_candidate_blocks", 0)),
                "downtrend_filter_signal_days": int(stats.get("downtrend_filter_signal_days", 0)),
                "buy_fills_total": int(stats.get("buy_fills", 0)),
                "add_buy_fills_total": int(stats.get("add_buy_fills", 0)),
                "sell_fills_total": int(stats.get("sell_fills", 0)),
            })
        rows.append(row)
    return rows


def assert_baseline_matches_v6(results, v6_summary):
    baseline = results[(results["case"] == "baseline_v6") & (results["period"] == "full")]
    if baseline.empty:
        raise AssertionError("baseline_v6 result is missing")
    row = baseline.iloc[0]
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


def select_walk_forward_best(results):
    candidates = results[~results["case"].eq("baseline_v6")]
    train = candidates[candidates["period"] == "train_2018_2021"].copy()
    train = train.sort_values(["calmar_ratio", "total_return_pct", "max_drawdown_pct"], ascending=[False, False, False])
    selected = train.iloc[0]
    validate = results[(results["case"] == selected["case"]) & (results["period"] == "validate_2022_2024")].iloc[0]
    confirm = results[(results["case"] == selected["case"]) & (results["period"] == "confirm_2025_2026")].iloc[0]
    return {
        "selected_case": selected["case"],
        "train_total_return_pct": float(selected["total_return_pct"]),
        "train_calmar_ratio": float(selected["calmar_ratio"]),
        "validate_total_return_pct": float(validate["total_return_pct"]),
        "validate_calmar_ratio": float(validate["calmar_ratio"]),
        "confirm_total_return_pct": float(confirm["total_return_pct"]),
        "confirm_calmar_ratio": float(confirm["calmar_ratio"]),
    }


def html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def recommendation_for(best, baseline, walk):
    if (
        best["case"] != "baseline_v6"
        and best["total_return_pct"] > baseline["total_return_pct"]
        and best["max_drawdown_pct"] >= baseline["max_drawdown_pct"] - 3.0
        and walk["validate_total_return_pct"] > 0
    ):
        return "建议进入 v6 合并候选，但先做交易成本、滑点和参数邻域压力测试。"
    return "暂不建议直接合并到 v6；保留为候选实验，下一步做参数邻域和交易成本压力测试。"


def baseline_delta_rows(baseline, v6_summary):
    keys = ["final_nav", "total_return_pct", "annual_return_pct", "max_drawdown_pct", "calmar_ratio", "trade_records"]
    rows = []
    for key in keys:
        actual = float(baseline[key])
        expected = float(v6_summary[key])
        rows.append({
            "field": key,
            "experiment": actual,
            "v6_summary": expected,
            "delta": actual - expected,
        })
    return rows


def write_readme(results, v4_summary, v5_summary, v6_summary, walk):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    baseline = full[full["case"] == "baseline_v6"].iloc[0]
    best = full.iloc[0]
    lines = [
        "# v6 Downtrend Evolution Experiment",
        "",
        "## 工作进度",
        "- 设计专家：量化策略专家负责规则审查，工程专家负责隔离和未来函数审查。",
        "- 设计：长期下降、季度级下降、脉冲上涨后下跌三类个股禁止买入风险。",
        "- 开发：只新增 tmp 实验脚本和测试，不修改 v4/v5/v6。",
        "- 验证：baseline_v6 必须逐项复现 v6/output/summary.json。",
        "- baseline_v6 精确校验：已通过，字段包括 final_nav、total_return_pct、annual_return_pct、max_drawdown_pct、calmar_ratio、trade_records。",
        "",
        "## 数据使用",
        "- 使用 v6/output/panel.parquet，来自 Tushare daily、adj_factor、daily_basic、stk_limit 等既有准备流程。",
        "- 本轮未新增外部数据表，避免把数据拉取和策略归因混在一起。",
        "- 所有信号在 panel 的 trade_date 行计算；v6 回测使用 T-1 signal_date、T 日开盘交易。",
        "",
        "## Web 依据",
    ]
    for note in SOURCE_NOTES:
        lines.append(f"- {note['topic']}：{note['note']} 来源：{note['url']}")
    lines.extend([
        "",
        "## 全周期结果",
        "| case | 总收益 | 年化 | 最大回撤 | Calmar | 交易数 | 过滤候选 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for _, row in full.iterrows():
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | {int(row['trade_records'])} | "
            f"{int(row.get('downtrend_filter_candidate_blocks', 0))} |"
        )
    lines.extend([
        "",
        "## 基线对比",
        f"- v4 总收益：{v4_summary['total_return_pct']:.2f}%，最大回撤：{v4_summary['max_drawdown_pct']:.2f}%。",
        f"- v5 总收益：{v5_summary['total_return_pct']:.2f}%，最大回撤：{v5_summary['max_drawdown_pct']:.2f}%。",
        f"- v6 总收益：{v6_summary['total_return_pct']:.2f}%，最大回撤：{v6_summary['max_drawdown_pct']:.2f}%。",
        "",
        "## baseline_v6 复现校验",
        "| 字段 | 实验值 | v6 summary | 差值 |",
        "|---|---:|---:|---:|",
    ])
    for row in baseline_delta_rows(baseline, v6_summary):
        lines.append(
            f"| {row['field']} | {row['experiment']:.6f} | {row['v6_summary']:.6f} | {row['delta']:.8f} |"
        )
    lines.extend([
        "",
        "## Walk-forward",
        f"- 训练期选择：{walk['selected_case']}，训练收益 {walk['train_total_return_pct']:.2f}%，Calmar {walk['train_calmar_ratio']:.4f}。",
        f"- 验证期收益：{walk['validate_total_return_pct']:.2f}%，Calmar {walk['validate_calmar_ratio']:.4f}。",
        f"- 确认期收益：{walk['confirm_total_return_pct']:.2f}%，Calmar {walk['confirm_calmar_ratio']:.4f}。",
        "",
        "## 建议",
        f"- 全周期最佳：{best['case']}。",
        f"- 当前 v6：{baseline['case']}。",
        f"- {recommendation_for(best, baseline, walk)}",
    ])
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_html_report(results, v4_summary, v5_summary, v6_summary, walk):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    baseline = full[full["case"] == "baseline_v6"].iloc[0]
    best = full.iloc[0]
    advice = recommendation_for(best, baseline, walk)

    full_rows = []
    for _, row in full.iterrows():
        klass = "best" if row["case"] == best["case"] else ("baseline" if row["case"] == "baseline_v6" else "")
        full_rows.append(
            f"<tr class=\"{klass}\"><td>{html_escape(row['case'])}</td>"
            f"<td>{row['total_return_pct']:.2f}%</td><td>{row['annual_return_pct']:.2f}%</td>"
            f"<td>{row['max_drawdown_pct']:.2f}%</td><td>{row['calmar_ratio']:.4f}</td>"
            f"<td>{int(row['trade_records'])}</td><td>{int(row.get('downtrend_filter_candidate_blocks', 0))}</td>"
            f"<td>{html_escape(row['description'])}</td></tr>"
        )

    period_map = {(row["case"], row["period"]): row for _, row in results.iterrows()}
    period_rows = []
    for case in list(full["case"]):
        cells = [f"<td>{html_escape(case)}</td>"]
        for period in ["train_2018_2021", "validate_2022_2024", "confirm_2025_2026", "2018", "2022", "2025", "2026"]:
            value = period_map.get((case, period), {}).get("total_return_pct")
            cells.append(f"<td>{value:.2f}%</td>" if value is not None else "<td>-</td>")
        period_rows.append("<tr>" + "".join(cells) + "</tr>")

    source_rows = "".join(
        f"<tr><td>{html_escape(note['topic'])}</td><td>{html_escape(note['note'])}</td>"
        f"<td><a href=\"{note['url']}\">{html_escape(note['source'])}</a></td></tr>"
        for note in SOURCE_NOTES
    )
    baseline_rows = "".join(
        f"<tr><td>{html_escape(row['field'])}</td><td>{row['experiment']:.6f}</td>"
        f"<td>{row['v6_summary']:.6f}</td><td>{row['delta']:.8f}</td></tr>"
        for row in baseline_delta_rows(baseline, v6_summary)
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>v6 下降趋势进化实验报表</title>
<style>
body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f4f6f8; color: #1f2937; }}
header {{ background: #263238; color: #fff; padding: 22px 30px; }}
main {{ padding: 24px 30px; }}
section {{ background: #fff; border: 1px solid #d7dee8; padding: 18px; margin-bottom: 18px; }}
.grid {{ display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 12px; }}
.metric {{ background: #fafafa; border: 1px solid #d7dee8; padding: 12px; }}
.metric strong {{ display: block; font-size: 24px; margin-top: 6px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #d7dee8; padding: 7px 8px; text-align: right; }}
th:first-child, td:first-child, th:last-child, td:last-child {{ text-align: left; }}
th {{ background: #34495e; color: #fff; }}
tr.best {{ background: #fff7d6; font-weight: 700; }}
tr.baseline {{ background: #e0f2fe; font-weight: 700; }}
.advice {{ background: #fff7ed; border-color: #fed7aa; }}
.sources td {{ text-align: left; }}
</style>
</head>
<body>
<header>
<h1>v6 下降趋势进化实验</h1>
<p>把“长期下降、季度级下降、脉冲上涨后脉冲式下跌不买入”量化后，在 tmp 中复用 v6 引擎回测。</p>
</header>
<main>
<section>
<h2>核心结论</h2>
<div class="grid">
<div class="metric"><span>v4 总收益</span><strong>{v4_summary['total_return_pct']:.2f}%</strong></div>
<div class="metric"><span>v5 总收益</span><strong>{v5_summary['total_return_pct']:.2f}%</strong></div>
<div class="metric"><span>当前 v6</span><strong>{baseline['total_return_pct']:.2f}%</strong><span>回撤 {baseline['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>本轮最佳</span><strong>{best['total_return_pct']:.2f}%</strong><span>{html_escape(best['case'])}</span></div>
</div>
</section>
<section class="advice">
<h2>是否合并</h2>
<p><strong>{html_escape(advice)}</strong></p>
<p>Walk-forward：训练选择 {html_escape(walk['selected_case'])}；验证期收益 {walk['validate_total_return_pct']:.2f}%，确认期收益 {walk['confirm_total_return_pct']:.2f}%。</p>
<p>baseline_v6 精确校验已通过：final_nav、收益、回撤、Calmar、交易数均与 v6/output/summary.json 在容差内一致。</p>
</section>
<section>
<h2>baseline_v6 复现校验</h2>
<table>
<thead><tr><th>字段</th><th>实验值</th><th>v6 summary</th><th>差值</th></tr></thead>
<tbody>{baseline_rows}</tbody>
</table>
</section>
<section>
<h2>全周期结果</h2>
<table>
<thead><tr><th>case</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>Calmar</th><th>交易数</th><th>过滤候选</th><th>说明</th></tr></thead>
<tbody>{''.join(full_rows)}</tbody>
</table>
</section>
<section>
<h2>分段结果</h2>
<table>
<thead><tr><th>case</th><th>训练2018-2021</th><th>验证2022-2024</th><th>确认2025-2026</th><th>2018</th><th>2022</th><th>2025</th><th>2026</th></tr></thead>
<tbody>{''.join(period_rows)}</tbody>
</table>
</section>
<section>
<h2>依据与量化</h2>
<table class="sources">
<thead><tr><th>主题</th><th>程序化处理</th><th>来源</th></tr></thead>
<tbody>{source_rows}</tbody>
</table>
</section>
<section>
<h2>下一步</h2>
<ol>
<li>对最佳候选与当前 v6 做滑点、手续费和成交额容量压力测试。</li>
<li>检查参数邻域：MA60 斜率阈值 -0.0003/-0.0005/-0.0010，脉冲跌幅 5 日 -6%/-8%/-10%。</li>
<li>若验证期和确认期都优于 v6，再迁移到 v6，并保留 v5/v6 输出隔离。</li>
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

    columns = list(dict.fromkeys([*v6.PANEL_COLUMNS, "close_qfq", "amount"]))
    panel = pd.read_parquet(v6_config.PANEL_PATH, columns=columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = add_downtrend_evolution_features(panel)
    market = v6.load_market_index()

    rows = []
    for case in CASES:
        print(f"running {case['name']}", flush=True)
        rows.extend(run_case(v6, panel, market, case))

    results = pd.DataFrame(rows)
    assert_baseline_matches_v6(results, v6_summary)
    walk = select_walk_forward_best(results)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    write_readme(results, v4_summary, v5_summary, v6_summary, walk)
    write_html_report(results, v4_summary, v5_summary, v6_summary, walk)
    print(f"Results saved: {RESULTS_PATH}")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()

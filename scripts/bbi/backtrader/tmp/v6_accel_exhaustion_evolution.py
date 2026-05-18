import csv
from contextlib import contextmanager
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "v6_accel_exhaustion_evolution_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
README_PATH = TMP_DIR / "v6_accel_exhaustion_README.md"
REPORT_PATH = OUTPUT_DIR / "report.html"

SOURCE_NOTES = [
    {
        "topic": "趋势跟随",
        "source": "Investopedia trend trading",
        "url": "https://www.investopedia.com/articles/active-trading/041814/four-most-commonlyused-indicators-trend-trading.asp",
        "note": "强趋势应优先跟随，不应因为上涨加速本身就反向交易。",
    },
    {
        "topic": "动量崩溃",
        "source": "Daniel & Moskowitz Momentum Crashes",
        "url": "https://www.nber.org/system/files/working_papers/w20439/w20439.pdf",
        "note": "熊市后期和高波动反弹阶段，动量策略容易遭遇反转损失。",
    },
    {
        "topic": "宽度 thrust",
        "source": "Investopedia Breadth Thrust",
        "url": "https://www.investopedia.com/terms/b/breadth-thrust-indicator.asp",
        "note": "底部更可靠的确认来自市场宽度快速修复，而不是单纯下跌加速。",
    },
    {
        "topic": "ATR/动态退出",
        "source": "backtesting.py trailing stop discussion",
        "url": "https://github.com/kernc/backtesting.py/discussions/238",
        "note": "工程实现常用动态止损/跟踪止损管理趋势持仓风险。",
    },
]

CASES = [
    {
        "name": "baseline_v6",
        "filter_col": None,
        "exit_enabled": False,
        "description": "当前 v6 原样复现。",
    },
    {
        "name": "forbid_up_exhaustion_buy",
        "filter_col": "up_accel_exhaustion",
        "exit_enabled": False,
        "description": "上涨加速后失速的股票不新买/不加仓。",
    },
    {
        "name": "forbid_bear_down_accel_buy",
        "filter_col": "bear_down_accel_risk",
        "exit_enabled": False,
        "description": "熊市式下跌加速风险不新买/不加仓。",
    },
    {
        "name": "forbid_accel_exhaustion_buy",
        "filter_col": "accel_exhaustion_forbid_buy",
        "exit_enabled": False,
        "description": "上涨失速 OR 下跌加速，不新买/不加仓。",
    },
    {
        "name": "exit_up_exhaustion_profit",
        "filter_col": None,
        "exit_enabled": True,
        "description": "盈利持仓若出现上涨加速后失速，次日开盘退出。",
    },
    {
        "name": "forbid_and_exit_exhaustion",
        "filter_col": "accel_exhaustion_forbid_buy",
        "exit_enabled": True,
        "description": "组合规则：风险股票不买，盈利持仓失速退出。",
    },
]

PERIODS = {
    "full": ("2018-01-01", "2026-05-14"),
}


def load_module_from_path(module_name, path):
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_path


def load_v6_module():
    return load_module_from_path("v6_run_backtest_accel_exhaustion", V6_DIR / "20_run_backtest.py")


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


def rolling_min_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .min()
        .reset_index(level=0, drop=True)
    )


def add_accel_exhaustion_features(panel):
    out = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = out.groupby("ts_code", sort=False)
    if "close_qfq" not in out.columns:
        out["close_qfq"] = out["close"]
    if "amount" not in out.columns:
        out["amount"] = 0.0

    out["_ma20_ax"] = rolling_mean_by_code(out, "close_qfq", 20)
    out["_ma60_ax"] = rolling_mean_by_code(out, "close_qfq", 30)
    out["_ret_5_ax"] = grouped["close_qfq"].pct_change(5, fill_method=None)
    out["_ret_10_ax"] = grouped["close_qfq"].pct_change(10, fill_method=None)
    out["_ret_20_ax"] = grouped["close_qfq"].pct_change(20, fill_method=None)
    out["_ret_63_ax"] = grouped["close_qfq"].pct_change(63, fill_method=None)
    out["_slope_5_ax"] = out["_ret_5_ax"] / 5.0
    out["_slope_10_ax"] = out["_ret_10_ax"] / 10.0
    out["_prev_slope_10_ax"] = grouped["_slope_10_ax"].shift(5)
    out["_accel_10_ax"] = out["_slope_10_ax"] - out["_prev_slope_10_ax"]
    out["_high_20_ax"] = rolling_max_by_code(out, "close_qfq", 20)
    out["_low_20_ax"] = rolling_min_by_code(out, "close_qfq", 20)
    out["_drop_from_20_high_ax"] = out["close_qfq"] / out["_high_20_ax"] - 1.0
    out["_range_20_ax"] = out["_high_20_ax"] / out["_low_20_ax"] - 1.0
    out["_amount_ma20_ax"] = rolling_mean_by_code(out, "amount", 20)
    out["_amount_ma5_ax"] = rolling_mean_by_code(out, "amount", 5)
    out["_amount_ratio_5_20_ax"] = out["_amount_ma5_ax"] / out["_amount_ma20_ax"]

    prior_accel = (
        (out["_ret_10_ax"] >= 0.05)
        | (grouped["_ret_10_ax"].shift(5) >= 0.18)
        | (grouped["_accel_10_ax"].shift(5) >= 0.010)
        | (grouped["_range_20_ax"].shift(1) >= 0.28)
    )
    recent_exhaustion = (
        (out["_ret_5_ax"] <= -0.06)
        | (out["_drop_from_20_high_ax"] <= -0.12)
    )
    activity_confirm = out["_amount_ratio_5_20_ax"].fillna(0.0) >= 1.15
    out["up_accel_exhaustion"] = (
        prior_accel
        & recent_exhaustion
        & activity_confirm
        & (out["close_qfq"] > out["_ma60_ax"] * 0.80)
    )

    out["bear_down_accel_risk"] = (
        (out["close_qfq"] < out["_ma20_ax"])
        & (out["_ma20_ax"] <= out["_ma60_ax"] * 1.05)
        & (out["_ret_20_ax"] < -0.10)
        & (out["_ret_5_ax"] < -0.04)
        & (out["_slope_5_ax"] < out["_slope_10_ax"])
    )

    current_v6 = (
        out["early_weakness_downtrend"].fillna(False).astype(bool)
        if "early_weakness_downtrend" in out.columns
        else pd.Series(False, index=out.index)
    )
    out["accel_exhaustion_forbid_buy"] = (
        out["up_accel_exhaustion"].fillna(False)
        | out["bear_down_accel_risk"].fillna(False)
        | current_v6
    )
    drop_cols = [col for col in out.columns if col.endswith("_ax")]
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


@contextmanager
def patched_exhaustion_exit(v6, enabled):
    original = v6.has_bearish_volume_signal

    def has_exhaustion_or_bearish_volume(code, pos, signal_panel):
        if original(code, pos, signal_panel):
            return True
        if not enabled or code not in signal_panel.index:
            return False
        profit_pct = v6.calc_position_profit_pct(code, pos, signal_panel)
        if profit_pct is None or profit_pct <= 0:
            return False
        row = signal_panel.loc[code]
        return bool(row.get("up_accel_exhaustion", False))

    try:
        v6.has_bearish_volume_signal = has_exhaustion_or_bearish_volume
        yield
    finally:
        v6.has_bearish_volume_signal = original


def calc_nav_metrics(nav, trades=None):
    nav = nav.copy()
    nav["date"] = pd.to_datetime(nav["date"])
    nav = nav.sort_values("date")
    daily_ret = nav["nav"].pct_change().dropna()
    total_ret = nav["nav"].iloc[-1] / nav["nav"].iloc[0] - 1.0
    days = max((nav["date"].iloc[-1] - nav["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    drawdown = nav["nav"] / nav["nav"].cummax() - 1.0
    max_dd = float(drawdown.min())
    sharpe = 0.0
    if daily_ret.std(ddof=0) > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std(ddof=0) * math.sqrt(252))
    return {
        "final_nav": float(nav["nav"].iloc[-1]),
        "total_return_pct": total_ret * 100.0,
        "annual_return_pct": annual_ret * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "calmar_ratio": (annual_ret / abs(max_dd)) if max_dd < 0 else 0.0,
        "sharpe": sharpe,
        "trade_records": int(len(trades)) if trades is not None else 0,
    }


def run_case(v6, panel, market, case):
    rows = []
    for period, (start, end) in PERIODS.items():
        with patched_v6_downtrend_filter(v6, case["filter_col"]):
            with patched_exhaustion_exit(v6, case["exit_enabled"]):
                nav, trades, rebalance, scores, holdings, stats = v6.run_backtest(panel, market, start, end)
        metrics = calc_nav_metrics(nav, trades)
        rows.append({
            "case": case["name"],
            "period": period,
            "description": case["description"],
            "filter_col": case["filter_col"] or "early_weakness_downtrend",
            "exit_enabled": bool(case["exit_enabled"]),
            "final_nav": metrics["final_nav"],
            "total_return_pct": metrics["total_return_pct"],
            "annual_return_pct": metrics["annual_return_pct"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
            "calmar_ratio": metrics["calmar_ratio"],
            "sharpe": metrics["sharpe"],
            "trade_records": metrics["trade_records"],
            "downtrend_filter_candidate_blocks": int(stats.get("downtrend_filter_candidate_blocks", 0)),
            "bearish_volume_exit_fills": int(stats.get("bearish_volume_exit_fills", 0)),
        })
    return rows


def segment_metrics_from_nav(nav, start, end):
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    segment = frame[(frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))].copy()
    if len(segment) < 2:
        return {
            "total_return_pct": float("nan"),
            "annual_return_pct": float("nan"),
            "max_drawdown_pct": float("nan"),
            "calmar_ratio": float("nan"),
        }
    return calc_nav_metrics(segment)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_baseline_matches_v6(results, v6_summary):
    baseline = results[(results["case"] == "baseline_v6") & (results["period"] == "full")].iloc[0]
    checks = [
        ("final_nav", 0.01),
        ("total_return_pct", 0.01),
        ("annual_return_pct", 0.01),
        ("max_drawdown_pct", 0.01),
        ("calmar_ratio", 0.001),
        ("trade_records", 0.0),
    ]
    for key, tolerance in checks:
        actual = float(baseline[key])
        expected = float(v6_summary[key])
        if abs(actual - expected) > tolerance:
            raise AssertionError(f"baseline mismatch {key}: {actual} != {expected}")


def select_walk_forward_best(results):
    train = results[results["period"] == "train_2018_2021"].copy()
    train = train.sort_values(
        ["calmar_ratio", "total_return_pct", "max_drawdown_pct"],
        ascending=[False, False, False],
    )
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


def baseline_delta_rows(baseline, v6_summary):
    keys = ["final_nav", "total_return_pct", "annual_return_pct", "max_drawdown_pct", "calmar_ratio", "trade_records"]
    return [
        {
            "field": key,
            "experiment": float(baseline[key]),
            "v6_summary": float(v6_summary[key]),
            "delta": float(baseline[key]) - float(v6_summary[key]),
        }
        for key in keys
    ]


def recommendation_for(best, baseline, walk):
    if (
        best["case"] != "baseline_v6"
        and best["total_return_pct"] > baseline["total_return_pct"]
        and best["max_drawdown_pct"] >= baseline["max_drawdown_pct"] - 3.0
        and walk["validate_total_return_pct"] >= baseline["total_return_pct"] * 0.2
    ):
        return "建议进入合并候选：收益高于 v6，回撤未明显恶化；但合并前必须做参数邻域和交易成本压力测试。"
    return "暂不建议合并：收益、回撤或 walk-forward 稳定性没有同时超过当前 v6。"


def annual_return_table(nav_by_label):
    rows = []
    for label, nav in nav_by_label.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        yearly = frame.set_index("date")["nav"].resample("YE").last().dropna()
        previous = yearly.shift(1)
        previous.iloc[0] = float(frame["nav"].iloc[0])
        for date, value in (yearly / previous - 1.0).items():
            rows.append({"strategy": label, "year": int(date.year), "return_pct": float(value * 100.0)})
    return pd.DataFrame(rows)


def monthly_return_table(nav_by_label):
    rows = []
    for label, nav in nav_by_label.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        monthly = frame.set_index("date")["nav"].resample("ME").last().dropna()
        previous = monthly.shift(1)
        previous.iloc[0] = float(frame["nav"].iloc[0])
        for date, value in (monthly / previous - 1.0).items():
            rows.append({"strategy": label, "month": date.strftime("%Y-%m"), "return_pct": float(value * 100.0)})
    return pd.DataFrame(rows)


def html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_return_matrix(rows, row_key, col_key, value_key, strategies):
    table = rows.pivot(index=row_key, columns=col_key, values=value_key)
    cols = [strategy for strategy in strategies if strategy in table.columns]
    table = table[cols].reset_index()
    return table


def write_readme(results, v4_summary, v5_summary, v6_summary, walk):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    baseline = full[full["case"] == "baseline_v6"].iloc[0]
    best = full.iloc[0]
    lines = [
        "# v6 Acceleration Exhaustion Evolution",
        "",
        "## 工作推进进度",
        "- 头脑风暴专家：趋势专家判断，上涨加速不是卖点，加速后失速才是风险。",
        "- 设计专家：量化专家把理论落到两个风险标签：`up_accel_exhaustion` 与 `bear_down_accel_risk`。",
        "- 数据专家：检查 Tushare 接口清单，本轮使用 v6 已准备好的 063/137 等字段，不新增 061/080 盘后字段，避免未来函数和归因混杂。",
        "- 开发专家：只在 tmp 下新增实验脚本和测试，复用 v6 引擎，不修改 v4/v5/v6 生产代码。",
        "- Review 专家：baseline_v6 必须复现 v6 summary，HTML 必须给出 v4/v5/v6/候选对比。",
        "",
        "## Web 复核",
    ]
    for note in SOURCE_NOTES:
        lines.append(f"- {note['topic']}：{note['note']} 来源：{note['url']}")
    lines.extend([
        "",
        "## Tushare 数据判断",
        "- 063 stk_factor_pro：已有日线、复权、BBI、成交额、技术因子，适合本轮价格/斜率/失速量化。",
        "- 137 idx_factor_pro：已有上证指数技术面因子，v6 已用于市场状态和大盘风控。",
        "- 061 cyq_perf、080 moneyflow：此前 v6_moneyflow 实验已验证不优于 v6；本轮不重复叠加。",
        "",
        "## 全周期结果",
        "| case | 总收益 | 年化 | 最大回撤 | Calmar | 交易数 | 过滤候选 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for _, row in full.iterrows():
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | {int(row['trade_records'])} | "
            f"{int(row['downtrend_filter_candidate_blocks'])} |"
        )
    lines.extend([
        "",
        "## v4/v5/v6 对比",
        f"- v4：总收益 {v4_summary['total_return_pct']:.2f}%，最大回撤 {v4_summary['max_drawdown_pct']:.2f}%。",
        f"- v5：总收益 {v5_summary['total_return_pct']:.2f}%，最大回撤 {v5_summary['max_drawdown_pct']:.2f}%。",
        f"- v6：总收益 {v6_summary['total_return_pct']:.2f}%，最大回撤 {v6_summary['max_drawdown_pct']:.2f}%。",
        "",
        "## baseline_v6 复现校验",
        "| 字段 | 实验值 | v6 summary | 差值 |",
        "|---|---:|---:|---:|",
    ])
    for row in baseline_delta_rows(baseline, v6_summary):
        lines.append(f"| {row['field']} | {row['experiment']:.6f} | {row['v6_summary']:.6f} | {row['delta']:.8f} |")
    lines.extend([
        "",
        "## Walk-forward",
        f"- 训练期选择：{walk['selected_case']}，训练收益 {walk['train_total_return_pct']:.2f}%，Calmar {walk['train_calmar_ratio']:.4f}。",
        f"- 验证期收益：{walk['validate_total_return_pct']:.2f}%，Calmar {walk['validate_calmar_ratio']:.4f}。",
        f"- 确认期收益：{walk['confirm_total_return_pct']:.2f}%，Calmar {walk['confirm_calmar_ratio']:.4f}。",
        "",
        "## 建议",
        f"- 全周期最佳：{best['case']}。",
        f"- {recommendation_for(best, baseline, walk)}",
    ])
    README_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_html_report(results, v4_summary, v5_summary, v6_summary, walk, nav_by_label):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    baseline = full[full["case"] == "baseline_v6"].iloc[0]
    best = full.iloc[0]
    advice = recommendation_for(best, baseline, walk)

    all_labels = ["v4", "v5", "v6", str(best["case"])]
    annual = build_return_matrix(annual_return_table(nav_by_label), "year", "strategy", "return_pct", all_labels)
    monthly = build_return_matrix(monthly_return_table(nav_by_label), "month", "strategy", "return_pct", all_labels)

    def rows_from_matrix(frame, first_col):
        out = []
        for _, row in frame.iterrows():
            cells = [f"<td>{html_escape(row[first_col])}</td>"]
            for col in frame.columns[1:]:
                cells.append(f"<td>{row[col]:.2f}%</td>" if pd.notna(row[col]) else "<td>-</td>")
            out.append("<tr>" + "".join(cells) + "</tr>")
        return "".join(out)

    full_rows = []
    for _, row in full.iterrows():
        klass = "best" if row["case"] == best["case"] else ("baseline" if row["case"] == "baseline_v6" else "")
        full_rows.append(
            f"<tr class=\"{klass}\"><td>{html_escape(row['case'])}</td>"
            f"<td>{row['total_return_pct']:.2f}%</td><td>{row['annual_return_pct']:.2f}%</td>"
            f"<td>{row['max_drawdown_pct']:.2f}%</td><td>{row['calmar_ratio']:.4f}</td>"
            f"<td>{int(row['trade_records'])}</td><td>{int(row['downtrend_filter_candidate_blocks'])}</td>"
            f"<td>{html_escape(row['description'])}</td></tr>"
        )
    baseline_rows = "".join(
        f"<tr><td>{html_escape(row['field'])}</td><td>{row['experiment']:.6f}</td>"
        f"<td>{row['v6_summary']:.6f}</td><td>{row['delta']:.8f}</td></tr>"
        for row in baseline_delta_rows(baseline, v6_summary)
    )
    source_rows = "".join(
        f"<tr><td>{html_escape(note['topic'])}</td><td>{html_escape(note['note'])}</td>"
        f"<td><a href=\"{note['url']}\">{html_escape(note['source'])}</a></td></tr>"
        for note in SOURCE_NOTES
    )
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>v6 加速失速进化实验</title>
<style>
body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f5f7fa; color: #1f2937; }}
header {{ background: #263238; color: white; padding: 22px 30px; }}
main {{ padding: 24px 30px; }}
section {{ background: white; border: 1px solid #d7dee8; padding: 18px; margin-bottom: 18px; }}
.grid {{ display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 12px; }}
.metric {{ background: #fafafa; border: 1px solid #d7dee8; padding: 12px; }}
.metric strong {{ display: block; font-size: 24px; margin-top: 6px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #d7dee8; padding: 7px 8px; text-align: right; }}
th:first-child, td:first-child, th:last-child, td:last-child {{ text-align: left; }}
th {{ background: #34495e; color: white; }}
tr.best {{ background: #fff7d6; font-weight: 700; }}
tr.baseline {{ background: #e0f2fe; font-weight: 700; }}
.advice {{ background: #fff7ed; border-color: #fed7aa; }}
.sources td {{ text-align: left; }}
</style>
</head>
<body>
<header>
<h1>v6 加速失速进化实验</h1>
<p>理论落地：熊市下跌加速不买；牛市上涨加速不直接卖，只在加速后失速时收紧买入/退出。</p>
</header>
<main>
<section>
<h2>核心结果</h2>
<div class="grid">
<div class="metric"><span>v4 总收益</span><strong>{v4_summary['total_return_pct']:.2f}%</strong><span>回撤 {v4_summary['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>v5 总收益</span><strong>{v5_summary['total_return_pct']:.2f}%</strong><span>回撤 {v5_summary['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>当前 v6</span><strong>{baseline['total_return_pct']:.2f}%</strong><span>回撤 {baseline['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>本轮最佳</span><strong>{best['total_return_pct']:.2f}%</strong><span>{html_escape(best['case'])}</span></div>
</div>
</section>
<section class="advice">
<h2>是否合并</h2>
<p><strong>{html_escape(advice)}</strong></p>
<p>Walk-forward 训练选择：{html_escape(walk['selected_case'])}；验证期收益 {walk['validate_total_return_pct']:.2f}%，确认期收益 {walk['confirm_total_return_pct']:.2f}%。</p>
</section>
<section>
<h2>全周期候选对比</h2>
<table>
<thead><tr><th>case</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>Calmar</th><th>交易数</th><th>过滤候选</th><th>说明</th></tr></thead>
<tbody>{''.join(full_rows)}</tbody>
</table>
</section>
<section>
<h2>年度收益</h2>
<table>
<thead><tr>{''.join(f'<th>{html_escape(col)}</th>' for col in annual.columns)}</tr></thead>
<tbody>{rows_from_matrix(annual, 'year')}</tbody>
</table>
</section>
<section>
<h2>月度收益</h2>
<table>
<thead><tr>{''.join(f'<th>{html_escape(col)}</th>' for col in monthly.columns)}</tr></thead>
<tbody>{rows_from_matrix(monthly, 'month')}</tbody>
</table>
</section>
<section>
<h2>baseline_v6 复现校验</h2>
<table>
<thead><tr><th>字段</th><th>实验值</th><th>v6 summary</th><th>差值</th></tr></thead>
<tbody>{baseline_rows}</tbody>
</table>
</section>
<section>
<h2>依据与定义</h2>
<table class="sources">
<thead><tr><th>主题</th><th>程序化处理</th><th>来源</th></tr></thead>
<tbody>{source_rows}</tbody>
</table>
</section>
<section>
<h2>下一步</h2>
<ol>
<li>若本轮最佳超过 v6：先做参数邻域、滑点、成交额容量压力测试，再考虑合并。</li>
<li>若没有超过 v6：保留当前 v6，不继续叠加复杂失速规则。</li>
<li>不要直接使用“上涨加速卖出”或“下跌加速买入”。本轮也没有这么做。</li>
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

    v4_summary = load_json(V4_DIR / "output" / "summary.json")
    v5_summary = load_json(V5_DIR / "output" / "summary.json")
    v6_summary = load_json(v6_config.SUMMARY_PATH)

    columns = list(dict.fromkeys([*v6.PANEL_COLUMNS, "close_qfq", "amount"]))
    panel = pd.read_parquet(v6_config.PANEL_PATH, columns=columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = add_accel_exhaustion_features(panel)
    market = v6.load_market_index()

    rows = []
    full_nav = {}
    for case in CASES:
        print(f"running {case['name']}", flush=True)
        with patched_v6_downtrend_filter(v6, case["filter_col"]):
            with patched_exhaustion_exit(v6, case["exit_enabled"]):
                nav, trades, rebalance, scores, holdings, stats = v6.run_backtest(panel, market, "2018-01-01", "2026-05-14")
        metrics = calc_nav_metrics(nav, trades)
        rows.append({
            "case": case["name"],
            "period": "full",
            "description": case["description"],
            "filter_col": case["filter_col"] or "early_weakness_downtrend",
            "exit_enabled": bool(case["exit_enabled"]),
            "final_nav": metrics["final_nav"],
            "total_return_pct": metrics["total_return_pct"],
            "annual_return_pct": metrics["annual_return_pct"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
            "calmar_ratio": metrics["calmar_ratio"],
            "sharpe": metrics["sharpe"],
            "trade_records": metrics["trade_records"],
            "downtrend_filter_candidate_blocks": int(stats.get("downtrend_filter_candidate_blocks", 0)),
            "bearish_volume_exit_fills": int(stats.get("bearish_volume_exit_fills", 0)),
        })
        for period, (start, end) in {
            "train_2018_2021": ("2018-01-01", "2021-12-31"),
            "validate_2022_2024": ("2022-01-01", "2024-12-31"),
            "confirm_2025_2026": ("2025-01-01", "2026-05-14"),
        }.items():
            seg = segment_metrics_from_nav(nav, start, end)
            rows.append({
                "case": case["name"],
                "period": period,
                "description": case["description"],
                "filter_col": case["filter_col"] or "early_weakness_downtrend",
                "exit_enabled": bool(case["exit_enabled"]),
                "final_nav": float("nan"),
                "total_return_pct": seg["total_return_pct"],
                "annual_return_pct": seg["annual_return_pct"],
                "max_drawdown_pct": seg["max_drawdown_pct"],
                "calmar_ratio": seg["calmar_ratio"],
                "sharpe": float("nan"),
                "trade_records": int(len(trades)),
                "downtrend_filter_candidate_blocks": int(stats.get("downtrend_filter_candidate_blocks", 0)),
                "bearish_volume_exit_fills": int(stats.get("bearish_volume_exit_fills", 0)),
            })
        full_nav[case["name"]] = nav

    results = pd.DataFrame(rows)
    assert_baseline_matches_v6(results, v6_summary)
    walk = select_walk_forward_best(results)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)

    best_case = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False).iloc[0]["case"]
    nav_by_label = {
        "v4": pd.read_csv(V4_DIR / "output" / "nav_series.csv"),
        "v5": pd.read_csv(V5_DIR / "output" / "nav_series.csv"),
        "v6": pd.read_csv(V6_DIR / "output" / "nav_series.csv"),
        str(best_case): full_nav[str(best_case)],
    }
    write_readme(results, v4_summary, v5_summary, v6_summary, walk)
    write_html_report(results, v4_summary, v5_summary, v6_summary, walk, nav_by_label)
    print(f"Results saved: {RESULTS_PATH}")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()

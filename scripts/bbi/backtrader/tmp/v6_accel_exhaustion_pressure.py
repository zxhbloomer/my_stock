import csv
from contextlib import contextmanager
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
BASE_EXPERIMENT_PATH = TMP_DIR / "v6_accel_exhaustion_evolution.py"
OUTPUT_DIR = TMP_DIR / "v6_accel_exhaustion_pressure_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "v6_accel_exhaustion_pressure_README.md"

VARIANTS = [
    {
        "name": "candidate_default_cost0",
        "drop_ret5_threshold": -0.06,
        "drop_from_high_threshold": -0.12,
        "activity_ratio_threshold": 1.15,
        "bear_ret20_threshold": -0.10,
        "bear_ret5_threshold": -0.04,
        "extra_cost_bps": 0,
        "description": "上一轮最佳候选原参数。",
    },
    {
        "name": "drop_loose",
        "drop_ret5_threshold": -0.04,
        "drop_from_high_threshold": -0.10,
        "activity_ratio_threshold": 1.15,
        "bear_ret20_threshold": -0.10,
        "bear_ret5_threshold": -0.04,
        "extra_cost_bps": 0,
        "description": "失速阈值放松，更多过滤。",
    },
    {
        "name": "drop_strict",
        "drop_ret5_threshold": -0.10,
        "drop_from_high_threshold": -0.16,
        "activity_ratio_threshold": 1.15,
        "bear_ret20_threshold": -0.10,
        "bear_ret5_threshold": -0.04,
        "extra_cost_bps": 0,
        "description": "失速阈值收紧，更少过滤。",
    },
    {
        "name": "candidate_default_cost5bps",
        "drop_ret5_threshold": -0.06,
        "drop_from_high_threshold": -0.12,
        "activity_ratio_threshold": 1.15,
        "bear_ret20_threshold": -0.10,
        "bear_ret5_threshold": -0.04,
        "extra_cost_bps": 5,
        "description": "原参数，买卖各增加 5bps 成本。",
    },
    {
        "name": "candidate_default_cost10bps",
        "drop_ret5_threshold": -0.06,
        "drop_from_high_threshold": -0.12,
        "activity_ratio_threshold": 1.15,
        "bear_ret20_threshold": -0.10,
        "bear_ret5_threshold": -0.04,
        "extra_cost_bps": 10,
        "description": "原参数，买卖各增加 10bps 成本。",
    },
]
VARIANTS_BY_NAME = {variant["name"]: variant for variant in VARIANTS}


def load_module(module_name, path):
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
    return load_module("v6_run_backtest_accel_pressure", V6_DIR / "20_run_backtest.py")


def load_base_experiment():
    return load_module("v6_accel_exhaustion_base_for_pressure", BASE_EXPERIMENT_PATH)


def add_features_for_variant(panel, variant):
    base = load_base_experiment()
    out = base.add_accel_exhaustion_features(panel)
    grouped = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True).groupby("ts_code", sort=False)
    work = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    if "close_qfq" not in work.columns:
        work["close_qfq"] = work["close"]
    if "amount" not in work.columns:
        work["amount"] = 0.0
    high20 = base.rolling_max_by_code(work, "close_qfq", 20)
    ma20 = base.rolling_mean_by_code(work, "close_qfq", 20)
    ma60 = base.rolling_mean_by_code(work, "close_qfq", 30)
    ret5 = grouped["close_qfq"].pct_change(5, fill_method=None)
    ret10 = grouped["close_qfq"].pct_change(10, fill_method=None)
    ret20 = grouped["close_qfq"].pct_change(20, fill_method=None)
    range20 = high20 / base.rolling_min_by_code(work, "close_qfq", 20) - 1.0
    amount_ratio = base.rolling_mean_by_code(work, "amount", 5) / base.rolling_mean_by_code(work, "amount", 20)
    prior_accel = (ret10 >= 0.05) | (grouped["close_qfq"].pct_change(10, fill_method=None).shift(5) >= 0.18) | (range20.shift(1) >= 0.28)
    recent_exhaustion = (
        (ret5 <= variant["drop_ret5_threshold"])
        | (work["close_qfq"] / high20 - 1.0 <= variant["drop_from_high_threshold"])
    )
    out["up_accel_exhaustion"] = (
        prior_accel
        & recent_exhaustion
        & (amount_ratio.fillna(0.0) >= variant["activity_ratio_threshold"])
        & (work["close_qfq"] > ma60 * 0.80)
    )
    slope5 = ret5 / 5.0
    slope10 = ret10 / 10.0
    out["bear_down_accel_risk"] = (
        (work["close_qfq"] < ma20)
        & (ma20 <= ma60 * 1.05)
        & (ret20 < variant["bear_ret20_threshold"])
        & (ret5 < variant["bear_ret5_threshold"])
        & (slope5 < slope10)
    )
    current_v6 = out["early_weakness_downtrend"].fillna(False).astype(bool)
    out["accel_exhaustion_forbid_buy"] = (
        out["up_accel_exhaustion"].fillna(False)
        | out["bear_down_accel_risk"].fillna(False)
        | current_v6
    )
    return out


@contextmanager
def patched_commission(v6, extra_cost_bps):
    original_buy = v6.COMMISSION_BUY
    original_sell = v6.COMMISSION_SELL
    extra = float(extra_cost_bps) / 10000.0
    try:
        v6.COMMISSION_BUY = original_buy + extra
        v6.COMMISSION_SELL = original_sell + extra
        yield
    finally:
        v6.COMMISSION_BUY = original_buy
        v6.COMMISSION_SELL = original_sell


def run_variant(v6, panel, market, variant):
    base = load_base_experiment()
    feature_panel = add_features_for_variant(panel, variant)
    with base.patched_v6_downtrend_filter(v6, "accel_exhaustion_forbid_buy"):
        with base.patched_exhaustion_exit(v6, False):
            with patched_commission(v6, variant["extra_cost_bps"]):
                nav, trades, rebalance, scores, holdings, stats = v6.run_backtest(
                    feature_panel,
                    market,
                    "2018-01-01",
                    "2026-05-14",
                )
    metrics = base.calc_nav_metrics(nav, trades)
    return {
        "case": variant["name"],
        "description": variant["description"],
        "extra_cost_bps": variant["extra_cost_bps"],
        "final_nav": metrics["final_nav"],
        "total_return_pct": metrics["total_return_pct"],
        "annual_return_pct": metrics["annual_return_pct"],
        "max_drawdown_pct": metrics["max_drawdown_pct"],
        "calmar_ratio": metrics["calmar_ratio"],
        "trade_records": metrics["trade_records"],
        "downtrend_filter_candidate_blocks": int(stats.get("downtrend_filter_candidate_blocks", 0)),
    }, nav


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def recommendation(best, baseline_v6, default_candidate, cost10):
    if (
        default_candidate["total_return_pct"] > baseline_v6["total_return_pct"]
        and default_candidate["max_drawdown_pct"] >= baseline_v6["max_drawdown_pct"] - 3.0
        and cost10["total_return_pct"] > baseline_v6["total_return_pct"]
    ):
        return "建议进入合并候选：原参数在 10bps 成本压力下仍高于 v6。下一步做滚动年份选择和更细参数邻域。"
    return "暂不建议合并：成本压力或邻域稳定性不足，继续保留候选。"


def write_outputs(results, summaries):
    rows = sorted(results, key=lambda row: row["total_return_pct"], reverse=True)
    baseline_v6 = summaries["v6"]
    default_candidate = next(row for row in rows if row["case"] == "candidate_default_cost0")
    cost10 = next(row for row in rows if row["case"] == "candidate_default_cost10bps")
    best = rows[0]
    advice = recommendation(best, baseline_v6, default_candidate, cost10)

    readme_lines = [
        "# v6 Acceleration Exhaustion Pressure Test",
        "",
        "## 目的",
        "围绕上一轮候选 `forbid_accel_exhaustion_buy` 做参数邻域和交易成本压力测试。",
        "",
        "## 结论",
        f"- 最佳变体：{best['case']}，总收益 {best['total_return_pct']:.2f}%，最大回撤 {best['max_drawdown_pct']:.2f}%。",
        f"- 原候选 0bps：{default_candidate['total_return_pct']:.2f}%，最大回撤 {default_candidate['max_drawdown_pct']:.2f}%。",
        f"- 原候选 10bps：{cost10['total_return_pct']:.2f}%，最大回撤 {cost10['max_drawdown_pct']:.2f}%。",
        f"- v6 基线：{baseline_v6['total_return_pct']:.2f}%，最大回撤 {baseline_v6['max_drawdown_pct']:.2f}%。",
        f"- 建议：{advice}",
        "",
        "## 结果",
        "| case | 总收益 | 年化 | 最大回撤 | Calmar | 成本bps | 交易数 | 过滤候选 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        readme_lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | {row['extra_cost_bps']} | "
            f"{row['trade_records']} | {row['downtrend_filter_candidate_blocks']} |"
        )
    README_PATH.write_text("\n".join(readme_lines), encoding="utf-8")

    table_rows = "".join(
        f"<tr class=\"{'best' if row['case'] == best['case'] else ''}\"><td>{html_escape(row['case'])}</td>"
        f"<td>{row['total_return_pct']:.2f}%</td><td>{row['annual_return_pct']:.2f}%</td>"
        f"<td>{row['max_drawdown_pct']:.2f}%</td><td>{row['calmar_ratio']:.4f}</td>"
        f"<td>{row['extra_cost_bps']}</td><td>{row['trade_records']}</td>"
        f"<td>{row['downtrend_filter_candidate_blocks']}</td><td>{html_escape(row['description'])}</td></tr>"
        for row in rows
    )
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>v6 加速失速压力测试</title>
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
.advice {{ background: #fff7ed; border-color: #fed7aa; }}
</style>
</head>
<body>
<header>
<h1>v6 加速失速候选压力测试</h1>
<p>记住并围绕上一轮最佳候选做邻域和成本压力，不扩散新规则。</p>
</header>
<main>
<section>
<h2>核心对比</h2>
<div class="grid">
<div class="metric"><span>v4</span><strong>{summaries['v4']['total_return_pct']:.2f}%</strong><span>回撤 {summaries['v4']['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>v5</span><strong>{summaries['v5']['total_return_pct']:.2f}%</strong><span>回撤 {summaries['v5']['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>v6</span><strong>{baseline_v6['total_return_pct']:.2f}%</strong><span>回撤 {baseline_v6['max_drawdown_pct']:.2f}%</span></div>
<div class="metric"><span>候选 10bps</span><strong>{cost10['total_return_pct']:.2f}%</strong><span>回撤 {cost10['max_drawdown_pct']:.2f}%</span></div>
</div>
</section>
<section class="advice">
<h2>建议</h2>
<p><strong>{html_escape(advice)}</strong></p>
</section>
<section>
<h2>压力测试结果</h2>
<table>
<thead><tr><th>case</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>Calmar</th><th>成本bps</th><th>交易数</th><th>过滤候选</th><th>说明</th></tr></thead>
<tbody>{table_rows}</tbody>
</table>
</section>
</main>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v6 = load_v6_module()
    import config as v6_config

    columns = list(dict.fromkeys([*v6.PANEL_COLUMNS, "close_qfq", "amount"]))
    panel = pd.read_parquet(v6_config.PANEL_PATH, columns=columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = v6.load_market_index()

    results = []
    for variant in VARIANTS:
        print(f"running {variant['name']}", flush=True)
        row, nav = run_variant(v6, panel, market, variant)
        results.append(row)

    pd.DataFrame(results).to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    summaries = {
        "v4": load_json(V4_DIR / "output" / "summary.json"),
        "v5": load_json(V5_DIR / "output" / "summary.json"),
        "v6": load_json(V6_DIR / "output" / "summary.json"),
    }
    write_outputs(results, summaries)
    print(f"Results saved: {RESULTS_PATH}")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()

import csv
from contextlib import contextmanager
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "v6_cost_pressure_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "v6_cost_pressure_README.md"
ROBUST_PATH = TMP_DIR / "v6_downtrend_robustness_experiment.py"
BASE_REPORT_PATH = TMP_DIR / "v6_uptrend_evolution_experiment.py"

CASES = (
    {"label": "current_v6", "ma": 20, "slope": 10, "ret": 21},
    {"label": "ret42_challenger", "ma": 20, "slope": 10, "ret": 42},
)
EXTRA_COST_BPS = (0, 5, 10)


def load_module(module_name, path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ROBUST = load_module("v6_downtrend_robustness_for_cost_pressure", ROBUST_PATH)
BASE = load_module("v6_base_report_for_cost_pressure", BASE_REPORT_PATH)


def case_name(case):
    return case["label"]


def load_v6_module():
    return ROBUST.load_v6_module()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@contextmanager
def patched_extra_cost(v6, extra_bps):
    original = v6.calc_commission

    def calc_commission_with_extra_cost(amount, is_buy):
        return original(amount, is_buy) + abs(float(amount)) * float(extra_bps) / 10000.0

    try:
        v6.calc_commission = calc_commission_with_extra_cost
        yield
    finally:
        v6.calc_commission = original


def reset_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def run_case(v6, panel, market, case, extra_bps):
    variant = f"{case_name(case)}_cost{extra_bps}bps"
    variant_dir = OUTPUT_DIR / variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    with ROBUST.patched_downtrend_flag(v6, ROBUST.flag_name(case)), patched_extra_cost(v6, extra_bps):
        nav, trades, rebalance, scores, holdings, stats = v6.run_backtest(panel, market, "2018-01-01", None)
    stats = dict(stats)
    stats.update({
        "case": case_name(case),
        "ma": case["ma"],
        "slope": case["slope"],
        "ret": case["ret"],
        "extra_cost_bps": int(extra_bps),
        "variant": variant,
    })
    nav.to_csv(variant_dir / "nav_series.csv", index=False)
    trades.to_csv(variant_dir / "trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    rebalance.to_csv(variant_dir / "rebalance_log.csv", index=False)
    scores.to_csv(variant_dir / "strength_scores.csv", index=False)
    (variant_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"nav": nav, "trades": trades, "rebalance": rebalance, "scores": scores, "stats": stats}


def load_baseline_outputs():
    return BASE.load_baseline_outputs()


def row_from_result(label, result):
    metrics = BASE.calc_nav_metrics(result["nav"], result["trades"])
    metrics["strategy"] = label
    metrics["case"] = result["stats"].get("case", label)
    metrics["extra_cost_bps"] = int(result["stats"].get("extra_cost_bps", 0))
    metrics["trade_records"] = int(result["stats"].get("trade_records", len(result["trades"])))
    metrics["downtrend_blocks"] = int(result["stats"].get("downtrend_filter_candidate_blocks", 0))
    if "commission" in result["trades"].columns:
        metrics["total_commission"] = float(pd.to_numeric(result["trades"]["commission"], errors="coerce").fillna(0.0).sum())
    else:
        metrics["total_commission"] = 0.0
    return metrics


def merge_recommendation(current_row, challenger_row):
    current_nav = float(current_row["final_nav"])
    challenger_nav = float(challenger_row["final_nav"])
    current_dd = float(current_row["max_drawdown_pct"])
    challenger_dd = float(challenger_row["max_drawdown_pct"])
    if challenger_nav > current_nav and challenger_dd >= current_dd - 3.0:
        return "可作为候选，但仍需样本外复核：ret42 在该成本下超过 current_v6，且回撤未超过 3 个百分点警戒。"
    if challenger_nav > current_nav:
        return "不建议合并：ret42 净值更高，但最大回撤恶化超过 3 个百分点警戒。"
    return "不建议合并：current_v6 在该成本下仍优于 ret42 或风险收益更稳。"


def build_report(baselines, experiments, expert_notes):
    nav_by_label = {label: data["nav"] for label, data in baselines.items()}
    nav_by_label.update({label: data["nav"] for label, data in experiments.items()})

    rows = []
    for label, data in baselines.items():
        metrics = BASE.calc_nav_metrics(data["nav"], data["trades"])
        metrics["strategy"] = label
        metrics["case"] = label
        metrics["extra_cost_bps"] = 0
        metrics["trade_records"] = int(data["summary"].get("trade_records", len(data["trades"])))
        metrics["downtrend_blocks"] = int(data["summary"].get("downtrend_filter_candidate_blocks", 0))
        if "commission" in data["trades"].columns:
            metrics["total_commission"] = float(pd.to_numeric(data["trades"]["commission"], errors="coerce").fillna(0.0).sum())
        else:
            metrics["total_commission"] = 0.0
        rows.append(metrics)
    for label, result in experiments.items():
        rows.append(row_from_result(label, result))

    summary = pd.DataFrame(rows)
    ordered = [
        "strategy", "case", "extra_cost_bps", "final_nav", "total_return_pct", "annual_return_pct",
        "max_drawdown_pct", "calmar_ratio", "sharpe", "sortino", "win_rate_pct", "empty_rate_pct",
        "trade_records", "downtrend_blocks", "total_commission",
    ]
    for col in ordered:
        if col not in summary.columns:
            summary[col] = float("nan")
    summary = summary[ordered]

    cost_rows = summary[summary["strategy"].str.contains("_cost", na=False)].copy()
    recommendations = []
    for bps in EXTRA_COST_BPS:
        current = cost_rows[(cost_rows["case"] == "current_v6") & (cost_rows["extra_cost_bps"] == bps)].iloc[0]
        challenger = cost_rows[(cost_rows["case"] == "ret42_challenger") & (cost_rows["extra_cost_bps"] == bps)].iloc[0]
        recommendations.append(f"{bps}bps：{merge_recommendation(current, challenger)}")

    annual = BASE.annual_return_table(nav_by_label).pivot(index="year", columns="strategy", values="return_pct").reset_index()
    monthly = BASE.monthly_return_table(nav_by_label).pivot(index="month", columns="strategy", values="return_pct").reset_index()
    monthly = monthly.tail(36)
    best = str(summary.sort_values(["final_nav", "calmar_ratio"], ascending=[False, False]).iloc[0]["strategy"])
    final_recommendation = "不建议替换 v6 当前参数。ret42 只在部分单点成本场景有净值优势，且结果不单调，不能证明更稳健。"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v6 成本压力测试</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #111827; }}
h1, h2 {{ margin: 18px 0 10px; }}
.note {{ padding: 12px; background: #f3f4f6; border-left: 4px solid #2563eb; margin: 12px 0; line-height: 1.7; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 10px 0 22px; }}
th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #374151; color: white; position: sticky; top: 0; }}
.wide {{ max-height: 520px; overflow: auto; border: 1px solid #d1d5db; }}
.pos {{ color: #dc2626; }}
.neg {{ color: #16a34a; }}
code {{ background: #f3f4f6; padding: 1px 4px; }}
</style>
</head>
<body>
<h1>v6 成本压力测试</h1>
<div class="note">
<b>最终建议：</b>{final_recommendation}<br>
<b>本表最高净值：</b>{best}<br>
<b>测试方法：</b>在 v6 已有佣金基础上，对买入和卖出额外增加 0/5/10 bps 成本；不改信号、不改成交价，只看成本敏感性。
</div>
<div class="note">
<b>解释限制：</b>成本提高后结果不一定单调，因为更高成本会改变现金余额、整手股数、是否能继续买入以及后续交易路径。10bps 单点超过 current_v6 不能单独作为合并依据。
</div>
<h2>专家与数据说明</h2>
<div class="note">{expert_notes}</div>
<h2>按成本场景的合并判断</h2>
<div class="note">{'<br>'.join(recommendations)}</div>
<h2>总览对比</h2>
{BASE.html_table(summary, float_cols=set(summary.columns) - {"strategy", "case", "extra_cost_bps", "trade_records", "downtrend_blocks"}, negative_is_bad_cols={"max_drawdown_pct"})}
<h2>年度收益率对比（%）</h2>
<div class="wide">{BASE.html_table(annual, float_cols=set(annual.columns) - {"year"})}</div>
<h2>最近 36 个月收益率对比（%）</h2>
<div class="wide">{BASE.html_table(monthly, float_cols=set(monthly.columns) - {"month"})}</div>
<h2>下一步</h2>
<ol>
<li>保留 current_v6 参数，不合并 ret42。</li>
<li>下一轮不要继续参数寻优，改做 v6 年度失效期诊断，重点看 2022-2024 弱段的亏损来源。</li>
<li>如要进入实盘候选，还需要更真实的冲击成本模型和停牌/涨跌停成交延迟复核。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")
    summary.to_csv(OUTPUT_DIR / "comparison_summary.csv", index=False)
    annual.to_csv(OUTPUT_DIR / "annual_returns.csv", index=False)
    monthly.to_csv(OUTPUT_DIR / "monthly_returns_tail36.csv", index=False)
    return summary


def assert_current_cost0_matches_v6(experiments, v6_summary):
    result = experiments["current_v6_cost0bps"]["stats"]
    for key, tolerance in [
        ("final_nav", 1e-2),
        ("total_return_pct", 1e-4),
        ("annual_return_pct", 1e-4),
        ("max_drawdown_pct", 1e-4),
        ("calmar_ratio", 1e-4),
        ("trade_records", 0),
    ]:
        actual = float(result[key])
        expected = float(v6_summary[key])
        if abs(actual - expected) > tolerance:
            raise AssertionError(f"current_v6_cost0bps {key}={actual} does not match v6 summary {expected}")


def append_readme(text):
    with README_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n" + text.rstrip() + "\n")


def main():
    print("[v6-cost] resetting output", flush=True)
    reset_output_dir()
    v6 = load_v6_module()
    required_columns = list(dict.fromkeys(v6.PANEL_COLUMNS + ["close_qfq"]))
    print("[v6-cost] loading panel", flush=True)
    panel = pd.read_parquet(V6_DIR / "output" / "panel.parquet", columns=required_columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    print(f"[v6-cost] panel rows={len(panel):,}", flush=True)
    print("[v6-cost] loading market", flush=True)
    market = pd.read_parquet(V6_DIR / "output" / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")

    print("[v6-cost] adding downtrend case flags", flush=True)
    panel = ROBUST.add_param_downtrend_features(panel, CASES)

    experiments = {}
    for case in CASES:
        for bps in EXTRA_COST_BPS:
            label = f"{case_name(case)}_cost{bps}bps"
            print(f"[v6-cost] running {label}", flush=True)
            experiments[label] = run_case(v6, panel, market, case, bps)
            stats = experiments[label]["stats"]
            print(
                f"[v6-cost] {label} final_nav={stats['final_nav']:.2f} "
                f"return={stats['total_return_pct']:.4f}% max_dd={stats['max_drawdown_pct']:.4f}%",
                flush=True,
            )

    baselines = load_baseline_outputs()
    assert_current_cost0_matches_v6(experiments, baselines["v6"]["summary"])
    expert_notes = (
        "Tavily 本轮成本/滑点搜索因额度限制失败，未使用其他搜索工具。"
        "本地设计评审原则：成本压力测试比继续堆过滤器更接近实盘；"
        "额外 bps 成本只改 commission，不改交易信号，便于归因。"
    )
    summary = build_report(baselines, experiments, expert_notes)
    best_row = summary.sort_values(["final_nav", "calmar_ratio"], ascending=[False, False]).iloc[0]
    append_readme(
        "# v6 Cost Pressure Progress\n\n"
        f"- Report: `{REPORT_PATH}`\n"
        f"- Best by final NAV: `{best_row['strategy']}` final_nav={best_row['final_nav']:.2f}, "
        f"annual={best_row['annual_return_pct']:.2f}%, max_dd={best_row['max_drawdown_pct']:.2f}%.\n"
        "- Merge recommendation is written in the HTML report.\n"
    )
    print(f"[v6-cost] report={REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()

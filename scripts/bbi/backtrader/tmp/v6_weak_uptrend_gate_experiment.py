import csv
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
OUTPUT_DIR = TMP_DIR / "v6_weak_uptrend_gate_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "v6_weak_uptrend_gate_README.md"
BASE_EXPERIMENT_PATH = TMP_DIR / "v6_uptrend_evolution_experiment.py"

VARIANTS = (
    "neutral_weak_price_confirm",
    "neutral_rs_confirm",
    "weak_regime_no_new_low",
    "bear_exception_uptrend",
    "neutral_price_gate",
    "neutral_rs_gate",
    "post_bear_strict_gate",
)


def load_base_experiment():
    spec = importlib.util.spec_from_file_location("v6_uptrend_base_for_weak_gate", BASE_EXPERIMENT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = load_base_experiment()


def load_v6_backtest_module():
    return BASE.load_v6_backtest_module()


def add_weak_uptrend_features(panel, market):
    return BASE.add_uptrend_features(panel, market)


def load_baseline_outputs():
    return BASE.load_baseline_outputs()


def price_gate(candidates):
    return (
        (candidates["close_qfq"] > candidates["ma60_qfq"])
        & (candidates["ma20_qfq"] > candidates["ma60_qfq"])
        & (candidates["ma60_slope_20"] > 0)
    )


def weak_price_confirm(candidates):
    return (
        (candidates["close_qfq"] > candidates["ma20_qfq"])
        & (candidates["ma20_slope_10"] > 0)
        & (candidates["ret_21"] > 0)
    )


def neutral_rs_confirm(candidates):
    return (
        (candidates["ret_63"] > candidates["market_ret_60"])
        | (candidates["rps_126"] >= 0.60)
    )


def no_new_low_confirm(candidates):
    return (
        (candidates["range_pos_63"] >= 0.35)
        | (candidates["high_pos_63"] >= 0.75)
    )


def rs_gate(candidates):
    return (
        price_gate(candidates)
        & (candidates["ret_63"] > candidates["market_ret_60"])
        & (candidates["rps_126"] >= 0.70)
        & (candidates["high_pos_252"] >= 0.75)
    )


def strict_post_bear_gate(candidates):
    return (
        (candidates["close_qfq"] > candidates["ma60_qfq"])
        & (candidates["ma60_qfq"] > candidates["ma120_qfq"])
        & (candidates["ma120_qfq"] > candidates["ma200_qfq"])
        & (candidates["ma120_slope_20"] > 0)
        & (candidates["ma200_slope_20"] > 0)
        & (candidates["ret_63"] > candidates["market_ret_60"])
        & (candidates["rps_126"] >= 0.80)
        & (candidates["high_pos_252"] >= 0.80)
    )


def filter_weak_uptrend_candidates(candidates, variant, market_regime_name, recent_bear):
    if candidates.empty:
        return candidates.copy()
    if market_regime_name == "bull":
        return candidates.copy()
    if variant == "neutral_weak_price_confirm":
        mask = weak_price_confirm(candidates)
    elif variant == "neutral_rs_confirm":
        mask = neutral_rs_confirm(candidates)
    elif variant == "weak_regime_no_new_low":
        mask = no_new_low_confirm(candidates)
    elif variant == "bear_exception_uptrend":
        if market_regime_name == "bear":
            mask = (
                (candidates["close_qfq"] > candidates["ma60_qfq"])
                & (candidates["ma60_slope_20"] > 0)
                & (candidates["rps_126"] >= 0.80)
                & (candidates["high_pos_252"] >= 0.75)
            )
        else:
            mask = neutral_rs_confirm(candidates)
    elif variant == "neutral_price_gate":
        mask = price_gate(candidates)
    elif variant == "neutral_rs_gate":
        mask = rs_gate(candidates)
    elif variant == "post_bear_strict_gate":
        mask = strict_post_bear_gate(candidates) if recent_bear else rs_gate(candidates)
    else:
        raise ValueError(f"unknown weak uptrend variant: {variant}")
    return candidates[mask.fillna(False)].copy()


def recent_bear_dates(market_regime, lookback=63):
    if market_regime is None or market_regime.empty:
        return set()
    regime = market_regime.copy().sort_index()
    recent = regime["regime"].eq("bear").rolling(lookback, min_periods=1).max().fillna(0).astype(bool)
    return set(regime.index[recent])


def reset_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def run_variant(variant, panel, market):
    v6 = load_v6_backtest_module()
    market_regime = v6.build_market_regime(market, panel)
    regime_by_date = market_regime["regime"].to_dict() if market_regime is not None else {}
    recent_bear_set = recent_bear_dates(market_regime)
    original_score_candidates = v6.score_candidates
    original_build_market_regime = v6.build_market_regime

    if variant == "bear_exception_uptrend" and market_regime is not None:
        adjusted_market_regime = market_regime.copy()
        adjusted_market_regime["regime"] = adjusted_market_regime["regime"].replace({"bear": "neutral"})

        def build_market_regime_with_bear_exception(_market, _panel):
            return adjusted_market_regime

        v6.build_market_regime = build_market_regime_with_bear_exception

    def score_candidates_with_gate(signal_panel, diagnostics=None):
        scored = original_score_candidates(signal_panel, diagnostics=diagnostics)
        if scored.empty:
            return scored
        signal_date = pd.Timestamp(scored["trade_date"].iloc[0])
        regime = regime_by_date.get(signal_date, "unknown")
        recent_bear = signal_date in recent_bear_set
        filtered = filter_weak_uptrend_candidates(scored, variant, regime, recent_bear)
        blocked = len(scored) - len(filtered)
        if diagnostics is not None:
            diagnostics["weak_uptrend_variant"] = variant
            diagnostics["weak_uptrend_candidate_blocks"] = (
                diagnostics.get("weak_uptrend_candidate_blocks", 0) + int(blocked)
            )
            if blocked:
                diagnostics["weak_uptrend_signal_days"] = diagnostics.get("weak_uptrend_signal_days", 0) + 1
            if recent_bear:
                diagnostics["weak_uptrend_recent_bear_signal_days"] = (
                    diagnostics.get("weak_uptrend_recent_bear_signal_days", 0) + 1
                )
        return filtered

    try:
        v6.score_candidates = score_candidates_with_gate
        nav, trades, rebalance, scores, holdings, stats = v6.run_backtest(
            panel,
            market,
            v6.BACKTEST_START_DATE,
            None,
        )
    finally:
        v6.score_candidates = original_score_candidates
        v6.build_market_regime = original_build_market_regime

    stats["weak_uptrend_variant"] = variant
    stats["last_holdings"] = holdings
    variant_dir = OUTPUT_DIR / variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    nav.to_csv(variant_dir / "nav_series.csv", index=False)
    trades.to_csv(variant_dir / "trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    rebalance.to_csv(variant_dir / "rebalance_log.csv", index=False)
    scores.to_csv(variant_dir / "strength_scores.csv", index=False)
    (variant_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {
        "nav": nav,
        "trades": trades,
        "rebalance": rebalance,
        "scores": scores,
        "stats": stats,
    }


def build_report(baselines, experiments, expert_notes):
    nav_by_label = {label: data["nav"] for label, data in baselines.items()}
    nav_by_label.update({label: data["nav"] for label, data in experiments.items()})

    rows = []
    for label, data in baselines.items():
        metrics = BASE.calc_nav_metrics(data["nav"], data["trades"])
        metrics["strategy"] = label
        metrics["trade_records"] = int(data["summary"].get("trade_records", len(data["trades"])))
        metrics["weak_blocks"] = 0
        rows.append(metrics)
    for label, data in experiments.items():
        metrics = BASE.calc_nav_metrics(data["nav"], data["trades"])
        metrics["strategy"] = label
        metrics["trade_records"] = int(data["stats"].get("trade_records", len(data["trades"])))
        metrics["weak_blocks"] = int(data["stats"].get("weak_uptrend_candidate_blocks", 0))
        rows.append(metrics)

    summary = pd.DataFrame(rows)
    ordered = [
        "strategy", "final_nav", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
        "calmar_ratio", "sharpe", "sortino", "win_rate_pct", "empty_rate_pct",
        "trade_records", "weak_blocks",
    ]
    for col in ordered:
        if col not in summary.columns:
            summary[col] = float("nan")
    summary = summary[ordered]

    annual = BASE.annual_return_table(nav_by_label).pivot(index="year", columns="strategy", values="return_pct").reset_index()
    monthly = BASE.monthly_return_table(nav_by_label).pivot(index="month", columns="strategy", values="return_pct").reset_index()
    monthly = monthly.tail(36)

    best = str(summary.sort_values(["final_nav", "calmar_ratio"], ascending=[False, False]).iloc[0]["strategy"])
    v6_nav = float(summary.loc[summary["strategy"] == "v6", "final_nav"].iloc[0])
    best_nav = float(summary.loc[summary["strategy"] == best, "final_nav"].iloc[0])
    if best == "v6":
        recommendation = "不建议合并：v6 原版仍是本组最高净值。"
    elif best in {"v4", "v5"}:
        recommendation = f"不建议合并：{best} 高于本轮变体，说明上涨趋势门控没有解决核心收益问题。"
    elif best_nav > v6_nav:
        recommendation = f"可作为 v7 候选：{best} 高于 v6，但需要先做阈值邻域和样本外复核。"
    else:
        recommendation = "不建议合并：本轮变体未稳定超过 v6。"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v6 弱市上涨趋势门控实验</title>
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
<h1>v6 弱市上涨趋势门控实验</h1>
<div class="note">
<b>合并建议：</b>{recommendation}<br>
<b>本轮最优：</b>{best}<br>
<b>设计：</b>多数变体牛市不额外过滤，neutral/unknown 或近期熊市后才要求上涨趋势确认；<code>bear_exception_uptrend</code> 是单独观察项，会放开 v6 熊市禁买，不能按普通门控解读。
</div>
<div class="note">
<b>代码评审提醒：</b><code>bear_exception_uptrend</code> 会改变 v6 熊市风控路径，关闭熊市禁买和熊市确认后的浮亏卖出效果；其净值和回撤均显著变差，只能作为反证，不可合并。
</div>
<h2>证据和专家意见</h2>
<div class="note">{expert_notes}</div>
<h2>总览对比</h2>
{BASE.html_table(summary, float_cols=set(summary.columns) - {"strategy", "trade_records", "weak_blocks"}, negative_is_bad_cols={"max_drawdown_pct"})}
<h2>年度收益率对比（%）</h2>
<div class="wide">{BASE.html_table(annual, float_cols=set(annual.columns) - {"year"})}</div>
<h2>最近 36 个月收益率对比（%）</h2>
<div class="wide">{BASE.html_table(monthly, float_cols=set(monthly.columns) - {"month"})}</div>
<h2>下一步</h2>
<ol>
<li>如果本轮最高者超过 v6，先做阈值邻域、年度拆分、股票集中度复核，不直接合并。</li>
<li>如果没有超过 v6，保留研究结论：A 股 v6 不适合简单加上涨趋势买入限制。</li>
<li>下一轮可测试经 T+1 shift 的资金流或筹码分布，但必须先防前视。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")
    summary.to_csv(OUTPUT_DIR / "comparison_summary.csv", index=False)
    annual.to_csv(OUTPUT_DIR / "annual_returns.csv", index=False)
    monthly.to_csv(OUTPUT_DIR / "monthly_returns_tail36.csv", index=False)
    return summary


def append_readme(text):
    with README_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n" + text.rstrip() + "\n")


def main():
    print("[v6-weak-uptrend] resetting output", flush=True)
    reset_output_dir()
    v6 = load_v6_backtest_module()
    required_columns = list(dict.fromkeys(v6.PANEL_COLUMNS + ["close_qfq"]))

    print("[v6-weak-uptrend] loading v6 panel", flush=True)
    panel = pd.read_parquet(V6_DIR / "output" / "panel.parquet", columns=required_columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    print(f"[v6-weak-uptrend] panel rows={len(panel):,}", flush=True)

    print("[v6-weak-uptrend] loading market index", flush=True)
    market = pd.read_parquet(V6_DIR / "output" / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")

    print("[v6-weak-uptrend] adding features", flush=True)
    panel = add_weak_uptrend_features(panel, market)

    experiments = {}
    for variant in VARIANTS:
        print(f"[v6-weak-uptrend] running {variant}", flush=True)
        experiments[variant] = run_variant(variant, panel, market)
        stats = experiments[variant]["stats"]
        print(
            f"[v6-weak-uptrend] {variant} final_nav={stats['final_nav']:.2f} "
            f"return={stats['total_return_pct']:.4f}% max_dd={stats['max_drawdown_pct']:.4f}%",
            flush=True,
        )

    baselines = load_baseline_outputs()
    expert_notes = (
        "Tavily 复核：上涨趋势常用均线多头排列、长均线向上、相对强度和 52 周强度；"
        "A 股文献显示中期动量不稳定，短期动量与反转并存，所以牛市和弱市不应使用完全相同门槛。"
    )
    summary = build_report(baselines, experiments, expert_notes)
    best_row = summary.sort_values(["final_nav", "calmar_ratio"], ascending=[False, False]).iloc[0]
    append_readme(
        "# v6 Weak Uptrend Gate Progress\n\n"
        f"- Report: `{REPORT_PATH}`\n"
        f"- Best by final NAV: `{best_row['strategy']}` final_nav={best_row['final_nav']:.2f}, "
        f"annual={best_row['annual_return_pct']:.2f}%, max_dd={best_row['max_drawdown_pct']:.2f}%.\n"
        "- Merge recommendation is written in the HTML report.\n"
    )
    print(f"[v6-weak-uptrend] report={REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()

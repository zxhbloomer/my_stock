import csv
from pathlib import Path

import pandas as pd

from v4_regime_split_strategy_experiment import load_inputs, run_case


OUTPUT_DIR = Path(__file__).parent / "v4_regime_split_neighbor_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


def build_cases():
    cases = [
        {
            "name": "current",
            "use_split": False,
            "bull_pullback": -0.05,
            "neutral_pullback": -0.05,
            "strong_pullback": -0.03,
            "bear_exit_loss_threshold": None,
        }
    ]
    for bull_pb in [-0.035, -0.04, -0.045]:
        for neutral_pb in [-0.065, -0.07, -0.075]:
            cases.append({
                "name": f"split_b{abs(bull_pb):.1%}_n{abs(neutral_pb):.1%}_bear0".replace(".", "p"),
                "use_split": True,
                "bull_pullback": bull_pb,
                "neutral_pullback": neutral_pb,
                "strong_pullback": min(-0.02, bull_pb * 0.65),
                "bear_exit_loss_threshold": 0.0,
            })
    for bull_pb, neutral_pb in [(-0.04, -0.07), (-0.04, -0.075), (-0.045, -0.07)]:
        cases.append({
            "name": f"split_b{abs(bull_pb):.1%}_n{abs(neutral_pb):.1%}_bear_m1".replace(".", "p"),
            "use_split": True,
            "bull_pullback": bull_pb,
            "neutral_pullback": neutral_pb,
            "strong_pullback": min(-0.02, bull_pb * 0.65),
            "bear_exit_loss_threshold": -0.01,
        })
    return cases


def score_case(full_row, p2018_row, p2022_row, p2025_row, current_rows):
    current_full = current_rows["full"]
    current_2018 = current_rows["2018"]
    current_2022 = current_rows["2022"]
    current_2025 = current_rows["2025"]
    score = 0.0
    score += float(full_row["annual_return_pct"]) - float(current_full["annual_return_pct"])
    score += (float(full_row["max_drawdown_pct"]) - float(current_full["max_drawdown_pct"])) * 0.15
    score += (float(p2018_row["total_return_pct"]) - float(current_2018["total_return_pct"])) * 0.08
    score += (float(p2022_row["total_return_pct"]) - float(current_2022["total_return_pct"])) * 0.08
    if float(p2025_row["total_return_pct"]) < float(current_2025["total_return_pct"]) * 0.6:
        score -= 2.0
    return round(score, 4)


def build_comparison(results):
    period_map = {
        case: {row["period"]: row for _, row in group.iterrows()}
        for case, group in results.groupby("case")
    }
    current_rows = period_map["current"]
    rows = []
    for case, periods in period_map.items():
        full = periods["full"]
        p2018 = periods["2018"]
        p2022 = periods["2022"]
        p2025 = periods["2025"]
        rows.append({
            "case": case,
            "score": score_case(full, p2018, p2022, p2025, current_rows),
            "full_total_return_pct": full["total_return_pct"],
            "full_annual_return_pct": full["annual_return_pct"],
            "full_max_drawdown_pct": full["max_drawdown_pct"],
            "return_2018_pct": p2018["total_return_pct"],
            "return_2022_pct": p2022["total_return_pct"],
            "return_2025_pct": p2025["total_return_pct"],
            "trades_full": full["trade_records"],
            "avg_cash_full_pct": full["avg_cash_pct"],
        })
    return pd.DataFrame(rows).sort_values(
        ["score", "full_annual_return_pct", "full_max_drawdown_pct"],
        ascending=[False, False, False],
    )


def write_summary(comparison):
    lines = [
        "# v4 牛熊分策略邻域实验",
        "",
        "## 目标",
        "",
        "围绕 `split_bull4_neutral7_bear0` 做小邻域搜索，比较它是否稳定优于 current v4。",
        "",
        "## 排名前十",
        "",
        "| case | score | 全区间收益 | 年化 | 最大回撤 | 2018 | 2022 | 2025 | 交易数 | 平均现金% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in comparison.head(10).iterrows():
        lines.append(
            f"| {row['case']} | {row['score']:.2f} | "
            f"{row['full_total_return_pct']:.2f}% | {row['full_annual_return_pct']:.2f}% | "
            f"{row['full_max_drawdown_pct']:.2f}% | {row['return_2018_pct']:.2f}% | "
            f"{row['return_2022_pct']:.2f}% | {row['return_2025_pct']:.2f}% | "
            f"{int(row['trades_full'])} | {row['avg_cash_full_pct']:.2f}% |"
        )
    lines.extend([
        "",
        "## 输出",
        "",
        f"- `{RESULTS_PATH.name}`",
        "- `comparison.csv`",
    ])
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment():
    v4, panel, market_for_bt, regime_by_date, regime = load_inputs()
    rows = []
    for case in build_cases():
        rows.extend(run_case(v4, panel, market_for_bt, regime_by_date, case))

    results = pd.DataFrame(rows)
    comparison = build_comparison(results)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    comparison.to_csv(OUTPUT_DIR / "comparison.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    write_summary(comparison)
    return results, comparison


def main():
    results, comparison = run_experiment()
    print(comparison.head(12).to_string(index=False))


if __name__ == "__main__":
    main()

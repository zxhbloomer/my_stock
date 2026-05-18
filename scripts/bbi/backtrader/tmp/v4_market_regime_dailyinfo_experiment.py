import csv
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from v4_regime_split_strategy_experiment import load_inputs, run_case


OUTPUT_DIR = Path(__file__).parent / "v4_market_regime_dailyinfo_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"
REGIME_PATH = OUTPUT_DIR / "market_regime_dailyinfo.csv"
DB_URL = "postgresql://root:123456@localhost:5432/my_stock"


def classify_regime_with_activity(row):
    close = float(row.get("close", np.nan))
    ma120 = float(row.get("ma120", np.nan))
    ma200 = float(row.get("ma200", np.nan))
    ma120_slope_20 = float(row.get("ma120_slope_20", np.nan))
    dd_252 = float(row.get("dd_252", np.nan))
    breadth = float(row.get("breadth_above_bbi", np.nan))
    amount_ratio = float(row.get("market_amount_ratio_20_120", np.nan))
    values = [close, ma120, ma200, ma120_slope_20, dd_252, breadth, amount_ratio]
    if any(not np.isfinite(v) for v in values):
        return "unknown"

    if dd_252 <= -0.20:
        return "bear"
    if close < ma120 and ma120_slope_20 < 0 and breadth < 0.45 and amount_ratio < 1.05:
        return "bear"
    if close > ma120 and close > ma200 and ma120_slope_20 > 0 and dd_252 > -0.10 and breadth >= 0.55:
        return "bull"
    if close > ma120 and ma120_slope_20 > 0 and breadth >= 0.55 and amount_ratio >= 1.15:
        return "bull"
    return "neutral"


def load_daily_info_activity():
    engine = create_engine(DB_URL)
    sql = text("""
        WITH ranked AS (
            SELECT
                trade_date,
                ts_code,
                amount,
                CASE
                    WHEN ts_code = 'SH_MARKET' THEN 1
                    WHEN ts_code = 'SH_A' THEN 2
                    WHEN ts_code = 'SZ_MARKET' THEN 3
                    ELSE 9
                END AS rank_no
            FROM tushare_v2."138_daily_info"
            WHERE ts_code IN ('SH_MARKET', 'SH_A', 'SZ_MARKET')
              AND amount IS NOT NULL
        ),
        sh AS (
            SELECT DISTINCT ON (trade_date)
                trade_date,
                amount AS sh_amount
            FROM ranked
            WHERE ts_code IN ('SH_MARKET', 'SH_A')
            ORDER BY trade_date, rank_no
        ),
        sz AS (
            SELECT trade_date, amount AS sz_amount
            FROM ranked
            WHERE ts_code = 'SZ_MARKET'
        )
        SELECT
            COALESCE(sh.trade_date, sz.trade_date) AS trade_date,
            sh.sh_amount,
            sz.sz_amount,
            COALESCE(sh.sh_amount, 0) + COALESCE(sz.sz_amount, 0) AS market_amount
        FROM sh
        FULL JOIN sz ON sh.trade_date = sz.trade_date
        ORDER BY trade_date
    """)
    with engine.connect() as conn:
        activity = pd.read_sql(sql, conn)
    activity["trade_date"] = pd.to_datetime(activity["trade_date"])
    activity["market_amount"] = pd.to_numeric(activity["market_amount"], errors="coerce")
    activity["market_amount_ma20"] = activity["market_amount"].rolling(20, min_periods=20).mean()
    activity["market_amount_ma120"] = activity["market_amount"].rolling(120, min_periods=120).mean()
    activity["market_amount_ratio_20_120"] = activity["market_amount_ma20"] / activity["market_amount_ma120"]
    return activity


def build_activity_regime(base_regime, activity):
    regime = base_regime.merge(
        activity[["trade_date", "market_amount", "market_amount_ma20", "market_amount_ma120", "market_amount_ratio_20_120"]],
        on="trade_date",
        how="left",
    )
    regime["regime_activity"] = regime.apply(classify_regime_with_activity, axis=1)
    return regime


def build_cases():
    return [
        {
            "name": "current",
            "use_split": False,
            "bull_pullback": -0.05,
            "neutral_pullback": -0.05,
            "strong_pullback": -0.03,
            "bear_exit_loss_threshold": None,
        },
        {
            "name": "activity_split_b4_n7_bear0",
            "use_split": True,
            "bull_pullback": -0.04,
            "neutral_pullback": -0.07,
            "strong_pullback": -0.026,
            "bear_exit_loss_threshold": 0.0,
        },
        {
            "name": "activity_split_b4_n75_bear0",
            "use_split": True,
            "bull_pullback": -0.04,
            "neutral_pullback": -0.075,
            "strong_pullback": -0.026,
            "bear_exit_loss_threshold": 0.0,
        },
        {
            "name": "activity_split_b35_n75_bear0",
            "use_split": True,
            "bull_pullback": -0.035,
            "neutral_pullback": -0.075,
            "strong_pullback": -0.023,
            "bear_exit_loss_threshold": 0.0,
        },
    ]


def run_experiment():
    v4, panel, market_for_bt, _old_regime_by_date, base_regime = load_inputs()
    activity = load_daily_info_activity()
    regime = build_activity_regime(base_regime, activity)
    regime_by_date = dict(zip(pd.to_datetime(regime["trade_date"]), regime["regime_activity"]))

    rows = []
    for case in build_cases():
        rows.extend(run_case(v4, panel, market_for_bt, regime_by_date, case))

    results = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    regime.to_csv(REGIME_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    write_summary(results, regime)
    return results, regime


def write_summary(results, regime):
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    p2018 = results[results["period"] == "2018"].sort_values("total_return_pct", ascending=False)
    p2025 = results[results["period"] == "2025"].sort_values("total_return_pct", ascending=False)
    counts = regime[regime["trade_date"] >= pd.Timestamp("2018-01-01")]["regime_activity"].value_counts()
    lines = [
        "# v4 daily_info 增强牛熊状态实验",
        "",
        "## 新增数据",
        "",
        "- 使用 `tushare_v2.\"138_daily_info\"`。",
        "- 上交所优先用 `SH_MARKET`，早期没有则用 `SH_A`；深交所用 `SZ_MARKET`。",
        "- `market_amount_ratio_20_120 = 20日市场成交均值 / 120日市场成交均值`。",
        "",
        "## 增强规则",
        "",
        "- 原 bull/bear 规则保留。",
        "- 若指数站上 MA120、MA120 斜率为正、BBI 宽度 >= 55%、成交活跃度 >= 1.15，则也判定为 bull。",
        "- 弱趋势、低宽度、低成交活跃度共同出现时判定 bear。",
        "",
        "## 状态天数",
        "",
    ]
    for name, count in counts.items():
        lines.append(f"- {name}: {int(count)}")
    lines.extend([
        "",
        "## 全区间结果",
        "",
        "| case | 总收益 | 年化 | 最大回撤 | 平均现金% | 交易数 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for _, row in full.iterrows():
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | "
            f"{row['annual_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['avg_cash_pct']:.2f}% | {int(row['trade_records'])} |"
        )
    lines.extend([
        "",
        "## 2018 结果",
        "",
        "| case | 2018收益 | 最大回撤 | 交易数 |",
        "|---|---:|---:|---:|",
    ])
    for _, row in p2018.iterrows():
        lines.append(f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | {int(row['trade_records'])} |")
    lines.extend([
        "",
        "## 2025 结果",
        "",
        "| case | 2025收益 | 最大回撤 | 交易数 |",
        "|---|---:|---:|---:|",
    ])
    for _, row in p2025.iterrows():
        lines.append(f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | {int(row['trade_records'])} |")
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    results, regime = run_experiment()
    print(regime[regime["trade_date"] >= pd.Timestamp("2018-01-01")]["regime_activity"].value_counts().to_string())
    print()
    full = results[results["period"] == "full"].sort_values("total_return_pct", ascending=False)
    print(full[["case", "total_return_pct", "annual_return_pct", "max_drawdown_pct", "avg_cash_pct", "trade_records"]].to_string(index=False))
    print()
    p2025 = results[results["period"] == "2025"].sort_values("total_return_pct", ascending=False)
    print(p2025[["case", "total_return_pct", "max_drawdown_pct", "trade_records"]].to_string(index=False))


if __name__ == "__main__":
    main()

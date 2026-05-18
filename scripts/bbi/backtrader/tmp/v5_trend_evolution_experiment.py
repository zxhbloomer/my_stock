import csv
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "scripts" / "bbi" / "backtrader" / "v5").exists():
            return parent
    return start.resolve().parents[4]


ROOT = find_repo_root(Path(__file__))
V5_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v5"
V5_OUTPUT = V5_DIR / "output"
OUTPUT_DIR = Path(__file__).parent / "v5_trend_evolution_output"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"


CASES = [
    {
        "name": "baseline_v5",
        "ret_126_min": None,
        "above_ratio_63_min": None,
        "max_holdings": None,
        "max_total_exposure": None,
    },
    {
        "name": "trend126",
        "ret_126_min": 0.0,
        "above_ratio_63_min": None,
        "max_holdings": None,
        "max_total_exposure": None,
    },
    {
        "name": "trend126_above60",
        "ret_126_min": 0.0,
        "above_ratio_63_min": 0.60,
        "max_holdings": None,
        "max_total_exposure": None,
    },
    {
        "name": "exposure600_hold6",
        "ret_126_min": None,
        "above_ratio_63_min": None,
        "max_holdings": 6,
        "max_total_exposure": 600_000.0,
    },
    {
        "name": "exposure700_hold7",
        "ret_126_min": None,
        "above_ratio_63_min": None,
        "max_holdings": 7,
        "max_total_exposure": 700_000.0,
    },
    {
        "name": "trend126_exposure600",
        "ret_126_min": 0.0,
        "above_ratio_63_min": None,
        "max_holdings": 6,
        "max_total_exposure": 600_000.0,
    },
    {
        "name": "trend126_above60_exposure600",
        "ret_126_min": 0.0,
        "above_ratio_63_min": 0.60,
        "max_holdings": 6,
        "max_total_exposure": 600_000.0,
    },
]


def load_v5_module():
    if str(V5_DIR) not in sys.path:
        sys.path.insert(0, str(V5_DIR))
    spec = importlib.util.spec_from_file_location("v5_run_backtest", V5_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_trend_filters(candidates, case):
    filtered = candidates
    if case["ret_126_min"] is not None:
        filtered = filtered[
            filtered["ret_126"].notna()
            & (filtered["ret_126"] > float(case["ret_126_min"]))
        ]
    if case["above_ratio_63_min"] is not None:
        filtered = filtered[
            filtered["above_ratio_63"].notna()
            & (filtered["above_ratio_63"] >= float(case["above_ratio_63_min"]))
        ]
    return filtered.copy()


def make_score_candidates(original_score_candidates, case):
    def wrapped_score_candidates(signal_panel):
        candidates = original_score_candidates(signal_panel)
        if candidates.empty:
            return candidates
        return apply_trend_filters(candidates, case)

    return wrapped_score_candidates


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
        "low_holdings_days": int((nav_df["holdings"] < 5).sum()),
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


def build_trade_feature_index(panel, all_dates):
    feature_cols = [
        "ret_126",
        "above_ratio_63",
        "above_ratio_126",
        "ret_63",
        "pullback_63",
    ]
    if len(all_dates) < 2:
        return pd.DataFrame(columns=["rebalance_date", "ts_code", *feature_cols])
    next_date_by_signal_date = {
        all_dates[i - 1]: all_dates[i]
        for i in range(1, len(all_dates))
    }
    features = panel.loc[
        panel["trade_date"].isin(next_date_by_signal_date),
        ["trade_date", "ts_code", *feature_cols],
    ].copy()
    features["rebalance_date"] = features["trade_date"].map(next_date_by_signal_date)
    return features.drop(columns=["trade_date"])


def build_buy_diagnostics(trades_df, trade_feature_index):
    empty = {
        "buy_ret_126_le_0": 0,
        "buy_above_ratio_63_lt_60": 0,
        "buy_missing_signal_features": 0,
        "buy_avg_ret_126": None,
        "buy_avg_above_ratio_63": None,
    }
    if trades_df.empty or trade_feature_index.empty:
        return empty
    buys = trades_df[trades_df["action"] == "buy"].copy()
    if buys.empty:
        return empty
    features = trade_feature_index.copy()
    features["rebalance_date"] = pd.to_datetime(features["rebalance_date"])
    buys["date"] = pd.to_datetime(buys["date"])
    merged = buys.merge(
        features,
        left_on=["date", "ts_code"],
        right_on=["rebalance_date", "ts_code"],
        how="left",
    )
    diagnostic_cols = ["ret_126", "above_ratio_63", "above_ratio_126", "ret_63", "pullback_63"]
    missing_signal_features = merged[diagnostic_cols].isna().any(axis=1)
    return {
        "buy_ret_126_le_0": int((pd.to_numeric(merged["ret_126"], errors="coerce") <= 0).sum()),
        "buy_above_ratio_63_lt_60": int((pd.to_numeric(merged["above_ratio_63"], errors="coerce") < 0.60).sum()),
        "buy_missing_signal_features": int(missing_signal_features.sum()),
        "buy_avg_ret_126": round(float(pd.to_numeric(merged["ret_126"], errors="coerce").mean()), 4),
        "buy_avg_above_ratio_63": round(float(pd.to_numeric(merged["above_ratio_63"], errors="coerce").mean()), 4),
    }


def run_case(v5, panel, market, trade_feature_index, case):
    original_score_candidates = v5.score_candidates
    original_max_holdings = v5.LONG_MAX_HOLDINGS
    original_max_total_exposure = v5.LONG_MAX_TOTAL_EXPOSURE
    try:
        v5.score_candidates = make_score_candidates(original_score_candidates, case)
        if case["max_holdings"] is not None:
            v5.LONG_MAX_HOLDINGS = int(case["max_holdings"])
        if case["max_total_exposure"] is not None:
            v5.LONG_MAX_TOTAL_EXPOSURE = float(case["max_total_exposure"])
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v5.run_backtest(
            panel,
            market,
            "2018-01-01",
            None,
        )
    finally:
        v5.score_candidates = original_score_candidates
        v5.LONG_MAX_HOLDINGS = original_max_holdings
        v5.LONG_MAX_TOTAL_EXPOSURE = original_max_total_exposure

    periods = {
        "2018": ("2018-01-01", "2018-12-31"),
        "2022": ("2022-01-01", "2022-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "full": ("2018-01-01", str(pd.to_datetime(nav_df["date"]).max())[:10]),
    }
    buy_diag = build_buy_diagnostics(trades_df, trade_feature_index)
    rows = []
    for period_name, (start, end) in periods.items():
        row = {
            "case": case["name"],
            "period": period_name,
            "ret_126_min": case["ret_126_min"],
            "above_ratio_63_min": case["above_ratio_63_min"],
            "max_holdings": case["max_holdings"] or original_max_holdings,
            "max_total_exposure": case["max_total_exposure"] or original_max_total_exposure,
            "summary_buy_fills": stats.get("buy_fills", 0),
            "summary_sell_fills": stats.get("sell_fills", 0),
            "summary_regime_bear_exit_fills": stats.get("regime_bear_exit_fills", 0),
        }
        row.update(summarize_period(nav_df, trades_df, start, end))
        if period_name == "full":
            row.update(buy_diag)
        rows.append(row)
    return rows


def load_v1_summary():
    path = V5_DIR.parent / "v1" / "output" / "stats_summary.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if df.empty:
        return {}
    numeric_cols = ["total_return", "annual_return", "max_drawdown"]
    out = {"rows": int(len(df))}
    for col in numeric_cols:
        if col in df.columns:
            out[f"{col}_mean"] = round(float(pd.to_numeric(df[col], errors="coerce").mean()), 4)
            out[f"{col}_median"] = round(float(pd.to_numeric(df[col], errors="coerce").median()), 4)
    return out


def write_summary(results, v5_summary, v1_summary):
    full = results[results["period"] == "full"].sort_values(
        ["annual_return_pct", "max_drawdown_pct"],
        ascending=[False, False],
    )
    period_map = {
        case: {row["period"]: row for _, row in group.iterrows()}
        for case, group in results.groupby("case")
    }
    lines = [
        "# v5 上涨趋势自动进化实验",
        "",
        "## 基准",
        "",
        f"- v5 总收益: {v5_summary.get('total_return_pct')}%",
        f"- v5 年化: {v5_summary.get('annual_return_pct')}%",
        f"- v5 最大回撤: {v5_summary.get('max_drawdown_pct')}%",
        f"- v1 统计行数: {v1_summary.get('rows', 'missing')}",
        "",
        "## 全区间排序",
        "",
        "| case | 总收益 | 年化 | 最大回撤 | Calmar | 2018 | 2022 | 2025 | 平均现金% | 平均持仓 | 交易数 | ret126<=0买入 | above63<0.60买入 | 缺失诊断 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in full.iterrows():
        rows = period_map[row["case"]]
        lines.append(
            f"| {row['case']} | {row['total_return_pct']:.2f}% | {row['annual_return_pct']:.2f}% | "
            f"{row['max_drawdown_pct']:.2f}% | {row['calmar_ratio']:.4f} | "
            f"{rows['2018']['total_return_pct']:.2f}% | {rows['2022']['total_return_pct']:.2f}% | "
            f"{rows['2025']['total_return_pct']:.2f}% | {row['avg_cash_pct']:.2f}% | "
            f"{row['avg_holdings']:.2f} | {int(row['trade_records'])} | "
            f"{int(row.get('buy_ret_126_le_0', 0))} | {int(row.get('buy_above_ratio_63_lt_60', 0))} | "
            f"{int(row.get('buy_missing_signal_features', 0))} |"
        )
    lines.extend([
        "",
        "## 判断",
        "",
        "- `ret126<=0买入` 用于检查是否仍在买半年下跌趋势。",
        "- `above63<0.60买入` 用于检查对应趋势阈值，不等于完整证明没有抄底。",
        "- `缺失诊断` 必须为 0，否则买入趋势检查不完整。",
        "- 曝光提升若收益上升但回撤同步扩大，应视为加风险而不是策略质量提升。",
    ])
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def assert_baseline_matches_v5(results, v5_summary):
    baseline = results[(results["case"] == "baseline_v5") & (results["period"] == "full")]
    if baseline.empty:
        raise AssertionError("baseline_v5 full-period result is missing")
    row = baseline.iloc[0]
    checks = [
        ("total_return_pct", 1e-4),
        ("annual_return_pct", 1e-4),
        ("max_drawdown_pct", 1e-4),
        ("trade_records", 0),
    ]
    for key, tolerance in checks:
        actual = float(row[key])
        expected = float(v5_summary[key])
        if abs(actual - expected) > tolerance:
            raise AssertionError(f"baseline_v5 {key}={actual} does not match v5 summary {expected}")


def run_experiment():
    v5 = load_v5_module()
    import config as v5_config
    panel = pd.read_parquet(v5.PANEL_PATH, columns=v5.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = v5.load_market_index()
    panel_for_dates = panel.copy()
    if v5_config.END_DATE:
        panel_for_dates = panel_for_dates[panel_for_dates["trade_date"] <= pd.Timestamp(v5_config.END_DATE)].copy()
    panel_for_dates = panel_for_dates[panel_for_dates["trade_date"] >= pd.Timestamp(v5_config.BACKTEST_START_DATE)].copy()
    all_dates = sorted(panel_for_dates["trade_date"].drop_duplicates())
    trade_feature_index = build_trade_feature_index(panel, all_dates)

    rows = []
    for case in CASES:
        rows.extend(run_case(v5, panel, market, trade_feature_index, case))

    results = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    v5_summary = json.loads(v5.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert_baseline_matches_v5(results, v5_summary)
    v1_summary = load_v1_summary()
    write_summary(results, v5_summary, v1_summary)
    return results


def main():
    results = run_experiment()
    full = results[results["period"] == "full"].sort_values("annual_return_pct", ascending=False)
    print(full[[
        "case", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
        "calmar_ratio", "avg_cash_pct", "trade_records",
        "buy_ret_126_le_0", "buy_above_ratio_63_lt_60",
        "buy_missing_signal_features",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()

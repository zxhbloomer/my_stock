from __future__ import annotations

import csv
import html
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "tmp_v4_uptrend_bbi_breakout_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v4_uptrend_bbi_breakout_README.md"

BREAKOUT_DISTANCE = 0.005
VARIANTS = (
    "short_bbi_breakout",
    "short_bbi_breakout_trend",
    "dual_bbi_breakout_trend",
    "adaptive_bbi_breakout_trend",
)

SOURCE_NOTES = [
    {
        "topic": "BBI",
        "source": "Tavily search: Bull Bear Index / 多空指标",
        "note": "BBI is a composite moving-average trend line. Common signal: price crosses above BBI while BBI turns upward.",
    },
    {
        "topic": "Trend following",
        "source": "Tavily search: trend following, time-series momentum, moving average rules",
        "note": "Trend rules should be treated as right-side confirmation and evaluated with drawdown and yearly behavior, not only final return.",
    },
    {
        "topic": "Tushare",
        "source": "docs/tushare/接口清单.md",
        "note": "This run reuses v6 prepared daily, limit, ST/suspension, liquidity, and stk_factor_pro fields. Post-close moneyflow/cyq data are intentionally excluded.",
    },
]


def load_module_from_path(module_name: str, path: Path):
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


def load_v6_backtest_module():
    return load_module_from_path("v6_backtest_for_tmp_v4_bbi_breakout", V6_DIR / "20_run_backtest.py")


def rolling_mean_by_code(panel: pd.DataFrame, column: str, window: int) -> pd.Series:
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .mean()
        .reset_index(level=0, drop=True)
    )


def rolling_max_by_code(panel: pd.DataFrame, column: str, window: int) -> pd.Series:
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .max()
        .reset_index(level=0, drop=True)
    )


def add_breakout_features(panel: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    out = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True).copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    grouped = out.groupby("ts_code", sort=False)

    for window in (5, 10, 20, 60):
        col = f"ma{window}_qfq"
        if col not in out.columns:
            out[col] = rolling_mean_by_code(out, "close_qfq", window)
    out["ma20_slope_10"] = grouped["ma20_qfq"].pct_change(10, fill_method=None)
    out["ma60_slope_20"] = grouped["ma60_qfq"].pct_change(20, fill_method=None)
    out["mid_bbi_qfq"] = (out["ma5_qfq"] + out["ma10_qfq"] + out["ma20_qfq"] + out["ma60_qfq"]) / 4.0
    out["short_bbi_slope_5"] = grouped["bbi_qfq"].pct_change(5, fill_method=None)
    out["mid_bbi_slope_5"] = grouped["mid_bbi_qfq"].pct_change(5, fill_method=None)
    out["high_qfq_252"] = rolling_max_by_code(out, "close_qfq", 252)
    out["high_pos_252"] = out["close_qfq"] / out["high_qfq_252"]
    out["rps_126"] = out.groupby("trade_date", sort=False)["ret_126"].rank(pct=True)

    prev_close = grouped["close_qfq"].shift(1)
    prev_bbi = grouped["bbi_qfq"].shift(1)
    out["short_bbi_distance"] = out["close_qfq"] / out["bbi_qfq"] - 1.0
    out["short_bbi_breakout"] = (
        (prev_close <= prev_bbi)
        & (out["short_bbi_distance"] >= BREAKOUT_DISTANCE)
        & (out["short_bbi_slope_5"] > 0)
    ).fillna(False)

    market_frame = market.copy()
    if "trade_date" in market_frame.columns:
        market_frame["trade_date"] = pd.to_datetime(market_frame["trade_date"])
        market_frame = market_frame.set_index("trade_date")
    market_frame = market_frame.sort_index()
    market_ret_60 = pd.to_numeric(market_frame["close"], errors="coerce").pct_change(60)
    out = out.merge(
        market_ret_60.rename("market_ret_60"),
        left_on="trade_date",
        right_index=True,
        how="left",
    )
    return out


def filter_breakout_candidates(candidates: pd.DataFrame, variant: str, market_regime_name: str) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    base = (
        candidates["short_bbi_breakout"].fillna(False)
        & (candidates["short_bbi_distance"] >= BREAKOUT_DISTANCE)
        & (candidates["short_bbi_slope_5"] > 0)
    )
    trend = (
        (candidates["close_qfq"] > candidates["ma20_qfq"])
        & (candidates["ma20_qfq"] > candidates["ma60_qfq"])
        & (candidates["ma20_slope_10"] > 0)
        & (candidates["ma60_slope_20"] > 0)
        & (candidates["ret_63"] > candidates["market_ret_60"].fillna(0.0))
        & (candidates["ret_63"] > 0)
    )
    if variant == "short_bbi_breakout":
        mask = base
    elif variant == "short_bbi_breakout_trend":
        mask = base & trend & (candidates["rps_126"] >= 0.70) & (candidates["high_pos_252"] >= 0.80)
    elif variant == "dual_bbi_breakout_trend":
        mask = (
            base
            & trend
            & (candidates["close_qfq"] > candidates["mid_bbi_qfq"])
            & (candidates["mid_bbi_slope_5"] > 0)
            & (candidates["rps_126"] >= 0.70)
            & (candidates["high_pos_252"] >= 0.80)
        )
    elif variant == "adaptive_bbi_breakout_trend":
        if market_regime_name == "bull":
            mask = (
                base
                & trend
                & (candidates["rps_126"] >= 0.60)
                & (candidates["high_pos_252"] >= 0.70)
            )
        else:
            mask = (
                base
                & trend
                & (candidates["close_qfq"] > candidates["mid_bbi_qfq"])
                & (candidates["mid_bbi_slope_5"] > 0)
                & (candidates["rps_126"] >= 0.80)
                & (candidates["high_pos_252"] >= 0.85)
            )
    else:
        raise ValueError(f"unknown breakout variant: {variant}")
    return candidates[mask.fillna(False)].copy()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_baseline_outputs() -> dict:
    outputs = {}
    for label, directory in (("v4", V4_DIR), ("v5", V5_DIR), ("v6", V6_DIR)):
        output = directory / "output"
        outputs[label] = {
            "summary": load_json(output / "summary.json"),
            "nav": pd.read_csv(output / "nav_series.csv"),
            "trades": pd.read_csv(output / "trade_records.csv"),
            "rebalance": pd.read_csv(output / "rebalance_log.csv"),
        }
    return outputs


def calc_nav_metrics(nav: pd.DataFrame, trades: pd.DataFrame | None = None) -> dict:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date")
    daily_ret = frame["nav"].pct_change().dropna()
    total_ret = frame["nav"].iloc[-1] / frame["nav"].iloc[0] - 1.0
    days = max((frame["date"].iloc[-1] - frame["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    drawdown = frame["nav"] / frame["nav"].cummax() - 1.0
    max_dd = float(drawdown.min())
    sharpe = 0.0
    sortino = 0.0
    if daily_ret.std(ddof=0) > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std(ddof=0) * math.sqrt(252))
    downside = daily_ret[daily_ret < 0]
    if len(downside) and downside.std(ddof=0) > 0:
        sortino = float(daily_ret.mean() / downside.std(ddof=0) * math.sqrt(252))
    empty_rate = float((frame["holdings"] == 0).mean()) if "holdings" in frame.columns else float("nan")
    win_rate = float("nan")
    if trades is not None and not trades.empty and "pnl" in trades.columns:
        sells = trades[trades["action"].astype(str).str.contains("sell", na=False)].copy()
        sells["pnl_num"] = pd.to_numeric(sells["pnl"], errors="coerce")
        sells = sells.dropna(subset=["pnl_num"])
        if not sells.empty:
            win_rate = float((sells["pnl_num"] > 0).mean())
    return {
        "final_nav": float(frame["nav"].iloc[-1]),
        "total_return_pct": total_ret * 100.0,
        "annual_return_pct": annual_ret * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "calmar_ratio": (annual_ret / abs(max_dd)) if max_dd < 0 else 0.0,
        "sharpe": sharpe,
        "sortino": sortino,
        "empty_rate_pct": empty_rate * 100.0,
        "win_rate_pct": win_rate * 100.0 if not math.isnan(win_rate) else float("nan"),
    }


def annual_return_table(nav_by_label: dict) -> pd.DataFrame:
    rows = []
    for label, nav in nav_by_label.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        yearly = frame.set_index("date")["nav"].resample("YE").last().dropna()
        if yearly.empty:
            continue
        previous = yearly.shift(1)
        previous.iloc[0] = float(frame["nav"].iloc[0])
        returns = yearly / previous - 1.0
        for date, value in returns.items():
            rows.append({"strategy": label, "year": int(date.year), "return_pct": float(value * 100.0)})
    return pd.DataFrame(rows)


def monthly_return_table(nav_by_label: dict) -> pd.DataFrame:
    rows = []
    for label, nav in nav_by_label.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        monthly = frame.set_index("date")["nav"].resample("ME").last().dropna()
        if monthly.empty:
            continue
        returns = monthly.pct_change()
        returns.iloc[0] = monthly.iloc[0] / frame["nav"].iloc[0] - 1.0
        for date, value in returns.dropna().items():
            rows.append({"strategy": label, "month": date.strftime("%Y-%m"), "return_pct": float(value * 100.0)})
    return pd.DataFrame(rows)


def html_table(df: pd.DataFrame, float_cols=None, negative_is_bad_cols=None) -> str:
    float_cols = set(float_cols or [])
    negative_is_bad_cols = set(negative_is_bad_cols or [])
    parts = ["<table>"]
    parts.append("<thead><tr>" + "".join(f"<th>{html.escape(str(col))}</th>" for col in df.columns) + "</tr></thead>")
    parts.append("<tbody>")
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            value = row[col]
            cls = ""
            if col in float_cols and pd.notna(value):
                numeric = float(value)
                text = f"{numeric:,.2f}"
                if col in negative_is_bad_cols:
                    cls = "bad" if numeric < 0 else "good" if numeric > 0 else ""
                else:
                    cls = "good" if numeric > 0 else "bad" if numeric < 0 else ""
            else:
                text = "" if pd.isna(value) else html.escape(str(value))
            cells.append(f'<td class="{cls}">{text}</td>')
        parts.append("<tr>" + "".join(cells) + "</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


def build_report(baselines: dict, experiments: dict, expert_notes: str) -> pd.DataFrame:
    nav_by_label = {label: data["nav"] for label, data in baselines.items()}
    nav_by_label.update({label: data["nav"] for label, data in experiments.items()})

    rows = []
    for label, data in baselines.items():
        metrics = calc_nav_metrics(data["nav"], data["trades"])
        metrics["strategy"] = label
        metrics["trade_records"] = int(data["summary"].get("trade_records", len(data["trades"])))
        metrics["breakout_blocks"] = float("nan")
        rows.append(metrics)
    for label, data in experiments.items():
        metrics = calc_nav_metrics(data["nav"], data["trades"])
        metrics["strategy"] = label
        metrics["trade_records"] = int(data["stats"].get("trade_records", len(data["trades"])))
        metrics["breakout_blocks"] = int(data["stats"].get("breakout_filter_candidate_blocks", 0))
        rows.append(metrics)
    summary = pd.DataFrame(rows)
    ordered = [
        "strategy", "final_nav", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
        "calmar_ratio", "sharpe", "sortino", "win_rate_pct", "empty_rate_pct",
        "trade_records", "breakout_blocks",
    ]
    summary = summary[ordered]

    annual = annual_return_table(nav_by_label)
    annual_pivot = annual.pivot(index="year", columns="strategy", values="return_pct").reset_index()
    monthly = monthly_return_table(nav_by_label)
    monthly_pivot = monthly.pivot(index="month", columns="strategy", values="return_pct").reset_index().tail(36)

    best = summary.sort_values(["final_nav", "calmar_ratio"], ascending=[False, False]).iloc[0]["strategy"]
    best_text = str(best)
    if best_text in {"v4", "v5", "v6"}:
        recommendation = f"{best_text} 仍强于本轮 BBI 突破变体，不建议合并。"
    else:
        recommendation = f"{best_text} 是本轮候选合并方向，但必须先做样本外年份和阈值邻域复核。"

    sources = "".join(
        f"<li><b>{html.escape(item['topic'])}</b>: {html.escape(item['note'])}</li>"
        for item in SOURCE_NOTES
    )
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>上涨趋势 + BBI 突破实验</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #1f2937; }}
h1, h2 {{ margin: 18px 0 10px; }}
.note {{ padding: 12px; background: #f3f4f6; border-left: 4px solid #2563eb; margin: 12px 0; line-height: 1.6; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 10px 0 22px; }}
th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #374151; color: white; position: sticky; top: 0; }}
.wide {{ max-height: 520px; overflow: auto; border: 1px solid #d1d5db; }}
.good {{ color: #dc2626; }}
.bad {{ color: #16a34a; }}
code {{ background: #f3f4f6; padding: 1px 4px; }}
</style>
</head>
<body>
<h1>上涨趋势 + BBI 突破实验</h1>
<div class="note">
<b>结论：</b>{html.escape(recommendation)}<br>
<b>本轮最优：</b>{html.escape(best_text)}<br>
<b>执行口径：</b>这是 v6 候选体系上的 BBI 突破叠加实验，不是独立 BBI 策略。信号日收盘确认，次日开盘成交；v6 的 pullback 入场门槛、手续费、涨跌停、停牌和风控逻辑仍然生效。<br>
<b>突破定义：</b>昨日收盘不高于 BBI，今日收盘至少高于 BBI 0.5%，且 5 日 BBI 斜率为正。
</div>
<h2>专家评审摘要</h2>
<div class="note">{html.escape(expert_notes)}</div>
<h2>资料与数据依据</h2>
<ul>{sources}</ul>
<h2>总览对比</h2>
{html_table(summary, float_cols=set(summary.columns) - {"strategy", "trade_records", "breakout_blocks"}, negative_is_bad_cols={"max_drawdown_pct"})}
<h2>年度收益率对比（%）</h2>
<div class="wide">{html_table(annual_pivot, float_cols=set(annual_pivot.columns) - {"year"})}</div>
<h2>最近 36 个月收益率对比（%）</h2>
<div class="wide">{html_table(monthly_pivot, float_cols=set(monthly_pivot.columns) - {"month"})}</div>
<h2>建议</h2>
<ol>
<li>若本轮变体没有超过 v6：不合并，只保留报告作为反证。</li>
<li>若某变体超过 v6：先做 2018、2021、2024、2025 分段复核，再考虑进入 v7。</li>
<li>下一轮可测试成交量确认，但必须只用信号日前已知数据。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html_doc, encoding="utf-8")
    summary.to_csv(OUTPUT_DIR / "comparison_summary.csv", index=False)
    annual_pivot.to_csv(OUTPUT_DIR / "annual_returns.csv", index=False)
    monthly_pivot.to_csv(OUTPUT_DIR / "monthly_returns_tail36.csv", index=False)
    return summary


def reset_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def run_variant(variant: str, panel: pd.DataFrame, market: pd.DataFrame) -> dict:
    v6 = load_v6_backtest_module()
    market_regime = v6.build_market_regime(market, panel)
    regime_by_date = market_regime["regime"].to_dict() if market_regime is not None else {}
    original_score_candidates = v6.score_candidates
    audit_rows = []

    def score_candidates_with_breakout(signal_panel, diagnostics=None):
        scored = original_score_candidates(signal_panel, diagnostics=diagnostics)
        if scored.empty:
            return scored
        signal_date = pd.Timestamp(scored["trade_date"].iloc[0])
        regime = regime_by_date.get(signal_date, "unknown")
        filtered = filter_breakout_candidates(scored, variant, regime)
        audit_cols = [
            "trade_date", "ts_code", "name", "score", "short_bbi_breakout",
            "short_bbi_distance", "short_bbi_slope_5", "mid_bbi_qfq",
            "mid_bbi_slope_5", "high_pos_252", "rps_126", "market_ret_60",
            "ret_63", "pullback_63",
        ]
        present_cols = [col for col in audit_cols if col in filtered.columns]
        if present_cols:
            audit_rows.extend(filtered[present_cols].head(50).to_dict("records"))
        blocked = len(scored) - len(filtered)
        if diagnostics is not None:
            diagnostics["breakout_filter_variant"] = variant
            diagnostics["breakout_filter_candidate_blocks"] = (
                diagnostics.get("breakout_filter_candidate_blocks", 0) + int(blocked)
            )
            if blocked:
                diagnostics["breakout_filter_signal_days"] = (
                    diagnostics.get("breakout_filter_signal_days", 0) + 1
                )
        return filtered

    v6.score_candidates = score_candidates_with_breakout
    nav, trades, rebalance, scores, holdings, stats = v6.run_backtest(
        panel,
        market,
        v6.BACKTEST_START_DATE,
        None,
    )
    stats["breakout_filter_variant"] = variant

    variant_dir = OUTPUT_DIR / variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    nav.to_csv(variant_dir / "nav_series.csv", index=False)
    trades.to_csv(variant_dir / "trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    rebalance.to_csv(variant_dir / "rebalance_log.csv", index=False)
    scores.to_csv(variant_dir / "strength_scores.csv", index=False)
    pd.DataFrame(audit_rows).to_csv(variant_dir / "breakout_feature_audit.csv", index=False)
    (variant_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"nav": nav, "trades": trades, "rebalance": rebalance, "scores": scores, "stats": stats}


def append_readme(text: str) -> None:
    with README_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n" + text.rstrip() + "\n")


def main() -> None:
    print("[tmp-v4-bbi-breakout] resetting output", flush=True)
    reset_output_dir()
    v6 = load_v6_backtest_module()
    required_columns = list(dict.fromkeys(v6.PANEL_COLUMNS + ["open_qfq", "close_qfq"]))
    print("[tmp-v4-bbi-breakout] loading v6 panel", flush=True)
    panel = pd.read_parquet(V6_DIR / "output" / "panel.parquet", columns=required_columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    print(f"[tmp-v4-bbi-breakout] panel rows={len(panel):,}", flush=True)
    market = pd.read_parquet(V6_DIR / "output" / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")

    print("[tmp-v4-bbi-breakout] adding breakout features", flush=True)
    panel = add_breakout_features(panel, market)
    experiments = {}
    for variant in VARIANTS:
        print(f"[tmp-v4-bbi-breakout] running {variant}", flush=True)
        experiments[variant] = run_variant(variant, panel, market)
        stats = experiments[variant]["stats"]
        print(
            f"[tmp-v4-bbi-breakout] {variant} final_nav={stats['final_nav']:.2f} "
            f"return={stats['total_return_pct']:.4f}% max_dd={stats['max_drawdown_pct']:.4f}%",
            flush=True,
        )

    baselines = load_baseline_outputs()
    expert_notes = (
        "专家判断：上涨趋势叠加 BBI 突破是合理候选，但主要风险是假突破、追高和过拟合。"
        "本实验保留 v6 次日成交机制，明确避免使用 moneyflow/cyq 等盘后数据。"
    )
    summary = build_report(baselines, experiments, expert_notes)
    best_row = summary.sort_values(["final_nav", "calmar_ratio"], ascending=[False, False]).iloc[0]
    append_readme(
        "## Run Result\n\n"
        f"- Report: `{REPORT_PATH}`\n"
        f"- Best by final NAV: `{best_row['strategy']}` final_nav={best_row['final_nav']:.2f}, "
        f"annual={best_row['annual_return_pct']:.2f}%, max_dd={best_row['max_drawdown_pct']:.2f}%.\n"
        "- Merge recommendation is written in the HTML report.\n"
    )
    print(f"[tmp-v4-bbi-breakout] report={REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()

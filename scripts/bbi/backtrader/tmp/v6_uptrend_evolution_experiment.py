import csv
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
REPO_ROOT = BACKTRADER_DIR.parent.parent.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "v6_uptrend_evolution_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "v6_uptrend_evolution_README.md"

VARIANTS = (
    "price_trend_only",
    "price_plus_relative_strength",
    "market_regime_adaptive",
)


def load_v6_backtest_module():
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(V6_DIR))
        spec = importlib.util.spec_from_file_location("v6_backtest_for_uptrend_tmp", V6_DIR / "20_run_backtest.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_path


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


def add_uptrend_features(panel, market):
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True).copy()
    grouped = panel.groupby("ts_code", sort=False)
    if "ma20_qfq" not in panel.columns:
        panel["ma20_qfq"] = rolling_mean_by_code(panel, "close_qfq", 20)
    panel["ma60_qfq"] = rolling_mean_by_code(panel, "close_qfq", 60)
    panel["ma120_qfq"] = rolling_mean_by_code(panel, "close_qfq", 120)
    panel["ma150_qfq"] = rolling_mean_by_code(panel, "close_qfq", 150)
    panel["ma200_qfq"] = rolling_mean_by_code(panel, "close_qfq", 200)
    panel["ma60_slope_20"] = grouped["ma60_qfq"].pct_change(20, fill_method=None)
    panel["ma120_slope_20"] = grouped["ma120_qfq"].pct_change(20, fill_method=None)
    panel["ma200_slope_20"] = grouped["ma200_qfq"].pct_change(20, fill_method=None)
    high_252 = rolling_max_by_code(panel, "close_qfq", 252)
    low_252 = rolling_min_by_code(panel, "close_qfq", 252)
    panel["high_qfq_252"] = high_252
    panel["low_qfq_252"] = low_252
    panel["high_pos_252"] = panel["close_qfq"] / high_252
    panel["low_gain_252"] = panel["close_qfq"] / low_252 - 1.0
    panel["rps_126"] = panel.groupby("trade_date", sort=False)["ret_126"].rank(pct=True)

    market_for_ret = market.copy()
    if "trade_date" in market_for_ret.columns:
        market_for_ret["trade_date"] = pd.to_datetime(market_for_ret["trade_date"])
        market_for_ret = market_for_ret.set_index("trade_date")
    market_for_ret = market_for_ret.sort_index()
    market_ret_60 = market_for_ret["close"].pct_change(60)
    panel = panel.merge(
        market_ret_60.rename("market_ret_60"),
        left_on="trade_date",
        right_index=True,
        how="left",
    )
    panel["uptrend_price_ok"] = (
        (panel["close_qfq"] > panel["ma60_qfq"])
        & (panel["ma20_qfq"] > panel["ma60_qfq"])
        & (panel["ma60_slope_20"] > 0)
    )
    panel["uptrend_rs_ok"] = (
        panel["uptrend_price_ok"]
        & (panel["ret_63"] > panel["market_ret_60"])
        & (panel["rps_126"] >= 0.70)
    )
    panel["uptrend_strict_ok"] = (
        (panel["close_qfq"] > panel["ma60_qfq"])
        & (panel["ma60_qfq"] > panel["ma120_qfq"])
        & (panel["ma120_qfq"] > panel["ma200_qfq"])
        & (panel["ma120_slope_20"] > 0)
        & (panel["ma200_slope_20"] > 0)
        & (panel["ret_63"] > panel["market_ret_60"])
        & (panel["rps_126"] >= 0.80)
        & (panel["high_pos_252"] >= 0.80)
    )
    return panel


def filter_uptrend_candidates(candidates, variant, market_regime_name):
    if candidates.empty:
        return candidates.copy()
    if variant == "price_trend_only":
        mask = (
            (candidates["close_qfq"] > candidates["ma60_qfq"])
            & (candidates["ma20_qfq"] > candidates["ma60_qfq"])
            & (candidates["ma60_slope_20"] > 0)
        )
    elif variant == "price_plus_relative_strength":
        mask = (
            (candidates["close_qfq"] > candidates["ma60_qfq"])
            & (candidates["ma20_qfq"] > candidates["ma60_qfq"])
            & (candidates["ma60_slope_20"] > 0)
            & (candidates["ret_63"] > candidates["market_ret_60"])
            & (candidates["rps_126"] >= 0.70)
        )
    elif variant == "market_regime_adaptive":
        if market_regime_name == "bull":
            mask = (
                (candidates["close_qfq"] > candidates["ma60_qfq"])
                & (candidates["ma20_qfq"] > candidates["ma60_qfq"])
                & (candidates["ma60_slope_20"] > 0)
                & (candidates["ret_63"] > 0)
                & (candidates["rps_126"] >= 0.60)
                & (candidates["high_pos_252"] >= 0.70)
            )
        elif market_regime_name == "bear":
            mask = (
                (candidates["close_qfq"] > candidates["ma60_qfq"])
                & (candidates["ma60_qfq"] > candidates["ma120_qfq"])
                & (candidates["ma120_qfq"] > candidates["ma200_qfq"])
                & (candidates["ma120_slope_20"] > 0)
                & (candidates["ma200_slope_20"] > 0)
                & (candidates["ret_63"] > candidates["market_ret_60"])
                & (candidates["rps_126"] >= 0.80)
                & (candidates["high_pos_252"] >= 0.80)
            )
        else:
            mask = (
                (candidates["close_qfq"] > candidates["ma60_qfq"])
                & (candidates["ma20_qfq"] > candidates["ma60_qfq"])
                & (candidates["ma60_slope_20"] > 0)
                & (candidates["ret_63"] > candidates["market_ret_60"])
                & (candidates["rps_126"] >= 0.70)
                & (candidates["high_pos_252"] >= 0.75)
            )
    else:
        raise ValueError(f"unknown uptrend variant: {variant}")
    return candidates[mask.fillna(False)].copy()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_baseline_outputs():
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
    sortino = 0.0
    if daily_ret.std(ddof=0) > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std(ddof=0) * math.sqrt(252))
    downside = daily_ret[daily_ret < 0]
    if len(downside) and downside.std(ddof=0) > 0:
        sortino = float(daily_ret.mean() / downside.std(ddof=0) * math.sqrt(252))
    empty_rate = float((nav["holdings"] == 0).mean()) if "holdings" in nav.columns else float("nan")
    win_rate = float("nan")
    avg_trade_pnl = float("nan")
    if trades is not None and not trades.empty and "pnl" in trades.columns:
        sells = trades[trades["action"].astype(str).str.contains("sell", na=False)].copy()
        sells["pnl_num"] = pd.to_numeric(sells["pnl"], errors="coerce")
        sells = sells.dropna(subset=["pnl_num"])
        if not sells.empty:
            win_rate = float((sells["pnl_num"] > 0).mean())
            avg_trade_pnl = float(sells["pnl_num"].mean())
    return {
        "final_nav": float(nav["nav"].iloc[-1]),
        "total_return_pct": total_ret * 100.0,
        "annual_return_pct": annual_ret * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "calmar_ratio": (annual_ret * 100.0 / abs(max_dd * 100.0)) if max_dd < 0 else 0.0,
        "sharpe": sharpe,
        "sortino": sortino,
        "empty_rate_pct": empty_rate * 100.0,
        "win_rate_pct": win_rate * 100.0 if not math.isnan(win_rate) else float("nan"),
        "avg_trade_pnl": avg_trade_pnl,
    }


def annual_return_table(nav_by_label):
    rows = []
    for label, nav in nav_by_label.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        year_end_nav = frame.set_index("date")["nav"].resample("YE").last().dropna()
        if year_end_nav.empty:
            continue
        previous_nav = year_end_nav.shift(1)
        previous_nav.iloc[0] = float(frame["nav"].iloc[0])
        yearly_ret = year_end_nav / previous_nav - 1.0
        for date, value in yearly_ret.items():
            rows.append({
                "strategy": label,
                "year": int(date.year),
                "return_pct": float(value * 100.0),
                "end_nav": float(year_end_nav.loc[date]),
            })
    return pd.DataFrame(rows)


def monthly_return_table(nav_by_label):
    rows = []
    for label, nav in nav_by_label.items():
        frame = nav.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        monthly = frame.set_index("date")["nav"].resample("ME").last().dropna()
        returns = monthly.pct_change()
        if not monthly.empty:
            returns.iloc[0] = monthly.iloc[0] / frame["nav"].iloc[0] - 1.0
        for date, value in returns.dropna().items():
            rows.append({
                "strategy": label,
                "month": date.strftime("%Y-%m"),
                "return_pct": float(value * 100.0),
            })
    return pd.DataFrame(rows)


def html_table(df, float_cols=None, negative_is_bad_cols=None):
    float_cols = set(float_cols or [])
    negative_is_bad_cols = set(negative_is_bad_cols or [])
    parts = ["<table>"]
    parts.append("<thead><tr>" + "".join(f"<th>{col}</th>" for col in df.columns) + "</tr></thead>")
    parts.append("<tbody>")
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            value = row[col]
            if col in float_cols and pd.notna(value):
                text = f"{float(value):,.2f}"
                if col in negative_is_bad_cols:
                    cls = "neg" if float(value) < 0 else "pos" if float(value) > 0 else ""
                else:
                    cls = "pos" if float(value) > 0 else "neg" if float(value) < 0 else ""
            else:
                text = "" if pd.isna(value) else str(value)
                cls = ""
            cells.append(f'<td class="{cls}">{text}</td>')
        parts.append("<tr>" + "".join(cells) + "</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


def build_report(baselines, experiments, expert_notes):
    nav_by_label = {label: data["nav"] for label, data in baselines.items()}
    nav_by_label.update({label: data["nav"] for label, data in experiments.items()})
    summary_rows = []
    for label, data in baselines.items():
        metrics = calc_nav_metrics(data["nav"], data["trades"])
        metrics["strategy"] = label
        metrics["trade_records"] = int(data["summary"].get("trade_records", len(data["trades"])))
        summary_rows.append(metrics)
    for label, data in experiments.items():
        metrics = calc_nav_metrics(data["nav"], data["trades"])
        metrics["strategy"] = label
        metrics["trade_records"] = int(data["stats"].get("trade_records", len(data["trades"])))
        metrics["uptrend_blocks"] = int(data["stats"].get("uptrend_filter_candidate_blocks", 0))
        summary_rows.append(metrics)
    summary = pd.DataFrame(summary_rows)
    ordered = ["strategy", "final_nav", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
               "calmar_ratio", "sharpe", "sortino", "win_rate_pct", "empty_rate_pct",
               "trade_records", "uptrend_blocks"]
    for col in ordered:
        if col not in summary.columns:
            summary[col] = float("nan")
    summary = summary[ordered]

    annual = annual_return_table(nav_by_label)
    annual_pivot = annual.pivot(index="year", columns="strategy", values="return_pct").reset_index()
    monthly = monthly_return_table(nav_by_label)
    monthly_pivot = monthly.pivot(index="month", columns="strategy", values="return_pct").reset_index()
    monthly_pivot = monthly_pivot.tail(36)

    best = summary.sort_values(["final_nav", "calmar_ratio"], ascending=[False, False]).iloc[0]["strategy"]
    if str(best) == "v6":
        recommendation = "当前 v6 仍是最优或接近最优，不建议合并上涨趋势过滤。"
    elif str(best) in {"v4", "v5"}:
        recommendation = f"{best} 强于本轮上涨趋势变体；不建议把本轮过滤合入 v6。"
    else:
        recommendation = f"候选合并方向是 {best}，但需要先通过样本外年份和阈值邻域复核。"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v6 上涨趋势进化实验</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #1f2937; }}
h1, h2 {{ margin: 18px 0 10px; }}
.note {{ padding: 12px; background: #f3f4f6; border-left: 4px solid #2563eb; margin: 12px 0; }}
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
<h1>v6 上涨趋势进化实验</h1>
<div class="note">
<b>结论：</b>{recommendation}<br>
<b>本轮最优：</b>{best}<br>
<b>规则：</b>只在 v6 候选集之后增加上涨趋势过滤，交易仍沿用 v6 次日开盘成交逻辑。
</div>
<h2>专家评审摘要</h2>
<div class="note">{expert_notes}</div>
<h2>总览对比</h2>
{html_table(summary, float_cols=set(summary.columns) - {"strategy", "trade_records", "uptrend_blocks"}, negative_is_bad_cols={"max_drawdown_pct"})}
<h2>年度收益率对比（%）</h2>
<div class="wide">{html_table(annual_pivot, float_cols=set(annual_pivot.columns) - {"year"})}</div>
<h2>最近 36 个月收益率对比（%）</h2>
<div class="wide">{html_table(monthly_pivot, float_cols=set(monthly_pivot.columns) - {"month"})}</div>
<h2>下一步</h2>
<ol>
<li>只对最优上涨趋势变体做阈值邻域复核，避免参数碰巧命中。</li>
<li>如需要引入 <code>moneyflow</code> 或 <code>cyq_perf</code>，必须先做 T+1 shift 设计，不能直接用当日盘后数据。</li>
<li>检查收益是否集中在少数年份或少数股票，再决定是否进入 v7。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")
    summary.to_csv(OUTPUT_DIR / "comparison_summary.csv", index=False)
    annual_pivot.to_csv(OUTPUT_DIR / "annual_returns.csv", index=False)
    monthly_pivot.to_csv(OUTPUT_DIR / "monthly_returns_tail36.csv", index=False)
    return summary


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
    original_score_candidates = v6.score_candidates

    def score_candidates_with_uptrend(signal_panel, diagnostics=None):
        scored = original_score_candidates(signal_panel, diagnostics=diagnostics)
        if scored.empty:
            return scored
        signal_date = pd.Timestamp(scored["trade_date"].iloc[0])
        regime = regime_by_date.get(signal_date, "unknown")
        filtered = filter_uptrend_candidates(scored, variant, regime)
        blocked = len(scored) - len(filtered)
        if diagnostics is not None:
            diagnostics["uptrend_filter_variant"] = variant
            diagnostics["uptrend_filter_candidate_blocks"] = (
                diagnostics.get("uptrend_filter_candidate_blocks", 0) + int(blocked)
            )
            if blocked:
                diagnostics["uptrend_filter_signal_days"] = (
                    diagnostics.get("uptrend_filter_signal_days", 0) + 1
                )
        return filtered

    v6.score_candidates = score_candidates_with_uptrend
    nav, trades, rebalance, scores, holdings, stats = v6.run_backtest(
        panel,
        market,
        v6.BACKTEST_START_DATE,
        None,
    )
    stats["uptrend_filter_variant"] = variant

    variant_dir = OUTPUT_DIR / variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    nav.to_csv(variant_dir / "nav_series.csv", index=False)
    trades.to_csv(variant_dir / "trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    rebalance.to_csv(variant_dir / "rebalance_log.csv", index=False)
    scores.to_csv(variant_dir / "strength_scores.csv", index=False)
    (variant_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "nav": nav,
        "trades": trades,
        "rebalance": rebalance,
        "scores": scores,
        "stats": stats,
    }


def append_readme(text):
    with README_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n" + text.rstrip() + "\n")


def main():
    print("[v6-uptrend] resetting output", flush=True)
    reset_output_dir()
    v6 = load_v6_backtest_module()
    required_columns = list(dict.fromkeys(v6.PANEL_COLUMNS + ["close_qfq"]))
    print("[v6-uptrend] loading v6 panel", flush=True)
    panel = pd.read_parquet(V6_DIR / "output" / "panel.parquet", columns=required_columns)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    print(f"[v6-uptrend] panel rows={len(panel):,}", flush=True)
    print("[v6-uptrend] loading market index", flush=True)
    market = pd.read_parquet(V6_DIR / "output" / "market_index.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")

    print("[v6-uptrend] adding uptrend features", flush=True)
    panel = add_uptrend_features(panel, market)
    print("[v6-uptrend] uptrend features ready", flush=True)
    experiments = {}
    for variant in VARIANTS:
        print(f"[v6-uptrend] running {variant}", flush=True)
        experiments[variant] = run_variant(variant, panel, market)
        stats = experiments[variant]["stats"]
        print(
            f"[v6-uptrend] {variant} final_nav={stats['final_nav']:.2f} "
            f"return={stats['total_return_pct']:.4f}% max_dd={stats['max_drawdown_pct']:.4f}%",
            flush=True,
        )

    baselines = load_baseline_outputs()
    expert_notes = (
        "上涨趋势至少包含价格趋势、结构趋势和强度趋势；牛熊市不应完全同一阈值。"
        "必须防前视、幸存者偏差、参数过拟合和只看总收益。"
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
    print(f"[v6-uptrend] report={REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()

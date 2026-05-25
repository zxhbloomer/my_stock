import csv
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from tmp_v8_theme_overlay_lib import (
    apply_theme_overlay_to_candidates,
    build_stock_theme_map,
    build_sw_theme_features,
    filter_theme_crash_candidates,
    is_stock_theme_crash,
)


ROOT = Path(__file__).resolve().parents[4]
V8_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "v8"
TMP_DIR = ROOT / "scripts" / "bbi" / "backtrader" / "tmp"
OUTPUT_DIR = TMP_DIR / "tmp_v8_theme_overlay_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v8_theme_overlay_README.md"

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"


def load_v8_module():
    sys.path.insert(0, str(V8_DIR))
    sys.modules.pop("config", None)
    spec = importlib.util.spec_from_file_location("v8_theme_base", V8_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def query_df(conn, sql):
    return pd.read_sql(text(sql), conn)


def load_theme_inputs(start_date, end_date):
    engine = create_engine(DB_URL, poolclass=NullPool)
    with engine.connect() as conn:
        sw_daily = query_df(
            conn,
            f"""
            SELECT ts_code, trade_date, name, close
            FROM {SCHEMA}."132_sw_daily"
            WHERE trade_date >= DATE '{start_date}'
              AND trade_date <= DATE '{end_date}'
            """,
        )
        members = query_df(
            conn,
            f"""
            SELECT ts_code, l1_code, l1_name, is_new
            FROM {SCHEMA}."131_index_member_all"
            WHERE is_new = 'Y'
            """,
        )
        limit_daily = query_df(
            conn,
            f"""
            SELECT trade_date, "limit", COUNT(*) AS count
            FROM {SCHEMA}."091_limit_list_d"
            WHERE trade_date >= DATE '{start_date}'
              AND trade_date <= DATE '{end_date}'
            GROUP BY trade_date, "limit"
            """,
        )
    sw_daily["trade_date"] = pd.to_datetime(sw_daily["trade_date"])
    limit_daily["trade_date"] = pd.to_datetime(limit_daily["trade_date"])
    stock_theme = build_stock_theme_map(members)
    theme_features = build_sw_theme_features(sw_daily)
    return stock_theme, theme_features, limit_daily


def run_one_variant(v8, panel, market, stock_theme, theme_features, variant):
    original_score_candidates = v8.score_candidates
    original_can_add_position = v8.can_add_position
    counters = {
        "theme_candidate_blocks": 0,
        "theme_add_blocks": 0,
    }

    def signal_date_from_candidates(candidates):
        if candidates.empty or "trade_date" not in candidates.columns:
            return None
        return pd.Timestamp(candidates["trade_date"].iloc[0])

    def score_with_boost(signal_panel, diagnostics=None):
        candidates = original_score_candidates(signal_panel, diagnostics=diagnostics)
        signal_date = signal_date_from_candidates(candidates)
        if signal_date is None:
            return candidates
        return apply_theme_overlay_to_candidates(
            candidates,
            signal_date,
            stock_theme,
            theme_features,
            theme_weight=0.12,
            crash_penalty=0.35,
        )

    def score_with_crash_filter(signal_panel, diagnostics=None):
        candidates = original_score_candidates(signal_panel, diagnostics=diagnostics)
        signal_date = signal_date_from_candidates(candidates)
        if signal_date is None:
            return candidates
        filtered = filter_theme_crash_candidates(candidates, signal_date, stock_theme, theme_features)
        counters["theme_candidate_blocks"] += int(len(candidates) - len(filtered))
        return filtered

    def can_add_with_theme_guard(code, pos, signal_panel):
        if not original_can_add_position(code, pos, signal_panel):
            return False
        if code not in signal_panel.index:
            return False
        signal_date = pd.Timestamp(signal_panel.loc[code].get("trade_date"))
        if is_stock_theme_crash(code, signal_date, stock_theme, theme_features):
            counters["theme_add_blocks"] += 1
            return False
        return True

    try:
        if variant == "theme_score_boost":
            v8.score_candidates = score_with_boost
        elif variant == "theme_ebb_filter_candidates":
            v8.score_candidates = score_with_crash_filter
        elif variant == "theme_ebb_no_add":
            v8.can_add_position = can_add_with_theme_guard
        elif variant == "theme_ebb_filter_and_no_add":
            v8.score_candidates = score_with_crash_filter
            v8.can_add_position = can_add_with_theme_guard

        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v8.run_backtest(
            panel.copy(),
            market.copy() if market is not None else None,
            v8.BACKTEST_START_DATE,
            None,
        )
        stats.update(counters)
        return nav_df, trades_df, rebalance_df, scores_df, holdings, stats
    finally:
        v8.score_candidates = original_score_candidates
        v8.can_add_position = original_can_add_position


def write_variant_output(name, nav_df, trades_df, rebalance_df, scores_df, holdings, stats):
    out_dir = OUTPUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    nav_df.to_csv(out_dir / "nav_series.csv", index=False)
    trades_df.to_csv(out_dir / "trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    rebalance_df.to_csv(out_dir / "rebalance_log.csv", index=False)
    scores_df.to_csv(out_dir / "strength_scores.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def calc_period_return(nav, freq):
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["period"] = data["date"].dt.to_period(freq).astype(str)
    data = data.sort_values("date")
    period_end_nav = data.groupby("period")["nav"].last()
    prior_end_nav = period_end_nav.shift(1)
    first_start_nav = float(data["nav"].iloc[0])
    rows = []
    for period, group in data.groupby("period"):
        group = group.sort_values("date")
        start = float(prior_end_nav.loc[period]) if pd.notna(prior_end_nav.loc[period]) else first_start_nav
        end = float(period_end_nav.loc[period])
        dd = (group["nav"] / group["nav"].cummax() - 1.0).min() * 100.0
        rows.append({
            "period": period,
            "return_pct": (end / start - 1.0) * 100.0 if start else 0.0,
            "max_dd_pct": dd,
            "start_nav": start,
            "end_nav": end,
        })
    return pd.DataFrame(rows)


def load_version_nav(version):
    path = ROOT / "scripts" / "bbi" / "backtrader" / version / "output" / "nav_series.csv"
    if not path.exists():
        return None
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    return nav


def load_version_summary(version):
    path = ROOT / "scripts" / "bbi" / "backtrader" / version / "output" / "summary.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def make_compare_report(variant_results, limit_daily):
    summary_rows = []
    nav_by_name = {}
    for version in ["v4", "v5", "v6", "v7", "v8"]:
        summary = load_version_summary(version)
        nav = load_version_nav(version)
        if summary and nav is not None:
            nav_by_name[version] = nav
            summary_rows.append({
                "name": version,
                "total_return_pct": summary.get("total_return_pct"),
                "annual_return_pct": summary.get("annual_return_pct"),
                "max_drawdown_pct": summary.get("max_drawdown_pct"),
                "final_nav": summary.get("final_nav"),
                "trade_records": summary.get("trade_records"),
                "theme_candidate_blocks": "",
                "theme_add_blocks": "",
            })
    for name, payload in variant_results.items():
        nav_by_name[name] = payload["nav"]
        stats = payload["stats"]
        summary_rows.append({
            "name": name,
            "total_return_pct": stats.get("total_return_pct"),
            "annual_return_pct": stats.get("annual_return_pct"),
            "max_drawdown_pct": stats.get("max_drawdown_pct"),
            "final_nav": stats.get("final_nav"),
            "trade_records": stats.get("trade_records"),
            "theme_candidate_blocks": stats.get("theme_candidate_blocks", 0),
            "theme_add_blocks": stats.get("theme_add_blocks", 0),
        })

    summary_df = pd.DataFrame(summary_rows)
    for col in ["total_return_pct", "annual_return_pct", "max_drawdown_pct", "final_nav"]:
        summary_df[col] = pd.to_numeric(summary_df[col], errors="coerce").round(2)

    annual_parts = []
    monthly_parts = []
    for name, nav in nav_by_name.items():
        annual = calc_period_return(nav, "Y")
        annual["name"] = name
        annual_parts.append(annual)
        monthly = calc_period_return(nav, "M")
        monthly["name"] = name
        monthly_parts.append(monthly)
    annual_df = pd.concat(annual_parts, ignore_index=True)
    monthly_df = pd.concat(monthly_parts, ignore_index=True)
    annual_pivot = annual_df.pivot(index="period", columns="name", values="return_pct").round(2).reset_index()
    monthly_2025 = monthly_df[monthly_df["period"].str.startswith("2025")]
    monthly_pivot_2025 = monthly_2025.pivot(index="period", columns="name", values="return_pct").round(2).reset_index()

    if not limit_daily.empty:
        limit_pivot = limit_daily.pivot_table(index="trade_date", columns="limit", values="count", aggfunc="sum").fillna(0)
        for col in ["D", "U", "Z"]:
            if col not in limit_pivot.columns:
                limit_pivot[col] = 0
        risk_days = limit_pivot.sort_values("D", ascending=False).head(12).reset_index()
        risk_days["trade_date"] = risk_days["trade_date"].dt.strftime("%Y-%m-%d")
    else:
        risk_days = pd.DataFrame()

    best_variant = summary_df[summary_df["name"].astype(str).str.startswith("theme_")].sort_values(
        ["total_return_pct", "max_drawdown_pct"], ascending=[False, False]
    ).head(1)
    if best_variant.empty:
        recommendation = "未产生主题实验结果，不建议合并。"
    else:
        row = best_variant.iloc[0]
        baseline_row = summary_df[summary_df["name"].eq("baseline_v8_replay")]
        baseline_ret = float(baseline_row.iloc[0]["total_return_pct"]) if not baseline_row.empty else float("nan")
        if pd.notna(baseline_ret) and float(row["total_return_pct"]) > baseline_ret:
            recommendation = (
                f"建议只考虑把 {row['name']} 继续推进到 v8 候选合入；"
                "但必须先做分段稳健性和静态行业映射替换验证。"
            )
        else:
            recommendation = "本轮主题 overlay 没有跑赢当前 v8，不建议合并；建议继续研究退潮风控或改用历史行业成分。"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v8 Theme Overlay Experiment</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #222; }}
h1, h2 {{ margin: 18px 0 10px; }}
.note {{ padding: 12px 14px; background: #f5f7fa; border-left: 4px solid #4466aa; margin: 12px 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0 24px; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #f0f0f0; }}
.bad {{ color: #a33; }}
.good {{ color: #176b3a; }}
</style>
</head>
<body>
<h1>v8 Theme Overlay Experiment</h1>
<div class="note">
目标是提升收益。第一版在 tmp 中验证，不修改正式 v8。主题层只用结构化数据，核心交易数据来自申万行业行情和静态行业映射。
</div>
<h2>结论建议</h2>
<p>{recommendation}</p>
<h2>总体对比</h2>
{summary_df.to_html(index=False, escape=False)}
<h2>年度收益对比 (%)</h2>
{annual_pivot.to_html(index=False, escape=False)}
<h2>2025 月度收益对比 (%)</h2>
{monthly_pivot_2025.to_html(index=False, escape=False)}
<h2>2025 风险日：跌停/涨停/炸板数量</h2>
{risk_days.to_html(index=False, escape=False) if not risk_days.empty else "<p>无涨跌停诊断数据。</p>"}
<h2>口径说明</h2>
<p>v8 在交易日使用前一交易日 signal_date 的信号，实验 overlay 保持同一口径。申万行业映射使用当前最新静态映射，这是本轮最大的研究限制，不能视为严格 point-in-time 成分。</p>
</body>
</html>
"""
    REPORT_PATH.write_text(html, encoding="utf-8")


def append_progress(text):
    with README_PATH.open("a", encoding="utf-8") as f:
        f.write(f"\n- {text}\n")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v8 = load_v8_module()
    panel = pd.read_parquet(v8.PANEL_PATH, columns=v8.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = v8.load_market_index()

    stock_theme, theme_features, limit_daily = load_theme_inputs("2017-01-01", "2026-12-31")
    theme_features.to_csv(OUTPUT_DIR / "sw_theme_features.csv", index=False)
    stock_theme.to_csv(OUTPUT_DIR / "stock_theme_map.csv", index=False)

    variants = [
        "baseline_v8_replay",
        "theme_score_boost",
        "theme_ebb_filter_candidates",
        "theme_ebb_no_add",
        "theme_ebb_filter_and_no_add",
    ]
    results = {}
    for variant in variants:
        print(f"[theme-overlay] running {variant}", flush=True)
        nav_df, trades_df, rebalance_df, scores_df, holdings, stats = run_one_variant(
            v8,
            panel,
            market,
            stock_theme,
            theme_features,
            variant if variant != "baseline_v8_replay" else "baseline",
        )
        write_variant_output(variant, nav_df, trades_df, rebalance_df, scores_df, holdings, stats)
        results[variant] = {"nav": nav_df, "stats": stats}
        print(
            "[theme-overlay] {name}: total={ret:.2f}% dd={dd:.2f}% trades={trades}".format(
                name=variant,
                ret=float(stats.get("total_return_pct", 0.0)),
                dd=float(stats.get("max_drawdown_pct", 0.0)),
                trades=int(stats.get("trade_records", 0)),
            ),
            flush=True,
        )

    make_compare_report(results, limit_daily)
    append_progress("Experiment run completed and HTML report generated.")
    print(f"[theme-overlay] report: {REPORT_PATH}")


if __name__ == "__main__":
    main()

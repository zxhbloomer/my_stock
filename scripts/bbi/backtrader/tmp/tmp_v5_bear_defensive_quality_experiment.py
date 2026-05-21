from __future__ import annotations

import csv
import html
import importlib.util
import json
import math
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "tmp_v5_bear_defensive_quality_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
README_PATH = TMP_DIR / "tmp_v5_bear_defensive_quality_README.md"

CASES = [
    {"name": "baseline_v6", "type": "baseline"},
    {"name": "defensive_filter", "type": "defensive_filter"},
    {"name": "defensive_score", "type": "defensive_score"},
    {"name": "defensive_filter_score", "type": "defensive_filter_score"},
]

FINA_COLUMNS = [
    "roe_dt",
    "grossprofit_margin",
    "ocf_to_or",
    "debt_to_assets",
]

DAILY_BASIC_COLUMNS = [
    "dv_ttm",
    "pb",
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
    return load_module_from_path("v6_backtest_for_bear_defensive_quality", V6_DIR / "20_run_backtest.py")


def load_v6_config_module():
    return load_module_from_path("v6_config_for_bear_defensive_quality", V6_DIR / "config.py")


def reset_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def append_progress(message: str):
    with README_PATH.open("a", encoding="utf-8") as f:
        f.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def zscore(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    std = series.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_baseline_outputs():
    outputs = {}
    for label, directory in (("v4", V4_DIR), ("v5", V5_DIR), ("v6", V6_DIR)):
        output = directory / "output"
        outputs[label] = {
            "summary": load_json(output / "summary.json"),
            "nav": pd.read_csv(output / "nav_series.csv"),
            "trades": pd.read_csv(output / "trade_records.csv"),
        }
    return outputs


def merge_financial_features(panel: pd.DataFrame, fina: pd.DataFrame) -> pd.DataFrame:
    left = panel.copy()
    left["trade_date"] = pd.to_datetime(left["trade_date"])
    left = left.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    if fina.empty:
        for col in FINA_COLUMNS:
            left[col] = np.nan
        return left
    right = fina.copy()
    right["ann_date"] = pd.to_datetime(right["ann_date"])
    right = right.sort_values(["ts_code", "ann_date"]).reset_index(drop=True)
    for col in FINA_COLUMNS:
        if col not in right.columns:
            right[col] = np.nan
    merged_frames = []
    for ts_code, group in left.groupby("ts_code", sort=False):
        src = right[right["ts_code"] == ts_code]
        if src.empty:
            out = group.copy()
            for col in FINA_COLUMNS:
                out[col] = np.nan
            merged_frames.append(out)
            continue
        out = pd.merge_asof(
            group.sort_values("trade_date"),
            src[["ann_date"] + FINA_COLUMNS].sort_values("ann_date"),
            left_on="trade_date",
            right_on="ann_date",
            direction="backward",
        )
        merged_frames.append(out)
    return pd.concat(merged_frames, ignore_index=True)


def add_bear_defensive_features(panel: pd.DataFrame, market: pd.DataFrame, daily_basic: pd.DataFrame, fina: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])

    daily = daily_basic.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    out = out.merge(
        daily[["ts_code", "trade_date"] + DAILY_BASIC_COLUMNS],
        on=["ts_code", "trade_date"],
        how="left",
    )
    out = merge_financial_features(out, fina)

    market_for_ret = market.copy()
    if "trade_date" in market_for_ret.columns:
        market_for_ret["trade_date"] = pd.to_datetime(market_for_ret["trade_date"])
        market_for_ret = market_for_ret.set_index("trade_date")
    market_for_ret = market_for_ret.sort_index()
    market_ret_60 = pd.to_numeric(market_for_ret["close"], errors="coerce").pct_change(60)
    out = out.merge(market_ret_60.rename("market_ret_60"), left_on="trade_date", right_index=True, how="left")
    out["relative_strength_63"] = pd.to_numeric(out["ret_63"], errors="coerce") - pd.to_numeric(out["market_ret_60"], errors="coerce")
    return out


def enrich_candidates_for_defensive_features(candidates: pd.DataFrame, daily_basic_lookup: pd.DataFrame, fina_by_code: dict[str, pd.DataFrame], market_ret_60: pd.Series) -> pd.DataFrame:
    out = candidates.copy().reset_index(drop=True)
    if out.empty:
        return out
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    daily = daily_basic_lookup.reindex(pd.MultiIndex.from_frame(out[["ts_code", "trade_date"]]))
    daily = daily.reset_index(drop=True)
    for col in DAILY_BASIC_COLUMNS:
        out[col] = daily[col].values if col in daily.columns else np.nan

    pieces = []
    for ts_code, group in out.groupby("ts_code", sort=False):
        fina = fina_by_code.get(ts_code)
        if fina is None or fina.empty:
            tmp = group.copy()
            for col in FINA_COLUMNS:
                tmp[col] = np.nan
            pieces.append(tmp)
            continue
        tmp = pd.merge_asof(
            group.sort_values("trade_date"),
            fina[["ann_date"] + FINA_COLUMNS].sort_values("ann_date"),
            left_on="trade_date",
            right_on="ann_date",
            direction="backward",
        )
        pieces.append(tmp)
    out = pd.concat(pieces, ignore_index=True)
    out["market_ret_60"] = out["trade_date"].map(market_ret_60)
    out["relative_strength_63"] = pd.to_numeric(out["ret_63"], errors="coerce") - pd.to_numeric(out["market_ret_60"], errors="coerce")
    return out


def compute_bear_defensive_score(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.copy()
    score_inputs = {
        "roe_dt": 0.25,
        "grossprofit_margin": 0.20,
        "ocf_to_or": 0.15,
        "debt_to_assets": -0.20,
        "volatility_63": -0.15,
        "dv_ttm": 0.10,
        "pb": -0.05,
        "relative_strength_63": 0.10,
    }
    out["bear_defensive_score"] = 0.0
    for col, weight in score_inputs.items():
        if col in out.columns:
            values = pd.to_numeric(out[col], errors="coerce")
        else:
            values = pd.Series(np.nan, index=out.index)
        if values.notna().any():
            values = values.fillna(values.median())
        else:
            values = values.fillna(0.0)
        out["bear_defensive_score"] += float(weight) * zscore(values)
    return out


def apply_bear_defensive_case(candidates: pd.DataFrame, case: dict):
    out = candidates.copy()
    diagnostics = {
        "input_candidates": int(len(out)),
        "blocked_candidates": 0,
        "missing_feature_rows": 0,
    }
    if out.empty or case["type"] == "baseline":
        return out, diagnostics

    out = compute_bear_defensive_score(out)
    if "relative_strength_63" not in out.columns:
        out["relative_strength_63"] = pd.to_numeric(out.get("ret_63"), errors="coerce") - pd.to_numeric(out.get("market_ret_60"), errors="coerce")
    probe_mask = out["bear_probe_stock_ok"].fillna(False).astype(bool) if "bear_probe_stock_ok" in out.columns else pd.Series(False, index=out.index)

    if case["type"] in {"defensive_filter", "defensive_filter_score"}:
        probe = out[probe_mask].copy()
        if not probe.empty:
            vol = pd.to_numeric(probe["volatility_63"], errors="coerce")
            roe = pd.to_numeric(probe["roe_dt"], errors="coerce")
            debt = pd.to_numeric(probe["debt_to_assets"], errors="coerce")
            rs = pd.to_numeric(probe["relative_strength_63"], errors="coerce")
            mask = (
                (rs > 0)
                & (vol <= vol.median())
                & (roe >= roe.median())
                & (debt <= debt.median())
            )
            diagnostics["missing_feature_rows"] = int((vol.isna() | roe.isna() | debt.isna() | rs.isna()).sum())
            keep_probe_codes = set(probe.loc[mask.fillna(False), "ts_code"])
            keep_mask = (~probe_mask) | out["ts_code"].isin(keep_probe_codes)
            diagnostics["blocked_candidates"] = int((~keep_mask).sum())
            out = out[keep_mask].copy()
    if case["type"] in {"defensive_score", "defensive_filter_score"}:
        if "score" in out.columns:
            out["score"] = out["score"] + out["bear_defensive_score"].where(out["bear_probe_stock_ok"].fillna(False), 0.0)
        sort_cols = [col for col in ["score", "bear_defensive_score", "above_ratio_63", "ret_63"] if col in out.columns]
        out = out.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return out, diagnostics


@contextmanager
def patched_score_candidates(v6, case_name: str, diagnostics: dict, daily_basic_lookup: pd.DataFrame, fina_by_code: dict[str, pd.DataFrame], market_ret_60: pd.Series):
    original_score_candidates = v6.score_candidates

    def wrapped_score_candidates(signal_panel, diagnostics=None):
        candidates = original_score_candidates(signal_panel, diagnostics=diagnostics)
        candidates = enrich_candidates_for_defensive_features(candidates, daily_basic_lookup, fina_by_code, market_ret_60)
        case = next(c for c in CASES if c["name"] == case_name)
        filtered, case_diag = apply_bear_defensive_case(candidates, case)
        for key, value in case_diag.items():
            if diagnostics is not None:
                diagnostics_key = f"case_{key}"
                diagnostics[diagnostics_key] = diagnostics.get(diagnostics_key, 0) + int(value)
        return filtered

    try:
        v6.score_candidates = wrapped_score_candidates
        yield
    finally:
        v6.score_candidates = original_score_candidates


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
    if daily_ret.std(ddof=0) > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std(ddof=0) * math.sqrt(252))
    return {
        "final_nav": float(frame["nav"].iloc[-1]),
        "total_return_pct": total_ret * 100.0,
        "annual_return_pct": annual_ret * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "calmar_ratio": (annual_ret / abs(max_dd)) if max_dd < 0 else 0.0,
        "trade_records": int(len(trades)) if trades is not None else 0,
        "sharpe": sharpe,
    }


def calc_period_return(nav: pd.DataFrame, start: str, end: str) -> float:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[(frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))].copy()
    if frame.empty:
        return float("nan")
    return (frame["nav"].iloc[-1] / frame["nav"].iloc[0] - 1.0) * 100.0


def make_monthly_returns(nav: pd.DataFrame) -> pd.DataFrame:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").set_index("date")
    monthly = frame["nav"].resample("ME").last().pct_change() * 100.0
    return monthly.reset_index(name="monthly_return_pct")


def load_support_data(v6, v6_config):
    panel = pd.read_parquet(v6.PANEL_PATH)
    market = pd.read_parquet(v6.MARKET_INDEX_PATH)
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date")
    engine = create_engine(v6_config.DB_URL)
    start_date = str(pd.to_datetime(panel["trade_date"]).min().date())
    end_date = str(pd.to_datetime(panel["trade_date"]).max().date())
    with engine.connect() as conn:
        daily_basic = pd.read_sql_query(
            text(f"""
                select ts_code, trade_date, dv_ttm, pb
                from {v6_config.SCHEMA}."027_daily_basic"
                where trade_date >= :start_date and trade_date <= :end_date
            """),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )
        fina = pd.read_sql_query(
            text(f"""
                select ts_code, ann_date, roe_dt, grossprofit_margin, ocf_to_or, debt_to_assets
                from {v6_config.SCHEMA}."042_fina_indicator"
                where ann_date <= :end_date
            """),
            conn,
            params={"end_date": end_date},
        )
    return panel, market, daily_basic, fina


def render_report(results: pd.DataFrame, comparisons: dict, period_tables: dict):
    rows = []
    for _, row in results.iterrows():
        recommend = "建议保留观察" if row["beats_v6"] else "不建议合并"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['case']))}</td>"
            f"<td>{row['final_nav']:.2f}</td>"
            f"<td>{row['total_return_pct']:.2f}%</td>"
            f"<td>{row['annual_return_pct']:.2f}%</td>"
            f"<td>{row['max_drawdown_pct']:.2f}%</td>"
            f"<td>{row['calmar_ratio']:.3f}</td>"
            f"<td>{int(row['trade_records'])}</td>"
            f"<td>{recommend}</td>"
            "</tr>"
        )

    compare_rows = []
    for name, metrics in comparisons.items():
        compare_rows.append(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{metrics['final_nav']:.2f}</td>"
            f"<td>{metrics['total_return_pct']:.2f}%</td>"
            f"<td>{metrics['annual_return_pct']:.2f}%</td>"
            f"<td>{metrics['max_drawdown_pct']:.2f}%</td>"
            f"<td>{metrics['calmar_ratio']:.3f}</td>"
            "</tr>"
        )

    period_sections = []
    for title, df in period_tables.items():
        rows_html = []
        for _, row in df.iterrows():
            cells = "".join(f"<td>{html.escape(str(v))}</td>" for v in row.tolist())
            rows_html.append(f"<tr>{cells}</tr>")
        headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
        period_sections.append(
            f"<h3>{html.escape(title)}</h3>"
            f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
        )

    report = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>tmp_v5 熊市防御质量实验</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 16px; background: #f6f8fb; color: #222; }}
    h1, h2, h3 {{ margin: 8px 0; }}
    .note {{ background: #fff; border: 1px solid #d8dee9; padding: 10px 12px; margin: 12px 0; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; margin: 12px 0; }}
    th, td {{ border: 1px solid #d8dee9; padding: 6px 8px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
  </style>
</head>
<body>
  <h1>tmp_v5 熊市防御质量实验</h1>
  <div class="note">
    本实验只在当前 v6 的熊市试探买入分支上增加防御候选筛选/评分，不修改普通 v6 买入路径。
  </div>
  <h2>新变体结果</h2>
  <table>
    <thead>
      <tr><th>case</th><th>final_nav</th><th>total</th><th>annual</th><th>max_dd</th><th>Calmar</th><th>trades</th><th>建议</th></tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>正式版本对比</h2>
  <table>
    <thead>
      <tr><th>strategy</th><th>final_nav</th><th>total</th><th>annual</th><th>max_dd</th><th>Calmar</th></tr>
    </thead>
    <tbody>{''.join(compare_rows)}</tbody>
  </table>
  {''.join(period_sections)}
</body>
</html>"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def open_report():
    import subprocess

    subprocess.run(
        [
            "C:\\Program Files\\PowerShell\\7\\pwsh.exe",
            "-Command",
            f"Start-Process -FilePath (Resolve-Path '{REPORT_PATH}') -WindowStyle Hidden",
        ],
        check=True,
    )


def main():
    append_progress("开始实现并运行实验。")
    reset_output_dir()
    v6 = load_v6_backtest_module()
    v6_config = load_v6_config_module()
    panel, market, daily_basic, fina = load_support_data(v6, v6_config)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    daily_basic["trade_date"] = pd.to_datetime(daily_basic["trade_date"])
    daily_basic_lookup = daily_basic.set_index(["ts_code", "trade_date"]).sort_index()
    fina["ann_date"] = pd.to_datetime(fina["ann_date"])
    fina_by_code = {code: grp.sort_values("ann_date").reset_index(drop=True) for code, grp in fina.groupby("ts_code", sort=False)}
    market_ret_60 = pd.to_numeric(market["close"], errors="coerce").pct_change(60)
    append_progress("已完成 daily_basic/fina_indicator 数据加载与 PIT 对齐。")

    baseline_outputs = load_baseline_outputs()
    results = []
    nav_map = {}
    trade_map = {}
    for case in CASES:
        append_progress(f"开始运行 case={case['name']}")
        with patched_score_candidates(v6, case["name"], {}, daily_basic_lookup, fina_by_code, market_ret_60):
            nav_df, trades_df, rebalance_df, scores_df, holdings, stats = v6.run_backtest(
                panel.copy(),
                market.copy(),
                v6_config.BACKTEST_START_DATE,
                v6_config.END_DATE,
            )
        metrics = calc_nav_metrics(nav_df, trades_df)
        metrics["case"] = case["name"]
        metrics["beats_v6"] = (
            metrics["total_return_pct"] > baseline_outputs["v6"]["summary"]["total_return_pct"]
            and metrics["max_drawdown_pct"] >= baseline_outputs["v6"]["summary"]["max_drawdown_pct"] - 3.0
        )
        results.append(metrics)
        nav_map[case["name"]] = nav_df
        trade_map[case["name"]] = trades_df
        nav_df.to_csv(OUTPUT_DIR / f"{case['name']}_nav.csv", index=False)
        trades_df.to_csv(OUTPUT_DIR / f"{case['name']}_trades.csv", index=False, quoting=csv.QUOTE_MINIMAL)
        append_progress(
            f"完成 case={case['name']} total={metrics['total_return_pct']:.2f}% annual={metrics['annual_return_pct']:.2f}% max_dd={metrics['max_drawdown_pct']:.2f}%"
        )

    results_df = pd.DataFrame(results).sort_values("total_return_pct", ascending=False).reset_index(drop=True)
    results_df.to_csv(RESULTS_PATH, index=False)

    comparisons = {}
    for name, payload in baseline_outputs.items():
        comparisons[name] = calc_nav_metrics(payload["nav"], payload["trades"])

    yearly_rows = []
    for name, nav in {**{k: v["nav"] for k, v in baseline_outputs.items()}, **nav_map}.items():
        for year in [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]:
            start = f"{year}-01-01"
            end = f"{year}-12-31"
            yearly_rows.append({"strategy": name, "year": year, "return_pct": round(calc_period_return(nav, start, end), 2)})
    yearly_df = pd.DataFrame(yearly_rows).pivot(index="year", columns="strategy", values="return_pct").reset_index()

    monthly_rows = []
    focus_navs = {"v4": baseline_outputs["v4"]["nav"], "v5": baseline_outputs["v5"]["nav"], "v6": baseline_outputs["v6"]["nav"]}
    best_case = results_df.iloc[0]["case"]
    focus_navs[best_case] = nav_map[best_case]
    for name, nav in focus_navs.items():
        monthly = make_monthly_returns(nav)
        monthly["strategy"] = name
        monthly_rows.append(monthly)
    monthly_df = pd.concat(monthly_rows, ignore_index=True)
    monthly_df["month"] = monthly_df["date"].dt.strftime("%Y-%m")
    monthly_pivot = monthly_df.pivot(index="month", columns="strategy", values="monthly_return_pct").reset_index()
    monthly_pivot = monthly_pivot[monthly_pivot["month"].str.startswith("2018-") | monthly_pivot["month"].str.startswith("2022-")]

    render_report(
        results_df,
        comparisons,
        {
            "年度收益对比": yearly_df.fillna(""),
            "重点月份对比（2018 / 2022）": monthly_pivot.fillna(""),
        },
    )
    append_progress(f"报告已生成：{REPORT_PATH}")
    open_report()
    append_progress("报告已自动打开。")


if __name__ == "__main__":
    main()

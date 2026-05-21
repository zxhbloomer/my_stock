from __future__ import annotations

import html
import subprocess
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
OUTPUT_DIR = TMP_DIR / "tmp_v6_bear_overlay_experiment_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v6_bear_overlay_experiment_README.md"
SOURCE_REGIME_PATH = TMP_DIR / "tmp_v6_2018_bear_hysteresis_experiment_output" / "hysteresis_fast_reentry_regime.csv"
INIT_NAV = 500_000.0
PERIODS = {
    "2018": ("2018-01-01", "2018-12-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2023": ("2023-01-01", "2023-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
}


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def load_nav(strategy: str) -> pd.DataFrame:
    path = BACKTRADER_DIR / strategy / "output" / "nav_series.csv"
    data = pd.read_csv(path)
    data["date"] = pd.to_datetime(data["date"])
    data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
    return data.sort_values("date").reset_index(drop=True)


def load_regime() -> pd.DataFrame:
    regime = pd.read_csv(SOURCE_REGIME_PATH)
    regime["trade_date"] = pd.to_datetime(regime["trade_date"])
    regime["target_exposure"] = pd.to_numeric(regime["target_exposure"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    return regime.sort_values("trade_date").reset_index(drop=True)


def apply_exposure_overlay(v6_nav: pd.DataFrame, exposure: pd.DataFrame, initial_nav: float = INIT_NAV) -> pd.DataFrame:
    nav = v6_nav.copy()
    nav["date"] = pd.to_datetime(nav["date"])
    nav["nav"] = pd.to_numeric(nav["nav"], errors="coerce")
    nav = nav.sort_values("date").reset_index(drop=True)
    nav["v6_daily_return"] = nav["nav"].pct_change(fill_method=None).fillna(0.0)

    regime = exposure[["trade_date", "target_exposure"]].copy()
    regime["trade_date"] = pd.to_datetime(regime["trade_date"])
    regime["target_exposure"] = pd.to_numeric(regime["target_exposure"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    merged = nav.merge(regime, left_on="date", right_on="trade_date", how="left")
    merged["target_exposure"] = merged["target_exposure"].ffill().fillna(0.0)
    merged["effective_exposure"] = merged["target_exposure"].shift(1).fillna(0.0)
    merged["overlay_daily_return"] = merged["effective_exposure"] * merged["v6_daily_return"]

    overlay_nav = []
    current = float(initial_nav)
    for i, row in merged.iterrows():
        if i == 0:
            current = float(initial_nav)
        else:
            current *= 1.0 + float(row["overlay_daily_return"])
        overlay_nav.append(current)
    merged["overlay_nav"] = overlay_nav
    merged["stock_value"] = merged["overlay_nav"] * merged["effective_exposure"]
    merged["cash_value"] = merged["overlay_nav"] - merged["stock_value"]
    return merged.drop(columns=["trade_date"])


def max_drawdown(nav: pd.Series) -> float:
    values = pd.to_numeric(nav, errors="coerce").dropna()
    if values.empty:
        return 0.0
    return float((values / values.cummax() - 1.0).min())


def annual_return(start_nav: float, end_nav: float, days: int) -> float:
    if start_nav <= 0 or end_nav <= 0 or days <= 0:
        return 0.0
    return float((end_nav / start_nav) ** (365.25 / days) - 1.0)


def summarize_nav(strategy: str, nav_df: pd.DataFrame, nav_col: str, start_date: str, end_date: str) -> dict:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    data = nav_df[(nav_df["date"] >= start) & (nav_df["date"] <= end)].copy()
    if data.empty:
        return {}
    start_nav = float(data.iloc[0][nav_col])
    end_nav = float(data.iloc[-1][nav_col])
    days = max((data.iloc[-1]["date"] - data.iloc[0]["date"]).days, 1)
    row = {
        "period": str(start.year),
        "strategy": strategy,
        "start_date": data.iloc[0]["date"].strftime("%Y-%m-%d"),
        "end_date": data.iloc[-1]["date"].strftime("%Y-%m-%d"),
        "final_nav": round(end_nav, 2),
        "total_return_pct": round((end_nav / start_nav - 1.0) * 100.0, 4),
        "annual_return_pct": round(annual_return(start_nav, end_nav, days) * 100.0, 4),
        "max_drawdown_pct": round(max_drawdown(data[nav_col]) * 100.0, 4),
    }
    if "effective_exposure" in data.columns:
        row["avg_effective_exposure_pct"] = round(float(data["effective_exposure"].mean() * 100.0), 2)
        row["risk_off_days"] = int((data["effective_exposure"] <= 0.0).sum())
        row["low_exposure_days"] = int((data["effective_exposure"] <= 0.2).sum())
    return row


def build_multi_period_compare(overlay: pd.DataFrame) -> pd.DataFrame:
    baselines = {name: load_nav(name) for name in ["v4", "v5", "v6"]}
    rows = []
    for label, (start, end) in PERIODS.items():
        for name, nav in baselines.items():
            row = summarize_nav(name, nav, "nav", start, end)
            if row:
                row["period"] = label
                rows.append(row)
        row = summarize_nav("v6_bear_overlay", overlay, "overlay_nav", start, end)
        if row:
            row["period"] = label
            rows.append(row)
    return pd.DataFrame(rows)


def build_monthly_returns(overlay: pd.DataFrame) -> pd.DataFrame:
    v6 = load_nav("v6")[["date", "nav"]].rename(columns={"nav": "v6_nav"})
    data = overlay[["date", "overlay_nav", "effective_exposure"]].merge(v6, on="date", how="left")
    data["month"] = data["date"].dt.to_period("M").astype(str)
    month_end = data.groupby("month", sort=True).tail(1).copy().reset_index(drop=True)
    month_end["prev_v6_nav"] = month_end["v6_nav"].shift(1)
    month_end["prev_overlay_nav"] = month_end["overlay_nav"].shift(1)
    rows = []
    for _, last in month_end.iterrows():
        month = str(last["month"])
        if not month.startswith(("2018", "2022", "2023", "2024")):
            continue
        group = data[data["month"] == month]
        prev_v6_nav = float(last["prev_v6_nav"]) if pd.notna(last["prev_v6_nav"]) else float(group.iloc[0]["v6_nav"])
        prev_overlay_nav = float(last["prev_overlay_nav"]) if pd.notna(last["prev_overlay_nav"]) else float(group.iloc[0]["overlay_nav"])
        v6_month_return = float(last["v6_nav"]) / prev_v6_nav - 1.0
        overlay_month_return = float(last["overlay_nav"]) / prev_overlay_nav - 1.0
        rows.append(
            {
                "月份": month,
                "v6月收益率": round(v6_month_return * 100.0, 2),
                "overlay月收益率": round(overlay_month_return * 100.0, 2),
                "overlay较v6改善": round((overlay_month_return - v6_month_return) * 100.0, 2),
                "月均有效仓位": round(float(group["effective_exposure"].mean() * 100.0), 2),
            }
        )
    return pd.DataFrame(rows)


def build_monthly_asset_summary(overlay: pd.DataFrame) -> pd.DataFrame:
    data = overlay.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["month"] = data["date"].dt.to_period("M")
    first_nav = float(data.iloc[0]["overlay_nav"])
    rows = []
    prev_nav = None
    for month, group in data.groupby("month", sort=True):
        last = group.iloc[-1]
        nav = float(last["overlay_nav"])
        exposure = float(last["effective_exposure"])
        stock_value = nav * exposure
        cash_value = nav - stock_value
        if prev_nav is None:
            pnl = nav - first_nav
            monthly_return = nav / first_nav - 1.0
        else:
            pnl = nav - prev_nav
            monthly_return = nav / prev_nav - 1.0
        year_group = data[data["date"].dt.year == int(str(month)[:4])]
        year_start_nav = float(year_group.iloc[0]["overlay_nav"])
        year_days = max((last["date"] - year_group.iloc[0]["date"]).days, 1)
        rows.append(
            {
                "月份": str(month),
                "月末总资产": round(nav, 2),
                "股票市值": round(stock_value, 2),
                "现金余额": round(cash_value, 2),
                "股票仓位": round(exposure * 100.0, 2),
                "现金占比": round((1.0 - exposure) * 100.0, 2),
                "当月盈亏(元)": round(pnl, 2),
                "当月收益率": round(monthly_return * 100.0, 2),
                "总收益率": round((nav / first_nav - 1.0) * 100.0, 2),
                "年内收益率": round((nav / year_start_nav - 1.0) * 100.0, 2),
                "年收益率": round(annual_return(year_start_nav, nav, year_days) * 100.0, 2),
            }
        )
        prev_nav = nav
    return pd.DataFrame(rows)


def fmt_pct(value) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2f}%"


def table_html(df: pd.DataFrame) -> str:
    return df.to_html(index=False, escape=False, classes="data")


def write_report(compare: pd.DataFrame, monthly: pd.DataFrame, asset: pd.DataFrame, overlay: pd.DataFrame) -> None:
    rows_2018 = compare[compare["period"] == "2018"].copy()
    v6_ret = float(rows_2018.loc[rows_2018["strategy"] == "v6", "total_return_pct"].iloc[0])
    ov_ret = float(rows_2018.loc[rows_2018["strategy"] == "v6_bear_overlay", "total_return_pct"].iloc[0])
    v6_dd = float(rows_2018.loc[rows_2018["strategy"] == "v6", "max_drawdown_pct"].iloc[0])
    ov_dd = float(rows_2018.loc[rows_2018["strategy"] == "v6_bear_overlay", "max_drawdown_pct"].iloc[0])
    decision = "建议先不直接合并为正式 v6；建议作为 v6 风控 overlay 继续做全周期验证。"
    if ov_ret > v6_ret and ov_dd > v6_dd:
        decision = "建议进入 v6 overlay 集成验证：2018 收益和回撤都明显优于原 v6。"

    source_note = (
        "Tavily 复核结论：公开资料更支持把熊市防御做成趋势跟随/战术配置/风险叠加，核心是控制风险暴露、保留现金流动性；"
        "本轮实现只测试仓位层，不改变 v6 选股。"
    )
    report = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v6 熊市仓位 Overlay 回测</title>
<style>
body{{font-family:Arial,'Microsoft YaHei',sans-serif;margin:24px;color:#222;background:#fafafa}}
h1{{font-size:24px;margin:0 0 12px}}
h2{{font-size:18px;margin-top:26px;border-left:4px solid #2f6f9f;padding-left:8px}}
.summary{{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:10px;margin:16px 0}}
.card{{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px}}
.num{{font-size:22px;font-weight:700;margin-top:6px}}
.good{{color:#0b7a3b}} .bad{{color:#b42318}}
table.data{{border-collapse:collapse;width:100%;background:#fff;margin-top:8px;font-size:13px}}
table.data th,table.data td{{border:1px solid #ddd;padding:6px 8px;text-align:right}}
table.data th:first-child,table.data td:first-child,table.data td:nth-child(2){{text-align:left}}
.note{{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px;line-height:1.7}}
</style>
</head>
<body>
<h1>v6 熊市仓位 Overlay 回测</h1>
<div class="note">
<b>这是什么策略：</b>熊市专用风险暴露层。它不重新选股，只把 v6 每日收益按前一日熊市目标仓位缩放。现金收益暂按 0。<br>
<b>结论：</b>{html.escape(decision)}<br>
<b>依据：</b>{html.escape(source_note)}
</div>
<div class="summary">
<div class="card">2018 v6收益<div class="num bad">{fmt_pct(v6_ret)}</div></div>
<div class="card">2018 overlay收益<div class="num good">{fmt_pct(ov_ret)}</div></div>
<div class="card">2018 v6最大回撤<div class="num bad">{fmt_pct(v6_dd)}</div></div>
<div class="card">2018 overlay最大回撤<div class="num good">{fmt_pct(ov_dd)}</div></div>
</div>
<h2>年度对比</h2>
{table_html(compare)}
<h2>月度收益对比</h2>
{table_html(monthly)}
<h2>月末资产与仓位</h2>
{table_html(asset[asset['月份'].str.startswith(('2018','2022','2023','2024'))])}
<h2>下一步</h2>
<div class="note">
1. 先把 overlay 作为独立风控层继续验证，不要替代 v6 选股。<br>
2. 下一轮要加入真实减仓交易成本/滑点，而不是只做收益缩放。<br>
3. 若 2018、2022、2023、2024 都优于 v6，再做“v6 原策略 + overlay 实盘执行版”。
</div>
</body>
</html>"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def open_report() -> None:
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Start-Process -FilePath '{REPORT_PATH}' -WindowStyle Hidden",
        ]
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text(
        "# tmp_v6 熊市仓位 overlay 实验进度\n\n"
        "目标：只把熊市仓位信号叠加到 v6 每日收益，不改变 v6 选股，用于判断空仓/降仓机制是否值得合并。\n\n",
        encoding="utf-8",
    )
    append_progress("开始：读取 v6 NAV 和 hysteresis_fast_reentry 熊市仓位信号。")
    v6_nav = load_nav("v6")
    regime = load_regime()
    overlay = apply_exposure_overlay(v6_nav, regime, INIT_NAV)
    append_progress(f"完成 overlay 序列 rows={len(overlay)} avg_effective_exposure={overlay['effective_exposure'].mean() * 100:.2f}%。")

    compare = build_multi_period_compare(overlay)
    monthly = build_monthly_returns(overlay)
    asset = build_monthly_asset_summary(overlay)
    overlay.to_csv(OUTPUT_DIR / "v6_bear_overlay_nav.csv", index=False, encoding="utf-8-sig")
    compare.to_csv(OUTPUT_DIR / "multi_period_compare.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "monthly_return_compare.csv", index=False, encoding="utf-8-sig")
    asset.to_csv(OUTPUT_DIR / "monthly_asset_summary.csv", index=False, encoding="utf-8-sig")
    write_report(compare, monthly, asset, overlay)
    append_progress(f"完成报表：{REPORT_PATH}")
    open_report()


if __name__ == "__main__":
    main()

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
RUN_DIR = TMP_DIR / "tmp_v6_2018_bear_hysteresis_experiment_output"
RESULTS_PATH = RUN_DIR / "results.csv"
NAV_PATH = RUN_DIR / "hysteresis_fast_reentry_nav.csv"
TRADES_PATH = RUN_DIR / "hysteresis_fast_reentry_trades.csv"
MONTHLY_EXPOSURE_PATH = RUN_DIR / "monthly_exposure_summary.csv"
OUTPUT_PATH = RUN_DIR / "report_2018_simple.html"

V6_NAV_PATH = TMP_DIR.parent / "v6" / "output" / "nav_series.csv"


def table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>无数据</p>"
    header = "".join(f"<th>{html.escape(str(col))}</th>" for col in df.columns)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{html.escape('' if pd.isna(v) else str(v))}</td>" for v in row.tolist())
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def monthly_returns(nav_path: Path, label: str) -> pd.DataFrame:
    nav = pd.read_csv(nav_path)
    nav["date"] = pd.to_datetime(nav["date"])
    nav["nav"] = pd.to_numeric(nav["nav"], errors="coerce")
    nav = nav[(nav["date"] >= "2018-01-01") & (nav["date"] <= "2018-12-31")].copy()
    nav["month"] = nav["date"].dt.strftime("%Y-%m")
    rows = []
    prev_end = None
    for month, group in nav.groupby("month", sort=True):
        first_nav = prev_end if prev_end is not None else float(group["nav"].iloc[0])
        last_nav = float(group["nav"].iloc[-1])
        prev_end = last_nav
        rows.append({"month": month, label: round((last_nav / first_nav - 1.0) * 100.0, 2)})
    return pd.DataFrame(rows)


def main() -> None:
    results = pd.read_csv(RESULTS_PATH)
    best = results.loc[results["case"].eq("hysteresis_fast_reentry")].copy()

    nav = pd.read_csv(NAV_PATH)
    nav["date"] = pd.to_datetime(nav["date"])
    nav_2018 = nav[(nav["date"] >= "2018-01-01") & (nav["date"] <= "2018-12-31")].copy()
    curve = nav_2018[["date", "nav", "cash", "holdings", "target_exposure", "actual_exposure"]].copy()
    curve["date"] = curve["date"].dt.strftime("%Y-%m-%d")

    trades = pd.read_csv(TRADES_PATH)
    trades["date"] = pd.to_datetime(trades["date"]).dt.strftime("%Y-%m-%d")

    exposure = pd.read_csv(MONTHLY_EXPOSURE_PATH)
    fast_monthly = monthly_returns(NAV_PATH, "latest")
    v6_monthly = monthly_returns(V6_NAV_PATH, "v6")
    monthly = fast_monthly.merge(v6_monthly, on="month", how="outer").merge(exposure, left_on="month", right_on="month", how="left")

    peak_row = curve.loc[curve["nav"].idxmax()].to_dict()
    trough_row = curve.loc[curve["nav"].idxmin()].to_dict()

    summary = {
        "start_nav": round(float(curve["nav"].iloc[0]), 2),
        "end_nav": round(float(curve["nav"].iloc[-1]), 2),
        "peak_nav": round(float(peak_row["nav"]), 2),
        "peak_date": peak_row["date"],
        "low_nav": round(float(trough_row["nav"]), 2),
        "low_date": trough_row["date"],
        "trade_records": int(len(trades)),
    }

    html_text = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>2018 简洁报表</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 16px; background: #f7f8fa; color: #222; }}
h1,h2 {{ margin: 8px 0; }}
.box {{ background:#fff; border:1px solid #d8dee9; padding:10px 12px; margin:12px 0; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; margin: 12px 0; font-size: 13px; }}
th,td {{ border: 1px solid #d8dee9; padding: 6px 8px; text-align: right; white-space: nowrap; }}
th:first-child,td:first-child {{ text-align: left; }}
.scroll {{ overflow:auto; max-height:520px; }}
</style></head><body>
<h1>2018 简洁报表</h1>
<div class="box">
<div>策略：<strong>hysteresis_fast_reentry</strong></div>
<div>起始资金：{summary['start_nav']}</div>
<div>期末资金：{summary['end_nav']}</div>
<div>年内高点：{summary['peak_nav']} / {summary['peak_date']}</div>
<div>年内低点：{summary['low_nav']} / {summary['low_date']}</div>
<div>交易笔数：{summary['trade_records']}</div>
</div>
<h2>年度结果</h2>
<div class="scroll">{table(best)}</div>
<h2>月度收益与月均仓位</h2>
<div class="scroll">{table(monthly)}</div>
<h2>全部交易明细</h2>
<div class="scroll">{table(trades)}</div>
<h2>资金曲线明细</h2>
<div class="scroll">{table(curve)}</div>
</body></html>"""

    OUTPUT_PATH.write_text(html_text, encoding="utf-8")
    subprocess.run(
        ["C:\\Program Files\\PowerShell\\7\\pwsh.exe", "-Command", f"Start-Process -FilePath (Resolve-Path '{OUTPUT_PATH}') -WindowStyle Hidden"],
        check=True,
    )


if __name__ == "__main__":
    main()

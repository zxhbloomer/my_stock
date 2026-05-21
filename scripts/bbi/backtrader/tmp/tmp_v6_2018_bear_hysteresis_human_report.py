from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
RUN_DIR = TMP_DIR / "tmp_v6_2018_bear_hysteresis_experiment_output"
RESULTS_PATH = RUN_DIR / "results.csv"
NAV_PATH = RUN_DIR / "hysteresis_fast_reentry_nav.csv"
TRADES_PATH = RUN_DIR / "hysteresis_fast_reentry_trades.csv"
OUT_PATH = RUN_DIR / "report_2018_human.html"


def monthly_returns(nav: pd.DataFrame) -> pd.DataFrame:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data[(data["date"] >= "2018-01-01") & (data["date"] <= "2018-12-31")].copy()
    data["month"] = data["date"].dt.strftime("%Y-%m")
    rows = []
    previous_end = None
    for month, group in data.groupby("month", sort=True):
        first_nav = previous_end if previous_end is not None else float(group["nav"].iloc[0])
        last_nav = float(group["nav"].iloc[-1])
        previous_end = last_nav
        rows.append(
            {
                "month": month,
                "return_pct": round((last_nav / first_nav - 1.0) * 100.0, 2),
                "avg_position_pct": round(float(group["actual_exposure"].mean() * 100.0), 1),
            }
        )
    return pd.DataFrame(rows)


def summarize_periods(nav: pd.DataFrame) -> pd.DataFrame:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data[(data["date"] >= "2018-01-01") & (data["date"] <= "2018-12-31")].copy()
    data["state"] = "持仓"
    data.loc[data["actual_exposure"] <= 0.001, "state"] = "空仓"
    data.loc[(data["actual_exposure"] > 0.001) & (data["actual_exposure"] <= 0.25), "state"] = "轻仓"

    periods = []
    start = None
    prev_state = None
    prev_date = None
    for _, row in data.iterrows():
        state = row["state"]
        date = row["date"]
        if prev_state is None:
            start = date
            prev_state = state
            prev_date = date
            continue
        if state != prev_state:
            periods.append(
                {
                    "state": prev_state,
                    "start": start.strftime("%Y-%m-%d"),
                    "end": prev_date.strftime("%Y-%m-%d"),
                }
            )
            start = date
            prev_state = state
        prev_date = date
    if prev_state is not None and start is not None and prev_date is not None:
        periods.append({"state": prev_state, "start": start.strftime("%Y-%m-%d"), "end": prev_date.strftime("%Y-%m-%d")})
    return pd.DataFrame(periods)


def important_trades(trades: pd.DataFrame) -> pd.DataFrame:
    data = trades.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data[(data["date"] >= "2018-01-01") & (data["date"] <= "2018-12-31")].copy()
    buy_days = data[data["action"] == "buy"].groupby("date").size().reset_index(name="count")
    sell_days = data[data["reason"].eq("risk_off_exit")].groupby("date").size().reset_index(name="count")
    rows = []
    for _, row in buy_days.iterrows():
        rows.append({"date": row["date"].strftime("%Y-%m-%d"), "event": "回场/加仓", "count": int(row["count"])})
    for _, row in sell_days.iterrows():
        rows.append({"date": row["date"].strftime("%Y-%m-%d"), "event": "风险退出", "count": int(row["count"])})
    out = pd.DataFrame(rows).sort_values(["date", "event"]).reset_index(drop=True)
    return out


def main() -> None:
    results = pd.read_csv(RESULTS_PATH)
    row = results.loc[results["case"].eq("hysteresis_fast_reentry")].iloc[0]
    nav = pd.read_csv(NAV_PATH)
    trades = pd.read_csv(TRADES_PATH)

    nav["date"] = pd.to_datetime(nav["date"])
    year_nav = nav[(nav["date"] >= "2018-01-01") & (nav["date"] <= "2018-12-31")].copy()
    peak_idx = year_nav["nav"].idxmax()
    low_idx = year_nav["nav"].idxmin()
    peak = year_nav.loc[peak_idx]
    low = year_nav.loc[low_idx]

    monthly = monthly_returns(nav)
    periods = summarize_periods(nav)
    events = important_trades(trades)

    monthly_rows = "".join(
        f"<tr><td>{m.month}</td><td>{m.return_pct:.2f}%</td><td>{m.avg_position_pct:.1f}%</td></tr>"
        for m in monthly.itertuples(index=False)
    )
    period_rows = "".join(
        f"<tr><td>{p.state}</td><td>{p.start}</td><td>{p.end}</td></tr>"
        for p in periods.itertuples(index=False)
    )
    event_rows = "".join(
        f"<tr><td>{e.date}</td><td>{e.event}</td><td>{e.count}</td></tr>"
        for e in events.itertuples(index=False)
    )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>2018 新策略简报</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; background: #f7f8fa; color: #222; }}
h1,h2 {{ margin: 10px 0; }}
.box {{ background: #fff; border: 1px solid #d8dee9; padding: 12px; margin: 12px 0; }}
.grid {{ display: grid; grid-template-columns: repeat(2, minmax(180px, 1fr)); gap: 10px; }}
.item {{ background: #fff; border: 1px solid #d8dee9; padding: 12px; }}
.big {{ font-size: 22px; font-weight: bold; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; margin: 12px 0; }}
th, td {{ border: 1px solid #d8dee9; padding: 8px; text-align: left; }}
</style>
</head>
<body>
<h1>2018 新策略简报</h1>

<div class="grid">
  <div class="item"><div>全年收益</div><div class="big">{row["total_return_pct"]:.2f}%</div></div>
  <div class="item"><div>最大回撤</div><div class="big">{row["max_drawdown_pct"]:.2f}%</div></div>
  <div class="item"><div>年末资金</div><div class="big">{row["final_nav"]:.0f}</div></div>
  <div class="item"><div>交易笔数</div><div class="big">{int(row["trade_records"])}</div></div>
</div>

<div class="box">
  <div>年内最高资金：<strong>{peak["nav"]:.0f}</strong>，日期：{peak["date"].strftime("%Y-%m-%d")}</div>
  <div>年内最低资金：<strong>{low["nav"]:.0f}</strong>，日期：{low["date"].strftime("%Y-%m-%d")}</div>
  <div>这套策略在 2018 年主要不是靠重仓赚钱，而是靠空仓/轻仓少亏。</div>
</div>

<h2>每个月结果</h2>
<table>
<thead><tr><th>月份</th><th>月收益</th><th>月均仓位</th></tr></thead>
<tbody>{monthly_rows}</tbody>
</table>

<h2>什么时候空仓、轻仓、持仓</h2>
<table>
<thead><tr><th>状态</th><th>开始</th><th>结束</th></tr></thead>
<tbody>{period_rows}</tbody>
</table>

<h2>关键动作</h2>
<table>
<thead><tr><th>日期</th><th>动作</th><th>股票数</th></tr></thead>
<tbody>{event_rows}</tbody>
</table>
</body>
</html>"""

    OUT_PATH.write_text(html, encoding="utf-8")
    subprocess.run(
        ["C:\\Program Files\\PowerShell\\7\\pwsh.exe", "-Command", f"Start-Process -FilePath (Resolve-Path '{OUT_PATH}') -WindowStyle Hidden"],
        check=True,
    )


if __name__ == "__main__":
    main()

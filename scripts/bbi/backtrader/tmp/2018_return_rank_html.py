from pathlib import Path
import html

import numpy as np
import pandas as pd


BACKTRADER_DIR = Path(__file__).resolve().parents[1]
PANEL_PATH = BACKTRADER_DIR / "v4" / "output" / "panel.parquet"
OUT_DIR = Path(__file__).resolve().parent
CSV_PATH = OUT_DIR / "2018_non_hotmoney_non_new_return_top100.csv"
HTML_PATH = OUT_DIR / "2018_non_hotmoney_non_new_return_top100.html"

YEAR_START = pd.Timestamp("2018-01-01")
YEAR_END = pd.Timestamp("2018-12-31")
FIRST_TRADE_MAX = pd.Timestamp("2018-01-10")
LAST_TRADE_MIN = pd.Timestamp("2018-12-20")
MIN_LIST_DAYS = 365
HOT_MONEY_MAX_HITS = 1


def pct(value):
    if pd.isna(value):
        return ""
    return f"{value:.2f}%"


def fmt_float(value, digits=4):
    if pd.isna(value):
        return ""
    return f"{value:.{digits}f}"


def build_rank():
    panel = pd.read_parquet(PANEL_PATH)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])

    year_panel = panel[
        (panel["trade_date"] >= YEAR_START)
        & (panel["trade_date"] <= YEAR_END)
    ].copy()
    year_panel = year_panel.sort_values(["ts_code", "trade_date"])

    rows = []
    stats = {
        "raw_codes": int(year_panel["ts_code"].nunique()),
        "after_full_year": 0,
        "after_non_new": 0,
        "after_non_hotmoney": 0,
        "after_no_st_suspend": 0,
    }

    for ts_code, group in year_panel.groupby("ts_code", sort=False):
        group = group.dropna(subset=["close_qfq"]).copy()
        if group.empty:
            continue

        first = group.iloc[0]
        last = group.iloc[-1]
        if first["trade_date"] > FIRST_TRADE_MAX or last["trade_date"] < LAST_TRADE_MIN:
            continue
        stats["after_full_year"] += 1

        if pd.isna(first.get("list_days")) or first["list_days"] < MIN_LIST_DAYS:
            continue
        stats["after_non_new"] += 1

        if bool(group["is_st"].any()) or bool(group["is_suspended"].any()):
            continue
        stats["after_no_st_suspend"] += 1

        max_hot_money_hits = int(group["hot_money_risk_hits"].fillna(0).max())
        if max_hot_money_hits > HOT_MONEY_MAX_HITS:
            continue
        stats["after_non_hotmoney"] += 1

        start_close = float(first["close_qfq"])
        end_close = float(last["close_qfq"])
        if not np.isfinite(start_close) or start_close <= 0 or not np.isfinite(end_close):
            continue

        annual_return = end_close / start_close - 1.0
        rows.append(
            {
                "rank": None,
                "ts_code": ts_code,
                "name": first["name"],
                "annual_return_pct": annual_return * 100.0,
                "start_date": first["trade_date"].strftime("%Y-%m-%d"),
                "end_date": last["trade_date"].strftime("%Y-%m-%d"),
                "start_close_qfq": start_close,
                "end_close_qfq": end_close,
                "list_date": pd.to_datetime(first["list_date"]).strftime("%Y-%m-%d")
                if pd.notna(first["list_date"])
                else "",
                "list_days_at_start": int(first["list_days"]),
                "max_hot_money_hits": max_hot_money_hits,
                "max_recent_limit_up_20": int(group["recent_limit_up_20"].fillna(0).max()),
                "max_recent_limit_up_63": int(group["recent_limit_up_63"].fillna(0).max()),
                "max_lhb_count_20": int(group["lhb_count_20"].fillna(0).max()),
                "max_turnover_rate_ma20": float(group["turnover_rate_ma20"].max(skipna=True)),
                "max_volume_ratio_20": float(group["volume_ratio_max20"].max(skipna=True)),
            }
        )

    result = (
        pd.DataFrame(rows)
        .sort_values("annual_return_pct", ascending=False)
        .head(100)
        .reset_index(drop=True)
    )
    result["rank"] = np.arange(1, len(result) + 1)
    return result, stats


def render_html(result, stats):
    rows = []
    for _, row in result.iterrows():
        ret_class = "pos" if row["annual_return_pct"] >= 0 else "neg"
        rows.append(
            "<tr>"
            f"<td>{int(row['rank'])}</td>"
            f"<td>{html.escape(row['ts_code'])}</td>"
            f"<td>{html.escape(str(row['name']))}</td>"
            f"<td class='{ret_class}'>{pct(row['annual_return_pct'])}</td>"
            f"<td>{html.escape(row['start_date'])}</td>"
            f"<td>{html.escape(row['end_date'])}</td>"
            f"<td>{fmt_float(row['start_close_qfq'])}</td>"
            f"<td>{fmt_float(row['end_close_qfq'])}</td>"
            f"<td>{html.escape(row['list_date'])}</td>"
            f"<td>{int(row['list_days_at_start'])}</td>"
            f"<td>{int(row['max_hot_money_hits'])}</td>"
            f"<td>{int(row['max_recent_limit_up_20'])}</td>"
            f"<td>{int(row['max_recent_limit_up_63'])}</td>"
            f"<td>{int(row['max_lhb_count_20'])}</td>"
            f"<td>{fmt_float(row['max_turnover_rate_ma20'], 2)}</td>"
            f"<td>{fmt_float(row['max_volume_ratio_20'], 2)}</td>"
            "</tr>"
        )

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>2018 非游资非新股收益排行 Top 100</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d8dde6;
      --text: #172033;
      --muted: #5f6b7a;
      --head: #26364d;
      --pos: #b42318;
      --neg: #176b3a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      line-height: 1.45;
    }}
    main {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 28px 24px 40px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .sub {{
      color: var(--muted);
      margin-bottom: 20px;
      font-size: 14px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }}
    .stat {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px 14px;
    }}
    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .stat strong {{
      font-size: 22px;
    }}
    .note {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px 14px;
      margin-bottom: 18px;
      color: var(--muted);
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 9px;
      text-align: right;
      white-space: nowrap;
    }}
    th {{
      position: sticky;
      top: 0;
      background: var(--head);
      color: #fff;
      font-weight: 600;
      z-index: 1;
    }}
    td:nth-child(2), td:nth-child(3), th:nth-child(2), th:nth-child(3) {{
      text-align: left;
    }}
    tbody tr:hover {{
      background: #eef3f8;
    }}
    .pos {{ color: var(--pos); font-weight: 700; }}
    .neg {{ color: var(--neg); font-weight: 700; }}
    .table-wrap {{
      overflow: auto;
      max-height: calc(100vh - 240px);
      border-radius: 6px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>2018 非游资、非新股收益排行 Top 100</h1>
    <div class="sub">收益按 2018 年首末交易日前复权收盘价计算，降序排列。</div>
    <section class="stats">
      <div class="stat"><span>2018 有行情股票数</span><strong>{stats['raw_codes']}</strong></div>
      <div class="stat"><span>覆盖全年交易窗口</span><strong>{stats['after_full_year']}</strong></div>
      <div class="stat"><span>排除新股后</span><strong>{stats['after_non_new']}</strong></div>
      <div class="stat"><span>排除 ST/停牌异常后</span><strong>{stats['after_no_st_suspend']}</strong></div>
      <div class="stat"><span>排除游资类后</span><strong>{stats['after_non_hotmoney']}</strong></div>
    </section>
    <section class="note">
      口径：首个交易日不晚于 2018-01-10，末个交易日不早于 2018-12-20；2018 年首个交易日上市满 365 天；
      全年无 ST 标记和停牌标记；游资类使用项目 v4 的 hot_money_risk_hits，保留全年最大值不超过 1 的股票。
      本版未加入“非脉冲式上涨”过滤。
    </section>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>排名</th><th>代码</th><th>名称</th><th>全年收益</th>
            <th>起始日</th><th>结束日</th><th>起始前复权收盘</th><th>结束前复权收盘</th>
            <th>上市日</th><th>起始上市天数</th><th>最大游资命中</th>
            <th>20日涨停最大数</th><th>63日涨停最大数</th><th>20日龙虎榜最大数</th>
            <th>20日均换手最大</th><th>20日量比最大</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </div>
  </main>
</body>
</html>
"""
    HTML_PATH.write_text(html_text, encoding="utf-8")


def main():
    result, stats = build_rank()
    result.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    render_html(result, stats)
    print(f"rows={len(result)}")
    print(f"csv={CSV_PATH}")
    print(f"html={HTML_PATH}")
    print(result[["rank", "ts_code", "name", "annual_return_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()

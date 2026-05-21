from __future__ import annotations

import html
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "tmp_v6_2018_bear_defensive_portfolio_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v6_2018_bear_defensive_portfolio_README.md"
RESULTS_PATH = OUTPUT_DIR / "results.csv"

INIT_CASH = 500_000.0
COMMISSION_BUY = 0.0005
COMMISSION_SELL = 0.0015
MIN_COMMISSION = 5.0
MAX_HOLDINGS = 20

FINA_COLUMNS = ["roe_dt", "grossprofit_margin", "ocf_to_or", "debt_to_assets"]
DAILY_BASIC_COLUMNS = ["dv_ttm", "pb"]


def append_progress(message: str):
    with README_PATH.open("a", encoding="utf-8") as f:
        f.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return (values - values.mean()) / std


def winsorize_series(series: pd.Series, lower: float = 0.02, upper: float = 0.98) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    valid = values.dropna()
    if valid.empty:
        return values
    lo = valid.quantile(lower)
    hi = valid.quantile(upper)
    return values.clip(lower=lo, upper=hi)


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
    merged = []
    for ts_code, group in left.groupby("ts_code", sort=False):
        src = right[right["ts_code"] == ts_code]
        if src.empty:
            out = group.copy()
            for col in FINA_COLUMNS:
                out[col] = np.nan
            merged.append(out)
            continue
        src = src.drop_duplicates(subset=["ann_date"], keep="last")
        out = pd.merge_asof(
            group.sort_values("trade_date"),
            src[["ann_date"] + FINA_COLUMNS].sort_values("ann_date"),
            left_on="trade_date",
            right_on="ann_date",
            direction="backward",
        )
        merged.append(out)
    return pd.concat(merged, ignore_index=True)


def first_trading_days_of_month(dates) -> pd.Series:
    d = pd.to_datetime(pd.Series(dates))
    return d.dt.to_period("M") != d.shift(1).dt.to_period("M")


def calc_commission(amount: float, is_buy: bool) -> float:
    rate = COMMISSION_BUY if is_buy else COMMISSION_SELL
    return max(abs(amount) * rate, MIN_COMMISSION)


def load_v6_baselines():
    output = V6_DIR / "output"
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    nav = pd.read_csv(output / "nav_series.csv")
    trades = pd.read_csv(output / "trade_records.csv")
    panel = pd.read_parquet(output / "panel.parquet")
    market = pd.read_parquet(output / "market_index.parquet")
    return summary, nav, trades, panel, market


def load_other_baseline_navs() -> dict[str, pd.DataFrame]:
    out = {}
    for name in ["v4", "v5"]:
        path = BACKTRADER_DIR / name / "output" / "nav_series.csv"
        out[name] = pd.read_csv(path)
    return out


def load_support_data(db_url: str, schema: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        daily_basic = pd.read_sql_query(
            text(
                f"""
                select ts_code, trade_date, dv_ttm, pb
                from {schema}."027_daily_basic"
                where trade_date >= :start_date and trade_date <= :end_date
                """
            ),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )
        fina = pd.read_sql_query(
            text(
                f"""
                select ts_code, ann_date, roe_dt, grossprofit_margin, ocf_to_or, debt_to_assets
                from {schema}."042_fina_indicator"
                where ann_date <= :end_date
                """
            ),
            conn,
            params={"end_date": end_date},
        )
    return daily_basic, fina


def add_market_features(panel: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    market_frame = market.copy()
    market_frame["trade_date"] = pd.to_datetime(market_frame["trade_date"])
    market_frame = market_frame.sort_values("trade_date")
    market_frame["market_ret_1"] = pd.to_numeric(market_frame["close"], errors="coerce").pct_change()
    out = out.merge(market_frame[["trade_date", "market_ret_1"]], on="trade_date", how="left")
    out["ret_1"] = out.groupby("ts_code", sort=False)["close_qfq"].pct_change(fill_method=None)
    out["volatility_126"] = out.groupby("ts_code", sort=False)["ret_1"].transform(lambda s: s.rolling(126, min_periods=80).std())
    cov = (
        out.groupby("ts_code", sort=False)
        .apply(lambda g: g["ret_1"].rolling(126, min_periods=80).cov(g["market_ret_1"]))
        .reset_index(level=0, drop=True)
    )
    mvar = out.groupby("ts_code", sort=False)["market_ret_1"].transform(lambda s: s.rolling(126, min_periods=80).var())
    out["beta_126"] = cov / mvar.replace(0.0, np.nan)
    rolling_high = out.groupby("ts_code", sort=False)["close_qfq"].transform(lambda s: s.rolling(126, min_periods=80).max())
    out["drawdown_126"] = out["close_qfq"] / rolling_high - 1.0
    return out


def add_support_features(panel: pd.DataFrame, daily_basic: pd.DataFrame, fina: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    daily = daily_basic.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    out = out.merge(daily[["ts_code", "trade_date"] + DAILY_BASIC_COLUMNS], on=["ts_code", "trade_date"], how="left")
    out = merge_financial_features(out, fina)
    return out


def compute_defensive_score(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    low_risk_score = (
        -0.30 * zscore(winsorize_series(out["volatility_63"]))
        -0.30 * zscore(winsorize_series(out["volatility_126"]))
        -0.20 * zscore(winsorize_series(out["beta_126"]))
        +0.20 * zscore(winsorize_series(out["drawdown_126"]))
    )
    dividend_score = zscore(winsorize_series(out["dv_ttm"]))
    quality_score = (
        0.35 * zscore(winsorize_series(out["roe_dt"]))
        +0.25 * zscore(winsorize_series(out["grossprofit_margin"]))
        +0.25 * zscore(winsorize_series(out["ocf_to_or"]))
        -0.15 * zscore(winsorize_series(out["debt_to_assets"]))
    )
    value_score = -zscore(winsorize_series(out["pb"]))
    momentum_score = 0.40 * zscore(winsorize_series(out["ret_21"])) + 0.60 * zscore(winsorize_series(out["ret_63"]))
    out["defensive_score"] = (
        0.35 * low_risk_score
        + 0.25 * dividend_score
        + 0.20 * quality_score
        + 0.10 * value_score
        + 0.10 * momentum_score
    )
    return out


def build_signal_panel(panel: pd.DataFrame, market: pd.DataFrame, daily_basic: pd.DataFrame, fina: pd.DataFrame) -> pd.DataFrame:
    enriched = add_market_features(panel, market)
    enriched = add_support_features(enriched, daily_basic, fina)
    enriched = compute_defensive_score(enriched)
    base = (
        enriched["is_eligible"].fillna(False)
        & (enriched["hot_money_risk_hits"].fillna(99) < 2)
        & (enriched["recent_limit_down_20"].fillna(0) == 0)
        & (pd.to_numeric(enriched["ret_21"], errors="coerce") > -0.18)
        & (pd.to_numeric(enriched["ret_63"], errors="coerce") > -0.35)
        & (pd.to_numeric(enriched["pb"], errors="coerce") > 0)
        & (pd.to_numeric(enriched["dv_ttm"], errors="coerce") > 0)
        & pd.to_numeric(enriched["volatility_126"], errors="coerce").notna()
        & pd.to_numeric(enriched["beta_126"], errors="coerce").notna()
        & pd.to_numeric(enriched["roe_dt"], errors="coerce").notna()
    )
    enriched["candidate"] = base
    return enriched


def run_backtest(signal_panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    panel = signal_panel.copy()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[(panel["trade_date"] >= "2018-01-01") & (panel["trade_date"] <= "2018-12-31")].copy()
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    dates = sorted(panel["trade_date"].unique())
    by_date = {d: g.set_index("ts_code", drop=False) for d, g in panel.groupby("trade_date", sort=True)}

    cash = INIT_CASH
    holdings: dict[str, dict] = {}
    nav_rows = []
    trades = []
    target_amount = INIT_CASH / MAX_HOLDINGS

    for i, date in enumerate(dates):
        day = by_date[date]
        month_start = i > 0 and pd.Timestamp(date).month != pd.Timestamp(dates[i - 1]).month
        if month_start:
            signal = by_date[dates[i - 1]]
            candidates = signal[signal["candidate"].fillna(False)].copy()
            candidates = candidates.sort_values(["defensive_score", "dv_ttm", "roe_dt"], ascending=[False, False, False])
            target_codes = list(candidates["ts_code"].head(MAX_HOLDINGS))
            target_set = set(target_codes)

            for code in list(holdings):
                if code not in target_set and code in day.index:
                    row = day.loc[code]
                    price = float(row["open"]) if float(row.get("open", np.nan)) > 0 else np.nan
                    if np.isfinite(price):
                        shares = holdings[code]["shares"]
                        amount = price * shares
                        comm = calc_commission(amount, is_buy=False)
                        cash += amount - comm
                        trades.append({"date": str(date)[:10], "ts_code": code, "action": "sell", "price": price, "shares": shares, "reason": "rebalance"})
                        del holdings[code]

            for code in target_codes:
                if code in holdings or code not in day.index:
                    continue
                row = day.loc[code]
                if bool(row.get("is_suspended", False)):
                    continue
                price = float(row["open"]) if float(row.get("open", np.nan)) > 0 else np.nan
                if not np.isfinite(price):
                    continue
                shares = int(min(target_amount, cash) / price / 100) * 100
                if shares < 100:
                    continue
                amount = price * shares
                comm = calc_commission(amount, is_buy=True)
                if amount + comm > cash:
                    continue
                cash -= amount + comm
                holdings[code] = {"shares": shares, "last_price": price}
                trades.append({"date": str(date)[:10], "ts_code": code, "action": "buy", "price": price, "shares": shares, "reason": "defensive_monthly"})

        nav = cash
        for code, pos in holdings.items():
            if code in day.index and float(day.loc[code].get("close", np.nan)) > 0:
                pos["last_price"] = float(day.loc[code]["close"])
            nav += pos["last_price"] * pos["shares"]
        nav_rows.append({"date": str(date)[:10], "nav": nav, "cash": cash, "holdings": len(holdings)})

    nav_df = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    return nav_df, trades_df, summarize_nav(nav_df, trades_df)


def summarize_nav(nav: pd.DataFrame, trades: pd.DataFrame | None = None) -> dict:
    if nav.empty:
        return {}
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    values = pd.to_numeric(data["nav"], errors="coerce")
    total_ret = values.iloc[-1] / values.iloc[0] - 1.0
    dd = values / values.cummax() - 1.0
    days = max((data["date"].iloc[-1] - data["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0 if total_ret > -1 else -1.0
    return {
        "start_date": str(data["date"].iloc[0])[:10],
        "end_date": str(data["date"].iloc[-1])[:10],
        "final_nav": round(float(values.iloc[-1]), 2),
        "total_return_pct": round(float(total_ret * 100.0), 4),
        "annual_return_pct": round(float(annual_ret * 100.0), 4),
        "max_drawdown_pct": round(float(dd.min() * 100.0), 4),
        "trade_records": 0 if trades is None else int(len(trades)),
        "buy_trades": 0 if trades is None or trades.empty else int(trades["action"].eq("buy").sum()),
    }


def slice_2018(nav: pd.DataFrame) -> pd.DataFrame:
    out = nav.copy()
    out["date"] = pd.to_datetime(out["date"])
    return out[(out["date"] >= "2018-01-01") & (out["date"] <= "2018-12-31")].copy()


def slice_trades_2018(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or trades.empty:
        return pd.DataFrame()
    out = trades.copy()
    out["date"] = pd.to_datetime(out["date"])
    return out[(out["date"] >= "2018-01-01") & (out["date"] <= "2018-12-31")].copy()


def period_return_table(nav_map: dict[str, pd.DataFrame], freq: str) -> pd.DataFrame:
    rows = []
    for name, nav in nav_map.items():
        if nav is None or nav.empty:
            continue
        data = nav.copy()
        data["date"] = pd.to_datetime(data["date"])
        data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
        data = data.dropna(subset=["date", "nav"]).sort_values("date")
        if data.empty:
            continue
        if freq == "Y":
            data["period"] = data["date"].dt.strftime("%Y")
        elif freq == "M":
            data["period"] = data["date"].dt.strftime("%Y-%m")
        else:
            raise ValueError(freq)
        previous_end = None
        for period, group in data.groupby("period", sort=True):
            first_nav = previous_end if previous_end is not None else float(group["nav"].iloc[0])
            last_nav = float(group["nav"].iloc[-1])
            previous_end = last_nav
            if first_nav <= 0:
                continue
            rows.append({"period": period, "strategy": name, "return_pct": round((last_nav / first_nav - 1.0) * 100.0, 2)})
    if not rows:
        return pd.DataFrame(columns=["period"])
    table = pd.DataFrame(rows).pivot(index="period", columns="strategy", values="return_pct").reset_index()
    table.columns.name = None
    return table


def render_report(compare: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame, notes: str):
    def table(df: pd.DataFrame) -> str:
        if df.empty:
            return "<p>无数据</p>"
        head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
        body = []
        for _, row in df.iterrows():
            cells = "".join(f"<td>{html.escape('' if pd.isna(v) else str(v))}</td>" for v in row.tolist())
            body.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"

    report = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>2018 独立熊市防御组合 vs v6</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 16px; background: #f6f8fb; color: #222; }}
h1, h2 {{ margin: 8px 0; }}
.note {{ background: #fff; border: 1px solid #d8dee9; padding: 10px 12px; margin: 12px 0; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; margin: 12px 0; font-size: 13px; }}
th, td {{ border: 1px solid #d8dee9; padding: 6px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
.scroll {{ overflow: auto; max-height: 520px; }}
</style>
</head>
<body>
<h1>2018 独立熊市防御组合 vs v4/v5/v6</h1>
<div class="note">
这次不是改 v6，而是单独做一个 2018 熊市 long-only 防御组合。月频、20 只、等权、低波红利质量打分。
</div>
<h2>核心结果</h2>
<div class="scroll">{table(compare)}</div>
<h2>年度对比</h2>
<div class="scroll">{table(yearly)}</div>
<h2>2018 月度对比</h2>
<div class="scroll">{table(monthly)}</div>
<h2>结论与建议</h2>
<div class="note"><pre>{html.escape(notes)}</pre></div>
</body>
</html>"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def open_report():
    subprocess.run(
        [
            "C:\\Program Files\\PowerShell\\7\\pwsh.exe",
            "-Command",
            f"Start-Process -FilePath (Resolve-Path '{REPORT_PATH}') -WindowStyle Hidden",
        ],
        check=True,
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text("# tmp_v6 2018 独立熊市防御组合进度\n\n", encoding="utf-8")
    append_progress("开始：加载 v6 基线与独立熊市策略所需数据。")

    sys_path = str(V6_DIR)
    if sys_path not in __import__("sys").path:
        __import__("sys").path.insert(0, sys_path)
    import config as v6_config  # type: ignore

    v6_summary, v6_nav, v6_trades, panel, market = load_v6_baselines()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    start_date = str(panel["trade_date"].min().date())
    end_date = str(panel["trade_date"].max().date())
    daily_basic, fina = load_support_data(v6_config.DB_URL, v6_config.SCHEMA, start_date, end_date)
    append_progress("完成 daily_basic / fina_indicator 加载。")

    signal_panel = build_signal_panel(panel, market, daily_basic, fina)
    append_progress("完成防御因子与候选池构建。")

    bear_nav, bear_trades, bear_stats = run_backtest(signal_panel)
    bear_nav.to_csv(OUTPUT_DIR / "bear_defensive_nav.csv", index=False)
    bear_trades.to_csv(OUTPUT_DIR / "bear_defensive_trades.csv", index=False)
    append_progress(
        f"完成独立熊市组合回测：2018 total={bear_stats['total_return_pct']:.2f}% max_dd={bear_stats['max_drawdown_pct']:.2f}%"
    )

    baselines = load_other_baseline_navs()
    v4_trades = pd.read_csv(BACKTRADER_DIR / "v4" / "output" / "trade_records.csv")
    v5_trades = pd.read_csv(BACKTRADER_DIR / "v5" / "output" / "trade_records.csv")
    nav_map = {
        "v4": baselines["v4"],
        "v5": baselines["v5"],
        "v6": v6_nav,
        "bear_defensive_2018": bear_nav,
    }
    trade_map = {
        "v4": v4_trades,
        "v5": v5_trades,
        "v6": v6_trades,
        "bear_defensive_2018": bear_trades,
    }
    compare_rows = []
    for name, nav in nav_map.items():
        stats = summarize_nav(slice_2018(nav), slice_trades_2018(trade_map[name]))
        compare_rows.append({"strategy": name, **stats})
    compare = pd.DataFrame(compare_rows)
    compare.to_csv(RESULTS_PATH, index=False, encoding="utf-8-sig")

    yearly = period_return_table(nav_map, "Y")
    monthly = period_return_table({k: slice_2018(v) for k, v in nav_map.items()}, "M")
    monthly = monthly[monthly["period"].astype(str).str.startswith("2018-")].reset_index(drop=True)

    merge_advice = "建议合并" if compare.loc[compare["strategy"].eq("bear_defensive_2018"), "total_return_pct"].iloc[0] > compare.loc[compare["strategy"].eq("v6"), "total_return_pct"].iloc[0] else "不建议合并"
    notes = (
        "策略研究专家结论：2018 独立熊市策略应更接近低波红利质量组合，而不是 v6 强势轮动的熊市补丁。\n"
        "实现评审：本轮先用 ann_date backward merge 处理财务 PIT；分红先用 daily_basic/dv_ttm 做最小版本，尚未接 dividend 事件表。\n"
        f"合并建议：{merge_advice}。\n"
        "下一步：若这次结果优于 v6，再补 dividend 事件口径、行业分散约束、beta 与下行波动约束，并扩大到 2017/2019/2022 做稳健性验证。"
    )
    render_report(compare, yearly, monthly, notes)
    append_progress(f"报告已生成：{REPORT_PATH}")
    open_report()
    append_progress("报告已自动打开。")


if __name__ == "__main__":
    main()

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V6_DIR = BACKTRADER_DIR / "v6"
BASELINE_MODULE_PATH = TMP_DIR / "tmp_v6_2018_bear_defensive_portfolio.py"
PREV_RESULTS_PATH = TMP_DIR / "tmp_v6_2018_bear_defensive_evolution_output" / "results.csv"
OUTPUT_DIR = TMP_DIR / "tmp_v6_2018_bear_regime_state_machine_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
README_PATH = TMP_DIR / "tmp_v6_2018_bear_regime_state_machine_README.md"

INIT_CASH = 500_000.0
COMMISSION_BUY = 0.0005
COMMISSION_SELL = 0.0015
MIN_COMMISSION = 5.0

CASES = [
    {"name": "state_machine_base", "max_holdings": 20, "max_per_industry": 3, "industry_neutral": True, "quality_trap": True},
    {"name": "state_machine_strict", "max_holdings": 20, "max_per_industry": 3, "industry_neutral": True, "quality_trap": True},
    {"name": "state_machine_breadth", "max_holdings": 20, "max_per_industry": 3, "industry_neutral": True, "quality_trap": True},
]


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


def group_zscore(frame: pd.DataFrame, group_col: str, value_col: str) -> pd.Series:
    def _score(group: pd.DataFrame) -> pd.Series:
        values = pd.to_numeric(group[value_col], errors="coerce")
        std = values.std(ddof=0)
        if pd.isna(std) or std == 0:
            return pd.Series(0.0, index=group.index)
        return (values - values.mean()) / std

    return frame.groupby(group_col, dropna=False, group_keys=False).apply(_score)


def select_with_industry_cap(frame: pd.DataFrame, max_holdings: int, max_per_industry: int | None) -> pd.DataFrame:
    ranked = frame.sort_values("defensive_score", ascending=False).reset_index(drop=True)
    if max_per_industry is None:
        return ranked.head(max_holdings).copy()
    selected_rows = []
    counts: dict[str, int] = {}
    for _, row in ranked.iterrows():
        industry = row.get("industry")
        industry_key = "UNKNOWN" if pd.isna(industry) or industry in ("", "None", None) else str(industry)
        if counts.get(industry_key, 0) >= max_per_industry:
            continue
        selected_rows.append(row.to_dict())
        counts[industry_key] = counts.get(industry_key, 0) + 1
        if len(selected_rows) >= max_holdings:
            break
    return pd.DataFrame(selected_rows)


def quality_trap_mask(frame: pd.DataFrame) -> pd.Series:
    dv = pd.to_numeric(frame["dv_ttm"], errors="coerce")
    roe = pd.to_numeric(frame["roe_dt"], errors="coerce")
    ocf = pd.to_numeric(frame["ocf_to_or"], errors="coerce")
    debt = pd.to_numeric(frame["debt_to_assets"], errors="coerce")
    return (dv >= dv.quantile(0.7)) & ((roe <= 3.0) | (ocf <= 0.0) | (debt >= 75.0))


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
    return {name: pd.read_csv(BACKTRADER_DIR / name / "output" / "nav_series.csv") for name in ["v4", "v5"]}


def load_other_baseline_trades() -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(BACKTRADER_DIR / name / "output" / "trade_records.csv") for name in ["v4", "v5"]}


def load_support_data(db_url: str, schema: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        daily_basic = pd.read_sql_query(
            text(f"""select ts_code, trade_date, dv_ttm, pb, pe_ttm from {schema}."027_daily_basic" where trade_date >= :start_date and trade_date <= :end_date"""),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )
        fina = pd.read_sql_query(
            text(f"""select ts_code, ann_date, roe_dt, grossprofit_margin, ocf_to_or, debt_to_assets from {schema}."042_fina_indicator" where ann_date <= :end_date"""),
            conn,
            params={"end_date": end_date},
        )
        stock_basic = pd.read_sql_query(
            text(f"""select ts_code, industry from {schema}."001_stock_basic" """),
            conn,
        )
        moneyflow = pd.read_sql_query(
            text(f"""select ts_code, trade_date, net_mf_amount from {schema}."080_moneyflow" where trade_date >= :start_date and trade_date <= :end_date"""),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )
        hsgt = pd.read_sql_query(
            text(f"""select trade_date, north_money, south_money from {schema}."087_moneyflow_hsgt" where trade_date >= :start_date and trade_date <= :end_date"""),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )
    return daily_basic, fina, stock_basic, moneyflow, hsgt


def merge_financial_features(panel: pd.DataFrame, fina: pd.DataFrame) -> pd.DataFrame:
    left = panel.copy()
    left["trade_date"] = pd.to_datetime(left["trade_date"])
    left = left.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    right = fina.copy()
    right["ann_date"] = pd.to_datetime(right["ann_date"])
    right = right.sort_values(["ts_code", "ann_date"]).reset_index(drop=True)
    merged = []
    fina_cols = ["roe_dt", "grossprofit_margin", "ocf_to_or", "debt_to_assets"]
    for code, group in left.groupby("ts_code", sort=False):
        src = right[right["ts_code"] == code]
        if src.empty:
            tmp = group.copy()
            for col in fina_cols:
                tmp[col] = np.nan
            merged.append(tmp)
            continue
        src = src.drop_duplicates(subset=["ann_date"], keep="last")
        tmp = pd.merge_asof(
            group.sort_values("trade_date"),
            src[["ann_date"] + fina_cols].sort_values("ann_date"),
            left_on="trade_date",
            right_on="ann_date",
            direction="backward",
        )
        merged.append(tmp)
    return pd.concat(merged, ignore_index=True)


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
    out["drawdown_126"] = out.groupby("ts_code", sort=False)["close_qfq"].transform(lambda s: s / s.rolling(126, min_periods=80).max() - 1.0)
    cov = (
        out.groupby("ts_code", sort=False)[["ret_1", "market_ret_1"]]
        .apply(lambda g: g["ret_1"].rolling(126, min_periods=80).cov(g["market_ret_1"]))
        .reset_index(level=0, drop=True)
    )
    mvar = out.groupby("ts_code", sort=False)["market_ret_1"].transform(lambda s: s.rolling(126, min_periods=80).var())
    out["beta_126"] = cov / mvar.replace(0.0, np.nan)
    return out


def build_base_panel(panel: pd.DataFrame, market: pd.DataFrame, daily_basic: pd.DataFrame, fina: pd.DataFrame, stock_basic: pd.DataFrame, moneyflow: pd.DataFrame, hsgt: pd.DataFrame) -> pd.DataFrame:
    enriched = add_market_features(panel, market)
    daily = daily_basic.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    enriched = enriched.merge(daily[["ts_code", "trade_date", "dv_ttm", "pb", "pe_ttm"]], on=["ts_code", "trade_date"], how="left")
    enriched = merge_financial_features(enriched, fina)
    enriched = add_moneyflow_features(enriched, moneyflow)
    enriched = build_regime_features(enriched, market, hsgt)
    enriched = enriched.merge(stock_basic[["ts_code", "industry"]], on="ts_code", how="left")
    enriched["industry"] = enriched["industry"].fillna("UNKNOWN")
    pe = pd.to_numeric(enriched["pe_ttm"], errors="coerce")
    enriched["ep"] = np.where(pe > 0, 1.0 / pe, np.nan)
    return enriched


def add_moneyflow_features(panel: pd.DataFrame, moneyflow: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    frame = moneyflow.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["net_mf_amount"] = pd.to_numeric(frame["net_mf_amount"], errors="coerce")
    out = out.merge(frame[["ts_code", "trade_date", "net_mf_amount"]], on=["ts_code", "trade_date"], how="left")
    out["net_mf_amount"] = out["net_mf_amount"].fillna(0.0)
    return out


def build_regime_features(panel: pd.DataFrame, market: pd.DataFrame, hsgt: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    market_frame = market.copy()
    market_frame["trade_date"] = pd.to_datetime(market_frame["trade_date"])
    market_frame = market_frame.sort_values("trade_date")
    market_frame["market_ma60"] = pd.to_numeric(market_frame["close"], errors="coerce").rolling(60, min_periods=40).mean()
    market_frame["market_above_ma60"] = (pd.to_numeric(market_frame["close"], errors="coerce") > market_frame["market_ma60"]).astype(int)
    market_frame["market_drawdown_120"] = pd.to_numeric(market_frame["close"], errors="coerce") / pd.to_numeric(market_frame["close"], errors="coerce").rolling(120, min_periods=60).max() - 1.0

    stock_flags = out[["trade_date", "ts_code", "close_qfq"]].copy()
    stock_flags["ma20"] = stock_flags.groupby("ts_code", sort=False)["close_qfq"].transform(lambda s: s.rolling(20, min_periods=15).mean())
    stock_flags["above_ma20"] = (pd.to_numeric(stock_flags["close_qfq"], errors="coerce") > pd.to_numeric(stock_flags["ma20"], errors="coerce")).astype(float)
    breadth = stock_flags.groupby("trade_date", sort=True)["above_ma20"].mean().reset_index(name="breadth_above_ma20")

    hsgt_frame = hsgt.copy()
    hsgt_frame["trade_date"] = pd.to_datetime(hsgt_frame["trade_date"])
    hsgt_frame["north_money"] = pd.to_numeric(hsgt_frame["north_money"], errors="coerce").fillna(0.0)
    hsgt_frame = hsgt_frame.groupby("trade_date", as_index=False)["north_money"].sum().sort_values("trade_date")
    hsgt_frame["north_money_ma20"] = hsgt_frame["north_money"].rolling(20, min_periods=5).mean()
    hsgt_frame["northbound_flow_strength"] = np.where(
        hsgt_frame["north_money_ma20"].abs() > 1e-9,
        hsgt_frame["north_money"] / hsgt_frame["north_money_ma20"].replace(0.0, np.nan),
        0.0,
    )
    hsgt_frame["northbound_flow_strength"] = hsgt_frame["northbound_flow_strength"].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    regime = market_frame[["trade_date", "market_above_ma60", "market_drawdown_120"]].merge(breadth, on="trade_date", how="left").merge(
        hsgt_frame[["trade_date", "northbound_flow_strength"]], on="trade_date", how="left"
    )
    regime["breadth_above_ma20"] = regime["breadth_above_ma20"].fillna(0.0)
    regime["northbound_flow_strength"] = regime["northbound_flow_strength"].fillna(0.0)
    return out.merge(regime, on="trade_date", how="left")


def classify_regime(row: pd.Series, case_name: str) -> str:
    above = int(row.get("market_above_ma60", 0))
    drawdown = float(row.get("market_drawdown_120", 0.0))
    breadth = float(row.get("breadth_above_ma20", 0.0))
    flow = float(row.get("northbound_flow_strength", 0.0))
    if case_name == "state_machine_strict":
        if above == 0 and drawdown <= -0.12 and breadth <= 0.38:
            return "risk_off"
        if above == 1 and drawdown >= -0.06 and breadth >= 0.58 and flow > -0.2:
            return "risk_on"
        return "neutral"
    if case_name == "state_machine_breadth":
        if breadth <= 0.32 and drawdown <= -0.10:
            return "risk_off"
        if breadth >= 0.62 and above == 1:
            return "risk_on"
        return "neutral"
    if above == 0 and drawdown <= -0.10 and breadth <= 0.40:
        return "risk_off"
    if above == 1 and drawdown >= -0.08 and breadth >= 0.55:
        return "risk_on"
    return "neutral"


def target_exposure_for_regime(regime: str) -> float:
    if regime == "risk_on":
        return 1.0
    if regime == "neutral":
        return 0.4
    return 0.0


def compute_defensive_score(frame: pd.DataFrame, industry_neutral: bool) -> pd.DataFrame:
    out = frame.copy()
    if industry_neutral:
        risk1 = -group_zscore(out, "industry", "volatility_63")
        risk2 = -group_zscore(out, "industry", "volatility_126")
        value = group_zscore(out, "industry", "ep")
    else:
        risk1 = -zscore(winsorize_series(out["volatility_63"]))
        risk2 = -zscore(winsorize_series(out["volatility_126"]))
        value = zscore(winsorize_series(out["ep"]))
    risk3 = -zscore(winsorize_series(out["beta_126"]))
    risk4 = zscore(winsorize_series(out["drawdown_126"]))
    dividend = zscore(winsorize_series(out["dv_ttm"]))
    quality = (
        0.35 * zscore(winsorize_series(out["roe_dt"]))
        + 0.25 * zscore(winsorize_series(out["grossprofit_margin"]))
        + 0.25 * zscore(winsorize_series(out["ocf_to_or"]))
        - 0.15 * zscore(winsorize_series(out["debt_to_assets"]))
    )
    momentum = 0.4 * zscore(winsorize_series(out["ret_21"])) + 0.6 * zscore(winsorize_series(out["ret_63"]))
    out["defensive_score"] = 0.35 * (0.30 * risk1 + 0.30 * risk2 + 0.20 * risk3 + 0.20 * risk4) + 0.25 * dividend + 0.20 * quality + 0.10 * value + 0.10 * momentum
    return out


def build_signal_panel(base_panel: pd.DataFrame, case: dict) -> pd.DataFrame:
    enriched = compute_defensive_score(base_panel, industry_neutral=case["industry_neutral"])
    enriched["regime"] = enriched.apply(lambda row: classify_regime(row, case["name"]), axis=1)
    base = (
        enriched["is_eligible"].fillna(False)
        & (enriched["hot_money_risk_hits"].fillna(99) < 2)
        & (enriched["recent_limit_down_20"].fillna(0) == 0)
        & (pd.to_numeric(enriched["ret_21"], errors="coerce") > -0.18)
        & (pd.to_numeric(enriched["ret_63"], errors="coerce") > -0.35)
        & (pd.to_numeric(enriched["pb"], errors="coerce") > 0)
        & (pd.to_numeric(enriched["ep"], errors="coerce") > 0)
        & (pd.to_numeric(enriched["dv_ttm"], errors="coerce") > 0)
        & pd.to_numeric(enriched["volatility_126"], errors="coerce").notna()
        & pd.to_numeric(enriched["beta_126"], errors="coerce").notna()
        & pd.to_numeric(enriched["roe_dt"], errors="coerce").notna()
    )
    if case["quality_trap"]:
        base = base & ~quality_trap_mask(enriched).fillna(False)
    base = base & (pd.to_numeric(enriched["net_mf_amount"], errors="coerce") > enriched["net_mf_amount"].quantile(0.2))
    enriched["candidate"] = base
    return enriched


def run_backtest(signal_panel: pd.DataFrame, max_holdings: int, max_per_industry: int | None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
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
    industry_peak = 0.0

    for i, date in enumerate(dates):
        day = by_date[date]
        month_start = i > 0 and pd.Timestamp(date).month != pd.Timestamp(dates[i - 1]).month
        if month_start:
            signal = by_date[dates[i - 1]]
            regime = str(signal["regime"].iloc[0]) if "regime" in signal.columns and not signal.empty else "neutral"
            target_exposure = target_exposure_for_regime(regime)
            candidates = signal[signal["candidate"].fillna(False)].copy()
            allowed_holdings = max(0, int(round(max_holdings * target_exposure)))
            if target_exposure <= 0:
                selected = pd.DataFrame(columns=candidates.columns)
            elif max_per_industry is None:
                selected = candidates.sort_values("defensive_score", ascending=False).head(max(allowed_holdings, 1))
            else:
                selected = select_with_industry_cap(candidates, max_holdings=max(allowed_holdings, 1), max_per_industry=max_per_industry)
            target_codes = list(selected["ts_code"])
            target_set = set(target_codes)

            for code in list(holdings):
                if code not in target_set and code in day.index:
                    row = day.loc[code]
                    price = float(row["open"]) if float(row.get("open", np.nan)) > 0 else np.nan
                    if np.isfinite(price):
                        shares = holdings[code]["shares"]
                        amount = price * shares
                        cash += amount - calc_commission(amount, is_buy=False)
                        trades.append({"date": str(date)[:10], "ts_code": code, "action": "sell", "price": price, "shares": shares, "reason": "rebalance"})
                        del holdings[code]

            target_amount = cash / max(max(len(target_codes), 1) - len(holdings), 1) if target_codes else 0.0
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
                holdings[code] = {"shares": shares, "last_price": price, "industry": row.get("industry", "UNKNOWN")}
                trades.append({"date": str(date)[:10], "ts_code": code, "action": "buy", "price": price, "shares": shares, "reason": regime})

        nav = cash
        industry_value: dict[str, float] = {}
        for code, pos in holdings.items():
            if code in day.index and float(day.loc[code].get("close", np.nan)) > 0:
                pos["last_price"] = float(day.loc[code]["close"])
            value = pos["last_price"] * pos["shares"]
            nav += value
            industry = pos.get("industry", "UNKNOWN")
            industry_value[industry] = industry_value.get(industry, 0.0) + value
        if nav > 0 and industry_value:
            industry_peak = max(industry_peak, max(industry_value.values()) / nav)
        day_regime = str(day["regime"].iloc[0]) if "regime" in day.columns and not day.empty else "neutral"
        nav_rows.append({"date": str(date)[:10], "nav": nav, "cash": cash, "holdings": len(holdings), "industry_peak": industry_peak, "regime": day_regime})

    nav_df = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    stats = summarize_nav(nav_df, trades_df)
    stats["max_industry_weight_pct"] = round(float(industry_peak * 100.0), 2)
    return nav_df, trades_df, stats


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
        if freq == "Y":
            data["period"] = data["date"].dt.strftime("%Y")
        else:
            data["period"] = data["date"].dt.strftime("%Y-%m")
        previous_end = None
        for period, group in data.groupby("period", sort=True):
            first_nav = previous_end if previous_end is not None else float(group["nav"].iloc[0])
            last_nav = float(group["nav"].iloc[-1])
            previous_end = last_nav
            rows.append({"period": period, "strategy": name, "return_pct": round((last_nav / first_nav - 1.0) * 100.0, 2)})
    if not rows:
        return pd.DataFrame(columns=["period"])
    table = pd.DataFrame(rows).pivot(index="period", columns="strategy", values="return_pct").reset_index()
    table.columns.name = None
    return table


def render_report(compare: pd.DataFrame, case_results: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame, notes: str):
    def table(df: pd.DataFrame) -> str:
        if df.empty:
            return "<p>无数据</p>"
        head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
        body = []
        for _, row in df.iterrows():
            cells = "".join(f"<td>{html.escape('' if pd.isna(v) else str(v))}</td>" for v in row.tolist())
            body.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"

    text = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>2018 熊市状态机实验</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 16px; background: #f6f8fb; color: #222; }}
h1,h2 {{ margin: 8px 0; }}
.note {{ background: #fff; border: 1px solid #d8dee9; padding: 10px 12px; margin: 12px 0; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; margin: 12px 0; font-size: 13px; }}
th,td {{ border: 1px solid #d8dee9; padding: 6px 8px; text-align: right; white-space: nowrap; }}
th:first-child,td:first-child {{ text-align: left; }}
.scroll {{ overflow: auto; max-height: 520px; }}
</style></head><body>
<h1>2018 熊市状态机实验</h1>
<div class="note">本轮将熊市状态机放到主逻辑：risk_on / neutral / risk_off 三态切换，防御股票池只作为底仓选择器。</div>
<h2>变体结果</h2><div class="scroll">{table(case_results)}</div>
<h2>和 v4/v5/v6 对比</h2><div class="scroll">{table(compare)}</div>
<h2>年度对比</h2><div class="scroll">{table(yearly)}</div>
<h2>2018 月度对比</h2><div class="scroll">{table(monthly)}</div>
<h2>建议</h2><div class="note"><pre>{html.escape(notes)}</pre></div>
</body></html>"""
    REPORT_PATH.write_text(text, encoding="utf-8")


def open_report():
    subprocess.run(
        ["C:\\Program Files\\PowerShell\\7\\pwsh.exe", "-Command", f"Start-Process -FilePath (Resolve-Path '{REPORT_PATH}') -WindowStyle Hidden"],
        check=True,
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text("# tmp_v6 2018 熊市状态机实验进度\n\n", encoding="utf-8")
    append_progress("开始：加载数据与基线。")

    import sys
    sys.path.insert(0, str(V6_DIR))
    import config as v6_config  # type: ignore

    v6_summary, v6_nav, v6_trades, panel, market = load_v6_baselines()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    panel = panel[(panel["trade_date"] >= "2017-01-01") & (panel["trade_date"] <= "2018-12-31")].copy()
    market = market[(market["trade_date"] >= "2017-01-01") & (market["trade_date"] <= "2018-12-31")].copy()
    append_progress(f"裁剪实验面板到 2017-2018：rows={len(panel)} codes={panel['ts_code'].nunique()}")
    daily_basic, fina, stock_basic, moneyflow, hsgt = load_support_data(v6_config.DB_URL, v6_config.SCHEMA, str(panel["trade_date"].min().date()), str(panel["trade_date"].max().date()))
    append_progress("完成 daily_basic/fina_indicator/stock_basic/moneyflow/hsgt 加载。")

    prev_results = pd.read_csv(PREV_RESULTS_PATH)
    prev_best_name = str(prev_results.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).iloc[0]["case"])
    prev_nav = pd.read_csv(TMP_DIR / "tmp_v6_2018_bear_defensive_evolution_output" / f"{prev_best_name}_nav.csv")
    prev_trades = pd.read_csv(TMP_DIR / "tmp_v6_2018_bear_defensive_evolution_output" / f"{prev_best_name}_trades.csv")

    base_panel = build_base_panel(panel, market, daily_basic, fina, stock_basic, moneyflow, hsgt)
    append_progress("完成含状态机特征的基础面板构建。")

    case_rows = []
    nav_map = {"v4": pd.read_csv(BACKTRADER_DIR / "v4" / "output" / "nav_series.csv"), "v5": pd.read_csv(BACKTRADER_DIR / "v5" / "output" / "nav_series.csv"), "v6": v6_nav, prev_best_name: prev_nav}
    trade_map = {"v4": pd.read_csv(BACKTRADER_DIR / "v4" / "output" / "trade_records.csv"), "v5": pd.read_csv(BACKTRADER_DIR / "v5" / "output" / "trade_records.csv"), "v6": v6_trades, prev_best_name: prev_trades}
    best_case_name = None
    best_case_return = -1e18

    for case in CASES:
        append_progress(f"开始 case={case['name']}")
        signal_panel = build_signal_panel(base_panel, case)
        nav, trades, stats = run_backtest(signal_panel, max_holdings=case["max_holdings"], max_per_industry=case["max_per_industry"])
        nav.to_csv(OUTPUT_DIR / f"{case['name']}_nav.csv", index=False)
        trades.to_csv(OUTPUT_DIR / f"{case['name']}_trades.csv", index=False)
        row = {"case": case["name"], **stats}
        case_rows.append(row)
        nav_map[case["name"]] = nav
        trade_map[case["name"]] = trades
        if row["total_return_pct"] > best_case_return:
            best_case_return = row["total_return_pct"]
            best_case_name = case["name"]
        append_progress(f"完成 case={case['name']} total={row['total_return_pct']:.2f}% max_dd={row['max_drawdown_pct']:.2f}% max_industry={row['max_industry_weight_pct']:.2f}%")

    case_results = pd.DataFrame(case_rows).sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).reset_index(drop=True)
    case_results.to_csv(RESULTS_PATH, index=False, encoding="utf-8-sig")

    compare_rows = []
    for name in ["v4", "v5", "v6", prev_best_name, best_case_name]:
        stats = summarize_nav(slice_2018(nav_map[name]), slice_trades_2018(trade_map[name]))
        compare_rows.append({"strategy": name, **stats})
    compare = pd.DataFrame(compare_rows)

    yearly = period_return_table(nav_map, "Y")
    monthly = period_return_table({k: slice_2018(v) for k, v in nav_map.items() if k in ["v4", "v5", "v6", prev_best_name, best_case_name]}, "M")
    monthly = monthly[monthly["period"].astype(str).str.startswith("2018-")].reset_index(drop=True)

    best_row = case_results.iloc[0]
    merge_advice = "建议继续研究" if float(best_row["total_return_pct"]) > -23.976 else "不建议合并"
    notes = (
        "研究复核结论：2018 熊市更该优先验证仓位开关，而不是继续微调单一 long-only 因子。\n"
        "代码/数据说明：状态机主信号使用指数趋势、指数回撤、市场广度、北向资金强弱；行业仍使用 stock_basic.industry。\n"
        f"上一轮最佳 case: {prev_best_name}。\n"
        f"当前最佳 case: {best_row['case']}，2018 收益 {best_row['total_return_pct']:.2f}%，最大回撤 {best_row['max_drawdown_pct']:.2f}%，最大行业占比 {best_row['max_industry_weight_pct']:.2f}%。\n"
        f"建议：{merge_advice}。\n"
        "限制：北向/资金流是弱确认信号；2018 年单年验证仍有限；停牌估值仍偏乐观。\n"
        "下一步：若状态机优于上一轮独立 long-only，则继续做更稳健的 risk_off/试探仓版本；若仍不如 v6，则下一步应转向市场中性或 CTA 原型。"
    )
    render_report(compare, case_results, yearly, monthly, notes)
    open_report()
    append_progress(f"完成报告并自动打开：{REPORT_PATH}")


if __name__ == "__main__":
    main()

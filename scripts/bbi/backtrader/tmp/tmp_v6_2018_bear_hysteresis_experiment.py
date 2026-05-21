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
OUTPUT_DIR = TMP_DIR / "tmp_v6_2018_bear_hysteresis_experiment_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
RESULTS_PATH = OUTPUT_DIR / "results.csv"
README_PATH = TMP_DIR / "tmp_v6_2018_bear_hysteresis_experiment_README.md"
DAILY_PATH = OUTPUT_DIR / "daily_regime_diagnostics.csv"
MONTHLY_EXPOSURE_PATH = OUTPUT_DIR / "monthly_exposure_summary.csv"
MONTHLY_ASSET_PATH = OUTPUT_DIR / "monthly_asset_summary.csv"
SWITCH_PATH = OUTPUT_DIR / "regime_switches.csv"
DESIGN_PATH = TMP_DIR / "tmp_v6_2018_bear_hysteresis_experiment_design.md"
PLAN_PATH = TMP_DIR / "tmp_v6_2018_bear_hysteresis_experiment_plan.md"

INIT_CASH = 500_000.0
COMMISSION_BUY = 0.0005
COMMISSION_SELL = 0.0015
MIN_COMMISSION = 5.0
START_DATE = pd.Timestamp("2018-01-01")
END_DATE = pd.Timestamp("2018-12-31")
EVAL_PERIODS = {
    "2018": ("2018-01-01", "2018-12-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2023": ("2023-01-01", "2023-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
}

CASES = [
    {"name": "hysteresis_base", "reentry_confirm_days": 3, "full_confirm_days": 5, "cooldown_days": 5, "max_holdings": 20, "max_per_industry": 3},
    {"name": "hysteresis_fast_reentry", "reentry_confirm_days": 2, "full_confirm_days": 4, "cooldown_days": 3, "max_holdings": 20, "max_per_industry": 3},
    {"name": "hysteresis_strict", "reentry_confirm_days": 4, "full_confirm_days": 6, "cooldown_days": 5, "max_holdings": 20, "max_per_industry": 3},
]


def append_progress(message: str) -> None:
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def write_static_docs() -> None:
    DESIGN_PATH.write_text(
        "# 2018 熊市空仓滞回实验设计\n\n"
        "- 目标：只改仓位门控，不同时改选股框架，验证空仓退出与再入场滞回是否比上一版状态机更有效。\n"
        "- 主信号：趋势、120日回撤、广度，不把北向资金作为主开关。\n"
        "- 关键修正：risk_off 日频退出；re-entry 需要连续确认；仓位采用 0/20/50/100 阶梯。\n"
        "- 输出：逐日状态、目标/实际仓位、月均仓位、状态切换点、月度收益与 v4/v5/v6 对比。\n",
        encoding="utf-8",
    )
    PLAN_PATH.write_text(
        "# 2018 熊市空仓滞回实验计划\n\n"
        "1. 写测试：风险分数、基础仓位映射、滞回再入场、状态汇总。\n"
        "2. 实现市场状态特征与滞回规则。\n"
        "3. 实现日频 risk_off 卖出 + 月频/日频受控再建仓。\n"
        "4. 生成逐日诊断、月均仓位、状态切换和 HTML 报表。\n"
        "5. 跑测试与 2018 回测，对比 v4/v5/v6 和前一轮状态机。\n",
        encoding="utf-8",
    )


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
    return values.clip(lower=valid.quantile(lower), upper=valid.quantile(upper))


def group_zscore(frame: pd.DataFrame, group_col: str, value_col: str) -> pd.Series:
    values = pd.to_numeric(frame[value_col], errors="coerce")
    return frame.groupby(group_col, dropna=False)[value_col].transform(
        lambda s: pd.Series(0.0, index=s.index) if (pd.isna(pd.to_numeric(s, errors="coerce").std(ddof=0)) or pd.to_numeric(s, errors="coerce").std(ddof=0) == 0)
        else (pd.to_numeric(s, errors="coerce") - pd.to_numeric(s, errors="coerce").mean()) / pd.to_numeric(s, errors="coerce").std(ddof=0)
    )


def group_zscore_by_date(frame: pd.DataFrame, group_col: str, value_col: str) -> pd.Series:
    out = pd.Series(index=frame.index, dtype=float)
    for _, day in frame.groupby("trade_date", sort=False):
        out.loc[day.index] = group_zscore(day, group_col, value_col)
    return out


def calc_commission(amount: float, is_buy: bool) -> float:
    return max(abs(amount) * (COMMISSION_BUY if is_buy else COMMISSION_SELL), MIN_COMMISSION)


def safe_float(value, default=float("nan")) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def get_open_price(row: pd.Series):
    price = safe_float(row.get("open"))
    return price if price > 0 else None


def is_limit_up_at_open(row: pd.Series) -> bool:
    price = safe_float(row.get("open"))
    up_limit = safe_float(row.get("up_limit"))
    return not pd.isna(price) and not pd.isna(up_limit) and up_limit > 0 and price >= up_limit - 1e-6


def is_limit_down_at_open(row: pd.Series) -> bool:
    price = safe_float(row.get("open"))
    down_limit = safe_float(row.get("down_limit"))
    return not pd.isna(price) and not pd.isna(down_limit) and down_limit > 0 and price <= down_limit + 1e-6


def can_buy(row: pd.Series) -> tuple[bool, str]:
    if bool(row.get("is_suspended", False)):
        return False, "suspended"
    if is_limit_up_at_open(row):
        return False, "limit_up"
    if get_open_price(row) is None:
        return False, "missing_open"
    return True, ""


def can_sell(row: pd.Series) -> tuple[bool, str]:
    if bool(row.get("is_suspended", False)):
        return False, "suspended"
    if is_limit_down_at_open(row):
        return False, "limit_down"
    if get_open_price(row) is None:
        return False, "missing_open"
    return True, ""


def apply_adj_factor(pos: dict, row: pd.Series) -> None:
    current = safe_float(row.get("adj_factor"))
    previous = safe_float(pos.get("last_adj_factor"))
    if pd.isna(current) or current <= 0:
        return
    if pd.isna(previous) or previous <= 0:
        pos["last_adj_factor"] = current
        return
    if abs(current - previous) < 1e-12:
        return
    ratio = current / previous
    if ratio <= 0 or pd.isna(ratio):
        return
    pos["shares"] *= ratio
    pos["cost_price"] /= ratio
    pos["last_adj_factor"] = current


def select_with_industry_cap(frame: pd.DataFrame, max_holdings: int, max_per_industry: int | None) -> pd.DataFrame:
    ranked = frame.sort_values("defensive_score", ascending=False).reset_index(drop=True)
    if max_per_industry is None:
        return ranked.head(max_holdings).copy()
    selected = []
    counts: dict[str, int] = {}
    for _, row in ranked.iterrows():
        industry = row.get("industry")
        key = "UNKNOWN" if pd.isna(industry) or industry in ("", "None", None) else str(industry)
        if counts.get(key, 0) >= max_per_industry:
            continue
        selected.append(row.to_dict())
        counts[key] = counts.get(key, 0) + 1
        if len(selected) >= max_holdings:
            break
    return pd.DataFrame(selected)


def load_v6_baselines():
    output = V6_DIR / "output"
    return (
        json.loads((output / "summary.json").read_text(encoding="utf-8")),
        pd.read_csv(output / "nav_series.csv"),
        pd.read_csv(output / "trade_records.csv"),
        pd.read_parquet(output / "panel.parquet"),
        pd.read_parquet(output / "market_index.parquet"),
    )


def load_other_navs() -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(BACKTRADER_DIR / name / "output" / "nav_series.csv") for name in ["v4", "v5"]}


def load_other_trades() -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(BACKTRADER_DIR / name / "output" / "trade_records.csv") for name in ["v4", "v5"]}


def load_support_data(db_url: str, schema: str, start_date: str, end_date: str):
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
        stock_basic = pd.read_sql_query(text(f"""select ts_code, industry from {schema}."001_stock_basic" """), conn)
    return daily_basic, fina, stock_basic


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


def build_regime_features(panel: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    market_frame = market.copy()
    market_frame["trade_date"] = pd.to_datetime(market_frame["trade_date"])
    market_frame = market_frame.sort_values("trade_date")
    close = pd.to_numeric(market_frame["close"], errors="coerce")
    market_frame["ma20"] = close.rolling(20, min_periods=15).mean()
    market_frame["ma60"] = close.rolling(60, min_periods=40).mean()
    market_frame["ma120"] = close.rolling(120, min_periods=80).mean()
    market_frame["ma200"] = close.rolling(200, min_periods=120).mean()
    market_frame["ma60_slope_20"] = market_frame["ma60"] / market_frame["ma60"].shift(20) - 1.0
    market_frame["market_drawdown_120"] = close / close.rolling(120, min_periods=60).max() - 1.0
    market_frame["close_below_ma120"] = (close < market_frame["ma120"]).astype(int)
    market_frame["close_below_ma200"] = (close < market_frame["ma200"]).astype(int)
    market_frame["ma20_above_ma60"] = (market_frame["ma20"] > market_frame["ma60"]).astype(int)

    breadth = out[["trade_date", "ts_code", "close_qfq"]].copy()
    breadth["ma20_stock"] = breadth.groupby("ts_code", sort=False)["close_qfq"].transform(lambda s: s.rolling(20, min_periods=15).mean())
    breadth["ma60_stock"] = breadth.groupby("ts_code", sort=False)["close_qfq"].transform(lambda s: s.rolling(60, min_periods=40).mean())
    breadth["above_ma20"] = (pd.to_numeric(breadth["close_qfq"], errors="coerce") > pd.to_numeric(breadth["ma20_stock"], errors="coerce")).astype(float)
    breadth["above_ma60"] = (pd.to_numeric(breadth["close_qfq"], errors="coerce") > pd.to_numeric(breadth["ma60_stock"], errors="coerce")).astype(float)
    breadth_daily = breadth.groupby("trade_date", sort=True).agg(
        breadth_above_ma20=("above_ma20", "mean"),
        breadth_above_ma60=("above_ma60", "mean"),
    ).reset_index()

    regime = market_frame[
        [
            "trade_date",
            "market_drawdown_120",
            "close_below_ma120",
            "close_below_ma200",
            "ma20_above_ma60",
            "ma60_slope_20",
        ]
    ].merge(breadth_daily, on="trade_date", how="left")
    regime["breadth_above_ma20"] = regime["breadth_above_ma20"].fillna(0.0)
    regime["breadth_above_ma60"] = regime["breadth_above_ma60"].fillna(0.0)
    return out.merge(regime, on="trade_date", how="left")


def build_base_panel(panel: pd.DataFrame, market: pd.DataFrame, daily_basic: pd.DataFrame, fina: pd.DataFrame, stock_basic: pd.DataFrame) -> pd.DataFrame:
    enriched = add_market_features(panel, market)
    daily = daily_basic.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    enriched = enriched.merge(daily[["ts_code", "trade_date", "dv_ttm", "pb", "pe_ttm"]], on=["ts_code", "trade_date"], how="left")
    enriched = merge_financial_features(enriched, fina)
    enriched = build_regime_features(enriched, market)
    enriched = enriched.merge(stock_basic[["ts_code", "industry"]], on="ts_code", how="left")
    enriched["industry"] = enriched["industry"].fillna("UNKNOWN")
    pe = pd.to_numeric(enriched["pe_ttm"], errors="coerce")
    enriched["ep"] = np.where(pe > 0, 1.0 / pe, np.nan)
    return enriched


def quality_trap_mask(frame: pd.DataFrame) -> pd.Series:
    dv = pd.to_numeric(frame["dv_ttm"], errors="coerce")
    roe = pd.to_numeric(frame["roe_dt"], errors="coerce")
    ocf = pd.to_numeric(frame["ocf_to_or"], errors="coerce")
    debt = pd.to_numeric(frame["debt_to_assets"], errors="coerce")
    return (dv >= dv.quantile(0.7)) & ((roe <= 3.0) | (ocf <= 0.0) | (debt >= 75.0))


def compute_defensive_score(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    risk1 = -group_zscore_by_date(out, "industry", "volatility_126")
    risk2 = out.groupby("trade_date", sort=False)["beta_126"].transform(lambda s: -zscore(winsorize_series(s)))
    risk3 = out.groupby("trade_date", sort=False)["drawdown_126"].transform(lambda s: zscore(winsorize_series(s)))
    dividend = out.groupby("trade_date", sort=False)["dv_ttm"].transform(lambda s: zscore(winsorize_series(s)))
    value = group_zscore_by_date(out, "industry", "ep")
    quality = (
        0.35 * out.groupby("trade_date", sort=False)["roe_dt"].transform(lambda s: zscore(winsorize_series(s)))
        + 0.25 * out.groupby("trade_date", sort=False)["grossprofit_margin"].transform(lambda s: zscore(winsorize_series(s)))
        + 0.25 * out.groupby("trade_date", sort=False)["ocf_to_or"].transform(lambda s: zscore(winsorize_series(s)))
        - 0.15 * out.groupby("trade_date", sort=False)["debt_to_assets"].transform(lambda s: zscore(winsorize_series(s)))
    )
    momentum = (
        0.4 * out.groupby("trade_date", sort=False)["ret_21"].transform(lambda s: zscore(winsorize_series(s)))
        + 0.6 * out.groupby("trade_date", sort=False)["ret_63"].transform(lambda s: zscore(winsorize_series(s)))
    )
    out["defensive_score"] = 0.35 * (0.40 * risk1 + 0.30 * risk2 + 0.30 * risk3) + 0.25 * dividend + 0.20 * quality + 0.10 * value + 0.10 * momentum
    return out


def compute_target_budget(target_exposure: float, cash: float, current_holdings_value_at_open: float) -> float:
    total_nav_at_open = float(cash) + float(current_holdings_value_at_open)
    return min(float(cash), total_nav_at_open * float(target_exposure))


def build_signal_panel(base_panel: pd.DataFrame) -> pd.DataFrame:
    enriched = compute_defensive_score(base_panel)
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
    base = base & ~quality_trap_mask(enriched).fillna(False)
    enriched["candidate"] = base
    return enriched


def compute_risk_points(row: pd.Series) -> int:
    points = 0
    if int(row.get("close_below_ma120", 0)) == 1:
        points += 1
    if float(row.get("ma60_slope_20", 0.0)) < 0:
        points += 1
    dd = float(row.get("market_drawdown_120", 0.0))
    if dd <= -0.10:
        points += 1
    if dd <= -0.15:
        points += 1
    if float(row.get("breadth_above_ma20", 0.0)) < 0.35:
        points += 1
    if float(row.get("breadth_above_ma60", 0.0)) < 0.30:
        points += 1
    return points


def base_target_exposure_from_row(row: pd.Series) -> float:
    dd = float(row.get("market_drawdown_120", 0.0))
    b20 = float(row.get("breadth_above_ma20", 0.0))
    b60 = float(row.get("breadth_above_ma60", 0.0))
    below120 = int(row.get("close_below_ma120", 0))
    below200 = int(row.get("close_below_ma200", 0))
    ma20_above_ma60 = int(row.get("ma20_above_ma60", 0))
    slope60 = float(row.get("ma60_slope_20", 0.0))
    if dd <= -0.20 or (below120 == 1 and b20 < 0.25) or (below200 == 1 and b60 < 0.25):
        return 0.0
    if dd <= -0.15 or (below120 == 1 and b20 < 0.35):
        return 0.2
    if dd > -0.10 and below120 == 0 and ma20_above_ma60 == 1 and b20 > 0.50 and b60 > 0.40 and slope60 > 0:
        return 1.0
    return 0.5


def apply_hysteresis(regime_frame: pd.DataFrame, reentry_confirm_days: int, full_confirm_days: int, cooldown_days: int) -> pd.DataFrame:
    out = regime_frame.copy().sort_values("trade_date").reset_index(drop=True)
    exposures = []
    reentry_streak = 0
    full_streak = 0
    cooldown = 0
    current = 1.0
    for _, row in out.iterrows():
        base_target = float(row["base_target_exposure"])
        if base_target <= 0:
            current = 0.0
            reentry_streak = 0
            full_streak = 0
            cooldown = 0
        elif current <= 0:
            if base_target >= 0.2 and float(row.get("breadth_above_ma20", 0.0)) > 0.35:
                reentry_streak += 1
            else:
                reentry_streak = 0
            if reentry_streak >= reentry_confirm_days:
                current = 0.2
                cooldown = cooldown_days
                reentry_streak = 0
        elif base_target <= 0.2:
            current = min(current, 0.2)
            reentry_streak = 0
            full_streak = 0
            cooldown = 0
        else:
            if current <= 0.2:
                if cooldown > 0:
                    cooldown -= 1
                if base_target >= 0.5 and float(row.get("market_drawdown_120", 0.0)) > -0.15 and float(row.get("breadth_above_ma20", 0.0)) > 0.40:
                    reentry_streak += 1
                else:
                    reentry_streak = 0
                if cooldown <= 0 and reentry_streak >= reentry_confirm_days:
                    current = 0.5
                    cooldown = cooldown_days
                    reentry_streak = 0
                    full_streak = 0
            elif current <= 0.5:
                if cooldown > 0:
                    cooldown -= 1
                if base_target >= 1.0:
                    full_streak += 1
                else:
                    full_streak = 0
                if cooldown <= 0 and full_streak >= full_confirm_days:
                    current = 1.0
        exposures.append(current)
    out["target_exposure"] = exposures
    out["risk_points"] = out.apply(compute_risk_points, axis=1)
    return out


def summarize_regime_path(regime_frame: pd.DataFrame) -> dict:
    data = regime_frame.copy()
    target = pd.to_numeric(data["target_exposure"], errors="coerce").fillna(0.0)
    prev = target.shift(1)
    switches = int((target != prev).fillna(False).sum() - 1) if len(target) else 0
    return {
        "switch_count": max(switches, 0),
        "risk_off_days": int((target <= 0.0).sum()),
        "probe_days": int((target == 0.2).sum()),
        "neutral_days": int((target == 0.5).sum()),
        "risk_on_days": int((target >= 1.0).sum()),
    }


def build_market_regime_table(signal_panel: pd.DataFrame, case: dict) -> pd.DataFrame:
    regime_cols = [
        "trade_date",
        "market_drawdown_120",
        "breadth_above_ma20",
        "breadth_above_ma60",
        "close_below_ma120",
        "close_below_ma200",
        "ma20_above_ma60",
        "ma60_slope_20",
    ]
    regime = signal_panel[regime_cols].drop_duplicates(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    regime["base_target_exposure"] = regime.apply(base_target_exposure_from_row, axis=1)
    regime = apply_hysteresis(
        regime,
        reentry_confirm_days=int(case["reentry_confirm_days"]),
        full_confirm_days=int(case["full_confirm_days"]),
        cooldown_days=int(case["cooldown_days"]),
    )
    return regime


def run_backtest(signal_panel: pd.DataFrame, regime_table: pd.DataFrame, max_holdings: int, max_per_industry: int | None):
    panel = signal_panel.copy()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[(panel["trade_date"] >= START_DATE) & (panel["trade_date"] <= END_DATE)].copy()
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    regime_map = regime_table.set_index("trade_date")
    dates = sorted(panel["trade_date"].unique())
    by_date = {d: g.set_index("ts_code", drop=False) for d, g in panel.groupby("trade_date", sort=True)}
    cash = INIT_CASH
    holdings: dict[str, dict] = {}
    trades = []
    nav_rows = []
    industry_peak = 0.0
    last_target_codes: set[str] = set()
    last_target_exposure = 0.0

    for i, date in enumerate(dates):
        day = by_date[date]
        prev_signal_date = dates[i - 1] if i > 0 else None
        if prev_signal_date is not None:
            target_row = regime_map.loc[pd.Timestamp(prev_signal_date)]
            target_exposure = float(target_row["target_exposure"])
            risk_off_now = target_exposure <= 0.0
            if risk_off_now:
                for code in list(holdings):
                    if code not in day.index:
                        continue
                    row = day.loc[code]
                    apply_adj_factor(holdings[code], row)
                    ok, _ = can_sell(row)
                    price = get_open_price(row)
                    if ok and price is not None:
                        shares = holdings[code]["shares"]
                        amount = price * shares
                        cash += amount - calc_commission(amount, is_buy=False)
                        trades.append({"date": str(date)[:10], "ts_code": code, "action": "sell", "price": price, "shares": shares, "reason": "risk_off_exit"})
                        del holdings[code]
                last_target_codes = set()
                last_target_exposure = 0.0
            else:
                month_start = pd.Timestamp(date).month != pd.Timestamp(prev_signal_date).month
                exposure_step_up = target_exposure > last_target_exposure + 1e-9
                need_rebuild = month_start or exposure_step_up
                signal = by_date[prev_signal_date]
                if need_rebuild:
                    candidates = signal[signal["candidate"].fillna(False)].copy()
                    allowed_holdings = max(0, int(round(max_holdings * target_exposure)))
                    if allowed_holdings <= 0:
                        selected = pd.DataFrame(columns=candidates.columns)
                    else:
                        selected = select_with_industry_cap(candidates, max_holdings=max(allowed_holdings, 1), max_per_industry=max_per_industry)
                    target_codes = set(selected["ts_code"].tolist())
                    pre_rebuild_value = cash
                    for code, pos in holdings.items():
                        if code in day.index and float(day.loc[code].get("open", np.nan)) > 0:
                            apply_adj_factor(pos, day.loc[code])
                            pre_rebuild_value += float(day.loc[code]["open"]) * pos["shares"]
                        else:
                            pre_rebuild_value += float(pos.get("last_price", 0.0)) * pos["shares"]
                    for code in list(holdings):
                        if code not in day.index:
                            continue
                        row = day.loc[code]
                        apply_adj_factor(holdings[code], row)
                        ok, _ = can_sell(row)
                        price = get_open_price(row)
                        if ok and price is not None:
                            shares = holdings[code]["shares"]
                            amount = price * shares
                            cash += amount - calc_commission(amount, is_buy=False)
                            trades.append({"date": str(date)[:10], "ts_code": code, "action": "sell", "price": price, "shares": shares, "reason": "rebalance"})
                            del holdings[code]
                    target_budget = min(cash, pre_rebuild_value * target_exposure)
                    slots_to_fill = len(target_codes)
                    target_amount = target_budget / slots_to_fill if slots_to_fill else 0.0
                    for code in selected["ts_code"].tolist():
                        if code in holdings or code not in day.index:
                            continue
                        row = day.loc[code]
                        ok, _ = can_buy(row)
                        if not ok:
                            continue
                        price = get_open_price(row)
                        if price is None:
                            continue
                        shares = int(min(target_amount, cash, target_budget) / price / 100) * 100
                        if shares < 100:
                            continue
                        amount = price * shares
                        comm = calc_commission(amount, is_buy=True)
                        if amount + comm > cash or amount + comm > target_budget + 1e-9:
                            continue
                        cash -= amount + comm
                        target_budget -= amount + comm
                        holdings[code] = {
                            "shares": shares,
                            "cost_price": price,
                            "last_price": price,
                            "last_adj_factor": safe_float(row.get("adj_factor"), None),
                            "industry": row.get("industry", "UNKNOWN"),
                        }
                        trades.append({"date": str(date)[:10], "ts_code": code, "action": "buy", "price": price, "shares": shares, "reason": f"target_{target_exposure:.1f}"})
                    last_target_codes = target_codes
                last_target_exposure = target_exposure

        nav = cash
        market_value = 0.0
        industry_value: dict[str, float] = {}
        for code, pos in holdings.items():
            if code in day.index and float(day.loc[code].get("close", np.nan)) > 0:
                apply_adj_factor(pos, day.loc[code])
                pos["last_price"] = float(day.loc[code]["close"])
            value = pos["last_price"] * pos["shares"]
            market_value += value
            nav += value
            industry = pos.get("industry", "UNKNOWN")
            industry_value[industry] = industry_value.get(industry, 0.0) + value
        if nav > 0 and industry_value:
            industry_peak = max(industry_peak, max(industry_value.values()) / nav)
        signal_target = float(regime_map.loc[pd.Timestamp(date)]["target_exposure"]) if pd.Timestamp(date) in regime_map.index else 0.0
        nav_rows.append(
            {
                "date": str(date)[:10],
                "nav": nav,
                "cash": cash,
                "holdings": len(holdings),
                "target_exposure": signal_target,
                "actual_exposure": market_value / nav if nav > 0 else 0.0,
                "base_target_exposure": float(regime_map.loc[pd.Timestamp(date)]["base_target_exposure"]) if pd.Timestamp(date) in regime_map.index else 0.0,
            }
        )

    nav_df = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    stats = summarize_nav(nav_df, trades_df)
    stats["max_industry_weight_pct"] = round(float(industry_peak * 100.0), 2)
    stats["avg_target_exposure_pct"] = round(float(nav_df["target_exposure"].mean() * 100.0), 2)
    stats["avg_actual_exposure_pct"] = round(float(nav_df["actual_exposure"].mean() * 100.0), 2)
    stats.update(summarize_regime_path(regime_table))
    return nav_df, trades_df, stats


def run_backtest_period(signal_panel: pd.DataFrame, regime_table: pd.DataFrame, start_date: str, end_date: str, max_holdings: int, max_per_industry: int | None):
    global START_DATE, END_DATE
    old_start, old_end = START_DATE, END_DATE
    START_DATE = pd.Timestamp(start_date)
    END_DATE = pd.Timestamp(end_date)
    try:
        return run_backtest(signal_panel, regime_table, max_holdings=max_holdings, max_per_industry=max_per_industry)
    finally:
        START_DATE, END_DATE = old_start, old_end


def summarize_nav(nav: pd.DataFrame, trades: pd.DataFrame | None = None) -> dict:
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


def slice_period(nav: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    out = nav.copy()
    out["date"] = pd.to_datetime(out["date"])
    return out[(out["date"] >= pd.Timestamp(start_date)) & (out["date"] <= pd.Timestamp(end_date))].copy()


def slice_2018(nav: pd.DataFrame) -> pd.DataFrame:
    return slice_period(nav, "2018-01-01", "2018-12-31")


def slice_trades_period(trades: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if trades is None or trades.empty:
        return pd.DataFrame()
    out = trades.copy()
    out["date"] = pd.to_datetime(out["date"])
    return out[(out["date"] >= pd.Timestamp(start_date)) & (out["date"] <= pd.Timestamp(end_date))].copy()


def slice_trades_2018(trades: pd.DataFrame) -> pd.DataFrame:
    return slice_trades_period(trades, "2018-01-01", "2018-12-31")


def period_return_table(nav_map: dict[str, pd.DataFrame], freq: str) -> pd.DataFrame:
    rows = []
    for name, nav in nav_map.items():
        if nav is None or nav.empty:
            continue
        data = nav.copy()
        data["date"] = pd.to_datetime(data["date"])
        data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
        data = data.dropna(subset=["date", "nav"]).sort_values("date")
        data["period"] = data["date"].dt.strftime("%Y" if freq == "Y" else "%Y-%m")
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


def build_monthly_asset_table(daily_diag: pd.DataFrame) -> pd.DataFrame:
    data = daily_diag.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data = data[data["trade_date"].between(START_DATE, END_DATE)].copy()
    data = data.sort_values("trade_date").reset_index(drop=True)
    data["month"] = data["trade_date"].dt.strftime("%Y-%m")
    month_end = data.groupby("month", as_index=False).tail(1).copy()
    month_end = month_end.sort_values("trade_date").reset_index(drop=True)
    month_end["股票市值"] = (pd.to_numeric(month_end["nav"], errors="coerce") - pd.to_numeric(month_end["cash"], errors="coerce")).round(2)
    month_end["股票仓位"] = np.where(
        pd.to_numeric(month_end["nav"], errors="coerce") > 0,
        pd.to_numeric(month_end["股票市值"], errors="coerce") / pd.to_numeric(month_end["nav"], errors="coerce") * 100.0,
        np.nan,
    )
    month_end["现金占比"] = np.where(
        pd.to_numeric(month_end["nav"], errors="coerce") > 0,
        pd.to_numeric(month_end["cash"], errors="coerce") / pd.to_numeric(month_end["nav"], errors="coerce") * 100.0,
        np.nan,
    )
    first_nav = float(pd.to_numeric(data["nav"], errors="coerce").iloc[0])
    prev_month_nav = None
    year_start_nav: dict[int, float] = {}
    year_start_date: dict[int, pd.Timestamp] = {}
    rows = []
    for _, row in month_end.iterrows():
        month = str(row["month"])
        month_nav = float(row["nav"])
        trade_date = pd.Timestamp(row["trade_date"])
        year = int(trade_date.year)
        if year not in year_start_nav:
            first_row_of_year = data[data["trade_date"].dt.year.eq(year)].iloc[0]
            year_start_nav[year] = float(first_row_of_year["nav"])
            year_start_date[year] = pd.Timestamp(first_row_of_year["trade_date"])
        month_pnl = month_nav - (prev_month_nav if prev_month_nav is not None else first_nav)
        month_ret = month_nav / (prev_month_nav if prev_month_nav is not None else first_nav) - 1.0
        total_ret = month_nav / first_nav - 1.0
        ytd_ret = month_nav / year_start_nav[year] - 1.0
        ytd_days = max((trade_date - year_start_date[year]).days, 1)
        annualized = (1.0 + ytd_ret) ** (365.0 / ytd_days) - 1.0 if ytd_ret > -1 else -1.0
        rows.append(
            {
                "月份": month,
                "月末总资产": round(month_nav, 2),
                "股票市值": round(float(row["股票市值"]), 2),
                "现金余额": round(float(row["cash"]), 2),
                "股票仓位": round(float(row["股票仓位"]), 2),
                "现金占比": round(float(row["现金占比"]), 2),
                "当月盈亏(元)": round(month_pnl, 2),
                "当月收益率": round(month_ret * 100.0, 2),
                "总收益率": round(total_ret * 100.0, 2),
                "年内收益率": round(ytd_ret * 100.0, 2),
                "年收益率": round(annualized * 100.0, 2),
            }
        )
        prev_month_nav = month_nav
    return pd.DataFrame(rows)


def render_report(compare: pd.DataFrame, case_results: pd.DataFrame, multi_period_compare: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame, monthly_assets: pd.DataFrame, switches: pd.DataFrame, notes: str):
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
<html lang="zh-CN"><head><meta charset="utf-8"><title>2018 熊市空仓滞回实验</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 16px; background: #f6f8fb; color: #222; }}
h1,h2 {{ margin: 8px 0; }}
.note {{ background: #fff; border: 1px solid #d8dee9; padding: 10px 12px; margin: 12px 0; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; margin: 12px 0; font-size: 13px; }}
th,td {{ border: 1px solid #d8dee9; padding: 6px 8px; text-align: right; white-space: nowrap; }}
th:first-child,td:first-child {{ text-align: left; }}
.scroll {{ overflow: auto; max-height: 520px; }}
</style></head><body>
<h1>2018 熊市空仓滞回实验</h1>
<div class="note">核心修正：risk_off 改为日频退出；再入场采用滞回和连续确认；仓位分 0/20/50/100 四档。选股仍沿用防御候选池，不把北向资金当主开关。</div>
<h2>变体结果</h2><div class="scroll">{table(case_results)}</div>
<h2>和 v4/v5/v6 对比</h2><div class="scroll">{table(compare)}</div>
<h2>多弱市验证</h2><div class="scroll">{table(multi_period_compare)}</div>
<h2>年度对比</h2><div class="scroll">{table(yearly)}</div>
<h2>2018 月度收益对比</h2><div class="scroll">{table(monthly)}</div>
<h2>2018 月度资产表</h2><div class="scroll">{table(monthly_assets)}</div>
<h2>状态切换</h2><div class="scroll">{table(switches)}</div>
<h2>建议</h2><div class="note"><pre>{html.escape(notes)}</pre></div>
</body></html>"""
    REPORT_PATH.write_text(text, encoding="utf-8")


def open_report() -> None:
    subprocess.run(
        ["C:\\Program Files\\PowerShell\\7\\pwsh.exe", "-Command", f"Start-Process -FilePath (Resolve-Path '{REPORT_PATH}') -WindowStyle Hidden"],
        check=True,
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text("# tmp_v6 2018 熊市空仓滞回实验进度\n\n", encoding="utf-8")
    write_static_docs()
    append_progress("开始：加载基线、面板、Tushare 支撑数据。")

    import sys
    sys.path.insert(0, str(V6_DIR))
    import config as v6_config  # type: ignore

    _, v6_nav, v6_trades, panel, market = load_v6_baselines()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    panel = panel[(panel["trade_date"] >= "2017-01-01") & (panel["trade_date"] <= "2024-12-31")].copy()
    market = market[(market["trade_date"] >= "2017-01-01") & (market["trade_date"] <= "2024-12-31")].copy()
    daily_basic, fina, stock_basic = load_support_data(v6_config.DB_URL, v6_config.SCHEMA, str(panel["trade_date"].min().date()), str(panel["trade_date"].max().date()))
    append_progress(f"已裁剪面板 rows={len(panel)} codes={panel['ts_code'].nunique()}，并完成 daily_basic/fina_indicator/stock_basic 加载。")

    signal_panel = build_signal_panel(build_base_panel(panel, market, daily_basic, fina, stock_basic))
    append_progress("完成基础面板、状态机特征和防御候选池构建。")

    other_navs = load_other_navs()
    other_trades = load_other_trades()
    nav_map = {"v4": other_navs["v4"], "v5": other_navs["v5"], "v6": v6_nav}
    trade_map = {"v4": other_trades["v4"], "v5": other_trades["v5"], "v6": v6_trades}
    case_rows = []
    period_rows = []
    best_name = None
    best_ret = -1e18
    best_regime = None
    best_nav = None
    best_trades = None

    for case in CASES:
        append_progress(f"开始 case={case['name']}")
        regime_table = build_market_regime_table(signal_panel, case)
        nav, trades, stats = run_backtest_period(signal_panel, regime_table, "2018-01-01", "2018-12-31", max_holdings=int(case["max_holdings"]), max_per_industry=case["max_per_industry"])
        nav.to_csv(OUTPUT_DIR / f"{case['name']}_nav.csv", index=False)
        trades.to_csv(OUTPUT_DIR / f"{case['name']}_trades.csv", index=False)
        regime_table.to_csv(OUTPUT_DIR / f"{case['name']}_regime.csv", index=False, encoding="utf-8-sig")
        row = {"case": case["name"], **stats}
        case_rows.append(row)
        nav_map[case["name"]] = nav
        trade_map[case["name"]] = trades
        if row["total_return_pct"] > best_ret:
            best_ret = row["total_return_pct"]
            best_name = case["name"]
            best_regime = regime_table
            best_nav = nav
            best_trades = trades
        append_progress(f"完成 case={case['name']} total={row['total_return_pct']:.2f}% max_dd={row['max_drawdown_pct']:.2f}% avg_target={row['avg_target_exposure_pct']:.2f}%")

        for period_name, (period_start, period_end) in EVAL_PERIODS.items():
            period_nav, period_trades, period_stats = run_backtest_period(
                signal_panel,
                regime_table,
                period_start,
                period_end,
                max_holdings=int(case["max_holdings"]),
                max_per_industry=case["max_per_industry"],
            )
            period_nav.to_csv(OUTPUT_DIR / f"{case['name']}_{period_name}_nav.csv", index=False)
            period_trades.to_csv(OUTPUT_DIR / f"{case['name']}_{period_name}_trades.csv", index=False)
            period_rows.append({"case": case["name"], "period": period_name, **period_stats})
            if case["name"] == best_name and period_name == "2018":
                best_nav = period_nav
                best_trades = period_trades

    case_results = pd.DataFrame(case_rows).sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).reset_index(drop=True)
    case_results.to_csv(RESULTS_PATH, index=False, encoding="utf-8-sig")
    period_results = pd.DataFrame(period_rows)
    period_results.to_csv(OUTPUT_DIR / "period_results.csv", index=False, encoding="utf-8-sig")

    compare_rows = []
    for name in ["v4", "v5", "v6", best_name]:
        if name == best_name:
            stats = summarize_nav(best_nav, best_trades)
        else:
            stats = summarize_nav(slice_2018(nav_map[name]), slice_trades_2018(trade_map[name]))
        compare_rows.append({"strategy": name, **stats})
    compare = pd.DataFrame(compare_rows)

    multi_period_compare_rows = []
    for period_name, (period_start, period_end) in EVAL_PERIODS.items():
        for name in ["v4", "v5", "v6"]:
            stats = summarize_nav(slice_period(nav_map[name], period_start, period_end), slice_trades_period(trade_map[name], period_start, period_end))
            multi_period_compare_rows.append({"period": period_name, "strategy": name, **stats})
        best_period = period_results[(period_results["case"].eq(best_name)) & (period_results["period"].eq(period_name))].iloc[0].to_dict()
        multi_period_compare_rows.append({"period": period_name, "strategy": best_name, **{k: v for k, v in best_period.items() if k not in {"case", "period"}}})
    multi_period_compare = pd.DataFrame(multi_period_compare_rows)
    multi_period_compare.to_csv(OUTPUT_DIR / "multi_period_compare.csv", index=False, encoding="utf-8-sig")

    yearly = period_return_table(nav_map, "Y")
    monthly = period_return_table({k: slice_2018(v) for k, v in nav_map.items() if k in ["v4", "v5", "v6"]}, "M")
    monthly_best = period_return_table({best_name: best_nav}, "M")
    if best_name in monthly_best.columns:
        monthly = monthly.merge(monthly_best[["period", best_name]], on="period", how="left")

    nav_diag = nav_map[best_name][["date", "actual_exposure", "nav", "cash", "holdings"]].rename(columns={"date": "trade_date"}).copy()
    nav_diag["trade_date"] = pd.to_datetime(nav_diag["trade_date"])
    daily_diag = pd.merge(
        best_regime.copy(),
        nav_diag,
        on="trade_date",
        how="left",
    )
    daily_diag.to_csv(DAILY_PATH, index=False, encoding="utf-8-sig")
    monthly_assets = build_monthly_asset_table(daily_diag)
    monthly_assets.to_csv(MONTHLY_ASSET_PATH, index=False, encoding="utf-8-sig")

    switch_mask = daily_diag["target_exposure"].ne(daily_diag["target_exposure"].shift(1)).fillna(False)
    switches = daily_diag.loc[switch_mask & daily_diag["trade_date"].between(START_DATE, END_DATE), ["trade_date", "base_target_exposure", "target_exposure", "market_drawdown_120", "breadth_above_ma20", "breadth_above_ma60", "risk_points"]].copy()
    switches.to_csv(SWITCH_PATH, index=False, encoding="utf-8-sig")

    best_row = case_results.iloc[0]
    notes = (
        f"最佳候选：{best_row['case']}，2018 收益 {best_row['total_return_pct']:.2f}%，最大回撤 {best_row['max_drawdown_pct']:.2f}%。\n"
        f"对比 v6：2018 收益 {float(compare.loc[compare['strategy'].eq('v6'), 'total_return_pct'].iloc[0]):.2f}%。\n"
        "判断口径：如果最佳候选仍未明显优于 v6，就不合并；但只要状态切换与仓位诊断更合理，就保留这条研究分支继续优化。\n"
        "下一步优先级：1）检查 2-4 月和 6-8 月的切换点；2）验证 2016/2022 弱市；3）再考虑把 v6 原生交易骨架接上这套仓位门控。"
    )
    multi_period_report = multi_period_compare[
        [
            "period",
            "strategy",
            "total_return_pct",
            "max_drawdown_pct",
            "annual_return_pct",
            "trade_records",
            "buy_trades",
        ]
    ].copy()
    render_report(compare, case_results, multi_period_report, yearly, monthly, monthly_assets, switches, notes)
    open_report()
    append_progress(f"完成报告并自动打开：{REPORT_PATH}")


if __name__ == "__main__":
    main()

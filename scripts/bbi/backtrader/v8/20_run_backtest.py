import argparse
import csv
import json
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from config import (
    BACKTEST_START_DATE,
    BEAR_PROBE_BBI_SLOPE_WINDOW,
    BEAR_PROBE_BREADTH_IMPROVE_5,
    BEAR_PROBE_BUY_ENABLED,
    BEAR_PROBE_MAX_TOTAL_EXPOSURE,
    BEAR_PROBE_MIN_BREADTH,
    BEAR_PROBE_POSITION_FRACTION,
    BULL_EARLY_ENTRY_PULLBACK_THRESHOLD,
    BULL_EARLY_ENTRY_STRONG_PULLBACK_THRESHOLD,
    BULL_ADD_PROFIT_THRESHOLDS,
    COMMISSION_BUY,
    COMMISSION_SELL,
    DB_URL,
    DC_SEGMENT_CRASH_DD_20,
    DC_SEGMENT_CRASH_RET_20,
    DC_SEGMENT_MEMBER_LAG_DAYS,
    DC_SEGMENT_OVERLAY_ACTIVE_FROM,
    DC_SEGMENT_OVERLAY_ENABLED,
    DC_SEGMENT_SCORE_WEIGHT,
    DOWNTREND_BUY_FILTER_ENABLED,
    DOWNTREND_FILTER_NAME,
    INIT_CASH,
    HOT_MONEY_RISK_ENABLED,
    HOT_MONEY_RISK_MIN_HITS,
    KEEP_TOP_N,
    LAST_HOLDINGS_PATH,
    LIMIT_DOWN_EXIT_ENABLED,
    LONG_ADD_PROFIT_THRESHOLDS,
    LONG_BEARISH_AMOUNT_MULTIPLIER,
    LONG_BEARISH_CLOSE_LOW_POSITION,
    LONG_BEARISH_DROP_THRESHOLD,
    LONG_MAX_HOLDINGS,
    LONG_MAX_TOTAL_EXPOSURE,
    LONG_POSITION_STEPS,
    LONG_PULLBACK_THRESHOLD,
    LONG_STRONG_TREND_PULLBACK_THRESHOLD,
    LONG_STOP_LOSS_PCT,
    MARKET_REGIME_FILTER_ENABLED,
    REGIME_BEAR_BREADTH_THRESHOLD,
    REGIME_BEAR_DD_252_THRESHOLD,
    REGIME_BEAR_EXIT_LOSS_THRESHOLD,
    REGIME_BULL_BREADTH_THRESHOLD,
    REGIME_BULL_DD_252_THRESHOLD,
    REGIME_NEUTRAL_PULLBACK_THRESHOLD,
    REGIME_STRONG_TREND_PULLBACK_THRESHOLD,
    MARKET_FILTER_ENABLED,
    MARKET_DROP_DD_20_THRESHOLD,
    MARKET_DROP_RET_5_THRESHOLD,
    MARKET_INDEX_CODE,
    MARKET_INDEX_PATH,
    MAX_AVG_DISTANCE_63,
    MAX_HIGH_POS_21,
    MAX_RET_21,
    MIN_RET_63,
    PURE_BULL_EXTRA_NAV_RATIO,
    PURE_BULL_EXTRA_TOTAL_CAP,
    RANK_STALE_EXIT_ENABLED,
    RANK_STALE_EXIT_MIN_TRADING_DAYS,
    RANK_STALE_EXIT_PROFIT_THRESHOLD_PCT,
    STRONG_TREND_ABOVE_RATIO_126,
    STRONG_TREND_ABOVE_RATIO_63,
    STRONG_TREND_RET_63,
    MIN_COMMISSION,
    MIN_SCORE,
    NAV_SERIES_PATH,
    OUTPUT_DIR,
    PANEL_PATH,
    POSITION_DAILY_PATH,
    REBALANCE_LOG_PATH,
    SCORES_PATH,
    SCHEMA,
    SUMMARY_PATH,
    STAR_MARKET_ADD_SCALE,
    STAR_MARKET_MAX_HOLDINGS,
    STAR_MARKET_POSITION_SCALE,
    STAR_MARKET_PREFIXES,
    TRADE_RECORDS_PATH,
)

PANEL_COLUMNS = [
    "ts_code", "trade_date", "name",
    "open", "high", "low", "close", "pre_close", "up_limit", "down_limit",
    "amount", "adj_factor", "is_suspended", "is_eligible",
    "above_bbi",
    "above_ratio_21", "above_ratio_63", "above_ratio_126",
    "avg_distance_63", "high_pos_21", "high_pos_63", "range_pos_63",
    "recent_limit_down_20", "recent_limit_up_20", "recent_limit_up_63",
    "turnover_rate_ma20", "turnover_rate_max20", "volume_ratio_max20",
    "lhb_count_20", "hot_money_risk_hits",
    "hm_limit_up_20_flag", "hm_limit_up_63_flag", "hm_turnover_ma20_flag",
    "hm_turnover_max20_flag", "hm_volume_ratio_max20_flag", "hm_lhb_count20_flag",
    "ret_21", "ret_63", "ret_126",
    "close_qfq", "bbi_qfq",
    "ma20_qfq", "ma20_slope_10", "early_weakness_downtrend",
    "up_accel_exhaustion", "bear_down_accel_risk", "accel_exhaustion_forbid_buy",
    "volatility_63", "amount_ma20", "circ_mv_ma20",
    "pullback_63",
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=BACKTEST_START_DATE, help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD")
    return parser.parse_args()


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def calc_commission(amount, is_buy):
    rate = COMMISSION_BUY if is_buy else COMMISSION_SELL
    return max(abs(amount) * rate, MIN_COMMISSION)


def get_open_price(row):
    price = safe_float(row.get("open"))
    return price if price > 0 else None


def is_limit_up_at_open(row):
    price = safe_float(row.get("open"))
    up_limit = safe_float(row.get("up_limit"))
    return not pd.isna(price) and not pd.isna(up_limit) and up_limit > 0 and price >= up_limit - 1e-6


def is_limit_down_at_open(row):
    price = safe_float(row.get("open"))
    down_limit = safe_float(row.get("down_limit"))
    return not pd.isna(price) and not pd.isna(down_limit) and down_limit > 0 and price <= down_limit + 1e-6


def is_limit_down_at_close(row):
    price = safe_float(row.get("close"))
    down_limit = safe_float(row.get("down_limit"))
    return not pd.isna(price) and not pd.isna(down_limit) and down_limit > 0 and price <= down_limit + 1e-6


def can_buy(row):
    if bool(row.get("is_suspended", False)):
        return False, "suspended"
    if is_limit_up_at_open(row):
        return False, "limit_up"
    if get_open_price(row) is None:
        return False, "missing_open"
    return True, ""


def can_sell(row):
    if bool(row.get("is_suspended", False)):
        return False, "suspended"
    if is_limit_down_at_open(row):
        return False, "limit_down"
    if get_open_price(row) is None:
        return False, "missing_open"
    return True, ""


def zscore(series):
    series = pd.to_numeric(series, errors="coerce")
    std = series.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def zscore_by_date(frame, value_col, out_col):
    values = pd.to_numeric(frame[value_col], errors="coerce")
    means = values.groupby(frame["trade_date"]).transform("mean")
    stds = values.groupby(frame["trade_date"]).transform(lambda s: s.std(ddof=0)).replace(0, np.nan)
    frame[out_col] = ((values - means) / stds).fillna(0.0)
    return frame


def validate_complete_trade_dates(open_dates, data_dates):
    open_set = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in open_dates}
    data_set = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in data_dates}
    return sorted(open_set - data_set)


def build_dc_segment_features(dc_daily):
    if dc_daily is None or dc_daily.empty:
        return pd.DataFrame(columns=["trade_date", "segment_code", "segment_score", "segment_crash"])
    data = dc_daily[["ts_code", "trade_date", "close", "amount"]].copy()
    data = data.rename(columns={"ts_code": "segment_code"})
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    data = data.dropna(subset=["segment_code", "trade_date", "close"]).sort_values(["segment_code", "trade_date"])
    grouped = data.groupby("segment_code", sort=False)
    data["seg_ret_20"] = grouped["close"].pct_change(20)
    data["seg_ret_60"] = grouped["close"].pct_change(60)
    rolling_high = grouped["close"].transform(lambda s: s.rolling(20, min_periods=5).max())
    data["seg_dd_20"] = data["close"] / rolling_high - 1.0
    data["seg_amount_rank_pct"] = data.groupby("trade_date")["amount"].rank(pct=True)
    for col in ["seg_ret_20", "seg_ret_60", "seg_amount_rank_pct"]:
        data[col] = data[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        data = zscore_by_date(data, col, f"{col}_z")
    data["segment_score"] = (
        0.45 * data["seg_ret_60_z"]
        + 0.35 * data["seg_ret_20_z"]
        + 0.20 * data["seg_amount_rank_pct_z"]
    ).clip(-3.0, 3.0)
    data["segment_crash"] = (
        (data["seg_ret_20"].fillna(0.0) <= DC_SEGMENT_CRASH_RET_20)
        | (data["seg_dd_20"].fillna(0.0) <= DC_SEGMENT_CRASH_DD_20)
    )
    return data[["trade_date", "segment_code", "segment_score", "segment_crash"]].copy()


def member_date_for_signal(signal_date, members, member_lag_days=DC_SEGMENT_MEMBER_LAG_DAYS):
    signal_date = pd.Timestamp(signal_date)
    member_dates = sorted(pd.to_datetime(members["trade_date"].dropna().unique()))
    available_dates = [d for d in member_dates if d <= signal_date]
    if len(available_dates) <= member_lag_days:
        return None
    return available_dates[-1 - member_lag_days]


def dc_segment_exposure(signal_date, members, segment_features):
    signal_date = pd.Timestamp(signal_date)
    empty = pd.DataFrame(columns=["ts_code", "has_segment_crash"])
    if members is None or members.empty or segment_features is None or segment_features.empty:
        return empty
    member_date = member_date_for_signal(signal_date, members)
    if member_date is None:
        return empty
    day_members = members[members["trade_date"].eq(member_date)][["con_code", "ts_code"]].copy()
    if day_members.empty:
        return empty
    day_members = day_members.rename(columns={"con_code": "ts_code", "ts_code": "segment_code"})
    day_features = segment_features[segment_features["trade_date"].eq(signal_date)].copy()
    merged = day_members.merge(day_features, on="segment_code", how="left")
    if merged.empty:
        return empty
    merged["segment_crash"] = merged["segment_crash"].where(merged["segment_crash"].notna(), False).astype(bool)
    return merged.groupby("ts_code").agg(has_segment_crash=("segment_crash", "max")).reset_index()


def load_dc_segment_overlay(start_date, end_date):
    if not DC_SEGMENT_OVERLAY_ENABLED:
        return None, None, "disabled"
    active_start = pd.Timestamp(DC_SEGMENT_OVERLAY_ACTIVE_FROM)
    end_ts = pd.Timestamp(end_date)
    if end_ts < active_start:
        return None, None, "not_active_in_period"
    engine = create_engine(DB_URL, poolclass=NullPool)
    with engine.connect() as conn:
        open_dates = pd.to_datetime(pd.read_sql(text(f"""
            SELECT cal_date::date AS trade_date
            FROM {SCHEMA}."003_trade_cal"
            WHERE exchange = 'SSE'
              AND is_open = 1
              AND cal_date >= :start_date
              AND cal_date <= :end_date
            ORDER BY cal_date
        """), conn, params={"start_date": str(active_start.date()), "end_date": end_date})["trade_date"])
        member_dates = pd.to_datetime(pd.read_sql(text(f"""
            SELECT DISTINCT trade_date::date AS trade_date
            FROM {SCHEMA}."098_dc_member"
            WHERE trade_date >= :start_date
              AND trade_date <= :end_date
        """), conn, params={"start_date": str(active_start.date()), "end_date": end_date})["trade_date"])
        daily_dates = pd.to_datetime(pd.read_sql(text(f"""
            SELECT DISTINCT trade_date::date AS trade_date
            FROM {SCHEMA}."099_dc_daily"
            WHERE trade_date >= :start_date
              AND trade_date <= :end_date
        """), conn, params={"start_date": str(active_start.date()), "end_date": end_date})["trade_date"])
        missing_members = validate_complete_trade_dates(open_dates, member_dates)
        missing_daily = validate_complete_trade_dates(open_dates, daily_dates)
        if missing_members or missing_daily:
            raise RuntimeError(
                "DC segment overlay completeness failed: "
                f"098_dc_member missing={missing_members[:10]}, "
                f"099_dc_daily missing={missing_daily[:10]}. "
                "请先补齐这些 DC 赛道数据后再运行正式 v8 回测；"
                "如果只是想临时忽略 DC overlay，请在 config.py 中显式设置 "
                "DC_SEGMENT_OVERLAY_ENABLED = False。"
            )
        dc_daily = pd.read_sql(text(f"""
            SELECT ts_code, trade_date, close, amount
            FROM {SCHEMA}."099_dc_daily"
            WHERE trade_date >= DATE '2024-10-01'
              AND trade_date <= :end_date
        """), conn, params={"end_date": end_date})
        members = pd.read_sql(text(f"""
            SELECT trade_date, ts_code, con_code
            FROM {SCHEMA}."098_dc_member"
            WHERE trade_date >= :start_date
              AND trade_date <= :end_date
        """), conn, params={"start_date": str(active_start.date()), "end_date": end_date})
    members["trade_date"] = pd.to_datetime(members["trade_date"])
    segment_features = build_dc_segment_features(dc_daily)
    return members, segment_features, "enabled"


def apply_dc_segment_crash_filter(candidates, signal_date, members, segment_features, diagnostics=None):
    if candidates.empty or not DC_SEGMENT_OVERLAY_ENABLED:
        return candidates
    if pd.Timestamp(signal_date) < pd.Timestamp(DC_SEGMENT_OVERLAY_ACTIVE_FROM):
        return candidates
    exposure = dc_segment_exposure(signal_date, members, segment_features)
    if exposure.empty:
        return candidates
    out = candidates.reset_index(drop=True).merge(exposure, on="ts_code", how="left")
    out["has_segment_crash"] = out["has_segment_crash"].where(out["has_segment_crash"].notna(), False).astype(bool)
    blocked = out["has_segment_crash"]
    if diagnostics is not None:
        blocked_count = int(blocked.sum())
        diagnostics["dc_segment_candidate_blocks"] = diagnostics.get("dc_segment_candidate_blocks", 0) + blocked_count
        if blocked_count:
            diagnostics["dc_segment_signal_days"] = diagnostics.get("dc_segment_signal_days", 0) + 1
    return out[~blocked].drop(columns=["has_segment_crash"], errors="ignore").copy().reset_index(drop=True)


def apply_dc_segment_score_boost(
    candidates,
    signal_date,
    members,
    segment_features,
    weight=DC_SEGMENT_SCORE_WEIGHT,
):
    if candidates.empty or not DC_SEGMENT_OVERLAY_ENABLED:
        return candidates.copy()
    if pd.Timestamp(signal_date) < pd.Timestamp(DC_SEGMENT_OVERLAY_ACTIVE_FROM):
        return candidates.copy()
    if members is None or members.empty or segment_features is None or segment_features.empty:
        return candidates.copy()

    member_date = member_date_for_signal(signal_date, members)
    if member_date is None:
        return candidates.copy()

    day_members = members[members["trade_date"].eq(member_date)][["con_code", "ts_code"]].copy()
    if day_members.empty:
        return candidates.copy()
    day_members = day_members.rename(columns={"con_code": "ts_code", "ts_code": "segment_code"})

    day_features = segment_features[segment_features["trade_date"].eq(pd.Timestamp(signal_date))][
        ["segment_code", "segment_score"]
    ].copy()
    if day_features.empty:
        return candidates.copy()

    exposure = day_members.merge(day_features, on="segment_code", how="left")
    if exposure.empty:
        return candidates.copy()
    exposure["segment_score"] = pd.to_numeric(exposure["segment_score"], errors="coerce").fillna(0.0)
    exposure = exposure.groupby("ts_code", as_index=False).agg(best_segment_score=("segment_score", "max"))

    out = candidates.reset_index(drop=True).drop(columns=["best_segment_score", "segment_adjustment"], errors="ignore")
    out = out.merge(exposure, on="ts_code", how="left")
    out["best_segment_score"] = pd.to_numeric(out["best_segment_score"], errors="coerce").fillna(0.0)
    out["segment_adjustment"] = out["best_segment_score"].clip(-2.0, 2.0) * float(weight)
    out["score"] = pd.to_numeric(out["score"], errors="coerce").fillna(0.0) + out["segment_adjustment"]
    return out.sort_values(
        ["score", "above_ratio_63", "ret_63", "amount_ma20", "best_segment_score"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)


def apply_downtrend_buy_filter(candidates, diagnostics=None):
    if not DOWNTREND_BUY_FILTER_ENABLED:
        return candidates
    if DOWNTREND_FILTER_NAME not in candidates.columns:
        raise ValueError(
            f"panel missing downtrend filter column {DOWNTREND_FILTER_NAME}. "
            "Run 10_prepare_data.py again."
        )
    blocked = candidates[DOWNTREND_FILTER_NAME].fillna(False).astype(bool)
    blocked_count = int(blocked.sum())
    if diagnostics is not None:
        diagnostics["downtrend_filter_candidate_blocks"] = (
            diagnostics.get("downtrend_filter_candidate_blocks", 0) + blocked_count
        )
        if blocked_count:
            diagnostics["downtrend_filter_signal_days"] = (
                diagnostics.get("downtrend_filter_signal_days", 0) + 1
            )
    return candidates[~blocked].copy()


def add_positive_return_ratio(panel, window=63, min_periods=30):
    out = panel.sort_values(["ts_code", "trade_date"]).copy()
    returns = out.groupby("ts_code", sort=False)["close_qfq"].pct_change()
    positive = returns.gt(0).where(returns.notna())
    out["positive_ret_ratio_63"] = (
        positive.groupby(out["ts_code"], sort=False)
        .transform(lambda s: s.rolling(window, min_periods=min_periods).mean())
        .fillna(0.0)
    )
    return out


def add_market_ret_63(panel, market):
    out = panel.copy()
    if market is None or market.empty or "close" not in market.columns:
        out["market_ret_63"] = 0.0
        return out
    market_frame = market.copy()
    if "trade_date" not in market_frame.columns:
        market_frame["trade_date"] = market_frame.index
    market_frame = market_frame.reset_index(drop=True)
    market_frame["trade_date"] = pd.to_datetime(market_frame["trade_date"])
    market_frame = market_frame.sort_values("trade_date")
    market_frame["market_ret_63"] = pd.to_numeric(market_frame["close"], errors="coerce").pct_change(63)
    return out.merge(market_frame[["trade_date", "market_ret_63"]], on="trade_date", how="left")


def is_weak_lowvol_market(market_regime_name, regime_snapshot):
    if market_regime_name == "bear":
        return True
    if market_regime_name != "neutral" or not regime_snapshot:
        return False
    market_dd = safe_float(regime_snapshot.get("market_dd_252"), 0.0)
    breadth = safe_float(regime_snapshot.get("breadth_above_bbi"), 1.0)
    return market_dd <= -0.10 and breadth <= 0.55


def apply_weak_lowvol_mom_filter(candidates, market_regime_name, regime_snapshot=None, diagnostics=None):
    if not is_weak_lowvol_market(market_regime_name, regime_snapshot):
        return candidates
    if candidates.empty:
        return candidates

    data = candidates.copy()
    for col, default in {
        "ret_21": 0.0,
        "ret_63": 0.0,
        "volatility_63": np.nan,
        "recent_limit_down_20": 0,
        "hot_money_risk_hits": 0,
    }.items():
        if col not in data.columns:
            data[col] = default

    vol_cut = pd.to_numeric(data["volatility_63"], errors="coerce").quantile(0.50)
    if pd.isna(vol_cut):
        vol_cut = float("inf")
    mask = (
        data["recent_limit_down_20"].fillna(1).eq(0)
        & pd.to_numeric(data["hot_money_risk_hits"], errors="coerce").fillna(99).lt(2)
        & pd.to_numeric(data["volatility_63"], errors="coerce").le(vol_cut)
        & pd.to_numeric(data["ret_63"], errors="coerce").gt(0.0)
        & pd.to_numeric(data["ret_21"], errors="coerce").gt(-0.05)
    )
    filtered = data[mask].copy()
    if diagnostics is not None:
        diagnostics["weak_lowvol_mom_signal_days"] = diagnostics.get("weak_lowvol_mom_signal_days", 0) + 1
        diagnostics["weak_lowvol_mom_candidate_blocks"] = (
            diagnostics.get("weak_lowvol_mom_candidate_blocks", 0) + int(len(data) - len(filtered))
        )
    return filtered


def score_candidates(signal_panel, diagnostics=None):
    candidates = signal_panel[signal_panel["is_eligible"].fillna(False)].copy()
    required_cols = ["high_pos_21", "high_pos_63", "range_pos_63", "recent_limit_down_20"]
    if HOT_MONEY_RISK_ENABLED:
        required_cols.extend([
            "recent_limit_up_20",
            "recent_limit_up_63",
            "turnover_rate_ma20",
            "turnover_rate_max20",
            "volume_ratio_max20",
            "lhb_count_20",
            "hot_money_risk_hits",
        ])
    missing_cols = [col for col in required_cols if col not in candidates.columns]
    if missing_cols:
        raise ValueError(
            f"panel missing candidate filter columns {missing_cols}. Run 10_prepare_data.py again."
        )
    hot_money_risk_ok = pd.Series(True, index=candidates.index)
    if HOT_MONEY_RISK_ENABLED:
        hot_money_risk_ok = (
            candidates["hot_money_risk_hits"].notna()
            & (candidates["hot_money_risk_hits"] < HOT_MONEY_RISK_MIN_HITS)
        )
    candidates["strong_trend"] = (
        (candidates["above_ratio_63"] >= STRONG_TREND_ABOVE_RATIO_63)
        & (candidates["above_ratio_126"] >= STRONG_TREND_ABOVE_RATIO_126)
        & (candidates["ret_63"] >= STRONG_TREND_RET_63)
        & hot_money_risk_ok
        & (candidates["recent_limit_down_20"] == 0)
    )
    recent_high_risk = (candidates["high_pos_21"] >= MAX_HIGH_POS_21) & ~candidates["strong_trend"]
    ret_21_ok = (candidates["ret_21"] <= MAX_RET_21) | candidates["strong_trend"]
    candidates = candidates[
        (candidates["above_ratio_63"] >= 0.55)
        & (candidates["above_ratio_126"] >= 0.50)
        & (candidates["ret_63"] >= MIN_RET_63)
        & ret_21_ok
        & (candidates["avg_distance_63"] <= MAX_AVG_DISTANCE_63)
        & candidates["high_pos_21"].notna()
        & candidates["high_pos_63"].notna()
        & candidates["range_pos_63"].notna()
        & candidates["recent_limit_down_20"].notna()
        & (candidates["recent_limit_down_20"] == 0)
        & hot_money_risk_ok
        & ~recent_high_risk
        & candidates["ret_63"].notna()
        & candidates["volatility_63"].notna()
        & candidates["amount_ma20"].notna()
    ].copy()
    if candidates.empty:
        candidates["score"] = []
        return candidates

    candidates["score"] = (
        0.30 * zscore(candidates["above_ratio_63"])
        + 0.25 * zscore(candidates["above_ratio_126"])
        + 0.15 * zscore(candidates["ret_63"])
        + 0.10 * zscore(candidates["avg_distance_63"])
        - 0.15 * zscore(candidates["volatility_63"])
        + 0.05 * zscore(np.log(candidates["amount_ma20"].clip(lower=1.0)))
    )
    candidates = candidates[candidates["score"] >= MIN_SCORE].copy()
    candidates = apply_downtrend_buy_filter(candidates, diagnostics=diagnostics)
    return candidates.sort_values(
        ["score", "above_ratio_63", "ret_63", "amount_ma20"],
        ascending=[False, False, False, False],
    )


def load_market_index():
    if not MARKET_FILTER_ENABLED:
        return None
    if not MARKET_INDEX_PATH.exists():
        raise FileNotFoundError(f"Missing {MARKET_INDEX_PATH}. Run 10_prepare_data.py first.")
    market = pd.read_parquet(MARKET_INDEX_PATH)
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    missing_cols = [col for col in ["close"] if col not in market.columns]
    if missing_cols:
        raise ValueError(
            f"{MARKET_INDEX_PATH} missing market columns {missing_cols}. "
            "Run 10_prepare_data.py again."
        )
    return market.sort_values("trade_date").set_index("trade_date")


def market_short_drop_blocks_buy(market, signal_date):
    if not MARKET_FILTER_ENABLED:
        return False, "disabled", {}
    if market is None or signal_date not in market.index:
        return True, "missing_market", {}
    history = market.loc[:signal_date].tail(20).copy()
    if len(history) < 20:
        return True, "missing_market_history", {}
    close = pd.to_numeric(history["close"], errors="coerce")
    if close.isna().any():
        return True, "missing_market_history", {}

    current_close = float(close.iloc[-1])
    ret_5 = current_close / float(close.iloc[-6]) - 1.0 if len(close) >= 6 else float("nan")
    dd_20 = current_close / float(close.max()) - 1.0
    snapshot = {
        "market_ret_5": ret_5,
        "market_dd_20": dd_20,
    }
    if ret_5 <= MARKET_DROP_RET_5_THRESHOLD:
        return True, "market_5d_drop", snapshot
    if dd_20 <= MARKET_DROP_DD_20_THRESHOLD:
        return True, "market_20d_drawdown", snapshot
    return False, "market_short_drop_ok", snapshot


def classify_market_regime(row):
    close = safe_float(row.get("close"))
    ma120 = safe_float(row.get("ma120"))
    ma200 = safe_float(row.get("ma200"))
    ma120_slope_20 = safe_float(row.get("ma120_slope_20"))
    dd_252 = safe_float(row.get("dd_252"))
    breadth = safe_float(row.get("breadth_above_bbi"))
    values = [close, ma120, ma200, ma120_slope_20, dd_252, breadth]
    if any(pd.isna(v) for v in values):
        return "unknown"
    if dd_252 <= REGIME_BEAR_DD_252_THRESHOLD:
        return "bear"
    if close < ma120 and ma120_slope_20 < 0 and breadth < REGIME_BEAR_BREADTH_THRESHOLD:
        return "bear"
    if (
        close > ma120
        and close > ma200
        and ma120_slope_20 > 0
        and dd_252 > REGIME_BULL_DD_252_THRESHOLD
        and breadth >= REGIME_BULL_BREADTH_THRESHOLD
    ):
        return "bull"
    return "neutral"


def build_market_regime(market, panel):
    if not MARKET_REGIME_FILTER_ENABLED or market is None:
        return None
    regime = market.copy().sort_index()
    close = pd.to_numeric(regime["close"], errors="coerce")
    regime["ma120"] = close.rolling(120, min_periods=120).mean()
    regime["ma200"] = close.rolling(200, min_periods=200).mean()
    regime["ma120_slope_20"] = regime["ma120"] / regime["ma120"].shift(20) - 1.0
    regime["dd_252"] = close / close.rolling(252, min_periods=120).max() - 1.0

    breadth = panel[["trade_date", "ts_code", "is_eligible", "above_bbi"]].copy()
    breadth = breadth[breadth["is_eligible"].fillna(False)]
    breadth["above_bbi_num"] = breadth["above_bbi"].fillna(False).astype(float)
    breadth_daily = breadth.groupby("trade_date").agg(
        breadth_above_bbi=("above_bbi_num", "mean"),
        breadth_count=("ts_code", "count"),
    )
    regime = regime.join(breadth_daily, how="left")
    regime["regime"] = regime.apply(classify_market_regime, axis=1)
    regime = add_bear_probe_market_features(regime)
    return regime


def add_bear_probe_market_features(market_regime, min_breadth=BEAR_PROBE_MIN_BREADTH, breadth_improve=BEAR_PROBE_BREADTH_IMPROVE_5):
    out = market_regime.copy()
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"])
        out = out.sort_values("trade_date").set_index("trade_date", drop=False)
    else:
        out = out.sort_index()
    breadth = pd.to_numeric(out["breadth_above_bbi"], errors="coerce")
    close = pd.to_numeric(out["close"], errors="coerce")
    out["breadth_change_5"] = breadth - breadth.shift(5)
    out["market_ma20"] = close.rolling(20, min_periods=3).mean()
    out["market_ma20_slope_5"] = out["market_ma20"] / out["market_ma20"].shift(5) - 1.0
    out["market_ma20_slope_3"] = out["market_ma20"] / out["market_ma20"].shift(3) - 1.0
    out["bear_probe_market_ok"] = (
        out["regime"].eq("bear")
        & (breadth >= min_breadth)
        & (out["breadth_change_5"] >= breadth_improve)
        & (close >= out["market_ma20"])
        & ((out["market_ma20_slope_5"] >= 0) | (out["market_ma20_slope_3"] >= 0))
    )
    return out


def add_bear_probe_stock_features(panel):
    out = panel.copy().sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = out.groupby("ts_code", sort=False)
    close = pd.to_numeric(out["close_qfq"], errors="coerce")
    bbi = pd.to_numeric(out["bbi_qfq"], errors="coerce")
    out["bbi_slope_5"] = grouped["bbi_qfq"].pct_change(BEAR_PROBE_BBI_SLOPE_WINDOW, fill_method=None)
    out["ret_5_probe"] = grouped["close_qfq"].pct_change(5, fill_method=None)
    risk = out.get("accel_exhaustion_forbid_buy", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    out["bear_probe_stock_ok"] = (
        (close > bbi)
        & (out["bbi_slope_5"] > 0)
        & (out["ret_5_probe"] > 0)
        & ~risk
    )
    return out


def get_market_regime(market_regime, signal_date):
    if not MARKET_REGIME_FILTER_ENABLED or market_regime is None or signal_date not in market_regime.index:
        return "disabled", {}
    row = market_regime.loc[signal_date]
    regime = str(row.get("regime", "unknown"))
    snapshot = {
        "market_regime": regime,
        "breadth_above_bbi": safe_float(row.get("breadth_above_bbi")),
        "breadth_change_5": safe_float(row.get("breadth_change_5")),
        "bear_probe_market_ok": bool(row.get("bear_probe_market_ok", False)),
        "market_dd_252": safe_float(row.get("dd_252")),
        "market_ma120_slope_20": safe_float(row.get("ma120_slope_20")),
    }
    return regime, snapshot


def regime_pullback_thresholds(market_regime_name):
    if not MARKET_REGIME_FILTER_ENABLED:
        return LONG_PULLBACK_THRESHOLD, LONG_STRONG_TREND_PULLBACK_THRESHOLD
    if market_regime_name == "bull":
        return BULL_EARLY_ENTRY_PULLBACK_THRESHOLD, BULL_EARLY_ENTRY_STRONG_PULLBACK_THRESHOLD
    if market_regime_name == "bear":
        return REGIME_NEUTRAL_PULLBACK_THRESHOLD, REGIME_STRONG_TREND_PULLBACK_THRESHOLD
    return REGIME_NEUTRAL_PULLBACK_THRESHOLD, REGIME_STRONG_TREND_PULLBACK_THRESHOLD


def mark_position(code, pos, day_panel):
    if code in day_panel.index:
        row = day_panel.loc[code]
        apply_adj_factor(pos, row)
        close_price = safe_float(row.get("close"))
        if close_price > 0:
            pos["last_price"] = close_price
            return close_price * pos["shares"]
    return pos.get("last_price", pos["cost_price"]) * pos["shares"]


def calc_position_cost(pos):
    return pos["cost_price"] * pos["shares"] + pos.get("buy_comm", 0.0)


def calc_position_profit_pct(code, pos, signal_panel):
    if code not in signal_panel.index:
        return None
    row = signal_panel.loc[code]
    apply_adj_factor(pos, row)
    close_price = safe_float(row.get("close"))
    if pd.isna(close_price) or close_price <= 0:
        return None
    pos["last_price"] = close_price
    cost_value = calc_position_cost(pos)
    if cost_value <= 0:
        return None
    market_value = close_price * pos["shares"]
    return market_value / cost_value - 1.0


def calc_total_exposure(holdings):
    return sum(float(pos.get("invested_amount", calc_position_cost(pos))) for pos in holdings.values())


def is_pure_bull_extra_step(step_index):
    return int(step_index) == 4


def calc_pure_bull_extra_exposure_limit(current_nav, market_regime_name, is_extra_winner_add):
    if market_regime_name != "bull" or not bool(is_extra_winner_add):
        return LONG_MAX_TOTAL_EXPOSURE
    ratio_limit = float(current_nav) * float(PURE_BULL_EXTRA_NAV_RATIO)
    capped = min(float(PURE_BULL_EXTRA_TOTAL_CAP), ratio_limit)
    return max(LONG_MAX_TOTAL_EXPOSURE, capped)


def can_use_pure_bull_extra_add(step_index, market_regime_name):
    return is_pure_bull_extra_step(step_index) and market_regime_name == "bull"


def calc_bear_probe_exposure(holdings):
    return sum(float(pos.get("invested_amount", 0.0)) for pos in holdings.values() if pos.get("probe_entry"))


def calc_bear_probe_target_amount(normal_first_step, cash, current_probe_exposure):
    target = normal_first_step * BEAR_PROBE_POSITION_FRACTION
    remaining_probe = BEAR_PROBE_MAX_TOTAL_EXPOSURE - current_probe_exposure
    return max(0.0, min(target, cash, remaining_probe))


def is_star_market_code(code):
    return isinstance(code, str) and code.startswith(STAR_MARKET_PREFIXES)


def calc_star_market_target_amount(code, target_amount, reason):
    if not is_star_market_code(code):
        return float(target_amount)
    if reason in {"long_initial_buy", "bear_probe_initial_buy"}:
        return float(target_amount) * float(STAR_MARKET_POSITION_SCALE)
    return float(target_amount) * float(STAR_MARKET_ADD_SCALE)


def can_open_star_market_position(code, holdings):
    if not is_star_market_code(code) or code in holdings:
        return True
    star_count = sum(1 for held_code in holdings if is_star_market_code(held_code))
    return star_count < int(STAR_MARKET_MAX_HOLDINGS)


def next_position_step(pos):
    step_index = int(pos.get("step_index", 0))
    if step_index >= len(LONG_POSITION_STEPS):
        return None
    return float(LONG_POSITION_STEPS[step_index])


def add_profit_thresholds_for_regime(market_regime_name):
    if market_regime_name == "bull":
        return BULL_ADD_PROFIT_THRESHOLDS
    return LONG_ADD_PROFIT_THRESHOLDS


def can_add_position(code, pos, signal_panel, market_regime_name=None):
    step_index = int(pos.get("step_index", 0))
    if step_index <= 0 or step_index >= len(LONG_POSITION_STEPS):
        return False
    profit_pct = calc_position_profit_pct(code, pos, signal_panel)
    if profit_pct is None:
        return False
    thresholds = add_profit_thresholds_for_regime(market_regime_name)
    threshold_index = step_index - 1
    if threshold_index >= len(thresholds):
        return False
    return profit_pct >= thresholds[threshold_index]


def has_limit_down_signal(code, pos, signal_panel):
    if not LIMIT_DOWN_EXIT_ENABLED or code not in signal_panel.index:
        return False
    row = signal_panel.loc[code]
    apply_adj_factor(pos, row)
    close_price = safe_float(row.get("close"))
    if close_price > 0:
        pos["last_price"] = close_price
    return is_limit_down_at_close(row)


def has_stop_loss_signal(code, pos, signal_panel):
    profit_pct = calc_position_profit_pct(code, pos, signal_panel)
    return profit_pct is not None and profit_pct <= LONG_STOP_LOSS_PCT


def should_rank_stale_exit(pos, profit_pct, candidate_by_code, code):
    if not RANK_STALE_EXIT_ENABLED:
        return False
    try:
        profit = float(profit_pct)
    except (TypeError, ValueError):
        return False
    holding_days = int(pos.get("holding_trading_days", 0) or 0)
    return (
        holding_days >= int(RANK_STALE_EXIT_MIN_TRADING_DAYS)
        and profit <= float(RANK_STALE_EXIT_PROFIT_THRESHOLD_PCT)
        and code not in candidate_by_code.index
    )


def has_bearish_volume_signal(code, pos, signal_panel):
    profit_pct = calc_position_profit_pct(code, pos, signal_panel)
    if profit_pct is None or profit_pct <= 0 or code not in signal_panel.index:
        return False
    row = signal_panel.loc[code]
    close_price = safe_float(row.get("close"))
    open_price = safe_float(row.get("open"))
    low_price = safe_float(row.get("low"))
    high_price = safe_float(row.get("high"))
    pre_close = safe_float(row.get("pre_close"))
    amount = safe_float(row.get("amount"))
    amount_ma20 = safe_float(row.get("amount_ma20"))
    values = [close_price, open_price, low_price, high_price, pre_close, amount, amount_ma20]
    if any(pd.isna(v) or v <= 0 for v in values):
        return False
    if close_price >= open_price:
        return False
    if close_price / pre_close - 1.0 > LONG_BEARISH_DROP_THRESHOLD:
        return False
    if amount < amount_ma20 * LONG_BEARISH_AMOUNT_MULTIPLIER:
        return False
    price_range = high_price - low_price
    if price_range <= 0:
        return False
    return close_price <= low_price + price_range * LONG_BEARISH_CLOSE_LOW_POSITION


def apply_adj_factor(pos, row):
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


def execute_sell(date, code, pos, day_panel, cash, trades, reason):
    if code not in day_panel.index:
        pos["pending_sell"] = True
        pos["pending_reason"] = reason
        return cash, False, "missing_row"
    row = day_panel.loc[code]
    apply_adj_factor(pos, row)
    ok, skip_reason = can_sell(row)
    if not ok:
        pos["pending_sell"] = True
        pos["pending_reason"] = reason
        return cash, False, skip_reason
    price = get_open_price(row)
    amount = price * pos["shares"]
    comm = calc_commission(amount, is_buy=False)
    cash += amount - comm
    pnl = (price - pos["cost_price"]) * pos["shares"] - pos["buy_comm"] - comm
    pnl_pct = pnl / max(pos["cost_price"] * pos["shares"] + pos["buy_comm"], 1.0) * 100.0
    trades.append({
        "date": str(date)[:10],
        "ts_code": code,
        "name": pos["name"],
        "action": "sell",
        "price": round(price, 4),
        "shares": pos["shares"],
        "amount": round(amount, 2),
        "commission": round(comm, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 4),
        "reason": reason,
    })
    return cash, True, ""


def execute_buy(date, row, target_amount, cash, holdings, trades, reason):
    ok, skip_reason = can_buy(row)
    if not ok:
        return cash, False, skip_reason
    code = row["ts_code"]
    if not can_open_star_market_position(code, holdings):
        return cash, False, "star_market_max_holdings"
    target_amount = calc_star_market_target_amount(code, target_amount, reason)
    price = get_open_price(row)
    shares = int(target_amount / price / 100) * 100
    if shares < 100:
        return cash, False, "insufficient_cash"
    amount = price * shares
    comm = calc_commission(amount, is_buy=True)
    if amount + comm > cash:
        shares = int((cash - MIN_COMMISSION) / price / 100) * 100
        amount = price * shares
        comm = calc_commission(amount, is_buy=True)
    if shares < 100 or amount + comm > cash:
        return cash, False, "insufficient_cash"
    cash -= amount + comm
    if code in holdings:
        pos = holdings[code]
        old_shares = pos["shares"]
        old_cost_value = pos["cost_price"] * old_shares
        new_shares = old_shares + shares
        pos["shares"] = new_shares
        pos["cost_price"] = (old_cost_value + amount) / new_shares
        pos["buy_comm"] = pos.get("buy_comm", 0.0) + comm
        pos["last_price"] = price
        pos["last_adj_factor"] = safe_float(row.get("adj_factor"), None)
        pos["invested_amount"] = pos.get("invested_amount", 0.0) + amount + comm
        pos["step_index"] = int(pos.get("step_index", 1)) + 1
    else:
        holdings[code] = {
            "name": row["name"],
            "shares": shares,
            "cost_price": price,
            "buy_comm": comm,
            "last_price": price,
            "last_adj_factor": safe_float(row.get("adj_factor"), None),
            "buy_date": str(date)[:10],
            "pending_sell": False,
            "invested_amount": amount + comm,
            "step_index": 1,
        }
    trades.append({
        "date": str(date)[:10],
        "ts_code": code,
        "name": row["name"],
        "action": "buy",
        "price": round(price, 4),
        "shares": shares,
        "amount": round(amount, 2),
        "commission": round(comm, 2),
        "pnl": "",
        "pnl_pct": "",
        "reason": reason,
    })
    return cash, True, ""


def calc_max_drawdown(nav_df):
    curve = nav_df["nav"] / nav_df["nav"].iloc[0]
    dd = curve / curve.cummax() - 1.0
    return float(dd.min() * 100.0)


def build_position_daily_rows(date, holdings):
    rows = []
    for code, pos in sorted(holdings.items()):
        shares = float(pos.get("shares", 0.0))
        price = float(pos.get("last_price", pos.get("cost_price", 0.0)))
        rows.append({
            "date": str(date)[:10],
            "ts_code": code,
            "name": pos.get("name", code),
            "shares": round(shares, 4),
            "close": round(price, 4),
            "market_value": round(shares * price, 2),
            "cost_price": round(float(pos.get("cost_price", 0.0)), 4),
            "invested_amount": round(float(pos.get("invested_amount", 0.0)), 2),
            "buy_comm": round(float(pos.get("buy_comm", 0.0)), 2),
            "step_index": int(pos.get("step_index", 0)),
        })
    return rows


def build_panel_by_date(panel):
    return {
        date: group_index.to_numpy()
        for date, group_index in panel.groupby("trade_date", sort=True).groups.items()
    }


def get_day_panel(panel, panel_by_date, date):
    indexer = panel_by_date[date]
    return panel.iloc[indexer].set_index("ts_code", drop=False)


def run_backtest(panel, market, start_date, end_date):
    if "positive_ret_ratio_63" not in panel.columns:
        panel = add_positive_return_ratio(panel)
    if "market_ret_63" not in panel.columns:
        panel = add_market_ret_63(panel, market)
    if BEAR_PROBE_BUY_ENABLED and "bear_probe_stock_ok" not in panel.columns:
        panel = add_bear_probe_stock_features(panel)
    market_regime = build_market_regime(market, panel)
    if end_date:
        panel = panel[panel["trade_date"] <= pd.Timestamp(end_date)].copy()
    panel = panel[panel["trade_date"] >= pd.Timestamp(start_date)].copy()
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    panel_by_date = build_panel_by_date(panel)
    all_dates = sorted(panel_by_date)
    overlay_end_date = str(all_dates[-2])[:10] if len(all_dates) >= 2 else str(all_dates[-1])[:10]
    dc_segment_members, dc_segment_features, dc_segment_status = load_dc_segment_overlay(start_date, overlay_end_date)

    cash = INIT_CASH
    holdings = {}
    trades = []
    rebalance_log = []
    score_rows = []
    nav_rows = []
    position_rows = []
    stats = {
        "signal_days": 0,
        "market_block_days": 0,
        "missing_market_days": 0,
        "buy_fills": 0,
        "add_buy_fills": 0,
        "sell_fills": 0,
        "buy_skips": 0,
        "sell_delays": 0,
        "limit_down_exit_signals": 0,
        "limit_down_exit_fills": 0,
        "stop_loss_signals": 0,
        "stop_loss_fills": 0,
        "bearish_volume_exit_signals": 0,
        "bearish_volume_exit_fills": 0,
        "regime_bear_exit_signals": 0,
        "regime_bear_exit_fills": 0,
        "regime_bear_block_days": 0,
        "bear_probe_enabled": bool(BEAR_PROBE_BUY_ENABLED),
        "bear_probe_signal_days": 0,
        "bear_probe_buys": 0,
        "downtrend_filter_enabled": bool(DOWNTREND_BUY_FILTER_ENABLED),
        "downtrend_filter_candidate_blocks": 0,
        "downtrend_filter_signal_days": 0,
        "weak_lowvol_mom_enabled": True,
        "weak_lowvol_mom_signal_days": 0,
        "weak_lowvol_mom_candidate_blocks": 0,
        "pure_bull_extra_add_signals": 0,
        "pure_bull_extra_add_fills": 0,
        "pure_bull_extra_add_amount": 0.0,
        "dc_segment_overlay_enabled": bool(DC_SEGMENT_OVERLAY_ENABLED),
        "dc_segment_overlay_status": dc_segment_status,
        "dc_segment_overlay_active_from": DC_SEGMENT_OVERLAY_ACTIVE_FROM,
        "dc_segment_member_lag_days": int(DC_SEGMENT_MEMBER_LAG_DAYS),
        "dc_segment_signal_days": 0,
        "dc_segment_candidate_blocks": 0,
        "rank_stale_exit_enabled": bool(RANK_STALE_EXIT_ENABLED),
        "rank_stale_exit_min_days": int(RANK_STALE_EXIT_MIN_TRADING_DAYS),
        "rank_stale_exit_profit_threshold_pct": float(RANK_STALE_EXIT_PROFIT_THRESHOLD_PCT),
        "rank_stale_exit_signals": 0,
        "rank_stale_exit_fills": 0,
    }
    # Bear confirmed loss exit: no-entry uses signal_date, while loss exits use
    # the previously confirmed bear state validated by the tmp experiment.
    previous_market_regime_name = "unknown"

    for i, date in enumerate(all_dates):
        day_panel = get_day_panel(panel, panel_by_date, date)
        risk_exit_codes = set()

        for code in list(holdings):
            if holdings[code].get("pending_sell"):
                pending_reason = holdings[code].get("pending_reason", "pending_sell")
                cash, sold, reason = execute_sell(date, code, holdings[code], day_panel, cash, trades, pending_reason)
                if sold:
                    del holdings[code]
                    risk_exit_codes.add(code)
                    stats["sell_fills"] += 1
                else:
                    stats["sell_delays"] += 1

        market_regime_name = "disabled"
        regime_snapshot = {}
        if i > 0 and holdings:
            signal_date = all_dates[i - 1]
            signal_panel = get_day_panel(panel, panel_by_date, signal_date)
            market_regime_name, regime_snapshot = get_market_regime(market_regime, signal_date)
            exit_reasons = {}
            for code in list(holdings):
                pos = holdings[code]
                if pos.get("pending_sell"):
                    continue
                pos["holding_trading_days"] = int(pos.get("holding_trading_days", 0) or 0) + 1
                profit_pct = calc_position_profit_pct(code, pos, signal_panel)
                if (
                    MARKET_REGIME_FILTER_ENABLED
                    and previous_market_regime_name == "bear"
                    and profit_pct is not None
                    and profit_pct <= REGIME_BEAR_EXIT_LOSS_THRESHOLD
                ):
                    exit_reasons[code] = "long_regime_bear_exit"
                    stats["regime_bear_exit_signals"] += 1
                elif profit_pct is not None and profit_pct <= LONG_STOP_LOSS_PCT:
                    exit_reasons[code] = "long_stop_loss"
                    stats["stop_loss_signals"] += 1
                elif has_limit_down_signal(code, pos, signal_panel):
                    exit_reasons[code] = "long_limit_down_exit"
                    stats["limit_down_exit_signals"] += 1
                elif has_bearish_volume_signal(code, pos, signal_panel):
                    exit_reasons[code] = "long_bearish_volume_exit"
                    stats["bearish_volume_exit_signals"] += 1
            for code, exit_reason in exit_reasons.items():
                cash, sold, reason = execute_sell(
                    date,
                    code,
                    holdings[code],
                    day_panel,
                    cash,
                    trades,
                    exit_reason,
                )
                if sold:
                    del holdings[code]
                    risk_exit_codes.add(code)
                    stats["sell_fills"] += 1
                    if exit_reason == "long_stop_loss":
                        stats["stop_loss_fills"] += 1
                    elif exit_reason == "long_limit_down_exit":
                        stats["limit_down_exit_fills"] += 1
                    elif exit_reason == "long_bearish_volume_exit":
                        stats["bearish_volume_exit_fills"] += 1
                    elif exit_reason == "long_regime_bear_exit":
                        stats["regime_bear_exit_fills"] += 1
                else:
                    stats["sell_delays"] += 1

        if i > 0:
            signal_date = all_dates[i - 1]
            stats["signal_days"] += 1
            market_regime_name, regime_snapshot = get_market_regime(market_regime, signal_date)
            short_drop_blocked, short_drop_reason, short_drop_snapshot = market_short_drop_blocks_buy(market, signal_date)
            regime_blocked = MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
            if regime_blocked:
                stats["regime_bear_block_days"] += 1
            probe_open = (
                BEAR_PROBE_BUY_ENABLED
                and regime_blocked
                and not short_drop_blocked
                and bool(regime_snapshot.get("bear_probe_market_ok", False))
            )
            if short_drop_blocked or (regime_blocked and not probe_open):
                stats["market_block_days"] += 1
                if short_drop_reason in {"missing_market", "missing_market_history"}:
                    stats["missing_market_days"] += 1
                market_reason = "market_regime_bear" if regime_blocked and not short_drop_blocked else short_drop_reason
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": market_reason,
                    "market_regime": market_regime_name,
                    "candidate_count": 0,
                    "bought_count": 0,
                    "market_ret_5": round(short_drop_snapshot.get("market_ret_5", float("nan")), 4),
                    "market_dd_20": round(short_drop_snapshot.get("market_dd_20", float("nan")), 4),
                    "market_dd_252": round(regime_snapshot.get("market_dd_252", float("nan")), 4),
                    "breadth_above_bbi": round(regime_snapshot.get("breadth_above_bbi", float("nan")), 4),
                    "breadth_change_5": round(regime_snapshot.get("breadth_change_5", float("nan")), 4),
                    "bear_probe_market_ok": bool(regime_snapshot.get("bear_probe_market_ok", False)),
                    "cash": round(cash, 2),
                })
            else:
                signal_panel = get_day_panel(panel, panel_by_date, signal_date)
                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)
                candidates = apply_dc_segment_crash_filter(
                    candidates,
                    signal_date,
                    dc_segment_members,
                    dc_segment_features,
                    diagnostics=stats,
                ).reset_index(drop=True)
                candidates = apply_dc_segment_score_boost(
                    candidates,
                    signal_date,
                    dc_segment_members,
                    dc_segment_features,
                ).reset_index(drop=True)
                candidates = apply_weak_lowvol_mom_filter(
                    candidates,
                    market_regime_name,
                    regime_snapshot,
                    diagnostics=stats,
                ).reset_index(drop=True)
                candidates["rank"] = np.arange(1, len(candidates) + 1)
                candidates["signal_date"] = str(signal_date)[:10]
                candidates["rebalance_date"] = str(date)[:10]
                score_cols = [
                    "signal_date", "rebalance_date", "rank", "ts_code", "name", "score",
                    "close",
                    "above_ratio_21", "above_ratio_63", "above_ratio_126",
                    "avg_distance_63", "high_pos_21", "high_pos_63", "range_pos_63",
                    "recent_limit_down_20", "recent_limit_up_20", "recent_limit_up_63",
                    "turnover_rate_ma20", "turnover_rate_max20", "volume_ratio_max20",
                    "lhb_count_20", "hot_money_risk_hits",
                    "hm_limit_up_20_flag", "hm_limit_up_63_flag", "hm_turnover_ma20_flag",
                    "hm_turnover_max20_flag", "hm_volume_ratio_max20_flag", "hm_lhb_count20_flag",
                    "ret_21", "ret_63", "ret_126",
                    "ma20_qfq", "ma20_slope_10", "early_weakness_downtrend",
                    "up_accel_exhaustion", "bear_down_accel_risk", "accel_exhaustion_forbid_buy",
                    "bbi_slope_5", "ret_5_probe", "bear_probe_stock_ok",
                    "positive_ret_ratio_63", "market_ret_63",
                    "volatility_63", "amount_ma20", "circ_mv_ma20", "pullback_63", "strong_trend",
                ]
                score_rows.extend(candidates[score_cols].head(100).to_dict("records"))
                bought_count = 0
                candidate_by_code = candidates.set_index("ts_code", drop=False)
                rank_stale_exit_reasons = {}
                for code in list(holdings):
                    if code in risk_exit_codes or code not in day_panel.index:
                        continue
                    pos = holdings[code]
                    if pos.get("pending_sell"):
                        continue
                    profit_pct = calc_position_profit_pct(code, pos, signal_panel)
                    if should_rank_stale_exit(pos, profit_pct, candidate_by_code, code):
                        rank_stale_exit_reasons[code] = "long_rank_stale_exit"
                        stats["rank_stale_exit_signals"] += 1
                for code, exit_reason in rank_stale_exit_reasons.items():
                    cash, sold, reason = execute_sell(date, code, holdings[code], day_panel, cash, trades, exit_reason)
                    if sold:
                        del holdings[code]
                        risk_exit_codes.add(code)
                        stats["sell_fills"] += 1
                        stats["rank_stale_exit_fills"] += 1
                    else:
                        stats["sell_delays"] += 1
                if not probe_open:
                    for code in list(holdings):
                        if code in risk_exit_codes or code not in candidate_by_code.index or code not in day_panel.index:
                            continue
                        pos = holdings[code]
                        if pos.get("pending_sell") or not can_add_position(code, pos, signal_panel, market_regime_name):
                            continue
                        step_index_before_add = int(pos.get("step_index", 0))
                        target_amount = next_position_step(pos)
                        if target_amount is None:
                            continue
                        current_nav = cash + sum(mark_position(c, p, signal_panel) for c, p in holdings.items())
                        is_extra_winner_add = is_pure_bull_extra_step(step_index_before_add)
                        if is_extra_winner_add:
                            stats["pure_bull_extra_add_signals"] += 1
                            if not can_use_pure_bull_extra_add(step_index_before_add, market_regime_name):
                                continue
                        exposure_limit = calc_pure_bull_extra_exposure_limit(
                            current_nav,
                            market_regime_name,
                            is_extra_winner_add,
                        )
                        available_exposure = exposure_limit - calc_total_exposure(holdings)
                        target_amount = min(target_amount, available_exposure)
                        if target_amount < 100:
                            continue
                        buy_reason = "pure_bull_extra_add" if is_extra_winner_add else "long_add_buy"
                        cash, bought, reason = execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, buy_reason)
                        if bought:
                            if is_extra_winner_add:
                                stats["pure_bull_extra_add_fills"] += 1
                                stats["pure_bull_extra_add_amount"] += float(trades[-1].get("amount", 0.0))
                                holdings[code]["pure_bull_extra_amount"] = (
                                    float(holdings[code].get("pure_bull_extra_amount", 0.0)) + float(trades[-1].get("amount", 0.0))
                                )
                            bought_count += 1
                            stats["buy_fills"] += 1
                            stats["add_buy_fills"] += 1
                        else:
                            stats["buy_skips"] += 1

                pullback_threshold, strong_pullback_threshold = regime_pullback_thresholds(market_regime_name)
                if probe_open:
                    stats["bear_probe_signal_days"] += 1
                    candidates = candidates[candidates["bear_probe_stock_ok"].fillna(False)].copy()
                    pullback_threshold = min(pullback_threshold, -0.02)
                    strong_pullback_threshold = min(strong_pullback_threshold, -0.015)
                entry_candidates = candidates[
                    candidates["pullback_63"].notna()
                    & (
                        (
                            candidates["strong_trend"].fillna(False)
                            & (candidates["pullback_63"] <= strong_pullback_threshold)
                        )
                        | (
                            ~candidates["strong_trend"].fillna(False)
                            & (candidates["pullback_63"] <= pullback_threshold)
                        )
                    )
                ]
                target_codes = list(entry_candidates["ts_code"].head(KEEP_TOP_N))
                for code in target_codes:
                    if len(holdings) >= LONG_MAX_HOLDINGS:
                        break
                    if code in holdings or code in risk_exit_codes or code not in day_panel.index:
                        continue
                    available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)
                    if probe_open:
                        target_amount = calc_bear_probe_target_amount(
                            float(LONG_POSITION_STEPS[0]),
                            cash,
                            calc_bear_probe_exposure(holdings),
                        )
                    else:
                        target_amount = min(float(LONG_POSITION_STEPS[0]), available_exposure)
                    target_amount = min(target_amount, available_exposure)
                    if target_amount < 100:
                        break
                    buy_reason = "bear_probe_initial_buy" if probe_open else "long_initial_buy"
                    cash, bought, reason = execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, buy_reason)
                    if bought:
                        bought_count += 1
                        stats["buy_fills"] += 1
                        if probe_open:
                            holdings[code]["probe_entry"] = True
                            stats["bear_probe_buys"] += 1
                    else:
                        stats["buy_skips"] += 1
                rebalance_log.append({
                    "date": str(date)[:10],
                    "signal_date": str(signal_date)[:10],
                    "market_reason": short_drop_reason,
                    "market_regime": market_regime_name,
                    "candidate_count": int(len(candidates)),
                    "entry_candidate_count": int(len(entry_candidates)),
                    "bought_count": int(bought_count),
                    "market_ret_5": round(short_drop_snapshot.get("market_ret_5", float("nan")), 4),
                    "market_dd_20": round(short_drop_snapshot.get("market_dd_20", float("nan")), 4),
                    "market_dd_252": round(regime_snapshot.get("market_dd_252", float("nan")), 4),
                    "breadth_above_bbi": round(regime_snapshot.get("breadth_above_bbi", float("nan")), 4),
                    "breadth_change_5": round(regime_snapshot.get("breadth_change_5", float("nan")), 4),
                    "bear_probe_market_ok": bool(regime_snapshot.get("bear_probe_market_ok", False)),
                    "pullback_threshold": round(pullback_threshold, 4),
                    "strong_pullback_threshold": round(strong_pullback_threshold, 4),
                    "cash": round(cash, 2),
                })
            previous_market_regime_name = market_regime_name

        nav = cash + sum(mark_position(c, p, day_panel) for c, p in holdings.items())
        nav_rows.append({"date": str(date)[:10], "nav": round(nav, 2), "cash": round(cash, 2), "holdings": len(holdings)})
        position_rows.extend(build_position_daily_rows(date, holdings))

    nav_df = pd.DataFrame(nav_rows)
    total_ret = nav_df["nav"].iloc[-1] / INIT_CASH - 1.0
    days = max((pd.Timestamp(nav_df["date"].iloc[-1]) - pd.Timestamp(nav_df["date"].iloc[0])).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    max_dd = calc_max_drawdown(nav_df)
    stats.update({
        "start_date": str(nav_df["date"].iloc[0]),
        "end_date": str(nav_df["date"].iloc[-1]),
        "init_cash": INIT_CASH,
        "final_nav": float(nav_df["nav"].iloc[-1]),
        "total_return_pct": round(total_ret * 100.0, 4),
        "annual_return_pct": round(annual_ret * 100.0, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "calmar_ratio": round((annual_ret * 100.0) / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "trade_records": len(trades),
    })
    return nav_df, pd.DataFrame(trades), pd.DataFrame(rebalance_log), pd.DataFrame(score_rows), pd.DataFrame(position_rows), holdings, stats


def write_last_holdings(holdings):
    holdings_out = {
        code: {
            "shares": round(float(pos.get("shares", 0.0)), 4),
            "cost_price": round(float(pos.get("cost_price", 0.0)), 4),
            "last_price": round(float(pos.get("last_price", pos.get("cost_price", 0.0))), 4),
            "name": pos.get("name", code),
            "pending_sell": bool(pos.get("pending_sell", False)),
            "pending_reason": pos.get("pending_reason", ""),
            "buy_date": pos.get("buy_date", ""),
            "invested_amount": round(float(pos.get("invested_amount", 0.0)), 2),
            "step_index": int(pos.get("step_index", 0)),
        }
        for code, pos in holdings.items()
    }
    LAST_HOLDINGS_PATH.write_text(
        json.dumps(holdings_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not PANEL_PATH.exists():
        raise FileNotFoundError(f"Missing {PANEL_PATH}. Run 10_prepare_data.py first.")
    try:
        panel = pd.read_parquet(PANEL_PATH, columns=PANEL_COLUMNS)
    except Exception as exc:
        raise RuntimeError(
            f"{PANEL_PATH} is missing required v8 columns. "
            "Run 10_prepare_data.py again before 20_run_backtest.py."
        ) from exc
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = load_market_index()
    nav_df, trades_df, rebalance_df, scores_df, position_df, holdings, stats = run_backtest(panel, market, args.start, args.end)

    nav_df.to_csv(NAV_SERIES_PATH, index=False)
    trades_df.to_csv(TRADE_RECORDS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    position_df.to_csv(POSITION_DAILY_PATH, index=False)
    rebalance_df.to_csv(REBALANCE_LOG_PATH, index=False)
    scores_df.to_csv(SCORES_PATH, index=False)
    write_last_holdings(holdings)
    SUMMARY_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Backtest done. Final NAV: {stats['final_nav']:,.2f}")
    print(f"Annual return: {stats['annual_return_pct']:.2f}%  Max DD: {stats['max_drawdown_pct']:.2f}%")
    print(f"Market blocks: {stats['market_block_days']}  Trades: {stats['trade_records']}")


if __name__ == "__main__":
    main()

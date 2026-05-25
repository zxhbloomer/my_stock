import numpy as np
import pandas as pd


def validate_complete_trade_dates(open_dates, data_dates, allowed_missing=None):
    allowed_missing = set(allowed_missing or [])
    open_set = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in open_dates}
    data_set = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in data_dates}
    return sorted(d for d in open_set - data_set if d not in allowed_missing)


def _zscore_by_date(frame, value_col, out_col):
    values = pd.to_numeric(frame[value_col], errors="coerce")
    means = values.groupby(frame["trade_date"]).transform("mean")
    stds = values.groupby(frame["trade_date"]).transform(lambda s: s.std(ddof=0)).replace(0, np.nan)
    frame[out_col] = ((values - means) / stds).fillna(0.0)
    return frame


def build_dc_segment_features(dc_daily):
    required = {"ts_code", "trade_date", "close", "amount"}
    missing = required - set(dc_daily.columns)
    if missing:
        raise ValueError(f"dc_daily missing columns: {sorted(missing)}")

    data = dc_daily[list(required)].copy()
    data = data.rename(columns={"ts_code": "segment_code"})
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    data = data.dropna(subset=["segment_code", "trade_date", "close"]).sort_values(["segment_code", "trade_date"])

    grouped = data.groupby("segment_code", sort=False)
    data["seg_ret_5"] = grouped["close"].pct_change(5)
    data["seg_ret_20"] = grouped["close"].pct_change(20)
    data["seg_ret_60"] = grouped["close"].pct_change(60)
    rolling_high = grouped["close"].transform(lambda s: s.rolling(20, min_periods=5).max())
    data["seg_dd_20"] = data["close"] / rolling_high - 1.0
    data["seg_amount_rank_pct"] = data.groupby("trade_date")["amount"].rank(pct=True)

    for col in ["seg_ret_20", "seg_ret_60", "seg_amount_rank_pct"]:
        data[col] = data[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        data = _zscore_by_date(data, col, f"{col}_z")

    data["segment_score"] = (
        0.45 * data["seg_ret_60_z"]
        + 0.35 * data["seg_ret_20_z"]
        + 0.20 * data["seg_amount_rank_pct_z"]
    ).clip(-3.0, 3.0)
    data["segment_mainline"] = (
        (data["segment_score"] >= 0.75)
        & (data["seg_ret_20"].fillna(0.0) > 0.0)
        & (data["seg_ret_60"].fillna(0.0) > 0.0)
    )
    data["segment_crash"] = (
        (data["seg_ret_20"].fillna(0.0) <= -0.08)
        | (data["seg_dd_20"].fillna(0.0) <= -0.12)
    )
    return data[
        [
            "trade_date",
            "segment_code",
            "seg_ret_5",
            "seg_ret_20",
            "seg_ret_60",
            "seg_dd_20",
            "seg_amount_rank_pct",
            "segment_score",
            "segment_mainline",
            "segment_crash",
        ]
    ].copy()


def _member_date_for_signal(signal_date, members, member_lag_days=0):
    signal_date = pd.Timestamp(signal_date)
    member_dates = sorted(pd.to_datetime(members["trade_date"].dropna().unique()))
    available_dates = [d for d in member_dates if d <= signal_date]
    if len(available_dates) <= member_lag_days:
        return None
    return available_dates[-1 - member_lag_days]


def _day_exposure(signal_date, members, segment_features, member_lag_days=0):
    signal_date = pd.Timestamp(signal_date)
    member_date = _member_date_for_signal(signal_date, members, member_lag_days=member_lag_days)
    if member_date is None:
        return pd.DataFrame(columns=["ts_code", "best_segment_score", "has_segment_crash", "has_segment_mainline"])
    day_members = members[members["trade_date"].eq(member_date)][["con_code", "ts_code"]].copy()
    if day_members.empty:
        return pd.DataFrame(columns=["ts_code", "best_segment_score", "has_segment_crash", "has_segment_mainline"])
    day_members = day_members.rename(columns={"con_code": "ts_code", "ts_code": "segment_code"})
    day_features = segment_features[segment_features["trade_date"].eq(signal_date)].copy()
    merged = day_members.merge(day_features, on="segment_code", how="left")
    if merged.empty:
        return pd.DataFrame(columns=["ts_code", "best_segment_score", "has_segment_crash", "has_segment_mainline"])
    merged["segment_score"] = pd.to_numeric(merged["segment_score"], errors="coerce").fillna(0.0)
    merged["segment_crash"] = merged["segment_crash"].where(merged["segment_crash"].notna(), False).astype(bool)
    merged["segment_mainline"] = merged["segment_mainline"].where(merged["segment_mainline"].notna(), False).astype(bool)
    return merged.groupby("ts_code").agg(
        best_segment_score=("segment_score", "max"),
        has_segment_crash=("segment_crash", "max"),
        has_segment_mainline=("segment_mainline", "max"),
    ).reset_index()


def apply_dc_segment_score_boost(
    candidates,
    signal_date,
    members,
    segment_features,
    weight=0.10,
    mainline_bonus=0.05,
    member_lag_days=0,
):
    if candidates.empty:
        return candidates.copy()
    base = candidates.reset_index(drop=True).drop(
        columns=[
            "best_segment_score",
            "has_segment_crash",
            "has_segment_mainline",
            "segment_adjustment",
        ],
        errors="ignore",
    )
    out = base.merge(
        _day_exposure(signal_date, members, segment_features, member_lag_days=member_lag_days),
        on="ts_code",
        how="left",
    )
    out["best_segment_score"] = pd.to_numeric(out["best_segment_score"], errors="coerce").fillna(0.0)
    out["has_segment_mainline"] = out["has_segment_mainline"].where(out["has_segment_mainline"].notna(), False).astype(bool)
    out["segment_adjustment"] = (out["best_segment_score"].clip(-2.0, 2.0) * weight)
    out.loc[out["has_segment_mainline"], "segment_adjustment"] += mainline_bonus
    out["score"] = pd.to_numeric(out["score"], errors="coerce").fillna(0.0) + out["segment_adjustment"]
    return out.sort_values(["score", "best_segment_score"], ascending=[False, False]).reset_index(drop=True)


def filter_dc_segment_crash_candidates(candidates, signal_date, members, segment_features, member_lag_days=0):
    if candidates.empty:
        return candidates.copy()
    out = candidates.reset_index(drop=True).merge(
        _day_exposure(signal_date, members, segment_features, member_lag_days=member_lag_days),
        on="ts_code",
        how="left",
    )
    out["has_segment_crash"] = out["has_segment_crash"].where(out["has_segment_crash"].notna(), False).astype(bool)
    return out[~out["has_segment_crash"]].copy().reset_index(drop=True)


def stock_has_crash_segment(ts_code, signal_date, members, segment_features, member_lag_days=0):
    exposure = _day_exposure(signal_date, members, segment_features, member_lag_days=member_lag_days)
    row = exposure[exposure["ts_code"].eq(ts_code)]
    if row.empty:
        return False
    return bool(row.iloc[0].get("has_segment_crash", False))

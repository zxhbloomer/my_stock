import numpy as np
import pandas as pd


def _zscore_by_date(frame, value_col, out_col):
    values = pd.to_numeric(frame[value_col], errors="coerce")
    means = values.groupby(frame["trade_date"]).transform("mean")
    stds = values.groupby(frame["trade_date"]).transform(lambda s: s.std(ddof=0))
    frame[out_col] = ((values - means) / stds.replace(0, np.nan)).fillna(0.0)
    return frame


def build_sw_theme_features(sw_daily, short_window=21, mid_window=63, slope_window=20):
    required = {"ts_code", "trade_date", "name", "close"}
    missing = required - set(sw_daily.columns)
    if missing:
        raise ValueError(f"sw_daily missing columns: {sorted(missing)}")

    data = sw_daily[list(required)].copy()
    data = data.rename(columns={"ts_code": "theme_code", "name": "theme_name"})
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data = data.dropna(subset=["theme_code", "trade_date", "close"]).sort_values(["theme_code", "trade_date"])

    grouped = data.groupby("theme_code", sort=False)
    data["theme_ret_21"] = grouped["close"].pct_change(short_window)
    data["theme_ret_63"] = grouped["close"].pct_change(mid_window)
    ma = grouped["close"].transform(lambda s: s.rolling(slope_window, min_periods=max(2, slope_window // 2)).mean())
    data["theme_ma_slope_20"] = ma / ma.groupby(data["theme_code"], sort=False).shift(slope_window) - 1.0
    rolling_high = grouped["close"].transform(lambda s: s.rolling(short_window, min_periods=2).max())
    data["theme_dd_21"] = data["close"] / rolling_high - 1.0

    for col in ["theme_ret_21", "theme_ret_63", "theme_ma_slope_20"]:
        data[col] = data[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        data = _zscore_by_date(data, col, f"{col}_z")

    data["theme_score"] = (
        0.40 * data["theme_ret_63_z"]
        + 0.35 * data["theme_ret_21_z"]
        + 0.25 * data["theme_ma_slope_20_z"]
    ).clip(lower=-3.0, upper=3.0)
    data["theme_crash"] = (
        (data["theme_ret_21"] <= -0.08)
        | (data["theme_dd_21"] <= -0.15)
    )
    return data[
        [
            "trade_date",
            "theme_code",
            "theme_name",
            "theme_ret_21",
            "theme_ret_63",
            "theme_ma_slope_20",
            "theme_dd_21",
            "theme_score",
            "theme_crash",
        ]
    ].copy()


def build_stock_theme_map(index_member_all):
    required = {"ts_code", "l1_code", "l1_name", "is_new"}
    missing = required - set(index_member_all.columns)
    if missing:
        raise ValueError(f"index_member_all missing columns: {sorted(missing)}")
    data = index_member_all.copy()
    data = data[data["is_new"].fillna("Y").astype(str).str.upper().eq("Y")]
    data = data.dropna(subset=["ts_code", "l1_code"])
    data = data.sort_values(["ts_code", "l1_code"]).drop_duplicates("ts_code", keep="last")
    return data.rename(columns={"l1_code": "theme_code", "l1_name": "theme_name"})[
        ["ts_code", "theme_code", "theme_name"]
    ].copy()


def apply_theme_overlay_to_candidates(
    candidates,
    signal_date,
    stock_theme,
    theme_features,
    theme_weight=0.12,
    crash_penalty=0.35,
):
    if candidates.empty:
        return candidates.copy()

    signal_date = pd.Timestamp(signal_date)
    out = candidates.reset_index(drop=True).merge(stock_theme, on="ts_code", how="left", suffixes=("", "_map"))
    day_features = theme_features[theme_features["trade_date"].eq(signal_date)].copy()
    out = out.merge(day_features, on="theme_code", how="left", suffixes=("", "_feature"))

    for col, default in {
        "theme_score": 0.0,
        "theme_ret_21": 0.0,
        "theme_ret_63": 0.0,
        "theme_dd_21": 0.0,
    }.items():
        if col not in out.columns:
            out[col] = default
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(default)
    if "theme_crash" not in out.columns:
        out["theme_crash"] = False
    out["theme_crash"] = out["theme_crash"].where(out["theme_crash"].notna(), False).astype(bool)

    out["theme_adjustment"] = theme_weight * pd.to_numeric(out["theme_score"], errors="coerce").fillna(0.0)
    out.loc[out["theme_crash"].astype(bool), "theme_adjustment"] -= crash_penalty
    out["score"] = pd.to_numeric(out["score"], errors="coerce").fillna(0.0) + out["theme_adjustment"]
    return out.sort_values(
        ["score", "theme_score", "theme_ret_63"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def attach_theme_features(candidates, signal_date, stock_theme, theme_features):
    if candidates.empty:
        return candidates.copy()
    signal_date = pd.Timestamp(signal_date)
    out = candidates.reset_index(drop=True).merge(stock_theme, on="ts_code", how="left", suffixes=("", "_map"))
    day_features = theme_features[theme_features["trade_date"].eq(signal_date)].copy()
    out = out.merge(day_features, on="theme_code", how="left", suffixes=("", "_feature"))
    if "theme_crash" not in out.columns:
        out["theme_crash"] = False
    out["theme_crash"] = out["theme_crash"].where(out["theme_crash"].notna(), False).astype(bool)
    return out


def filter_theme_crash_candidates(candidates, signal_date, stock_theme, theme_features):
    out = attach_theme_features(candidates, signal_date, stock_theme, theme_features)
    if out.empty:
        return out
    return out[~out["theme_crash"]].copy().reset_index(drop=True)


def is_stock_theme_crash(ts_code, signal_date, stock_theme, theme_features):
    signal_date = pd.Timestamp(signal_date)
    mapping = stock_theme[stock_theme["ts_code"].eq(ts_code)]
    if mapping.empty:
        return False
    theme_code = mapping.iloc[0]["theme_code"]
    feature = theme_features[
        theme_features["trade_date"].eq(signal_date)
        & theme_features["theme_code"].eq(theme_code)
    ]
    if feature.empty:
        return False
    return bool(feature.iloc[0].get("theme_crash", False))

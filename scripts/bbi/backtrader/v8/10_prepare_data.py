import argparse
import datetime
import gc
import json
import shutil
import time

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from config import (
    BACKTEST_START_DATE,
    DB_URL,
    DC_SEGMENT_OVERLAY_ACTIVE_FROM,
    DC_SEGMENT_OVERLAY_ENABLED,
    DOWNTREND_MA_WINDOW,
    DOWNTREND_RET_WINDOW,
    DOWNTREND_SLOPE_WINDOW,
    END_DATE,
    EXCLUDE_CODE_PREFIXES,
    FILTER_MIN_AMOUNT,
    FILTER_MIN_CIRC_MV,
    FILTER_MIN_LIST_DAYS,
    HOT_MONEY_LHB_COUNT20_THRESHOLD,
    HOT_MONEY_LHB_LOOKBACK,
    HOT_MONEY_LIMIT_UP_20_THRESHOLD,
    HOT_MONEY_LIMIT_UP_63_THRESHOLD,
    HOT_MONEY_LIMIT_UP_LOOKBACK_MID,
    HOT_MONEY_LIMIT_UP_LOOKBACK_SHORT,
    HOT_MONEY_TURNOVER_LOOKBACK,
    HOT_MONEY_TURNOVER_MA20_THRESHOLD,
    HOT_MONEY_TURNOVER_MAX20_THRESHOLD,
    HOT_MONEY_VOLUME_RATIO_LOOKBACK,
    HOT_MONEY_VOLUME_RATIO_MAX20_THRESHOLD,
    LIQUIDITY_LOOKBACK,
    LONG_PULLBACK_LOOKBACK,
    LOOKBACK_LONG,
    LOOKBACK_MID,
    LOOKBACK_SHORT,
    MARKET_FILTER_ENABLED,
    MARKET_INDEX_CODE,
    MARKET_INDEX_NAME,
    MARKET_INDEX_PATH,
    MIN_HISTORY_ROWS,
    OUTPUT_DIR,
    PANEL_PATH,
    RECENT_HIGH_LOOKBACK,
    RECENT_HIGH_SHORT_LOOKBACK,
    RECENT_LIMIT_DOWN_LOOKBACK,
    SCHEMA,
    START_DATE,
    STAR_MARKET_ALLOW_FROM,
    STAR_MARKET_PREFIXES,
    STOCK_LIST_PATH,
)

FETCH_CHUNK_SIZE = 150
LOW_COUNT_RATIO = 0.8
DB_COMPLETENESS_TABLES = (
    {
        "table": "063_stk_factor_pro",
        "date_col": "trade_date",
        "where": "",
        "check_low_count": True,
    },
    {
        "table": "029_stk_limit",
        "date_col": "trade_date",
        "where": "",
        "check_low_count": True,
    },
    {
        "table": "137_idx_factor_pro",
        "date_col": "trade_date",
        "where": "ts_code = '000001.SH'",
        "check_low_count": False,
    },
    {
        "table": "098_dc_member",
        "date_col": "trade_date",
        "where": "",
        "check_low_count": False,
        "start_date": DC_SEGMENT_OVERLAY_ACTIVE_FROM,
        "enabled": DC_SEGMENT_OVERLAY_ENABLED,
    },
    {
        "table": "099_dc_daily",
        "date_col": "trade_date",
        "where": "",
        "check_low_count": True,
        "start_date": DC_SEGMENT_OVERLAY_ACTIVE_FROM,
        "enabled": DC_SEGMENT_OVERLAY_ENABLED,
    },
)


def fmt_seconds(seconds):
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m{sec:.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h{int(minutes)}m{sec:.1f}s"


def dataframe_memory_mb(df):
    if df is None or df.empty:
        return 0.0
    return float(df.memory_usage(deep=False).sum() / 1024 / 1024)


def log_step(message, start_time=None, total_start=None, df=None, extra=None):
    parts = [f"[v8-prepare] {message}"]
    if start_time is not None:
        parts.append(f"step={fmt_seconds(time.perf_counter() - start_time)}")
    if total_start is not None:
        parts.append(f"total={fmt_seconds(time.perf_counter() - total_start)}")
    if df is not None:
        parts.append(f"rows={len(df):,}")
        parts.append(f"mem_est={dataframe_memory_mb(df):.1f}MB")
    if extra:
        parts.append(extra)
    print(" | ".join(parts), flush=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=START_DATE, help="YYYY-MM-DD, include warmup")
    parser.add_argument("--backtest-start", default=BACKTEST_START_DATE, help="YYYY-MM-DD")
    parser.add_argument("--end", default=END_DATE, help="YYYY-MM-DD")
    parser.add_argument("--codes", default="", help="Comma-separated ts_code list for quick checks")
    return parser.parse_args()


def query_df(conn, sql, params=None):
    result = conn.execute(text(sql), params or {})
    return pd.DataFrame(result.fetchall(), columns=result.keys())


def format_compact_date(value):
    if value is None:
        return ""
    return pd.Timestamp(value).strftime("%Y%m%d")


def resolve_completeness_end_date(end_date, now=None):
    now = now or datetime.datetime.now()
    today = now.date()
    end_day = pd.Timestamp(end_date).date()
    if end_day >= today and now.time() < datetime.time(21, 0):
        return (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    return pd.Timestamp(end_date).strftime("%Y-%m-%d")


def analyze_daily_count_completeness(expected_dates, counts_by_date, low_count_ratio=LOW_COUNT_RATIO, check_low_count=True):
    missing_dates = []
    low_count_dates = []
    low_count_details = []
    previous_count = None
    for trade_date in expected_dates:
        count = int(counts_by_date.get(trade_date, 0))
        if count == 0:
            missing_dates.append(trade_date)
            continue
        if check_low_count and previous_count and count < previous_count * low_count_ratio:
            low_count_dates.append(trade_date)
            low_count_details.append({
                "date": trade_date,
                "count": count,
                "previous_count": previous_count,
            })
        previous_count = count
    return {
        "missing_dates": missing_dates,
        "low_count_dates": low_count_dates,
        "low_count_details": low_count_details,
    }


def fetch_sse_trade_dates(conn, start_date, end_date):
    rows = conn.execute(text(f"""
        SELECT cal_date
        FROM {SCHEMA}."003_trade_cal"
        WHERE exchange = 'SSE'
          AND is_open = 1
          AND cal_date >= CAST(:start_date AS date)
          AND cal_date <= CAST(:end_date AS date)
        ORDER BY cal_date
    """), {"start_date": start_date, "end_date": end_date}).fetchall()
    return [format_compact_date(row[0]) for row in rows if row and row[0]]


def fetch_daily_counts(conn, table, date_col, start_date, end_date, where=""):
    where_clause = f" AND {where}" if where else ""
    rows = conn.execute(text(f"""
        SELECT "{date_col}", COUNT(*) AS row_count
        FROM {SCHEMA}."{table}"
        WHERE "{date_col}" >= CAST(:start_date AS date)
          AND "{date_col}" <= CAST(:end_date AS date)
          {where_clause}
        GROUP BY "{date_col}"
    """), {"start_date": start_date, "end_date": end_date}).fetchall()
    return {format_compact_date(row[0]): int(row[1]) for row in rows if row and row[0]}


def format_db_completeness_error(results):
    lines = [
        "Database completeness check failed before v8 prepare.",
        "Please fix database gaps first, for example via UI: 智能增量 -> 全部日期.",
    ]
    for result in results:
        missing = result.get("missing_dates", [])
        low_count = result.get("low_count_dates", [])
        if not missing and not low_count:
            continue
        lines.append("")
        lines.append(f"{result['table']}:")
        lines.append(
            "- missing trading days: {}, examples: {}".format(
                len(missing),
                ", ".join(missing[:10]) if missing else "-",
            )
        )
        detail_text = "-"
        details = result.get("low_count_details", [])
        if details:
            detail_text = ", ".join(
                "{}(count={}, previous={})".format(item["date"], item["count"], item["previous_count"])
                for item in details[:10]
            )
        lines.append(
            "- low-count trading days: {}, examples: {}".format(
                len(low_count),
                detail_text,
            )
        )
    return "\n".join(lines)


def validate_database_completeness(conn, start_date, end_date):
    expected_dates = fetch_sse_trade_dates(conn, start_date, end_date)
    if not expected_dates:
        raise RuntimeError(
            f"No SSE open trading days found in 003_trade_cal for {start_date}~{end_date}."
        )
    results = []
    for spec in DB_COMPLETENESS_TABLES:
        if not bool(spec.get("enabled", True)):
            continue
        spec_start_date = max(pd.Timestamp(start_date), pd.Timestamp(spec.get("start_date", start_date)))
        if spec_start_date > pd.Timestamp(end_date):
            continue
        spec_start_date_text = spec_start_date.strftime("%Y-%m-%d")
        expected_dates_for_spec = fetch_sse_trade_dates(conn, spec_start_date_text, end_date)
        counts = fetch_daily_counts(
            conn,
            spec["table"],
            spec["date_col"],
            spec_start_date_text,
            end_date,
            spec.get("where", ""),
        )
        result = analyze_daily_count_completeness(
            expected_dates_for_spec,
            counts,
            LOW_COUNT_RATIO,
            bool(spec.get("check_low_count", True)),
        )
        result["table"] = spec["table"]
        result["start_date"] = spec_start_date_text
        results.append(result)
    failures = [
        result for result in results
        if result["missing_dates"] or result["low_count_dates"]
    ]
    if failures:
        raise RuntimeError(format_db_completeness_error(failures))
    return results


def filter_point_in_time_universe(stocks, start_date, end_date, requested_codes):
    stocks = stocks.copy()
    stocks["list_date"] = pd.to_datetime(stocks["list_date"], errors="coerce")
    stocks["delist_date"] = pd.to_datetime(stocks["delist_date"], errors="coerce")
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    stocks = stocks[
        stocks["list_date"].notna()
        & (stocks["list_date"] <= end_ts)
        & (stocks["delist_date"].isna() | (stocks["delist_date"] >= start_ts))
    ]
    ts_code = stocks["ts_code"].astype(str)
    for prefix in EXCLUDE_CODE_PREFIXES:
        stocks = stocks[~ts_code.str.startswith(prefix)]
        ts_code = stocks["ts_code"].astype(str)
    if end_ts < pd.Timestamp(STAR_MARKET_ALLOW_FROM):
        stocks = stocks[~ts_code.str.startswith(STAR_MARKET_PREFIXES)]
    if requested_codes:
        stocks = stocks[stocks["ts_code"].isin(requested_codes)]
    return stocks.reset_index(drop=True)


def compute_point_in_time_eligibility(panel):
    listed_on_trade_date = (
        panel["list_date"].notna()
        & (panel["trade_date"] >= panel["list_date"])
        & (panel["delist_date"].isna() | (panel["trade_date"] <= panel["delist_date"]))
    )
    star_market_allowed = (
        ~panel["ts_code"].astype(str).str.startswith(STAR_MARKET_PREFIXES)
        | (panel["trade_date"] >= pd.Timestamp(STAR_MARKET_ALLOW_FROM))
    )
    return (
        listed_on_trade_date
        & star_market_allowed
        & panel["is_listed_long_enough"]
        & panel["is_liquid"]
        & ~panel["is_st"]
        & ~panel["is_suspended"]
        & panel["above_ratio_126"].notna()
    )


def rolling_mean_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .mean()
        .reset_index(level=0, drop=True)
    )


def rolling_std_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .std()
        .reset_index(level=0, drop=True)
    )


def rolling_sum_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .sum()
        .reset_index(level=0, drop=True)
    )


def rolling_max_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .max()
        .reset_index(level=0, drop=True)
    )


def rolling_min_by_code(panel, column, window):
    return (
        panel.groupby("ts_code", sort=False)[column]
        .rolling(window, min_periods=window)
        .min()
        .reset_index(level=0, drop=True)
    )


def add_strength_features(panel):
    step_start = time.perf_counter()
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    log_step("feature sort done", step_start, df=panel)
    grouped = panel.groupby("ts_code", sort=False)
    step_start = time.perf_counter()
    panel["above_bbi"] = panel["close_qfq"] > panel["bbi_qfq"]
    panel["bbi_distance"] = panel["close_qfq"] / panel["bbi_qfq"] - 1.0
    panel["ret_21"] = grouped["close_qfq"].pct_change(LOOKBACK_SHORT)
    panel["ret_63"] = grouped["close_qfq"].pct_change(LOOKBACK_MID)
    panel["ret_126"] = grouped["close_qfq"].pct_change(LOOKBACK_LONG)
    panel["ma20_qfq"] = rolling_mean_by_code(panel, "close_qfq", DOWNTREND_MA_WINDOW)
    panel["ma20_slope_10"] = (
        grouped["ma20_qfq"].pct_change(DOWNTREND_SLOPE_WINDOW, fill_method=None)
        / DOWNTREND_SLOPE_WINDOW
    )
    downtrend_ret = grouped["close_qfq"].pct_change(DOWNTREND_RET_WINDOW)
    panel["early_weakness_downtrend"] = (
        (panel["close_qfq"] < panel["ma20_qfq"])
        & (panel["ma20_slope_10"] < 0)
        & (downtrend_ret < 0)
    )
    ma60_accel = rolling_mean_by_code(panel, "close_qfq", 30)
    ret_5_accel = grouped["close_qfq"].pct_change(5, fill_method=None)
    ret_10_accel = grouped["close_qfq"].pct_change(10, fill_method=None)
    ret_20_accel = grouped["close_qfq"].pct_change(20, fill_method=None)
    slope_5_accel = ret_5_accel / 5.0
    slope_10_accel = ret_10_accel / 10.0
    high_20_accel = rolling_max_by_code(panel, "close_qfq", 20)
    low_20_accel = rolling_min_by_code(panel, "close_qfq", 20)
    range_20_accel = high_20_accel / low_20_accel - 1.0
    amount_ratio_5_20_accel = (
        rolling_mean_by_code(panel, "amount", 5)
        / rolling_mean_by_code(panel, "amount", 20)
    )
    prior_accel = (
        (ret_10_accel >= 0.05)
        | (ret_10_accel.groupby(panel["ts_code"], sort=False).shift(5) >= 0.18)
        | (range_20_accel.groupby(panel["ts_code"], sort=False).shift(1) >= 0.28)
    )
    recent_exhaustion = (
        (ret_5_accel <= -0.06)
        | (panel["close_qfq"] / high_20_accel - 1.0 <= -0.12)
    )
    panel["up_accel_exhaustion"] = (
        prior_accel
        & recent_exhaustion
        & (amount_ratio_5_20_accel.fillna(0.0) >= 1.15)
        & (panel["close_qfq"] > ma60_accel * 0.80)
    )
    panel["bear_down_accel_risk"] = (
        (panel["close_qfq"] < panel["ma20_qfq"])
        & (panel["ma20_qfq"] <= ma60_accel * 1.05)
        & (ret_20_accel < -0.10)
        & (ret_5_accel < -0.04)
        & (slope_5_accel < slope_10_accel)
    )
    panel["accel_exhaustion_forbid_buy"] = (
        panel["early_weakness_downtrend"].fillna(False)
        | panel["up_accel_exhaustion"].fillna(False)
        | panel["bear_down_accel_risk"].fillna(False)
    )
    panel["high_qfq_63"] = rolling_max_by_code(panel, "close_qfq", LONG_PULLBACK_LOOKBACK)
    panel["pullback_63"] = panel["close_qfq"] / panel["high_qfq_63"] - 1.0
    log_step("feature returns done", step_start, df=panel)
    step_start = time.perf_counter()
    panel["is_limit_down_close"] = (
        panel["down_limit"].notna()
        & (panel["down_limit"] > 0)
        & (panel["close"] <= panel["down_limit"] + 1e-6)
    )
    panel["recent_limit_down_20"] = rolling_sum_by_code(
        panel,
        "is_limit_down_close",
        RECENT_LIMIT_DOWN_LOOKBACK,
    )
    log_step("feature recent limit-down done", step_start, df=panel)
    step_start = time.perf_counter()
    panel["is_limit_up_close"] = (
        panel["up_limit"].notna()
        & (panel["up_limit"] > 0)
        & (panel["close"] >= panel["up_limit"] - 1e-6)
    )
    panel["recent_limit_up_20"] = rolling_sum_by_code(
        panel,
        "is_limit_up_close",
        HOT_MONEY_LIMIT_UP_LOOKBACK_SHORT,
    )
    panel["recent_limit_up_63"] = rolling_sum_by_code(
        panel,
        "is_limit_up_close",
        HOT_MONEY_LIMIT_UP_LOOKBACK_MID,
    )
    panel["turnover_rate_ma20"] = rolling_mean_by_code(
        panel,
        "turnover_rate",
        HOT_MONEY_TURNOVER_LOOKBACK,
    )
    panel["turnover_rate_max20"] = rolling_max_by_code(
        panel,
        "turnover_rate",
        HOT_MONEY_TURNOVER_LOOKBACK,
    )
    panel["volume_ratio_max20"] = rolling_max_by_code(
        panel,
        "volume_ratio",
        HOT_MONEY_VOLUME_RATIO_LOOKBACK,
    )
    panel["lhb_count_20"] = rolling_sum_by_code(
        panel,
        "is_lhb",
        HOT_MONEY_LHB_LOOKBACK,
    )
    hot_money_flags = [
        panel["recent_limit_up_20"] >= HOT_MONEY_LIMIT_UP_20_THRESHOLD,
        panel["recent_limit_up_63"] >= HOT_MONEY_LIMIT_UP_63_THRESHOLD,
        panel["turnover_rate_ma20"] >= HOT_MONEY_TURNOVER_MA20_THRESHOLD,
        panel["turnover_rate_max20"] >= HOT_MONEY_TURNOVER_MAX20_THRESHOLD,
        panel["volume_ratio_max20"] >= HOT_MONEY_VOLUME_RATIO_MAX20_THRESHOLD,
        panel["lhb_count_20"] >= HOT_MONEY_LHB_COUNT20_THRESHOLD,
    ]
    hot_money_flag_names = [
        "hm_limit_up_20_flag",
        "hm_limit_up_63_flag",
        "hm_turnover_ma20_flag",
        "hm_turnover_max20_flag",
        "hm_volume_ratio_max20_flag",
        "hm_lhb_count20_flag",
    ]
    for name, values in zip(hot_money_flag_names, hot_money_flags):
        panel[name] = values.fillna(False)
    panel["hot_money_risk_hits"] = panel[hot_money_flag_names].sum(axis=1).astype("int16")
    log_step("feature hot-money risk done", step_start, df=panel)
    step_start = time.perf_counter()
    panel["above_ratio_21"] = rolling_mean_by_code(panel, "above_bbi", LOOKBACK_SHORT)
    panel["above_ratio_63"] = rolling_mean_by_code(panel, "above_bbi", LOOKBACK_MID)
    panel["above_ratio_126"] = rolling_mean_by_code(panel, "above_bbi", LOOKBACK_LONG)
    panel["below_ratio_63"] = 1.0 - panel["above_ratio_63"]
    panel["avg_distance_21"] = rolling_mean_by_code(panel, "bbi_distance", LOOKBACK_SHORT)
    panel["avg_distance_63"] = rolling_mean_by_code(panel, "bbi_distance", LOOKBACK_MID)
    log_step("feature rolling means done", step_start, df=panel)
    step_start = time.perf_counter()
    high_close_21 = rolling_max_by_code(panel, "close_qfq", RECENT_HIGH_SHORT_LOOKBACK)
    panel["high_pos_21"] = panel["close_qfq"] / high_close_21
    high_close = rolling_max_by_code(panel, "close_qfq", RECENT_HIGH_LOOKBACK)
    low_close = rolling_min_by_code(panel, "close_qfq", RECENT_HIGH_LOOKBACK)
    range_width = high_close - low_close
    panel["high_pos_63"] = panel["close_qfq"] / high_close
    panel["range_pos_63"] = np.where(
        range_width > 0,
        (panel["close_qfq"] - low_close) / range_width,
        np.nan,
    )
    log_step("feature recent-high position done", step_start, df=panel)
    step_start = time.perf_counter()
    panel["_daily_return"] = grouped["close_qfq"].pct_change()
    panel["volatility_63"] = rolling_std_by_code(panel, "_daily_return", LOOKBACK_MID)
    panel["amount_ma20"] = rolling_mean_by_code(panel, "amount", LIQUIDITY_LOOKBACK)
    panel["circ_mv_ma20"] = rolling_mean_by_code(panel, "circ_mv", LIQUIDITY_LOOKBACK)
    log_step("feature volatility/liquidity done", step_start, df=panel)
    return panel.drop(columns=["_daily_return"])


def chunks(values, size):
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i:i + size]


def reset_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except PermissionError as exc:
            raise PermissionError(
                f"Cannot clean output item because it is in use: {path}. "
                "Close the report browser/server or any program using this file, then retry."
            ) from exc


def main():
    total_start = time.perf_counter()
    args = parse_args()
    start_date = args.start or START_DATE
    backtest_start = args.backtest_start or BACKTEST_START_DATE
    end_date = args.end or END_DATE or datetime.date.today().strftime("%Y-%m-%d")
    completeness_end_date = resolve_completeness_end_date(end_date)
    requested_codes = {c.strip() for c in args.codes.split(",") if c.strip()}

    log_step(
        "start",
        total_start=total_start,
        extra=(
            f"date_range={start_date}~{end_date}, "
            f"completeness_range={start_date}~{completeness_end_date}, "
            f"chunk_size={FETCH_CHUNK_SIZE}"
        ),
    )
    step_start = time.perf_counter()
    reset_output_dir()
    log_step("output cleaned", step_start, total_start)

    step_start = time.perf_counter()
    engine = create_engine(DB_URL, poolclass=NullPool)
    log_step("db engine created", step_start, total_start)

    step_start = time.perf_counter()
    with engine.connect() as conn:
        db_quality = validate_database_completeness(conn, start_date, completeness_end_date)
    log_step(
        "database completeness checked",
        step_start,
        total_start,
        extra="tables={}".format(",".join(item["table"] for item in db_quality)),
    )

    step_start = time.perf_counter()
    with engine.connect() as conn:
        stock_sql = f"""
            SELECT ts_code, name, list_date, delist_date, market, exchange, list_status
            FROM {SCHEMA}."001_stock_basic"
        """
        stocks = query_df(conn, stock_sql)
    log_step("stock universe query done", step_start, total_start, stocks)

    step_start = time.perf_counter()
    stocks = filter_point_in_time_universe(stocks, start_date, end_date, requested_codes)
    stocks.to_csv(STOCK_LIST_PATH, index=False)
    valid_codes = set(stocks["ts_code"])
    log_step("stock universe filtered", step_start, total_start, stocks, f"stocks={len(stocks):,}")

    factor_sql = f"""
            SELECT
                f.ts_code, f.trade_date,
                f.open, f.high, f.low, f.close, f.pre_close,
                f.open_qfq, f.close_qfq, f.bbi_qfq,
                f.amount, f.circ_mv, f.adj_factor, f.turnover_rate, f.volume_ratio
            FROM {SCHEMA}."063_stk_factor_pro" f
            WHERE f.trade_date >= CAST(:start_date AS date)
              AND f.trade_date <= CAST(:end_date AS date)
              AND f.ts_code = ANY(:codes)
              AND f.bbi_qfq IS NOT NULL
            ORDER BY f.ts_code, f.trade_date
        """
    limit_sql = f"""
            SELECT ts_code, trade_date, up_limit, down_limit
            FROM {SCHEMA}."029_stk_limit"
            WHERE trade_date >= CAST(:start_date AS date)
              AND trade_date <= CAST(:end_date AS date)
              AND ts_code = ANY(:codes)
        """
    st_sql = f"""
            SELECT DISTINCT ts_code, trade_date, TRUE AS is_st
            FROM {SCHEMA}."004_stock_st"
            WHERE trade_date >= CAST(:start_date AS date)
              AND trade_date <= CAST(:end_date AS date)
              AND ts_code = ANY(:codes)
        """
    suspend_sql = f"""
            SELECT DISTINCT ts_code, trade_date, TRUE AS is_suspended
            FROM {SCHEMA}."030_suspend_d"
            WHERE suspend_type = 'S'
              AND trade_date >= CAST(:start_date AS date)
              AND trade_date <= CAST(:end_date AS date)
              AND ts_code = ANY(:codes)
        """
    lhb_sql = f"""
            SELECT DISTINCT ts_code, trade_date, TRUE AS is_lhb
            FROM {SCHEMA}."088_top_list"
            WHERE trade_date >= CAST(:start_date AS date)
              AND trade_date <= CAST(:end_date AS date)
              AND ts_code = ANY(:codes)
        """
    frames = []
    limit_frames = []
    st_frames = []
    suspend_frames = []
    lhb_frames = []
    code_list = sorted(valid_codes)
    step_start = time.perf_counter()
    with engine.connect() as conn:
        for idx, code_chunk in enumerate(chunks(code_list, FETCH_CHUNK_SIZE), 1):
            chunk_start = time.perf_counter()
            params = {"start_date": start_date, "end_date": end_date, "codes": code_chunk}
            sql_start = time.perf_counter()
            frame = query_df(conn, factor_sql, params)
            factor_seconds = time.perf_counter() - sql_start
            if not frame.empty:
                frames.append(frame)
            sql_start = time.perf_counter()
            lim = query_df(conn, limit_sql, params)
            limit_seconds = time.perf_counter() - sql_start
            if not lim.empty:
                limit_frames.append(lim)
            sql_start = time.perf_counter()
            st = query_df(conn, st_sql, params)
            st_seconds = time.perf_counter() - sql_start
            if not st.empty:
                st_frames.append(st)
            sql_start = time.perf_counter()
            sus = query_df(conn, suspend_sql, params)
            suspend_seconds = time.perf_counter() - sql_start
            if not sus.empty:
                suspend_frames.append(sus)
            sql_start = time.perf_counter()
            lhb = query_df(conn, lhb_sql, params)
            lhb_seconds = time.perf_counter() - sql_start
            if not lhb.empty:
                lhb_frames.append(lhb)
            if idx % 5 == 0 or idx == 1 or idx == ((len(code_list) + FETCH_CHUNK_SIZE - 1) // FETCH_CHUNK_SIZE):
                fetched_codes = min(idx * FETCH_CHUNK_SIZE, len(code_list))
                log_step(
                    "chunk fetched",
                    chunk_start,
                    total_start,
                    extra=(
                        f"chunk={idx}, codes={fetched_codes}/{len(code_list)}, "
                        f"factor_rows={len(frame):,}, limit_rows={len(lim):,}, "
                        f"st_rows={len(st):,}, suspend_rows={len(sus):,}, lhb_rows={len(lhb):,}, "
                        f"factor_sql={fmt_seconds(factor_seconds)}, "
                        f"limit_sql={fmt_seconds(limit_seconds)}, "
                        f"st_sql={fmt_seconds(st_seconds)}, "
                        f"suspend_sql={fmt_seconds(suspend_seconds)}, "
                        f"lhb_sql={fmt_seconds(lhb_seconds)}"
                    ),
                )
    log_step(
        "all chunks fetched",
        step_start,
        total_start,
        extra=(
            f"factor_parts={len(frames)}, limit_parts={len(limit_frames)}, "
            f"st_parts={len(st_frames)}, suspend_parts={len(suspend_frames)}, "
            f"lhb_parts={len(lhb_frames)}"
        ),
    )
    if not frames:
        raise RuntimeError("No factor rows fetched for v8 universe.")
    step_start = time.perf_counter()
    panel = pd.concat(frames, ignore_index=True)
    log_step("factor concat done", step_start, total_start, panel)
    if limit_frames:
        step_start = time.perf_counter()
        limits = pd.concat(limit_frames, ignore_index=True)
        log_step("limit concat done", step_start, total_start, limits)
        step_start = time.perf_counter()
        panel = panel.merge(limits, on=["ts_code", "trade_date"], how="left")
        del limits
        gc.collect()
        log_step("limit merge done", step_start, total_start, panel)
    else:
        panel["up_limit"] = np.nan
        panel["down_limit"] = np.nan
    if st_frames:
        step_start = time.perf_counter()
        st_data = pd.concat(st_frames, ignore_index=True)
        log_step("st concat done", step_start, total_start, st_data)
        step_start = time.perf_counter()
        panel = panel.merge(st_data, on=["ts_code", "trade_date"], how="left")
        del st_data
        gc.collect()
        log_step("st merge done", step_start, total_start, panel)
    else:
        panel["is_st"] = False
    if suspend_frames:
        step_start = time.perf_counter()
        suspend_data = pd.concat(suspend_frames, ignore_index=True)
        log_step("suspend concat done", step_start, total_start, suspend_data)
        step_start = time.perf_counter()
        panel = panel.merge(suspend_data, on=["ts_code", "trade_date"], how="left")
        del suspend_data
        gc.collect()
        log_step("suspend merge done", step_start, total_start, panel)
    else:
        panel["is_suspended"] = False
    if lhb_frames:
        step_start = time.perf_counter()
        lhb_data = pd.concat(lhb_frames, ignore_index=True)
        log_step("lhb concat done", step_start, total_start, lhb_data)
        step_start = time.perf_counter()
        panel = panel.merge(lhb_data, on=["ts_code", "trade_date"], how="left")
        del lhb_data
        gc.collect()
        log_step("lhb merge done", step_start, total_start, panel)
    else:
        panel["is_lhb"] = False

    step_start = time.perf_counter()
    panel = panel[panel["ts_code"].isin(valid_codes)].copy()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    numeric_cols = [
        "open", "high", "low", "close", "pre_close", "open_qfq", "close_qfq", "bbi_qfq",
        "amount", "circ_mv", "adj_factor", "up_limit", "down_limit",
        "turnover_rate", "volume_ratio",
    ]
    for col in numeric_cols:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")
    panel = panel.dropna(subset=["open", "high", "low", "close", "pre_close", "open_qfq", "close_qfq", "bbi_qfq"])
    panel["is_st"] = panel["is_st"].eq(True)
    panel["is_suspended"] = panel["is_suspended"].eq(True)
    panel["is_lhb"] = panel["is_lhb"].eq(True)
    log_step("panel type cleanup done", step_start, total_start, panel)
    step_start = time.perf_counter()
    panel = panel.merge(stocks[["ts_code", "name", "list_date", "delist_date"]], on="ts_code", how="left")
    log_step("stock info merge done", step_start, total_start, panel)
    step_start = time.perf_counter()
    panel = add_strength_features(panel)
    log_step("strength features done", step_start, total_start, panel)
    step_start = time.perf_counter()
    panel["list_days"] = (panel["trade_date"] - panel["list_date"]).dt.days
    panel["is_listed_long_enough"] = panel["list_days"] >= FILTER_MIN_LIST_DAYS
    panel["is_liquid"] = (panel["amount_ma20"] >= FILTER_MIN_AMOUNT) & (panel["circ_mv_ma20"] >= FILTER_MIN_CIRC_MV)
    panel["is_eligible"] = compute_point_in_time_eligibility(panel)
    counts = panel.groupby("ts_code").size()
    keep_codes = set(counts[counts >= MIN_HISTORY_ROWS].index)
    panel = panel.loc[panel["ts_code"].isin(keep_codes)]
    log_step("eligibility filters done", step_start, total_start, panel, f"keep_codes={len(keep_codes):,}")
    step_start = time.perf_counter()
    panel.to_parquet(PANEL_PATH, index=False)
    log_step("panel parquet saved", step_start, total_start, panel, f"path={PANEL_PATH}")

    if MARKET_FILTER_ENABLED:
        step_start = time.perf_counter()
        with engine.connect() as conn:
            market_sql = f"""
                SELECT trade_date, open, close, amount
                FROM {SCHEMA}."137_idx_factor_pro"
                WHERE ts_code = :ts_code
                  AND trade_date >= CAST(:start_date AS date)
                  AND trade_date <= CAST(:end_date AS date)
                ORDER BY trade_date
            """
            market = query_df(conn, market_sql, {
                "ts_code": MARKET_INDEX_CODE,
                "start_date": start_date,
                "end_date": end_date,
            })
        log_step("market query done", step_start, total_start, market)
        step_start = time.perf_counter()
        market["trade_date"] = pd.to_datetime(market["trade_date"])
        for col in ["open", "close", "amount"]:
            market[col] = pd.to_numeric(market[col], errors="coerce")
        market = market.dropna(subset=["open", "close", "amount"])
        market.to_parquet(MARKET_INDEX_PATH, index=False)
        log_step(
            "market parquet saved",
            step_start,
            total_start,
            market,
            f"index={MARKET_INDEX_CODE} {MARKET_INDEX_NAME}, path={MARKET_INDEX_PATH}",
        )

    meta = {
        "start_date": start_date,
        "backtest_start": backtest_start,
        "end_date": end_date,
        "base_universe_rows": int(len(stocks)),
        "panel_rows": int(len(panel)),
        "panel_stocks": int(panel["ts_code"].nunique()),
        "database_bbi_only": True,
        "anti_lookahead": "rebalance at T open uses previous completed trading day as signal_date",
    }
    (OUTPUT_DIR / "data_quality.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log_step("done", total_start, total_start, panel)


if __name__ == "__main__":
    main()

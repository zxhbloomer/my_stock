import json
import socket
import subprocess
import sys
import time
import webbrowser
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from config import (
    BASE_POSITION_AMOUNT,
    DB_URL,
    DC_SEGMENT_CRASH_DD_20,
    DC_SEGMENT_CRASH_RET_20,
    DC_SEGMENT_MEMBER_LAG_DAYS,
    DC_SEGMENT_OVERLAY_ACTIVE_FROM,
    INIT_CASH,
    LAST_HOLDINGS_PATH,
    LONG_POSITION_STEPS,
    MAX_POSITION_AMOUNT,
    NAV_SERIES_PATH,
    PANEL_PATH,
    REBALANCE_LOG_PATH,
    REPORT_PATH,
    SCHEMA,
    SCORES_PATH,
    SUMMARY_PATH,
    TRADE_RECORDS_PATH,
)

RISK_FREE = 0.02
REPORT_PORT_START = 18085
V8_MAX_POSITION_AMOUNT = float(sum(LONG_POSITION_STEPS))


def load_strategy_outputs():
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    nav = pd.read_csv(NAV_SERIES_PATH, parse_dates=["date"])
    trades = pd.read_csv(TRADE_RECORDS_PATH) if TRADE_RECORDS_PATH.exists() else pd.DataFrame()
    scores = pd.read_csv(SCORES_PATH) if SCORES_PATH.exists() else pd.DataFrame()
    rebalance_log = pd.read_csv(REBALANCE_LOG_PATH) if REBALANCE_LOG_PATH.exists() else pd.DataFrame()
    holdings = {}
    if LAST_HOLDINGS_PATH.exists():
        holdings = json.loads(LAST_HOLDINGS_PATH.read_text(encoding="utf-8"))
    return summary, prepare_nav(nav), trades, scores, rebalance_log, holdings


def prepare_nav(nav):
    nav = nav.copy()
    nav["equity_curve"] = nav["nav"] / INIT_CASH
    nav["pct_chg"] = nav["equity_curve"].pct_change().fillna(0)
    nav["max2here"] = nav["equity_curve"].expanding().max()
    nav["drawdown"] = nav["equity_curve"] / nav["max2here"] - 1.0
    return nav


def calc_metrics(nav, summary):
    dd_end = nav.loc[nav["drawdown"].idxmin(), "date"]
    before_dd = nav[nav["date"] <= dd_end]
    dd_start = before_dd.loc[before_dd["equity_curve"].idxmax(), "date"] if not before_dd.empty else dd_end
    daily_ret = nav["pct_chg"]
    excess = daily_ret - RISK_FREE / 252
    sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0.0
    metrics = {
        "总收益": f"{summary.get('total_return_pct', 0.0):.2f}%",
        "累积净值": f"{nav['equity_curve'].iloc[-1]:.2f}",
        "年化收益": f"{summary.get('annual_return_pct', 0.0):.2f}%",
        "最大回撤": f"{summary.get('max_drawdown_pct', 0.0):.2f}%",
        "最大回撤开始": str(dd_start)[:10],
        "最大回撤结束": str(dd_end)[:10],
        "夏普比率": f"{sharpe:.3f}",
        "卡玛比率": f"{summary.get('calmar_ratio', 0.0):.3f}",
        "初始资金": f"{INIT_CASH:,.0f}",
        "最终资产": f"{summary.get('final_nav', nav['nav'].iloc[-1]):,.0f}",
        "盈利": f"{summary.get('final_nav', nav['nav'].iloc[-1]) - INIT_CASH:,.0f}",
    }
    return metrics


def make_net_value_figure(nav, metrics, start_date, end_date):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=nav["date"], y=nav["equity_curve"],
        name="策略净值", line=dict(color="#2196F3", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=nav["date"], y=nav["drawdown"],
        name="回撤(右轴)", opacity=0.25, marker_color="#F44336",
        line=dict(width=0), fill="tozeroy", yaxis="y2",
    ))
    fig.add_trace(go.Table(
        header=dict(values=["指标", "数值"], fill_color="#34495e",
                    font=dict(color="white", size=12), align="left"),
        cells=dict(values=[list(metrics.keys()), list(metrics.values())],
                   fill_color=[["#f8f9fa"] * len(metrics)],
                   align="left", font=dict(size=12)),
        domain=dict(x=[0.75, 1.0], y=[0.0, 0.85]),
    ))
    fig.update_layout(
        template="none", width=1500, height=600,
        title=dict(text=f"v8 BBI月度强弱轮动  回测区间：{start_date} ~ {end_date}", x=0.02, xanchor="left"),
        hovermode="x unified", xaxis=dict(domain=[0.0, 0.72]),
        yaxis=dict(title="净值"), yaxis2=dict(title="回撤", overlaying="y", side="right"),
        margin=dict(t=60, b=40), legend=dict(x=0.01, y=0.99),
    )
    return fig


def fmt_arrow(value, is_pct=False, is_currency=False):
    if pd.isna(value):
        return "-"
    if is_pct:
        text = f"{value * 100:.2f}%"
    elif is_currency:
        text = f"{value:,.0f}"
    else:
        text = f"{value:.2f}"
    if value > 0:
        return f"+{text} ▲"
    if value < 0:
        return f"{text} ▼"
    return text


def fmt_pct(value):
    if pd.isna(value):
        return "-"
    return f"{value * 100:.2f}%"


def font_color(value):
    if pd.isna(value) or value == 0:
        return "#333333"
    return "#dc2626" if value > 0 else "#16a34a"


def signed_class(value):
    if pd.isna(value) or value == 0:
        return "neutral"
    return "pos" if value > 0 else "neg"


def fmt_num(value, digits=2, thousands=False):
    if value is None or pd.isna(value):
        return "-"
    if thousands:
        return f"{float(value):,.{digits}f}"
    return f"{float(value):.{digits}f}"


def fmt_int(value):
    if value is None or pd.isna(value):
        return "-"
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return "-"


def fmt_date(value):
    if value is None or pd.isna(value):
        return "-"
    text = str(value)
    return text[:10]


def build_monthly_market_regime_summary(rebalance_log):
    if rebalance_log is None or rebalance_log.empty:
        return {}
    required_cols = {"date", "market_regime"}
    if not required_cols.issubset(rebalance_log.columns):
        return {}
    data = rebalance_log[["date", "market_regime"]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"])
    if data.empty:
        return {}
    data["period_end"] = data["date"].dt.to_period("M").dt.to_timestamp("M")
    data["market_regime"] = data["market_regime"].fillna("unknown").astype(str)

    labels = [
        ("bull", "牛市"),
        ("neutral", "震荡"),
        ("bear", "熊市"),
    ]
    summary = {}
    for period_end, group in data.groupby("period_end"):
        counts = group["market_regime"].value_counts()
        parts = [f"{label}({int(counts.get(key, 0))})" for key, label in labels]
        known_keys = {key for key, _ in labels}
        unknown_count = int(counts[~counts.index.isin(known_keys)].sum())
        if unknown_count:
            parts.append(f"未知({unknown_count})")
        summary[pd.Timestamp(period_end)] = " / ".join(parts)
    return summary


def week_number_in_month(date):
    date = pd.Timestamp(date)
    month_start = date.replace(day=1)
    first_week_start = month_start - pd.Timedelta(days=month_start.weekday())
    return int(((date - first_week_start).days // 7) + 1)


def build_weekly_regime_summary(rebalance_log):
    if rebalance_log is None or rebalance_log.empty:
        return {}
    required_cols = {"date", "market_regime"}
    if not required_cols.issubset(rebalance_log.columns):
        return {}
    data = rebalance_log[["date", "market_regime"]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"])
    if data.empty:
        return {}
    data["month_key"] = data["date"].dt.strftime("%Y-%m")
    data["week_no"] = data["date"].map(week_number_in_month)
    data["market_regime"] = data["market_regime"].fillna("unknown").astype(str)
    summary = {}
    for key, group in data.groupby(["month_key", "week_no"]):
        counts = group["market_regime"].value_counts()
        summary[key] = (
            f"牛({int(counts.get('bull', 0))})/"
            f"震({int(counts.get('neutral', 0))})/"
            f"熊({int(counts.get('bear', 0))})"
        )
    return summary


def build_monthly_week_cells(nav, rebalance_log=None, weekly_hotspots=None):
    weekly_hotspots = weekly_hotspots or {}
    if nav is None or nav.empty or "date" not in nav.columns or "nav" not in nav.columns:
        return {}
    data = nav[["date", "nav"]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
    data = data.dropna(subset=["date", "nav"]).sort_values("date")
    if data.empty:
        return {}
    data["period_end"] = data["date"].dt.to_period("M").dt.to_timestamp("M")
    data["month_key"] = data["date"].dt.strftime("%Y-%m")
    data["week_no"] = data["date"].map(week_number_in_month)
    regime_summary = build_weekly_regime_summary(rebalance_log)
    prev_nav = None
    by_month = {}
    for (period_end, month_key, week_no), group in data.groupby(["period_end", "month_key", "week_no"], sort=True):
        if week_no < 1 or week_no > 5:
            continue
        end_nav = float(group["nav"].iloc[-1])
        base_nav = float(group["nav"].iloc[0]) if prev_nav is None else prev_nav
        week_ret = end_nav / base_nav - 1.0 if base_nav else float("nan")
        prev_nav = end_nav
        by_month.setdefault(pd.Timestamp(period_end), [None, None, None, None, None])
        by_month[pd.Timestamp(period_end)][week_no - 1] = {
            "hotspots": weekly_hotspots.get((month_key, int(week_no)), "-"),
            "regime": regime_summary.get((month_key, int(week_no)), "牛(0)/震(0)/熊(0)"),
            "return": fmt_arrow(week_ret, is_pct=True),
            "class": signed_class(week_ret),
        }
    return by_month


def zscore_by_date(frame, value_col, out_col):
    values = pd.to_numeric(frame[value_col], errors="coerce")
    means = values.groupby(frame["trade_date"]).transform("mean")
    stds = values.groupby(frame["trade_date"]).transform(lambda s: s.std(ddof=0)).replace(0, np.nan)
    frame[out_col] = ((values - means) / stds).fillna(0.0)
    return frame


def build_dc_segment_score_frame(dc_daily):
    required = {"ts_code", "trade_date", "close", "amount"}
    missing = required - set(dc_daily.columns)
    if missing:
        raise ValueError(f"dc_daily missing columns: {sorted(missing)}")
    source_cols = list(required)
    name_col = None
    for candidate in ["name", "segment_name"]:
        if candidate in dc_daily.columns:
            name_col = candidate
            source_cols.append(candidate)
            break
    data = dc_daily[source_cols].copy()
    data = data.rename(columns={"ts_code": "segment_code"})
    if name_col:
        data = data.rename(columns={name_col: "segment_name"})
        data["segment_name"] = data["segment_name"].fillna("").astype(str).str.strip()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    data = data.dropna(subset=["segment_code", "trade_date", "close"]).sort_values(["segment_code", "trade_date"])
    grouped = data.groupby("segment_code", sort=False)
    data["seg_ret_20"] = grouped["close"].pct_change(20)
    data["seg_ret_60"] = grouped["close"].pct_change(60)
    data["seg_amount_rank_pct"] = data.groupby("trade_date")["amount"].rank(pct=True)
    for col in ["seg_ret_20", "seg_ret_60", "seg_amount_rank_pct"]:
        data[col] = data[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        data = zscore_by_date(data, col, f"{col}_z")
    data["segment_score"] = (
        0.45 * data["seg_ret_60_z"]
        + 0.35 * data["seg_ret_20_z"]
        + 0.20 * data["seg_amount_rank_pct_z"]
    ).clip(-3.0, 3.0)
    rolling_high = grouped["close"].transform(lambda s: s.rolling(20, min_periods=5).max())
    data["seg_dd_20"] = data["close"] / rolling_high - 1.0
    data["segment_crash"] = (
        (data["seg_ret_20"].fillna(0.0) <= DC_SEGMENT_CRASH_RET_20)
        | (data["seg_dd_20"].fillna(0.0) <= DC_SEGMENT_CRASH_DD_20)
    )
    result_cols = ["trade_date", "segment_code", "segment_score"]
    if "segment_name" in data.columns:
        result_cols.append("segment_name")
    result_cols.append("segment_crash")
    return data[result_cols].copy()


def build_weekly_hotspots_from_dc_daily(dc_daily, top_n=3):
    if dc_daily is None or dc_daily.empty:
        return {}
    features = build_dc_segment_score_frame(dc_daily)
    if features.empty:
        return {}
    features["month_key"] = features["trade_date"].dt.strftime("%Y-%m")
    features["week_no"] = features["trade_date"].map(week_number_in_month)
    hotspots = {}
    for (month_key, week_no), group in features.groupby(["month_key", "week_no"], sort=True):
        if week_no < 1 or week_no > 5:
            continue
        last_date = group["trade_date"].max()
        last_day = group[group["trade_date"].eq(last_date)].copy()
        last_day = last_day.sort_values("segment_score", ascending=False).head(top_n)
        if "segment_name" in last_day.columns:
            display = last_day["segment_name"].where(last_day["segment_name"].astype(str).str.len() > 0, last_day["segment_code"])
        else:
            display = last_day["segment_code"]
        leaders = display.astype(str).tolist()
        hotspots[(month_key, int(week_no))] = "、".join(leaders) if leaders else "-"
    return hotspots


def member_date_for_signal_report(signal_date, members, member_lag_days=DC_SEGMENT_MEMBER_LAG_DAYS):
    signal_date = pd.Timestamp(signal_date)
    member_dates = sorted(pd.to_datetime(members["trade_date"].dropna().unique()))
    available_dates = [d for d in member_dates if d <= signal_date]
    if len(available_dates) <= int(member_lag_days):
        return None
    return available_dates[-1 - int(member_lag_days)]


def build_weekly_candidate_dc_segment_hotspots(
    scores,
    members,
    dc_daily,
    top_candidate_n=20,
    top_segment_n=3,
):
    if scores is None or scores.empty or members is None or members.empty or dc_daily is None or dc_daily.empty:
        return {}
    required_score_cols = {"signal_date", "rank", "ts_code"}
    required_member_cols = {"trade_date", "ts_code", "con_code"}
    if required_score_cols - set(scores.columns) or required_member_cols - set(members.columns):
        return {}
    active_start = pd.Timestamp(DC_SEGMENT_OVERLAY_ACTIVE_FROM)
    score_data = scores[list(required_score_cols)].copy()
    score_data["signal_date"] = pd.to_datetime(score_data["signal_date"], errors="coerce")
    score_data["rank"] = pd.to_numeric(score_data["rank"], errors="coerce")
    score_data = score_data.dropna(subset=["signal_date", "rank", "ts_code"])
    score_data = score_data[
        score_data["rank"].le(int(top_candidate_n))
        & score_data["signal_date"].ge(active_start)
    ].copy()
    if score_data.empty:
        return {}

    member_data = members[["trade_date", "ts_code", "con_code"]].copy()
    member_data["trade_date"] = pd.to_datetime(member_data["trade_date"], errors="coerce")
    member_data = member_data.dropna(subset=["trade_date", "ts_code", "con_code"])
    features = build_dc_segment_score_frame(dc_daily)
    if member_data.empty or features.empty:
        return {}
    member_dates = sorted(pd.to_datetime(member_data["trade_date"].dropna().unique()))
    members_by_date = {pd.Timestamp(k): v for k, v in member_data.groupby("trade_date", sort=False)}
    features_by_date = {pd.Timestamp(k): v for k, v in features.groupby("trade_date", sort=False)}

    hotspots = {}
    for signal_date, group in score_data.groupby("signal_date", sort=True):
        available_dates = [d for d in member_dates if d <= signal_date]
        if len(available_dates) <= int(DC_SEGMENT_MEMBER_LAG_DAYS):
            continue
        member_date = pd.Timestamp(available_dates[-1 - int(DC_SEGMENT_MEMBER_LAG_DAYS)])
        day_members = members_by_date.get(member_date, pd.DataFrame())[["con_code", "ts_code"]].copy()
        if day_members.empty:
            continue
        day_members = day_members.rename(columns={"con_code": "ts_code", "ts_code": "segment_code"})
        day_features = features_by_date.get(pd.Timestamp(signal_date), pd.DataFrame()).copy()
        if day_features.empty:
            continue
        exposure = group[["ts_code"]].merge(day_members, on="ts_code", how="inner")
        exposure = exposure.merge(day_features, on="segment_code", how="left")
        crash = exposure["segment_crash"].where(exposure["segment_crash"].notna(), False).astype(bool)
        exposure = exposure[~crash].copy()
        if exposure.empty:
            continue
        exposure["segment_score"] = pd.to_numeric(exposure["segment_score"], errors="coerce").fillna(0.0)
        name_col = "segment_name" if "segment_name" in exposure.columns else "segment_code"
        leaders = (
            exposure.groupby(["segment_code", name_col], dropna=False)
            .agg(
                stock_count=("ts_code", "nunique"),
                segment_score=("segment_score", "max"),
            )
            .reset_index()
            .sort_values(["segment_score", "stock_count"], ascending=[False, False])
            .head(int(top_segment_n))
        )
        values = []
        for _, row in leaders.iterrows():
            name = str(row.get(name_col) or row["segment_code"]).strip() or str(row["segment_code"])
            values.append(f"{name}({int(row['stock_count'])})")
        if not values:
            continue
        month_key = signal_date.strftime("%Y-%m")
        week_no = week_number_in_month(signal_date)
        if 1 <= week_no <= 5:
            hotspots[(month_key, int(week_no))] = "、".join(values)
    return hotspots


def load_weekly_candidate_dc_segment_hotspots(scores, nav):
    if scores is None or scores.empty or nav is None or nav.empty or "date" not in nav.columns:
        return {}
    start_date = max(
        pd.Timestamp(DC_SEGMENT_OVERLAY_ACTIVE_FROM) - pd.Timedelta(days=120),
        pd.to_datetime(nav["date"], errors="coerce").min() - pd.Timedelta(days=120),
    )
    end_date = pd.to_datetime(nav["date"], errors="coerce").max()
    if pd.isna(start_date) or pd.isna(end_date):
        return {}
    try:
        engine = create_engine(DB_URL, poolclass=NullPool)
        with engine.connect() as conn:
            dc_daily = pd.read_sql(text(f"""
                SELECT d.ts_code, d.trade_date, d.close, d.amount, i.name
                FROM {SCHEMA}."099_dc_daily" d
                LEFT JOIN (
                    SELECT DISTINCT ON (ts_code) ts_code, name
                    FROM {SCHEMA}."097_dc_index"
                    WHERE trade_date <= :end_date
                    ORDER BY ts_code, trade_date DESC
                ) i ON i.ts_code = d.ts_code
                WHERE d.trade_date >= :start_date
                  AND d.trade_date <= :end_date
            """), conn, params={"start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d")})
            members = pd.read_sql(text(f"""
                SELECT trade_date, ts_code, con_code
                FROM {SCHEMA}."098_dc_member"
                WHERE trade_date >= :active_start
                  AND trade_date <= :end_date
            """), conn, params={"active_start": DC_SEGMENT_OVERLAY_ACTIVE_FROM, "end_date": end_date.strftime("%Y-%m-%d")})
        return build_weekly_candidate_dc_segment_hotspots(scores, members, dc_daily)
    except Exception as exc:
        print(f"[report] weekly candidate DC segment hotspots unavailable: {exc}")
        return {}


def load_weekly_dc_segment_hotspots(nav):
    if nav is None or nav.empty or "date" not in nav.columns:
        return {}
    start_date = pd.to_datetime(nav["date"], errors="coerce").min()
    end_date = pd.to_datetime(nav["date"], errors="coerce").max()
    if pd.isna(start_date) or pd.isna(end_date):
        return {}
    query_start = (start_date - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    query_end = end_date.strftime("%Y-%m-%d")
    try:
        engine = create_engine(DB_URL, poolclass=NullPool)
        with engine.connect() as conn:
            dc_daily = pd.read_sql(text(f"""
                SELECT d.ts_code, d.trade_date, d.close, d.amount, i.name
                FROM {SCHEMA}."099_dc_daily" d
                LEFT JOIN (
                    SELECT DISTINCT ON (ts_code) ts_code, name
                    FROM {SCHEMA}."097_dc_index"
                    WHERE trade_date <= :end_date
                    ORDER BY ts_code, trade_date DESC
                ) i ON i.ts_code = d.ts_code
                WHERE d.trade_date >= :start_date
                  AND d.trade_date <= :end_date
            """), conn, params={"start_date": query_start, "end_date": query_end})
        return build_weekly_hotspots_from_dc_daily(dc_daily)
    except Exception as exc:
        print(f"[report] weekly DC segment hotspots unavailable: {exc}")
        return {}


def build_monthly_return_data(nav, rebalance_log=None):
    nav_indexed = nav.set_index("date")
    monthly_nav = nav_indexed["nav"].resample("ME").last()
    if "cash" in nav_indexed.columns:
        monthly_cash = nav_indexed["cash"].resample("ME").last()
    else:
        monthly_cash = pd.Series(np.nan, index=monthly_nav.index)
    monthly_stock_value = monthly_nav - monthly_cash
    monthly_stock_ratio = monthly_stock_value / monthly_nav
    monthly_cash_ratio = monthly_cash / monthly_nav
    prev_month_nav = monthly_nav.shift(1)
    prev_month_nav.iloc[0] = INIT_CASH
    monthly_pnl = monthly_nav - prev_month_nav
    monthly_ret = monthly_nav / prev_month_nav - 1.0
    total_ret = monthly_nav / INIT_CASH - 1.0
    year_base = prev_month_nav.groupby(prev_month_nav.index.year).transform("first")
    ytd_ret = monthly_nav / year_base - 1.0

    dates = list(monthly_nav.index)
    n = len(dates)
    year_labels, row_bg = [], []
    prev_year, year_toggle = None, True
    for d in dates:
        if d.year != prev_year:
            year_labels.append(str(d.year))
            prev_year = d.year
            year_toggle = not year_toggle
        else:
            year_labels.append("")
        row_bg.append("#eef4fb" if year_toggle else "#f7f7f7")

    annual_col = []
    annual_colors = []
    annual_classes = []
    for i, d in enumerate(dates):
        is_last = i == n - 1 or dates[i + 1].year != d.year
        value = ytd_ret.iloc[i] if is_last else float("nan")
        annual_col.append(fmt_arrow(value, is_pct=True) if is_last else "")
        annual_colors.append(font_color(value))
        annual_classes.append(signed_class(value) if is_last else "neutral")

    return {
        "dates": dates,
        "year_labels": year_labels,
        "row_bg": row_bg,
        "market_regime_summary": build_monthly_market_regime_summary(rebalance_log),
        "monthly_nav": monthly_nav,
        "monthly_stock_value": monthly_stock_value,
        "monthly_cash": monthly_cash,
        "monthly_stock_ratio": monthly_stock_ratio,
        "monthly_cash_ratio": monthly_cash_ratio,
        "monthly_pnl": monthly_pnl,
        "monthly_ret": monthly_ret,
        "total_ret": total_ret,
        "ytd_ret": ytd_ret,
        "annual_col": annual_col,
        "annual_colors": annual_colors,
        "annual_classes": annual_classes,
    }


def make_equity_figure(nav):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=nav["date"], y=nav["nav"],
        name="资金（元）", line=dict(color="#2196F3", width=2),
    ))
    fig.update_layout(
        template="none", width=760, height=600,
        title=dict(text="资金曲线", x=0.02, xanchor="left"),
        yaxis=dict(title="资金（元）", tickformat=",.0f"),
        margin=dict(t=60, b=40, l=20, r=20), showlegend=False,
    )
    return fig


def make_week_cell_html(cell):
    if not cell:
        return "-"
    def week_line(text):
        value = str(text)
        escaped = escape(value)
        return f'<div class="week-line" title="{escape(value, quote=True)}">{escaped}</div>'
    return (
        week_line(f'1、板块：{cell.get("hotspots", "-")}')
        + week_line(f'2、{cell.get("regime", "-")}')
        + week_line(f'3、收益：{cell.get("return", "-")}')
    )


def make_monthly_return_table_html(nav, rebalance_log=None, weekly_hotspots=None):
    data = build_monthly_return_data(nav, rebalance_log=rebalance_log)
    week_cells = build_monthly_week_cells(nav, rebalance_log=rebalance_log, weekly_hotspots=weekly_hotspots)
    headers = [
        "年份", "月份", "市场状态", "月末总资产", "股票市值", "现金余额", "股票仓位", "现金占比",
        "当月盈亏(元)", "当月收益率", "总收益率", "年内收益率", "年收益率",
    ]
    year_groups = {}
    for idx, date in enumerate(data["dates"]):
        year_groups.setdefault(date.year, []).append(idx)
    html = ['<div class="monthly-table-wrap"><table class="monthly-return-table">']
    html.append(
        "<colgroup>"
        "<col class=\"year-col\"><col class=\"month-col\"><col class=\"regime-col\"><col class=\"asset-col\"><col class=\"asset-col\"><col class=\"asset-col\">"
        "<col class=\"rate-col\"><col class=\"rate-col\">"
        "<col class=\"pnl-col\"><col class=\"rate-col\"><col class=\"rate-col\">"
        "<col class=\"rate-col\"><col class=\"rate-col\">"
        "<col class=\"week-col\"><col class=\"week-col\"><col class=\"week-col\"><col class=\"week-col\"><col class=\"week-col\">"
        "</colgroup>"
    )
    html.append("<thead><tr>")
    for header in headers:
        html.append(f'<th rowspan="2">{escape(header)}</th>')
    html.append('<th colspan="5">周</th>')
    html.append("</tr><tr>")
    for header in ["一周", "二周", "三周", "四周", "五周"]:
        html.append(f"<th>{header}</th>")
    html.append("</tr></thead><tbody>")
    for i, d in enumerate(data["dates"]):
        year_indexes = year_groups[d.year]
        is_year_first_row = i == year_indexes[0]
        annual_index = year_indexes[-1]
        row_bg = data["row_bg"][i]
        row = [
            (d.strftime("%m月"), "neutral"),
            (data["market_regime_summary"].get(pd.Timestamp(d), "-"), "neutral"),
            (f"{data['monthly_nav'].iloc[i]:,.0f}", "neutral"),
            (fmt_int(data["monthly_stock_value"].iloc[i]), "neutral"),
            (fmt_int(data["monthly_cash"].iloc[i]), "neutral"),
            (fmt_pct(data["monthly_stock_ratio"].iloc[i]), "neutral"),
            (fmt_pct(data["monthly_cash_ratio"].iloc[i]), "neutral"),
            (fmt_arrow(data["monthly_pnl"].iloc[i], is_currency=True), signed_class(data["monthly_pnl"].iloc[i])),
            (fmt_arrow(data["monthly_ret"].iloc[i], is_pct=True), signed_class(data["monthly_ret"].iloc[i])),
            (fmt_arrow(data["total_ret"].iloc[i], is_pct=True), signed_class(data["total_ret"].iloc[i])),
            (fmt_arrow(data["ytd_ret"].iloc[i], is_pct=True), signed_class(data["ytd_ret"].iloc[i])),
        ]
        html.append(f'<tr style="background:{row_bg}">')
        if is_year_first_row:
            html.append(
                f'<td class="neutral merged-cell" rowspan="{len(year_indexes)}" style="text-align:center">'
                f"{d.year}</td>"
            )
        for col_idx, (text, klass) in enumerate(row):
            align = "right" if col_idx >= 2 else "center"
            html.append(f'<td class="{klass}" style="text-align:{align}">{escape(str(text))}</td>')
        if is_year_first_row:
            annual_text = data["annual_col"][annual_index]
            annual_class = data["annual_classes"][annual_index]
            html.append(
                f'<td class="{annual_class} merged-cell" rowspan="{len(year_indexes)}" style="text-align:right">'
                f"{escape(str(annual_text))}</td>"
            )
        for cell in week_cells.get(pd.Timestamp(d), [None, None, None, None, None]):
            klass = cell.get("class", "neutral") if cell else "neutral"
            html.append(f'<td class="{klass} week-cell" style="text-align:left">{make_week_cell_html(cell)}</td>')
        html.append("</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


def make_equity_table_figure(nav):
    data = build_monthly_return_data(nav)
    dates = data["dates"]
    n = len(dates)
    neutral = ["#333333"] * n
    fig = make_subplots(
        rows=1, cols=2, column_widths=[0.50, 0.50],
        specs=[[{"type": "xy"}, {"type": "table"}]],
    )
    fig.add_trace(go.Scatter(
        x=nav["date"], y=nav["nav"],
        name="资金（元）", line=dict(color="#2196F3", width=2),
    ), row=1, col=1)
    fig.add_trace(go.Table(
        columnwidth=[50, 40, 110, 105, 105, 80, 80, 110, 90, 95, 95, 90],
        header=dict(
            values=[
                "年份", "月份", "月末总资产", "股票市值", "现金余额", "股票仓位", "现金占比",
                "当月盈亏(元)", "当月收益率", "总收益率", "年内收益率", "年收益率",
            ],
            fill_color="#2c3e50", font=dict(color="white", size=11),
            align="center", height=28, line_color="#d0d7de",
        ),
        cells=dict(
            values=[
                data["year_labels"],
                [d.strftime("%m月") for d in dates],
                [f"{v:,.0f}" for v in data["monthly_nav"].values],
                [fmt_int(v) for v in data["monthly_stock_value"].values],
                [fmt_int(v) for v in data["monthly_cash"].values],
                [fmt_pct(v) for v in data["monthly_stock_ratio"].values],
                [fmt_pct(v) for v in data["monthly_cash_ratio"].values],
                [fmt_arrow(v, is_currency=True) for v in data["monthly_pnl"].values],
                [fmt_arrow(v, is_pct=True) for v in data["monthly_ret"].values],
                [fmt_arrow(v, is_pct=True) for v in data["total_ret"].values],
                [fmt_arrow(v, is_pct=True) for v in data["ytd_ret"].values],
                data["annual_col"],
            ],
            fill_color=[data["row_bg"]] * 12,
            align=["center", "center", "right", "right", "right", "right", "right", "right", "right", "right", "right", "right"],
            font=dict(
                size=11,
                color=[
                    neutral,
                    neutral,
                    neutral,
                    neutral,
                    neutral,
                    neutral,
                    neutral,
                    [font_color(v) for v in data["monthly_pnl"].values],
                    [font_color(v) for v in data["monthly_ret"].values],
                    [font_color(v) for v in data["total_ret"].values],
                    [font_color(v) for v in data["ytd_ret"].values],
                    data["annual_colors"],
                ],
            ),
            height=24,
            line_color=[data["row_bg"]] + [["#d0d7de"] * n] * 11,
            line_width=1,
        ),
    ), row=1, col=2)
    fig.update_layout(
        template="none", width=1800, height=max(500, min(1100, n * 25 + 80)),
        title=dict(text="资金曲线 & 月度收益明细", x=0.02, xanchor="left"),
        yaxis=dict(title="资金（元）", tickformat=",.0f"),
        margin=dict(t=60, b=40, l=20, r=20), showlegend=False,
    )
    return fig


def make_annual_return_figure(nav):
    yearly = nav.set_index("date")["pct_chg"].resample("YE").apply(lambda x: (1 + x).prod() - 1)
    values = [round(v * 100, 2) for v in yearly.values]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[str(d.year) for d in yearly.index],
        y=values,
        marker_color=["#e74c3c" if v >= 0 else "#2ecc71" for v in values],
        text=[f"{v:.1f}%" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        template="none", width=1500, height=400,
        title=dict(text="逐年收益率", x=0.02, xanchor="left"),
        yaxis=dict(title="收益率(%)"), margin=dict(t=60, b=40),
    )
    return fig


def make_simple_table(title, df, columns, width=1500, max_rows=300):
    if df is None or df.empty:
        table_df = pd.DataFrame(columns=columns)
    else:
        keep_cols = [c for c in columns if c in df.columns]
        table_df = df[keep_cols].copy()
        if max_rows and len(table_df) > max_rows:
            table_df = table_df.tail(max_rows)
    fig = go.Figure(data=[go.Table(
        header=dict(values=list(table_df.columns), fill_color="#2c3e50",
                    font=dict(color="white", size=11), align="center"),
        cells=dict(values=[table_df[c] for c in table_df.columns],
                   fill_color=[["#f8f9fa"] * len(table_df)],
                   align="center", font=dict(size=10), height=22),
    )])
    fig.update_layout(
        width=width, height=min(720, max(220, len(table_df) * 22 + 80)),
        title=dict(text=title, x=0.02, xanchor="left"),
        margin=dict(t=50, b=10),
    )
    return fig


def make_candidate_figure(scores):
    columns = [
        "signal_date", "rebalance_date", "rank", "ts_code", "name", "score",
        "above_ratio_21", "above_ratio_63", "above_ratio_126",
        "avg_distance_63", "high_pos_21", "high_pos_63", "range_pos_63",
        "pullback_63",
        "recent_limit_down_20", "recent_limit_up_20", "recent_limit_up_63",
        "turnover_rate_ma20", "turnover_rate_max20", "volume_ratio_max20",
        "lhb_count_20", "hot_money_risk_hits",
        "hm_limit_up_20_flag", "hm_limit_up_63_flag", "hm_turnover_ma20_flag",
        "hm_turnover_max20_flag", "hm_volume_ratio_max20_flag", "hm_lhb_count20_flag",
        "ret_21", "ret_63", "ret_126",
        "volatility_63", "amount_ma20", "circ_mv_ma20",
    ]
    if scores is not None and not scores.empty:
        sort_cols = [c for c in ["rebalance_date", "rank"] if c in scores.columns]
        scores = scores.sort_values(sort_cols) if sort_cols else scores
    return make_simple_table("候选排序明细（最近300行）", scores, columns, width=1800, max_rows=300)


def html_table(headers, rows, classes=None, cell_classes=None, table_class="report-table"):
    classes = classes or [""] * len(rows)
    cell_classes = cell_classes or [[] for _ in rows]
    html = [f'<div class="html-table-wrap"><table class="{table_class}">']
    html.append("<thead><tr>")
    for header in headers:
        html.append(f"<th>{escape(str(header))}</th>")
    html.append("</tr></thead><tbody>")
    if not rows:
        html.append(f'<tr><td class="empty-cell" colspan="{len(headers)}">暂无数据</td></tr>')
    for row, row_class, row_cell_classes in zip(rows, classes, cell_classes):
        html.append(f'<tr class="{row_class}">')
        for idx, value in enumerate(row):
            klass = row_cell_classes[idx] if idx < len(row_cell_classes) else ""
            html.append(f'<td class="{klass}">{escape(str(value))}</td>')
        html.append("</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


def make_holdings_table_html(holdings, report_end_date):
    rows = []
    row_classes = []
    cell_classes = []
    for code, pos in holdings.items():
        cost = float(pos.get("cost_price", 0.0) or 0.0)
        last = float(pos.get("last_price", cost) or cost)
        shares = float(pos.get("shares", 0) or 0.0)
        invested = float(pos.get("invested_amount", 0.0) or 0.0)
        pnl = last * shares - invested
        pnl_pct = (last - cost) / cost * 100 if cost > 0 else 0.0
        buy_date = fmt_date(pos.get("buy_date", "-"))
        hold_days = "-"
        if buy_date != "-" and report_end_date is not None:
            try:
                hold_days = str((pd.Timestamp(report_end_date) - pd.Timestamp(buy_date)).days)
            except Exception:
                hold_days = "-"
        row_classes.append("")
        rows.append([
            code,
            pos.get("name", code),
            buy_date,
            hold_days,
            fmt_num(shares, digits=2, thousands=True),
            fmt_num(cost, digits=2),
            fmt_num(last, digits=2),
            fmt_num(invested, digits=2, thousands=True),
            fmt_num(pnl, digits=2, thousands=True),
            fmt_num(pnl_pct, digits=2),
            f"{int(pos.get('step_index', 0) or 0)}/{len(LONG_POSITION_STEPS)}",
            "是" if pos.get("pending_sell") else "否",
        ])
        cell_classes.append([
            "text-cell", "text-cell", "date-cell", "num-cell",
            "num-cell", "num-cell", "num-cell", "num-cell",
            f"num-cell {signed_class(pnl)}",
            f"num-cell {signed_class(pnl_pct)}",
            "text-cell", "text-cell",
        ])
    headers = ["代码", "名称", "买入日期", "持仓天数", "持仓股数", "成本价", "最新价", "已投入", "盈利(元)", "浮盈%", "建仓阶段", "待卖出"]
    return html_table(headers, rows, row_classes, cell_classes, table_class="report-table holdings-table")


def make_trade_table_html(trades):
    df = trades.copy()
    rename_map = {
        "date": "日期",
        "ts_code": "代码",
        "name": "名称",
        "action": "操作",
        "price": "价格",
        "shares": "股数",
        "amount": "金额",
        "commission": "手续费",
        "pnl": "盈亏(元)",
        "pnl_pct": "盈亏%",
        "reason": "原因",
    }
    for col in rename_map:
        if col not in df.columns:
            df[col] = np.nan
    df = df[list(rename_map)].rename(columns=rename_map)
    df["操作"] = df["操作"].replace({"buy": "买入", "sell": "卖出"})
    reason_map = {
        "monthly_strength_rebalance": "月度强弱调仓买入",
        "rank_drop_exit": "排名跌出卖出",
        "pending_sell": "延迟卖出成功",
        "limit_down_exit": "跌停风控卖出",
        "long_initial_buy": "长期策略首笔买入",
        "long_add_buy": "长期策略盈利加仓",
        "pure_bull_extra_add": "纯牛市小额最后加仓",
        "long_stop_loss": "长期策略-5%止损",
        "long_limit_down_exit": "长期策略跌停硬止损",
        "long_bearish_volume_exit": "长期策略放量大阴线卖出",
        "long_regime_bear_exit": "熊市确认后浮亏卖出",
        "long_rank_stale_exit": "长期低效持仓卖出",
        "bear_probe_initial_buy": "熊市小仓位试探买入",
        "market_bearish_volume": "大盘放量阴线风控",
        "market_regime_bear": "熊市确认后不开仓",
        "market_5d_not_weak": "大盘未弱不触发",
        "not_bearish_candle": "大盘非阴线不触发",
        "drop_too_small": "大盘跌幅不足不触发",
        "volume_not_expanded": "大盘未放量不触发",
    }
    df["原因"] = df["原因"].replace(reason_map)
    df["日期"] = df["日期"].apply(fmt_date)
    pnl_values = pd.to_numeric(df["盈亏(元)"], errors="coerce").reset_index(drop=True)
    pnl_pct_values = pd.to_numeric(df["盈亏%"], errors="coerce").reset_index(drop=True)
    df["价格"] = pd.to_numeric(df["价格"], errors="coerce").apply(lambda x: fmt_num(x, digits=2))
    df["股数"] = pd.to_numeric(df["股数"], errors="coerce").apply(lambda x: fmt_num(x, digits=2, thousands=True))
    df["金额"] = pd.to_numeric(df["金额"], errors="coerce").apply(lambda x: fmt_num(x, digits=2, thousands=True))
    df["手续费"] = pd.to_numeric(df["手续费"], errors="coerce").apply(lambda x: fmt_num(x, digits=2, thousands=True))
    df["盈亏(元)"] = pnl_values.apply(lambda x: fmt_num(x, digits=2, thousands=True))
    df["盈亏%"] = pnl_pct_values.apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "-")
    df["持仓天数"] = "-"
    open_dates = {}
    for idx, row in df.iterrows():
        code = row["代码"]
        action = row["操作"]
        date = pd.Timestamp(row["日期"])
        if action == "买入":
            open_dates.setdefault(code, date)
        elif action == "卖出":
            open_date = open_dates.get(code)
            if open_date is not None:
                df.at[idx, "持仓天数"] = str((date - open_date).days)
                open_dates.pop(code, None)
    df["操作"] = df["操作"].replace({"buy": "买入", "sell": "卖出"})
    ordered_cols = ["日期", "代码", "名称", "操作", "持仓天数", "价格", "股数", "金额", "手续费", "盈亏(元)", "盈亏%", "原因"]
    df = df[ordered_cols].reset_index(drop=True)
    rows = df.values.tolist()
    row_classes = [
        "buy-row" if "买入" in str(action) else ("sell-row" if "卖出" in str(action) else "")
        for action in df["操作"].tolist()
    ]
    cell_classes = []
    for idx, row in df.iterrows():
        if row["操作"] == "买入":
            action_class = "text-cell buy-action-cell"
        elif row["操作"] == "卖出":
            action_class = "text-cell sell-action-cell"
        else:
            action_class = "text-cell"
        cell_classes.append([
            "date-cell", "text-cell", "text-cell", action_class, "num-cell",
            "num-cell", "num-cell", "num-cell", "num-cell",
            f"num-cell {signed_class(pnl_values.iloc[idx])}",
            f"num-cell {signed_class(pnl_pct_values.iloc[idx])}",
            "text-cell",
        ])
    return html_table(ordered_cols, rows, row_classes, cell_classes, table_class="report-table trades-table")


TRADE_REASON_MAP = {
    "monthly_strength_rebalance": "月度强弱调仓买入",
    "rank_drop_exit": "排名跌出卖出",
    "pending_sell": "延迟卖出成功",
    "limit_down_exit": "跌停风控卖出",
    "long_initial_buy": "长期策略首笔买入",
    "long_add_buy": "长期策略盈利加仓",
    "pure_bull_extra_add": "纯牛市小额最后加仓",
    "long_stop_loss": "长期策略-5%止损",
    "long_limit_down_exit": "长期策略跌停硬止损",
    "long_bearish_volume_exit": "长期策略放量大阴线卖出",
    "long_regime_bear_exit": "熊市确认后浮亏卖出",
    "long_rank_stale_exit": "长期低效持仓卖出",
    "bear_probe_initial_buy": "熊市小仓位试探买入",
    "market_bearish_volume": "大盘放量阴线风控",
    "market_regime_bear": "熊市确认后不开仓",
    "market_5d_not_weak": "大盘未弱不触发",
    "not_bearish_candle": "大盘非阴线不触发",
    "drop_too_small": "大盘跌幅不足不触发",
    "volume_not_expanded": "大盘未放量不触发",
}


def line_join(values):
    cleaned = [str(v) for v in values if str(v) and str(v) != "-"]
    return "\n".join(cleaned) if cleaned else "-"


def enrich_scores_with_panel_price(scores):
    if scores is None or scores.empty or "close" in scores.columns or not PANEL_PATH.exists():
        return scores
    try:
        panel = pd.read_parquet(PANEL_PATH, columns=["trade_date", "ts_code", "close"])
    except Exception:
        return scores
    if panel.empty or not {"signal_date", "ts_code"}.issubset(scores.columns):
        return scores
    data = scores.copy()
    data["signal_date"] = pd.to_datetime(data["signal_date"], errors="coerce")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"], errors="coerce")
    price_map = panel.rename(columns={"trade_date": "signal_date"})[["signal_date", "ts_code", "close"]]
    return data.merge(price_map, on=["signal_date", "ts_code"], how="left")


def build_latest_candidate_rows(scores, holdings, trades, max_rows=30):
    if scores is None or scores.empty:
        return []
    data = enrich_scores_with_panel_price(scores).copy()
    if "rank" not in data.columns or "ts_code" not in data.columns:
        return []
    date_col = "rebalance_date" if "rebalance_date" in data.columns else "signal_date"
    if date_col in data.columns:
        latest_date = pd.to_datetime(data[date_col], errors="coerce").max()
        data = data[pd.to_datetime(data[date_col], errors="coerce").eq(latest_date)].copy()
    data["rank"] = pd.to_numeric(data["rank"], errors="coerce")
    data = data[data["rank"].le(max_rows)].sort_values("rank").head(max_rows)

    trade_groups = {}
    if trades is not None and not trades.empty and {"ts_code", "action", "date"}.issubset(trades.columns):
        trade_data = trades.copy()
        trade_data["date"] = trade_data["date"].apply(fmt_date)
        for code, group in trade_data.sort_values("date").groupby("ts_code", sort=False):
            buy_rows = group[group["action"].eq("buy")]
            sell_rows = group[group["action"].eq("sell")]
            reasons = group.get("reason", pd.Series(dtype=object)).fillna("-").replace(TRADE_REASON_MAP).tolist()
            trade_groups[code] = {
                "buy_dates": buy_rows["date"].tolist(),
                "sell_dates": sell_rows["date"].tolist(),
                "reasons": reasons,
            }

    rows = []
    holdings = holdings or {}
    for _, row in data.iterrows():
        code = row.get("ts_code", "-")
        pos = holdings.get(code, {})
        shares = float(pos.get("shares", 0) or 0)
        invested = float(pos.get("invested_amount", 0) or 0)
        price = row.get("close", np.nan)
        if pd.isna(price):
            price = pos.get("last_price", np.nan)
        group = trade_groups.get(code, {})
        rows.append({
            "排名": fmt_int(row.get("rank")),
            "股票代码": code,
            "股票名称": row.get("name", code),
            "价格": fmt_num(price, digits=2),
            "仓位": fmt_num(shares, digits=2, thousands=True) if shares > 0 else "-",
            "仓位金额": fmt_num(invested, digits=2, thousands=True) if invested > 0 else "-",
            "建仓日期": line_join(group.get("buy_dates", [])),
            "卖出日期": line_join(group.get("sell_dates", [])),
            "原因": line_join(group.get("reasons", [])),
        })
    return rows


def make_latest_candidates_table_html(scores, holdings, trades):
    rows_dicts = build_latest_candidate_rows(scores, holdings, trades, max_rows=30)
    headers = ["排名", "股票代码", "股票名称", "价格", "仓位", "仓位金额", "建仓日期", "卖出日期", "原因"]
    rows = [[row.get(header, "-") for header in headers] for row in rows_dicts]
    cell_classes = [[
        "num-cell", "text-cell", "text-cell", "num-cell", "num-cell", "num-cell",
        "multiline-cell date-cell buy-date-cell",
        "multiline-cell date-cell sell-date-cell",
        "multiline-cell text-cell",
    ] for _ in rows]
    return html_table(headers, rows, cell_classes=cell_classes, table_class="report-table latest-candidates-table")


def make_html(summary, nav, trades, scores, rebalance_log, holdings):
    start_date = str(nav["date"].iloc[0])[:10]
    end_date = str(nav["date"].iloc[-1])[:10]
    metrics = calc_metrics(nav, summary)
    weekly_hotspots = load_weekly_candidate_dc_segment_hotspots(scores, nav)
    figs = [
        (make_net_value_figure(nav, metrics, start_date, end_date), "净值曲线"),
        (make_equity_figure(nav), "资金曲线"),
        (make_annual_return_figure(nav), "年度收益"),
    ]

    sections_html = ""
    for i, (fig, label) in enumerate(figs, 1):
        div = pio.to_html(fig, full_html=False, include_plotlyjs=(i == 1))
        if label == "资金曲线":
            sections_html += (
                '<div class="section wide-section"><div class="section-title">资金曲线 & 月度收益明细</div>'
                '<div class="equity-grid">'
                f'<div class="equity-chart">{div}</div>'
                f'<div class="equity-table">{make_monthly_return_table_html(nav, rebalance_log=rebalance_log, weekly_hotspots=weekly_hotspots)}</div>'
                '</div></div>\n'
            )
        else:
            sections_html += f'<div class="section"><div class="section-title">{label}</div>{div}</div>\n'
    sections_html += (
        f'<div class="section"><div class="section-title">当前持仓（{len(holdings)}只）</div>'
        f'{make_holdings_table_html(holdings, end_date)}</div>\n'
    )
    sections_html += (
        f'<div class="section"><div class="section-title">历史交易明细（共{len(trades)}笔）</div>'
        f'{make_trade_table_html(trades)}</div>\n'
    )
    sections_html += (
        '<div class="section"><div class="section-title">最新候选股票 Top 30</div>'
        f'{make_latest_candidates_table_html(scores, holdings, trades)}</div>\n'
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>v8 BBI月度强弱轮动报表</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 0; background: #f0f2f5; }}
  .header {{ background: #2c3e50; color: white; padding: 16px 24px; }}
  .header h2 {{ margin: 0; font-size: 1.4em; }}
  .header p {{ margin: 4px 0 0; font-size: 0.9em; color: #bdc3c7; }}
  .section {{ background: white; margin: 16px; border-radius: 8px; padding: 16px; overflow-x: auto; }}
  .wide-section {{ overflow-x: auto; }}
  .section-title {{ font-size: 1.05em; font-weight: bold; color: #2c3e50; margin-bottom: 8px;
                    padding-bottom: 6px; border-bottom: 2px solid #f39c12; }}
  .equity-grid {{ display: grid; grid-template-columns: 760px 1160px; gap: 16px; align-items: start; min-width: 1936px; }}
  .equity-chart, .equity-table {{ min-width: 0; }}
  .monthly-table-wrap {{ height: 600px; overflow: auto; border: 1px solid #d0d7de; }}
  .monthly-return-table {{ border-collapse: separate; border-spacing: 0; table-layout: fixed; width: 2520px; font-size: 12px; }}
  .monthly-return-table .year-col {{ width: 52px; }}
  .monthly-return-table .month-col {{ width: 48px; }}
  .monthly-return-table .regime-col {{ width: 180px; }}
  .monthly-return-table .asset-col {{ width: 105px; }}
  .monthly-return-table .pnl-col {{ width: 110px; }}
  .monthly-return-table .rate-col {{ width: 86px; }}
  .monthly-return-table .week-col {{ width: 240px; }}
  .monthly-return-table th {{ position: sticky; top: 0; z-index: 2; background: #2c3e50; color: white; padding: 7px 6px; border-right: 1px solid #d0d7de; border-bottom: 1px solid #d0d7de; text-align: center; }}
  .monthly-return-table td {{ padding: 5px 6px; border-right: 1px solid #d0d7de; border-bottom: 1px solid #d0d7de; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .monthly-return-table .merged-cell {{ vertical-align: middle; font-weight: 600; }}
  .monthly-return-table .pos {{ color: #dc2626; }}
  .monthly-return-table .neg {{ color: #16a34a; }}
  .monthly-return-table .neutral {{ color: #333333; }}
  .monthly-return-table .week-cell {{ font-size: 11px; line-height: 1.45; white-space: normal; overflow: visible; text-overflow: clip; vertical-align: top; }}
  .monthly-return-table .week-line {{ display: block; white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: anywhere; word-break: break-word; }}
  .html-table-wrap {{ max-height: 620px; overflow: auto; border: 1px solid #d0d7de; }}
  .report-table {{ border-collapse: separate; border-spacing: 0; width: 100%; min-width: 980px; font-size: 12px; }}
  .report-table th {{ position: sticky; top: 0; z-index: 2; background: #34495e; color: white; padding: 7px 8px; border-right: 1px solid #d0d7de; border-bottom: 1px solid #d0d7de; text-align: center; white-space: nowrap; }}
  .report-table td {{ padding: 6px 8px; border-right: 1px solid #d0d7de; border-bottom: 1px solid #d0d7de; white-space: nowrap; }}
  .report-table .text-cell {{ text-align: left; }}
  .report-table .date-cell {{ text-align: left; }}
  .report-table .num-cell {{ text-align: right; }}
  .report-table .pos {{ color: #dc2626; }}
  .report-table .neg {{ color: #16a34a; }}
  .report-table .empty-cell {{ color: #666; padding: 18px; }}
  .holdings-table tbody tr {{ background: #fff8e1; }}
  .trades-table .buy-row {{ background: #fff8e1; }}
  .trades-table .sell-row {{ background: #e8f5e9; }}
  .trades-table .buy-action-cell {{ color: #dc2626; font-weight: 600; }}
  .trades-table .sell-action-cell {{ color: #16a34a; font-weight: 600; }}
  .latest-candidates-table {{ min-width: 1320px; }}
  .latest-candidates-table .multiline-cell {{ white-space: pre-line; line-height: 1.45; vertical-align: top; }}
  .latest-candidates-table .buy-date-cell {{ color: #dc2626; font-weight: 600; }}
  .latest-candidates-table .sell-date-cell {{ color: #16a34a; font-weight: 600; }}
</style>
</head>
<body>
<div class="header">
  <h2>v8 BBI月度强弱轮动策略报表</h2>
  <p>回测区间：{start_date} ~ {end_date} &nbsp;|&nbsp; 初始资金：{INIT_CASH:,.0f}元 &nbsp;|&nbsp; 单票目标：约{BASE_POSITION_AMOUNT:,.0f}元起，常规4档封顶{MAX_POSITION_AMOUNT:,.0f}元；牛市额外第5档后单票最高约{V8_MAX_POSITION_AMOUNT:,.0f}元</p>
  <p>策略口径：每月第一个实际交易日开盘调仓，使用上一交易日收盘后的 BBI 强弱排名；若上证指数短期大跌或市场状态为熊市，则本次不新开仓。已合入“牛市提前买入”“纯牛市小额最后加仓”和“长期低效持仓退出”：牛市首买回撤阈值提前到 -2.5%（强趋势 -1.2%）；仅在信号日为牛市、已有持仓第 4 档后且浮盈达到 50% 时，允许第 5 档 5 万元额外加仓；持仓满 231 个交易日、信号日浮盈不大于 0%、且跌出候选榜前 20 时，次日开盘卖出；震荡/熊市不触发额外加仓，止损、熊市过滤、熊市小仓位试探不变。</p>
  <p>候选过滤：价格达到近 21 日最高价 95% 以上不买；近 20 个交易日出现过收盘跌停不买；游资风险命中 2 项及以上不买；加速失速/下跌风险不买（保留早期弱势下降趋势过滤，并额外排除上涨加速后失速、熊市式下跌加速风险）。</p>
  <p>板块风控：2025-01-02 起启用东方财富板块 overlay；使用 099_dc_daily 的信号日收盘板块行情，以及 098_dc_member 滞后一交易日的成分关系。若候选股暴露在 20 日跌幅或 20 日回撤触发的崩溃板块中，则不新买入。</p>
</div>
{sections_html}
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")


def find_free_port(start_port=REPORT_PORT_START, max_tries=200):
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free port found from {start_port} to {start_port + max_tries - 1}")


def open_report():
    try:
        port = find_free_port()
    except RuntimeError as exc:
        print(f"Auto open skipped: {exc}")
        print(f"Open report manually: {REPORT_PATH}")
        return
    subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port)],
        cwd=str(REPORT_PATH.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    time.sleep(0.5)
    url = f"http://localhost:{port}/report.html"
    webbrowser.open(url)
    print(f"Opening: {url}")


def main():
    summary, nav, trades, scores, rebalance_log, holdings = load_strategy_outputs()
    make_html(summary, nav, trades, scores, rebalance_log, holdings)
    print(f"Report saved: {REPORT_PATH}")
    open_report()


if __name__ == "__main__":
    main()

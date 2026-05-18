import csv
import json
import math
import shutil
import sys
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "tmp_v1_bear_accel_bbi_output"
README_PATH = TMP_DIR / "tmp_v1_bear_accel_bbi_README.md"
REPORT_PATH = OUTPUT_DIR / "report.html"
RESULTS_PATH = OUTPUT_DIR / "summary.csv"

INIT_CASH = 500_000.0
POSITION_AMOUNT = 80_000.0
MAX_HOLDINGS = 5
COMMISSION_BUY = 0.0005
COMMISSION_SELL = 0.0015
MIN_COMMISSION = 5.0
STOP_LOSS_PCT = -0.08
MAX_HOLD_DAYS = 30
ACCEL_LOOKBACK_DAYS = 10
MIN_RET_21 = -0.12
SLOPE_WINDOW = 10
SLOPE_DELTA_LAG = 5
SLOPE_QUANTILE_WINDOW = 252
SLOPE_QUANTILE = 0.20


SOURCE_NOTES = [
    {
        "topic": "恐慌卖出/下跌加速",
        "note": "Tavily 搜到 Investopedia 对 capitulation 的定义：市场下跌中的恐慌卖出会加速价格下跌。它支持“下跌加速”这个现象存在，但不等于买点有效。",
        "url": "https://www.investopedia.com/terms/c/capitulation.asp",
    },
    {
        "topic": "均线斜率",
        "note": "Tavily 搜到 MA slope 资料：斜率由均线当前值和过去值变化计算，正斜率表示上行趋势，负斜率表示下行趋势。",
        "url": "https://thetradinganalyst.com/moving-average-slope/",
    },
    {
        "topic": "均线技术规则论文",
        "note": "Tavily 搜到 Brock/Lakonishok/LeBaron 1992：论文检验移动均线和交易区间突破等简单技术规则，说明这些规则可以统计检验，但不保证本策略有效。",
        "url": "http://technicalanalysis.org.uk/support-and-resistance/BrockLakonishokLeBaron1992.pdf",
    },
    {
        "topic": "开源回测实现",
        "note": "Tavily 搜到 backtesting.py 与多个 GitHub MA crossover 项目，常见实现是均线穿越、止损、回测统计；也提醒 sideways/whipsaw 会影响策略。",
        "url": "https://kernc.github.io/backtesting.py/",
    },
    {
        "topic": "BBI 数据",
        "note": "BBI 使用 Tushare `063_stk_factor_pro.bbi_qfq`，不在本地重算。",
        "url": "docs/tushare/tushare.pro/document/23ac1.html",
    },
    {
        "topic": "执行规则",
        "note": "信号使用收盘后可见数据，交易在下一交易日开盘执行；避免同日收盘信号同日成交。",
        "url": "local: tmp_v1 design review",
    },
]


def reset_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def calc_commission(amount, is_buy):
    rate = COMMISSION_BUY if is_buy else COMMISSION_SELL
    return max(abs(float(amount)) * rate, MIN_COMMISSION)


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def build_market_regime(market):
    out = market.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("trade_date").reset_index(drop=True)
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["ma120"] = out["close"].rolling(120, min_periods=120).mean()
    out["ma120_slope_20"] = out["ma120"].pct_change(20, fill_method=None)
    out["high_252"] = out["close"].rolling(252, min_periods=120).max()
    out["dd_252"] = out["close"] / out["high_252"] - 1.0
    out["market_regime"] = np.where(
        (out["close"] < out["ma120"]) & (out["ma120_slope_20"] < 0),
        "bear",
        "non_bear",
    )
    return out[["trade_date", "close", "ma120", "ma120_slope_20", "dd_252", "market_regime"]]


def _rolling_slope(values):
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2 or np.isnan(arr).any():
        return np.nan
    x = np.arange(len(arr), dtype=float)
    x = x - x.mean()
    y = arr - arr.mean()
    denom = float((x * x).sum())
    if denom == 0:
        return np.nan
    return float((x * y).sum() / denom)


def add_bbi_reclaim_signal(panel):
    out = panel.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    prev_close = out.groupby("ts_code", sort=False)["close_qfq"].shift(1)
    prev_bbi = out.groupby("ts_code", sort=False)["bbi_qfq"].shift(1)
    out["bbi_reclaim"] = (
        (pd.to_numeric(prev_close, errors="coerce") <= pd.to_numeric(prev_bbi, errors="coerce"))
        & (pd.to_numeric(out["close_qfq"], errors="coerce") > pd.to_numeric(out["bbi_qfq"], errors="coerce"))
    )
    return out


def add_acceleration_features(panel):
    out = add_bbi_reclaim_signal(panel)
    grouped = out.groupby("ts_code", sort=False)
    log_close = np.log(pd.to_numeric(out["close_qfq"], errors="coerce").where(lambda s: s > 0))
    out["_log_close"] = log_close
    out["ret_21_accel"] = grouped["close_qfq"].pct_change(21, fill_method=None)
    out["slope_10"] = (
        out.groupby("ts_code", sort=False)["_log_close"]
        .rolling(SLOPE_WINDOW, min_periods=SLOPE_WINDOW)
        .apply(_rolling_slope, raw=True)
        .reset_index(level=0, drop=True)
    )
    out["slope_delta_5"] = out["slope_10"] - grouped["slope_10"].shift(SLOPE_DELTA_LAG)
    out["slope_delta_q20"] = (
        out.groupby("ts_code", sort=False)["slope_delta_5"]
        .rolling(SLOPE_QUANTILE_WINDOW, min_periods=60)
        .quantile(SLOPE_QUANTILE)
        .reset_index(level=0, drop=True)
    )
    out["slope_delta_q20"] = grouped["slope_delta_q20"].shift(1)
    out["accel_breach_today"] = (
        (out["ret_21_accel"] <= MIN_RET_21)
        & (out["slope_10"] < 0)
        & (out["slope_delta_5"] <= out["slope_delta_q20"])
    )
    shifted_breach = grouped["accel_breach_today"].shift(1)
    shifted_breach = shifted_breach.where(shifted_breach.notna(), False).astype(bool)
    out["prior_accel_breach_10"] = (
        shifted_breach.groupby(out["ts_code"], sort=False)
        .rolling(ACCEL_LOOKBACK_DAYS, min_periods=1)
        .max()
        .reset_index(level=0, drop=True)
        .astype(bool)
    )
    out["slope_improving_3"] = out["slope_10"] > grouped["slope_10"].shift(3)
    out["prev_low_5"] = (
        grouped["close_qfq"]
        .rolling(5, min_periods=5)
        .min()
        .reset_index(level=0, drop=True)
    )
    out["prev_low_5"] = grouped["prev_low_5"].shift(1)
    out["above_prev_low_5"] = out["close_qfq"] > out["prev_low_5"]
    out["setup_ready"] = (
        out["prior_accel_breach_10"]
        & (out["slope_improving_3"] | out["above_prev_low_5"])
        & out["bbi_reclaim"]
    )
    return out.drop(columns=["_log_close", "prev_low_5"])


def load_base_outputs():
    base = {}
    for label, directory in [("v4", V4_DIR), ("v5", V5_DIR), ("v6", V6_DIR)]:
        base[label] = {
            "summary": json.loads((directory / "output" / "summary.json").read_text(encoding="utf-8")),
            "nav": pd.read_csv(directory / "output" / "nav_series.csv"),
            "trades": pd.read_csv(directory / "output" / "trade_records.csv"),
        }
    return base


def load_v6_data():
    panel = pd.read_parquet(V6_DIR / "output" / "panel.parquet")
    market = pd.read_parquet(V6_DIR / "output" / "market_index.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    return panel, market


def is_limit_up_at_open(row):
    price = safe_float(row.get("open"))
    up_limit = safe_float(row.get("up_limit"))
    return not pd.isna(price) and not pd.isna(up_limit) and up_limit > 0 and price >= up_limit - 1e-6


def is_limit_down_at_open(row):
    price = safe_float(row.get("open"))
    down_limit = safe_float(row.get("down_limit"))
    return not pd.isna(price) and not pd.isna(down_limit) and down_limit > 0 and price <= down_limit + 1e-6


def get_open_price(row):
    price = safe_float(row.get("open_qfq"), safe_float(row.get("open")))
    return price if price > 0 else None


def can_buy(row):
    if bool(row.get("is_suspended", False)):
        return False
    if not bool(row.get("is_eligible", False)):
        return False
    if is_limit_up_at_open(row):
        return False
    return get_open_price(row) is not None


def can_sell(row):
    if bool(row.get("is_suspended", False)):
        return False
    if is_limit_down_at_open(row):
        return False
    return get_open_price(row) is not None


def should_signal_buy(row, variant):
    if variant == "bear_only" and row.get("market_regime") != "bear":
        return False
    return bool(row.get("setup_ready", False))


def choose_buy_candidates(signal_panel, variant):
    candidates = signal_panel[signal_panel.apply(lambda row: should_signal_buy(row, variant), axis=1)].copy()
    if candidates.empty:
        return candidates
    ret_21 = (
        pd.to_numeric(candidates["ret_21_accel"], errors="coerce")
        if "ret_21_accel" in candidates.columns
        else pd.Series(0.0, index=candidates.index)
    )
    slope_delta = (
        pd.to_numeric(candidates["slope_delta_5"], errors="coerce")
        if "slope_delta_5" in candidates.columns
        else pd.Series(0.0, index=candidates.index)
    )
    amount_ma20 = (
        pd.to_numeric(candidates["amount_ma20"], errors="coerce")
        if "amount_ma20" in candidates.columns
        else pd.Series(0.0, index=candidates.index)
    )
    candidates["rank_score"] = (
        -ret_21.fillna(0.0)
        + slope_delta.fillna(0.0)
    )
    candidates["_amount_ma20_sort"] = amount_ma20.fillna(0.0)
    return candidates.sort_values(["rank_score", "_amount_ma20_sort"], ascending=[False, False])


def position_return(pos, close_price):
    cost_value = float(pos["cost_price"]) * int(pos["shares"])
    if cost_value <= 0:
        return 0.0
    return float(close_price) * int(pos["shares"]) / cost_value - 1.0


def run_signal_backtest(panel, variant):
    data = panel.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data = data.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    dates = sorted(data["trade_date"].unique())
    rows_by_date = {date: frame.set_index("ts_code") for date, frame in data.groupby("trade_date", sort=False)}
    cash = INIT_CASH
    positions = {}
    nav_rows = []
    trades = []
    stats = {
        "variant": variant,
        "signal_days": 0,
        "buy_fills": 0,
        "sell_fills": 0,
        "blocked_buy_signals": 0,
        "bear_signal_days": 0,
        "non_bear_signal_days": 0,
    }

    for i, date in enumerate(dates):
        today = rows_by_date[date]
        signal_panel = rows_by_date[dates[i - 1]] if i > 0 else None

        for code in list(positions):
            if code not in today.index:
                continue
            row = today.loc[code]
            close_price = safe_float(row.get("close_qfq"), safe_float(row.get("close")))
            pos = positions[code]
            hold_days = int(pos.get("hold_days", 0)) + 1
            pos["hold_days"] = hold_days
            signal_row = signal_panel.loc[code] if signal_panel is not None and code in signal_panel.index else None
            cross_down = False
            stop_loss = False
            if signal_row is not None:
                cross_down = (
                    safe_float(signal_row.get("close_qfq")) < safe_float(signal_row.get("bbi_qfq"))
                )
                signal_close = safe_float(signal_row.get("close_qfq"))
                stop_loss = position_return(pos, signal_close) <= STOP_LOSS_PCT if signal_close > 0 else False
            timeout = hold_days >= MAX_HOLD_DAYS
            if (cross_down or stop_loss or timeout) and can_sell(row):
                price = get_open_price(row)
                shares = int(pos["shares"])
                amount = shares * price
                commission = calc_commission(amount, is_buy=False)
                cash += amount - commission
                reason = "cross_down" if cross_down else ("stop_loss" if stop_loss else "timeout")
                trades.append({
                    "date": str(pd.Timestamp(date).date()),
                    "ts_code": code,
                    "name": row.get("name", ""),
                    "action": "sell",
                    "price": round(price, 4),
                    "shares": shares,
                    "amount": round(amount, 2),
                    "commission": round(commission, 2),
                    "reason": reason,
                    "hold_days": hold_days,
                    "pnl_pct": round(position_return(pos, price) * 100.0, 4),
                })
                stats["sell_fills"] += 1
                del positions[code]

        if signal_panel is not None and len(positions) < MAX_HOLDINGS:
            candidates = choose_buy_candidates(signal_panel, variant)
            if not candidates.empty:
                stats["signal_days"] += 1
                if (candidates["market_regime"] == "bear").any():
                    stats["bear_signal_days"] += 1
                if (candidates["market_regime"] != "bear").any():
                    stats["non_bear_signal_days"] += 1
            for code, signal_row in candidates.iterrows():
                if len(positions) >= MAX_HOLDINGS:
                    break
                if code in positions or code not in today.index:
                    continue
                row = today.loc[code]
                if not can_buy(row):
                    stats["blocked_buy_signals"] += 1
                    continue
                price = get_open_price(row)
                shares = int(min(POSITION_AMOUNT, cash) / price / 100) * 100
                if shares <= 0:
                    continue
                amount = shares * price
                commission = calc_commission(amount, is_buy=True)
                if cash < amount + commission:
                    continue
                cash -= amount + commission
                positions[code] = {
                    "shares": shares,
                    "cost_price": price,
                    "buy_date": date,
                    "hold_days": 0,
                }
                trades.append({
                    "date": str(pd.Timestamp(date).date()),
                    "ts_code": code,
                    "name": row.get("name", signal_row.get("name", "")),
                    "action": "buy",
                    "price": round(price, 4),
                    "shares": shares,
                    "amount": round(amount, 2),
                    "commission": round(commission, 2),
                    "reason": f"{variant}_accel_bbi_reclaim",
                    "hold_days": 0,
                    "pnl_pct": 0.0,
                })
                stats["buy_fills"] += 1

        market_value = 0.0
        for code, pos in positions.items():
            if code in today.index:
                row = today.loc[code]
                price = safe_float(row.get("close_qfq"), safe_float(row.get("close")))
                if price > 0:
                    market_value += int(pos["shares"]) * price
        nav_rows.append({
            "date": str(pd.Timestamp(date).date()),
            "nav": round(cash + market_value, 2),
            "cash": round(cash, 2),
            "holdings": len(positions),
        })

    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    nav.attrs["stats"] = stats
    return nav, trades_df


def calc_nav_metrics(nav, trades):
    nav = nav.copy()
    nav["date"] = pd.to_datetime(nav["date"])
    total_ret = nav["nav"].iloc[-1] / nav["nav"].iloc[0] - 1.0
    days = max((nav["date"].iloc[-1] - nav["date"].iloc[0]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    curve = nav["nav"] / nav["nav"].iloc[0]
    dd = curve / curve.cummax() - 1.0
    sell_trades = trades[trades["action"] == "sell"].copy() if not trades.empty else pd.DataFrame()
    win_rate = 0.0
    avg_hold_days = 0.0
    if not sell_trades.empty and "pnl_pct" in sell_trades.columns:
        pnl = pd.to_numeric(sell_trades["pnl_pct"], errors="coerce")
        win_rate = float((pnl > 0).mean() * 100.0)
        avg_hold_days = float(pd.to_numeric(sell_trades["hold_days"], errors="coerce").mean())
    return {
        "final_nav": round(float(nav["nav"].iloc[-1]), 2),
        "total_return_pct": round(float(total_ret * 100.0), 4),
        "annual_return_pct": round(float(annual_ret * 100.0), 4),
        "max_drawdown_pct": round(float(dd.min() * 100.0), 4),
        "calmar_ratio": round(float(annual_ret * 100.0 / abs(dd.min() * 100.0)), 4) if dd.min() < 0 else 0.0,
        "avg_cash_pct": round(float((nav["cash"] / nav["nav"]).mean() * 100.0), 4),
        "avg_holdings": round(float(nav["holdings"].mean()), 4),
        "trade_records": int(len(trades)),
        "win_rate_pct": round(win_rate, 4),
        "avg_hold_days": round(avg_hold_days, 4),
    }


def annual_return_table(nav_by_label):
    rows = []
    for label, nav in nav_by_label.items():
        df = nav.copy()
        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["nav"]
        year_end = series.resample("YE").last()
        year_start = year_end.shift(1)
        if not year_start.empty:
            year_start.iloc[0] = series.iloc[0]
        for date, end_nav in year_end.items():
            start_nav = year_start.loc[date]
            rows.append({
                "year": int(date.year),
                "strategy": label,
                "return_pct": round(float((end_nav / start_nav - 1.0) * 100.0), 4),
            })
    return pd.DataFrame(rows)


def monthly_return_table(nav_by_label):
    rows = []
    for label, nav in nav_by_label.items():
        df = nav.copy()
        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["nav"]
        month_end = series.resample("ME").last()
        month_start = month_end.shift(1)
        if not month_start.empty:
            month_start.iloc[0] = series.iloc[0]
        for date, end_nav in month_end.items():
            start_nav = month_start.loc[date]
            rows.append({
                "month": str(date.date())[:7],
                "strategy": label,
                "return_pct": round(float((end_nav / start_nav - 1.0) * 100.0), 4),
            })
    return pd.DataFrame(rows)


def html_table(df, float_cols=None):
    float_cols = float_cols or set()
    out = ["<table><thead><tr>"]
    for col in df.columns:
        out.append(f"<th>{escape(str(col))}</th>")
    out.append("</tr></thead><tbody>")
    for _, row in df.iterrows():
        out.append("<tr>")
        for col in df.columns:
            value = row[col]
            if col in float_cols and pd.notna(value):
                text = f"{float(value):,.2f}"
            else:
                text = str(value)
            klass = ""
            if col in float_cols and pd.notna(value):
                klass = " class=\"pos\"" if float(value) > 0 else (" class=\"neg\"" if float(value) < 0 else "")
            out.append(f"<td{klass}>{escape(text)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def write_readme(summary, expert_notes):
    best = summary.sort_values(["total_return_pct", "calmar_ratio"], ascending=[False, False]).iloc[0]
    lines = [
        "# tmp_v1 Bear Acceleration BBI Experiment",
        "",
        "## 工作推进",
        "- 使用 Superpowers 流程：头脑风暴、计划、TDD、设计评审、开发、运行验证。",
        "- 设计评审专家建议：简化熊市定义，排除确认日同日加速，执行日检查可交易性。",
        "- Tavily 搜索：已补充完成，覆盖 capitulation、均线斜率、移动均线论文、GitHub/开源回测实现。",
        "- 开发范围：只写入 `scripts/bbi/backtrader/tmp`。",
        "",
        "## 专家意见",
        expert_notes,
        "",
        "## Tavily 复核",
        "- Capitulation：公开定义支持“恐慌卖出会加速下跌”，但只是现象，不是可直接买入的充分条件。",
        "- MA slope：公开资料支持用均线斜率量化趋势方向，负斜率表示下行趋势。",
        "- Brock/Lakonishok/LeBaron 1992：移动均线和交易区间突破属于可统计检验的经典技术规则。",
        "- GitHub/backtesting.py：开源实现多为 MA crossover、RSI、止损和回测模板；没有证据支持本 tmp_v1 规则天然优于 v6。",
        "",
        "## 结果摘要",
        summary.to_markdown(index=False),
        "",
        "## 初步建议",
        f"- 本轮最佳净值策略：{best['strategy']}，总收益 {best['total_return_pct']:.2f}%。",
        "- 是否合并：如果 tmp_v1 不能显著超过 v6 且回撤不改善，不建议合并；若超过也应先做参数邻域和成本压力测试。",
    ]
    README_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_report(summary, annual, monthly, expert_notes):
    best = summary.sort_values(["total_return_pct", "calmar_ratio"], ascending=[False, False]).iloc[0]
    v6_row = summary[summary["strategy"] == "v6"].iloc[0]
    if best["strategy"].startswith("tmp_v1") and best["total_return_pct"] > v6_row["total_return_pct"]:
        advice = "可以进入下一轮候选，但还不建议直接合并；先做参数邻域、成本、样本外压力测试。"
    else:
        advice = "不建议合并。当前 tmp_v1 规则没有证明能稳定超过 v6。"
    source_rows = "".join(
        f"<tr><td>{escape(item['topic'])}</td><td>{escape(item['note'])}</td><td>{escape(item['url'])}</td></tr>"
        for item in SOURCE_NOTES
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>tmp_v1 熊市下跌加速 BBI 买点实验</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #111827; background: #f5f7fa; }}
h1, h2 {{ margin: 18px 0 10px; }}
.note {{ padding: 12px; background: #fff; border-left: 4px solid #2563eb; margin: 12px 0; line-height: 1.7; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; margin: 10px 0 22px; }}
th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #374151; color: white; }}
.wide {{ max-height: 520px; overflow: auto; border: 1px solid #d1d5db; background: #fff; }}
.pos {{ color: #dc2626; }}
.neg {{ color: #16a34a; }}
</style>
</head>
<body>
<h1>tmp_v1 熊市下跌加速 BBI 买点实验</h1>
<div class="note">
<b>合并建议：</b>{escape(advice)}<br>
<b>本轮最佳：</b>{escape(str(best['strategy']))}，总收益 {best['total_return_pct']:.2f}%，最大回撤 {best['max_drawdown_pct']:.2f}%。<br>
<b>当前 v6：</b>总收益 {v6_row['total_return_pct']:.2f}%，最大回撤 {v6_row['max_drawdown_pct']:.2f}%。
</div>
<h2>专家评审摘要</h2>
<div class="note">{escape(expert_notes)}</div>
<h2>总览：v4 / v5 / v6 / tmp_v1</h2>
{html_table(summary, float_cols=set(summary.columns) - {'strategy', 'trade_records'})}
<h2>年度收益对比（%）</h2>
<div class="wide">{html_table(annual, float_cols=set(annual.columns) - {'year'})}</div>
<h2>最近 36 个月收益对比（%）</h2>
<div class="wide">{html_table(monthly.tail(36), float_cols=set(monthly.columns) - {'month'})}</div>
<h2>依据和数据</h2>
<table><thead><tr><th>主题</th><th>说明</th><th>来源</th></tr></thead><tbody>{source_rows}</tbody></table>
<h2>下一步</h2>
<ol>
<li>若 tmp_v1 优于 v6：做参数邻域、滑点成本和分段样本外复核。</li>
<li>若 tmp_v1 弱于 v6：保留报告，不合并，继续分析 2022-2024 v6 弱段亏损来源。</li>
<li>可加一个简单基线：21 日大跌后 BBI 上穿，不加斜率加速，验证“加速”是否真的贡献收益。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")


def run_experiment():
    reset_output_dir()
    base = load_base_outputs()
    panel, market = load_v6_data()
    regime = build_market_regime(market)
    panel = add_acceleration_features(panel)
    panel = panel.merge(regime[["trade_date", "market_regime", "dd_252"]], on="trade_date", how="left")

    variants = {}
    for variant in ["bear_only", "all_market"]:
        nav, trades = run_signal_backtest(panel, variant)
        nav.to_csv(OUTPUT_DIR / f"{variant}_nav_series.csv", index=False)
        trades.to_csv(OUTPUT_DIR / f"{variant}_trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
        stats = calc_nav_metrics(nav, trades)
        stats.update(nav.attrs.get("stats", {}))
        (OUTPUT_DIR / f"{variant}_summary.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        variants[f"tmp_v1_{variant}"] = {"nav": nav, "trades": trades, "summary": stats}

    summary_rows = []
    nav_by_label = {}
    for label, data in base.items():
        row = dict(data["summary"])
        row["strategy"] = label
        summary_rows.append(row)
        nav_by_label[label] = data["nav"]
    for label, data in variants.items():
        row = dict(data["summary"])
        row["strategy"] = label
        summary_rows.append(row)
        nav_by_label[label] = data["nav"]

    keep_cols = [
        "strategy", "final_nav", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
        "calmar_ratio", "avg_cash_pct", "avg_holdings", "trade_records", "win_rate_pct",
        "avg_hold_days", "signal_days", "bear_signal_days", "non_bear_signal_days",
        "blocked_buy_signals",
    ]
    summary = pd.DataFrame(summary_rows)
    for col in keep_cols:
        if col not in summary.columns:
            summary[col] = np.nan
    summary = summary[keep_cols]
    summary.to_csv(RESULTS_PATH, index=False)

    annual = annual_return_table(nav_by_label).pivot(index="year", columns="strategy", values="return_pct").reset_index()
    monthly = monthly_return_table(nav_by_label).pivot(index="month", columns="strategy", values="return_pct").reset_index()
    annual.to_csv(OUTPUT_DIR / "annual_returns.csv", index=False)
    monthly.to_csv(OUTPUT_DIR / "monthly_returns.csv", index=False)

    expert_notes = (
        "设计专家指出：原方案阈值过多、容易过拟合；已调整为单一熊市定义 "
        "`close < MA120 且 MA120_slope_20 < 0`，并把 252 日回撤仅作为诊断。"
        "数据 QA 指出：加速信号必须排除确认日，交易必须在下一交易日开盘并检查执行日可交易性；已按此实现。"
    )
    write_readme(summary, expert_notes)
    write_report(summary, annual, monthly, expert_notes)
    return summary


def main():
    summary = run_experiment()
    print(summary.to_string(index=False))
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()


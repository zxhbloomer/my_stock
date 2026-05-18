import csv
import json
import shutil
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
OUTPUT_DIR = TMP_DIR / "tmp_v2_bull_pullback_bbi_output"
README_PATH = TMP_DIR / "tmp_v2_bull_pullback_bbi_README.md"
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
PULLBACK_MIN = -0.15
PULLBACK_MAX = -0.04
BELOW_BBI_LOOKBACK = 10
HOT_MONEY_MAX_HITS = 2


SOURCE_NOTES = [
    {
        "topic": "Pullback",
        "note": "Tavily 搜到 Investopedia：pullback 是上涨轨迹中的短期下跌或暂停，常被视为买入机会。",
        "url": "https://www.investopedia.com/terms/p/pullback.asp",
    },
    {
        "topic": "均线支撑",
        "note": "Tavily 搜到 Investopedia Golden Cross：移动均线在 pullback 中可作为支撑，直到重新下穿。",
        "url": "https://www.investopedia.com/terms/g/goldencross.asp",
    },
    {
        "topic": "趋势交易",
        "note": "Tavily 搜到 trend trading 资料：趋势交易顺主趋势，不试图预测精确顶部和底部。",
        "url": "https://www.investopedia.com/articles/active-trading/041814/four-most-commonlyused-indicators-trend-trading.asp",
    },
    {
        "topic": "开源实现",
        "note": "Tavily 搜到 GitHub/Backtesting.py 示例：常见实现是均线穿越、pullback/RSI、止损和回测统计，必须验证 whipsaw 和交易成本。",
        "url": "https://kernc.github.io/backtesting.py/",
    },
    {
        "topic": "Tushare 数据",
        "note": "使用 v6 已准备的 Tushare parquet：`063_stk_factor_pro.bbi_qfq`、复权价格、涨跌停、ST/流动性过滤等。",
        "url": "docs/tushare/接口清单.md",
    },
]


def reset_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def calc_commission(amount, is_buy):
    rate = COMMISSION_BUY if is_buy else COMMISSION_SELL
    return max(abs(float(amount)) * rate, MIN_COMMISSION)


def build_market_regime(market):
    out = market.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("trade_date").reset_index(drop=True)
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["ma120"] = out["close"].rolling(120, min_periods=120).mean()
    out["ma120_slope_20"] = out["ma120"].pct_change(20, fill_method=None)
    out["high_252"] = out["close"].rolling(252, min_periods=120).max()
    out["dd_252"] = out["close"] / out["high_252"] - 1.0
    bear = (out["close"] < out["ma120"]) & (out["ma120_slope_20"] < 0)
    bull = (out["close"] > out["ma120"]) & (out["ma120_slope_20"] > 0) & (out["dd_252"] > -0.15)
    out["market_regime"] = np.select([bull, bear], ["bull", "bear"], default="neutral")
    return out[["trade_date", "close", "ma120", "ma120_slope_20", "dd_252", "market_regime"]]


def add_bull_pullback_features(panel):
    out = panel.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = out.groupby("ts_code", sort=False)

    prev_close = grouped["close_qfq"].shift(1)
    prev_bbi = grouped["bbi_qfq"].shift(1)
    out["bbi_reclaim"] = (
        (pd.to_numeric(prev_close, errors="coerce") <= pd.to_numeric(prev_bbi, errors="coerce"))
        & (pd.to_numeric(out["close_qfq"], errors="coerce") > pd.to_numeric(out["bbi_qfq"], errors="coerce"))
    )
    out["below_bbi"] = pd.to_numeric(out["close_qfq"], errors="coerce") < pd.to_numeric(out["bbi_qfq"], errors="coerce")
    shifted_below_bbi = grouped["below_bbi"].shift(1)
    out["recent_below_bbi_10"] = (
        shifted_below_bbi.groupby(out["ts_code"], sort=False)
        .rolling(BELOW_BBI_LOOKBACK, min_periods=1)
        .max()
        .reset_index(level=0, drop=True)
        .where(lambda s: s.notna(), False)
        .astype(bool)
    )
    pullback = pd.to_numeric(out["pullback_63"], errors="coerce")
    out["healthy_pullback"] = (pullback >= PULLBACK_MIN) & (pullback <= PULLBACK_MAX)
    hot_money_hits = (
        pd.to_numeric(out["hot_money_risk_hits"], errors="coerce")
        if "hot_money_risk_hits" in out.columns
        else pd.Series(0, index=out.index)
    )
    out["trend_quality"] = (
        out["is_eligible"].fillna(False).astype(bool)
        & (pd.to_numeric(out["above_ratio_63"], errors="coerce") >= 0.55)
        & (pd.to_numeric(out["above_ratio_126"], errors="coerce") >= 0.50)
        & (pd.to_numeric(out["ret_63"], errors="coerce") >= 0)
        & (hot_money_hits.fillna(99) < HOT_MONEY_MAX_HITS)
    )
    out["setup_ready"] = (
        out["trend_quality"]
        & (out["healthy_pullback"] | out["recent_below_bbi_10"])
        & out["bbi_reclaim"]
    )
    return out


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


def get_open_price(row):
    price = safe_float(row.get("open_qfq"), safe_float(row.get("open")))
    return price if price > 0 else None


def is_limit_up_at_open(row):
    price = safe_float(row.get("open"))
    up_limit = safe_float(row.get("up_limit"))
    return not pd.isna(price) and not pd.isna(up_limit) and up_limit > 0 and price >= up_limit - 1e-6


def is_limit_down_at_open(row):
    price = safe_float(row.get("open"))
    down_limit = safe_float(row.get("down_limit"))
    return not pd.isna(price) and not pd.isna(down_limit) and down_limit > 0 and price <= down_limit + 1e-6


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
    if not bool(row.get("setup_ready", False)):
        return False
    regime = row.get("market_regime")
    if variant == "bull_reclaim":
        return regime == "bull"
    if variant == "non_bear_reclaim":
        return regime != "bear"
    raise ValueError(f"unknown variant: {variant}")


def choose_buy_candidates(signal_panel, variant):
    candidates = signal_panel[signal_panel.apply(lambda row: should_signal_buy(row, variant), axis=1)].copy()
    if candidates.empty:
        return candidates
    def numeric_col(name, default=0.0):
        if name in candidates.columns:
            return pd.to_numeric(candidates[name], errors="coerce").fillna(default)
        return pd.Series(default, index=candidates.index)

    candidates["rank_score"] = (
        0.35 * numeric_col("above_ratio_63")
        + 0.25 * numeric_col("above_ratio_126")
        + 0.20 * numeric_col("ret_63").clip(lower=-1.0, upper=2.0)
        - 0.10 * numeric_col("volatility_63")
        - 0.10 * numeric_col("hot_money_risk_hits")
    )
    candidates["_amount_ma20_sort"] = numeric_col("amount_ma20")
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
        "signal_days_capacity_available": 0,
        "buy_fills": 0,
        "sell_fills": 0,
        "blocked_buy_signals": 0,
        "bull_signal_days": 0,
        "neutral_signal_days": 0,
        "deferred_sell_signals": 0,
    }

    for i, date in enumerate(dates):
        today = rows_by_date[date]
        signal_panel = rows_by_date[dates[i - 1]] if i > 0 else None

        for code in list(positions):
            if code not in today.index:
                continue
            row = today.loc[code]
            pos = positions[code]
            hold_days = int(pos.get("hold_days", 0)) + 1
            pos["hold_days"] = hold_days
            signal_row = signal_panel.loc[code] if signal_panel is not None and code in signal_panel.index else None
            cross_down = False
            stop_loss = False
            if signal_row is not None:
                cross_down = safe_float(signal_row.get("close_qfq")) < safe_float(signal_row.get("bbi_qfq"))
                signal_close = safe_float(signal_row.get("close_qfq"))
                stop_loss = position_return(pos, signal_close) <= STOP_LOSS_PCT if signal_close > 0 else False
            timeout = hold_days >= MAX_HOLD_DAYS
            exit_signal = cross_down or stop_loss or timeout
            if exit_signal and not can_sell(row):
                stats["deferred_sell_signals"] += 1
            if exit_signal and can_sell(row):
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
                stats["signal_days_capacity_available"] += 1
                if (candidates["market_regime"] == "bull").any():
                    stats["bull_signal_days"] += 1
                if (candidates["market_regime"] == "neutral").any():
                    stats["neutral_signal_days"] += 1
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
                positions[code] = {"shares": shares, "cost_price": price, "buy_date": date, "hold_days": 0}
                trades.append({
                    "date": str(pd.Timestamp(date).date()),
                    "ts_code": code,
                    "name": row.get("name", signal_row.get("name", "")),
                    "action": "buy",
                    "price": round(price, 4),
                    "shares": shares,
                    "amount": round(amount, 2),
                    "commission": round(commission, 2),
                    "reason": f"{variant}_pullback_bbi_reclaim",
                    "hold_days": 0,
                    "pnl_pct": 0.0,
                })
                stats["buy_fills"] += 1

        market_value = 0.0
        for code, pos in positions.items():
            if code in today.index:
                price = safe_float(today.loc[code].get("close_qfq"), safe_float(today.loc[code].get("close")))
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
    sells = trades[trades["action"] == "sell"].copy() if not trades.empty else pd.DataFrame()
    win_rate = 0.0
    avg_hold_days = 0.0
    if not sells.empty and "pnl_pct" in sells.columns:
        pnl = pd.to_numeric(sells["pnl_pct"], errors="coerce")
        win_rate = float((pnl > 0).mean() * 100.0)
        avg_hold_days = float(pd.to_numeric(sells["hold_days"], errors="coerce").mean())
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
            rows.append({"year": int(date.year), "strategy": label, "return_pct": round(float((end_nav / year_start.loc[date] - 1.0) * 100.0), 4)})
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
            rows.append({"month": str(date.date())[:7], "strategy": label, "return_pct": round(float((end_nav / month_start.loc[date] - 1.0) * 100.0), 4)})
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
            text = f"{float(value):,.2f}" if col in float_cols and pd.notna(value) else str(value)
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
        "# tmp_v2 Bull Pullback BBI Experiment",
        "",
        "## 工作推进",
        "- 使用 Superpowers 流程：头脑风暴、计划、TDD、设计评审、开发、运行验证。",
        "- Tavily 搜索支持：pullback 在上升趋势中常被视为买点候选；移动均线可作支撑/确认；趋势交易顺主趋势。",
        "- 设计评审专家建议：先只测 `bull_reclaim` 与 `non_bear_reclaim`，不要混入 v6 排名增强。",
        "- 开发范围：只写入 `scripts/bbi/backtrader/tmp`。",
        "",
        "## 专家意见",
        expert_notes,
        "",
        "## 结果摘要",
        summary.to_markdown(index=False),
        "",
        "## 初步建议",
        f"- 本轮最佳净值策略：{best['strategy']}，总收益 {best['total_return_pct']:.2f}%。",
        "- 是否合并：只有 tmp_v2 明显超过 v6 且回撤恶化不超过 3 个百分点，才进入合并候选；否则保留为失败/观察实验。",
        "- 比较口径：tmp_v2 是 qfq 价格口径的独立 tmp 策略系统，v4/v5/v6 是既有完整系统输出；此处用于收益/风险方向性比较，不等同于完全相同的撮合账本。",
    ]
    README_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_report(summary, annual, monthly, expert_notes):
    best = summary.sort_values(["total_return_pct", "calmar_ratio"], ascending=[False, False]).iloc[0]
    v6_row = summary[summary["strategy"] == "v6"].iloc[0]
    if best["strategy"].startswith("tmp_v2") and best["total_return_pct"] > v6_row["total_return_pct"] and best["max_drawdown_pct"] >= v6_row["max_drawdown_pct"] - 3.0:
        advice = "可进入下一轮合并候选，但先做参数邻域、成本和样本外压力测试。"
    else:
        advice = "不建议合并。当前 tmp_v2 没有在收益/回撤上明确击败 v6。"
    source_rows = "".join(
        f"<tr><td>{escape(item['topic'])}</td><td>{escape(item['note'])}</td><td>{escape(item['url'])}</td></tr>"
        for item in SOURCE_NOTES
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>tmp_v2 牛市回撤 BBI 修复买点实验</title>
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
<h1>tmp_v2 牛市回撤 BBI 修复买点实验</h1>
<div class="note">
<b>合并建议：</b>{escape(advice)}<br>
<b>本轮最佳：</b>{escape(str(best['strategy']))}，总收益 {best['total_return_pct']:.2f}%，最大回撤 {best['max_drawdown_pct']:.2f}%。<br>
<b>当前 v6：</b>总收益 {v6_row['total_return_pct']:.2f}%，最大回撤 {v6_row['max_drawdown_pct']:.2f}%。
</div>
<h2>专家评审摘要</h2>
<div class="note">{escape(expert_notes)}</div>
<div class="note">比较口径提醒：tmp_v2 使用 qfq 价格口径做独立 tmp 回测，v4/v5/v6 为既有完整系统输出；本报表用于方向性收益/风险比较，不表示撮合账本完全一致。</div>
<h2>总览：v4 / v5 / v6 / tmp_v2</h2>
{html_table(summary, float_cols=set(summary.columns) - {'strategy', 'trade_records'})}
<h2>年度收益对比（%）</h2>
<div class="wide">{html_table(annual, float_cols=set(annual.columns) - {'year'})}</div>
<h2>最近 36 个月收益对比（%）</h2>
<div class="wide">{html_table(monthly.tail(36), float_cols=set(monthly.columns) - {'month'})}</div>
<h2>Tavily 依据和数据</h2>
<table><thead><tr><th>主题</th><th>说明</th><th>来源</th></tr></thead><tbody>{source_rows}</tbody></table>
<h2>下一步</h2>
<ol>
<li>若 tmp_v2 优于 v6：做参数邻域、滑点成本和分段样本外复核。</li>
<li>若 tmp_v2 弱于 v6：保留报告，不合并，继续分析 v6 弱段或考虑把 pullback 作为 v6 加仓条件而非独立策略。</li>
<li>后续可单独测试 `bull_reclaim_plus_v6_rank`，但只有在基础信号有效后再做。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")


def run_experiment():
    reset_output_dir()
    base = load_base_outputs()
    panel, market = load_v6_data()
    regime = build_market_regime(market)
    panel = add_bull_pullback_features(panel)
    panel = panel.merge(regime[["trade_date", "market_regime", "dd_252"]], on="trade_date", how="left")

    variants = {}
    for variant in ["bull_reclaim", "non_bear_reclaim"]:
        nav, trades = run_signal_backtest(panel, variant)
        nav.to_csv(OUTPUT_DIR / f"{variant}_nav_series.csv", index=False)
        trades.to_csv(OUTPUT_DIR / f"{variant}_trade_records.csv", index=False, quoting=csv.QUOTE_MINIMAL)
        stats = calc_nav_metrics(nav, trades)
        stats.update(nav.attrs.get("stats", {}))
        (OUTPUT_DIR / f"{variant}_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        variants[f"tmp_v2_{variant}"] = {"nav": nav, "trades": trades, "summary": stats}

    rows = []
    nav_by_label = {}
    for label, data in base.items():
        row = dict(data["summary"])
        row["strategy"] = label
        rows.append(row)
        nav_by_label[label] = data["nav"]
    for label, data in variants.items():
        row = dict(data["summary"])
        row["strategy"] = label
        rows.append(row)
        nav_by_label[label] = data["nav"]

    keep_cols = [
        "strategy", "final_nav", "total_return_pct", "annual_return_pct", "max_drawdown_pct",
        "calmar_ratio", "avg_cash_pct", "avg_holdings", "trade_records", "win_rate_pct",
        "avg_hold_days", "signal_days_capacity_available", "bull_signal_days", "neutral_signal_days",
        "blocked_buy_signals",
    ]
    summary = pd.DataFrame(rows)
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
        "设计专家认为：修正后的理论方向合理，pullback 应只在趋势支持时测试；"
        "`bull_reclaim` 最干净，`non_bear_reclaim` 是对照但可能混入震荡 whipsaw。"
        "已按建议去掉 v6 排名叠加，先验证基础信号。"
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


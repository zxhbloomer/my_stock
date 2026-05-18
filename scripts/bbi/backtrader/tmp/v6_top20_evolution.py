from __future__ import annotations

import html
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
RUN_DIR = TMP_DIR / "2018_v6_top20_evolution"
README_PATH = RUN_DIR / "README.md"
DESIGN_PATH = RUN_DIR / "design_review.md"
PLAN_PATH = RUN_DIR / "implementation_plan.md"
REPORT_PATH = RUN_DIR / "report.html"

YEAR_START = pd.Timestamp("2018-01-01")
YEAR_END = pd.Timestamp("2018-12-31")
FIRST_TRADE_MAX = pd.Timestamp("2018-01-10")
LAST_TRADE_MIN = pd.Timestamp("2018-12-20")
MIN_LIST_DAYS = 365
HOT_MONEY_MAX_HITS = 1
INIT_CASH = 500_000.0
COMMISSION_BUY = 0.0005
COMMISSION_SELL = 0.0015
MIN_COMMISSION = 5.0


def ensure_run_dir():
    RUN_DIR.mkdir(parents=True, exist_ok=True)


def append_progress(message: str):
    ensure_run_dir()
    with README_PATH.open("a", encoding="utf-8") as f:
        f.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def pct(value, digits=2):
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}%"


def zscore(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    std = series.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def rank_top_returns(panel: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    data = panel.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data = data[(data["trade_date"] >= YEAR_START) & (data["trade_date"] <= YEAR_END)]
    data = data.sort_values(["ts_code", "trade_date"])

    rows = []
    for code, group in data.groupby("ts_code", sort=False):
        group = group.dropna(subset=["close_qfq"])
        if group.empty:
            continue
        first = group.iloc[0]
        last = group.iloc[-1]
        if first["trade_date"] > FIRST_TRADE_MAX or last["trade_date"] < LAST_TRADE_MIN:
            continue
        if pd.isna(first.get("list_days")) or first["list_days"] < MIN_LIST_DAYS:
            continue
        if bool(group.get("is_st", pd.Series(False, index=group.index)).fillna(False).any()):
            continue
        if bool(group.get("is_suspended", pd.Series(False, index=group.index)).fillna(False).any()):
            continue
        if int(group.get("hot_money_risk_hits", pd.Series(0, index=group.index)).fillna(0).max()) > HOT_MONEY_MAX_HITS:
            continue
        start_close = float(first["close_qfq"])
        end_close = float(last["close_qfq"])
        if not np.isfinite(start_close) or start_close <= 0 or not np.isfinite(end_close):
            continue
        rows.append(
            {
                "rank": 0,
                "ts_code": code,
                "name": first.get("name", code),
                "start_date": first["trade_date"],
                "end_date": last["trade_date"],
                "start_close_qfq": start_close,
                "end_close_qfq": end_close,
                "annual_return_pct": (end_close / start_close - 1.0) * 100.0,
                "list_date": first.get("list_date", ""),
                "list_days_at_start": int(first["list_days"]),
                "max_hot_money_hits": int(group.get("hot_money_risk_hits", pd.Series(0, index=group.index)).fillna(0).max()),
            }
        )
    result = pd.DataFrame(rows).sort_values("annual_return_pct", ascending=False).head(top_n).reset_index(drop=True)
    if not result.empty:
        result["rank"] = np.arange(1, len(result) + 1)
    return result


def load_variant(variant: str) -> dict:
    output = BACKTRADER_DIR / variant / "output"
    panel_path = output / "panel.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(f"Missing {panel_path}")
    panel = pd.read_parquet(panel_path)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    data = {"panel": panel}
    for name in ["summary", "trade_records", "strength_scores", "rebalance_log", "nav_series", "market_index"]:
        path_json = output / f"{name}.json"
        path_csv = output / f"{name}.csv"
        path_parquet = output / f"{name}.parquet"
        if path_json.exists():
            data[name] = json.loads(path_json.read_text(encoding="utf-8"))
        elif path_csv.exists():
            data[name] = pd.read_csv(path_csv)
        elif path_parquet.exists():
            frame = pd.read_parquet(path_parquet)
            if "trade_date" in frame.columns:
                frame["trade_date"] = pd.to_datetime(frame["trade_date"])
            data[name] = frame
    return data


def prepare_v6_diagnostic_scores(panel: pd.DataFrame, market_index: pd.DataFrame | None) -> pd.DataFrame:
    data = panel.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data = data[(data["trade_date"] >= YEAR_START) & (data["trade_date"] <= YEAR_END)]

    if market_index is not None:
        market = market_index.copy()
        market["trade_date"] = pd.to_datetime(market["trade_date"])
        market = market.sort_values("trade_date")
        close = pd.to_numeric(market["close"], errors="coerce")
        market["ma120"] = close.rolling(120, min_periods=120).mean()
        market["ma200"] = close.rolling(200, min_periods=200).mean()
        market["ma120_slope_20"] = market["ma120"] / market["ma120"].shift(20) - 1.0
        market["dd_252"] = close / close.rolling(252, min_periods=120).max() - 1.0
        breadth = data[data["is_eligible"].fillna(False)].groupby("trade_date")["above_bbi"].mean().rename("breadth_above_bbi")
        market = market.merge(breadth.reset_index(), on="trade_date", how="left")
        market["market_regime"] = np.where(
            (market["dd_252"] <= -0.20)
            | ((close < market["ma120"]) & (market["ma120_slope_20"] < 0) & (market["breadth_above_bbi"] < 0.45)),
            "bear",
            np.where(
                (close > market["ma120"]) & (close > market["ma200"]) & (market["ma120_slope_20"] > 0) & (market["dd_252"] > -0.10),
                "bull",
                "neutral",
            ),
        )
        data = data.merge(market[["trade_date", "market_regime", "dd_252", "breadth_above_bbi"]], on="trade_date", how="left")
    else:
        data["market_regime"] = "unknown"
        data["dd_252"] = np.nan
        data["breadth_above_bbi"] = np.nan

    hot_money_ok = data["hot_money_risk_hits"].fillna(99) < 2
    data["raw_candidate"] = data["is_eligible"].fillna(False)
    data["strong_trend"] = (
        (data["above_ratio_63"] >= 0.80)
        & (data["above_ratio_126"] >= 0.60)
        & (data["ret_63"] >= 0.80)
        & hot_money_ok
        & (data["recent_limit_down_20"] == 0)
    )
    recent_high_risk = (data["high_pos_21"] >= 0.95) & ~data["strong_trend"]
    ret_21_ok = (data["ret_21"] <= 0.45) | data["strong_trend"]
    data["after_base_filters"] = (
        data["raw_candidate"]
        & (data["above_ratio_63"] >= 0.55)
        & (data["above_ratio_126"] >= 0.50)
        & (data["ret_63"] >= 0.0)
        & ret_21_ok
        & (data["avg_distance_63"] <= 0.18)
        & data["high_pos_21"].notna()
        & data["high_pos_63"].notna()
        & data["range_pos_63"].notna()
        & (data["recent_limit_down_20"] == 0)
        & hot_money_ok
        & ~recent_high_risk
        & data["volatility_63"].notna()
        & data["amount_ma20"].notna()
    )
    data["blocked_by_market_regime"] = data["market_regime"].eq("bear")
    data["blocked_by_downtrend"] = data.get("early_weakness_downtrend", pd.Series(False, index=data.index)).fillna(False).astype(bool)
    pullback_threshold = np.where(data["strong_trend"], -0.026, np.where(data["market_regime"].eq("bear"), -0.07, -0.07))
    data["entry_candidate"] = data["after_base_filters"] & ~data["blocked_by_market_regime"] & ~data["blocked_by_downtrend"] & (data["pullback_63"] <= pullback_threshold)
    data["diagnostic_score"] = add_evolved_score(data)["evolved_score"]
    return data


def classify_miss_reason(code: str, v6_buy_codes: set[str], score_rows: pd.DataFrame) -> str:
    if code in v6_buy_codes:
        return "v6_bought"
    if score_rows.empty:
        return "no_2018_signal_rows"
    rows = score_rows[score_rows["ts_code"] == code]
    if rows.empty:
        return "not_in_2018_panel"
    def flag_any(column: str) -> bool:
        if column not in rows.columns:
            return False
        return bool(rows[column].fillna(False).any())

    if not flag_any("raw_candidate"):
        return "not_eligible_or_universe_filter"
    if not flag_any("after_base_filters"):
        return "failed_base_candidate_filters"
    if flag_any("blocked_by_market_regime"):
        return "blocked_by_market_regime"
    if flag_any("blocked_by_downtrend"):
        return "blocked_by_downtrend_filter"
    if not flag_any("entry_candidate"):
        return "failed_pullback_or_rank_entry"
    return "candidate_not_bought_capacity_or_timing"


def add_evolved_score(rows: pd.DataFrame) -> pd.DataFrame:
    scored = rows.copy()
    for col in ["ret_63", "ret_126", "above_ratio_63", "above_ratio_126", "volatility_63", "pullback_63", "avg_distance_63", "amount_ma20"]:
        if col not in scored:
            scored[col] = np.nan
    scored["evolved_score"] = (
        0.24 * zscore(scored["ret_126"])
        + 0.22 * zscore(scored["above_ratio_126"])
        + 0.18 * zscore(scored["ret_63"])
        + 0.14 * zscore(scored["above_ratio_63"])
        - 0.14 * zscore(scored["volatility_63"])
        - 0.05 * zscore(scored["avg_distance_63"].abs())
        + 0.03 * zscore(np.log(pd.to_numeric(scored["amount_ma20"], errors="coerce").clip(lower=1.0)))
    )
    return scored


def add_uptrend_features(panel: pd.DataFrame) -> pd.DataFrame:
    data = panel.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data = data.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    grouped = data.groupby("ts_code", sort=False)["close_qfq"]
    data["ma20_qfq"] = grouped.transform(lambda s: s.rolling(20, min_periods=20).mean())
    data["ma60_qfq"] = grouped.transform(lambda s: s.rolling(60, min_periods=60).mean())
    data["ma120_qfq"] = grouped.transform(lambda s: s.rolling(120, min_periods=120).mean())
    data["ma20_slope_10"] = data.groupby("ts_code", sort=False)["ma20_qfq"].pct_change(10, fill_method=None)
    data["ma60_slope_20"] = data.groupby("ts_code", sort=False)["ma60_qfq"].pct_change(20, fill_method=None)
    high_120 = grouped.transform(lambda s: s.rolling(120, min_periods=60).max())
    low_60 = grouped.transform(lambda s: s.rolling(60, min_periods=30).min())
    data["trend_drawdown_120"] = data["close_qfq"] / high_120 - 1.0
    data["trend_range_pos_60"] = np.where(
        high_120 > low_60,
        (data["close_qfq"] - low_60) / (high_120 - low_60),
        np.nan,
    )
    data["ma_uptrend"] = (
        (data["close_qfq"] > data["ma20_qfq"])
        & (data["ma20_qfq"] > data["ma60_qfq"])
        & (data["ma60_qfq"] > data["ma120_qfq"])
        & (data["ma20_slope_10"] > 0)
        & (data["ma60_slope_20"] > 0)
    )
    return data


def candidate_panel(panel: pd.DataFrame, market_index: pd.DataFrame | None, mode: str) -> pd.DataFrame:
    data = prepare_v6_diagnostic_scores(panel, market_index)
    data = add_evolved_score(data)
    base = data["after_base_filters"] & (data["recent_limit_down_20"] == 0)
    if mode == "v6_like":
        data["candidate"] = data["entry_candidate"]
    elif mode == "no_market_hard_block":
        pullback_ok = data["pullback_63"] <= np.where(data["strong_trend"], -0.026, -0.07)
        data["candidate"] = base & ~data["blocked_by_downtrend"] & pullback_ok
    elif mode == "bear_defensive_allow":
        bear = data["market_regime"].eq("bear")
        defensive = (
            (data["ret_126"] > 0)
            & (data["ret_63"] > -0.05)
            & (data["above_ratio_126"] >= 0.55)
            & (data["volatility_63"] <= data.groupby("trade_date")["volatility_63"].transform("median"))
            & (data["hot_money_risk_hits"].fillna(99) < 2)
            & (data["pullback_63"] <= -0.02)
        )
        normal = data["entry_candidate"]
        data["candidate"] = normal | (bear & base & defensive)
    else:
        raise ValueError(f"Unknown mode: {mode}")
    return data


def calc_commission(amount: float, is_buy: bool) -> float:
    return max(abs(amount) * (COMMISSION_BUY if is_buy else COMMISSION_SELL), MIN_COMMISSION)


def run_simple_backtest(signal_panel: pd.DataFrame, start="2018-01-01", end="2018-12-31", max_holdings=5, rebalance: str = "D") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    panel = signal_panel.copy()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[(panel["trade_date"] >= pd.Timestamp(start)) & (panel["trade_date"] <= pd.Timestamp(end))]
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    dates = sorted(panel["trade_date"].unique())
    by_date = {d: g.set_index("ts_code", drop=False) for d, g in panel.groupby("trade_date", sort=True)}
    cash = INIT_CASH
    holdings: dict[str, dict] = {}
    nav_rows = []
    trades = []
    target_amount = INIT_CASH / max_holdings

    for i, date in enumerate(dates):
        day = by_date[date]
        do_rebalance = True
        if rebalance == "M" and i > 0:
            do_rebalance = pd.Timestamp(date).month != pd.Timestamp(dates[i - 1]).month
        if i > 0 and do_rebalance:
            signal_date = dates[i - 1]
            signal = by_date[signal_date]
            ranked = signal[signal["candidate"].fillna(False)].sort_values(
                ["evolved_score", "ret_126", "amount_ma20"],
                ascending=[False, False, False],
            )
            target_codes = set(ranked["ts_code"].head(max_holdings))
            for code in list(holdings):
                if code not in target_codes and code in day.index:
                    row = day.loc[code]
                    price = float(row["open"]) if float(row.get("open", np.nan)) > 0 else np.nan
                    if np.isfinite(price):
                        shares = holdings[code]["shares"]
                        amount = price * shares
                        comm = calc_commission(amount, is_buy=False)
                        cash += amount - comm
                        trades.append({"date": str(date)[:10], "ts_code": code, "name": holdings[code]["name"], "action": "sell", "price": price, "shares": shares, "reason": "rebalance"})
                        del holdings[code]
            for _, row in ranked.iterrows():
                code = row["ts_code"]
                if len(holdings) >= max_holdings:
                    break
                if code in holdings or code not in day.index:
                    continue
                trade_row = day.loc[code]
                if bool(trade_row.get("is_suspended", False)):
                    continue
                price = float(trade_row["open"]) if float(trade_row.get("open", np.nan)) > 0 else np.nan
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
                holdings[code] = {"name": trade_row.get("name", code), "shares": shares, "last_price": price}
                trades.append({"date": str(date)[:10], "ts_code": code, "name": trade_row.get("name", code), "action": "buy", "price": price, "shares": shares, "reason": "candidate"})
        value = cash
        for code, pos in holdings.items():
            if code in day.index and float(day.loc[code].get("close", np.nan)) > 0:
                pos["last_price"] = float(day.loc[code]["close"])
            value += pos["last_price"] * pos["shares"]
        nav_rows.append({"date": str(date)[:10], "nav": value, "cash": cash, "holdings": len(holdings)})

    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    stats = summarize_nav(nav, trades_df)
    return nav, trades_df, stats


def candidate_panel_monthly_defensive(panel: pd.DataFrame, market_index: pd.DataFrame | None) -> pd.DataFrame:
    data = candidate_panel(panel, market_index, "bear_defensive_allow")
    defensive = (
        data["candidate"].fillna(False)
        & (data["evolved_score"] >= data.groupby("trade_date")["evolved_score"].transform(lambda s: s.quantile(0.90)))
        & (data["volatility_63"] <= data.groupby("trade_date")["volatility_63"].transform(lambda s: s.quantile(0.45)))
        & (data["ret_126"] > 0)
        & (data["above_ratio_126"] >= 0.60)
    )
    data["candidate"] = defensive
    return data


def candidate_panel_uptrend_only(panel: pd.DataFrame, market_index: pd.DataFrame | None, pullback_required: bool = False) -> pd.DataFrame:
    data = prepare_v6_diagnostic_scores(panel, market_index)
    data = add_uptrend_features(data)
    data = add_evolved_score(data)
    hot_money_ok = data["hot_money_risk_hits"].fillna(99) < 2
    base = (
        data["is_eligible"].fillna(False)
        & hot_money_ok
        & (data["recent_limit_down_20"] == 0)
        & data["ma_uptrend"].fillna(False)
        & (data["ret_63"] > 0)
        & (data["ret_126"] > 0)
        & (data["above_ratio_63"] >= 0.60)
        & (data["above_ratio_126"] >= 0.55)
        & (data["volatility_63"].notna())
    )
    not_overextended = (data["trend_drawdown_120"] <= -0.015) | (data["high_pos_21"] <= 0.985)
    if pullback_required:
        entry = base & (data["pullback_63"] <= -0.025) & (data["pullback_63"] >= -0.16)
    else:
        entry = base & not_overextended
    data["candidate"] = entry
    data["evolved_score"] = (
        data["evolved_score"]
        + 0.20 * zscore(data["ma20_slope_10"])
        + 0.15 * zscore(data["ma60_slope_20"])
        - 0.10 * zscore(data["trend_drawdown_120"].abs())
    )
    return data


def summarize_nav(nav: pd.DataFrame, trades: pd.DataFrame | None = None) -> dict:
    if nav.empty:
        return {}
    values = pd.to_numeric(nav["nav"], errors="coerce")
    total_ret = values.iloc[-1] / values.iloc[0] - 1.0
    dd = values / values.cummax() - 1.0
    days = max((pd.Timestamp(nav["date"].iloc[-1]) - pd.Timestamp(nav["date"].iloc[0])).days, 1)
    annual = (1.0 + total_ret) ** (365.0 / days) - 1.0 if total_ret > -1 else -1.0
    buy_count = 0
    if trades is not None and not trades.empty and "action" in trades.columns:
        buy_count = int(trades["action"].eq("buy").sum())
    return {
        "start_date": str(nav["date"].iloc[0]),
        "end_date": str(nav["date"].iloc[-1]),
        "final_nav": float(values.iloc[-1]),
        "total_return_pct": round(total_ret * 100, 4),
        "annual_return_pct": round(annual * 100, 4),
        "max_drawdown_pct": round(float(dd.min()) * 100, 4),
        "trade_records": 0 if trades is None else int(len(trades)),
        "buy_trades": buy_count,
    }


def period_return_table(nav_by_variant: dict[str, pd.DataFrame], freq: str = "Y") -> pd.DataFrame:
    rows = []
    for variant, nav in nav_by_variant.items():
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
            raise ValueError(f"Unsupported freq: {freq}")
        previous_end = None
        for period, group in data.groupby("period", sort=True):
            first = float(previous_end) if previous_end is not None else float(group["nav"].iloc[0])
            last = float(group["nav"].iloc[-1])
            previous_end = last
            if first <= 0:
                continue
            rows.append({"period": period, "variant": variant, "return_pct": round((last / first - 1.0) * 100.0, 2)})
    if not rows:
        return pd.DataFrame(columns=["period"])
    table = pd.DataFrame(rows).pivot(index="period", columns="variant", values="return_pct").reset_index()
    table.columns.name = None
    preferred = ["period", "v4", "v5", "v6", "v6_like_simple", "uptrend_only", "uptrend_pullback"]
    ordered = [col for col in preferred if col in table.columns]
    ordered.extend([col for col in table.columns if col not in ordered])
    table = table[ordered]
    return table


def slice_nav_2018(nav: pd.DataFrame) -> pd.DataFrame:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    return data[(data["date"] >= YEAR_START) & (data["date"] <= YEAR_END)].copy()


def bought_codes_2018(trades: pd.DataFrame) -> set[str]:
    if trades is None or trades.empty or "action" not in trades.columns:
        return set()
    data = trades.copy()
    data["date"] = pd.to_datetime(data["date"])
    return set(data[(data["date"].between(YEAR_START, YEAR_END)) & (data["action"].eq("buy"))]["ts_code"].astype(str))


def write_design_and_plan():
    DESIGN_PATH.write_text(
        """# 2018 v6 Top20 漏买诊断与熊市条件放行设计

## 设计结论
量化策略专家审阅认为，v6 漏买 2018 强票的最高概率原因是 bear regime 硬阻断，其次是 early_weakness_downtrend 误杀熊市中的早期强股。代码审阅专家要求把诊断和策略严格分层：Top20 只能用于事后解释，不能进入新策略规则。

## 本轮最小方案
1. 用 v6 panel 重建 2018 非游资非新股收益 Top20。
2. 对 Top20 做逐日归因，识别是否被市场 regime、downtrend、基础候选、pullback/排名等拦截。
3. 实验两个候选：关闭市场硬阻断的诊断版本、bear defensive allow 的条件放行版本。
4. 新策略只使用 signal date 已经在 panel 中存在的历史技术/流动性字段，不使用 Top20 标签，不使用未 shift 的 moneyflow/cyq/fina 数据。

## Web 证据摘要
Tavily 搜索得到的公开资料一致指向：熊市/不确定环境中，quality/profitability、low volatility/defensive、momentum 的组合更适合防守和捕捉相对强势；但防御因子可能在牛市跑输，所以本轮只在 bear regime 中条件放行，不替换全局逻辑。
""",
        encoding="utf-8",
    )
    PLAN_PATH.write_text(
        """# 2018 v6 Top20 Evolution Implementation Plan

**Goal:** 解释 v6 为什么错过 2018 非游资非新股 Top20，并验证一个熊市条件放行实验是否改善收益。

**Architecture:** 单个临时模块提供可测试函数，主流程读取现有 v4/v5/v6 输出，生成诊断、回测、对比和 HTML 报告。

**Tasks:**
- 写标准库 unittest 测试：Top20 过滤、漏买原因分类、防御动量打分。
- 实现 `v6_top20_evolution.py`。
- 运行测试。
- 运行实验，生成 CSV/JSON/HTML。
- 打开 HTML。

**No-git:** 不执行 git 命令，不改正式 v4/v5/v6 文件。
""",
        encoding="utf-8",
    )


def render_report(top20, miss, compare, yearly_returns, monthly_returns, expert_notes, sources):
    def table(df: pd.DataFrame, cols: list[str]) -> str:
        if df is None or df.empty:
            return "<p>无数据</p>"
        head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
        body = []
        for _, row in df[cols].iterrows():
            cells = ""
            for c in cols:
                value = row[c]
                text = "" if pd.isna(value) else str(value)
                cells += f"<td>{html.escape(text)}</td>"
            body.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"

    def table_auto(df: pd.DataFrame) -> str:
        if df is None or df.empty:
            return "<p>无数据</p>"
        cols = list(df.columns)
        return table(df, cols)

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>2018 v6 Top20 漏买诊断与策略进化</title>
<style>
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 0; background: #f5f7fa; color: #172033; }}
main {{ max-width: 1480px; margin: 0 auto; padding: 28px; }}
h1 {{ margin: 0 0 8px; font-size: 26px; }}
h2 {{ margin-top: 28px; font-size: 20px; }}
.note, .card {{ background: #fff; border: 1px solid #d9dee7; border-radius: 6px; padding: 14px; margin: 12px 0; }}
.grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
.metric {{ background: #fff; border: 1px solid #d9dee7; border-radius: 6px; padding: 14px; }}
.metric span {{ display: block; color: #5f6b7a; font-size: 12px; }}
.metric strong {{ font-size: 22px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 13px; }}
th, td {{ border: 1px solid #d9dee7; padding: 7px 8px; text-align: right; white-space: nowrap; }}
th {{ background: #26364d; color: #fff; position: sticky; top: 0; }}
td:nth-child(2), td:nth-child(3), th:nth-child(2), th:nth-child(3) {{ text-align: left; }}
.scroll {{ overflow: auto; max-height: 520px; border-radius: 6px; }}
.warn {{ color: #9a3412; font-weight: 700; }}
.good {{ color: #166534; font-weight: 700; }}
</style>
</head>
<body><main>
<h1>2018 v6 Top20 漏买诊断与策略进化</h1>
<div class="note">目标是提升收益，但本报告把“诊断标签”和“策略信号”分开：Top20 只用于解释 v6 漏买，不参与新策略选股。</div>

<h2>基准与实验对比</h2>
<div class="scroll">{table(compare, ["variant", "period", "total_return_pct", "annual_return_pct", "max_drawdown_pct", "trade_records", "buy_trades", "top20_bought_count"])}</div>

<h2>按年收益对比</h2>
<div class="note">单位：%。正式 v4/v5/v6 使用各自 output/nav_series；latest 使用本轮上涨趋势实验的 simple 临时引擎结果，因此只覆盖 2018。</div>
<div class="scroll">{table_auto(yearly_returns)}</div>

<h2>2018 月度收益对比</h2>
<div class="note">单位：%。这张表用于看 2018 熊市中每个月的损益来源。</div>
<div class="scroll">{table_auto(monthly_returns)}</div>

<h2>2018 Top20 与 v6 漏买原因</h2>
<div class="scroll">{table(miss, ["rank", "ts_code", "name", "annual_return_pct", "v6_reason", "best_seen_regime", "max_diagnostic_score"])}</div>

<h2>Top20 原始收益排行</h2>
<div class="scroll">{table(top20, ["rank", "ts_code", "name", "annual_return_pct", "start_date", "end_date", "max_hot_money_hits"])}</div>

<h2>专家设计 Review</h2>
<div class="card"><pre>{html.escape(expert_notes)}</pre></div>

<h2>证据与可用数据</h2>
<div class="card"><pre>{html.escape(sources)}</pre></div>

<h2>建议</h2>
<div class="note">
<p class="warn">不建议合并当前任何放行实验。</p>
<p>实测显示，关闭熊市硬阻断和 bear defensive allowlist 都能提高 Top20 捕获数，但在临时 simple 引擎下收益与最大回撤显著变差；月频防御版也未优于正式 v6。注意：simple 引擎和正式 v6 交易执行口径不同，因此这些候选结果只能作为研究证据，不能直接作为正式策略合并依据。</p>
<p>当前最可靠的结论是：v6 漏买 Top20 的主因确实是 bear regime 防守，但“买到更多 Top20”不等于组合赚钱。下一步应进入 v7 研究，而不是合并：用正式 v6 引擎做同口径开关实验，接入按公告日生效的质量/盈利因子、相对指数强度、下行波动和行业分散约束，并做 2017、2019、2020、2021 分年度验证。</p>
</div>
</main></body></html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def run_experiment():
    ensure_run_dir()
    README_PATH.write_text("# 2018 v6 Top20 Evolution Progress\n\n", encoding="utf-8")
    append_progress("开始：读取 v4/v5/v6 输出并建立诊断实验。")
    write_design_and_plan()

    variants = {name: load_variant(name) for name in ["v4", "v5", "v6"]}
    top20 = rank_top_returns(variants["v6"]["panel"], top_n=20)
    top20.to_csv(RUN_DIR / "top20_2018.csv", index=False, encoding="utf-8-sig")
    append_progress("完成 Top20 诊断集构建。")

    v6_trades = variants["v6"].get("trade_records", pd.DataFrame())
    v6_bought = bought_codes_2018(v6_trades)
    diag = prepare_v6_diagnostic_scores(variants["v6"]["panel"], variants["v6"].get("market_index"))
    miss_rows = []
    for _, row in top20.iterrows():
        code_rows = diag[diag["ts_code"] == row["ts_code"]]
        reason = classify_miss_reason(row["ts_code"], v6_bought, code_rows)
        miss_rows.append(
            {
                "rank": int(row["rank"]),
                "ts_code": row["ts_code"],
                "name": row["name"],
                "annual_return_pct": round(float(row["annual_return_pct"]), 2),
                "v6_reason": reason,
                "best_seen_regime": "" if code_rows.empty else str(code_rows["market_regime"].mode().iloc[0]),
                "max_diagnostic_score": "" if code_rows.empty else round(float(code_rows["diagnostic_score"].max()), 4),
            }
        )
    miss = pd.DataFrame(miss_rows)
    miss.to_csv(RUN_DIR / "v6_top20_miss_reasons.csv", index=False, encoding="utf-8-sig")
    append_progress("完成 v6 漏买归因。")

    compare_rows = []
    top20_codes = set(top20["ts_code"])
    for name in ["v4", "v5", "v6"]:
        nav = variants[name].get("nav_series", pd.DataFrame())
        trades = variants[name].get("trade_records", pd.DataFrame())
        nav2018 = slice_nav_2018(nav)
        trades2018 = trades.copy()
        if not trades2018.empty and "date" in trades2018.columns:
            trades2018["date"] = pd.to_datetime(trades2018["date"])
            trades2018 = trades2018[trades2018["date"].between(YEAR_START, YEAR_END)]
        stats2018 = summarize_nav(nav2018, trades2018)
        compare_rows.append(
            {
                "variant": name,
                "period": "2018",
                **stats2018,
                "top20_bought_count": len(top20_codes & bought_codes_2018(trades)),
            }
        )
        summary = variants[name].get("summary", {})
        compare_rows.append(
            {
                "variant": name,
                "period": "full_output",
                "total_return_pct": summary.get("total_return_pct", ""),
                "annual_return_pct": summary.get("annual_return_pct", ""),
                "max_drawdown_pct": summary.get("max_drawdown_pct", ""),
                "trade_records": summary.get("trade_records", ""),
                "top20_bought_count": len(top20_codes & bought_codes_2018(trades)),
                "start_date": summary.get("start_date", ""),
                "end_date": summary.get("end_date", ""),
                "final_nav": summary.get("final_nav", ""),
            }
        )

    signal = candidate_panel(variants["v6"]["panel"], variants["v6"].get("market_index"), "v6_like")
    nav, trades, stats = run_simple_backtest(signal, start="2018-01-01", end="2018-12-31")
    nav.to_csv(RUN_DIR / "v6_like_simple_nav.csv", index=False)
    trades.to_csv(RUN_DIR / "v6_like_simple_trades.csv", index=False, encoding="utf-8-sig")
    compare_rows.append(
        {
            "variant": "v6_like_simple",
            "period": "2018_simple_tmp",
            **stats,
            "top20_bought_count": len(top20_codes & bought_codes_2018(trades)),
        }
    )

    for mode in ["no_market_hard_block", "bear_defensive_allow"]:
        signal = candidate_panel(variants["v6"]["panel"], variants["v6"].get("market_index"), mode)
        nav, trades, stats = run_simple_backtest(signal, start="2018-01-01", end="2018-12-31")
        nav.to_csv(RUN_DIR / f"{mode}_nav.csv", index=False)
        trades.to_csv(RUN_DIR / f"{mode}_trades.csv", index=False, encoding="utf-8-sig")
        compare_rows.append(
            {
                "variant": mode,
                "period": "2018_simple_tmp",
                **stats,
                "top20_bought_count": len(top20_codes & bought_codes_2018(trades)),
            }
        )
    signal = candidate_panel_monthly_defensive(variants["v6"]["panel"], variants["v6"].get("market_index"))
    nav, trades, stats = run_simple_backtest(signal, start="2018-01-01", end="2018-12-31", max_holdings=3, rebalance="M")
    nav.to_csv(RUN_DIR / "bear_monthly_defensive_nav.csv", index=False)
    trades.to_csv(RUN_DIR / "bear_monthly_defensive_trades.csv", index=False, encoding="utf-8-sig")
    compare_rows.append(
        {
            "variant": "bear_monthly_defensive",
            "period": "2018_simple_tmp",
            **stats,
            "top20_bought_count": len(top20_codes & bought_codes_2018(trades)),
        }
    )
    for variant_name, pullback_required in [("uptrend_only", False), ("uptrend_pullback", True)]:
        signal = candidate_panel_uptrend_only(
            variants["v6"]["panel"],
            variants["v6"].get("market_index"),
            pullback_required=pullback_required,
        )
        nav, trades, stats = run_simple_backtest(signal, start="2018-01-01", end="2018-12-31", max_holdings=5, rebalance="M")
        nav.to_csv(RUN_DIR / f"{variant_name}_nav.csv", index=False)
        trades.to_csv(RUN_DIR / f"{variant_name}_trades.csv", index=False, encoding="utf-8-sig")
        compare_rows.append(
            {
                "variant": variant_name,
                "period": "2018_simple_tmp",
                **stats,
                "top20_bought_count": len(top20_codes & bought_codes_2018(trades)),
            }
        )
    compare = pd.DataFrame(compare_rows)
    compare.to_csv(RUN_DIR / "comparison.csv", index=False, encoding="utf-8-sig")
    nav_by_variant = {}
    for name in ["v4", "v5", "v6"]:
        nav_by_variant[name] = variants[name].get("nav_series", pd.DataFrame())
    for name in ["v6_like_simple", "uptrend_only", "uptrend_pullback"]:
        path = RUN_DIR / f"{name}_nav.csv"
        if path.exists():
            nav_by_variant[name] = pd.read_csv(path)
    yearly_returns = period_return_table(nav_by_variant, freq="Y")
    monthly_returns = period_return_table(
        {
            name: slice_nav_2018(nav)
            for name, nav in nav_by_variant.items()
            if nav is not None and not nav.empty
        },
        freq="M",
    )
    yearly_returns.to_csv(RUN_DIR / "yearly_returns.csv", index=False, encoding="utf-8-sig")
    monthly_returns.to_csv(RUN_DIR / "monthly_returns_2018.csv", index=False, encoding="utf-8-sig")
    append_progress("完成 v4/v5/v6 与两个候选实验对比。")

    expert_notes = (
        "量化策略专家：最高概率漏买原因是 market regime 硬阻断，其次是 downtrend 过滤；"
        "建议 bear regime 条件放行，不建议关闭熊市过滤。\n"
        "代码审阅专家：诊断和策略必须分层；Top20 标签不能进入候选规则；所有交易使用前一交易日信号。"
    )
    sources = (
        "Tavily: factor investing references point to quality/profitability, low volatility/defensive, and momentum in bear/uncertain markets. "
        "Tavily: uptrend definitions consistently describe higher highs and higher lows; moving-average trend following commonly uses price above rising short/medium averages and pullbacks toward support. "
        "Tushare docs: 可后续接入 daily_basic、fina_indicator、income/cashflow/balancesheet、cyq_perf/cyq_chips、moneyflow、hsgt_top10，但盘后数据必须 shift，财务数据必须按公告日生效。"
    )
    render_report(top20, miss, compare, yearly_returns, monthly_returns, expert_notes, sources)
    append_progress(f"完成 HTML 报告：{REPORT_PATH}")
    return REPORT_PATH


if __name__ == "__main__":
    print(run_experiment())

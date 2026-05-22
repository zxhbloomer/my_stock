from __future__ import annotations

import html
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
V7_DIR = BACKTRADER_DIR / "v7"

OUTPUT_DIR = TMP_DIR / "tmp_v7_value_quality_lowturnover_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_value_quality_lowturnover_README.md"

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"
START_DATE = "2018-01-01"
END_DATE = None

CASES = [
    {
        "case": "vq40_daily_stop10",
        "rebalance": "D",
        "v7_weight": 0.60,
        "value_weight": 0.40,
        "stop_loss": -0.10,
        "add_thresholds": (0.08, 0.16, 0.24),
    },
    {
        "case": "vq60_daily_stop12",
        "rebalance": "D",
        "v7_weight": 0.40,
        "value_weight": 0.60,
        "stop_loss": -0.12,
        "add_thresholds": (0.10, 0.20, 0.30),
    },
    {
        "case": "vq40_monthly_stop10",
        "rebalance": "M",
        "v7_weight": 0.60,
        "value_weight": 0.40,
        "stop_loss": -0.10,
        "add_thresholds": (0.08, 0.16, 0.24),
    },
    {
        "case": "vq60_monthly_stop12",
        "rebalance": "M",
        "v7_weight": 0.40,
        "value_weight": 0.60,
        "stop_loss": -0.12,
        "add_thresholds": (0.10, 0.20, 0.30),
    },
    {
        "case": "vq60_quarterly_stop12",
        "rebalance": "Q",
        "v7_weight": 0.40,
        "value_weight": 0.60,
        "stop_loss": -0.12,
        "add_thresholds": (0.10, 0.20, 0.30),
    },
]


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (values - values.mean()) / std


def lower_is_better_score(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    values = values.where(values > 0)
    return -zscore(values.clip(values.quantile(0.02), values.quantile(0.98)))


def higher_is_better_score(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return zscore(values.clip(values.quantile(0.02), values.quantile(0.98)))


def write_readme_header() -> None:
    README_PATH.write_text(
        """# tmp_v7 价值质量低换手实验

目标：在不修改正式 v7 的前提下，验证“PB/PE 估值 + ROE/ROA/现金流质量 + 股息率 + 低换手调仓”是否能保留收益、降低交易频率和改善弱市年份。

设计 review：
- 量化研究员：PB+ROE 是公开研究中常见的价值质量框架，但低 PB 单因子可能是价值陷阱，必须叠加盈利质量、现金流、负债和趋势确认。
- 数据工程师：`027_daily_basic` 可提供 PB/PE/股息率，`042_fina_indicator` 可提供 ROE/ROA/经营现金流/负债率；财务指标必须按 `ann_date + 1 day` 后才允许使用。
- 风控专家：不把 v7 直接改成价值策略，先做 tmp 独立实验；低换手通过月末/季末信号日买入、放宽止损和提高加仓门槛实现。
- 开发 review：单日月末/季末窗口过严，第一轮全周期 0 交易；改为月末最后 5 个信号日、季末最后 8 个信号日，保留低换手但避免完全错过入场。
- 开发 review 2：月末/季末窗口仍 0 交易，补充日频入场版本，用来区分“价值因子无效”和“低换手窗口过窄”。

Tavily 复核：
- PB-ROE 策略研究支持低 PB 与高 ROE 组合，但提示行业/风格切换和价值陷阱风险。
- 红利、低估值、低波动、质量组合常用于稳健/长期配置。

进度：
""",
        encoding="utf-8",
    )


def load_v7_config():
    sys.path.insert(0, str(V7_DIR))
    try:
        spec = importlib.util.spec_from_file_location("v7_config_for_vq", V7_DIR / "config.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        try:
            sys.path.remove(str(V7_DIR))
        except ValueError:
            pass


def load_v7_backtest_module(module_name: str, case: dict):
    sys.path.insert(0, str(V7_DIR))
    old_config = sys.modules.get("config")
    config_spec = importlib.util.spec_from_file_location("config", V7_DIR / "config.py")
    config_mod = importlib.util.module_from_spec(config_spec)
    assert config_spec.loader is not None
    config_spec.loader.exec_module(config_mod)
    sys.modules["config"] = config_mod
    try:
        source = (V7_DIR / "20_run_backtest.py").read_text(encoding="utf-8")
        source = replace_once(
            source,
            "    market_regime = build_market_regime(market, panel)\n",
            "    market_regime = build_market_regime(market, panel)\n"
            "    panel = __value_apply_rebalance_calendar(panel, VALUE_REBALANCE)\n",
        )
        source = replace_once(
            source,
            '    panel = panel[panel["trade_date"] >= pd.Timestamp(start_date)].copy()\n'
            '    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)\n',
            '    panel = panel[panel["trade_date"] >= pd.Timestamp(start_date)]\n',
        )
        source = replace_once(
            source,
            "def build_panel_by_date(panel):\n"
            "    return {\n"
            "        date: group_index.to_numpy()\n"
            "        for date, group_index in panel.groupby(\"trade_date\", sort=True).groups.items()\n"
            "    }\n",
            "def build_panel_by_date(panel):\n"
            "    positions = pd.Series(np.arange(len(panel)), index=panel.index)\n"
            "    return {\n"
            "        date: positions.loc[group_index].to_numpy()\n"
            "        for date, group_index in panel.groupby(\"trade_date\", sort=True).groups.items()\n"
            "    }\n",
        )
        source = replace_once(
            source,
            '        "weak_lowvol_mom_candidate_blocks": 0,\n',
            '        "weak_lowvol_mom_candidate_blocks": 0,\n'
            '        "value_quality_case": VALUE_CASE,\n'
            '        "value_quality_rebalance": VALUE_REBALANCE,\n'
            '        "value_quality_candidate_days": 0,\n'
            '        "value_quality_candidate_blocks": 0,\n',
        )
        source = replace_once(
            source,
            '                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)\n'
            '                candidates = apply_weak_lowvol_mom_filter(\n',
            '                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)\n'
            '                candidates = __value_attach_features(candidates, signal_date, VALUE_FEATURES)\n'
            '                candidates = __value_apply_score(candidates, VALUE_CASE, VALUE_V7_WEIGHT, VALUE_QUALITY_WEIGHT, stats).reset_index(drop=True)\n'
            '                candidates = apply_weak_lowvol_mom_filter(\n',
        )
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(module_name, loader=None))
        module.__file__ = str(V7_DIR / "20_run_backtest.py")
        module.VALUE_CASE = case["case"]
        module.VALUE_REBALANCE = case["rebalance"]
        module.VALUE_V7_WEIGHT = case["v7_weight"]
        module.VALUE_QUALITY_WEIGHT = case["value_weight"]
        module.VALUE_FEATURES = case.get("features", pd.DataFrame())
        module.__value_apply_rebalance_calendar = apply_rebalance_calendar
        module.__value_attach_features = attach_value_features
        module.__value_apply_score = apply_value_quality_score
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.LONG_STOP_LOSS_PCT = case["stop_loss"]
        module.LONG_ADD_PROFIT_THRESHOLDS = case["add_thresholds"]
        return module
    finally:
        if old_config is not None:
            sys.modules["config"] = old_config
        else:
            sys.modules.pop("config", None)
        try:
            sys.path.remove(str(V7_DIR))
        except ValueError:
            pass


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"Patch anchor not found:\n{old}")
    return source.replace(old, new, 1)


def allowed_signal_dates(trade_dates: pd.Series, freq: str) -> set[pd.Timestamp]:
    dates = pd.Series(pd.to_datetime(trade_dates).drop_duplicates()).sort_values()
    if freq == "M":
        allowed = dates.groupby(dates.dt.to_period("M")).tail(5)
    elif freq == "Q":
        allowed = dates.groupby(dates.dt.to_period("Q")).tail(8)
    else:
        allowed = dates
    return set(pd.to_datetime(allowed).dt.normalize())


def apply_rebalance_calendar(panel: pd.DataFrame, freq: str) -> pd.DataFrame:
    if freq not in {"M", "Q"}:
        return panel
    out = panel
    allowed = allowed_signal_dates(out["trade_date"], freq)
    signal_allowed = pd.to_datetime(out["trade_date"]).dt.normalize().isin(allowed)
    out.loc[~signal_allowed, "is_eligible"] = False
    return out


def apply_value_quality_score(
    candidates: pd.DataFrame,
    case_name: str,
    v7_weight: float,
    value_weight: float,
    diagnostics: dict | None = None,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    data = candidates.copy()
    required = ["pb", "pe_ttm", "dv_ttm", "roe", "roa", "ocf_to_or", "debt_to_assets"]
    for col in required:
        if col not in data.columns:
            data[col] = np.nan

    valid = (
        pd.to_numeric(data["pb"], errors="coerce").between(0.1, 20.0)
        & pd.to_numeric(data["pe_ttm"], errors="coerce").between(0.0, 100.0)
        & pd.to_numeric(data["roe"], errors="coerce").gt(0.0)
        & pd.to_numeric(data["debt_to_assets"], errors="coerce").lt(95.0)
    )
    if diagnostics is not None:
        diagnostics["value_quality_candidate_days"] = diagnostics.get("value_quality_candidate_days", 0) + 1
        diagnostics["value_quality_candidate_blocks"] = (
            diagnostics.get("value_quality_candidate_blocks", 0) + int(len(data) - int(valid.sum()))
        )
    data = data[valid].copy()
    if data.empty:
        return data

    data["v7_raw_score"] = pd.to_numeric(data["score"], errors="coerce").fillna(0.0)
    data["value_quality_score"] = (
        0.18 * lower_is_better_score(data["pb"])
        + 0.10 * lower_is_better_score(data["pe_ttm"])
        + 0.14 * higher_is_better_score(data["dv_ttm"].fillna(0.0))
        + 0.24 * higher_is_better_score(data["roe"])
        + 0.10 * higher_is_better_score(data["roa"])
        + 0.12 * higher_is_better_score(data["ocf_to_or"])
        + 0.06 * higher_is_better_score(data.get("grossprofit_margin", pd.Series(0.0, index=data.index)))
        - 0.06 * higher_is_better_score(data["debt_to_assets"])
    )
    data["score"] = v7_weight * zscore(data["v7_raw_score"]) + value_weight * data["value_quality_score"]
    return data.sort_values(
        ["score", "value_quality_score", "v7_raw_score"],
        ascending=[False, False, False],
    )


def attach_value_features(candidates: pd.DataFrame, signal_date, features: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty or features is None or features.empty:
        return candidates
    signal_ts = pd.Timestamp(signal_date)
    daily_features = features[features["trade_date"].eq(signal_ts)]
    if daily_features.empty:
        return candidates
    return candidates.merge(daily_features.drop(columns=["trade_date"]), on="ts_code", how="left")


def sql_date_list(dates: list[pd.Timestamp]) -> str:
    return ",".join(f"'{d.date().isoformat()}'" for d in dates)


def fetch_financial_signal_features(signal_dates: list[pd.Timestamp], start_date: str, end_date: str | None) -> pd.DataFrame:
    if not signal_dates:
        return pd.DataFrame()
    date_sql = sql_date_list(signal_dates)
    end = end_date or pd.Timestamp.today().date().isoformat()
    engine = create_engine(DB_URL)
    daily_sql = f"""
        select ts_code, trade_date, pe_ttm, pb, dv_ttm, total_mv, circ_mv
        from {SCHEMA}."027_daily_basic"
        where trade_date in ({date_sql})
    """
    fina_sql = f"""
        select ts_code, ann_date, end_date, roe, roa, grossprofit_margin,
               ocf_to_or, debt_to_assets
        from {SCHEMA}."042_fina_indicator"
        where ann_date >= :start_date and ann_date <= :end_date
    """
    append_progress("读取 daily_basic 信号日估值数据。")
    daily = pd.read_sql(text(daily_sql), engine)
    append_progress(f"daily_basic rows={len(daily):,}。")
    append_progress("读取 fina_indicator 财务指标数据。")
    fina = pd.read_sql(text(fina_sql), engine, params={"start_date": "2016-01-01", "end_date": end})
    append_progress(f"fina_indicator rows={len(fina):,}。")
    if daily.empty:
        return daily

    features = align_financial_features(daily, fina)
    for col in ["pe_ttm", "pb", "dv_ttm", "roe", "roa", "grossprofit_margin", "ocf_to_or", "debt_to_assets"]:
        features[col] = pd.to_numeric(features[col], errors="coerce")
    return features[
        [
            "ts_code",
            "trade_date",
            "pe_ttm",
            "pb",
            "dv_ttm",
            "total_mv",
            "circ_mv",
            "ann_date",
            "end_date",
            "roe",
            "roa",
            "grossprofit_margin",
            "ocf_to_or",
            "debt_to_assets",
        ]
    ]


def align_financial_features(daily: pd.DataFrame, fina: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    fina = fina.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    fina["ann_date"] = pd.to_datetime(fina["ann_date"])
    fina["available_date"] = fina["ann_date"] + pd.Timedelta(days=1)
    fina = fina.sort_values(["ts_code", "available_date", "end_date"])
    daily = daily.sort_values(["ts_code", "trade_date"])
    merged_parts = []
    for code, left in daily.groupby("ts_code", sort=False):
        right = fina[fina["ts_code"].eq(code)]
        if right.empty:
            merged_parts.append(left)
            continue
        merged = pd.merge_asof(
            left.sort_values("trade_date"),
            right.drop(columns=["ts_code"]).sort_values("available_date"),
            left_on="trade_date",
            right_on="available_date",
            direction="backward",
        )
        merged["ts_code"] = code
        merged_parts.append(merged)
    features = pd.concat(merged_parts, ignore_index=True)
    return features


def summarize_nav(name: str, nav: pd.DataFrame, trades: pd.DataFrame, stats: dict | None = None) -> dict:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
    start_nav = float(data.iloc[0]["nav"])
    end_nav = float(data.iloc[-1]["nav"])
    total_ret = end_nav / start_nav - 1.0
    days = max((data.iloc[-1]["date"] - data.iloc[0]["date"]).days, 1)
    annual_ret = (1.0 + total_ret) ** (365.0 / days) - 1.0
    curve = data["nav"] / start_nav
    max_dd = float((curve / curve.cummax() - 1.0).min())
    row = {
        "case": name,
        "final_nav": end_nav,
        "total_return_pct": total_ret * 100.0,
        "annual_return_pct": annual_ret * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "trade_records": int(len(trades)),
    }
    if stats:
        row.update(
            {
                "buy_fills": int(stats.get("buy_fills", 0)),
                "sell_fills": int(stats.get("sell_fills", 0)),
                "stop_loss_fills": int(stats.get("stop_loss_fills", 0)),
                "value_quality_candidate_days": int(stats.get("value_quality_candidate_days", 0)),
                "value_quality_candidate_blocks": int(stats.get("value_quality_candidate_blocks", 0)),
            }
        )
    return row


def load_existing_nav(version: str) -> pd.DataFrame | None:
    path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
    if not path.exists():
        return None
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    return nav[nav["date"] >= pd.Timestamp(START_DATE)].copy()


def load_existing_trades(version: str) -> pd.DataFrame:
    path = BACKTRADER_DIR / version / "output" / "trade_records.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def period_returns(nav: pd.DataFrame, freq: str) -> pd.Series:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
    data = data.sort_values("date").set_index("date")
    last = data["nav"].resample(freq).last().dropna()
    prev = pd.concat([pd.Series([data["nav"].iloc[0]], index=[last.index[0] - pd.offsets.Day(1)]), last])
    return prev.pct_change().iloc[1:] * 100.0


def make_return_table(nav_map: dict[str, pd.DataFrame], freq: str) -> pd.DataFrame:
    pieces = []
    for name, nav in nav_map.items():
        pieces.append(period_returns(nav, freq).rename(name))
    table = pd.concat(pieces, axis=1).round(2)
    table.index = table.index.strftime("%Y" if freq == "YE" else "%Y-%m")
    return table.reset_index(names="period")


def trade_duration_summary(trades: pd.DataFrame) -> dict:
    if trades.empty or "action" not in trades.columns:
        return {"closed_lots": 0, "median_hold_days": np.nan, "avg_hold_days": np.nan}
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    open_lots: dict[str, list[dict]] = {}
    lots = []
    for _, row in t.sort_values("date").iterrows():
        code = row["ts_code"]
        if row["action"] == "buy":
            open_lots.setdefault(code, []).append({"date": row["date"], "shares": float(row["shares"])})
        elif row["action"] == "sell":
            remaining = float(row["shares"])
            for lot in open_lots.get(code, []):
                if remaining <= 0:
                    break
                used = min(float(lot["shares"]), remaining)
                if used > 0:
                    lots.append((row["date"] - lot["date"]).days)
                    lot["shares"] -= used
                    remaining -= used
            open_lots[code] = [lot for lot in open_lots.get(code, []) if lot["shares"] > 0]
    if not lots:
        return {"closed_lots": 0, "median_hold_days": np.nan, "avg_hold_days": np.nan}
    s = pd.Series(lots)
    return {"closed_lots": int(len(s)), "median_hold_days": float(s.median()), "avg_hold_days": float(s.mean())}


def html_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    data = df if max_rows is None else df.head(max_rows)
    return data.to_html(index=False, escape=True, classes="data")


def generate_report(summary: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame, sources: list[str]) -> None:
    baseline = summary[summary["case"].eq("v7")]
    baseline_ret = float(baseline.iloc[0]["total_return_pct"]) if not baseline.empty else float("nan")
    exp = summary[summary["case"].str.startswith("vq")]
    best = exp.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).iloc[0] if not exp.empty else summary.iloc[0]
    advice = "暂不合并：实验没有超过 v7。"
    if best["total_return_pct"] > baseline_ret:
        if best["trade_records"] < float(baseline.iloc[0]["trade_records"]):
            advice = f"可进入下一轮验证：{best['case']} 收益高于 v7 且交易次数更低，但仍需逐笔审查和滑点压力测试。"
        else:
            advice = f"暂不直接合并：{best['case']} 收益高于 v7，但交易次数没有下降。"
    source_list = "".join(f"<li>{html.escape(src)}</li>" for src in sources)
    REPORT_PATH.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 价值质量低换手实验</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #222; }}
h1, h2 {{ margin-bottom: 8px; }}
.note {{ padding: 12px 14px; background: #f3f6fa; border-left: 4px solid #4b7bec; margin: 12px 0; }}
table.data {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 8px 0 22px; }}
table.data th, table.data td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
table.data th:first-child, table.data td:first-child {{ text-align: left; }}
table.data th {{ background: #f7f7f7; }}
</style>
</head>
<body>
<h1>v7 价值质量低换手实验</h1>
<div class="note"><b>建议：</b>{html.escape(advice)}</div>
<p>本实验不修改正式 v7，只在 tmp 中复用 v7 回测框架并加入财务因子与低换手调仓约束。财务指标按公告日后一日才可使用，估值指标只在信号日使用，交易仍发生在下一交易日开盘。</p>
<h2>全周期汇总</h2>
{html_table(summary.round(4))}
<h2>年度收益率 %</h2>
{html_table(yearly)}
<h2>月度收益率 %</h2>
{html_table(monthly, 120)}
<h2>研究依据</h2>
<ul>{source_list}</ul>
</body>
</html>
""",
        encoding="utf-8",
    )


def run_case(case: dict, panel: pd.DataFrame, market: pd.DataFrame, features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    case = dict(case)
    case["features"] = features
    module = load_v7_backtest_module(f"tmp_vq_{case['case']}", case)
    nav, trades, rebalance, scores, holdings, stats = module.run_backtest(
        panel.copy(deep=False),
        market.copy(deep=False),
        START_DATE,
        END_DATE,
    )
    nav.to_csv(OUTPUT_DIR / f"{case['case']}_nav_series.csv", index=False)
    trades.to_csv(OUTPUT_DIR / f"{case['case']}_trade_records.csv", index=False, encoding="utf-8-sig")
    rebalance.to_csv(OUTPUT_DIR / f"{case['case']}_rebalance_log.csv", index=False, encoding="utf-8-sig")
    stats.update(trade_duration_summary(trades))
    (OUTPUT_DIR / f"{case['case']}_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    append_progress(f"完成 {case['case']}：total_return={stats.get('total_return_pct'):.2f}%，trades={len(trades)}。")
    return nav, trades, stats


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_readme_header()
    append_progress("开始设计-开发-回测闭环。")

    config = load_v7_config()
    columns_module = load_v7_backtest_module("tmp_vq_columns", CASES[0])
    panel = pd.read_parquet(config.PANEL_PATH, columns=list(columns_module.PANEL_COLUMNS))
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = pd.read_parquet(config.MARKET_INDEX_PATH)
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date", drop=True)
    append_progress(f"加载 v7 panel rows={len(panel):,}。")

    backtest_dates = panel.loc[panel["trade_date"] >= pd.Timestamp(START_DATE), "trade_date"]
    if any(case["rebalance"] == "D" for case in CASES):
        signal_dates = sorted(pd.to_datetime(backtest_dates.drop_duplicates()))
    else:
        signal_dates = sorted(
            allowed_signal_dates(backtest_dates, "M")
            | allowed_signal_dates(backtest_dates, "Q")
        )
    features = fetch_financial_signal_features(signal_dates, START_DATE, END_DATE)
    append_progress("完成信号日财务特征准备，不合并到全量 panel。")

    nav_map: dict[str, pd.DataFrame] = {}
    rows = []
    for version in ["v4", "v5", "v6", "v7"]:
        nav = load_existing_nav(version)
        if nav is None:
            continue
        trades = load_existing_trades(version)
        nav_map[version] = nav
        row = summarize_nav(version, nav, trades)
        row.update(trade_duration_summary(trades))
        rows.append(row)

    for case in CASES:
        nav, trades, stats = run_case(case, panel, market, features)
        nav_map[case["case"]] = nav
        row = summarize_nav(case["case"], nav, trades, stats)
        row.update(trade_duration_summary(trades))
        rows.append(row)

    summary = pd.DataFrame(rows)
    summary.to_csv(OUTPUT_DIR / "summary_compare.csv", index=False, encoding="utf-8-sig")
    yearly = make_return_table(nav_map, "YE")
    monthly = make_return_table(nav_map, "ME")
    yearly.to_csv(OUTPUT_DIR / "yearly_returns.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "monthly_returns.csv", index=False, encoding="utf-8-sig")

    generate_report(
        summary,
        yearly,
        monthly,
        [
            "新浪财经：PB-ROE / Smart Beta 低估值优质资产复核",
            "BigQuant：PB-ROE 策略、红利低波与质量因子研究摘要",
            "本地 Tushare：027_daily_basic、042_fina_indicator",
        ],
    )
    append_progress(f"生成 HTML 报表：{REPORT_PATH}")
    print(summary.sort_values("total_return_pct", ascending=False).to_string(index=False))
    print(f"REPORT={REPORT_PATH}")


if __name__ == "__main__":
    main()

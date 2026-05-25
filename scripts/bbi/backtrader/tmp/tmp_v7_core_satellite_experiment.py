from __future__ import annotations

import html
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V7_DIR = BACKTRADER_DIR / "v7"

OUTPUT_DIR = TMP_DIR / "tmp_v7_core_satellite_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_core_satellite_README.md"

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"
START_DATE = "2018-01-01"
END_DATE = None

CASES = [
    {
        "case": "核心仓标签_前30止损8",
        "v7_weight": 1.00,
        "core_weight": 0.00,
        "core_quantile": 0.70,
        "filter_to_core": False,
        "rerank_by_core": False,
        "normal_stop": -0.05,
        "core_stop": -0.08,
    },
    {
        "case": "核心仓标签_前40止损8",
        "v7_weight": 1.00,
        "core_weight": 0.00,
        "core_quantile": 0.60,
        "filter_to_core": False,
        "rerank_by_core": False,
        "normal_stop": -0.05,
        "core_stop": -0.08,
    },
    {
        "case": "核心仓标签_前40止损10",
        "v7_weight": 1.00,
        "core_weight": 0.00,
        "core_quantile": 0.60,
        "filter_to_core": False,
        "rerank_by_core": False,
        "normal_stop": -0.05,
        "core_stop": -0.10,
    },
]


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def write_readme_header() -> None:
    README_PATH.write_text(
        """# tmp_v7 核心仓/卫星仓实验

目标：在不修改正式 v7 的前提下，验证“v7 强势趋势候选 + 价值质量核心仓标记 + 核心仓持有保护”是否能提升收益、减少止损和延长持仓。

头脑风暴结论：
- 不把 v7 改成纯价值策略；已有 tmp 实验证明纯价值质量低换手弱于 v7。
- 本轮只对 v7 已经选出的候选股做核心仓分层：高价值质量分为核心仓，其余仍是卫星交易仓。
- 第一轮严格保留 v7 原始排序、买入、加仓和熊市退出，只验证核心仓止损从 -5% 放宽到 -8% 或 -10% 是否有效。
- 财务指标必须按公告日后一日生效；估值指标只在信号日使用；交易仍用下一交易日开盘价。

专家角色评审：
- 量化研究员：价值、质量、低波/低换手可以作为长期持有条件，但不能替代 v7 的趋势主线。
- 数据工程师：`027_daily_basic` 和 `042_fina_indicator` 已有本地表和历史 tmp 使用记录，可以用于第一版。
- 风控专家：核心仓止损放宽必须有质量门槛，且第一轮只改止损一个点，不能同时改排序、过滤和熊市退出。
- 前端/报表专家：报表用中文展示，重点给年度、月度、交易次数、止损次数、持仓天数和是否建议合并。

Tavily 复核：
- S&P Global、MSCI、Robeco 等资料均把价值、动量、质量、低波、红利视为常见股票因子。
- A 股研究资料提示 PB-ROE、价值动量、低换手/低波动有效性依赖市场风格，必须回测验证，不能臆想。

进度：
""",
        encoding="utf-8",
    )


def zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (values - values.mean()) / std


def clip_numeric(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    low = values.quantile(0.02)
    high = values.quantile(0.98)
    return values.clip(low, high)


def lower_is_better_score(series: pd.Series) -> pd.Series:
    values = clip_numeric(series).where(lambda s: s > 0)
    return -zscore(values)


def higher_is_better_score(series: pd.Series) -> pd.Series:
    return zscore(clip_numeric(series))


def compute_core_quality_score(data: pd.DataFrame) -> pd.Series:
    return (
        0.16 * lower_is_better_score(data["pb"])
        + 0.10 * lower_is_better_score(data["pe_ttm"])
        + 0.12 * higher_is_better_score(data["dv_ttm"].fillna(0.0))
        + 0.26 * higher_is_better_score(data["roe"])
        + 0.10 * higher_is_better_score(data["roa"])
        + 0.12 * higher_is_better_score(data["ocf_to_or"])
        + 0.06 * higher_is_better_score(data.get("grossprofit_margin", pd.Series(0.0, index=data.index)))
        - 0.08 * higher_is_better_score(data["debt_to_assets"])
    )


def apply_core_satellite_score(
    candidates: pd.DataFrame,
    v7_weight: float,
    core_weight: float,
    core_quantile: float,
    filter_to_core: bool,
    rerank_by_core: bool = True,
    diagnostics: dict | None = None,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    data = candidates.copy()
    data["__original_order"] = np.arange(len(data))
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
        diagnostics["core_quality_candidate_days"] = diagnostics.get("core_quality_candidate_days", 0) + 1
        diagnostics["core_quality_missing_or_invalid"] = (
            diagnostics.get("core_quality_missing_or_invalid", 0) + int(len(data) - int(valid.sum()))
        )

    data["v7_raw_score"] = pd.to_numeric(data["score"], errors="coerce").fillna(0.0)
    data["core_quality_score"] = np.nan
    data["core_candidate"] = False
    scored = data[valid].copy()
    if scored.empty:
        return data.sort_values("__original_order").drop(columns=["__original_order"])

    scored["core_quality_score"] = compute_core_quality_score(scored)
    cutoff = scored["core_quality_score"].quantile(core_quantile)
    scored["core_candidate"] = scored["core_quality_score"] >= cutoff
    if rerank_by_core:
        scored["score"] = v7_weight * zscore(scored["v7_raw_score"]) + core_weight * scored["core_quality_score"]
    else:
        scored["score"] = scored["v7_raw_score"]
    if filter_to_core:
        before = len(scored)
        scored = scored[scored["core_candidate"]].copy()
        if diagnostics is not None:
            diagnostics["core_quality_filtered"] = diagnostics.get("core_quality_filtered", 0) + int(before - len(scored))
        return scored.sort_values(
            ["score", "core_candidate", "core_quality_score", "v7_raw_score"],
            ascending=[False, False, False, False],
        ).drop(columns=["__original_order"])

    data.loc[scored.index, "score"] = scored["score"]
    data.loc[scored.index, "core_quality_score"] = scored["core_quality_score"]
    data.loc[scored.index, "core_candidate"] = scored["core_candidate"]
    if rerank_by_core:
        out = data.sort_values(
            ["score", "core_candidate", "core_quality_score", "v7_raw_score"],
            ascending=[False, False, False, False],
        )
    else:
        out = data.sort_values("__original_order")
    return out.drop(columns=["__original_order"])


def should_stop_loss(pos: dict, profit_pct: float, normal_stop: float, core_stop: float) -> bool:
    threshold = core_stop if pos.get("core_entry") else normal_stop
    return profit_pct <= threshold


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"patch anchor not found: {old[:80]}")
    return source.replace(old, new, 1)


def load_v7_config():
    spec = importlib.util.spec_from_file_location("v7_config_for_core", V7_DIR / "config.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
            '        "weak_lowvol_mom_candidate_blocks": 0,\n',
            '        "weak_lowvol_mom_candidate_blocks": 0,\n'
            '        "core_initial_buys": 0,\n'
            '        "core_quality_candidate_days": 0,\n'
            '        "core_quality_missing_or_invalid": 0,\n'
            '        "core_quality_filtered": 0,\n',
        )
        source = replace_once(
            source,
            "elif profit_pct is not None and profit_pct <= LONG_STOP_LOSS_PCT:\n",
            "elif profit_pct is not None and __core_should_stop_loss(pos, profit_pct):\n",
        )
        source = replace_once(
            source,
            '                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)\n',
            '                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)\n'
            '                candidates = __core_attach_features(candidates, signal_date, CORE_FEATURES)\n'
            '                candidates = __core_apply_score(candidates, CORE_V7_WEIGHT, CORE_QUALITY_WEIGHT, CORE_QUANTILE, CORE_FILTER_TO_CORE, CORE_RERANK_BY_CORE, stats).reset_index(drop=True)\n',
        )
        source = replace_once(
            source,
            '                    if bought:\n'
            '                        bought_count += 1\n'
            '                        stats["buy_fills"] += 1\n'
            '                        if probe_open:\n',
            '                    if bought:\n'
            '                        bought_count += 1\n'
            '                        stats["buy_fills"] += 1\n'
            '                        if code in candidate_by_code.index and bool(candidate_by_code.loc[code].get("core_candidate", False)):\n'
            '                            holdings[code]["core_entry"] = True\n'
            '                            holdings[code]["core_quality_score"] = float(candidate_by_code.loc[code].get("core_quality_score", 0.0) or 0.0)\n'
            '                            stats["core_initial_buys"] += 1\n'
            '                        if probe_open:\n',
        )

        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.CORE_FEATURES = case.get("features", pd.DataFrame())
        module.CORE_V7_WEIGHT = case["v7_weight"]
        module.CORE_QUALITY_WEIGHT = case["core_weight"]
        module.CORE_QUANTILE = case["core_quantile"]
        module.CORE_FILTER_TO_CORE = case["filter_to_core"]
        module.CORE_RERANK_BY_CORE = case["rerank_by_core"]
        module.CORE_NORMAL_STOP = case["normal_stop"]
        module.CORE_STOP = case["core_stop"]
        module.__core_attach_features = attach_value_features
        module.__core_apply_score = apply_core_satellite_score
        module.__core_should_stop_loss = lambda pos, profit: should_stop_loss(
            pos, profit, module.CORE_NORMAL_STOP, module.CORE_STOP
        )
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
    return pd.concat(merged_parts, ignore_index=True)


def fetch_financial_signal_features(signal_dates: list[pd.Timestamp]) -> pd.DataFrame:
    if not signal_dates:
        return pd.DataFrame()
    end = pd.Timestamp.today().date().isoformat()
    engine = create_engine(DB_URL)
    daily_sql = f"""
        select ts_code, trade_date, pe_ttm, pb, dv_ttm, total_mv, circ_mv
        from {SCHEMA}."027_daily_basic"
        where trade_date in ({sql_date_list(signal_dates)})
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
        "方案": name,
        "最终净值": end_nav,
        "总收益%": total_ret * 100.0,
        "年化%": annual_ret * 100.0,
        "最大回撤%": max_dd * 100.0,
        "交易笔数": int(len(trades)),
    }
    if stats:
        row.update(
            {
                "买入次数": int(stats.get("buy_fills", 0)),
                "卖出次数": int(stats.get("sell_fills", 0)),
                "止损次数": int(stats.get("stop_loss_fills", 0)),
                "核心仓买入": int(stats.get("core_initial_buys", 0)),
                "核心候选日": int(stats.get("core_quality_candidate_days", 0)),
            }
        )
    row.update(trade_duration_summary(trades))
    return row


def trade_duration_summary(trades: pd.DataFrame) -> dict:
    if trades.empty or "action" not in trades.columns:
        return {"平仓批次": 0, "持仓中位天数": np.nan, "平均持仓天数": np.nan}
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
        return {"平仓批次": 0, "持仓中位天数": np.nan, "平均持仓天数": np.nan}
    s = pd.Series(lots)
    return {"平仓批次": int(len(s)), "持仓中位天数": float(s.median()), "平均持仓天数": float(s.mean())}


def period_returns(nav: pd.DataFrame, freq: str) -> pd.Series:
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["nav"] = pd.to_numeric(data["nav"], errors="coerce")
    data = data.sort_values("date").set_index("date")
    last = data["nav"].resample(freq).last().dropna()
    prev = pd.concat([pd.Series([data["nav"].iloc[0]], index=[last.index[0] - pd.offsets.Day(1)]), last])
    return prev.pct_change().iloc[1:] * 100.0


def make_return_table(nav_map: dict[str, pd.DataFrame], freq: str) -> pd.DataFrame:
    pieces = [period_returns(nav, freq).rename(name) for name, nav in nav_map.items()]
    table = pd.concat(pieces, axis=1).round(2)
    table.index = table.index.strftime("%Y" if freq == "YE" else "%Y-%m")
    return table.reset_index(names="期间")


def html_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    data = df if max_rows is None else df.head(max_rows)
    return data.to_html(index=False, escape=True, classes="data")


def generate_report(summary: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame) -> None:
    v7_rows = summary[summary["方案"].eq("v7")]
    exp = summary[summary["方案"].isin([case["case"] for case in CASES])]
    v7_return = float(v7_rows.iloc[0]["总收益%"]) if not v7_rows.empty else float("nan")
    best = exp.sort_values(["总收益%", "最大回撤%"], ascending=[False, False]).iloc[0] if not exp.empty else summary.iloc[0]
    if float(best["总收益%"]) > v7_return:
        advice = f"建议进入下一轮验证：{best['方案']} 总收益高于 v7。先不要直接合并，需做逐年归因和参数稳健性。"
    else:
        advice = f"暂不建议合并：本轮最佳 {best['方案']} 未超过 v7，说明核心仓持有保护没有带来足够收益补偿。"

    REPORT_PATH.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 核心仓/卫星仓实验</title>
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
<h1>v7 核心仓/卫星仓实验</h1>
<div class="note"><b>合并建议：</b>{html.escape(advice)}</div>
<p>本实验只在 tmp 中运行，不修改正式 v7。核心仓定义为：v7 已选出的强势候选股里，估值、盈利质量、现金流、负债和股息综合分靠前的股票。本轮严格保留 v7 原始候选排序、买入、加仓和熊市退出，只把核心仓的 5% 止损放宽到 8% 或 10%。</p>
<h2>全周期对比</h2>
{html_table(summary.round(4))}
<h2>年度收益率 %</h2>
{html_table(yearly)}
<h2>月度收益率 %</h2>
{html_table(monthly, 120)}
<h2>下一步</h2>
<p>如果本轮未超过 v7，不合并；下一轮应改为“核心仓只影响卖出，不参与候选排序”或增加行业主线分，而不是继续盲目放宽止损。</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def run_case(case: dict, panel: pd.DataFrame, market: pd.DataFrame, features: pd.DataFrame):
    case = dict(case)
    case["features"] = features
    module = load_v7_backtest_module(f"tmp_core_{case['case']}", case)
    nav, trades, rebalance, scores, holdings, stats = module.run_backtest(
        panel.copy(deep=False), market.copy(deep=False), START_DATE, END_DATE
    )
    nav.to_csv(OUTPUT_DIR / f"{case['case']}_nav_series.csv", index=False)
    trades.to_csv(OUTPUT_DIR / f"{case['case']}_trade_records.csv", index=False, encoding="utf-8-sig")
    rebalance.to_csv(OUTPUT_DIR / f"{case['case']}_rebalance_log.csv", index=False, encoding="utf-8-sig")
    stats.update(trade_duration_summary(trades))
    (OUTPUT_DIR / f"{case['case']}_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    append_progress(f"完成 {case['case']}：total_return={stats.get('total_return_pct'):.2f}%，trades={len(trades)}，core_buys={stats.get('core_initial_buys', 0)}。")
    return nav, trades, stats


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_readme_header()
    append_progress("开始设计-开发-回测闭环。")

    config = load_v7_config()
    columns_module = load_v7_backtest_module("tmp_core_columns", CASES[0])
    panel = pd.read_parquet(config.PANEL_PATH, columns=list(columns_module.PANEL_COLUMNS))
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = pd.read_parquet(config.MARKET_INDEX_PATH)
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date", drop=True)
    append_progress(f"加载 v7 panel rows={len(panel):,}。")

    signal_dates = sorted(pd.to_datetime(panel.loc[panel["trade_date"] >= pd.Timestamp(START_DATE), "trade_date"].drop_duplicates()))
    features = fetch_financial_signal_features(signal_dates)
    append_progress("完成信号日财务特征准备，不合并到全量 panel。")

    nav_map: dict[str, pd.DataFrame] = {}
    rows = []
    for version in ["v4", "v5", "v6", "v7"]:
        nav = load_existing_nav(version)
        if nav is None:
            continue
        trades = load_existing_trades(version)
        nav_map[version] = nav
        rows.append(summarize_nav(version, nav, trades))

    for case in CASES:
        nav, trades, stats = run_case(case, panel, market, features)
        nav_map[case["case"]] = nav
        rows.append(summarize_nav(case["case"], nav, trades, stats))

    summary = pd.DataFrame(rows)
    yearly = make_return_table(nav_map, "YE")
    monthly = make_return_table(nav_map, "ME")
    summary.to_csv(OUTPUT_DIR / "summary_compare.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "yearly_returns.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "monthly_returns.csv", index=False, encoding="utf-8-sig")
    generate_report(summary, yearly, monthly)
    append_progress(f"生成 HTML 报表：{REPORT_PATH}")
    append_progress("代码 review：本轮只改 tmp；财务 PIT 使用 ann_date + 1；未触碰 v7 正式代码；下一步按结果决定是否做行业主线版本。")
    print(summary.sort_values("总收益%", ascending=False).to_string(index=False))
    print(f"REPORT={REPORT_PATH}")


if __name__ == "__main__":
    main()

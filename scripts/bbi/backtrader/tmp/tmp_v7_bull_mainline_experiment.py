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

OUTPUT_DIR = TMP_DIR / "tmp_v7_bull_mainline_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_bull_mainline_README.md"

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"
START_DATE = "2018-01-01"
END_DATE = None

CASES = [
    {
        "case": "当前v7复现",
        "mode": "baseline",
        "boost_weight": 0.0,
        "filter_threshold": None,
        "breadth_threshold": None,
    },
    {
        "case": "牛市行业主线加分10",
        "mode": "boost",
        "boost_weight": 0.10,
        "filter_threshold": None,
        "breadth_threshold": None,
    },
    {
        "case": "牛市行业主线加分20",
        "mode": "boost",
        "boost_weight": 0.20,
        "filter_threshold": None,
        "breadth_threshold": None,
    },
    {
        "case": "牛市行业主线前40过滤",
        "mode": "filter",
        "boost_weight": 0.10,
        "filter_threshold": 0.60,
        "breadth_threshold": 0.55,
    },
    {
        "case": "牛市行业主线前30过滤",
        "mode": "filter",
        "boost_weight": 0.10,
        "filter_threshold": 0.70,
        "breadth_threshold": 0.58,
    },
]


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def write_readme_header() -> None:
    README_PATH.write_text(
        """# tmp_v7 牛市行业主线实验

目标：验证“牛市中坚持核心主线、减少失败买入、长期持有优质趋势”的量化版本能否提升 v7 收益。

头脑风暴结论：
- 不把 v7 改成价值股策略；此前价值/质量/低换手实验弱于 v7。
- 本轮只在牛市状态下使用行业主线，震荡市和熊市保持 v7 原逻辑。
- 本地申万/同花顺行业指数表当前不存在，所以第一版使用 `001_stock_basic.industry` 加股票级聚合。
- 主线定义必须客观：行业 63 日中位收益、21 日中位收益、行业内站上 BBI 比例、行业样本数量。
- 不使用 LLM 直接判断主线，避免不可复现和未来信息。

专家角色评审：
- 量化研究员：行业动量/行业轮动有研究依据，但不是无条件有效；必须和 v7 基准同口径回测。
- 数据工程师：当前可用行业指数表缺失，先用 stock_basic 行业字段；若后续补齐 `132_sw_daily` 和 `131_index_member_all`，再升级到行业指数版本。
- 风控专家：牛市可以更重视主线，熊市和弱势不放宽风控；过滤过强可能错过个股独立行情，所以同时测加分和过滤。
- 前端/报表专家：报表用中文，重点展示全周期、年度、月度、交易次数、止损次数、是否建议合并。

Tavily 复核：
- 行业轮动/行业动量是成熟研究方向，但文献也提示不同市场和周期下效果不同。
- 动量策略通常需要定期再平衡；本实验不提高频率，只把行业主线作为牛市候选排序/过滤条件。
- 结论必须服从本地回测结果，不能因为理论合理就合并。

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


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"patch anchor not found: {old[:80]}")
    return source.replace(old, new, 1)


def load_v7_config():
    spec = importlib.util.spec_from_file_location("v7_config_for_bull_mainline", V7_DIR / "config.py")
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
            '        "bull_mainline_mode": BULL_MAINLINE_CASE.get("mode", "baseline"),\n'
            '        "bull_mainline_signal_days": 0,\n'
            '        "bull_mainline_filtered": 0,\n',
        )
        source = replace_once(
            source,
            "                candidates = apply_weak_lowvol_mom_filter(\n"
            "                    candidates,\n"
            "                    market_regime_name,\n"
            "                    regime_snapshot,\n"
            "                    diagnostics=stats,\n"
            "                ).reset_index(drop=True)\n",
            "                candidates = apply_weak_lowvol_mom_filter(\n"
            "                    candidates,\n"
            "                    market_regime_name,\n"
            "                    regime_snapshot,\n"
            "                    diagnostics=stats,\n"
            "                ).reset_index(drop=True)\n"
            "                candidates = __apply_bull_mainline_overlay(\n"
            "                    candidates,\n"
            "                    market_regime_name,\n"
            "                    diagnostics=stats,\n"
            "                ).reset_index(drop=True)\n",
        )
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.BULL_MAINLINE_CASE = dict(case)
        module.__apply_bull_mainline_overlay = apply_bull_mainline_overlay
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


def fetch_stock_industry() -> pd.DataFrame:
    engine = create_engine(DB_URL)
    sql = text(f'SELECT ts_code, industry FROM {SCHEMA}."001_stock_basic"')
    with engine.connect() as conn:
        data = pd.read_sql(sql, conn)
    data["industry"] = data["industry"].fillna("未分类").replace("", "未分类")
    return data


def add_industry_mainline_features(panel: pd.DataFrame, industry_map: pd.DataFrame) -> pd.DataFrame:
    out = panel.merge(industry_map, on="ts_code", how="left")
    out["industry"] = out["industry"].fillna("未分类")
    usable = out[out["is_eligible"].fillna(False)].copy()
    usable["above_bbi_num"] = usable["above_bbi"].fillna(False).astype(float)
    grouped = usable.groupby(["trade_date", "industry"], observed=True).agg(
        industry_member_count=("ts_code", "count"),
        industry_ret_63_median=("ret_63", "median"),
        industry_ret_21_median=("ret_21", "median"),
        industry_above_bbi_ratio=("above_bbi_num", "mean"),
        industry_volatility_63_median=("volatility_63", "median"),
    ).reset_index()
    grouped = grouped[grouped["industry_member_count"] >= 8].copy()
    grouped["industry_ret_63_rank"] = grouped.groupby("trade_date")["industry_ret_63_median"].rank(pct=True)
    grouped["industry_ret_21_rank"] = grouped.groupby("trade_date")["industry_ret_21_median"].rank(pct=True)
    grouped["industry_low_vol_rank"] = grouped.groupby("trade_date")["industry_volatility_63_median"].rank(
        pct=True,
        ascending=False,
    )
    grouped["industry_mainline_score"] = (
        0.45 * grouped["industry_ret_63_rank"].fillna(0.0)
        + 0.25 * grouped["industry_ret_21_rank"].fillna(0.0)
        + 0.20 * grouped["industry_above_bbi_ratio"].fillna(0.0)
        + 0.10 * grouped["industry_low_vol_rank"].fillna(0.0)
    )
    keep_cols = [
        "trade_date",
        "industry",
        "industry_member_count",
        "industry_ret_63_median",
        "industry_ret_21_median",
        "industry_above_bbi_ratio",
        "industry_mainline_score",
    ]
    out = out.merge(grouped[keep_cols], on=["trade_date", "industry"], how="left")
    out["industry_member_count"] = out["industry_member_count"].fillna(0).astype("int32")
    for col in [
        "industry_ret_63_median",
        "industry_ret_21_median",
        "industry_above_bbi_ratio",
        "industry_mainline_score",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def apply_bull_mainline_overlay(
    candidates: pd.DataFrame,
    market_regime_name: str,
    diagnostics: dict | None = None,
) -> pd.DataFrame:
    case = globals().get("BULL_MAINLINE_CASE", {"mode": "baseline"})
    if candidates.empty or market_regime_name != "bull" or case.get("mode") == "baseline":
        return candidates
    data = candidates.copy()
    if diagnostics is not None:
        diagnostics["bull_mainline_signal_days"] = diagnostics.get("bull_mainline_signal_days", 0) + 1
    score = pd.to_numeric(data.get("industry_mainline_score", 0.0), errors="coerce").fillna(0.0)
    ret_63 = pd.to_numeric(data.get("industry_ret_63_median", 0.0), errors="coerce").fillna(0.0)
    breadth = pd.to_numeric(data.get("industry_above_bbi_ratio", 0.0), errors="coerce").fillna(0.0)
    member_count = pd.to_numeric(data.get("industry_member_count", 0), errors="coerce").fillna(0)
    if case.get("filter_threshold") is not None:
        threshold = float(case["filter_threshold"])
        breadth_threshold = float(case.get("breadth_threshold") or 0.0)
        mask = (
            score.ge(threshold)
            & breadth.ge(breadth_threshold)
            & ret_63.gt(0.0)
            & member_count.ge(8)
        )
        if diagnostics is not None:
            diagnostics["bull_mainline_filtered"] = diagnostics.get("bull_mainline_filtered", 0) + int(len(data) - int(mask.sum()))
        data = data[mask].copy()
        if data.empty:
            return data
    weight = float(case.get("boost_weight") or 0.0)
    if weight > 0:
        data["score"] = pd.to_numeric(data["score"], errors="coerce").fillna(0.0) + weight * zscore(
            data["industry_mainline_score"]
        )
    return data.sort_values(
        ["score", "industry_mainline_score", "above_ratio_63", "ret_63", "amount_ma20"],
        ascending=[False, False, False, False, False],
    )


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
    calmar = annual_ret / abs(max_dd) if max_dd < 0 else np.nan
    row = {
        "方案": name,
        "最终净值": end_nav,
        "总收益%": total_ret * 100.0,
        "年化%": annual_ret * 100.0,
        "最大回撤%": max_dd * 100.0,
        "Calmar": calmar,
        "交易笔数": int(len(trades)),
    }
    if stats:
        row.update(
            {
                "买入次数": int(stats.get("buy_fills", 0)),
                "卖出次数": int(stats.get("sell_fills", 0)),
                "止损次数": int(stats.get("stop_loss_fills", 0)),
                "牛市主线生效天数": int(stats.get("bull_mainline_signal_days", 0)),
                "牛市主线过滤数量": int(stats.get("bull_mainline_filtered", 0)),
            }
        )
    row.update(trade_duration_summary(trades))
    return row


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


def pick_report_baseline(summary: pd.DataFrame) -> pd.Series:
    replay = summary[summary["方案"].eq("当前v7复现")]
    if not replay.empty:
        return replay.iloc[0]
    v7 = summary[summary["方案"].eq("v7")]
    if not v7.empty:
        return v7.iloc[0]
    return summary.iloc[0]


def generate_report(summary: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame) -> None:
    experiment_names = [case["case"] for case in CASES if case["mode"] != "baseline"]
    exp = summary[summary["方案"].isin(experiment_names)]
    baseline = pick_report_baseline(summary)
    best = exp.sort_values(["总收益%", "Calmar"], ascending=[False, False]).iloc[0] if not exp.empty else summary.iloc[0]
    if float(best["总收益%"]) > float(baseline["总收益%"]) and float(best["Calmar"]) >= float(baseline["Calmar"]):
        advice = f"建议进入下一轮验证：{best['方案']} 同时超过当前 v7 复现收益和 Calmar。"
    elif float(best["总收益%"]) > float(baseline["总收益%"]):
        advice = f"谨慎验证：{best['方案']} 收益超过 v7，但风险收益比未同步确认。"
    else:
        advice = f"暂不建议合并：本轮最佳 {best['方案']} 未超过当前 v7 复现基线。"
    sources = [
        ("Gauging the effectiveness of sector rotation strategies", "https://link.springer.com/article/10.1057/s41260-020-00161-6"),
        ("Dynamic Sector Rotation Strategy", "https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4573209_code3074981.pdf?abstractid=4573209&mirid=1"),
        ("行业轮动定义：按经济周期或趋势在行业间配置", "https://www.investopedia.com/terms/s/sectorrotation.asp"),
    ]
    source_html = "".join(f'<li><a href="{html.escape(url)}">{html.escape(title)}</a></li>' for title, url in sources)
    REPORT_PATH.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 牛市行业主线实验</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #222; }}
h1, h2 {{ margin-bottom: 8px; }}
.note {{ padding: 12px 14px; background: #f3f6fa; border-left: 4px solid #2563eb; margin: 12px 0; }}
table.data {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 8px 0 22px; }}
table.data th, table.data td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
table.data th:first-child, table.data td:first-child {{ text-align: left; }}
table.data th {{ background: #f7f7f7; }}
</style>
</head>
<body>
<h1>v7 牛市行业主线实验</h1>
<div class="note"><b>合并建议：</b>{html.escape(advice)}</div>
<p>本实验只在 tmp 中运行，不修改正式 v7。牛市中用行业主线对候选股加分或过滤；震荡市和熊市保持 v7 原买入、退出、止损和熊市防守逻辑。</p>
<p>数据说明：本地没有申万/同花顺行业指数历史表，本轮使用 stock_basic 行业字段，加总同一行业内个股 63 日收益、21 日收益和站上 BBI 的比例。后续若补齐行业指数数据，应升级为行业指数版本。</p>
<h2>全周期对比</h2>
{html_table(summary.round(4))}
<h2>年度收益率 %</h2>
{html_table(yearly)}
<h2>月度收益率 %</h2>
{html_table(monthly, 120)}
<h2>研究依据</h2>
<ul>{source_html}</ul>
<h2>下一步</h2>
<p>若没有超过 v7，不合并；若超过 v7，需要继续做参数稳健性、弱市年份拆解、行业覆盖诊断，并优先补齐申万行业指数数据。</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def run_case(case: dict, panel: pd.DataFrame, market: pd.DataFrame):
    globals()["BULL_MAINLINE_CASE"] = dict(case)
    module = load_v7_backtest_module(f"tmp_bull_mainline_{case['mode']}_{case['case']}", case)
    nav, trades, rebalance, scores, holdings, stats = module.run_backtest(
        panel.copy(deep=False),
        market.copy(deep=False),
        START_DATE,
        END_DATE,
    )
    nav.to_csv(OUTPUT_DIR / f"{case['case']}_nav_series.csv", index=False)
    trades.to_csv(OUTPUT_DIR / f"{case['case']}_trade_records.csv", index=False, encoding="utf-8-sig")
    rebalance.to_csv(OUTPUT_DIR / f"{case['case']}_rebalance_log.csv", index=False, encoding="utf-8-sig")
    (OUTPUT_DIR / f"{case['case']}_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    append_progress(f"完成 {case['case']}：total_return={stats.get('total_return_pct'):.2f}%，trades={len(trades)}。")
    return nav, trades, stats


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_readme_header()
    append_progress("开始设计-开发-回测闭环。")

    config = load_v7_config()
    columns_module = load_v7_backtest_module("tmp_bull_mainline_columns", CASES[0])
    panel = pd.read_parquet(config.PANEL_PATH, columns=list(columns_module.PANEL_COLUMNS))
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    industry_map = fetch_stock_industry()
    panel = add_industry_mainline_features(panel, industry_map)
    append_progress(f"加载并计算行业主线特征 rows={len(panel):,}，industries={industry_map['industry'].nunique():,}。")

    market = pd.read_parquet(config.MARKET_INDEX_PATH)
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market = market.sort_values("trade_date").set_index("trade_date", drop=True)

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
        nav, trades, stats = run_case(case, panel, market)
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
    append_progress("代码 review：本轮只改 tmp；只在 bull 状态候选排序/过滤层叠加行业主线；neutral/bear 保持 v7 原逻辑。")
    print(summary.sort_values("总收益%", ascending=False).to_string(index=False))
    print(f"REPORT={REPORT_PATH}")


if __name__ == "__main__":
    main()

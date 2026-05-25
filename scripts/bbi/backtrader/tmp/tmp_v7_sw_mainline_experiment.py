from __future__ import annotations

import html
import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V7_DIR = BACKTRADER_DIR / "v7"

OUTPUT_DIR = TMP_DIR / "tmp_v7_sw_mainline_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_sw_mainline_README.md"

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
    },
    {
        "case": "牛市申万主线加分10",
        "mode": "boost",
        "boost_weight": 0.10,
        "filter_threshold": None,
    },
    {
        "case": "牛市申万主线加分20",
        "mode": "boost",
        "boost_weight": 0.20,
        "filter_threshold": None,
    },
    {
        "case": "牛市申万主线过滤60",
        "mode": "filter",
        "boost_weight": 0.10,
        "filter_threshold": 0.60,
    },
]


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def write_readme_header() -> None:
    README_PATH.write_text(
        """# tmp_v7 申万行业主线实验

目标：把牛市中的“核心主线”改成申万行业指数驱动，而不是静态行业名粗聚合。

关键判断：
- `132_sw_daily` 是可用的真实申万行业指数历史序列，能覆盖 2018+ 回测。
- `131_index_member_all` 在当前库里是静态快照，没有 `out_date` 变更，因此不能当历史成分表使用。
- 为了做可运行的研究验证，本轮用 `131` 的三级行业名做股票到行业的代理映射，但明确标记为研究代理，不声称历史真值。

设计原则：
- 牛市：行业主线加分或轻过滤。
- 熊市、弱势：保持 v7 原逻辑，不放宽风控。
- 不让行业主线替代个股趋势。
- 价值/质量只做排雷，不压过趋势。

专家评审：
- 量化研究员：行业轮动应以行业指数序列为核心，不应以股票静态行业名为主。
- 数据工程师：`132` 可用于时间序列，`131` 只能做当前分类代理。
- 风控专家：过滤阈值应比上一版更谨慎，先测加分版。
- 报表专家：只看结果，不讲复杂术语，给出是否合并和下一步。

进度：
""",
        encoding="utf-8",
    )


def normalize_name(name: str) -> str:
    if pd.isna(name):
        return ""
    s = str(name).strip()
    s = re.sub(r"\s+", "", s)
    for token in ["Ⅱ", "Ⅲ", "Ⅰ", "IV", "V"]:
        s = s.replace(token, "")
    return s


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
    spec = importlib.util.spec_from_file_location("v7_config_for_sw_mainline", V7_DIR / "config.py")
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
            '        "sw_mainline_mode": SW_MAINLINE_CASE.get("mode", "baseline"),\n'
            '        "sw_mainline_signal_days": 0,\n'
            '        "sw_mainline_filtered": 0,\n',
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
            "                candidates = __apply_sw_mainline_overlay(\n"
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
        module.SW_MAINLINE_CASE = dict(case)
        module.__apply_sw_mainline_overlay = apply_sw_mainline_overlay
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


def fetch_stock_industry_proxy() -> pd.DataFrame:
    engine = create_engine(DB_URL)
    sql = text(f"""
        select s.ts_code, s.industry, m.l3_name
        from {SCHEMA}."001_stock_basic" s
        left join {SCHEMA}."131_index_member_all" m
          on s.ts_code = m.ts_code and m.is_new = 'Y'
    """)
    with engine.connect() as conn:
        data = pd.read_sql(sql, conn)
    data["proxy_industry"] = data["l3_name"].fillna(data["industry"]).fillna("未分类")
    data["proxy_industry_norm"] = data["proxy_industry"].map(normalize_name)
    data["industry_norm"] = data["industry"].map(normalize_name)
    return data[["ts_code", "industry", "proxy_industry", "proxy_industry_norm", "industry_norm"]]


def build_sw_mainline_table() -> pd.DataFrame:
    engine = create_engine(DB_URL)
    sql = text(f"""
        select ts_code, trade_date, name, close, high, low, pct_change, pe, pb, float_mv, total_mv
        from {SCHEMA}."132_sw_daily"
        where trade_date >= cast(:start_date as date)
          and trade_date <= cast(:end_date as date)
    """)
    with engine.connect() as conn:
        table = pd.read_sql(sql, conn, params={"start_date": START_DATE, "end_date": END_DATE or pd.Timestamp.today().strftime("%Y-%m-%d")})
    table["trade_date"] = pd.to_datetime(table["trade_date"])
    table["name_norm"] = table["name"].map(normalize_name)
    table = table.groupby(["name_norm", "trade_date"], as_index=False).agg(
        close=("close", "median"),
        high=("high", "median"),
        low=("low", "median"),
        pct_change=("pct_change", "median"),
        pe=("pe", "median"),
        pb=("pb", "median"),
        float_mv=("float_mv", "median"),
        total_mv=("total_mv", "median"),
        source_codes=("ts_code", "nunique"),
    )
    table = table.sort_values(["name_norm", "trade_date"]).reset_index(drop=True)
    group = table.groupby("name_norm", sort=False)
    table["ret_21"] = group["close"].pct_change(21)
    table["ret_63"] = group["close"].pct_change(63)
    table["ma20"] = group["close"].transform(lambda s: s.rolling(20, min_periods=15).mean())
    table["ma60"] = group["close"].transform(lambda s: s.rolling(60, min_periods=30).mean())
    table["above_ma20"] = table["close"] > table["ma20"]
    table["above_ma60"] = table["close"] > table["ma60"]
    table["bbi_proxy"] = table["above_ma20"].astype(float) * 0.6 + table["above_ma60"].astype(float) * 0.4
    table["ret_63_rank"] = table.groupby("trade_date")["ret_63"].rank(pct=True)
    table["ret_21_rank"] = table.groupby("trade_date")["ret_21"].rank(pct=True)
    table["sw_mainline_score"] = (
        0.40 * table["ret_63_rank"].fillna(0.0)
        + 0.25 * table["ret_21_rank"].fillna(0.0)
        + 0.15 * table["above_ma20"].astype(float).fillna(0.0)
        + 0.10 * table["above_ma60"].astype(float).fillna(0.0)
        + 0.10 * table["bbi_proxy"].fillna(0.0)
    )
    table["sw_mainline_rank"] = table.groupby("trade_date")["sw_mainline_score"].rank(pct=True)
    table["sw_member_count"] = table.groupby("trade_date")["name_norm"].transform("count")
    return table


def add_sw_mainline_features(panel: pd.DataFrame, stock_map: pd.DataFrame, sw_daily: pd.DataFrame) -> pd.DataFrame:
    out = panel.merge(stock_map, on="ts_code", how="left")
    out["proxy_industry_norm"] = out["proxy_industry_norm"].fillna("未分类")
    sw_daily = sw_daily.copy()
    out = out.merge(
        sw_daily[
            [
                "trade_date",
                "name_norm",
                "sw_member_count",
                "sw_mainline_score",
                "sw_mainline_rank",
            ]
        ],
        left_on=["trade_date", "proxy_industry_norm"],
        right_on=["trade_date", "name_norm"],
        how="left",
    )
    out = out.drop(columns=["name_norm"], errors="ignore")
    for col in [
        "sw_member_count",
        "sw_mainline_score",
        "sw_mainline_rank",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def apply_sw_mainline_overlay(candidates: pd.DataFrame, market_regime_name: str, diagnostics: dict | None = None) -> pd.DataFrame:
    case = globals().get("SW_MAINLINE_CASE", {"mode": "baseline"})
    if candidates.empty or market_regime_name != "bull" or case.get("mode") == "baseline":
        return candidates
    data = candidates.copy()
    if diagnostics is not None:
        diagnostics["sw_mainline_signal_days"] = diagnostics.get("sw_mainline_signal_days", 0) + 1
    rank = pd.to_numeric(data.get("sw_mainline_rank", 0.0), errors="coerce").fillna(0.0)
    score = pd.to_numeric(data.get("sw_mainline_score", 0.0), errors="coerce").fillna(0.0)
    if case.get("filter_threshold") is not None:
        threshold = float(case["filter_threshold"])
        mask = rank.ge(threshold) & score.gt(0.0)
        if diagnostics is not None:
            diagnostics["sw_mainline_filtered"] = diagnostics.get("sw_mainline_filtered", 0) + int(len(data) - int(mask.sum()))
        data = data[mask].copy()
        if data.empty:
            return data
    weight = float(case.get("boost_weight") or 0.0)
    if weight > 0:
        data["score"] = pd.to_numeric(data["score"], errors="coerce").fillna(0.0) + weight * zscore(data["sw_mainline_score"])
    return data.sort_values(
        ["score", "sw_mainline_score", "above_ratio_63", "ret_63", "amount_ma20"],
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
                "申万主线生效天数": int(stats.get("sw_mainline_signal_days", 0)),
                "申万主线过滤数量": int(stats.get("sw_mainline_filtered", 0)),
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
    source_html = "".join(
        f'<li><a href="{html.escape(url)}">{html.escape(title)}</a></li>'
        for title, url in [
            ("申万行业分类", "https://tushare.pro/document/2?doc_id=181"),
            ("申万行业成分（分级）", "https://tushare.pro/document/2?doc_id=335"),
            ("申万行业指数日行情", "https://tushare.pro/document/2?doc_id=327"),
        ]
    )
    REPORT_PATH.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 申万行业主线实验</title>
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
<h1>v7 申万行业主线实验</h1>
<div class="note"><b>合并建议：</b>{html.escape(advice)}</div>
<p>本实验使用申万行业指数 `132_sw_daily` 计算行业主线强弱；`131_index_member_all` 只作为股票到行业的研究代理映射，不当作历史成分真值。</p>
<p>这意味着结果比上一版更接近真实行业轮动，但仍有历史分类代理误差，不能把它当最终定论。</p>
<h2>全周期对比</h2>
{html_table(summary.round(4))}
<h2>年度收益率 %</h2>
{html_table(yearly)}
<h2>月度收益率 %</h2>
{html_table(monthly, 120)}
<h2>研究依据</h2>
<ul>{source_html}</ul>
<h2>下一步</h2>
<p>若不超过 v7，不合并；若接近或超过 v7，再细看 2018、2022 等弱市年份表现，并考虑只保留“加分版”而不做硬过滤。</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def run_case(case: dict, panel: pd.DataFrame, market: pd.DataFrame):
    globals()["SW_MAINLINE_CASE"] = dict(case)
    module = load_v7_backtest_module(f"tmp_sw_mainline_{case['mode']}_{case['case']}", case)
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
    columns_module = load_v7_backtest_module("tmp_sw_mainline_columns", CASES[0])
    panel = pd.read_parquet(config.PANEL_PATH, columns=list(columns_module.PANEL_COLUMNS))
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    stock_map = fetch_stock_industry_proxy()
    sw_daily = build_sw_mainline_table()
    panel = add_sw_mainline_features(panel, stock_map, sw_daily)
    append_progress(
        f"加载并计算申万主线特征 rows={len(panel):,}，sw_groups={sw_daily['name_norm'].nunique():,}，"
        f"stock_map_coverage={(panel['sw_mainline_rank'].notna().mean() * 100):.2f}%"
    )

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
    append_progress("代码 review：申万指数用于时间序列，131 仅作股票行业代理映射。")
    print(summary.sort_values("总收益%", ascending=False).to_string(index=False))
    print(f"REPORT={REPORT_PATH}")


if __name__ == "__main__":
    main()

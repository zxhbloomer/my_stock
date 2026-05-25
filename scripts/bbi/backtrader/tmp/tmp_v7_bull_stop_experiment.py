from __future__ import annotations

import html
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V7_DIR = BACKTRADER_DIR / "v7"

OUTPUT_DIR = TMP_DIR / "tmp_v7_bull_stop_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_bull_stop_README.md"

START_DATE = "2018-01-01"
END_DATE = None

CASES = [
    {"case": "当前v7复现", "stop_mode": "baseline"},
    {"case": "牛市固定止损8", "stop_mode": "fixed8"},
    {"case": "牛市固定止损10", "stop_mode": "fixed10"},
    {"case": "牛市ATR二倍止损", "stop_mode": "atr2"},
    {"case": "牛市吊灯止损三倍", "stop_mode": "chandelier3"},
]


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def write_readme_header() -> None:
    README_PATH.write_text(
        """# tmp_v7 牛市专用止损实验

目标：验证“牛市可适当宽止损，熊市不宽止损”的假设是否能提升 v7 收益。

头脑风暴结论：
- 不做全市场宽止损；此前宽止损实验已经证明无条件放宽不可靠。
- 先复现当前正式 v7，再只在 v7 已判断的 bull 状态下放宽止损；neutral 和 bear 仍保持 v7 的 -5% 止损。
- 熊市退出、跌停退出、放量大阴线退出、开仓过滤均不改。
- ATR/吊灯止损只使用 signal_date 已知的 high/low/close 历史行情，不用未来价格。

专家角色评审：
- 量化研究员：牛市让趋势持仓有更大波动容忍度是合理假设，但必须和熊市风控分离。
- 风控专家：熊市不宽止损；若收益提升来自回撤显著扩大，不合并。
- 数据工程师：v7 panel 已有 high/low/close，可以在 tmp 中计算 ATR 百分比和吊灯止损，不需要改 10_prepare_data。
- 前端/报表专家：报表展示全周期、年度、月度，并明确是否建议合并。

Tavily 复核：
- ATR 是常见波动率止损基础；止损距离可用 ATR 乘数动态调整。
- Chandelier Exit 是基于 ATR 的趋势跟踪退出方法，常见参数为 22 日、3 倍 ATR；ATR 固定止损先用 2 倍，不扫参数。
- 成熟风控更强调市场状态：趋势/牛市可给空间，熊市应降仓、少开仓、快退出。

进度：
""",
        encoding="utf-8",
    )


def add_atr_stop_features(
    panel: pd.DataFrame,
    atr_window: int = 14,
    chandelier_window: int = 22,
    chandelier_mult: float = 3.0,
) -> pd.DataFrame:
    out = panel.sort_values(["ts_code", "trade_date"]).copy()
    high = pd.to_numeric(out["high"], errors="coerce")
    low = pd.to_numeric(out["low"], errors="coerce")
    close = pd.to_numeric(out["close"], errors="coerce")
    prev_close = close.groupby(out["ts_code"], sort=False).shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.groupby(out["ts_code"], sort=False).transform(
        lambda s: s.rolling(atr_window, min_periods=max(3, atr_window // 2)).mean()
    )
    rolling_high = high.groupby(out["ts_code"], sort=False).transform(
        lambda s: s.rolling(chandelier_window, min_periods=max(3, chandelier_window // 2)).max()
    )
    out["atr_pct_14"] = atr / close.replace(0, np.nan)
    chandelier_stop_price = rolling_high - chandelier_mult * atr
    out["chandelier_stop_pct"] = chandelier_stop_price / close.replace(0, np.nan) - 1.0
    return out


def stop_threshold_for_regime(market_regime_name: str, stop_mode: str, normal_stop: float) -> float:
    if stop_mode == "baseline":
        return normal_stop
    if market_regime_name != "bull":
        return normal_stop
    if stop_mode == "fixed8":
        return -0.08
    if stop_mode == "fixed10":
        return -0.10
    return normal_stop


def dynamic_stop_threshold(market_regime_name: str, stop_mode: str, row: pd.Series, normal_stop: float) -> float:
    fixed = stop_threshold_for_regime(market_regime_name, stop_mode, normal_stop)
    if market_regime_name != "bull":
        return normal_stop
    if stop_mode == "atr2":
        atr_pct = pd.to_numeric(pd.Series([row.get("atr_pct_14")]), errors="coerce").iloc[0]
        if pd.notna(atr_pct) and atr_pct > 0:
            return min(normal_stop, -2.0 * float(atr_pct))
    if stop_mode == "chandelier3":
        stop_pct = pd.to_numeric(pd.Series([row.get("chandelier_stop_pct")]), errors="coerce").iloc[0]
        if pd.notna(stop_pct):
            return min(normal_stop, float(stop_pct))
    return fixed


def bull_stop_trigger(
    market_regime_name: str,
    stop_mode: str,
    code: str,
    signal_panel: pd.DataFrame,
    profit_pct: float,
    normal_stop: float,
) -> bool:
    if code not in signal_panel.index:
        return profit_pct <= normal_stop
    threshold = dynamic_stop_threshold(market_regime_name, stop_mode, signal_panel.loc[code], normal_stop)
    return profit_pct <= threshold


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"patch anchor not found: {old[:80]}")
    return source.replace(old, new, 1)


def load_v7_config():
    spec = importlib.util.spec_from_file_location("v7_config_for_bull_stop", V7_DIR / "config.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_v7_backtest_module(module_name: str, stop_mode: str):
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
            '        "bull_stop_mode": BULL_STOP_MODE,\n'
            '        "bull_stop_checks": 0,\n'
            '        "bull_stop_fills": 0,\n',
        )
        source = replace_once(
            source,
            "elif profit_pct is not None and profit_pct <= LONG_STOP_LOSS_PCT:\n",
            "elif profit_pct is not None and __bull_stop_trigger(market_regime_name, code, signal_panel, profit_pct):\n",
        )
        source = replace_once(
            source,
            '                    if exit_reason == "long_stop_loss":\n'
            '                        stats["stop_loss_fills"] += 1\n',
            '                    if exit_reason == "long_stop_loss":\n'
            '                        stats["stop_loss_fills"] += 1\n'
            '                        if market_regime_name == "bull":\n'
            '                            stats["bull_stop_fills"] += 1\n',
        )

        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.BULL_STOP_MODE = stop_mode

        def _trigger(market_regime_name, code, signal_panel, profit_pct):
            if market_regime_name == "bull":
                module.stats_placeholder = None
            return bull_stop_trigger(
                market_regime_name,
                module.BULL_STOP_MODE,
                code,
                signal_panel,
                profit_pct,
                module.LONG_STOP_LOSS_PCT,
            )

        module.__bull_stop_trigger = _trigger
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
                "牛市止损成交": int(stats.get("bull_stop_fills", 0)),
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
    experiment_names = [case["case"] for case in CASES if case["stop_mode"] != "baseline"]
    exp = summary[summary["方案"].isin(experiment_names)]
    baseline = pick_report_baseline(summary)
    v7_return = float(baseline["总收益%"])
    best = exp.sort_values(["总收益%", "最大回撤%"], ascending=[False, False]).iloc[0] if not exp.empty else summary.iloc[0]
    if float(best["总收益%"]) > v7_return:
        advice = f"可进入下一轮验证：{best['方案']} 总收益高于当前 v7 复现基线，但需检查弱市年份和回撤。"
    else:
        advice = f"暂不建议合并：本轮最佳 {best['方案']} 未超过当前 v7 复现基线。"
    sources = [
        ("ATR 波动率止损说明", "https://www.investopedia.com/articles/trading/09/volatility-stops.asp"),
        ("Chandelier Exit 定义和常见 22 日/3ATR 参数", "https://corporatefinanceinstitute.com/resources/equities/chandelier-exit/"),
        ("ATR 动态止损实践说明", "https://www.luxalgo.com/blog/how-to-use-atr-for-volatility-based-stop-losses"),
        ("波动率止损和 ATR trailing stop", "https://trendspider.com/learning-center/volatility-stop-indicator-a-comprehensive-guide-for-traders"),
    ]
    source_html = "".join(f'<li><a href="{html.escape(url)}">{html.escape(title)}</a></li>' for title, url in sources)
    REPORT_PATH.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 牛市专用止损实验</title>
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
<h1>v7 牛市专用止损实验</h1>
<div class="note"><b>合并建议：</b>{html.escape(advice)}</div>
<p>本实验只在 tmp 中运行，不修改正式 v7。只在市场状态为牛市时调整止损；震荡市和熊市保持 v7 原 5% 止损、熊市退出、跌停退出和放量大阴线退出。报表合并建议使用“当前v7复现”作为基准，避免旧输出污染判断。</p>
<h2>全周期对比</h2>
{html_table(summary.round(4))}
<h2>年度收益率 %</h2>
{html_table(yearly)}
<h2>月度收益率 %</h2>
{html_table(monthly, 120)}
<h2>研究依据</h2>
<ul>{source_html}</ul>
<h2>下一步</h2>
<p>若没有超过 v7，不合并；若超过 v7，需要进一步看 2018、2022 等弱市年份是否恶化，以及收益是否只来自单一年份。</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def run_case(case: dict, panel: pd.DataFrame, market: pd.DataFrame):
    module = load_v7_backtest_module(f"tmp_bull_stop_{case['stop_mode']}", case["stop_mode"])
    nav, trades, rebalance, scores, holdings, stats = module.run_backtest(
        panel.copy(deep=False), market.copy(deep=False), START_DATE, END_DATE
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
    columns_module = load_v7_backtest_module("tmp_bull_stop_columns", CASES[0]["stop_mode"])
    panel = pd.read_parquet(config.PANEL_PATH, columns=list(columns_module.PANEL_COLUMNS))
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = add_atr_stop_features(panel)
    append_progress(f"加载并计算 ATR/吊灯止损特征 rows={len(panel):,}。")
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
    append_progress("代码 review：本轮只改 tmp；只替换牛市止损判断；neutral/bear 保持 v7 原风控。")
    print(summary.sort_values("总收益%", ascending=False).to_string(index=False))
    print(f"REPORT={REPORT_PATH}")


if __name__ == "__main__":
    main()

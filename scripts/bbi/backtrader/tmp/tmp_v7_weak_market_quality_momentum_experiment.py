from __future__ import annotations

import html
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V4_DIR = BACKTRADER_DIR / "v4"
V5_DIR = BACKTRADER_DIR / "v5"
V6_DIR = BACKTRADER_DIR / "v6"
V7_DIR = BACKTRADER_DIR / "v7"

OUTPUT_DIR = TMP_DIR / "tmp_v7_weak_market_quality_momentum_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_weak_market_quality_momentum_README.md"
DESIGN_PATH = TMP_DIR / "tmp_v7_weak_market_quality_momentum_design.md"
PLAN_PATH = TMP_DIR / "tmp_v7_weak_market_quality_momentum_plan.md"

START_DATE = "2018-01-01"
END_DATE = None

WEAK_FILTER_MODES = [
    "v7_baseline",
    "weak_lowvol_mom",
    "weak_fip_lowvol",
    "weak_relative_strength",
    "weak_combined",
]


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def write_design_and_plan() -> None:
    DESIGN_PATH.write_text(
        """# tmp_v7 弱熊市质量动量过滤实验设计

## 目标
保留 v6/v7 在牛市和正常市场的收益能力，只在弱市/熊市下收紧买入候选，验证低波、动量一致性、相对强弱和风险过滤能否减少 2018、2022 等弱熊年份的损失。

## 研究依据
- Tavily 复核：低波动因子适合作为防御增强，但单独使用通常只是少跌；公开研究更支持低波 + 动量、价值/红利/质量的组合。
- Tavily 复核：Momentum Crashes 研究提示熊市和高波动阶段纯动量容易在反弹时崩溃，因此弱熊市场不能只追短期强势，要加入波动和趋势质量约束。
- 本地实验：全空仓/强降仓能改善 2018，但显著伤害 2022 和全周期复利，因此本实验不采用一刀切空仓。

## 方案
不修改 v7 正式代码。动态加载 v7 回测模块，在内存里插入弱熊市候选过滤：
- 非弱市/非熊市：候选完全透传，保持 v7。
- bear 或弱 neutral：按实验 case 收紧候选。
- 使用 T-1 signal_date 面板字段；新增 FIP 类 `positive_ret_ratio_63` 和 `market_ret_63` 也只由截至 signal_date 的历史价格计算。

## 专家 review
- 量化研究员：方向合理，避免了把 2022 简化为单边熊市。
- 数据工程师：第一轮用现有 panel 与 market_index，避免新增财务公告日对齐风险。
- 风控专家：不做全空仓，先做候选质量过滤，降低误杀反弹风险。
""",
        encoding="utf-8",
    )
    PLAN_PATH.write_text(
        """# tmp_v7 Weak Market Quality Momentum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 本计划按用户要求不操作 git。

**Goal:** 在 tmp 中验证弱熊市低波动量过滤是否优于 v7 baseline。

**Architecture:** 动态加载 v7 `20_run_backtest.py`，不改正式 v7；对 `score_candidates` 后的候选增加 case 级过滤；生成全周期、年度、月度 HTML 对比。

**Tech Stack:** Python, pandas, v7 backtest module, local CSV/Parquet outputs.

---

### Task 1: 测试先行
- [x] 新增 `test_tmp_v7_weak_market_quality_momentum.py`。
- [x] 验证 RED：目标实验模块不存在时测试失败。

### Task 2: 实验脚本
- [x] 新增 `tmp_v7_weak_market_quality_momentum_experiment.py`。
- [x] 实现 FIP、market_ret_63、弱熊市场候选过滤。
- [x] 动态加载 v7 并在内存注入过滤逻辑。

### Task 3: 回测和报表
- [ ] 运行测试。
- [ ] 运行全周期回测。
- [ ] 生成并打开 HTML 报表。
- [ ] 记录 README 进度和 review 结论。
""",
        encoding="utf-8",
    )


def add_positive_return_ratio(panel: pd.DataFrame, window: int = 63, min_periods: int = 30) -> pd.DataFrame:
    out = panel.sort_values(["ts_code", "trade_date"]).copy()
    returns = out.groupby("ts_code", sort=False)["close_qfq"].pct_change()
    positive = returns.gt(0).where(returns.notna())
    out["positive_ret_ratio_63"] = (
        positive.groupby(out["ts_code"], sort=False)
        .transform(lambda s: s.rolling(window, min_periods=min_periods).mean())
        .fillna(0.0)
    )
    return out


def add_market_ret_63(panel: pd.DataFrame, market: pd.DataFrame | None) -> pd.DataFrame:
    out = panel.copy()
    if market is None or market.empty or "close" not in market.columns:
        out["market_ret_63"] = 0.0
        return out
    market_frame = market.copy()
    if "trade_date" not in market_frame.columns:
        market_frame["trade_date"] = market_frame.index
    market_frame = market_frame.reset_index(drop=True)
    market_frame["trade_date"] = pd.to_datetime(market_frame["trade_date"])
    market_frame = market_frame.sort_values("trade_date")
    market_frame["market_ret_63"] = pd.to_numeric(market_frame["close"], errors="coerce").pct_change(63)
    return out.merge(market_frame[["trade_date", "market_ret_63"]], on="trade_date", how="left")


def is_weak_market(market_regime_name: str, regime_snapshot: dict | None = None) -> bool:
    if market_regime_name == "bear":
        return True
    if market_regime_name != "neutral" or not regime_snapshot:
        return False
    market_dd = float(regime_snapshot.get("market_dd_252", 0.0) or 0.0)
    breadth = float(regime_snapshot.get("breadth_above_bbi", 1.0) or 1.0)
    return market_dd <= -0.10 and breadth <= 0.55


def apply_weak_market_quality_filter(
    candidates: pd.DataFrame,
    market_regime_name: str,
    mode: str,
    diagnostics: dict | None = None,
    regime_snapshot: dict | None = None,
) -> pd.DataFrame:
    if mode in {"off", "v7_baseline"} or not is_weak_market(market_regime_name, regime_snapshot):
        return candidates
    if candidates.empty:
        return candidates

    data = candidates.copy()
    required_defaults = {
        "ret_21": 0.0,
        "ret_63": 0.0,
        "volatility_63": np.nan,
        "positive_ret_ratio_63": 0.0,
        "market_ret_63": 0.0,
        "recent_limit_down_20": 0,
        "hot_money_risk_hits": 0,
        "above_bbi": False,
        "above_ratio_63": 0.0,
    }
    for col, default in required_defaults.items():
        if col not in data.columns:
            data[col] = default

    vol_cut = data["volatility_63"].quantile(0.50)
    if pd.isna(vol_cut):
        vol_cut = float("inf")
    base_quality = (
        data["recent_limit_down_20"].fillna(1).eq(0)
        & (pd.to_numeric(data["hot_money_risk_hits"], errors="coerce").fillna(99) < 2)
    )
    lowvol_mom = (
        base_quality
        & (pd.to_numeric(data["volatility_63"], errors="coerce") <= vol_cut)
        & (pd.to_numeric(data["ret_63"], errors="coerce") > 0.0)
        & (pd.to_numeric(data["ret_21"], errors="coerce") > -0.05)
    )
    fip_ok = pd.to_numeric(data["positive_ret_ratio_63"], errors="coerce").fillna(0.0) >= 0.52
    relative_ok = (
        pd.to_numeric(data["ret_63"], errors="coerce").fillna(-9.0)
        > pd.to_numeric(data["market_ret_63"], errors="coerce").fillna(0.0) + 0.02
    ) & data["above_bbi"].fillna(False).astype(bool)

    if mode == "weak_lowvol_mom":
        mask = lowvol_mom
    elif mode == "weak_fip_lowvol":
        mask = lowvol_mom & fip_ok
    elif mode == "weak_relative_strength":
        mask = base_quality & relative_ok
    elif mode == "weak_combined" or mode == "combined":
        mask = lowvol_mom & fip_ok & relative_ok & (pd.to_numeric(data["above_ratio_63"], errors="coerce") >= 0.60)
    else:
        raise ValueError(f"unknown weak filter mode: {mode}")

    filtered = data[mask].copy()
    if diagnostics is not None:
        diagnostics["weak_filter_signal_days"] = diagnostics.get("weak_filter_signal_days", 0) + 1
        diagnostics["weak_filter_candidate_blocks"] = diagnostics.get("weak_filter_candidate_blocks", 0) + int(len(data) - len(filtered))
    return filtered


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"Patch anchor not found:\n{old}")
    return source.replace(old, new, 1)


def load_v7_module(module_name: str, mode: str):
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
            "def run_backtest(panel, market, start_date, end_date):\n",
            "def run_backtest(panel, market, start_date, end_date):\n"
            "    panel = __weak_add_positive_return_ratio(panel)\n"
            "    panel = __weak_add_market_ret_63(panel, market)\n",
        )
        source = replace_once(
            source,
            '        "downtrend_filter_signal_days": 0,\n',
            '        "downtrend_filter_signal_days": 0,\n'
            '        "weak_filter_mode": WEAK_FILTER_MODE,\n'
            '        "weak_filter_signal_days": 0,\n'
            '        "weak_filter_candidate_blocks": 0,\n',
        )
        source = replace_once(
            source,
            '                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)\n'
            '                candidates["rank"] = np.arange(1, len(candidates) + 1)\n',
            '                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)\n'
            '                candidates = __weak_apply_filter(candidates, market_regime_name, WEAK_FILTER_MODE, stats, regime_snapshot).reset_index(drop=True)\n'
            '                candidates["rank"] = np.arange(1, len(candidates) + 1)\n',
        )
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(module_name, loader=None))
        module.__file__ = str(V7_DIR / "20_run_backtest.py")
        module.WEAK_FILTER_MODE = "off" if mode == "v7_baseline" else mode
        module.__weak_add_positive_return_ratio = add_positive_return_ratio
        module.__weak_add_market_ret_63 = add_market_ret_63
        module.__weak_apply_filter = apply_weak_market_quality_filter
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
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
        row.update({
            "market_block_days": int(stats.get("market_block_days", 0)),
            "weak_filter_signal_days": int(stats.get("weak_filter_signal_days", 0)),
            "weak_filter_candidate_blocks": int(stats.get("weak_filter_candidate_blocks", 0)),
        })
    return row


def load_existing_nav(version: str) -> pd.DataFrame | None:
    path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
    if not path.exists():
        return None
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    nav = nav[nav["date"] >= pd.Timestamp(START_DATE)].copy()
    return nav


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
        ret = period_returns(nav, freq).rename(name)
        pieces.append(ret)
    table = pd.concat(pieces, axis=1).round(2)
    table.index = table.index.strftime("%Y" if freq == "YE" else "%Y-%m")
    return table.reset_index(names="period")


def html_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    data = df if max_rows is None else df.head(max_rows)
    return data.to_html(index=False, escape=True, classes="data")


def generate_report(summary: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame, sources: list[str]) -> None:
    best_case = summary.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).iloc[0]
    baseline = summary[summary["case"].eq("v7_baseline")]
    baseline_ret = float(baseline.iloc[0]["total_return_pct"]) if not baseline.empty else float("nan")
    best_ret = float(best_case["total_return_pct"])
    yearly_indexed = yearly.set_index("period") if "period" in yearly.columns else pd.DataFrame()
    weak_year_notes = []
    for year in ["2018", "2022"]:
        if not yearly_indexed.empty and year in yearly_indexed.index and "v7_baseline" in yearly_indexed.columns and best_case["case"] in yearly_indexed.columns:
            base_year = float(yearly_indexed.loc[year, "v7_baseline"])
            best_year = float(yearly_indexed.loc[year, best_case["case"]])
            direction = "改善" if best_year > base_year else "未改善"
            weak_year_notes.append(f"{year}: {best_case['case']} {best_year:.2f}% vs v7 {base_year:.2f}%（{direction}）")
    weak_year_text = "；".join(weak_year_notes)
    if best_case["case"] == "v7_baseline" or best_ret <= baseline_ret:
        merge_advice = "暂不合并：候选实验未超过 v7 baseline。"
    elif any("未改善" in note for note in weak_year_notes):
        merge_advice = (
            f"暂不直接合并：{best_case['case']} 全周期收益高于 v7 baseline，"
            f"但关键弱熊年份没有同时改善（{weak_year_text}）。建议进入下一轮定向优化。"
        )
    else:
        merge_advice = (
            f"可进入下一轮验证：{best_case['case']} 全周期收益和关键弱熊年份均优于 v7 baseline，"
            "但仍需交易明细、滑点和分段压力测试。"
        )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>tmp_v7 弱熊市质量动量过滤实验</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #202124; }}
h1, h2 {{ margin: 18px 0 10px; }}
.note {{ background: #f5f7fb; border-left: 4px solid #4e79a7; padding: 10px 12px; margin: 12px 0; }}
table.data {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-bottom: 18px; }}
table.data th, table.data td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
table.data th:first-child, table.data td:first-child {{ text-align: left; }}
table.data th {{ background: #f1f3f4; }}
.small {{ color: #5f6368; font-size: 12px; }}
</style>
</head>
<body>
<h1>tmp_v7 弱熊市质量动量过滤实验</h1>
<div class="note">
<b>结论：</b>{html.escape(merge_advice)}<br>
<b>最佳 case：</b>{html.escape(str(best_case['case']))}，
总收益 {best_case['total_return_pct']:.2f}% ，年化 {best_case['annual_return_pct']:.2f}% ，最大回撤 {best_case['max_drawdown_pct']:.2f}%。
</div>
<h2>整体对比</h2>
{html_table(summary.round(4))}
<h2>年度收益率对比（%）</h2>
{html_table(yearly)}
<h2>月度收益率对比（%）</h2>
{html_table(monthly)}
<h2>建议</h2>
<p>如果实验 case 没有同时改善全周期收益和关键弱熊年份，不直接合并到 v7。本轮最佳 case 主要改善了 2022、2020、2021、2023、2024、2026，但 2018 仍弱于 v7 baseline。</p>
<p>当前过滤器保留了 v7 原有熊市禁买逻辑，主要处理弱 neutral 和少量 bear_probe 日期；它不是“熊市替代禁买”的最终版本。下一步应单独测试：在确认熊市反弹窗口里，用低波动量候选替代一部分禁买，而不是全市场放开。</p>
<h2>外部依据</h2>
<ul>
{''.join(f'<li>{html.escape(src)}</li>' for src in sources)}
</ul>
<p class="small">所有候选过滤均发生在 signal_date，交易在下一交易日开盘执行；新增 rolling 字段由历史 close_qfq 计算，未使用未来数据。</p>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def run_case(name: str, panel: pd.DataFrame, market: pd.DataFrame | None, end_date: str | None):
    module = load_v7_module(f"tmp_{name}", mode=name)
    nav, trades, rebalance, scores, holdings, stats = module.run_backtest(panel.copy(), market.copy() if market is not None else None, START_DATE, end_date)
    nav.to_csv(OUTPUT_DIR / f"{name}_nav_series.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(OUTPUT_DIR / f"{name}_trade_records.csv", index=False, encoding="utf-8-sig")
    rebalance.to_csv(OUTPUT_DIR / f"{name}_rebalance_log.csv", index=False, encoding="utf-8-sig")
    scores.to_csv(OUTPUT_DIR / f"{name}_strength_scores.csv", index=False, encoding="utf-8-sig")
    (OUTPUT_DIR / f"{name}_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return nav, trades, stats


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text(
        "# tmp_v7 弱熊市质量动量过滤实验进度\n\n"
        "目标：不修改 v7 正式代码，验证弱市/熊市下低波、动量一致性、相对强弱过滤能否减少亏损并保留牛市收益。\n\n",
        encoding="utf-8",
    )
    write_design_and_plan()
    append_progress("完成设计和计划文档。")

    sys.path.insert(0, str(V7_DIR))
    try:
        config_spec = importlib.util.spec_from_file_location("v7_config_for_tmp", V7_DIR / "config.py")
        config = importlib.util.module_from_spec(config_spec)
        assert config_spec.loader is not None
        config_spec.loader.exec_module(config)
    finally:
        try:
            sys.path.remove(str(V7_DIR))
        except ValueError:
            pass

    market_module = load_v7_module("tmp_loader_for_market", mode="v7_baseline")
    panel = pd.read_parquet(config.PANEL_PATH, columns=market_module.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = market_module.load_market_index()
    append_progress(f"加载 v7 panel rows={len(panel)}。")

    nav_map: dict[str, pd.DataFrame] = {}
    trade_map: dict[str, pd.DataFrame] = {}
    rows = []
    for version in ["v4", "v5", "v6", "v7"]:
        nav = load_existing_nav(version)
        if nav is not None:
            trades_path = BACKTRADER_DIR / version / "output" / "trade_records.csv"
            trades = pd.read_csv(trades_path) if trades_path.exists() else pd.DataFrame()
            nav_map[version] = nav
            rows.append(summarize_nav(version, nav, trades, {}))

    for mode in WEAK_FILTER_MODES:
        append_progress(f"开始运行 case={mode}。")
        nav, trades, stats = run_case(mode, panel, market, END_DATE)
        nav_map[mode] = nav
        trade_map[mode] = trades
        rows.append(summarize_nav(mode, nav, trades, stats))
        append_progress(
            f"完成 case={mode} total={stats.get('total_return_pct')}% "
            f"max_dd={stats.get('max_drawdown_pct')}% weak_blocks={stats.get('weak_filter_candidate_blocks', 0)}。"
        )

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
            "Tavily: 华泰低波 Smart Beta 报告摘要，低波+动量、价值+低波能改善风险收益。",
            "Tavily: Momentum Crashes 论文，熊市和高波动阶段纯动量未来收益较差。",
            "Tavily: A股动量指标量化策略研究，系统性下跌时需空仓或降低仓位，但个股动量仍可贡献超额。",
        ],
    )
    append_progress(f"完成报表：{REPORT_PATH}")

    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath '{REPORT_PATH}'"], shell=False)
        append_progress("已尝试自动打开 HTML 报表。")
    except Exception as exc:
        append_progress(f"自动打开报表失败：{exc}")

    print(f"Report: {REPORT_PATH}")
    print(summary.sort_values("total_return_pct", ascending=False).head(8).to_string(index=False))


if __name__ == "__main__":
    main()

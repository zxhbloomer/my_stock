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
V7_DIR = BACKTRADER_DIR / "v7"
PREV_PATH = TMP_DIR / "tmp_v7_weak_market_quality_momentum_experiment.py"

OUTPUT_DIR = TMP_DIR / "tmp_v7_bear_probe_lowvol_mom_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_bear_probe_lowvol_mom_README.md"
DESIGN_PATH = TMP_DIR / "tmp_v7_bear_probe_lowvol_mom_design.md"
PLAN_PATH = TMP_DIR / "tmp_v7_bear_probe_lowvol_mom_plan.md"

START_DATE = "2018-01-01"
END_DATE = None
CASES = [
    "v7_baseline",
    "weak_lowvol_mom",
    "probe_05_strict",
    "probe_10_strict",
    "probe_15_strict",
    "probe_10_ultra",
]


def load_prev_module():
    spec = importlib.util.spec_from_file_location("prev_weak_lowvol_mom", PREV_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PREV = load_prev_module()


def append_progress(message: str) -> None:
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def write_design_and_plan() -> None:
    DESIGN_PATH.write_text(
        """# tmp_v7 熊市反弹低波动量小仓位试探实验设计

## 目标
保留上一轮 `weak_lowvol_mom` 的全周期优势，同时专门优化 2018。实验只在 v7 已确认的熊市反弹窗口中做小仓位试探，不放开普通熊市禁买。

## 外部依据
- Tavily 复核：熊市反弹很常见，但实时区分真假反弹很难，因此不能全仓押注。
- Tavily 复核：熊市持续修复通常需要估值、情绪、政策、宏观恶化放缓等多因素配合；本地只有价格和宽度时，应采用小仓位试探。
- Momentum Crashes 研究提示熊市高波动阶段纯动量风险高，所以试探候选必须叠加低波和趋势质量过滤。

## 方案
- 非熊市：沿用 `weak_lowvol_mom`。
- 熊市：保留 v7 的 `bear_probe_market_ok` 作为必要条件。
- 试探窗口中进一步要求市场宽度和宽度改善强于 v7 默认。
- 候选要求低波、正 21/63 日动量、FIP 一致性、无近期跌停、无高游资风险。
- 测试 5%、10%、15% 三档小仓位，以及一个更严格的 10% ultra 版本。

## 设计 review
- 量化研究员：不改变牛市逻辑，先围绕 2018 做局部试探，符合收益目标。
- 风控专家：熊市反弹真假难判，必须小仓位并要求确认信号。
- 数据工程师：只用已有 panel 和 market_index，新增指标均为历史滚动，不引入财务公告日前视风险。
""",
        encoding="utf-8",
    )
    PLAN_PATH.write_text(
        """# tmp_v7 Bear Probe Lowvol Momentum Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 本计划不操作 git。

**Goal:** 测试 v7 熊市反弹确认窗口中的低波动量小仓位试探，争取改善 2018 且保留全周期收益。

**Architecture:** 动态加载 v7，不改正式 v7；复用上一轮 weak_lowvol_mom 过滤；额外注入 refined bear probe 开关、候选过滤和仓位 cap。

**Tech Stack:** Python, pandas, local v7 backtest outputs.

---

### Task 1: 测试
- [x] 写 `test_tmp_v7_bear_probe_lowvol_mom.py`。
- [x] 验证 RED：模块不存在时失败。

### Task 2: 实现
- [x] 新增实验脚本。
- [x] 实现 refined probe open、target amount、candidate filter。
- [x] 注入 v7 run_backtest。

### Task 3: 验证
- [ ] 跑测试和 py_compile。
- [ ] 跑全周期回测。
- [ ] 生成 HTML 报表。
- [ ] 做 QA review 和合并建议。
""",
        encoding="utf-8",
    )


def probe_fraction(mode: str) -> float:
    if mode == "probe_05_strict":
        return 0.05
    if mode in {"probe_10_strict", "probe_10_ultra"}:
        return 0.10
    if mode == "probe_15_strict":
        return 0.15
    return 0.15


def refined_bear_probe_open(market_regime_name: str, regime_snapshot: dict | None, mode: str) -> bool:
    if mode in {"v7_baseline", "weak_lowvol_mom"}:
        return bool(regime_snapshot and regime_snapshot.get("bear_probe_market_ok", False))
    if market_regime_name != "bear" or not regime_snapshot:
        return False
    if not bool(regime_snapshot.get("bear_probe_market_ok", False)):
        return False
    breadth = float(regime_snapshot.get("breadth_above_bbi", 0.0) or 0.0)
    breadth_change = float(regime_snapshot.get("breadth_change_5", 0.0) or 0.0)
    if mode == "probe_10_ultra":
        return breadth >= 0.45 and breadth_change >= 0.12
    return breadth >= 0.40 and breadth_change >= 0.10


def refined_probe_target_amount(normal_first_step: float, cash: float, current_probe_exposure: float, mode: str, init_cash: float) -> float:
    fraction = probe_fraction(mode)
    max_total = float(init_cash) * fraction
    available = max(0.0, max_total - float(current_probe_exposure))
    target = float(normal_first_step) * fraction
    return max(0.0, min(target, float(cash), available))


def apply_refined_probe_candidate_filter(candidates: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode in {"v7_baseline", "weak_lowvol_mom"} or candidates.empty:
        return candidates
    data = candidates.copy()
    for col, default in {
        "ret_21": 0.0,
        "ret_63": 0.0,
        "volatility_63": np.nan,
        "positive_ret_ratio_63": 0.0,
        "recent_limit_down_20": 0,
        "hot_money_risk_hits": 0,
        "above_bbi": False,
        "above_ratio_63": 0.0,
    }.items():
        if col not in data.columns:
            data[col] = default
    vol_q = 0.40 if mode != "probe_10_ultra" else 0.30
    vol_cut = pd.to_numeric(data["volatility_63"], errors="coerce").quantile(vol_q)
    if pd.isna(vol_cut):
        vol_cut = float("inf")
    fip_min = 0.54 if mode != "probe_10_ultra" else 0.56
    above_min = 0.62 if mode != "probe_10_ultra" else 0.68
    mask = (
        pd.to_numeric(data["volatility_63"], errors="coerce").le(vol_cut)
        & pd.to_numeric(data["ret_21"], errors="coerce").gt(0.0)
        & pd.to_numeric(data["ret_63"], errors="coerce").gt(0.0)
        & pd.to_numeric(data["positive_ret_ratio_63"], errors="coerce").ge(fip_min)
        & pd.to_numeric(data["above_ratio_63"], errors="coerce").ge(above_min)
        & data["above_bbi"].fillna(False).astype(bool)
        & data["recent_limit_down_20"].fillna(1).eq(0)
        & pd.to_numeric(data["hot_money_risk_hits"], errors="coerce").fillna(99).lt(2)
    )
    return data[mask].copy()


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"Patch anchor not found:\n{old}")
    return source.replace(old, new, 1)


def load_v7_module(module_name: str, case: str):
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
            '        "bear_probe_lowvol_case": BEAR_PROBE_LOWVOL_CASE,\n'
            '        "weak_filter_signal_days": 0,\n'
            '        "weak_filter_candidate_blocks": 0,\n'
            '        "refined_probe_raw_signal_days": 0,\n'
            '        "refined_probe_open_days": 0,\n'
            '        "refined_probe_block_days": 0,\n',
        )
        source = replace_once(
            source,
            """            probe_open = (
                BEAR_PROBE_BUY_ENABLED
                and regime_blocked
                and not short_drop_blocked
                and bool(regime_snapshot.get("bear_probe_market_ok", False))
            )
""",
            """            raw_probe_open = (
                BEAR_PROBE_BUY_ENABLED
                and regime_blocked
                and not short_drop_blocked
                and bool(regime_snapshot.get("bear_probe_market_ok", False))
            )
            if raw_probe_open:
                stats["refined_probe_raw_signal_days"] += 1
            probe_open = raw_probe_open and __refined_bear_probe_open(market_regime_name, regime_snapshot, BEAR_PROBE_LOWVOL_CASE)
            if probe_open:
                stats["refined_probe_open_days"] += 1
            elif raw_probe_open:
                stats["refined_probe_block_days"] += 1
""",
        )
        source = replace_once(
            source,
            '                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)\n'
            '                candidates["rank"] = np.arange(1, len(candidates) + 1)\n',
            '                candidates = score_candidates(signal_panel, diagnostics=stats).reset_index(drop=True)\n'
            '                candidates = __weak_apply_filter(candidates, market_regime_name, WEAK_FILTER_MODE, stats, regime_snapshot).reset_index(drop=True)\n'
            '                candidates["rank"] = np.arange(1, len(candidates) + 1)\n',
        )
        source = replace_once(
            source,
            """                if probe_open:
                    stats["bear_probe_signal_days"] += 1
                    candidates = candidates[candidates["bear_probe_stock_ok"].fillna(False)].copy()
                    pullback_threshold = min(pullback_threshold, -0.02)
                    strong_pullback_threshold = min(strong_pullback_threshold, -0.015)
""",
            """                if probe_open:
                    stats["bear_probe_signal_days"] += 1
                    candidates = candidates[candidates["bear_probe_stock_ok"].fillna(False)].copy()
                    candidates = __refined_probe_candidate_filter(candidates, BEAR_PROBE_LOWVOL_CASE)
                    pullback_threshold = min(pullback_threshold, -0.02)
                    strong_pullback_threshold = min(strong_pullback_threshold, -0.015)
""",
        )
        source = replace_once(
            source,
            """                        target_amount = calc_bear_probe_target_amount(
                            float(LONG_POSITION_STEPS[0]),
                            cash,
                            calc_bear_probe_exposure(holdings),
                        )
""",
            """                        target_amount = __refined_probe_target_amount(
                            float(LONG_POSITION_STEPS[0]),
                            cash,
                            calc_bear_probe_exposure(holdings),
                            BEAR_PROBE_LOWVOL_CASE,
                            INIT_CASH,
                        )
""",
        )
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(module_name, loader=None))
        module.__file__ = str(V7_DIR / "20_run_backtest.py")
        module.BEAR_PROBE_LOWVOL_CASE = case
        module.WEAK_FILTER_MODE = "off" if case == "v7_baseline" else "weak_lowvol_mom"
        module.__weak_add_positive_return_ratio = PREV.add_positive_return_ratio
        module.__weak_add_market_ret_63 = PREV.add_market_ret_63
        module.__weak_apply_filter = PREV.apply_weak_market_quality_filter
        module.__refined_bear_probe_open = refined_bear_probe_open
        module.__refined_probe_target_amount = refined_probe_target_amount
        module.__refined_probe_candidate_filter = apply_refined_probe_candidate_filter
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


def run_case(case: str, panel: pd.DataFrame, market: pd.DataFrame | None):
    module = load_v7_module(f"tmp_bear_probe_{case}", case)
    nav, trades, rebalance, scores, holdings, stats = module.run_backtest(panel.copy(), market.copy() if market is not None else None, START_DATE, END_DATE)
    nav.to_csv(OUTPUT_DIR / f"{case}_nav_series.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(OUTPUT_DIR / f"{case}_trade_records.csv", index=False, encoding="utf-8-sig")
    rebalance.to_csv(OUTPUT_DIR / f"{case}_rebalance_log.csv", index=False, encoding="utf-8-sig")
    scores.to_csv(OUTPUT_DIR / f"{case}_strength_scores.csv", index=False, encoding="utf-8-sig")
    (OUTPUT_DIR / f"{case}_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return nav, trades, stats


def load_existing_nav(version: str) -> pd.DataFrame | None:
    path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
    if not path.exists():
        return None
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    return nav[nav["date"] >= pd.Timestamp(START_DATE)].copy()


def make_summary_row(name: str, nav: pd.DataFrame, trades: pd.DataFrame, stats: dict | None = None) -> dict:
    row = PREV.summarize_nav(name, nav, trades, stats or {})
    if stats:
        row.update({
            "refined_probe_raw_signal_days": int(stats.get("refined_probe_raw_signal_days", 0)),
            "refined_probe_open_days": int(stats.get("refined_probe_open_days", 0)),
            "refined_probe_block_days": int(stats.get("refined_probe_block_days", 0)),
            "bear_probe_buys": int(stats.get("bear_probe_buys", 0)),
        })
    return row


def html_table(df: pd.DataFrame) -> str:
    return df.to_html(index=False, escape=True, classes="data")


def generate_report(summary: pd.DataFrame, yearly: pd.DataFrame, monthly: pd.DataFrame) -> None:
    baseline = summary[summary["case"].eq("v7_baseline")].iloc[0]
    weak = summary[summary["case"].eq("weak_lowvol_mom")].iloc[0]
    best = summary.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).iloc[0]
    probe_summary = summary[summary["case"].astype(str).str.startswith("probe_")].copy()
    best_probe = probe_summary.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).iloc[0]
    y = yearly.copy()
    y["period"] = y["period"].astype(str)
    y = y.set_index("period")
    def yr(case: str, year: str) -> float:
        return float(y.loc[year, case]) if year in y.index and case in y.columns else float("nan")
    advice = "暂不合并：probe 组没有产生有效增量，继续保留 weak_lowvol_mom 为候选核心。"
    if float(best_probe["total_return_pct"]) >= float(weak["total_return_pct"]) and yr(str(best_probe["case"]), "2018") > yr("v7_baseline", "2018"):
        advice = "probe 组可进入下一轮候选：全周期不弱于 weak_lowvol_mom，且 2018 优于 v7 baseline。"
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>tmp_v7 熊市反弹低波动量试探实验</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #202124; }}
.note {{ background:#f5f7fb; border-left:4px solid #4e79a7; padding:10px 12px; margin:12px 0; }}
table.data {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-bottom: 18px; }}
table.data th, table.data td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
table.data th:first-child, table.data td:first-child {{ text-align: left; }}
table.data th {{ background:#f1f3f4; }}
</style>
</head>
<body>
<h1>tmp_v7 熊市反弹低波动量小仓位试探</h1>
<div class="note">
<b>结论：</b>{html.escape(advice)}<br>
<b>v7 baseline：</b>总收益 {baseline['total_return_pct']:.2f}%，2018 {yr('v7_baseline','2018'):.2f}%<br>
<b>weak_lowvol_mom：</b>总收益 {weak['total_return_pct']:.2f}%，2018 {yr('weak_lowvol_mom','2018'):.2f}%<br>
<b>全表最佳：</b>{html.escape(str(best['case']))}，总收益 {best['total_return_pct']:.2f}%，2018 {yr(str(best['case']),'2018'):.2f}%<br>
<b>probe 组最佳：</b>{html.escape(str(best_probe['case']))}，总收益 {best_probe['total_return_pct']:.2f}%，2018 {yr(str(best_probe['case']),'2018'):.2f}%，实际试探买入 {int(best_probe.get('bear_probe_buys', 0))} 次
</div>
<h2>整体对比</h2>
{html_table(summary.round(4))}
<h2>年度收益率（%）</h2>
{html_table(yearly)}
<h2>2018 与 2022 月度收益率（%）</h2>
{html_table(monthly[monthly['period'].str.startswith(('2018-', '2022-'))])}
<h2>建议</h2>
<p>本轮只测试 v7 已确认熊市反弹窗口里的小仓位试探，不放开普通熊市禁买。如果没有同时满足“全周期不低于 268.83%”和“2018 优于 v7”，不合并。</p>
<p>下一步若本轮失败，应把 2018 改善目标从“增加试探”转为“更早退出或更少持有 2018 上半年高风险仓位”。</p>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text(
        "# tmp_v7 熊市反弹低波动量小仓位试探实验进度\n\n"
        "目标：保留 weak_lowvol_mom 全周期优势，并专门测试 2018 熊市反弹窗口小仓位试探。\n\n",
        encoding="utf-8",
    )
    write_design_and_plan()
    append_progress("完成设计和计划文档。")

    loader = load_v7_module("tmp_bear_probe_loader", "v7_baseline")
    config = sys.modules.get("config")
    if config is None:
        config_spec = importlib.util.spec_from_file_location("config", V7_DIR / "config.py")
        config = importlib.util.module_from_spec(config_spec)
        assert config_spec.loader is not None
        config_spec.loader.exec_module(config)
    panel = pd.read_parquet(config.PANEL_PATH, columns=loader.PANEL_COLUMNS)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = loader.load_market_index()
    append_progress(f"加载 v7 panel rows={len(panel)}。")

    nav_map: dict[str, pd.DataFrame] = {}
    rows = []
    for version in ["v4", "v5", "v6", "v7"]:
        nav = load_existing_nav(version)
        if nav is not None:
            trades_path = BACKTRADER_DIR / version / "output" / "trade_records.csv"
            trades = pd.read_csv(trades_path) if trades_path.exists() else pd.DataFrame()
            nav_map[version] = nav
            rows.append(make_summary_row(version, nav, trades, {}))

    for case in CASES:
        append_progress(f"开始运行 case={case}。")
        nav, trades, stats = run_case(case, panel, market)
        nav_map[case] = nav
        rows.append(make_summary_row(case, nav, trades, stats))
        append_progress(
            f"完成 case={case} total={stats.get('total_return_pct')}% "
            f"max_dd={stats.get('max_drawdown_pct')}% probe_buys={stats.get('bear_probe_buys')}。"
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(OUTPUT_DIR / "summary_compare.csv", index=False, encoding="utf-8-sig")
    yearly = PREV.make_return_table(nav_map, "YE")
    monthly = PREV.make_return_table(nav_map, "ME")
    yearly.to_csv(OUTPUT_DIR / "yearly_returns.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "monthly_returns.csv", index=False, encoding="utf-8-sig")
    generate_report(summary, yearly, monthly)
    append_progress(f"完成报表：{REPORT_PATH}")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath '{REPORT_PATH}'"], shell=False)
        append_progress("已尝试自动打开 HTML 报表。")
    except Exception as exc:
        append_progress(f"自动打开报表失败：{exc}")
    print(f"Report: {REPORT_PATH}")
    print(summary.sort_values("total_return_pct", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()

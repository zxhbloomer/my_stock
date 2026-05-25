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

OUTPUT_DIR = TMP_DIR / "tmp_v7_bull_downgrade_exposure_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_bull_downgrade_exposure_README.md"

START_DATE = "2018-01-01"
END_DATE = None

BASE_MAX_HOLDINGS = 5
BASE_TOTAL_EXPOSURE = 500_000.0

CASES = [
    {
        "case": "当前v7复现",
        "mode": "baseline",
        "bull_max_holdings": BASE_MAX_HOLDINGS,
        "bull_exposure_ratio": None,
        "bull_max_single_ratio": None,
        "winner_add_multiplier": 1.0,
    },
    {
        "case": "严格牛市扩仓8_降级减仓",
        "mode": "strict_extension",
        "bull_max_holdings": 8,
        "bull_exposure_ratio": 0.60,
        "bull_max_single_ratio": 0.18,
        "winner_add_multiplier": 1.0,
    },
    {
        "case": "严格牛市扩仓10_降级减仓",
        "mode": "strict_extension",
        "bull_max_holdings": 10,
        "bull_exposure_ratio": 0.70,
        "bull_max_single_ratio": 0.16,
        "winner_add_multiplier": 1.0,
    },
    {
        "case": "核心赢家加预算70_降级回归",
        "mode": "winner_budget",
        "bull_max_holdings": BASE_MAX_HOLDINGS,
        "bull_exposure_ratio": 0.70,
        "bull_max_single_ratio": 0.25,
        "winner_add_multiplier": 1.6,
    },
    {
        "case": "核心赢家加预算60_降级回归",
        "mode": "winner_budget",
        "bull_max_holdings": BASE_MAX_HOLDINGS,
        "bull_exposure_ratio": 0.60,
        "bull_max_single_ratio": 0.22,
        "winner_add_multiplier": 1.35,
    },
]


def append_progress(message):
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def replace_once(source, old, new):
    if old not in source:
        raise RuntimeError(f"patch anchor not found: {old[:120]}")
    return source.replace(old, new, 1)


def is_strict_extension_case(case):
    return case.get("mode") == "strict_extension"


def is_winner_budget_case(case):
    return case.get("mode") == "winner_budget"


def max_holdings_for_regime(market_regime_name, case):
    if market_regime_name == "bull" and is_strict_extension_case(case):
        return int(case.get("bull_max_holdings") or BASE_MAX_HOLDINGS)
    return BASE_MAX_HOLDINGS


def total_exposure_limit(market_regime_name, case, nav):
    if market_regime_name != "bull" or case.get("mode") == "baseline":
        return BASE_TOTAL_EXPOSURE
    ratio = float(case.get("bull_exposure_ratio") or 0.0)
    if ratio <= 0:
        return BASE_TOTAL_EXPOSURE
    return max(BASE_TOTAL_EXPOSURE, float(nav) * ratio)


def single_position_limit(market_regime_name, case, nav):
    if market_regime_name != "bull" or case.get("mode") == "baseline":
        return BASE_TOTAL_EXPOSURE
    ratio = float(case.get("bull_max_single_ratio") or 0.0)
    if ratio <= 0:
        return BASE_TOTAL_EXPOSURE
    return float(nav) * ratio


def cap_entry_amount(requested_amount, market_regime_name, case, nav, cash, current_total_exposure):
    if not is_strict_extension_case(case):
        remaining = BASE_TOTAL_EXPOSURE - float(current_total_exposure)
        return max(0.0, min(float(requested_amount), remaining))
    remaining = total_exposure_limit(market_regime_name, case, nav) - float(current_total_exposure)
    return max(0.0, min(float(requested_amount), float(cash), remaining))


def cap_winner_extra_amount(
    requested_amount,
    market_regime_name,
    case,
    nav,
    cash,
    current_total_exposure,
    current_position_exposure,
):
    if not is_winner_budget_case(case) or market_regime_name != "bull":
        return 0.0
    total_remaining = total_exposure_limit(market_regime_name, case, nav) - float(current_total_exposure)
    single_remaining = single_position_limit(market_regime_name, case, nav) - float(current_position_exposure)
    return max(0.0, min(float(requested_amount), float(cash), total_remaining, single_remaining))


def select_downgrade_full_exit_codes(holdings, market_regime_name, max_holdings):
    if market_regime_name == "bull":
        return []
    rows = []
    for code, pos in holdings.items():
        tag = pos.get("tag", "core")
        is_extension = tag == "bull_extension"
        rank = int(pos.get("rank", 9999) or 9999)
        invested = float(pos.get("invested_amount", 0.0) or 0.0)
        rows.append((code, is_extension, rank, invested))
    rows.sort(key=lambda item: (item[1], item[2], -item[3]), reverse=True)
    if market_regime_name == "bear":
        return [code for code, is_extension, _, _ in rows if is_extension]
    excess = max(0, len(holdings) - int(max_holdings))
    return [code for code, _, _, _ in rows[:excess]]


def calc_extra_trim_order(pos, open_price):
    extra = float(pos.get("bull_extra_amount", 0.0) or 0.0)
    price = float(open_price or 0.0)
    if extra <= 0 or price <= 0:
        return 0, 0.0
    shares = int(extra / price / 100) * 100
    shares = min(int(pos.get("shares", 0) or 0), shares)
    if shares < 100:
        return 0, 0.0
    return shares, shares * price


def load_v7_backtest_module(module_name, case):
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
            '        "bull_downgrade_case": BULL_DOWNGRADE_CASE.get("case", "baseline"),\n'
            '        "bull_extension_buys": 0,\n'
            '        "bull_downgrade_full_exit_signals": 0,\n'
            '        "bull_downgrade_full_exit_fills": 0,\n'
            '        "winner_extra_buys": 0,\n'
            '        "winner_extra_trim_signals": 0,\n'
            '        "winner_extra_trim_fills": 0,\n',
        )
        source = replace_once(
            source,
            "            exit_reasons = {}\n",
            "            if __should_trim_winner_extra(market_regime_name):\n"
            "                for trim_code in list(holdings):\n"
            "                    if trim_code not in day_panel.index or holdings[trim_code].get(\"pending_sell\"):\n"
            "                        continue\n"
            "                    cash, trimmed, trim_reason = __execute_extra_trim(\n"
            "                        date, trim_code, holdings[trim_code], day_panel, cash, trades\n"
            "                    )\n"
            "                    if trimmed:\n"
            "                        stats[\"winner_extra_trim_fills\"] += 1\n"
            "                    elif trim_reason:\n"
            "                        stats[\"sell_delays\"] += 1\n"
            "            exit_reasons = {}\n"
            "            for downgrade_code in __select_downgrade_full_exit_codes(holdings, market_regime_name):\n"
            "                if downgrade_code in day_panel.index and not holdings[downgrade_code].get(\"pending_sell\"):\n"
            "                    exit_reasons[downgrade_code] = \"bull_downgrade_full_exit\"\n"
            "                    stats[\"bull_downgrade_full_exit_signals\"] += 1\n",
        )
        source = replace_once(
            source,
            "                    if exit_reason == \"long_stop_loss\":\n"
            "                        stats[\"stop_loss_fills\"] += 1\n"
            "                    elif exit_reason == \"long_limit_down_exit\":\n",
            "                    if exit_reason == \"bull_downgrade_full_exit\":\n"
            "                        stats[\"bull_downgrade_full_exit_fills\"] += 1\n"
            "                    elif exit_reason == \"long_stop_loss\":\n"
            "                        stats[\"stop_loss_fills\"] += 1\n"
            "                    elif exit_reason == \"long_limit_down_exit\":\n",
        )
        source = replace_once(
            source,
            "                        available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n"
            "                        target_amount = min(target_amount, available_exposure)\n",
            "                        base_target_amount = target_amount\n"
            "                        if __is_winner_budget_case(market_regime_name):\n"
            "                            current_nav = __calc_current_nav(cash, holdings, signal_panel)\n"
            "                            current_position_exposure = float(pos.get(\"invested_amount\", calc_position_cost(pos)))\n"
            "                            requested_extra_amount = float(base_target_amount) * __winner_add_multiplier()\n"
            "                            target_amount = __cap_winner_extra_amount(\n"
            "                                requested_extra_amount,\n"
            "                                market_regime_name,\n"
            "                                current_nav,\n"
            "                                cash,\n"
            "                                calc_total_exposure(holdings),\n"
            "                                current_position_exposure,\n"
            "                            )\n"
            "                        else:\n"
            "                            available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n"
            "                            target_amount = min(target_amount, available_exposure)\n",
        )
        source = replace_once(
            source,
            "                        cash, bought, reason = execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, \"long_add_buy\")\n"
            "                        if bought:\n",
            "                        before_invested = float(pos.get(\"invested_amount\", calc_position_cost(pos)))\n"
            "                        cash, bought, reason = execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, \"long_add_buy\")\n"
            "                        if bought and __is_winner_budget_case(market_regime_name):\n"
            "                            after_invested = float(holdings[code].get(\"invested_amount\", calc_position_cost(holdings[code])))\n"
            "                            extra_amount = max(0.0, after_invested - before_invested - float(base_target_amount))\n"
            "                            holdings[code][\"tag\"] = \"core\"\n"
            "                            holdings[code][\"bull_extra_amount\"] = float(holdings[code].get(\"bull_extra_amount\", 0.0)) + extra_amount\n"
            "                            stats[\"winner_extra_buys\"] += 1\n"
            "                        if bought:\n",
        )
        source = replace_once(
            source,
            "                    if len(holdings) >= LONG_MAX_HOLDINGS:\n",
            "                    if len(holdings) >= __max_holdings_for_regime(market_regime_name):\n",
        )
        source = replace_once(
            source,
            "                    available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n"
            "                    if probe_open:\n"
            "                        target_amount = calc_bear_probe_target_amount(\n"
            "                            float(LONG_POSITION_STEPS[0]),\n"
            "                            cash,\n"
            "                            calc_bear_probe_exposure(holdings),\n"
            "                        )\n"
            "                    else:\n"
            "                        target_amount = min(float(LONG_POSITION_STEPS[0]), available_exposure)\n"
            "                    target_amount = min(target_amount, available_exposure)\n",
            "                    extension_entry = __is_extension_entry(market_regime_name, holdings)\n"
            "                    current_nav = __calc_current_nav(cash, holdings, signal_panel)\n"
            "                    if probe_open:\n"
            "                        target_amount = calc_bear_probe_target_amount(\n"
            "                            float(LONG_POSITION_STEPS[0]),\n"
            "                            cash,\n"
            "                            calc_bear_probe_exposure(holdings),\n"
            "                        )\n"
            "                    else:\n"
            "                        target_amount = __cap_entry_amount(\n"
            "                            float(LONG_POSITION_STEPS[0]),\n"
            "                            market_regime_name,\n"
            "                            current_nav,\n"
            "                            cash,\n"
            "                            calc_total_exposure(holdings),\n"
            "                        )\n",
        )
        source = replace_once(
            source,
            "                    cash, bought, reason = execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, buy_reason)\n"
            "                    if bought:\n",
            "                    cash, bought, reason = execute_buy(date, day_panel.loc[code], target_amount, cash, holdings, trades, buy_reason)\n"
            "                    if bought and code in holdings:\n"
            "                        holdings[code][\"rank\"] = int(candidate_by_code.loc[code].get(\"rank\", 9999)) if code in candidate_by_code.index else 9999\n"
            "                        if extension_entry:\n"
            "                            holdings[code][\"tag\"] = \"bull_extension\"\n"
            "                            stats[\"bull_extension_buys\"] += 1\n"
            "                        else:\n"
            "                            holdings[code].setdefault(\"tag\", \"core\")\n"
            "                    if bought:\n",
        )

        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.BULL_DOWNGRADE_CASE = dict(case)

        def _calc_current_nav(cash, holdings, day_panel):
            return float(cash) + sum(module.mark_position(c, p, day_panel) for c, p in holdings.items())

        def _max_holdings_for_regime(market_regime_name):
            return max_holdings_for_regime(market_regime_name, module.BULL_DOWNGRADE_CASE)

        def _is_winner_budget_case(market_regime_name):
            return is_winner_budget_case(module.BULL_DOWNGRADE_CASE) and market_regime_name == "bull"

        def _winner_add_multiplier():
            return float(module.BULL_DOWNGRADE_CASE.get("winner_add_multiplier") or 1.0)

        def _cap_winner_extra_amount(
            requested_amount,
            market_regime_name,
            nav,
            cash,
            current_total_exposure,
            current_position_exposure,
        ):
            return cap_winner_extra_amount(
                requested_amount,
                market_regime_name,
                module.BULL_DOWNGRADE_CASE,
                nav,
                cash,
                current_total_exposure,
                current_position_exposure,
            )

        def _cap_entry_amount(requested_amount, market_regime_name, nav, cash, current_total_exposure):
            return cap_entry_amount(
                requested_amount,
                market_regime_name,
                module.BULL_DOWNGRADE_CASE,
                nav,
                cash,
                current_total_exposure,
            )

        def _is_extension_entry(market_regime_name, holdings):
            return (
                is_strict_extension_case(module.BULL_DOWNGRADE_CASE)
                and market_regime_name == "bull"
                and len(holdings) >= BASE_MAX_HOLDINGS
            )

        def _select_downgrade_full_exit_codes(holdings, market_regime_name):
            return select_downgrade_full_exit_codes(holdings, market_regime_name, BASE_MAX_HOLDINGS)

        def _should_trim_winner_extra(market_regime_name):
            return is_winner_budget_case(module.BULL_DOWNGRADE_CASE) and market_regime_name != "bull"

        def _execute_extra_trim(date, code, pos, day_panel, cash, trades):
            if float(pos.get("bull_extra_amount", 0.0) or 0.0) <= 0:
                return cash, False, ""
            if code not in day_panel.index:
                return cash, False, "missing_row"
            row = day_panel.loc[code]
            ok, skip_reason = module.can_sell(row)
            if not ok:
                return cash, False, skip_reason
            price = module.get_open_price(row)
            shares, amount = calc_extra_trim_order(pos, price)
            if shares < 100:
                pos["bull_extra_amount"] = 0.0
                return cash, False, ""
            comm = module.calc_commission(amount, is_buy=False)
            old_shares = float(pos["shares"])
            ratio = shares / old_shares if old_shares > 0 else 0.0
            buy_comm_removed = float(pos.get("buy_comm", 0.0) or 0.0) * ratio
            pnl = (price - float(pos["cost_price"])) * shares - buy_comm_removed - comm
            pnl_pct = pnl / max(float(pos["cost_price"]) * shares + buy_comm_removed, 1.0) * 100.0
            cash += amount - comm
            pos["shares"] = old_shares - shares
            pos["buy_comm"] = max(0.0, float(pos.get("buy_comm", 0.0) or 0.0) - buy_comm_removed)
            pos["invested_amount"] = max(
                0.0,
                float(pos.get("invested_amount", 0.0) or 0.0)
                - (float(pos["cost_price"]) * shares + buy_comm_removed),
            )
            pos["bull_extra_amount"] = max(0.0, float(pos.get("bull_extra_amount", 0.0) or 0.0) - amount)
            pos["last_price"] = price
            trades.append({
                "date": str(date)[:10],
                "ts_code": code,
                "name": pos.get("name", row.get("name", "")),
                "action": "sell",
                "price": round(price, 4),
                "shares": shares,
                "amount": round(amount, 2),
                "commission": round(comm, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "reason": "winner_extra_trim",
            })
            return cash, True, ""

        module.__calc_current_nav = _calc_current_nav
        module.__max_holdings_for_regime = _max_holdings_for_regime
        module.__is_winner_budget_case = _is_winner_budget_case
        module.__winner_add_multiplier = _winner_add_multiplier
        module.__cap_winner_extra_amount = _cap_winner_extra_amount
        module.__cap_entry_amount = _cap_entry_amount
        module.__is_extension_entry = _is_extension_entry
        module.__select_downgrade_full_exit_codes = _select_downgrade_full_exit_codes
        module.__should_trim_winner_extra = _should_trim_winner_extra
        module.__execute_extra_trim = _execute_extra_trim
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


def normalize_market_frame(market):
    out = market.copy()
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"])
        out = out.sort_values("trade_date").set_index("trade_date")
    else:
        out.index = pd.to_datetime(out.index)
        out = out.sort_index()
    return out


def load_existing_nav(version):
    path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
    if not path.exists():
        return None
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    return nav[nav["date"] >= pd.Timestamp(START_DATE)].copy()


def load_existing_summary(version):
    path = BACKTRADER_DIR / version / "output" / "summary.json"
    if not path.exists():
        return {"case": version, "missing": True}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["case"] = version
    return data


def calc_nav_stats(nav, init_cash=500_000.0):
    curve = nav["nav"] / float(init_cash)
    dd = curve / curve.cummax() - 1.0
    total_ret = curve.iloc[-1] - 1.0
    days = max((nav["date"].iloc[-1] - nav["date"].iloc[0]).days, 1)
    annual = (1.0 + total_ret) ** (365.0 / days) - 1.0
    return {
        "final_nav": float(nav["nav"].iloc[-1]),
        "total_return_pct": float(total_ret * 100.0),
        "annual_return_pct": float(annual * 100.0),
        "max_drawdown_pct": float(dd.min() * 100.0),
        "calmar_ratio": float(annual / abs(dd.min())) if dd.min() < 0 else np.nan,
        "avg_cash_ratio": float((nav["cash"] / nav["nav"]).mean()) if "cash" in nav else np.nan,
        "avg_holdings": float(nav["holdings"].mean()) if "holdings" in nav else np.nan,
    }


def yearly_returns(nav):
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["nav"].sort_index().resample("YE").last().pct_change()


def monthly_returns(nav):
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["nav"].sort_index().resample("ME").last().pct_change()


def regime_audit(nav, rebalance_log):
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    regimes = rebalance_log[["date", "market_regime"]].copy()
    regimes["date"] = pd.to_datetime(regimes["date"])
    merged = frame.merge(regimes, on="date", how="left")
    nonbull_over = int(((merged["market_regime"] != "bull") & (merged["holdings"] > BASE_MAX_HOLDINGS)).sum())
    bear_over = int(((merged["market_regime"] == "bear") & (merged["holdings"] > BASE_MAX_HOLDINGS)).sum())
    return {
        "nonbull_over5_days": nonbull_over,
        "bear_over5_days": bear_over,
    }


def run_case(case, panel, market):
    module = load_v7_backtest_module("tmp_v7_bull_downgrade_" + case["case"], case)
    nav, trades, rebalance_log, score_rows, holdings, stats = module.run_backtest(
        panel.copy(),
        market.copy(),
        START_DATE,
        END_DATE,
    )
    stats["case"] = case["case"]
    stats["mode"] = case["mode"]
    stats["avg_cash_ratio"] = float((nav["cash"] / nav["nav"]).mean())
    stats["avg_holdings"] = float(nav["holdings"].mean())
    stats.update(regime_audit(nav, rebalance_log))
    return stats, nav, trades, rebalance_log


def format_pct(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def table_html(df, title):
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{html.escape(str(v))}</td>" for v in row.tolist())
        rows.append(f"<tr>{cells}</tr>")
    headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    return f"<h2>{html.escape(title)}</h2><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def best_candidate(all_stats):
    candidates = [s for s in all_stats if s.get("mode") in {"strict_extension", "winner_budget"}]
    if not candidates:
        return None
    return max(candidates, key=lambda s: float(s.get("total_return_pct", -999999)))


def build_report(all_stats, nav_by_case):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for stats in all_stats:
        summary_rows.append({
            "策略": stats["case"],
            "总收益": format_pct(stats.get("total_return_pct")),
            "年化": format_pct(stats.get("annual_return_pct")),
            "最大回撤": format_pct(stats.get("max_drawdown_pct")),
            "Calmar": f"{float(stats.get('calmar_ratio', 0.0)):.2f}" if stats.get("calmar_ratio") is not None and not pd.isna(stats.get("calmar_ratio")) else "-",
            "交易数": stats.get("trade_records", "-"),
            "止损": stats.get("stop_loss_fills", "-"),
            "扩展买入": stats.get("bull_extension_buys", "-"),
            "降级卖出": stats.get("bull_downgrade_full_exit_fills", "-"),
            "赢家加仓": stats.get("winner_extra_buys", "-"),
            "加仓回归": stats.get("winner_extra_trim_fills", "-"),
            "非牛超5天数": stats.get("nonbull_over5_days", "-"),
            "平均现金": format_pct(float(stats.get("avg_cash_ratio", np.nan)) * 100.0),
            "平均持股": f"{float(stats.get('avg_holdings', np.nan)):.2f}" if not pd.isna(stats.get("avg_holdings", np.nan)) else "-",
        })
    summary_df = pd.DataFrame(summary_rows)

    yearly = {}
    monthly = {}
    for name, nav in nav_by_case.items():
        yearly[name] = yearly_returns(nav) * 100.0
        monthly[name] = monthly_returns(nav) * 100.0
    yearly_df = pd.DataFrame(yearly).round(2).reset_index()
    yearly_df["date"] = yearly_df["date"].dt.strftime("%Y")
    yearly_df = yearly_df.rename(columns={"date": "年份"}).fillna("-")
    monthly_df = pd.DataFrame(monthly).round(2).tail(36).reset_index()
    monthly_df["date"] = monthly_df["date"].dt.strftime("%Y-%m")
    monthly_df = monthly_df.rename(columns={"date": "月份"}).fillna("-")

    best = best_candidate(all_stats)
    v7 = next((s for s in all_stats if s["case"] == "v7"), None)
    advice = "暂不合并"
    reason = "本轮实验尚未超过 v7 的收益/回撤组合。"
    if best is not None and v7 is not None:
        improves = float(best.get("total_return_pct", -999)) > float(v7.get("total_return_pct", -999))
        dd_ok = float(best.get("max_drawdown_pct", -999)) >= float(v7.get("max_drawdown_pct", -999)) - 3.0
        no_nonbull_over = int(best.get("nonbull_over5_days", 0)) == 0
        if improves and dd_ok and no_nonbull_over:
            advice = "建议进入合入候选"
            reason = "最佳实验收益超过 v7，回撤恶化不超过 3 个百分点，且非牛市不再超持。"
    best_text = "无"
    if best is not None:
        best_text = f"{best['case']}：总收益 {format_pct(best.get('total_return_pct'))}，最大回撤 {format_pct(best.get('max_drawdown_pct'))}"

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 牛市扩仓降级减仓实验报告</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #1f2937; }}
h1 {{ font-size: 24px; margin-bottom: 6px; }}
h2 {{ font-size: 18px; margin-top: 24px; }}
.note {{ padding: 12px 14px; background: #f3f4f6; border-left: 4px solid #2563eb; margin: 16px 0; }}
.warn {{ border-left-color: #dc2626; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 8px; font-size: 13px; }}
th, td {{ border: 1px solid #d1d5db; padding: 7px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #374151; color: white; position: sticky; top: 0; }}
.small {{ color: #6b7280; font-size: 12px; }}
</style>
</head>
<body>
<h1>v7 牛市扩仓降级减仓实验报告</h1>
<div class="note"><b>合并建议：{html.escape(advice)}</b><br>{html.escape(reason)}<br>最佳实验：{html.escape(best_text)}</div>
<div class="note warn"><b>代码审查结论</b><br>本轮已增加非牛市超5持仓审计。若该列不为 0，说明扩仓仍被带入 neutral/bear，结论不能用于合入。</div>
<p class="small">实验只写 tmp，正式 v4/v5/v6/v7 文件未修改。Tavily 复核用于定义 position sizing、pyramiding 和趋势降级风险控制；本轮不新增 Tushare 数据，避免归因混杂。</p>
{table_html(summary_df, "核心指标对比")}
{table_html(yearly_df, "年度收益对比（%）")}
{table_html(monthly_df, "最近36个月月度收益对比（%）")}
<h2>下一步建议</h2>
<ol>
<li>若严格扩仓胜出，下一步只细调 bull 最大持仓和降级卖出排序。</li>
<li>若赢家加预算胜出，下一步测试更细的强牛/弱牛加仓阈值。</li>
<li>若两者仍弱于 v7，继续做失败买入过滤，而不是扩大仓位。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_progress("开始运行牛市扩仓降级减仓实验。")
    panel = pd.read_parquet(V7_DIR / "output" / "panel.parquet")
    market = pd.read_parquet(V7_DIR / "output" / "market_index.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = normalize_market_frame(market)
    append_progress(f"加载 v7 panel rows={len(panel):,}。")

    all_stats = []
    nav_by_case = {}
    for version in ["v4", "v5", "v6", "v7"]:
        stats = load_existing_summary(version)
        nav = load_existing_nav(version)
        if nav is not None:
            stats.update(calc_nav_stats(nav))
            stats["case"] = version
            nav_by_case[version] = nav
        all_stats.append(stats)

    for case in CASES:
        stats, nav, trades, rebalance_log = run_case(case, panel, market)
        nav.to_csv(OUTPUT_DIR / f"{case['case']}_nav_series.csv", index=False, encoding="utf-8-sig")
        trades.to_csv(OUTPUT_DIR / f"{case['case']}_trade_records.csv", index=False, encoding="utf-8-sig")
        rebalance_log.to_csv(OUTPUT_DIR / f"{case['case']}_rebalance_log.csv", index=False, encoding="utf-8-sig")
        (OUTPUT_DIR / f"{case['case']}_summary.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        all_stats.append(stats)
        nav_by_case[case["case"]] = nav.copy()
        append_progress(
            f"完成 {case['case']}：total_return={stats['total_return_pct']:.2f}%，"
            f"max_dd={stats['max_drawdown_pct']:.2f}%，trades={stats['trade_records']}，"
            f"nonbull_over5={stats.get('nonbull_over5_days', '-')}"
        )

    build_report(all_stats, nav_by_case)
    append_progress(f"生成 HTML 报表：{REPORT_PATH}")
    append_progress("设计 review：专家角色确认本轮关键是降级减仓，不引入新数据以保持归因清晰。")
    append_progress("开发 review：检查项包括非牛市超持、扩展仓标签、赢家额外加仓回归、signal_date 估值口径。")


if __name__ == "__main__":
    main()

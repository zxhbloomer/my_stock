from pathlib import Path
import importlib.util
import sys

import numpy as np
import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
BACKTRADER_DIR = TMP_DIR.parent
V6_DIR = BACKTRADER_DIR / "v6"
TOP100_PATH = TMP_DIR / "2018_non_hotmoney_non_new_return_top100.csv"
OUT_CSV = TMP_DIR / "2018_v6_top20_buy_diagnosis.csv"
OUT_HTML = TMP_DIR / "2018_v6_top20_buy_diagnosis.html"

YEAR_START = pd.Timestamp("2018-01-01")
YEAR_END = pd.Timestamp("2018-12-31")


def load_v6_backtest_module():
    sys.path.insert(0, str(V6_DIR))
    spec = importlib.util.spec_from_file_location("v6_run_backtest_diag", V6_DIR / "20_run_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reason_failed_base(row):
    checks = [
        ("非基础池", not bool(row.get("is_eligible", False))),
        ("63日站上BBI比例不足", pd.isna(row.get("above_ratio_63")) or row.get("above_ratio_63") < 0.55),
        ("126日站上BBI比例不足", pd.isna(row.get("above_ratio_126")) or row.get("above_ratio_126") < 0.50),
        ("63日收益为负", pd.isna(row.get("ret_63")) or row.get("ret_63") < 0.0),
        ("63日均偏离过高", pd.isna(row.get("avg_distance_63")) or row.get("avg_distance_63") > 0.18),
        ("20日内跌停", pd.isna(row.get("recent_limit_down_20")) or row.get("recent_limit_down_20") != 0),
        ("游资风险命中>=2", pd.notna(row.get("hot_money_risk_hits")) and row.get("hot_money_risk_hits") >= 2),
        ("缺少波动率", pd.isna(row.get("volatility_63"))),
        ("缺少成交额均值", pd.isna(row.get("amount_ma20"))),
    ]
    reasons = [name for name, failed in checks if failed]
    if pd.notna(row.get("high_pos_21")) and row.get("high_pos_21") >= 0.95 and not bool(row.get("strong_trend", False)):
        reasons.append("接近21日新高且非强趋势")
    if pd.notna(row.get("ret_21")) and row.get("ret_21") > 0.45 and not bool(row.get("strong_trend", False)):
        reasons.append("21日涨幅过高且非强趋势")
    return ";".join(reasons[:4])


def main():
    v6 = load_v6_backtest_module()
    top20 = pd.read_csv(TOP100_PATH).head(20)
    top20_codes = set(top20["ts_code"].astype(str))

    panel = pd.read_parquet(V6_DIR / "output" / "panel.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel = panel[(panel["trade_date"] >= YEAR_START) & (panel["trade_date"] <= YEAR_END)].copy()
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)

    market = v6.load_market_index()
    market_regime = v6.build_market_regime(market, panel)
    panel_by_date = v6.build_panel_by_date(panel)
    all_dates = sorted(panel_by_date)
    trades = pd.read_csv(V6_DIR / "output" / "trade_records.csv")
    trades["date"] = pd.to_datetime(trades["date"])
    buys = trades[(trades["date"].between(YEAR_START, YEAR_END)) & (trades["action"].eq("buy"))]

    rows = []
    for _, stock in top20.iterrows():
        code = str(stock["ts_code"])
        code_buys = buys[buys["ts_code"].eq(code)].sort_values("date")
        counters = {
            "signal_days_seen": 0,
            "market_block_days": 0,
            "base_filter_fail_days": 0,
            "scored_candidate_days": 0,
            "downtrend_block_days": 0,
            "entry_candidate_days": 0,
            "target_top20_days": 0,
        }
        first_base_fail = ""
        best_score = np.nan
        best_rank = np.nan
        best_candidate_date = ""
        first_target_date = ""

        for i in range(1, len(all_dates)):
            signal_date = all_dates[i - 1]
            if signal_date < YEAR_START or signal_date > YEAR_END:
                continue
            signal_panel = v6.get_day_panel(panel, panel_by_date, signal_date)
            if code not in signal_panel.index:
                continue
            counters["signal_days_seen"] += 1
            market_regime_name, _ = v6.get_market_regime(market_regime, signal_date)
            short_blocked, short_reason, _ = v6.market_short_drop_blocks_buy(market, signal_date)
            regime_blocked = v6.MARKET_REGIME_FILTER_ENABLED and market_regime_name == "bear"
            if short_blocked or regime_blocked:
                counters["market_block_days"] += 1
                continue

            candidates_before_downtrend = v6.score_candidates(signal_panel, diagnostics={}).reset_index(drop=True)
            candidates_before_downtrend["rank"] = np.arange(1, len(candidates_before_downtrend) + 1)
            hit = candidates_before_downtrend[candidates_before_downtrend["ts_code"].eq(code)]
            if hit.empty:
                counters["base_filter_fail_days"] += 1
                if not first_base_fail:
                    row = signal_panel.loc[code]
                    first_base_fail = reason_failed_base(row)
                continue

            hit_row = hit.iloc[0]
            counters["scored_candidate_days"] += 1
            score = float(hit_row["score"])
            if pd.isna(best_score) or score > best_score:
                best_score = score
                best_rank = int(hit_row["rank"])
                best_candidate_date = str(signal_date)[:10]

            pullback_threshold, strong_pullback_threshold = v6.regime_pullback_thresholds(market_regime_name)
            strong = bool(hit_row.get("strong_trend", False))
            pullback = hit_row.get("pullback_63")
            pullback_ok = pd.notna(pullback) and (
                (strong and pullback <= strong_pullback_threshold)
                or ((not strong) and pullback <= pullback_threshold)
            )
            if not pullback_ok:
                continue

            counters["entry_candidate_days"] += 1
            entry_candidates = candidates_before_downtrend[
                candidates_before_downtrend["pullback_63"].notna()
                & (
                    (
                        candidates_before_downtrend["strong_trend"].fillna(False)
                        & (candidates_before_downtrend["pullback_63"] <= strong_pullback_threshold)
                    )
                    | (
                        ~candidates_before_downtrend["strong_trend"].fillna(False)
                        & (candidates_before_downtrend["pullback_63"] <= pullback_threshold)
                    )
                )
            ]
            target_codes = list(entry_candidates["ts_code"].head(v6.KEEP_TOP_N))
            if code in target_codes:
                counters["target_top20_days"] += 1
                if not first_target_date:
                    first_target_date = str(signal_date)[:10]

        if not code_buys.empty:
            conclusion = "v6实际买入"
            detail = f"首次买入 {code_buys.iloc[0]['date'].date()}，原因 {code_buys.iloc[0]['reason']}"
        elif counters["market_block_days"] and counters["scored_candidate_days"] == 0 and counters["base_filter_fail_days"] == 0:
            conclusion = "主要被大盘风控阻断"
            detail = "该股有数据的信号日全部落在市场禁止买入日"
        elif counters["scored_candidate_days"] == 0:
            conclusion = "未通过个股候选基础过滤"
            detail = first_base_fail
        elif counters["entry_candidate_days"] == 0:
            conclusion = "通过评分但未满足回撤买点"
            detail = f"最佳入围 {best_candidate_date}，候选排名 {best_rank}，分数 {best_score:.4f}"
        elif counters["target_top20_days"] == 0:
            conclusion = "满足买点但未进入当日目标前20"
            detail = f"最佳入围 {best_candidate_date}，候选排名 {best_rank}，分数 {best_score:.4f}"
        else:
            conclusion = "进入目标但未成交或仓位容量限制"
            detail = f"首次目标信号 {first_target_date}"

        rows.append({
            "rank": int(stock["rank"]),
            "ts_code": code,
            "name": stock["name"],
            "annual_return_pct": round(float(stock["annual_return_pct"]), 2),
            "v6_bought": not code_buys.empty,
            "conclusion": conclusion,
            "detail": detail,
            **counters,
            "best_candidate_date": best_candidate_date,
            "best_candidate_rank": "" if pd.isna(best_rank) else int(best_rank),
            "best_score": "" if pd.isna(best_score) else round(best_score, 4),
            "first_target_signal_date": first_target_date,
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    result.to_html(OUT_HTML, index=False, escape=False)
    print(result.to_string(index=False))
    print(f"csv={OUT_CSV}")
    print(f"html={OUT_HTML}")


if __name__ == "__main__":
    main()

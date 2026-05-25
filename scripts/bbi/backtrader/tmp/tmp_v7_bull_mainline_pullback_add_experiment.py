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

OUTPUT_DIR = TMP_DIR / "tmp_v7_bull_mainline_pullback_add_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_bull_mainline_pullback_add_README.md"

START_DATE = "2018-01-01"
END_DATE = None

BASE_LONG_MAX_HOLDINGS = 5
BASE_LONG_MAX_TOTAL_EXPOSURE = 500_000.0
BASE_LONG_STOP_LOSS_PCT = -0.05
BASE_INITIAL_AMOUNT = 80_000.0

CASES = [
    {"case": "当前v7复现", "mode": "baseline"},
    {
        "case": "主线牛股回踩_7只_总仓50",
        "mode": "mainline_pullback",
        "mainline_score_min": 0.70,
        "mainline_breadth_min": 0.55,
        "mainline_industry_ret_63_min": 0.0,
        "stock_above_ratio_63_min": 0.75,
        "stock_above_ratio_126_min": 0.60,
        "stock_ret_63_min": 0.50,
        "max_bbi_distance": 0.05,
        "pullback_max": -0.03,
        "max_high_pos_21": 0.95,
        "max_ret_21_for_pullback": 0.45,
        "bull_max_holdings": 7,
        "strong_bull_max_holdings": 7,
        "bull_total_exposure": 500_000.0,
        "strong_total_exposure": 500_000.0,
        "extension_initial_amount": 40_000.0,
    },
    {
        "case": "主线牛股回踩_10只_总仓55",
        "mode": "mainline_pullback",
        "mainline_score_min": 0.70,
        "mainline_breadth_min": 0.55,
        "mainline_industry_ret_63_min": 0.0,
        "stock_above_ratio_63_min": 0.75,
        "stock_above_ratio_126_min": 0.60,
        "stock_ret_63_min": 0.50,
        "max_bbi_distance": 0.05,
        "pullback_max": -0.03,
        "max_high_pos_21": 0.95,
        "max_ret_21_for_pullback": 0.45,
        "bull_max_holdings": 7,
        "strong_bull_max_holdings": 10,
        "bull_total_exposure": 500_000.0,
        "strong_total_exposure": 550_000.0,
        "extension_initial_amount": 50_000.0,
    },
    {
        "case": "主线牛股回踩_10只_总仓65",
        "mode": "mainline_pullback",
        "mainline_score_min": 0.70,
        "mainline_breadth_min": 0.55,
        "mainline_industry_ret_63_min": 0.0,
        "stock_above_ratio_63_min": 0.75,
        "stock_above_ratio_126_min": 0.60,
        "stock_ret_63_min": 0.50,
        "max_bbi_distance": 0.05,
        "pullback_max": -0.03,
        "max_high_pos_21": 0.95,
        "max_ret_21_for_pullback": 0.45,
        "bull_max_holdings": 7,
        "strong_bull_max_holdings": 10,
        "bull_total_exposure": 550_000.0,
        "strong_total_exposure": 650_000.0,
        "extension_initial_amount": 50_000.0,
    },
    {
        "case": "主线牛股回踩_10只_总仓55_宽止损8",
        "mode": "mainline_pullback_wide_stop",
        "mainline_score_min": 0.70,
        "mainline_breadth_min": 0.55,
        "mainline_industry_ret_63_min": 0.0,
        "stock_above_ratio_63_min": 0.75,
        "stock_above_ratio_126_min": 0.60,
        "stock_ret_63_min": 0.50,
        "max_bbi_distance": 0.05,
        "pullback_max": -0.03,
        "max_high_pos_21": 0.95,
        "max_ret_21_for_pullback": 0.45,
        "bull_max_holdings": 7,
        "strong_bull_max_holdings": 10,
        "bull_total_exposure": 500_000.0,
        "strong_total_exposure": 550_000.0,
        "extension_initial_amount": 50_000.0,
        "wide_stop_loss": -0.08,
    },
    {
        "case": "严格主线牛股回踩_7只_总仓50",
        "mode": "mainline_pullback",
        "mainline_score_min": 0.80,
        "mainline_breadth_min": 0.60,
        "mainline_industry_ret_63_min": 0.05,
        "stock_above_ratio_63_min": 0.80,
        "stock_above_ratio_126_min": 0.65,
        "stock_ret_63_min": 0.60,
        "max_bbi_distance": 0.03,
        "pullback_max": -0.05,
        "max_high_pos_21": 0.90,
        "max_ret_21_for_pullback": 0.30,
        "bull_max_holdings": 7,
        "strong_bull_max_holdings": 7,
        "bull_total_exposure": 500_000.0,
        "strong_total_exposure": 500_000.0,
        "extension_initial_amount": 40_000.0,
    },
]


def append_progress(message: str) -> None:
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def safe_float(value, default=float("nan")) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def is_strong_bull(market_regime_name: str, regime_snapshot: dict, case: dict) -> bool:
    if market_regime_name != "bull":
        return False
    return (
        safe_float(regime_snapshot.get("breadth_above_bbi")) >= float(case.get("strong_breadth", 0.65))
        and safe_float(regime_snapshot.get("market_ma120_slope_20")) >= float(case.get("strong_slope", 0.0))
        and safe_float(regime_snapshot.get("market_dd_252")) >= float(case.get("strong_dd", -0.05))
    )


def is_mainline_industry(row, case: dict) -> bool:
    return (
        safe_float(row.get("industry_mainline_score"), 0.0) >= float(case.get("mainline_score_min", 0.70))
        and safe_float(row.get("industry_above_bbi_ratio"), 0.0) >= float(case.get("mainline_breadth_min", 0.55))
        and safe_float(row.get("industry_ret_63_median"), 0.0) >= float(case.get("mainline_industry_ret_63_min", 0.0))
        and safe_float(row.get("industry_member_count"), 0.0) >= float(case.get("industry_member_count_min", 8))
    )


def is_mainline_bull_stock(row, case: dict) -> bool:
    return (
        is_mainline_industry(row, case)
        and safe_float(row.get("above_ratio_63"), 0.0) >= float(case.get("stock_above_ratio_63_min", 0.75))
        and safe_float(row.get("above_ratio_126"), 0.0) >= float(case.get("stock_above_ratio_126_min", 0.60))
        and safe_float(row.get("ret_63"), 0.0) >= float(case.get("stock_ret_63_min", 0.50))
    )


def is_mainline_pullback_stock(row, case: dict) -> bool:
    if case.get("mode") == "baseline":
        return False
    close = safe_float(row.get("close_qfq"))
    bbi = safe_float(row.get("bbi_qfq"))
    if pd.isna(close) or pd.isna(bbi) or bbi <= 0 or close <= bbi:
        return False
    bbi_distance = close / bbi - 1.0
    eps = 1e-12
    return (
        is_mainline_bull_stock(row, case)
        and bbi_distance <= float(case.get("max_bbi_distance", 0.05)) + eps
        and safe_float(row.get("pullback_63")) <= float(case.get("pullback_max", -0.03))
        and safe_float(row.get("high_pos_21")) < float(case.get("max_high_pos_21", 0.95))
        and safe_float(row.get("ret_21")) <= float(case.get("max_ret_21_for_pullback", 0.45))
    )


def max_holdings_for_regime(market_regime_name: str, regime_snapshot: dict, case: dict) -> int:
    if case.get("mode") == "baseline" or market_regime_name != "bull":
        return BASE_LONG_MAX_HOLDINGS
    if is_strong_bull(market_regime_name, regime_snapshot, case):
        return int(case.get("strong_bull_max_holdings", case.get("bull_max_holdings", BASE_LONG_MAX_HOLDINGS)))
    return int(case.get("bull_max_holdings", BASE_LONG_MAX_HOLDINGS))


def total_exposure_limit(market_regime_name: str, regime_snapshot: dict, case: dict) -> float:
    if case.get("mode") == "baseline" or market_regime_name != "bull":
        return BASE_LONG_MAX_TOTAL_EXPOSURE
    if is_strong_bull(market_regime_name, regime_snapshot, case):
        return float(case.get("strong_total_exposure", BASE_LONG_MAX_TOTAL_EXPOSURE))
    return float(case.get("bull_total_exposure", BASE_LONG_MAX_TOTAL_EXPOSURE))


def is_mainline_pullback_code(code: str, signal_panel: pd.DataFrame, case: dict) -> bool:
    if case.get("mode") == "baseline" or code not in signal_panel.index:
        return False
    return is_mainline_pullback_stock(signal_panel.loc[code], case)


def initial_target_amount(
    current_holding_count: int,
    code: str,
    signal_panel: pd.DataFrame,
    market_regime_name: str,
    regime_snapshot: dict,
    available_exposure: float,
    case: dict,
) -> float:
    if case.get("mode") == "baseline" or current_holding_count < BASE_LONG_MAX_HOLDINGS:
        return min(BASE_INITIAL_AMOUNT, available_exposure)
    if market_regime_name != "bull" or not is_mainline_pullback_code(code, signal_panel, case):
        return 0.0
    return min(float(case.get("extension_initial_amount", 40_000.0)), available_exposure)


def stop_loss_for_position(market_regime_name: str, regime_snapshot: dict, pos: dict, case: dict) -> float:
    if (
        (case.get("mode") == "mainline_pullback_wide_stop" or "wide_stop_loss" in case)
        and is_strong_bull(market_regime_name, regime_snapshot, case)
        and bool(pos.get("mainline_pullback_entry", False))
    ):
        return float(case.get("wide_stop_loss", -0.08))
    return BASE_LONG_STOP_LOSS_PCT


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"patch anchor not found: {old[:100]}")
    return source.replace(old, new, 1)


def load_v7_config():
    spec = importlib.util.spec_from_file_location("v7_config_for_mainline_pullback", V7_DIR / "config.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fetch_stock_industry() -> pd.DataFrame:
    from sqlalchemy import create_engine, text

    config = load_v7_config()
    engine = create_engine(config.DB_URL)
    sql = text(f'SELECT ts_code, industry FROM {config.SCHEMA}."001_stock_basic"')
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
            '        "mainline_pullback_case": MAINLINE_PULLBACK_CASE.get("case", "baseline"),\n'
            '        "mainline_pullback_extension_buys": 0,\n'
            '        "mainline_pullback_add_buys": 0,\n'
            '        "mainline_pullback_skips": 0,\n',
        )
        source = replace_once(
            source,
            "elif profit_pct is not None and profit_pct <= LONG_STOP_LOSS_PCT:\n",
            "elif profit_pct is not None and __stop_loss_trigger(market_regime_name, regime_snapshot, holdings[code], profit_pct):\n",
        )
        source = replace_once(
            source,
            "                        if pos.get(\"pending_sell\") or not can_add_position(code, pos, signal_panel):\n",
            "                        if pos.get(\"pending_sell\") or not __can_add_mainline_pullback(code, pos, signal_panel, market_regime_name, regime_snapshot):\n",
        )
        source = replace_once(
            source,
            "                        available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n",
            "                        available_exposure = __total_exposure_limit(market_regime_name, regime_snapshot) - calc_total_exposure(holdings)\n",
        )
        source = replace_once(
            source,
            '                            stats["add_buy_fills"] += 1\n',
            '                            stats["add_buy_fills"] += 1\n'
            '                            if __is_mainline_pullback_code(code, signal_panel):\n'
            '                                stats["mainline_pullback_add_buys"] += 1\n',
        )
        source = replace_once(
            source,
            "                    if len(holdings) >= LONG_MAX_HOLDINGS:\n",
            "                    if len(holdings) >= __max_holdings(market_regime_name, regime_snapshot):\n",
        )
        source = replace_once(
            source,
            "                    if code in holdings or code in risk_exit_codes or code not in day_panel.index:\n"
            "                        continue\n",
            "                    if code in holdings or code in risk_exit_codes or code not in day_panel.index:\n"
            "                        continue\n"
            "                    if len(holdings) >= 5 and not __is_mainline_pullback_code(code, signal_panel):\n"
            "                        stats[\"mainline_pullback_skips\"] += 1\n"
            "                        continue\n",
        )
        source = replace_once(
            source,
            "                    available_exposure = LONG_MAX_TOTAL_EXPOSURE - calc_total_exposure(holdings)\n",
            "                    available_exposure = __total_exposure_limit(market_regime_name, regime_snapshot) - calc_total_exposure(holdings)\n",
        )
        source = replace_once(
            source,
            "                    else:\n"
            "                        target_amount = min(float(LONG_POSITION_STEPS[0]), available_exposure)\n",
            "                    else:\n"
            "                        target_amount = __initial_target_amount(len(holdings), code, signal_panel, market_regime_name, regime_snapshot, available_exposure)\n",
        )
        source = replace_once(
            source,
            "                    if bought:\n"
            "                        bought_count += 1\n"
            "                        stats[\"buy_fills\"] += 1\n"
            "                        if probe_open:\n"
            "                            holdings[code][\"probe_entry\"] = True\n"
            "                            stats[\"bear_probe_buys\"] += 1\n",
            "                    if bought:\n"
            "                        bought_count += 1\n"
            "                        stats[\"buy_fills\"] += 1\n"
            "                        if __is_mainline_pullback_code(code, signal_panel):\n"
            "                            holdings[code][\"mainline_pullback_entry\"] = True\n"
            "                        if __is_extension_entry(len(holdings), market_regime_name, regime_snapshot):\n"
            "                            holdings[code][\"extension_entry\"] = True\n"
            "                            stats[\"mainline_pullback_extension_buys\"] += 1\n"
            "                        if probe_open:\n"
            "                            holdings[code][\"probe_entry\"] = True\n"
            "                            stats[\"bear_probe_buys\"] += 1\n",
        )
        source = replace_once(
            source,
            "                score_rows.extend(candidates[score_cols].head(100).to_dict(\"records\"))\n",
            "                score_cols = score_cols + [\n"
            "                    col for col in [\n"
            "                        \"industry\", \"industry_member_count\", \"industry_ret_63_median\",\n"
            "                        \"industry_ret_21_median\", \"industry_above_bbi_ratio\", \"industry_mainline_score\",\n"
            "                    ] if col in candidates.columns\n"
            "                ]\n"
            "                score_rows.extend(candidates[score_cols].head(100).to_dict(\"records\"))\n",
        )

        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__file__"] = str(V7_DIR / "20_run_backtest.py")
        sys.modules[module_name] = module
        exec(compile(source, str(V7_DIR / "20_run_backtest.py"), "exec"), module.__dict__)
        module.MAINLINE_PULLBACK_CASE = dict(case)

        def _is_code(code, signal_panel):
            return is_mainline_pullback_code(code, signal_panel, module.MAINLINE_PULLBACK_CASE)

        def _max_holdings(market_regime_name, regime_snapshot):
            return max_holdings_for_regime(market_regime_name, regime_snapshot, module.MAINLINE_PULLBACK_CASE)

        def _total_limit(market_regime_name, regime_snapshot):
            return total_exposure_limit(market_regime_name, regime_snapshot, module.MAINLINE_PULLBACK_CASE)

        def _initial_amount(current_holding_count, code, signal_panel, market_regime_name, regime_snapshot, available_exposure):
            return initial_target_amount(
                current_holding_count,
                code,
                signal_panel,
                market_regime_name,
                regime_snapshot,
                available_exposure,
                module.MAINLINE_PULLBACK_CASE,
            )

        def _is_extension_entry(holding_count_after_buy, market_regime_name, regime_snapshot):
            if module.MAINLINE_PULLBACK_CASE.get("mode") == "baseline" or market_regime_name != "bull":
                return False
            return int(holding_count_after_buy) > BASE_LONG_MAX_HOLDINGS

        def _can_add(code, pos, signal_panel, market_regime_name, regime_snapshot):
            if not module.can_add_position(code, pos, signal_panel):
                return False
            if module.MAINLINE_PULLBACK_CASE.get("mode") == "baseline" or market_regime_name != "bull":
                return True
            return _is_code(code, signal_panel)

        def _stop_trigger(market_regime_name, regime_snapshot, pos, profit_pct):
            threshold = stop_loss_for_position(market_regime_name, regime_snapshot, pos, module.MAINLINE_PULLBACK_CASE)
            return profit_pct <= threshold

        module.__is_mainline_pullback_code = _is_code
        module.__max_holdings = _max_holdings
        module.__total_exposure_limit = _total_limit
        module.__initial_target_amount = _initial_amount
        module.__is_extension_entry = _is_extension_entry
        module.__can_add_mainline_pullback = _can_add
        module.__stop_loss_trigger = _stop_trigger
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


def normalize_market_frame(market: pd.DataFrame) -> pd.DataFrame:
    out = market.copy()
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"])
        return out.sort_values("trade_date").set_index("trade_date")
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def load_existing_nav(version: str) -> pd.DataFrame | None:
    path = BACKTRADER_DIR / version / "output" / "nav_series.csv"
    if not path.exists():
        return None
    nav = pd.read_csv(path)
    nav["date"] = pd.to_datetime(nav["date"])
    return nav[nav["date"] >= pd.Timestamp(START_DATE)].copy()


def load_existing_summary(version: str) -> dict:
    data = json.loads((BACKTRADER_DIR / version / "output" / "summary.json").read_text(encoding="utf-8"))
    data["case"] = version
    data["mode"] = "published"
    return data


def calc_nav_stats(nav: pd.DataFrame, init_cash: float = 500_000.0) -> dict:
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
        "avg_cash_ratio": float((nav["cash"] / nav["nav"]).mean()) if "cash" in nav else np.nan,
        "avg_holdings": float(nav["holdings"].mean()) if "holdings" in nav else np.nan,
    }


def monthly_returns(nav: pd.DataFrame) -> pd.Series:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["nav"].sort_index().resample("ME").last().pct_change()


def yearly_returns(nav: pd.DataFrame) -> pd.Series:
    frame = nav.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["nav"].sort_index().resample("YE").last().pct_change()


def build_buy_audit(case: dict, trades: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    dates = sorted(pd.to_datetime(panel["trade_date"]).dropna().unique())
    signal_date_by_rebalance = {
        pd.Timestamp(dates[i]).strftime("%Y-%m-%d"): pd.Timestamp(dates[i - 1])
        for i in range(1, len(dates))
    }
    panel_idx = panel.set_index(["trade_date", "ts_code"], drop=False)
    rows = []
    buy_trades = trades[trades["action"].astype(str).eq("buy")].copy()
    for _, trade in buy_trades.iterrows():
        trade_date = pd.Timestamp(trade["date"]).strftime("%Y-%m-%d")
        signal_date = signal_date_by_rebalance.get(trade_date)
        code = str(trade["ts_code"])
        feature = None
        if signal_date is not None and (signal_date, code) in panel_idx.index:
            feature = panel_idx.loc[(signal_date, code)]
        row = {
            "trade_date": trade_date,
            "signal_date": signal_date.strftime("%Y-%m-%d") if signal_date is not None else "",
            "ts_code": code,
            "name": trade.get("name", ""),
            "reason": trade.get("reason", ""),
            "amount": trade.get("amount", np.nan),
        }
        if feature is not None:
            bbi = safe_float(feature.get("bbi_qfq"))
            close = safe_float(feature.get("close_qfq"))
            row.update({
                "industry": feature.get("industry", ""),
                "industry_mainline_score": safe_float(feature.get("industry_mainline_score")),
                "industry_above_bbi_ratio": safe_float(feature.get("industry_above_bbi_ratio")),
                "industry_ret_63_median": safe_float(feature.get("industry_ret_63_median")),
                "above_ratio_63": safe_float(feature.get("above_ratio_63")),
                "above_ratio_126": safe_float(feature.get("above_ratio_126")),
                "ret_63": safe_float(feature.get("ret_63")),
                "ret_21": safe_float(feature.get("ret_21")),
                "pullback_63": safe_float(feature.get("pullback_63")),
                "high_pos_21": safe_float(feature.get("high_pos_21")),
                "bbi_distance": close / bbi - 1.0 if bbi > 0 else np.nan,
                "is_mainline_pullback": is_mainline_pullback_stock(feature, case),
            })
        rows.append(row)
    return pd.DataFrame(rows)


def run_case(case: dict, panel: pd.DataFrame, market: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    module_name = "tmp_v7_mainline_pullback_" + str(abs(hash(case["case"])))
    module = load_v7_backtest_module(module_name, case)
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
    stats["avg_exposure_ratio"] = float(((nav["nav"] - nav["cash"]) / nav["nav"]).mean())
    rebalance_df = pd.DataFrame(rebalance_log)
    score_df = pd.DataFrame(score_rows)
    audit_df = build_buy_audit(case, trades, panel)
    return stats, nav, trades, rebalance_df, score_df, audit_df


def format_pct(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def table_html(df: pd.DataFrame, title: str) -> str:
    headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, row in df.iterrows():
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row.tolist()) + "</tr>")
    return f"<h2>{html.escape(title)}</h2><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def best_experiment(all_stats: list[dict]) -> dict | None:
    experiments = [s for s in all_stats if s.get("mode") not in {"published", "baseline"}]
    if not experiments:
        return None
    return max(experiments, key=lambda s: float(s.get("total_return_pct", -999999)))


def build_report(all_stats: list[dict], nav_by_case: dict[str, pd.DataFrame]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for stats in all_stats:
        summary_rows.append({
            "策略": stats["case"],
            "总收益": format_pct(stats.get("total_return_pct")),
            "年化": format_pct(stats.get("annual_return_pct")),
            "最大回撤": format_pct(stats.get("max_drawdown_pct")),
            "Calmar": f"{float(stats.get('calmar_ratio', 0.0)):.2f}",
            "交易数": stats.get("trade_records", "-"),
            "扩展买入": stats.get("mainline_pullback_extension_buys", "-"),
            "主线回踩加仓": stats.get("mainline_pullback_add_buys", "-"),
            "平均现金占比": format_pct(float(stats.get("avg_cash_ratio", np.nan)) * 100.0),
            "平均持股": f"{float(stats.get('avg_holdings', np.nan)):.2f}" if not pd.isna(stats.get("avg_holdings", np.nan)) else "-",
        })
    summary_df = pd.DataFrame(summary_rows)

    yearly_df = pd.DataFrame({name: yearly_returns(nav) * 100.0 for name, nav in nav_by_case.items()}).round(2).reset_index()
    yearly_df["date"] = yearly_df["date"].dt.strftime("%Y")
    yearly_df = yearly_df.rename(columns={"date": "年份"}).fillna("-")
    monthly_df = pd.DataFrame({name: monthly_returns(nav) * 100.0 for name, nav in nav_by_case.items()}).round(2).tail(36).reset_index()
    monthly_df["date"] = monthly_df["date"].dt.strftime("%Y-%m")
    monthly_df = monthly_df.rename(columns={"date": "月份"}).fillna("-")

    v7 = next((s for s in all_stats if s["case"] == "v7"), None)
    best = best_experiment(all_stats)
    advice = "暂不合并"
    reason = "最佳实验未同时超过 v7 收益并维持可接受回撤。"
    if best and v7:
        improves_return = float(best.get("total_return_pct", -999)) > float(v7.get("total_return_pct", -999)) + 1e-6
        drawdown_ok = float(best.get("max_drawdown_pct", -999)) >= float(v7.get("max_drawdown_pct", -999)) - 5.0
        if improves_return and drawdown_ok:
            advice = "建议进入正式合入候选"
            reason = "最佳实验总收益超过 v7，最大回撤恶化不超过 5 个百分点。"
    display_best = best or {"case": "无实验", "total_return_pct": np.nan, "max_drawdown_pct": np.nan}

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>v7 主线牛股回踩加仓实验报告</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #1f2937; }}
h1 {{ font-size: 24px; margin-bottom: 6px; }}
h2 {{ font-size: 18px; margin-top: 24px; }}
.note {{ padding: 12px 14px; background: #f3f4f6; border-left: 4px solid #2563eb; margin: 16px 0; line-height: 1.6; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 8px; font-size: 13px; }}
th, td {{ border: 1px solid #d1d5db; padding: 7px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #374151; color: white; position: sticky; top: 0; }}
.small {{ color: #6b7280; font-size: 12px; }}
li {{ margin: 6px 0; }}
</style>
</head>
<body>
<h1>v7 主线牛股回踩加仓实验报告</h1>
<div class="note"><b>合并建议：{html.escape(advice)}</b><br>{html.escape(reason)}<br>最佳实验：{html.escape(display_best["case"])}，总收益 {format_pct(display_best.get("total_return_pct"))}，最大回撤 {format_pct(display_best.get("max_drawdown_pct"))}。</div>
<p class="small">实验只修改 tmp 注入逻辑，正式 v4/v5/v6/v7 文件未修改。交易信号来自 signal_date，不使用交易日未来数据。注意：行业主线第一版使用 stock_basic 静态行业映射，若历史行业分类发生变化，行业标签存在点时性风险。</p>
{table_html(summary_df, "核心指标对比")}
{table_html(yearly_df, "年度收益对比（%）")}
{table_html(monthly_df, "最近36个月月度收益对比（%）")}
<h2>策略解释</h2>
<ol>
<li>前 5 只股票仍按 v7 的候选、回踩、分批买入执行。</li>
<li>第 6-10 只不是普通排名扩展，只能买“主线行业 + 强趋势个股 + BBI 上方回踩”的股票。</li>
<li>已有持仓在牛市加仓时，也必须重新满足主线牛股回踩，避免高位追涨加仓。</li>
<li>输出目录包含每个 case 的 rebalance_log、score_rows 和 buy_audit，用于复核触发日、行业、股票和阈值。</li>
</ol>
<h2>下一步建议</h2>
<ol>
<li>若收益不如 v7，不合并；说明主线回踩触发质量或频率不足。</li>
<li>若扩展买入很少，下一步先看触发日志，不直接放宽总仓。</li>
<li>若某一年明显拖累收益，下一轮针对该年份做主线行业识别误差分析。</li>
</ol>
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_progress("开始运行主线牛股回踩加仓实验。")
    panel = pd.read_parquet(V7_DIR / "output" / "panel.parquet")
    market = normalize_market_frame(pd.read_parquet(V7_DIR / "output" / "market_index.parquet"))
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    append_progress(f"加载 v7 panel rows={len(panel):,}。")

    industry_map = fetch_stock_industry()
    append_progress(f"加载行业映射 rows={len(industry_map):,}。")
    panel = add_industry_mainline_features(panel, industry_map)
    append_progress("生成 signal_date 可用的行业主线特征。")

    all_stats = []
    nav_by_case = {}
    for version in ["v4", "v5", "v6", "v7"]:
        stats = load_existing_summary(version)
        nav = load_existing_nav(version)
        if nav is not None:
            stats.update(calc_nav_stats(nav))
            nav_by_case[version] = nav
        all_stats.append(stats)

    for case in CASES:
        stats, nav, trades, rebalance_df, score_df, audit_df = run_case(case, panel, market)
        nav.to_csv(OUTPUT_DIR / f"{case['case']}_nav_series.csv", index=False, encoding="utf-8-sig")
        trades.to_csv(OUTPUT_DIR / f"{case['case']}_trade_records.csv", index=False, encoding="utf-8-sig")
        rebalance_df.to_csv(OUTPUT_DIR / f"{case['case']}_rebalance_log.csv", index=False, encoding="utf-8-sig")
        score_df.to_csv(OUTPUT_DIR / f"{case['case']}_score_rows.csv", index=False, encoding="utf-8-sig")
        audit_df.to_csv(OUTPUT_DIR / f"{case['case']}_buy_audit.csv", index=False, encoding="utf-8-sig")
        (OUTPUT_DIR / f"{case['case']}_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        all_stats.append(stats)
        nav_by_case[case["case"]] = nav.copy()
        append_progress(
            f"完成 {case['case']}：total_return={stats['total_return_pct']:.2f}%，"
            f"max_dd={stats['max_drawdown_pct']:.2f}%，trades={stats['trade_records']}，"
            f"extension={stats.get('mainline_pullback_extension_buys', 0)}，"
            f"add={stats.get('mainline_pullback_add_buys', 0)}。"
        )

    build_report(all_stats, nav_by_case)
    append_progress(f"生成 HTML 报表：{REPORT_PATH}")
    append_progress("设计 review：专家角色确认本轮纠正为主线牛股回踩，不再把第6-10名普通股票当扩展池。")
    append_progress("开发 review：正式 v4-v7 文件未修改；规则函数可直接测试；输出写入 tmp。")


if __name__ == "__main__":
    main()

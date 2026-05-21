import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd


V7_DIR = Path(__file__).resolve().parent


def load_v7_module(module_name, filename):
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(V7_DIR))
        spec = importlib.util.spec_from_file_location(module_name, V7_DIR / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_path


backtest = load_v7_module("v7_backtest_for_no_lookahead_test", "20_run_backtest.py")


class V6NoLookaheadTests(unittest.TestCase):
    def make_minimal_panel(self):
        rows = []
        for day, forbid_buy in [
            ("2024-01-02", False),
            ("2024-01-03", True),
        ]:
            rows.append({
                "ts_code": "000001.SZ",
                "trade_date": pd.Timestamp(day),
                "name": "TEST",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "close_qfq": 10.2,
                "bbi_qfq": 9.8,
                "pre_close": 10.0,
                "up_limit": 11.0,
                "down_limit": 9.0,
                "amount": 100000.0,
                "adj_factor": 1.0,
                "is_suspended": False,
                "is_eligible": True,
                "above_bbi": True,
                "above_ratio_21": 0.8,
                "above_ratio_63": 0.8,
                "above_ratio_126": 0.8,
                "avg_distance_63": 0.02,
                "high_pos_21": 0.5,
                "high_pos_63": 0.5,
                "range_pos_63": 0.5,
                "recent_limit_down_20": 0.0,
                "recent_limit_up_20": 0.0,
                "recent_limit_up_63": 0.0,
                "turnover_rate_ma20": 2.0,
                "turnover_rate_max20": 3.0,
                "volume_ratio_max20": 1.2,
                "lhb_count_20": 0.0,
                "hot_money_risk_hits": 0.0,
                "hm_limit_up_20_flag": False,
                "hm_limit_up_63_flag": False,
                "hm_turnover_ma20_flag": False,
                "hm_turnover_max20_flag": False,
                "hm_volume_ratio_max20_flag": False,
                "hm_lhb_count20_flag": False,
                "ret_21": 0.1,
                "ret_63": 0.2,
                "ret_126": 0.3,
                "ma20_qfq": 9.5,
                "ma20_slope_10": 0.01,
                "early_weakness_downtrend": False,
                "up_accel_exhaustion": False,
                "bear_down_accel_risk": False,
                "accel_exhaustion_forbid_buy": forbid_buy,
                "volatility_63": 0.02,
                "amount_ma20": 100000.0,
                "circ_mv_ma20": 200000.0,
                "pullback_63": -0.06,
            })
        return pd.DataFrame(rows)

    def test_rebalance_uses_previous_day_signal_not_current_day_filter(self):
        panel = self.make_minimal_panel()

        with patch.object(backtest, "MARKET_FILTER_ENABLED", False), \
                patch.object(backtest, "MARKET_REGIME_FILTER_ENABLED", False), \
                patch.object(backtest, "HOT_MONEY_RISK_ENABLED", False), \
                patch.object(backtest, "LONG_MAX_HOLDINGS", 1), \
                patch.object(backtest, "KEEP_TOP_N", 1), \
                patch.object(backtest, "LONG_POSITION_STEPS", (10000.0,)):
            _, trades, rebalance, _, _, stats = backtest.run_backtest(
                panel,
                market=None,
                start_date="2024-01-02",
                end_date="2024-01-03",
            )

        self.assertEqual(stats["buy_fills"], 1)
        self.assertEqual(trades.iloc[0]["date"], "2024-01-03")
        self.assertEqual(trades.iloc[0]["action"], "buy")
        self.assertEqual(trades.iloc[0]["reason"], "long_initial_buy")
        self.assertEqual(rebalance.iloc[0]["signal_date"], "2024-01-02")


if __name__ == "__main__":
    unittest.main()

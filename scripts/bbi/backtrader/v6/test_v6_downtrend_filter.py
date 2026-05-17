import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd


V6_DIR = Path(__file__).resolve().parent


def load_module(filename, module_name):
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(V6_DIR))
        spec = importlib.util.spec_from_file_location(module_name, V6_DIR / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_path


class V6DowntrendFilterTest(unittest.TestCase):
    def test_output_dir_is_isolated_under_v6(self):
        config = load_module("config.py", "v6_config_for_test")

        self.assertEqual(config.OUTPUT_DIR.parent.resolve(), V6_DIR.resolve())
        self.assertNotIn("v5", str(config.OUTPUT_DIR).lower())

    def test_add_strength_features_marks_early_weakness_downtrend(self):
        prepare = load_module("10_prepare_data.py", "v6_prepare_for_test")
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        rows = []
        for i, date in enumerate(dates):
            close_qfq = 100.0 - i
            rows.append({
                "ts_code": "000001.SZ",
                "trade_date": date,
                "close_qfq": close_qfq,
                "bbi_qfq": close_qfq + 5.0,
                "close": close_qfq,
                "up_limit": close_qfq * 1.1,
                "down_limit": close_qfq * 0.9,
                "turnover_rate": 1.0,
                "volume_ratio": 1.0,
                "is_lhb": 0,
                "amount": 100000.0,
                "circ_mv": 1000000.0,
            })
        panel = pd.DataFrame(rows)

        result = prepare.add_strength_features(panel)

        self.assertIn("ma20_qfq", result.columns)
        self.assertIn("ma20_slope_10", result.columns)
        self.assertIn("early_weakness_downtrend", result.columns)
        self.assertTrue(bool(result.iloc[-1]["early_weakness_downtrend"]))

    def test_score_candidates_filters_early_weakness_downtrend(self):
        backtest = load_module("20_run_backtest.py", "v6_backtest_for_test")
        base = {
            "is_eligible": True,
            "high_pos_21": 0.8,
            "high_pos_63": 0.8,
            "range_pos_63": 0.5,
            "recent_limit_down_20": 0,
            "recent_limit_up_20": 0,
            "recent_limit_up_63": 0,
            "turnover_rate_ma20": 1.0,
            "turnover_rate_max20": 1.0,
            "volume_ratio_max20": 1.0,
            "lhb_count_20": 0,
            "hot_money_risk_hits": 0,
            "above_ratio_63": 0.7,
            "above_ratio_126": 0.7,
            "ret_21": -0.05,
            "ret_63": 0.1,
            "ret_126": 0.1,
            "avg_distance_63": 0.02,
            "volatility_63": 0.02,
            "amount_ma20": 100000.0,
            "early_weakness_downtrend": False,
        }
        allowed = dict(base, ts_code="000001.SZ", name="allowed")
        blocked = dict(base, ts_code="000002.SZ", name="blocked", early_weakness_downtrend=True)
        diagnostics = {}

        scored = backtest.score_candidates(pd.DataFrame([allowed, blocked]), diagnostics=diagnostics)

        self.assertEqual(scored["ts_code"].tolist(), ["000001.SZ"])
        self.assertEqual(diagnostics.get("downtrend_filter_candidate_blocks"), 1)

    def test_score_candidates_scores_before_downtrend_filter(self):
        backtest = load_module("20_run_backtest.py", "v6_backtest_score_order_for_test")
        base = {
            "is_eligible": True,
            "high_pos_21": 0.8,
            "high_pos_63": 0.8,
            "range_pos_63": 0.5,
            "recent_limit_down_20": 0,
            "recent_limit_up_20": 0,
            "recent_limit_up_63": 0,
            "turnover_rate_ma20": 1.0,
            "turnover_rate_max20": 1.0,
            "volume_ratio_max20": 1.0,
            "lhb_count_20": 0,
            "hot_money_risk_hits": 0,
            "ret_21": -0.05,
            "ret_126": 0.1,
            "amount_ma20": 100000.0,
        }
        allowed = dict(
            base,
            ts_code="000001.SZ",
            name="allowed",
            above_ratio_63=0.9,
            above_ratio_126=0.9,
            ret_63=0.4,
            avg_distance_63=0.1,
            volatility_63=0.01,
            early_weakness_downtrend=False,
        )
        blocked = dict(
            base,
            ts_code="000002.SZ",
            name="blocked",
            above_ratio_63=0.6,
            above_ratio_126=0.6,
            ret_63=0.05,
            avg_distance_63=0.01,
            volatility_63=0.05,
            early_weakness_downtrend=True,
        )

        scored = backtest.score_candidates(pd.DataFrame([allowed, blocked]))

        self.assertEqual(scored["ts_code"].tolist(), ["000001.SZ"])
        self.assertGreater(float(scored.iloc[0]["score"]), 0.9)


if __name__ == "__main__":
    unittest.main()

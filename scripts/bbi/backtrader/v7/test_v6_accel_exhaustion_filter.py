import importlib.util
from pathlib import Path
import sys
import unittest

import pandas as pd


V6_DIR = Path(__file__).resolve().parent


def load_v6_module(module_name, filename):
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(V6_DIR))
        spec = importlib.util.spec_from_file_location(module_name, V6_DIR / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_path


prepare = load_v6_module("v6_prepare_for_accel_test", "10_prepare_data.py")
config = load_v6_module("v6_config_for_accel_test", "config.py")


class V6AccelExhaustionFilterTests(unittest.TestCase):
    def make_panel(self, close, amount=None):
        if amount is None:
            amount = [1000.0] * len(close)
        rows = len(close)
        return pd.DataFrame({
            "ts_code": ["000001.SZ"] * rows,
            "trade_date": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "close_qfq": close,
            "bbi_qfq": [90.0] * rows,
            "close": close,
            "up_limit": [200.0] * rows,
            "down_limit": [1.0] * rows,
            "turnover_rate": [2.0] * rows,
            "volume_ratio": [1.0] * rows,
            "is_lhb": [False] * rows,
            "amount": amount,
            "circ_mv": [200000.0] * rows,
        })

    def test_add_strength_features_creates_accel_exhaustion_flags(self):
        close = [100.0] * 30 + [106.0, 112.0, 119.0, 127.0, 136.0, 132.0, 127.0, 122.0, 117.0, 112.0]
        amount = [1000.0] * 30 + [1100.0, 1200.0, 1400.0, 1600.0, 2000.0, 2200.0, 2300.0, 2300.0, 2200.0, 2100.0]

        enriched = prepare.add_strength_features(self.make_panel(close, amount))

        self.assertIn("up_accel_exhaustion", enriched.columns)
        self.assertIn("bear_down_accel_risk", enriched.columns)
        self.assertIn("accel_exhaustion_forbid_buy", enriched.columns)
        self.assertTrue(bool(enriched.iloc[-1]["up_accel_exhaustion"]))
        self.assertTrue(bool(enriched.iloc[-1]["accel_exhaustion_forbid_buy"]))

    def test_accel_exhaustion_forbid_buy_preserves_early_weakness_rule(self):
        close = [120.0] * 30 + [118.0, 116.0, 114.0, 111.0, 108.0, 104.0, 100.0, 95.0, 90.0, 84.0]

        enriched = prepare.add_strength_features(self.make_panel(close))

        self.assertTrue(bool(enriched.iloc[-1]["early_weakness_downtrend"]))
        self.assertTrue(bool(enriched.iloc[-1]["accel_exhaustion_forbid_buy"]))

    def test_v6_default_filter_uses_combined_accel_exhaustion_column(self):
        self.assertEqual(config.DOWNTREND_FILTER_NAME, "accel_exhaustion_forbid_buy")


if __name__ == "__main__":
    unittest.main()

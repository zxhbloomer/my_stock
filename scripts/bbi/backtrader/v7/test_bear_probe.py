import importlib.util
from pathlib import Path
import sys
import unittest

import pandas as pd


MODULE_PATH = Path(__file__).parent / "20_run_backtest.py"


def load_module():
    sys.path.insert(0, str(MODULE_PATH.parent))
    spec = importlib.util.spec_from_file_location("v6_run_backtest_for_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class BearProbeTests(unittest.TestCase):
    def test_market_probe_requires_bear_regime_and_breadth_repair(self):
        mod = load_module()
        dates = pd.date_range("2020-01-01", periods=8, freq="D")
        market_regime = pd.DataFrame(
            {
                "trade_date": dates,
                "regime": ["bear"] * 8,
                "close": [100, 99, 98, 97, 96, 97, 98, 99],
                "breadth_above_bbi": [0.22, 0.23, 0.24, 0.25, 0.26, 0.31, 0.37, 0.46],
            }
        )

        result = mod.add_bear_probe_market_features(market_regime, min_breadth=0.35, breadth_improve=0.08)

        self.assertFalse(bool(result.loc[dates[4], "bear_probe_market_ok"]))
        self.assertTrue(bool(result.loc[dates[7], "bear_probe_market_ok"]))

    def test_probe_amount_uses_config_fraction_and_cap(self):
        mod = load_module()

        amount = mod.calc_bear_probe_target_amount(
            normal_first_step=80_000.0,
            cash=500_000.0,
            current_probe_exposure=50_000.0,
        )

        self.assertEqual(amount, 12_000.0)
        capped = mod.calc_bear_probe_target_amount(
            normal_first_step=80_000.0,
            cash=500_000.0,
            current_probe_exposure=70_000.0,
        )
        self.assertEqual(capped, 5_000.0)


if __name__ == "__main__":
    unittest.main()

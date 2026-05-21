import importlib.util
from pathlib import Path
import sys
import unittest

import pandas as pd


MODULE_PATH = Path(__file__).parent / "20_run_backtest.py"


def load_module():
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(MODULE_PATH.parent))
        spec = importlib.util.spec_from_file_location("v7_weak_lowvol_for_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_path


class WeakLowvolMomTests(unittest.TestCase):
    def sample_candidates(self):
        return pd.DataFrame(
            {
                "ts_code": ["good", "high_vol", "negative_21", "limit_down"],
                "ret_21": [0.04, 0.05, -0.01, 0.03],
                "ret_63": [0.12, 0.15, 0.10, 0.14],
                "volatility_63": [0.12, 0.48, 0.13, 0.11],
                "recent_limit_down_20": [0, 0, 0, 1],
                "hot_money_risk_hits": [0, 0, 0, 0],
                "score": [1.0, 0.9, 0.8, 0.7],
            }
        )

    def test_healthy_market_does_not_filter_candidates(self):
        mod = load_module()
        candidates = self.sample_candidates()

        filtered = mod.apply_weak_lowvol_mom_filter(
            candidates,
            market_regime_name="bull",
            regime_snapshot={"market_dd_252": -0.02, "breadth_above_bbi": 0.7},
            diagnostics={},
        )

        self.assertEqual(filtered["ts_code"].tolist(), candidates["ts_code"].tolist())

    def test_weak_market_keeps_only_lowvol_positive_momentum_candidates(self):
        mod = load_module()

        filtered = mod.apply_weak_lowvol_mom_filter(
            self.sample_candidates(),
            market_regime_name="neutral",
            regime_snapshot={"market_dd_252": -0.12, "breadth_above_bbi": 0.5},
            diagnostics={},
        )

        self.assertEqual(filtered["ts_code"].tolist(), ["good"])

    def test_positive_return_ratio_ignores_missing_first_return(self):
        mod = load_module()
        panel = pd.DataFrame(
            {
                "ts_code": ["A"] * 5,
                "trade_date": pd.date_range("2020-01-01", periods=5, freq="D"),
                "close_qfq": [10.0, 11.0, 10.0, 12.0, 24.0],
            }
        )

        enriched = mod.add_positive_return_ratio(panel, window=3, min_periods=1)

        self.assertEqual(enriched["positive_ret_ratio_63"].round(4).tolist(), [0.0, 1.0, 0.5, 0.6667, 0.6667])

    def test_no_refined_probe_experiment_logic_was_merged(self):
        source = MODULE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("BEAR_PROBE_LOWVOL_CASE", source)
        self.assertNotIn("probe_05_strict", source)
        self.assertNotIn("probe_10_strict", source)
        self.assertNotIn("probe_15_strict", source)
        self.assertNotIn("probe_10_ultra", source)
        self.assertNotIn("probe_05", source)
        self.assertNotIn("probe_10", source)
        self.assertNotIn("probe_15", source)
        self.assertNotIn("refined_probe", source)

    def test_weak_filter_updates_diagnostics(self):
        mod = load_module()
        diagnostics = {}

        filtered = mod.apply_weak_lowvol_mom_filter(
            self.sample_candidates(),
            market_regime_name="neutral",
            regime_snapshot={"market_dd_252": -0.12, "breadth_above_bbi": 0.5},
            diagnostics=diagnostics,
        )

        self.assertEqual(filtered["ts_code"].tolist(), ["good"])
        self.assertEqual(diagnostics["weak_lowvol_mom_signal_days"], 1)
        self.assertEqual(diagnostics["weak_lowvol_mom_candidate_blocks"], 3)


if __name__ == "__main__":
    unittest.main()

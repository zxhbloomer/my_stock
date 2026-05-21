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


prepare = load_v6_module("v6_prepare_for_pit_universe_test", "10_prepare_data.py")


class V6PointInTimeUniverseTests(unittest.TestCase):
    def test_universe_keeps_stock_that_delists_after_backtest_start(self):
        stocks = pd.DataFrame({
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
            "name": ["正常A", "退市B", "旧退市C"],
            "list_date": ["2010-01-01", "2010-01-01", "2010-01-01"],
            "delist_date": [None, "2019-06-01", "2016-12-31"],
            "market": ["主板", "主板", "主板"],
            "exchange": ["SZSE", "SZSE", "SZSE"],
            "list_status": ["L", "D", "D"],
        })

        filtered = prepare.filter_point_in_time_universe(
            stocks,
            start_date="2018-01-01",
            end_date="2018-12-31",
            requested_codes=set(),
        )

        self.assertEqual(set(filtered["ts_code"]), {"000001.SZ", "000002.SZ"})

    def test_eligibility_blocks_rows_after_delist_date(self):
        panel = pd.DataFrame({
            "ts_code": ["000002.SZ", "000002.SZ"],
            "trade_date": pd.to_datetime(["2019-05-31", "2019-06-02"]),
            "list_date": pd.to_datetime(["2010-01-01", "2010-01-01"]),
            "delist_date": pd.to_datetime(["2019-06-01", "2019-06-01"]),
            "is_listed_long_enough": [True, True],
            "is_liquid": [True, True],
            "is_st": [False, False],
            "is_suspended": [False, False],
            "above_ratio_126": [0.8, 0.8],
        })

        eligible = prepare.compute_point_in_time_eligibility(panel)

        self.assertTrue(bool(eligible.iloc[0]))
        self.assertFalse(bool(eligible.iloc[1]))


if __name__ == "__main__":
    unittest.main()

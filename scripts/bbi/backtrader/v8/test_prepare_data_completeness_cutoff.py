import datetime
import importlib.util
from pathlib import Path
import sys
import unittest


V8_DIR = Path(__file__).resolve().parent


def load_v8_module(module_name, filename):
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(V8_DIR))
        spec = importlib.util.spec_from_file_location(module_name, V8_DIR / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_path


prepare = load_v8_module("v8_prepare_for_completeness_cutoff_test", "10_prepare_data.py")


class V8CompletenessCutoffTests(unittest.TestCase):
    def test_before_21_excludes_today_from_required_completeness(self):
        now = datetime.datetime(2026, 5, 27, 20, 59, 0)

        end_date = prepare.resolve_completeness_end_date("2026-05-27", now=now)

        self.assertEqual(end_date, "2026-05-26")

    def test_at_21_includes_today_in_required_completeness(self):
        now = datetime.datetime(2026, 5, 27, 21, 0, 0)

        end_date = prepare.resolve_completeness_end_date("2026-05-27", now=now)

        self.assertEqual(end_date, "2026-05-27")

    def test_before_21_keeps_historical_end_date(self):
        now = datetime.datetime(2026, 5, 27, 20, 59, 0)

        end_date = prepare.resolve_completeness_end_date("2026-05-20", now=now)

        self.assertEqual(end_date, "2026-05-20")


if __name__ == "__main__":
    unittest.main()

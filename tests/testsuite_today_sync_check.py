import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_DIR = ROOT / "data" / "手动执行" / "20260425"
CHECK_SCRIPT = SYNC_DIR / "run_check_today_sync.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_today_sync", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TodaySyncCheckTests(unittest.TestCase):
    def test_required_daily_table_missing_today_generates_rerun_command(self):
        mod = load_module()

        result = mod.evaluate_table(
            spec=mod.TableSpec("014_daily.py", "014_daily", "trade_date", "required_daily"),
            target_date="20260512",
            today_count=0,
            previous_count=5300,
            table_exists=True,
        )

        self.assertEqual(result.status, "missing")
        self.assertEqual(result.command, "python -X utf8 014_daily.py --start 20260512 --end 20260512")

    def test_required_daily_table_low_count_generates_rerun_command(self):
        mod = load_module()

        result = mod.evaluate_table(
            spec=mod.TableSpec("027_daily_basic.py", "027_daily_basic", "trade_date", "required_daily"),
            target_date="20260512",
            today_count=100,
            previous_count=5000,
            table_exists=True,
        )

        self.assertEqual(result.status, "low_count")
        self.assertEqual(result.command, "python -X utf8 027_daily_basic.py --start 20260512 --end 20260512")

    def test_static_and_sparse_tables_do_not_generate_required_daily_commands(self):
        mod = load_module()

        static_result = mod.evaluate_table(
            spec=mod.TableSpec("001_stock_basic.py", "001_stock_basic", None, "static"),
            target_date="20260512",
            today_count=5000,
            previous_count=0,
            table_exists=True,
        )
        sparse_result = mod.evaluate_table(
            spec=mod.TableSpec("088_top_list.py", "088_top_list", "trade_date", "sparse"),
            target_date="20260512",
            today_count=0,
            previous_count=20,
            table_exists=True,
        )

        self.assertIsNone(static_result.command)
        self.assertIsNone(sparse_result.command)

    def test_margin_detail_allows_documented_name_column_in_database(self):
        script = (SYNC_DIR / "074_margin_detail.py").read_text(encoding="utf-8")

        self.assertIn("name        VARCHAR(50)", script)
        self.assertIn('allow_extra_cols={"name"}', script)


if __name__ == "__main__":
    unittest.main()

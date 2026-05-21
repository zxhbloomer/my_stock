import unittest
import importlib.util
from pathlib import Path

from data.ui.sync_service import SyncService


ROOT = Path(__file__).resolve().parents[1]
SYNC_DIR = ROOT / "data" / "手动执行" / "20260425"


class Spec:
    def __init__(self, script, table, date_col, category):
        self.script = script
        self.table = table
        self.date_col = date_col
        self.category = category


class SmartIncrementalTests(unittest.TestCase):
    def test_run_all_scripts_are_covered_by_check_specs(self):
        run_all_spec = importlib.util.spec_from_file_location("sync_run_all_for_test", SYNC_DIR / "run_all.py")
        run_all = importlib.util.module_from_spec(run_all_spec)
        run_all_spec.loader.exec_module(run_all)

        check_spec = importlib.util.spec_from_file_location("sync_check_for_test", SYNC_DIR / "run_check_today_sync.py")
        check = importlib.util.module_from_spec(check_spec)
        check_spec.loader.exec_module(check)

        configured = {spec.script for spec in check.TABLE_SPECS}
        missing = [script for script in run_all.SCRIPTS if script not in configured]

        self.assertEqual(missing, [])

    def test_full_scan_start_respects_script_default_start(self):
        self.assertEqual(SyncService._effective_full_start("20100101", "20180101"), "20180101")
        self.assertEqual(SyncService._effective_full_start("20100101", "19910102"), "20100101")
        self.assertEqual(SyncService._effective_full_start("20100101", None), "20100101")

    def test_required_daily_issue_builds_range_command_from_missing_dates(self):
        spec = Spec("014_daily.py", "014_daily", "trade_date", "required_daily")

        issue = SyncService._build_smart_issue(
            spec=spec,
            status="missing",
            start_date="20100101",
            end_date="20260521",
            missing_dates=["20260519", "20260520", "20260521"],
            low_count_dates=[],
            today_count=None,
            previous_count=None,
            syncable=True,
            message="缺失 3 个交易日",
        )

        self.assertEqual(issue["script_name"], "014_daily.py")
        self.assertEqual(issue["missing_count"], 3)
        self.assertEqual(issue["date_range"], "20260519 ~ 20260521")
        self.assertEqual(issue["run_start"], "20260519")
        self.assertEqual(issue["run_end"], "20260521")
        self.assertEqual(issue["command"], "python -X utf8 014_daily.py --start 20260519 --end 20260521")

    def test_static_issue_builds_command_without_date_args(self):
        spec = Spec("001_stock_basic.py", "001_stock_basic", None, "static")

        issue = SyncService._build_smart_issue(
            spec=spec,
            status="empty_static",
            start_date="20100101",
            end_date="20260521",
            missing_dates=[],
            low_count_dates=[],
            today_count=0,
            previous_count=None,
            syncable=True,
            message="静态表为空",
        )

        self.assertEqual(issue["date_range"], "-")
        self.assertEqual(issue["run_start"], "")
        self.assertEqual(issue["run_end"], "")
        self.assertEqual(issue["command"], "python -X utf8 001_stock_basic.py")


if __name__ == "__main__":
    unittest.main()

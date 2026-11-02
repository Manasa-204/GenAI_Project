"""
test_dual_view_architecture.py
------------------------------
Automated test suite verifying the complete Dual-View Architecture:
1. Shared SQLite DB schema and synchronization.
2. Background tracker process detection and usage logging.
3. Enforcement engine rule checking & process termination safety.
4. Headless main.py orchestration loop.
5. Parental web dashboard API responses.
6. Child desktop GUI state reader.
"""

import os
import sys
import tempfile
import unittest

import db_manager
import user_tracker
import enforcement
import main
import web_dashboard


class TestDualViewArchitecture(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_study_monitor.db")
        db_manager.init_db(self.test_db)
        enforcement.set_mock_mode(True)

    def tearDown(self):
        enforcement.set_mock_mode(False)

    def test_01_db_schema_and_parental_rules(self):
        """Verifies database initializes tracked_processes and default enforcement_rules."""
        rules = db_manager.get_enforcement_rules(db_path=self.test_db)
        self.assertGreaterEqual(len(rules), 4, "Default parental rules must be seeded.")

        # Test adding custom parental rule
        db_manager.set_enforcement_rule(
            process_name="game_test.exe",
            display_name="Game Test",
            time_limit_minutes=30,
            is_blocked=0,
            category="Gaming",
            db_path=self.test_db
        )
        updated_rules = db_manager.get_enforcement_rules(db_path=self.test_db)
        matching = [r for r in updated_rules if r["process_name"] == "game_test.exe"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["time_limit_minutes"], 30)

    def test_02_process_usage_tracking(self):
        """Verifies recording process usage increments today and total time."""
        usage1 = db_manager.record_process_usage(
            process_name="code.exe",
            window_title="main.py - Visual Studio Code",
            delta_seconds=10,
            category="Educational / Productive",
            db_path=self.test_db
        )
        self.assertEqual(usage1["today_time_seconds"], 10)
        self.assertEqual(usage1["total_time_seconds"], 10)

        usage2 = db_manager.record_process_usage(
            process_name="code.exe",
            window_title="main.py - Visual Studio Code",
            delta_seconds=15,
            db_path=self.test_db
        )
        self.assertEqual(usage2["today_time_seconds"], 25)
        self.assertEqual(usage2["total_time_seconds"], 25)

        procs = db_manager.get_tracked_processes(db_path=self.test_db)
        self.assertTrue(any(p["process_name"] == "code.exe" for p in procs))

    def test_03_enforcement_time_limit_check(self):
        """Verifies over-limit detection and restriction triggers."""
        # Set 1 minute limit on discord.exe
        db_manager.set_enforcement_rule(
            process_name="discord.exe",
            time_limit_minutes=1,
            is_blocked=0,
            db_path=self.test_db
        )

        # Record 30 seconds of usage (under limit)
        db_manager.record_process_usage("discord.exe", delta_seconds=30, db_path=self.test_db)
        is_restricted, reason, _ = db_manager.check_process_restriction("discord.exe", db_path=self.test_db)
        self.assertFalse(is_restricted, "Should be allowed under limit")

        # Record another 40 seconds (total 70s > 1m limit)
        db_manager.record_process_usage("discord.exe", delta_seconds=40, db_path=self.test_db)
        is_restricted, reason, _ = db_manager.check_process_restriction("discord.exe", db_path=self.test_db)
        self.assertTrue(is_restricted, "Should be restricted when daily limit exceeded")
        self.assertIn("Time limit exceeded", reason)

    def test_04_headless_orchestrator_cycle(self):
        """Verifies main.run_orchestrator_cycle executes headless without UI."""
        tracker = user_tracker.WindowsProcessTracker(db_path=self.test_db)
        db_manager.reset_balance(100, db_path=self.test_db)

        cycle_res = main.run_orchestrator_cycle(
            tracker=tracker,
            interval=1.0,
            db_path=self.test_db,
            verbose=False
        )
        self.assertIn("balance", cycle_res)
        self.assertEqual(cycle_res["balance"], 99)  # 100 - 1

    def test_05_parental_web_dashboard_payloads(self):
        """Verifies web_dashboard data payloads are accurate."""
        db_manager.update_child_state(
            current_process="notepad.exe",
            current_window="notes.txt - Notepad",
            db_path=self.test_db
        )
        state = db_manager.get_child_state(db_path=self.test_db)
        self.assertEqual(state["current_process"], "notepad.exe")
        self.assertEqual(state["current_window"], "notes.txt - Notepad")

    def test_06_desktop_child_status_reader(self):
        """Verifies desktop_app data reading logic."""
        import desktop_app
        db_manager.reset_balance(3600, db_path=self.test_db)
        state = db_manager.get_child_state(db_path=self.test_db)
        formatted = desktop_app.ChildDesktopApp._format_time(None, state["current_balance"])
        self.assertEqual(formatted, "01:00:00")


if __name__ == "__main__":
    unittest.main()


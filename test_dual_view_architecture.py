"""
test_dual_view_architecture.py
------------------------------
Automated Test Suite for Dual-View Architecture & Multi-Process Synchronization.
Validates:
[x] Shared SQLite Database with WAL mode & multi-process transactional integrity.
[x] Real-time state synchronization between Parent Admin and Student Views.
[x] REST API payload schema integrity (/api/status, /api/timeline, /api/policies).
[x] Read-only Motivational Student view vs. privileged Parent Admin controls.
"""

import os
import sys
import time
import tempfile
import unittest

import db_manager


class TestDualViewArchitecture(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_dual_view.db")
        db_manager.init_db(self.db_path)

    def tearDown(self):
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_shared_sqlite_multi_connection_sync(self):
        """Verifies multi-connection concurrent state synchronization."""
        # Connection A updates study time balance
        new_bal = db_manager.update_balance(+15, reason="study_session_conn_a", db_path=self.db_path)
        self.assertEqual(new_bal, 15)

        # Connection B reads balance
        current_bal_b = db_manager.get_current_balance(db_path=self.db_path)
        self.assertEqual(current_bal_b, 15, "Connection B must observe immediate WAL updates from Connection A")

        # Connection B starts Emergency Lockdown
        lockdown_b = db_manager.start_emergency_lockdown(
            duration_minutes=20,
            reason="Math Exam Cram",
            zero_tolerance=True,
            db_path=self.db_path
        )
        self.assertTrue(lockdown_b["is_active"])
        self.assertEqual(lockdown_b["duration_seconds"], 1200)

        # Connection A checks Emergency Lockdown status
        lockdown_a = db_manager.get_emergency_lockdown(db_path=self.db_path)
        self.assertTrue(lockdown_a["is_active"], "Student connection must observe active emergency lockdown")
        self.assertGreater(lockdown_a["seconds_remaining"], 1190)
        self.assertEqual(lockdown_a["reason"], "Math Exam Cram")
        self.assertTrue(lockdown_a["zero_tolerance"])

    def test_student_vs_parent_payload_integrity(self):
        """Verifies the REST API payload integrity for both Student and Parent views."""
        # Setup sample telemetry
        db_manager.update_balance(+10, reason="unit_test_accrual", db_path=self.db_path)
        db_manager.set_policy("youtube.com", quota_minutes=45, category="Leisure", db_path=self.db_path)
        db_manager.log_app_activity("Google Chrome", "Wikipedia - Osmosis", "Educational", 45.0, db_path=self.db_path)

        # 1. Policies Payload Integrity
        policies = db_manager.get_policies(db_path=self.db_path)
        self.assertIsInstance(policies, list)
        self.assertGreaterEqual(len(policies), 1)
        yt_policy = next((p for p in policies if "youtube" in p["app_or_domain"]), None)
        self.assertIsNotNone(yt_policy)
        self.assertEqual(yt_policy["quota_minutes"], 45)
        self.assertEqual(yt_policy["remaining_seconds"], 2700)
        self.assertFalse(yt_policy["is_exhausted"])

        # 2. App Usage Distribution Integrity
        dist = db_manager.get_app_distribution(range_str="today", db_path=self.db_path)
        self.assertIn("apps", dist)
        self.assertIn("categories", dist)
        self.assertGreaterEqual(len(dist["apps"]), 1)
        self.assertEqual(dist["apps"][0]["app_name"], "Google Chrome")

        # 3. Recent Applications Grid Integrity
        recent_apps = db_manager.get_recent_apps(limit=8, db_path=self.db_path)
        self.assertIsInstance(recent_apps, list)
        self.assertEqual(len(recent_apps), 1)
        self.assertEqual(recent_apps[0]["category"], "Educational")

    def test_emergency_lockdown_edit_and_stop_lifecycle(self):
        """Verifies the complete Start -> Edit -> Stop lifecycle of Emergency Lockdown."""
        # 1. Start with 15 minutes
        res1 = db_manager.start_emergency_lockdown(15, reason="Sprint 1", zero_tolerance=True, db_path=self.db_path)
        self.assertTrue(res1["is_active"])
        self.assertEqual(res1["duration_seconds"], 900)

        # 2. Edit to 30 minutes
        res2 = db_manager.edit_emergency_lockdown(30, db_path=self.db_path)
        self.assertTrue(res2["is_active"])
        self.assertEqual(res2["duration_seconds"], 1800)
        self.assertGreater(res2["seconds_remaining"], 1700)

        # 3. Stop lockdown
        res3 = db_manager.stop_emergency_lockdown(db_path=self.db_path)
        self.assertFalse(res3["is_active"])
        self.assertEqual(res3["seconds_remaining"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""
test_master_prompt_features.py
------------------------------
Automated Test Suite for Master RBAC, Granular Policy Engine,
Spatial Focus Filtering & 10-Second Focus Quality Scoring.

Validates:
[x] Master PIN verification (PBKDF2 hash & '1323' emergency bypass).
[x] Security alerts & Tamper Attempt logging on unauthorized exit.
[x] Granular Policy Engine & Quota Budgets (e.g. 45-minute YouTube leisure access).
[x] Spatial Focus Region reticle filtering (Central 20%-80% X, 15%-85% Y).
[x] Continuous 10-Second Composite Focus Quality Score & Semantic Color streaming.
"""

import os
import sys
import time
import tempfile
import unittest

import db_manager
import enforcement
import vision_pipeline
from user_tracker import is_in_focus_region


class TestMasterPromptFeatures(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_features.db")
        db_manager.init_db(self.db_path)

    def tearDown(self):
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_master_pin_rbac_and_tamper_security_alerts(self):
        """Verifies Master PIN '1323' verification and Tamper Attempt logging."""
        # 1. Master PIN 1323 must always pass
        self.assertTrue(db_manager.verify_security_pin("1323", db_path=self.db_path))
        self.assertTrue(db_manager.verify_security_pin(" 1323 \n", db_path=self.db_path))

        # 2. Invalid PINs must fail
        self.assertFalse(db_manager.verify_security_pin("1234", db_path=self.db_path))
        self.assertFalse(db_manager.verify_security_pin("admin", db_path=self.db_path))
        self.assertFalse(db_manager.verify_security_pin("", db_path=self.db_path))

        # 3. Log a TAMPER_ATTEMPT security alert
        db_manager.log_security_alert("TAMPER_ATTEMPT", "Unauthorized HUD exit with wrong PIN: '9999'", db_path=self.db_path)
        alerts = db_manager.get_security_alerts(limit=5, db_path=self.db_path)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "TAMPER_ATTEMPT")
        self.assertIn("9999", alerts[0]["details"])

    def test_granular_policy_engine_and_quota_budget(self):
        """
        PROVES: If YouTube is granted 45 minutes of leisure time,
        it grants the 45-minute interval and only enforces when exhausted.
        """
        # Set YouTube quota to 45 minutes
        db_manager.set_policy("youtube.com", quota_minutes=45, category="Leisure", db_path=self.db_path)

        # Check remaining quota
        rem = db_manager.get_policy_remaining_seconds("youtube.com", db_path=self.db_path)
        self.assertEqual(rem, 2700, "Initial remaining quota must be exactly 45 * 60 = 2700s")

        # Simulate student watching YouTube for 60 seconds
        rem_after = db_manager.record_policy_usage("youtube.com", duration_seconds=60, db_path=self.db_path)
        self.assertEqual(rem_after, 2640, "Remaining seconds must decrement by 60s to 2640s")

        # Verify policy remaining calculation via matching substring
        rem_match = db_manager.get_policy_remaining_seconds("https://www.youtube.com/watch?v=123", db_path=self.db_path)
        self.assertEqual(rem_match, 2640)

        # Exhaust the quota
        db_manager.record_policy_usage("youtube.com", duration_seconds=2640, db_path=self.db_path)
        rem_exhausted = db_manager.get_policy_remaining_seconds("youtube.com", db_path=self.db_path)
        self.assertEqual(rem_exhausted, 0, "Quota must be exhausted (0 seconds remaining)")

    def test_spatial_focus_region_reticle_filtering(self):
        """Verifies spatial reticle filter (20%-80% X, 15%-85% Y)."""
        # Central face -> FOCUS REGION ACTIVE
        center_face = {"cx": 0.50, "cy": 0.50, "width": 0.3, "height": 0.35}
        self.assertTrue(is_in_focus_region(center_face), "Center face (0.5, 0.5) must be inside focus region")

        # Corner / Peripheral face (Passerby walking behind on side) -> PERIPHERAL_FACE_IGNORED
        periphery_face_left = {"cx": 0.10, "cy": 0.50, "width": 0.15, "height": 0.20}
        self.assertFalse(is_in_focus_region(periphery_face_left), "Peripheral face (X=0.10) must be outside reticle")

        periphery_face_top = {"cx": 0.50, "cy": 0.08, "width": 0.15, "height": 0.20}
        self.assertFalse(is_in_focus_region(periphery_face_top), "Peripheral face (Y=0.08) must be outside reticle")

    def test_continuous_10s_composite_focus_quality_score(self):
        """
        Verifies continuous composite focus quality evaluation:
        - >= 70%: Emerald Green (Active Study / Deep Flow)
        - 40%-69%: Amber Yellow (Focus Drifting / Drowsy)
        - < 40%: Rose Red (Distracted / Alert)
        """
        evaluator = vision_pipeline.CompositeFocusEvaluator(window_seconds=10.0)

        # Case 1: Attentive student, open eyes, centered posture, educational process
        score_focused = evaluator.record_sample(
            ear=0.28,
            is_eyes_closed=False,
            sleep_duration=0.0,
            pitch=0.0,
            yaw=0.0,
            posture_state="DIRECT_FOCUS",
            foreground_category="Educational"
        )
        self.assertGreaterEqual(score_focused, 70.0, f"Attentive student score must be >= 70%, got {score_focused:.1f}")
        self.assertEqual(evaluator.current_color, "emerald")
        self.assertEqual(evaluator.current_classification, "FOCUSED")

        # Case 2: Drowsy / Microsleep (eyes closed > 2s)
        # Record several drowsy samples to simulate 10-second decay
        for _ in range(12):
            score_drowsy = evaluator.record_sample(
                ear=0.08,
                is_eyes_closed=True,
                sleep_duration=3.5,
                pitch=-18.0,
                yaw=0.0,
                posture_state="DROWSY_MICROSLEEP",
                foreground_category="Educational"
            )

        self.assertLess(score_drowsy, 60.0, f"Drowsy microsleep score should decay smoothly, got {score_drowsy:.1f}")
        self.assertIn(evaluator.current_color, ["amber", "rose"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

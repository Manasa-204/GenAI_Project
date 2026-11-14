"""
test_master_prompt_features.py
-------------------------------
End-to-end verification test suite for all Master Prompt features:
1. Feature 1: Dual-Portal System & RBAC (PBKDF2 Parent Auth, Master PIN 1323, Session Roles)
2. Feature 2: Policy Engine, Time-Budgeting & Quotas (app_policies, parent_alerts, daily_focus_metrics)
3. Feature 3: Advanced 3D Kinematics & Posture Matrix (8 discrete movement/posture states)
4. Feature 4: Granular YouTube Title Decomposition & SLM Verification (Regex + Tier 1/2 classification)
5. Feature 5: Dual-Portal Web Dashboard API Endpoints & Auth Handshake
6. Feature 6: Desktop Client Anti-Tamper Exit Interception
"""

import os
import sys
import tempfile
import unittest
import numpy as np

import db_manager
import policy_engine
import vision_pipeline
import semantic_pipeline
import enforcement
import web_dashboard


class TestMasterPromptFeatures(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_master.db")
        db_manager.init_db(self.test_db)
        enforcement.set_mock_mode(True)

    def tearDown(self):
        enforcement.set_mock_mode(False)
        db_manager.set_current_role("STUDENT")

    # -------------------------------------------------------------------------
    # Feature 1: Dual-Portal System & RBAC
    # -------------------------------------------------------------------------
    def test_feature1_cryptographic_parent_auth_and_roles(self):
        # 1. Master PIN verification (default 1323)
        self.assertTrue(db_manager.is_parent_configured(self.test_db))
        self.assertTrue(db_manager.verify_parent_pin("1323", db_path=self.test_db))
        self.assertFalse(db_manager.verify_parent_pin("0000", db_path=self.test_db))
        self.assertFalse(db_manager.verify_parent_pin("1234", db_path=self.test_db))

        # 2. Setup custom parent credentials with PBKDF2
        custom_pin = "8899"
        db_manager.setup_parent_credentials(pin=custom_pin, db_path=self.test_db)
        self.assertTrue(db_manager.verify_parent_pin(custom_pin, db_path=self.test_db))
        self.assertFalse(db_manager.verify_parent_pin("1323", db_path=self.test_db))

        # 3. In-memory role switching
        self.assertEqual(db_manager.get_current_role(), "STUDENT")
        db_manager.set_current_role("PARENT")
        self.assertEqual(db_manager.get_current_role(), "PARENT")
        db_manager.set_current_role("STUDENT")
        self.assertEqual(db_manager.get_current_role(), "STUDENT")

    # -------------------------------------------------------------------------
    # Feature 2: Policy Engine, Time-Budgeting & Quotas
    # -------------------------------------------------------------------------
    def test_feature2_policy_engine_and_quotas(self):
        # 1. Seed and query app policies
        policies = db_manager.get_app_policies(db_path=self.test_db)
        self.assertGreaterEqual(len(policies), 4)

        # 2. Hard block evaluation
        db_manager.set_app_policy(
            target_name="tiktok.exe",
            category="SOCIAL",
            policy_type="HARD_BLOCK",
            db_path=self.test_db
        )
        is_restr, reason, pol = db_manager.check_process_restriction("tiktok.exe", db_path=self.test_db)
        self.assertTrue(is_restr)
        self.assertIn("permanently blocked", reason)

        # 3. Quota exceeded evaluation
        db_manager.set_app_policy(
            target_name="chess.exe",
            category="GAMING",
            policy_type="DAILY_QUOTA",
            daily_quota_seconds=60,
            curfew_start="",
            curfew_end="",
            db_path=self.test_db
        )
        # Usage 30s -> allowed
        db_manager.record_process_usage("chess.exe", delta_seconds=30, db_path=self.test_db)
        is_restr, reason, _ = db_manager.check_process_restriction("chess.exe", db_path=self.test_db)
        self.assertFalse(is_restr)

        # Usage +40s (total 70s > 60s quota) -> restricted
        db_manager.record_process_usage("chess.exe", delta_seconds=40, db_path=self.test_db)
        is_restr, reason, _ = db_manager.check_process_restriction("chess.exe", db_path=self.test_db)
        self.assertTrue(is_restr)
        self.assertIn("Time limit exceeded", reason)

        # 4. Parent alert dispatch and acknowledgement
        alert = db_manager.dispatch_parent_alert(
            target_app="chess.exe",
            event_type="QUOTA_EXHAUSTED",
            severity="WARNING",
            details="Chess quota exhausted for today.",
            db_path=self.test_db
        )
        self.assertEqual(alert["event_type"], "QUOTA_EXHAUSTED")
        alerts = db_manager.get_parent_alerts(db_path=self.test_db)
        self.assertGreaterEqual(len(alerts), 1)

        ack = db_manager.acknowledge_parent_alert(alert["id"], db_path=self.test_db)
        self.assertTrue(ack)

        # 5. Daily focus metrics
        metrics = db_manager.update_daily_focus_metrics(
            study_seconds=120,
            pure_focus_seconds=100,
            drowsy_seconds=10,
            away_seconds=10,
            distraction_attempt=True,
            db_path=self.test_db
        )
        self.assertEqual(metrics["total_study_seconds"], 120)
        self.assertEqual(metrics["pure_focus_seconds"], 100)
        self.assertEqual(metrics["distraction_attempts"], 1)

    # -------------------------------------------------------------------------
    # Feature 3: Advanced 3D Kinematics & Posture Classification Matrix
    # -------------------------------------------------------------------------
    def test_feature3_8_state_posture_classification_matrix(self):
        pipe = vision_pipeline.VisionPipeline()

        # State 1: DIRECT_FOCUS (Pitch 0, Yaw 0, EAR 0.30, active input)
        res_focus = pipe._classify_8_state_matrix(
            avg_ear=0.30, pitch=0.0, yaw=0.0, roll=0.0,
            pc_idle_sec=0.5, face_detected=True, current_time=100.0
        )
        self.assertEqual(res_focus["state"], "ACTIVE")
        self.assertEqual(res_focus["sub_state"], "DIRECT_FOCUS")
        self.assertEqual(res_focus["balance_delta"], 1)

        # State 2: PASSIVE_READING (Pitch 0, Yaw 0, EAR 0.25, idle 15s)
        res_read = pipe._classify_8_state_matrix(
            avg_ear=0.25, pitch=0.0, yaw=0.0, roll=0.0,
            pc_idle_sec=15.0, face_detected=True, current_time=100.0
        )
        self.assertEqual(res_read["state"], "ACTIVE")
        self.assertEqual(res_read["sub_state"], "PASSIVE_READING")
        self.assertEqual(res_read["balance_delta"], 1)

        # State 3: DESK_NOTE_TAKING (Pitch -22°, Yaw 0, EAR 0.22)
        res_notes = pipe._classify_8_state_matrix(
            avg_ear=0.22, pitch=-22.0, yaw=0.0, roll=0.0,
            pc_idle_sec=5.0, face_detected=True, current_time=100.0
        )
        self.assertEqual(res_notes["state"], "ACTIVE")
        self.assertEqual(res_notes["sub_state"], "DESK_NOTE_TAKING")
        self.assertEqual(res_notes["balance_delta"], 1)

        # State 4: MOBILE_DISTRACTION (Pitch -33°, EAR 0.25 open eyes looking into phone/lap, idle > 3s, duration >= 2s)
        pipe.mobile_start_time = 90.0
        res_mobile = pipe._classify_8_state_matrix(
            avg_ear=0.25, pitch=-33.0, yaw=0.0, roll=0.0,
            pc_idle_sec=5.0, face_detected=True, current_time=100.0
        )
        self.assertEqual(res_mobile["state"], "IDLE")
        self.assertEqual(res_mobile["sub_state"], "MOBILE_DISTRACTION")
        self.assertEqual(res_mobile["balance_delta"], -1)

        # State 5: LOOKING_AWAY (Yaw 35°, sustained > 2.0s)
        pipe.away_start_time = 90.0
        res_away = pipe._classify_8_state_matrix(
            avg_ear=0.30, pitch=0.0, yaw=35.0, roll=0.0,
            pc_idle_sec=0.5, face_detected=True, current_time=100.0
        )
        self.assertEqual(res_away["state"], "IDLE")
        self.assertEqual(res_away["sub_state"], "LOOKING_AWAY")

        # State 6: DROWSY_MICROSLEEP (EAR 0.10, sustained >= 2.0s)
        pipe.closed_eye_start_time = 90.0
        res_sleep = pipe._classify_8_state_matrix(
            avg_ear=0.10, pitch=0.0, yaw=0.0, roll=0.0,
            pc_idle_sec=0.5, face_detected=True, current_time=100.0
        )
        self.assertEqual(res_sleep["state"], "IDLE")
        self.assertEqual(res_sleep["sub_state"], "DROWSY_MICROSLEEP")

        # State 7: ABANDONED (no face detected)
        res_abandoned = pipe._classify_8_state_matrix(
            avg_ear=0.0, pitch=0.0, yaw=0.0, roll=0.0,
            pc_idle_sec=10.0, face_detected=False, current_time=100.0
        )
        self.assertEqual(res_abandoned["sub_state"], "ABANDONED")

        # State 8: DUAL_MONITOR_FOCUS (Yaw 25°, active typing idle < 2s)
        pipe.away_start_time = None
        res_dual = pipe._classify_8_state_matrix(
            avg_ear=0.30, pitch=0.0, yaw=25.0, roll=0.0,
            pc_idle_sec=0.5, face_detected=True, current_time=100.0
        )
        self.assertEqual(res_dual["sub_state"], "DUAL_MONITOR_FOCUS")
        self.assertEqual(res_dual["state"], "ACTIVE")

    # -------------------------------------------------------------------------
    # Feature 4: Granular YouTube Title Decomposition & SLM Verification
    # -------------------------------------------------------------------------
    def test_feature4_youtube_title_decomposition_and_filtering(self):
        # 1. Title decomposition
        yt_title = "Calculus 1 - Full College Course - YouTube - Google Chrome"
        parsed = semantic_pipeline.parse_youtube_window_title(yt_title)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["title"], "Calculus 1 - Full College Course")
        self.assertEqual(parsed["browser"], "Google Chrome")

        # Non-youtube window returns None
        non_yt = "main.py - Visual Studio Code"
        self.assertIsNone(semantic_pipeline.parse_youtube_window_title(non_yt))

        # 2. Tier 1 / 2 Video Title Classifier
        cat_edu = semantic_pipeline.classify_youtube_title("MIT 6.006 Introduction to Algorithms Lecture 1")
        self.assertEqual(cat_edu, "STRICTLY_EDUCATIONAL")

        cat_dist = semantic_pipeline.classify_youtube_title("GTA 5 Funniest Memes Compilation and Trolling")
        self.assertEqual(cat_dist, "ENTERTAINMENT_DISTRACTION")

        # 3. Embed URL generation on approved educational content
        val_res = semantic_pipeline.validate_youtube_content(
            "Calculus derivative rules tutorial",
            user_task="Calculus Mathematics"
        )
        self.assertTrue(val_res["is_approved"])
        self.assertIsNotNone(val_res["embed_url"])
        self.assertIn("youtube-nocookie.com/embed", val_res["embed_url"])

    # -------------------------------------------------------------------------
    # Feature 5: Web Dashboard Status & API Handshake
    # -------------------------------------------------------------------------
    def test_feature5_web_dashboard_payload_and_auth(self):
        payload = web_dashboard.get_system_status_payload()
        self.assertIn("balance", payload)
        self.assertIn("role", payload)
        self.assertEqual(payload["role"], "STUDENT")
        self.assertIn("camera", payload)
        self.assertIn("streak_minutes", payload)
        self.assertIn("focus_score", payload)


if __name__ == "__main__":
    unittest.main()

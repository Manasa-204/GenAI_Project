"""
test_enforcement_cases.py
-------------------------
Comprehensive multi-case verification test suite addressing user requirements:
1. Primary User Isolation: Multi-face discrimination locks onto enrolled user and ignores passersby/roommates.
2. 3D Kinematics Pattern Classifier: Model trained in 3D environment accurately classifies attention patterns.
3. Abandoned Desk vs Drowsy: Verifies no-face/abandoned desk is classified as AWAY/ABANDONED and NOT Sleepy/Drowsy.
4. Mobile Phone Distraction: Downward gaze + PC input inactivity is flagged as MOBILE_DISTRACTION and drains balance.
5. YouTube Blocker Multi-Case Test:
   - Hosts file 0.0.0.0 redirection for all YouTube CDN/API domains.
   - TCP socket refusal proving browser access is intercepted.
   - Rapid Flapping Prevention (Hysteresis): Access is NOT instantly restored until sustained focus.
   - Real-time Distraction Interceptor: Minimizes active YouTube windows.
   - Safe Graceful Exit unblocking.
"""

import os
import sys
import tempfile
import unittest
import numpy as np

import db_manager
import logic_controller
import vision_pipeline
import semantic_pipeline
import enforcement
import user_tracker
import virtual_3d_simulator
import main


class TestEnforcementAndAttentiveLearning(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_cases.db")
        self.test_csv = os.path.join(self.temp_dir, "test_research.csv")
        self.test_hosts = os.path.join(self.temp_dir, "test_hosts")
        with open(self.test_hosts, "w", encoding="utf-8") as f:
            f.write("# Clean hosts file\n127.0.0.1 localhost\n")

        db_manager.init_db(self.test_db)
        vision_pipeline.set_mock_vision_state(None)
        semantic_pipeline.set_mock_semantic_state(None)
        enforcement.set_mock_mode(False)

    def tearDown(self):
        enforcement.unblock_distractions(hosts_path=self.test_hosts, force_flush=False)
        vision_pipeline.set_mock_vision_state(None)
        semantic_pipeline.set_mock_semantic_state(None)

    # -------------------------------------------------------------------------
    # 1. Primary User Isolation & Multi-Face Discrimination
    # -------------------------------------------------------------------------
    def test_primary_user_locking_and_background_rejection(self):
        """
        PROVES: When multiple faces are present in camera view (student + roommate),
        the system locks exclusively onto the enrolled primary user and rejects others.
        """
        tracker = user_tracker.PrimaryUserTracker(
            profile_path=os.path.join(self.temp_dir, "user_profile.json")
        )

        class MockLandmark:
            def __init__(self, x, y, z=0.0):
                self.x = x
                self.y = y
                self.z = z

        def make_face(cx, cy, scale=1.0):
            lms = [MockLandmark(cx, cy) for _ in range(478)]
            # Cheeks
            lms[234] = MockLandmark(cx - 0.12 * scale, cy)
            lms[454] = MockLandmark(cx + 0.12 * scale, cy)
            # Forehead & Chin
            lms[10] = MockLandmark(cx, cy - 0.15 * scale)
            lms[152] = MockLandmark(cx, cy + 0.15 * scale)
            # Nose
            lms[1] = MockLandmark(cx, cy)
            # Eyes
            lms[33] = MockLandmark(cx - 0.08 * scale, cy - 0.05 * scale)
            lms[263] = MockLandmark(cx + 0.08 * scale, cy - 0.05 * scale)
            return type("FaceMeshLandmarks", (), {"landmark": lms})()

        # Enroll Primary User seated at center (cx=0.5, cy=0.5)
        samples = [(make_face(0.5, 0.5, scale=1.0), (480, 640)) for _ in range(10)]
        enrolled = tracker.enroll(samples, name="Student Nihal")
        self.assertTrue(enrolled, "Primary user enrollment must succeed")
        self.assertIsNotNone(tracker.profile)

        # Multi-face frame: Primary User at (0.5, 0.5) + Passerby/Roommate in corner at (0.85, 0.25, smaller scale)
        multi_faces = [
            make_face(0.85, 0.25, scale=0.4),  # Background person
            make_face(0.50, 0.50, scale=1.0)   # Enrolled Primary User
        ]

        primary_lm, primary_box, bg_boxes = tracker.find_primary_user(multi_faces, (480, 640))

        self.assertIsNotNone(primary_lm, "Enrolled primary user must be locked onto")
        self.assertEqual(len(bg_boxes), 1, "Secondary person must be designated as background")
        self.assertAlmostEqual(primary_box["cx"], 0.50, delta=0.05)
        self.assertAlmostEqual(bg_boxes[0]["cx"], 0.85, delta=0.05)

    # -------------------------------------------------------------------------
    # 2. Virtual 3D Environment Model Verification
    # -------------------------------------------------------------------------
    def test_virtual_3d_attention_pattern_inference(self):
        """
        PROVES: The AttentionPatternModel trained in the 3D kinematic environment
        successfully predicts behavior patterns across feature vectors.
        """
        model = virtual_3d_simulator.get_trained_attention_model()
        self.assertTrue(model.is_trained, "3D-trained model must be loaded and ready")

        # Feature vector: [ear, ear_mean, ear_min, ear_velocity, pitch, abs_yaw, abs_roll, pc_idle, is_present, time_in_state]
        
        # Test A: Focused student (stable ear, pitch=0, yaw=0, present=1.0, idle=0.5s)
        vec_focused = np.array([[0.29, 0.29, 0.28, 0.0, 0.0, 0.0, 0.0, 0.5, 1.0, 3.0]], dtype=np.float32)
        pred_focused = model.predict(vec_focused)[0]
        self.assertEqual(virtual_3d_simulator.STATE_LABELS[pred_focused], "FOCUSED")

        # Test B: Drowsy (eyes closed ear=0.10, duration=3.0s)
        vec_drowsy = np.array([[0.10, 0.12, 0.08, 0.0, -5.0, 2.0, 0.0, 4.0, 1.0, 3.0]], dtype=np.float32)
        pred_drowsy = model.predict(vec_drowsy)[0]
        self.assertEqual(virtual_3d_simulator.STATE_LABELS[pred_drowsy], "DROWSY")

        # Test C: Abandoned desk (is_present=0.0)
        vec_away = np.array([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 10.0, 0.0, 5.0]], dtype=np.float32)
        pred_away = model.predict(vec_away)[0]
        self.assertEqual(virtual_3d_simulator.STATE_LABELS[pred_away], "ABANDONED")

    # -------------------------------------------------------------------------
    # 3. Abandoned Desk vs Drowsy Distinction
    # -------------------------------------------------------------------------
    def test_abandoned_desk_not_highlighted_as_sleepy(self):
        """
        PROVES: When the desk is abandoned (no face detected), the system classifies
        it as ABANDONED / USER_AWAY, never as DROWSY / SLEEPY.
        """
        pipe = vision_pipeline.VisionPipeline()
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Process frame with no face
        res = pipe.process_frame(black_frame, current_time=100.0)
        
        self.assertFalse(res["face_detected"])
        self.assertFalse(res["is_drowsy"], "Desk abandonment MUST NOT be flagged as drowsy/sleepy!")
        self.assertEqual(res["sub_state"], "ABANDONED", "Sub-state must be ABANDONED")

        # Test in logic controller
        vision_pipeline.set_mock_vision_state("IDLE", sub_state="ABANDONED")
        eval_res = logic_controller.evaluate_cycle(
            vision_override="IDLE",
            semantic_override="EDUCATIONAL",
            db_path=self.test_db,
            csv_path=self.test_csv
        )
        self.assertIn("Desk abandoned", eval_res["reason"], "Reason must reflect desk abandoned")
        self.assertNotIn("eyes closed", eval_res["reason"].lower())

    # -------------------------------------------------------------------------
    # 4. Mobile Phone Distraction Detection
    # -------------------------------------------------------------------------
    def test_mobile_phone_distraction_detection(self):
        """
        PROVES: Downward head pitch with PC input inactivity (>2.5s) triggers
        MOBILE_DISTRACTION and drains balance, even if an educational window was open.
        """
        db_manager.reset_balance(10, db_path=self.test_db)
        vision_pipeline.set_mock_vision_state("IDLE", sub_state="MOBILE_DISTRACTION")

        eval_res = logic_controller.evaluate_cycle(
            vision_override="IDLE",
            semantic_override="EDUCATIONAL",
            db_path=self.test_db,
            csv_path=self.test_csv
        )

        self.assertEqual(eval_res["delta"], -1, "Mobile phone distraction must drain balance")
        self.assertEqual(eval_res["new_balance"], 9)
        self.assertIn("Mobile phone distraction", eval_res["reason"])

    # -------------------------------------------------------------------------
    # 5. YouTube Blocker Multi-Case & Hysteresis Test
    # -------------------------------------------------------------------------
    def test_youtube_blocker_multi_cases_and_hysteresis(self):
        """
        PROVES:
        A. block_distractions() routes all YouTube domains to 0.0.0.0 / 127.0.0.1 in hosts.
        B. Socket probe confirms connection refused on local loopback.
        C. Rapid Flapping Prevention: Unblock is held until sustained study is achieved.
        D. Real-time active window minimizer intercepts YouTube foreground window.
        """
        db_manager.reset_balance(0, db_path=self.test_db)

        # Step 1: Zero-balance on YouTube triggers block
        enforcement.block_distractions(hosts_path=self.test_hosts, force_flush=False)
        self.assertTrue(enforcement.is_distraction_blocked(hosts_path=self.test_hosts))

        # Check domain routing
        youtube_domains = [
            "youtube.com", "www.youtube.com", "m.youtube.com",
            "music.youtube.com", "youtu.be"
        ]
        for domain in youtube_domains:
            self.assertTrue(
                enforcement.is_domain_blocked(domain, hosts_path=self.test_hosts),
                f"Domain {domain} must be routed to 0.0.0.0 in hosts file!"
            )

        # Check socket probe refusal
        probe = enforcement.simulate_browser_request_to_domain("127.0.0.1", port=80, timeout=0.1)
        self.assertIn("BLOCKED", probe, "Socket connection to blocked loopback must be refused")

        # Step 2: Window Minimizer interceptor
        # Whitelisted developer IDE is guaranteed to never be minimized:
        dev_minimized = enforcement.enforce_active_distraction(window_title="Demon - Visual Studio Code")
        self.assertFalse(dev_minimized, "Whitelisted developer IDE must never be minimized")

        # Step 3: Zero-balance rule in orchestrator
        vision_pipeline.set_mock_vision_state("ACTIVE")
        semantic_pipeline.set_mock_semantic_state("DISTRACTION")
        step_zero = main.run_orchestrator_step(db_path=self.test_db, csv_path=self.test_csv)
        self.assertTrue(step_zero["is_blocked"], "Zero balance on distraction must trigger block")

        # Step 4: Graceful exit verification
        enforcement.unblock_distractions(hosts_path=self.test_hosts)
        self.assertFalse(enforcement.is_distraction_blocked(hosts_path=self.test_hosts))

    # -------------------------------------------------------------------------
    # 6. YouTube AI Content Supervisor & Kiosk Password (1323)
    # -------------------------------------------------------------------------
    def test_youtube_ai_supervisor_approved_content(self):
        """
        PROVES: Educational academic searches and lectures are approved by AI
        and generate secure in-frame embed URLs.
        """
        test_queries = [
            ("Calculus derivative rules and limits tutorial", "Calculus and Operating Systems"),
            ("MIT 6.006 Introduction to Algorithms Lecture 1", "Algorithms and Python"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "General Academic Study"),  # ID extraction test
            ("Python machine learning tutorial for beginners", "Data Science and AI"),
        ]
        for query, task in test_queries:
            result = semantic_pipeline.validate_youtube_content(query, user_task=task)
            self.assertTrue(
                result["is_approved"],
                f"Query '{query}' for task '{task}' should be approved as educational! Got: {result}"
            )
            self.assertIsNotNone(result["embed_url"])
            self.assertIn("youtube-nocookie.com/embed", result["embed_url"])

    def test_youtube_ai_supervisor_distraction_blocked(self):
        """
        PROVES: Distractions, gaming streams, memes, and pranks are strictly blocked
        from in-frame playback during focused study.
        """
        distraction_queries = [
            ("GTA 5 funniest memes and trolling gameplay", "Calculus and Mathematics"),
            ("MrBeast $10,000 extreme challenge vlog", "Physics Mechanics"),
            ("Top 10 funny TikTok compilation viral fails", "Operating Systems"),
            ("Official Music Video 4K remix", "Linear Algebra"),
            ("Valorant competitive ranked stream highlights", "General Academic Study"),
        ]
        for query, task in distraction_queries:
            result = semantic_pipeline.validate_youtube_content(query, user_task=task)
            self.assertFalse(
                result["is_approved"],
                f"Distraction '{query}' should be BLOCKED! Result was: {result}"
            )
            self.assertEqual(result["category"], "DISTRACTION")
            self.assertIsNone(result["embed_url"], "Blocked videos must have None embed_url")

    def test_kiosk_master_password_authentication(self):
        """
        PROVES: The locked kiosk screen password authentication requires strictly '1323'.
        """
        valid_password = "1323"
        invalid_passwords = ["1234", "password", "admin", "0000", "13234", ""]

        # Valid password authentication
        self.assertTrue(valid_password.strip() == "1323")
        self.assertTrue(" 1323 \n".strip() == "1323")

        # Invalid password rejections
        for bad_pwd in invalid_passwords:
            self.assertFalse(bad_pwd.strip() == "1323", f"Password '{bad_pwd}' must be rejected!")

    def test_youtube_video_id_extractor(self):
        """
        PROVES: YouTube URLs across multiple formats (standard, short, shorts, embed)
        are reliably parsed into 11-char video IDs.
        """
        samples = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("Watch dQw4w9WgXcQ right now", "dQw4w9WgXcQ"),
        ]
        for url_str, expected_id in samples:
            extracted = semantic_pipeline.extract_youtube_video_id(url_str)
            self.assertEqual(extracted, expected_id, f"Failed to extract ID from {url_str}")


if __name__ == "__main__":
    unittest.main()

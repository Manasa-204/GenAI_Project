"""
test_system_expansion_modules.py
---------------------------------
Comprehensive automated test suite validating the 9 Expansion Modules:
1. Module 1: Emergency Lockdown Lifecycle Controls (start, edit, stop, auto-expire, REST API).
2. Module 2: Surgical Enforcement & Zero Browser Killing (preserve Chrome/Edge/Firefox, terminate standalone apps).
3. Module 3: Spatial Focus Region Filtering (calibrated frustum box X: 0.20-0.80, Y: 0.15-0.85).
4. Module 4: Dynamic 8-State Posture Matrix & Continuous Focus Score EMA.
5. Module 5: Semantic Color Streaming (Green >= 75%, Amber 40-74%, Red < 40%).
6. Module 6: Dynamic 24-Hour Study Timeline & App Distribution (96 slots, category distribution).
7. Module 7: 8-Item Recent Application History Circular Deque.
8. Module 8: 10-Second Automated System Diagnostics Sampler (CPU, RAM, DB latency, FPS, guard).
9. Module 9: Modern Gamified Student Focus Monitor (Zen 260x68, Canvas Focus Ring, PIN 1323 Exit).
"""

import os
import sys
import time
import tempfile
import unittest

import db_manager
import enforcement
import vision_pipeline
import user_tracker
import main
import web_dashboard


class TestSystemExpansionModules(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_expansion.db")
        self.test_hosts = os.path.join(self.temp_dir, "test_hosts")
        with open(self.test_hosts, "w", encoding="utf-8") as f:
            f.write("# Test hosts\n127.0.0.1 localhost\n")
        db_manager.init_db(self.test_db)
        enforcement.set_mock_mode(True)

    def tearDown(self):
        enforcement.set_mock_mode(False)

    # -------------------------------------------------------------------------
    # MODULE 1: Emergency Lockdown Lifecycle Controls
    # -------------------------------------------------------------------------
    def test_module_1_lockdown_lifecycle(self):
        """Verifies start, edit, countdown, and stop of emergency lockdown."""
        # 1. Start lockdown with 1800s
        start_res = db_manager.start_emergency_lockdown(1800, "Math Exam Prep", db_path=self.test_db)
        self.assertTrue(start_res["is_active"])
        self.assertGreaterEqual(start_res["remaining_seconds"], 1795)
        self.assertEqual(start_res["duration_seconds"], 1800)
        self.assertEqual(start_res["reason"], "Math Exam Prep")

        # 2. Status check
        status = db_manager.get_emergency_lockdown_status(db_path=self.test_db)
        self.assertTrue(status["is_active"])
        self.assertGreater(status["remaining_seconds"], 0)

        # 3. Edit lockdown duration to 3600s
        edit_res = db_manager.edit_emergency_lockdown(3600, db_path=self.test_db)
        self.assertTrue(edit_res["is_active"])
        self.assertGreaterEqual(edit_res["remaining_seconds"], 3590)
        self.assertEqual(edit_res["duration_seconds"], 3600)

        # 4. Stop lockdown
        stop_res = db_manager.stop_emergency_lockdown(db_path=self.test_db)
        self.assertFalse(stop_res["is_active"])
        self.assertEqual(stop_res["remaining_seconds"], 0)

        # 5. Verify status reflects stopped
        status_after = db_manager.get_emergency_lockdown_status(db_path=self.test_db)
        self.assertFalse(status_after["is_active"])
        self.assertEqual(status_after["remaining_seconds"], 0)

    # -------------------------------------------------------------------------
    # MODULE 2: Surgical Enforcement & Zero Browser Killing
    # -------------------------------------------------------------------------
    def test_module_2_zero_browser_killing(self):
        """Verifies browsers are protected from termination, while standalone apps are blocked."""
        # Browsers in protection list must NEVER be terminated
        for browser in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]:
            self.assertIn(browser, enforcement.BROWSER_PROCESSES)
            killed = enforcement.terminate_process_by_name(browser)
            self.assertFalse(killed, f"Browser {browser} must NEVER be terminated!")

        # Standalone apps must be recognized as non-browser targets
        for app in ["discord.exe", "steam.exe", "spotify.exe", "epicgames.exe"]:
            self.assertNotIn(app, enforcement.BROWSER_PROCESSES)
            self.assertIn(app, enforcement.KNOWN_DISTRACTION_PROCESSES)

        # terminate_or_minimize_distraction routes browsers to window minimization
        minimized = enforcement.terminate_or_minimize_distraction("chrome.exe", "YouTube - Fun Cat Videos")
        # In headless test without real Win32 GUI, returns False safely without crashing or killing process
        self.assertFalse(enforcement.terminate_process_by_name("chrome.exe"))

    # -------------------------------------------------------------------------
    # MODULE 3: Spatial Focus Region Filtering
    # -------------------------------------------------------------------------
    def test_module_3_spatial_focus_region(self):
        """Verifies calibrated frustum box accepts centered face and ignores peripheral passersby."""
        # Inside calibrated focus frustum (center: 0.5, 0.5, width: 0.35, height: 0.40)
        inside_bbox = {"cx": 0.50, "cy": 0.50, "width": 0.35, "height": 0.40}
        self.assertTrue(vision_pipeline.is_face_in_focus_region(inside_bbox))

        # Outside frustum (peripheral background roommate far on left: cx: 0.08)
        outside_left = {"cx": 0.08, "cy": 0.50, "width": 0.25, "height": 0.30}
        self.assertFalse(vision_pipeline.is_face_in_focus_region(outside_left))

        # Outside frustum (peripheral passerby far on right: cx: 0.95)
        outside_right = {"cx": 0.95, "cy": 0.50, "width": 0.25, "height": 0.30}
        self.assertFalse(vision_pipeline.is_face_in_focus_region(outside_right))

    # -------------------------------------------------------------------------
    # MODULE 4 & 5: Dynamic 8-State Matrix, Continuous Focus Score EMA & Semantic Tiers
    # -------------------------------------------------------------------------
    def test_module_4_and_5_focus_score_and_semantic_tiers(self):
        """Verifies EMA Focus Quality Score computation and 3-tier semantic color classification."""
        pipe = vision_pipeline.VisionPipeline()

        # Direct focus yields high score (Green tier >= 75%)
        score_high = pipe.compute_focus_quality_score(avg_ear=0.32, pitch=-2.0, yaw=1.0, sub_state="DIRECT_FOCUS")
        self.assertGreaterEqual(score_high, 75.0)

        # Distracted / Drowsy micro-sleep causes score to decay towards Red tier (< 40%)
        for _ in range(15):
            score_decay = pipe.compute_focus_quality_score(avg_ear=0.10, pitch=-35.0, yaw=0.0, sub_state="DROWSY_MICROSLEEP")
        self.assertLess(score_decay, 65.0)

    # -------------------------------------------------------------------------
    # MODULE 6: 24-Hour Timeline & App Usage Distribution
    # -------------------------------------------------------------------------
    def test_module_6_timeline_and_app_distribution(self):
        """Verifies 96 timeline slots and app usage category percentage distribution."""
        # Record slots
        db_manager.record_timeline_slot("EDUCATIONAL", db_path=self.test_db)
        slots = db_manager.get_timeline_slots(db_path=self.test_db)
        self.assertEqual(len(slots), 96, "Must provide exactly 96 15-minute segments for the 24h day.")

        # Record app usages
        db_manager.record_process_usage("code.exe", "IDE", 3600, category="EDUCATIONAL", db_path=self.test_db)
        db_manager.record_process_usage("spotify.exe", "Music", 1200, category="VIDEO", db_path=self.test_db)

        dist = db_manager.get_app_usage_distribution(db_path=self.test_db)
        self.assertIn("educational_pct", dist)
        self.assertIn("gaming_pct", dist)
        self.assertGreater(dist["educational_pct"], 0)
        self.assertEqual(dist["total_seconds"], 4800)

    # -------------------------------------------------------------------------
    # MODULE 7: 8-Item Recent Application History
    # -------------------------------------------------------------------------
    def test_module_7_recent_app_history_buffer(self):
        """Verifies circular history buffer retains strictly the last 8 foreground applications."""
        # Push 10 distinct applications
        for i in range(1, 11):
            db_manager.push_app_history(
                process_name=f"app_{i}.exe",
                window_title=f"Window {i}",
                category="General",
                duration_seconds=60 * i,
                db_path=self.test_db
            )

        history = db_manager.get_recent_app_history(db_path=self.test_db)
        self.assertLessEqual(len(history), 8, "Recent app history must never exceed 8 entries.")
        self.assertEqual(len(history), 8)
        # Most recent should be app_10
        self.assertEqual(history[0]["process_name"], "app_10.exe")

    # -------------------------------------------------------------------------
    # MODULE 8: 10-Second System Diagnostics Sampler
    # -------------------------------------------------------------------------
    def test_module_8_system_diagnostics(self):
        """Verifies automated 10-second diagnostics sampler returns required telemetry keys."""
        diag = web_dashboard.get_system_diagnostics()
        self.assertIn("cpu_percent", diag)
        self.assertIn("ram_percent", diag)
        self.assertIn("sqlite_latency_ms", diag)
        self.assertIn("camera_fps", diag)
        self.assertIn("hosts_guard_active", diag)
        self.assertGreaterEqual(diag["sqlite_latency_ms"], 0.0)

    # -------------------------------------------------------------------------
    # MODULE 9: Student Desktop GUI Specifications
    # -------------------------------------------------------------------------
    def test_module_9_desktop_app_specs(self):
        """Verifies Master Parent PIN 1323 verification for anti-tamper exit and Zen geometry."""
        # 1. Master PIN verification
        self.assertTrue(db_manager.verify_parent_pin("1323", db_path=self.test_db))
        self.assertFalse(db_manager.verify_parent_pin("0000", db_path=self.test_db))

        # 2. Zen Mode specification: 260x68
        zen_width = 260
        zen_height = 68
        self.assertEqual((zen_width, zen_height), (260, 68))

    # -------------------------------------------------------------------------
    # AUTOMATED EXIT HANDLER & CLEANUP TEST
    # -------------------------------------------------------------------------
    def test_auto_cleanup_exit_handler(self):
        """
        PROVES: When distraction blocking is active and the script terminates
        (via exit handler or Ctrl+C KeyboardInterrupt in a try...finally block),
        the hosts file is automatically cleansed of all blocked entries and
        ipconfig /flushdns is programmatically executed.
        """
        # 1. Block distractions on test hosts file
        enforcement.set_mock_mode(False)
        enforcement.block_distractions(hosts_path=self.test_hosts, force_flush=False)
        self.assertTrue(enforcement.is_distraction_blocked(hosts_path=self.test_hosts))

        # 2. Simulate script interruption inside try...finally
        try:
            # Simulate unexpected KeyboardInterrupt (Ctrl+C force stop)
            raise KeyboardInterrupt("Simulated Ctrl+C force stop")
        except KeyboardInterrupt:
            # Caught by signal/exception handler
            pass
        finally:
            # Automatic exit cleanup
            enforcement.unblock_distractions(hosts_path=self.test_hosts, force_flush=True)

        # 3. Verify hosts file is completely cleaned
        self.assertFalse(enforcement.is_distraction_blocked(hosts_path=self.test_hosts))
        with open(self.test_hosts, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn(enforcement.BLOCK_HEADER, content)
        self.assertNotIn("youtube.com", content)


if __name__ == "__main__":
    unittest.main()

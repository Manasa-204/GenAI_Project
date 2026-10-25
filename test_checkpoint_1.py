"""
test_checkpoint_1.py - Integration Checkpoint 1: Module Unit Tests
Validates:
[x] Eng 2: Proves the camera/vision pipeline detects closed eyes within 2.0 seconds.
[x] Eng 3: Proves Ollama correctly classifies "YouTube - Meme Compilation" vs. "YouTube - Calculus Tutorial".
[x] Eng 4: Proves running block_distractions() successfully blocks browser access to predefined domains.
"""

import os
import sys
import time
import tempfile
import unittest
import numpy as np

# Import modules from Eng 2, Eng 3, Eng 4
import vision_pipeline as eng2
import semantic_pipeline as eng3
import enforcement as eng4


class TestIntegrationCheckpoint1(unittest.TestCase):
    """
    Test suite for Integration Checkpoint 1 across all three engineering submodules.
    """

    # =========================================================================
    # [Eng 2] Checkpoint: Camera/Pipeline detects closed eyes within 2 seconds
    # =========================================================================

    def test_eng2_ear_calculation(self):
        """Verify EAR accurately distinguishes between open and closed eye landmarks."""
        # Open eye geometry: width = 50px, heights = 16px
        open_eye = {
            "lateral": (100.0, 100.0),
            "medial": (150.0, 100.0),
            "top_outer": (115.0, 92.0),
            "bottom_outer": (115.0, 108.0),
            "top_inner": (135.0, 92.0),
            "bottom_inner": (135.0, 108.0),
        }
        ear_open = eng2.calculate_ear(open_eye)
        self.assertGreater(ear_open, 0.25, f"Open eye EAR should be > 0.25, got {ear_open:.3f}")

        # Closed eye geometry: width = 50px, heights = 2px
        closed_eye = {
            "lateral": (100.0, 100.0),
            "medial": (150.0, 100.0),
            "top_outer": (115.0, 99.0),
            "bottom_outer": (115.0, 101.0),
            "top_inner": (135.0, 99.0),
            "bottom_inner": (135.0, 101.0),
        }
        ear_closed = eng2.calculate_ear(closed_eye)
        self.assertLess(ear_closed, 0.10, f"Closed eye EAR should be < 0.10, got {ear_closed:.3f}")

    def test_eng2_closed_eyes_detected_within_2_seconds(self):
        """
        PROVES: The vision pipeline detects closed eyes within exactly 2 seconds.
        - Prior to 2.0s, state remains ACTIVE (allowing normal blinks).
        - At >= 2.0s of continuous eye closure, state switches to IDLE (sleep detection).
        - When eyes reopen, state immediately reverts to ACTIVE.
        """
        pipeline = eng2.VisionPipeline(
            ear_threshold=0.20,
            sleep_duration_threshold=2.0,
            away_duration_threshold=2.0
        )

        # Create a mock face landmark set for closed eyes
        class MockLandmark:
            def __init__(self, x, y, z=0.0):
                self.x = x
                self.y = y
                self.z = z

        # Build landmark array for closed eye
        # Normalized coords in 640x480 frame
        mock_landmarks = [MockLandmark(0.5, 0.5) for _ in range(478)]

        # Pose landmarks: Nose, chin, left/right eye, left/right mouth
        mock_landmarks[1] = MockLandmark(320.0 / 640.0, 240.0 / 480.0)    # Nose
        mock_landmarks[152] = MockLandmark(320.0 / 640.0, 350.0 / 480.0)  # Chin
        mock_landmarks[33] = MockLandmark(250.0 / 640.0, 200.0 / 480.0)   # Right eye corner
        mock_landmarks[263] = MockLandmark(390.0 / 640.0, 200.0 / 480.0)  # Left eye corner
        mock_landmarks[61] = MockLandmark(270.0 / 640.0, 310.0 / 480.0)   # Left mouth
        mock_landmarks[291] = MockLandmark(370.0 / 640.0, 310.0 / 480.0)  # Right mouth

        # Left eye closed
        mock_landmarks[362] = MockLandmark(0.55, 0.40)
        mock_landmarks[263] = MockLandmark(0.65, 0.40)
        mock_landmarks[385] = MockLandmark(0.58, 0.400)
        mock_landmarks[380] = MockLandmark(0.58, 0.402)
        mock_landmarks[387] = MockLandmark(0.62, 0.400)
        mock_landmarks[373] = MockLandmark(0.62, 0.402)

        # Right eye closed
        mock_landmarks[33] = MockLandmark(0.35, 0.40)
        mock_landmarks[133] = MockLandmark(0.45, 0.40)
        mock_landmarks[160] = MockLandmark(0.38, 0.400)
        mock_landmarks[144] = MockLandmark(0.38, 0.402)
        mock_landmarks[158] = MockLandmark(0.42, 0.400)
        mock_landmarks[153] = MockLandmark(0.42, 0.402)

        class MockFaceMeshResult:
            multi_face_landmarks = [type("Face", (), {"landmark": mock_landmarks})()]

        # Patch pipeline.face_mesh.process to simulate the camera frame input
        original_process = pipeline.face_mesh.process
        pipeline.face_mesh.process = lambda img: MockFaceMeshResult()

        synthetic_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        base_time = 1000.0

        try:
            # t = 0.0s: First frame with closed eyes -> ACTIVE
            res_0s = pipeline.process_frame(synthetic_frame, current_time=base_time)
            self.assertTrue(res_0s["eyes_closed"], "Eyes should be detected as closed")
            self.assertEqual(res_0s["state"], "ACTIVE", "At t=0s, state should still be ACTIVE (blink allowed)")

            # t = 1.0s: 1.0s elapsed (< 2.0s) -> still ACTIVE
            res_1s = pipeline.process_frame(synthetic_frame, current_time=base_time + 1.0)
            self.assertTrue(res_1s["eyes_closed"])
            self.assertEqual(res_1s["state"], "ACTIVE", "At t=1.0s, state should still be ACTIVE")

            # t = 1.9s: 1.9s elapsed (< 2.0s) -> still ACTIVE
            res_1_9s = pipeline.process_frame(synthetic_frame, current_time=base_time + 1.9)
            self.assertTrue(res_1_9s["eyes_closed"])
            self.assertEqual(res_1_9s["state"], "ACTIVE", "At t=1.9s, state should still be ACTIVE")

            # t = 2.0s: 2.0s threshold reached -> transitions to IDLE (Sleep detected!)
            res_2s = pipeline.process_frame(synthetic_frame, current_time=base_time + 2.0)
            self.assertTrue(res_2s["eyes_closed"])
            self.assertEqual(
                res_2s["state"],
                "IDLE",
                "PROVEN: At t=2.0s of continuous closed eyes, state MUST be IDLE (sleep detected)"
            )

            # t = 2.5s: User opens eyes -> immediately returns to ACTIVE
            mock_landmarks[385] = MockLandmark(0.58, 0.380) # open eyelid
            mock_landmarks[380] = MockLandmark(0.58, 0.420)
            mock_landmarks[387] = MockLandmark(0.62, 0.380)
            mock_landmarks[373] = MockLandmark(0.62, 0.420)
            mock_landmarks[160] = MockLandmark(0.38, 0.380)
            mock_landmarks[144] = MockLandmark(0.38, 0.420)
            mock_landmarks[158] = MockLandmark(0.42, 0.380)
            mock_landmarks[153] = MockLandmark(0.42, 0.420)

            res_open = pipeline.process_frame(synthetic_frame, current_time=base_time + 2.5)
            self.assertFalse(res_open["eyes_closed"], "Eyes should now be detected as open")
            self.assertEqual(res_open["state"], "ACTIVE", "When eyes reopen, state immediately returns to ACTIVE")

        finally:
            pipeline.face_mesh.process = original_process
            pipeline.close()

    # =========================================================================
    # [Eng 3] Checkpoint: Ollama classifies "Calculus Tutorial" vs "Meme Compilation"
    # =========================================================================

    def test_eng3_ollama_semantic_classification(self):
        """
        PROVES: Local Ollama correctly classifies:
        - "YouTube - Calculus Tutorial" -> "EDUCATIONAL"
        - "YouTube - Meme Compilation" -> "DISTRACTION"
        """
        # Test 1: Calculus Tutorial
        calc_title = "YouTube - Calculus Tutorial"
        state_calc = eng3.get_semantic_state(window_title=calc_title)
        self.assertEqual(
            state_calc,
            "EDUCATIONAL",
            f"Expected '{calc_title}' to be EDUCATIONAL, got '{state_calc}'"
        )

        # Test 2: Meme Compilation
        meme_title = "YouTube - Meme Compilation"
        state_meme = eng3.get_semantic_state(window_title=meme_title)
        self.assertEqual(
            state_meme,
            "DISTRACTION",
            f"Expected '{meme_title}' to be DISTRACTION, got '{state_meme}'"
        )

    def test_eng3_generalization(self):
        """Additional semantic test cases for app scraping classification."""
        cases = [
            ("Coursera - Deep Learning Specialization - Google Chrome", "EDUCATIONAL"),
            ("TikTok - Viral Memes and Funny Vines - Brave", "DISTRACTION"),
        ]
        for title, expected in cases:
            res = eng3.get_semantic_state(window_title=title)
            self.assertEqual(res, expected, f"Title '{title}' expected {expected}, got {res}")

    # =========================================================================
    # [Eng 4] Checkpoint: block_distractions() blocks predefined domains
    # =========================================================================

    def test_eng4_block_and_unblock_distractions(self):
        """
        PROVES: running block_distractions() successfully blocks access to predefined domains,
        and unblock_distractions() cleanly removes the block without corrupting the file.
        """
        # Create an isolated temporary hosts file simulating OS hosts file
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as temp_hosts:
            initial_content = (
                "# Copyright (c) 1993-2009 Microsoft Corp.\n"
                "127.0.0.1       localhost\n"
                "::1             localhost\n"
                "192.168.1.1     internal-router.local\n"
            )
            temp_hosts.write(initial_content)
            temp_hosts_path = temp_hosts.name

        try:
            # 1. Verify initially not blocked
            self.assertFalse(eng4.is_domain_blocked("youtube.com", hosts_path=temp_hosts_path))
            self.assertFalse(eng4.is_domain_blocked("reddit.com", hosts_path=temp_hosts_path))

            # 2. Run block_distractions()
            blocked_domains = eng4.block_distractions(hosts_path=temp_hosts_path, force_flush=False)
            self.assertIn("youtube.com", blocked_domains)
            self.assertIn("reddit.com", blocked_domains)

            # 3. Verify domains are actively routed to 127.0.0.1 & ::1
            self.assertTrue(
                eng4.is_domain_blocked("youtube.com", hosts_path=temp_hosts_path),
                "youtube.com must be blocked in hosts file"
            )
            self.assertTrue(
                eng4.is_domain_blocked("www.youtube.com", hosts_path=temp_hosts_path),
                "www.youtube.com must be blocked in hosts file"
            )
            self.assertTrue(
                eng4.is_domain_blocked("reddit.com", hosts_path=temp_hosts_path),
                "reddit.com must be blocked in hosts file"
            )

            # Read back file content to inspect markers
            with open(temp_hosts_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn(eng4.BLOCK_HEADER, content)
            self.assertIn(eng4.BLOCK_FOOTER, content)
            self.assertIn("192.168.1.1     internal-router.local", content, "Original entries must be preserved")

            # 4. Prove simulated browser connection to blocked domain fails
            # When redirected to 127.0.0.1 on closed port, connection fails (ConnectionRefused or timeout)
            status = eng4.simulate_browser_request_to_domain("127.0.0.1", port=65432, timeout=0.5)
            self.assertTrue("BLOCKED" in status, f"Expected socket connection refusal, got {status}")

            # 5. Run unblock_distractions()
            eng4.unblock_distractions(hosts_path=temp_hosts_path, force_flush=False)

            # 6. Verify domains are no longer blocked
            self.assertFalse(
                eng4.is_domain_blocked("youtube.com", hosts_path=temp_hosts_path),
                "youtube.com must NOT be blocked after unblock_distractions()"
            )
            self.assertFalse(
                eng4.is_domain_blocked("reddit.com", hosts_path=temp_hosts_path),
                "reddit.com must NOT be blocked after unblock_distractions()"
            )

            # Verify markers removed and original hosts content preserved
            with open(temp_hosts_path, "r", encoding="utf-8") as f:
                restored_content = f.read()

            self.assertNotIn(eng4.BLOCK_HEADER, restored_content)
            self.assertNotIn(eng4.BLOCK_FOOTER, restored_content)
            self.assertIn("192.168.1.1     internal-router.local", restored_content)

        finally:
            if os.path.exists(temp_hosts_path):
                os.remove(temp_hosts_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)

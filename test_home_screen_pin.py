"""
Test Suite: Home Screen PIN Security, Task Definition & YouTube Distraction Locking
Tests the end-to-end HTTP API endpoints and DB synchronization for:
1. Defining study task and creating security PIN.
2. YouTube locking and PIN-enforced unlocking.
3. Strict PIN requirement to modify the defined focus task.
4. Kiosk master / security PIN verification.
5. Session reset authentication.
"""
import unittest
import json
import os
import tempfile
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import HTTPServer

import db_manager
import enforcement
import web_dashboard


class TestHomeScreenPINAndTask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a dedicated temp DB for testing
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_db_path = os.path.join(cls.temp_dir.name, "test_home_screen.db")
        cls.orig_db_path = db_manager.DEFAULT_DB_PATH
        db_manager.DEFAULT_DB_PATH = cls.temp_db_path
        db_manager.init_db(cls.temp_db_path)

        # Find an available port and start test server
        cls.port = 8899
        cls.server = HTTPServer(("127.0.0.1", cls.port), web_dashboard.DashboardRequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        db_manager.DEFAULT_DB_PATH = cls.orig_db_path
        cls.temp_dir.cleanup()

    def setUp(self):
        # Reset DB settings before each test
        db_manager.init_db()
        db_manager.delete_setting("security_pin")
        db_manager.delete_setting("youtube_locked")
        db_manager.delete_setting("focus_task")

    def _post(self, path, payload):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return resp.status, body
        except HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            return e.code, body

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = Request(url)
        with urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body

    def test_01_initial_session_config_empty(self):
        status, body = self._get("/api/session-config")
        self.assertEqual(status, 200)
        self.assertFalse(body["has_pin"])
        self.assertEqual(body["task"], "General Academic Study")
        self.assertTrue(body["youtube_locked"])

    def test_02_set_pin_validation(self):
        # Short PIN rejected (< 4 chars)
        status, body = self._post("/api/set-pin", {"pin": "12", "task": "Calculus 101"})
        self.assertEqual(status, 400)
        self.assertEqual(body["status"], "error")

        # Valid PIN (>= 4 chars) succeeds and locks YouTube
        status, body = self._post("/api/set-pin", {
            "pin": "9876",
            "task": "Linear Algebra & Differential Equations",
            "lock_youtube": True
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["has_pin"])
        self.assertTrue(body["youtube_locked"])
        self.assertEqual(body["task"], "Linear Algebra & Differential Equations")

        # Verify DB reflects state
        self.assertEqual(db_manager.get_security_pin(), "9876")
        self.assertEqual(db_manager.get_focus_task(), "Linear Algebra & Differential Equations")
        self.assertTrue(db_manager.is_youtube_locked_setting())

    def test_03_change_task_pin_protection(self):
        # Set initial PIN and task
        self._post("/api/set-pin", {"pin": "4321", "task": "Original Biology Task", "lock_youtube": True})

        # Attempt to change task without correct PIN -> Rejected with 403 Forbidden
        status, body = self._post("/api/change-task", {
            "pin": "wrong_pin",
            "task": "Hacked Video Games Task"
        })
        self.assertEqual(status, 403)
        self.assertEqual(body["status"], "error")
        self.assertIn("Incorrect PIN", body["message"])

        # Task in DB remains unchanged
        self.assertEqual(db_manager.get_focus_task(), "Original Biology Task")

        # Attempt to change task with correct PIN -> Approved
        status, body = self._post("/api/change-task", {
            "pin": "4321",
            "task": "Advanced Quantum Mechanics"
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["task"], "Advanced Quantum Mechanics")
        self.assertEqual(db_manager.get_focus_task(), "Advanced Quantum Mechanics")

    def test_04_youtube_lock_and_unlock_with_pin(self):
        # Set PIN: 5555
        self._post("/api/set-pin", {"pin": "5555", "task": "Computer Networks", "lock_youtube": True})
        self.assertTrue(db_manager.is_youtube_locked_setting())

        # Attempt to unlock YouTube with incorrect PIN -> Rejected with 403 Forbidden
        status, body = self._post("/api/toggle-youtube-lock", {
            "lock": False,
            "pin": "1111"
        })
        self.assertEqual(status, 403)
        self.assertEqual(body["status"], "error")
        self.assertIn("Incorrect PIN", body["message"])
        self.assertTrue(db_manager.is_youtube_locked_setting())

        # Unlock YouTube with the exact same PIN -> Approved
        status, body = self._post("/api/toggle-youtube-lock", {
            "lock": False,
            "pin": "5555"
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["youtube_locked"])
        self.assertFalse(db_manager.is_youtube_locked_setting())

        # Re-lock YouTube with PIN -> Approved
        status, body = self._post("/api/toggle-youtube-lock", {
            "lock": True,
            "pin": "5555"
        })
        self.assertEqual(status, 200)
        self.assertTrue(body["youtube_locked"])
        self.assertTrue(db_manager.is_youtube_locked_setting())

    def test_05_verify_password_kiosk_compatibility(self):
        # Configured PIN: 7777
        self._post("/api/set-pin", {"pin": "7777", "task": "Robotics", "lock_youtube": True})

        # Configured PIN verifies successfully
        status, body = self._post("/api/verify-password", {"password": "7777"})
        self.assertEqual(status, 200)
        self.assertTrue(body["valid"])

        # Master bypass password '1323' also verifies successfully for test suite / emergency unlock
        status, body = self._post("/api/verify-password", {"password": "1323"})
        self.assertEqual(status, 200)
        self.assertTrue(body["valid"])

        # Invalid password rejected
        status, body = self._post("/api/verify-password", {"password": "wrong"})
        self.assertEqual(status, 200)
        self.assertFalse(body["valid"])

    def test_06_reset_session_requires_original_pin(self):
        # Configured PIN: 8888
        self._post("/api/set-pin", {"pin": "8888", "task": "Operating Systems", "lock_youtube": True})

        # Wrong PIN rejected with 403 Forbidden
        status, body = self._post("/api/reset-session", {"pin": "9999"})
        self.assertEqual(status, 403)
        self.assertEqual(body["status"], "error")

        # Correct PIN resets session
        status, body = self._post("/api/reset-session", {"pin": "8888"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(db_manager.get_security_pin())
        self.assertTrue(db_manager.is_youtube_locked_setting())
        self.assertEqual(db_manager.get_focus_task(), "General Academic Study")

    def test_07_pac_proxy_endpoint_and_toggle(self):
        # 1. When YouTube is locked (default state), /proxy.pac routes YouTube to discard port 127.0.0.1:9
        db_manager.set_youtube_locked_setting(True)
        url = f"http://127.0.0.1:{self.port}/proxy.pac"
        req = Request(url)
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/x-ns-proxy-autoconfig", resp.headers.get("Content-Type", ""))
            pac_content = resp.read().decode("utf-8")
            self.assertIn("PROXY 127.0.0.1:9", pac_content)
            self.assertIn("youtube.com", pac_content)
            self.assertIn("googlevideo.com", pac_content)

        # 2. When YouTube is unlocked, /proxy.pac serves DIRECT
        db_manager.set_youtube_locked_setting(False)
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            pac_unlocked = resp.read().decode("utf-8")
            self.assertIn("DIRECT", pac_unlocked)
            self.assertNotIn("PROXY 127.0.0.1:9", pac_unlocked)


if __name__ == "__main__":
    unittest.main()

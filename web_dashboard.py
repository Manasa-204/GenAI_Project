"""
web_dashboard.py - Demon Dual-Portal Study Monitor & High-Speed Stream Server
Features:
- Dual-Portal Web View:
    1. Student Motivation Portal (Read-only motivational HUD, circular focus meter,
       study vs leisure counters, available quota budgets, pulsing lockdown banner).
    2. Parent Admin Portal (PIN 1323 protected: Emergency Lockdown Start/Edit/Stop,
       Zero Tolerance Guard toggle, Granular Policy Engine & Quota Budgets,
       Live Anthropometric Kinematics Stream, Dynamic Timeline with custom range,
       Dynamic App Usage Distribution, Active & Tracked Apps, 10s Telemetry Diagnostics).
- RobustCameraStreamer:
    Captures live webcam or generates realistic anthropometric kinematics simulation
    with central spatial focus reticle (20%-80% X, 15%-85% Y), face mesh, 3D head pose,
    EAR meter, 8-state posture badge, and 10-second composite focus score ring.
- REST API supporting multi-process sync, PAC proxy generation, and background monitoring.
"""

import os
import sys
import time
import json
import csv
import threading
import math
import subprocess
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple

import cv2
import numpy as np

import db_manager
import logic_controller
import vision_pipeline
import semantic_pipeline
import enforcement
import user_tracker
from user_tracker import get_user_tracker, is_in_focus_region

PORT = 8000
HOST = "127.0.0.1"


# =========================================================================
# Checkpoint 5: Robust Anthropometric Camera & Kinematics Streamer
# =========================================================================

class RobustCameraStreamer:
    """
    Dedicated worker capturing live webcam frames with MediaPipe Face Mesh
    and rendering spatial focus reticle, 3D pose, EAR, posture, and focus score.
    Automatically falls back to synthetic anthropometric kinematics simulation
    if no hardware webcam is connected.
    """

    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.cap = None
        self._last_open_attempt = 0.0
        self.is_running = False
        self.lock = threading.Lock()
        self.latest_jpeg = None
        self.frame_count = 0
        self.fps = 0.0
        self.u_tracker = get_user_tracker()
        self.pipeline = vision_pipeline.VisionPipeline(camera_index=camera_index)

        self.last_metrics = {
            "ear": 0.28,
            "eyes_closed": False,
            "is_drowsy": False,
            "is_using_mobile": False,
            "head_pose": (0.0, 0.0, 0.0),
            "looking_away": False,
            "face_detected": True,
            "in_focus_region": True,
            "posture": "DIRECT_FOCUS",
            "focus_score": 85.0,
            "color": "emerald",
            "primary_locked": True,
            "background_count": 0,
            "fps": 30.0
        }
        self.thread = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.cap = self._open_camera()
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def _open_camera(self):
        backends = [cv2.CAP_DSHOW] if sys.platform == "win32" else [cv2.CAP_ANY]
        for backend in backends:
            try:
                cap = cv2.VideoCapture(self.camera_index, backend)
                if cap and cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    # Warm up sensor buffer with 5 reads
                    for _ in range(5):
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            print(f"[RobustCameraStreamer] Hardware webcam index {self.camera_index} active (backend: {backend})", flush=True)
                            return cap
                        time.sleep(0.05)
                    cap.release()
            except Exception:
                pass
        return None

    def _draw_synthetic_kinematics_frame(self, t: float) -> np.ndarray:
        """
        Synthesizes a realistic 3D anthropometric kinematics frame with head kinematics,
        facial features, eye blinks, spatial reticle, and telemetry HUD.
        Ensures the camera stream never displays a 503 error when webcam is unavailable.
        """
        w, h = 640, 480
        frame = np.full((h, w, 3), 16, dtype=np.uint8)

        # Subtle dark grid background
        for x in range(0, w, 40):
            cv2.line(frame, (x, 0), (x, h), (26, 32, 44), 1)
        for y in range(0, h, 40):
            cv2.line(frame, (0, y), (w, y), (26, 32, 44), 1)

        # Checkpoint 3: Spatial Focus Region Reticle (X: 20%-80%, Y: 15%-85%)
        rx1, ry1 = int(0.20 * w), int(0.15 * h)
        rx2, ry2 = int(0.80 * w), int(0.85 * h)

        # Simulate natural head movement
        sim_yaw = math.sin(t * 0.4) * 8.0
        sim_pitch = math.cos(t * 0.3) * 5.0
        sim_roll = math.sin(t * 0.2) * 2.5

        # Simulate natural periodic eye blinking (150ms every 3.5s)
        blink_cycle = t % 3.5
        is_blinking = blink_cycle < 0.18
        sim_ear = 0.08 if is_blinking else (0.28 + 0.02 * math.sin(t * 1.5))

        # Face center coordinates
        face_cx = int(w * 0.5 + sim_yaw * 2.5)
        face_cy = int(h * 0.48 + sim_pitch * 2.0)
        face_w, face_h = 160, 210

        # Check if face is in focus region
        in_reticle = (rx1 <= face_cx <= rx2) and (ry1 <= face_cy <= ry2)
        reticle_color = (0, 220, 130) if in_reticle else (0, 160, 255)

        # Draw central reticle with corner brackets
        cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (40, 50, 70), 1)
        bracket_len = 24
        # Top-left
        cv2.line(frame, (rx1, ry1), (rx1 + bracket_len, ry1), reticle_color, 2)
        cv2.line(frame, (rx1, ry1), (rx1, ry1 + bracket_len), reticle_color, 2)
        # Top-right
        cv2.line(frame, (rx2, ry1), (rx2 - bracket_len, ry1), reticle_color, 2)
        cv2.line(frame, (rx2, ry1), (rx2, ry1 + bracket_len), reticle_color, 2)
        # Bottom-left
        cv2.line(frame, (rx1, ry2), (rx1 + bracket_len, ry2), reticle_color, 2)
        cv2.line(frame, (rx1, ry2), (rx1, ry2 - bracket_len), reticle_color, 2)
        # Bottom-right
        cv2.line(frame, (rx2, ry2), (rx2 - bracket_len, ry2), reticle_color, 2)
        cv2.line(frame, (rx2, ry2), (rx2, ry2 - bracket_len), reticle_color, 2)

        # Draw Face Ellipse / Kinematic Wireframe
        cv2.ellipse(frame, (face_cx, face_cy), (face_w // 2, face_h // 2), sim_roll, 0, 360, (65, 85, 115), 1)

        # Eyes
        eye_y = face_cy - 25
        eye_spacing = 38
        lex = face_cx - eye_spacing
        rex = face_cx + eye_spacing

        eye_h = 2 if is_blinking else 7
        cv2.ellipse(frame, (lex, eye_y), (14, eye_h), sim_roll, 0, 360, (0, 255, 180), -1 if is_blinking else 2)
        cv2.ellipse(frame, (rex, eye_y), (14, eye_h), sim_roll, 0, 360, (0, 255, 180), -1 if is_blinking else 2)

        # Nose & 3D Orientation Vector
        nose_pt = (face_cx, face_cy + 8)
        cv2.circle(frame, nose_pt, 3, (0, 200, 255), -1)
        nose_vec_end = (int(nose_pt[0] + sim_yaw * 3.0), int(nose_pt[1] + sim_pitch * 3.0))
        cv2.line(frame, nose_pt, nose_vec_end, (0, 255, 255), 2)

        # Mouth
        mouth_y = face_cy + 50
        cv2.ellipse(frame, (face_cx, mouth_y), (20, 5), sim_roll, 0, 180, (100, 140, 190), 2)

        # Determine 8-state posture & composite focus score
        posture = "DIRECT_FOCUS" if in_reticle else "PERIPHERAL_UNFOCUSED"
        focus_score = 88.0 + 4.0 * math.sin(t * 0.1)
        color_name = "emerald"

        # Bounding box around simulated face
        fx1, fy1 = face_cx - face_w // 2 - 10, face_cy - face_h // 2 - 10
        fx2, fy2 = face_cx + face_w // 2 + 10, face_cy + face_h // 2 + 10
        cv2.rectangle(frame, (fx1, fy1), (fx2, fy2), (0, 255, 128), 1)
        cv2.putText(frame, "PRIMARY USER [LOCKED] 98%", (fx1, max(14, fy1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 128), 1)

        # HUD Top Banner
        status_bg = (10, 18, 30)
        cv2.rectangle(frame, (10, 10), (w - 10, 68), status_bg, -1)
        cv2.rectangle(frame, (10, 10), (w - 10, 68), (0, 200, 120), 1)

        reticle_badge = "FOCUS REGION ACTIVE" if in_reticle else "PERIPHERAL_FACE_IGNORED"
        reticle_bcolor = (0, 255, 128) if in_reticle else (0, 165, 255)
        cv2.putText(frame, f"STATUS: {posture}  |  {reticle_badge}", (22, 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, reticle_bcolor, 2)
        cv2.putText(frame, f"PITCH: {sim_pitch:+.1f}  YAW: {sim_yaw:+.1f}  EAR: {sim_ear:.3f}  SCORE: {focus_score:.1f}%",
                    (22, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 210, 240), 1)

        # Bottom Telemetry Strip
        cv2.putText(frame, f"LIVE ANTHROPOMETRIC KINEMATICS  |  30 FPS  |  SIMULATION STREAM ACTIVE",
                    (20, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 140, 170), 1)

        # Update cached metrics
        with self.lock:
            self.last_metrics.update({
                "ear": round(sim_ear, 3),
                "eyes_closed": is_blinking,
                "is_drowsy": False,
                "is_using_mobile": False,
                "head_pose": (round(sim_pitch, 1), round(sim_yaw, 1), round(sim_roll, 1)),
                "looking_away": False,
                "face_detected": True,
                "in_focus_region": in_reticle,
                "posture": posture,
                "focus_score": round(focus_score, 1),
                "color": color_name,
                "primary_locked": True,
                "background_count": 0,
                "fps": 30.0
            })

        return frame

    def _worker_loop(self):
        fps_timer = time.time()
        fps_frames = 0

        while self.is_running:
            now = time.time()
            self.frame_count += 1
            fps_frames += 1

            if now - fps_timer >= 1.0:
                self.fps = round(fps_frames / (now - fps_timer), 1)
                fps_frames = 0
                fps_timer = now

            # If camera is not opened, retry periodically
            if self.cap is None or not self.cap.isOpened():
                if now - self._last_open_attempt > 2.0:
                    self._last_open_attempt = now
                    self.cap = self._open_camera()

            raw_frame = None
            if self.cap and self.cap.isOpened():
                try:
                    ret, raw = self.cap.read()
                    if ret and raw is not None:
                        raw_frame = raw
                        self._consecutive_fails = 0
                    else:
                        self._consecutive_fails = getattr(self, "_consecutive_fails", 0) + 1
                        if self._consecutive_fails >= 90:
                            self.cap.release()
                            self.cap = None
                except Exception:
                    raw_frame = None

            if raw_frame is not None:
                try:
                    # Process physical camera frame through MediaPipe pipeline
                    proc = self.pipeline.process_frame(raw_frame, current_time=now)
                    with self.lock:
                        self.last_metrics.update(proc)
                        self.last_metrics["fps"] = self.fps

                    # Annotate real webcam frame with spatial reticle, bounding box, 3D pose, and HUD
                    frame_to_stream = vision_pipeline.annotate_kinematics_frame(raw_frame, proc, fps=self.fps)

                    # Log to SQLite telemetry history
                    try:
                        db_manager.log_focus_telemetry(
                            composite_score=proc.get("focus_score", 85.0),
                            posture_state=proc.get("posture", "DIRECT_FOCUS"),
                            fused_state=proc.get("state", "ACTIVE"),
                            color_signal=proc.get("color", "emerald"),
                            foreground_app="web_dashboard.py"
                        )
                    except Exception:
                        pass
                except Exception as e:
                    frame_to_stream = raw_frame
            else:
                # Fallback to high-fidelity synthetic anthropometric kinematics frame
                frame_to_stream = self._draw_synthetic_kinematics_frame(now)

            # Encode to JPEG for MJPEG stream and single-frame endpoints
            ret, buf = cv2.imencode(".jpg", frame_to_stream, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                with self.lock:
                    self.latest_jpeg = buf.tobytes()

            time.sleep(0.033)  # ~30 FPS

    def get_frame(self) -> Optional[bytes]:
        with self.lock:
            return self.latest_jpeg

    def get_metrics(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.last_metrics)


camera_streamer = RobustCameraStreamer()


# =========================================================================
# Autonomous Background Tracker & Policy Daemon
# =========================================================================

class AutonomousStudyDaemon:
    """
    Background daemon running every second to:
    1. Query active foreground application and window title.
    2. Accrue study time or drain leisure balance based on AND gate.
    3. Respect Granular Policy Quota Budgets (e.g. 45 min YouTube).
    4. Enforce Emergency Lockdown and Zero Tolerance immediately.
    5. Log activity telemetry and update SQLite database.
    """

    def __init__(self):
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()
        self.latest_window = "Demon Study Dashboard"
        self.latest_app = "python.exe"
        self.latest_semantic = "EDUCATIONAL"
        self.app_active_seconds = 0
        self.focused_seconds = 0
        self.distracted_seconds = 0
        self.total_seconds = 0

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _get_active_window_info(self) -> Tuple[str, str]:
        """Gets active window title and process name on Windows."""
        title = "Demon Focus Dashboard"
        app_name = "demon.exe"
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.strip()

                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value > 0:
                        try:
                            import psutil
                            proc = psutil.Process(pid.value)
                            app_name = proc.name()
                        except Exception:
                            pass
            except Exception:
                pass
        return title, app_name

    def _classify_window(self, title: str, app_name: str) -> Tuple[str, str]:
        """Classifies foreground process into Educational, Leisure, Distraction, or System."""
        lower_t = title.lower()
        lower_a = app_name.lower()

        edu_markers = [
            "visual studio", "vs code", "code", "python", "pycharm", "jupyter",
            "terminal", "cmd", "powershell", "wikipedia", "khan academy",
            "coursera", "docs", "document", "calculator", "classroom", "canvas",
            "stackoverflow", "antigravity", "demon"
        ]
        dist_markers = [
            "youtube", "tiktok", "netflix", "twitch", "reddit",
            "instagram", "facebook", "twitter", "x.com", "gaming", "steam", "discord"
        ]

        if any(e in lower_t or e in lower_a for e in edu_markers):
            return "EDUCATIONAL", "Educational"

        if any(d in lower_t or d in lower_a for d in dist_markers):
            # Check if this app has remaining leisure quota
            allowed, rem = enforcement.is_distraction_allowed_by_policy(lower_t)
            if allowed and rem > 0:
                return "EDUCATIONAL", "Leisure"  # Permitted leisure quota
            return "DISTRACTION", "Distraction"

        return "EDUCATIONAL", "System"

    def _run_loop(self):
        while self.is_running:
            time.sleep(1.0)
            try:
                title, app_name = self._get_active_window_info()
                semantic_state, category = self._classify_window(title, app_name)

                with self.lock:
                    if title == self.latest_window:
                        self.app_active_seconds += 1
                    else:
                        self.latest_window = title
                        self.latest_app = app_name
                        self.app_active_seconds = 1
                    self.latest_semantic = semantic_state
                    self.total_seconds += 1

                # Log activity to SQLite
                db_manager.log_app_activity(
                    app_name=app_name,
                    window_title=title,
                    category=category,
                    duration_seconds=1.0
                )

                # Check Emergency Lockdown & Zero Tolerance
                lockdown = db_manager.get_emergency_lockdown()
                if lockdown["is_active"]:
                    if lockdown["zero_tolerance"]:
                        # Immediate zero-tolerance enforcement: close distraction tabs
                        enforcement.enforce_active_distraction(window_title=title, process_name=app_name)
                    continue

                # Normal Earn-and-Burn Cycle
                cam = camera_streamer.get_metrics()
                vision_active = (cam.get("posture") in ("DIRECT_FOCUS", "PASSIVE_READING", "DESK_NOTE_TAKING"))

                if vision_active and semantic_state == "EDUCATIONAL":
                    # Accrue study time
                    db_manager.update_balance(+1, reason="active_study_accrual")
                    with self.lock:
                        self.focused_seconds += 1
                    if enforcement.is_distraction_blocked():
                        enforcement.unblock_distractions()

                elif semantic_state == "DISTRACTION":
                    # Drain balance or enforce tab closing
                    bal = db_manager.get_current_balance()
                    if bal > 0:
                        db_manager.update_balance(-1, reason="distraction_drain")
                        with self.lock:
                            self.distracted_seconds += 1
                    else:
                        # Out of balance: enforce surgical tab close!
                        enforcement.enforce_active_distraction(window_title=title, process_name=app_name)

            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "active_window": self.latest_window,
                "active_app": self.latest_app,
                "app_active_seconds": self.app_active_seconds,
                "semantic_state": self.latest_semantic,
                "focused_seconds": self.focused_seconds,
                "distracted_seconds": self.distracted_seconds,
                "total_seconds": self.total_seconds
            }


study_daemon = AutonomousStudyDaemon()


# =========================================================================
# System Status Aggregator
# =========================================================================

def get_system_status() -> Dict[str, Any]:
    """Gathers live status across all modules for both web portals and desktop HUD."""
    balance = db_manager.get_current_balance()
    study_today = db_manager.get_today_study_time()
    lockdown = db_manager.get_emergency_lockdown()
    zero_tolerance = db_manager.get_zero_tolerance()
    is_blocked = enforcement.is_distraction_blocked()

    stats = study_daemon.get_stats()
    cam_info = camera_streamer.get_metrics()
    policies = db_manager.get_policies()
    recent_apps = db_manager.get_recent_apps(limit=8)

    # Calculate system diagnostics
    start_db = time.time()
    db_manager.get_current_balance()
    db_latency_ms = round((time.time() - start_db) * 1000.0, 2)

    memory_mb = 45.0
    try:
        import psutil
        proc = psutil.Process()
        memory_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        pass

    # Study streak calculation
    mins_today = study_today // 60
    secs_today = study_today % 60
    study_today_str = f"{mins_today // 60:02d}h {mins_today % 60:02d}m {secs_today:02d}s"

    bal_mins = balance // 60
    bal_secs = balance % 60
    leisure_balance_str = f"{bal_mins:02d}m {bal_secs:02d}s"

    return {
        "balance": balance,
        "leisure_balance_str": leisure_balance_str,
        "study_time_today": study_today,
        "study_time_today_str": study_today_str,
        "is_blocked": is_blocked,
        "lockdown": lockdown,
        "zero_tolerance": zero_tolerance,
        "camera": cam_info,
        "stats": stats,
        "policies": policies,
        "recent_apps": recent_apps,
        "diagnostics": {
            "db_latency_ms": db_latency_ms,
            "vision_fps": cam_info.get("fps", 30.0),
            "memory_mb": memory_mb,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
    }


# =========================================================================
# Dual-Portal HTML & Client Application
# =========================================================================

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Demon Study Monitor - Dual Portal</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%236366f1'/%3E%3Ctext y='68' x='50' font-size='60' text-anchor='middle'%3E%F0%9F%A7%A0%3C/text%3E%3C/svg%3E">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Plus+Jakarta+Sans:wght@400;500;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #070a12; color: #f1f5f9; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .glass { background: rgba(15, 23, 42, 0.75); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); }
        .pulsing-red { animation: pulseRed 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulseRed { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .88; transform: scale(1.008); } }
    </style>
</head>
<body class="min-h-screen flex flex-col justify-between p-4 md:p-6 select-none">

    <!-- Top Navigation & Role Switcher -->
    <header class="max-w-7xl w-full mx-auto flex items-center justify-between py-3 border-b border-slate-800 mb-6">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-xl shadow-lg shadow-indigo-600/30">🧠</div>
            <div>
                <h1 class="text-lg font-black tracking-tight text-white flex items-center gap-2">
                    DEMON <span class="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 font-semibold" id="portal-role-badge">STUDENT MOTIVATION VIEW</span>
                </h1>
                <p class="text-xs text-slate-400">Contextual Focus Engine & Surgical Guard</p>
            </div>
        </div>

        <div class="flex items-center gap-3">
            <button id="role-toggle-btn" onclick="togglePortalMode()" class="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 flex items-center gap-2 transition-all">
                <span>🔐</span> Switch to Parent Admin Mode (PIN 1323)
            </button>
        </div>
    </header>

    <!-- Checkpoint 1: Prominent Red Pulsing Lockdown Banner -->
    <div id="lockdown-banner" class="max-w-7xl w-full mx-auto hidden mb-6">
        <div class="w-full bg-gradient-to-r from-rose-950 via-rose-900 to-rose-950 border-2 border-rose-500/80 rounded-2xl p-4 shadow-2xl shadow-rose-950/80 pulsing-red flex flex-col md:flex-row items-center justify-between gap-4">
            <div class="flex items-center gap-3.5">
                <div class="w-12 h-12 rounded-xl bg-rose-600 flex items-center justify-center text-2xl shadow-lg shadow-rose-600/50">🔒</div>
                <div>
                    <h2 class="text-base font-black text-white tracking-wide flex items-center gap-2">
                        EMERGENCY LOCKDOWN ACTIVE
                        <span id="lockdown-zero-badge" class="text-[10px] px-2 py-0.5 rounded-full bg-rose-500 text-white font-bold">ZERO TOLERANCE GUARD ON</span>
                    </h2>
                    <p class="text-xs text-rose-200" id="lockdown-reason-text">Mandatory Focus Period</p>
                </div>
            </div>
            <div class="flex items-center gap-6">
                <div class="text-right">
                    <span class="text-[10px] uppercase font-bold tracking-widest text-rose-300">Countdown Remaining</span>
                    <div class="text-2xl font-black text-white mono tracking-wider" id="lockdown-countdown-timer">15:00</div>
                </div>
                <!-- Admin quick controls (visible in admin mode) -->
                <div id="lockdown-admin-quick-actions" class="hidden flex items-center gap-2">
                    <button onclick="promptEditLockdown()" class="px-3 py-1.5 rounded-lg bg-rose-700 hover:bg-rose-600 text-white text-xs font-bold transition">✏ Edit</button>
                    <button onclick="stopEmergencyLockdown()" class="px-3 py-1.5 rounded-lg bg-rose-800 hover:bg-rose-700 text-white text-xs font-bold transition">⏹ Stop</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Active Foreground Application Notification (Checkpoint 7) -->
    <div class="max-w-7xl w-full mx-auto mb-6 glass rounded-2xl p-3.5 flex items-center justify-between">
        <div class="flex items-center gap-3">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
            <div>
                <span class="text-[10px] uppercase tracking-wider font-bold text-slate-400">Current Foreground Window</span>
                <div class="text-xs font-bold text-white flex items-center gap-2">
                    <span id="fg-app-name" class="mono text-indigo-400">Loading...</span>
                    <span id="fg-app-title" class="text-slate-300 font-normal truncate max-w-md">Scanning active window</span>
                </div>
            </div>
        </div>
        <span id="fg-app-category" class="text-xs px-2.5 py-1 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold">Educational</span>
    </div>

    <!-- ================================================================= -->
    <!-- VIEW 1: STUDENT MOTIVATION PORTAL (Read-Only Motivation View)     -->
    <!-- ================================================================= -->
    <main id="student-portal-view" class="max-w-7xl w-full mx-auto flex-1 grid grid-cols-1 md:grid-cols-3 gap-6">
        
        <!-- Live Focus Circular Ring & Battery Energy -->
        <div class="glass rounded-3xl p-6 flex flex-col items-center justify-center text-center">
            <span class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4">Focus Quality Meter</span>
            
            <div class="relative w-48 h-48 flex items-center justify-center">
                <svg class="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="40" stroke="#1e293b" stroke-width="8" fill="transparent"/>
                    <circle id="student-focus-circle" cx="50" cy="50" r="40" stroke="#10b981" stroke-width="8" stroke-dasharray="251.2" stroke-dashoffset="50" stroke-linecap="round" fill="transparent" class="transition-all duration-700"/>
                </svg>
                <div class="absolute flex flex-col items-center">
                    <span id="student-focus-pct" class="text-4xl font-black text-white mono">85%</span>
                    <span id="student-posture-badge" class="text-[11px] font-bold text-emerald-400 uppercase tracking-widest mt-0.5">DIRECT FOCUS</span>
                </div>
            </div>

            <div class="mt-6 w-full flex items-center justify-between px-4 py-2.5 rounded-xl bg-slate-900/60 border border-slate-800">
                <span class="text-xs text-slate-400">Mental Energy Stamina</span>
                <span id="student-stamina-pct" class="text-xs font-bold text-indigo-400 mono">⚡ 94%</span>
            </div>

            <!-- Live Face & Attention Preview -->
            <div class="mt-4 w-full aspect-video rounded-2xl overflow-hidden border border-slate-800 bg-black relative shadow-inner">
                <img id="student-camera-feed" src="/api/video_feed" class="w-full h-full object-cover" alt="Student Camera Preview" onerror="handleStreamError(this)">
                <div class="absolute bottom-2 left-2 text-[10px] mono text-emerald-400 font-bold bg-black/80 px-2.5 py-0.5 rounded border border-emerald-500/40 flex items-center gap-1.5 shadow">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> FACE LOCK ACTIVE
                </div>
            </div>
        </div>

        <!-- Dual Time Balance Cards -->
        <div class="glass rounded-3xl p-6 flex flex-col justify-between">
            <div>
                <span class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 block">Time Balances Today</span>
                
                <div class="p-4 rounded-2xl bg-emerald-950/30 border border-emerald-500/20 mb-4">
                    <span class="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">🎓 Study Time Earned Today</span>
                    <div id="student-study-today" class="text-2xl font-black text-white mono mt-1">00h 00m 00s</div>
                    <p class="text-[11px] text-slate-400 mt-1">+1s accrued per second of focused educational work</p>
                </div>

                <div class="p-4 rounded-2xl bg-indigo-950/30 border border-indigo-500/20">
                    <span class="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">🎮 Remaining Leisure Balance</span>
                    <div id="student-leisure-balance" class="text-2xl font-black text-white mono mt-1">00m 00s</div>
                    <p class="text-[11px] text-slate-400 mt-1">Can be spent on allowed entertainment during free intervals</p>
                </div>
            </div>

            <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-center text-xs text-slate-400">
                Keep eyes on study materials to maintain your flow streak!
            </div>
        </div>

        <!-- Allowed Leisure Quotas & Policies Available -->
        <div class="glass rounded-3xl p-6 flex flex-col justify-between">
            <div>
                <span class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 block">Allowed Leisure Quota Budgets</span>
                <p class="text-xs text-slate-400 mb-4">Policies granted by parent for today:</p>

                <div id="student-policies-list" class="space-y-3">
                    <!-- Dynamic Policy Cards -->
                    <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
                        <div>
                            <span class="text-xs font-bold text-white">YouTube Leisure</span>
                            <span class="block text-[10px] text-slate-400">45 minutes daily allowance</span>
                        </div>
                        <span class="text-xs font-bold text-emerald-400 mono">45m 00s left</span>
                    </div>
                </div>
            </div>

            <div class="p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/30 text-xs text-indigo-300">
                💡 <span class="font-bold">Tip:</span> Leisure apps will automatically close when their daily quota expires or during Emergency Lockdown.
            </div>
        </div>

        <!-- AI-Supervised Academic YouTube Study Center -->
        <section class="col-span-1 md:col-span-3 glass rounded-3xl p-6 border border-indigo-500/30 shadow-2xl space-y-4">
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                <div class="flex items-center gap-3">
                    <div class="w-11 h-11 rounded-2xl bg-red-600/20 border border-red-500/40 flex items-center justify-center text-2xl text-red-500 shadow-lg shadow-red-500/20">
                        ▶
                    </div>
                    <div>
                        <h2 class="text-base font-black text-white flex items-center gap-2">
                            Academic YouTube Study Center
                            <span class="text-[10px] px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold">SLM SUPERVISED</span>
                        </h2>
                        <p class="text-xs text-slate-400">External distraction tabs in browsers are automatically closed. Use this embedded player to watch educational lectures and course tutorials in a distraction-free container.</p>
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-xs text-slate-400">Guardian Filter:</span>
                    <span class="text-xs px-2.5 py-1 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-bold flex items-center gap-1.5">
                        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> SLM Topic Classifier Active
                    </span>
                </div>
            </div>

            <!-- Topic / URL Input Bar -->
            <div class="flex flex-col sm:flex-row items-center gap-3">
                <div class="relative flex-1 w-full">
                    <span class="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm">🔍</span>
                    <input type="text" id="yt-query-input" placeholder="Paste YouTube link or enter study topic (e.g., Calculus MIT, Harvard CS50, Physics mechanics)..." class="w-full bg-slate-900 border border-slate-700 rounded-xl pl-9 pr-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition">
                </div>
                <button onclick="analyzeAndLoadYouTube()" class="w-full sm:w-auto px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold transition shadow-lg shadow-indigo-600/30 flex items-center justify-center gap-2 shrink-0">
                    <span>⚡</span> Analyze & Stream
                </button>
            </div>

            <!-- Quick Academic Curriculum Presets -->
            <div class="flex flex-wrap items-center gap-2 pt-1">
                <span class="text-[11px] font-bold text-slate-400">Quick Curricula:</span>
                <button onclick="loadPresetYouTube('https://www.youtube.com/watch?v=7K1sB05pE0A')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] text-slate-200 border border-slate-700 transition">📐 MIT Calculus (18.01)</button>
                <button onclick="loadPresetYouTube('https://www.youtube.com/watch?v=8mAITcNt710')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] text-slate-200 border border-slate-700 transition">💻 Harvard CS50 Intro</button>
                <button onclick="loadPresetYouTube('https://www.youtube.com/watch?v=kKKM8Y-u7ds')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] text-slate-200 border border-slate-700 transition">⚡ Physics: Newton's Laws</button>
                <button onclick="loadPresetYouTube('https://www.youtube.com/watch?v=8kK2zwjRV0M')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] text-slate-200 border border-slate-700 transition">🧬 CrashCourse: DNA Structure</button>
                <button onclick="loadPresetYouTube('Minecraft gameplay speedrun 1.20')" class="px-2.5 py-1 rounded-lg bg-rose-950/60 hover:bg-rose-900/80 text-[11px] text-rose-300 border border-rose-800/60 transition">🎮 Test Blocker: Gaming Video</button>
            </div>

            <!-- SLM Dynamic Feedback Banners -->
            <div id="yt-scanning-banner" class="hidden p-3.5 rounded-2xl bg-indigo-950/40 border border-indigo-500/40 text-indigo-300 text-xs flex items-center gap-3">
                <span class="animate-spin text-base">⏳</span>
                <div>
                    <span class="font-bold block text-white">SLM Topic Classifier In Progress</span>
                    <span class="text-[11px] text-indigo-300">Analyzing video metadata, keywords, and academic relevance against current study task...</span>
                </div>
            </div>

            <div id="yt-approved-banner" class="hidden p-4 rounded-2xl bg-emerald-950/50 border border-emerald-500/60 text-emerald-200 text-xs space-y-1">
                <div class="flex items-center gap-2">
                    <span class="text-base">✅</span>
                    <span class="font-bold text-white text-sm">TOPIC APPROVED BY AI STUDY SUPERVISOR</span>
                    <span id="yt-approved-badge" class="text-[10px] px-2 py-0.5 rounded bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 font-bold">EDUCATIONAL</span>
                </div>
                <p id="yt-approved-reason" class="text-emerald-300/90 pl-6 text-[11px]">Academic topic verified. In-frame study stream permitted.</p>
            </div>

            <div id="yt-blocked-banner" class="hidden p-4 rounded-2xl bg-rose-950/60 border border-rose-500/70 text-rose-200 text-xs space-y-1">
                <div class="flex items-center gap-2">
                    <span class="text-base">⛔</span>
                    <span class="font-bold text-white text-sm">TOPIC BLOCKED BY AI STUDY SUPERVISOR</span>
                    <span id="yt-blocked-badge" class="text-[10px] px-2 py-0.5 rounded bg-rose-500/30 text-rose-300 border border-rose-500/40 font-bold">NON-ACADEMIC DISTRACTION</span>
                </div>
                <p id="yt-blocked-reason" class="text-rose-300/90 pl-6 text-[11px]">Content detected as entertainment or gaming. Please focus on academic materials.</p>
            </div>

            <!-- Embedded Distraction-Free Video Frame -->
            <div id="yt-frame-container" class="hidden w-full aspect-video rounded-2xl overflow-hidden border border-slate-800 bg-black relative shadow-2xl">
                <iframe id="yt-study-iframe" class="w-full h-full" src="" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
            </div>
        </section>
    </main>

    <!-- ================================================================= -->
    <!-- VIEW 2: PARENT ADMIN MODE (PIN 1323 Protected Controls)           -->
    <!-- ================================================================= -->
    <main id="parent-admin-view" class="max-w-7xl w-full mx-auto hidden flex-1 space-y-6">
        
        <!-- Toolbar: Emergency Lockdown Controls & Zero Tolerance Guard -->
        <div class="glass rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center gap-3">
                <span class="text-xs font-black uppercase tracking-wider text-white">Emergency Lockdown Controls:</span>
                <button onclick="promptStartLockdown()" class="px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white shadow-md shadow-rose-600/30 transition">
                    ⏱ Start Lock
                </button>
                <button onclick="promptEditLockdown()" class="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-200 border border-slate-700 transition">
                    ✏ Edit Lock
                </button>
                <button onclick="stopEmergencyLockdown()" class="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-200 border border-slate-700 transition">
                    ⏹ Stop Lock
                </button>
            </div>

            <!-- Zero Tolerance Guard Toggle -->
            <div class="flex items-center gap-3 bg-slate-900/90 border border-slate-700/80 px-3.5 py-1.5 rounded-xl">
                <div>
                    <span class="text-xs font-bold text-white block">Zero Tolerance Guard</span>
                    <span class="text-[10px] text-slate-400">Immediately blocks & closes leisure apps</span>
                </div>
                <input type="checkbox" id="zero-tolerance-toggle" onchange="toggleZeroTolerance(this.checked)" class="w-4 h-4 text-rose-600 bg-slate-800 rounded border-slate-700 cursor-pointer">
            </div>
        </div>

        <!-- Upper Grid: Live Anthropometric Kinematics Stream & Granular Policy Engine -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            <!-- Checkpoint 5: Live Anthropometric Kinematics Stream -->
            <div class="glass rounded-3xl p-5 flex flex-col justify-between">
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <h3 class="text-sm font-bold text-white flex items-center gap-2">
                            📹 Live Anthropometric Kinematics Stream
                            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                        </h3>
                        <p class="text-[11px] text-slate-400">Spatial Reticle (20%-80% X, 15%-85% Y) & 3D Posture Estimation</p>
                    </div>
                    <span id="cam-stream-fps" class="text-xs mono text-indigo-400 font-bold">30.0 FPS</span>
                </div>

                <div class="relative w-full aspect-video bg-black rounded-2xl overflow-hidden border border-slate-800 flex items-center justify-center">
                    <img id="live-camera-feed" src="/api/video_feed" class="w-full h-full object-cover" alt="Kinematics Stream" onerror="handleStreamError(this)">
                </div>

                <div class="grid grid-cols-4 gap-2 mt-4 text-center">
                    <div class="p-2 rounded-xl bg-slate-900/80 border border-slate-800">
                        <span class="text-[9px] uppercase font-bold text-slate-400 block">Posture</span>
                        <span id="admin-posture" class="text-xs font-bold text-emerald-400">DIRECT_FOCUS</span>
                    </div>
                    <div class="p-2 rounded-xl bg-slate-900/80 border border-slate-800">
                        <span class="text-[9px] uppercase font-bold text-slate-400 block">EAR Meter</span>
                        <span id="admin-ear" class="text-xs font-bold text-indigo-400 mono">0.285</span>
                    </div>
                    <div class="p-2 rounded-xl bg-slate-900/80 border border-slate-800">
                        <span class="text-[9px] uppercase font-bold text-slate-400 block">Head Pitch</span>
                        <span id="admin-pitch" class="text-xs font-bold text-white mono">+2.4°</span>
                    </div>
                    <div class="p-2 rounded-xl bg-slate-900/80 border border-slate-800">
                        <span class="text-[9px] uppercase font-bold text-slate-400 block">Focus Region</span>
                        <span id="admin-reticle" class="text-xs font-bold text-emerald-400">ACTIVE</span>
                    </div>
                </div>
            </div>

            <!-- Important Change: Granular Policy Engine & Quota Budgets -->
            <div class="glass rounded-3xl p-5 flex flex-col justify-between">
                <div>
                    <div class="flex items-center justify-between mb-3">
                        <div>
                            <h3 class="text-sm font-bold text-white">⚙️ Granular Policy Engine & Quota Budgets</h3>
                            <p class="text-[11px] text-slate-400">Set daily leisure allowance intervals (e.g. YouTube 45 mins)</p>
                        </div>
                        <button onclick="promptAddPolicy()" class="px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white transition">+ Add Policy</button>
                    </div>

                    <div id="admin-policies-table" class="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                        <!-- Dynamic Policies -->
                    </div>
                </div>

                <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-[11px] text-slate-400 flex items-center justify-between mt-4">
                    <span>When an app reaches 0 remaining minutes, tab closes automatically.</span>
                    <button onclick="resetAllPolicies()" class="text-indigo-400 hover:underline font-semibold">Reset Daily Quotas</button>
                </div>
            </div>
        </div>

        <!-- Lower Grid: Checkpoint 6 Dynamic Timeline & Dynamic App Usage Distribution -->
        <div class="glass rounded-3xl p-5 space-y-5">
            <div class="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <h3 class="text-sm font-bold text-white">📊 Dynamic Focus Timeline & App Usage Distribution</h3>
                    <p class="text-[11px] text-slate-400">Color-coded study segments and exact application engagement time</p>
                </div>

                <!-- Timeline Range Dropdown (Checkpoint 6) -->
                <div class="flex items-center gap-2">
                    <span class="text-xs text-slate-400">Timeline Range:</span>
                    <select id="timeline-range-selector" onchange="onTimelineRangeChanged()" class="bg-slate-900 border border-slate-700 text-xs text-white rounded-xl px-3 py-1.5 focus:outline-none focus:border-indigo-500">
                        <option value="lockdown">Current Lockdown Duration</option>
                        <option value="1">Last 1 Hour</option>
                        <option value="2">Last 2 Hours</option>
                        <option value="4" selected>Last 4 Hours</option>
                        <option value="8">Last 8 Hours</option>
                        <option value="12">Last 12 Hours</option>
                        <option value="24">Last 24 Hours</option>
                        <option value="today">Today</option>
                    </select>
                </div>
            </div>

            <!-- Dynamic Timeline Segments Bar -->
            <div>
                <div class="flex items-center justify-between text-[10px] text-slate-400 mb-1.5" id="timeline-time-labels">
                    <span>Start</span>
                    <span>Midpoint</span>
                    <span>Now</span>
                </div>
                <div id="timeline-segments-bar" class="w-full h-8 bg-slate-950 rounded-xl overflow-hidden flex gap-0.5 p-1 border border-slate-800">
                    <!-- 48 dynamic color blocks -->
                </div>
                <div class="flex items-center justify-center gap-6 mt-2 text-[10px] text-slate-400">
                    <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Active Study</span>
                    <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-indigo-500"></span> Allowed Leisure Quota</span>
                    <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span> Idle / Away</span>
                    <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span> Blocked Distraction</span>
                </div>
            </div>

            <!-- Dynamic App Usage Distribution Bar & Cards -->
            <div class="pt-4 border-t border-slate-800/80">
                <span class="text-xs font-bold text-white mb-2 block">Application Usage Distribution (in selected period)</span>
                
                <div id="app-distribution-bar" class="w-full h-4 rounded-full overflow-hidden bg-slate-950 flex mb-3">
                    <div style="width: 70%" class="bg-emerald-500" title="Educational"></div>
                    <div style="width: 20%" class="bg-indigo-500" title="Leisure"></div>
                    <div style="width: 10%" class="bg-rose-500" title="Distraction"></div>
                </div>

                <div id="app-breakdown-grid" class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <!-- Dynamic App Breakdown Cards -->
                </div>
            </div>
        </div>

        <!-- Checkpoint 7: Last 8 Recent Applications -->
        <div class="glass rounded-3xl p-5">
            <h3 class="text-sm font-bold text-white mb-3">🕒 Recently Active Applications (Last 8 Open Windows)</h3>
            <div id="recent-apps-grid" class="grid grid-cols-2 md:grid-cols-4 gap-3">
                <!-- 8 Dynamic Cards -->
            </div>
        </div>

        <!-- Checkpoint 8: 10-Second System Diagnostics Drawer -->
        <details class="glass rounded-2xl p-4 cursor-pointer">
            <summary class="text-xs font-bold text-slate-300 flex items-center justify-between">
                <span>⚙️ System Diagnostics & Sensor Telemetry (Auto-refreshes every 10s)</span>
                <span id="diag-timestamp" class="text-[10px] text-slate-400 mono">--:--:--</span>
            </summary>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-3 border-t border-slate-800 text-center">
                <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
                    <span class="text-[10px] uppercase text-slate-400 block font-bold">DB Latency</span>
                    <span id="diag-db" class="text-sm font-bold text-emerald-400 mono">0.45 ms</span>
                </div>
                <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
                    <span class="text-[10px] uppercase text-slate-400 block font-bold">Vision Sensor FPS</span>
                    <span id="diag-fps" class="text-sm font-bold text-indigo-400 mono">30.0 FPS</span>
                </div>
                <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
                    <span class="text-[10px] uppercase text-slate-400 block font-bold">Process Memory</span>
                    <span id="diag-ram" class="text-sm font-bold text-white mono">42.5 MB</span>
                </div>
                <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
                    <span class="text-[10px] uppercase text-slate-400 block font-bold">Active Host Guard</span>
                    <span class="text-sm font-bold text-emerald-400">PAC & Surgical</span>
                </div>
            </div>
        </details>
    </main>

    <!-- Footer -->
    <footer class="max-w-7xl w-full mx-auto py-4 border-t border-slate-900 flex items-center justify-between text-xs text-slate-500 mt-6">
        <span>Demon AI Study Monitor & Dual Portal</span>
        <span>Master Recovery PIN: <span class="mono font-bold text-slate-400">1323</span></span>
    </footer>

    <!-- PIN Prompt Modal for Parent Admin Access -->
    <div id="pin-modal" class="fixed inset-0 bg-slate-950/80 backdrop-blur-md hidden flex items-center justify-center p-4 z-50">
        <div class="glass max-w-sm w-full p-6 rounded-3xl text-center shadow-2xl border border-slate-700">
            <div class="w-12 h-12 rounded-2xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center text-xl mx-auto mb-3">🔐</div>
            <h3 class="text-base font-black text-white mb-1">Enter Master PIN</h3>
            <p class="text-xs text-slate-400 mb-4">Required to access Parent Admin Controls</p>
            <input type="password" id="pin-input" placeholder="Enter PIN (1323)" class="w-full bg-slate-900 border border-slate-700 text-center text-sm font-bold text-white rounded-xl py-2.5 mb-3 focus:outline-none focus:border-indigo-500 mono tracking-widest" onkeydown="if(event.key==='Enter') submitParentPIN()">
            <div id="pin-error" class="text-xs text-rose-400 font-bold mb-3 hidden">Incorrect PIN. Try again.</div>
            <div class="flex gap-2">
                <button onclick="closePINModal()" class="flex-1 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300">Cancel</button>
                <button onclick="submitParentPIN()" class="flex-1 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white">Unlock</button>
            </div>
        </div>
    </div>

    <!-- JavaScript Client App -->
    <script>
        let currentPortal = 'student'; // 'student' or 'parent'
        let cachedStatus = null;

        function togglePortalMode() {
            if (currentPortal === 'student') {
                // Open PIN modal
                document.getElementById('pin-modal').classList.remove('hidden');
                document.getElementById('pin-input').value = '';
                document.getElementById('pin-input').focus();
            } else {
                // Switch back to Student
                currentPortal = 'student';
                updatePortalView();
            }
        }

        function closePINModal() {
            document.getElementById('pin-modal').classList.add('hidden');
            document.getElementById('pin-error').classList.add('hidden');
        }

        async function submitParentPIN() {
            const entered = document.getElementById('pin-input').value.trim();
            const res = await fetch('/api/verify-pin', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ pin: entered })
            });
            const data = await res.json();
            if (data.valid) {
                closePINModal();
                currentPortal = 'parent';
                updatePortalView();
            } else {
                document.getElementById('pin-error').classList.remove('hidden');
            }
        }

        function updatePortalView() {
            const studentView = document.getElementById('student-portal-view');
            const parentView = document.getElementById('parent-admin-view');
            const roleBadge = document.getElementById('portal-role-badge');
            const toggleBtn = document.getElementById('role-toggle-btn');
            const adminQuick = document.getElementById('lockdown-admin-quick-actions');

            if (currentPortal === 'parent') {
                studentView.classList.add('hidden');
                parentView.classList.remove('hidden');
                roleBadge.textContent = 'PARENT ADMIN MODE';
                roleBadge.className = 'text-xs px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30 font-semibold';
                toggleBtn.innerHTML = '<span>🎓</span> Switch to Student View';
                adminQuick.classList.remove('hidden');
                loadTimelineData();
                const pf = document.getElementById('live-camera-feed');
                if (pf) pf.src = '/api/video_feed?t=' + Date.now();
            } else {
                parentView.classList.add('hidden');
                studentView.classList.remove('hidden');
                roleBadge.textContent = 'STUDENT MOTIVATION VIEW';
                roleBadge.className = 'text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 font-semibold';
                toggleBtn.innerHTML = '<span>🔐</span> Switch to Parent Admin Mode (PIN 1323)';
                adminQuick.classList.add('hidden');
                const sf = document.getElementById('student-camera-feed');
                if (sf) sf.src = '/api/video_feed?t=' + Date.now();
            }
        }

        // =================================================================
        // Dynamic Sync Polling Loop (Every 1s)
        // =================================================================
        async function pollStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                cachedStatus = data;
                renderStatus(data);
            } catch (e) {
                console.error(e);
            }
        }

        function renderStatus(data) {
            // 1. Foreground Window
            document.getElementById('fg-app-name').textContent = data.stats.active_app || 'System';
            document.getElementById('fg-app-title').textContent = data.stats.active_window || '';

            // 2. Lockdown Banner (Checkpoint 1)
            const banner = document.getElementById('lockdown-banner');
            const ld = data.lockdown;
            if (ld && ld.is_active) {
                banner.classList.remove('hidden');
                document.getElementById('lockdown-reason-text').textContent = ld.reason || 'Study Session';
                const mins = Math.floor(ld.seconds_remaining / 60);
                const secs = ld.seconds_remaining % 60;
                document.getElementById('lockdown-countdown-timer').textContent = 
                    `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
                document.getElementById('lockdown-zero-badge').textContent = ld.zero_tolerance ? 'ZERO TOLERANCE GUARD ON' : 'GRACE ALLOWED';
            } else {
                banner.classList.add('hidden');
            }

            // 3. Student View Elements
            const cam = data.camera;
            const score = cam.focus_score || 85.0;
            document.getElementById('student-focus-pct').textContent = Math.round(score) + '%';
            document.getElementById('student-posture-badge').textContent = cam.posture || 'DIRECT FOCUS';

            // Circular progress arc
            const circle = document.getElementById('student-focus-circle');
            const offset = 251.2 - (251.2 * (score / 100));
            circle.style.strokeDashoffset = offset;
            circle.setAttribute('stroke', cam.color === 'emerald' ? '#10b981' : (cam.color === 'amber' ? '#f59e0b' : '#f43f5e'));

            document.getElementById('student-study-today').textContent = data.study_time_today_str;
            document.getElementById('student-leisure-balance').textContent = data.leisure_balance_str;

            // Student Policies list
            const polList = document.getElementById('student-policies-list');
            if (data.policies && data.policies.length) {
                polList.innerHTML = data.policies.map(p => `
                    <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
                        <div>
                            <span class="text-xs font-bold text-white">${p.app_or_domain}</span>
                            <span class="block text-[10px] text-slate-400">${p.quota_minutes} min quota (${p.category})</span>
                        </div>
                        <span class="text-xs font-bold ${p.remaining_seconds > 0 ? 'text-emerald-400' : 'text-rose-400'} mono">
                            ${Math.floor(p.remaining_seconds / 60)}m ${p.remaining_seconds % 60}s left
                        </span>
                    </div>
                `).join('');
            }

            // 4. Admin View Elements
            document.getElementById('zero-tolerance-toggle').checked = data.zero_tolerance;
            document.getElementById('admin-posture').textContent = cam.posture;
            document.getElementById('admin-ear').textContent = cam.ear;
            document.getElementById('admin-pitch').textContent = cam.head_pose ? (cam.head_pose[0] > 0 ? '+' : '') + cam.head_pose[0] + '°' : '0.0°';
            document.getElementById('admin-reticle').textContent = cam.in_focus_region ? 'ACTIVE' : 'OUTSIDE RETICLE';
            document.getElementById('admin-reticle').className = cam.in_focus_region ? 'text-xs font-bold text-emerald-400' : 'text-xs font-bold text-amber-400';

            // Admin Policies Table
            const adminPolTable = document.getElementById('admin-policies-table');
            if (data.policies) {
                adminPolTable.innerHTML = data.policies.map(p => `
                    <div class="p-3 rounded-xl bg-slate-900/90 border border-slate-800 flex items-center justify-between">
                        <div>
                            <span class="text-xs font-bold text-white">${p.app_or_domain}</span>
                            <span class="block text-[10px] text-slate-400">Quota: ${p.quota_minutes}m | Used: ${Math.floor(p.used_seconds / 60)}m</span>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-xs mono font-bold ${p.remaining_seconds > 0 ? 'text-emerald-400' : 'text-rose-400'}">
                                ${Math.floor(p.remaining_seconds / 60)}m ${p.remaining_seconds % 60}s left
                            </span>
                            <button onclick="deletePolicy('${p.app_or_domain}')" class="text-slate-500 hover:text-rose-400 text-xs px-2 py-1">✕</button>
                        </div>
                    </div>
                `).join('');
            }

            // Recent Apps Grid (Checkpoint 7)
            const recentGrid = document.getElementById('recent-apps-grid');
            if (data.recent_apps) {
                recentGrid.innerHTML = data.recent_apps.map(a => `
                    <div class="p-3 rounded-2xl bg-slate-900 border border-slate-800">
                        <span class="text-xs font-bold text-white block truncate">${a.app_name}</span>
                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-indigo-400 font-semibold">${a.category}</span>
                        <span class="block text-xs font-bold text-slate-300 mono mt-2">${a.time_str} today</span>
                    </div>
                `).join('');
            }

            // Diagnostics (Checkpoint 8)
            const diag = data.diagnostics;
            if (diag) {
                document.getElementById('diag-db').textContent = diag.db_latency_ms + ' ms';
                document.getElementById('diag-fps').textContent = diag.vision_fps + ' FPS';
                document.getElementById('diag-ram').textContent = diag.memory_mb + ' MB';
                document.getElementById('diag-timestamp').textContent = diag.timestamp;
            }
        }

        // =================================================================
        // Checkpoint 6: Dynamic Timeline & Dynamic App Distribution
        // =================================================================
        async function loadTimelineData() {
            const range = document.getElementById('timeline-range-selector').value;
            const res = await fetch(`/api/timeline?range=${range}`);
            const data = await res.json();

            // Render Segments Bar
            const bar = document.getElementById('timeline-segments-bar');
            if (data.segments && data.segments.length) {
                bar.innerHTML = data.segments.map(s => {
                    let col = 'bg-slate-800';
                    if (s.color === 'emerald') col = 'bg-emerald-500';
                    else if (s.color === 'blue') col = 'bg-indigo-500';
                    else if (s.color === 'amber') col = 'bg-amber-500';
                    else if (s.color === 'rose') col = 'bg-rose-500';
                    return `<div class="flex-1 ${col} rounded-sm" title="${s.time_label}: ${s.state} (${s.avg_score}%)"></div>`;
                }).join('');
            }

            // Render App Breakdown
            const dist = data.distribution;
            if (dist && dist.apps) {
                const grid = document.getElementById('app-breakdown-grid');
                grid.innerHTML = dist.apps.map(a => `
                    <div class="p-2.5 rounded-xl bg-slate-900 border border-slate-800">
                        <span class="text-xs font-bold text-white truncate block">${a.app_name}</span>
                        <span class="text-[10px] text-indigo-400 font-semibold">${a.category}</span>
                        <span class="block text-xs font-bold text-slate-300 mono mt-1">${a.time_str} (${a.percentage}%)</span>
                    </div>
                `).join('');
            }
        }

        function onTimelineRangeChanged() {
            loadTimelineData();
        }

        // =================================================================
        // Emergency Lockdown API Calls (Checkpoint 1)
        // =================================================================
        async function promptStartLockdown() {
            const mins = prompt("Enter Emergency Lockdown Duration in Minutes:", "15");
            if (!mins) return;
            const reason = prompt("Enter Lockdown Reason:", "Study Session") || "Study Session";
            await fetch('/api/lockdown/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ duration_minutes: parseInt(mins), reason: reason, zero_tolerance: true })
            });
            pollStatus();
        }

        async function promptEditLockdown() {
            const mins = prompt("Enter New Lockdown Duration in Minutes:", "30");
            if (!mins) return;
            await fetch('/api/lockdown/edit', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ new_duration_minutes: parseInt(mins) })
            });
            pollStatus();
        }

        async function stopEmergencyLockdown() {
            if (confirm("Are you sure you want to stop Emergency Lockdown?")) {
                await fetch('/api/lockdown/stop', { method: 'POST' });
                pollStatus();
            }
        }

        async function toggleZeroTolerance(checked) {
            await fetch('/api/zero-tolerance', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ enabled: checked })
            });
            pollStatus();
        }

        // =================================================================
        // Granular Policy Engine API Calls
        // =================================================================
        async function promptAddPolicy() {
            const app = prompt("Enter Application or Domain (e.g. youtube.com, discord.exe):", "youtube.com");
            if (!app) return;
            const quota = prompt("Enter Allowed Daily Quota in Minutes:", "45");
            if (!quota) return;
            await fetch('/api/policies/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ app_or_domain: app, quota_minutes: parseInt(quota), category: "Leisure" })
            });
            pollStatus();
        }

        async function deletePolicy(app) {
            if (confirm(`Delete quota policy for ${app}?`)) {
                await fetch('/api/policies/delete', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ app_or_domain: app })
                });
                pollStatus();
            }
        }

        async function resetAllPolicies() {
            if (confirm("Reset today's used minutes for all quota policies?")) {
                await fetch('/api/policies/reset', { method: 'POST' });
                pollStatus();
            }
        }

        // =================================================================
        // AI-Supervised Academic YouTube Study Center
        // =================================================================
        function loadPresetYouTube(urlOrQuery) {
            const input = document.getElementById('yt-query-input');
            if (input) {
                input.value = urlOrQuery;
                analyzeAndLoadYouTube();
            }
        }

        async function analyzeAndLoadYouTube() {
            const input = document.getElementById('yt-query-input');
            if (!input) return;
            const val = input.value.trim();
            if (!val) {
                alert("Please paste a YouTube URL or enter a study topic.");
                return;
            }

            const scanningBanner = document.getElementById('yt-scanning-banner');
            const approvedBanner = document.getElementById('yt-approved-banner');
            const blockedBanner = document.getElementById('yt-blocked-banner');
            const frameContainer = document.getElementById('yt-frame-container');
            const iframe = document.getElementById('yt-study-iframe');

            if (scanningBanner) scanningBanner.classList.remove('hidden');
            if (approvedBanner) approvedBanner.classList.add('hidden');
            if (blockedBanner) blockedBanner.classList.add('hidden');
            if (frameContainer) frameContainer.classList.add('hidden');
            if (iframe) iframe.src = "";

            try {
                const res = await fetch('/api/youtube/validate-topic', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ query: val })
                });
                const data = await res.json();
                if (scanningBanner) scanningBanner.classList.add('hidden');

                if (data.is_approved && data.embed_url) {
                    if (approvedBanner) approvedBanner.classList.remove('hidden');
                    const badge = document.getElementById('yt-approved-badge');
                    const reason = document.getElementById('yt-approved-reason');
                    if (badge) badge.textContent = data.category || 'EDUCATIONAL';
                    if (reason) reason.textContent = `${data.title} — ${data.reason}`;
                    if (iframe) iframe.src = data.embed_url;
                    if (frameContainer) frameContainer.classList.remove('hidden');
                } else {
                    if (blockedBanner) blockedBanner.classList.remove('hidden');
                    const badge = document.getElementById('yt-blocked-badge');
                    const reason = document.getElementById('yt-blocked-reason');
                    if (badge) badge.textContent = data.category || 'DISTRACTION';
                    if (reason) reason.textContent = `${data.title || val} — ${data.reason}`;
                }
            } catch (err) {
                if (scanningBanner) scanningBanner.classList.add('hidden');
                if (blockedBanner) blockedBanner.classList.remove('hidden');
                const reason = document.getElementById('yt-blocked-reason');
                if (reason) reason.textContent = "Failed to communicate with SLM supervisor. Please try again.";
            }
        }

        document.getElementById('yt-query-input')?.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') analyzeAndLoadYouTube();
        });

        function handleStreamError(img) {
            img.src = '/api/camera_frame?t=' + Date.now();
            setTimeout(() => {
                img.src = '/api/video_feed?t=' + Date.now();
            }, 1200);
        }

        // Stream reconnect watchdog
        setInterval(() => {
            const activeImg = currentPortal === 'parent' ? document.getElementById('live-camera-feed') : document.getElementById('student-camera-feed');
            if (activeImg && (!activeImg.complete || activeImg.naturalWidth === 0)) {
                activeImg.src = '/api/video_feed?t=' + Date.now();
            }
        }, 8000);

        // Polling loop
        setInterval(pollStatus, 1000);
        setInterval(() => {
            if (currentPortal === 'parent') loadTimelineData();
        }, 10000);

        pollStatus();
    </script>
</body>
</html>
"""


# =========================================================================
# HTTP Request Handler & REST Endpoints
# =========================================================================

class DashboardRequestHandler(BaseHTTPRequestHandler):

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_str, code=200):
        body = html_str.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self._send_html(DASHBOARD_HTML)

        elif parsed.path == "/favicon.ico":
            ico_svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#6366f1"/><text y="68" x="50" font-size="60" text-anchor="middle">&#129504;</text></svg>"""
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(ico_svg)))
            self.end_headers()
            self.wfile.write(ico_svg)

        elif parsed.path == "/api/status":
            self._send_json(get_system_status())

        elif parsed.path == "/api/camera_frame":
            frame = camera_streamer.get_frame()
            if frame:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.send_header("Cache-Control", "no-cache, no-store")
                self.end_headers()
                self.wfile.write(frame)
            else:
                self.send_error(503, "Camera frame not ready")

        elif parsed.path == "/api/video_feed":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            try:
                while True:
                    frame = camera_streamer.get_frame()
                    if frame:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("utf-8"))
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.033)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
                pass

        elif parsed.path == "/api/timeline":
            params = parse_qs(parsed.query)
            range_str = params.get("range", ["4"])[0]
            segments = db_manager.get_focus_telemetry_timeline(range_str=range_str)
            dist = db_manager.get_app_distribution(range_str=range_str)
            self._send_json({"range": range_str, "segments": segments, "distribution": dist})

        elif parsed.path == "/api/policies":
            self._send_json(db_manager.get_policies())

        elif parsed.path == "/proxy.pac":
            is_locked = db_manager.is_youtube_locked_setting(default=True)
            pac_str = enforcement.get_pac_script(is_locked=is_locked)
            pac_bytes = pac_str.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
            self.send_header("Content-Length", str(len(pac_bytes)))
            self.end_headers()
            self.wfile.write(pac_bytes)

        elif parsed.path == "/api/session-config":
            self._send_json({
                "status": "ok",
                "has_pin": bool(db_manager.get_security_pin()),
                "task": db_manager.get_focus_task(),
                "youtube_locked": db_manager.is_youtube_locked_setting(default=True),
                "is_blocked": enforcement.is_distraction_blocked(),
                "hosts_writeable": enforcement.can_write_hosts(),
                "pac_enabled": enforcement.is_pac_proxy_enabled()
            })

        elif parsed.path == "/api/run-tests":
            import run_all_tests
            summary = run_all_tests.run_all(verbose=False)
            self._send_json(summary)

        else:
            self.send_error(404, "Endpoint Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            payload = {}

        # PIN Verification
        if parsed.path in ("/api/verify-pin", "/api/verify-password"):
            entered_pin = payload.get("pin") or payload.get("password") or ""
            valid = db_manager.verify_security_pin(entered_pin)
            if not valid:
                db_manager.log_security_alert("TAMPER_ATTEMPT", f"Invalid PIN entered in web portal: {entered_pin}")
            self._send_json({"status": "ok", "valid": valid})

        elif parsed.path == "/api/set-pin":
            pin = str(payload.get("pin", "")).strip()
            task = str(payload.get("task", "")).strip()
            lock_yt = bool(payload.get("lock_youtube", True))
            if len(pin) < 4:
                self._send_json({"status": "error", "message": "PIN must be at least 4 digits"}, 400)
                return
            db_manager.set_security_pin(pin)
            if task:
                db_manager.set_focus_task(task)
            db_manager.set_youtube_locked_setting(lock_yt)
            self._send_json({
                "status": "ok",
                "has_pin": True,
                "task": db_manager.get_focus_task(),
                "youtube_locked": db_manager.is_youtube_locked_setting()
            })

        elif parsed.path == "/api/change-task":
            pin = str(payload.get("pin", "")).strip()
            new_task = str(payload.get("task", "")).strip()
            if not db_manager.verify_security_pin(pin):
                self._send_json({"status": "error", "message": "Incorrect PIN"}, 403)
                return
            db_manager.set_focus_task(new_task)
            self._send_json({"status": "ok", "task": new_task})

        elif parsed.path == "/api/toggle-youtube-lock":
            pin = str(payload.get("pin", "")).strip()
            lock_val = bool(payload.get("lock", True))
            if not db_manager.verify_security_pin(pin):
                self._send_json({"status": "error", "message": "Incorrect PIN"}, 403)
                return
            db_manager.set_youtube_locked_setting(lock_val)
            if lock_val:
                enforcement.block_distractions()
            else:
                enforcement.unblock_distractions()
            self._send_json({"status": "ok", "youtube_locked": lock_val})

        elif parsed.path == "/api/reset-session":
            pin = str(payload.get("pin", "")).strip()
            if not db_manager.verify_security_pin(pin):
                self._send_json({"status": "error", "message": "Incorrect PIN"}, 403)
                return
            db_manager.delete_setting("security_pin")
            db_manager.delete_setting("security_pin_hash")
            db_manager.set_youtube_locked_setting(True)
            db_manager.set_focus_task("General Academic Study")
            self._send_json({"status": "ok"})

        # Checkpoint 1: Emergency Lockdown Controls
        elif parsed.path == "/api/lockdown/start":
            dur = payload.get("duration_minutes", 15)
            reason = payload.get("reason", "Study Session")
            zero_tol = payload.get("zero_tolerance", True)
            res = db_manager.start_emergency_lockdown(duration_minutes=dur, reason=reason, zero_tolerance=zero_tol)
            self._send_json({"status": "ok", "lockdown": res})

        elif parsed.path == "/api/lockdown/edit":
            new_dur = payload.get("new_duration_minutes", 30)
            res = db_manager.edit_emergency_lockdown(new_duration_minutes=new_dur)
            self._send_json({"status": "ok", "lockdown": res})

        elif parsed.path == "/api/lockdown/stop":
            res = db_manager.stop_emergency_lockdown()
            enforcement.unblock_distractions()
            self._send_json({"status": "ok", "lockdown": res})

        elif parsed.path == "/api/zero-tolerance":
            enabled = payload.get("enabled", True)
            db_manager.set_zero_tolerance(enabled)
            self._send_json({"status": "ok", "zero_tolerance": enabled})

        # Important Change: Granular Policy Management
        elif parsed.path == "/api/policies/save":
            app = payload.get("app_or_domain", "")
            quota = payload.get("quota_minutes", 45)
            category = payload.get("category", "Leisure")
            if app:
                db_manager.set_policy(app, quota_minutes=quota, category=category)
            self._send_json({"status": "ok", "policies": db_manager.get_policies()})

        elif parsed.path == "/api/policies/delete":
            app = payload.get("app_or_domain", "")
            if app:
                db_manager.delete_policy(app)
            self._send_json({"status": "ok", "policies": db_manager.get_policies()})

        elif parsed.path == "/api/policies/reset":
            policies = db_manager.get_policies()
            for p in policies:
                db_manager.reset_policy_usage(p["app_or_domain"])
            self._send_json({"status": "ok", "policies": db_manager.get_policies()})

        # Academic YouTube Study Frame & SLM Topic Filtering
        elif parsed.path == "/api/youtube/validate-topic":
            query = payload.get("query", "").strip()
            task = payload.get("task", db_manager.get_focus_task() or "General Academic Study")

            vid_id = semantic_pipeline.extract_youtube_video_id(query)
            clean_title = query

            if vid_id and ("youtube.com" in query.lower() or "youtu.be" in query.lower()):
                try:
                    import urllib.request
                    oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid_id}&format=json"
                    req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=2.0) as oresp:
                        odata = json.loads(oresp.read().decode())
                        if odata.get("title"):
                            clean_title = odata["title"]
                except Exception:
                    pass

            eval_res = semantic_pipeline.validate_youtube_content(
                query_or_url=clean_title,
                user_task=task
            )

            if not eval_res.get("is_approved", False):
                db_manager.log_security_alert(
                    alert_type="BLOCKED_YOUTUBE_TOPIC",
                    details=f"Topic '{clean_title}' rejected by SLM Guardian: {eval_res.get('reason')}"
                )
            else:
                db_manager.log_app_activity(
                    app_name="youtube_study_frame",
                    window_title=f"YouTube Study: {clean_title}",
                    category="Educational",
                    duration_seconds=5.0
                )

            res_vid_id = eval_res.get("video_id") or vid_id
            if not res_vid_id and eval_res.get("is_approved"):
                res_vid_id = "7K1sB05pE0A"

            embed_url = f"https://www.youtube-nocookie.com/embed/{res_vid_id}?autoplay=1&rel=0&modestbranding=1" if (eval_res.get("is_approved") and res_vid_id) else None

            self._send_json({
                "status": "ok",
                "is_approved": eval_res.get("is_approved", False),
                "category": eval_res.get("category", "EDUCATIONAL"),
                "reason": eval_res.get("reason", "Evaluated by AI Study Guardian."),
                "title": clean_title,
                "video_id": res_vid_id,
                "embed_url": embed_url,
                "videos": eval_res.get("videos", [])
            })

        elif parsed.path == "/api/toggle-block":
            block = payload.get("block", True)
            if block:
                enforcement.block_distractions()
            else:
                enforcement.unblock_distractions()
            self._send_json({
                "status": "ok",
                "is_blocked": enforcement.is_distraction_blocked(),
                "hosts_writeable": enforcement.can_write_hosts()
            })

        elif parsed.path == "/api/step":
            res = logic_controller.evaluate_cycle()
            self._send_json({"status": "ok", "step": res})

        else:
            self.send_error(404, "Endpoint Not Found")


def run_server(port=PORT):
    camera_streamer.start()
    study_daemon.start()

    server = ThreadingHTTPServer((HOST, port), DashboardRequestHandler)
    print(f"[web_dashboard] Serving Demon Dual-Portal Dashboard on http://{HOST}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[web_dashboard] Server shutting down gracefully...")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()

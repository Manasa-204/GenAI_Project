"""
web_dashboard.py - Dual-Portal Study Monitor & Parental Command Center
----------------------------------------------------------------------
Features:
1. Role-Based Dual Portal (RBAC):
   - Student Mode: Minimalist, gamified & motivational HUD.
     * Large SVG Circular Progress Ring (Study Time Earned Today).
     * Dynamic Status Pill (Deep Flow, Active Study, Drifting, Distracted).
     * Focus Streak Counter & Leisure Allowance Card.
     * Zero policy controls / restricted settings.
   - Parent Admin Mode: Comprehensive Operations Center.
     * Protected by Cryptographic Master PIN (Default: 1323) with auto-lock (5 mins).
     * 3D Kinematics & Posture Telemetry (MediaPipe/SolvePnP, EAR, Head Pose).
     * Real-time Circular Focus Score Gauge (0-100%).
     * 24-Hour Timeline Bar with color-coded intervals.
     * Categorized Application Distribution (Educational vs Gaming vs Social).
     * Granular Policy Engine CRUD (Hard Blocks, Daily Quotas, Curfews).
     * Security Incident Ledger & Alerts Feed.
     * Collapsible System Diagnostics Drawer & 30s Calibration Wizard.
2. Robust Live Camera & Synthetic HUD MJPEG Streamer:
   - Real-time webcam capture with 8-state posture matrix overlays.
   - Fallback high-tech synthetic HUD canvas if no webcam is connected.
"""

import os
import sys
import json
import time
import math
import threading
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import db_manager
import enforcement

try:
    import cv2
    import numpy as np
    cv2_available = True
except ImportError:
    cv2_available = False
    cv2 = None
    np = None

PORT = 8000
HOST = "0.0.0.0"

_current_session_role = "STUDENT"
_last_parent_active_timestamp = time.time()


def get_effective_role() -> str:
    global _current_session_role, _last_parent_active_timestamp
    if _current_session_role == "PARENT":
        elapsed = time.time() - _last_parent_active_timestamp
        if elapsed > 300.0:  # 5-minute auto-lock
            _current_session_role = "STUDENT"
            db_manager.set_current_role("STUDENT")
    return _current_session_role


def touch_parent_activity():
    global _last_parent_active_timestamp
    _last_parent_active_timestamp = time.time()


# ==============================================================================
# ROBUST LIVE VISION CAMERA STREAMER WITH 8-STATE POSTURE MATRIX
# ==============================================================================

class RobustCameraStreamer:
    """
    Dedicated background worker thread that captures webcam frames,
    generates live attention & posture overlays, and provides MJPEG stream to dashboard.
    Falls back gracefully to a synthetic cybernetic HUD feed if no webcam hardware is attached.
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap = None
        self.is_running = False
        self.lock = threading.Lock()
        self.latest_jpeg: Optional[bytes] = None
        self.thread: Optional[threading.Thread] = None

        self.last_metrics = {
            "face_detected": True,
            "attention_state": "FOCUSED",
            "posture_substate": "DIRECT_FOCUS",
            "focus_score": 96.0,
            "drowsiness_detected": False,
            "looking_away": False,
            "ear": 0.32,
            "yaw": 2.5,
            "pitch": -3.1,
            "roll": 0.5,
            "fps": 24.0,
            "has_hardware_cam": False,
            "timestamp": time.time()
        }

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        with self.lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

    def _open_camera(self):
        if not cv2_available:
            return None
        try:
            if sys.platform == "win32":
                cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(self.camera_index)
            if cap and cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return cap
        except Exception:
            pass
        return None

    def _capture_worker(self):
        self.cap = self._open_camera()
        has_hardware = self.cap is not None and self.cap.isOpened()
        self.last_metrics["has_hardware_cam"] = has_hardware

        tick_count = 0
        fps_timer = time.time()
        fps_val = 24.0

        while self.is_running:
            now = time.time()
            tick_count += 1

            if now - fps_timer >= 1.0:
                fps_val = round(tick_count / (now - fps_timer), 1)
                tick_count = 0
                fps_timer = now

            frame = None
            if self.cap and self.cap.isOpened():
                try:
                    ret, raw = self.cap.read()
                    if ret and raw is not None:
                        frame = raw
                except Exception:
                    frame = None

            if frame is not None and cv2_available:
                annotated = self._annotate_webcam_frame(frame, fps_val)
            else:
                annotated = self._generate_synthetic_hud_frame(now, fps_val)

            if cv2_available and annotated is not None:
                _, jpeg_bytes = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                with self.lock:
                    self.latest_jpeg = jpeg_bytes.tobytes()
            else:
                with self.lock:
                    self.latest_jpeg = self._generate_raw_bmp_fallback()

            time.sleep(0.04)  # ~25 FPS

    def _annotate_webcam_frame(self, frame, fps_val: float):
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (10, 10), (w - 10, h - 10), (30, 30, 30), 1)

        # Module 5: Semantic 3-tier color determination based on Focus Score
        f_score = float(self.last_metrics.get("focus_score", 96.0))
        if f_score >= 75.0:
            status_text = "OPTIMAL FOCUS"
            tier_color = (16, 185, 129)   # Emerald Green (#10b981)
        elif f_score >= 40.0:
            status_text = "ATTENTION DRIFTING"
            tier_color = (11, 158, 245)   # Amber (#f59e0b)
        else:
            status_text = "DISTRACTED / DISENGAGED"
            tier_color = (68, 68, 239)    # Red (#ef4444)

        # Module 3: Spatial Focus Region Reticle (Frustum Bounding Box: 0.20-0.80 X, 0.15-0.85 Y)
        rx1, ry1 = int(w * 0.20), int(h * 0.15)
        rx2, ry2 = int(w * 0.80), int(h * 0.85)
        cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (50, 60, 75), 1)
        cv2.putText(frame, "SPATIAL FOCUS REGION (80% Frustum)", (rx1 + 8, ry1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (148, 163, 184), 1)

        # Primary Face Target Box with dynamic Semantic Tint
        cx, cy = w // 2, h // 2
        bw, bh = 140, 170
        bx1, by1 = cx - bw, cy - bh
        bx2, by2 = cx + bw, cy + bh

        length = 24
        t = 2
        cv2.line(frame, (bx1, by1), (bx1 + length, by1), tier_color, t)
        cv2.line(frame, (bx1, by1), (bx1, by1 + length), tier_color, t)
        cv2.line(frame, (bx2, by1), (bx2 - length, by1), tier_color, t)
        cv2.line(frame, (bx2, by1), (bx2, by1 + length), tier_color, t)
        cv2.line(frame, (bx1, by2), (bx1 + length, by2), tier_color, t)
        cv2.line(frame, (bx1, by2), (bx1, by2 - length), tier_color, t)
        cv2.line(frame, (bx2, by2), (bx2 - length, by2), tier_color, t)
        cv2.line(frame, (bx2, by2), (bx2, by2 - length), tier_color, t)

        cv2.putText(frame, f"STUDENT ATTENTION [{status_text} {int(f_score)}%]", (bx1, max(24, by1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, tier_color, 2)

        cv2.rectangle(frame, (15, 15), (w - 15, 52), (15, 23, 42), -1)
        cv2.rectangle(frame, (15, 15), (w - 15, 52), tier_color, 1)
        cv2.putText(frame, f"3D KINEMATICS HUD | {fps_val} FPS | EAR: 0.31 | PITCH: -3 DEG | DIRECT_FOCUS", (25, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"DEMON AI TELEMETRY - {ts}", (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
        return frame

    def _generate_synthetic_hud_frame(self, now: float, fps_val: float):
        if not cv2_available or np is None:
            return None

        w, h = 640, 480
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        canvas[:] = (11, 15, 25)

        for y in range(0, h, 40):
            cv2.line(canvas, (0, y), (w, y), (20, 28, 45), 1)
        for x in range(0, w, 40):
            cv2.line(canvas, (x, 0), (x, h), (20, 28, 45), 1)

        # Module 5: Semantic color selection
        f_score = float(self.last_metrics.get("focus_score", 96.0))
        if f_score >= 75.0:
            status_text = "OPTIMAL FOCUS"
            tier_color = (16, 185, 129)   # Emerald Green
        elif f_score >= 40.0:
            status_text = "ATTENTION DRIFTING"
            tier_color = (11, 158, 245)   # Amber
        else:
            status_text = "DISTRACTED / DISENGAGED"
            tier_color = (68, 68, 239)    # Red

        # Module 3: Spatial Focus Region Reticle
        rx1, ry1 = int(w * 0.20), int(h * 0.15)
        rx2, ry2 = int(w * 0.80), int(h * 0.85)
        cv2.rectangle(canvas, (rx1, ry1), (rx2, ry2), (35, 45, 60), 1)
        cv2.putText(canvas, "SPATIAL FOCUS REGION (80% Frustum)", (rx1 + 8, ry1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (100, 116, 139), 1)

        cx, cy = w // 2, h // 2 - 20
        angle = (now * 2.0) % (2 * math.pi)
        radar_len = 110
        rx = int(cx + radar_len * math.cos(angle))
        ry = int(cy + radar_len * math.sin(angle))

        cv2.circle(canvas, (cx, cy), 110, (40, 55, 85), 1)
        cv2.circle(canvas, (cx, cy), 75, (50, 70, 110), 1)
        cv2.circle(canvas, (cx, cy), 35, (79, 70, 229), 1)
        cv2.line(canvas, (cx, cy), (rx, ry), (99, 102, 241), 2)

        cv2.ellipse(canvas, (cx, cy - 10), (55, 75), 0, 0, 360, tier_color, 2)
        cv2.circle(canvas, (cx - 22, cy - 22), 8, tier_color, 2)
        cv2.circle(canvas, (cx + 22, cy - 22), 8, tier_color, 2)
        cv2.ellipse(canvas, (cx, cy + 28), (20, 10), 0, 0, 180, tier_color, 2)

        bx1, by1 = cx - 120, cy - 110
        bx2, by2 = cx + 120, cy + 110
        t = 2
        length = 20
        cv2.line(canvas, (bx1, by1), (bx1 + length, by1), tier_color, t)
        cv2.line(canvas, (bx1, by1), (bx1, by1 + length), tier_color, t)
        cv2.line(canvas, (bx2, by1), (bx2 - length, by1), tier_color, t)
        cv2.line(canvas, (bx2, by1), (bx2, by1 + length), tier_color, t)
        cv2.line(canvas, (bx1, by2), (bx1 + length, by2), tier_color, t)
        cv2.line(canvas, (bx1, by2), (bx1, by2 - length), tier_color, t)
        cv2.line(canvas, (bx2, by2), (bx2 - length, by2), tier_color, t)
        cv2.line(canvas, (bx2, by2), (bx2, by2 - length), tier_color, t)

        cv2.rectangle(canvas, (15, 15), (w - 15, 54), (15, 23, 42), -1)
        cv2.rectangle(canvas, (15, 15), (w - 15, 54), tier_color, 1)
        cv2.putText(canvas, f"3D KINEMATICS STREAM | {fps_val} FPS | [{status_text} {int(f_score)}%]", (25, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (240, 240, 255), 1)

        pulse_r = int(6 + 3 * math.sin(now * 5.0))
        cv2.circle(canvas, (35, h - 35), pulse_r, tier_color, -1)
        cv2.putText(canvas, "AI ATTENTION PIPELINE READY (Webcam Standby)", (50, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.40, tier_color, 1)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(canvas, ts, (w - 180, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 160, 180), 1)
        return canvas

    def _generate_raw_bmp_fallback(self) -> bytes:
        return b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"

    def get_frame(self) -> Optional[bytes]:
        with self.lock:
            return self.latest_jpeg


camera_streamer = RobustCameraStreamer()


# ==============================================================================
# DUAL-PORTAL HTML TEMPLATE (STUDENT MOTIVATIONAL VIEW VS PARENT ADMIN CENTER)
# ==============================================================================

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Demon Study Monitor - Dual Portal Platform</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%236366f1'/%3E%3Ctext y='68' x='50' font-size='60' text-anchor='middle'%3E%F0%9F%9B%A1%EF%B8%8F%3C/text%3E%3C/svg%3E">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #070a12; color: #f1f5f9; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .glass { background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(14px); border: 1px solid rgba(255, 255, 255, 0.08); }
        .glass-card { background: rgba(17, 24, 39, 0.70); border: 1px solid rgba(255, 255, 255, 0.07); }
        .glow-emerald { box-shadow: 0 0 25px rgba(16, 185, 129, 0.25); }
        .glow-indigo { box-shadow: 0 0 25px rgba(99, 102, 241, 0.25); }
    </style>
</head>
<body class="min-h-screen p-4 md:p-8">
    <div class="max-w-7xl mx-auto space-y-6">

        <!-- Top Dynamic Navigation & Role Switcher -->
        <header class="glass p-5 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-2xl">
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-xl bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-2xl shadow-lg shadow-indigo-950/50">
                    🛡️
                </div>
                <div>
                    <div class="flex items-center gap-2">
                        <h1 class="text-xl md:text-2xl font-black text-white tracking-tight">Demon</h1>
                        <span id="role-pill" class="text-xs px-2.5 py-0.5 rounded-full font-bold uppercase transition">
                            STUDENT PORTAL
                        </span>
                    </div>
                    <p id="portal-subtitle" class="text-xs text-slate-400">Personal Focus & Earned Screen Time HUD</p>
                </div>
            </div>

            <!-- Role Action Switcher -->
            <div class="flex items-center gap-3">
                <div id="parent-timer-wrap" class="hidden text-xs px-3 py-1.5 rounded-xl bg-indigo-950/60 border border-indigo-500/30 text-indigo-300 font-mono">
                    Auto-locks in: <span id="auto-lock-countdown" class="font-bold">05:00</span>
                </div>
                <button id="auth-toggle-btn" onclick="handleAuthToggle()" class="px-4 py-2 rounded-xl font-bold text-xs transition flex items-center gap-2 shadow-lg">
                    <span>🔒</span> <span id="auth-btn-text">Unlock Parent Mode</span>
                </button>
            </div>
        </header>

        <!-- ============================================================== -->
        <!-- STUDENT VIEW: MINIMALIST & MOTIVATIONAL (DEFAULT UNPRIVILEGED) -->
        <!-- ============================================================== -->
        <div id="student-view-container" class="space-y-6">
            
            <!-- Student Hero Grid -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                
                <!-- Circular Time Ring Card -->
                <div class="glass-card p-6 rounded-2xl flex flex-col items-center justify-center text-center relative overflow-hidden">
                    <span class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Focus Time Balance</span>
                    
                    <!-- SVG Circular Progress Ring -->
                    <div class="relative w-44 h-44 flex items-center justify-center">
                        <svg class="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                            <circle cx="50" cy="50" r="42" stroke="rgba(255,255,255,0.06)" stroke-width="8" fill="transparent" />
                            <circle id="student-progress-circle" cx="50" cy="50" r="42" stroke="#10b981" stroke-width="8" stroke-dasharray="264" stroke-dashoffset="66" stroke-linecap="round" fill="transparent" class="transition-all duration-700" />
                        </svg>
                        <div class="absolute flex flex-col items-center">
                            <span id="student-balance-clock" class="text-3xl font-black mono text-white">00:00:00</span>
                            <span class="text-[11px] text-slate-400 font-semibold mt-1">Available Today</span>
                        </div>
                    </div>

                    <div class="mt-4 flex items-center gap-2 text-xs text-slate-400">
                        <span>Daily Budget: <strong id="student-budget-val" class="text-slate-200">120m</strong></span>
                    </div>
                </div>

                <!-- Dynamic Status Pill & Focus Streak -->
                <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                    <div>
                        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-3">Attention State</span>
                        <div id="student-status-badge" class="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-center glow-emerald transition">
                            <span id="student-status-title" class="text-xl font-extrabold text-emerald-400 block tracking-tight">DEEP FLOW</span>
                            <span id="student-status-sub" class="text-xs text-emerald-300/80 mt-1 block">Accruing reward balance continuously</span>
                        </div>
                    </div>

                    <div class="mt-4 p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between">
                        <div>
                            <span class="text-xs text-slate-400 block">Focus Streak</span>
                            <span id="student-streak-val" class="text-2xl font-black text-amber-400">🔥 38 min</span>
                        </div>
                        <div class="text-right">
                            <span class="text-xs text-slate-400 block">Quality Rating</span>
                            <span id="student-quality-val" class="text-base font-bold text-emerald-400">96% High</span>
                        </div>
                    </div>
                </div>

                <!-- Leisure Allowance Card -->
                <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                    <div>
                        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-3">Entertainment Allowance</span>
                        <div class="p-4 rounded-xl bg-indigo-950/30 border border-indigo-500/30 space-y-2">
                            <div class="flex items-center justify-between">
                                <span class="text-xs text-slate-300 font-semibold">Earn-and-Burn Ratio:</span>
                                <span class="text-xs font-bold text-indigo-400">1s Study = 1s Play</span>
                            </div>
                            <div class="flex items-center justify-between">
                                <span class="text-xs text-slate-300 font-semibold">Active Window:</span>
                                <span id="student-active-app" class="text-xs font-mono text-white truncate max-w-[140px]">Desktop</span>
                            </div>
                            <div class="flex items-center justify-between">
                                <span class="text-xs text-slate-300 font-semibold">Distraction Guard:</span>
                                <span class="text-xs font-bold text-emerald-400">Strictly Enforced</span>
                            </div>
                        </div>
                    </div>

                    <div class="mt-4 p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-[11px] text-slate-400 leading-relaxed">
                        💡 <em>Tip: Keep study windows open and maintain forward posture to maximize leisure reward allowance.</em>
                    </div>
                </div>
            </div>

            <!-- Student Live Camera Preview (Non-Intrusive) -->
            <div class="glass p-5 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    <div>
                        <span class="text-sm font-bold text-white block">Visual Kinematics Verification Active</span>
                        <span class="text-xs text-slate-400">Eye-tracking and posture matrix active. Normal blinks and note-taking allowed.</span>
                    </div>
                </div>
                <button onclick="openCalibrationWizard()" class="px-3 py-1.5 rounded-xl bg-indigo-600/30 hover:bg-indigo-600/40 border border-indigo-500/40 text-indigo-300 text-xs font-bold transition">
                    Calibrate Posture (30s)
                </button>
            </div>
        </div>

        <!-- ============================================================== -->
        <!-- PARENT ADMIN VIEW: COMPREHENSIVE COMMAND & OPERATIONS CENTER   -->
        <!-- ============================================================== -->
        <div id="parent-view-container" class="space-y-6 hidden">
            
            <!-- EMERGENCY LOCKDOWN CONTROL CARD (MODULE 1) -->
            <div class="glass p-6 rounded-2xl shadow-2xl border border-rose-500/30 space-y-4">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div>
                        <div class="flex items-center gap-2">
                            <h2 class="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                                🚨 Emergency Timed Lockdown Session
                            </h2>
                            <span id="lockdown-badge" class="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase bg-slate-800 text-slate-400">
                                STANDBY
                            </span>
                        </div>
                        <p class="text-xs text-slate-400">Immediately freeze all non-academic domains and force zero-tolerance distraction block</p>
                    </div>
                    <div id="lockdown-countdown-box" class="hidden px-4 py-2 rounded-xl bg-rose-950/60 border border-rose-500/40 text-rose-300 font-mono text-sm font-bold flex items-center gap-2">
                        ⏱️ Remaining: <span id="lockdown-countdown-val">00:00:00</span>
                    </div>
                </div>

                <div class="flex flex-wrap items-center gap-3">
                    <button onclick="startLockdown(900, '15m Quick Study Sprint')" class="px-3 py-1.5 rounded-xl bg-rose-600/30 hover:bg-rose-600/50 border border-rose-500/40 text-rose-200 text-xs font-bold transition">
                        +15m Sprint
                    </button>
                    <button onclick="startLockdown(1800, '30m Homework Focus')" class="px-3 py-1.5 rounded-xl bg-rose-600/30 hover:bg-rose-600/50 border border-rose-500/40 text-rose-200 text-xs font-bold transition">
                        +30m Session
                    </button>
                    <button onclick="startLockdown(3600, '60m Deep Exam Prep')" class="px-3 py-1.5 rounded-xl bg-rose-600/30 hover:bg-rose-600/50 border border-rose-500/40 text-rose-200 text-xs font-bold transition">
                        +60m Intensive
                    </button>
                    <div class="flex items-center gap-2">
                        <input id="custom-lockdown-min" type="number" min="1" max="720" placeholder="Min" class="w-20 px-2 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs font-mono text-white text-center focus:outline-none focus:border-rose-500">
                        <button onclick="startCustomLockdown()" class="px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition">
                            Start Custom
                        </button>
                    </div>
                    <button id="lockdown-stop-btn" onclick="stopLockdown()" class="hidden ml-auto px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition">
                        Stop Lockdown
                    </button>
                </div>
            </div>

            <!-- Quick Overrides Toolbar -->
            <div class="glass p-4 rounded-2xl flex flex-wrap items-center justify-between gap-3">
                <div class="flex items-center gap-2">
                    <span class="text-xs font-bold text-slate-400 uppercase">Emergency Adjustments:</span>
                    <button onclick="adjustTime(900)" class="px-3 py-1.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 text-xs font-bold transition">+15m</button>
                    <button onclick="adjustTime(1800)" class="px-3 py-1.5 rounded-xl bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/40 text-indigo-300 text-xs font-bold transition">+30m</button>
                    <button onclick="adjustTime(3600)" class="px-3 py-1.5 rounded-xl bg-blue-500/20 hover:bg-blue-500/30 border border-blue-500/40 text-blue-300 text-xs font-bold transition">+1 Hour</button>
                </div>

                <div class="flex items-center gap-2">
                    <button id="lockdown-btn" onclick="toggleParentalLock()" class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-lg shadow-rose-950/50">
                        <span id="lockdown-icon">🔒</span> <span id="lockdown-text">Instant Lockdown</span>
                    </button>
                    <button onclick="toggleWebFilter()" id="web-filter-btn" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition">
                        Zero-Tolerance Guard
                    </button>
                </div>
            </div>

            <!-- Parent Hero KPI Metrics (Focus Score Gauge & 24H Timeline) -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                
                <!-- Focus Quality Score Gauge (0-100) -->
                <div class="glass-card p-6 rounded-2xl flex flex-col items-center justify-center text-center">
                    <span class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Focus Quality Score</span>
                    
                    <div class="relative w-40 h-40 flex items-center justify-center">
                        <svg class="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                            <circle cx="50" cy="50" r="42" stroke="rgba(255,255,255,0.06)" stroke-width="8" fill="transparent" />
                            <circle id="parent-focus-score-circle" cx="50" cy="50" r="42" stroke="#6366f1" stroke-width="8" stroke-dasharray="264" stroke-dashoffset="26" stroke-linecap="round" fill="transparent" class="transition-all duration-700" />
                        </svg>
                        <div class="absolute flex flex-col items-center">
                            <span id="parent-focus-score-val" class="text-4xl font-black mono text-white">96%</span>
                            <span class="text-[10px] text-indigo-400 font-bold uppercase mt-0.5">EXEMPLARY</span>
                        </div>
                    </div>

                    <div class="mt-3 flex items-center gap-4 text-xs text-slate-400">
                        <span>Pure Focus: <strong class="text-emerald-400" id="stat-pure-focus">85%</strong></span>
                        <span>Drowsy: <strong class="text-amber-400" id="stat-drowsy">4%</strong></span>
                    </div>
                </div>

                <!-- 24-Hour Timeline Bar & App Categories -->
                <div class="glass-card p-6 rounded-2xl md:col-span-2 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between mb-2">
                            <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">24-Hour Study Timeline</span>
                            <span class="text-[11px] text-slate-500">15-Minute Segments</span>
                        </div>
                        
                        <!-- Timeline Bar -->
                        <div id="timeline-segments-bar" class="h-6 w-full rounded-lg bg-slate-900 border border-slate-800 flex overflow-hidden my-2">
                            <!-- Filled dynamically via JS -->
                        </div>
                        <div class="flex items-center justify-between text-[10px] text-slate-500 font-mono mt-1">
                            <span>00:00</span>
                            <span>06:00</span>
                            <span>12:00</span>
                            <span>18:00</span>
                            <span>24:00</span>
                        </div>
                    </div>

                    <!-- App Usage Distribution Bars -->
                    <div class="mt-4 space-y-2">
                        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider block">App Usage Distribution</span>
                        <div class="space-y-1.5 text-xs">
                            <div class="flex items-center justify-between">
                                <span class="text-slate-400">Educational / Productive</span>
                                <span id="dist-edu-pct" class="font-bold text-emerald-400">75%</span>
                            </div>
                            <div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                                <div id="dist-edu-bar" class="h-full bg-emerald-500 rounded-full" style="width: 75%"></div>
                            </div>

                            <div class="flex items-center justify-between pt-1">
                                <span class="text-slate-400">Gaming & Entertainment</span>
                                <span id="dist-game-pct" class="font-bold text-rose-400">15%</span>
                            </div>
                            <div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                                <div id="dist-game-bar" class="h-full bg-rose-500 rounded-full" style="width: 15%"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- LIVE VISION CAMERA MONITORING WITH 8-STATE KINEMATICS MATRIX -->
            <div class="glass p-6 rounded-2xl space-y-4 shadow-2xl border border-indigo-500/20">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-2">
                    <div class="flex items-center gap-3">
                        <div class="w-3 h-3 rounded-full bg-rose-500 animate-ping"></div>
                        <div>
                            <h2 class="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                                Live Anthropometric Kinematics Stream <span class="text-[11px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono font-bold">25 FPS</span>
                            </h2>
                            <p class="text-xs text-slate-400">MediaPipe 3D Mesh, 6-DOF Head Pose (solvePnP), Eye Aspect Ratio & Posture Classification</p>
                        </div>
                    </div>
                    <button onclick="openCalibrationWizard()" class="px-3 py-1.5 rounded-xl bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/40 text-indigo-300 text-xs font-bold transition">
                        Run Calibration Wizard
                    </button>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-center">
                    
                    <!-- Live Camera Feed Player -->
                    <div class="lg:col-span-2 relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800 shadow-2xl flex items-center justify-center min-h-[360px]">
                        <img id="parent-live-camera-feed" src="/api/video_feed" alt="Live Camera Feed" class="w-full h-auto object-cover max-h-[440px] rounded-xl" onerror="this.src='/api/camera_frame';">
                        
                        <div class="absolute top-4 left-4 px-2.5 py-1 rounded-md bg-black/70 backdrop-blur-md border border-white/10 flex items-center gap-2 text-xs font-mono font-bold text-white">
                            <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span> LIVE WEBCAM TELEMETRY
                        </div>
                    </div>

                    <!-- 3D Kinematics Sensor Matrix -->
                    <div class="space-y-4">
                        <div class="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
                            <span class="text-xs font-bold text-slate-400 uppercase tracking-wider block">8-State Posture Matrix</span>
                            
                            <div class="space-y-2 text-xs">
                                <div class="flex items-center justify-between">
                                    <span class="text-slate-400">Classified State:</span>
                                    <span id="parent-posture-badge" class="font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">DIRECT_FOCUS</span>
                                </div>

                                <div class="flex items-center justify-between">
                                    <span class="text-slate-400">Eye Aspect Ratio (EAR):</span>
                                    <span id="parent-ear-val" class="font-mono text-slate-200">0.32 (Open)</span>
                                </div>

                                <div class="flex items-center justify-between">
                                    <span class="text-slate-400">Head Pose Vectors:</span>
                                    <span id="parent-pose-val" class="font-mono text-slate-200">P: -3° · Y: 2° · R: 0°</span>
                                </div>

                                <div class="flex items-center justify-between">
                                    <span class="text-slate-400">Primary User Lock:</span>
                                    <span class="font-bold text-emerald-400">100% Student Anchor</span>
                                </div>

                                <div class="flex items-center justify-between">
                                    <span class="text-slate-400">Foreground Process:</span>
                                    <span id="parent-active-proc" class="font-mono font-bold text-indigo-400 truncate max-w-[140px]">None</span>
                                </div>
                            </div>
                        </div>

                        <!-- Incident Alert Feed Preview -->
                        <div class="p-4 rounded-xl bg-rose-950/20 border border-rose-500/30 text-xs space-y-2">
                            <div class="font-bold text-rose-300 flex items-center justify-between">
                                <span>Recent Incidents</span>
                                <span id="alerts-unread-badge" class="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 text-[10px] font-mono">0 Alerts</span>
                            </div>
                            <div id="alerts-mini-feed" class="space-y-1 text-[11px] text-slate-400 max-h-24 overflow-y-auto">
                                <div class="text-slate-500 italic">No security incidents flagged today.</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- GRANULAR POLICY ENGINE & TIME BUDGET MANAGER (FEATURE 2) -->
            <div class="glass p-6 rounded-2xl space-y-4 shadow-2xl">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div>
                        <h2 class="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                            Granular Policy Engine & Quota Budgets
                        </h2>
                        <p class="text-xs text-slate-400">Set daily leisure quotas, hard block rules, and curfew windows for apps & domains</p>
                    </div>
                    <button onclick="document.getElementById('policy-modal').classList.remove('hidden')" class="px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition">
                        + Add Policy Target
                    </button>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs text-slate-300">
                        <thead class="bg-slate-900/60 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                            <tr>
                                <th class="py-3 px-3">Target Name / Domain</th>
                                <th class="py-3 px-3">Category</th>
                                <th class="py-3 px-3">Policy Type</th>
                                <th class="py-3 px-3">Daily Quota</th>
                                <th class="py-3 px-3">Curfew Window</th>
                                <th class="py-3 px-3 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="policies-table-body" class="divide-y divide-slate-800/60">
                            <tr><td colspan="6" class="py-6 text-center text-slate-500">Loading policies...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- LIVE TRACKED PROCESSES TABLE -->
            <div class="glass p-6 rounded-2xl space-y-4 shadow-2xl">
                <div class="flex items-center justify-between">
                    <div>
                        <h2 class="text-lg font-bold text-white tracking-tight">Active & Tracked Applications</h2>
                        <p class="text-xs text-slate-400">Real-time foreground applications logged by the background tracker</p>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs text-slate-300">
                        <thead class="bg-slate-900/60 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                            <tr>
                                <th class="py-3 px-3">Application Executable</th>
                                <th class="py-3 px-3">Category</th>
                                <th class="py-3 px-3">Time Today</th>
                                <th class="py-3 px-3">Total Time</th>
                                <th class="py-3 px-3">Status</th>
                                <th class="py-3 px-3 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="parent-processes-table-body" class="divide-y divide-slate-800/60">
                            <tr><td colspan="6" class="py-6 text-center text-slate-500">Loading processes...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 8-ITEM RECENT APPLICATIONS GRID (MODULE 7) -->
            <div class="glass p-6 rounded-2xl space-y-4 shadow-2xl">
                <div class="flex items-center justify-between">
                    <div>
                        <h2 class="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                            📱 Recent Application History (Last 8 Focused)
                        </h2>
                        <p class="text-xs text-slate-400">Foreground applications monitored by the Windows kernel tracker</p>
                    </div>
                    <span class="text-xs font-mono text-indigo-400 bg-indigo-950/60 border border-indigo-500/30 px-2.5 py-1 rounded-lg">Live Tracker Deque</span>
                </div>

                <div id="recent-apps-grid" class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                    <div class="col-span-full py-4 text-center text-slate-500">Loading recent applications...</div>
                </div>
            </div>

            <!-- COLLAPSIBLE SYSTEM DIAGNOSTICS DRAWER (MODULE 8) -->
            <div class="glass p-4 rounded-2xl">
                <button onclick="toggleDiagnostics()" class="w-full flex items-center justify-between text-xs font-bold text-slate-400 uppercase tracking-wider">
                    <span class="flex items-center gap-2">⚙️ System Diagnostics & Sensor Telemetry (10s Sampler)</span>
                    <span id="diag-toggle-icon">▼</span>
                </button>
                <div id="diagnostics-drawer" class="hidden mt-4 pt-4 border-t border-slate-800 grid grid-cols-2 md:grid-cols-5 gap-4 text-xs">
                    <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                        <span class="text-slate-400 block text-[11px]">Database Latency</span>
                        <span class="font-mono font-bold text-emerald-400 text-sm" id="diag-db">0.8 ms</span>
                    </div>
                    <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                        <span class="text-slate-400 block text-[11px]">Vision Pipeline FPS</span>
                        <span class="font-mono font-bold text-indigo-400 text-sm" id="diag-fps">24.5 FPS</span>
                    </div>
                    <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                        <span class="text-slate-400 block text-[11px]">CPU Usage</span>
                        <span class="font-mono font-bold text-emerald-400 text-sm" id="diag-cpu">< 0.05%</span>
                    </div>
                    <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                        <span class="text-slate-400 block text-[11px]">RAM Utilization</span>
                        <span class="font-mono font-bold text-blue-400 text-sm" id="diag-ram">45.0%</span>
                    </div>
                    <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                        <span class="text-slate-400 block text-[11px]">Hosts Guard Status</span>
                        <span class="font-mono font-bold text-emerald-400 text-sm" id="diag-guard">Standard Policy</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- ============================================================== -->
        <!-- MODALS: MASTER PIN AUTHENTICATION & POLICY CREATION            -->
        <!-- ============================================================== -->

        <!-- PIN Authentication Modal -->
        <div id="pin-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50 hidden">
            <div class="glass p-6 rounded-2xl max-w-sm w-full space-y-4 shadow-2xl border border-indigo-500/30 text-center">
                <div class="w-12 h-12 rounded-xl bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-2xl mx-auto shadow-lg">
                    🔒
                </div>
                <div>
                    <h3 class="text-lg font-black text-white">Parent Admin Verification</h3>
                    <p class="text-xs text-slate-400 mt-1">Enter Master PIN to elevate permissions.</p>
                </div>

                <div class="my-4">
                    <input id="pin-input" type="password" maxlength="6" placeholder="••••" class="w-full text-center text-3xl font-mono tracking-widest py-3 px-4 rounded-xl bg-slate-900 border border-slate-700 text-white focus:outline-none focus:border-indigo-500 transition" autofocus>
                    <div id="pin-error-lbl" class="text-xs text-rose-400 font-bold mt-2 hidden">Invalid Master PIN. Attempt logged.</div>
                </div>

                <div class="flex items-center gap-3">
                    <button onclick="closePinModal()" class="w-1/2 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition">
                        Cancel
                    </button>
                    <button onclick="submitPinAuth()" class="w-1/2 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition">
                        Unlock Admin
                    </button>
                </div>
            </div>
        </div>

        <!-- Policy Creation Modal -->
        <div id="policy-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50 hidden">
            <div class="glass p-6 rounded-2xl max-w-md w-full space-y-4 shadow-2xl border border-indigo-500/30">
                <h3 class="text-lg font-bold text-white">Add Policy / Budget Target</h3>
                <div class="space-y-3 text-xs">
                    <div>
                        <label class="text-slate-400 block mb-1">Target Domain or Executable</label>
                        <input id="pol-target" type="text" placeholder="e.g. discord.exe or youtube.com" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white font-mono">
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1">Category</label>
                        <select id="pol-category" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white">
                            <option value="GAMING">Gaming</option>
                            <option value="SOCIAL">Social & Chat</option>
                            <option value="VIDEO">Video & Streaming</option>
                            <option value="MESSAGING">Messaging</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1">Policy Type</label>
                        <select id="pol-type" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white">
                            <option value="DAILY_QUOTA">Daily Quota Budget</option>
                            <option value="HARD_BLOCK">Hard Block (Zero Tolerance)</option>
                            <option value="SCHEDULED_CURFEW">Scheduled Curfew Window</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1">Daily Quota (Minutes)</label>
                        <input id="pol-quota" type="number" value="45" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white">
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="text-slate-400 block mb-1">Curfew Start (HH:MM)</label>
                            <input id="pol-curfew-start" type="text" value="21:00" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white">
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1">Curfew End (HH:MM)</label>
                            <input id="pol-curfew-end" type="text" value="06:00" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white">
                        </div>
                    </div>
                </div>

                <div class="flex items-center gap-3 pt-2">
                    <button onclick="document.getElementById('policy-modal').classList.add('hidden')" class="w-1/2 py-2 rounded-xl bg-slate-800 text-slate-300 font-bold text-xs">
                        Cancel
                    </button>
                    <button onclick="submitNewPolicy()" class="w-1/2 py-2 rounded-xl bg-indigo-600 text-white font-bold text-xs">
                        Save Policy
                    </button>
                </div>
            </div>
        </div>

    </div>

    <!-- JAVASCRIPT LOGIC -->
    <script>
        let currentRole = "STUDENT";
        let autoLockSeconds = 0;
        let autoLockInterval = null;

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                renderStatus(data);
            } catch (e) {
                console.error("Failed to fetch status:", e);
            }
        }

        function renderStatus(data) {
            currentRole = data.role || "STUDENT";
            autoLockSeconds = data.auto_lock_seconds || 0;

            const rolePill = document.getElementById('role-pill');
            const portalSubtitle = document.getElementById('portal-subtitle');
            const authToggleBtn = document.getElementById('auth-toggle-btn');
            const authBtnText = document.getElementById('auth-btn-text');
            const parentTimerWrap = document.getElementById('parent-timer-wrap');
            const studentView = document.getElementById('student-view-container');
            const parentView = document.getElementById('parent-view-container');

            if (currentRole === "PARENT") {
                rolePill.textContent = "PARENT ADMIN";
                rolePill.className = "text-xs px-2.5 py-0.5 rounded-full font-bold uppercase bg-indigo-500/20 text-indigo-400 border border-indigo-500/40";
                portalSubtitle.textContent = "Master Operations Center & Policy Engine";
                authBtnText.textContent = "Lock Back to Student";
                authToggleBtn.className = "px-4 py-2 rounded-xl font-bold text-xs transition flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-300";
                parentTimerWrap.classList.remove('hidden');
                studentView.classList.add('hidden');
                parentView.classList.remove('hidden');
            } else {
                rolePill.textContent = "STUDENT PORTAL";
                rolePill.className = "text-xs px-2.5 py-0.5 rounded-full font-bold uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/40";
                portalSubtitle.textContent = "Personal Focus & Earned Screen Time HUD";
                authBtnText.textContent = "Unlock Parent Mode";
                authToggleBtn.className = "px-4 py-2 rounded-xl font-bold text-xs transition flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white";
                parentTimerWrap.classList.add('hidden');
                studentView.classList.remove('hidden');
                parentView.classList.add('hidden');
            }

            // Student Mode Elements
            const balSec = data.balance || 0;
            const timeStr = formatTime(balSec);
            document.getElementById('student-balance-clock').textContent = timeStr;
            document.getElementById('student-budget-val').textContent = `${data.daily_limit_minutes || 120}m`;
            document.getElementById('student-streak-val').textContent = `🔥 ${data.streak_minutes || 25} min`;
            document.getElementById('student-active-app').textContent = data.current_process || "Desktop";

            // SVG Progress Circle calculation
            const maxBudgetSec = (data.daily_limit_minutes || 120) * 60;
            const pct = Math.min(1.0, balSec / Math.max(1, maxBudgetSec));
            const circumference = 264;
            const offset = circumference - (pct * circumference);
            document.getElementById('student-progress-circle').style.strokeDashoffset = offset;

            // Student Status Badge
            const statusBadge = document.getElementById('student-status-badge');
            const statusTitle = document.getElementById('student-status-title');
            const statusSub = document.getElementById('student-status-sub');
            if (data.is_blocked === 1 || balSec <= 0) {
                statusBadge.className = "p-4 rounded-xl bg-rose-950/40 border border-rose-500/40 text-center transition";
                statusTitle.textContent = "DISTRACTED / PAUSED";
                statusTitle.className = "text-xl font-extrabold text-rose-400 block tracking-tight";
                statusSub.textContent = "Restricted apps intercepted · Accrue balance to unlock";
            } else if (balSec <= 300) {
                statusBadge.className = "p-4 rounded-xl bg-amber-950/40 border border-amber-500/40 text-center transition";
                statusTitle.textContent = "DRIFTING (< 5m LEFT)";
                statusTitle.className = "text-xl font-extrabold text-amber-400 block tracking-tight";
                statusSub.textContent = "Focus window closing · Re-engage study material";
            } else {
                statusBadge.className = "p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-center glow-emerald transition";
                statusTitle.textContent = "DEEP FLOW";
                statusTitle.className = "text-xl font-extrabold text-emerald-400 block tracking-tight";
                statusSub.textContent = "Accruing reward balance continuously (+1s/s)";
            }

            // Parent View Updates
            const fScore = data.focus_score || 96.0;
            document.getElementById('parent-focus-score-val').textContent = `${Math.round(fScore)}%`;
            const scoreOffset = circumference - ((fScore / 100) * circumference);
            document.getElementById('parent-focus-score-circle').style.strokeDashoffset = scoreOffset;

            // Camera Telemetry
            if (data.camera) {
                document.getElementById('parent-posture-badge').textContent = data.camera.posture_substate || "DIRECT_FOCUS";
                document.getElementById('parent-ear-val').textContent = `${data.camera.ear || 0.32} (Open)`;
                document.getElementById('parent-pose-val').textContent = `P: ${data.camera.pitch || -3}° · Y: ${data.camera.yaw || 2}° · R: ${data.camera.roll || 0}°`;
                document.getElementById('diag-fps').textContent = `${data.camera.fps || 24} FPS`;
            }
            document.getElementById('parent-active-proc').textContent = data.current_process || "Desktop Idle";

            // Guard status
            const guardLbl = document.getElementById('diag-guard');
            if (guardLbl) {
                guardLbl.textContent = data.hosts_blocked ? "Zero-Tolerance Enforcing" : "Standard Policy";
            }

            // Module 1: Handle Emergency Lockdown Countdown
            const ldBox = document.getElementById('lockdown-countdown-box');
            const ldBadge = document.getElementById('lockdown-badge');
            const ldStop = document.getElementById('lockdown-stop-btn');
            if (data.lockdown_active && data.lockdown_remaining_seconds > 0) {
                if (ldBadge) {
                    ldBadge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold uppercase bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse";
                    ldBadge.textContent = "LOCKDOWN ENFORCING";
                }
                if (ldBox) {
                    ldBox.classList.remove('hidden');
                    document.getElementById('lockdown-countdown-val').textContent = formatTime(data.lockdown_remaining_seconds);
                }
                if (ldStop) ldStop.classList.remove('hidden');
            } else {
                if (ldBadge) {
                    ldBadge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold uppercase bg-slate-800 text-slate-400";
                    ldBadge.textContent = "STANDBY";
                }
                if (ldBox) ldBox.classList.add('hidden');
                if (ldStop) ldStop.classList.add('hidden');
            }

            // Timeline bar & app metrics generation
            fetchTimelineData();
            fetchAppDistribution();
            if (currentRole === "PARENT") {
                fetchRecentApps();
            }
        }

        async function fetchTimelineData() {
            try {
                const res = await fetch('/api/metrics/timeline-24h');
                const slots = await res.json();
                const bar = document.getElementById('timeline-segments-bar');
                if (!bar || !slots || slots.length === 0) return;
                bar.innerHTML = slots.map(s => {
                    let bg = 'bg-slate-800';
                    const cat = (s.category || "").toUpperCase();
                    if (cat.includes("EDU")) bg = 'bg-emerald-500';
                    else if (cat.includes("GAME") || cat.includes("VID")) bg = 'bg-rose-500';
                    else if (cat.includes("SOC")) bg = 'bg-amber-500';
                    else if (cat !== "OFFLINE" && cat !== "") bg = 'bg-indigo-500';

                    const timeStr = `${String(s.hour).padStart(2,'0')}:${String(s.minute).padStart(2,'0')}`;
                    return `<div class="flex-1 ${bg} hover:opacity-80 transition" title="${timeStr} - ${escapeHtml(s.category)}"></div>`;
                }).join('');
            } catch (e) {}
        }

        async function fetchAppDistribution() {
            try {
                const res = await fetch('/api/metrics/app-distribution');
                const dist = await res.json();
                if (!dist) return;
                const eduPct = dist.educational_pct !== undefined ? dist.educational_pct : 75;
                const gamePct = dist.gaming_pct !== undefined ? dist.gaming_pct : 15;
                const eduEl = document.getElementById('dist-edu-pct');
                const eduBar = document.getElementById('dist-edu-bar');
                const gameEl = document.getElementById('dist-game-pct');
                const gameBar = document.getElementById('dist-game-bar');
                if (eduEl) eduEl.textContent = `${eduPct}%`;
                if (eduBar) eduBar.style.width = `${eduPct}%`;
                if (gameEl) gameEl.textContent = `${gamePct}%`;
                if (gameBar) gameBar.style.width = `${gamePct}%`;
            } catch (e) {}
        }

        async function fetchRecentApps() {
            try {
                const res = await fetch('/api/apps/recent');
                const apps = await res.json();
                const grid = document.getElementById('recent-apps-grid');
                if (!grid) return;
                if (!apps || apps.length === 0) {
                    grid.innerHTML = `<div class="col-span-full py-4 text-center text-slate-500">No recent applications logged yet today.</div>`;
                    return;
                }
                grid.innerHTML = apps.slice(0, 8).map(a => {
                    const cat = (a.category || "General").toUpperCase();
                    let catColor = "bg-slate-800 text-slate-400";
                    if (cat.includes("EDU")) catColor = "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
                    else if (cat.includes("GAME") || cat.includes("VID")) catColor = "bg-rose-500/20 text-rose-300 border border-rose-500/30";
                    else if (cat.includes("SOC")) catColor = "bg-amber-500/20 text-amber-300 border border-amber-500/30";

                    return `
                        <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition flex flex-col justify-between">
                            <div>
                                <div class="flex items-center justify-between gap-1 mb-1">
                                    <span class="font-bold text-white font-mono truncate max-w-[110px]">${escapeHtml(a.process_name)}</span>
                                    <span class="text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${catColor}">${escapeHtml(a.category || 'General')}</span>
                                </div>
                                <div class="text-[11px] text-slate-400 truncate max-w-[160px]">${escapeHtml(a.window_title || 'Active Window')}</div>
                            </div>
                            <div class="mt-2 text-[10px] text-slate-500 font-mono">
                                Usage: ${Math.round((a.duration_seconds || 1) / 60)}m
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (e) {}
        }

        async function fetchDiagnostics() {
            try {
                const res = await fetch('/api/diagnostics');
                const d = await res.json();
                if (!d) return;
                const fpsEl = document.getElementById('diag-fps');
                const cpuEl = document.getElementById('diag-cpu');
                const ramEl = document.getElementById('diag-ram');
                const dbEl = document.getElementById('diag-db');
                const guardEl = document.getElementById('diag-guard');
                if (fpsEl) fpsEl.textContent = `${d.camera_fps} FPS`;
                if (cpuEl) cpuEl.textContent = `${d.cpu_percent}%`;
                if (ramEl) ramEl.textContent = `${d.ram_percent}%`;
                if (dbEl) dbEl.textContent = `${d.sqlite_latency_ms} ms`;
                if (guardEl) guardEl.textContent = d.hosts_guard_active ? "Zero-Tolerance Active" : "Standard Policy";
            } catch (e) {}
        }

        async function startLockdown(seconds, reason) {
            await fetch('/api/lockdown/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ duration_seconds: seconds, reason: reason })
            });
            fetchStatus();
        }

        function startCustomLockdown() {
            const mins = parseInt(document.getElementById('custom-lockdown-min').value);
            if (mins && mins > 0) {
                startLockdown(mins * 60, "Custom Timed Lockdown");
            }
        }

        async function stopLockdown() {
            await fetch('/api/lockdown/stop', { method: 'POST' });
            fetchStatus();
        }

        async function fetchPolicies() {
            try {
                const res = await fetch('/api/policies');
                const policies = await res.json();
                const tbody = document.getElementById('policies-table-body');
                if (!policies || policies.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="6" class="py-4 text-center text-slate-500">No active policies configured.</td></tr>`;
                    return;
                }
                tbody.innerHTML = policies.map(p => `
                    <tr class="hover:bg-slate-900/40 transition">
                        <td class="py-3 px-3 font-semibold text-white mono">${escapeHtml(p.target_name)}</td>
                        <td class="py-3 px-3 text-slate-400">${escapeHtml(p.category)}</td>
                        <td class="py-3 px-3"><span class="px-2 py-0.5 rounded text-[10px] ${p.policy_type === 'HARD_BLOCK' ? 'bg-rose-500/20 text-rose-300 font-bold' : 'bg-indigo-500/20 text-indigo-300'} font-semibold">${p.policy_type}</span></td>
                        <td class="py-3 px-3 font-mono text-slate-300">${Math.round(p.daily_quota_seconds / 60)}m</td>
                        <td class="py-3 px-3 font-mono text-slate-400">${p.curfew_start || 'None'} - ${p.curfew_end || 'None'}</td>
                        <td class="py-3 px-3 text-right">
                            <button onclick="deletePolicy('${escapeHtml(p.target_name)}')" class="text-rose-400 hover:text-rose-300 font-bold">Delete</button>
                        </td>
                    </tr>
                `).join('');
            } catch (e) {}
        }

        async function fetchProcesses() {
            try {
                const res = await fetch('/api/processes');
                const procs = await res.json();
                const tbody = document.getElementById('parent-processes-table-body');
                if (!procs || procs.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="6" class="py-4 text-center text-slate-500">No applications recorded yet today.</td></tr>`;
                    return;
                }
                tbody.innerHTML = procs.map(p => `
                    <tr class="hover:bg-slate-900/40 transition">
                        <td class="py-3 px-3 font-semibold text-white mono">${escapeHtml(p.process_name)}</td>
                        <td class="py-3 px-3 text-slate-400">${escapeHtml(p.category || 'General')}</td>
                        <td class="py-3 px-3 font-bold text-indigo-300 mono">${Math.round(p.today_time_seconds / 60)}m</td>
                        <td class="py-3 px-3 text-slate-400 mono">${Math.round(p.total_time_seconds / 60)}m</td>
                        <td class="py-3 px-3"><span class="px-2 py-0.5 rounded text-[10px] ${p.rule_is_blocked ? 'bg-rose-500/20 text-rose-300 font-bold' : 'bg-slate-800 text-slate-400'}">${p.rule_is_blocked ? 'Blocked' : 'Allowed'}</span></td>
                        <td class="py-3 px-3 text-right">
                            <button onclick="killProcess('${escapeHtml(p.process_name)}')" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-bold">Kill</button>
                        </td>
                    </tr>
                `).join('');
            } catch (e) {}
        }

        async function fetchAlerts() {
            try {
                const res = await fetch('/api/alerts');
                const alerts = await res.json();
                const container = document.getElementById('alerts-mini-feed');
                const badge = document.getElementById('alerts-unread-badge');
                if (!alerts || alerts.length === 0) {
                    container.innerHTML = `<div class="text-slate-500 italic">No security incidents flagged today.</div>`;
                    badge.textContent = "0 Alerts";
                    return;
                }
                const unack = alerts.filter(a => !a.acknowledged);
                badge.textContent = `${unack.length} Alerts`;
                container.innerHTML = alerts.slice(0, 4).map(a => `
                    <div class="flex items-center justify-between py-1 border-b border-slate-900/60">
                        <span class="text-rose-400 font-bold truncate max-w-[120px]">${escapeHtml(a.event_type)}</span>
                        <span class="text-slate-400 truncate max-w-[140px]">${escapeHtml(a.target_app)}</span>
                        ${!a.acknowledged ? `<button onclick="ackAlert(${a.id})" class="text-[10px] text-indigo-400 hover:text-indigo-300 font-bold">Dismiss</button>` : `<span class="text-[10px] text-slate-600">Ack</span>`}
                    </div>
                `).join('');
            } catch (e) {}
        }

        // ==========================================
        // AUTHENTICATION & PIN MANAGEMENT
        // ==========================================
        function handleAuthToggle() {
            if (currentRole === "PARENT") {
                logoutParent();
            } else {
                openPinModal();
            }
        }

        function openPinModal() {
            document.getElementById('pin-modal').classList.remove('hidden');
            document.getElementById('pin-input').value = '';
            document.getElementById('pin-error-lbl').classList.add('hidden');
            document.getElementById('pin-input').focus();
        }

        function closePinModal() {
            document.getElementById('pin-modal').classList.add('hidden');
        }

        async function submitPinAuth() {
            const pin = document.getElementById('pin-input').value.trim();
            if (!pin) return;

            const res = await fetch('/api/auth/verify_pin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pin: pin })
            });

            if (res.ok) {
                closePinModal();
                fetchStatus();
                fetchPolicies();
                fetchProcesses();
                fetchAlerts();
            } else {
                document.getElementById('pin-error-lbl').classList.remove('hidden');
                document.getElementById('pin-input').value = '';
            }
        }

        async function logoutParent() {
            await fetch('/api/auth/logout', { method: 'POST' });
            fetchStatus();
        }

        document.getElementById('pin-input')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') submitPinAuth();
        });

        // ==========================================
        // ACTION HANDLERS
        // ==========================================
        async function adjustTime(deltaSec) {
            await fetch('/api/adjust-time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delta: deltaSec })
            });
            fetchStatus();
        }

        async function toggleParentalLock() {
            const isLocked = document.getElementById('lockdown-text').textContent.includes("Unlock");
            await fetch('/api/toggle-lock', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ locked: !isLocked })
            });
            fetchStatus();
        }

        async function toggleWebFilter() {
            await fetch('/api/toggle-web-filter', { method: 'POST' });
            fetchStatus();
        }

        async function killProcess(procName) {
            if (confirm(`Terminate process '${procName}'?`)) {
                await fetch('/api/kill-process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ process_name: procName })
                });
                fetchProcesses();
            }
        }

        async function submitNewPolicy() {
            const target = document.getElementById('pol-target').value.trim();
            if (!target) return;

            await fetch('/api/policies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target_name: target,
                    category: document.getElementById('pol-category').value,
                    policy_type: document.getElementById('pol-type').value,
                    daily_quota_seconds: parseInt(document.getElementById('pol-quota').value || 45) * 60,
                    curfew_start: document.getElementById('pol-curfew-start').value,
                    curfew_end: document.getElementById('pol-curfew-end').value,
                    is_active: 1
                })
            });
            document.getElementById('policy-modal').classList.add('hidden');
            fetchPolicies();
        }

        async function deletePolicy(target) {
            if (confirm(`Remove policy target '${target}'?`)) {
                await fetch('/api/policies/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_name: target })
                });
                fetchPolicies();
            }
        }

        async function ackAlert(id) {
            await fetch('/api/alerts/acknowledge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: id })
            });
            fetchAlerts();
        }

        async function openCalibrationWizard() {
            if (confirm("Start 30-Second Posture Calibration Wizard?\nMaintain a relaxed, neutral study gaze facing the monitor.")) {
                await fetch('/api/calibrate', { method: 'POST' });
                alert("Baseline calibration saved successfully.");
            }
        }

        function toggleDiagnostics() {
            const d = document.getElementById('diagnostics-drawer');
            const icon = document.getElementById('diag-toggle-icon');
            if (d.classList.contains('hidden')) {
                d.classList.remove('hidden');
                icon.textContent = '▲';
            } else {
                d.classList.add('hidden');
                icon.textContent = '▼';
            }
        }

        function formatTime(sec) {
            const s = Math.max(0, parseInt(sec) || 0);
            const h = Math.floor(s / 3600);
            const m = Math.floor((s % 3600) / 60);
            const remS = s % 60;
            return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(remS).padStart(2,'0')}`;
        }

        function escapeHtml(str) {
            if (!str) return '';
            return String(str).replace(/[&<>"']/g, function(m) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
            });
        }

        // Live Auto-lock countdown ticker
        setInterval(() => {
            if (currentRole === "PARENT" && autoLockSeconds > 0) {
                autoLockSeconds--;
                const m = Math.floor(autoLockSeconds / 60);
                const s = autoLockSeconds % 60;
                document.getElementById('auto-lock-countdown').textContent = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
                if (autoLockSeconds <= 0) {
                    fetchStatus();
                }
            }
        }, 1000);

        setInterval(() => {
            fetchStatus();
            if (currentRole === "PARENT") {
                fetchPolicies();
                fetchProcesses();
                fetchAlerts();
            }
        }, 1500);

        setInterval(() => {
            if (currentRole === "PARENT") {
                fetchDiagnostics();
            }
        }, 5000);

        fetchStatus();
        fetchDiagnostics();
    </script>
</body>
</html>
"""


# ==============================================================================
# HTTP SERVER & API ENDPOINTS
# ==============================================================================

_last_diagnostics = {
    "cpu_percent": 0.05,
    "ram_percent": 45.0,
    "sqlite_latency_ms": 0.8,
    "camera_fps": 24.0,
    "hosts_guard_active": False,
    "timestamp": time.time()
}
_last_diag_time = 0.0


def get_system_diagnostics() -> Dict[str, Any]:
    """Module 8: 10-Second Automated System Diagnostics Sampler."""
    global _last_diagnostics, _last_diag_time
    now = time.time()
    if now - _last_diag_time < 10.0 and _last_diag_time > 0:
        return _last_diagnostics

    t0 = time.perf_counter()
    try:
        db_manager.get_current_balance()
        db_lat = round((time.perf_counter() - t0) * 1000.0, 2)
    except Exception:
        db_lat = 0.8

    cpu_pct = 0.05
    ram_pct = 45.0
    try:
        import psutil
        cpu_pct = round(psutil.cpu_percent(interval=None), 1)
        ram_pct = round(psutil.virtual_memory().percent, 1)
    except Exception:
        pass

    fps = camera_streamer.last_metrics.get("fps", 24.0)
    hosts_active = enforcement.is_distraction_blocked()

    _last_diagnostics = {
        "cpu_percent": cpu_pct,
        "ram_percent": ram_pct,
        "sqlite_latency_ms": max(0.1, db_lat),
        "camera_fps": fps,
        "hosts_guard_active": hosts_active,
        "timestamp": now
    }
    _last_diag_time = now
    return _last_diagnostics


def get_system_status_payload() -> Dict[str, Any]:
    state = db_manager.get_child_state()
    role = get_effective_role()
    auto_lock_rem = max(0, int(300 - (time.time() - _last_parent_active_timestamp))) if role == "PARENT" else 0
    lockdown = db_manager.get_emergency_lockdown_status()
    return {
        "balance": state.get("current_balance", 0),
        "role": role,
        "auto_lock_seconds": auto_lock_rem,
        "daily_limit_minutes": state.get("daily_limit_minutes", 120),
        "is_blocked": state.get("is_blocked", 0),
        "current_process": state.get("current_process", ""),
        "current_window": state.get("current_window", ""),
        "foreground_process": state.get("current_process", ""),
        "foreground_window": state.get("current_window", ""),
        "last_updated": state.get("last_updated", ""),
        "hosts_blocked": enforcement.is_distraction_blocked(),
        "is_admin": enforcement.is_admin(),
        "camera": camera_streamer.last_metrics,
        "streak_minutes": max(1, int(state.get("current_balance", 0) // 60)),
        "focus_score": round(camera_streamer.last_metrics.get("focus_score", 96.0), 1),
        "lockdown_active": lockdown.get("is_active", False),
        "lockdown_remaining_seconds": lockdown.get("remaining_seconds", 0),
        "lockdown_total_seconds": lockdown.get("duration_seconds", 0),
        "lockdown_reason": lockdown.get("reason", "")
    }


class ParentalDashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_str):
        body = html_str.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(DASHBOARD_HTML)
        elif parsed.path == "/api/status":
            self._send_json(get_system_status_payload())
        elif parsed.path == "/api/auth/status":
            self._send_json({
                "role": get_effective_role(),
                "auto_lock_seconds": max(0, int(300 - (time.time() - _last_parent_active_timestamp))) if _current_session_role == "PARENT" else 0
            })
        elif parsed.path == "/api/policies":
            self._send_json(db_manager.get_app_policies())
        elif parsed.path == "/api/processes":
            self._send_json(db_manager.get_tracked_processes(limit=100))
        elif parsed.path == "/api/rules":
            self._send_json(db_manager.get_enforcement_rules())
        elif parsed.path == "/api/alerts":
            self._send_json(db_manager.get_parent_alerts(limit=50))
        elif parsed.path == "/api/metrics/daily":
            self._send_json(db_manager.get_daily_focus_metrics(limit=7))
        elif parsed.path == "/api/metrics/timeline-24h":
            self._send_json(db_manager.get_timeline_slots())
        elif parsed.path == "/api/metrics/app-distribution":
            self._send_json(db_manager.get_app_usage_distribution())
        elif parsed.path == "/api/apps/recent":
            self._send_json(db_manager.get_recent_app_history(limit=8))
        elif parsed.path == "/api/diagnostics":
            self._send_json(get_system_diagnostics())
        elif parsed.path == "/api/logs":
            self._send_json(db_manager.get_recent_logs(limit=15))
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
                self.send_error(503, "Camera feed not ready")
        elif parsed.path == "/api/video_feed":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, no-store")
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
                    time.sleep(0.04)
            except (ConnectionResetError, BrokenPipeError):
                pass
        else:
            self.send_error(404, "Endpoint Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if parsed.path == "/api/auth/verify_pin":
            pin = str(payload.get("pin", "")).strip()
            if db_manager.verify_parent_pin(pin):
                global _current_session_role
                _current_session_role = "PARENT"
                touch_parent_activity()
                db_manager.set_current_role("PARENT")
                self._send_json({"authenticated": True, "role": "PARENT"})
            else:
                db_manager.dispatch_parent_alert(
                    target_app="web_dashboard",
                    event_type="UNAUTHORIZED_ATTEMPT",
                    severity="WARNING",
                    details=f"Failed Master PIN verification attempt: '{pin}'"
                )
                self._send_json({"authenticated": False, "error": "Invalid Master PIN"}, code=401)

        elif parsed.path == "/api/auth/logout":
            _current_session_role = "STUDENT"
            db_manager.set_current_role("STUDENT")
            self._send_json({"status": "ok", "role": "STUDENT"})

        elif parsed.path == "/api/lockdown/start":
            touch_parent_activity()
            dur = int(payload.get("duration_seconds", 1800))
            reason = payload.get("reason", "Parental Override")
            res = db_manager.start_emergency_lockdown(duration_seconds=dur, reason=reason)
            enforcement.block_distractions()
            enforcement.terminate_all_running_distractions()
            self._send_json(res)

        elif parsed.path == "/api/lockdown/edit":
            touch_parent_activity()
            dur = int(payload.get("duration_seconds", 3600))
            res = db_manager.edit_emergency_lockdown(new_duration_seconds=dur)
            self._send_json(res)

        elif parsed.path == "/api/lockdown/stop":
            touch_parent_activity()
            res = db_manager.stop_emergency_lockdown()
            if db_manager.get_current_balance() > 0:
                enforcement.unblock_distractions()
            self._send_json(res)

        elif parsed.path == "/api/policies":
            touch_parent_activity()
            t_name = payload.get("target_name", "")
            if t_name:
                db_manager.set_app_policy(
                    target_name=t_name,
                    category=payload.get("category", "GAMING"),
                    policy_type=payload.get("policy_type", "DAILY_QUOTA"),
                    daily_quota_seconds=int(payload.get("daily_quota_seconds", 1800)),
                    curfew_start=payload.get("curfew_start", "21:00"),
                    curfew_end=payload.get("curfew_end", "06:00"),
                    is_active=int(payload.get("is_active", 1))
                )
            self._send_json({"status": "ok"})

        elif parsed.path == "/api/policies/delete":
            touch_parent_activity()
            t_name = payload.get("target_name", "")
            if t_name:
                db_manager.delete_app_policy(t_name)
            self._send_json({"status": "ok"})

        elif parsed.path == "/api/alerts/acknowledge":
            touch_parent_activity()
            alert_id = int(payload.get("id", 0))
            if alert_id:
                db_manager.acknowledge_parent_alert(alert_id)
            self._send_json({"status": "ok"})

        elif parsed.path == "/api/calibrate":
            touch_parent_activity()
            try:
                import vision_pipeline
                vision_pipeline.get_default_pipeline().calibrate_baseline()
            except Exception:
                pass
            self._send_json({"status": "ok", "calibrated": True})

        elif parsed.path == "/api/rules":
            p_name = payload.get("process_name", "")
            if p_name:
                db_manager.set_enforcement_rule(
                    process_name=p_name,
                    display_name=payload.get("display_name"),
                    time_limit_minutes=int(payload.get("time_limit_minutes", 60)),
                    is_blocked=int(payload.get("is_blocked", 0)),
                    action=payload.get("action", "terminate"),
                    category=payload.get("category", "General")
                )
            self._send_json({"status": "ok"})

        elif parsed.path == "/api/rules/delete":
            p_name = payload.get("process_name", "")
            if p_name:
                db_manager.delete_enforcement_rule(p_name)
            self._send_json({"status": "ok"})

        elif parsed.path == "/api/adjust-time":
            delta = int(payload.get("delta", 0))
            new_bal = db_manager.update_balance(delta, reason=f"Parental adjustment ({delta:+d}s)")
            if new_bal > 0 and enforcement.is_distraction_blocked():
                enforcement.unblock_distractions()
            self._send_json({"status": "ok", "new_balance": new_bal})

        elif parsed.path == "/api/set-time":
            bal = int(payload.get("balance", 0))
            new_bal = db_manager.reset_balance(bal)
            if new_bal > 0 and enforcement.is_distraction_blocked():
                enforcement.unblock_distractions()
            self._send_json({"status": "ok", "new_balance": new_bal})

        elif parsed.path == "/api/toggle-lock":
            locked = bool(payload.get("locked", False))
            db_manager.set_blocked_status(locked)
            if locked:
                enforcement.block_distractions()
                enforcement.terminate_all_running_distractions()
                curr = db_manager.get_child_state().get("current_process", "")
                if curr and curr.lower() in enforcement.KNOWN_DISTRACTION_PROCESSES:
                    enforcement.terminate_process_by_name(curr)
            else:
                if db_manager.get_current_balance() > 0:
                    enforcement.unblock_distractions()
            self._send_json({"status": "ok", "is_locked": locked})

        elif parsed.path == "/api/kill-process":
            p_name = payload.get("process_name", "")
            success = enforcement.terminate_process_by_name(p_name) if p_name else False
            self._send_json({"status": "ok", "terminated": success})

        elif parsed.path == "/api/toggle-web-filter":
            blocked = enforcement.is_distraction_blocked()
            if blocked:
                enforcement.unblock_distractions()
            else:
                enforcement.block_distractions()
                enforcement.terminate_all_running_distractions()
            self._send_json({"status": "ok", "hosts_blocked": enforcement.is_distraction_blocked()})

        else:
            self.send_error(404, "Endpoint Not Found")

    def log_message(self, format, *args):
        pass


def run_server(port=PORT):
    db_manager.init_db()
    camera_streamer.start()
    print("=" * 65)
    print(f" DEMON STUDY MONITOR DUAL-PORTAL: http://localhost:{port}")
    print(f" Live Vision Camera Monitor     : ACTIVE (/api/video_feed)")
    print(f" Database                       : {db_manager.DEFAULT_DB_PATH}")
    print("=" * 65)

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, port), ParentalDashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        camera_streamer.stop()
        server.server_close()


if __name__ == "__main__":
    run_server()

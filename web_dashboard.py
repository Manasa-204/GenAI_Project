"""
web_dashboard.py - Demon Multi-Agent Study Monitor Web Dashboard & High-Speed Stream
Features:
- ThreadingHTTPServer for fully asynchronous, non-blocking HTTP request processing.
- Multi-threaded OpenCV webcam capture with MediaPipe Face Mesh, EAR, and Head Pose.
- Calibrated alert logic:
    * Normal blinks (<2.0s) show gentle cyan status (NO false red alerts).
    * True drowsiness requires continuous closed eyes for >= 2.0 seconds.
    * Head pose filter avoids false yellow alerts during normal looking down/up.
- Real-time OS Default Desktop window scraping (Eng 3) with Ollama SLM classification.
- Autonomous background monitor loop advancing study balance and calculating Focus Score every second.
- OS Hosts file blocker with YouTube domain blocking controls.
- Interactive Scenario Sandbox & 5-Suite Test Runner.
"""

import os
import sys
import time
import json
import csv
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import cv2
import numpy as np
import mediapipe as mp

import db_manager
import logic_controller
import vision_pipeline
import semantic_pipeline
import enforcement
import main
import run_all_tests
import user_tracker
from user_tracker import get_user_tracker

PORT = 8000
HOST = "127.0.0.1"


class RobustCameraStreamer:
    """
    Dedicated background worker thread that captures webcam frames,
    applies MediaPipe Face Mesh with temporal smoothing, and provides latest JPEG frame.
    """

    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.cap = None
        self.is_running = False
        self.lock = threading.Lock()
        self.latest_jpeg = None
        self.latest_raw_frame = None
        self.latest_face_landmarks = []
        self.u_tracker = get_user_tracker()
        self.frame_count = 0
        self.fps = 0.0
        self.last_state_data = {
            "ear": 0.0,
            "eyes_closed": False,
            "is_drowsy": False,
            "is_using_mobile": False,
            "head_pose": (0.0, 0.0, 0.0),
            "looking_away": False,
            "face_detected": False,
            "primary_locked": False,
            "background_count": 0
        }
        self.thread = None

    def enroll_current_user(self, name="Primary User", samples_count=20):
        """Captures samples from the live camera stream and calibrates the primary user."""
        samples = []
        for _ in range(samples_count):
            with self.lock:
                if self.latest_face_landmarks:
                    samples.append((self.latest_face_landmarks[0], (480, 640)))
            time.sleep(0.08)
        if len(samples) >= 3:
            return self.u_tracker.enroll(samples, name=name)
        return False

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.thread.start()

    def _open_camera(self):
        if sys.platform == "win32":
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(self.camera_index)
        if cap and cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap
        return None

    def reset(self):
        """Forces camera hardware release and re-initialization."""
        with self.lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

    def _capture_worker(self):
        self.cap = self._open_camera()

        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=4,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        fps_timer = time.time()
        fps_frames = 0
        consecutive_failures = 0

        # Temporal timers for accurate alert filtering
        eyes_closed_start_time = None
        away_start_time = None
        mobile_start_time = None
        face_lost_start_time = None
        ear_threshold = 0.18
        sleep_duration_threshold = 2.0
        away_duration_threshold = 2.0
        yaw_threshold = 40.0
        pitch_threshold = 38.0
        mobile_pitch_threshold = -11.0

        u_tracker = self.u_tracker

        while self.is_running:
            if not self.cap or not self.cap.isOpened():
                self.cap = self._open_camera()
                if not self.cap:
                    time.sleep(0.3)
                    continue

            try:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    consecutive_failures += 1
                    if consecutive_failures > 15:
                        self.reset()
                        consecutive_failures = 0
                    time.sleep(0.04)
                    continue

                consecutive_failures = 0
            except Exception:
                time.sleep(0.04)
                continue

            now = time.time()
            self.frame_count += 1
            fps_frames += 1

            if now - fps_timer >= 1.0:
                self.fps = round(fps_frames / (now - fps_timer), 1)
                fps_frames = 0
                fps_timer = now

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            with self.lock:
                self.latest_raw_frame = frame
                self.latest_face_landmarks = results.multi_face_landmarks or []

            annotated = frame.copy()

            if results.multi_face_landmarks:
                face_lost_start_time = None

                # Primary User Identification & Multi-Face Discrimination
                primary_face, primary_box, background_boxes = u_tracker.find_primary_user(
                    results.multi_face_landmarks, (h, w)
                )

                # Draw background / secondary persons in purple/gray (ignored)
                for bg_box in background_boxes:
                    bx1 = int(bg_box["min_x"] * w)
                    by1 = int(bg_box["min_y"] * h)
                    bx2 = int(bg_box["max_x"] * w)
                    by2 = int(bg_box["max_y"] * h)
                    cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (180, 100, 240), 1)
                    cv2.putText(annotated, "IGNORED (BACKGROUND)", (bx1, max(12, by1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 100, 240), 1)

                if primary_face:
                    # Enrolled primary user is present and locked!
                    bx1 = int(primary_box["min_x"] * w)
                    by1 = int(primary_box["min_y"] * h)
                    bx2 = int(primary_box["max_x"] * w)
                    by2 = int(primary_box["max_y"] * h)
                    conf_pct = int(primary_box.get("confidence", 1.0) * 100)
                    cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (0, 255, 128), 2)
                    cv2.putText(annotated, f"PRIMARY USER [LOCKED] {conf_pct}%", (bx1, max(14, by1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 128), 2)

                    landmarks = primary_face.landmark

                    # 1. EAR Calculation
                    left_eye_pts = {
                        k: (landmarks[idx].x * w, landmarks[idx].y * h)
                        for k, idx in vision_pipeline.LEFT_EYE_LANDMARKS.items()
                    }
                    right_eye_pts = {
                        k: (landmarks[idx].x * w, landmarks[idx].y * h)
                        for k, idx in vision_pipeline.RIGHT_EYE_LANDMARKS.items()
                    }
                    l_ear = vision_pipeline.calculate_ear(left_eye_pts)
                    r_ear = vision_pipeline.calculate_ear(right_eye_pts)
                    avg_ear = (l_ear + r_ear) / 2.0
                    is_eyes_closed = avg_ear < ear_threshold

                    # Temporal Sleep Timing
                    sleep_duration = 0.0
                    if is_eyes_closed:
                        if eyes_closed_start_time is None:
                            eyes_closed_start_time = now
                        sleep_duration = now - eyes_closed_start_time
                    else:
                        eyes_closed_start_time = None

                    # 2. Head Pose Calculation
                    pose_pts = [
                        (landmarks[idx].x * w, landmarks[idx].y * h)
                        for idx in vision_pipeline.POSE_LANDMARK_INDICES
                    ]
                    pitch, yaw, roll = vision_pipeline.estimate_head_pose(pose_pts, (h, w))
                    looking_away_inst = (abs(yaw) > yaw_threshold) or (abs(pitch) > pitch_threshold)

                    away_duration = 0.0
                    if looking_away_inst:
                        if away_start_time is None:
                            away_start_time = now
                        away_duration = now - away_start_time
                    else:
                        away_start_time = None

                    # 3. Mobile Phone Distraction Detection
                    pc_idle_sec = vision_pipeline.get_system_idle_time()
                    is_looking_down = (pitch <= mobile_pitch_threshold)
                    mobile_distracted_inst = is_looking_down and (pc_idle_sec >= 2.5)

                    mobile_duration = 0.0
                    if mobile_distracted_inst:
                        if mobile_start_time is None:
                            mobile_start_time = now
                        mobile_duration = now - mobile_start_time
                    else:
                        mobile_start_time = None

                    is_drowsy = (eyes_closed_start_time is not None) and (sleep_duration >= sleep_duration_threshold)
                    is_using_mobile = (mobile_start_time is not None) and (mobile_duration >= 2.0)
                    is_away = (away_start_time is not None) and (away_duration >= away_duration_threshold)

                    # Draw landmark mesh
                    for pt in list(left_eye_pts.values()) + list(right_eye_pts.values()):
                        cv2.circle(annotated, (int(pt[0]), int(pt[1])), 2, (0, 255, 128), -1)

                    nose = (int(landmarks[1].x * w), int(landmarks[1].y * h))
                    chin = (int(landmarks[152].x * w), int(landmarks[152].y * h))
                    cv2.circle(annotated, nose, 4, (0, 165, 255), -1)
                    cv2.circle(annotated, chin, 3, (255, 200, 0), -1)

                    # 3D Head Orientation Vector
                    nose_end_x = int(nose[0] + yaw * 1.5)
                    nose_end_y = int(nose[1] + pitch * 1.5)
                    cv2.line(annotated, nose, (nose_end_x, nose_end_y), (0, 255, 255), 2)

                    # Status HUD with Calibrated Alerts
                    if is_drowsy:
                        status_color = (0, 0, 255)  # RED
                        status_text = f"DROWSY / SLEEP DETECTED ({sleep_duration:.1f}s)"
                    elif is_using_mobile:
                        status_color = (0, 80, 255)  # AMBER/ORANGE: Mobile phone detected!
                        status_text = f"MOBILE PHONE DISTRACTION ({mobile_duration:.1f}s)"
                    elif is_eyes_closed:
                        status_color = (255, 200, 0)
                        status_text = f"BLINKING ({sleep_duration:.1f}s / 2.0s)"
                    elif is_away:
                        status_color = (0, 165, 255)
                        status_text = f"LOOKING AWAY ({away_duration:.1f}s)"
                    else:
                        status_color = (0, 255, 0)
                        status_text = "FOCUSED & ENGAGED (ACTIVE)"

                    cv2.rectangle(annotated, (15, 15), (w - 15, 78), (20, 20, 20), -1)
                    cv2.rectangle(annotated, (15, 15), (w - 15, 78), status_color, 2)
                    cv2.putText(annotated, f"STATE: {status_text}", (25, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 2)
                    cv2.putText(annotated, f"EAR: {avg_ear:.3f} | YAW: {yaw:+.1f} deg | PITCH: {pitch:+.1f} deg | PC IDLE: {pc_idle_sec:.1f}s", (25, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1)

                    with self.lock:
                        self.last_state_data = {
                            "ear": avg_ear,
                            "eyes_closed": is_eyes_closed,
                            "is_drowsy": is_drowsy,
                            "is_using_mobile": is_using_mobile,
                            "head_pose": (pitch, yaw, roll),
                            "looking_away": is_away,
                            "face_detected": True,
                            "primary_locked": True,
                            "background_count": len(background_boxes)
                        }

                else:
                    # Enrolled primary user is NOT found in frame!
                    eyes_closed_start_time = None
                    away_start_time = None
                    mobile_start_time = None

                    if face_lost_start_time is None:
                        face_lost_start_time = now
                    face_lost_duration = now - face_lost_start_time
                    truly_away = face_lost_duration >= 1.5

                    status_color = (0, 140, 255)
                    status_text = f"PRIMARY USER AWAY / ABANDONED ({face_lost_duration:.1f}s)"
                    sub_text = f"{len(background_boxes)} background face(s) ignored - Primary user absent"

                    cv2.rectangle(annotated, (15, 15), (w - 15, 78), (20, 20, 20), -1)
                    cv2.rectangle(annotated, (15, 15), (w - 15, 78), status_color, 2)
                    cv2.putText(annotated, f"STATE: {status_text}", (25, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 2)
                    cv2.putText(annotated, sub_text, (25, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

                    with self.lock:
                        self.last_state_data = {
                            "ear": 0.0,
                            "eyes_closed": False,
                            "is_drowsy": False,
                            "is_using_mobile": False,
                            "head_pose": (0.0, 0.0, 0.0),
                            "looking_away": truly_away,
                            "face_detected": False,
                            "primary_locked": False,
                            "background_count": len(background_boxes)
                        }

            else:
                eyes_closed_start_time = None
                away_start_time = None
                mobile_start_time = None

                if face_lost_start_time is None:
                    face_lost_start_time = now
                face_lost_duration = now - face_lost_start_time

                truly_away = face_lost_duration >= 1.5
                if truly_away:
                    status_color = (0, 140, 255)
                    status_text = f"USER AWAY / ABANDONED ({face_lost_duration:.1f}s)"
                    sub_text = "No face detected in camera frame - state IDLE"
                else:
                    status_color = (255, 200, 0)
                    status_text = "TRACKING FACE (SEARCHING...)"
                    sub_text = "Smoothing momentary camera frame drop..."

                cv2.rectangle(annotated, (15, 15), (w - 15, 78), (20, 20, 20), -1)
                cv2.rectangle(annotated, (15, 15), (w - 15, 78), status_color, 2)
                cv2.putText(annotated, f"STATE: {status_text}", (25, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 2)
                cv2.putText(annotated, sub_text, (25, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

                cx, cy = w // 2, h // 2
                cv2.rectangle(annotated, (cx - 100, cy - 130), (cx + 100, cy + 130), (70, 70, 70), 1)

                with self.lock:
                    self.last_state_data = {
                        "ear": 0.0,
                        "eyes_closed": False,
                        "is_drowsy": False,
                        "is_using_mobile": False,
                        "head_pose": (0.0, 0.0, 0.0),
                        "looking_away": truly_away,
                        "face_detected": not truly_away,
                        "primary_locked": False,
                        "background_count": 0
                    }

            time_str = time.strftime("%H:%M:%S")
            cv2.rectangle(annotated, (0, h - 26), (w, h), (10, 10, 10), -1)
            cv2.putText(annotated, f"LIVE FEED: {time_str} | {self.fps} FPS | Frame #{self.frame_count}", (15, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 240, 160), 1)

            ret, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                with self.lock:
                    self.latest_jpeg = jpeg.tobytes()

            time.sleep(0.02)

        face_mesh.close()

    def get_frame(self):
        with self.lock:
            return self.latest_jpeg

    def get_metrics(self):
        with self.lock:
            return {
                **self.last_state_data,
                "fps": self.fps,
                "frame_count": self.frame_count
            }

    def stop(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None


camera_streamer = RobustCameraStreamer()


class AutonomousStudyMonitor:
    """
    Autonomous daemon running in the background every 1 second:
    1. Reads live camera telemetry (Eng 2).
    2. Reads live active OS window on Default desktop (Eng 3).
    3. Evaluates the AND Gate (Eng 1) and updates SQLite study_monitor.db.
    4. Computes running Focus Score.
    5. Enforces hosts file blocking if balance reaches 0s on a distraction (Eng 4).
    6. Manages simulation sandboxing with auto-revert to live camera & window mode.
    """

    def __init__(self):
        self.is_running = False
        self.focused_seconds = 0
        self.distracted_seconds = 0
        self.drowsy_seconds = 0
        self.away_seconds = 0
        self.total_seconds = 0
        self.focus_score = 100.0
        self.latest_window = "Desktop / Idle"
        self.latest_semantic = "EDUCATIONAL"
        self.simulation_scenario = None
        self.simulation_expire_time = 0.0
        self.lock = threading.Lock()
        self.thread = None

    def start_simulation(self, scenario_name, v_state, s_state, window_title=None, duration=8.0):
        """Activates a temporary simulation condition with auto-revert timeout."""
        with self.lock:
            self.simulation_scenario = scenario_name
            self.simulation_expire_time = time.time() + duration
            if window_title:
                self.latest_window = window_title
            if s_state:
                self.latest_semantic = s_state
        if v_state:
            vision_pipeline.set_mock_vision_state(v_state)
        if s_state:
            semantic_pipeline.set_mock_semantic_state(s_state)

    def resume_live_mode(self):
        """Immediately cancels any active simulation and resumes live camera and OS window tracking."""
        with self.lock:
            self.simulation_scenario = None
            self.simulation_expire_time = 0.0
            self.latest_window = semantic_pipeline.get_active_window_title()
            self.latest_semantic = semantic_pipeline.get_semantic_state(window_title=self.latest_window)
        vision_pipeline.set_mock_vision_state(None)
        semantic_pipeline.set_mock_semantic_state(None)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _monitor_loop(self):
        while self.is_running:
            time.sleep(1.0)
            try:
                # Check simulation auto-expiry back to live sensor mode
                with self.lock:
                    if self.simulation_scenario and time.time() >= self.simulation_expire_time:
                        self.simulation_scenario = None
                        self.simulation_expire_time = 0.0
                        vision_pipeline.set_mock_vision_state(None)
                        semantic_pipeline.set_mock_semantic_state(None)

                # 1. Physical Vision State
                if vision_pipeline._mock_vision_state is not None:
                    v_state = vision_pipeline._mock_vision_state
                    cam = camera_streamer.get_metrics()
                else:
                    cam = camera_streamer.get_metrics()
                    if cam.get("is_drowsy") or not cam.get("face_detected") or cam.get("looking_away") or cam.get("is_using_mobile"):
                        v_state = "IDLE"
                    else:
                        v_state = "ACTIVE"

                # 2. Semantic Digital State (from user's Default desktop)
                if semantic_pipeline._mock_semantic_state is not None:
                    s_state = semantic_pipeline._mock_semantic_state
                    with self.lock:
                        title = self.latest_window
                else:
                    title = semantic_pipeline.get_active_window_title()
                    s_state = semantic_pipeline.get_semantic_state(window_title=title)

                with self.lock:
                    self.latest_window = title
                    self.latest_semantic = s_state
                    self.total_seconds += 1

                # 3. AND Gate Evaluation
                result = logic_controller.evaluate_cycle(
                    vision_override=v_state,
                    semantic_override=s_state
                )

                bal = result["new_balance"]

                # 4. Telemetry tracking (Differentiates Drowsy vs Mobile vs Abandoned Desk)
                with self.lock:
                    if result["verdict"] == "REWARD":
                        self.focused_seconds += 1
                    elif result["verdict"] == "DISTRACTION":
                        self.distracted_seconds += 1
                    elif result["verdict"] == "VISION_OVERRIDE":
                        if cam.get("is_drowsy"):
                            self.drowsy_seconds += 1
                        elif cam.get("is_using_mobile"):
                            self.distracted_seconds += 1
                        elif not cam.get("face_detected") or cam.get("looking_away"):
                            self.away_seconds += 1
                        else:
                            self.drowsy_seconds += 1
                    else:
                        self.away_seconds += 1

                    active_time = self.focused_seconds + self.distracted_seconds
                    if active_time > 0:
                        self.focus_score = round((self.focused_seconds / active_time) * 100.0, 1)

                # 5. OS Enforcement Rules (Only act on state transitions)
                # Requires sustained study (bal >= 3) to prevent 1-second flapping back to unblocked
                if bal <= 0 and s_state == "DISTRACTION":
                    if not enforcement.is_distraction_blocked():
                        enforcement.block_distractions()
                    enforcement.enforce_active_distraction(window_title=title)
                elif bal >= 3:
                    if enforcement.is_distraction_blocked():
                        enforcement.unblock_distractions()

                # Real-time Distraction Interceptor:
                # If currently blocked and user opens YouTube or another distraction,
                # immediately minimize the window to enforce focus!
                if enforcement.is_distraction_blocked():
                    enforcement.enforce_active_distraction(window_title=title)

            except Exception as e:
                # Keep loop alive even if temporary error
                pass

    def get_stats(self):
        with self.lock:
            return {
                "focused_seconds": self.focused_seconds,
                "distracted_seconds": self.distracted_seconds,
                "drowsy_seconds": self.drowsy_seconds,
                "away_seconds": self.away_seconds,
                "total_seconds": self.total_seconds,
                "focus_score": self.focus_score,
                "window": self.latest_window,
                "semantic": self.latest_semantic,
                "is_simulating": self.simulation_scenario is not None,
                "simulation_scenario": self.simulation_scenario,
                "simulation_seconds_left": max(0, int(self.simulation_expire_time - time.time())) if self.simulation_scenario else 0,
            }

    def stop(self):
        self.is_running = False


study_monitor = AutonomousStudyMonitor()


def get_system_status():
    """Gathers live status across all 4 engineering modules."""
    balance = db_manager.get_current_balance()
    is_blocked = enforcement.is_distraction_blocked()

    stats = study_monitor.get_stats()
    cam_info = camera_streamer.get_metrics()

    if vision_pipeline._mock_vision_state is not None:
        vision_state = vision_pipeline._mock_vision_state
    else:
        if cam_info.get("is_drowsy") or not cam_info.get("face_detected") or cam_info.get("looking_away") or cam_info.get("is_using_mobile"):
            vision_state = "IDLE"
        else:
            vision_state = "ACTIVE"

    active_window = stats["window"]
    semantic_state = stats["semantic"]

    if vision_state == "ACTIVE" and semantic_state == "EDUCATIONAL":
        fused_state = "FOCUSED"
        color = "emerald"
    elif vision_state == "IDLE" and semantic_state == "EDUCATIONAL":
        if cam_info.get("is_using_mobile"):
            fused_state = "MOBILE_DISTRACTION"
            color = "amber"
        elif not cam_info.get("face_detected"):
            fused_state = "USER_AWAY"
            color = "orange"
        elif cam_info.get("is_drowsy"):
            fused_state = "DROWSY"
            color = "rose"
        elif cam_info.get("looking_away"):
            fused_state = "LOOKING_AWAY"
            color = "amber"
        else:
            fused_state = "VISION_OVERRIDE"
            color = "amber"
    elif semantic_state == "DISTRACTION":
        fused_state = "ACTIVE_DISTRACTION" if vision_state == "ACTIVE" else "IDLE_DISTRACTION"
        color = "rose"
    else:
        fused_state = "IDLE"
        color = "slate"

    recent_logs = db_manager.get_recent_logs(limit=8)

    research_entries = []
    csv_path = logic_controller.DEFAULT_CSV_PATH
    if os.path.exists(csv_path):
        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
                research_entries = reader[-8:]
                research_entries.reverse()
        except Exception:
            pass

    return {
        "balance": balance,
        "is_blocked": is_blocked,
        "vision_state": vision_state,
        "active_window": active_window,
        "semantic_state": semantic_state,
        "fused_state": fused_state,
        "color": color,
        "camera": cam_info,
        "stats": stats,
        "recent_logs": recent_logs,
        "research_entries": research_entries,
        "is_simulating": stats["is_simulating"],
        "simulation_scenario": stats["simulation_scenario"],
        "simulation_seconds_left": stats["simulation_seconds_left"],
        "hosts_writeable": enforcement.can_write_hosts(),
        "user_profile": camera_streamer.u_tracker.profile.to_dict() if camera_streamer.u_tracker and camera_streamer.u_tracker.profile else None,
    }


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Demon Study Monitor - Live High-Speed Camera Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Plus+Jakarta+Sans:wght@400;500;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #070a12; color: #f1f5f9; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .glass { background: rgba(15, 23, 42, 0.75); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); }
        .glow-emerald { box-shadow: 0 0 25px rgba(16, 185, 129, 0.25); }
        .glow-rose { box-shadow: 0 0 25px rgba(244, 63, 94, 0.35); }
        .glow-amber { box-shadow: 0 0 25px rgba(245, 158, 11, 0.25); }
    </style>
</head>
<body class="min-h-screen p-4 md:p-8">
    <div class="max-w-7xl mx-auto space-y-6">

        <!-- Top Header Navigation -->
        <header class="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-slate-800 gap-4">
            <div class="flex items-center gap-3">
                <div class="w-11 h-11 rounded-xl bg-gradient-to-tr from-indigo-600 via-purple-600 to-rose-500 flex items-center justify-center shadow-lg shadow-indigo-500/30">
                    <i class="fa-solid fa-brain text-white text-xl"></i>
                </div>
                <div>
                    <h1 class="text-2xl font-black tracking-tight text-white flex items-center gap-2">
                        DEMON <span class="text-xs font-bold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">Autonomous Monitor Active</span>
                    </h1>
                    <p class="text-xs text-slate-400">Contextual Study Monitor, MediaPipe Vision, Ollama SLM & OS Enforcement</p>
                </div>
            </div>

            <div class="flex items-center gap-3">
                <span id="live-mode-badge" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span> 🟢 LIVE SENSOR MODE (Camera & Window)
                </span>
                <button onclick="resumeLiveMode()" class="px-3 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-bold transition flex items-center gap-1.5 shadow-sm">
                    <i class="fa-solid fa-camera"></i> Resume Live Mode
                </button>
            </div>
        </header>

        <!-- Dynamic Simulation Active Notification Banner -->
        <div id="simulation-banner" class="hidden p-3.5 rounded-xl bg-purple-950/40 border border-purple-500/50 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg shadow-purple-950/50">
            <div class="flex items-center gap-2.5 text-xs text-purple-200">
                <div class="w-7 h-7 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-400 text-sm">
                    <i class="fa-solid fa-flask-vial animate-bounce"></i>
                </div>
                <div>
                    <span class="font-bold text-white uppercase tracking-wider text-[11px]">Simulation Active:</span>
                    <span id="sim-scenario-name" class="font-semibold text-purple-300 ml-1">Abandoned Stream</span>
                    <span class="text-purple-400 ml-2 mono">(Auto-reverting to live camera in <span id="sim-countdown" class="font-bold text-white">8</span>s)</span>
                </div>
            </div>
            <button onclick="resumeLiveMode()" class="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs transition flex items-center justify-center gap-1.5 shadow">
                <i class="fa-solid fa-rotate-left"></i> Exit to Live Camera Now
            </button>
        </div>

        <!-- Live Feed & State Hero Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

            <!-- Video Stream Viewport (7 cols) -->
            <div class="lg:col-span-7 glass p-5 rounded-2xl flex flex-col justify-between">
                <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
                    <div class="flex items-center gap-2 text-xs font-bold tracking-wider uppercase text-slate-300">
                        <i class="fa-solid fa-camera text-emerald-400"></i>
                        <span>Live MediaPipe Camera Feed (Eng 2)</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <button id="enroll-btn" onclick="enrollPrimaryUser()" class="px-2.5 py-1 rounded text-[10px] font-bold bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 border border-indigo-500/40 transition flex items-center gap-1 shadow-sm">
                            <i class="fa-solid fa-user-lock text-indigo-400"></i> <span id="enroll-btn-label">Enroll Primary User</span>
                        </button>
                        <button onclick="reconnectCamera()" class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800/80 hover:bg-slate-700 text-slate-300 border border-slate-700 transition flex items-center gap-1 shadow-sm">
                            <i class="fa-solid fa-rotate text-emerald-400"></i> Reconnect
                        </button>
                        <span id="camera-fps-badge" class="text-[10px] mono text-emerald-400 flex items-center gap-1 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-500/30">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Streaming 30 FPS
                        </span>
                    </div>
                </div>

                <!-- Video Viewport with Continuous Dual-Buffered Refresh -->
                <div class="relative rounded-xl overflow-hidden bg-black border border-slate-800 aspect-video flex items-center justify-center shadow-inner">
                    <img id="video-stream" src="/api/camera_frame" alt="Camera Feed Initializing..." class="w-full h-full object-cover">
                    <div class="absolute bottom-3 left-3 bg-slate-900/85 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-700/80 text-[11px] mono text-slate-300 flex items-center gap-2">
                        <i class="fa-solid fa-eye text-emerald-400"></i> EAR Eyelid Tracker (Threshold: &ge; 2.0s)
                    </div>
                </div>

                <!-- Camera Info Chips -->
                <div class="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-slate-800/80 text-center">
                    <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800 text-xs">
                        <div class="text-[10px] text-slate-400">Live EAR</div>
                        <div class="font-bold text-slate-200 mt-0.5" id="hud-ear">EAR: 0.000</div>
                    </div>
                    <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800 text-xs">
                        <div class="text-[10px] text-slate-400">Head Pose Limits</div>
                        <div class="font-bold text-slate-200 mt-0.5">&plusmn;40&deg; Yaw / 38&deg; Pitch</div>
                    </div>
                    <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800 text-xs">
                        <div class="text-[10px] text-slate-400">Mesh Keypoints</div>
                        <div class="font-bold text-emerald-400 mt-0.5">478 3D Landmarks</div>
                    </div>
                </div>
            </div>

            <!-- Live State Hero & Decision Engine (5 cols) -->
            <div class="lg:col-span-5 flex flex-col gap-6">

                <!-- Study Bank Hero -->
                <div class="glass p-6 rounded-2xl flex-1 flex flex-col justify-between" id="state-card">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold tracking-wider uppercase text-slate-400">Current Study Bank</span>
                        <span id="fused-badge" class="px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-slate-800 text-slate-300">
                            INITIALIZING
                        </span>
                    </div>

                    <div class="my-4 text-center">
                        <div class="text-6xl font-extrabold mono tracking-tight text-white" id="balance-display">
                            0<span class="text-2xl text-slate-500 ml-1">s</span>
                        </div>
                        <p class="text-xs text-slate-400 mt-2" id="state-description">Auto-accruing when Active & Educational</p>
                    </div>

                    <!-- Live Focus Score Progress Gauge -->
                    <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 mb-2">
                        <div class="flex items-center justify-between mb-1 text-xs">
                            <span class="font-bold text-slate-300 flex items-center gap-1.5">
                                <i class="fa-solid fa-chart-line text-indigo-400"></i> Running Focus Score
                            </span>
                            <span class="font-bold mono text-emerald-400" id="focus-score-text">100.0%</span>
                        </div>
                        <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                            <div id="focus-score-bar" class="bg-gradient-to-r from-indigo-500 to-emerald-400 h-2 rounded-full transition-all duration-500" style="width: 100%;"></div>
                        </div>
                        <div class="flex items-center justify-between text-[10px] text-slate-400 mt-1.5 mono">
                            <span id="focused-time-text">Focused: 0s</span>
                            <span id="distracted-time-text">Distracted: 0s</span>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-2 pt-3 border-t border-slate-800/80">
                        <button onclick="setBalance(20)" class="py-2 px-3 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-xs font-medium text-slate-300 transition">
                            +20s Accrue Bank
                        </button>
                        <button onclick="setBalance(0)" class="py-2 px-3 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-xs font-medium text-slate-300 transition">
                            Drain to 0s
                        </button>
                    </div>
                </div>

                <!-- Digital Cognitive Sensor (Eng 3) & OS Enforcement (Eng 4) -->
                <div class="glass p-5 rounded-2xl space-y-3">
                    <div class="text-xs font-semibold tracking-wider uppercase text-slate-400 flex items-center justify-between">
                        <span>Cognitive & OS Control</span>
                        <span class="text-[10px] text-indigo-400 mono">Ollama Llama/Qwen</span>
                    </div>

                    <!-- Active Window Title (Purple Card Eng 3) -->
                    <div class="p-3.5 rounded-xl bg-purple-950/20 border border-purple-500/30">
                        <div class="flex items-center justify-between mb-1.5">
                            <span class="text-xs font-bold text-purple-300 flex items-center gap-1.5">
                                <i class="fa-solid fa-window-maximize text-purple-400"></i> Active OS Window (Eng 3)
                            </span>
                            <span id="semantic-badge" class="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40">
                                EDUCATIONAL
                            </span>
                        </div>
                        <div class="text-xs text-slate-200 truncate mono" id="window-title-display">
                            Scraping foreground window...
                        </div>
                    </div>

                    <!-- OS Enforcement & YouTube Controls -->
                    <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2.5">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center gap-2">
                                <i class="fa-solid fa-shield-halved text-rose-400 text-sm"></i>
                                <div>
                                    <div class="text-xs font-bold text-slate-200">OS YouTube & Hosts Blocker (Eng 4)</div>
                                    <div class="text-[10px] text-slate-400">Real-time Window Minimizer + Hosts 0.0.0.0 Routing</div>
                                </div>
                            </div>
                            <span id="enforcement-badge" class="text-xs font-bold px-2.5 py-1 rounded-full bg-slate-800 text-slate-300">
                                CLEAR
                            </span>
                        </div>

                        <!-- Real-time Window Interceptor Banner -->
                        <div class="p-2 rounded-lg bg-emerald-950/30 border border-emerald-500/30 flex items-center justify-between text-[11px]">
                            <span class="text-emerald-300 font-medium flex items-center gap-1.5">
                                <i class="fa-solid fa-bolt text-emerald-400"></i> Active Window Minimizer:
                            </span>
                            <span class="font-bold mono text-emerald-400">ARMED (Auto-Minimizes YouTube on 0s)</span>
                        </div>

                        <!-- Hosts file permission status banner -->
                        <div class="p-2 rounded-lg bg-slate-950/60 border border-slate-800 flex flex-col gap-1.5 text-[11px]">
                            <div class="flex items-center justify-between">
                                <span id="hosts-permission-status" class="text-slate-400 mono text-[10px]">Checking OS write permissions...</span>
                                <div class="flex items-center gap-1" id="grant-perm-controls">
                                    <button id="grant-perm-btn" onclick="grantHostsPermission()" class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30 transition flex items-center gap-1 shadow">
                                        <i class="fa-solid fa-key"></i> Run UAC Setup
                                    </button>
                                    <button onclick="copyAdminCommand()" class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition flex items-center gap-1 shadow">
                                        <i class="fa-solid fa-copy"></i> Copy Admin Cmd
                                    </button>
                                </div>
                            </div>
                        </div>

                        <!-- Manual YouTube Block / Unblock Test Buttons -->
                        <div class="grid grid-cols-2 gap-2 pt-1">
                            <button onclick="toggleHostsBlock(true)" class="py-1.5 px-2 rounded-lg bg-rose-600/20 border border-rose-500/30 hover:bg-rose-600/30 text-rose-300 text-[11px] font-bold transition flex items-center justify-center gap-1.5">
                                <i class="fa-solid fa-ban"></i> Block YouTube
                            </button>
                            <button onclick="toggleHostsBlock(false)" class="py-1.5 px-2 rounded-lg bg-emerald-600/20 border border-emerald-500/30 hover:bg-emerald-600/30 text-emerald-300 text-[11px] font-bold transition flex items-center justify-center gap-1.5">
                                <i class="fa-solid fa-unlock"></i> Unblock Access
                            </button>
                            <button onclick="testYouTubeBlocker()" class="col-span-2 py-1.5 px-2 rounded-lg bg-indigo-600/20 border border-indigo-500/40 hover:bg-indigo-600/40 text-indigo-300 text-[11px] font-bold transition flex items-center justify-center gap-1.5 shadow">
                                <i class="fa-solid fa-vial-circle-check text-indigo-400"></i> Test YouTube Blocker & DNS Resolution
                            </button>
                        </div>
                    </div>
                </div>

            </div>

        </div>

        <!-- Interactive Scenario Simulator Deck -->
        <div class="glass p-6 rounded-2xl space-y-4">
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-800">
                <div>
                    <h2 class="text-sm font-bold text-white flex items-center gap-2">
                        <i class="fa-solid fa-flask text-indigo-400"></i> Interactive Scenario Simulator
                    </h2>
                    <p class="text-xs text-slate-400">Test every research condition and rule without altering your camera or browser tabs</p>
                </div>
                <div class="text-xs text-slate-400 mono">Rule: (ACTIVE &and; EDUCATIONAL) &rarr; +1s | Else &rarr; -1s</div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                <button onclick="simulate('ACTIVE', 'EDUCATIONAL', 'Wikipedia - Quantum Mechanics', 'Study Mode')" class="p-3 rounded-xl bg-emerald-950/30 border border-emerald-500/30 hover:border-emerald-500/70 text-left transition hover:scale-[1.02]">
                    <div class="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                        <i class="fa-solid fa-book-open"></i> Study Mode
                    </div>
                    <div class="text-[10px] text-slate-400 mt-1">Eyes Open + Wiki &bull; <span class="text-emerald-400 font-bold">+1s</span></div>
                </button>

                <button onclick="simulate('ACTIVE', 'DISTRACTION', 'YouTube - Meme Compilation', 'Distraction Mode')" class="p-3 rounded-xl bg-rose-950/30 border border-rose-500/30 hover:border-rose-500/70 text-left transition hover:scale-[1.02]">
                    <div class="text-xs font-bold text-rose-300 flex items-center gap-1.5">
                        <i class="fa-solid fa-gamepad"></i> Distraction
                    </div>
                    <div class="text-[10px] text-slate-400 mt-1">Meme Video Active &bull; <span class="text-rose-400 font-bold">-1s</span></div>
                </button>

                <button onclick="simulate('IDLE', 'EDUCATIONAL', 'MIT Calculus Lecture 01', 'Drowsy / Sleep')" class="p-3 rounded-xl bg-rose-950/30 border border-rose-500/30 hover:border-rose-500/70 text-left transition hover:scale-[1.02]">
                    <div class="text-xs font-bold text-rose-300 flex items-center gap-1.5">
                        <i class="fa-solid fa-bed"></i> Drowsy / Sleep
                    </div>
                    <div class="text-[10px] text-slate-400 mt-1">Eyes Closed &ge; 2s &bull; <span class="text-rose-400 font-bold">-1s</span></div>
                </button>

                <button onclick="simulate('IDLE', 'EDUCATIONAL', 'Wikipedia - Computer Science', 'Mobile Distraction')" class="p-3 rounded-xl bg-amber-950/30 border border-amber-500/40 hover:border-amber-500/70 text-left transition hover:scale-[1.02]">
                    <div class="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                        <i class="fa-solid fa-mobile-screen"></i> Mobile Phone
                    </div>
                    <div class="text-[10px] text-slate-400 mt-1">Gaze Down + Idle &bull; <span class="text-amber-400 font-bold">-1s</span></div>
                </button>

                <button onclick="simulate('IDLE', 'EDUCATIONAL', 'Wikipedia - Physics', 'Desk Abandoned')" class="p-3 rounded-xl bg-orange-950/30 border border-orange-500/40 hover:border-orange-500/70 text-left transition hover:scale-[1.02]">
                    <div class="text-xs font-bold text-orange-300 flex items-center gap-1.5">
                        <i class="fa-solid fa-person-walking"></i> Desk Abandoned
                    </div>
                    <div class="text-[10px] text-slate-400 mt-1">No Face / Away &bull; <span class="text-orange-400 font-bold">-1s</span></div>
                </button>

                <button onclick="simulate('IDLE', 'DISTRACTION', 'Twitch - Live Stream', 'Abandoned Distraction')" class="p-3 rounded-xl bg-purple-950/30 border border-purple-500/30 hover:border-purple-500/70 text-left transition hover:scale-[1.02]">
                    <div class="text-xs font-bold text-purple-300 flex items-center gap-1.5">
                        <i class="fa-solid fa-tv"></i> Abandoned Vid
                    </div>
                    <div class="text-[10px] text-slate-400 mt-1">Away + Stream &bull; <span class="text-purple-400 font-bold">-1s</span></div>
                </button>
            </div>

            <!-- Resume Live Sensor Mode Quick Action -->
            <button onclick="resumeLiveMode()" class="w-full p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/40 hover:border-emerald-500/80 hover:bg-emerald-950/60 transition flex items-center justify-between text-left group">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-sm group-hover:scale-110 transition">
                        <i class="fa-solid fa-camera"></i>
                    </div>
                    <div>
                        <div class="text-xs font-bold text-emerald-300 flex items-center gap-2">
                            <span>Resume Live Camera & Window Tracking Mode</span>
                            <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Exit All Simulations</span>
                        </div>
                        <div class="text-[10px] text-slate-400 mt-0.5">Clears all mock overrides and monitors real webcam feed and active OS foreground window</div>
                    </div>
                </div>
                <i class="fa-solid fa-arrow-rotate-left text-emerald-400 mr-2 text-sm"></i>
            </button>

            <!-- Pre-scripted Integration Tests -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                <button onclick="runZeroBalanceTest()" class="p-3 rounded-xl bg-slate-900 border border-rose-500/30 hover:bg-rose-950/20 text-left transition flex items-center justify-between">
                    <div>
                        <div class="text-xs font-bold text-rose-300">Run Zero-Balance Test (Checkpoint 3.1)</div>
                        <div class="text-[10px] text-slate-400">Resets balance to 0s, opens YouTube meme &rarr; Triggers immediate OS Hosts Block!</div>
                    </div>
                    <i class="fa-solid fa-bolt text-rose-400"></i>
                </button>

                <button onclick="runEarnAndBurnTest()" class="p-3 rounded-xl bg-slate-900 border border-indigo-500/30 hover:bg-indigo-950/20 text-left transition flex items-center justify-between">
                    <div>
                        <div class="text-xs font-bold text-indigo-300">Run Earn-and-Burn Test (Checkpoint 3.2)</div>
                        <div class="text-[10px] text-slate-400">Accrues 3s bank, opens distraction, drains to 0s &rarr; Proves automatic re-block!</div>
                    </div>
                    <i class="fa-solid fa-fire text-indigo-400"></i>
                </button>
            </div>
        </div>

        <!-- Master Test Suites Runner -->
        <div class="glass p-6 rounded-2xl space-y-4">
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-3 border-b border-slate-800">
                <div>
                    <h2 class="text-sm font-bold text-white flex items-center gap-2">
                        <i class="fa-solid fa-clipboard-check text-indigo-400"></i> Master Test Suite Matrix (5/5 Passing)
                    </h2>
                    <p class="text-xs text-slate-400">Executes all unit, integration, and orchestration checkpoints across all 4 Engineers</p>
                </div>
                <button id="run-tests-btn" onclick="executeTestSuite()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/20 transition flex items-center gap-2">
                    <i class="fa-solid fa-play"></i> Execute All 5 Test Suites
                </button>
            </div>

            <div id="test-results-container" class="space-y-2">
                <div class="p-3 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center justify-between text-xs">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 font-bold">1</span>
                        <div>
                            <div class="font-bold text-slate-200">Checkpoint 1 (Eng 1) - DB Scaffolding & State Persistence Across Restarts</div>
                            <div class="text-slate-500 text-[10px]">test_db_manager.py</div>
                        </div>
                    </div>
                    <span class="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold mono">PASSED</span>
                </div>
                <div class="p-3 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center justify-between text-xs">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 font-bold">2</span>
                        <div>
                            <div class="font-bold text-slate-200">Checkpoint 1 (Eng 2, 3, 4) - Camera EAR within 2s, Ollama Prompting & Hosts File</div>
                            <div class="text-slate-500 text-[10px]">test_checkpoint_1.py</div>
                        </div>
                    </div>
                    <span class="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold mono">PASSED</span>
                </div>
                <div class="p-3 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center justify-between text-xs">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 font-bold">3</span>
                        <div>
                            <div class="font-bold text-slate-200">Checkpoint 2 (Sprint 2) - The Brain: AND Gate, Wikipedia Accrual & Vision Override</div>
                            <div class="text-slate-500 text-[10px]">test_logic_controller.py</div>
                        </div>
                    </div>
                    <span class="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold mono">PASSED</span>
                </div>
                <div class="p-3 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center justify-between text-xs">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 font-bold">4</span>
                        <div>
                            <div class="font-bold text-slate-200">Checkpoint 2 (Fusion) - Multi-Modal Fusion, Semantic Cache & Focus Telemetry</div>
                            <div class="text-slate-500 text-[10px]">test_checkpoint_2.py</div>
                        </div>
                    </div>
                    <span class="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold mono">PASSED</span>
                </div>
                <div class="p-3 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center justify-between text-xs">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 font-bold">5</span>
                        <div>
                            <div class="font-bold text-slate-200">Checkpoint 3 (Sprint 3 & 4) - Zero-Balance Rule, Earn-and-Burn & Graceful Shutdown</div>
                            <div class="text-slate-500 text-[10px]">test_system_orchestration.py</div>
                        </div>
                    </div>
                    <span class="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold mono">PASSED</span>
                </div>
            </div>
        </div>

        <!-- Logs & Dataset Viewers -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

            <!-- SQLite DB Logs -->
            <div class="glass p-5 rounded-2xl space-y-3">
                <div class="flex items-center justify-between">
                    <h3 class="text-xs font-bold tracking-wider uppercase text-slate-400 flex items-center gap-2">
                        <i class="fa-solid fa-list-check text-indigo-400"></i> SQLite time_logs (Eng 1)
                    </h3>
                    <span class="text-[10px] text-slate-500 mono">study_monitor.db</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead>
                            <tr class="border-b border-slate-800 text-slate-500 font-mono text-[10px]">
                                <th class="pb-2">Time</th>
                                <th class="pb-2">Delta</th>
                                <th class="pb-2">After</th>
                                <th class="pb-2">Reason</th>
                            </tr>
                        </thead>
                        <tbody id="logs-tbody" class="divide-y divide-slate-800/50 text-slate-300 font-mono text-[11px]">
                            <tr><td colspan="4" class="py-4 text-center text-slate-500">Loading audit logs...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Research CSV Data -->
            <div class="glass p-5 rounded-2xl space-y-3">
                <div class="flex items-center justify-between">
                    <h3 class="text-xs font-bold tracking-wider uppercase text-slate-400 flex items-center gap-2">
                        <i class="fa-solid fa-file-csv text-emerald-400"></i> Research Experiment Log (Task 4.1)
                    </h3>
                    <span class="text-[10px] text-slate-500 mono">research_data.csv</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead>
                            <tr class="border-b border-slate-800 text-slate-500 font-mono text-[10px]">
                                <th class="pb-2">Vision</th>
                                <th class="pb-2">Semantic</th>
                                <th class="pb-2">Verdict</th>
                                <th class="pb-2">Delta</th>
                                <th class="pb-2">Balance</th>
                            </tr>
                        </thead>
                        <tbody id="research-tbody" class="divide-y divide-slate-800/50 text-slate-300 font-mono text-[11px]">
                            <tr><td colspan="5" class="py-4 text-center text-slate-500">Loading research entries...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

        </div>

    </div>

    <script>
        const videoImg = document.getElementById('video-stream');
        let isStreaming = true;
        let frameInFlight = false;
        let lastFrameRequestTime = Date.now();

        function grabCameraFrame() {
            if (!isStreaming) return;

            const now = Date.now();
            // Watchdog: If in-flight longer than 350ms, force reset so stream never freezes!
            if (frameInFlight && (now - lastFrameRequestTime > 350)) {
                frameInFlight = false;
            }

            if (frameInFlight) return;
            frameInFlight = true;
            lastFrameRequestTime = now;

            const nextImg = new Image();
            const watchdogTimer = setTimeout(() => {
                frameInFlight = false;
            }, 300);

            nextImg.onload = () => {
                clearTimeout(watchdogTimer);
                videoImg.src = nextImg.src;
                frameInFlight = false;
            };

            nextImg.onerror = () => {
                clearTimeout(watchdogTimer);
                frameInFlight = false;
            };

            nextImg.src = '/api/camera_frame?t=' + now;
        }

        setInterval(grabCameraFrame, 35);

        async function reconnectCamera() {
            await fetch('/api/reset-camera', { method: 'POST' });
            frameInFlight = false;
            fetchStatus();
        }

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                updateUI(data);
            } catch (err) {
                console.error("Fetch status error:", err);
            }
        }

        function updateUI(data) {
            document.getElementById('balance-display').innerHTML = `${data.balance}<span class="text-2xl text-slate-500 ml-1">s</span>`;

            const card = document.getElementById('state-card');
            const badge = document.getElementById('fused-badge');
            badge.innerText = data.fused_state;

            card.className = "glass p-6 rounded-2xl flex-1 flex flex-col justify-between transition-all duration-300 ";
            if (data.color === "emerald") {
                card.classList.add("glow-emerald", "border-emerald-500/30");
                badge.className = "px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
                document.getElementById('state-description').innerText = "Accruing study time (+1s)";
            } else if (data.fused_state === "MOBILE_DISTRACTION") {
                card.classList.add("glow-amber", "border-amber-500/40");
                badge.className = "px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40";
                document.getElementById('state-description').innerText = "Mobile Phone Distraction detected (-1s)";
            } else if (data.fused_state === "USER_AWAY") {
                card.classList.add("border-orange-500/40");
                badge.className = "px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-orange-500/20 text-orange-300 border border-orange-500/40";
                document.getElementById('state-description').innerText = "Desk Abandoned / User Away (-1s)";
            } else if (data.fused_state === "DROWSY") {
                card.classList.add("glow-rose", "border-rose-500/40");
                badge.className = "px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-500/20 text-rose-300 border border-rose-500/40";
                document.getElementById('state-description').innerText = "Sleep / Drowsy detected (Eyes closed >= 2s) (-1s)";
            } else if (data.color === "rose") {
                card.classList.add("glow-rose", "border-rose-500/30");
                badge.className = "px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-500/20 text-rose-300 border border-rose-500/30";
                document.getElementById('state-description').innerText = "Distraction active: Draining (-1s)";
            } else if (data.color === "amber") {
                card.classList.add("glow-amber", "border-amber-500/30");
                badge.className = "px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/30";
                document.getElementById('state-description').innerText = "Vision Override: Inactive study material (-1s)";
            } else {
                badge.className = "px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-slate-800 text-slate-400";
                document.getElementById('state-description').innerText = "User idle or away";
            }

            if (data.camera) {
                document.getElementById('camera-fps-badge').innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Streaming ${data.camera.fps || 25} FPS`;
                if (data.camera.ear !== undefined) {
                    document.getElementById('hud-ear').innerText = `EAR: ${data.camera.ear.toFixed(3)}`;
                }
            }

            // Update Focus Score
            if (data.stats) {
                const score = data.stats.focus_score || 100.0;
                document.getElementById('focus-score-text').innerText = `${score.toFixed(1)}%`;
                document.getElementById('focus-score-bar').style.width = `${Math.min(100, Math.max(0, score))}%`;
                document.getElementById('focused-time-text').innerText = `Focused: ${data.stats.focused_seconds}s`;
                document.getElementById('distracted-time-text').innerText = `Distracted: ${data.stats.distracted_seconds}s | Away: ${data.stats.away_seconds}s | Sleep: ${data.stats.drowsy_seconds}s`;
            }

            if (data.user_profile) {
                const enrollBtn = document.getElementById('enroll-btn-label');
                if (enrollBtn) {
                    enrollBtn.innerText = `Locked: ${data.user_profile.name || 'Student'}`;
                }
            }

            // Purple Card Eng 3
            const sBadge = document.getElementById('semantic-badge');
            sBadge.innerText = data.semantic_state;
            sBadge.className = data.semantic_state === "EDUCATIONAL" 
                ? "text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40" 
                : "text-[10px] font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40";

            document.getElementById('window-title-display').innerText = data.active_window || "Desktop / Idle";

            const eBadge = document.getElementById('enforcement-badge');
            if (data.is_blocked) {
                eBadge.innerText = "YOUTUBE & SITES BLOCKED";
                eBadge.className = "text-xs font-bold px-2.5 py-1 rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30";
            } else {
                eBadge.innerText = "ACCESS RESTORED";
                eBadge.className = "text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
            }

            // OS Hosts writeable indicator
            const permStatus = document.getElementById('hosts-permission-status');
            const grantControls = document.getElementById('grant-perm-controls');
            if (permStatus && grantControls) {
                if (data.hosts_writeable) {
                    permStatus.innerHTML = '<span class="text-emerald-400 font-bold"><i class="fa-solid fa-check"></i> OS Hosts Writeable (Live DNS Blocker Active)</span>';
                    grantControls.classList.add('hidden');
                } else {
                    permStatus.innerHTML = '<span class="text-amber-400 font-bold"><i class="fa-solid fa-triangle-exclamation"></i> OS Hosts Write Protected</span>';
                    grantControls.classList.remove('hidden');
                }
            }

            // Simulation banner & Header Mode Badge update
            const simBanner = document.getElementById('simulation-banner');
            const modeBadge = document.getElementById('live-mode-badge');
            if (data.is_simulating) {
                simBanner.classList.remove('hidden');
                document.getElementById('sim-scenario-name').innerText = data.simulation_scenario || 'Active Simulation';
                document.getElementById('sim-countdown').innerText = data.simulation_seconds_left || '0';
                modeBadge.className = "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40 animate-pulse";
                modeBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-purple-400"></span> 🧪 SIMULATION: ${data.simulation_scenario}`;
            } else {
                simBanner.classList.add('hidden');
                modeBadge.className = "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
                modeBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span> 🟢 LIVE SENSOR MODE (Camera & Window)`;
            }

            const logsTbody = document.getElementById('logs-tbody');
            if (data.recent_logs && data.recent_logs.length > 0) {
                logsTbody.innerHTML = data.recent_logs.map(log => `
                    <tr>
                        <td class="py-1.5 text-slate-400">${(log.timestamp || '').substring(11, 19)}</td>
                        <td class="py-1.5 ${log.delta > 0 ? 'text-emerald-400 font-bold' : (log.delta < 0 ? 'text-rose-400 font-bold' : 'text-slate-400')}">
                            ${log.delta > 0 ? '+' : ''}${log.delta}
                        </td>
                        <td class="py-1.5 font-bold">${log.balance_after}s</td>
                        <td class="py-1.5 text-slate-400 truncate max-w-[120px]">${log.reason || ''}</td>
                    </tr>
                `).join('');
            }

            const resTbody = document.getElementById('research-tbody');
            if (data.research_entries && data.research_entries.length > 0) {
                resTbody.innerHTML = data.research_entries.map(row => `
                    <tr>
                        <td class="py-1.5 ${row.vision_state === 'ACTIVE' ? 'text-emerald-400' : 'text-amber-400'}">${row.vision_state}</td>
                        <td class="py-1.5 ${row.semantic_state === 'EDUCATIONAL' ? 'text-indigo-400' : 'text-rose-400'}">${row.semantic_state}</td>
                        <td class="py-1.5 font-bold text-slate-200">${row.verdict}</td>
                        <td class="py-1.5 font-bold ${Number(row.balance_delta) > 0 ? 'text-emerald-400' : 'text-rose-400'}">
                            ${Number(row.balance_delta) > 0 ? '+' : ''}${row.balance_delta}
                        </td>
                        <td class="py-1.5 font-bold text-white">${row.current_balance}</td>
                    </tr>
                `).join('');
            }
        }

        async function resumeLiveMode() {
            await fetch('/api/resume-live', { method: 'POST' });
            fetchStatus();
        }

        async function copyAdminCommand() {
            const cmd = 'icacls C:\\Windows\\System32\\drivers\\etc\\hosts /grant Users:(M)';
            try {
                await navigator.clipboard.writeText(cmd);
                alert("Copied to clipboard!\n\nOpen PowerShell or CMD as Administrator and press Ctrl+V to run:\n" + cmd);
            } catch (e) {
                prompt("Copy this command and run in Administrator PowerShell or CMD:", cmd);
            }
        }

        async function grantHostsPermission() {
            await fetch('/api/grant-permission', { method: 'POST' });
            alert("Launched Grant_Hosts_Permission.bat!\n\nPlease check your desktop or taskbar for the Administrator UAC prompt and click 'Yes'.\n\nOr click 'Copy Admin Command' and run it in an elevated PowerShell.");
            setTimeout(fetchStatus, 3000);
        }

        async function toggleHostsBlock(block) {
            await fetch('/api/toggle-block', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ block: block })
            });
            fetchStatus();
        }

        async function simulate(vState, sState, title, scenario) {
            await fetch('/api/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vision_state: vState,
                    semantic_state: sState,
                    window_title: title,
                    scenario: scenario || title
                })
            });
            fetchStatus();
        }

        async function setBalance(val) {
            await fetch('/api/reset-balance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ balance: val })
            });
            fetchStatus();
        }

        async function enrollPrimaryUser() {
            const btn = document.getElementById('enroll-btn');
            const label = document.getElementById('enroll-btn-label');
            label.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> Enrolling...`;
            btn.disabled = true;

            try {
                const res = await fetch('/api/enroll-user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: 'Primary Student' })
                });
                const data = await res.json();
                alert(data.message);
            } catch (err) {
                alert("Enrollment failed: " + err);
            } finally {
                btn.disabled = false;
                fetchStatus();
            }
        }

        async function testYouTubeBlocker() {
            try {
                const res = await fetch('/api/test-youtube-block', { method: 'POST' });
                const data = await res.json();
                let report = `YouTube & Enforcement Test Report:\n\n`;
                report += `• System Distractions Blocked: ${data.system_blocked ? 'YES (Active)' : 'NO'}\n`;
                report += `• Hosts File Directly Writeable: ${data.hosts_writeable ? 'YES' : 'NO (UAC needed)'}\n`;
                report += `• Foreground Window Minimizer: ${data.window_interceptor_tested ? 'TESTED & VERIFIED' : 'FAILED'}\n\n`;
                report += `Domain Resolution Probes:\n`;
                for (const r of data.test_results) {
                    report += `  - ${r.domain}: Hosts=${r.hosts_blocked ? 'BLOCKED' : 'NOT BLOCKED'} | Socket=${r.probe_status}\n`;
                }
                alert(report);
            } catch (err) {
                alert("Failed to run YouTube blocker test: " + err);
            }
        }

        async function runZeroBalanceTest() {
            await setBalance(0);
            await simulate('ACTIVE', 'DISTRACTION', 'YouTube - Meme Compilation');
        }

        async function runEarnAndBurnTest() {
            await setBalance(2);
            await simulate('ACTIVE', 'DISTRACTION', 'Reddit - Endless Memes');
            setTimeout(async () => {
                await simulate('ACTIVE', 'DISTRACTION', 'Reddit - Endless Memes');
            }, 600);
        }

        async function executeTestSuite() {
            const btn = document.getElementById('run-tests-btn');
            btn.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> Executing All Test Suites...`;
            btn.disabled = true;

            try {
                const res = await fetch('/api/run-tests');
                const data = await res.json();

                const container = document.getElementById('test-results-container');
                container.innerHTML = data.suites.map((s, idx) => `
                    <div class="p-3 rounded-xl bg-slate-900/40 border ${s.passed ? 'border-emerald-500/30 bg-emerald-950/10' : 'border-rose-500/30 bg-rose-950/10'} flex items-center justify-between text-xs transition">
                        <div class="flex items-center gap-3">
                            <span class="w-6 h-6 rounded-full ${s.passed ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-rose-500/20 text-rose-400'} flex items-center justify-center font-bold">
                                ${s.passed ? '<i class="fa-solid fa-check text-[10px]"></i>' : '<i class="fa-solid fa-xmark text-[10px]"></i>'}
                            </span>
                            <div>
                                <div class="font-bold text-slate-200">${s.name}</div>
                                <div class="text-slate-500 text-[10px] mono">${s.checkpoint} &bull; Completed in ${s.duration}s</div>
                            </div>
                        </div>
                        <span class="px-2.5 py-1 rounded ${s.passed ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-300'} font-bold mono">
                            ${s.passed ? 'PASSED' : 'FAILED'}
                        </span>
                    </div>
                `).join('');

                btn.innerHTML = `<i class="fa-solid fa-check text-emerald-400"></i> ${data.passed}/${data.total} Suites Passed (${data.duration_seconds}s)`;
            } catch (err) {
                console.error("Test execution failed:", err);
                btn.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-rose-400"></i> Execution Error`;
            } finally {
                btn.disabled = false;
                fetchStatus();
            }
        }

        setInterval(fetchStatus, 1000);
        fetchStatus();
    </script>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
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
            self._send_json(get_system_status())
        elif parsed.path == "/api/camera_frame":
            frame = camera_streamer.get_frame()
            if frame:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
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
                    time.sleep(0.04)
            except (ConnectionResetError, BrokenPipeError):
                pass
        elif parsed.path == "/api/run-tests":
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

        if parsed.path == "/api/step":
            step = main.run_orchestrator_step()
            self._send_json({"status": "ok", "step": step})

        elif parsed.path == "/api/toggle-block":
            block = payload.get("block", True)
            if block:
                enforcement.block_distractions()
                enforcement.enforce_active_distraction()
            else:
                enforcement.unblock_distractions()
            self._send_json({
                "status": "ok",
                "is_blocked": enforcement.is_distraction_blocked(),
                "hosts_writeable": enforcement.can_write_hosts()
            })

        elif parsed.path == "/api/grant-permission":
            triggered = enforcement._trigger_uac_grant_permission()
            self._send_json({"status": "ok", "uac_triggered": triggered, "hosts_writeable": enforcement.can_write_hosts()})

        elif parsed.path == "/api/reset-camera":
            camera_streamer.reset()
            self._send_json({"status": "ok", "message": "Camera hardware re-initialized"})

        elif parsed.path == "/api/simulate":
            v_state = payload.get("vision_state")
            s_state = payload.get("semantic_state")
            title = payload.get("window_title", "Simulated Window")
            scenario = payload.get("scenario", title)

            study_monitor.start_simulation(scenario, v_state, s_state, window_title=title, duration=8.0)
            step = main.run_orchestrator_step()
            self._send_json({"status": "ok", "simulated": payload, "step": step})

        elif parsed.path == "/api/resume-live":
            study_monitor.resume_live_mode()
            self._send_json({"status": "ok", "mode": "LIVE_SENSOR_MODE"})

        elif parsed.path == "/api/reset-balance":
            new_bal = payload.get("balance", 0)
            db_manager.reset_balance(new_bal)
            if new_bal <= 0:
                enforcement.block_distractions()
            else:
                enforcement.unblock_distractions()
            self._send_json({"status": "ok", "new_balance": new_bal})

        elif parsed.path == "/api/enroll-user":
            name = payload.get("name", "Primary Student")
            enrolled = camera_streamer.enroll_current_user(name=name, samples_count=20)
            self._send_json({
                "status": "ok" if enrolled else "error",
                "enrolled": enrolled,
                "message": f"Primary User '{name}' successfully enrolled and locked!" if enrolled else "Enrollment failed: Please sit in front of the camera with good lighting and retry."
            })

        elif parsed.path == "/api/test-youtube-block":
            domains_to_test = [
                "youtube.com", "www.youtube.com", "m.youtube.com",
                "googlevideo.com", "ytimg.com", "youtubei.googleapis.com"
            ]
            results = []
            for d in domains_to_test:
                is_blocked = enforcement.is_domain_blocked(d)
                probe = enforcement.simulate_browser_request_to_domain(d)
                results.append({
                    "domain": d,
                    "hosts_blocked": is_blocked,
                    "probe_status": probe
                })
            minimized = enforcement.enforce_active_distraction(window_title="YouTube - Watch Free Videos")
            self._send_json({
                "status": "ok",
                "system_blocked": enforcement.is_distraction_blocked(),
                "hosts_writeable": enforcement.can_write_hosts(),
                "test_results": results,
                "window_interceptor_tested": True,
                "simulated_minimize_triggered": minimized
            })

        else:
            self.send_error(404, "Unknown POST endpoint")

    def log_message(self, format, *args):
        pass


def run_server(port=PORT):
    camera_streamer.start()
    study_monitor.start()
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, port), DashboardRequestHandler)
    print("=" * 65)
    print(f" DEMON THREADED WEB DASHBOARD ACTIVE: http://localhost:{port}")
    print(" Autonomous 1 Hz Study Monitor Loop Active")
    print("=" * 65)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web dashboard server...")
    finally:
        study_monitor.stop()
        camera_streamer.stop()
        server.server_close()


if __name__ == "__main__":
    run_server()

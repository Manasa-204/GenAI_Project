"""
vision_pipeline.py - Computer Vision & Anthropometric Kinematics Engine
Responsible for:
- Spatial Focus Region reticle filtering (20%-80% X, 15%-85% Y)
- Real-time EAR, 3D Head Pose, and 8-state posture tracking
- Continuous 10-Second Composite Focus Quality Score (Eye + Head + Activity + Foreground Process)
- Semantic Color classification (Emerald Green >= 70%, Amber Yellow 40-69%, Rose Red < 40%)
"""

import sys
import time
import math
from typing import Dict, Any, Optional, List, Tuple
from collections import deque
import numpy as np
import cv2
import mediapipe as mp

from user_tracker import get_user_tracker, is_in_focus_region, FOCUS_REGION
import db_manager


# Landmark indices for MediaPipe Face Mesh (468/478 landmarks)
LEFT_EYE_LANDMARKS = {
    "lateral": 362,   # Outer corner
    "medial": 263,    # Inner corner
    "top_outer": 385,
    "top_inner": 387,
    "bottom_outer": 380,
    "bottom_inner": 373,
}

RIGHT_EYE_LANDMARKS = {
    "lateral": 33,    # Outer corner
    "medial": 133,    # Inner corner
    "top_outer": 160,
    "top_inner": 158,
    "bottom_outer": 144,
    "bottom_inner": 153,
}

# 3D Generic Anthropometric Head Model Points (in mm)
HEAD_MODEL_POINTS_3D = np.array([
    [0.0, 0.0, 0.0],          # Nose tip (Landmark 1)
    [0.0, 330.0, -65.0],      # Chin (Landmark 152)
    [-225.0, -170.0, -135.0], # Left eye corner (Landmark 33)
    [225.0, -170.0, -135.0],  # Right eye corner (Landmark 263)
    [-150.0, 150.0, -125.0],  # Left mouth corner (Landmark 61)
    [150.0, 150.0, -125.0],   # Right mouth corner (Landmark 291)
], dtype=np.float64)

POSE_LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]

# 8 Posture States (Checkpoint 4)
POSTURE_STATES = [
    "DIRECT_FOCUS",        # Seated centered, facing screen squarely
    "PASSIVE_READING",     # Reading screen attentively, minimal movement
    "DESK_NOTE_TAKING",    # Head pitched downward (-15°..-30°), hands/typing active
    "DROWSY_MICROSLEEP",   # Eyes closed >= 2.0s or drooping
    "LOOKING_AWAY",        # Head turned sideways (|yaw| > 25°) or up
    "MOBILE_DISTRACTION",  # Head pitched down with zero PC activity
    "PERIPHERAL_UNFOCUSED",# Face outside the 20%-80% focus region
    "USER_AWAY"            # Desk abandoned / no face in frame
]


def get_system_idle_time() -> float:
    """Returns elapsed seconds since last keyboard or mouse input on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                return max(0.0, millis / 1000.0)
        except Exception:
            pass
    return 0.0


def calculate_landmark_distance(pt1, pt2):
    """Euclidean distance between two landmarks (x, y)."""
    return math.hypot(pt1[0] - pt2[0], pt1[1] - pt2[1])


def calculate_ear(eye_landmarks):
    """
    Calculate Eye Aspect Ratio (EAR) given a dict or list of 6 landmark coordinates:
    EAR = (||p2 - p6|| + ||p3 - p5||) / (2.0 * ||p1 - p4||)
    """
    if isinstance(eye_landmarks, dict):
        p1 = eye_landmarks["lateral"]
        p4 = eye_landmarks["medial"]
        p2 = eye_landmarks["top_outer"]
        p6 = eye_landmarks["bottom_outer"]
        p3 = eye_landmarks["top_inner"]
        p5 = eye_landmarks["bottom_inner"]
    elif len(eye_landmarks) == 6:
        p1, p2, p3, p4, p5, p6 = eye_landmarks
    else:
        raise ValueError("eye_landmarks must be a dict with keys or 6 coordinate pairs.")

    vertical_dist1 = calculate_landmark_distance(p2, p6)
    vertical_dist2 = calculate_landmark_distance(p3, p5)
    horizontal_dist = calculate_landmark_distance(p1, p4)

    if horizontal_dist <= 1e-6:
        return 0.0

    return (vertical_dist1 + vertical_dist2) / (2.0 * horizontal_dist)


def estimate_head_pose(landmarks_2d, frame_shape):
    """
    Estimates 3D head rotation angles (Pitch, Yaw, Roll) via cv2.solvePnP.
    Returns (pitch, yaw, roll) in degrees.
    """
    height, width = frame_shape[:2]
    focal_length = width
    center = (width / 2.0, height / 2.0)
    camera_matrix = np.array([
        [focal_length, 0.0, center[0]],
        [0.0, focal_length, center[1]],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)

    dist_coeffs = np.zeros((4, 1), dtype=np.float64)
    image_points = np.array(landmarks_2d, dtype=np.float64)

    success, rotation_vector, translation_vector = cv2.solvePnP(
        HEAD_MODEL_POINTS_3D,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE
    )

    if not success:
        return 0.0, 0.0, 0.0

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    sy = math.sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        x = math.atan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
        y = math.atan2(-rotation_matrix[2, 0], sy)
        z = math.atan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
    else:
        x = math.atan2(-rotation_matrix[1, 2], rotation_matrix[1, 1])
        y = math.atan2(-rotation_matrix[2, 0], sy)
        z = 0.0

    pitch = math.degrees(x)
    yaw = math.degrees(y)
    roll = math.degrees(z)
    return pitch, yaw, roll


# =========================================================================
# Checkpoint 4: Continuous 10-Second Composite Focus Quality Evaluator
# =========================================================================

class CompositeFocusEvaluator:
    """
    Continuously aggregates:
    1. Eye movements & openness (EAR, blink dynamics, micro-sleep) -> 30%
    2. Head posture (Pitch, Yaw, 8-state posture classification)    -> 25%
    3. User interaction activity (PC idle time, keystrokes)        -> 15%
    4. Active foreground process (Educational vs Distraction)      -> 30%

    Calculates a dynamic 10-second composite focus score with EMA smoothing.
    Classifies color signals:
    - >= 70%: Emerald Green (Focused / Deep Flow)
    - 40% - 69%: Amber Yellow (Focus Drifting / Drowsy)
    - < 40%: Rose Red (Distracted / Alert)
    """

    def __init__(self, window_seconds: float = 10.0, ema_alpha: float = 0.5):
        self.window_seconds = window_seconds
        self.ema_alpha = ema_alpha
        self.samples = deque()  # stores (timestamp, instant_score, posture, color)
        self.smoothed_score = 85.0
        self.last_10s_eval_time = time.time()
        self.current_posture = "DIRECT_FOCUS"
        self.current_color = "emerald"
        self.current_classification = "FOCUSED"

    def record_sample(
        self,
        ear: float,
        is_eyes_closed: bool,
        sleep_duration: float,
        pitch: float,
        yaw: float,
        posture_state: str,
        foreground_category: str = "Educational",
        current_time: Optional[float] = None
    ) -> float:
        now = current_time or time.time()

        # 1. Eye Score (30%)
        if sleep_duration >= 2.0:
            eye_score = 0.0  # True microsleep/drowsy
        elif is_eyes_closed:
            eye_score = 50.0  # Prolonged blink / droop
        elif ear >= 0.23:
            eye_score = 100.0  # Attentive open eyes
        elif ear >= 0.18:
            eye_score = 85.0   # Normal gaze
        else:
            eye_score = 30.0

        # 2. Head Posture Score (25%)
        if posture_state == "DIRECT_FOCUS":
            head_score = 100.0
        elif posture_state == "PASSIVE_READING":
            head_score = 95.0
        elif posture_state == "DESK_NOTE_TAKING":
            head_score = 88.0
        elif posture_state == "PERIPHERAL_UNFOCUSED":
            head_score = 30.0
        elif posture_state in ("LOOKING_AWAY", "MOBILE_DISTRACTION"):
            head_score = 15.0
        elif posture_state in ("DROWSY_MICROSLEEP", "USER_AWAY"):
            head_score = 0.0
        else:
            head_score = 50.0

        # 3. User Activity Score (15%)
        idle_sec = get_system_idle_time()
        if idle_sec < 5.0:
            activity_score = 100.0
        elif idle_sec < 25.0:
            activity_score = 85.0
        elif idle_sec < 60.0:
            activity_score = 65.0
        else:
            activity_score = 40.0

        # 4. Foreground Process Score (30%)
        cat_lower = foreground_category.lower()
        if "edu" in cat_lower or "code" in cat_lower or "study" in cat_lower:
            process_score = 100.0
        elif "leisure" in cat_lower:
            process_score = 75.0  # Allowed quota
        elif "distraction" in cat_lower:
            process_score = 0.0   # Blocked distraction active
        else:
            process_score = 70.0  # Neutral system tool

        # Instantaneous weighted score
        instant_score = (
            0.30 * eye_score +
            0.25 * head_score +
            0.15 * activity_score +
            0.30 * process_score
        )
        instant_score = float(np.clip(instant_score, 0.0, 100.0))

        # Add to rolling sample window
        self.samples.append((now, instant_score))

        # Evict samples older than window_seconds (10s)
        cutoff = now - self.window_seconds
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

        # Compute 10-second window average
        if self.samples:
            window_avg = sum(s[1] for s in self.samples) / len(self.samples)
        else:
            window_avg = instant_score

        # Apply Exponential Moving Average (EMA)
        self.smoothed_score = (
            self.ema_alpha * window_avg +
            (1.0 - self.ema_alpha) * self.smoothed_score
        )
        self.smoothed_score = float(np.clip(self.smoothed_score, 0.0, 100.0))

        # Update classification & color signal
        self.current_posture = posture_state
        if self.smoothed_score >= 70.0:
            self.current_classification = "FOCUSED"
            self.current_color = "emerald"  # #10b981
        elif self.smoothed_score >= 40.0:
            self.current_classification = "FOCUS_DRIFTING"
            self.current_color = "amber"    # #f59e0b
        else:
            self.current_classification = "DISTRACTED"
            self.current_color = "rose"     # #f43f5e

        # Log focus telemetry periodically (every 5-10s)
        if now - self.last_10s_eval_time >= 5.0:
            self.last_10s_eval_time = now
            try:
                db_manager.log_focus_telemetry(
                    composite_score=round(self.smoothed_score, 1),
                    posture_state=self.current_posture,
                    fused_state=self.current_classification,
                    color_signal=self.current_color,
                    foreground_app=foreground_category
                )
            except Exception:
                pass

        return self.smoothed_score

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "focus_score": round(self.smoothed_score, 1),
            "classification": self.current_classification,
            "color": self.current_color,
            "posture": self.current_posture,
            "is_focused": self.smoothed_score >= 70.0
        }


# =========================================================================
# Vision Pipeline Class
# =========================================================================

class VisionPipeline:
    """
    Main Computer Vision Pipeline integrating face mesh, 8-state posture,
    spatial focus region, and continuous composite focus evaluation.
    """

    def __init__(
        self,
        camera_index: int = 0,
        ear_threshold: float = 0.18,
        sleep_duration_threshold: float = 2.0,
        away_duration_threshold: float = 2.0,
        yaw_threshold: float = 28.0,
        pitch_threshold: float = 25.0,
        mobile_pitch_threshold: float = -14.0,
        mobile_duration_threshold: float = 2.0
    ):
        self.camera_index = camera_index
        self.ear_threshold = ear_threshold
        self.sleep_duration_threshold = sleep_duration_threshold
        self.away_duration_threshold = away_duration_threshold
        self.yaw_threshold = yaw_threshold
        self.pitch_threshold = pitch_threshold
        self.mobile_pitch_threshold = mobile_pitch_threshold
        self.mobile_duration_threshold = mobile_duration_threshold

        self.cap = None
        self._last_cap_attempt = 0.0

        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=4,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        self.user_tracker = get_user_tracker()
        self.focus_evaluator = CompositeFocusEvaluator(window_seconds=10.0)

        # Temporal Timers
        self.closed_eye_start_time = None
        self.away_start_time = None
        self.mobile_start_time = None
        self.last_state = "ACTIVE"
        self.last_posture = "DIRECT_FOCUS"

    def reset_timers(self):
        """Reset state tracking timers."""
        self.closed_eye_start_time = None
        self.away_start_time = None
        self.mobile_start_time = None
        self.last_state = "ACTIVE"
        self.last_posture = "DIRECT_FOCUS"

    def _get_camera_frame(self):
        # 1. Check if SQLite has fresh focus telemetry (meaning web_dashboard is actively streaming the camera)
        try:
            latest = db_manager.get_latest_focus_telemetry(max_age_seconds=3.0)
            if latest is not None:
                return None
        except Exception:
            pass

        now = time.time()
        if self.cap is None or not self.cap.isOpened():
            if now - self._last_cap_attempt < 3.0:
                return None
            self._last_cap_attempt = now
            if sys.platform == "win32":
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            else:
                self.cap = cv2.VideoCapture(self.camera_index)
            if self.cap and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        return frame if ret and frame is not None else None

    def process_frame(self, frame, current_time=None, foreground_category="Educational"):
        if current_time is None:
            current_time = time.time()

        if frame is None:
            if self.away_start_time is None:
                self.away_start_time = current_time
            away_duration = current_time - self.away_start_time
            state = "IDLE" if away_duration >= self.away_duration_threshold else "ACTIVE"
            score = self.focus_evaluator.record_sample(
                ear=0.0, is_eyes_closed=False, sleep_duration=0.0,
                pitch=0.0, yaw=0.0, posture_state="USER_AWAY",
                foreground_category=foreground_category, current_time=current_time
            )
            return {
                "state": state,
                "sub_state": "ABANDONED",
                "posture": "USER_AWAY",
                "focus_score": score,
                "color": self.focus_evaluator.current_color,
                "face_detected": False,
                "primary_locked": False,
                "in_focus_region": False,
                "ear": 0.0,
                "eyes_closed": False,
                "is_drowsy": False,
                "is_away": True,
                "head_pose": (0.0, 0.0, 0.0),
                "looking_away": True,
                "sleep_duration": 0.0,
                "away_duration": away_duration,
                "background_faces_count": 0
            }

        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)

        if not results.multi_face_landmarks:
            if self.away_start_time is None:
                self.away_start_time = current_time
            self.closed_eye_start_time = None
            away_duration = current_time - self.away_start_time
            state = "IDLE" if away_duration >= self.away_duration_threshold else "ACTIVE"
            score = self.focus_evaluator.record_sample(
                ear=0.0, is_eyes_closed=False, sleep_duration=0.0,
                pitch=0.0, yaw=0.0, posture_state="USER_AWAY",
                foreground_category=foreground_category, current_time=current_time
            )
            return {
                "state": state,
                "sub_state": "ABANDONED",
                "posture": "USER_AWAY",
                "focus_score": score,
                "color": self.focus_evaluator.current_color,
                "face_detected": False,
                "primary_locked": False,
                "in_focus_region": False,
                "ear": 0.0,
                "eyes_closed": False,
                "is_drowsy": False,
                "is_away": True,
                "head_pose": (0.0, 0.0, 0.0),
                "looking_away": True,
                "sleep_duration": 0.0,
                "away_duration": away_duration,
                "background_faces_count": 0
            }

        primary_lm, primary_box, background_boxes = self.user_tracker.find_primary_user(
            results.multi_face_landmarks, (height, width)
        )

        if primary_lm is None:
            # Only background/peripheral faces detected
            if self.away_start_time is None:
                self.away_start_time = current_time
            self.closed_eye_start_time = None
            away_duration = current_time - self.away_start_time
            state = "IDLE" if away_duration >= self.away_duration_threshold else "ACTIVE"
            score = self.focus_evaluator.record_sample(
                ear=0.0, is_eyes_closed=False, sleep_duration=0.0,
                pitch=0.0, yaw=0.0, posture_state="PERIPHERAL_UNFOCUSED",
                foreground_category=foreground_category, current_time=current_time
            )
            return {
                "state": state,
                "sub_state": "ABANDONED",
                "posture": "PERIPHERAL_UNFOCUSED",
                "focus_score": score,
                "color": self.focus_evaluator.current_color,
                "face_detected": False,
                "primary_locked": False,
                "in_focus_region": False,
                "ear": 0.0,
                "eyes_closed": False,
                "is_drowsy": False,
                "is_away": True,
                "head_pose": (0.0, 0.0, 0.0),
                "looking_away": True,
                "sleep_duration": 0.0,
                "away_duration": away_duration,
                "background_faces_count": len(background_boxes),
                "background_boxes": background_boxes
            }

        # Checkpoint 3: Spatial Focus Region verification
        in_reticle = is_in_focus_region(primary_box)

        landmarks = primary_lm.landmark

        # 1. EAR Calculation
        left_eye_pts = {
            k: (landmarks[idx].x * width, landmarks[idx].y * height)
            for k, idx in LEFT_EYE_LANDMARKS.items()
        }
        right_eye_pts = {
            k: (landmarks[idx].x * width, landmarks[idx].y * height)
            for k, idx in RIGHT_EYE_LANDMARKS.items()
        }
        left_ear = calculate_ear(left_eye_pts)
        right_ear = calculate_ear(right_eye_pts)
        avg_ear = (left_ear + right_ear) / 2.0
        eyes_closed = avg_ear < self.ear_threshold

        # 2. Head Pose Calculation
        pose_pts = [
            (landmarks[idx].x * width, landmarks[idx].y * height)
            for idx in POSE_LANDMARK_INDICES
        ]
        pitch, yaw, roll = estimate_head_pose(pose_pts, (height, width))
        looking_away = (abs(yaw) > self.yaw_threshold) or (pitch > self.pitch_threshold)

        # 3. Timers
        sleep_duration = 0.0
        if eyes_closed:
            if self.closed_eye_start_time is None:
                self.closed_eye_start_time = current_time
            sleep_duration = current_time - self.closed_eye_start_time
        else:
            self.closed_eye_start_time = None

        away_duration = 0.0
        if looking_away:
            if self.away_start_time is None:
                self.away_start_time = current_time
            away_duration = current_time - self.away_start_time
        else:
            self.away_start_time = None

        pc_idle_sec = get_system_idle_time()
        is_looking_down = (pitch <= self.mobile_pitch_threshold)
        mobile_distracted_inst = is_looking_down and (pc_idle_sec >= 2.5)

        mobile_duration = 0.0
        if mobile_distracted_inst:
            if self.mobile_start_time is None:
                self.mobile_start_time = current_time
            mobile_duration = current_time - self.mobile_start_time
        else:
            self.mobile_start_time = None

        is_using_mobile = (self.mobile_start_time is not None) and (mobile_duration >= self.mobile_duration_threshold)
        is_sleeping = (self.closed_eye_start_time is not None) and (sleep_duration >= self.sleep_duration_threshold)
        is_away = (self.away_start_time is not None) and (away_duration >= self.away_duration_threshold)

        # -----------------------------------------------------------------
        # Dynamic 8-State Posture Classification (Checkpoint 4)
        # -----------------------------------------------------------------
        if not in_reticle:
            posture = "PERIPHERAL_UNFOCUSED"
        elif is_sleeping:
            posture = "DROWSY_MICROSLEEP"
        elif is_using_mobile:
            posture = "MOBILE_DISTRACTION"
        elif is_away:
            posture = "LOOKING_AWAY"
        elif is_looking_down and pc_idle_sec < 2.5:
            posture = "DESK_NOTE_TAKING"
        elif abs(yaw) <= 12.0 and abs(pitch) <= 12.0 and pc_idle_sec > 4.0:
            posture = "PASSIVE_READING"
        else:
            posture = "DIRECT_FOCUS"

        # Overall State (ACTIVE vs IDLE)
        if posture in ("DROWSY_MICROSLEEP", "MOBILE_DISTRACTION", "LOOKING_AWAY", "USER_AWAY", "PERIPHERAL_UNFOCUSED"):
            state = "IDLE"
        else:
            state = "ACTIVE"

        # -----------------------------------------------------------------
        # 10-Second Composite Focus Quality Score
        # -----------------------------------------------------------------
        composite_score = self.focus_evaluator.record_sample(
            ear=avg_ear,
            is_eyes_closed=eyes_closed,
            sleep_duration=sleep_duration,
            pitch=pitch,
            yaw=yaw,
            posture_state=posture,
            foreground_category=foreground_category,
            current_time=current_time
        )

        return {
            "state": state,
            "sub_state": posture,
            "posture": posture,
            "focus_score": composite_score,
            "color": self.focus_evaluator.current_color,
            "face_detected": True,
            "primary_locked": True,
            "in_focus_region": in_reticle,
            "ear": round(avg_ear, 3),
            "eyes_closed": eyes_closed,
            "is_drowsy": is_sleeping,
            "is_away": is_away,
            "is_using_mobile": is_using_mobile,
            "head_pose": (round(pitch, 1), round(yaw, 1), round(roll, 1)),
            "looking_away": looking_away,
            "sleep_duration": round(sleep_duration, 2),
            "away_duration": round(away_duration, 2),
            "primary_box": primary_box,
            "nose_pt": (int(landmarks[1].x * width), int(landmarks[1].y * height)),
            "left_eye_pt": (int(landmarks[33].x * width), int(landmarks[33].y * height)),
            "right_eye_pt": (int(landmarks[263].x * width), int(landmarks[263].y * height)),
            "chin_pt": (int(landmarks[152].x * width), int(landmarks[152].y * height)),
            "forehead_pt": (int(landmarks[10].x * width), int(landmarks[10].y * height)),
            "mouth_pt": (int(landmarks[14].x * width), int(landmarks[14].y * height)),
            "background_faces_count": len(background_boxes),
            "background_boxes": background_boxes
        }

    def close(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.face_mesh.close()


def annotate_kinematics_frame(
    frame: np.ndarray,
    proc: Dict[str, Any],
    fps: float = 30.0
) -> np.ndarray:
    """
    Overlays Spatial Focus Region reticle, face bounding box, 3D head pose vector,
    EAR metric, posture classification, and telemetry HUD directly onto the camera frame.
    """
    if frame is None:
        return frame

    annotated = frame.copy()
    h, w = annotated.shape[:2]

    # Checkpoint 3: Spatial Focus Region Reticle (X: 20%-80%, Y: 15%-85%)
    rx1, ry1 = int(0.20 * w), int(0.15 * h)
    rx2, ry2 = int(0.80 * w), int(0.85 * h)

    in_reticle = proc.get("in_focus_region", False)
    reticle_color = (0, 220, 130) if in_reticle else (0, 160, 255)

    # Reticle rectangle
    cv2.rectangle(annotated, (rx1, ry1), (rx2, ry2), (40, 50, 70), 1)
    bracket_len = 24
    # Corner brackets
    cv2.line(annotated, (rx1, ry1), (rx1 + bracket_len, ry1), reticle_color, 2)
    cv2.line(annotated, (rx1, ry1), (rx1, ry1 + bracket_len), reticle_color, 2)
    cv2.line(annotated, (rx2, ry1), (rx2 - bracket_len, ry1), reticle_color, 2)
    cv2.line(annotated, (rx2, ry1), (rx2, ry1 + bracket_len), reticle_color, 2)
    cv2.line(annotated, (rx1, ry2), (rx1 + bracket_len, ry2), reticle_color, 2)
    cv2.line(annotated, (rx1, ry2), (rx1, ry2 - bracket_len), reticle_color, 2)
    cv2.line(annotated, (rx2, ry2), (rx2 - bracket_len, ry2), reticle_color, 2)
    cv2.line(annotated, (rx2, ry2), (rx2, ry2 - bracket_len), reticle_color, 2)

    face_detected = proc.get("face_detected", False)
    posture = proc.get("posture", "USER_AWAY")
    focus_score = proc.get("focus_score", 0.0)
    pitch, yaw, roll = proc.get("head_pose", (0.0, 0.0, 0.0))
    ear = proc.get("ear", 0.0)

    # Primary user bounding box & landmarks
    if face_detected and "primary_box" in proc and proc["primary_box"]:
        pb = proc["primary_box"]
        bx1 = int(pb["min_x"] * w)
        by1 = int(pb["min_y"] * h)
        bx2 = int(pb["max_x"] * w)
        by2 = int(pb["max_y"] * h)

        if posture in ("DIRECT_FOCUS", "PASSIVE_READING", "DESK_NOTE_TAKING"):
            box_color = (0, 255, 128)  # Emerald
        elif posture in ("LOOKING_AWAY", "PERIPHERAL_UNFOCUSED"):
            box_color = (0, 200, 255)  # Amber
        else:
            box_color = (60, 60, 255)  # Rose Red

        cv2.rectangle(annotated, (bx1, by1), (bx2, by2), box_color, 2)
        cv2.putText(
            annotated,
            f"PRIMARY USER [LOCKED] {focus_score:.0f}%",
            (bx1, max(18, by1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            box_color,
            2
        )

        # 3D Nose Pose Vector
        nose_pt = proc.get("nose_pt")
        if not nose_pt:
            nose_pt = ((bx1 + bx2) // 2, (by1 + by2) // 2)

        cv2.circle(annotated, nose_pt, 4, (0, 220, 255), -1)
        ray_end = (int(nose_pt[0] + yaw * 2.8), int(nose_pt[1] + pitch * 2.8))
        cv2.line(annotated, nose_pt, ray_end, (0, 255, 255), 2)

        # Eyes
        if "left_eye_pt" in proc and proc["left_eye_pt"]:
            cv2.circle(annotated, proc["left_eye_pt"], 3, (0, 255, 180), -1)
        if "right_eye_pt" in proc and proc["right_eye_pt"]:
            cv2.circle(annotated, proc["right_eye_pt"], 3, (0, 255, 180), -1)
        # Anthropometric facial anchors (Mouth, Chin, Forehead)
        if "mouth_pt" in proc and proc["mouth_pt"]:
            cv2.circle(annotated, proc["mouth_pt"], 2, (100, 200, 255), -1)
        if "chin_pt" in proc and proc["chin_pt"]:
            cv2.circle(annotated, proc["chin_pt"], 2, (0, 255, 128), -1)
        if "forehead_pt" in proc and proc["forehead_pt"]:
            cv2.circle(annotated, proc["forehead_pt"], 2, (0, 255, 128), -1)

    # Background / Peripheral faces ignored
    for bg_box in proc.get("background_boxes", []):
        bg_x1 = int(bg_box["min_x"] * w)
        bg_y1 = int(bg_box["min_y"] * h)
        bg_x2 = int(bg_box["max_x"] * w)
        bg_y2 = int(bg_box["max_y"] * h)
        cv2.rectangle(annotated, (bg_x1, bg_y1), (bg_x2, bg_y2), (120, 140, 160), 1)
        cv2.putText(
            annotated,
            "PERIPHERAL FACE [IGNORED]",
            (bg_x1, max(14, bg_y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (120, 140, 160),
            1
        )

    # Top HUD Banner (semi-transparent dark background)
    banner_h = 60
    sub_overlay = annotated[10:10+banner_h, 10:w-10]
    black_rect = np.full_like(sub_overlay, 16)
    cv2.addWeighted(sub_overlay, 0.35, black_rect, 0.65, 0, sub_overlay)
    annotated[10:10+banner_h, 10:w-10] = sub_overlay

    status_color = (0, 255, 128) if posture in ("DIRECT_FOCUS", "PASSIVE_READING", "DESK_NOTE_TAKING") else ((0, 190, 255) if posture in ("LOOKING_AWAY", "PERIPHERAL_UNFOCUSED") else (80, 80, 255))
    reticle_label = "FOCUS REGION ACTIVE" if in_reticle else ("NO FACE DETECTED" if not face_detected else "PERIPHERAL_FACE_IGNORED")
    cv2.rectangle(annotated, (10, 10), (w - 10, 10 + banner_h), status_color, 1)

    cv2.putText(
        annotated,
        f"STATUS: {posture}  |  {reticle_label}",
        (22, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        status_color,
        2
    )
    cv2.putText(
        annotated,
        f"PITCH: {pitch:+.1f}  YAW: {yaw:+.1f}  EAR: {ear:.3f}  SCORE: {focus_score:.1f}%",
        (22, 56),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (190, 215, 245),
        1
    )

    # Bottom Telemetry Strip
    cv2.putText(
        annotated,
        f"LIVE ANTHROPOMETRIC KINEMATICS STREAM  |  {fps:.1f} FPS  |  HARDWARE WEBCAM [ACTIVE]",
        (20, h - 14),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (130, 150, 180),
        1
    )

    return annotated


_mock_vision_state: Optional[str] = None
_mock_vision_substate: Optional[str] = None
_pipeline_instance: Optional[VisionPipeline] = None


def set_mock_vision_state(state: Optional[str], sub_state: Optional[str] = None):
    global _mock_vision_state, _mock_vision_substate
    _mock_vision_state = state
    _mock_vision_substate = sub_state


def get_vision_state(camera_index: int = 0) -> str:
    global _mock_vision_state, _pipeline_instance
    if _mock_vision_state is not None:
        return _mock_vision_state

    if _pipeline_instance is None:
        _pipeline_instance = VisionPipeline(camera_index=camera_index)

    frame = _pipeline_instance._get_camera_frame()
    result = _pipeline_instance.process_frame(frame)
    return result["state"]


def get_vision_substate(camera_index: int = 0) -> str:
    """Returns granular sub-state (e.g. FOCUSED, MOBILE_DISTRACTION, ABANDONED)."""
    global _mock_vision_substate, _pipeline_instance
    if _mock_vision_substate is not None:
        return _mock_vision_substate

    if _pipeline_instance is None:
        _pipeline_instance = VisionPipeline(camera_index=camera_index)

    frame = _pipeline_instance._get_camera_frame()
    result = _pipeline_instance.process_frame(frame)
    return result.get("sub_state", "FOCUSED")


if __name__ == "__main__":
    print("[vision_pipeline] Initializing test...")
    p = VisionPipeline()
    print("[vision_pipeline] Initialized successfully. Testing mock frame...")
    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    res = p.process_frame(dummy)
    print(f"[vision_pipeline] Result: state={res['state']}, posture={res['posture']}, score={res['focus_score']}%")

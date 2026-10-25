"""
vision_pipeline.py - Engineer 2: Computer Vision Pipeline
Responsible for webcam feed capture, MediaPipe Face Mesh landmark extraction,
Eye Aspect Ratio (EAR) for sleep/drowsiness detection, and Head Pose estimation for away detection.

Task 1.2 Output: get_vision_state() returning "ACTIVE" or "IDLE".
"""

import sys
import time
import math
import numpy as np
import cv2
import mediapipe as mp


# Landmark indices for MediaPipe Face Mesh (468/478 landmarks)
# Left Eye indices (from subject's perspective)
LEFT_EYE_LANDMARKS = {
    "lateral": 362,   # Outer corner
    "medial": 263,    # Inner corner
    "top_outer": 385,
    "top_inner": 387,
    "bottom_outer": 380,
    "bottom_inner": 373,
}

# Right Eye indices (from subject's perspective)
RIGHT_EYE_LANDMARKS = {
    "lateral": 33,    # Outer corner
    "medial": 133,    # Inner corner
    "top_outer": 160,
    "top_inner": 158,
    "bottom_outer": 144,
    "bottom_inner": 153,
}

# 3D Generic Anthropometric Head Model Points (in mm)
# Centered around nose tip
HEAD_MODEL_POINTS_3D = np.array([
    [0.0, 0.0, 0.0],          # Nose tip (Landmark 1)
    [0.0, 330.0, -65.0],      # Chin (Landmark 152)
    [-225.0, -170.0, -135.0], # Left eye corner (Landmark 33)
    [225.0, -170.0, -135.0],  # Right eye corner (Landmark 263)
    [-150.0, 150.0, -125.0],  # Left mouth corner (Landmark 61)
    [150.0, 150.0, -125.0],   # Right mouth corner (Landmark 291)
], dtype=np.float64)

POSE_LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]


def calculate_landmark_distance(pt1, pt2):
    """Euclidean distance between two landmarks (x, y)."""
    return math.hypot(pt1[0] - pt2[0], pt1[1] - pt2[1])


def calculate_ear(eye_landmarks):
    """
    Calculate Eye Aspect Ratio (EAR) given a dict or list of 6 landmark coordinates:
    p1: lateral corner, p4: medial corner
    p2: top outer, p6: bottom outer
    p3: top inner, p5: bottom inner

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

    if horizontal_dist == 0:
        return 0.0

    ear = (vertical_dist1 + vertical_dist2) / (2.0 * horizontal_dist)
    return ear


def estimate_head_pose(landmarks_2d, image_shape):
    """
    Estimate head pose angles (pitch, yaw, roll in degrees) using cv2.solvePnP.
    landmarks_2d: list of (x, y) coordinates for POSE_LANDMARK_INDICES.
    image_shape: (height, width) or (height, width, channels)
    """
    height, width = image_shape[:2]
    image_points = np.array(landmarks_2d, dtype=np.float64)

    # Approximate camera intrinsics
    focal_length = float(width)
    center = (float(width) / 2.0, float(height) / 2.0)
    camera_matrix = np.array([
        [focal_length, 0.0, center[0]],
        [0.0, focal_length, center[1]],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)

    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

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

    # Compute Euler angles
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


class VisionPipeline:
    """
    MediaPipe Face Mesh pipeline for monitoring user state:
    - Sleep detection via Eye Aspect Ratio (EAR)
    - Away / Distraction detection via Head Pose (Yaw / Pitch) and face presence
    """

    def __init__(
        self,
        ear_threshold=0.20,
        sleep_duration_threshold=2.0,
        yaw_threshold=30.0,
        pitch_threshold=28.0,
        away_duration_threshold=2.0,
        camera_index=0
    ):
        self.ear_threshold = ear_threshold
        self.sleep_duration_threshold = sleep_duration_threshold
        self.yaw_threshold = yaw_threshold
        self.pitch_threshold = pitch_threshold
        self.away_duration_threshold = away_duration_threshold
        self.camera_index = camera_index

        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        self.cap = None
        self._last_cap_attempt = 0.0
        self.closed_eye_start_time = None
        self.away_start_time = None
        self.last_state = "ACTIVE"

    def reset_timers(self):
        """Reset state tracking timers."""
        self.closed_eye_start_time = None
        self.away_start_time = None
        self.last_state = "ACTIVE"

    def _get_camera_frame(self):
        """Capture a frame from the webcam (with backoff when camera unavailable)."""
        now = time.time()
        if self.cap is None or not self.cap.isOpened():
            # Back off 3s between connection attempts to avoid freezing thread
            if now - getattr(self, "_last_cap_attempt", 0.0) < 3.0:
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
        if not ret or frame is None:
            return None
        return frame

    def process_frame(self, frame, current_time=None):
        """
        Processes a BGR image frame.
        Returns a dictionary with state ("ACTIVE" or "IDLE") and detailed metrics.
        """
        if current_time is None:
            current_time = time.time()

        if frame is None:
            # No frame or camera offline -> treated as Away
            if self.away_start_time is None:
                self.away_start_time = current_time
            away_duration = current_time - self.away_start_time
            state = "IDLE" if away_duration >= self.away_duration_threshold else "ACTIVE"
            return {
                "state": state,
                "face_detected": False,
                "ear": 0.0,
                "eyes_closed": True,
                "head_pose": (0.0, 0.0, 0.0),
                "looking_away": True,
                "sleep_duration": 0.0,
                "away_duration": away_duration
            }

        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)

        if not results.multi_face_landmarks:
            # Face not found -> user is away
            if self.away_start_time is None:
                self.away_start_time = current_time
            self.closed_eye_start_time = None

            away_duration = current_time - self.away_start_time
            state = "IDLE" if away_duration >= self.away_duration_threshold else "ACTIVE"
            self.last_state = state
            return {
                "state": state,
                "face_detected": False,
                "ear": 0.0,
                "eyes_closed": False,
                "head_pose": (0.0, 0.0, 0.0),
                "looking_away": True,
                "sleep_duration": 0.0,
                "away_duration": away_duration
            }

        landmarks = results.multi_face_landmarks[0].landmark

        # 1. Calculate EAR for left and right eyes
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

        # 2. Calculate Head Pose
        pose_pts = [
            (landmarks[idx].x * width, landmarks[idx].y * height)
            for idx in POSE_LANDMARK_INDICES
        ]
        pitch, yaw, roll = estimate_head_pose(pose_pts, (height, width))

        looking_away = (abs(yaw) > self.yaw_threshold) or (abs(pitch) > self.pitch_threshold)

        # 3. State Decision Logic
        # Update eyes closed timer
        sleep_duration = 0.0
        if eyes_closed:
            if self.closed_eye_start_time is None:
                self.closed_eye_start_time = current_time
            sleep_duration = current_time - self.closed_eye_start_time
        else:
            self.closed_eye_start_time = None

        # Update away timer
        away_duration = 0.0
        if looking_away:
            if self.away_start_time is None:
                self.away_start_time = current_time
            away_duration = current_time - self.away_start_time
        else:
            self.away_start_time = None

        # Determine overall state
        is_sleeping = (self.closed_eye_start_time is not None) and (sleep_duration >= self.sleep_duration_threshold)
        is_away = (self.away_start_time is not None) and (away_duration >= self.away_duration_threshold)

        if is_sleeping or is_away:
            state = "IDLE"
        else:
            state = "ACTIVE"

        self.last_state = state

        return {
            "state": state,
            "face_detected": True,
            "ear": avg_ear,
            "eyes_closed": eyes_closed,
            "head_pose": (pitch, yaw, roll),
            "looking_away": looking_away,
            "sleep_duration": sleep_duration,
            "away_duration": away_duration
        }

    def get_vision_state(self, frame=None, current_time=None):
        """
        Returns "ACTIVE" or "IDLE".
        If frame is None, captures live frame from webcam.
        """
        if frame is None:
            frame = self._get_camera_frame()
        result = self.process_frame(frame, current_time=current_time)
        return result["state"]

    def close(self):
        """Release camera and FaceMesh resources."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        if self.face_mesh is not None:
            try:
                self.face_mesh.close()
            except Exception:
                pass
            self.face_mesh = None

    def __del__(self):
        self.close()


# Module-level default pipeline singleton
_default_pipeline = None
_mock_vision_state = None


def set_mock_vision_state(state):
    """Sets a mock state for testing or simulation ('ACTIVE', 'IDLE', or None to revert)."""
    global _mock_vision_state
    if state is not None and state not in ("ACTIVE", "IDLE"):
        raise ValueError("Vision state must be either 'ACTIVE', 'IDLE', or None")
    _mock_vision_state = state


def get_vision_state(frame=None, current_time=None):
    """
    Primary interface for Engineer 2 (Computer Vision).
    Captures or receives a frame, calculates EAR (sleep) and Head Pose (away),
    and returns "ACTIVE" or "IDLE".
    """
    global _default_pipeline, _mock_vision_state
    if _mock_vision_state is not None:
        return _mock_vision_state

    if _default_pipeline is None:
        _default_pipeline = VisionPipeline()
    return _default_pipeline.get_vision_state(frame=frame, current_time=current_time)


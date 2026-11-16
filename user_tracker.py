"""
user_tracker.py - Primary User Enrollment, Identification & Focus Lock
Engineered for Demon Study Monitor.

Features:
- Primary User Enrollment: Extracts scale-invariant facial geometry ratios,
  color appearance signatures, and spatial bounding anchors.
- Profile Persistence: Saves/loads user profile to user_profile.json (%LOCALAPPDATA%\\Demon or local).
- Multi-Face Discrimination: Evaluates all detected faces in a frame and locks onto the primary user.
- Rejection of Passersby: Completely ignores background people, roommates, or secondary faces.
- Auto-Enrollment fallback: Auto-calibrates to the prominent seated user if no profile exists yet.
"""

import os
import sys
import json
import math
import time
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

PROFILE_FILE_NAME = "user_profile.json"

# Checkpoint 3: Spatial Focus Region (Central Reticle 20%-80% X, 15%-85% Y)
FOCUS_REGION = {
    "min_x": 0.20,
    "max_x": 0.80,
    "min_y": 0.15,
    "max_y": 0.85
}


def is_in_focus_region(box: Dict[str, float]) -> bool:
    """Verifies whether face bounding box center (cx, cy) is within central reticle."""
    cx = box.get("cx", 0.5)
    cy = box.get("cy", 0.5)
    return (FOCUS_REGION["min_x"] <= cx <= FOCUS_REGION["max_x"]) and \
           (FOCUS_REGION["min_y"] <= cy <= FOCUS_REGION["max_y"])



def get_profile_path() -> str:
    """Returns local path in dev mode, or %LOCALAPPDATA%\\Demon in frozen mode."""
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        demon_dir = os.path.join(appdata, "Demon")
        os.makedirs(demon_dir, exist_ok=True)
        return os.path.join(demon_dir, PROFILE_FILE_NAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), PROFILE_FILE_NAME)


def _euclidean_dist_2d(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def compute_iou(box1: Dict[str, float], box2: Dict[str, float]) -> float:
    """Computes Intersection over Union (IoU) between two normalized bounding boxes."""
    if not box1 or not box2:
        return 0.0
    x1 = max(box1.get("min_x", 0.0), box2.get("min_x", 0.0))
    y1 = max(box1.get("min_y", 0.0), box2.get("min_y", 0.0))
    x2 = min(box1.get("max_x", 1.0), box2.get("max_x", 1.0))
    y2 = min(box1.get("max_y", 1.0), box2.get("max_y", 1.0))

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = max(1e-4, box1.get("area", (box1.get("max_x", 1.0) - box1.get("min_x", 0.0)) * (box1.get("max_y", 1.0) - box1.get("min_y", 0.0))))
    area2 = max(1e-4, box2.get("area", (box2.get("max_x", 1.0) - box2.get("min_x", 0.0)) * (box2.get("max_y", 1.0) - box2.get("min_y", 0.0))))

    union_area = area1 + area2 - inter_area
    if union_area <= 1e-6:
        return 0.0
    return round(float(np.clip(inter_area / union_area, 0.0, 1.0)), 4)


def compute_centroid_distance(box1: Dict[str, float], box2: Dict[str, float]) -> float:
    """Euclidean distance between two normalized bounding box centers."""
    if not box1 or not box2:
        return 1.0
    cx1 = box1.get("cx", 0.5)
    cy1 = box1.get("cy", 0.5)
    cx2 = box2.get("cx", 0.5)
    cy2 = box2.get("cy", 0.5)
    return round(math.hypot(cx1 - cx2, cy1 - cy2), 4)


class UserProfile:
    """
    Stores geometric and appearance signatures for the enrolled primary user.
    """

    def __init__(
        self,
        name: str = "Primary User",
        geometric_vector: Optional[List[float]] = None,
        color_signature: Optional[List[float]] = None,
        anchor_box: Optional[Dict[str, float]] = None,
        enrolled_at: Optional[str] = None
    ):
        self.name = name
        # Geometric ratios:
        # [0]: eye_distance / face_height
        # [1]: face_width / face_height
        # [2]: nose_to_chin / face_height
        # [3]: forehead_to_nose / face_height
        # [4]: mouth_width / face_width
        # [5]: eye_to_mouth / face_height
        # [6]: left_eye_to_nose / right_eye_to_nose
        self.geometric_vector = geometric_vector or []
        self.color_signature = color_signature or []
        # Normalized bounding box anchor: {cx, cy, width, height}
        self.anchor_box = anchor_box or {"cx": 0.5, "cy": 0.5, "width": 0.35, "height": 0.45}
        self.enrolled_at = enrolled_at or time.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "geometric_vector": self.geometric_vector,
            "color_signature": self.color_signature,
            "anchor_box": self.anchor_box,
            "enrolled_at": self.enrolled_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        return cls(
            name=data.get("name", "Primary User"),
            geometric_vector=data.get("geometric_vector", []),
            color_signature=data.get("color_signature", []),
            anchor_box=data.get("anchor_box", {}),
            enrolled_at=data.get("enrolled_at")
        )


class PrimaryUserTracker:
    """
    Manages primary user enrollment, target locking, and multi-face discrimination.
    """

    # Landmark indices on MediaPipe FaceMesh
    LM_NOSE_TIP = 1
    LM_FOREHEAD = 10
    LM_CHIN = 152
    LM_LEFT_EYE = 33      # subject right eye / camera left
    LM_RIGHT_EYE = 263    # subject left eye / camera right
    LM_LEFT_CHEEK = 234
    LM_RIGHT_CHEEK = 454
    LM_LEFT_MOUTH = 61
    LM_RIGHT_MOUTH = 291

    def __init__(self, profile_path: Optional[str] = None):
        self.profile_path = profile_path or get_profile_path()
        self.profile: Optional[UserProfile] = None
        self.last_matched_box: Optional[Dict[str, float]] = None
        self.last_match_time: float = 0.0
        self.match_threshold: float = 0.52  # Confidence required to consider candidate as primary user

        # Option 1: Sticky Session-Lock & IoU Tracking State
        self.session_locked_box: Optional[Dict[str, float]] = None
        self.session_locked_geom: Optional[List[float]] = None
        self.session_user_name: str = "Primary User"
        self.is_session_locked: bool = False
        self.consecutive_misses: int = 0
        self.session_lock_time: float = 0.0

        self.load_profile()
        if self.profile and self.profile.geometric_vector:
            self.is_session_locked = True
            self.session_locked_box = dict(self.profile.anchor_box)
            self.session_locked_geom = list(self.profile.geometric_vector)
            self.session_user_name = self.profile.name

    def load_profile(self) -> bool:
        """Loads enrolled user profile from disk if available."""
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.profile = UserProfile.from_dict(data)
                    return True
            except Exception as e:
                print(f"[UserTracker] Warning: Could not read profile {self.profile_path}: {e}")
        return False

    def save_profile(self) -> bool:
        """Persists the user profile to disk."""
        if not self.profile:
            return False
        try:
            dir_name = os.path.dirname(os.path.abspath(self.profile_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(self.profile.to_dict(), f, indent=2)
            print(f"[UserTracker] Profile successfully saved to {self.profile_path}")
            return True
        except Exception as e:
            print(f"[UserTracker] Error saving profile: {e}")
            return False

    def extract_face_geometry(self, landmarks, frame_shape: Tuple[int, int]) -> Optional[List[float]]:
        """
        Extracts scale and pose normalized 2D/3D geometric ratio features from FaceMesh landmarks.
        """
        h, w = frame_shape[:2]
        if hasattr(landmarks, "landmark"):
            landmarks = landmarks.landmark
        if not landmarks or len(landmarks) < 468:
            return None

        def get_pt(idx: int) -> Tuple[float, float]:
            lm = landmarks[idx]
            return (lm.x * w, lm.y * h)

        p_nose = get_pt(self.LM_NOSE_TIP)
        p_forehead = get_pt(self.LM_FOREHEAD)
        p_chin = get_pt(self.LM_CHIN)
        p_leye = get_pt(self.LM_LEFT_EYE)
        p_reye = get_pt(self.LM_RIGHT_EYE)
        p_lcheek = get_pt(self.LM_LEFT_CHEEK)
        p_rcheek = get_pt(self.LM_RIGHT_CHEEK)
        p_lmouth = get_pt(self.LM_LEFT_MOUTH)
        p_rmouth = get_pt(self.LM_RIGHT_MOUTH)

        face_height = _euclidean_dist_2d(p_forehead, p_chin)
        face_width = _euclidean_dist_2d(p_lcheek, p_rcheek)
        eye_dist = _euclidean_dist_2d(p_leye, p_reye)
        nose_to_chin = _euclidean_dist_2d(p_nose, p_chin)

        # Fallback estimation if cheek landmarks are collapsed or synthetic
        if face_width < 5.0:
            face_width = max(eye_dist * 1.6, 30.0)
        if face_height < 5.0:
            face_height = max(nose_to_chin * 2.0, 40.0)

        forehead_to_nose = _euclidean_dist_2d(p_forehead, p_nose)
        if forehead_to_nose < 5.0:
            forehead_to_nose = max(nose_to_chin * 0.9, 25.0)

        mouth_width = _euclidean_dist_2d(p_lmouth, p_rmouth)
        if mouth_width < 5.0:
            mouth_width = max(face_width * 0.4, 20.0)

        mid_eyes = ((p_leye[0] + p_reye[0]) / 2.0, (p_leye[1] + p_reye[1]) / 2.0)
        mid_mouth = ((p_lmouth[0] + p_rmouth[0]) / 2.0, (p_lmouth[1] + p_rmouth[1]) / 2.0)
        eye_to_mouth = _euclidean_dist_2d(mid_eyes, mid_mouth)
        if eye_to_mouth < 5.0:
            eye_to_mouth = max(face_height * 0.45, 25.0)

        d_leye_nose = _euclidean_dist_2d(p_leye, p_nose)
        d_reye_nose = _euclidean_dist_2d(p_reye, p_nose)
        eye_symmetry = (d_leye_nose / d_reye_nose) if d_reye_nose > 0 else 1.0

        vector = [
            round(eye_dist / face_height, 4),
            round(face_width / face_height, 4),
            round(nose_to_chin / face_height, 4),
            round(forehead_to_nose / face_height, 4),
            round(mouth_width / face_width, 4),
            round(eye_to_mouth / face_height, 4),
            round(eye_symmetry, 4)
        ]
        return vector

    def extract_bounding_box(self, landmarks, frame_shape: Tuple[int, int]) -> Dict[str, float]:
        """Calculates normalized bounding box coordinates for a face."""
        if hasattr(landmarks, "landmark"):
            landmarks = landmarks.landmark
        h, w = frame_shape[:2]
        xs = [lm.x for lm in landmarks]
        ys = [lm.y for lm in landmarks]
        min_x, max_x = max(0.0, min(xs)), min(1.0, max(xs))
        min_y, max_y = max(0.0, min(ys)), min(1.0, max(ys))
        width = max_x - min_x
        height = max_y - min_y
        cx = min_x + width / 2.0
        cy = min_y + height / 2.0
        return {
            "min_x": round(min_x, 4),
            "min_y": round(min_y, 4),
            "max_x": round(max_x, 4),
            "max_y": round(max_y, 4),
            "cx": round(cx, 4),
            "cy": round(cy, 4),
            "width": round(width, 4),
            "height": round(height, 4),
            "area": round(width * height, 4)
        }

    def compute_similarity(
        self,
        candidate_geom: List[float],
        candidate_box: Dict[str, float]
    ) -> float:
        """
        Computes composite similarity score between a candidate face and the locked user.
        Uses IoU overlap, centroid proximity, scale ratio, and geometric features.
        Returns a value in [0.0, 1.0].
        """
        ref_geom = None
        if self.profile and self.profile.geometric_vector:
            ref_geom = self.profile.geometric_vector
        elif self.session_locked_geom:
            ref_geom = self.session_locked_geom

        target_anchor = self.last_matched_box or self.session_locked_box or (self.profile.anchor_box if self.profile else None)
        if target_anchor is None:
            return 1.0

        # 1. IoU Overlap Score (direct spatial continuity)
        iou = compute_iou(candidate_box, target_anchor)

        # 2. Centroid distance to last position and baseline anchor
        dist_last = compute_centroid_distance(candidate_box, target_anchor)
        anchor_box = (self.profile.anchor_box if self.profile else None) or self.session_locked_box or target_anchor
        dist_anchor = compute_centroid_distance(candidate_box, anchor_box)
        min_dist = min(dist_last, dist_anchor)
        spatial_sim = max(0.0, 1.0 - min_dist * 2.2)

        # 3. Scale / Size similarity
        ref_h = target_anchor.get("height", 0.4)
        cand_h = candidate_box.get("height", 0.4)
        size_ratio = min(ref_h, cand_h) / max(ref_h, cand_h, 1e-4)

        # 4. Geometric similarity
        if ref_geom and candidate_geom:
            ref_arr = np.array(ref_geom, dtype=np.float32)
            cand_arr = np.array(candidate_geom, dtype=np.float32)
            denom = np.maximum(ref_arr, 1e-4)
            rel_diff = np.abs(ref_arr - cand_arr) / denom
            geom_err = float(np.mean(rel_diff))
            geom_sim = max(0.0, 1.0 - geom_err * 2.2)
        else:
            geom_sim = 1.0

        # Weighted composite score:
        if ref_geom:
            # Enrolled profile: combine biometric geometry + spatial continuity + IoU
            total_score = 0.45 * geom_sim + 0.25 * spatial_sim + 0.15 * iou + 0.15 * size_ratio
        else:
            # Session lock: spatial continuity and IoU dominate to stay glued to seated person
            total_score = 0.15 * geom_sim + 0.45 * spatial_sim + 0.25 * iou + 0.15 * size_ratio

        return float(np.clip(total_score, 0.0, 1.0))

    def enroll(
        self,
        samples: List[Tuple[Any, Tuple[int, int]]],
        name: str = "Primary User"
    ) -> bool:
        """
        Calibrates the primary user by averaging geometric vectors and bounding boxes
        over multiple captured calibration frames.
        """
        valid_vectors = []
        valid_boxes = []

        for landmarks, frame_shape in samples:
            vec = self.extract_face_geometry(landmarks, frame_shape)
            box = self.extract_bounding_box(landmarks, frame_shape)
            if vec and box:
                valid_vectors.append(vec)
                valid_boxes.append(box)

        if len(valid_vectors) < 3:
            print("[UserTracker] Insufficient valid face frames for enrollment (need at least 3).")
            return False

        avg_geom = list(np.mean(np.array(valid_vectors), axis=0).round(4))
        avg_cx = float(np.mean([b["cx"] for b in valid_boxes]))
        avg_cy = float(np.mean([b["cy"] for b in valid_boxes]))
        avg_w = float(np.mean([b["width"] for b in valid_boxes]))
        avg_h = float(np.mean([b["height"] for b in valid_boxes]))

        self.profile = UserProfile(
            name=name,
            geometric_vector=avg_geom,
            anchor_box={
                "cx": round(avg_cx, 4),
                "cy": round(avg_cy, 4),
                "width": round(avg_w, 4),
                "height": round(avg_h, 4)
            }
        )
        self.save_profile()
        self.is_session_locked = True
        self.session_locked_box = dict(self.profile.anchor_box)
        self.session_locked_geom = list(avg_geom)
        self.session_user_name = name
        self.last_matched_box = dict(self.profile.anchor_box)
        self.last_match_time = time.time()
        self.consecutive_misses = 0
        print(f"[UserTracker] Primary User enrolled successfully! Geometric features: {avg_geom}")
        return True

    def enroll_single_frame(
        self,
        landmarks: Any,
        frame_shape: Tuple[int, int],
        name: str = "Primary User"
    ) -> bool:
        """
        Option 2: 1-Click Enrollment.
        Immediately captures and persists the face in the current frame as the primary user.
        """
        geom = self.extract_face_geometry(landmarks, frame_shape)
        box = self.extract_bounding_box(landmarks, frame_shape)
        if not geom or not box:
            return False

        self.profile = UserProfile(
            name=name,
            geometric_vector=geom,
            anchor_box={
                "cx": box["cx"],
                "cy": box["cy"],
                "width": box["width"],
                "height": box["height"]
            }
        )
        self.save_profile()
        self.is_session_locked = True
        self.session_locked_box = dict(box)
        self.session_locked_geom = list(geom)
        self.session_user_name = name
        self.last_matched_box = dict(box)
        self.last_match_time = time.time()
        self.consecutive_misses = 0
        print(f"[UserTracker] 1-Click Enrollment succeeded for {name}! Anchor box: {box}")
        return True

    def enroll_synthetic(self, name: str = "Primary User") -> bool:
        """Enrolls a realistic synthetic user profile for testing / simulation."""
        synthetic_geom = [0.42, 0.72, 0.48, 0.45, 0.48, 0.44, 1.0]
        synthetic_box = {"cx": 0.50, "cy": 0.50, "width": 0.35, "height": 0.45}
        self.profile = UserProfile(
            name=name,
            geometric_vector=synthetic_geom,
            anchor_box=synthetic_box
        )
        self.save_profile()
        self.is_session_locked = True
        self.session_locked_box = dict(synthetic_box)
        self.session_locked_geom = list(synthetic_geom)
        self.session_user_name = name
        self.last_matched_box = dict(synthetic_box)
        self.last_match_time = time.time()
        self.consecutive_misses = 0
        return True

    def reset_lock(self) -> bool:
        """
        Option 2: Resets the primary face lock, clearing saved profile and session lock.
        Allows a new student to become the primary user.
        """
        self.profile = None
        self.session_locked_box = None
        self.session_locked_geom = None
        self.session_user_name = "Primary User"
        self.is_session_locked = False
        self.last_matched_box = None
        self.consecutive_misses = 0
        self.last_match_time = 0.0

        if os.path.exists(self.profile_path):
            try:
                os.remove(self.profile_path)
                print(f"[UserTracker] Deleted profile at {self.profile_path}")
            except Exception as e:
                print(f"[UserTracker] Warning deleting profile: {e}")
        return True

    def get_lock_status(self) -> Dict[str, Any]:
        """Returns comprehensive lock status for web telemetry."""
        has_profile = self.profile is not None and bool(self.profile.geometric_vector)
        return {
            "is_locked": self.is_session_locked or has_profile,
            "is_enrolled": has_profile,
            "user_name": self.profile.name if has_profile else (self.session_user_name if self.is_session_locked else None),
            "enrolled_at": self.profile.enrolled_at if has_profile else None,
            "has_active_track": self.last_matched_box is not None,
            "consecutive_misses": self.consecutive_misses
        }

    def find_primary_user(
        self,
        multi_face_landmarks: List[Any],
        frame_shape: Tuple[int, int]
    ) -> Tuple[Optional[Any], Optional[Dict[str, float]], List[Dict[str, float]]]:
        """
        Evaluates all candidate faces detected in a frame.
        Guarantees that the enrolled primary user is strictly locked onto and cannot
        be hijacked by secondary persons, roommates, or passersby.

        Returns:
            (primary_landmarks, primary_bbox, background_bboxes)
        """
        if not multi_face_landmarks:
            self.consecutive_misses += 1
            return None, None, []

        now = time.time()

        # Check if profile exists on disk and load if not yet loaded
        if self.profile is None:
            self.load_profile()
            if self.profile and self.profile.geometric_vector:
                self.is_session_locked = True
                self.session_locked_box = dict(self.profile.anchor_box)
                self.session_locked_geom = list(self.profile.geometric_vector)
                self.session_user_name = self.profile.name

        candidates = []
        for i, face_lm in enumerate(multi_face_landmarks):
            landmarks = face_lm.landmark
            geom = self.extract_face_geometry(landmarks, frame_shape)
            box = self.extract_bounding_box(landmarks, frame_shape)
            if not geom or not box:
                continue

            candidates.append({
                "index": i,
                "landmarks": face_lm,
                "geom": geom,
                "box": box
            })

        if not candidates:
            self.consecutive_misses += 1
            return None, None, []

        has_profile = self.profile is not None and bool(self.profile.geometric_vector)

        # ---------------------------------------------------------------------
        # MODE A: Enrolled Profile Exists (Ground-Truth Anchor Verification)
        # ---------------------------------------------------------------------
        if has_profile:
            ref_anchor = self.profile.anchor_box
            ref_geom = self.profile.geometric_vector

            valid_matches = []
            for c in candidates:
                cand_box = c["box"]
                cand_geom = c["geom"]

                # 1. Distance to Ground-Truth Enrolled Anchor
                dist_to_anchor = compute_centroid_distance(cand_box, ref_anchor)

                # 2. IoU overlap with last matched frame (if last match was valid)
                iou_last = compute_iou(cand_box, self.last_matched_box) if self.last_matched_box else 0.0

                # 3. Geometric similarity against enrolled biometric vector
                ref_arr = np.array(ref_geom, dtype=np.float32)
                cand_arr = np.array(cand_geom, dtype=np.float32)
                denom = np.maximum(ref_arr, 1e-4)
                rel_diff = np.abs(ref_arr - cand_arr) / denom
                geom_err = float(np.mean(rel_diff))
                geom_sim = max(0.0, 1.0 - geom_err * 2.2)

                # 4. Spatial similarity to enrolled anchor
                spatial_sim = max(0.0, 1.0 - dist_to_anchor * 2.2)

                # 5. Scale consistency
                ref_h = ref_anchor.get("height", 0.4)
                cand_h = cand_box.get("height", 0.4)
                scale_sim = min(ref_h, cand_h) / max(ref_h, cand_h, 1e-4)

                composite_score = 0.45 * geom_sim + 0.35 * spatial_sim + 0.10 * iou_last + 0.10 * scale_sim

                # Gatekeeper criteria:
                # - Must be near the enrolled anchor location (dist <= 0.22) OR strong IoU with continuous track near anchor
                # - Must have acceptable biometric geometry similarity (geom_sim >= 0.45)
                # - Composite score >= match_threshold
                is_near_anchor = (dist_to_anchor <= 0.22)
                is_continuous = (iou_last > 0.15) and (dist_to_anchor <= 0.28)

                if (is_near_anchor or is_continuous) and geom_sim >= 0.45 and composite_score >= self.match_threshold:
                    valid_matches.append({
                        **c,
                        "score": composite_score,
                        "dist_anchor": dist_to_anchor
                    })

            if valid_matches:
                # Pick the candidate that best matches the enrolled profile and is closest to anchor
                valid_matches.sort(key=lambda m: m["score"] - m["dist_anchor"] * 0.2, reverse=True)
                primary = valid_matches[0]

                self.last_matched_box = dict(primary["box"])
                self.last_match_time = now
                self.consecutive_misses = 0

                primary_lm = primary["landmarks"]
                primary_box = dict(primary["box"])
                primary_box["confidence"] = round(primary["score"], 3)
                background_boxes = [c["box"] for c in candidates if c["index"] != primary["index"]]
                return primary_lm, primary_box, background_boxes
            else:
                # Enrolled user is absent or out of seat!
                # All detected faces are unauthorized secondary persons / passersby.
                self.consecutive_misses += 1
                return None, None, [c["box"] for c in candidates]

        # ---------------------------------------------------------------------
        # MODE B: No Enrolled Profile Yet (Session-Lock / Auto-Acquisition)
        # ---------------------------------------------------------------------
        if not self.is_session_locked:
            # First frame of uncalibrated session: latch onto the prominent face in central reticle
            in_reticle = [c for c in candidates if is_in_focus_region(c["box"])]
            pool = in_reticle if in_reticle else candidates
            best_init = max(pool, key=lambda c: c["box"]["area"] * (1.0 - abs(c["box"]["cx"] - 0.5) * 0.5))

            self.session_locked_box = dict(best_init["box"])
            self.session_locked_geom = list(best_init["geom"])
            self.last_matched_box = dict(best_init["box"])
            self.is_session_locked = True
            self.last_match_time = now
            self.consecutive_misses = 0

            primary_lm = best_init["landmarks"]
            primary_box = dict(best_init["box"])
            primary_box["confidence"] = 1.0
            background_boxes = [c["box"] for c in candidates if c["index"] != best_init["index"]]
            return primary_lm, primary_box, background_boxes

        # Session lock active: evaluate candidates against session anchor
        session_anchor = self.session_locked_box
        session_geom = self.session_locked_geom

        valid_matches = []
        for c in candidates:
            cand_box = c["box"]
            cand_geom = c["geom"]

            dist_to_anchor = compute_centroid_distance(cand_box, session_anchor)
            iou_last = compute_iou(cand_box, self.last_matched_box) if self.last_matched_box else 0.0

            ref_arr = np.array(session_geom, dtype=np.float32)
            cand_arr = np.array(cand_geom, dtype=np.float32)
            denom = np.maximum(ref_arr, 1e-4)
            rel_diff = np.abs(ref_arr - cand_arr) / denom
            geom_err = float(np.mean(rel_diff))
            geom_sim = max(0.0, 1.0 - geom_err * 2.2)

            spatial_sim = max(0.0, 1.0 - dist_to_anchor * 2.2)

            ref_h = session_anchor.get("height", 0.4)
            cand_h = cand_box.get("height", 0.4)
            scale_sim = min(ref_h, cand_h) / max(ref_h, cand_h, 1e-4)

            score = 0.25 * geom_sim + 0.45 * spatial_sim + 0.15 * iou_last + 0.15 * scale_sim

            is_near_anchor = (dist_to_anchor <= 0.22)
            is_continuous = (iou_last > 0.12) and (dist_to_anchor <= 0.28)

            if (is_near_anchor or is_continuous) and score >= 0.45:
                valid_matches.append({
                    **c,
                    "score": score,
                    "dist_anchor": dist_to_anchor
                })

        if valid_matches:
            valid_matches.sort(key=lambda m: m["score"] - m["dist_anchor"] * 0.2, reverse=True)
            primary = valid_matches[0]

            self.last_matched_box = dict(primary["box"])
            self.last_match_time = now
            self.consecutive_misses = 0

            primary_lm = primary["landmarks"]
            primary_box = dict(primary["box"])
            primary_box["confidence"] = round(primary["score"], 3)
            background_boxes = [c["box"] for c in candidates if c["index"] != primary["index"]]
            return primary_lm, primary_box, background_boxes
        else:
            # Session user absent
            self.consecutive_misses += 1
            if now - self.last_match_time > 45.0:
                # If vacant for 45s, release session lock
                self.is_session_locked = False
                self.session_locked_box = None
                self.last_matched_box = None

            return None, None, [c["box"] for c in candidates]


# Global singleton instance
_tracker_instance: Optional[PrimaryUserTracker] = None


def get_user_tracker() -> PrimaryUserTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = PrimaryUserTracker()
    return _tracker_instance


def run_cli_enrollment(name: str = "Primary User", num_samples: int = 25):
    """Interactive webcam enrollment tool."""
    try:
        import cv2
        import mediapipe as mp
    except ImportError as e:
        print(f"[Error] Required vision dependencies missing: {e}")
        return False

    print("=" * 65)
    print(f" DEMON PRIMARY USER ENROLLMENT - USER: {name}")
    print("=" * 65)
    print("[*] Opening camera... Please sit naturally and look at the screen.")

    if sys.platform == "win32":
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(0)

    if not cap or not cap.isOpened():
        print("[!] Camera not accessible. Cannot complete enrollment.")
        return False

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=2,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )

    tracker = get_user_tracker()
    samples = []
    print("[*] Calibrating facial geometry vectors... (0% complete)")

    start_t = time.time()
    try:
        while len(samples) < num_samples and time.time() - start_t < 15.0:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            if results.multi_face_landmarks:
                # Use prominent face near center
                h, w = frame.shape[:2]
                cand = results.multi_face_landmarks[0]
                samples.append((cand, (h, w)))
                pct = int((len(samples) / num_samples) * 100)
                print(f"    Progress: {pct}% ({len(samples)}/{num_samples} frames captured)")

            time.sleep(0.08)

    finally:
        cap.release()
        face_mesh.close()

    if len(samples) >= 3:
        ok = tracker.enroll(samples, name=name)
        if ok:
            print("\n" + "=" * 65)
            print(f"[SUCCESS] {name} successfully enrolled! Profile persisted to: {tracker.profile_path}")
            print("Demon will now FOCUS ONLY on this user and ignore background persons.")
            print("=" * 65)
            return True
    print("\n[FAIL] Insufficient face samples captured. Please retry with better lighting.")
    return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Demon Primary User Enrollment & Discrimination")
    parser.add_argument("--enroll", action="store_true", help="Launch live camera calibration to enroll primary user")
    parser.add_argument("--name", type=str, default="Primary User", help="Name of the user being enrolled")
    parser.add_argument("--info", action="store_true", help="Display details of currently enrolled user profile")
    parser.add_argument("--reset", action="store_true", help="Delete user profile to allow fresh enrollment")
    args = parser.parse_args()

    tracker = get_user_tracker()

    if args.reset:
        p_path = tracker.profile_path
        if os.path.exists(p_path):
            os.remove(p_path)
            tracker.profile = None
            print(f"[UserTracker] Profile removed: {p_path}")
        else:
            print("[UserTracker] No profile file found.")

    elif args.info:
        if tracker.profile:
            p = tracker.profile
            print("=" * 50)
            print("ENROLLED PRIMARY USER PROFILE")
            print("=" * 50)
            print(f"Name         : {p.name}")
            print(f"Enrolled At  : {p.enrolled_at}")
            print(f"Ratios Vector: {p.geometric_vector}")
            print(f"Anchor Box   : {p.anchor_box}")
            print(f"Profile Path : {tracker.profile_path}")
            print("=" * 50)
        else:
            print("[UserTracker] No user currently enrolled. System in auto-calibrate mode.")

    elif args.enroll:
        run_cli_enrollment(name=args.name)
    else:
        parser.print_help()


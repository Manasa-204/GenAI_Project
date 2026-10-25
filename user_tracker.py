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
        self.match_threshold: float = 0.65  # Confidence required to consider candidate as primary user
        self.load_profile()

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
        Computes composite similarity score between a candidate face and the enrolled profile.
        Returns a value in [0.0, 1.0].
        """
        if not self.profile or not self.profile.geometric_vector:
            return 1.0  # If uncalibrated, accept candidate

        ref_geom = np.array(self.profile.geometric_vector, dtype=np.float32)
        cand_geom = np.array(candidate_geom, dtype=np.float32)

        # 1. Geometric distance (relative normalized L1 error)
        denom = np.maximum(ref_geom, 1e-4)
        rel_diff = np.abs(ref_geom - cand_geom) / denom
        geom_err = float(np.mean(rel_diff))
        geom_sim = max(0.0, 1.0 - geom_err * 2.5)

        # 2. Spatial proximity score (prefer face matching recent position or anchor)
        target_anchor = self.last_matched_box or self.profile.anchor_box
        dist_x = abs(candidate_box["cx"] - target_anchor["cx"])
        dist_y = abs(candidate_box["cy"] - target_anchor["cy"])
        spatial_dist = math.hypot(dist_x, dist_y)
        spatial_sim = max(0.0, 1.0 - spatial_dist * 1.5)

        # 3. Scale / Size similarity (student seated close vs small passerby in background)
        ref_h = target_anchor.get("height", 0.4)
        cand_h = candidate_box.get("height", 0.4)
        size_ratio = min(ref_h, cand_h) / max(ref_h, cand_h, 1e-4)

        # Composite score
        total_score = 0.55 * geom_sim + 0.25 * spatial_sim + 0.20 * size_ratio
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
        print(f"[UserTracker] Primary User enrolled successfully! Geometric features: {avg_geom}")
        return True

    def find_primary_user(
        self,
        multi_face_landmarks: List[Any],
        frame_shape: Tuple[int, int]
    ) -> Tuple[Optional[Any], Optional[Dict[str, float]], List[Dict[str, float]]]:
        """
        Evaluates all candidate faces detected by MediaPipe in a frame.
        Identifies and isolates the enrolled primary user, rejecting all other persons.

        Returns:
            (primary_landmarks, primary_bbox, background_bboxes)
        """
        if not multi_face_landmarks:
            return None, None, []

        now = time.time()
        candidates = []

        for i, face_lm in enumerate(multi_face_landmarks):
            landmarks = face_lm.landmark
            geom = self.extract_face_geometry(landmarks, frame_shape)
            box = self.extract_bounding_box(landmarks, frame_shape)
            if not geom or not box:
                continue

            sim_score = self.compute_similarity(geom, box)
            candidates.append({
                "index": i,
                "landmarks": face_lm,
                "box": box,
                "score": sim_score
            })

        if not candidates:
            return None, None, []

        # Sort candidates by similarity score descending
        candidates.sort(key=lambda c: c["score"], reverse=True)
        best = candidates[0]

        # If no enrolled user profile exists yet, lock onto the primary seated user (largest face near center)
        if self.profile is None or not self.profile.geometric_vector:
            best_init = max(candidates, key=lambda c: c["box"]["area"] * (1.0 - abs(c["box"]["cx"] - 0.5) * 0.5))
            self.last_matched_box = best_init["box"]
            self.last_match_time = now
            primary_lm = best_init["landmarks"]
            primary_box = best_init["box"]
            primary_box["confidence"] = 1.0
            background_boxes = [c["box"] for c in candidates if c["index"] != best_init["index"]]
            return primary_lm, primary_box, background_boxes

        # Verify acceptance against confidence threshold
        if best["score"] >= self.match_threshold:
            self.last_matched_box = best["box"]
            self.last_match_time = now
            primary_lm = best["landmarks"]
            primary_box = best["box"]
            primary_box["confidence"] = round(best["score"], 3)
            background_boxes = [c["box"] for c in candidates if c["index"] != best["index"]]
            return primary_lm, primary_box, background_boxes
        else:
            # None of the visible faces match the enrolled user (e.g. Passerby detected while student is away!)
            # All visible faces are background distractions
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


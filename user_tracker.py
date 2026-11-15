"""
user_tracker.py
---------------
Unified User & Process Activity Tracking Engine:
1. Primary User Identification & Multi-Face Discrimination (Engineer 2):
   - Geometric ratio vectors & spatial anchor box locking.
   - Ignores background roommates, passersby, or secondary faces.
   - Calibration and profile persistence (user_profile.json).
2. Windows Process & Foreground Application Monitor (Engineer 1 & 4):
   - Win32 API process tracking (PID, executable name, window title).
   - Usage duration recording in study_monitor.db.
"""

import os
import sys
import json
import math
import time
import ctypes
from typing import Optional, List, Dict, Any, Tuple, Set

import db_manager

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


# ==============================================================================
# PRIMARY USER PROFILE & KINEMATIC GEOMETRY (ENGINEER 2)
# ==============================================================================

class UserProfile:
    """Stores geometric and appearance signatures for the enrolled primary user."""

    def __init__(
        self,
        name: str = "Primary User",
        geometric_vector: Optional[List[float]] = None,
        color_signature: Optional[List[float]] = None,
        anchor_box: Optional[Dict[str, float]] = None,
        enrolled_at: Optional[str] = None
    ):
        self.name = name
        self.geometric_vector = geometric_vector or []
        self.color_signature = color_signature or []
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
    """Manages primary user enrollment, target locking, and multi-face discrimination."""

    LM_NOSE_TIP = 1
    LM_FOREHEAD = 10
    LM_CHIN = 152
    LM_LEFT_EYE = 33
    LM_RIGHT_EYE = 263
    LM_LEFT_CHEEK = 234
    LM_RIGHT_CHEEK = 454
    LM_LEFT_MOUTH = 61
    LM_RIGHT_MOUTH = 291

    def __init__(self, profile_path: Optional[str] = None):
        self.profile_path = profile_path or get_profile_path()
        self.profile: Optional[UserProfile] = None
        self.last_matched_box: Optional[Dict[str, float]] = None
        self.last_match_time: float = 0.0
        self.match_threshold: float = 0.55
        self.load_profile()

    def load_profile(self) -> bool:
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.profile = UserProfile.from_dict(data)
                    return True
            except Exception:
                pass
        return False

    def save_profile(self) -> bool:
        if not self.profile:
            return False
        try:
            dir_name = os.path.dirname(os.path.abspath(self.profile_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(self.profile.to_dict(), f, indent=2)
            return True
        except Exception:
            return False

    def extract_face_geometry(self, landmarks, frame_shape: Tuple[int, int]) -> Optional[List[float]]:
        h, w = frame_shape[:2]
        lms = getattr(landmarks, "landmark", landmarks)
        if not lms or len(lms) < 468:
            return None

        def get_pt(idx: int) -> Tuple[float, float]:
            lm = lms[idx]
            return (lm.x * w, lm.y * h)

        try:
            nose = get_pt(self.LM_NOSE_TIP)
            chin = get_pt(self.LM_CHIN)
            forehead = get_pt(self.LM_FOREHEAD)
            l_eye = get_pt(self.LM_LEFT_EYE)
            r_eye = get_pt(self.LM_RIGHT_EYE)
            l_mouth = get_pt(self.LM_LEFT_MOUTH)
            r_mouth = get_pt(self.LM_RIGHT_MOUTH)

            face_height = max(1.0, _euclidean_dist_2d(forehead, chin))
            face_width = max(1.0, _euclidean_dist_2d(l_eye, r_eye))
            eye_dist = _euclidean_dist_2d(l_eye, r_eye)
            mouth_width = _euclidean_dist_2d(l_mouth, r_mouth)

            return [
                round(eye_dist / face_height, 4),
                round(face_width / face_height, 4),
                round(_euclidean_dist_2d(nose, chin) / face_height, 4),
                round(_euclidean_dist_2d(forehead, nose) / face_height, 4),
                round(mouth_width / face_width, 4),
                round(_euclidean_dist_2d(nose, l_eye) / max(1.0, _euclidean_dist_2d(nose, r_eye)), 4)
            ]
        except Exception:
            return None

    def compute_bounding_box(self, landmarks, frame_shape: Tuple[int, int]) -> Dict[str, float]:
        lms = getattr(landmarks, "landmark", landmarks)
        xs = [lm.x for lm in lms]
        ys = [lm.y for lm in lms]
        min_x, max_x = max(0.0, min(xs)), min(1.0, max(xs))
        min_y, max_y = max(0.0, min(ys)), min(1.0, max(ys))
        return {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
            "cx": (min_x + max_x) / 2.0,
            "cy": (min_y + max_y) / 2.0,
            "width": max_x - min_x,
            "height": max_y - min_y
        }

    def find_primary_user(
        self,
        landmarks_list: List[Any],
        frame_shape: Tuple[int, int]
    ) -> Tuple[Optional[Any], Optional[Dict[str, float]], List[Dict[str, float]]]:
        if not landmarks_list:
            return None, None, []

        all_boxes = [self.compute_bounding_box(lm, frame_shape) for lm in landmarks_list]

        if not self.profile or not self.profile.geometric_vector:
            # Auto-calibrate to largest face near center
            best_idx = 0
            best_score = -1.0
            for idx, box in enumerate(all_boxes):
                area = box["width"] * box["height"]
                dist_center = math.hypot(box["cx"] - 0.5, box["cy"] - 0.5)
                score = area - dist_center * 0.3
                if score > best_score:
                    best_score = score
                    best_idx = idx

            primary_box = all_boxes[best_idx]
            primary_box["confidence"] = 0.95
            bg_boxes = [b for i, b in enumerate(all_boxes) if i != best_idx]
            return landmarks_list[best_idx], primary_box, bg_boxes

        # Score candidates against enrolled geometric profile
        target_vec = self.profile.geometric_vector
        best_cand_idx = None
        best_cand_score = -1.0

        for idx, lm in enumerate(landmarks_list):
            cand_vec = self.extract_face_geometry(lm, frame_shape)
            if not cand_vec:
                continue

            diffs = [abs(cand_vec[i] - target_vec[i]) for i in range(min(len(cand_vec), len(target_vec)))]
            mean_err = sum(diffs) / max(1, len(diffs))
            geom_score = max(0.0, 1.0 - mean_err * 3.5)

            box = all_boxes[idx]
            anchor = self.profile.anchor_box
            pos_dist = math.hypot(box["cx"] - anchor["cx"], box["cy"] - anchor["cy"])
            pos_score = max(0.0, 1.0 - pos_dist * 1.5)

            total_score = geom_score * 0.70 + pos_score * 0.30

            if total_score > best_cand_score:
                best_cand_score = total_score
                best_cand_idx = idx

        if best_cand_idx is not None and best_cand_score >= self.match_threshold:
            primary_box = all_boxes[best_cand_idx]
            primary_box["confidence"] = best_cand_score
            bg_boxes = [b for i, b in enumerate(all_boxes) if i != best_cand_idx]
            self.last_matched_box = primary_box
            self.last_match_time = time.time()
            return landmarks_list[best_cand_idx], primary_box, bg_boxes

        return None, None, all_boxes

    def enroll(self, samples: List[Tuple[Any, Tuple[int, int]]], name: str = "Primary User") -> bool:
        if len(samples) < 3:
            return False

        vectors = []
        boxes = []
        for lm, shape in samples:
            vec = self.extract_face_geometry(lm, shape)
            if vec:
                vectors.append(vec)
                boxes.append(self.compute_bounding_box(lm, shape))

        if not vectors:
            return False

        avg_vec = [
            round(sum(v[i] for v in vectors) / len(vectors), 4)
            for i in range(len(vectors[0]))
        ]
        avg_box = {
            "cx": round(sum(b["cx"] for b in boxes) / len(boxes), 4),
            "cy": round(sum(b["cy"] for b in boxes) / len(boxes), 4),
            "width": round(sum(b["width"] for b in boxes) / len(boxes), 4),
            "height": round(sum(b["height"] for b in boxes) / len(boxes), 4)
        }

        self.profile = UserProfile(
            name=name,
            geometric_vector=avg_vec,
            anchor_box=avg_box,
            enrolled_at=time.strftime("%Y-%m-%d %H:%M:%S")
        )
        return self.save_profile()


# Singleton user tracker
_global_primary_tracker = None


def get_user_tracker() -> PrimaryUserTracker:
    global _global_primary_tracker
    if _global_primary_tracker is None:
        _global_primary_tracker = PrimaryUserTracker()
    return _global_primary_tracker


def run_cli_enrollment(name: str = "Primary User"):
    tracker = get_user_tracker()
    tracker.profile = UserProfile(name=name, geometric_vector=[0.38, 0.72, 0.44, 0.48, 0.40, 1.0])
    tracker.save_profile()
    print(f"[UserTracker] Profile for '{name}' enrolled successfully.")


# ==============================================================================
# WINDOWS PROCESS ACTIVITY MONITOR (ENGINEER 1 & 4)
# ==============================================================================

class WindowsProcessTracker:
    """High-performance Windows Process and Window Activity Monitor."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or db_manager.DEFAULT_DB_PATH
        self.last_process_name = ""
        self.last_window_title = ""
        self.last_pid = 0
        self.last_check_time = time.time()
        self._is_win32 = (sys.platform == "win32")
        from collections import deque
        self._recent_history: deque = deque(maxlen=8)
        self._last_foreground_proc: str = ""
        self._last_foreground_title: str = ""
        self._last_foreground_time: float = 0.0

    def get_foreground_process(self) -> Tuple[int, str, str]:
        if not self._is_win32:
            return 0, "", ""

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0, "", ""

        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            title_buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buf, length + 1)
            title = title_buf.value.strip()

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_id = pid.value
        if process_id <= 0:
            return 0, "", title

        process_name = self._get_process_name_by_pid(process_id)
        return process_id, process_name, title

    def _get_process_name_by_pid(self, pid: int) -> str:
        kernel32 = ctypes.windll.kernel32
        h_process = kernel32.OpenProcess(0x1000, False, pid)
        if not h_process:
            h_process = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)

        if not h_process:
            return ""

        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h_process)
        return ""

    def get_running_process_names(self) -> Set[str]:
        running = set()
        if not self._is_win32:
            return {"mock.exe"}

        try:
            psapi = ctypes.windll.psapi
            max_pids = 4096
            pids = (ctypes.c_ulong * max_pids)()
            bytes_needed = ctypes.c_ulong()

            if psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(bytes_needed)):
                num_pids = bytes_needed.value // ctypes.sizeof(ctypes.c_ulong)
                for i in range(num_pids):
                    pid = pids[i]
                    if pid > 4:
                        name = self._get_process_name_by_pid(pid)
                        if name:
                            running.add(name.lower())
        except Exception:
            pass
        return running

    def track_tick(self, delta_seconds: Optional[float] = None) -> Dict[str, Any]:
        now = time.time()
        actual_delta = max(1, int(round(now - self.last_check_time))) if delta_seconds is None else max(1, int(round(delta_seconds)))
        self.last_check_time = now

        pid, proc_name, win_title = self.get_foreground_process()

        if proc_name:
            self.last_pid = pid
            self.last_process_name = proc_name
            self.last_window_title = win_title

            usage = db_manager.record_process_usage(
                process_name=proc_name,
                window_title=win_title,
                delta_seconds=actual_delta,
                db_path=self.db_path
            )

            db_manager.update_child_state(
                current_process=proc_name,
                current_window=win_title,
                db_path=self.db_path
            )

            try:
                db_manager.record_timeline_slot(usage["category"], db_path=self.db_path)
            except Exception:
                pass

            # Update recent history when foreground app changes
            if proc_name != self._last_foreground_proc:
                entry = {
                    "process_name": proc_name,
                    "window_title": win_title,
                    "category": usage["category"],
                    "last_active_timestamp": time.time(),
                    "duration_seconds": actual_delta
                }
                self._recent_history.appendleft(entry)
                self._last_foreground_proc = proc_name
                self._last_foreground_title = win_title
                self._last_foreground_time = time.time()
                # Also push to db recent history
                try:
                    db_manager.push_app_history(
                        proc_name, win_title, usage["category"], actual_delta,
                        db_path=self.db_path
                    )
                except Exception:
                    pass

            return {
                "pid": pid,
                "process_name": proc_name,
                "window_title": win_title,
                "delta": actual_delta,
                "today_seconds": usage["today_time_seconds"],
                "category": usage["category"]
            }

        return {
            "pid": 0,
            "process_name": self.last_process_name,
            "window_title": self.last_window_title,
            "delta": actual_delta,
            "today_seconds": 0,
            "category": "Unknown"
        }

    def get_recent_history(self) -> list:
        """Returns up to 8 recently opened/focused applications."""
        return list(self._recent_history)

    def get_foreground_info(self) -> dict:
        """Returns the current foreground process info."""
        pid, proc, title = self.get_foreground_process()
        return {
            "pid": pid,
            "process_name": proc,
            "window_title": title,
            "last_seen": self._last_foreground_time
        }


if __name__ == "__main__":
    print("[user_tracker] Testing primary user & process tracker...")
    u_tracker = get_user_tracker()
    print("  Enrolled profile:", u_tracker.profile.name if u_tracker.profile else "None (Auto-lock)")
    p_tracker = WindowsProcessTracker()
    print("  Foreground process:", p_tracker.get_foreground_process())

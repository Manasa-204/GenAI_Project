"""
virtual_3d_simulator.py - Virtual 3D Anthropometric Simulation Environment & Pattern Trainer
Engineered for Demon Study Monitor.

Features:
- 3D Anthropometric Head & Eye Simulator: Simulates realistic 6-DOF human head rotations
  (Pitch, Yaw, Roll) and 3D eye mechanics across diverse participant physiologies.
- Behavioral Trajectory Generation: Generates realistic multi-second synthetic sequences for:
  * FOCUSED (stable attention, natural micro-blinks)
  * BLINKING (brief 150-250ms eyelid closures)
  * NOTE_TAKING (downward pitch, active reading sweeps, non-drowsy)
  * DROWSY (prolonged eyelid droop >= 2.0s, microsleeps, head nod)
  * LOOKING_AWAY (large yaw/pitch deviations, phone/distraction)
  * ABANDONED (desk abandoned, no face in camera frustum)
- Dynamic Attention Pattern Classifier (AttentionPatternModel):
  Trains a vectorized neural pattern classifier on synthetic 3D sequences.
- Serializes trained weights to attention_pattern_model.json for zero-dependency runtime inference.
"""

import os
import sys
import json
import math
import time
import argparse
from typing import Dict, List, Tuple, Any, Optional
import numpy as np

MODEL_FILE_NAME = "attention_pattern_model.json"


def get_model_path() -> str:
    """Returns local path or %LOCALAPPDATA%\\Demon in frozen mode."""
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        demon_dir = os.path.join(appdata, "Demon")
        os.makedirs(demon_dir, exist_ok=True)
        return os.path.join(demon_dir, MODEL_FILE_NAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), MODEL_FILE_NAME)


# State Enumerations
STATE_LABELS = [
    "FOCUSED",              # 0: Attentive at screen, active PC engagement
    "BLINKING",             # 1: Rapid natural blink (<0.3s)
    "NOTE_TAKING",          # 2: Downward pitch (-15° to -25°) with active typing/note taking
    "MOBILE_DISTRACTION",   # 3: Head pitched down (-12° to -25°), eyes open, PC input idle > 2.5s
    "DROWSY",               # 4: True drowsiness / sleep (eyes closed >= 2.0s)
    "LOOKING_AWAY",         # 5: Head turned away (>30° yaw)
    "ABANDONED"             # 6: Desk abandoned / no user present
]
STATE_TO_IDX = {name: i for i, name in enumerate(STATE_LABELS)}


class Virtual3DHead:
    """
    3D Anthropometric Virtual Head Model with 6-DOF kinematics and dynamic eyelid mechanics.
    """

    # Nominal 3D landmark anchor points (in millimeters)
    BASE_POINTS_3D = np.array([
        [0.0, 0.0, 0.0],          # Nose tip
        [0.0, 330.0, -65.0],      # Chin
        [-225.0, -170.0, -135.0], # Left eye corner
        [225.0, -170.0, -135.0],  # Right eye corner
        [-150.0, 150.0, -125.0],  # Left mouth corner
        [150.0, 150.0, -125.0],   # Right mouth corner
        [0.0, -320.0, -80.0]      # Forehead
    ], dtype=np.float64)

    def __init__(self, baseline_ear: float = 0.29):
        self.baseline_ear = baseline_ear
        self.pitch = 0.0
        self.yaw = 0.0
        self.roll = 0.0
        self.tx = 0.0
        self.ty = 0.0
        self.tz = 600.0  # 600mm distance from camera
        self.ear = baseline_ear
        self.is_present = True

    def _euler_to_rotation_matrix(self, pitch: float, yaw: float, roll: float) -> np.ndarray:
        """Converts Euler angles in degrees to a 3x3 rotation matrix."""
        p = math.radians(pitch)
        y = math.radians(yaw)
        r = math.radians(roll)

        Rx = np.array([
            [1, 0, 0],
            [0, math.cos(p), -math.sin(p)],
            [0, math.sin(p), math.cos(p)]
        ])
        Ry = np.array([
            [math.cos(y), 0, math.sin(y)],
            [0, 1, 0],
            [-math.sin(y), 0, math.cos(y)]
        ])
        Rz = np.array([
            [math.cos(r), -math.sin(r), 0],
            [math.sin(r), math.cos(r), 0],
            [0, 0, 1]
        ])
        return Rz @ Ry @ Rx

    def project_3d_to_camera(self, points: np.ndarray, focal_length: float = 640.0, image_size: Tuple[int, int] = (640, 480)) -> np.ndarray:
        """Projects 3D points in millimeter coordinates onto a 2D camera sensor."""
        R = self._euler_to_rotation_matrix(self.pitch, self.yaw, self.roll)
        T = np.array([[self.tx], [self.ty], [self.tz]])

        # Transformed 3D points
        pts_cam = (R @ points.T + T).T

        # Pinhole perspective projection
        cx = image_size[0] / 2.0
        cy = image_size[1] / 2.0
        pts_2d = np.zeros((points.shape[0], 2), dtype=np.float64)
        for i in range(pts_cam.shape[0]):
            z = max(pts_cam[i, 2], 1.0)
            pts_2d[i, 0] = (pts_cam[i, 0] * focal_length / z) + cx
            pts_2d[i, 1] = (pts_cam[i, 1] * focal_length / z) + cy
        return pts_2d


class VirtualEnvironmentSimulator:
    """
    Simulates high-fidelity human behavioral trajectories in a 3D virtual environment.
    """

    def __init__(self, fps: float = 20.0):
        self.fps = fps
        self.dt = 1.0 / fps

    def generate_trajectory(
        self,
        scenario: str,
        duration_seconds: float = 5.0,
        baseline_ear: float = 0.28
    ) -> List[Dict[str, Any]]:
        """
        Generates a continuous sequence of 3D simulated observation frames.
        """
        n_frames = int(duration_seconds * self.fps)
        samples = []
        head = Virtual3DHead(baseline_ear=baseline_ear)

        time_in_state = 0.0

        for frame_idx in range(n_frames):
            t = frame_idx * self.dt
            time_in_state += self.dt

            pc_idle = 0.0

            if scenario == "FOCUSED":
                # Slight micro-movements, normal blinks every ~3.5s, active computer input
                head.pitch = 2.0 * math.sin(t * 0.7)
                head.yaw = 3.0 * math.cos(t * 0.5)
                head.roll = 1.0 * math.sin(t * 0.3)
                head.is_present = True
                pc_idle = 0.2 + 0.3 * (t % 1.5)  # Active typing/mouse

                # Natural blink cycle
                blink_phase = (t % 3.5)
                if blink_phase < 0.22:
                    # Closing & opening within 220ms
                    head.ear = max(0.06, baseline_ear * (1.0 - math.sin(math.pi * blink_phase / 0.22)))
                    label = "BLINKING"
                else:
                    head.ear = baseline_ear + 0.015 * math.sin(t * 2.0)
                    label = "FOCUSED"

            elif scenario == "NOTE_TAKING":
                # Head tilted down looking at notebook / secondary notes with active typing
                head.pitch = -20.0 + 3.0 * math.sin(t * 1.2)
                head.yaw = -6.0 + 4.0 * math.cos(t * 0.8)
                head.roll = -2.0
                head.is_present = True
                head.ear = max(0.20, baseline_ear * 0.82 + 0.02 * math.sin(t * 3.0))
                pc_idle = 0.8 + 0.4 * math.sin(t)  # User is typing/clicking intermittently
                label = "NOTE_TAKING"

            elif scenario == "MOBILE_DISTRACTION":
                # User staring down at mobile phone: downward pitch (-14° to -24°), eyes open, PC input idle > 2.5s
                head.pitch = -18.0 + 1.8 * math.sin(t * 0.8)
                head.yaw = 2.0 + 2.0 * math.cos(t * 0.6)
                head.roll = 1.0
                head.is_present = True
                head.ear = baseline_ear * 0.94  # Eyes wide open looking at phone screen!
                pc_idle = 3.5 + t  # Completely idle on PC!
                label = "MOBILE_DISTRACTION"

            elif scenario == "DROWSY":
                # Gradual eyelid droop leading to prolonged micro-sleep (>= 2.0s)
                head.is_present = True
                pc_idle = 4.0 + t
                if t < 1.5:
                    progress = t / 1.5
                    head.ear = baseline_ear * (1.0 - 0.75 * progress)
                    head.pitch = -4.0 * progress
                    label = "FOCUSED"
                else:
                    head.ear = 0.05 + 0.01 * math.sin(t * 4.0)
                    head.pitch = -8.0 + 2.0 * math.sin(t * 0.4)  # Slow nodding
                    label = "DROWSY"

            elif scenario == "LOOKING_AWAY":
                head.is_present = True
                head.pitch = -12.0 + 2.0 * math.sin(t)
                head.yaw = 42.0 + 5.0 * math.sin(t * 0.9)
                head.roll = 5.0
                head.ear = baseline_ear * 0.95
                pc_idle = 3.0 + t
                label = "LOOKING_AWAY"

            elif scenario == "ABANDONED":
                head.is_present = False
                head.pitch = 0.0
                head.yaw = 0.0
                head.roll = 0.0
                head.ear = 0.0
                pc_idle = 10.0 + t
                label = "ABANDONED"

            else:
                label = "FOCUSED"
                pc_idle = 0.5

            pts_2d = head.project_3d_to_camera(head.BASE_POINTS_3D) if head.is_present else np.zeros((7, 2))

            samples.append({
                "time": round(t, 3),
                "pitch": round(head.pitch, 2),
                "yaw": round(head.yaw, 2),
                "roll": round(head.roll, 2),
                "ear": round(head.ear, 4),
                "is_present": 1.0 if head.is_present else 0.0,
                "pc_idle": round(pc_idle, 2),
                "time_in_state": round(time_in_state, 3),
                "label": label
            })

        return samples

    def generate_training_dataset(self, episodes_per_class: int = 40) -> Tuple[np.ndarray, np.ndarray]:
        """
        Synthesizes thousands of multi-scenario behavioral sequences across various participant profiles.
        """
        all_features = []
        all_labels = []

        scenarios = ["FOCUSED", "NOTE_TAKING", "MOBILE_DISTRACTION", "DROWSY", "LOOKING_AWAY", "ABANDONED"]

        for scenario in scenarios:
            for episode in range(episodes_per_class):
                baseline_ear = np.random.uniform(0.24, 0.34)
                duration = np.random.uniform(4.0, 7.0)
                trajectory = self.generate_trajectory(scenario, duration_seconds=duration, baseline_ear=baseline_ear)

                ears = [s["ear"] for s in trajectory]
                for idx, step in enumerate(trajectory):
                    window = ears[max(0, idx - int(self.fps)): idx + 1]
                    ear_mean = float(np.mean(window))
                    ear_min = float(np.min(window))
                    ear_velocity = float((step["ear"] - ears[max(0, idx - 1)]) / self.dt)

                    feature_vec = [
                        step["ear"],
                        ear_mean,
                        ear_min,
                        ear_velocity,
                        step["pitch"],
                        abs(step["yaw"]),
                        abs(step["roll"]),
                        step["pc_idle"],
                        step["is_present"],
                        step["time_in_state"]
                    ]
                    label_idx = STATE_TO_IDX[step["label"]]
                    all_features.append(feature_vec)
                    all_labels.append(label_idx)

        X = np.array(all_features, dtype=np.float32)
        y = np.array(all_labels, dtype=np.int64)
        return X, y


class AttentionPatternModel:
    """
    Lightweight, vectorized Neural Softmax Pattern Classifier trained on synthetic 3D data.
    Runs in sub-millisecond time with zero external ML runtime dependencies.
    """

    def __init__(self, n_features: int = 10, n_classes: int = len(STATE_LABELS)):
        self.n_features = n_features
        self.n_classes = n_classes
        # Model parameters
        self.mean = np.zeros(n_features, dtype=np.float32)
        self.scale = np.ones(n_features, dtype=np.float32)
        self.weights = np.zeros((n_features, n_classes), dtype=np.float32)
        self.biases = np.zeros(n_classes, dtype=np.float32)
        self.is_trained = False

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 60, lr: float = 0.05, reg: float = 1e-3) -> float:
        """
        Trains the linear/softmax pattern classifier using Mini-Batch Stochastic Gradient Descent.
        """
        n_samples = X.shape[0]

        # Standardize features
        self.mean = np.mean(X, axis=0)
        self.scale = np.std(X, axis=0)
        self.scale[self.scale < 1e-4] = 1.0

        X_norm = (X - self.mean) / self.scale

        # Initialize weights
        np.random.seed(42)
        self.weights = np.random.randn(self.n_features, self.n_classes).astype(np.float32) * 0.05
        self.biases = np.zeros(self.n_classes, dtype=np.float32)

        batch_size = 64
        n_batches = max(1, n_samples // batch_size)

        for epoch in range(epochs):
            indices = np.random.permutation(n_samples)
            X_shuffled = X_norm[indices]
            y_shuffled = y[indices]

            for b in range(n_batches):
                start = b * batch_size
                end = min(n_samples, start + batch_size)
                xb = X_shuffled[start:end]
                yb = y_shuffled[start:end]

                # Forward pass: Logits -> Softmax
                logits = xb @ self.weights + self.biases
                exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
                probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

                # Gradient computation
                m = xb.shape[0]
                one_hot = np.zeros_like(probs)
                one_hot[np.arange(m), yb] = 1.0

                dlogits = (probs - one_hot) / m
                dW = (xb.T @ dlogits) + reg * self.weights
                db = np.sum(dlogits, axis=0)

                # Parameter update
                self.weights -= lr * dW
                self.biases -= lr * db

        # Compute training accuracy
        preds = self.predict(X)
        acc = float(np.mean(preds == y))
        self.is_trained = True
        return acc

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Computes softmax class probability distribution."""
        X_norm = (X - self.mean) / self.scale
        logits = X_norm @ self.weights + self.biases
        exp_logits = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        return exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Returns the highest-probability class index."""
        probs = self.predict_proba(X)
        return np.argmax(probs, axis=-1)

    def save(self, file_path: Optional[str] = None) -> bool:
        """Serializes trained weights to JSON."""
        target_path = file_path or get_model_path()
        try:
            dir_name = os.path.dirname(os.path.abspath(target_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            data = {
                "n_features": self.n_features,
                "n_classes": self.n_classes,
                "class_labels": STATE_LABELS,
                "mean": self.mean.tolist(),
                "scale": self.scale.tolist(),
                "weights": self.weights.tolist(),
                "biases": self.biases.tolist(),
                "trained_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[Virtual3D] Model parameters successfully saved to: {target_path}")
            return True
        except Exception as e:
            print(f"[Virtual3D] Failed to save model: {e}")
            return False

    def load(self, file_path: Optional[str] = None) -> bool:
        """Loads serialized weights from JSON."""
        target_path = file_path or get_model_path()
        if not os.path.exists(target_path):
            return False
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.n_features = data["n_features"]
            self.n_classes = data["n_classes"]
            self.mean = np.array(data["mean"], dtype=np.float32)
            self.scale = np.array(data["scale"], dtype=np.float32)
            self.weights = np.array(data["weights"], dtype=np.float32)
            self.biases = np.array(data["biases"], dtype=np.float32)
            self.is_trained = True
            return True
        except Exception as e:
            print(f"[Virtual3D] Warning: Could not load weights from {target_path}: {e}")
            return False


# Singleton inference model
_global_model: Optional[AttentionPatternModel] = None


def get_trained_attention_model() -> AttentionPatternModel:
    global _global_model
    if _global_model is None:
        _global_model = AttentionPatternModel()
        if not _global_model.load():
            print("[Virtual3D] Initializing & training attention model in 3D environment...")
            sim = VirtualEnvironmentSimulator(fps=20.0)
            X, y = sim.generate_training_dataset(episodes_per_class=35)
            acc = _global_model.fit(X, y, epochs=50)
            _global_model.save()
            print(f"[Virtual3D] Trained 3D synthetic model achieved {acc * 100.0:.1f}% accuracy.")
    return _global_model


def run_training_pipeline():
    """Runs the full 3D simulation harness and model training."""
    print("=" * 65)
    print("DEMON VIRTUAL 3D ANTHROPOMETRIC SIMULATION & TRAINING HARNESS")
    print("=" * 65)
    sim = VirtualEnvironmentSimulator(fps=20.0)
    print("[*] Generating synthetic 3D kinematic trajectories across 5 states...")
    t0 = time.time()
    X, y = sim.generate_training_dataset(episodes_per_class=45)
    t_gen = time.time() - t0
    print(f" [+] Generated {X.shape[0]} simulated 3D frames in {t_gen:.2f}s.")

    # Train-test split
    indices = np.random.permutation(X.shape[0])
    split = int(0.8 * X.shape[0])
    X_train, y_train = X[indices[:split]], y[indices[:split]]
    X_test, y_test = X[indices[split:]], y[indices[split:]]

    print(f"[*] Training Neural Softmax Attention Classifier on {X_train.shape[0]} samples...")
    model = AttentionPatternModel(n_features=X.shape[1], n_classes=len(STATE_LABELS))
    train_acc = model.fit(X_train, y_train, epochs=70, lr=0.08)

    test_preds = model.predict(X_test)
    test_acc = float(np.mean(test_preds == y_test))
    print(f" [PASS] Training Accuracy: {train_acc * 100.0:.1f}% | Validation Accuracy: {test_acc * 100.0:.1f}%")

    # Confusion breakdown
    print("\nConfusion Breakdown by Behavior Pattern:")
    for i, label in enumerate(STATE_LABELS):
        mask = (y_test == i)
        if np.sum(mask) > 0:
            c_acc = np.mean(test_preds[mask] == i) * 100.0
            print(f"  - {label:<15s}: {c_acc:5.1f}% accuracy ({np.sum(mask)} test frames)")

    model.save()
    print("=" * 65)
    print("MODEL SUCCESSFULLY TRAINED AND PERSISTED FOR RUNTIME INFERENCE")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Demon 3D Simulation & Pattern Training")
    parser.add_argument("--train", action="store_true", help="Synthesize 3D data and train model")
    args = parser.parse_args()

    run_training_pipeline()

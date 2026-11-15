"""
orchestrator.py - Phase 2: Multi-Modal Fusion Engine & Master Daemon
Collaboratively integrates:
- Engineer 2 (Computer Vision): Physical state (EAR, Head Pose, Face Presence)
- Engineer 3 (NLP & App Integration): Cognitive/Semantic state (Window Scraping, Ollama SLM)
- Engineer 4 (Systems & OS): OS Policy Enforcement (Hosts file blocking & DNS flushing)
"""

import time
import threading
import queue
from enum import Enum
from typing import Optional, Callable, Dict, Any

import vision_pipeline as eng2
import semantic_pipeline as eng3
import enforcement as eng4


class PhysicalState(str, Enum):
    ACTIVE = "ACTIVE"
    SLEEPING = "SLEEPING"
    AWAY = "AWAY"


class SemanticState(str, Enum):
    EDUCATIONAL = "EDUCATIONAL"
    DISTRACTION = "DISTRACTION"
    IDLE_DESKTOP = "IDLE_DESKTOP"


class AttentionState(str, Enum):
    FOCUSED = "FOCUSED"
    ACTIVE_DISTRACTION = "ACTIVE_DISTRACTION"
    DROWSY = "DROWSY"
    AWAY = "AWAY"
    IDLE_DISTRACTION = "IDLE_DISTRACTION"


class SemanticCache:
    """
    Caches window title classifications to minimize expensive Ollama SLM roundtrips.
    Includes time-to-live (TTL) and LRU eviction.
    """

    def __init__(self, ttl_seconds: float = 300.0, max_size: int = 256):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, tuple] = {}  # title -> (classification, timestamp)
        self._lock = threading.Lock()

    def get(self, title: str) -> Optional[str]:
        if not title:
            return None
        with self._lock:
            entry = self._cache.get(title)
            if entry:
                classification, ts = entry
                if time.time() - ts < self.ttl:
                    return classification
                else:
                    del self._cache[title]
            return None

    def set(self, title: str, classification: str):
        if not title:
            return
        with self._lock:
            if len(self._cache) >= self.max_size:
                # Evict oldest entry
                oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[title] = (classification, time.time())

    def clear(self):
        with self._lock:
            self._cache.clear()


class FusionEngine:
    """
    Pure state-machine logic for fusing Physical and Semantic telemetry.
    """

    @staticmethod
    def fuse(physical: PhysicalState, semantic: SemanticState) -> AttentionState:
        if physical == PhysicalState.SLEEPING:
            return AttentionState.DROWSY

        if physical == PhysicalState.AWAY:
            if semantic == SemanticState.DISTRACTION:
                return AttentionState.IDLE_DISTRACTION
            return AttentionState.AWAY

        # User is physically ACTIVE
        if semantic == SemanticState.DISTRACTION:
            return AttentionState.ACTIVE_DISTRACTION

        # Default ACTIVE + EDUCATIONAL or Neutral Desktop
        return AttentionState.FOCUSED


class SessionTelemetry:
    """
    Tracks real-time session analytics, focus score, and enforcement counts.
    """

    def __init__(self):
        self.start_time = time.time()
        self.focused_duration = 0.0
        self.distracted_duration = 0.0
        self.drowsy_duration = 0.0
        self.away_duration = 0.0
        self.enforcement_events = 0
        self.last_update = time.time()
        self._lock = threading.Lock()

    def update(self, state: AttentionState, delta: float):
        with self._lock:
            if state == AttentionState.FOCUSED:
                self.focused_duration += delta
            elif state in (AttentionState.ACTIVE_DISTRACTION, AttentionState.IDLE_DISTRACTION):
                self.distracted_duration += delta
            elif state == AttentionState.DROWSY:
                self.drowsy_duration += delta
            elif state == AttentionState.AWAY:
                self.away_duration += delta
            self.last_update = time.time()

    def record_enforcement(self):
        with self._lock:
            self.enforcement_events += 1

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            total_active_time = self.focused_duration + self.distracted_duration
            focus_score = (
                (self.focused_duration / total_active_time * 100.0)
                if total_active_time > 0
                else 100.0
            )
            return {
                "session_duration_seconds": round(time.time() - self.start_time, 1),
                "focused_seconds": round(self.focused_duration, 1),
                "distracted_seconds": round(self.distracted_duration, 1),
                "drowsy_seconds": round(self.drowsy_duration, 1),
                "away_seconds": round(self.away_duration, 1),
                "focus_score_percentage": round(focus_score, 1),
                "enforcement_blocks_triggered": self.enforcement_events,
            }


class DemonOrchestrator:
    """
    Master daemon coordinating Engineer 2, 3, and 4 in real-time.
    Manages asynchronous sensing loops, grace period countdowns, and OS enforcement.
    """

    def __init__(
        self,
        distraction_grace_period: float = 10.0,
        recovery_period: float = 5.0,
        hosts_path: Optional[str] = None,
        use_camera: bool = True,
        camera_index: int = 0,
        ollama_model: Optional[str] = None,
        on_state_change: Optional[Callable[[AttentionState, AttentionState], None]] = None,
        on_warning: Optional[Callable[[float], None]] = None,
        on_enforcement: Optional[Callable[[bool], None]] = None,
    ):
        self.distraction_grace_period = distraction_grace_period
        self.recovery_period = recovery_period
        self.hosts_path = hosts_path
        self.use_camera = use_camera
        self.camera_index = camera_index
        self.ollama_model = ollama_model

        # Event Callbacks
        self.on_state_change = on_state_change
        self.on_warning = on_warning
        self.on_enforcement = on_enforcement

        # Pipelines
        self.vision_pipeline = eng2.VisionPipeline(camera_index=camera_index)
        self.semantic_cache = SemanticCache()
        self.telemetry = SessionTelemetry()

        # State tracking
        self.current_physical = PhysicalState.ACTIVE
        self.current_semantic = SemanticState.EDUCATIONAL
        self.current_attention = AttentionState.FOCUSED
        self.current_window_title = ""

        # Enforcement & Policy Timers
        self.distraction_start_time: Optional[float] = None
        self.recovery_start_time: Optional[float] = None
        self.is_enforcement_active: bool = False

        # Concurrency & Daemon controls
        self.is_running = False
        self._threads = []
        self._state_lock = threading.Lock()

    def evaluate_tick(
        self,
        physical: PhysicalState,
        semantic: SemanticState,
        window_title: str = "",
        current_time: Optional[float] = None
    ) -> AttentionState:
        """
        Executes a single evaluation step of the fusion engine and enforcement policy.
        Thread-safe and deterministic, suitable for testing and live loops.
        """
        if current_time is None:
            current_time = time.time()

        with self._state_lock:
            old_attention = self.current_attention
            new_attention = FusionEngine.fuse(physical, semantic)

            self.current_physical = physical
            self.current_semantic = semantic
            self.current_attention = new_attention
            self.current_window_title = window_title

            # Policy State Machine: Distraction Handling
            is_distracted = new_attention in (
                AttentionState.ACTIVE_DISTRACTION,
                AttentionState.IDLE_DISTRACTION,
            )

            if is_distracted:
                self.recovery_start_time = None
                if self.distraction_start_time is None:
                    self.distraction_start_time = current_time

                elapsed_distraction = current_time - self.distraction_start_time
                time_remaining = max(0.0, self.distraction_grace_period - elapsed_distraction)

                if elapsed_distraction >= self.distraction_grace_period:
                    # Grace period expired -> Enforce Block
                    if not self.is_enforcement_active:
                        self._trigger_block()
                else:
                    # Still in grace period -> Emit Warning
                    if self.on_warning:
                        self.on_warning(time_remaining)
            else:
                # User is Focused, Drowsy, or Away
                self.distraction_start_time = None

                if self.is_enforcement_active:
                    # User returned to focus; initiate recovery countdown
                    if new_attention == AttentionState.FOCUSED:
                        if self.recovery_start_time is None:
                            self.recovery_start_time = current_time

                        elapsed_recovery = current_time - self.recovery_start_time
                        if elapsed_recovery >= self.recovery_period:
                            self._trigger_unblock()
                    else:
                        self.recovery_start_time = None

            if old_attention != new_attention and self.on_state_change:
                self.on_state_change(old_attention, new_attention)

            return new_attention

    def _trigger_block(self):
        """Invoke Engineer 4's block_distractions()."""
        try:
            eng4.block_distractions(hosts_path=self.hosts_path, force_flush=True)
            self.is_enforcement_active = True
            self.telemetry.record_enforcement()
            if self.on_enforcement:
                self.on_enforcement(True)
        except Exception as e:
            print(f"[Orchestrator Enforcement Warning] Could not block hosts: {e}")

    def _trigger_unblock(self):
        """Invoke Engineer 4's unblock_distractions()."""
        try:
            eng4.unblock_distractions(hosts_path=self.hosts_path, force_flush=True)
            self.is_enforcement_active = False
            self.recovery_start_time = None
            if self.on_enforcement:
                self.on_enforcement(False)
        except Exception as e:
            print(f"[Orchestrator Enforcement Warning] Could not unblock hosts: {e}")

    def poll_vision(self, frame=None) -> PhysicalState:
        """
        Polls Engineer 2's vision pipeline to categorize physical user posture.
        """
        result = self.vision_pipeline.process_frame(frame)
        if not result["face_detected"] or result["looking_away"]:
            return PhysicalState.AWAY
        if result["eyes_closed"] and result["sleep_duration"] >= self.vision_pipeline.sleep_duration_threshold:
            return PhysicalState.SLEEPING
        return PhysicalState.ACTIVE

    def poll_semantic(self, title: Optional[str] = None) -> tuple[SemanticState, str]:
        """
        Polls Engineer 3's semantic pipeline with caching.
        Returns: (SemanticState, window_title)
        """
        if title is None:
            title = eng3.get_active_window_title()

        if not title or title.strip() in ("Desktop / Idle", "Task Switching", ""):
            return SemanticState.IDLE_DESKTOP, title

        # Check Cache first
        cached = self.semantic_cache.get(title)
        if cached:
            raw_classification = cached
        else:
            raw_classification = eng3.get_semantic_state(
                window_title=title, model=self.ollama_model
            )
            self.semantic_cache.set(title, raw_classification)

        state = (
            SemanticState.EDUCATIONAL
            if raw_classification == "EDUCATIONAL"
            else SemanticState.DISTRACTION
        )
        return state, title

    def run_step(self, frame=None, window_title=None, current_time=None) -> AttentionState:
        """
        Executes a single discrete step combining vision capture, window scrape, and evaluation.
        """
        physical = self.poll_vision(frame=frame)
        semantic, title = self.poll_semantic(title=window_title)
        return self.evaluate_tick(physical, semantic, window_title=title, current_time=current_time)

    def start_daemon(self, tick_interval: float = 1.0):
        """
        Spawns the background monitoring daemon loops.
        """
        if self.is_running:
            return

        self.is_running = True
        daemon_thread = threading.Thread(target=self._daemon_loop, args=(tick_interval,), daemon=True)
        self._threads.append(daemon_thread)
        daemon_thread.start()

    def _daemon_loop(self, tick_interval: float):
        last_tick = time.time()
        while self.is_running:
            now = time.time()
            delta = now - last_tick
            last_tick = now

            try:
                frame = self.vision_pipeline._get_camera_frame() if self.use_camera else None
                state = self.run_step(frame=frame, current_time=now)
                self.telemetry.update(state, delta)
            except Exception as e:
                print(f"[Orchestrator Daemon Error] {e}")

            time.sleep(tick_interval)

    def stop_daemon(self):
        """Gracefully halts the orchestrator daemon and releases camera resources."""
        self.is_running = False
        if self.is_enforcement_active:
            self._trigger_unblock()
        self.vision_pipeline.close()


def create_orchestrator(
    distraction_grace_period: float = 10.0,
    recovery_period: float = 5.0,
    hosts_path: Optional[str] = None,
    use_camera: bool = True
) -> DemonOrchestrator:
    """Factory function for initializing the unified Demon system daemon."""
    return DemonOrchestrator(
        distraction_grace_period=distraction_grace_period,
        recovery_period=recovery_period,
        hosts_path=hosts_path,
        use_camera=use_camera
    )

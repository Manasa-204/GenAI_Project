"""
test_checkpoint_2.py - Integration Checkpoint 2: Orchestration & State Fusion Tests
Validates:
[x] Multi-modal Fusion: Combines Physical (Eng 2) and Semantic (Eng 3) states into AttentionState.
[x] Semantic Cache: Avoids redundant Ollama SLM roundtrips for repeated window titles.
[x] Grace Period & Escalation: Distraction triggers warning countdown, then enforces OS block (Eng 4).
[x] Recovery Policy: Sustained focused activity cleanly unblocks the OS hosts file.
[x] Telemetry & Focus Analytics: Measures session duration, focus percentage, and block counts.
"""

import os
import time
import tempfile
import unittest

from orchestrator import (
    DemonOrchestrator,
    FusionEngine,
    PhysicalState,
    SemanticState,
    AttentionState,
    SemanticCache,
    SessionTelemetry,
)
import enforcement as eng4


class TestIntegrationCheckpoint2(unittest.TestCase):
    """
    Test suite for Phase 2: Master Multi-Modal Fusion and Orchestration Daemon.
    """

    def test_fusion_matrix_logic(self):
        """Verify the complete multi-modal state fusion truth table."""
        # Active + Educational -> FOCUSED
        self.assertEqual(
            FusionEngine.fuse(PhysicalState.ACTIVE, SemanticState.EDUCATIONAL),
            AttentionState.FOCUSED,
        )
        # Active + Neutral Desktop -> FOCUSED
        self.assertEqual(
            FusionEngine.fuse(PhysicalState.ACTIVE, SemanticState.IDLE_DESKTOP),
            AttentionState.FOCUSED,
        )
        # Active + Distraction -> ACTIVE_DISTRACTION
        self.assertEqual(
            FusionEngine.fuse(PhysicalState.ACTIVE, SemanticState.DISTRACTION),
            AttentionState.ACTIVE_DISTRACTION,
        )
        # Sleeping (eyes closed >= 2s) + Educational -> DROWSY
        self.assertEqual(
            FusionEngine.fuse(PhysicalState.SLEEPING, SemanticState.EDUCATIONAL),
            AttentionState.DROWSY,
        )
        # Sleeping + Distraction -> DROWSY
        self.assertEqual(
            FusionEngine.fuse(PhysicalState.SLEEPING, SemanticState.DISTRACTION),
            AttentionState.DROWSY,
        )
        # Away (head turned / no face) + Educational -> AWAY
        self.assertEqual(
            FusionEngine.fuse(PhysicalState.AWAY, SemanticState.EDUCATIONAL),
            AttentionState.AWAY,
        )
        # Away + Distraction -> IDLE_DISTRACTION
        self.assertEqual(
            FusionEngine.fuse(PhysicalState.AWAY, SemanticState.DISTRACTION),
            AttentionState.IDLE_DISTRACTION,
        )

    def test_semantic_cache_performance(self):
        """Verify semantic cache avoids redundant external API roundtrips."""
        cache = SemanticCache(ttl_seconds=60.0, max_size=5)

        self.assertIsNone(cache.get("YouTube - Calculus Tutorial"))

        cache.set("YouTube - Calculus Tutorial", "EDUCATIONAL")
        self.assertEqual(cache.get("YouTube - Calculus Tutorial"), "EDUCATIONAL")

        # Cache eviction when max_size exceeded
        for i in range(10):
            cache.set(f"Window {i}", "DISTRACTION")

        self.assertLessEqual(len(cache._cache), 5)
        # Oldest entry should be evicted
        self.assertIsNone(cache.get("YouTube - Calculus Tutorial"))

    def test_escalation_grace_period_and_enforcement(self):
        """
        PROVES:
        1. Distraction starts -> Warning callback receives remaining time.
        2. Within grace period -> Hosts file is NOT yet blocked.
        3. Exceeding grace period -> block_distractions() is automatically triggered.
        4. Domains become blocked in hosts file.
        """
        # Create an isolated temporary hosts file for safe non-destructive testing
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as temp_hosts:
            temp_hosts.write("127.0.0.1 localhost\n")
            temp_hosts_path = temp_hosts.name

        warnings_received = []
        enforcements_triggered = []

        def on_warning(time_left):
            warnings_received.append(time_left)

        def on_enforcement(is_blocked):
            enforcements_triggered.append(is_blocked)

        grace_period = 3.0  # 3 seconds grace period for test
        orchestrator = DemonOrchestrator(
            distraction_grace_period=grace_period,
            recovery_period=2.0,
            hosts_path=temp_hosts_path,
            use_camera=False,
            on_warning=on_warning,
            on_enforcement=on_enforcement,
        )

        try:
            base_time = 1000.0

            # t = 0.0s: User opens a distraction (Active + Distraction)
            state_0 = orchestrator.evaluate_tick(
                PhysicalState.ACTIVE,
                SemanticState.DISTRACTION,
                window_title="YouTube - Meme Compilation",
                current_time=base_time,
            )
            self.assertEqual(state_0, AttentionState.ACTIVE_DISTRACTION)
            self.assertFalse(orchestrator.is_enforcement_active)
            self.assertFalse(eng4.is_domain_blocked("youtube.com", hosts_path=temp_hosts_path))
            self.assertGreater(len(warnings_received), 0)

            # t = 1.5s: Still within grace period (< 3.0s)
            state_1 = orchestrator.evaluate_tick(
                PhysicalState.ACTIVE,
                SemanticState.DISTRACTION,
                window_title="YouTube - Meme Compilation",
                current_time=base_time + 1.5,
            )
            self.assertEqual(state_1, AttentionState.ACTIVE_DISTRACTION)
            self.assertFalse(orchestrator.is_enforcement_active)
            self.assertFalse(eng4.is_domain_blocked("youtube.com", hosts_path=temp_hosts_path))

            # t = 3.0s: Grace period expires -> OS Enforcement triggers!
            state_3 = orchestrator.evaluate_tick(
                PhysicalState.ACTIVE,
                SemanticState.DISTRACTION,
                window_title="YouTube - Meme Compilation",
                current_time=base_time + 3.0,
            )
            self.assertEqual(state_3, AttentionState.ACTIVE_DISTRACTION)
            self.assertTrue(orchestrator.is_enforcement_active, "Enforcement MUST be active after grace period")
            self.assertTrue(
                eng4.is_domain_blocked("youtube.com", hosts_path=temp_hosts_path),
                "youtube.com MUST be blocked in hosts file",
            )
            self.assertIn(True, enforcements_triggered)

        finally:
            if os.path.exists(temp_hosts_path):
                os.remove(temp_hosts_path)

    def test_recovery_policy_and_clean_unblock(self):
        """
        PROVES:
        1. When blocked, if user returns to FOCUSED activity, recovery timer starts.
        2. Once sustained for the recovery duration, unblock_distractions() is called.
        3. Hosts file entries are cleanly cleared.
        """
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as temp_hosts:
            temp_hosts.write("127.0.0.1 localhost\n")
            temp_hosts_path = temp_hosts.name

        enforcements = []

        orchestrator = DemonOrchestrator(
            distraction_grace_period=2.0,
            recovery_period=3.0,
            hosts_path=temp_hosts_path,
            use_camera=False,
            on_enforcement=lambda b: enforcements.append(b),
        )

        try:
            base_time = 2000.0

            # 1. Trigger block at t=2.0s
            orchestrator.evaluate_tick(
                PhysicalState.ACTIVE,
                SemanticState.DISTRACTION,
                window_title="Reddit - Memes",
                current_time=base_time,
            )
            orchestrator.evaluate_tick(
                PhysicalState.ACTIVE,
                SemanticState.DISTRACTION,
                window_title="Reddit - Memes",
                current_time=base_time + 2.0,
            )
            self.assertTrue(orchestrator.is_enforcement_active)
            self.assertTrue(eng4.is_domain_blocked("reddit.com", hosts_path=temp_hosts_path))

            # 2. User switches to Educational content at t=3.0s
            orchestrator.evaluate_tick(
                PhysicalState.ACTIVE,
                SemanticState.EDUCATIONAL,
                window_title="VS Code - project.py",
                current_time=base_time + 3.0,
            )
            # Still blocked during recovery probation
            self.assertTrue(orchestrator.is_enforcement_active)
            self.assertTrue(eng4.is_domain_blocked("reddit.com", hosts_path=temp_hosts_path))

            # 3. Sustained focus reaches t=6.0s (3.0s elapsed >= recovery_period) -> Unblocked!
            orchestrator.evaluate_tick(
                PhysicalState.ACTIVE,
                SemanticState.EDUCATIONAL,
                window_title="VS Code - project.py",
                current_time=base_time + 6.0,
            )
            self.assertFalse(orchestrator.is_enforcement_active, "Enforcement should now be cleared")
            self.assertFalse(
                eng4.is_domain_blocked("reddit.com", hosts_path=temp_hosts_path),
                "reddit.com should be unblocked in hosts file",
            )
            self.assertIn(False, enforcements)

        finally:
            if os.path.exists(temp_hosts_path):
                os.remove(temp_hosts_path)

    def test_session_telemetry_analytics(self):
        """Verify tracking of focus score, state durations, and intervention counts."""
        telemetry = SessionTelemetry()
        telemetry.update(AttentionState.FOCUSED, 30.0)
        telemetry.update(AttentionState.ACTIVE_DISTRACTION, 10.0)
        telemetry.update(AttentionState.DROWSY, 5.0)
        telemetry.update(AttentionState.AWAY, 15.0)
        telemetry.record_enforcement()

        summary = telemetry.get_summary()
        self.assertEqual(summary["focused_seconds"], 30.0)
        self.assertEqual(summary["distracted_seconds"], 10.0)
        self.assertEqual(summary["drowsy_seconds"], 5.0)
        self.assertEqual(summary["away_seconds"], 15.0)
        self.assertEqual(summary["enforcement_blocks_triggered"], 1)

        # Focus score = 30 / (30 + 10) * 100 = 75.0%
        self.assertEqual(summary["focus_score_percentage"], 75.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

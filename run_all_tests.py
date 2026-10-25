"""
run_all_tests.py - Master Verification Runner
Executes all unit, integration, and orchestration test suites across all 4 Engineers:
- Engineer 1: db_manager.py, logic_controller.py, system orchestration
- Engineer 2: vision_pipeline.py (MediaPipe Face Mesh, EAR within 2s, Head Pose)
- Engineer 3: semantic_pipeline.py (Ollama SLM classification, pygetwindow)
- Engineer 4: enforcement.py (Hosts file blocking, unblocking, DNS cache)
"""

import sys
import subprocess
import time

TEST_SUITES = [
    {
        "id": "CP1_ENG1",
        "name": "Eng 1: DB Scaffolding & Persistence Across Restarts",
        "command": [sys.executable, "test_db_manager.py"],
        "checkpoint": "Checkpoint 1 (Eng 1)"
    },
    {
        "id": "CP1_ENG2_3_4",
        "name": "Eng 2, 3, 4: Vision (EAR 2s), Ollama Classification & Hosts Blocking",
        "command": [sys.executable, "test_checkpoint_1.py"],
        "checkpoint": "Checkpoint 1 (Eng 2, 3, 4)"
    },
    {
        "id": "CP2_BRAIN",
        "name": "The Brain: AND Gate, Wikipedia Accrual & Vision Override",
        "command": [sys.executable, "test_logic_controller.py"],
        "checkpoint": "Checkpoint 2 (Sprint 2)"
    },
    {
        "id": "CP2_FUSION",
        "name": "Multi-Modal State Fusion, Semantic Cache & Telemetry",
        "command": [sys.executable, "test_checkpoint_2.py"],
        "checkpoint": "Checkpoint 2 (Fusion & Telemetry)"
    },
    {
        "id": "CP3_SYSTEM",
        "name": "System Orchestration: Zero-Balance, Earn-and-Burn & Graceful Exit",
        "command": [sys.executable, "test_system_orchestration.py"],
        "checkpoint": "Checkpoint 3 (Sprint 3 & 4)"
    }
]


def run_all(verbose: bool = True):
    print("=" * 70)
    print("DEMON STUDY MONITOR - MASTER TEST RUNNER ACROSS ALL 4 ENGINEERS")
    print("=" * 70)

    results = []
    total_start = time.time()

    for idx, suite in enumerate(TEST_SUITES, 1):
        print(f"\n[{idx}/{len(TEST_SUITES)}] Running {suite['checkpoint']}: {suite['name']}...")
        start_t = time.time()
        proc = subprocess.run(suite["command"], capture_output=True, text=True)
        duration = round(time.time() - start_t, 3)
        passed = (proc.returncode == 0)

        results.append({
            "id": suite["id"],
            "name": suite["name"],
            "checkpoint": suite["checkpoint"],
            "passed": passed,
            "duration": duration,
            "stdout": proc.stdout,
            "stderr": proc.stderr
        })

        if passed:
            print(f"    -> [PASS] Passed in {duration}s")
        else:
            print(f"    -> [FAIL] Failed in {duration}s (Exit code: {proc.returncode})")
            if verbose:
                print("--- Output ---")
                print(proc.stdout)
                print(proc.stderr)

    total_duration = round(time.time() - total_start, 2)
    passed_count = sum(1 for r in results if r["passed"])

    print("\n" + "=" * 70)
    print(f"SUMMARY: {passed_count}/{len(TEST_SUITES)} Test Suites Passed ({total_duration}s)")
    print("=" * 70)
    for r in results:
        badge = "[PASS]" if r["passed"] else "[FAIL]"
        print(f"  {badge:6s} | {r['duration']:5.2f}s | {r['checkpoint']:25s} | {r['name']}")
    print("=" * 70)

    return {
        "total": len(TEST_SUITES),
        "passed": passed_count,
        "failed": len(TEST_SUITES) - passed_count,
        "duration_seconds": total_duration,
        "suites": results
    }


if __name__ == "__main__":
    summary = run_all()
    sys.exit(0 if summary["failed"] == 0 else 1)

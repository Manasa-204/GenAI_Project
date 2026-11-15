"""
run_all_tests.py - Master Verification Runner (Demon Study Monitor)
Executes all 9 automated unit, integration, and orchestration test suites:
1. Checkpoint 1 (Eng 1): DB Scaffolding & Persistence Across Restarts
2. Checkpoint 1 (Eng 2, 3, 4): Vision (EAR 2s), Ollama Classification & Hosts Blocking
3. Checkpoint 2 (Sprint 2): The Brain: AND Gate, Wikipedia Accrual & Vision Override
4. Checkpoint 2 (Fusion & Telemetry): Multi-Modal State Fusion, Semantic Cache & Telemetry
5. Checkpoint 3 (Sprint 3 & 4): System Orchestration: Zero-Balance, Earn-and-Burn & Graceful Exit
6. Enforcement & 3D Learning: Primary User Lock, 3D Kinematics, Mobile Distraction & YouTube Enforcement
7. Home Screen PIN & Task Security: Task Definition & YouTube Distraction Locking
8. Dual-View Architecture: Shared SQLite database, multi-process sync, and REST API payload integrity
9. Master RBAC & Policy Engine: Master PIN hashing (PBKDF2), policy curfew/quota evaluation, and security alerts
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
    },
    {
        "id": "ENF_ATTENTION",
        "name": "Primary User Lock, 3D Kinematics, Mobile Distraction & YouTube Enforcement",
        "command": [sys.executable, "test_enforcement_cases.py"],
        "checkpoint": "Enforcement & 3D Learning"
    },
    {
        "id": "PIN_SECURITY",
        "name": "Home Screen PIN Security, Task Definition & YouTube Distraction Locking",
        "command": [sys.executable, "test_home_screen_pin.py"],
        "checkpoint": "PIN & YouTube Security"
    },
    {
        "id": "DUAL_VIEW",
        "name": "Dual-View Architecture, Multi-Process Sync & REST API Payload Integrity",
        "command": [sys.executable, "test_dual_view_architecture.py"],
        "checkpoint": "Dual-View Architecture"
    },
    {
        "id": "MASTER_FEATURES",
        "name": "Master RBAC, Granular Policy Quotas, Reticle Filter & 10s Quality Score",
        "command": [sys.executable, "test_master_prompt_features.py"],
        "checkpoint": "Master RBAC & Policies"
    }
]


def run_all(verbose: bool = True):
    print("=" * 75)
    print("DEMON STUDY MONITOR - MASTER TEST RUNNER ACROSS ALL 9 EXPANSION SUITES")
    print("=" * 75)

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

    print("\n" + "=" * 75)
    print(f"SUMMARY: {passed_count}/{len(TEST_SUITES)} Test Suites Passed ({total_duration}s)")
    print("=" * 75)
    for r in results:
        badge = "[PASS]" if r["passed"] else "[FAIL]"
        print(f"  {badge:6s} | {r['duration']:5.2f}s | {r['checkpoint']:28s} | {r['name']}")
    print("=" * 75)

    return {
        "total": len(TEST_SUITES),
        "passed": passed_count,
        "failed": len(TEST_SUITES) - passed_count,
        "duration": total_duration,
        "results": results
    }


if __name__ == "__main__":
    summary = run_all(verbose=True)
    sys.exit(0 if summary["failed"] == 0 else 1)

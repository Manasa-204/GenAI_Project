"""
test_db_manager.py
------------------
Unit test suite and Checkpoint 1 verification for Engineer 1.

Verifies:
1. Schema creation (user_state and time_logs).
2. Balance queries and updates (+delta and -delta).
3. Zero-clamping behavior (preventing invalid negative time).
4. Transaction logging integrity.
5. Integration Checkpoint 1: Proves database persistence across script/process restarts.
"""

import os
import sys
import tempfile
import subprocess
from db_manager import (
    init_db,
    get_current_balance,
    update_balance,
    get_recent_logs,
    reset_balance,
)

def run_tests():
    print("=" * 60)
    print("RUNNING UNIT TESTS FOR db_manager.py (Engineer 1 - Task 1.1)")
    print("=" * 60)

    # Use a temporary database file for isolated testing
    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, "test_study_monitor.db")
    print(f"[*] Temporary Test DB: {test_db}")

    try:
        # Test 1: Initialization
        init_db(test_db)
        initial_balance = get_current_balance(test_db)
        assert initial_balance == 0, f"Expected 0, got {initial_balance}"
        print(" [PASS] Test 1: Database initialized with 0 balance.")

        # Test 2: Accrue balance
        bal1 = update_balance(+10, reason="study_session_1", db_path=test_db)
        assert bal1 == 10, f"Expected 10, got {bal1}"
        assert get_current_balance(test_db) == 10
        print(" [PASS] Test 2: Accrued +10 units successfully (Balance = 10).")

        # Test 3: Additional increments
        bal2 = update_balance(+5, reason="study_session_2", db_path=test_db)
        assert bal2 == 15, f"Expected 15, got {bal2}"
        print(" [PASS] Test 3: Incremented +5 units (Balance = 15).")

        # Test 4: Drain balance
        bal3 = update_balance(-4, reason="break_distraction", db_path=test_db)
        assert bal3 == 11, f"Expected 11, got {bal3}"
        print(" [PASS] Test 4: Drained -4 units (Balance = 11).")

        # Test 5: Clamping at 0
        bal4 = update_balance(-50, reason="excessive_distraction", db_path=test_db)
        assert bal4 == 0, f"Expected clamped 0, got {bal4}"
        print(" [PASS] Test 5: Clamped minimum at 0 on excessive drain.")

        # Test 6: Verify time logs
        logs = get_recent_logs(limit=10, db_path=test_db)
        assert len(logs) >= 4, f"Expected at least 4 logs, got {len(logs)}"
        print(f" [PASS] Test 6: time_logs recorded {len(logs)} transactions successfully.")

        # Test 7: Reset balance
        reset_val = reset_balance(25, db_path=test_db)
        assert reset_val == 25
        assert get_current_balance(test_db) == 25
        print(" [PASS] Test 7: Reset balance to 25 verified.")

        print("\n" + "=" * 60)
        print("INTEGRATION CHECKPOINT 1: PERSISTENCE ACROSS SCRIPT RESTARTS")
        print("=" * 60)
        
        # We will write a balance using a subprocess, terminate the process,
        # and then read the balance in a SECOND fresh subprocess.
        script_writer = (
            f"import sys; from db_manager import update_balance; "
            f"update_balance(77, reason='process_A', db_path=r'{test_db}')"
        )
        p1 = subprocess.run([sys.executable, "-c", script_writer], capture_output=True, text=True)
        assert p1.returncode == 0, f"Process 1 failed: {p1.stderr}"
        print(" [->] Process A started, updated balance to 77, and exited cleanly.")

        # Process B reads the balance
        script_reader = (
            f"import sys; from db_manager import get_current_balance; "
            f"bal = get_current_balance(db_path=r'{test_db}'); "
            f"sys.exit(0 if bal == 102 else 1)"  # 25 + 77 = 102
        )
        p2 = subprocess.run([sys.executable, "-c", script_reader], capture_output=True, text=True)
        assert p2.returncode == 0, f"Process B failed to verify persisted state. Exit code: {p2.returncode}"
        print(" [->] Process B started in fresh Python environment and confirmed balance = 102.")
        print(" [PASS] CHECKPOINT 1 CLEARED: Database retains state after script restarts!\n")

    finally:
        # Clean up temporary test files
        if os.path.exists(test_db):
            os.remove(test_db)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)

if __name__ == "__main__":
    run_tests()

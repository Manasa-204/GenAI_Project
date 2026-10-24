"""
test_system_orchestration.py
----------------------------
Integration Checkpoint 3 Verification for Engineer 1.

Verifies:
1. The Zero-Balance Test:
   - Start with balance = 0.
   - Try to open Reddit/distraction.
   - System triggers block_distractions().
2. The Earn-and-Burn Test:
   - Effective study session increases balance > 0.
   - Access to distraction is unblocked.
   - User looks away/burns time until balance drops <= 0.
   - System automatically blocks distraction again.
3. Graceful Shutdown Verification:
   - Verifies cleanup_on_exit() unblocks distractions so user is never locked out.
"""

import os
import tempfile
import db_manager
import logic_controller
import vision_pipeline
import semantic_pipeline
import enforcement
import main


def run_tests():
    print("=" * 65)
    print("RUNNING CHECKPOINT 3: SYSTEM ORCHESTRATION & ENFORCEMENT")
    print("=" * 65)

    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, "test_orchestration.db")
    test_csv = os.path.join(temp_dir, "test_research.csv")

    try:
        # -------------------------------------------------------------
        # TEST 1: The Zero-Balance Test
        # -------------------------------------------------------------
        print("\n[*] Starting Checkpoint 3 - Test 1: The Zero-Balance Test...")
        # Start system with 0 balance
        db_manager.reset_balance(0, db_path=test_db)
        enforcement.unblock_distractions()
        assert not enforcement.is_distraction_blocked()

        # User attempts to open Reddit (DISTRACTION) with 0 balance
        vision_pipeline.set_mock_vision_state("ACTIVE")
        semantic_pipeline.set_mock_semantic_state("DISTRACTION")

        step1 = main.run_orchestrator_step(db_path=test_db, csv_path=test_csv)

        assert step1["new_balance"] == 0, f"Expected 0 balance, got {step1['new_balance']}"
        assert step1["is_blocked"] is True, "System failed to block distraction with 0 balance!"
        assert enforcement.is_distraction_blocked() is True
        print(" [PASS] Checkpoint 3 - Test 1 Passed: Zero-Balance Reddit attempt immediately blocked!")

        # -------------------------------------------------------------
        # TEST 2: The Earn-and-Burn Test
        # -------------------------------------------------------------
        print("\n[*] Starting Checkpoint 3 - Test 2: The Earn-and-Burn Test...")
        # Step A: Study effectively (ACTIVE + EDUCATIONAL) to accrue balance
        vision_pipeline.set_mock_vision_state("ACTIVE")
        semantic_pipeline.set_mock_semantic_state("EDUCATIONAL")

        print("  -> Studying to accrue balance...")
        for _ in range(3):
            step_earn = main.run_orchestrator_step(db_path=test_db, csv_path=test_csv)
        
        current_bal = db_manager.get_current_balance(test_db)
        assert current_bal == 3, f"Expected balance of 3, got {current_bal}"
        assert step_earn["is_blocked"] is False, "Distraction should be unblocked with positive balance!"
        print(f"  [+] Accrued balance: {current_bal} units. Distractions unblocked.")

        # Step B: User opens distraction (DISTRACTION + ACTIVE) - should remain accessible while balance > 0
        semantic_pipeline.set_mock_semantic_state("DISTRACTION")
        print("  -> User opens distraction. Burning accrued time...")
        
        # Cycle 1: Balance 3 -> 2 (unblocked)
        burn1 = main.run_orchestrator_step(db_path=test_db, csv_path=test_csv)
        assert burn1["new_balance"] == 2
        assert burn1["is_blocked"] is False

        # Cycle 2: Balance 2 -> 1 (unblocked)
        burn2 = main.run_orchestrator_step(db_path=test_db, csv_path=test_csv)
        assert burn2["new_balance"] == 1
        assert burn2["is_blocked"] is False

        # Cycle 3: Balance 1 -> 0 (Drained to 0 -> MUST BLOCK!)
        burn3 = main.run_orchestrator_step(db_path=test_db, csv_path=test_csv)
        assert burn3["new_balance"] == 0
        assert burn3["is_blocked"] is True, "System must block distraction when balance hits 0!"
        assert enforcement.is_distraction_blocked() is True
        print(" [PASS] Checkpoint 3 - Test 2 Passed: Earn-and-Burn verified. System re-blocked distraction when balance drained to 0!")

        # -------------------------------------------------------------
        # TEST 3: Graceful Shutdown (Task 4.2)
        # -------------------------------------------------------------
        print("\n[*] Starting Test 3: Graceful Shutdown Cleanup...")
        assert enforcement.is_distraction_blocked() is True
        main.cleanup_on_exit()
        assert enforcement.is_distraction_blocked() is False, "Cleanup failed to unblock distractions!"
        print(" [PASS] Test 3 Passed: Graceful shutdown guaranteed unblocking of system.")

        print("\n" + "=" * 65)
        print(" [ALL PASS] CHECKPOINT 3 CLEARED: ORCHESTRATION & ENFORCEMENT VERIFIED!")
        print("=" * 65)

    finally:
        for f in [test_db, test_csv]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


if __name__ == "__main__":
    run_tests()

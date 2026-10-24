"""
test_logic_controller.py
------------------------
Unit tests and Checkpoint 2 verification for Engineer 1.

Verifies:
1. The AND Gate Truth Table (Task 2.3).
2. Checkpoint 2 Test 1: User studying Wikipedia + Eyes open -> "Both Active: Accruing Time" & balance increases.
3. Checkpoint 2 Test 2: User on Wikipedia + Eyes closed -> Balance stops increasing (Vision override).
4. Distraction scenario: Social media -> Balance drains.
5. Sensor fault tolerance: Logic controller does not crash on sensor errors.
6. Research data logging: Confirms entries are correctly logged to CSV.
"""

import os
import csv
import tempfile
import io
import sys
from contextlib import redirect_stdout

import db_manager
import logic_controller
import vision_pipeline
import semantic_pipeline


def run_tests():
    print("=" * 65)
    print("RUNNING LOGIC CONTROLLER & CHECKPOINT 2 VERIFICATION")
    print("=" * 65)

    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, "test_checkpoint2.db")
    test_csv = os.path.join(temp_dir, "test_research_data.csv")

    try:
        # Initialize DB and set initial balance to 10
        db_manager.reset_balance(10, db_path=test_db)
        assert db_manager.get_current_balance(test_db) == 10

        # -------------------------------------------------------------
        # CHECKPOINT 2 - TEST 1: Wikipedia + Eyes Open (Both Active)
        # -------------------------------------------------------------
        print("\n[*] Running Checkpoint 2 - Test 1: Active + Educational...")
        vision_pipeline.set_mock_vision_state("ACTIVE")
        semantic_pipeline.set_mock_semantic_state("EDUCATIONAL")

        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            res1 = logic_controller.evaluate_cycle(db_path=test_db, csv_path=test_csv)
        
        output_text = captured_output.getvalue()
        assert "Both Active: Accruing Time" in output_text, f"Expected output message not found: {output_text}"
        assert res1["delta"] == +1, f"Expected +1 delta, got {res1['delta']}"
        assert res1["new_balance"] == 11, f"Expected balance to increase to 11, got {res1['new_balance']}"
        print(" [PASS] Checkpoint 2 - Test 1 Passed: Console printed 'Both Active: Accruing Time' and balance increased (10 -> 11).")

        # -------------------------------------------------------------
        # CHECKPOINT 2 - TEST 2: Wikipedia + Eyes Closed (Vision Override)
        # -------------------------------------------------------------
        print("\n[*] Running Checkpoint 2 - Test 2: Inactive/Eyes Closed + Educational...")
        vision_pipeline.set_mock_vision_state("IDLE")  # Eyes closed / away
        semantic_pipeline.set_mock_semantic_state("EDUCATIONAL")

        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            res2 = logic_controller.evaluate_cycle(db_path=test_db, csv_path=test_csv)

        output_text2 = captured_output.getvalue()
        assert "Vision override" in output_text2, f"Expected vision override output: {output_text2}"
        assert res2["delta"] == -1, f"Expected -1 delta, got {res2['delta']}"
        assert res2["new_balance"] == 10, f"Expected balance to decrease to 10, got {res2['new_balance']}"
        print(" [PASS] Checkpoint 2 - Test 2 Passed: Vision override triggered; balance stopped increasing and decreased (11 -> 10).")

        # -------------------------------------------------------------
        # TEST 3: Distraction (Reddit / YouTube Meme)
        # -------------------------------------------------------------
        print("\n[*] Running Test 3: Eyes Open + Distraction...")
        vision_pipeline.set_mock_vision_state("ACTIVE")
        semantic_pipeline.set_mock_semantic_state("DISTRACTION")

        res3 = logic_controller.evaluate_cycle(db_path=test_db, csv_path=test_csv)
        assert res3["delta"] == -1
        assert res3["new_balance"] == 9
        print(" [PASS] Test 3 Passed: Distraction drained balance (10 -> 9).")

        # -------------------------------------------------------------
        # TEST 4: Fault Tolerance (Sensor Crashes/Exceptions)
        # -------------------------------------------------------------
        print("\n[*] Running Test 4: Fault tolerance against sensor exceptions...")
        # Simulate broken pipeline methods
        class BrokenSensor:
            def get_vision_state(self):
                raise RuntimeError("Camera disconnected unexpectedly!")
        
        orig_vp = logic_controller.vision_pipeline
        logic_controller.vision_pipeline = BrokenSensor()
        
        # Controller must handle exception and not crash
        res_safe = logic_controller.evaluate_cycle(db_path=test_db, csv_path=test_csv)
        assert res_safe["vision_state"] == "IDLE", "Controller should safely default to IDLE on sensor crash."
        logic_controller.vision_pipeline = orig_vp
        print(" [PASS] Test 4 Passed: Handled sensor crash gracefully without dying.")

        # -------------------------------------------------------------
        # TEST 5: Research CSV Logging Verification (Phase 4.1)
        # -------------------------------------------------------------
        print("\n[*] Running Test 5: Research data CSV output validation...")
        assert os.path.exists(test_csv), "research_data.csv should exist."
        with open(test_csv, mode="r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            headers = reader[0]
            assert "vision_state" in headers
            assert "semantic_state" in headers
            assert "verdict" in headers
            assert "current_balance" in headers
            # Check row count: 1 header + 4 evaluations = 5 rows
            assert len(reader) == 5, f"Expected 5 rows in CSV, got {len(reader)}"
        print(f" [PASS] Test 5 Passed: research_data.csv properly formatted with {len(reader)-1} logged entries.")

        print("\n" + "=" * 65)
        print(" [ALL PASS] CHECKPOINT 2 CLEARED: THE BRAIN & LOGIC FUSION VERIFIED!")
        print("=" * 65)

    finally:
        # Cleanup temp directory
        for f in [test_db, test_csv]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)

if __name__ == "__main__":
    run_tests()

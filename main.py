"""
main.py
-------
Engineer 1 (Data & Logic - Lead)
Final System Orchestrator for the AI-Driven Contextual Study Monitor.

Implements:
- Task 3.1: Triggering OS Enforcement based on DB Balance and Semantic State.
- Task 4.2: Graceful Shutdown guaranteeing unblock_distractions() on exit.
- Full cycle orchestration tying together:
    * db_manager.py
    * logic_controller.py
    * vision_pipeline.py
    * semantic_pipeline.py
    * enforcement.py
"""

import sys
import time
import signal
import atexit
import argparse
from typing import Optional

import db_manager
import logic_controller
import enforcement


_cleaned_up = False

def cleanup_on_exit():
    """
    Task 4.2: Graceful Shutdown Handler.
    Guarantees that distractions are unblocked upon program exit or crash,
    preventing the user from being locked out of websites.
    """
    global _cleaned_up
    if _cleaned_up:
        return
    _cleaned_up = True
    print("\n[main] Executing safe shutdown cleanup...")
    try:
        enforcement.unblock_distractions()
        print("[main] Distractions safely unblocked.")
    except Exception as e:
        print(f"[main] Warning during cleanup: {e}", file=sys.stderr)


# Register exit handlers for unexpected termination
atexit.register(cleanup_on_exit)

def signal_handler(signum, frame):
    """Handles SIGINT (Ctrl+C) and SIGTERM cleanly."""
    print(f"\n[main] Termination signal received ({signum}).")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, signal_handler)


def run_orchestrator_step(
    db_path: Optional[str] = None,
    csv_path: Optional[str] = None
) -> dict:
    """
    Executes a single orchestrated step:
    1. Evaluates logic cycle (AND gate + updates DB + logs CSV).
    2. Checks current balance and semantic state.
    3. Triggers enforcement rules (Task 3.1):
       - If balance <= 0 and semantic_state == "DISTRACTION":
             enforcement.block_distractions()
       - If balance > 0:
             enforcement.unblock_distractions()
    """
    # 1. Step the logic controller
    result = logic_controller.evaluate_cycle(db_path=db_path, csv_path=csv_path)
    current_balance = result["new_balance"]
    semantic_state = result["semantic_state"]

    # 2. Apply enforcement rules
    if current_balance <= 0 and semantic_state == "DISTRACTION":
        print(f"[main] Enforcement Rule Triggered: Balance <= 0 ({current_balance}s) & Distraction active.")
        enforcement.block_distractions()
    elif current_balance > 0:
        if enforcement.is_distraction_blocked():
            print(f"[main] Balance positive ({current_balance}s): Restoring access.")
        enforcement.unblock_distractions()

    return {
        **result,
        "is_blocked": enforcement.is_distraction_blocked()
    }


def main():
    parser = argparse.ArgumentParser(
        description="AI-Driven Contextual Study Monitor - Orchestrator"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds (default: 5.0)"
    )
    parser.add_argument(
        "--reset-balance",
        type=int,
        default=None,
        help="Reset initial balance to specified value before starting"
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Run for N cycles and then stop (useful for testing)"
    )
    args = parser.parse_args()

    print("=" * 65)
    print("AI-DRIVEN CONTEXTUAL STUDY MONITOR - SYSTEM ORCHESTRATOR")
    print("Engineer 1 (Data & Logic - Lead)")
    print("=" * 65)

    # Initialize Database
    db_manager.init_db()
    if args.reset_balance is not None:
        db_manager.reset_balance(args.reset_balance)
        print(f"[main] Balance reset to: {args.reset_balance} units")

    balance = db_manager.get_current_balance()
    print(f"[main] System starting. Active Balance: {balance} units.")
    print(f"[main] Polling loop running every {args.poll_interval}s. Press Ctrl+C to quit.")

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            print(f"\n--- [Cycle #{cycle_count}] ---")
            step = run_orchestrator_step()
            print(f"Status: Balance={step['new_balance']} | Blocked={step['is_blocked']}")

            if args.max_cycles and cycle_count >= args.max_cycles:
                print(f"[main] Completed {args.max_cycles} cycles. Stopping.")
                break

            time.sleep(args.poll_interval)
            
    except KeyboardInterrupt:
        print("\n[main] KeyboardInterrupt received.")
    finally:
        cleanup_on_exit()


if __name__ == "__main__":
    main()

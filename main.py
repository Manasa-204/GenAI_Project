"""
main.py - Headless Background Tracker & Orchestrator
---------------------------------------------------
Acts strictly as a headless orchestrator running in the background.
Initializes:
1. db_manager.py: Shared SQLite database (study_monitor.db)
2. user_tracker.py: Windows process & foreground application tracking
3. enforcement.py: Rule enforcement, process termination & distraction blocking

Runs in an efficient continuous loop (while True) with optimized sleep intervals
to maintain negligible CPU usage (<0.1%).
"""

import sys
import time
import os
import signal
import atexit
import argparse
from typing import Optional

import db_manager
import user_tracker
import enforcement

_is_running = True
_cleaned_up = False


def cleanup_on_exit():
    """Safe exit handler to ensure hosts file and database remain consistent."""
    global _cleaned_up
    if not _cleaned_up:
        _cleaned_up = True
        try:
            # When stopping the service cleanly, restore domain access if child has balance
            balance = db_manager.get_current_balance()
            if balance > 0:
                enforcement.unblock_distractions()
        except Exception:
            pass


atexit.register(cleanup_on_exit)


def signal_handler(signum, frame):
    """Handles OS termination signals cleanly."""
    global _is_running
    _is_running = False
    cleanup_on_exit()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, signal_handler)


def run_orchestrator_cycle(
    tracker: user_tracker.WindowsProcessTracker,
    interval: float = 1.0,
    db_path: Optional[str] = None,
    verbose: bool = False
) -> dict:
    """
    Executes a single headless orchestration cycle:
    1. Inspects foreground window and running process.
    2. Logs process usage to study_monitor.db.
    3. Decrements active screen time balance if consuming time.
    4. Enforces parental restrictions and terminates blocked applications.
    """
    # 1. Track active application
    tick = tracker.track_tick(delta_seconds=interval)
    proc_name = tick.get("process_name", "")
    pid = tick.get("pid", 0)

    # 2. Decrement remaining allowed time if active and balance > 0
    balance = db_manager.get_current_balance(db_path=db_path)
    if balance > 0:
        # Subtract the tick interval
        new_balance = db_manager.update_balance(
            delta=-int(round(interval)),
            reason=f"Active: {proc_name or 'Idle'}",
            clamp_min=0,
            db_path=db_path
        )
    else:
        new_balance = balance

    # 3. Enforce parental rules (Process termination & domain blocking)
    enf_result = enforcement.enforce_rules(
        current_proc_name=proc_name,
        current_pid=pid,
        db_path=db_path
    )

    if verbose and (proc_name or enf_result["actions_taken"]):
        actions = ", ".join(enf_result["actions_taken"]) if enf_result["actions_taken"] else "None"
        print(f"[Tracker] App: {proc_name:20s} | Bal: {new_balance:5d}s | Locked: {enf_result['is_locked']} | Actions: {actions}")

    return {
        "process_name": proc_name,
        "pid": pid,
        "balance": new_balance,
        "is_locked": enf_result["is_locked"],
        "actions_taken": enf_result["actions_taken"]
    }


def main():
    parser = argparse.ArgumentParser(description="Demon Headless Background Tracker Service")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds (default: 1.0s)")
    parser.add_argument("--verbose", action="store_true", help="Print debug information to console")
    parser.add_argument("--max-cycles", type=int, default=None, help="Stop after N cycles (for automated tests)")
    args = parser.parse_args()

    # 1. Initialize Shared Database
    db_manager.init_db()

    # 2. Initialize Process Monitor
    tracker = user_tracker.WindowsProcessTracker()

    if args.verbose:
        print("=" * 65)
        print(" DEMON HEADLESS BACKGROUND TRACKER STARTED")
        print(f" Polling Interval : {args.interval}s")
        print(f" Database Path    : {db_manager.DEFAULT_DB_PATH}")
        print("=" * 65)

    cycles = 0
    try:
        while _is_running:
            cycles += 1
            run_orchestrator_cycle(
                tracker=tracker,
                interval=args.interval,
                verbose=args.verbose
            )

            if args.max_cycles and cycles >= args.max_cycles:
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        pass
    finally:
        cleanup_on_exit()


if __name__ == "__main__":
    main()

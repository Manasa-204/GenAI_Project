"""
main.py - Demon Master Runtime & Live Attention HUD
Coordinates Engineer 1 (Logic), Engineer 2 (Vision), Engineer 3 (Semantic NLP), and Engineer 4 (OS Enforcement).

Usage:
  python main.py                    # Standard 5s polling orchestrator loop (safe mode)
  python main.py --poll-interval 1.0 --reset-balance 10 --max-cycles 6  # Fast demo mode
  python main.py --hud              # Run live Attention HUD console
  python main.py --enforce-real     # Live system hosts enforcement (Requires Administrator)
  python main.py --no-camera        # Headless mode without webcam
"""

import sys
import time
import os
import argparse
import atexit
import signal
import tempfile
from typing import Optional

import db_manager
import logic_controller
import enforcement
import enforcement as eng4

try:
    from orchestrator import DemonOrchestrator, PhysicalState
except ImportError:
    DemonOrchestrator = None
    PhysicalState = None


_cleaned_up = False


def cleanup_on_exit():
    """
    Task 4.2: Graceful Shutdown Handler.
    Guarantees that distractions are unblocked upon program exit or crash,
    preventing the user from being locked out of websites.
    """
    global _cleaned_up
    try:
        enforcement.unblock_distractions()
        if not _cleaned_up:
            _cleaned_up = True
            print("\n[main] Executing safe shutdown cleanup: Distractions unblocked.")
    except Exception as e:
        print(f"\n[main] Warning during cleanup: {e}", file=sys.stderr)


# Register exit handlers for unexpected termination
atexit.register(cleanup_on_exit)


def signal_handler(signum, frame):
    """Handles SIGINT (Ctrl+C) and SIGTERM cleanly."""
    print(f"\n[main] Termination signal received ({signum}). Shutting down gracefully...")
    cleanup_on_exit()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, signal_handler)


def run_orchestrator_step(
    db_path: Optional[str] = None,
    csv_path: Optional[str] = None
) -> dict:
    """
    Executes a single orchestrated step according to Eng 1 specification:
    1. Evaluates logic cycle (AND gate + updates DB + logs CSV).
    2. Checks current balance and semantic state.
    3. Triggers enforcement rules (Task 3.1):
       - If balance <= 0 and semantic_state == 'DISTRACTION':
             enforcement.block_distractions()
       - If balance > 0:
             enforcement.unblock_distractions()
    """
    result = logic_controller.evaluate_cycle(db_path=db_path, csv_path=csv_path)
    current_balance = result["new_balance"]
    semantic_state = result["semantic_state"]

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


def print_banner():
    banner = r"""
  ____  _____ __  __  ___  _   _ 
 |  _ \| ____|  \/  |/ _ \| \ | |
 | | | |  _| | |\/| | | | |  \| |  Multi-Agent Attention Daemon
 | |_| | |___| |  | | |_| | |\  |  [Eng 1: Logic | Eng 2: Vision | Eng 3: NLP | Eng 4: OS]
 |____/|_____|_|  |_|\___/|_| \_|
    """
    print(banner)


def run_hud_mode(args):
    """Runs the high-frequency HUD daemon with live attention scoring."""
    if DemonOrchestrator is None:
        print("[ERROR] DemonOrchestrator could not be imported from orchestrator.py.")
        sys.exit(1)

    is_admin = eng4.is_admin()
    if args.enforce_real:
        if not is_admin:
            print("[ERROR] --enforce-real was specified but this terminal is NOT running as Administrator.")
            print("Please reopen PowerShell or Terminal with 'Run as Administrator'.")
            sys.exit(1)
        hosts_path = None
        mode_desc = "[LIVE SYSTEM ENFORCEMENT - ADMIN]"
    else:
        temp_hosts = tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8")
        temp_hosts.write("# Demon Sandbox Hosts\n127.0.0.1 localhost\n::1 localhost\n")
        temp_hosts.close()
        hosts_path = temp_hosts.name
        mode_desc = f"[SAFE SANDBOX MODE] -> {hosts_path}"

    print(f"Mode: {mode_desc}")
    print(f"Distraction Grace Period: {args.grace_period}s | Recovery Period: {args.recovery_period}s")
    print(f"Webcam Active: {not args.no_camera}\n")
    print("Press Ctrl+C to stop.\n" + "-" * 70)

    def on_warning(seconds_left):
        print(f"\n  [!] WARNING: Distraction detected! OS Block in {seconds_left:.1f}s...")

    def on_enforcement(is_blocked):
        if is_blocked:
            print("\n  [>>>] ENFORCEMENT TRIGGERED: Predefined distraction domains BLOCKED.")
        else:
            print("\n  [<<<] RECOVERY CONFIRMED: Distraction domains UNBLOCKED. Focus restored.")

    orchestrator = DemonOrchestrator(
        distraction_grace_period=args.grace_period,
        recovery_period=args.recovery_period,
        hosts_path=hosts_path,
        use_camera=not args.no_camera,
        on_warning=on_warning,
        on_enforcement=on_enforcement,
    )

    try:
        last_time = time.time()
        while True:
            now = time.time()
            delta = now - last_time
            last_time = now

            if not args.no_camera:
                frame = orchestrator.vision_pipeline._get_camera_frame()
                physical = orchestrator.poll_vision(frame=frame)
                v_res = orchestrator.vision_pipeline.process_frame(frame)
                ear_str = f"EAR:{v_res['ear']:.2f}"
                pose_str = f"Yaw:{v_res['head_pose'][1]:.0f}°"
            else:
                physical = PhysicalState.ACTIVE
                ear_str = "EAR:N/A"
                pose_str = "Yaw:N/A"

            semantic, title = orchestrator.poll_semantic()
            short_title = (title[:30] + "..") if len(title) > 30 else title

            attention = orchestrator.evaluate_tick(
                physical, semantic, window_title=title, current_time=now
            )
            orchestrator.telemetry.update(attention, delta)

            state_tag = f"[{attention.value}]"
            block_tag = "[BLOCKED]" if orchestrator.is_enforcement_active else "[CLEAR]"
            telemetry = orchestrator.telemetry.get_summary()

            hud_line = (
                f"\r{state_tag:19s} {block_tag:8s} | "
                f"{ear_str:8s} {pose_str:8s} | "
                f"Window: \"{short_title:32s}\" | "
                f"Score: {telemetry['focus_score_percentage']:.0f}%"
            )
            print(hud_line, end="", flush=True)
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\nShutting down Demon orchestrator...")
    finally:
        orchestrator.stop_daemon()
        if hosts_path and os.path.exists(hosts_path) and not args.enforce_real:
            try:
                os.remove(hosts_path)
            except Exception:
                pass

        summary = orchestrator.telemetry.get_summary()
        print("\n" + "=" * 60)
        print(" SESSION FOCUS SUMMARY")
        print("=" * 60)
        print(f" Total Session Time : {summary['session_duration_seconds']}s")
        print(f" Focused Time       : {summary['focused_seconds']}s")
        print(f" Distracted Time    : {summary['distracted_seconds']}s")
        print(f" Drowsy Time        : {summary['drowsy_seconds']}s")
        print(f" Away Time          : {summary['away_seconds']}s")
        print(f" Final Focus Score  : {summary['focus_score_percentage']}%")
        print(f" Blocks Enforced    : {summary['enforcement_blocks_triggered']}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="AI-Driven Contextual Study Monitor - Orchestrator (Demon)"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds for standard cycle (default: 5.0)"
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
    parser.add_argument(
        "--enforce-real",
        action="store_true",
        help="Enforce OS hosts file directly on system C:\\Windows\\System32\\drivers\\etc\\hosts (Admin required)"
    )
    parser.add_argument(
        "--no-camera",
        action="store_true",
        help="Disable camera feed (test semantic scraping and enforcement only)"
    )
    parser.add_argument(
        "--hud",
        action="store_true",
        help="Run high-frequency live Attention HUD daemon"
    )
    parser.add_argument(
        "--grace-period",
        type=float,
        default=8.0,
        help="Distraction grace period in seconds before blocking (default: 8.0s)"
    )
    parser.add_argument(
        "--recovery-period",
        type=float,
        default=5.0,
        help="Focused recovery period in seconds before unblocking (default: 5.0s)"
    )
    args = parser.parse_args()

    if args.hud:
        run_hud_mode(args)
        return

    print_banner()

    # Initialize Database (Sprint 1)
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
        print("\n[main] Polling loop stopped by user.")
    finally:
        cleanup_on_exit()


if __name__ == "__main__":
    main()

"""
logic_controller.py
-------------------
Engineer 1 (Data & Logic - Lead)
Decision Engine ("The Brain") for the AI-Driven Contextual Study Monitor.

Implements:
- Task 2.1: Vision Integration (5-second polling loop without crashing)
- Task 2.2: Semantic Integration (Synchronous active window classification query)
- Task 2.3: The AND Gate decision logic & database balance updates
- Task 4.1: Research data logging to research_data.csv
"""

import os
import sys
import csv
import time
from datetime import datetime
from typing import Dict, Any, Optional

import db_manager

# Import sensory pipelines with safe fallbacks
try:
    import vision_pipeline
except ImportError:
    vision_pipeline = None

try:
    import semantic_pipeline
except ImportError:
    semantic_pipeline = None

DEFAULT_CSV_FILE = "research_data.csv"


def get_default_csv_path() -> str:
    """Returns local path in dev mode, or %LOCALAPPDATA%\\Demon in frozen .exe mode."""
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        demon_dir = os.path.join(appdata, "Demon")
        os.makedirs(demon_dir, exist_ok=True)
        return os.path.join(demon_dir, DEFAULT_CSV_FILE)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_CSV_FILE)


DEFAULT_CSV_PATH = get_default_csv_path()
DEFAULT_POLL_INTERVAL = 5.0  # seconds


def init_research_log(csv_path: Optional[str] = None) -> str:
    """Ensures the research CSV file exists and has appropriate headers."""
    target_path = csv_path or DEFAULT_CSV_PATH
    if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
        with open(target_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "vision_state",
                "semantic_state",
                "verdict",
                "balance_delta",
                "current_balance",
                "reason"
            ])
    return target_path


def log_research_entry(
    timestamp: str,
    vision_state: str,
    semantic_state: str,
    verdict: str,
    delta: int,
    balance: int,
    reason: str,
    csv_path: Optional[str] = None
) -> None:
    """Appends a single cycle event to the research dataset."""
    target_path = init_research_log(csv_path)
    with open(target_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            vision_state,
            semantic_state,
            verdict,
            delta,
            balance,
            reason
        ])


def read_vision_state_safe() -> str:
    """
    Safely queries the vision pipeline without allowing camera/mesh exceptions to crash the loop.
    Returns 'ACTIVE' or 'IDLE' (defaults to 'IDLE' if sensor fails).
    """
    if vision_pipeline and hasattr(vision_pipeline, "get_vision_state"):
        try:
            state = vision_pipeline.get_vision_state()
            if state in ("ACTIVE", "IDLE"):
                return state
        except Exception as e:
            print(f"[logic_controller] Warning: Vision sensor error: {e}")
            return "IDLE"
    return "IDLE"


def read_semantic_state_safe() -> str:
    """
    Safely queries the semantic pipeline without allowing OS/Ollama exceptions to crash the loop.
    Returns 'EDUCATIONAL' or 'DISTRACTION' (defaults to 'DISTRACTION' on failure).
    """
    if semantic_pipeline and hasattr(semantic_pipeline, "get_semantic_state"):
        try:
            state = semantic_pipeline.get_semantic_state()
            if state in ("EDUCATIONAL", "DISTRACTION"):
                return state
        except Exception as e:
            print(f"[logic_controller] Warning: Semantic sensor error: {e}")
            return "DISTRACTION"
    return "DISTRACTION"


def evaluate_cycle(
    vision_override: Optional[str] = None,
    semantic_override: Optional[str] = None,
    db_path: Optional[str] = None,
    csv_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes a single evaluation cycle:
    1. Reads physical state (vision) and digital state (semantic).
    2. Computes the AND Gate verdict:
       - (ACTIVE and EDUCATIONAL) -> +1 reward (Accruing Time)
       - (IDLE and EDUCATIONAL)   -> -1 drain (Vision override: user asleep/away)
       - (* and DISTRACTION)      -> -1 drain (Distraction active)
       - (IDLE and DISTRACTION)   -> -1 drain (Inactive distraction)
    3. Updates database balance.
    4. Logs to research_data.csv.
    """
    now_iso = datetime.now().isoformat()
    
    # 1. Acquire inputs
    vision_state = vision_override or read_vision_state_safe()
    semantic_state = semantic_override or read_semantic_state_safe()

    # 2. Evaluate the AND Gate
    if vision_state == "ACTIVE" and semantic_state == "EDUCATIONAL":
        verdict = "REWARD"
        delta = +1
        reason = "Both Active: Accruing Time"
        print(f"[{now_iso}] [SUCCESS] Both Active: Accruing Time (+{delta}s)")

    elif vision_state == "IDLE" and semantic_state == "EDUCATIONAL":
        verdict = "VISION_OVERRIDE"
        delta = -1
        reason = "Vision override: User idle/eyes closed despite educational window"
        print(f"[{now_iso}] [OVERRIDE] Inactive on Study Material (Vision override) ({delta}s)")

    elif semantic_state == "DISTRACTION":
        verdict = "DISTRACTION"
        delta = -1
        reason = "Distraction detected"
        print(f"[{now_iso}] [DRAIN] Distraction active ({delta}s)")

    else:
        verdict = "IDLE"
        delta = -1
        reason = "User idle and inactive"
        print(f"[{now_iso}] [DRAIN] Idle state ({delta}s)")

    # 3. Update persistent database balance
    new_balance = db_manager.update_balance(delta=delta, reason=reason, db_path=db_path)

    # 4. Log to research data CSV (Phase 4.1)
    log_research_entry(
        timestamp=now_iso,
        vision_state=vision_state,
        semantic_state=semantic_state,
        verdict=verdict,
        delta=delta,
        balance=new_balance,
        reason=reason,
        csv_path=csv_path
    )

    return {
        "timestamp": now_iso,
        "vision_state": vision_state,
        "semantic_state": semantic_state,
        "verdict": verdict,
        "delta": delta,
        "new_balance": new_balance,
        "reason": reason
    }


def run_logic_loop(
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_cycles: Optional[int] = None,
    db_path: Optional[str] = None,
    csv_path: Optional[str] = None
) -> None:
    """
    Main 5-second polling loop for Logic Fusion (Phase 2).
    Runs continuously until interrupted or max_cycles is reached.
    """
    print(f"[logic_controller] Starting Logic Fusion Engine (Poll interval: {poll_interval}s)...")
    init_research_log(csv_path)
    cycle_count = 0
    
    try:
        while True:
            cycle_count += 1
            print(f"\n--- Cycle #{cycle_count} ---")
            result = evaluate_cycle(db_path=db_path, csv_path=csv_path)
            print(f"Current Balance: {result['new_balance']} units")
            
            if max_cycles and cycle_count >= max_cycles:
                print(f"[logic_controller] Reached maximum cycles ({max_cycles}). Exiting loop.")
                break
                
            time.sleep(poll_interval)
            
    except KeyboardInterrupt:
        print("\n[logic_controller] Loop stopped by user.")


if __name__ == "__main__":
    run_logic_loop(poll_interval=2.0, max_cycles=3)

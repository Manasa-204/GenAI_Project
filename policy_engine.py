"""
policy_engine.py - Comprehensive Policy Engine, Time-Budgeting & Quotas
------------------------------------------------------------------------
Implements Feature 2:
1. Hard Block Enforcement (immediate termination & window minimization)
2. Curfew Window Schedules (e.g. 21:00 - 06:00)
3. Granular Daily Time Quotas per Target (app / domain)
4. Earn-and-Burn Integration with Master Study Balance
5. Midnight Quota Reset & Alert Dispatcher
"""

import sys
import time
from datetime import datetime, date
from typing import Optional, Dict, Any, Tuple

import db_manager
import enforcement

_last_reset_date = date.today()


def check_and_apply_midnight_reset(db_path: Optional[str] = None):
    """Automatically resets used_today_seconds across all policies at 00:00:00 local time."""
    global _last_reset_date
    today = date.today()
    if today != _last_reset_date:
        _last_reset_date = today
        with db_manager.get_db(db_path) as conn:
            conn.execute("UPDATE app_policies SET used_today_seconds = 0;")
            conn.commit()


def evaluate_target_policy(
    target_name: str,
    window_title: str = "",
    delta_seconds: int = 1,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates policy restrictions for an active process or web target:
    1. Midnight Reset
    2. Hard Block
    3. Curfew Window
    4. Daily Quota
    5. Earn-and-Burn Linkage
    """
    check_and_apply_midnight_reset(db_path=db_path)
    clean_target = target_name.strip().lower()

    with db_manager.get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM app_policies
            WHERE target_name = ? OR target_name = ? OR ? LIKE ('%' || target_name || '%');
        """, (clean_target, f"{clean_target}.exe", clean_target))
        policy = cursor.fetchone()

        if not policy:
            return {"verdict": "ALLOWED", "reason": "No policy configured", "policy": None}

        pol = dict(policy)
        if not pol.get("is_active", 1):
            return {"verdict": "ALLOWED", "reason": "Policy inactive", "policy": pol}

        # 1. HARD_BLOCK
        if pol["policy_type"] == "HARD_BLOCK":
            db_manager.dispatch_parent_alert(
                target_app=clean_target,
                event_type="UNAUTHORIZED_ATTEMPT",
                severity="CRITICAL",
                details=f"Student attempted to access permanently blacklisted app: {clean_target}",
                db_path=db_path
            )
            enforcement.terminate_process_by_name(clean_target)
            enforcement.enforce_active_distraction(window_title=window_title)
            return {
                "verdict": "BLOCKED_HARD",
                "reason": f"Target '{clean_target}' is permanently blacklisted.",
                "policy": pol
            }

        # 2. Curfew Window Check
        curfew_start = pol.get("curfew_start")
        curfew_end = pol.get("curfew_end")
        if curfew_start and curfew_end:
            now_time = datetime.now().strftime("%H:%M")
            if curfew_start <= curfew_end:
                in_curfew = (curfew_start <= now_time <= curfew_end)
            else:
                in_curfew = (now_time >= curfew_start or now_time <= curfew_end)

            if in_curfew:
                db_manager.dispatch_parent_alert(
                    target_app=clean_target,
                    event_type="UNAUTHORIZED_ATTEMPT",
                    severity="WARNING",
                    details=f"Curfew active for {clean_target} ({curfew_start} - {curfew_end})",
                    db_path=db_path
                )
                enforcement.terminate_process_by_name(clean_target)
                enforcement.enforce_active_distraction(window_title=window_title)
                return {
                    "verdict": "BLOCKED_CURFEW",
                    "reason": f"Curfew active for '{clean_target}' ({curfew_start} - {curfew_end}).",
                    "policy": pol
                }

        # 3. Daily Quota Check
        quota = pol.get("daily_quota_seconds", 0)
        used = pol.get("used_today_seconds", 0)
        if quota > 0 and used >= quota:
            db_manager.dispatch_parent_alert(
                target_app=clean_target,
                event_type="QUOTA_EXHAUSTED",
                severity="WARNING",
                details=f"Daily leisure quota exhausted for {clean_target}: {used // 60}m used",
                db_path=db_path
            )
            enforcement.terminate_process_by_name(clean_target)
            enforcement.enforce_active_distraction(window_title=window_title)
            return {
                "verdict": "BLOCKED_QUOTA_EXCEEDED",
                "reason": f"Daily quota of {quota // 60}m exceeded for '{clean_target}'.",
                "policy": pol
            }

        # 4. Earn-and-Burn Linkage: If balance is 0 and target is entertainment/gaming/social, shut down
        balance = db_manager.get_current_balance(db_path=db_path)
        cat = pol.get("category", "")
        if balance <= 0 and cat in ("GAMING", "SOCIAL", "VIDEO"):
            enforcement.terminate_process_by_name(clean_target)
            enforcement.enforce_active_distraction(window_title=window_title)
            return {
                "verdict": "BLOCKED_ZERO_BALANCE",
                "reason": f"Earned study balance is 0. Leisure app '{clean_target}' locked.",
                "policy": pol
            }

        return {
            "verdict": "ALLOWED",
            "reason": f"Active within policy ({used // 60}m / {quota // 60}m used today).",
            "policy": pol
        }


if __name__ == "__main__":
    print("[policy_engine] Initializing policy engine test...")
    eval_res = evaluate_target_policy("robloxplayerbeta.exe")
    print("  Roblox Policy Evaluation:", eval_res["verdict"], "-", eval_res["reason"])
    eval_youtube = evaluate_target_policy("youtube.com")
    print("  YouTube Policy Evaluation:", eval_youtube["verdict"], "-", eval_youtube["reason"])


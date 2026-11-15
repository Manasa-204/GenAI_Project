"""
db_manager.py
-------------
Demon Study Monitor - Database & State Management Module
Manages SQLite storage for:
- User study balance and time accrual logs
- Emergency Lockdown status and countdown
- Zero Tolerance Guard configuration
- Granular Application Policies & Quota Budgets
- Real-time Application Activity & Distribution Telemetry
- Focus Kinematics & Posture History
- Security & Tamper Alerts
- Master RBAC Security PIN (PBKDF2-hashed with '1323' master override)
"""

import sqlite3
import os
import sys
import time
import hashlib
import binascii
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager

DEFAULT_DB_FILE = "study_monitor.db"


def get_default_db_path() -> str:
    """Returns local path in dev mode, or %LOCALAPPDATA%\\Demon in frozen mode."""
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        demon_dir = os.path.join(appdata, "Demon")
        os.makedirs(demon_dir, exist_ok=True)
        return os.path.join(demon_dir, DEFAULT_DB_FILE)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_DB_FILE)


DEFAULT_DB_PATH = get_default_db_path()
_initialized_dbs = set()


@contextmanager
def get_db(db_path: Optional[str] = None):
    """
    Context manager that yields a SQLite connection with WAL mode and 30s timeout.
    Guarantees connection is closed promptly across multi-process access.
    """
    target_path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
    except Exception:
        pass
    try:
        yield conn
    finally:
        conn.close()


def hash_pin(pin: str) -> str:
    """Hashes a PIN using PBKDF2 with SHA-256 and a random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 100000)
    return f"{binascii.hexlify(salt).decode('ascii')}${binascii.hexlify(key).decode('ascii')}"


def verify_hash(pin: str, stored_hash: str) -> bool:
    """Verifies a PIN against a stored salt$hash string."""
    try:
        salt_hex, key_hex = stored_hash.split("$")
        salt = binascii.unhexlify(salt_hex.encode("ascii"))
        expected_key = binascii.unhexlify(key_hex.encode("ascii"))
        actual_key = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 100000)
        return actual_key == expected_key
    except Exception:
        return False


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes the database schema if tables do not already exist."""
    target_path = db_path or DEFAULT_DB_PATH
    if target_path in _initialized_dbs and os.path.exists(target_path):
        return

    dir_name = os.path.dirname(os.path.abspath(target_path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with get_db(target_path) as conn:
        cursor = conn.cursor()

        # 1. User State Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_balance INTEGER NOT NULL DEFAULT 0,
                study_time_today INTEGER NOT NULL DEFAULT 0,
                last_updated TEXT NOT NULL
            );
        """)

        # Migration: ensure study_time_today column exists if table was created in older version
        cursor.execute("PRAGMA table_info(user_state);")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if "study_time_today" not in existing_cols:
            try:
                cursor.execute("ALTER TABLE user_state ADD COLUMN study_time_today INTEGER NOT NULL DEFAULT 0;")
            except Exception:
                pass
        cursor.execute("""
            INSERT OR IGNORE INTO user_state (id, current_balance, study_time_today, last_updated)
            VALUES (1, 0, 0, ?)
        """, (datetime.now().isoformat(),))

        # 2. Time Accrual / Drain Logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS time_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT
            );
        """)

        # 3. Application Settings & Configuration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            );
        """)

        # 4. Emergency Lockdown State
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emergency_lockdown (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_active INTEGER NOT NULL DEFAULT 0,
                start_time REAL NOT NULL DEFAULT 0.0,
                duration_seconds INTEGER NOT NULL DEFAULT 900,
                end_time REAL NOT NULL DEFAULT 0.0,
                reason TEXT NOT NULL DEFAULT 'Study Session',
                zero_tolerance INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO emergency_lockdown
            (id, is_active, start_time, duration_seconds, end_time, reason, zero_tolerance, updated_at)
            VALUES (1, 0, 0.0, 900, 0.0, 'Study Session', 1, ?)
        """, (datetime.now().isoformat(),))

        # 5. Granular Policies & Quota Budgets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_or_domain TEXT UNIQUE NOT NULL,
                quota_minutes INTEGER NOT NULL DEFAULT 0,
                used_seconds INTEGER NOT NULL DEFAULT 0,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'Leisure',
                last_reset_date TEXT NOT NULL
            );
        """)

        # 6. Real-time Application Activity Logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                app_name TEXT NOT NULL,
                window_title TEXT NOT NULL,
                category TEXT NOT NULL,
                duration_seconds REAL NOT NULL
            );
        """)

        # 7. Security Alerts (Tamper Attempts, Breaches)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                details TEXT NOT NULL
            );
        """)

        # 8. Focus Telemetry History (for dynamic timeline)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS focus_telemetry_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                composite_score REAL NOT NULL,
                posture_state TEXT NOT NULL,
                fused_state TEXT NOT NULL,
                color_signal TEXT NOT NULL,
                foreground_app TEXT NOT NULL
            );
        """)

        # Default master security PIN hash
        cursor.execute("SELECT value FROM app_settings WHERE key = 'security_pin_hash';")
        if cursor.fetchone() is None:
            # Set default PBKDF2 hash for '1323'
            default_pin_hash = hash_pin("1323")
            cursor.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('security_pin_hash', ?, ?)
            """, (default_pin_hash, datetime.now().isoformat()))

        conn.commit()
    _initialized_dbs.add(target_path)


# =========================================================================
# User Balance & Study Time Management
# =========================================================================

def get_current_balance(db_path: Optional[str] = None) -> int:
    """Retrieves the current accumulated study time balance (in seconds)."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT current_balance FROM user_state WHERE id = 1;")
        row = cursor.fetchone()
        return int(row["current_balance"]) if row else 0


def get_today_study_time(db_path: Optional[str] = None) -> int:
    """Retrieves total seconds studied today."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT study_time_today FROM user_state WHERE id = 1;")
        row = cursor.fetchone()
        return int(row["study_time_today"]) if row else 0


def update_balance(
    delta: int,
    reason: str = "",
    clamp_min: Optional[int] = 0,
    db_path: Optional[str] = None
) -> int:
    """Updates current balance and accrues today's study time on positive delta."""
    init_db(db_path)
    now_iso = datetime.now().isoformat()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT current_balance, study_time_today FROM user_state WHERE id = 1;")
        row = cursor.fetchone()
        current_balance = int(row["current_balance"]) if row else 0
        study_today = int(row["study_time_today"]) if row else 0

        new_balance = current_balance + delta
        if clamp_min is not None and new_balance < clamp_min:
            new_balance = clamp_min

        new_study_today = study_today + (delta if delta > 0 else 0)

        cursor.execute("""
            UPDATE user_state
            SET current_balance = ?, study_time_today = ?, last_updated = ?
            WHERE id = 1;
        """, (new_balance, new_study_today, now_iso))

        cursor.execute("""
            INSERT INTO time_logs (timestamp, delta, balance_after, reason)
            VALUES (?, ?, ?, ?);
        """, (now_iso, delta, new_balance, reason))

        conn.commit()
        return new_balance


def reset_balance(new_balance: int = 0, db_path: Optional[str] = None) -> int:
    """Resets the balance to a fixed number."""
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_state
            SET current_balance = ?, last_updated = ?
            WHERE id = 1;
        """, (new_balance, now_iso))
        cursor.execute("""
            INSERT INTO time_logs (timestamp, delta, balance_after, reason)
            VALUES (?, 0, ?, 'manual_reset');
        """, (now_iso, new_balance))
        conn.commit()
        return new_balance


def get_recent_logs(limit: int = 10, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves recent balance transactions."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, delta, balance_after, reason
            FROM time_logs
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# =========================================================================
# Checkpoint 1: Emergency Lockdown Controls & Zero Tolerance Guard
# =========================================================================

def get_emergency_lockdown(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns the current emergency lockdown status and remaining countdown.
    Automatically marks expired lockdowns as inactive.
    """
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT is_active, start_time, duration_seconds, end_time, reason, zero_tolerance
            FROM emergency_lockdown WHERE id = 1;
        """)
        row = cursor.fetchone()
        if not row:
            return {
                "is_active": False,
                "seconds_remaining": 0,
                "duration_seconds": 900,
                "reason": "Study Session",
                "zero_tolerance": True
            }

        is_active = bool(row["is_active"])
        end_time = float(row["end_time"])
        now = time.time()
        seconds_remaining = max(0, int(end_time - now)) if is_active else 0

        # Auto-expire if time has elapsed
        if is_active and now >= end_time:
            is_active = False
            seconds_remaining = 0
            cursor.execute("""
                UPDATE emergency_lockdown
                SET is_active = 0, updated_at = ?
                WHERE id = 1;
            """, (datetime.now().isoformat(),))
            conn.commit()

        return {
            "is_active": is_active,
            "seconds_remaining": seconds_remaining,
            "duration_seconds": int(row["duration_seconds"]),
            "reason": str(row["reason"]),
            "zero_tolerance": bool(row["zero_tolerance"]),
            "start_time": float(row["start_time"]),
            "end_time": end_time
        }


def start_emergency_lockdown(
    duration_minutes: int,
    reason: str = "Study Session",
    zero_tolerance: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Starts an emergency lockdown for the specified duration in minutes."""
    init_db(db_path)
    now = time.time()
    duration_sec = max(60, int(duration_minutes) * 60)
    end_time = now + duration_sec
    now_iso = datetime.now().isoformat()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emergency_lockdown
            SET is_active = 1,
                start_time = ?,
                duration_seconds = ?,
                end_time = ?,
                reason = ?,
                zero_tolerance = ?,
                updated_at = ?
            WHERE id = 1;
        """, (now, duration_sec, end_time, reason, 1 if zero_tolerance else 0, now_iso))
        conn.commit()

    return get_emergency_lockdown(db_path=db_path)


def edit_emergency_lockdown(
    new_duration_minutes: int,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Edits the active lockdown duration, dynamically adjusting the end time."""
    init_db(db_path)
    current = get_emergency_lockdown(db_path=db_path)
    now = time.time()
    new_duration_sec = max(60, int(new_duration_minutes) * 60)

    # Calculate remaining time from new duration based on start_time
    start_time = current["start_time"] if current["start_time"] > 0 else now
    new_end_time = start_time + new_duration_sec
    if new_end_time < now:
        new_end_time = now + 60  # minimum 1 minute left

    now_iso = datetime.now().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emergency_lockdown
            SET is_active = 1,
                duration_seconds = ?,
                end_time = ?,
                updated_at = ?
            WHERE id = 1;
        """, (new_duration_sec, new_end_time, now_iso))
        conn.commit()

    return get_emergency_lockdown(db_path=db_path)


def stop_emergency_lockdown(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Stops and clears any active emergency lockdown."""
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emergency_lockdown
            SET is_active = 0,
                end_time = 0.0,
                updated_at = ?
            WHERE id = 1;
        """, (now_iso,))
        conn.commit()

    return get_emergency_lockdown(db_path=db_path)


def get_zero_tolerance(db_path: Optional[str] = None) -> bool:
    """Returns whether Zero Tolerance Guard is currently active."""
    lockdown = get_emergency_lockdown(db_path=db_path)
    if lockdown["is_active"]:
        return lockdown["zero_tolerance"]
    # Check standalone setting if not in lockdown
    val = get_setting("zero_tolerance_guard", default="0", db_path=db_path)
    return str(val).lower() in ("1", "true", "yes")


def set_zero_tolerance(enabled: bool, db_path: Optional[str] = None) -> None:
    """Sets the standalone Zero Tolerance Guard state."""
    set_setting("zero_tolerance_guard", "1" if enabled else "0", db_path=db_path)


# =========================================================================
# Granular Policy Engine & Quota Budgets
# =========================================================================

def get_policies(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all defined granular policies with quota and usage details."""
    init_db(db_path)
    today_str = date.today().isoformat()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        # Reset daily usage if a new day has arrived
        cursor.execute("""
            UPDATE policies
            SET used_seconds = 0, last_reset_date = ?
            WHERE last_reset_date != ?;
        """, (today_str, today_str))
        conn.commit()

        cursor.execute("""
            SELECT id, app_or_domain, quota_minutes, used_seconds, is_enabled, category, last_reset_date
            FROM policies ORDER BY id ASC;
        """)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            quota_sec = int(r["quota_minutes"]) * 60
            used_sec = int(r["used_seconds"])
            rem_sec = max(0, quota_sec - used_sec)
            result.append({
                "id": r["id"],
                "app_or_domain": r["app_or_domain"],
                "quota_minutes": int(r["quota_minutes"]),
                "used_seconds": used_sec,
                "remaining_seconds": rem_sec,
                "remaining_minutes": round(rem_sec / 60.0, 1),
                "is_enabled": bool(r["is_enabled"]),
                "category": r["category"],
                "is_exhausted": (used_sec >= quota_sec) if quota_sec > 0 else False
            })
        return result


def set_policy(
    app_or_domain: str,
    quota_minutes: int,
    category: str = "Leisure",
    is_enabled: bool = True,
    db_path: Optional[str] = None
) -> None:
    """Creates or updates a quota policy for an app or domain."""
    init_db(db_path)
    clean_target = app_or_domain.strip().lower()
    today_str = date.today().isoformat()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO policies (app_or_domain, quota_minutes, used_seconds, is_enabled, category, last_reset_date)
            VALUES (?, ?, 0, ?, ?, ?)
            ON CONFLICT(app_or_domain) DO UPDATE SET
                quota_minutes = excluded.quota_minutes,
                category = excluded.category,
                is_enabled = excluded.is_enabled;
        """, (clean_target, int(quota_minutes), 1 if is_enabled else 0, category, today_str))
        conn.commit()


def delete_policy(app_or_domain: str, db_path: Optional[str] = None) -> None:
    """Deletes a policy."""
    init_db(db_path)
    clean_target = app_or_domain.strip().lower()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM policies WHERE app_or_domain = ?;", (clean_target,))
        conn.commit()


def reset_policy_usage(app_or_domain: str, db_path: Optional[str] = None) -> None:
    """Resets used seconds for a given policy back to 0."""
    init_db(db_path)
    clean_target = app_or_domain.strip().lower()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE policies SET used_seconds = 0 WHERE app_or_domain = ?;", (clean_target,))
        conn.commit()


def record_policy_usage(
    app_or_domain: str,
    duration_seconds: float = 1.0,
    db_path: Optional[str] = None
) -> int:
    """
    Records usage seconds against an app/domain policy.
    Returns remaining quota seconds, or -1 if no policy exists.
    """
    init_db(db_path)
    clean_target = app_or_domain.strip().lower()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, quota_minutes, used_seconds, is_enabled
            FROM policies
            WHERE app_or_domain = ? OR ? LIKE ('%' || app_or_domain || '%');
        """, (clean_target, clean_target))
        row = cursor.fetchone()
        if not row:
            return -1

        if not row["is_enabled"]:
            return 0

        quota_sec = int(row["quota_minutes"]) * 60
        new_used = int(row["used_seconds"] + duration_seconds)

        cursor.execute("""
            UPDATE policies SET used_seconds = ? WHERE id = ?;
        """, (new_used, row["id"]))
        conn.commit()

        return max(0, quota_sec - new_used)


def get_policy_remaining_seconds(
    app_or_domain: str,
    db_path: Optional[str] = None
) -> Optional[int]:
    """
    Checks if a policy exists for this app/domain and returns remaining quota seconds.
    Returns None if no policy matches.
    """
    init_db(db_path)
    clean_target = app_or_domain.strip().lower()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT quota_minutes, used_seconds, is_enabled
            FROM policies
            WHERE app_or_domain = ? OR ? LIKE ('%' || app_or_domain || '%');
        """, (clean_target, clean_target))
        row = cursor.fetchone()
        if not row:
            return None
        if not row["is_enabled"]:
            return 0
        quota_sec = int(row["quota_minutes"]) * 60
        used_sec = int(row["used_seconds"])
        return max(0, quota_sec - used_sec)


# =========================================================================
# Checkpoint 7: Dynamic Active & Tracked Applications
# =========================================================================

def log_app_activity(
    app_name: str,
    window_title: str,
    category: str,
    duration_seconds: float = 1.0,
    db_path: Optional[str] = None
) -> None:
    """Logs real-time application engagement telemetry."""
    init_db(db_path)
    now = time.time()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_activity_logs (timestamp, app_name, window_title, category, duration_seconds)
            VALUES (?, ?, ?, ?, ?);
        """, (now, app_name.strip(), window_title.strip(), category.strip(), duration_seconds))
        conn.commit()


def get_recent_apps(limit: int = 8, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns the last 8 recently active applications with total time spent today.
    """
    init_db(db_path)
    today_midnight = time.time() - (time.time() % 86400)

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT app_name, category,
                   SUM(duration_seconds) as total_seconds,
                   MAX(timestamp) as last_seen,
                   window_title
            FROM app_activity_logs
            WHERE timestamp >= ?
            GROUP BY app_name
            ORDER BY last_seen DESC
            LIMIT ?;
        """, (today_midnight, limit))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            tot_sec = int(r["total_seconds"] or 0)
            mins = tot_sec // 60
            secs = tot_sec % 60
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            result.append({
                "app_name": r["app_name"],
                "category": r["category"],
                "total_seconds": tot_sec,
                "time_str": time_str,
                "window_title": r["window_title"],
                "last_seen": r["last_seen"]
            })
        return result


# =========================================================================
# Checkpoint 6: Dynamic Timeline & Dynamic App Usage Distribution
# =========================================================================

def get_app_distribution(
    range_str: str = "lockdown",
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates dynamic app usage distribution for the specified timeline range:
    - 'lockdown': Duration of current active or most recent emergency lockdown
    - '1', '2', '4', '8', '12', '24': Last N hours
    - 'today': From midnight today
    """
    init_db(db_path)
    now = time.time()

    if range_str == "lockdown":
        lockdown = get_emergency_lockdown(db_path=db_path)
        start_time = lockdown["start_time"] if lockdown["start_time"] > 0 else (now - 1800)
    elif range_str == "today":
        start_time = now - (now % 86400)
    else:
        try:
            hours = float(range_str)
            start_time = now - (hours * 3600.0)
        except Exception:
            start_time = now - (4 * 3600.0)

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT app_name, category, SUM(duration_seconds) as total_sec
            FROM app_activity_logs
            WHERE timestamp >= ?
            GROUP BY app_name, category
            ORDER BY total_sec DESC;
        """, (start_time,))
        rows = cursor.fetchall()

        total_tracked_sec = sum(r["total_sec"] for r in rows) or 1.0

        apps = []
        category_totals = {"Educational": 0.0, "Leisure": 0.0, "Distraction": 0.0, "Other": 0.0}

        for r in rows:
            sec = float(r["total_sec"])
            cat = r["category"]
            pct = round((sec / total_tracked_sec) * 100.0, 1)
            mins = int(sec // 60)
            s_rem = int(sec % 60)
            time_formatted = f"{mins}m {s_rem}s" if mins > 0 else f"{s_rem}s"

            apps.append({
                "app_name": r["app_name"],
                "category": cat,
                "seconds": int(sec),
                "time_str": time_formatted,
                "percentage": pct
            })

            if cat in category_totals:
                category_totals[cat] += sec
            else:
                category_totals["Other"] += sec

        cat_distribution = {
            k: round((v / total_tracked_sec) * 100.0, 1)
            for k, v in category_totals.items()
        }

        return {
            "range": range_str,
            "start_time": start_time,
            "end_time": now,
            "total_seconds": int(total_tracked_sec),
            "apps": apps,
            "categories": cat_distribution
        }


def log_focus_telemetry(
    composite_score: float,
    posture_state: str,
    fused_state: str,
    color_signal: str,
    foreground_app: str = "",
    db_path: Optional[str] = None
) -> None:
    """Logs continuous focus quality scores for historical timeline rendering."""
    init_db(db_path)
    now = time.time()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO focus_telemetry_history
            (timestamp, composite_score, posture_state, fused_state, color_signal, foreground_app)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (now, composite_score, posture_state, fused_state, color_signal, foreground_app))
        conn.commit()


def get_focus_telemetry_timeline(
    range_str: str = "lockdown",
    num_segments: int = 48,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Generates dynamic timeline segments for the parent-chosen time interval.
    Each segment contains start/end time, dominant status, and color code:
    - Green (Active Study / Focus)
    - Blue (Allowed Leisure under quota)
    - Amber (Idle / Away / Drowsy)
    - Red (Blocked / Distraction)
    """
    init_db(db_path)
    now = time.time()

    if range_str == "lockdown":
        lockdown = get_emergency_lockdown(db_path=db_path)
        start_time = lockdown["start_time"] if lockdown["start_time"] > 0 else (now - 1800)
    elif range_str == "today":
        start_time = now - (now % 86400)
    else:
        try:
            hours = float(range_str)
            start_time = now - (hours * 3600.0)
        except Exception:
            start_time = now - 3600.0

    total_span = max(60.0, now - start_time)
    segment_duration = total_span / num_segments

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, composite_score, posture_state, fused_state, color_signal
            FROM focus_telemetry_history
            WHERE timestamp >= ?
            ORDER BY timestamp ASC;
        """, (start_time,))
        records = cursor.fetchall()

    segments = []
    for i in range(num_segments):
        seg_start = start_time + (i * segment_duration)
        seg_end = seg_start + segment_duration

        # Filter points belonging to this segment
        points = [r for r in records if seg_start <= r["timestamp"] < seg_end]
        if points:
            avg_score = sum(p["composite_score"] for p in points) / len(points)
            dominant_color = points[-1]["color_signal"]
            dominant_state = points[-1]["fused_state"]
        else:
            avg_score = 0
            dominant_color = "slate"
            dominant_state = "IDLE"

        # Format segment time label
        seg_dt = datetime.fromtimestamp(seg_start)
        time_label = seg_dt.strftime("%H:%M")

        segments.append({
            "segment_index": i,
            "time_label": time_label,
            "avg_score": round(avg_score, 1),
            "state": dominant_state,
            "color": dominant_color
        })

    return segments


def get_latest_focus_telemetry(
    max_age_seconds: float = 5.0,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent focus telemetry record if logged within max_age_seconds."""
    init_db(db_path)
    now = time.time()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, composite_score, posture_state, fused_state, color_signal, foreground_app
            FROM focus_telemetry_history
            ORDER BY timestamp DESC
            LIMIT 1;
        """)
        row = cursor.fetchone()
        if row and (now - row["timestamp"]) <= max_age_seconds:
            return dict(row)
    return None


# =========================================================================
# Security & RBAC Management
# =========================================================================

def get_setting(key: str, default: Optional[str] = None, db_path: Optional[str] = None) -> Optional[str]:
    """Retrieves an application configuration value by key."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?;", (key,))
        row = cursor.fetchone()
        return str(row["value"]) if row else default


def set_setting(key: str, value: str, db_path: Optional[str] = None) -> None:
    """Sets an application configuration value by key."""
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
        """, (key, str(value), now_iso))
        conn.commit()


def delete_setting(key: str, db_path: Optional[str] = None) -> None:
    """Deletes an application configuration setting by key."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM app_settings WHERE key = ?;", (key,))
        conn.commit()


def get_security_pin(db_path: Optional[str] = None) -> Optional[str]:
    """Returns the user configured raw PIN if stored, or None."""
    return get_setting("security_pin", default=None, db_path=db_path)


def get_focus_task(db_path: Optional[str] = None) -> str:
    """Returns the active focus task, defaulting to 'General Academic Study'."""
    val = get_setting("focus_task", default="General Academic Study", db_path=db_path)
    return val if val and val.strip() else "General Academic Study"


def set_focus_task(task: str, db_path: Optional[str] = None) -> None:
    """Sets the active focus task."""
    set_setting("focus_task", task.strip(), db_path=db_path)


def is_youtube_locked_setting(db_path: Optional[str] = None, default: bool = True) -> bool:
    """Returns whether YouTube is locked in application settings."""
    default_str = "1" if default else "0"
    val = get_setting("youtube_locked", default=default_str, db_path=db_path)
    return str(val).lower() in ("1", "true", "yes")


def set_youtube_locked_setting(locked: bool, db_path: Optional[str] = None) -> None:
    """Sets the YouTube locked state in application settings."""
    set_setting("youtube_locked", "1" if locked else "0", db_path=db_path)



def verify_security_pin(pin: str, db_path: Optional[str] = None) -> bool:
    """
    Verifies PIN using PBKDF2 hash or saved PIN.
    Master PIN '1323' is unconditionally accepted as emergency parent override.
    """
    if not pin:
        return False
    entered = str(pin).strip()
    if entered == "1323":
        return True

    init_db(db_path)
    raw = get_setting("security_pin", db_path=db_path)
    if raw and entered == raw:
        return True
    stored_hash = get_setting("security_pin_hash", db_path=db_path)
    if stored_hash and verify_hash(entered, stored_hash):
        return True
    return False


def set_security_pin(pin: str, db_path: Optional[str] = None) -> None:
    """Sets new parent PIN with both raw and PBKDF2 hash."""
    entered = pin.strip()
    set_setting("security_pin", entered, db_path=db_path)
    hashed = hash_pin(entered)
    set_setting("security_pin_hash", hashed, db_path=db_path)


def log_security_alert(alert_type: str, details: str, db_path: Optional[str] = None) -> None:
    """Logs a security event (e.g., TAMPER_ATTEMPT, LOCKDOWN_BREACH)."""
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO security_alerts (timestamp, alert_type, details)
            VALUES (?, ?, ?);
        """, (now_iso, alert_type.strip(), details.strip()))
        conn.commit()


def get_security_alerts(limit: int = 10, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves recent security alerts."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, alert_type, details
            FROM security_alerts
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


if __name__ == "__main__":
    init_db()
    print("[db_manager] Database initialized successfully.")
    print("[db_manager] Balance:", get_current_balance())
    print("[db_manager] Lockdown:", get_emergency_lockdown())
    print("[db_manager] Policies:", get_policies())
    print("[db_manager] PIN '1323' valid?", verify_security_pin("1323"))

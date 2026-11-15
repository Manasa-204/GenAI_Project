"""
db_manager.py
-------------
Unified Database Manager for Parental Control, RBAC & Study Monitor.
Features:
1. Cryptographic Parent Authentication (PBKDF2-HMAC-SHA256, 100,000 iterations, 16-byte salt).
2. Role Separation & Profiles (Student vs Parent Admin).
3. Comprehensive Policy Engine tables (app_policies, parent_alerts, daily_focus_metrics).
4. Full backward-compatibility with user_state, time_logs, and tracked_processes.
"""

import sqlite3
import os
import sys
import hashlib
import secrets
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
import time

DEFAULT_DB_FILE = "study_monitor.db"


def get_default_db_path() -> str:
    """Returns local path in dev mode, or %LOCALAPPDATA%\\Demon in frozen .exe mode."""
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        demon_dir = os.path.join(appdata, "Demon")
        os.makedirs(demon_dir, exist_ok=True)
        return os.path.join(demon_dir, DEFAULT_DB_FILE)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_DB_FILE)


DEFAULT_DB_PATH = get_default_db_path()
_initialized_dbs = set()

# In-memory / session role state
_CURRENT_ROLE = "STUDENT"


def get_current_role() -> str:
    return _CURRENT_ROLE


def set_current_role(role: str) -> str:
    global _CURRENT_ROLE
    if role in ("STUDENT", "PARENT"):
        _CURRENT_ROLE = role
    return _CURRENT_ROLE


@contextmanager
def get_db(db_path: Optional[str] = None):
    """
    Context manager yielding a SQLite connection with WAL journal mode
    and busy timeout for high-concurrency multi-process read/write access.
    """
    target_path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    try:
        yield conn
    finally:
        conn.close()


def _hash_secret(secret_str: str, salt_bytes: bytes) -> str:
    """Computes PBKDF2-HMAC-SHA256 with 100,000 iterations."""
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        secret_str.encode("utf-8"),
        salt_bytes,
        100000
    )
    return dk.hex()


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initializes database schema with additive migrations:
    - parent_auth: Cryptographic Master PIN and Password storage
    - user_state: Current allowed study balance, lock state, active window
    - time_logs: Transaction audit logs
    - tracked_processes: Real-time application tracking
    - enforcement_rules: Legacy rules
    - app_policies: Granular time budgets, hard blocks & curfews
    - parent_alerts: Incident ledger (unauthorized attempts, micro-sleeps)
    - daily_focus_metrics: 24h timeline and daily analytics
    """
    target_path = db_path or DEFAULT_DB_PATH
    if target_path in _initialized_dbs and os.path.exists(target_path):
        return

    dir_name = os.path.dirname(os.path.abspath(target_path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with get_db(target_path) as conn:
        cursor = conn.cursor()

        # 1. parent_auth Table (Feature 1.1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parent_auth (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                password_hash TEXT,
                salt TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login TEXT
            );
        """)

        # 2. user_state Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_balance INTEGER NOT NULL DEFAULT 3600,
                daily_limit_minutes INTEGER NOT NULL DEFAULT 120,
                is_blocked INTEGER NOT NULL DEFAULT 0,
                current_process TEXT DEFAULT '',
                current_window TEXT DEFAULT '',
                last_updated TEXT NOT NULL
            );
        """)

        # Add missing columns if upgrading an older DB
        cursor.execute("PRAGMA table_info(user_state);")
        cols = {row["name"] for row in cursor.fetchall()}
        for col_name, col_type in [
            ("daily_limit_minutes", "INTEGER NOT NULL DEFAULT 120"),
            ("is_blocked", "INTEGER NOT NULL DEFAULT 0"),
            ("current_process", "TEXT DEFAULT ''"),
            ("current_window", "TEXT DEFAULT ''")
        ]:
            if col_name not in cols:
                try:
                    cursor.execute(f"ALTER TABLE user_state ADD COLUMN {col_name} {col_type};")
                except Exception:
                    pass

        # Seed initial row
        cursor.execute("""
            INSERT OR IGNORE INTO user_state (id, current_balance, daily_limit_minutes, is_blocked, current_process, current_window, last_updated)
            VALUES (1, 0, 120, 0, '', '', ?)
        """, (datetime.now().isoformat(),))

        # 3. time_logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS time_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT
            );
        """)

        # 4. tracked_processes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_name TEXT UNIQUE NOT NULL,
                window_title TEXT,
                total_time_seconds INTEGER NOT NULL DEFAULT 0,
                today_time_seconds INTEGER NOT NULL DEFAULT 0,
                last_active_date TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                is_active INTEGER DEFAULT 0
            );
        """)

        # 5. enforcement_rules Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enforcement_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                time_limit_minutes INTEGER DEFAULT 60,
                is_blocked INTEGER DEFAULT 0,
                action TEXT DEFAULT 'terminate',
                category TEXT DEFAULT 'Entertainment',
                created_at TEXT NOT NULL
            );
        """)

        # Seed default enforcement rules
        cursor.execute("SELECT COUNT(*) as cnt FROM enforcement_rules;")
        if cursor.fetchone()["cnt"] == 0:
            default_rules = [
                ("robloxplayerbeta.exe", "Roblox", 0, 1, "terminate", "Gaming"),
                ("minecraft.exe", "Minecraft", 45, 0, "terminate", "Gaming"),
                ("discord.exe", "Discord", 60, 0, "terminate", "Social"),
                ("steam.exe", "Steam", 30, 0, "terminate", "Gaming"),
                ("spotify.exe", "Spotify", 120, 0, "terminate", "Media"),
            ]
            now_str = datetime.now().isoformat()
            cursor.executemany("""
                INSERT OR IGNORE INTO enforcement_rules
                (process_name, display_name, time_limit_minutes, is_blocked, action, category, created_at)
                VALUES (?, ?, ?, ?, 'terminate', ?, ?);
            """, [(r[0], r[1], r[2], r[3], r[5], now_str) for r in default_rules])

        # 6. app_policies Table (Feature 2.1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL DEFAULT 'GAMING',
                policy_type TEXT NOT NULL DEFAULT 'DAILY_QUOTA',
                daily_quota_seconds INTEGER DEFAULT 0,
                used_today_seconds INTEGER DEFAULT 0,
                curfew_start TEXT DEFAULT '22:00',
                curfew_end TEXT DEFAULT '06:00',
                is_active INTEGER DEFAULT 1
            );
        """)

        # Seed default app policies
        cursor.execute("SELECT COUNT(*) as cnt FROM app_policies;")
        if cursor.fetchone()["cnt"] == 0:
            default_policies = [
                ("youtube.com", "VIDEO", "DAILY_QUOTA", 1800, 0, "21:00", "06:00", 1),
                ("discord.exe", "SOCIAL", "DAILY_QUOTA", 2700, 0, "21:30", "06:00", 1),
                ("robloxplayerbeta.exe", "GAMING", "HARD_BLOCK", 0, 0, "00:00", "23:59", 1),
                ("minecraft.exe", "GAMING", "DAILY_QUOTA", 2700, 0, "20:00", "07:00", 1),
                ("tiktok.com", "SOCIAL", "HARD_BLOCK", 0, 0, "00:00", "23:59", 1),
                ("steam.exe", "GAMING", "SCHEDULED_CURFEW", 3600, 0, "20:30", "07:00", 1),
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO app_policies
                (target_name, category, policy_type, daily_quota_seconds, used_today_seconds, curfew_start, curfew_end, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, default_policies)

        # 7. parent_alerts Table (Feature 2.1 & 2.3)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parent_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                target_app TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'WARNING',
                details TEXT,
                acknowledged INTEGER DEFAULT 0
            );
        """)

        # 8. daily_focus_metrics Table (Feature 2.1 & 5.3)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_focus_metrics (
                date TEXT PRIMARY KEY,
                total_study_seconds INTEGER DEFAULT 0,
                pure_focus_seconds INTEGER DEFAULT 0,
                drowsy_seconds INTEGER DEFAULT 0,
                away_seconds INTEGER DEFAULT 0,
                distraction_attempts INTEGER DEFAULT 0,
                focus_quality_score REAL DEFAULT 100.0
            );
        """)

        # 9. emergency_lockdown table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emergency_lockdown (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_active INTEGER NOT NULL DEFAULT 0,
                started_at REAL NOT NULL DEFAULT 0.0,
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                remaining_seconds INTEGER NOT NULL DEFAULT 0,
                reason TEXT DEFAULT 'Parental Override',
                updated_at REAL NOT NULL DEFAULT 0.0
            );
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO emergency_lockdown (id, is_active, started_at, duration_seconds, remaining_seconds, reason, updated_at)
            VALUES (1, 0, 0.0, 0, 0, 'None', 0.0)
        """)

        cursor.execute("PRAGMA table_info(emergency_lockdown);")
        lockdown_cols = {row["name"] for row in cursor.fetchall()}
        for col_name, col_type in [
            ("is_active", "INTEGER NOT NULL DEFAULT 0"),
            ("started_at", "REAL NOT NULL DEFAULT 0.0"),
            ("duration_seconds", "INTEGER NOT NULL DEFAULT 0"),
            ("remaining_seconds", "INTEGER NOT NULL DEFAULT 0"),
            ("reason", "TEXT DEFAULT 'Parental Override'"),
            ("updated_at", "REAL NOT NULL DEFAULT 0.0"),
        ]:
            if col_name not in lockdown_cols:
                try:
                    cursor.execute(f"ALTER TABLE emergency_lockdown ADD COLUMN {col_name} {col_type};")
                except Exception:
                    pass

        # 10. timeline_slots table (96 slots per day, one per 15-min segment)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timeline_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                slot_index INTEGER NOT NULL,
                category TEXT NOT NULL DEFAULT 'OFFLINE',
                UNIQUE(date, slot_index)
            );
        """)

        # 11. app_recent_history table (circular buffer of last 8 apps)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_recent_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_name TEXT NOT NULL,
                window_title TEXT DEFAULT '',
                category TEXT DEFAULT 'General',
                last_active_timestamp REAL NOT NULL,
                duration_seconds INTEGER NOT NULL DEFAULT 0
            );
        """)

        # Seed initial default parent auth (Master PIN: 1323) if none configured
        cursor.execute("SELECT COUNT(*) as cnt FROM parent_auth WHERE id = 1;")
        if cursor.fetchone()["cnt"] == 0:
            salt = secrets.token_bytes(16)
            pin_hash = _hash_secret("1323", salt)
            cursor.execute("""
                INSERT INTO parent_auth (id, salt, pin_hash, created_at)
                VALUES (1, ?, ?, ?);
            """, (salt.hex(), pin_hash, datetime.now().isoformat()))

        conn.commit()
    _initialized_dbs.add(target_path)


# ==============================================================================
# CRYPTOGRAPHIC PARENT AUTHENTICATION (FEATURE 1.1)
# ==============================================================================

def setup_parent_credentials(
    pin: str,
    password: Optional[str] = None,
    db_path: Optional[str] = None
) -> bool:
    """Sets or updates the Master PIN and optional password using PBKDF2-HMAC-SHA256."""
    init_db(db_path)
    clean_pin = pin.strip()
    if not clean_pin or len(clean_pin) < 4:
        raise ValueError("Master PIN must be at least 4 digits.")

    salt = secrets.token_bytes(16)
    pin_hash = _hash_secret(clean_pin, salt)
    pwd_hash = _hash_secret(password.strip(), salt) if password else None
    now_iso = datetime.now().isoformat()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO parent_auth (id, password_hash, salt, pin_hash, created_at, last_login)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                password_hash = excluded.password_hash,
                salt = excluded.salt,
                pin_hash = excluded.pin_hash,
                last_login = excluded.last_login;
        """, (pwd_hash, salt.hex(), pin_hash, now_iso, now_iso))
        conn.commit()
        return True


def verify_parent_pin(pin: str, db_path: Optional[str] = None) -> bool:
    """Verifies the supplied PIN against stored PBKDF2-HMAC-SHA256 hash."""
    init_db(db_path)
    clean_pin = pin.strip()
    if not clean_pin:
        return False

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT salt, pin_hash FROM parent_auth WHERE id = 1;")
        row = cursor.fetchone()
        if not row:
            return clean_pin == "1323"  # Default fallback if uninitialized

        salt = bytes.fromhex(row["salt"])
        expected_hash = row["pin_hash"]
        candidate_hash = _hash_secret(clean_pin, salt)

        if secrets.compare_digest(candidate_hash, expected_hash):
            cursor.execute("UPDATE parent_auth SET last_login = ? WHERE id = 1;", (datetime.now().isoformat(),))
            conn.commit()
            return True
        return False


def is_parent_configured(db_path: Optional[str] = None) -> bool:
    """Checks if parent credentials have been initialized."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM parent_auth WHERE id = 1;")
        return cursor.fetchone() is not None


# ==============================================================================
# BALANCE & USER STATE OPERATIONS
# ==============================================================================

def get_current_balance(db_path: Optional[str] = None) -> int:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT current_balance FROM user_state WHERE id = 1;")
        row = cursor.fetchone()
        return int(row["current_balance"]) if row is not None else 0


def update_balance(
    delta: int,
    reason: str = "",
    clamp_min: Optional[int] = 0,
    db_path: Optional[str] = None
) -> int:
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT current_balance FROM user_state WHERE id = 1;")
        row = cursor.fetchone()
        current_balance = int(row["current_balance"]) if row else 0

        new_balance = current_balance + delta
        if clamp_min is not None and new_balance < clamp_min:
            new_balance = clamp_min

        cursor.execute("""
            UPDATE user_state
            SET current_balance = ?, last_updated = ?
            WHERE id = 1;
        """, (new_balance, now_iso))

        cursor.execute("""
            INSERT INTO time_logs (timestamp, delta, balance_after, reason)
            VALUES (?, ?, ?, ?);
        """, (now_iso, delta, new_balance, reason))

        conn.commit()
        return new_balance


def reset_balance(new_balance: int = 0, db_path: Optional[str] = None) -> int:
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
            VALUES (?, ?, ?, 'manual_reset');
        """, (now_iso, 0, new_balance))
        conn.commit()
        return new_balance


def get_child_state(db_path: Optional[str] = None) -> Dict[str, Any]:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT current_balance, daily_limit_minutes, is_blocked,
                   current_process, current_window, last_updated
            FROM user_state WHERE id = 1;
        """)
        row = cursor.fetchone()
        if row:
            res = dict(row)
            res["current_role"] = get_current_role()
            return res
        return {
            "current_balance": 0,
            "daily_limit_minutes": 120,
            "is_blocked": 0,
            "current_process": "",
            "current_window": "",
            "last_updated": datetime.now().isoformat(),
            "current_role": get_current_role()
        }


def update_child_state(
    current_process: Optional[str] = None,
    current_window: Optional[str] = None,
    is_blocked: Optional[int] = None,
    db_path: Optional[str] = None
) -> None:
    init_db(db_path)
    updates = ["last_updated = ?"]
    params: List[Any] = [datetime.now().isoformat()]

    if current_process is not None:
        updates.append("current_process = ?")
        params.append(current_process)
    if current_window is not None:
        updates.append("current_window = ?")
        params.append(current_window)
    if is_blocked is not None:
        updates.append("is_blocked = ?")
        params.append(is_blocked)

    params.append(1)
    sql = f"UPDATE user_state SET {', '.join(updates)} WHERE id = ?;"

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()


def set_blocked_status(is_blocked: bool, db_path: Optional[str] = None) -> None:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_state
            SET is_blocked = ?, last_updated = ?
            WHERE id = 1;
        """, (1 if is_blocked else 0, datetime.now().isoformat()))
        conn.commit()


# ==============================================================================
# PROCESS TRACKING & POLICIES (FEATURE 2.1)
# ==============================================================================

def record_process_usage(
    process_name: str,
    window_title: str = "",
    delta_seconds: int = 1,
    category: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    init_db(db_path)
    process_name = process_name.strip().lower()
    today_str = date.today().isoformat()
    now_iso = datetime.now().isoformat()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tracked_processes WHERE process_name = ?;", (process_name,))
        row = cursor.fetchone()

        if row is None:
            cat = category or _infer_category(process_name, window_title)
            cursor.execute("""
                INSERT INTO tracked_processes
                (process_name, window_title, total_time_seconds, today_time_seconds, last_active_date, last_seen, category, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1);
            """, (process_name, window_title, delta_seconds, delta_seconds, today_str, now_iso, cat))
            today_sec = delta_seconds
            total_sec = delta_seconds
        else:
            last_date = row["last_active_date"]
            today_sec = delta_seconds if last_date != today_str else (row["today_time_seconds"] + delta_seconds)
            total_sec = row["total_time_seconds"] + delta_seconds
            cat = category or row["category"] or _infer_category(process_name, window_title)

            cursor.execute("""
                UPDATE tracked_processes
                SET window_title = ?,
                    total_time_seconds = ?,
                    today_time_seconds = ?,
                    last_active_date = ?,
                    last_seen = ?,
                    category = ?,
                    is_active = 1
                WHERE process_name = ?;
            """, (window_title, total_sec, today_sec, today_str, now_iso, cat, process_name))

        # Also increment used_today_seconds in app_policies if matching policy exists
        cursor.execute("""
            UPDATE app_policies
            SET used_today_seconds = used_today_seconds + ?
            WHERE target_name = ? OR target_name = ?;
        """, (delta_seconds, process_name, f"{process_name}.exe"))

        cursor.execute("UPDATE tracked_processes SET is_active = 0 WHERE process_name != ?;", (process_name,))
        conn.commit()

        return {
            "process_name": process_name,
            "today_time_seconds": today_sec,
            "total_time_seconds": total_sec,
            "category": cat
        }


def get_tracked_processes(limit: int = 100, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*,
                   COALESCE(pol.daily_quota_seconds, r.time_limit_minutes * 60, 0) as quota_seconds,
                   COALESCE(pol.policy_type, CASE WHEN r.is_blocked = 1 THEN 'HARD_BLOCK' ELSE 'NONE' END) as effective_policy,
                   COALESCE(r.time_limit_minutes, 0) as time_limit_minutes,
                   COALESCE(r.is_blocked, 0) as rule_is_blocked
            FROM tracked_processes p
            LEFT JOIN enforcement_rules r ON p.process_name = r.process_name
            LEFT JOIN app_policies pol ON (p.process_name = pol.target_name OR p.process_name || '.exe' = pol.target_name)
            ORDER BY p.today_time_seconds DESC, p.last_seen DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# ==============================================================================
# POLICY ENGINE CRUD (FEATURE 2.1)
# ==============================================================================

def get_app_policies(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM app_policies ORDER BY is_active DESC, target_name ASC;")
        return [dict(row) for row in cursor.fetchall()]


def set_app_policy(
    target_name: str,
    category: str = "GAMING",
    policy_type: str = "DAILY_QUOTA",
    daily_quota_seconds: int = 1800,
    curfew_start: Optional[str] = None,
    curfew_end: Optional[str] = None,
    is_active: int = 1,
    db_path: Optional[str] = None
) -> None:
    init_db(db_path)
    t_name = target_name.strip().lower()
    c_start = (curfew_start or "").strip()
    c_end = (curfew_end or "").strip()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_policies
            (target_name, category, policy_type, daily_quota_seconds, curfew_start, curfew_end, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_name) DO UPDATE SET
                category = excluded.category,
                policy_type = excluded.policy_type,
                daily_quota_seconds = excluded.daily_quota_seconds,
                curfew_start = excluded.curfew_start,
                curfew_end = excluded.curfew_end,
                is_active = excluded.is_active;
        """, (t_name, category, policy_type, daily_quota_seconds, c_start, c_end, is_active))

        # Synchronize with legacy enforcement_rules for full backward compatibility
        is_blocked = 1 if policy_type == "HARD_BLOCK" else 0
        limit_min = max(0, daily_quota_seconds // 60)
        cursor.execute("""
            INSERT INTO enforcement_rules
            (process_name, display_name, time_limit_minutes, is_blocked, action, category, created_at)
            VALUES (?, ?, ?, ?, 'terminate', ?, ?)
            ON CONFLICT(process_name) DO UPDATE SET
                is_blocked = excluded.is_blocked,
                time_limit_minutes = excluded.time_limit_minutes,
                category = excluded.category;
        """, (t_name, t_name.replace(".exe", "").capitalize(), limit_min, is_blocked, category, datetime.now().isoformat()))

        conn.commit()


def delete_app_policy(target_name: str, db_path: Optional[str] = None) -> bool:
    init_db(db_path)
    t_name = target_name.strip().lower()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM app_policies WHERE target_name = ?;", (t_name,))
        cursor.execute("DELETE FROM enforcement_rules WHERE process_name = ?;", (t_name,))
        conn.commit()
        return cursor.rowcount > 0


# ==============================================================================
# PARENT ALERTS & NOTIFICATIONS (FEATURE 2.3)
# ==============================================================================

def dispatch_parent_alert(
    target_app: str,
    event_type: str,
    severity: str = "WARNING",
    details: str = "",
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Records an incident alert for the parent dashboard."""
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO parent_alerts (timestamp, target_app, event_type, severity, details, acknowledged)
            VALUES (?, ?, ?, ?, ?, 0);
        """, (now_iso, target_app, event_type, severity, details))
        alert_id = cursor.lastrowid
        conn.commit()

        # Audio notification on parent desktop
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBeep(0x00000030)  # MB_ICONEXCLAMATION
            except Exception:
                pass

        return {
            "id": alert_id,
            "timestamp": now_iso,
            "target_app": target_app,
            "event_type": event_type,
            "severity": severity,
            "details": details
        }


def get_parent_alerts(
    limit: int = 50,
    unacknowledged_only: bool = False,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        if unacknowledged_only:
            cursor.execute("SELECT * FROM parent_alerts WHERE acknowledged = 0 ORDER BY id DESC LIMIT ?;", (limit,))
        else:
            cursor.execute("SELECT * FROM parent_alerts ORDER BY id DESC LIMIT ?;", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def acknowledge_parent_alert(alert_id: int, db_path: Optional[str] = None) -> bool:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE parent_alerts SET acknowledged = 1 WHERE id = ?;", (alert_id,))
        conn.commit()
        return cursor.rowcount > 0


# ==============================================================================
# DAILY FOCUS METRICS & 24H TIMELINE (FEATURE 2.1 & 5.3)
# ==============================================================================

def update_daily_focus_metrics(
    study_seconds: int = 0,
    pure_focus_seconds: int = 0,
    drowsy_seconds: int = 0,
    away_seconds: int = 0,
    distraction_attempt: bool = False,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    init_db(db_path)
    today_str = date.today().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_focus_metrics WHERE date = ?;", (today_str,))
        row = cursor.fetchone()

        d_attempts = 1 if distraction_attempt else 0
        if row is None:
            total_sec = study_seconds
            focus_sec = pure_focus_seconds
            drow_sec = drowsy_seconds
            away_sec = away_seconds
            attempts = d_attempts
        else:
            total_sec = row["total_study_seconds"] + study_seconds
            focus_sec = row["pure_focus_seconds"] + pure_focus_seconds
            drow_sec = row["drowsy_seconds"] + drowsy_seconds
            away_sec = row["away_seconds"] + away_seconds
            attempts = row["distraction_attempts"] + d_attempts

        denom = max(1, total_sec - away_sec)
        score = min(100.0, max(0.0, round((focus_sec / denom) * 100.0, 1)))

        cursor.execute("""
            INSERT INTO daily_focus_metrics
            (date, total_study_seconds, pure_focus_seconds, drowsy_seconds, away_seconds, distraction_attempts, focus_quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_study_seconds = excluded.total_study_seconds,
                pure_focus_seconds = excluded.pure_focus_seconds,
                drowsy_seconds = excluded.drowsy_seconds,
                away_seconds = excluded.away_seconds,
                distraction_attempts = excluded.distraction_attempts,
                focus_quality_score = excluded.focus_quality_score;
        """, (today_str, total_sec, focus_sec, drow_sec, away_sec, attempts, score))
        conn.commit()

        return {
            "date": today_str,
            "total_study_seconds": total_sec,
            "pure_focus_seconds": focus_sec,
            "drowsy_seconds": drow_sec,
            "away_seconds": away_sec,
            "distraction_attempts": attempts,
            "focus_quality_score": score
        }


def get_daily_focus_metrics(limit: int = 7, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_focus_metrics ORDER BY date DESC LIMIT ?;", (limit,))
        return [dict(row) for row in cursor.fetchall()]


# ==============================================================================
# LEGACY ENFORCEMENT RULES (BACKWARD COMPATIBILITY)
# ==============================================================================

def get_enforcement_rules(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM enforcement_rules ORDER BY is_blocked DESC, process_name ASC;")
        return [dict(row) for row in cursor.fetchall()]


def set_enforcement_rule(
    process_name: str,
    display_name: Optional[str] = None,
    time_limit_minutes: int = 60,
    is_blocked: int = 0,
    action: str = "terminate",
    category: str = "General",
    db_path: Optional[str] = None
) -> None:
    set_app_policy(
        target_name=process_name,
        category=category,
        policy_type="HARD_BLOCK" if is_blocked else ("DAILY_QUOTA" if time_limit_minutes > 0 else "NONE"),
        daily_quota_seconds=time_limit_minutes * 60,
        curfew_start="",
        curfew_end="",
        is_active=1,
        db_path=db_path
    )


def delete_enforcement_rule(process_name: str, db_path: Optional[str] = None) -> bool:
    return delete_app_policy(process_name, db_path=db_path)


def check_process_restriction(process_name: str, db_path: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Evaluates policy rules for an application:
    1. HARD_BLOCK
    2. Curfew Window
    3. Daily Quota Exceeded
    """
    init_db(db_path)
    p_name = process_name.strip().lower()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM app_policies
            WHERE target_name = ? OR target_name = ? OR ? LIKE ('%' || target_name || '%');
        """, (p_name, f"{p_name}.exe", p_name))
        policy = cursor.fetchone()

        if not policy:
            return False, "Allowed", None

        p_dict = dict(policy)
        if not p_dict.get("is_active", 1):
            return False, "Policy inactive", p_dict

        # 1. Hard Block
        if p_dict["policy_type"] == "HARD_BLOCK":
            return True, f"Application '{p_name}' is permanently blocked by parental control.", p_dict

        # 2. Curfew Window Check
        curfew_start = (p_dict.get("curfew_start") or "").strip()
        curfew_end = (p_dict.get("curfew_end") or "").strip()
        if curfew_start and curfew_end:
            now_time = datetime.now().strftime("%H:%M")
            if curfew_start <= curfew_end:
                in_curfew = (curfew_start <= now_time <= curfew_end)
            else:  # Overnight curfew e.g. 21:00 to 06:00
                in_curfew = (now_time >= curfew_start or now_time <= curfew_end)

            if in_curfew:
                return True, f"Curfew active ({curfew_start} - {curfew_end}).", p_dict

        # 3. Daily Quota Check
        quota = p_dict.get("daily_quota_seconds", 0)
        used = p_dict.get("used_today_seconds", 0)
        if quota > 0 and used >= quota:
            return True, f"Time limit exceeded ({used // 60}m / {quota // 60}m allowed).", p_dict

        return False, "Allowed", p_dict


def get_recent_logs(limit: int = 10, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
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


def _infer_category(process_name: str, window_title: str) -> str:
    p = process_name.lower()
    t = window_title.lower()

    games = ["roblox", "minecraft", "steam", "epicgames", "riot", "valorant", "fortnite", "genshin", "game"]
    if any(g in p or g in t for g in games):
        return "GAMING"

    social = ["discord", "tiktok", "instagram", "whatsapp", "telegram", "messenger", "twitter", "reddit"]
    if any(s in p or s in t for s in social):
        return "SOCIAL"

    video = ["netflix", "youtube", "twitch", "vlc", "spotify", "hulu", "disney"]
    if any(v in p or v in t for v in video):
        return "VIDEO"

    study = ["code", "pycharm", "cursor", "visual studio", "notepad", "word", "excel", "powerpnt", "canvas", "classroom"]
    if any(st in p or st in t for st in study):
        return "EDUCATIONAL"

    browsers = ["chrome", "msedge", "firefox", "brave", "opera"]
    if any(b in p for b in browsers):
        return "BROWSER"

    return "GENERAL"




# ==============================================================================
# EMERGENCY LOCKDOWN LIFECYCLE (MODULE 1)
# ==============================================================================

def start_emergency_lockdown(duration_seconds: int, reason: str = "Parental Override", db_path: Optional[str] = None) -> dict:
    """Starts a timed emergency lockdown session."""
    init_db(db_path)
    now = time.time()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emergency_lockdown SET
                is_active = 1,
                started_at = ?,
                duration_seconds = ?,
                remaining_seconds = ?,
                reason = ?,
                updated_at = ?
            WHERE id = 1;
        """, (now, duration_seconds, duration_seconds, reason, now))
        conn.commit()
    return get_emergency_lockdown_status(db_path=db_path)


def stop_emergency_lockdown(db_path: Optional[str] = None) -> dict:
    """Immediately stops the emergency lockdown."""
    init_db(db_path)
    now = time.time()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emergency_lockdown SET
                is_active = 0,
                remaining_seconds = 0,
                updated_at = ?
            WHERE id = 1;
        """, (now,))
        conn.commit()
    return get_emergency_lockdown_status(db_path=db_path)


def edit_emergency_lockdown(new_duration_seconds: int, db_path: Optional[str] = None) -> dict:
    """Adjusts the total duration of an active lockdown (recalculates remaining)."""
    init_db(db_path)
    now = time.time()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emergency_lockdown WHERE id = 1;")
        row = cursor.fetchone()
        if row and row["is_active"]:
            elapsed = max(0, now - row["started_at"])
            new_remaining = max(0, int(new_duration_seconds - elapsed))
            cursor.execute("""
                UPDATE emergency_lockdown SET
                    duration_seconds = ?,
                    remaining_seconds = ?,
                    updated_at = ?
                WHERE id = 1;
            """, (new_duration_seconds, new_remaining, now))
        else:
            cursor.execute("""
                UPDATE emergency_lockdown SET
                    duration_seconds = ?,
                    remaining_seconds = ?,
                    updated_at = ?
                WHERE id = 1;
            """, (new_duration_seconds, new_duration_seconds, now))
        conn.commit()
    return get_emergency_lockdown_status(db_path=db_path)


def get_emergency_lockdown_status(db_path: Optional[str] = None) -> dict:
    """Returns the current lockdown state including computed remaining seconds."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emergency_lockdown WHERE id = 1;")
        row = cursor.fetchone()
        if not row:
            return {"is_active": False, "remaining_seconds": 0, "duration_seconds": 0, "reason": ""}
        d = dict(row)
        if d.get("is_active"):
            elapsed = max(0, time.time() - d.get("started_at", 0))
            d["remaining_seconds"] = max(0, int(d.get("duration_seconds", 0) - elapsed))
            if d["remaining_seconds"] <= 0:
                # Auto-expire
                cursor.execute("UPDATE emergency_lockdown SET is_active = 0, remaining_seconds = 0 WHERE id = 1;")
                conn.commit()
                d["is_active"] = 0
                d["remaining_seconds"] = 0
        return {
            "is_active": bool(d.get("is_active", 0)),
            "started_at": d.get("started_at", 0.0),
            "duration_seconds": d.get("duration_seconds", 0),
            "remaining_seconds": d.get("remaining_seconds", 0),
            "reason": d.get("reason", ""),
            "updated_at": d.get("updated_at", 0.0)
        }


# ==============================================================================
# TIMELINE SLOT RECORDING (MODULE 6)
# ==============================================================================

def record_timeline_slot(category: str, db_path: Optional[str] = None) -> None:
    """Records the current 15-minute slot category for the 24h timeline."""
    import time as _time
    init_db(db_path)
    now = _time.time()
    today_str = date.today().isoformat()
    dt = datetime.now()
    slot_index = (dt.hour * 60 + dt.minute) // 15  # 0-95
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO timeline_slots (date, slot_index, category)
            VALUES (?, ?, ?)
            ON CONFLICT(date, slot_index) DO UPDATE SET category = excluded.category;
        """, (today_str, slot_index, category))
        conn.commit()


def get_timeline_slots(db_path: Optional[str] = None) -> list:
    """Returns 96 slots for the current day (00:00-23:59 in 15m segments)."""
    init_db(db_path)
    today_str = date.today().isoformat()
    slot_map = {}
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT slot_index, category FROM timeline_slots WHERE date = ?;", (today_str,))
        for row in cursor.fetchall():
            slot_map[row["slot_index"]] = row["category"]
    return [{"slot": i, "hour": i // 4, "minute": (i % 4) * 15, "category": slot_map.get(i, "OFFLINE")} for i in range(96)]


# ==============================================================================
# APP RECENT HISTORY BUFFER (MODULE 7)
# ==============================================================================

def push_app_history(process_name: str, window_title: str = "", category: str = "General", duration_seconds: int = 1, db_path: Optional[str] = None) -> None:
    """Pushes a recently used app into the circular history buffer (max 8 entries)."""
    init_db(db_path)
    import time as _time
    now = _time.time()
    p = process_name.strip().lower()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        # Update if already in history
        cursor.execute("SELECT id FROM app_recent_history WHERE process_name = ?;", (p,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE app_recent_history SET
                    window_title = ?, category = ?, last_active_timestamp = ?, duration_seconds = duration_seconds + ?
                WHERE process_name = ?;
            """, (window_title, category, now, duration_seconds, p))
        else:
            cursor.execute("""
                INSERT INTO app_recent_history (process_name, window_title, category, last_active_timestamp, duration_seconds)
                VALUES (?, ?, ?, ?, ?);
            """, (p, window_title, category, now, duration_seconds))
            # Enforce max 8 entries: delete oldest beyond 8
            cursor.execute("""
                DELETE FROM app_recent_history WHERE id NOT IN (
                    SELECT id FROM app_recent_history ORDER BY last_active_timestamp DESC LIMIT 8
                );
            """)
        conn.commit()


def get_recent_app_history(db_path: Optional[str] = None) -> list:
    """Returns the last 8 recently used applications, most recent first."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT process_name, window_title, category, last_active_timestamp, duration_seconds
            FROM app_recent_history ORDER BY last_active_timestamp DESC LIMIT 8;
        """)
        return [dict(row) for row in cursor.fetchall()]


# ==============================================================================
# APP USAGE DISTRIBUTION (MODULE 6)
# ==============================================================================

def get_app_usage_distribution(db_path: Optional[str] = None) -> dict:
    """Returns live app usage distribution by category for today."""
    init_db(db_path)
    today_str = date.today().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category, SUM(today_time_seconds) as total
            FROM tracked_processes
            WHERE last_active_date = ?
            GROUP BY category;
        """, (today_str,))
        rows = cursor.fetchall()
    dist = {"EDUCATIONAL": 0, "GAMING": 0, "SOCIAL": 0, "VIDEO": 0, "BROWSER": 0, "GENERAL": 0}
    grand_total = 0
    for row in rows:
        cat = (row["category"] or "GENERAL").upper()
        sec = row["total"] or 0
        grand_total += sec
        for key in dist:
            if key in cat:
                dist[key] += sec
                break
        else:
            dist["GENERAL"] += sec
    edu_pct = round((dist["EDUCATIONAL"] / max(1, grand_total)) * 100, 1)
    gaming_pct = round(((dist["GAMING"] + dist["VIDEO"]) / max(1, grand_total)) * 100, 1)
    social_pct = round((dist["SOCIAL"] / max(1, grand_total)) * 100, 1)
    other_pct = round(100 - edu_pct - gaming_pct - social_pct, 1)
    return {
        "educational_pct": edu_pct,
        "gaming_pct": gaming_pct,
        "social_pct": social_pct,
        "other_pct": max(0, other_pct),
        "total_seconds": grand_total,
        "breakdown": dist
    }


if __name__ == "__main__":
    print("[db_manager] Initializing comprehensive enterprise database...")
    init_db()
    configured = is_parent_configured()
    print(f"[db_manager] Parent Auth Configured: {configured}")
    verified = verify_parent_pin("1323")
    print(f"[db_manager] Verified Default Master PIN '1323': {verified}")
    policies = get_app_policies()
    print(f"[db_manager] Active Policies: {len(policies)}")

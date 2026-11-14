"""
db_manager.py
-------------
Unified Database Manager for Parental Control & Study Monitor.
Manages SQLite storage for:
1. user_state: Child balance, allowed screen time, and lock state.
2. time_logs: Historical balance and rule enforcement transaction logs.
3. tracked_processes: Windows applications detected, active time today, total time.
4. enforcement_rules: Parental rules, daily time limits, and blocking status.
"""

import sqlite3
import os
import sys
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager

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


@contextmanager
def get_db(db_path: Optional[str] = None):
    """
    Context manager that yields a SQLite connection with WAL journal mode
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


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initializes database schema if tables do not already exist:
    - user_state: current allowed balance (in seconds), daily limits, locked status.
    - time_logs: audit ledger for time changes and parental interventions.
    - tracked_processes: process usage tracking (today and all-time).
    - enforcement_rules: parental restrictions, process blacklists, daily limits.
    """
    target_path = db_path or DEFAULT_DB_PATH
    if target_path in _initialized_dbs and os.path.exists(target_path):
        return

    dir_name = os.path.dirname(os.path.abspath(target_path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with get_db(target_path) as conn:
        cursor = conn.cursor()

        # 1. user_state table
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

        # Add missing columns if upgrading an existing older DB
        cursor.execute("PRAGMA table_info(user_state);")
        cols = {row["name"] for row in cursor.fetchall()}
        if "daily_limit_minutes" not in cols:
            try:
                cursor.execute("ALTER TABLE user_state ADD COLUMN daily_limit_minutes INTEGER NOT NULL DEFAULT 120;")
            except Exception:
                pass
        if "is_blocked" not in cols:
            try:
                cursor.execute("ALTER TABLE user_state ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0;")
            except Exception:
                pass
        if "current_process" not in cols:
            try:
                cursor.execute("ALTER TABLE user_state ADD COLUMN current_process TEXT DEFAULT '';")
            except Exception:
                pass
        if "current_window" not in cols:
            try:
                cursor.execute("ALTER TABLE user_state ADD COLUMN current_window TEXT DEFAULT '';")
            except Exception:
                pass

        # Insert default row if table is empty
        cursor.execute("""
            INSERT OR IGNORE INTO user_state (id, current_balance, daily_limit_minutes, is_blocked, current_process, current_window, last_updated)
            VALUES (1, 0, 120, 0, '', '', ?)
        """, (datetime.now().isoformat(),))

        # 2. time_logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS time_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT
            );
        """)

        # 3. tracked_processes table
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

        # 4. enforcement_rules table
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

        # Seed initial standard rules if empty
        cursor.execute("SELECT COUNT(*) as cnt FROM enforcement_rules;")
        if cursor.fetchone()["cnt"] == 0:
            now_iso = datetime.now().isoformat()
            default_rules = [
                ("discord.exe", "Discord", 60, 0, "terminate", "Social & Chat", now_iso),
                ("steam.exe", "Steam", 60, 0, "terminate", "Gaming", now_iso),
                ("robloxplayerbeta.exe", "Roblox", 45, 0, "terminate", "Gaming", now_iso),
                ("minecraft.exe", "Minecraft", 45, 0, "terminate", "Gaming", now_iso),
                ("epicgameslauncher.exe", "Epic Games", 30, 0, "terminate", "Gaming", now_iso),
                ("tiktok.exe", "TikTok App", 0, 1, "terminate", "Social & Video", now_iso),
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO enforcement_rules
                (process_name, display_name, time_limit_minutes, is_blocked, action, category, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, default_rules)

        conn.commit()
    _initialized_dbs.add(target_path)


# ==============================================================================
# BALANCE & USER STATE OPERATIONS
# ==============================================================================

def get_current_balance(db_path: Optional[str] = None) -> int:
    """Retrieves current accumulated study/screen time balance (in seconds)."""
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
    """Updates the balance by delta, logs to time_logs, and returns new balance."""
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

        # If balance reaches 0, auto-flag is_blocked if exhausted
        is_blocked_flag = 1 if new_balance <= 0 and current_balance > 0 else 0

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
    """Resets the balance to an absolute number."""
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
    """Retrieves full child system state for Desktop App and Web Dashboard."""
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
            return dict(row)
        return {
            "current_balance": 0,
            "daily_limit_minutes": 120,
            "is_blocked": 0,
            "current_process": "",
            "current_window": "",
            "last_updated": datetime.now().isoformat()
        }


def update_child_state(
    current_process: Optional[str] = None,
    current_window: Optional[str] = None,
    is_blocked: Optional[int] = None,
    db_path: Optional[str] = None
) -> None:
    """Updates background runtime status in user_state."""
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
    """Explicitly sets or clears the system-wide blocked status."""
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
# PROCESS TRACKING OPERATIONS
# ==============================================================================

def record_process_usage(
    process_name: str,
    window_title: str = "",
    delta_seconds: int = 1,
    category: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Records elapsed time for a tracked application.
    Automatically resets today_time_seconds when crossing into a new day.
    """
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
            # Check if last active was a previous day
            last_date = row["last_active_date"]
            if last_date != today_str:
                today_sec = delta_seconds
            else:
                today_sec = row["today_time_seconds"] + delta_seconds

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

        # Reset active status of other processes
        cursor.execute("UPDATE tracked_processes SET is_active = 0 WHERE process_name != ?;", (process_name,))
        conn.commit()

        return {
            "process_name": process_name,
            "today_time_seconds": today_sec,
            "total_time_seconds": total_sec,
            "category": cat
        }


def get_tracked_processes(limit: int = 100, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns list of tracked processes sorted by today's usage descending."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*,
                   COALESCE(r.time_limit_minutes, 0) as time_limit_minutes,
                   COALESCE(r.is_blocked, 0) as rule_is_blocked,
                   COALESCE(r.action, 'none') as rule_action
            FROM tracked_processes p
            LEFT JOIN enforcement_rules r ON p.process_name = r.process_name
            ORDER BY p.today_time_seconds DESC, p.last_seen DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# ==============================================================================
# ENFORCEMENT RULES OPERATIONS
# ==============================================================================

def get_enforcement_rules(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all active parental enforcement rules."""
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
    """Inserts or updates an enforcement rule for a process."""
    init_db(db_path)
    p_name = process_name.strip().lower()
    disp = display_name or p_name.replace(".exe", "").capitalize()
    now_iso = datetime.now().isoformat()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO enforcement_rules
            (process_name, display_name, time_limit_minutes, is_blocked, action, category, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(process_name) DO UPDATE SET
                display_name = excluded.display_name,
                time_limit_minutes = excluded.time_limit_minutes,
                is_blocked = excluded.is_blocked,
                action = excluded.action,
                category = excluded.category;
        """, (p_name, disp, time_limit_minutes, is_blocked, action, category, now_iso))
        conn.commit()


def delete_enforcement_rule(process_name: str, db_path: Optional[str] = None) -> bool:
    """Deletes an enforcement rule by process name."""
    init_db(db_path)
    p_name = process_name.strip().lower()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM enforcement_rules WHERE process_name = ?;", (p_name,))
        conn.commit()
        return cursor.rowcount > 0


def check_process_restriction(process_name: str, db_path: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Checks if a process is currently restricted.
    Returns: (is_restricted, reason_string, rule_dict)
    """
    init_db(db_path)
    p_name = process_name.strip().lower()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM enforcement_rules WHERE process_name = ?;", (p_name,))
        rule = cursor.fetchone()
        if not rule:
            return False, "No rule", None

        rule_dict = dict(rule)

        # 1. Direct explicit block
        if rule_dict["is_blocked"] == 1:
            return True, f"Application '{rule_dict['display_name']}' is permanently blocked by parental control.", rule_dict

        # 2. Daily time limit check
        cursor.execute("SELECT today_time_seconds, last_active_date FROM tracked_processes WHERE process_name = ?;", (p_name,))
        p_row = cursor.fetchone()
        if p_row:
            today_str = date.today().isoformat()
            if p_row["last_active_date"] == today_str:
                used_min = p_row["today_time_seconds"] / 60.0
                limit_min = rule_dict["time_limit_minutes"]
                if limit_min > 0 and used_min >= limit_min:
                    return True, f"Time limit exceeded ({used_min:.1f}m / {limit_min}m allowed today).", rule_dict

        return False, "Allowed", rule_dict


def get_recent_logs(limit: int = 10, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves recent balance and enforcement logs."""
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
    """Helper to categorize common Windows applications."""
    p = process_name.lower()
    t = window_title.lower()

    games = ["roblox", "minecraft", "steam", "epicgames", "riot", "valorant", "fortnite", "genshin", "game"]
    if any(g in p or g in t for g in games):
        return "Gaming"

    social = ["discord", "tiktok", "instagram", "whatsapp", "telegram", "messenger", "twitter", "reddit"]
    if any(s in p or s in t for s in social):
        return "Social & Chat"

    video = ["netflix", "youtube", "twitch", "vlc", "spotify", "hulu", "disney"]
    if any(v in p or v in t for v in video):
        return "Entertainment"

    study = ["code", "pycharm", "cursor", "visual studio", "notepad", "word", "excel", "powerpnt", "canvas", "classroom"]
    if any(st in p or st in t for st in study):
        return "Educational / Productive"

    browsers = ["chrome", "msedge", "firefox", "brave", "opera"]
    if any(b in p for b in browsers):
        return "Web Browser"

    return "General"


if __name__ == "__main__":
    print("[db_manager] Initializing unified database...")
    init_db()
    current = get_current_balance()
    print(f"[db_manager] Current Balance: {current} seconds")
    rules = get_enforcement_rules()
    print(f"[db_manager] Active Rules Loaded: {len(rules)}")

"""
db_manager.py
-------------
Engineer 1 (Data & Logic - Lead)
Database module for the AI-Driven Contextual Study Monitor.

Manages SQLite storage for earned study time balance and transaction logs.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

DEFAULT_DB_FILE = "study_monitor.db"
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_DB_FILE)


@contextmanager
def get_db(db_path: Optional[str] = None):
    """
    Context manager that yields a SQLite connection and guarantees
    the connection handle is closed immediately on exit (essential for Windows).
    """
    target_path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initializes the database schema if tables do not already exist:
    - user_state: Tracks current running balance.
    - time_logs: Records every balance change with timestamp and reason.
    """
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        
        # Table to store single-record current balance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_balance INTEGER NOT NULL DEFAULT 0,
                last_updated TEXT NOT NULL
            );
        """)
        
        # Initialize default user state row if empty
        cursor.execute("""
            INSERT OR IGNORE INTO user_state (id, current_balance, last_updated)
            VALUES (1, 0, ?)
        """, (datetime.now().isoformat(),))

        # Table to store historical time accrual/drain logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS time_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT
            );
        """)
        
        conn.commit()


def get_current_balance(db_path: Optional[str] = None) -> int:
    """
    Retrieves the current accumulated study time balance (in seconds or units).
    Returns 0 if no balance has been initialized yet.
    """
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT current_balance FROM user_state WHERE id = 1;")
        row = cursor.fetchone()
        if row is not None:
            return int(row["current_balance"])
        return 0


def update_balance(
    delta: int, 
    reason: str = "", 
    clamp_min: Optional[int] = 0, 
    db_path: Optional[str] = None
) -> int:
    """
    Updates the current balance by adding `delta` (+1 reward, -1 drain, etc.).
    
    Args:
        delta: The amount to add or subtract from current balance.
        reason: Optional description of why balance changed (e.g., 'active_study', 'distraction_drain').
        clamp_min: Minimum allowable balance (default is 0 so balance cannot go negative).
        db_path: Optional custom path to SQLite database.
        
    Returns:
        The new integer balance after the update.
    """
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        
        # Read current balance
        cursor.execute("SELECT current_balance FROM user_state WHERE id = 1;")
        row = cursor.fetchone()
        current_balance = int(row["current_balance"]) if row else 0
        
        # Calculate new balance
        new_balance = current_balance + delta
        if clamp_min is not None and new_balance < clamp_min:
            new_balance = clamp_min
            
        # Update current balance in state table
        cursor.execute("""
            UPDATE user_state
            SET current_balance = ?, last_updated = ?
            WHERE id = 1;
        """, (new_balance, now_iso))
        
        # Append transaction to time_logs table
        cursor.execute("""
            INSERT INTO time_logs (timestamp, delta, balance_after, reason)
            VALUES (?, ?, ?, ?);
        """, (now_iso, delta, new_balance, reason))
        
        conn.commit()
        return new_balance


def get_recent_logs(limit: int = 10, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves the most recent time log entries for auditing and debugging."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, delta, balance_after, reason
            FROM time_logs
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def reset_balance(new_balance: int = 0, db_path: Optional[str] = None) -> int:
    """Resets the balance to a fixed number (useful for testing and checkpoint resets)."""
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


if __name__ == "__main__":
    print("[db_manager] Initializing database...")
    init_db()
    current = get_current_balance()
    print(f"[db_manager] Current Balance: {current}")
    updated = update_balance(+5, reason="cli_test_accrual")
    print(f"[db_manager] Updated Balance (+5): {updated}")
    print("[db_manager] Recent logs:", get_recent_logs(limit=3))

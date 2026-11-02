"""
desktop_app.py - Child's Desktop User App (Lightweight Tkinter GUI)
------------------------------------------------------------------
Lightweight, native GUI for the child's computer.
Strictly acts as a read-only viewer for the child:
- Reads allowed time and lock status directly from study_monitor.db.
- Displays remaining time countdown clock, active app info, and warnings.
- Does NOT perform any tracking or process termination itself (relies 100%
  on the headless Demon background service).
"""

import sys
import os
import time
import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict, Any

import db_manager


class ChildDesktopApp:
    """
    Lightweight, modern desktop HUD for the child's screen.
    Reads shared SQLite database (study_monitor.db) every 1 second.
    """

    def __init__(self, root: tk.Tk, db_path: Optional[str] = None):
        self.root = root
        self.db_path = db_path or db_manager.DEFAULT_DB_PATH
        self.root.title("Demon - Screen Time & Study Monitor")
        self.root.geometry("440x560")
        self.root.minsize(400, 500)
        self.root.configure(bg="#0b0f19")

        # Keep on top toggle
        self.always_on_top = tk.BooleanVar(value=True)
        self.root.attributes("-topmost", True)

        self._build_ui()
        self._refresh_from_db()

    def _build_ui(self):
        # 1. Top Header Bar
        header_frame = tk.Frame(self.root, bg="#111827", padx=16, pady=12)
        header_frame.pack(fill=tk.X)

        title_lbl = tk.Label(
            header_frame,
            text="🛡️ Focus & Study Monitor",
            font=("Segoe UI", 12, "bold"),
            fg="#f9fafb",
            bg="#111827"
        )
        title_lbl.pack(side=tk.LEFT)

        top_chk = tk.Checkbutton(
            header_frame,
            text="Pin on top",
            variable=self.always_on_top,
            command=self._toggle_topmost,
            font=("Segoe UI", 8),
            fg="#9ca3af",
            bg="#111827",
            selectcolor="#1f2937",
            activebackground="#111827",
            activeforeground="#f3f4f6"
        )
        top_chk.pack(side=tk.RIGHT)

        # 2. Main Content Container
        main_frame = tk.Frame(self.root, bg="#0b0f19", padx=20, pady=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Status Badge Pill
        self.status_pill = tk.Label(
            main_frame,
            text="CHECKING STATUS...",
            font=("Segoe UI", 9, "bold"),
            fg="#10b981",
            bg="#064e3b",
            padx=12,
            pady=4,
            relief=tk.FLAT
        )
        self.status_pill.pack(anchor=tk.CENTER, pady=(0, 10))

        # Digital Countdown Clock
        self.clock_lbl = tk.Label(
            main_frame,
            text="00:00:00",
            font=("Consolas", 38, "bold"),
            fg="#ffffff",
            bg="#0b0f19"
        )
        self.clock_lbl.pack(anchor=tk.CENTER, pady=4)

        self.sub_clock_lbl = tk.Label(
            main_frame,
            text="Remaining Study & Screen Time",
            font=("Segoe UI", 9),
            fg="#9ca3af",
            bg="#0b0f19"
        )
        self.sub_clock_lbl.pack(anchor=tk.CENTER, pady=(0, 14))

        # Progress Bar
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#1f2937",
            background="#4f46e5",
            thickness=6
        )
        self.prog_bar = ttk.Progressbar(
            main_frame,
            style="Custom.Horizontal.TProgressbar",
            orient="horizontal",
            mode="determinate",
            maximum=100,
            value=100
        )
        self.prog_bar.pack(fill=tk.X, pady=(0, 18))

        # Active App Info Card
        app_card = tk.LabelFrame(
            main_frame,
            text=" Current Active Application ",
            font=("Segoe UI", 9, "bold"),
            fg="#e5e7eb",
            bg="#111827",
            padx=14,
            pady=10,
            relief=tk.RIDGE
        )
        app_card.pack(fill=tk.X, pady=(0, 14))

        self.proc_lbl = tk.Label(
            app_card,
            text="Detecting active window...",
            font=("Segoe UI", 10, "bold"),
            fg="#60a5fa",
            bg="#111827",
            anchor="w"
        )
        self.proc_lbl.pack(fill=tk.X)

        self.win_lbl = tk.Label(
            app_card,
            text="",
            font=("Segoe UI", 8),
            fg="#9ca3af",
            bg="#111827",
            anchor="w",
            wraplength=360,
            justify=tk.LEFT
        )
        self.win_lbl.pack(fill=tk.X, pady=(2, 4))

        self.app_time_lbl = tk.Label(
            app_card,
            text="Time spent today: 0m",
            font=("Segoe UI", 8, "italic"),
            fg="#d1d5db",
            bg="#111827",
            anchor="w"
        )
        self.app_time_lbl.pack(fill=tk.X)

        # Active Rules Summary Card
        rules_card = tk.LabelFrame(
            main_frame,
            text=" Daily Parental Limits & Rules ",
            font=("Segoe UI", 9, "bold"),
            fg="#e5e7eb",
            bg="#111827",
            padx=14,
            pady=10,
            relief=tk.RIDGE
        )
        rules_card.pack(fill=tk.BOTH, expand=True)

        self.rules_listbox = tk.Listbox(
            rules_card,
            font=("Segoe UI", 8),
            bg="#111827",
            fg="#d1d5db",
            selectbackground="#1f2937",
            highlightthickness=0,
            relief=tk.FLAT
        )
        self.rules_listbox.pack(fill=tk.BOTH, expand=True)

        # Bottom Notice Bar
        footer = tk.Frame(self.root, bg="#070a12", padx=16, pady=8)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        self.footer_lbl = tk.Label(
            footer,
            text="Background Tracker: Active (System Service)",
            font=("Segoe UI", 7),
            fg="#6b7280",
            bg="#070a12"
        )
        self.footer_lbl.pack(anchor=tk.CENTER)

    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.always_on_top.get())

    def _format_time(self, seconds: int) -> str:
        s = max(0, seconds)
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        return f"{h:02d}:{m:02d}:{sec:02d}"

    def _refresh_from_db(self):
        """Polls study_monitor.db every second and updates the child GUI."""
        try:
            state = db_manager.get_child_state(db_path=self.db_path)
            balance = state.get("current_balance", 0)
            is_blocked = state.get("is_blocked", 0)
            daily_limit = state.get("daily_limit_minutes", 120) * 60
            curr_proc = state.get("current_process", "")
            curr_win = state.get("current_window", "")

            # 1. Update Clock
            self.clock_lbl.config(text=self._format_time(balance))

            # 2. Update Progress Bar
            if daily_limit > 0:
                pct = min(100, max(0, (balance / daily_limit) * 100))
                self.prog_bar["value"] = pct

            # 3. Update Status Pill & Warning Colors
            if is_blocked == 1 or balance <= 0:
                self.status_pill.config(
                    text="LOCKDOWN: SCREEN TIME EXPIRED",
                    fg="#f87171",
                    bg="#450a0a"
                )
                self.clock_lbl.config(fg="#ef4444")
            elif balance <= 300:  # <= 5 minutes
                self.status_pill.config(
                    text="WARNING: LESS THAN 5 MINUTES LEFT",
                    fg="#fde047",
                    bg="#713f12"
                )
                self.clock_lbl.config(fg="#f59e0b")
            else:
                self.status_pill.config(
                    text="SESSION ACTIVE · TIME REMAINING",
                    fg="#34d399",
                    bg="#064e3b"
                )
                self.clock_lbl.config(fg="#ffffff")

            # 4. Update Current App Display
            if curr_proc:
                self.proc_lbl.config(text=curr_proc.upper())
                self.win_lbl.config(text=curr_win or "Active window")

                # Fetch usage for this app
                procs = db_manager.get_tracked_processes(limit=50, db_path=self.db_path)
                matching = next((p for p in procs if p["process_name"] == curr_proc), None)
                if matching:
                    today_m = round(matching["today_time_seconds"] / 60, 1)
                    limit_m = matching["time_limit_minutes"]
                    limit_str = f" / {limit_m}m limit" if limit_m > 0 else " (No limit)"
                    self.app_time_lbl.config(text=f"Time used today: {today_m}m{limit_str}")
                else:
                    self.app_time_lbl.config(text="Time used today: <1m")
            else:
                self.proc_lbl.config(text="Desktop Idle")
                self.win_lbl.config(text="No active tracked application")
                self.app_time_lbl.config(text="")

            # 5. Update Rules Summary (every 5 seconds to reduce redraws)
            rules = db_manager.get_enforcement_rules(db_path=self.db_path)
            self.rules_listbox.delete(0, tk.END)
            for r in rules:
                p_name = r["process_name"]
                if r["is_blocked"] == 1:
                    status = "[BLOCKED]"
                elif r["time_limit_minutes"] > 0:
                    status = f"[{r['time_limit_minutes']}m limit]"
                else:
                    status = "[Allowed]"
                self.rules_listbox.insert(tk.END, f" {status:<15} {p_name} ({r['category']})")

        except Exception as e:
            # Concurrency safety: Ignore temporary read collisions
            pass

        # Schedule next tick in 1000ms
        self.root.after(1000, self._refresh_from_db)


def main():
    root = tk.Tk()
    app = ChildDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

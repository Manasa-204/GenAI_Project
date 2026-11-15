"""
desktop_app.py - Student Desktop Focus HUD GUI (Demon Study Monitor)
Checkpoint 9: Modernized Student Desktop Focus HUD
Features:
- Custom-drawn circular canvas progress arc showing live focus score and battery percentage.
- Two separate live counters: Study Time Earned Today vs. Remaining Leisure Balance.
- Zen mode completely removed as requested.
- Dynamic 1-second synchronization with background daemon & SQLite database.
- Real-time Emergency Lockdown Active banner with countdown timer.
- Anti-tamper exit protection: X button prompts for Master PIN ('1323').
  Entering wrong PIN rejects exit and logs TAMPER_ATTEMPT security alert.
"""

import os
import sys
import time
import math
import json
import urllib.request
import tkinter as tk
from tkinter import messagebox

import db_manager


class StudentDesktopHUD:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Demon - Student Focus HUD")
        self.root.geometry("380x640")
        self.root.minsize(360, 600)
        self.root.configure(bg="#070a12")

        # Keep on top toggle option
        self.root.attributes("-topmost", True)

        # Anti-tamper window close protocol
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_requested)

        # State Variables
        self.focus_score = 85.0
        self.posture = "DIRECT_FOCUS"
        self.color = "#10b981"
        self.study_today_str = "00h 00m 00s"
        self.leisure_bal_str = "00m 00s"
        self.active_app = "Demon Focus HUD"
        self.active_cat = "Educational"
        self.battery_pct = 94

        self._build_ui()
        self.update_telemetry()

    def _build_ui(self):
        # 1. Header Frame
        self.header_frame = tk.Frame(self.root, bg="#070a12", pady=10, padx=16)
        self.header_frame.pack(fill="x")

        title_lbl = tk.Label(
            self.header_frame,
            text="DEMON FOCUS HUD",
            font=("Plus Jakarta Sans", 11, "bold"),
            fg="#f1f5f9",
            bg="#070a12"
        )
        title_lbl.pack(side="left")

        self.role_badge = tk.Label(
            self.header_frame,
            text="STUDENT VIEW",
            font=("JetBrains Mono", 8, "bold"),
            fg="#818cf8",
            bg="#1e1b4b",
            padx=8,
            pady=2
        )
        self.role_badge.pack(side="right")

        # 2. Emergency Lockdown Pulsing Banner (Checkpoint 1)
        self.lockdown_frame = tk.Frame(self.root, bg="#881337", pady=8, padx=12)
        self.lockdown_label = tk.Label(
            self.lockdown_frame,
            text="🔒 EMERGENCY LOCKDOWN ACTIVE: 15:00",
            font=("Plus Jakarta Sans", 9, "bold"),
            fg="#ffffff",
            bg="#881337"
        )
        self.lockdown_label.pack()
        # Hidden by default
        self.lockdown_active = False

        # 3. Circular Canvas Progress Arc (Live Focus Score & Battery Percentage)
        self.canvas_frame = tk.Frame(self.root, bg="#070a12", pady=4)
        self.canvas_frame.pack()

        self.canvas = tk.Canvas(self.canvas_frame, width=200, height=200, bg="#070a12", highlightthickness=0)
        self.canvas.pack()

        # Battery / Stamina strip
        self.battery_label = tk.Label(
            self.root,
            text="⚡ Focus Energy Stamina: 94%",
            font=("JetBrains Mono", 9, "bold"),
            fg="#818cf8",
            bg="#0f172a",
            pady=4,
            padx=12
        )
        self.battery_label.pack(pady=4)

        # 4. Dual Time Counters Frame
        self.counters_frame = tk.Frame(self.root, bg="#070a12", padx=16, pady=6)
        self.counters_frame.pack(fill="x")

        # Card 1: Study Time Earned Today
        self.study_card = tk.Frame(self.counters_frame, bg="#064e3b", padx=12, pady=10, relief="flat")
        self.study_card.pack(fill="x", pady=4)

        study_title = tk.Label(
            self.study_card,
            text="🎓 STUDY TIME EARNED TODAY",
            font=("Plus Jakarta Sans", 8, "bold"),
            fg="#34d399",
            bg="#064e3b"
        )
        study_title.pack(anchor="w")

        self.study_val_lbl = tk.Label(
            self.study_card,
            text="00h 00m 00s",
            font=("JetBrains Mono", 14, "bold"),
            fg="#ffffff",
            bg="#064e3b"
        )
        self.study_val_lbl.pack(anchor="w", pady=(2, 0))

        # Card 2: Remaining Leisure Balance
        self.leisure_card = tk.Frame(self.counters_frame, bg="#1e1b4b", padx=12, pady=10, relief="flat")
        self.leisure_card.pack(fill="x", pady=4)

        leisure_title = tk.Label(
            self.leisure_card,
            text="🎮 REMAINING LEISURE BALANCE",
            font=("Plus Jakarta Sans", 8, "bold"),
            fg="#a5b4fc",
            bg="#1e1b4b"
        )
        leisure_title.pack(anchor="w")

        self.leisure_val_lbl = tk.Label(
            self.leisure_card,
            text="00m 00s",
            font=("JetBrains Mono", 14, "bold"),
            fg="#ffffff",
            bg="#1e1b4b"
        )
        self.leisure_val_lbl.pack(anchor="w", pady=(2, 0))

        # 5. Active Foreground App Card (Checkpoint 7)
        self.app_frame = tk.Frame(self.root, bg="#0f172a", padx=12, pady=8)
        self.app_frame.pack(fill="x", padx=16, pady=6)

        app_title = tk.Label(
            self.app_frame,
            text="ACTIVE APPLICATION",
            font=("Plus Jakarta Sans", 7, "bold"),
            fg="#94a3b8",
            bg="#0f172a"
        )
        app_title.pack(anchor="w")

        self.app_name_lbl = tk.Label(
            self.app_frame,
            text="Scanning active process...",
            font=("JetBrains Mono", 9, "bold"),
            fg="#e2e8f0",
            bg="#0f172a"
        )
        self.app_name_lbl.pack(anchor="w")

        # 6. Policy Quota Strip
        self.quota_label = tk.Label(
            self.root,
            text="YouTube Quota: 45m remaining",
            font=("JetBrains Mono", 8),
            fg="#64748b",
            bg="#070a12",
            pady=4
        )
        self.quota_label.pack(side="bottom", pady=8)

        self._draw_circle(self.focus_score, self.color, self.posture)

    def _draw_circle(self, score: float, color: str, posture: str):
        """Draws custom smooth circular canvas progress arc."""
        self.canvas.delete("all")
        cx, cy, r = 100, 100, 75
        width = 12

        # Background Track
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline="#1e293b", width=width
        )

        # Dynamic Arc
        angle = int((score / 100.0) * 359.9)
        if angle > 0:
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=90, extent=-angle,
                outline=color, width=width, style="arc"
            )

        # Text in center
        self.canvas.create_text(
            cx, cy - 8,
            text=f"{int(score)}%",
            font=("JetBrains Mono", 24, "bold"),
            fill="#ffffff"
        )
        self.canvas.create_text(
            cx, cy + 20,
            text=posture.replace("_", " "),
            font=("Plus Jakarta Sans", 8, "bold"),
            fill=color
        )

    def update_telemetry(self):
        """Queries local status and dynamically refreshes GUI elements every second."""
        try:
            # First attempt REST API query from local server
            req = urllib.request.Request("http://127.0.0.1:8000/api/status", headers={"User-Agent": "DemonHUD"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            score = data["camera"].get("focus_score", 85.0)
            posture = data["camera"].get("posture", "DIRECT_FOCUS")
            col_name = data["camera"].get("color", "emerald")
            col_hex = "#10b981" if col_name == "emerald" else ("#f59e0b" if col_name == "amber" else "#f43f5e")

            study_today = data.get("study_time_today_str", "00h 00m 00s")
            leisure_bal = data.get("leisure_balance_str", "00m 00s")
            active_app = data["stats"].get("active_app", "System")
            active_cat = data["stats"].get("semantic_state", "Educational")

            # Lockdown status
            ld = data.get("lockdown", {})
            is_locked = ld.get("is_active", False)
            rem_sec = ld.get("seconds_remaining", 0)

            # Policy quota status
            policies = data.get("policies", [])
            yt_pol = next((p for p in policies if "youtube" in p.get("app_or_domain", "")), None)
            if yt_pol:
                yt_rem_m = int(yt_pol["remaining_seconds"] // 60)
                yt_rem_s = int(yt_pol["remaining_seconds"] % 60)
                self.quota_label.config(text=f"YouTube Quota: {yt_rem_m}m {yt_rem_s}s remaining")

        except Exception:
            # Fallback directly to SQLite database
            db_bal = db_manager.get_current_balance()
            study_sec = db_manager.get_today_study_time()
            mins_s = study_sec // 60
            study_today = f"{mins_s // 60:02d}h {mins_s % 60:02d}m {study_sec % 60:02d}s"
            leisure_bal = f"{db_bal // 60:02d}m {db_bal % 60:02d}s"
            score = 85.0
            posture = "DIRECT_FOCUS"
            col_hex = "#10b981"
            active_app = "Demon Focus Daemon"
            is_locked = False
            rem_sec = 0

        # Update HUD Elements
        self._draw_circle(score, col_hex, posture)
        self.study_val_lbl.config(text=study_today)
        self.leisure_val_lbl.config(text=leisure_bal)
        self.app_name_lbl.config(text=active_app)

        # Battery calculation
        batt = int(min(100, max(20, score * 1.05)))
        self.battery_label.config(text=f"⚡ Focus Energy Stamina: {batt}%")

        # Emergency Lockdown Banner
        if is_locked:
            if not self.lockdown_active:
                self.lockdown_frame.pack(after=self.header_frame, fill="x", pady=2)
                self.lockdown_active = True
            mins = rem_sec // 60
            secs = rem_sec % 60
            self.lockdown_label.config(text=f"🔒 EMERGENCY LOCKDOWN: {mins:02d}:{secs:02d}")
        else:
            if self.lockdown_active:
                self.lockdown_frame.pack_forget()
                self.lockdown_active = False

        # Schedule next update in 1 second
        self.root.after(1000, self.update_telemetry)

    def on_close_requested(self):
        """
        Anti-Tamper Exit Protection (Checkpoint 9):
        Prompts for Master PIN ('1323').
        If incorrect, rejects exit and logs TAMPER_ATTEMPT security alert.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Authentication Required")
        dialog.geometry("300x180")
        dialog.configure(bg="#0f172a")
        dialog.transient(self.root)
        dialog.grab_set()

        lbl = tk.Label(
            dialog,
            text="Enter Parent Master PIN to Exit:",
            font=("Plus Jakarta Sans", 9, "bold"),
            fg="#f8fafc",
            bg="#0f172a",
            pady=10
        )
        lbl.pack()

        pin_entry = tk.Entry(
            dialog,
            show="*",
            font=("JetBrains Mono", 14, "bold"),
            justify="center",
            width=10,
            bg="#1e293b",
            fg="#ffffff",
            insertbackground="#ffffff"
        )
        pin_entry.pack(pady=5)
        pin_entry.focus()

        err_lbl = tk.Label(dialog, text="", font=("Plus Jakarta Sans", 8), fg="#f43f5e", bg="#0f172a")
        err_lbl.pack()

        def submit():
            entered = pin_entry.get().strip()
            if db_manager.verify_security_pin(entered):
                dialog.destroy()
                self.root.destroy()
            else:
                db_manager.log_security_alert("TAMPER_ATTEMPT", f"Desktop HUD exit attempted with invalid PIN: '{entered}'")
                err_lbl.config(text="Access Denied! Incorrect PIN.")
                pin_entry.delete(0, tk.END)

        btn_frame = tk.Frame(dialog, bg="#0f172a", pady=10)
        btn_frame.pack()

        tk.Button(
            btn_frame,
            text="Cancel",
            command=dialog.destroy,
            font=("Plus Jakarta Sans", 8),
            bg="#334155",
            fg="#ffffff",
            padx=10
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="Unlock & Exit",
            command=submit,
            font=("Plus Jakarta Sans", 8, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            padx=10
        ).pack(side="left", padx=5)

        pin_entry.bind("<Return>", lambda e: submit())


def main():
    root = tk.Tk()
    app = StudentDesktopHUD(root)
    root.mainloop()


if __name__ == "__main__":
    main()

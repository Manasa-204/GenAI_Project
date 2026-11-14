# MASTER PROMPT: FULL SYSTEM EXPANSION — DEMON AI STUDY MONITOR (DUAL-PORTAL DESKTOP PLATFORM)

You are tasked with expanding the "Demon Study Monitor" system into an enterprise-ready, dual-portal (Parent Admin vs. Student Client) desktop application with advanced 3D anthropometric kinematic classification, granular time budgeting, YouTube distraction sub-filtering, and tamper-resistant OS enforcement.

================================================================================
CRITICAL ARCHITECTURAL CONSTRAINTS & NON-BREAKING MANDATE:
1. All existing modules (`db_manager.py`, `logic_controller.py`, `vision_pipeline.py`, `semantic_pipeline.py`, `enforcement.py`, `main.py`, `orchestrator.py`) MUST maintain backward compatibility.
2. Existing unit tests (`test_db_manager.py`, `test_checkpoint_1.py`, `test_checkpoint_2.py`, `test_system_orchestration.py`, `test_enforcement_cases.py`) MUST pass without regression.
3. Every new capability must be designed additively using modular classes, decorators, and non-destructive database migrations.
================================================================================

--------------------------------------------------------------------------------
FEATURE 1: DUAL-PORTAL SYSTEM & ROLE-BASED ACCESS CONTROL (RBAC)
--------------------------------------------------------------------------------
1.1 Cryptographic Parent Authentication & Profile Isolation:
   - Module: `db_manager.py` (extend database initialization).
   - Implement Table `parent_auth`:
     * Columns: `id` (INTEGER PK), `password_hash` (TEXT), `salt` (TEXT), `pin_hash` (TEXT), `created_at` (TIMESTAMP), `last_login` (TIMESTAMP).
     * Algorithm: PBKDF2-HMAC-SHA256 with 100,000 iterations and a 16-byte cryptographically secure salt (`secrets.token_bytes(16)`).
     * Functions:
       - `setup_parent_credentials(pin: str, password: Optional[str] = None)`
       - `verify_parent_pin(pin: str) -> bool`
       - `is_parent_configured() -> bool`
     * On first run: Prompt for 4-to-6 digit Master PIN initialization.

1.2 Role Separation & Views:
   - Provide an in-memory/session-based role state: `CURRENT_ROLE: "STUDENT" | "PARENT"`.
   - Student Mode (Default Unprivileged):
     * Starts automatically on system boot.
     * Non-intrusive floating HUD widget or compact window.
     * Read-only access to earned balance, focus streak, and allowed leisure budget.
     * All settings, process termination, domain unblocking, and database tables are locked.
   - Parent Admin Mode (Elevated & Protected):
     * Accessed by clicking an "Admin / Parent" lock icon in the UI and validating the Master PIN.
     * Full access to policy configuration, live telemetry, security audit logs, camera calibration, and emergency overrides.
     * Auto-locks back to Student Mode after 5 minutes of inactivity.

--------------------------------------------------------------------------------
FEATURE 2: COMPREHENSIVE POLICY ENGINE, TIME-BUDGETING & QUOTAS
--------------------------------------------------------------------------------
2.1 Policy Database Schema:
   - Table `app_policies`:
     * Columns: `id` (INTEGER PK), `target_name` (TEXT UNIQUE - e.g., "youtube.com", "discord.exe", "instagram.com"), `category` (TEXT - "VIDEO", "SOCIAL", "GAMING", "MESSAGING"), `policy_type` (TEXT - "HARD_BLOCK", "DAILY_QUOTA", "SCHEDULED_CURFEW"), `daily_quota_seconds` (INTEGER DEFAULT 0), `used_today_seconds` (INTEGER DEFAULT 0), `curfew_start` (TEXT - "HH:MM"), `curfew_end` (TEXT - "HH:MM"), `is_active` (BOOLEAN DEFAULT 1).
   - Table `parent_alerts`:
     * Columns: `id` (INTEGER PK), `timestamp` (TIMESTAMP), `target_app` (TEXT), `event_type` (TEXT - "UNAUTHORIZED_ATTEMPT", "QUOTA_EXHAUSTED", "MICROSLEEP_CLUSTER", "TAMPER_ATTEMPT"), `severity` (TEXT - "INFO", "WARNING", "CRITICAL"), `details` (TEXT), `acknowledged` (BOOLEAN DEFAULT 0).
   - Table `daily_focus_metrics`:
     * Columns: `date` (DATE PK), `total_study_seconds` (INTEGER), `pure_focus_seconds` (INTEGER), `drowsy_seconds` (INTEGER), `away_seconds` (INTEGER), `distraction_attempts` (INTEGER), `focus_quality_score` (FLOAT 0-100).

2.2 Quota & Curfew Evaluation Engine:
   - Module: Create `policy_engine.py` (interfacing with `logic_controller.py` and `enforcement.py`).
   - Evaluator Logic:
     1. Hard Block: If target in `app_policies` has `policy_type == "HARD_BLOCK"`, instantly block via `enforcement.py` and minimize foreground window.
     2. Curfew Window: If current system time falls within `[curfew_start, curfew_end]`, target is blocked regardless of study balance.
     3. Daily Quota:
        * Track active foreground usage per target.
        * If `used_today_seconds >= daily_quota_seconds`:
          - Transition target status to `BLOCKED_QUOTA_EXCEEDED`.
          - Dispatch alert to `parent_alerts`.
          - Call `enforcement.block_distractions()` for that domain.
     4. Earn-and-Burn Integration:
        * Link general leisure allowance to the study balance: 1 second of leisure consumes 1 second of earned balance. If balance drops to 0, entertainment shuts down.
     5. Midnight Reset: Automated cron/timer resetting `used_today_seconds` at 00:00:00 local time.

2.3 Real-Time Alert Dispatcher:
   - When a student attempts to launch a restricted app or visit a blocked domain:
     * Log incident into `parent_alerts`.
     * Sound an optional subtle auditory notification.
     * Show a native Windows system notification / desktop toast on the parent workstation.
     * Expose a WebSocket event: `{"event": "PARENT_ALERT", "data": {...}}`.

--------------------------------------------------------------------------------
FEATURE 3: ADVANCED 3D KINEMATICS & POSTURE CLASSIFICATION MATRIX
--------------------------------------------------------------------------------
3.1 Sensor Fusion Pipeline:
   - Module: Extend `vision_pipeline.py` and `user_tracker.py`.
   - Inputs to fuse:
     * MediaPipe 478-point 3D Face Mesh.
     * Eye Aspect Ratio (EAR) across left & right eye landmarks.
     * 6-DOF Head Pose via OpenCV `solvePnP` (Pitch, Yaw, Roll in degrees).
     * Foreground user input tracker (Keyboard & Mouse activity via Win32 `GetLastInputInfo`).

3.2 Comprehensive Movement & Posture Matrix Specification:
   The classifier must return a discrete sub-state from the following 8 states:
   1. `DIRECT_FOCUS`:
      * Pitch: -10° to +10° | Yaw: -15° to +15° | EAR > 0.20.
      * Input: Active mouse/keyboard OR reading pause < 10s.
      * Impact: Balance Delta = +1s (Accruing).
   2. `PASSIVE_READING`:
      * Pitch: -12° to +12° | Yaw: -15° to +15° | EAR > 0.20.
      * Input: 0 keystrokes/mouse for 10s to 30s, natural micro-blinks (150-300ms).
      * Impact: Balance Delta = +1s (Do not penalize deep reading).
   3. `DESK_NOTE_TAKING`:
      * Pitch: -15° to -32° (downward angle toward notebook) | Yaw: -20° to +20°.
      * EAR: Eyelids appear narrowed due to downward gaze, but not closed.
      * Peripheral: Periodic micro-movements of head/hand.
      * Impact: Balance Delta = +1s (or hold neutral balance).
   4. `MOBILE_DISTRACTION`:
      * Pitch: -15° to -35° | Gaze: Centered downwards into lap or hands.
      * Input: 0 PC keyboard/mouse events for > 3.0s continuously.
      * Impact: Balance Delta = -1s (Drain). After 10s of sustained mobile distraction, log a distraction alert.
   5. `LOOKING_AWAY`:
      * Yaw: > 28° or < -28° (turned toward room/window) sustained > 2.5s.
      * Impact: Balance Delta = -1s (Drain / Pause).
   6. `DROWSY_MICROSLEEP`:
      * EAR < 0.18 sustained for >= 2.0s with characteristic slow eyelid droop or downward head nod.
      * Impact: Vision Override = -1s. Trigger drowsiness notification to student.
   7. `ABANDONED_DESK`:
      * 0 faces detected in camera frustum for > 3.0s.
      * Impact: Auto-freeze session timer. Do not accrue or drain.
   8. `DUAL_MONITOR_FOCUS`:
      * Yaw: 20° to 38° sustained, BUT mouse coordinates are actively moving on Secondary Display screen bounds (`screeninfo` / `pygetwindow`).
      * Impact: Balance Delta = +1s (Classified as focused, zero penalty).

3.3 Temporal Hysteresis & Anti-Flicker Filter:
   - Prevent state flapping: Any state transition requires a rolling 2.0-second sliding confirmation window.
   - Natural micro-blinks (closures < 350ms) must NEVER trigger the `DROWSY` state.

--------------------------------------------------------------------------------
FEATURE 4: GRANULAR YOUTUBE & DIGITAL DEVIATION FILTERING
--------------------------------------------------------------------------------
4.1 Multi-Tier Content Inspection:
   - Module: Extend `semantic_pipeline.py`.
   - Tier 1: Regex & Title Decomposition:
     * Extract active browser window title format: `"{Video Title} - YouTube - {Browser}"`.
     * Extract regex patterns:
       - Whitelisted / Educational: Calculus, Physics, Khan Academy, Python, Lecture, Tutorial, Coursera, Documentation, Course.
       - Blacklisted / Entertainment: Shorts, Meme, Gameplay, Stream, Walkthrough, React, VLOG, TikTok, Music Video, Trailer, Speedrun.
     * If YouTube is running:
       - If Title matches Educational -> Classify as `EDUCATIONAL` (+1s accrual).
       - If Title contains `/shorts/` or matches Entertainment -> Classify as `DISTRACTION` (-1s drain, and enforce window minimization if balance <= 0).
   - Tier 2: Category Identification:
     * Detect and classify other child-deviation desktop apps:
       - Gaming: `RobloxPlayerBeta.exe`, `Minecraft.exe`, `Steam.exe`, `EpicGamesLauncher.exe`, `Valorant.exe`.
       - Social: `Discord.exe`, `WhatsApp.exe`, `Telegram.exe`.
     * Match process names and window titles against `app_policies`.

4.2 Enforcement Escalation:
   - Level 1: Gentle UI warning overlay on screen ("This content is categorized as Entertainment").
   - Level 2: Minimize foreground window (`user32.ShowWindow(hwnd, SW_MINIMIZE)`).
   - Level 3: Network loopback routing via OS `hosts` file modification (`enforcement.py`) and DNS cache flush (`ipconfig /flushdns`).

--------------------------------------------------------------------------------
FEATURE 5: DASHBOARD UI TRANSFORMATION & CLEAN METRICS
--------------------------------------------------------------------------------
5.1 UI Decluttering & Architectural Cleanup:
   - Clean up `web_dashboard.py` frontend:
     * Strip away from the primary view: Raw EAR float numbers, Euler pitch/yaw degrees, mock scenario buttons ("Inject Sleep"), and raw CSV table dumps.
     * Move all test suites and low-level sensor readouts into a secure, collapsible "Diagnostics & Calibration" drawer (accessible only in Parent Mode).

5.2 Student Dashboard (Minimal & Motivational):
   - Hero Element: Circular progress ring showing Earned Study Balance (HH:MM:SS) and current Focus Streak.
   - Dynamic Status Pill:
     * Green: "Focused & Learning"
     * Blue: "Note-Taking / Reading"
     * Orange: "Looking Away (Timer Paused)"
     * Red: "Distraction Active"
   - Entertainment Allowance Card: Visual remaining budget for permitted apps (e.g., "YouTube: 15 / 30 mins used today").
   - Friendly Context Banners: "Take a 5-minute break" or "You earned 20 minutes of leisure time!".

5.3 Parent Admin Dashboard (Observational & Actionable):
   - Focus Quality Scorecard: Aggregate circular gauge (0–100%) calculated via:
     `Focus_Score = (Pure_Focus_Time / (Total_Session_Time - Away_Time)) * 100`
   - Visual Chronological Day Timeline:
     * An interactive 24-hour horizontal bar color-coded by event:
       - Green = Focused Study
       - Yellow = Drowsiness / Microsleep
       - Gray = Away / Inactive
       - Red = Blocked App Access Attempt
   - App Usage Distribution: Clean bar/donut chart comparing Educational Software vs. Web Browsers vs. Entertainment.
   - Incident & Alert Feed: Live chronological log of policy infractions with an "Acknowledge" button.
   - Policy & Quota Control Panel: Toggle buttons to block/allow apps, slider controls for daily minute quotas, and curfew time pickers.

--------------------------------------------------------------------------------
FEATURE 6: DESKTOP APPLICATION PACKAGING & ANTI-TAMPER SECURITY
--------------------------------------------------------------------------------
6.1 Desktop Client Wrapper:
   - Module: Refactor `desktop_app.py`.
   - Implement native desktop integration using PyWebView or PySide6:
     * Borderless modern window, dark theme (`#0f172a`), 1280x850 default resolution.
     * System Tray integration: Minimizes to system tray with quick status tooltip ("Demon Monitor: Active - Student Focused").
     * Auto-start with Windows option (Registry key `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).

6.2 Anti-Tamper & Resilience:
   - Watchdog Architecture:
     * The background monitoring daemon runs detached from the main UI window. If the student closes the UI window, the monitoring and enforcement engine continues running in the system tray.
   - Protected Exit:
     * Attempting to close the app via system tray, UI exit button, or hotkey triggers a PIN prompt. Without the Master Parent PIN, the app cannot be exited.
   - Graceful Exit Guarantee:
     * In the event of a system reboot or authorized exit via Parent PIN, `enforcement.unblock_distractions()` is reliably executed via `atexit` and `signal` handlers to ensure system hosts are never left locked.

--------------------------------------------------------------------------------
FEATURE 7: ENVIRONMENT STANDARDIZATION & CALIBRATION WIZARD
--------------------------------------------------------------------------------
7.1 MediaPipe Compatibility Fix:
   - Ensure explicit compatibility with `mediapipe==0.10.14` and `numpy<2.0.0` so that `mp.solutions.face_mesh` operates without deprecation failures.
   - Provide fallback initialization: Wrap FaceMesh instantiation with a safety fallback that gracefully falls back to mock mode if camera hardware is occupied or unavailable.

7.2 30-Second User Calibration Wizard:
   - Interactive 3-step setup modal on first launch:
     * Step 1: "Look directly at your screen" -> Records baseline Pitch, Yaw, and open-eye EAR.
     * Step 2: "Close your eyes for 3 seconds" -> Records closed-eye EAR threshold (automatically sets dynamic EAR threshold at `(Open_EAR + Closed_EAR) / 2`).
     * Step 3
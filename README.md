# Demon AI - Contextual Study Monitor & Dual-Portal Focus Platform

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-blue.svg)](https://microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.13-brightgreen.svg)](https://python.org)
[![Engineers](https://img.shields.io/badge/Engineering-4%20Specialized%20Roles-indigo.svg)](#multi-agent-engineering-roles)
[![Tests](https://img.shields.io/badge/Test%20Suite-9%2F9%20Passed%20(100%25)-emerald.svg)](#verification--test-suite)
[![Branch](https://img.shields.io/badge/Branch-loki-purple.svg)](https://github.com/Manasa-204/GenAI_Project/tree/loki)

**Demon** is an autonomous, tamper-resistant, dual-portal parental control and attentive study enforcement platform. Engineered around physical kinematics, semantic context understanding, and OS-level enforcement, Demon ensures focused academic learning by dynamically budgeting screen time, neutralizing digital deviations, and providing real-time AI supervision without compromising student well-being.

---

## Table of Contents
1. [Multi-Agent Engineering Roles](#multi-agent-engineering-roles)
2. [Dual-View & Dual-Portal Architecture](#dual-view--dual-portal-architecture)
3. [Master Expansion Features](#master-expansion-features)
   - [Feature 1: Dual-Portal System & RBAC (PBKDF2 Auth)](#feature-1-dual-portal-system--rbac)
   - [Feature 2: Comprehensive Policy Engine, Quotas & Curfews](#feature-2-comprehensive-policy-engine-quotas--curfews)
   - [Feature 3: Advanced 3D Kinematics & 8-State Posture Matrix](#feature-3-advanced-3d-kinematics--8-state-posture-matrix)
   - [Feature 4: Granular YouTube & Digital Deviation Filtering](#feature-4-granular-youtube--digital-deviation-filtering)
   - [Feature 5: Dashboard UI Transformation (Student vs Parent)](#feature-5-dashboard-ui-transformation)
   - [Feature 6: Desktop Client Packaging & Anti-Tamper OS Protection](#feature-6-desktop-client-packaging--anti-tamper-os-protection)
   - [Feature 7: MediaPipe Compatibility & 30s Calibration Wizard](#feature-7-mediapipe-compatibility--calibration-wizard)
4. [Quick Start & Launch Guide](#quick-start--launch-guide)
5. [Windows Service Persistence & PyInstaller](#windows-service-persistence--pyinstaller)
6. [Web Dashboard REST API Reference](#web-dashboard-rest-api-reference)
7. [Verification & Test Suite](#verification--test-suite)
8. [Project Structure](#project-structure)

---

## Multi-Agent Engineering Roles

The platform was architected across four dedicated engineering submodules:

- **Engineer 1 (Data & Logic - Lead)**: SQLite persistent database (`db_manager.py`), policy engine (`policy_engine.py`), AND Gate Decision Controller (`logic_controller.py`), and headless background orchestrator (`main.py`).
- **Engineer 2 (Computer Vision)**: Webcam kinematics capture, MediaPipe 478 3D landmark mesh, solvePnP 6-DOF head pose estimation, Eye Aspect Ratio (EAR) micro-sleep detection, and primary user facial anchoring (`vision_pipeline.py`, `user_tracker.py`).
- **Engineer 3 (NLP & App Integration)**: OS window scraping via Win32 `ctypes` & `pygetwindow`, regex window title decomposition, and local Ollama SLM prompt inference (`semantic_pipeline.py`).
- **Engineer 4 (Systems & OS Enforcement)**: Windows hosts file loopback redirection (`127.0.0.1` / `::1`), zero-tolerance distraction process termination, active window interception, and Task Scheduler persistence (`enforcement.py`).

---

## Dual-View & Dual-Portal Architecture

```
                                  +------------------------------------------+
                                  |     Child's Active Foreground Window     |
                                  +--------------------+---------------------+
                                                       |
                                                       v
+-------------------------------+      +-------------------------------+      +-------------------------------+
|     Engineer 2: Vision        |      |   Engineer 3: Semantic NLP    |      |  Engineer 4: OS Enforcement   |
|     (vision_pipeline.py)      |      |   (semantic_pipeline.py)      |      |  (enforcement.py)             |
+-------------------------------+      +-------------------------------+      +-------------------------------+
| - MediaPipe 478 Mesh (3D)     |      | - Win32 Window Title Scraping |      | - Hosts Redirection (0.0.0.0) |
| - 6-DOF solvePnP Head Pose    |      | - YouTube Regex Decomposition |      | - Zero-Tolerance Terminations |
| - EAR Micro-blink Filter      |      | - Ollama SLM Classification   |      | - Active Window Minimizer     |
| - 8-State Posture Matrix      |      |   (Strictly Educational vs    |      | - DNS Cache Auto-Flush        |
| - Primary User Spatial Lock   |      |    Entertainment Distraction) |      | - Safe Graceful Restoration   |
+---------------+---------------+      +---------------+---------------+      +---------------+---------------+
                |                                      |                                      ^
                +------------------+   +---------------+                                      |
                                   |   |                                                      |
                                   v   v                                                      |
                    +------------------------------------+                                    |
                    |    The Brain: Decision Engine      |                                    |
                    |    (logic_controller.py)           |                                    |
                    +------------------------------------+                                    |
                    | - AND Gate: ACTIVE + EDUCATIONAL   |                                    |
                    |   -> +1s Time Accrual (Reward)     |                                    |
                    | - Vision Override: IDLE + EDU      |                                    |
                    |   -> -1s Time Drain (Sleepy/Away)  |                                    |
                    | - Distraction: * + DISTRACTION     |                                    |
                    |   -> -1s Time Drain (Intervention) |                                    |
                    +------------------+-----------------+                                    |
                                       |                                                      |
                                       v                                                      |
                    +------------------------------------+                                    |
                    |  Shared SQLite Database Engine     |                                    |
                    |  (study_monitor.db / db_manager.py)|                                    |
                    +------------------------------------+                                    |
                    | - user_state (Earned Balance)      |                                    |
                    | - parent_auth (PBKDF2 Salt & PIN)  |                                    |
                    | - app_policies (Quotas & Curfews)  |                                    |
                    | - parent_alerts (Security Incidents|                                    |
                    | - tracked_processes (Time Usage)   |                                    |
                    +---------+----------------+---------+                                    |
                              |                |                                              |
             +----------------+                +----------------+                             |
             |                                                  |                             |
             v                                                  v                             v
+-------------------------------+              +--------------------------------+   +-------------------+
|   Child Desktop App (GUI)     |              |   Dual-Portal Web Dashboard    |   | Headless Daemon   |
|   (desktop_app.py)            |              |   (web_dashboard.py)           |   | (main.py)         |
+-------------------------------+              +--------------------------------+   +-------------------+
| - Floating HUD & Zen Pill     |              | - Student Mode: Motivational   |   | - 1.0s cycle loop |
| - Gamified Focus Battery      |              |   Progress Ring & Status Pill  |   | - Active Win32    |
| - Anti-Tamper PIN Exit Modal  |              | - Parent Admin Mode (PIN 1323):|   |   process monitor |
| - Minimal CPU usage (<0.01%)  |              |   Telemetry, Policies, 24h Bar |   | - Auto-Enforce    |
+-------------------------------+              +--------------------------------+   +-------------------+
```

---

## Master Expansion Features

### Feature 1: Dual-Portal System & RBAC
- **Cryptographic Parent Credentials**:
  - Implemented in `db_manager.py` using table `parent_auth`.
  - Cryptographic standard: **PBKDF2-HMAC-SHA256** with 100,000 iterations and a 16-byte cryptographically secure salt (`secrets.token_bytes(16)`).
  - Default Master PIN: **`1323`** (seeded automatically on database setup).
- **Session Role Isolation**:
  - In-memory role management: `CURRENT_ROLE: "STUDENT" | "PARENT"`.
  - **Student Mode (Default Unprivileged)**: Read-only access to earned balance, streak counters, and leisure budget. All policy controls, process terminations, and configurations remain locked.
  - **Parent Admin Mode (Elevated)**: Accessed via the Master PIN modal. Grants full access to real-time telemetry, 24-hour timelines, policy editor, alert feed, and diagnostics.
  - **5-Minute Inactivity Auto-Lock**: Automatically locks back to Student Mode after 300 seconds of inactivity.

---

### Feature 2: Comprehensive Policy Engine, Quotas & Curfews
- **Granular Policy Schema (`policy_engine.py` & `db_manager.py`)**:
  - `app_policies`: Supports `HARD_BLOCK`, `DAILY_QUOTA`, and `SCHEDULED_CURFEW` policies.
  - `parent_alerts`: Incident audit ledger recording `UNAUTHORIZED_ATTEMPT`, `QUOTA_EXHAUSTED`, `MICROSLEEP_CLUSTER`, and `TAMPER_ATTEMPT` events.
  - `daily_focus_metrics`: Aggregates pure focus, drowsy, away, and distraction durations across days.
- **Evaluation Engine**:
  - **Hard Block**: Instantly terminates blocked processes and redirects web domains.
  - **Curfew Windows**: Blocks targets when local system time falls inside curfew boundaries (supports overnight windows, e.g., `21:00` to `06:00`).
  - **Daily Quotas & Earn-and-Burn**: Restricts applications when daily allowed seconds are exhausted; general entertainment allowance burns accrued study balance at a 1:1 ratio.
  - **Automated Midnight Reset**: Resets daily usage counters at 00:00:00 local time.

---

### Feature 3: Advanced 3D Kinematics & 8-State Posture Matrix
- **Sensor Fusion (`vision_pipeline.py`)**:
  - Fuses MediaPipe 478 3D landmark mesh, solvePnP 6-DOF head pose (Pitch, Yaw, Roll), Eye Aspect Ratio (EAR), and Win32 `GetLastInputInfo` user idle time.
  - **The 8 Discrete States**:
    1. `DIRECT_FOCUS`: Pitch \(-10^\circ\) to \(+10^\circ\), Yaw \(-15^\circ\) to \(+15^\circ\), EAR \(\ge 0.20\) \(\to\) **+1s reward balance**.
    2. `PASSIVE_READING`: Pitch \(-12^\circ\) to \(+12^\circ\), Yaw \(-15^\circ\) to \(+15^\circ\), EAR \(\ge 0.20\), PC idle 10–30s \(\to\) **+1s reward balance** (no penalty for deep reading).
    3. `DESK_NOTE_TAKING`: Downward pitch \(-15^\circ\) to \(-32^\circ\), Yaw \(-20^\circ\) to \(+20^\circ\), open eyelids \(\to\) **+1s reward balance**.
    4. `MOBILE_DISTRACTION`: Steep downward gaze into lap/phone (\(-15^\circ\) to \(-35^\circ\)), 0 PC input for \(>3.0\)s continuously \(\to\) **-1s drain** + parent alert.
    5. `LOOKING_AWAY`: Yaw \(>28^\circ\) or \(<-28^\circ\) sustained \(>2.5\)s \(\to\) **-1s drain / pause**.
    6. `DROWSY_MICROSLEEP`: EAR \(<0.18\) sustained \(\ge 2.0\)s \(\to\) **Vision override -1s**.
    7. `ABANDONED_DESK`: 0 faces detected in camera frustum \(\to\) **Auto-freezes session**.
    8. `DUAL_MONITOR_FOCUS`: Yaw \(20^\circ\) to \(38^\circ\) with active typing \(\to\) **+1s reward balance**.
- **Temporal Hysteresis & Anti-Flicker**:
  - Natural micro-blinks (\(<350\)ms) ignored to prevent erroneous drowsiness triggers.
  - 3-step baseline calibration wizard (`calibrate_baseline()`).

---

### Feature 4: Granular YouTube & Digital Deviation Filtering
- **Regex Window Title Decomposition (`semantic_pipeline.py`)**:
  - Pattern: `r"^(?P<title>.+?)\s*-\s*YouTube\s*(?:-\s*(?P<browser>Google Chrome|Brave|Microsoft\s*Edge|Mozilla Firefox))?$"`
- **Multi-Tier Decision Pipeline**:
  - **Tier 1 (Local Regex & Heuristics)**:
    - *Whitelist Keywords*: `lecture`, `tutorial`, `course`, `khan academy`, `mit opencourseware`, `crash course`, `derivation`, `proof`, `calculus`, `linear algebra`.
    - *Blacklist Keywords*: `vlog`, `prank`, `gaming`, `stream`, `mrbeast`, `shorts`, `funny`, `memes`, `highlights`, `reaction`.
  - **Tier 2 (Ollama SLM Verification)**: Prompts local lightweight LLM for ambiguous titles.
  - **Tier 3 (Policy Escalation)**:
    - Level 1: Desktop toast notification.
    - Level 2: Intercepts and minimizes browser window via `pygetwindow.minimize()`.
    - Level 3: Terminates browser or activates locked focus overlay if sustained \(>10\)s.
  - **Deterministic Embed URL Generation**: Generates privacy-enhanced `youtube-nocookie.com/embed/{id}?autoplay=1` frames for verified academic queries.

---

### Feature 5: Dashboard UI Transformation
- **Dual UI Engine (`web_dashboard.py`)**:
  - **Student View (Minimalist & Motivational)**:
    - Large circular SVG progress ring displaying accrued study time today.
    - Dynamic status pill: *Deep Flow* (emerald pulse), *Active Study* (indigo), *Drifting* (amber), *Distracted / Paused* (rose).
    - Focus streak counter (consecutive distraction-free minutes).
    - Entertainment allowance balance card.
    - Clean live camera stream preview.
  - **Parent Admin View (Operations Command Center)**:
    - Real-time Circular Focus Score Gauge (0–100%).
    - 24-Hour horizontal study timeline bar with color-coded 15-minute segments.
    - Application category distribution (Educational vs Gaming vs Social).
    - Granular Policy Engine manager (Hard Blocks, Daily Quotas, Curfews).
    - Live Vision Camera Feed with 3D Head Pose vectors, EAR gauge, and 8-state posture badge.
    - Incident Alert feed with one-click acknowledge.
    - Collapsible system diagnostics drawer (CPU load, memory, database latency).

---

### Feature 6: Desktop Client Packaging & Anti-Tamper OS Protection
- **Modal PIN Exit Interception (`desktop_app.py`)**:
  - Intercepts OS `WM_DELETE_WINDOW` close events.
  - Displays a modal PIN dialog requiring the Master PIN (`1323`) to exit.
  - Unauthorized exit attempts trigger a `TAMPER_ATTEMPT` critical security alert to `parent_alerts` and deny termination.
  - Verified exit restores network routing via `enforcement.unblock_distractions()`.

---

### Feature 7: MediaPipe Compatibility & Calibration Wizard
- **Resilient MediaPipe Fallback**:
  - Compatibility shim prevents `AttributeError: module 'mediapipe' has no attribute 'solutions'` on Python 3.13.
  - Automatically falls back to high-tech synthetic HUD canvas if physical webcam is detached or inaccessible.
- **30-Second Calibration Wizard**:
  - Interactively establishes baseline neutral gaze, desk note-taking angles, and dual-monitor offsets via `/api/calibrate`.

---

## Quick Start & Launch Guide

### Prerequisites
- Windows 10 / 11 (64-bit).
- Python 3.10+ (Installed at `C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe` or standard PATH).
- Dependencies: `pip install -r requirements.txt` (or `opencv-python`, `mediapipe`, `requests`, `pygetwindow`, `numpy`).

### One-Click Startup (All Services)
Double-click [`start_all.bat`](file:///c:/Users/nihal/.gemini/antigravity/scratch/GenAI_Project/start_all.bat) or run in PowerShell:
```powershell
.\start_all.bat
```
This automatically boots:
1. The **Headless Background Tracker** (`main.py`).
2. The **Dual-Portal Web Dashboard** (`web_dashboard.py` on `http://localhost:8000`).
3. The **Student Desktop Focus HUD** (`desktop_app.py`).

### Individual Component Launch

1. **Headless Background Tracker**:
   ```powershell
   & "C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe" main.py --verbose
   ```
2. **Dual-Portal Web Dashboard**:
   ```powershell
   & "C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe" web_dashboard.py
   ```
   Open [http://localhost:8000](http://localhost:8000) in any browser. Click **Unlock Parent Mode** and enter PIN **`1323`** to access Parent Admin mode.
3. **Student Desktop Focus HUD**:
   ```powershell
   & "C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe" desktop_app.py
   ```

---

## Windows Service Persistence & PyInstaller

### 1. Compile Headless Executable (`Demon.exe`)
Run [`build_exe.bat`](file:///c:/Users/nihal/.gemini/antigravity/scratch/GenAI_Project/build_exe.bat) or execute PyInstaller directly:
```powershell
pyinstaller Demon.spec
```
- `console=False` ensures zero Command Prompt windows appear.
- Output: `dist\Demon\Demon.exe`.

### 2. Install Persistent Windows Background Service
Run [`install_background_service.bat`](file:///c:/Users/nihal/.gemini/antigravity/scratch/GenAI_Project/install_background_service.bat) as Administrator:
```powershell
.\install_background_service.bat
```
Registers `Demon.exe` into Windows Task Scheduler:
- **Trigger**: At system startup (`/sc ONSTART`).
- **Privilege**: Highest Administrator (`/rl HIGHEST`) for zero-tolerance process terminations.
- **Logon**: Whether user is logged on or not (`/np`).

---

## Web Dashboard REST API Reference

| Endpoint | Method | Role | Description |
|---|:---:|:---:|---|
| `/api/status` | `GET` | All | Returns balance, active process, role, auto-lock timer, and camera telemetry |
| `/api/auth/status` | `GET` | All | Returns current active role (`STUDENT` or `PARENT`) and seconds until auto-lock |
| `/api/auth/verify_pin` | `POST` | All | Verifies Master PIN (`{"pin": "1323"}`). Elevates session to `PARENT` mode |
| `/api/auth/logout` | `POST` | Parent | Immediately resets role to `STUDENT` mode |
| `/api/policies` | `GET` | Parent | Retrieves list of all configured application and domain policies |
| `/api/policies` | `POST` | Parent | Creates or updates target policy (`target_name`, `policy_type`, `daily_quota_seconds`, `curfew_start`, `curfew_end`) |
| `/api/policies/delete` | `POST` | Parent | Deletes target policy rule |
| `/api/alerts` | `GET` | Parent | Retrieves security and tamper alerts from `parent_alerts` ledger |
| `/api/alerts/acknowledge` | `POST` | Parent | Acknowledges / dismisses alert by ID (`{"id": 1}`) |
| `/api/metrics/daily` | `GET` | Parent | Returns 7-day focus analytics, pure study seconds, and distraction attempts |
| `/api/metrics/timeline-24h` | `GET` | Parent | Returns 96 15-minute segments with category tagging across the 24-hour day |
| `/api/metrics/app-distribution` | `GET` | Parent | Returns daily category breakdown percentages (Educational, Gaming, Social) |
| `/api/apps/recent` | `GET` | Parent | Returns circular deque of the last 8 focused foreground applications |
| `/api/diagnostics` | `GET` | Parent | Automated 10-second diagnostics sampler (CPU %, RAM %, SQLite latency ms, FPS) |
| `/api/lockdown/start` | `POST` | Parent | Starts a timed emergency lockdown session (`{"duration_seconds": 1800}`) |
| `/api/lockdown/edit` | `POST` | Parent | Adjusts active lockdown duration (`{"duration_seconds": 3600}`) |
| `/api/lockdown/stop` | `POST` | Parent | Terminates emergency lockdown and restores standard network policies |
| `/api/calibrate` | `POST` | Parent | Triggers 30-second baseline posture calibration wizard |
| `/api/adjust-time` | `POST` | Parent | Adjusts student screen time balance by delta seconds (`{"delta": 1800}`) |
| `/api/set-time` | `POST` | Parent | Resets student screen time balance to absolute seconds (`{"balance": 3600}`) |
| `/api/toggle-lock` | `POST` | Parent | Toggles instant lockdown mode (proactively terminates distraction apps) |
| `/api/toggle-web-filter` | `POST` | Parent | Toggles zero-tolerance hosts domain redirection |
| `/api/kill-process` | `POST` | Parent | Immediately terminates target running process (`{"process_name": "discord.exe"}`) |
| `/api/camera_frame` | `GET` | All | Returns latest single JPEG frame snapshot |
| `/api/video_feed` | `GET` | All | Multi-part MJPEG live camera stream with real-time HUD overlays |

---

## Verification & Test Suite

The platform includes a rigorous test suite verifying every component without regressions.

Run the master test runner across all modules:
```powershell
& "C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe" run_all_tests.py
```

### Full Verification Matrix (9/9 Suites Passed)

| Test Suite | Execution Command | Result |
|---|---|:---:|
| **Master Test Runner** | `python run_all_tests.py` | **`9/9 PASS`** |
| **Database & Persistence** | `python test_db_manager.py` | **`PASS (100%)`** |
| **Sensory Pipelines** | `python test_checkpoint_1.py` | **`PASS (100%)`** |
| **Multi-Modal Fusion** | `python test_checkpoint_2.py` | **`PASS (100%)`** |
| **Decision Engine AND Gate** | `python test_logic_controller.py` | **`PASS (100%)`** |
| **System Orchestration** | `python test_system_orchestration.py` | **`PASS (100%)`** |
| **Enforcement & 3D Learning** | `python test_enforcement_cases.py` | **`PASS (100%)`** |
| **Dual-View Architecture** | `python test_dual_view_architecture.py` | **`PASS (100%)`** |
| **Master Prompt Features** | `python test_master_prompt_features.py` | **`PASS (100%)`** |
| **9-Module Expansion Suite** | `python test_system_expansion_modules.py` | **`PASS (100%)`** |

---

## Project Structure

```
GenAI_Project/
├── db_manager.py                     # SQLite schema, PBKDF2 parent auth, policies, metrics
├── policy_engine.py                  # Quota evaluation, curfews, midnight resets, alert dispatcher
├── logic_controller.py               # AND Gate decision engine, research CSV logger
├── vision_pipeline.py                # MediaPipe Face Mesh, 6-DOF solvePnP, 8-state posture matrix
├── user_tracker.py                   # PrimaryUserTracker (spatial lock) & WindowsProcessTracker
├── semantic_pipeline.py              # YouTube regex decomposition, Ollama SLM, cache
├── enforcement.py                    # Hosts file blocking, surgical termination & zero browser killing
├── main.py                           # Headless background orchestrator daemon
├── web_dashboard.py                  # Dual-Portal web dashboard & live MJPEG camera stream
├── desktop_app.py                    # Student Desktop HUD GUI with anti-tamper PIN exit modal
├── Demon.spec                        # Headless PyInstaller build specification
├── start_all.bat                     # One-click multi-process runtime launcher
├── build_exe.bat                     # PyInstaller executable compilation script
├── install_background_service.bat    # Windows Task Scheduler registration script
├── Grant_Hosts_Permission.bat        # Windows hosts file permissions configuration
├── run_all_tests.py                  # Master automated test suite runner (9 suites)
├── test_db_manager.py                # Checkpoint 1: Database persistence unit tests
├── test_checkpoint_1.py              # Checkpoint 1: Vision EAR & Ollama classification
├── test_checkpoint_2.py              # Checkpoint 2: Multi-modal fusion & state cache
├── test_logic_controller.py          # Checkpoint 2: Decision engine logic tests
├── test_system_orchestration.py      # Checkpoint 3: Zero-balance & earn-and-burn tests
├── test_enforcement_cases.py         # Checkpoint 4: 3D kinematics, mobile distraction & YouTube
├── test_dual_view_architecture.py    # Dual-view sync, quotas & background tracker tests
├── test_master_prompt_features.py    # Master Prompt expansion feature integration tests
├── test_system_expansion_modules.py  # 9-Module expansion verification test suite
├── CHANGELOG.md                      # Detailed version release notes and milestone history
└── progress_log.md                   # Technical development log, architecture decisions & fixes
```

---

## License & Intellectual Property
Developed under the **Demon AI Study Monitor Project** for secure, privacy-first parental guidance and attentive computer-aided study environments.

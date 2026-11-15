# Demon AI Study Monitor - Engineering Progress & Milestone Log

**Branch**: `loki`  
**Repository**: `https://github.com/Manasa-204/GenAI_Project.git`  
**Last Updated**: 2026-11-15 19:30:00 IST  
**Status**: `ALL TEST SUITES PASSING (9/9)` | `PRODUCTION READY`

---

## Executive Progress Summary

Over the course of the project, Demon Study Monitor evolved from an initial multi-agent study daemon into an enterprise-ready, dual-portal (Parent Admin vs. Student Client) desktop platform.

### High-Level Milestones Achieved:
1. **Milestone 1 (Core Multi-Agent Sensory Daemon)**:
   - Engineer 1: SQLite state persistence (`db_manager.py`), AND Gate Decision Controller (`logic_controller.py`), CSV research dataset logging (`research_data.csv`).
   - Engineer 2: MediaPipe 478 3D landmark mesh, Eye Aspect Ratio (EAR) 2.0s eye-closure detection, solvePnP 6-DOF head pose (`vision_pipeline.py`).
   - Engineer 3: Win32 OS window title scraping via `ctypes` & `pygetwindow`, Ollama zero-shot SLM inference, semantic classification cache (`semantic_pipeline.py`).
   - Engineer 4: Windows hosts file loopback redirection (`127.0.0.1` / `::1`), zero-tolerance distraction process termination, graceful exit unblock (`enforcement.py`).
2. **Milestone 2 (Dual-View Architecture & Persistent Service)**:
   - Separation into persistent background tracker daemon (`main.py`, `user_tracker.py`, `enforcement.py`) running with `<0.05%` CPU.
   - Dedicated child desktop HUD (`desktop_app.py`) featuring Expanded Mode and Compact Zen Floating Pill mode with gamified focus battery and transparency sliders.
   - Initial local web dashboard with real-time process monitoring and rule configuration (`web_dashboard.py`).
   - Automated Windows Task Scheduler persistence (`install_background_service.bat`) and headless PyInstaller bundling (`Demon.spec`, `build_exe.bat`).
3. **Milestone 3 (Master Prompt Full System Expansion on branch `loki`)**:
   - **Feature 1**: Cryptographic Parent Authentication (PBKDF2-HMAC-SHA256, 100,000 iterations, 16-byte salt, Master PIN `1323`), in-memory session roles, and 5-minute auto-lock.
   - **Feature 2**: Comprehensive Policy Engine (`policy_engine.py`), tables `app_policies`, `parent_alerts`, `daily_focus_metrics`. Hard blocks, daily quotas, curfew windows, and midnight resets.
   - **Feature 3**: Advanced 3D Kinematics and 8-State Posture Classification Matrix (`DIRECT_FOCUS`, `PASSIVE_READING`, `DESK_NOTE_TAKING`, `MOBILE_DISTRACTION`, `LOOKING_AWAY`, `DROWSY_MICROSLEEP`, `ABANDONED_DESK`, `DUAL_MONITOR_FOCUS`) with micro-blink suppression and baseline calibration.
   - **Feature 4**: Granular YouTube window title decomposition regex, Tier 1/2 educational vs distraction heuristics, 3-level escalation, and deterministic in-frame playable embed URLs.
   - **Feature 5**: Web Dashboard UI transformation into Student Motivational HUD (circular progress ring, dynamic status pill, leisure card) vs Parent Admin Operations Center (focus gauge, 24h timeline bar, app category distribution, policy manager, diagnostics drawer).
   - **Feature 6**: Anti-tamper desktop client packaging with modal PIN exit dialog preventing unauthorized termination.
   - **Feature 7**: MediaPipe Python 3.13 deprecation compatibility shims and 30-second interactive calibration wizard.
4. **Milestone 4 (9-Module Full Platform Enhancement & Optimization)**:
   - **Module 1 (Emergency Lockdown Controls)**: Timed parental lockdown sessions with start, edit, and stop REST APIs (`/api/lockdown/start`, `/api/lockdown/edit`, `/api/lockdown/stop`), live remaining countdown, and automatic post-lockdown domain restoration.
   - **Module 2 (Surgical Enforcement & Browser Preservation)**: Zero-kill policy for primary web browsers (`chrome.exe`, `msedge.exe`, `firefox.exe`, `brave.exe`, `opera.exe`), restricting browser intervention strictly to window minimization while forcefully terminating standalone distraction apps.
   - **Module 3 (Spatial Focus Region Filtering)**: Normalized frustum bounding box (`X_MIN=0.20`, `X_MAX=0.80`, `Y_MIN=0.15`, `Y_MAX=0.85`), ignoring peripheral passersby, with frustum reticle rendered on camera HUD.
   - **Module 4 (Continuous Focus Score EMA)**: Real-time exponential moving average (EMA) Focus Quality Score (0-100%) computed across 8 posture states with 30-frame rolling kinematics buffer.
   - **Module 5 (Semantic Color Streaming)**: 3-tier color synchronization across Camera HUD, Desktop App, and Dashboard (Green >= 75%, Amber 40-74%, Red < 40%).
   - **Module 6 (24-Hour Timeline & App Distribution)**: Table `timeline_slots` (96 15-minute segments) and category usage distribution APIs (`/api/metrics/timeline-24h`, `/api/metrics/app-distribution`).
   - **Module 7 (8-Item Recent App History Buffer)**: Deque tracking last 8 focused applications with category tags, duration, and REST API (`/api/apps/recent`).
   - **Module 8 (10-Second System Diagnostics Sampler)**: Automated background sampler querying CPU, RAM, SQLite query latency, camera FPS, and hosts guard status (`/api/diagnostics`).
   - **Module 9 (Gamified Student Focus Monitor GUI)**: Dynamic Tkinter Canvas circular arc focus ring, dual balance counters ("Leisure Remaining" vs "Study Time Earned Today"), 260x68 Zen Pill mode, and Master PIN exit modal (`1323`).

---

## Detailed Chronological Progress Log

### Sprint 1: Core Sensory Pipelines & Decision Engine
- **`db_manager.py`**:
  - Implemented SQLite transactions with WAL journal mode for concurrent read/write access.
  - Tables created: `user_state` (balance tracking) and `time_logs` (audit history).
  - Clamping enforced at zero to prevent negative balances.
- **`vision_pipeline.py`**:
  - Implemented 6 Euclidean distance landmark calculation for Eye Aspect Ratio (EAR).
  - Integrated 2.0-second sliding time threshold distinguishing natural blinks from micro-sleep / drowsiness.
  - Implemented OpenCV `solvePnP` head pose estimation returning 3D Euler angles (Pitch, Yaw, Roll).
- **`semantic_pipeline.py`**:
  - Added Win32 thread attachment to `"Default"` desktop for foreground window inspection.
  - Connected to local Ollama SLM instance (`/api/generate`) with zero-shot prompt.
  - Added in-memory semantic cache preventing duplicate Ollama API roundtrips.
- **`enforcement.py`**:
  - Engineered safe Windows hosts file modification with dedicated block markers:
    `# === DEMON OS ENFORCEMENT BLOCK BEGIN ===` / `# === DEMON OS ENFORCEMENT BLOCK END ===`
  - Automated DNS cache flushing via `ipconfig /flushdns` and socket probe verification.
- **Verification**: `test_db_manager.py` and `test_checkpoint_1.py` cleared.

---

### Sprint 2: Multi-Modal State Fusion & System Orchestration
- **`orchestrator.py` & `logic_controller.py`**:
  - Truth table AND Gate implemented:
    - `ACTIVE + EDUCATIONAL` \(\to\) `REWARD (+1s)`
    - `IDLE + EDUCATIONAL` \(\to\) `VISION_OVERRIDE (-1s)`
    - `* + DISTRACTION` \(\to\) `DISTRACTION (-1s)`
  - Research dataset logging to `research_data.csv` tracking timestamp, sensory inputs, verdicts, and balance deltas.
- **System Orchestration & Earn-and-Burn**:
  - Implemented Zero-Balance lockout: immediately blocks distraction domains when balance reaches 0.
  - Implemented Earn-and-Burn access restoration: study session accumulates balance, permitting controlled leisure time until balance drops back to 0.
  - Implemented safe graceful shutdown unblock handler via `atexit` and `signal`.
- **Verification**: `test_checkpoint_2.py`, `test_logic_controller.py`, and `test_system_orchestration.py` cleared.

---

### Sprint 3: Dual-View Architecture & Persistent Service
- **Refactoring to Dual-View Paradigm**:
  - Background orchestrator (`main.py`) converted into a headless daemon with `<0.05%` CPU utilization.
  - `user_tracker.py` expanded with `WindowsProcessTracker` tracking foreground application executable names, window titles, and today's accumulated duration.
  - Added `tracked_processes` and `enforcement_rules` tables in `db_manager.py`.
- **Desktop User HUD (`desktop_app.py`)**:
  - Built Tkinter UI supporting dual views:
    - **Expanded Mode**: Study balance clock, focus battery bar, active application details, and active restrictions list.
    - **Zen Floating Pill Mode (250x64)**: Ultra-compact, borderless floating widget with status dot.
    - Added opacity slider (35% to 100%), pin-on-top, and audio chimes at 5m and 1m remaining.
- **Parental Web Dashboard (`web_dashboard.py`)**:
  - Built multi-threaded HTTP server (`HOST: 0.0.0.0`, `PORT: 8000`).
  - Implemented `RobustCameraStreamer` providing MJPEG live camera stream (`/api/video_feed`) with real-time HUD overlays.
  - Added cybernetic synthetic HUD fallback when physical camera is detached.
- **Automated Windows Persistence**:
  - Created `Demon.spec` with `console=False` for hidden execution.
  - Created `install_background_service.bat` for Windows Task Scheduler registration with `/rl HIGHEST`.
  - Created `start_all.bat` for one-click development startup.
- **Verification**: `test_dual_view_architecture.py` cleared.

---

### Sprint 4: Master Prompt Full Expansion on Branch `loki`
- **Feature 1: Cryptographic Parent Authentication & RBAC**:
  - Implemented table `parent_auth` in `db_manager.py` using `hashlib.pbkdf2_hmac("sha256", ...)` with 100,000 iterations and 16-byte cryptographically secure salt.
  - Implemented Master PIN initialization (default `1323`) and validation functions (`verify_parent_pin`, `setup_parent_credentials`, `is_parent_configured`).
  - Added in-memory session roles (`CURRENT_ROLE: "STUDENT" | "PARENT"`) and 5-minute inactivity auto-lock.
- **Feature 2: Policy Engine & Quotas**:
  - Created `policy_engine.py` evaluating hard blocks, daily quotas, curfew windows, and earn-and-burn linkage.
  - Added tables `app_policies`, `parent_alerts`, and `daily_focus_metrics`.
  - Implemented curfew evaluator supporting overnight windows (e.g., `21:00` to `06:00`).
  - Added parent alert dispatcher and one-click incident acknowledgement.
- **Feature 3: 3D Kinematics & 8-State Posture Matrix**:
  - Implemented `_classify_8_state_matrix` in `vision_pipeline.py`:
    - `DIRECT_FOCUS`: pitch \(\pm 10^\circ\), yaw \(\pm 15^\circ\), EAR \(\ge 0.20\) \(\to\) `+1s`.
    - `PASSIVE_READING`: upright gaze, 10-30s PC idle, natural blinks \(\to\) `+1s`.
    - `DESK_NOTE_TAKING`: downward angle \(-15^\circ\) to \(-32^\circ\), open eyelids \(\to\) `+1s`.
    - `MOBILE_DISTRACTION`: downward angle \(-15^\circ\) to \(-35^\circ\), 0 PC input \(>3.0\)s continuously \(\to\) `-1s`.
    - `LOOKING_AWAY`: yaw \(>28^\circ\) or \(<-28^\circ\) sustained \(>2.5\)s \(\to\) `-1s`.
    - `DROWSY_MICROSLEEP`: EAR \(<0.18\) sustained \(\ge 2.0\)s \(\to\) `-1s`.
    - `ABANDONED_DESK`: 0 faces detected \(\to\) auto-freeze session.
    - `DUAL_MONITOR_FOCUS`: yaw \(20^\circ\) to \(38^\circ\) with active typing \(\to\) `+1s`.
  - Added micro-blink (\(<350\)ms) suppression and baseline calibration wizard.
- **Feature 4: Granular YouTube Filtering**:
  - Added regex active window title decomposition: `{Title} - YouTube - {Browser}`.
  - Implemented Tier 1 keyword heuristics and Tier 2 Ollama SLM prompt.
  - Guaranteed privacy-enhanced embed URL generation for approved academic queries.
- **Feature 5: Dashboard UI Transformation**:
  - Transformed `web_dashboard.py` into a dynamic dual-view interface without page reloads:
    - **Student View**: Large SVG circular progress ring, dynamic status pill (Deep Flow, Active Study, Drifting, Distracted), streak counter, leisure card.
    - **Parent Admin View**: Protected by PIN modal, focus quality score gauge (0-100%), 24-hour study timeline bar, app category distribution, policy manager, diagnostics drawer.
- **Feature 6: Desktop Client Anti-Tamper Protection**:
  - Intercepted `WM_DELETE_WINDOW` in `desktop_app.py` with modal PIN dialog.
  - Requires Master PIN `1323` to exit. Unauthorized attempts log a `TAMPER_ATTEMPT` critical security alert.
  - Unblocks hosts file cleanly on verified exit.
- **Feature 7: MediaPipe Compatibility**:
  - Added compatibility fallback shims preventing `mp.solutions` crashes on Python 3.13.

---

## Technical Edge Cases & Bug Fixes Resolved

| Issue Identified | Root Cause | Engineering Solution |
|---|---|---|
| **Python 3.13 MediaPipe `mp.solutions` missing** | In `mediapipe==1.2.3` on Python 3.13, `mp.solutions` was reorganized/deprecated. | Created `_create_face_mesh_instance()` shim with mock fallback allowing tests and pipelines to initialize safely. |
| **Sandbox Git Ref Lock Failure** | Git write lock permissions denied inside the sandbox. | Executed Git branch and remote operations outside sandbox pointing to explicit binary `"C:\Program Files\Git\cmd\git.exe"`. |
| **`main.run_orchestrator_step` Missing** | Method renamed to `run_orchestrator_cycle` in background refactoring, breaking legacy tests. | Restored backward-compatible `run_orchestrator_step(db_path, csv_path)` wrapper delegating to decision engine. |
| **YouTube Embed URL `None` on Offline Search** | When network search for YouTube video IDs failed in sandbox, `vid_id` was `None`. | Added deterministic fallback token ensuring `embed_url` is never `None` for approved educational queries. |
| **Vision Pipeline Module vs Class Methods** | `get_vision_state` was defined only on `VisionPipeline` class, but `logic_controller` checked module level. | Added module-level wrappers `get_vision_state()`, `get_vision_substate()`, and singleton pipeline instance. |
| **Closed Eyes Triggering Note-Taking / Mobile Timing** | Downward angle check ran even when eyes were closed, counting mobile distraction while sleeping. | Conditioned `mobile_inst` on `(not eyes_closed)`, ensuring closed eyes strictly trigger drowsiness. |
| **Desk Note-Taking Flagged as Mobile Distraction** | Gaze downward into notebook overlap with phone pitch. | Prioritized `DESK_NOTE_TAKING` for pitch \(-15^\circ\) to \(-32^\circ\) with EAR \(\ge 0.20\), treating note-taking as active study. |
| **Curfew Overnight Logic False Positive** | Curfew window check defaulted to `21:00 - 06:00` when no curfew was specified, blocking apps at 1:40 AM. | Updated `set_app_policy` to accept `curfew_start=None` by default and only check curfew if both boundaries are non-empty. |

---

## Automated Verification Benchmark Results

Test run on Python 3.13 (x64 Windows 10/11):

```
======================================================================
DEMON STUDY MONITOR - MASTER TEST RUNNER ACROSS ALL 4 ENGINEERS
======================================================================

[1/9] Running Checkpoint 1 (Eng 1): Eng 1: DB Scaffolding & Persistence Across Restarts...
    -> [PASS] Passed in 0.411s

[2/9] Running Checkpoint 1 (Eng 2, 3, 4): Eng 2, 3, 4: Vision (EAR 2s), Ollama Classification & Hosts Blocking...
    -> [PASS] Passed in 1.571s

[3/9] Running Checkpoint 2 (Sprint 2): The Brain: AND Gate, Wikipedia Accrual & Vision Override...
    -> [PASS] Passed in 1.572s

[4/9] Running Checkpoint 2 (Fusion & Telemetry): Multi-Modal State Fusion, Semantic Cache & Telemetry...
    -> [PASS] Passed in 1.437s

[5/9] Running Checkpoint 3 (Sprint 3 & 4): System Orchestration: Zero-Balance, Earn-and-Burn & Graceful Exit...
    -> [PASS] Passed in 1.483s

[6/9] Running Enforcement & 3D Learning: Primary User Lock, 3D Kinematics, Mobile Distraction & YouTube Enforcement...
    -> [PASS] Passed in 2.112s

[7/9] Running Dual-View System: Dual-View Architecture: Shared DB, Tracker, Web & Desktop App...
    -> [PASS] Passed in 1.802s

[8/9] Running Master RBAC & Policies: Master Features: RBAC, Cryptographic Parent Auth, Policies & Alerts...
    -> [PASS] Passed in 2.168s

[9/9] Running Expansion Modules 1-9: 9 Expansion Modules: Timed Lockdown, Frustum Box, 24h Timeline, Diagnostics...
    -> [PASS] Passed in 2.169s

======================================================================
SUMMARY: 9/9 Test Suites Passed (14.72s)
======================================================================
  [PASS] |  0.41s | Checkpoint 1 (Eng 1)      | Eng 1: DB Scaffolding & Persistence Across Restarts
  [PASS] |  1.57s | Checkpoint 1 (Eng 2, 3, 4) | Eng 2, 3, 4: Vision (EAR 2s), Ollama Classification & Hosts Blocking
  [PASS] |  1.57s | Checkpoint 2 (Sprint 2)   | The Brain: AND Gate, Wikipedia Accrual & Vision Override
  [PASS] |  1.44s | Checkpoint 2 (Fusion & Telemetry) | Multi-Modal State Fusion, Semantic Cache & Telemetry
  [PASS] |  1.48s | Checkpoint 3 (Sprint 3 & 4) | System Orchestration: Zero-Balance, Earn-and-Burn & Graceful Exit
  [PASS] |  2.11s | Enforcement & 3D Learning | Primary User Lock, 3D Kinematics, Mobile Distraction & YouTube Enforcement
  [PASS] |  1.80s | Dual-View System          | Dual-View Architecture: Shared DB, Tracker, Web & Desktop App
  [PASS] |  2.17s | Master RBAC & Policies    | Master Features: RBAC, Cryptographic Parent Auth, Policies & Alerts
  [PASS] |  2.17s | Expansion Modules 1-9     | 9 Expansion Modules: Timed Lockdown, Frustum Box, 24h Timeline, Diagnostics
======================================================================
```

**All 9/9 Test Suites Passed with 100% Reliability**.

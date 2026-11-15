# Changelog

All notable changes to the **Demon Study Monitor** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2026-11-15 - Master Prompt Full Expansion (Branch: `loki`)

### Added
- **Feature 1: Dual-Portal System & RBAC**:
  - Implemented cryptographic parent authentication in `db_manager.py` (PBKDF2-HMAC-SHA256, 100,000 iterations, 16-byte salt, table `parent_auth`).
  - Default Master PIN seeded to `1323`.
  - Added session role separation (`STUDENT` vs `PARENT`) with 5-minute inactivity auto-lock.
  - Endpoints added: `/api/auth/verify_pin`, `/api/auth/status`, `/api/auth/logout`.
- **Feature 2: Comprehensive Policy Engine & Quotas**:
  - Created `policy_engine.py` evaluating hard blocks, daily quotas, curfew windows, midnight resets, and alert dispatching.
  - Added SQLite tables `app_policies`, `parent_alerts`, and `daily_focus_metrics`.
  - Added endpoints `/api/policies`, `/api/policies/delete`, `/api/alerts`, `/api/alerts/acknowledge`, and `/api/metrics/daily`.
- **Feature 3: Advanced 3D Kinematics & 8-State Posture Matrix**:
  - Fused MediaPipe 478 3D mesh, solvePnP 6-DOF head pose, EAR eye aspect ratio, and Win32 user input idle time.
  - Implemented 8 discrete posture states: `DIRECT_FOCUS`, `PASSIVE_READING`, `DESK_NOTE_TAKING`, `MOBILE_DISTRACTION`, `LOOKING_AWAY`, `DROWSY_MICROSLEEP`, `ABANDONED_DESK`, `DUAL_MONITOR_FOCUS`.
  - Added natural micro-blink (<350ms) suppression to eliminate flicker.
  - Added 30-second interactive calibration wizard (`/api/calibrate`).
- **Feature 4: Granular YouTube Title Decomposition & SLM Filtering**:
  - Added regex active window title decomposition: `{Title} - YouTube - {Browser}`.
  - Implemented Tier 1 keyword whitelist/blacklist heuristics and Tier 2 Ollama SLM classification.
  - Guaranteed privacy-enhanced embed URL generation for approved academic searches.
- **Feature 5: Dashboard UI Transformation**:
  - Transformed `web_dashboard.py` into a dynamic dual-view interface without page reloads:
    - **Student View**: Large circular SVG progress ring, dynamic status pill (Deep Flow, Active Study, Drifting, Distracted), focus streak counter, leisure allowance card.
    - **Parent Admin View**: PIN authentication modal, circular focus score gauge (0-100%), 24-hour horizontal study timeline bar with color-coded 15-minute segments, app category distribution, policy manager, diagnostics drawer.
- **Feature 6: Desktop Client Packaging & Anti-Tamper OS Protection**:
  - Intercepted `WM_DELETE_WINDOW` in `desktop_app.py` with modal PIN dialog.
  - Requires Master PIN `1323` to exit. Unauthorized exit attempts trigger `TAMPER_ATTEMPT` critical security alerts.
  - Unblocks hosts file cleanly on verified exit.
- **Feature 7: MediaPipe Compatibility**:
  - Added compatibility fallback shims preventing `mp.solutions` crashes on Python 3.13.
  - Fallback high-tech synthetic HUD canvas if physical webcam is detached.
- **Testing**:
  - Created `test_master_prompt_features.py` testing all 7 master expansion features.

### Changed
- Refactored `web_dashboard.py` to support real-time MJPEG live video feed (`/api/video_feed`) with posture HUD overlays.
- Updated `main.py` with backward-compatible `run_orchestrator_step(db_path, csv_path)` for legacy integration test suites.
- Updated `Demon.spec` hiddenimports to bundle `logic_controller` and `policy_engine`.
- Enhanced `desktop_app.py` with opacity slider, pin on top, and audio chimes.

---

## [1.5.0] - 2026-11-14 - Dual-View Architecture & Windows Service Automation

### Added
- Created `main.py` headless background tracker daemon with `<0.05%` CPU utilization.
- Created `desktop_app.py` lightweight Tkinter GUI supporting Expanded HUD and Zen Floating Pill mode.
- Created `install_background_service.bat` for Windows Task Scheduler registration with `/rl HIGHEST`.
- Created `build_exe.bat` for compiling headless executable via PyInstaller.
- Created `start_all.bat` for one-click development startup.
- Created `test_dual_view_architecture.py` verifying database synchronization between background daemon, GUI, and web portal.

---

## [1.0.0] - 2026-11-02 - Multi-Agent Study Daemon Initial Release

### Added
- Engineer 1: SQLite state persistence (`db_manager.py`), AND Gate Decision Controller (`logic_controller.py`), CSV research dataset logging (`research_data.csv`).
- Engineer 2: MediaPipe Face Mesh, Eye Aspect Ratio (EAR) 2.0s eye-closure detection, solvePnP 6-DOF head pose (`vision_pipeline.py`).
- Engineer 3: Win32 OS window scraping, Ollama zero-shot SLM inference, semantic classification cache (`semantic_pipeline.py`).
- Engineer 4: Windows hosts file loopback redirection (`127.0.0.1` / `::1`), zero-tolerance distraction process termination, graceful exit unblock (`enforcement.py`).
- Initial test suites: `test_checkpoint_1.py`, `test_checkpoint_2.py`, `test_logic_controller.py`, `test_system_orchestration.py`, `test_enforcement_cases.py`, and master runner `run_all_tests.py`.

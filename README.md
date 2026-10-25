# Demon - AI-Driven Contextual Study Monitor & Focus Enforcement

An autonomous multi-agent productivity and attention enforcement daemon built through the collaboration of four specialized engineering roles:

- **Engineer 1 (Data & Logic - Lead)**: SQLite balance database (`db_manager.py`), AND Gate Decision Controller (`logic_controller.py`), Research Data Logger (`research_data.csv`), and System Orchestration (`main.py`).
- **Engineer 2 (Computer Vision)**: Webcam feed capture, MediaPipe Face Mesh (478 3D landmarks), Eye Aspect Ratio (EAR) sleep detection, and Head Pose estimation (`vision_pipeline.py`).
- **Engineer 3 (NLP & App Integration)**: OS window scraping (`pygetwindow` / Win32 `ctypes`) and local Ollama SLM prompt inference (`semantic_pipeline.py`).
- **Engineer 4 (Systems & OS)**: OS Hosts file manipulation, distraction domain loopback (`127.0.0.1` / `::1`), and DNS cache flushing (`enforcement.py`).

---

## System Architecture

```
                                      +------------------------------------+
                                      |   Active OS Foreground Window      |
                                      +-----------------+------------------+
                                                        |
                                                        v
+-----------------------------+       +------------------------------------+       +------------------------------------+
|  Engineer 2: Vision         |       |  Engineer 3: Semantic NLP          |       |  Engineer 4: OS Enforcement        |
|  (vision_pipeline.py)       |       |  (semantic_pipeline.py)            |       |  (enforcement.py)                  |
+-----------------------------+       +------------------------------------+       +------------------------------------+
| - MediaPipe Face Mesh (478) |       | - pygetwindow Title Scraping       |       | - OS Hosts File Modification       |
| - EAR Calculation (Sleep)   |       | - Local Ollama SLM Inference       |       | - DNS Resolver Cache Flushing      |
| - Head Pose / PnP (Away)    |       |   (temperature=0.0 zero-shot)      |       | - 127.0.0.1 / ::1 Loopback Routing |
|                             |       | - Semantic Classification Cache    |       | - State tracking & Auto-unblock    |
| Output: "ACTIVE" | "IDLE"   |       | Output: "EDUCATIONAL"|"DISTRACTION"|       | Output: block() / unblock()        |
+--------------+--------------+       +-----------------+------------------+       +-----------------+------------------+
               |                                        |                                    ^
               +-------------------+   +----------------+                                    |
                                   |   |                                                     |
                                   v   v                                                     |
                    +------------------------------------+                                   |
                    |   Engineer 1: Logic Controller     |                                   |
                    |   (logic_controller.py)            |                                   |
                    +------------------------------------+                                   |
                    | - AND Gate: ACTIVE + EDUCATIONAL   |                                   |
                    |   -> +1s Time Accrual              |                                   |
                    | - Vision Override: IDLE + EDU      |                                   |
                    |   -> -1s Time Drain                |                                   |
                    | - Distraction: * + DISTRACTION     |                                   |
                    |   -> -1s Time Drain                |                                   |
                    +-----------------+------------------+                                   |
                                      |                                                      |
                                      v                                                      |
                    +------------------------------------+                                   |
                    |   Engineer 1: Database Manager     |                                   |
                    |   (db_manager.py)                  |                                   |
                    +------------------------------------+                                   |
                    | - SQLite `user_state` (Balance)    |                                   |
                    | - SQLite `time_logs` (Audit Log)   |                                   |
                    | - `research_data.csv` (Experiment) |                                   |
                    +-----------------+------------------+                                   |
                                      |                                                      |
                                      v                                                      |
                    +------------------------------------+                                   |
                    |   System Orchestrator              |-----------------------------------+
                    |   (main.py / orchestrator.py)      |  (If Balance <= 0 & Distraction: BLOCK)
                    +------------------------------------+  (If Balance > 0: UNBLOCK)
```

---

## The Decision Engine (AND Gate)

| Physical State (Eng 2) | Semantic State (Eng 3) | Verdict | Balance Delta | Reason |
|---|---|---|:---:|---|
| **ACTIVE** (Eyes open, looking at screen) | **EDUCATIONAL** (Study, math, code) | `REWARD` | **+1s** | Both Active: Accruing Time |
| **IDLE** (Eyes closed / asleep $\ge 2\text{s}$) | **EDUCATIONAL** (Lecture / docs) | `VISION_OVERRIDE` | **-1s** | Vision override: User asleep/away |
| **ACTIVE** (Eyes open) | **DISTRACTION** (Memes, social, gaming) | `DISTRACTION` | **-1s** | Distraction active |
| **IDLE** (User away / asleep) | **DISTRACTION** (Abandoned media) | `IDLE` | **-1s** | User idle & inactive |

---

## Web Dashboard (Local Site)

The system includes a reactive web dashboard running locally at:

**`http://localhost:8000`**

### Dashboard Features:
1. **Live Telemetry Hero**: Digital study balance clock, fused state badge, and sensor indicators.
2. **Interactive Scenario Simulator**: One-click simulation for Study Mode, Drowsy/Sleep, Distractions, Zero-Balance Test, and Earn-and-Burn Test.
3. **Live Test Suite Execution**: Executes all 5 test suites on demand with real-time pass/fail badges.
4. **Historical Audit Tables**: Live view of SQLite `time_logs` transactions and `research_data.csv` dataset.

Launch the web site at any time:
```bash
python web_dashboard.py
```

---

## Verification & Master Test Suite

Run all 5 test suites across all 4 engineers:

```bash
python run_all_tests.py
```

### Verification Matrix:
- [x] **Checkpoint 1 (Eng 1)**: SQLite schema initialization and state persistence across script restarts (`test_db_manager.py`).
- [x] **Checkpoint 1 (Eng 2, 3, 4)**: Camera EAR closed eyes detection within 2s, Ollama zero-shot classification, and OS hosts domain blocking (`test_checkpoint_1.py`).
- [x] **Checkpoint 2 (Sprint 2)**: The Brain AND Gate, Wikipedia accrual (+1s), and Vision Override (-1s) (`test_logic_controller.py`).
- [x] **Checkpoint 2 (Fusion & Telemetry)**: State fusion matrix, semantic cache, and grace period countdown (`test_checkpoint_2.py`).
- [x] **Checkpoint 3 (Sprint 3 & 4)**: The Zero-Balance block test, Earn-and-Burn access restoration, and Graceful Shutdown unblock (`test_system_orchestration.py`).

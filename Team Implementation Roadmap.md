# Team Implementation & Chronological Roadmap
**Project:** AI-Driven Contextual Study Monitor (PC/Desktop)

## Engineering Roles
To maximize parallel development, the team is divided into four specialized roles:
*   **Engineer 1 (Data & Logic - Lead):** Responsible for Database, State Controller, and final System Orchestration.
*   **Engineer 2 (Computer Vision):** Responsible for the webcam feed, MediaPipe, and physical state classification.
*   **Engineer 3 (NLP & App Integration):** Responsible for OS window scraping and local Ollama (SLM) prompting.
*   **Engineer 4 (Systems & OS):** Responsible for administrative OS enforcement (Hosts file/DNS blocking).

---

## Phase 1: Parallel Core Development (Sprint 1)
*Goal: Build the independent modules. Modules do not talk to each other yet. They only return standardized outputs.*

### Tasks
*   **[Eng 1] Task 1.1: Database Scaffolding**
    *   *Action:* Create `db_manager.py`. Set up SQLite database (`time_logs` table). Implement `update_balance(delta)` and `get_current_balance()`.
    *   *Output:* A functional DB module that can be imported by others.
*   **[Eng 2] Task 1.2: Vision Pipeline**
    *   *Action:* Create `vision_pipeline.py`. Implement MediaPipe Face Mesh. Calculate EAR (sleep) and Head Pose (away).
    *   *Output:* Function `get_vision_state()` returning `"ACTIVE"` or `"IDLE"`.
*   **[Eng 3] Task 1.3: Semantic Pipeline**
    *   *Action:* Create `semantic_pipeline.py`. Implement `pygetwindow` to grab active window titles. Connect to local Ollama API (e.g., Llama 3) via `requests`.
    *   *Output:* Function `get_semantic_state()` returning `"EDUCATIONAL"` or `"DISTRACTION"`.
*   **[Eng 4] Task 1.4: OS Enforcement Engine**
    *   *Action:* Create `enforcement.py`. Write scripts requiring Admin/Sudo to read/write the OS `hosts` file.
    *   *Output:* Functions `block_distractions()` and `unblock_distractions()`.

### 🛑 Integration Checkpoint 1: Module Unit Tests
*Dependencies must be resolved before proceeding.*
*   [ ] Eng 1 proves the DB retains state after a script restarts.
*   [ ] Eng 2 proves the camera detects closed eyes within 2 seconds.
*   [ ] Eng 3 proves Ollama correctly classifies "YouTube - Meme Compilation" vs. "YouTube - Calculus Tutorial".
*   [ ] Eng 4 proves running `block_distractions()` successfully blocks browser access to predefined domains.

---

## Phase 2: Logic Fusion (Sprint 2)
*Goal: Connect the physical and digital sensors to the decision engine (The Brain).*

### Tasks
*   **[Eng 1 & Eng 2] Task 2.1: Vision Integration**
    *   *Action:* Import `vision_pipeline` into `logic_controller.py`. Set up a 5-second polling loop to read the camera state without crashing.
*   **[Eng 1 & Eng 3] Task 2.2: Semantic Integration**
    *   *Action:* Import `semantic_pipeline` into `logic_controller.py`. Query the active window synchronously with the camera check.
*   **[Eng 1] Task 2.3: The AND Gate & DB Update**
    *   *Action:* Write the reward logic. If (`ACTIVE` AND `EDUCATIONAL`), call `db_manager.update_balance(+1)`. Else if (`DISTRACTION` OR `IDLE`), call `db_manager.update_balance(-1)`.

### 🛑 Integration Checkpoint 2: The "Brain" Check
*   [ ] Run `logic_controller.py`. 
*   [ ] **Test:** Engineer opens a Wikipedia article on Science and stares at it. The console prints "Both Active: Accruing Time" and the DB balance increases.
*   [ ] **Test:** Engineer closes their eyes while on the Wikipedia article. The DB balance stops increasing (Vision override).

---

## Phase 3: Final Orchestration & Enforcement (Sprint 3)
*Goal: Tie the logic engine to the OS enforcement layer to create the automated loop.*

### Tasks
*   **[Eng 1 & Eng 4] Task 3.1: Triggering Enforcement**
    *   *Action:* Create `main.py`. In the main loop, check `db_manager.get_current_balance()`.
    *   *Action:* If balance <= 0 and `get_semantic_state() == "DISTRACTION"`, trigger `enforcement.block_distractions()`. 
    *   *Action:* If balance > 0, trigger `enforcement.unblock_distractions()`.
*   **[Eng 2 & Eng 3] Task 3.2: Edge-Case Handling & Optimization**
    *   *Action:* (Eng 2) Optimize MediaPipe frame sampling to reduce CPU load (e.g., 2 FPS instead of 30 FPS).
    *   *Action:* (Eng 3) Cache previous window titles so Ollama isn't queried unnecessarily if the user hasn't switched tabs.

### 🛑 Integration Checkpoint 3: End-to-End System Test
*   [ ] **The Zero-Balance Test:** Start system with 0 earned time. Try to open Reddit. The system should immediately block it.
*   [ ] **The Earn-and-Burn Test:** Study effectively for 2 minutes (balance > 0). Open Reddit. It should load. Look away from the screen for 2 minutes (balance drains). Reddit should suddenly become blocked.

---

## Phase 4: Polish for Research Experiment (Sprint 4)
*Goal: Make the system robust enough for participant testing.*

### Tasks
*   **[All Engineers] Task 4.1: Data Logging**
    *   *Action:* Modify `logic_controller.py` to append every state change (timestamp, vision state, semantic state, balance) to a `research_data.csv` file for paper analysis.
*   **[Eng 4] Task 4.2: Graceful Shutdown**
    *   *Action:* Ensure that if the program crashes or is manually closed, it automatically calls `unblock_distractions()` so the user's PC isn't permanently locked out of websites.
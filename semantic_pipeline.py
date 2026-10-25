"""
semantic_pipeline.py - Engineer 3: NLP & App Integration
Responsible for OS window scraping using pygetwindow (with OS fallbacks)
and local Ollama (SLM) prompting via requests for activity classification.

Task 1.3 Output: get_semantic_state() returning "EDUCATIONAL" or "DISTRACTION".
"""

import os
import re
import sys
import requests
import pygetwindow as gw

DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", None)


def get_active_window_title():
    """
    Scrapes the title of the currently active/foreground OS window.
    On Windows, attaches to the interactive 'Default' desktop to access real user windows
    even when running inside agent/service environments.
    """
    title = None

    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # Explicitly attach thread to interactive Default desktop
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)

            # 1. Check Foreground Window
            hwnd = user32.GetForegroundWindow()
            if hwnd and user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    val = buffer.value.strip()
                    if val and val not in ("Program Manager", "Windows Input Experience", "Task Switching"):
                        title = val

            # 2. If foreground is blank or generic, inspect top-level visible application windows
            if not title:
                visible_windows = []
                def enum_proc(h, extra):
                    if user32.IsWindowVisible(h):
                        l = user32.GetWindowTextLengthW(h)
                        if l > 0:
                            b = ctypes.create_unicode_buffer(l + 1)
                            user32.GetWindowTextW(h, b, l + 1)
                            t = b.value.strip()
                            if t and t not in ("Program Manager", "Windows Input Experience", "Settings"):
                                visible_windows.append(t)
                    return True
                WND = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
                user32.EnumWindows(WND(enum_proc), 0)
                if visible_windows:
                    title = visible_windows[0]
        except Exception:
            pass

    if not title:
        try:
            active_window = gw.getActiveWindow()
            if active_window and active_window.title:
                title = active_window.title.strip()
            else:
                raw_title = gw.getActiveWindowTitle()
                if raw_title:
                    title = raw_title.strip()
        except Exception:
            pass

    return title if title else "Desktop / Idle"



def get_available_ollama_models(ollama_url=DEFAULT_OLLAMA_URL):
    """Fetch list of locally installed model names from Ollama."""
    try:
        resp = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            return models
    except Exception:
        pass
    return []


def resolve_model_name(requested_model=None, ollama_url=DEFAULT_OLLAMA_URL):
    """
    Resolves which Ollama model to use:
    1. requested_model argument (if provided)
    2. OLLAMA_MODEL env var
    3. Auto-detected installed model (llama3, qwen2.5, etc.)
    4. Fallback default 'llama3'
    """
    if requested_model:
        return requested_model
    if DEFAULT_MODEL:
        return DEFAULT_MODEL

    available = get_available_ollama_models(ollama_url)
    if available:
        # Check if llama3 or qwen is in available models
        for pref in ["llama3", "llama3:latest", "qwen2.5:7b", "qwen2.5:latest"]:
            for m in available:
                if m == pref or m.startswith(pref):
                    return m
        return available[0]

    return "llama3"


CLASSIFICATION_PROMPT_TEMPLATE = """You are an automated productivity activity classifier.
Analyze the provided active OS window title and classify whether the user's current activity is EDUCATIONAL or a DISTRACTION.

Definitions:
- EDUCATIONAL: Academic study, tutorials, university lectures, calculus/math, coding, software development, documentation, research papers, course materials, books, search engines, standard desktop navigation, IDEs, study tools.
- DISTRACTION: Video games, memes, comedy compilations, social media reels/shorts, entertainment gossip, movie streams, gaming streams.

Few-Shot Examples:
Window: "YouTube - Calculus Tutorial" -> EDUCATIONAL
Window: "Coursera: Machine Learning by Andrew Ng - Google Chrome" -> EDUCATIONAL
Window: "Visual Studio Code - semantic_pipeline.py" -> EDUCATIONAL
Window: "Google Search: Python async programming - Google Chrome" -> EDUCATIONAL
Window: "Desktop / Idle" -> EDUCATIONAL
Window: "YouTube - Meme Compilation" -> DISTRACTION
Window: "Reddit: r/funny memes - Mozilla Firefox" -> DISTRACTION
Window: "Steam - Counter-Strike 2" -> DISTRACTION
Window: "Twitch - GTA V Stream" -> DISTRACTION

Window: "{window_title}"
Respond strictly with only ONE word: either "EDUCATIONAL" or "DISTRACTION". Do not include any other words or punctuation."""


_window_cache = {}


def clear_semantic_cache():
    """Task 3.2: Clears the cached window title classifications."""
    global _window_cache
    _window_cache.clear()


def classify_window_title(window_title, model=None, ollama_url=DEFAULT_OLLAMA_URL, timeout=15):
    """
    Queries local Ollama API to classify window_title into EDUCATIONAL or DISTRACTION.
    Implements Task 3.2 caching so Ollama isn't queried unnecessarily when user hasn't switched tabs.
    """
    if not window_title or not window_title.strip():
        return "EDUCATIONAL"

    clean_key = window_title.strip().lower()
    if clean_key in _window_cache:
        return _window_cache[clean_key]

    clean = clean_key

    # Fast-path 1 (Explicit Distractions): Entertainment, gaming, meme compilations, video streams
    if any(k in clean for k in [
        "meme compilation", "funny memes", "tiktok", "reels", "shorts", "twitch",
        "netflix", "steam", "counter-strike", "valorant", "fortnite", "gta v",
        "dankmemes", "r/funny", "instagram", "twitter / x", "hulu", "disney+",
        "prime video", "roblox", "minecraft", "league of legends"
    ]):
        _window_cache[clean_key] = "DISTRACTION"
        return "DISTRACTION"

    # Fast-path 2 (Study, Research, Development, Navigation & Workspace):
    if any(k in clean for k in [
        "demon study monitor", "localhost:8000", "visual studio code", "cursor", "sublime",
        "pycharm", "intellij", "powershell", "cmd.exe", "terminal", "bash", "git bash",
        "wikipedia", "arxiv", "khan academy", "coursera", "edx", "mit opencourseware",
        "calculus", "tutorial", "documentation", "docs", "stackoverflow", "stack overflow",
        "desktop", "desktop / idle", "settings", "file explorer", "explorer.exe", "documents",
        "new tab", "google", "bing", "duckduckgo",
        "study", "lecture", "learning", "classroom", "canvas", "blackboard", "moodle",
        "research", "paper", "reader", "pdf", "acrobat", "notion", "obsidian", "anki", "github"
    ]):
        _window_cache[clean_key] = "EDUCATIONAL"
        return "EDUCATIONAL"

    target_model = resolve_model_name(model, ollama_url)
    prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(window_title=window_title.strip())

    endpoint = f"{ollama_url.rstrip('/')}/api/generate"
    payload = {
        "model": target_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 10
        }
    }

    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
        response.raise_for_status()
        raw_text = response.json().get("response", "").strip().upper()
    except Exception as e:
        # Fallback keyword heuristic if Ollama service is unreachable
        clean = window_title.lower()
        if any(term in clean for term in ["calculus", "tutorial", "lecture", "coursera", "code", "learn", "study"]):
            _window_cache[clean_key] = "EDUCATIONAL"
            return "EDUCATIONAL"
        if any(term in clean for term in ["meme", "compilation", "funny", "game", "tiktok", "reel"]):
            _window_cache[clean_key] = "DISTRACTION"
            return "DISTRACTION"
        raise ConnectionError(f"Failed to communicate with Ollama at {endpoint}: {e}")

    # Extract classified label
    if "EDUCATIONAL" in raw_text:
        result = "EDUCATIONAL"
    elif "DISTRACTION" in raw_text:
        result = "DISTRACTION"
    else:
        tokens = re.findall(r"\b(EDUCATIONAL|DISTRACTION)\b", raw_text)
        if tokens:
            result = tokens[0]
        else:
            result = "DISTRACTION" if "MEME" in raw_text or "ENTERTAINMENT" in raw_text else "EDUCATIONAL"

    _window_cache[clean_key] = result
    return result


_mock_semantic_state = None


def set_mock_semantic_state(state):
    """Sets a mock state for testing or simulation ('EDUCATIONAL', 'DISTRACTION', or None to revert)."""
    global _mock_semantic_state
    if state is not None and state not in ("EDUCATIONAL", "DISTRACTION"):
        raise ValueError("Semantic state must be either 'EDUCATIONAL', 'DISTRACTION', or None")
    _mock_semantic_state = state


def get_semantic_state(window_title=None, model=None, ollama_url=DEFAULT_OLLAMA_URL):
    """
    Primary interface for Engineer 3 (NLP & App Integration).
    Scrapes the active window title (if not provided) and prompts local Ollama SLM.
    Returns: "EDUCATIONAL" or "DISTRACTION".
    """
    global _mock_semantic_state
    if _mock_semantic_state is not None and window_title is None:
        return _mock_semantic_state

    if window_title is None:
        window_title = get_active_window_title()

    return classify_window_title(window_title, model=model, ollama_url=ollama_url)


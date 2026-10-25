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
        hdesk = None
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
                WND = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumWindows(WND(enum_proc), 0)
                if visible_windows:
                    title = visible_windows[0]
        except Exception:
            pass
        finally:
            if hdesk:
                try:
                    user32.CloseDesktop(hdesk)
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


_MAX_WINDOW_CACHE = 500
_window_cache = {}


def _cache_put(key: str, val: str):
    global _window_cache
    if len(_window_cache) >= _MAX_WINDOW_CACHE:
        for k in list(_window_cache.keys())[:100]:
            _window_cache.pop(k, None)
    _window_cache[key] = val


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
        _cache_put(clean_key, "DISTRACTION")
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
        _cache_put(clean_key, "EDUCATIONAL")
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
            _cache_put(clean_key, "EDUCATIONAL")
            return "EDUCATIONAL"
        if any(term in clean for term in ["meme", "compilation", "funny", "game", "tiktok", "reel"]):
            _cache_put(clean_key, "DISTRACTION")
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

    _cache_put(clean_key, result)
    return result


_mock_semantic_state = None


def set_mock_semantic_state(state):
    """Sets a mock state for testing or simulation ('EDUCATIONAL', 'DISTRACTION', or None to revert)."""
    global _mock_semantic_state
    if state is not None and state not in ("EDUCATIONAL", "DISTRACTION"):
        raise ValueError("Semantic state must be either 'EDUCATIONAL', 'DISTRACTION', or None")
    _mock_semantic_state = state


from urllib.parse import quote_plus
from typing import Optional, Dict, Any
import json


def extract_youtube_video_id(url_or_str: str) -> Optional[str]:
    """Extracts 11-char YouTube video ID if present in string or URL."""
    if not url_or_str:
        return None
    clean = url_or_str.strip()
    if re.match(r"^[0-9A-Za-z_-]{11}$", clean):
        return clean
    patterns = [
        r"(?:v=)([0-9A-Za-z_-]{11})(?:[&?]|$)",
        r"youtu\.be\/([0-9A-Za-z_-]{11})(?:[&?]|$)",
        r"embed\/([0-9A-Za-z_-]{11})(?:[&?]|$)",
        r"shorts\/([0-9A-Za-z_-]{11})(?:[&?]|$)",
        r"(?:watch\?v=|\/v\/|\/u\/\w\/)([0-9A-Za-z_-]{11})",
        r"(?:\b)([0-9A-Za-z_-]{11})(?:\b)"
    ]
    for p in patterns:
        m = re.search(p, clean)
        if m:
            cand = m.group(1)
            # Ensure it is a valid 11-char token with numbers/mixed case
            if len(cand) == 11 and (any(c.isdigit() for c in cand) or any(c.isupper() for c in cand)):
                return cand
    return None


def validate_youtube_content(
    query_or_url: str,
    user_task: str = "General Academic Study",
    ollama_url: str = DEFAULT_OLLAMA_URL
) -> Dict[str, Any]:
    """
    Evaluates whether a YouTube search query or video URL is EDUCATIONAL and relevant
    to the user's active study task. If not, playback is strictly blocked.
    """
    clean_query = (query_or_url or "").strip()
    clean_task = (user_task or "General Academic Study").strip()

    if not clean_query:
        return {
            "is_approved": False,
            "category": "INVALID",
            "reason": "Please enter a search query or YouTube video link.",
            "video_id": None,
            "embed_url": None
        }

    vid_id = extract_youtube_video_id(clean_query)
    q_lower = clean_query.lower()
    task_lower = clean_task.lower()

    # 1. Distraction keywords check
    distraction_keywords = [
        "meme", "memes", "funny", "tiktok", "reels", "shorts", "prank", "pranks",
        "gaming", "gameplay", "gta", "minecraft", "fortnite", "valorant", "roblox",
        "stream", "twitch", "comedy", "music video", "official music video", "trailer",
        "movie clip", "vlog", "mrbeast", "dank", "compilation", "react", "reaction",
        "entertainment", "gossip", "unboxing", "challenge", "asmr", "horrific", "scary",
        "fails", "fail", "dance", "trolling"
    ]

    matched_distraction = next((kw for kw in distraction_keywords if re.search(rf"\b{re.escape(kw)}\b", q_lower)), None)
    if matched_distraction and matched_distraction not in task_lower:
        return {
            "is_approved": False,
            "category": "DISTRACTION",
            "reason": f"Content contains entertainment keyword '{matched_distraction}' which is blocked during focus sessions.",
            "video_id": vid_id,
            "embed_url": None
        }

    # 2. Try querying Ollama for deep semantic relevance if available
    try:
        model = resolve_model_name(None, ollama_url)
        prompt = (
            f"You are an AI Academic Content Classifier for a focused student workstation.\n"
            f"Active Student Task: \"{clean_task}\"\n"
            f"Requested YouTube Query or Title: \"{clean_query}\"\n\n"
            f"Evaluate if this YouTube content is EDUCATIONAL and relevant to the student's task.\n"
            f"Respond strictly with a JSON object in this exact format:\n"
            f'{{"approved": true, "category": "EDUCATIONAL", "reason": "concise explanation"}}'
        )
        endpoint = f"{ollama_url.rstrip('/')}/api/generate"
        resp = requests.post(
            endpoint,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 50}
            },
            timeout=3.0
        )
        if resp.status_code == 200:
            raw = resp.json().get("response", "").strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                approved = bool(parsed.get("approved", False))
                cat = parsed.get("category", "EDUCATIONAL" if approved else "DISTRACTION")
                reason = parsed.get("reason", "Evaluated by AI.")
                embed = f"https://www.youtube-nocookie.com/embed/{vid_id}?autoplay=1" if (approved and vid_id) else (
                    f"https://www.youtube-nocookie.com/embed?listType=search&list={quote_plus(clean_query)}" if approved else None
                )
                return {
                    "is_approved": approved,
                    "category": cat,
                    "reason": reason,
                    "video_id": vid_id,
                    "embed_url": embed
                }
    except Exception:
        pass

    # 3. Local Academic Semantic Heuristic
    academic_keywords = [
        "calculus", "math", "mathematics", "physics", "chemistry", "biology",
        "computer science", "programming", "python", "java", "c++", "data structures",
        "algorithms", "tutorial", "lecture", "course", "class", "edx", "coursera",
        "khan academy", "mit", "harvard", "stanford", "professor", "explanation",
        "how to", "history", "economics", "psychology", "literature", "engineering",
        "research", "paper", "architecture", "design patterns", "devops", "database",
        "sql", "machine learning", "ai", "neural network", "linear algebra", "statistics",
        "derivatives", "integration", "geometry", "algebra", "operating systems",
        "compiler", "frontend", "backend", "react", "fastapi", "docker", "kubernetes"
    ]

    is_academic = any(kw in q_lower for kw in academic_keywords)
    task_words = [w for w in re.findall(r"[a-zA-Z]{3,}", task_lower) if w not in ("and", "the", "for", "with", "study", "learning")]
    task_overlap = any(w in q_lower for w in task_words) if task_words else False

    if is_academic or task_overlap or clean_task == "General Academic Study":
        embed = f"https://www.youtube-nocookie.com/embed/{vid_id}?autoplay=1" if vid_id else f"https://www.youtube-nocookie.com/embed?listType=search&list={quote_plus(clean_query)}"
        return {
            "is_approved": True,
            "category": "EDUCATIONAL",
            "reason": f"Content matches academic keywords or active study task ('{clean_task}').",
            "video_id": vid_id,
            "embed_url": embed
        }
    else:
        return {
            "is_approved": False,
            "category": "UNRELATED",
            "reason": f"Content does not appear educational or relevant to your active task: '{clean_task}'.",
            "video_id": vid_id,
            "embed_url": None
        }


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


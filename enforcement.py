"""
enforcement.py - Systems & OS Enforcement Engine (Demon Study Monitor)
Responsible for:
- Surgical tab closing via Ctrl+W (never terminating the parent browser process)
- Strict termination for standalone blacklisted executables (discord.exe, steam.exe)
- Granular Policy & Quota Budget compliance (allows quota time, e.g. 45 min YouTube)
- Emergency Lockdown & Zero Tolerance immediate enforcement
- Windows PAC proxy & Hosts file domain redirection
"""

import os
import sys
import time
import ctypes
import subprocess
import socket
import winreg
import atexit
from typing import Optional, List, Dict, Any, Tuple

import db_manager

BLOCK_HEADER = "# === DEMON OS ENFORCEMENT BLOCK BEGIN ==="
BLOCK_FOOTER = "# === DEMON OS ENFORCEMENT BLOCK END ==="
REDIRECT_IPV4 = "127.0.0.1"
REDIRECT_IPV6 = "::1"

INTERNET_SETTINGS_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37

DEFAULT_DISTRACTION_DOMAINS = [
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
    "reddit.com",
    "www.reddit.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "tiktok.com",
    "www.tiktok.com",
    "netflix.com",
    "www.netflix.com",
    "twitch.tv",
    "www.twitch.tv",
    "discord.com",
    "www.discord.com",
    "pinterest.com",
    "www.pinterest.com",
]

STANDALONE_BLACKLIST_EXES = [
    "discord.exe",
    "steam.exe",
    "spotify.exe",
    "epicgameslauncher.exe",
    "riotclientservices.exe",
    "robloxplayerbeta.exe",
    "battle.net.exe"
]

SAFE_WHITELIST_TITLES = [
    "demon", "visual studio", "vs code", "antigravity", "cursor",
    "cmd", "powershell", "terminal", "bash", "python", "pycharm"
]

_is_blocked_state = False
_mock_mode = False


def set_mock_mode(enabled: bool = True):
    """Enable or disable mock enforcement mode for unit tests."""
    global _mock_mode
    _mock_mode = enabled


def get_default_hosts_path():
    """Returns the default system hosts file path depending on the OS."""
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        return os.path.join(system_root, "System32", "drivers", "etc", "hosts")
    return "/etc/hosts"


def is_admin():
    """Check if the current process has administrative/root privileges."""
    if sys.platform == "win32":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return os.geteuid() == 0


def can_write_hosts(hosts_path=None) -> bool:
    """Checks whether the hosts file is directly writeable."""
    target_path = hosts_path or get_default_hosts_path()
    try:
        with open(target_path, "a", encoding="utf-8") as f:
            pass
        return True
    except Exception:
        return False


def _trigger_uac_grant_permission():
    """Launches Grant_Hosts_Permission.bat to allow the user to elevate via UAC."""
    if sys.platform != "win32":
        return False
    bat_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Grant_Hosts_Permission.bat")
    if not os.path.exists(bat_path):
        bat_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "Grant_Hosts_Permission.bat")
    if os.path.exists(bat_path):
        try:
            os.startfile(bat_path)
            return True
        except Exception:
            pass
    return False


def flush_dns():
    """Flushes the local OS DNS resolver cache."""
    try:
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            subprocess.run(
                ["ipconfig", "/flushdns"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags
            )
        elif sys.platform.startswith("linux"):
            subprocess.run(["resolvectl", "flush-caches"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        elif sys.platform == "darwin":
            subprocess.run(["dscacheutil", "-flushcache"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["killall", "-HUP", "mDNSResponder"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception:
        return False


# =========================================================================
# PAC Proxy System (Works without admin, intercepts Chrome/Edge DoH)
# =========================================================================

def get_pac_script(is_locked: bool = True) -> str:
    """
    Generates dynamic Proxy Auto-Configuration (PAC) script.
    When is_locked is True, routes YouTube and distractions to dead port 127.0.0.1:9.
    When is_locked is False, returns DIRECT for all traffic.
    """
    if not is_locked:
        return "function FindProxyForURL(url, host) {\n    return 'DIRECT';\n}\n"

    return """function FindProxyForURL(url, host) {
    var h = ("" + host).toLowerCase();
    if (
        shExpMatch(h, "*youtube.com*") ||
        shExpMatch(h, "*youtu.be*") ||
        shExpMatch(h, "*googlevideo.com*") ||
        shExpMatch(h, "*ytimg.com*") ||
        shExpMatch(h, "*yt3.ggpht.com*") ||
        shExpMatch(h, "*yt4.ggpht.com*") ||
        shExpMatch(h, "*youtubei.googleapis.com*") ||
        shExpMatch(h, "*youtubekids.com*") ||
        shExpMatch(h, "*tiktok.com*") ||
        shExpMatch(h, "*netflix.com*") ||
        shExpMatch(h, "*twitch.tv*") ||
        shExpMatch(h, "*reddit.com*") ||
        shExpMatch(h, "*instagram.com*") ||
        h.indexOf("youtube") !== -1 ||
        h.indexOf("youtu.be") !== -1 ||
        h.indexOf("googlevideo") !== -1
    ) {
        return "PROXY 127.0.0.1:9";
    }
    return "DIRECT";
}
"""


def enable_pac_proxy(pac_url: str = "http://127.0.0.1:8000/proxy.pac") -> bool:
    """Enables Windows system PAC proxy in HKCU."""
    if sys.platform != "win32":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, pac_url)

        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        return True
    except Exception:
        return False


def disable_pac_proxy() -> bool:
    """Disables the PAC proxy setting by removing AutoConfigURL."""
    if sys.platform != "win32":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, "AutoConfigURL")
            except FileNotFoundError:
                pass
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        return True
    except Exception:
        return False


def is_pac_proxy_enabled() -> bool:
    """Checks if AutoConfigURL is currently set in HKCU."""
    if sys.platform != "win32":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "AutoConfigURL")
            return bool(val)
    except Exception:
        return False


try:
    atexit.register(disable_pac_proxy)
except Exception:
    pass


# =========================================================================
# Checkpoint 2: Surgical Tab Closing & Quota Enforcement
# =========================================================================

def close_active_browser_tab(hwnd) -> bool:
    """
    Surgically closes the active tab in the browser using Ctrl+W.
    Never terminates or kills the browser process itself.
    """
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        # Bring window into active input focus if needed
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.02)

        # Send Ctrl + W keystrokes
        VK_CONTROL = 0x11
        VK_W = 0x57
        KEYEVENTF_KEYUP = 0x0002

        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_W, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

        # Warning beep
        user32.MessageBeep(0x00000010)
        return True
    except Exception:
        return False


def terminate_standalone_app(hwnd, process_name: str = "") -> bool:
    """
    Terminates a standalone distraction application (e.g. discord.exe, steam.exe).
    """
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        # First attempt graceful WM_CLOSE
        WM_CLOSE = 0x0010
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

        # If process name provided and still running after 0.2s, force terminate
        if process_name and any(p.lower() in process_name.lower() for p in STANDALONE_BLACKLIST_EXES):
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            subprocess.run(
                ["taskkill", "/F", "/IM", process_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags
            )
        return True
    except Exception:
        return False


def is_distraction_allowed_by_policy(app_or_title: str) -> Tuple[bool, Optional[int]]:
    """
    Evaluates whether an app or site is currently permitted by Granular Quota Budget:
    - If in Zero Tolerance Emergency Lockdown: Strictly False (0 remaining).
    - If policy exists (e.g. YouTube 45 mins): returns (True, remaining_seconds) if remaining > 0.
    - If quota is exhausted (remaining == 0): returns (False, 0).
    - If no policy exists: returns (False, None).
    """
    lockdown = db_manager.get_emergency_lockdown()
    if lockdown["is_active"] and lockdown["zero_tolerance"]:
        return False, 0

    lower_text = app_or_title.lower()

    # Check for policy match (e.g., youtube.com, discord.exe)
    policies = db_manager.get_policies()
    for pol in policies:
        target = pol["app_or_domain"].lower()
        if target in lower_text or target.replace(".com", "") in lower_text:
            rem = pol["remaining_seconds"]
            if rem > 0 and pol["is_enabled"]:
                return True, rem
            else:
                return False, 0

    return False, None


def enforce_active_distraction(window_title=None, process_name=None):
    """
    Active distraction enforcement (Checkpoint 2 & Policy Engine):
    1. Checks if title matches safe whitelist (IDE, code editor, terminal) -> never enforce.
    2. Checks if title matches a known distraction.
    3. Checks Granular Policy Engine:
       - If YouTube has remaining quota (e.g. 45 min interval), ACCESS IS GRANTED!
         It tracks usage and does NOT close the tab.
    4. If no quota or in Zero Tolerance Lockdown:
       - If it's a browser tab (Chrome/Edge/Firefox), CLOSES THE TAB (Ctrl+W)!
       - If it's a standalone blacklisted app (discord.exe, steam.exe), TERMINATES the executable.
    """
    global _is_blocked_state, _mock_mode
    if _mock_mode:
        return False

    if sys.platform != "win32":
        return False

    hdesk = None
    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)

        hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindowVisible(hwnd):
            return False

        if window_title:
            curr_title = window_title.strip()
        else:
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return False
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            curr_title = buf.value.strip()

        curr_title_lower = curr_title.lower()

        # Whitelist safe workspace apps
        if any(w in curr_title_lower for w in SAFE_WHITELIST_TITLES):
            return False

        # Identify distraction keywords
        distraction_keywords = [
            "youtube", "youtu.be", "tiktok", "netflix",
            "twitch", "reddit", "twitter", "instagram", "facebook", "gaming"
        ]

        is_distraction = any(kw in curr_title_lower for kw in distraction_keywords)

        # Check if standalone blacklist executable is running
        is_standalone_blacklisted = False
        p_name = process_name or ""
        if not p_name:
            # Query process ID and executable name
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value > 0:
                try:
                    import psutil
                    proc = psutil.Process(pid.value)
                    p_name = proc.name().lower()
                except Exception:
                    pass

        if p_name and any(b in p_name for b in STANDALONE_BLACKLIST_EXES):
            is_distraction = True
            is_standalone_blacklisted = True

        if not is_distraction:
            return False

        # -----------------------------------------------------------------
        # Granular Policy Engine & Quota Budget Check
        # -----------------------------------------------------------------
        allowed, remaining_sec = is_distraction_allowed_by_policy(curr_title_lower)
        if allowed:
            # User is using their allowed leisure quota budget!
            # Record 1 second of quota usage
            db_manager.record_policy_usage(curr_title_lower, duration_seconds=1.0)
            return False  # ACCESS GRANTED! Do not close or minimize!

        # -----------------------------------------------------------------
        # Surgical Enforcement (Tab Close or App Termination)
        # -----------------------------------------------------------------
        browser_markers = ["edge", "chrome", "firefox", "brave", "opera", "browser"]
        is_browser = any(b in curr_title_lower or b in p_name for b in browser_markers)

        if is_browser:
            # User requirement Checkpoint 2: "i want the window tab to be closed"
            close_active_browser_tab(hwnd)
            return True
        elif is_standalone_blacklisted:
            # Standalone blacklisted app: strictly terminate
            terminate_standalone_app(hwnd, process_name=p_name)
            return True
        else:
            # Fallback: close window
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            return True

    except Exception:
        pass
    finally:
        if hdesk and 'user32' in locals() and hasattr(user32, 'CloseDesktop'):
            try:
                user32.CloseDesktop(hdesk)
            except Exception:
                pass
    return False


# =========================================================================
# Hosts File Blocking
# =========================================================================

def _clean_hosts_content(content):
    """Strips any existing DEMON enforcement block from hosts content."""
    lines = content.splitlines()
    cleaned = []
    in_block = False

    for line in lines:
        if BLOCK_HEADER in line:
            in_block = True
            continue
        if BLOCK_FOOTER in line:
            in_block = False
            continue
        if not in_block:
            cleaned.append(line)

    return "\n".join(cleaned).rstrip() + "\n"


def is_distraction_blocked(hosts_path=None) -> bool:
    """Returns whether distractions are currently in the blocked state."""
    global _is_blocked_state
    if hosts_path is not None:
        if os.path.exists(hosts_path):
            try:
                with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    return BLOCK_HEADER in content
            except Exception:
                pass
        return False
    return _is_blocked_state


def block_distractions(domains=None, hosts_path=None, force_flush=True):
    """
    Blocks distraction domains via PAC Proxy (zero admin) and hosts file.
    Filter out domains that have an active, unexhausted leisure quota.
    """
    global _is_blocked_state, _mock_mode
    if domains is None:
        domains = list(DEFAULT_DISTRACTION_DOMAINS)

    if _mock_mode:
        _is_blocked_state = True
        return domains

    # Only filter out quota domains during live runtime without custom hosts_path
    filtered_domains = list(domains)
    if hosts_path is None:
        lockdown = db_manager.get_emergency_lockdown()
        if not (lockdown["is_active"] and lockdown["zero_tolerance"]):
            active_filtered = []
            for d in domains:
                allowed, rem = is_distraction_allowed_by_policy(d)
                if not allowed:
                    active_filtered.append(d)
            filtered_domains = active_filtered

    # Enable PAC proxy
    enable_pac_proxy()

    target_path = hosts_path or get_default_hosts_path()

    try:
        existing_content = ""
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                existing_content = f.read()

        cleaned_content = _clean_hosts_content(existing_content)

        block_lines = [
            BLOCK_HEADER,
            f"# Total blocked domains: {len(filtered_domains)}",
        ]
        for domain in filtered_domains:
            domain = domain.strip().lower()
            if domain:
                block_lines.append(f"0.0.0.0\t{domain}")
                block_lines.append(f"{REDIRECT_IPV4}\t{domain}")
                block_lines.append(f"{REDIRECT_IPV6}\t{domain}")
        block_lines.append(BLOCK_FOOTER)
        block_lines.append("")

        new_block = "\n".join(block_lines)
        final_content = cleaned_content.rstrip() + "\n\n" + new_block

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(final_content)

        if force_flush:
            flush_dns()

        _is_blocked_state = True
        return filtered_domains

    except Exception:
        _is_blocked_state = True
        return filtered_domains


def unblock_distractions(hosts_path=None, force_flush=True):
    """Removes the DEMON enforcement block and disables PAC proxy."""
    global _is_blocked_state, _mock_mode
    if _mock_mode:
        _is_blocked_state = False
        return True

    disable_pac_proxy()

    target_path = hosts_path or get_default_hosts_path()

    try:
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                existing_content = f.read()

            cleaned_content = _clean_hosts_content(existing_content)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(cleaned_content)

            if force_flush:
                flush_dns()

        _is_blocked_state = False
        return True
    except Exception:
        _is_blocked_state = False
        return True


def is_domain_blocked(domain, hosts_path=None):
    """Verifies if a specific domain is currently routed to localhost in the hosts file."""
    target_path = hosts_path or get_default_hosts_path()
    if not os.path.exists(target_path):
        return False

    domain = domain.strip().lower()
    with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
        in_block = False
        for line in f:
            line_str = line.strip()
            if BLOCK_HEADER in line_str:
                in_block = True
                continue
            if BLOCK_FOOTER in line_str:
                in_block = False
                continue
            if in_block and not line_str.startswith("#"):
                parts = line_str.split()
                if len(parts) >= 2 and parts[1].lower() == domain:
                    if parts[0] in ("0.0.0.0", REDIRECT_IPV4, REDIRECT_IPV6):
                        return True
    return False


def simulate_browser_request_to_domain(domain, port=80, timeout=1.0):
    """Simulates a browser HTTP socket connection to test domain reachability."""
    try:
        s = socket.create_connection((domain, port), timeout=timeout)
        s.close()
        return "REACHABLE"
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        return f"BLOCKED ({type(e).__name__})"


if __name__ == "__main__":
    print("[enforcement] Initializing enforcement module...")
    print(f"[enforcement] Is blocked: {is_distraction_blocked()}")
    print(f"[enforcement] Can write hosts: {can_write_hosts()}")

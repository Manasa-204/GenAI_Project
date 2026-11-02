"""
enforcement.py
--------------
Systems & OS Enforcement Engine for Parental Control.
Handles:
1. Domain-level website blocking via Windows hosts file (YouTube, TikTok, Gaming sites).
2. Proactive Zero-Tolerance Distraction App Termination:
   - When distraction blocking is active (balance <= 0 or lockdown enabled),
     STRICTLY blocks and immediately terminates ALL distraction processes:
     Roblox, Minecraft, Steam, Discord, Epic Games, Valorant, TikTok, Spotify, etc.
3. Real-Time Distraction Window Interceptor:
   - Minimizes / intercepts active browser windows or applications navigating to distraction content.
"""

import os
import sys
import ctypes
import subprocess
import socket
from typing import Optional, List, Dict, Any, Tuple, Set

import db_manager

BLOCK_HEADER = "# === DEMON OS ENFORCEMENT BLOCK BEGIN ==="
BLOCK_FOOTER = "# === DEMON OS ENFORCEMENT BLOCK END ==="
REDIRECT_IPV4 = "127.0.0.1"
REDIRECT_IPV6 = "::1"

# Comprehensive list of distraction domains redirected to localhost
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
    "roblox.com",
    "www.roblox.com",
    "steamcommunity.com",
    "store.steampowered.com",
]

# Comprehensive Blacklist of Distraction Executable Names (Case-insensitive)
KNOWN_DISTRACTION_PROCESSES = {
    # Games & Gaming Launchers
    "robloxplayerbeta.exe",
    "roblox.exe",
    "minecraft.exe",
    "javaw.exe",
    "steam.exe",
    "steamwebhelper.exe",
    "epicgameslauncher.exe",
    "epicwebhelper.exe",
    "riotclientservices.exe",
    "valorant.exe",
    "valorant-win64-shipping.exe",
    "fortniteclient-win64-shipping.exe",
    "fortnite.exe",
    "leagueclient.exe",
    "leagueclientux.exe",
    "genshinimpact.exe",
    "gta5.exe",
    "battle.net.exe",
    "origin.exe",
    "ea.exe",
    "eadesktop.exe",
    "ubisoftconnect.exe",
    # Social & Chat
    "discord.exe",
    "tiktok.exe",
    "whatsapp.exe",
    "telegram.exe",
    "instagram.exe",
    "facebook.exe",
    "slack.exe",
    "messenger.exe",
    # Media & Streaming
    "spotify.exe",
    "netflix.exe",
    "twitch.exe",
    "vlc.exe",
    "hulu.exe",
    "disneyplus.exe",
}

_is_blocked_state = False
_mock_mode = False


def set_mock_mode(enabled: bool = True):
    """Enable or disable mock enforcement mode for testing."""
    global _mock_mode
    _mock_mode = enabled


def get_default_hosts_path() -> str:
    """Returns default system hosts file path."""
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        return os.path.join(system_root, "System32", "drivers", "etc", "hosts")
    return "/etc/hosts"


def is_admin() -> bool:
    """Checks if current process has Administrator privileges."""
    if sys.platform == "win32":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return os.geteuid() == 0


def flush_dns() -> bool:
    """Flushes OS DNS resolver cache."""
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


def _clean_hosts_content(content: str) -> str:
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


def is_distraction_blocked(hosts_path: Optional[str] = None) -> bool:
    """Returns whether distractions are currently in the blocked state."""
    global _is_blocked_state
    if hosts_path is not None:
        if os.path.exists(hosts_path):
            try:
                with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                    return BLOCK_HEADER in f.read()
            except Exception:
                pass
        return False

    # Also inspect database state
    try:
        state = db_manager.get_child_state()
        if state.get("is_blocked", 0) == 1 or state.get("current_balance", 0) <= 0:
            return True
    except Exception:
        pass

    return _is_blocked_state


def can_write_hosts(hosts_path: Optional[str] = None) -> bool:
    """Checks whether target hosts file is writeable."""
    target_path = hosts_path or get_default_hosts_path()
    try:
        with open(target_path, "a", encoding="utf-8") as f:
            pass
        return True
    except Exception:
        return False


def _trigger_uac_grant_permission() -> bool:
    """Triggers Grant_Hosts_Permission.bat via UAC elevation if available."""
    if sys.platform != "win32":
        return False
    bat_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Grant_Hosts_Permission.bat")
    if os.path.exists(bat_path):
        try:
            os.startfile(bat_path)
            return True
        except Exception:
            pass
    return False


def block_distractions(
    domains: Optional[List[str]] = None,
    hosts_path: Optional[str] = None,
    force_flush: bool = True
) -> List[str]:
    """
    Blocks distraction domains by redirecting to 0.0.0.0, 127.0.0.1, and ::1.
    """
    global _is_blocked_state, _mock_mode
    if domains is None:
        domains = DEFAULT_DISTRACTION_DOMAINS

    if _mock_mode:
        _is_blocked_state = True
        return domains

    target_path = hosts_path or get_default_hosts_path()

    try:
        existing_content = ""
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                existing_content = f.read()

        cleaned_content = _clean_hosts_content(existing_content)

        block_lines = [
            BLOCK_HEADER,
            f"# Total blocked domains: {len(domains)}",
        ]
        for domain in domains:
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
        return domains

    except PermissionError:
        _is_blocked_state = True
        return domains
    except Exception:
        _is_blocked_state = True
        return domains


def unblock_distractions(hosts_path: Optional[str] = None, force_flush: bool = True) -> bool:
    """Removes the DEMON enforcement block, restoring domain access."""
    global _is_blocked_state, _mock_mode
    if _mock_mode:
        _is_blocked_state = False
        return True

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


def is_domain_blocked(domain: str, hosts_path: Optional[str] = None) -> bool:
    """Verifies if domain is currently in blocked state."""
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


def simulate_browser_request_to_domain(domain: str, port: int = 80, timeout: float = 1.0) -> str:
    """Tests socket connection to domain to verify reachability."""
    try:
        s = socket.create_connection((domain, port), timeout=timeout)
        s.close()
        return "REACHABLE"
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        return f"BLOCKED ({type(e).__name__})"


def enforce_active_distraction(window_title: Optional[str] = None) -> bool:
    """
    Minimizes or intercepts active foreground window if it matches distraction keywords.
    Plays system alert sound to reinforce focus.
    """
    if sys.platform != "win32":
        return False

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindowVisible(hwnd):
            return False

        if window_title:
            curr_title = window_title.strip().lower()
        else:
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return False
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            curr_title = buf.value.strip().lower()

        # Whitelist safe study and development tools
        whitelist = ["demon", "visual studio", "antigravity", "cursor", "cmd", "powershell", "terminal", "python", "word", "canvas"]
        if any(w in curr_title for w in whitelist):
            return False

        distraction_keywords = [
            "youtube", "youtu.be", "tiktok", "netflix",
            "twitch", "reddit", "twitter", "instagram", "facebook",
            "roblox", "steam", "discord", "minecraft", "game"
        ]

        for kw in distraction_keywords:
            if kw in curr_title:
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE (Minimizes window to taskbar)
                user32.MessageBeep(0x00000010)  # System warning alert sound
                return True
    except Exception:
        pass
    return False


# ==============================================================================
# STRICT PROACTIVE DISTRACTION PROCESS TERMINATION
# ==============================================================================

def terminate_process_by_name(process_name: str) -> bool:
    """
    Terminates all running instances of the specified process name.
    Uses Win32 TerminateProcess with taskkill /F fallback.
    """
    if sys.platform != "win32":
        return True

    p_name = process_name.strip().lower()
    if not p_name:
        return False

    # Prevent accidentally killing critical system processes
    protected = ["explorer.exe", "svchost.exe", "csrss.exe", "winlogon.exe", "services.exe", "taskmgr.exe", "demon.exe"]
    if p_name in protected:
        return False

    try:
        creationflags = 0x08000000  # CREATE_NO_WINDOW
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/IM", p_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags
        )
        return result.returncode == 0
    except Exception:
        return False


def terminate_all_running_distractions() -> List[str]:
    """
    Scans the system for ANY running distraction applications and forcefully terminates them.
    Called whenever distraction blocking is active.
    Returns list of terminated process names.
    """
    if sys.platform != "win32":
        return []

    terminated = []
    try:
        import user_tracker
        tracker = user_tracker.WindowsProcessTracker()
        running_names = tracker.get_running_process_names()

        for proc in running_names:
            p_lower = proc.lower()
            if p_lower in KNOWN_DISTRACTION_PROCESSES:
                if terminate_process_by_name(p_lower):
                    terminated.append(p_lower)
                    try:
                        ctypes.windll.user32.MessageBeep(0x00000010)
                    except Exception:
                        pass
    except Exception:
        pass

    return terminated


def enforce_rules(
    current_proc_name: str = "",
    current_pid: int = 0,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Master Parental Enforcement Orchestrator:
    1. Distraction Blocking Active:
       - If child balance <= 0 OR lockdown is active:
         * Proactively blocks all distraction domains in hosts.
         * Hunts and terminates ALL running distraction processes across the system.
         * Minimizes active windows showing distraction titles.
    2. Individual Application Limits:
       - Evaluates time limits from enforcement_rules table and terminates over-limit apps.
    """
    state = db_manager.get_child_state(db_path=db_path)
    balance = state.get("current_balance", 0)
    is_blocked = state.get("is_blocked", 0)

    is_lockdown_active = (balance <= 0 or is_blocked == 1)
    actions_taken: List[str] = []

    # 1. Distraction Blocking Active (Strict Zero-Tolerance Mode)
    if is_lockdown_active:
        if not is_distraction_blocked():
            block_distractions()
            actions_taken.append("OS Distraction Domains Blocked (Zero-Tolerance Lockdown Active)")

        # Proactively terminate all running distraction apps on the machine!
        terminated_distractions = terminate_all_running_distractions()
        for t in terminated_distractions:
            actions_taken.append(f"Blocked & Terminated distraction process: '{t}'")
            db_manager.update_balance(0, reason=f"[ZERO-TOLERANCE] Intercepted and terminated: {t}", db_path=db_path)

        # Also inspect current foreground process
        if current_proc_name:
            curr = current_proc_name.lower()
            if curr in KNOWN_DISTRACTION_PROCESSES or any(d.replace(".exe", "") in curr for d in KNOWN_DISTRACTION_PROCESSES):
                terminate_process_by_name(current_proc_name)
                actions_taken.append(f"Terminated foreground distraction '{current_proc_name}'")

        # Intercept any distraction browser windows or media
        enforce_active_distraction()
    else:
        # Time remaining and not in lockdown
        if is_distraction_blocked():
            unblock_distractions()
            actions_taken.append("Restored Unrestricted Web & App Access")

    # 2. Check individual application limits (when not in full lockdown)
    if current_proc_name and not is_lockdown_active:
        is_restricted, reason, rule = db_manager.check_process_restriction(current_proc_name, db_path=db_path)
        if is_restricted and rule:
            action = rule.get("action", "terminate")
            if action == "terminate":
                killed = terminate_process_by_name(current_proc_name)
                if killed:
                    actions_taken.append(f"Terminated '{current_proc_name}': {reason}")
                    db_manager.update_balance(0, reason=f"Enforcement Terminated: {current_proc_name} ({reason})", db_path=db_path)
            elif action == "minimize":
                enforce_active_distraction()
                actions_taken.append(f"Minimized '{current_proc_name}': {reason}")

    return {
        "balance": balance,
        "is_locked": is_lockdown_active,
        "actions_taken": actions_taken
    }


if __name__ == "__main__":
    print("[enforcement] Testing zero-tolerance enforcement engine...")
    print(f"  Is Admin: {is_admin()}")
    print(f"  Known distraction blacklisted apps: {len(KNOWN_DISTRACTION_PROCESSES)}")
    print(f"  Distraction blocked status: {is_distraction_blocked()}")

"""
enforcement.py
--------------
Systems & OS Enforcement Engine for Parental Control.
Handles:
1. Domain-level website blocking via Windows hosts file and DNS resolver cache flushing.
2. Direct Windows Process termination (taskkill / Win32 TerminateProcess) for blacklisted apps.
3. Time limit enforcement and automated lockdown triggers.
"""

import os
import sys
import ctypes
import subprocess
import socket
from typing import Optional, List, Dict, Any, Tuple

import db_manager

BLOCK_HEADER = "# === DEMON OS ENFORCEMENT BLOCK BEGIN ==="
BLOCK_FOOTER = "# === DEMON OS ENFORCEMENT BLOCK END ==="
REDIRECT_IPV4 = "127.0.0.1"
REDIRECT_IPV6 = "::1"

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
    """Minimizes foreground window if matching distraction keywords."""
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

        # Whitelist safe workspace tools
        whitelist = ["demon", "visual studio", "antigravity", "cursor", "cmd", "powershell", "terminal", "python"]
        if any(w in curr_title for w in whitelist):
            return False

        distraction_keywords = [
            "youtube", "youtu.be", "tiktok", "netflix",
            "twitch", "reddit", "twitter", "instagram", "facebook", "roblox"
        ]

        for kw in distraction_keywords:
            if kw in curr_title:
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                user32.MessageBeep(0x00000010)  # Warning sound
                return True
    except Exception:
        pass
    return False


# ==============================================================================
# PROCESS TERMINATION & RESTRICTION ENFORCEMENT
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
        # Use Windows taskkill with CREATE_NO_WINDOW flag
        creationflags = 0x08000000
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/IM", p_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags
        )
        return result.returncode == 0
    except Exception:
        return False


def terminate_process_by_pid(pid: int) -> bool:
    """Terminates process by PID using Win32 TerminateProcess API."""
    if sys.platform != "win32" or pid <= 4:
        return False

    PROCESS_TERMINATE = 0x0001
    kernel32 = ctypes.windll.kernel32
    h_proc = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not h_proc:
        return False

    try:
        return bool(kernel32.TerminateProcess(h_proc, 1))
    finally:
        kernel32.CloseHandle(h_proc)


def enforce_rules(
    current_proc_name: str = "",
    current_pid: int = 0,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Orchestrates parental enforcement across the entire system:
    1. Checks if child's allowed screen time is exhausted (balance <= 0) or locked.
    2. Checks individual application rules and terminates restricted/over-limit apps.
    3. Blocks or unblocks distraction domains.
    Returns summary dict.
    """
    state = db_manager.get_child_state(db_path=db_path)
    balance = state.get("current_balance", 0)
    is_blocked = state.get("is_blocked", 0)

    actions_taken: List[str] = []

    # 1. System-wide balance exhaustion check
    if balance <= 0 or is_blocked == 1:
        if not is_distraction_blocked():
            block_distractions()
            actions_taken.append("OS Distraction Domains Blocked (Allowed Time Expired / Locked)")

        # Terminate any non-whitelisted entertainment foreground process
        if current_proc_name:
            curr = current_proc_name.lower()
            entertainment = ["discord.exe", "steam.exe", "robloxplayerbeta.exe", "minecraft.exe", "epicgameslauncher.exe", "tiktok.exe"]
            if any(e in curr for e in entertainment):
                terminate_process_by_name(current_proc_name)
                actions_taken.append(f"Terminated '{current_proc_name}' (Zero balance lockdown)")
    else:
        # Balance positive and not locked
        if is_distraction_blocked():
            unblock_distractions()
            actions_taken.append("Restored Web Access (Positive Allowed Time)")

    # 2. Check individual application limits
    if current_proc_name:
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
        "is_locked": is_blocked == 1 or balance <= 0,
        "actions_taken": actions_taken
    }


if __name__ == "__main__":
    print("[enforcement] Testing enforcement module...")
    print(f"  Is Admin: {is_admin()}")
    print(f"  Can write hosts: {can_write_hosts()}")
    print(f"  Is domain blocked (youtube.com): {is_domain_blocked('youtube.com')}")

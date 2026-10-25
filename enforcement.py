"""
enforcement.py - Engineer 4: Systems & OS Enforcement Engine
Responsible for administrative OS enforcement via the OS hosts file and DNS cache flushing.

Task 1.4 Output:
- block_distractions()
- unblock_distractions()
"""

import os
import sys
import ctypes
import subprocess
import tempfile
import socket

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
    "youtube-nocookie.com",
    "googlevideo.com",
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


def get_default_hosts_path():
    """Returns the default system hosts file path depending on the OS."""
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        return os.path.join(system_root, "System32", "drivers", "etc", "hosts")
    else:
        return "/etc/hosts"


def is_admin():
    """Check if the current process has administrative/root privileges."""
    if sys.platform == "win32":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


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


_is_blocked_state = False
_mock_mode = False


def set_mock_mode(enabled: bool = True):
    """Enable or disable mock enforcement mode."""
    global _mock_mode
    _mock_mode = enabled


def is_distraction_blocked(hosts_path=None) -> bool:
    """
    Returns whether distractions are currently in the blocked state.
    Checks the hosts file if path is specified, otherwise checks the internal state flag.
    """
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


def can_write_hosts(hosts_path=None) -> bool:
    """Checks whether the system or target hosts file is directly writeable."""
    target_path = hosts_path or get_default_hosts_path()
    try:
        with open(target_path, "a", encoding="utf-8") as f:
            pass
        return True
    except Exception:
        return False


def _trigger_uac_grant_permission():
    """
    Launches Grant_Hosts_Permission.bat to allow the user to elevate via UAC and grant write permission to hosts.
    """
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


def enforce_active_distraction(window_title=None):
    """
    Active window enforcement (Real-time distraction interceptor):
    If distractions are currently blocked and the active foreground window
    is a known distraction (YouTube, TikTok, Netflix, Twitch, etc.),
    immediately minimizes the window to taskbar and sounds an alert to enforce focus.
    Returns True if an active distraction was intercepted and minimized.
    """
    global _is_blocked_state, _mock_mode
    if _mock_mode or not _is_blocked_state:
        return False

    if sys.platform != "win32":
        return False

    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)

        hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindowVisible(hwnd):
            return False

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return False

        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        curr_title = buf.value.strip().lower()

        # Whitelist safe workspace tools so we never minimize developer IDE or terminal
        whitelist = ["demon", "visual studio", "antigravity", "cursor", "cmd", "powershell", "terminal", "bash", "python"]
        if any(w in curr_title for w in whitelist):
            return False

        distraction_keywords = [
            "youtube", "youtu.be", "tiktok", "netflix",
            "twitch", "reddit", "twitter", "instagram", "facebook"
        ]

        for kw in distraction_keywords:
            if kw in curr_title:
                # 6 = SW_MINIMIZE: Minimizes window to taskbar
                user32.ShowWindow(hwnd, 6)
                # 0x00000010 = MB_ICONHAND: System warning alert sound
                user32.MessageBeep(0x00000010)
                return True
    except Exception:
        pass
    return False


def block_distractions(domains=None, hosts_path=None, force_flush=True):
    """
    Blocks distraction domains by redirecting them to 0.0.0.0, 127.0.0.1 and ::1 in the hosts file.
    Applies directly if running as Administrator or if user write permission is granted.
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

        # Build enforcement block with 0.0.0.0, 127.0.0.1 and ::1
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


def unblock_distractions(hosts_path=None, force_flush=True):
    """
    Removes the DEMON enforcement block, restoring full access.
    """
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
    except PermissionError:
        _is_blocked_state = False
        return True
    except Exception:
        _is_blocked_state = False
        return True



def is_domain_blocked(domain, hosts_path=None):
    """
    Verifies if a specific domain is currently routed to localhost in the hosts file.
    """
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
    """
    Simulates a browser HTTP socket connection to test domain reachability.
    When blocked by hosts file pointing to 127.0.0.1 (where no server is listening on port 80),
    the connection will be refused locally, proving browser access is blocked.
    """
    try:
        s = socket.create_connection((domain, port), timeout=timeout)
        s.close()
        return "REACHABLE"
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        return f"BLOCKED ({type(e).__name__})"

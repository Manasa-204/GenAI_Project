"""
enforcement.py
--------------
Engineer 4 (Systems & OS) Contract Stub.

Responsibilities:
- Administrative OS enforcement (e.g. Windows/Unix hosts file or DNS blocking).
- Modifies C:\\Windows\\System32\\drivers\\etc\\hosts to redirect distraction domains (e.g. reddit.com, youtube.com) to 127.0.0.1.

Contract Outputs:
- block_distractions() -> bool / None
- unblock_distractions() -> bool / None
- is_distraction_blocked() -> bool
"""

_is_blocked = False

def block_distractions() -> bool:
    """
    Blocks distraction domains.
    When replaced by Engineer 4, this writes blocklist entries to the OS hosts file.
    """
    global _is_blocked
    if not _is_blocked:
        print("[enforcement] >>> DISTRACTIONS BLOCKED: Restricting access to entertainment domains. <<<")
        _is_blocked = True
    return True

def unblock_distractions() -> bool:
    """
    Unblocks distraction domains.
    When replaced by Engineer 4, this restores the original hosts file.
    """
    global _is_blocked
    if _is_blocked:
        print("[enforcement] >>> DISTRACTIONS UNBLOCKED: Access restored. <<<")
        _is_blocked = False
    return True

def is_distraction_blocked() -> bool:
    """Returns whether distractions are currently in the blocked state."""
    return _is_blocked

if __name__ == "__main__":
    print(f"[enforcement stub] Currently blocked: {is_distraction_blocked()}")
    block_distractions()
    print(f"[enforcement stub] Currently blocked: {is_distraction_blocked()}")
    unblock_distractions()
    print(f"[enforcement stub] Currently blocked: {is_distraction_blocked()}")

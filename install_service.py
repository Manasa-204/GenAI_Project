r"""
install_service.py
------------------
Automated Windows Task Scheduler installer and manager for Demon Background Tracker.
Configures:
- Run 'At Startup' (/sc ONSTART)
- Run 'Whether user is logged on or not' (/ru 'NT AUTHORITY\SYSTEM')
- Run with 'Highest Privileges' (/rl HIGHEST - Administrator)

Usage:
  python install_service.py --install    # Creates & registers the task
  python install_service.py --start      # Immediately starts the task
  python install_service.py --status     # Displays task run status
  python install_service.py --stop       # Stops the task
  python install_service.py --uninstall  # Deletes task from Task Scheduler
"""

import sys
import os
import ctypes
import subprocess
import argparse

TASK_NAME = "DemonBackgroundTracker"


def is_admin() -> bool:
    """Checks if running with Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate():
    """Relaunches the current script with Administrator UAC prompt."""
    if not is_admin():
        print("[!] Administrator privileges required. Requesting UAC elevation...")
        params = " ".join([f'"{arg}"' for arg in sys.argv])
        hinstance = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            params,
            None,
            1  # SW_SHOWNORMAL
        )
        sys.exit(0)


def get_target_executable() -> str:
    """Resolves path to compiled Demon.exe or fallback to pythonw.exe main.py."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir_exe = os.path.join(base_dir, "dist", "Demon", "Demon.exe")
    dist_single_exe = os.path.join(base_dir, "dist", "Demon.exe")

    if os.path.exists(dist_dir_exe):
        return f'"{dist_dir_exe}"'
    elif os.path.exists(dist_single_exe):
        return f'"{dist_single_exe}"'

    # Fallback to pythonw.exe (headless python runner) or python.exe
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    runner = pythonw if os.path.exists(pythonw) else sys.executable
    main_py = os.path.join(base_dir, "main.py")
    return f'"{runner}" "{main_py}"'


def install_task():
    elevate()
    target_cmd = get_target_executable()
    print("=" * 65)
    print(" REGISTERING DEMON BACKGROUND TRACKER IN WINDOWS TASK SCHEDULER")
    print("=" * 65)
    print(f" Task Name   : {TASK_NAME}")
    print(f" Target Exec : {target_cmd}")
    print(" Trigger     : At Startup (Boot)")
    print(" User Context: NT AUTHORITY\\SYSTEM (Whether logged on or not)")
    print(" Privileges  : HIGHEST (Administrator)")
    print("-" * 65)

    cmd = [
        "schtasks",
        "/create",
        "/tn", TASK_NAME,
        "/tr", target_cmd,
        "/sc", "ONSTART",
        "/ru", "NT AUTHORITY\\SYSTEM",
        "/rl", "HIGHEST",
        "/f"
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0:
        print("[SUCCESS] Windows Task successfully scheduled!")
        print(result.stdout.strip())
        print("\nStarting task...")
        start_task()
    else:
        print("[ERROR] Failed to schedule task:")
        print(result.stderr.strip())


def start_task():
    elevate()
    res = subprocess.run(["schtasks", "/run", "/tn", TASK_NAME], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        print(f"[OK] {TASK_NAME} triggered to run.")
    else:
        print(f"[!] Warning: {res.stderr.strip()}")


def stop_task():
    elevate()
    res = subprocess.run(["schtasks", "/end", "/tn", TASK_NAME], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(res.stdout.strip() if res.returncode == 0 else res.stderr.strip())


def uninstall_task():
    elevate()
    res = subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        print(f"[SUCCESS] {TASK_NAME} removed from Windows Task Scheduler.")
    else:
        print(f"[ERROR] Could not delete task: {res.stderr.strip()}")


def get_task_status():
    res = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST", "/v"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        print(res.stdout)
    else:
        print(f"Task '{TASK_NAME}' is NOT registered in Task Scheduler.")


def main():
    parser = argparse.ArgumentParser(description="Demon Task Scheduler Service Manager")
    parser.add_argument("--install", action="store_true", help="Install and start Windows Scheduled Task")
    parser.add_argument("--uninstall", action="store_true", help="Remove task from Task Scheduler")
    parser.add_argument("--start", action="store_true", help="Start the background task now")
    parser.add_argument("--stop", action="store_true", help="End running background task")
    parser.add_argument("--status", action="store_true", help="Query task configuration and status")
    args = parser.parse_args()

    if args.uninstall:
        uninstall_task()
    elif args.start:
        start_task()
    elif args.stop:
        stop_task()
    elif args.status:
        get_task_status()
    else:
        install_task()


if __name__ == "__main__":
    main()

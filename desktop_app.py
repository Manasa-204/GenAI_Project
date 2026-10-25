"""
desktop_app.py - Standalone Desktop Launcher for Demon Study Monitor
Initializes the background web dashboard and launches a native, borderless desktop window via PyWebView.
Falls back to the system default browser if native webview window cannot be displayed.
"""

import os
import sys
import time
import threading
import webbrowser
import web_dashboard
import main

# Ensure graceful cleanup on exit
import atexit
atexit.register(main.cleanup_on_exit)


def start_backend():
    """Starts the Demon web dashboard and autonomous monitor threads."""
    try:
        web_dashboard.run_server(port=8000)
    except Exception as e:
        print(f"[DesktopApp] Server error: {e}", file=sys.stderr)


def main_desktop():
    # 1. Start Web Dashboard server in a background daemon thread
    server_thread = threading.Thread(target=start_backend, daemon=True)
    server_thread.start()

    # Wait briefly for socket to bind
    time.sleep(1.2)

    url = "http://127.0.0.1:8000"

    # 2. Try launching via PyWebView native window
    use_webview = True
    try:
        import webview
        window = webview.create_window(
            title="Demon - AI Study Monitor & Focus Enforcement",
            url=url,
            width=1280,
            height=850,
            min_size=(960, 600),
            background_color="#0f172a",
            text_select=False
        )
        webview.start(gui="edgechromium", debug=False)
    except Exception as e:
        print(f"[DesktopApp] PyWebView native window unavailable ({e}). Falling back to browser...", file=sys.stderr)
        use_webview = False

    # 3. Fallback: launch in default system browser and keep process alive
    if not use_webview:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1.0)
        except (KeyboardInterrupt, SystemExit):
            pass


if __name__ == "__main__":
    main_desktop()

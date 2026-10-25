"""
demo_checkpoint_1.py - Live Interactive Demo for Integration Checkpoint 1
Demonstrates:
- Engineer 2: MediaPipe Face Mesh, EAR (Sleep), and Head Pose (Away)
- Engineer 3: Active Window Scraping & Ollama Semantic Classification
- Engineer 4: OS Hosts File Enforcement (Block / Unblock)
"""

import sys
import time
import argparse
import vision_pipeline as eng2
import semantic_pipeline as eng3
import enforcement as eng4


def demo_vision(duration=10):
    print("\n" + "=" * 60)
    print(" [Eng 2] Computer Vision Pipeline Live Feed")
    print("=" * 60)
    print(f"Opening webcam feed for {duration} seconds...")
    print("Try: 1) Closing your eyes for > 2 seconds (Trigger IDLE/Sleep)")
    print("     2) Looking away from screen or leaving camera view (Trigger IDLE/Away)")
    print("     3) Looking at screen with eyes open (Trigger ACTIVE)\n")

    pipeline = eng2.VisionPipeline(
        ear_threshold=0.20,
        sleep_duration_threshold=2.0,
        away_duration_threshold=2.0
    )

    start_time = time.time()
    try:
        while time.time() - start_time < duration:
            frame = pipeline._get_camera_frame()
            if frame is None:
                print("  [Warning] No camera frame captured.")
                time.sleep(0.5)
                continue

            result = pipeline.process_frame(frame)
            status_indicator = "[ACTIVE]" if result["state"] == "ACTIVE" else "[IDLE]"
            pitch, yaw, roll = result["head_pose"]

            print(
                f"\r{status_indicator:8s} | Face: {result['face_detected']!s:5s} | "
                f"EAR: {result['ear']:.3f} (Closed: {result['eyes_closed']!s:5s}) | "
                f"Yaw: {yaw:5.1f}° | SleepDur: {result['sleep_duration']:.1f}s | "
                f"State: {result['state']}",
                end="",
                flush=True
            )
            time.sleep(0.1)
    finally:
        pipeline.close()
    print("\n\nVision pipeline demo completed.")


def demo_semantic():
    print("\n" + "=" * 60)
    print(" [Eng 3] NLP & App Integration (Ollama Semantic Pipeline)")
    print("=" * 60)

    # 1. Active window scraping
    active_window = eng3.get_active_window_title()
    print(f"Scraped Foreground Window: \"{active_window}\"")
    live_state = eng3.get_semantic_state(window_title=active_window)
    print(f"Ollama Live Classification: -> {live_state}\n")

    # 2. Checkpoint Benchmark Titles
    benchmarks = [
        "YouTube - Calculus Tutorial",
        "YouTube - Meme Compilation",
        "MIT 18.06 Linear Algebra Spring 2005 - YouTube",
        "Reddit: r/dankmemes - Endless scrolling",
        "Visual Studio Code - Demon Project Workspace",
        "Twitch - Grand Theft Auto V Roleplay Stream"
    ]

    print("Benchmarking Ollama on Test Window Titles:")
    for title in benchmarks:
        state = eng3.get_semantic_state(window_title=title)
        print(f"  • \"{title}\" -> {state}")


def demo_enforcement():
    print("\n" + "=" * 60)
    print(" [Eng 4] OS Enforcement Engine (Hosts File & DNS)")
    print("=" * 60)
    print(f"Running as Administrator: {eng4.is_admin()}")
    print(f"Default Hosts Path: {eng4.get_default_hosts_path()}")

    # Use a safe simulated hosts file for demonstration
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as f:
        f.write("# OS Hosts Mock\n127.0.0.1 localhost\n")
        mock_path = f.name

    try:
        print("\n1. Applying block_distractions()...")
        blocked = eng4.block_distractions(hosts_path=mock_path, force_flush=False)
        print(f"   Successfully blocked {len(blocked)} distraction domains.")
        print(f"   Is youtube.com blocked? {eng4.is_domain_blocked('youtube.com', hosts_path=mock_path)}")
        print(f"   Is reddit.com blocked?  {eng4.is_domain_blocked('reddit.com', hosts_path=mock_path)}")

        print("\n2. Applying unblock_distractions()...")
        eng4.unblock_distractions(hosts_path=mock_path, force_flush=False)
        print("   Successfully unblocked distractions.")
        print(f"   Is youtube.com blocked? {eng4.is_domain_blocked('youtube.com', hosts_path=mock_path)}")
        print(f"   Is reddit.com blocked?  {eng4.is_domain_blocked('reddit.com', hosts_path=mock_path)}")
    finally:
        import os
        if os.path.exists(mock_path):
            os.remove(mock_path)


def main():
    parser = argparse.ArgumentParser(description="Demon Integration Checkpoint 1 Demo")
    parser.add_argument("--module", choices=["all", "vision", "semantic", "enforcement"], default="all")
    args = parser.parse_args()

    if args.module in ("all", "semantic"):
        demo_semantic()
    if args.module in ("all", "enforcement"):
        demo_enforcement()
    if args.module in ("all", "vision"):
        demo_vision(duration=5)


if __name__ == "__main__":
    main()

"""
vision_pipeline.py
------------------
Engineer 2 (Computer Vision) Contract Stub.

Responsibilities:
- Reads webcam feed using OpenCV / MediaPipe Face Mesh.
- Calculates Eye Aspect Ratio (EAR) for sleep detection.
- Estimates head pose for user absence/distraction.

Contract Output:
- get_vision_state() -> returns "ACTIVE" or "IDLE"
"""

# Default state used when running in stub/mock mode
_current_vision_state = "ACTIVE"

def set_mock_vision_state(state: str) -> None:
    """Helper for testing: sets the state returned by get_vision_state()."""
    global _current_vision_state
    if state not in ("ACTIVE", "IDLE"):
        raise ValueError("Vision state must be either 'ACTIVE' or 'IDLE'")
    _current_vision_state = state

def get_vision_state() -> str:
    """
    Returns the physical state of the user.
    - "ACTIVE": User is present, looking at the screen with eyes open.
    - "IDLE": User is away or eyes are closed (sleeping/nodding off).
    """
    return _current_vision_state

if __name__ == "__main__":
    print(f"[vision_pipeline stub] Current state: {get_vision_state()}")

"""
semantic_pipeline.py
--------------------
Engineer 3 (NLP & App Integration) Contract Stub.

Responsibilities:
- Reads active window titles via pygetwindow.
- Prompts local Ollama SLM (e.g. Llama 3) to classify window content.

Contract Output:
- get_semantic_state() -> returns "EDUCATIONAL" or "DISTRACTION"
"""

# Default state used when running in stub/mock mode
_current_semantic_state = "EDUCATIONAL"

def set_mock_semantic_state(state: str) -> None:
    """Helper for testing: sets the state returned by get_semantic_state()."""
    global _current_semantic_state
    if state not in ("EDUCATIONAL", "DISTRACTION"):
        raise ValueError("Semantic state must be either 'EDUCATIONAL' or 'DISTRACTION'")
    _current_semantic_state = state

def get_semantic_state() -> str:
    """
    Returns the digital/contextual state of the active window.
    - "EDUCATIONAL": Study materials, research papers, Wikipedia, docs, IDEs, etc.
    - "DISTRACTION": Social media, entertainment, gaming, etc.
    """
    return _current_semantic_state

if __name__ == "__main__":
    print(f"[semantic_pipeline stub] Current state: {get_semantic_state()}")

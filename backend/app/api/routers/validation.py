"""Validation endpoint — runs the test suite and returns results.

Single endpoint: POST /api/v1/validation/run
Returns the test report as JSON.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()

# ── State — simple in-memory (no DB needed) ─────────────────────────

_state = {
    "status": "idle",  # idle | running | success | failed
    "started_at": None,
    "finished_at": None,
    "duration_ms": 0,
    "report": None,
}
_lock = threading.Lock()


def _run_validation():
    """Run the test suite in a background thread."""
    global _state

    # Ensure backend is importable
    backend_path = str(Path(__file__).resolve().parent.parent.parent)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    t0 = time.monotonic()
    try:
        from tests.test_extraction_validation import run_all_tests
        report = run_all_tests()

        with _lock:
            _state["status"] = "success" if report["success"] else "failed"
            _state["report"] = report
    except Exception as exc:
        with _lock:
            _state["status"] = "failed"
            _state["report"] = {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 0,
                "success": False,
                "details": [{"name": "runner", "status": "error", "error": str(exc)[:500]}],
            }
    finally:
        with _lock:
            _state["finished_at"] = datetime.now(timezone.utc).isoformat()
            _state["duration_ms"] = int((time.monotonic() - t0) * 1000)


@router.post("/validation/run")
def trigger_validation() -> dict[str, Any]:
    """Trigger the validation suite.

    If already running, returns current state.
    Otherwise starts a background thread and returns immediately.
    """
    with _lock:
        if _state["status"] == "running":
            return dict(_state)

        _state["status"] = "running"
        _state["started_at"] = datetime.now(timezone.utc).isoformat()
        _state["finished_at"] = None
        _state["duration_ms"] = 0
        _state["report"] = None

    thread = threading.Thread(target=_run_validation, daemon=True)
    thread.start()

    return dict(_state)


@router.get("/validation/status")
def get_validation_status() -> dict[str, Any]:
    """Get current validation state and report."""
    with _lock:
        return dict(_state)

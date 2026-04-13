"""Write structured result files for a batch run.

Outputs:
    all_results.json           — every company with QA + tiering fields
    ready_for_positioning.json — tier_1 companies (position_now)
    ready_for_review.json      — tier_2 companies (inspect_human)
    needs_recollection.json    — tier_3 companies (collect_more)
    excluded.json              — tier_4 companies (exclude)
    run_summary.json           — aggregate counts by tier/state/qa
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_results(
    results: list[dict[str, Any]],
    output_dir: Path,
    started_at: datetime,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    finished_at = datetime.now(timezone.utc)
    duration = (finished_at - started_at).total_seconds()

    # Partition by operational_state (new gate) for primary outputs
    positioning = [r for r in results if r.get("operational_state") == "position_now"]
    review = [r for r in results if r.get("operational_state") == "inspect_human"]
    recollect = [r for r in results if r.get("operational_state") == "collect_more"]
    excluded = [r for r in results if r.get("operational_state") == "exclude"]
    errors = [r for r in results if r.get("error")]

    # Build summary using the operational state mapper
    try:
        import sys
        _BACKEND = str(Path(__file__).resolve().parent.parent.parent / "backend")
        if _BACKEND not in sys.path:
            sys.path.insert(0, _BACKEND)
        from app.services.operational_state_mapper import build_run_summary
        summary = build_run_summary(
            results,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
        )
        summary["duration_seconds"] = round(duration, 1)
    except ImportError:
        # Fallback summary if backend not available (e.g., writing raw results)
        summary = _legacy_summary(results, started_at, finished_at, duration)

    def _write(name: str, data: Any) -> None:
        p = output_dir / name
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    _write("all_results.json", results)
    _write("ready_for_positioning.json", positioning)
    _write("ready_for_review.json", review)
    _write("needs_recollection.json", recollect)
    _write("excluded.json", excluded)
    _write("run_summary.json", summary)

    return output_dir


def _legacy_summary(
    results: list[dict[str, Any]],
    started_at: datetime,
    finished_at: datetime,
    duration: float,
) -> dict[str, Any]:
    """Fallback summary when QA/tiering fields are not present."""
    from collections import Counter

    status_counts = Counter(r.get("status", "unknown") for r in results)
    return {
        "total_companies": len(results),
        "ready_for_review": status_counts.get("ready_for_review", 0),
        "needs_recollection": status_counts.get("needs_recollection", 0),
        "excluded": status_counts.get("excluded", 0),
        "collected": status_counts.get("collected", 0),
        "errors": sum(1 for r in results if r.get("error")),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration, 1),
        "note": "Legacy summary — QA/tiering fields not applied. Run with --qa to enable.",
    }


def load_progress(state_file: Path) -> set[str]:
    if not state_file.exists():
        return set()
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return set(data.get("done_domains", []))
    except Exception:
        return set()


def save_progress(state_file: Path, done_domains: set[str]) -> None:
    state_file.write_text(
        json.dumps({"done_domains": sorted(done_domains)}, indent=2),
        encoding="utf-8",
    )

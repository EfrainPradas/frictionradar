"""Deterministic status assignment based on evaluation evidence."""

from __future__ import annotations

from typing import Any

# Canonical statuses
PENDING = "pending"
COLLECTED = "collected"
NEEDS_RECOLLECTION = "needs_recollection"
READY_FOR_REVIEW = "ready_for_review"
EXCLUDED = "excluded"
FINALIZED = "finalized"


def assign_status(
    signals_count: int,
    evaluation: dict[str, Any] | None,
    company_type: str | None = None,
    error: str | None = None,
) -> tuple[str, list[str]]:
    """Return (status, notes) based on evidence quality.

    Rules are deterministic and follow the spec priority:
    1. excluded  — invalid/broken
    2. needs_recollection — 0 signals or low extraction
    3. collected — some evidence but not review-worthy
    4. ready_for_review — meaningful evidence present
    """
    notes: list[str] = []

    if error:
        notes.append(f"Processing error: {error}")
        return NEEDS_RECOLLECTION, notes

    kpis = (evaluation or {}).get("kpis", {})
    evidence = (evaluation or {}).get("evidence", {})
    diag = (evaluation or {}).get("diagnostic_state", "")
    extraction = kpis.get("extraction_coverage", "low")
    hiring_pressure = kpis.get("hiring_pressure", "low")
    pain_clarity = kpis.get("pain_clarity", "low")
    positioning = kpis.get("positioning_readiness", "low")

    # ── needs_recollection ──────────────────────────────────────────
    if signals_count == 0:
        notes.append("No signals captured")
        return NEEDS_RECOLLECTION, notes

    if extraction == "low":
        notes.append("Extraction coverage is low")
        return NEEDS_RECOLLECTION, notes

    open_count = evidence.get("open_positions_count", 0)
    visible_areas = evidence.get("visible_hiring_areas", 0)
    if signals_count < 3 and open_count == 0 and visible_areas == 0:
        notes.append("Very weak evidence: few signals, no hiring breadth")
        return NEEDS_RECOLLECTION, notes

    # ── ready_for_review ────────────────────────────────────────────
    is_meaningful = (
        hiring_pressure in ("high", "moderate")
        or pain_clarity in ("high", "moderate")
        or positioning in ("high", "moderate")
    )

    if extraction in ("moderate", "high") and is_meaningful:
        if diag == "broad_hiring_pattern_detected":
            notes.append("Broad hiring demand detected")
            notes.append("Dominant pain not yet isolated")
        elif diag in ("specific_pain_emerging", "specific_pain_identified"):
            notes.append(f"Diagnostic: {diag.replace('_', ' ')}")
        elif diag == "ready_for_positioning":
            notes.append("Ready for targeted positioning")

        if company_type == "job_market_intermediary":
            notes.append("Classified as job-market intermediary — verify before targeting")

        return READY_FOR_REVIEW, notes

    # ── collected ───────────────────────────────────────────────────
    notes.append("Some evidence collected but not yet review-ready")
    if hiring_pressure == "low":
        notes.append("Hiring pressure is low")
    return COLLECTED, notes

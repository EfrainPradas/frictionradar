"""
Commercial Pipeline Service — manages the internal review workflow.

Handles:
  - Intake: promote companies from positioning engine to pipeline
  - Stage transitions with audit logging
  - Evidence snapshot capture
  - Pipeline queries and statistics
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.models.commercial_pipeline import PipelineEntry, PipelineEvent
from app.services.positioning_engine import positioning_engine, PositioningOutput
from app.core.logging import get_logger

logger = get_logger(__name__)

# Valid stage transitions
VALID_TRANSITIONS = {
    "radar": {"reviewing", "parked", "rejected"},
    "reviewing": {"approved", "parked", "rejected", "radar"},
    "approved": {"preparing", "parked", "rejected", "reviewing"},
    "preparing": {"ready", "parked", "reviewing"},
    "ready": {"parked", "preparing"},
    "parked": {"radar", "reviewing", "rejected"},
    "rejected": {"radar"},  # Allow re-opening
}

STAGE_ORDER = {
    "radar": 0, "reviewing": 1, "approved": 2,
    "preparing": 3, "ready": 4, "parked": -1, "rejected": -2,
}


def intake_company(
    db: Session,
    company_id: UUID,
    source: str = "manual",
    batch_run_id: Optional[str] = None,
    priority: Optional[int] = None,
) -> PipelineEntry:
    """Add a company to the pipeline. Captures evidence snapshot.

    Returns existing entry if company is already in pipeline.
    """
    existing = (
        db.query(PipelineEntry)
        .filter(PipelineEntry.company_id == company_id)
        .first()
    )
    if existing:
        return existing

    # Generate positioning to capture snapshot
    positioning = positioning_engine.generate(company_id=company_id, db=db)

    # Determine priority if not provided
    if priority is None:
        if positioning.confidence_band == "high":
            priority = 1
        elif positioning.confidence_band == "moderate":
            priority = 2
        else:
            priority = 3

    entry = PipelineEntry(
        company_id=company_id,
        stage="radar",
        priority=priority,
        diagnostic_state_at_intake=positioning.generated_from_ds,
        confidence_band_at_intake=positioning.confidence_band,
        dominant_function=positioning.dominant_function,
        classified_roles_count=positioning.evidence_depth.get("classified_roles", 0),
        jds_count=positioning.evidence_depth.get("jds_extracted", 0),
        positioning_eligible=positioning.eligible,
        candidate_archetype=positioning.candidate_archetype if positioning.eligible else None,
        positioning_angle=positioning.positioning_angle if positioning.eligible else None,
        intake_source=source,
        batch_run_id=batch_run_id,
    )
    db.add(entry)
    db.flush()

    # Log intake event
    _log_event(
        db, entry.id,
        event_type="intake",
        to_stage="radar",
        actor="system",
        note=f"Intake from {source}. Eligible: {positioning.eligible}, band: {positioning.confidence_band}",
        metadata={
            "evidence_depth": positioning.evidence_depth,
            "gate_passed": positioning.gate_passed,
        },
    )

    db.commit()
    logger.info(f"Pipeline intake: {positioning.company_name} -> radar (priority {priority})")
    return entry


def transition_stage(
    db: Session,
    entry_id: UUID,
    to_stage: str,
    actor: str,
    note: Optional[str] = None,
    review_decision: Optional[str] = None,
) -> PipelineEntry:
    """Move a pipeline entry to a new stage with audit logging."""
    entry = db.query(PipelineEntry).filter(PipelineEntry.id == entry_id).first()
    if not entry:
        raise ValueError(f"Pipeline entry {entry_id} not found")

    current = entry.stage
    valid_next = VALID_TRANSITIONS.get(current, set())

    if to_stage not in valid_next:
        raise ValueError(
            f"Invalid transition: {current} -> {to_stage}. "
            f"Valid: {valid_next}"
        )

    from_stage = entry.stage
    entry.stage = to_stage
    entry.updated_at = datetime.now(timezone.utc)

    if review_decision:
        entry.review_decision = review_decision
        entry.reviewer = actor
        entry.reviewed_at = datetime.now(timezone.utc)

    if note:
        entry.review_notes = note

    _log_event(
        db, entry.id,
        event_type="stage_change",
        from_stage=from_stage,
        to_stage=to_stage,
        actor=actor,
        note=note,
    )

    db.commit()
    logger.info(f"Pipeline transition: {entry.company_id} {from_stage} -> {to_stage} by {actor}")
    return entry


def add_note(
    db: Session,
    entry_id: UUID,
    note: str,
    actor: str,
) -> PipelineEvent:
    """Add a note to a pipeline entry without changing stage."""
    entry = db.query(PipelineEntry).filter(PipelineEntry.id == entry_id).first()
    if not entry:
        raise ValueError(f"Pipeline entry {entry_id} not found")

    event = _log_event(
        db, entry.id,
        event_type="note",
        actor=actor,
        note=note,
    )
    db.commit()
    return event


def update_positioning(
    db: Session,
    entry_id: UUID,
    message_angle: Optional[str] = None,
    target_profile_notes: Optional[str] = None,
    actor: str = "system",
) -> PipelineEntry:
    """Update positioning details on a pipeline entry."""
    entry = db.query(PipelineEntry).filter(PipelineEntry.id == entry_id).first()
    if not entry:
        raise ValueError(f"Pipeline entry {entry_id} not found")

    if message_angle is not None:
        entry.message_angle_draft = message_angle
    if target_profile_notes is not None:
        entry.target_profile_notes = target_profile_notes

    entry.updated_at = datetime.now(timezone.utc)

    _log_event(
        db, entry.id,
        event_type="positioning_update",
        actor=actor,
        note="Positioning details updated",
    )

    db.commit()
    return entry


def batch_intake(
    db: Session,
    min_classified_roles: int = 3,
    eligible_only: bool = True,
    source: str = "batch_intake",
    limit: int = 50,
) -> dict:
    """Intake multiple companies from positioning engine results.

    Selects companies not yet in pipeline that meet evidence criteria.
    """
    from sqlalchemy import text as sqtext

    # Get companies with enough roles, not already in pipeline
    existing_ids = {
        row[0] for row in
        db.query(PipelineEntry.company_id).all()
    }

    # Find candidates
    role_counts = (
        db.query(
            CompanyJobRole.company_id,
            func.count(CompanyJobRole.id).label("cnt"),
        )
        .filter(
            CompanyJobRole.functional_area.isnot(None),
            ~CompanyJobRole.functional_area.in_(["junk", "unknown"]),
        )
        .group_by(CompanyJobRole.company_id)
        .having(func.count(CompanyJobRole.id) >= min_classified_roles)
        .all()
    )

    candidates = [
        (cid, cnt) for cid, cnt in role_counts
        if cid not in existing_ids
    ]

    # Sort by role count descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    candidates = candidates[:limit]

    intaken = 0
    skipped = 0

    for cid, cnt in candidates:
        positioning = positioning_engine.generate(company_id=cid, db=db)

        if eligible_only and not positioning.eligible:
            skipped += 1
            continue

        intake_company(db, cid, source=source)
        intaken += 1

    return {
        "candidates_found": len(candidates),
        "intaken": intaken,
        "skipped_ineligible": skipped,
        "already_in_pipeline": len(existing_ids),
    }


def get_pipeline_stats(db: Session) -> dict:
    """Get pipeline statistics by stage."""
    stages = (
        db.query(PipelineEntry.stage, func.count(PipelineEntry.id))
        .group_by(PipelineEntry.stage)
        .all()
    )

    priorities = (
        db.query(PipelineEntry.priority, func.count(PipelineEntry.id))
        .filter(PipelineEntry.stage.notin_(["rejected", "parked"]))
        .group_by(PipelineEntry.priority)
        .all()
    )

    return {
        "by_stage": {stage: cnt for stage, cnt in stages},
        "by_priority": {f"p{p}": cnt for p, cnt in priorities if p},
        "total": sum(cnt for _, cnt in stages),
        "active": sum(cnt for s, cnt in stages if s not in ("rejected", "parked")),
    }


def get_entries_by_stage(
    db: Session,
    stage: str,
    limit: int = 50,
) -> list[PipelineEntry]:
    """Get pipeline entries for a specific stage, ordered by priority."""
    return (
        db.query(PipelineEntry)
        .filter(PipelineEntry.stage == stage)
        .order_by(PipelineEntry.priority.asc(), PipelineEntry.created_at.desc())
        .limit(limit)
        .all()
    )


def get_entry_with_events(
    db: Session,
    entry_id: UUID,
) -> dict:
    """Get a pipeline entry with its full event history."""
    entry = db.query(PipelineEntry).filter(PipelineEntry.id == entry_id).first()
    if not entry:
        return None

    events = (
        db.query(PipelineEvent)
        .filter(PipelineEvent.pipeline_entry_id == entry_id)
        .order_by(PipelineEvent.created_at.desc())
        .all()
    )

    return {
        "entry": entry,
        "events": events,
    }


# ── Internal helpers ─────────────────────────────────────────────────

def _log_event(
    db: Session,
    pipeline_entry_id: UUID,
    event_type: str,
    from_stage: Optional[str] = None,
    to_stage: Optional[str] = None,
    actor: Optional[str] = None,
    note: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> PipelineEvent:
    event = PipelineEvent(
        pipeline_entry_id=pipeline_entry_id,
        event_type=event_type,
        from_stage=from_stage,
        to_stage=to_stage,
        actor=actor,
        note=note,
        metadata_json=metadata,
    )
    db.add(event)
    return event

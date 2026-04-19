"""
Commercial Pipeline API — internal review workflow endpoints.

These endpoints are for the NovaWork team to manage the company
review pipeline. NOT for external/candidate use.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from app.db.session import get_db
from app.services import commercial_pipeline_service as pipeline_svc

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ── Request models ───────────────────────────────────────────────────

class IntakeRequest(BaseModel):
    company_id: UUID
    priority: Optional[int] = None
    source: str = "manual"


class BatchIntakeRequest(BaseModel):
    min_classified_roles: int = 3
    eligible_only: bool = True
    limit: int = 50


class TransitionRequest(BaseModel):
    to_stage: str
    actor: str
    note: Optional[str] = None
    review_decision: Optional[str] = None


class NoteRequest(BaseModel):
    note: str
    actor: str


class PositioningUpdateRequest(BaseModel):
    message_angle: Optional[str] = None
    target_profile_notes: Optional[str] = None
    actor: str = "system"


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/stats")
def pipeline_stats(db: Session = Depends(get_db)):
    """Get pipeline statistics by stage and priority."""
    return pipeline_svc.get_pipeline_stats(db)


@router.post("/intake")
def intake_company(req: IntakeRequest, db: Session = Depends(get_db)):
    """Add a single company to the pipeline."""
    entry = pipeline_svc.intake_company(
        db, req.company_id, source=req.source, priority=req.priority
    )
    return _entry_to_dict(entry)


@router.post("/batch-intake")
def batch_intake(req: BatchIntakeRequest, db: Session = Depends(get_db)):
    """Intake multiple eligible companies into the pipeline."""
    result = pipeline_svc.batch_intake(
        db,
        min_classified_roles=req.min_classified_roles,
        eligible_only=req.eligible_only,
        limit=req.limit,
    )
    return result


@router.get("/stage/{stage}")
def list_by_stage(stage: str, limit: int = 50, db: Session = Depends(get_db)):
    """List pipeline entries for a specific stage."""
    entries = pipeline_svc.get_entries_by_stage(db, stage, limit)
    return [_entry_to_dict(e) for e in entries]


@router.get("/entries/{entry_id}")
def get_entry(entry_id: UUID, db: Session = Depends(get_db)):
    """Get a pipeline entry with its full event history."""
    result = pipeline_svc.get_entry_with_events(db, entry_id)
    if not result:
        raise HTTPException(status_code=404, detail="Pipeline entry not found")

    entry = result["entry"]
    events = result["events"]

    return {
        **_entry_to_dict(entry),
        "events": [
            {
                "id": str(ev.id),
                "event_type": ev.event_type,
                "from_stage": ev.from_stage,
                "to_stage": ev.to_stage,
                "actor": ev.actor,
                "note": ev.note,
                "metadata": ev.metadata_json,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
            for ev in events
        ],
    }


@router.post("/entries/{entry_id}/transition")
def transition(entry_id: UUID, req: TransitionRequest, db: Session = Depends(get_db)):
    """Move a pipeline entry to a new stage."""
    try:
        entry = pipeline_svc.transition_stage(
            db, entry_id,
            to_stage=req.to_stage,
            actor=req.actor,
            note=req.note,
            review_decision=req.review_decision,
        )
        return _entry_to_dict(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/entries/{entry_id}/note")
def add_note(entry_id: UUID, req: NoteRequest, db: Session = Depends(get_db)):
    """Add a note to a pipeline entry without changing stage."""
    try:
        pipeline_svc.add_note(db, entry_id, note=req.note, actor=req.actor)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/entries/{entry_id}/positioning")
def update_positioning(
    entry_id: UUID,
    req: PositioningUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update positioning details (message angle, target profile) on a pipeline entry."""
    try:
        entry = pipeline_svc.update_positioning(
            db, entry_id,
            message_angle=req.message_angle,
            target_profile_notes=req.target_profile_notes,
            actor=req.actor,
        )
        return _entry_to_dict(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Helpers ──────────────────────────────────────────────────────────

def _entry_to_dict(entry) -> dict:
    return {
        "id": str(entry.id),
        "company_id": str(entry.company_id),
        "stage": entry.stage,
        "priority": entry.priority,
        "diagnostic_state_at_intake": entry.diagnostic_state_at_intake,
        "confidence_band_at_intake": entry.confidence_band_at_intake,
        "dominant_function": entry.dominant_function,
        "classified_roles_count": entry.classified_roles_count,
        "jds_count": entry.jds_count,
        "positioning_eligible": entry.positioning_eligible,
        "candidate_archetype": entry.candidate_archetype,
        "positioning_angle": entry.positioning_angle,
        "target_profile_notes": entry.target_profile_notes,
        "message_angle_draft": entry.message_angle_draft,
        "reviewer": entry.reviewer,
        "review_notes": entry.review_notes,
        "review_decision": entry.review_decision,
        "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
        "intake_source": entry.intake_source,
        "batch_run_id": entry.batch_run_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }

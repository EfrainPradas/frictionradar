"""
Phase 11: Commercial Pipeline — tracks companies through the internal
review workflow from radar detection to outreach-ready.

This is NOT outreach automation. This is an internal decision-tracking
system for the NovaWork team to review evidence, make go/no-go calls,
and prepare positioning before any external contact.
"""

import uuid
from sqlalchemy import Column, String, Text, Boolean, SmallInteger, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class PipelineEntry(Base):
    """A company's journey through the commercial review workflow.

    Stages:
        radar       — company detected with positioning potential
        reviewing   — team is reviewing evidence and positioning output
        approved    — approved for candidate matching / angle prep
        preparing   — message angles and candidate profiles being prepared
        ready       — fully prepared for outreach (future phase)
        parked      — paused (not rejected, may revisit)
        rejected    — evidence insufficient or company not a fit
    """

    __tablename__ = "pipeline_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,  # One entry per company
    )

    # Stage tracking
    stage = Column(String, nullable=False, default="radar", index=True)
    priority = Column(SmallInteger, nullable=True, index=True)  # 1=hot, 2=warm, 3=watch

    # Evidence snapshot (captured at intake)
    diagnostic_state_at_intake = Column(String, nullable=True)
    confidence_band_at_intake = Column(String, nullable=True)
    dominant_function = Column(String, nullable=True)
    classified_roles_count = Column(SmallInteger, nullable=True)
    jds_count = Column(SmallInteger, nullable=True)
    positioning_eligible = Column(Boolean, nullable=True, default=False)

    # Review decisions
    reviewer = Column(String, nullable=True)  # who reviewed
    review_notes = Column(Text, nullable=True)
    review_decision = Column(String, nullable=True)  # approve / reject / park
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Positioning angle (approved output)
    candidate_archetype = Column(String, nullable=True)
    positioning_angle = Column(Text, nullable=True)
    target_profile_notes = Column(Text, nullable=True)
    message_angle_draft = Column(Text, nullable=True)

    # Metadata
    intake_source = Column(String, nullable=True)  # batch_run / manual / api
    batch_run_id = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company = relationship("Company")


class PipelineEvent(Base):
    """Audit log for pipeline state transitions.

    Every stage change, note, or decision is logged here for auditability.
    """

    __tablename__ = "pipeline_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String, nullable=False)  # stage_change, note, decision, evidence_update
    from_stage = Column(String, nullable=True)
    to_stage = Column(String, nullable=True)
    actor = Column(String, nullable=True)  # who did it
    note = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    pipeline_entry = relationship("PipelineEntry")

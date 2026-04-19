"""SQLAlchemy models for entity resolution and deduplication.

Three tables:
  - CompanyMatchCandidate:  pair of potentially duplicate master records
  - CompanyMergeDecision:   accepted merge (canonical absorbs duplicate)
  - CompanyResolutionLog:   audit trail per resolution run
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CompanyMatchCandidate(Base):
    __tablename__ = "company_match_candidates"
    __table_args__ = (
        UniqueConstraint("master_id_a", "master_id_b", name="uq_match_pair"),
        CheckConstraint("master_id_a < master_id_b", name="ck_pair_order"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    master_id_a = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    master_id_b = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    confidence = Column(Numeric(4, 3), nullable=False)
    reason_code = Column(String, nullable=False)
    reason_detail = Column(Text, nullable=True)

    status = Column(String, nullable=False, default="pending", index=True)
    resolution_run_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class CompanyMergeDecision(Base):
    __tablename__ = "company_merge_decisions"
    __table_args__ = (
        UniqueConstraint("canonical_id", "duplicate_id", name="uq_merge_pair"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    duplicate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_candidate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_match_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )

    merge_reason = Column(Text, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False)
    merged_by = Column(String, nullable=False, default="auto")

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CompanyResolutionLog(Base):
    __tablename__ = "company_resolution_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    started_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)

    total_compared = Column(Integer, default=0)
    total_candidates = Column(Integer, default=0)
    total_auto_merged = Column(Integer, default=0)
    total_flagged = Column(Integer, default=0)

    status = Column(String, nullable=False, default="running")
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

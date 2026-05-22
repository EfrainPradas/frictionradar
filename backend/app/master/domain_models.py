"""SQLAlchemy models for company web presence / domain resolution."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CompanyDomain(Base):
    """Tracks a domain associated with a master company record.

    One company may have multiple domains (primary + alternates).
    """

    __tablename__ = "company_domains"
    __table_args__ = (
        UniqueConstraint("company_master_id", "domain", name="uq_master_domain"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_master_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    domain = Column(String, nullable=False, index=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    domain_status = Column(String, nullable=False, default="unresolved", index=True)
    confidence = Column(Numeric(4, 3), nullable=False, default=0.500)

    source = Column(String, nullable=True)
    http_status = Column(Integer, nullable=True)
    redirects_to = Column(String, nullable=True)
    title_tag = Column(String, nullable=True)

    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DomainResolutionRun(Base):
    """Audit trail for domain resolution batch runs."""

    __tablename__ = "domain_resolution_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    started_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), default=lambda: datetime.now(timezone.utc)
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)

    total_processed = Column(Integer, default=0)
    total_resolved = Column(Integer, default=0)
    total_rejected = Column(Integer, default=0)
    total_ambiguous = Column(Integer, default=0)
    total_errors = Column(Integer, default=0)

    status = Column(String, nullable=False, default="running")
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), default=lambda: datetime.now(timezone.utc)
    )

"""Extraction routing persistence models.

Three tables:
  - company_ats_detection: which ATS platform was detected for a company
  - company_extraction_cache: cached NormalizedJobsResult per company
  - company_extraction_attempts: log of every extraction attempt
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base


class CompanyAtsDetection(Base):
    """Records which ATS platform was detected for a company's careers page."""

    __tablename__ = "company_ats_detection"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    domain = Column(String, index=True, nullable=False)
    ats_platform = Column(String, nullable=False)  # greenhouse, lever, etc.
    ats_url = Column(String, nullable=True)  # e.g. boards.greenhouse.io/stripe
    detection_source = Column(String, nullable=True)  # homepage_embed, url_pattern, ats_guess
    confidence = Column(Numeric, nullable=True)
    detected_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: datetime.now(timezone.utc),
    )


class CompanyExtractionCache(Base):
    """Cached extraction result for a company.

    Stores the serialized NormalizedJobsResult so we can skip re-extraction
    if the data is still fresh (within TTL).
    """

    __tablename__ = "company_extraction_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    domain = Column(String, index=True, nullable=False)
    strategy_used = Column(String, nullable=False)  # ats_api, http_static, playwright
    careers_url = Column(String, nullable=True)
    ats_platform = Column(String, nullable=True)

    # Cached payload
    open_positions_count = Column(Integer, nullable=True)
    jobs_count = Column(Integer, default=0)
    hiring_areas_json = Column(JSONB, nullable=True)  # List[str]
    jobs_json = Column(JSONB, nullable=True)  # List[NormalizedJob as dict]
    evidence_quality = Column(String, nullable=True)
    confidence = Column(Numeric, nullable=True)

    cached_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)


class CompanyExtractionAttempt(Base):
    """Log of every extraction attempt — success or failure.

    Used for observability: which strategies are chosen, how often they
    succeed, how long they take, and what fallback patterns emerge.
    """

    __tablename__ = "company_extraction_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    domain = Column(String, index=True, nullable=False)

    # Decision
    strategy = Column(String, nullable=False)  # ats_api, http_static, playwright
    reason_code = Column(String, nullable=False)  # from ReasonCode enum
    fallback_from = Column(String, nullable=True)  # previous strategy that failed

    # Outcome
    success = Column(Boolean, default=False)
    error = Column(Text, nullable=True)
    jobs_found = Column(Integer, default=0)
    positions_count = Column(Integer, nullable=True)
    evidence_quality = Column(String, nullable=True)

    # Timing
    duration_ms = Column(Integer, default=0)
    used_cache = Column(Boolean, default=False)

    # Source
    careers_url = Column(String, nullable=True)
    ats_platform = Column(String, nullable=True)

    attempted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: datetime.now(timezone.utc),
    )

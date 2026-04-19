"""SQLAlchemy models for the ingestion staging pipeline.

Three tables:
  - ImportRun:                  tracks each import execution
  - CompanyStagingRaw:          raw records from input file
  - CompanyStagingNormalized:   cleaned records ready for upsert
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ImportRun(Base):
    """Tracks a single import execution."""

    __tablename__ = "import_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(String, nullable=False, index=True)
    source_file = Column(String, nullable=False)
    source_type = Column(String, nullable=False, default="json_file")

    started_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)

    total_raw = Column(Integer, default=0)
    total_normalized = Column(Integer, default=0)
    total_inserted = Column(Integer, default=0)
    total_updated = Column(Integer, default=0)
    total_skipped = Column(Integer, default=0)
    total_errors = Column(Integer, default=0)

    status = Column(String, nullable=False, default="running", index=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    raw_records = relationship(
        "CompanyStagingRaw", back_populates="import_run", cascade="all, delete-orphan"
    )
    normalized_records = relationship(
        "CompanyStagingNormalized", back_populates="import_run", cascade="all, delete-orphan"
    )


class CompanyStagingRaw(Base):
    """Raw record exactly as it appeared in the input file."""

    __tablename__ = "company_staging_raw"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    row_index = Column(Integer, nullable=False)
    raw_payload = Column(JSONB, nullable=False)
    raw_name = Column(String, nullable=True)
    raw_domain = Column(String, nullable=True)

    status = Column(String, nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    import_run = relationship("ImportRun", back_populates="raw_records")
    normalized = relationship(
        "CompanyStagingNormalized", back_populates="staging_raw", uselist=False
    )


class CompanyStagingNormalized(Base):
    """Cleaned, normalized record ready for upsert into company_master."""

    __tablename__ = "company_staging_normalized"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    staging_raw_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_staging_raw.id", ondelete="CASCADE"),
        nullable=False,
    )

    legal_name = Column(String, nullable=False)
    normalized_name = Column(String, nullable=False, index=True)
    domain = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    location_raw = Column(String, nullable=True)
    jurisdiction_state = Column(String, nullable=True)
    source = Column(String, nullable=True)

    matched_master_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_method = Column(String, nullable=True)
    action = Column(String, nullable=False, default="pending", index=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    import_run = relationship("ImportRun", back_populates="normalized_records")
    staging_raw = relationship("CompanyStagingRaw", back_populates="normalized")

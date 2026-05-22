import uuid
from sqlalchemy import Column, String, Boolean, SmallInteger, DateTime, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    domain = Column(String, unique=True, index=True)
    industry = Column(String, nullable=True)
    company_size = Column(String, nullable=True)
    source_added_from = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Phase 9: Dataset governance fields
    normalized_name = Column(String, nullable=True, index=True)
    geography = Column(String, nullable=True, index=True)
    entity_type = Column(String, nullable=True)
    priority_tier = Column(SmallInteger, nullable=True, index=True)
    dataset_status = Column(String, nullable=True, default="imported", index=True)
    careers_url = Column(String, nullable=True)
    careers_accessibility = Column(String, nullable=True, default="unknown")
    last_collection_at = Column(DateTime(timezone=True), nullable=True)
    last_analysis_run_id = Column(String, nullable=True)
    latest_diagnostic_state = Column(String, nullable=True)
    positioning_eligible = Column(Boolean, nullable=True, default=False, index=True)
    notes = Column(Text, nullable=True)

    inferred_sector = Column(String, nullable=True, index=True)
    inferred_sector_source = Column(String, nullable=True)
    inferred_sector_confidence = Column(String, nullable=True)

    signals = relationship(
        "CompanySignal", back_populates="company", cascade="all, delete-orphan"
    )
    runs = relationship(
        "CollectionRun", back_populates="company", cascade="all, delete-orphan"
    )
    job_roles = relationship(
        "CompanyJobRole", back_populates="company", cascade="all, delete-orphan"
    )
    role_signals = relationship(
        "CompanyRoleSignal", back_populates="company", cascade="all, delete-orphan"
    )
    hiring_patterns = relationship(
        "HiringPattern", back_populates="company", cascade="all, delete-orphan"
    )
    page_captures = relationship(
        "PageCapture", back_populates="company", cascade="all, delete-orphan"
    )

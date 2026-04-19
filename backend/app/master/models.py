"""SQLAlchemy models for the Company Master Index.

Four tables:
  - CompanyMaster:      canonical identity record per legal entity
  - CompanyExternalId:  flexible external identifier storage (EIN, CIK, UEI, etc.)
  - CompanyAlias:       DBA / trade names / normalized variants
  - CompanySourceRecord: full source provenance with raw payload
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class CompanyMaster(Base):
    """Canonical identity record for a U.S. legal entity."""

    __tablename__ = "company_master"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Names
    legal_name = Column(String, nullable=False)
    normalized_name = Column(String, nullable=False, index=True)

    # Entity metadata
    entity_type = Column(String, nullable=True)  # corporation, llc, lp, nonprofit, etc.
    entity_status = Column(String, nullable=False, default="active", index=True)
    jurisdiction_state = Column(String, nullable=True, index=True)  # 2-letter state code
    formation_date = Column(Date, nullable=True)

    # Source quality
    source_priority = Column(Integer, nullable=False, default=50)
    source_confidence = Column(Numeric(3, 2), nullable=False, default=0.50)

    # Link to analysis workspace (populated in later phases)
    linked_company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Verification
    last_verified_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    external_ids = relationship(
        "CompanyExternalId", back_populates="company_master", cascade="all, delete-orphan"
    )
    aliases = relationship(
        "CompanyAlias", back_populates="company_master", cascade="all, delete-orphan"
    )
    source_records = relationship(
        "CompanySourceRecord", back_populates="company_master", cascade="all, delete-orphan"
    )


class CompanyExternalId(Base):
    """External identifier for a master company record.

    Flexible EAV-style: one row per (company, id_type, id_value).
    Supports state_registry_id, ein, edgar_cik, sam_uei, duns, lei, etc.
    """

    __tablename__ = "company_external_ids"
    __table_args__ = (
        UniqueConstraint("company_master_id", "id_type", "id_value", name="uq_ext_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_master_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_type = Column(String, nullable=False)  # state_registry_id, ein, edgar_cik, sam_uei
    id_value = Column(String, nullable=False)
    issuing_authority = Column(String, nullable=True)  # DE_SOS, IRS, SEC, GSA
    verified = Column(Boolean, default=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company_master = relationship("CompanyMaster", back_populates="external_ids")


class CompanyAlias(Base):
    """DBA names, trade names, abbreviations, former names."""

    __tablename__ = "company_aliases"
    __table_args__ = (
        UniqueConstraint("company_master_id", "alias_name", "alias_type", name="uq_alias"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_master_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    alias_name = Column(String, nullable=False, index=True)
    alias_type = Column(String, nullable=False, default="dba")  # dba, trade_name, abbreviation, former_name, normalized
    is_primary = Column(Boolean, default=False)
    source = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company_master = relationship("CompanyMaster", back_populates="aliases")


class CompanySourceRecord(Base):
    """Provenance record: which source produced data, when, and the raw payload.

    Never delete source records — they form the audit trail.
    """

    __tablename__ = "company_source_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_master_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_name = Column(String, nullable=False, index=True)  # sec_edgar, sam_gov, state_sos_de, csv_import
    source_record_id = Column(String, nullable=True)  # ID from external source
    source_url = Column(String, nullable=True)

    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    raw_payload = Column(JSONB, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company_master = relationship("CompanyMaster", back_populates="source_records")

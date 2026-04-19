"""Pydantic schemas for the Company Master Index.

Three-tier pattern per repo convention: Base → Create → Read.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── CompanyMaster ──────────────────────────────────────────────────

class CompanyMasterBase(BaseModel):
    legal_name: str = Field(..., description="Official legal name of the entity")
    normalized_name: str = Field(..., description="Lowercase, punctuation-stripped name for matching")
    entity_type: Optional[str] = None
    entity_status: str = Field(default="active")
    jurisdiction_state: Optional[str] = Field(default=None, description="2-letter US state code")
    formation_date: Optional[date] = None
    source_priority: int = Field(default=50, ge=0, le=100)
    source_confidence: float = Field(default=0.50, ge=0.0, le=1.0)


class CompanyMasterCreate(CompanyMasterBase):
    linked_company_id: Optional[UUID] = None


class CompanyMasterRead(CompanyMasterBase):
    id: UUID
    linked_company_id: Optional[UUID] = None
    last_verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    external_ids: list[CompanyExternalIdRead] = Field(default_factory=list)
    aliases: list[CompanyAliasRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CompanyMasterSummary(BaseModel):
    """Lightweight read schema without nested relations."""
    id: UUID
    legal_name: str
    normalized_name: str
    entity_type: Optional[str] = None
    entity_status: str
    jurisdiction_state: Optional[str] = None
    source_confidence: float
    linked_company_id: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── CompanyExternalId ──────────────────────────────────────────────

class CompanyExternalIdBase(BaseModel):
    id_type: str = Field(..., description="Identifier type: state_registry_id, ein, edgar_cik, sam_uei, duns, lei")
    id_value: str = Field(..., description="The identifier value")
    issuing_authority: Optional[str] = None
    verified: bool = False


class CompanyExternalIdCreate(CompanyExternalIdBase):
    company_master_id: UUID


class CompanyExternalIdRead(CompanyExternalIdBase):
    id: UUID
    company_master_id: UUID
    verified_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── CompanyAlias ───────────────────────────────────────────────────

class CompanyAliasBase(BaseModel):
    alias_name: str
    alias_type: str = Field(default="dba", description="dba, trade_name, abbreviation, former_name, normalized")
    is_primary: bool = False
    source: Optional[str] = None


class CompanyAliasCreate(CompanyAliasBase):
    company_master_id: UUID


class CompanyAliasRead(CompanyAliasBase):
    id: UUID
    company_master_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── CompanySourceRecord ────────────────────────────────────────────

class CompanySourceRecordBase(BaseModel):
    source_name: str = Field(..., description="sec_edgar, sam_gov, state_sos_de, csv_import, etc.")
    source_record_id: Optional[str] = None
    source_url: Optional[str] = None
    raw_payload: Optional[dict] = None


class CompanySourceRecordCreate(CompanySourceRecordBase):
    company_master_id: UUID
    fetched_at: Optional[datetime] = None


class CompanySourceRecordRead(CompanySourceRecordBase):
    id: UUID
    company_master_id: UUID
    fetched_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Forward reference resolution for nested schemas
CompanyMasterRead.model_rebuild()

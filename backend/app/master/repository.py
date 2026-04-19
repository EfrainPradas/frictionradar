"""Minimal data access layer for the Company Master Index.

Provides CRUD operations and basic lookup queries. Entity resolution
and batch ingestion will be added in later phases.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from .canonical import normalize_company_name, normalize_state_code
from .models import CompanyAlias, CompanyExternalId, CompanyMaster, CompanySourceRecord
from .schemas import (
    CompanyAliasCreate,
    CompanyExternalIdCreate,
    CompanyMasterCreate,
    CompanySourceRecordCreate,
)


# ── CompanyMaster CRUD ─────────────────────────────────────────────

def create_master_company(db: Session, data: CompanyMasterCreate) -> CompanyMaster:
    """Create a new master company record with auto-normalized name."""
    record = CompanyMaster(
        legal_name=data.legal_name,
        normalized_name=normalize_company_name(data.legal_name),
        entity_type=data.entity_type,
        entity_status=data.entity_status,
        jurisdiction_state=normalize_state_code(data.jurisdiction_state),
        formation_date=data.formation_date,
        source_priority=data.source_priority,
        source_confidence=data.source_confidence,
        linked_company_id=data.linked_company_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_master_company(db: Session, master_id: UUID) -> Optional[CompanyMaster]:
    return db.query(CompanyMaster).filter(CompanyMaster.id == master_id).first()


def find_by_normalized_name(db: Session, name: str) -> list[CompanyMaster]:
    """Find master records by normalized name (exact match)."""
    normalized = normalize_company_name(name)
    return (
        db.query(CompanyMaster)
        .filter(CompanyMaster.normalized_name == normalized)
        .all()
    )


def find_by_external_id(db: Session, id_type: str, id_value: str) -> Optional[CompanyMaster]:
    """Find a master record by an external identifier."""
    ext = (
        db.query(CompanyExternalId)
        .filter(
            CompanyExternalId.id_type == id_type,
            CompanyExternalId.id_value == id_value,
        )
        .first()
    )
    if ext is None:
        return None
    return get_master_company(db, ext.company_master_id)


def list_master_companies(
    db: Session,
    *,
    status: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CompanyMaster]:
    q = db.query(CompanyMaster)
    if status:
        q = q.filter(CompanyMaster.entity_status == status)
    if jurisdiction:
        q = q.filter(CompanyMaster.jurisdiction_state == normalize_state_code(jurisdiction))
    return q.order_by(CompanyMaster.legal_name).offset(offset).limit(limit).all()


def count_master_companies(db: Session, *, status: Optional[str] = None) -> int:
    q = db.query(CompanyMaster)
    if status:
        q = q.filter(CompanyMaster.entity_status == status)
    return q.count()


def update_master_company(
    db: Session, master_id: UUID, **kwargs
) -> Optional[CompanyMaster]:
    record = get_master_company(db, master_id)
    if record is None:
        return None
    for key, value in kwargs.items():
        if hasattr(record, key):
            setattr(record, key, value)
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record


# ── External IDs ───────────────────────────────────────────────────

def add_external_id(db: Session, data: CompanyExternalIdCreate) -> CompanyExternalId:
    record = CompanyExternalId(
        company_master_id=data.company_master_id,
        id_type=data.id_type,
        id_value=data.id_value,
        issuing_authority=data.issuing_authority,
        verified=data.verified,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_external_ids(db: Session, master_id: UUID) -> list[CompanyExternalId]:
    return (
        db.query(CompanyExternalId)
        .filter(CompanyExternalId.company_master_id == master_id)
        .all()
    )


# ── Aliases ────────────────────────────────────────────────────────

def add_alias(db: Session, data: CompanyAliasCreate) -> CompanyAlias:
    record = CompanyAlias(
        company_master_id=data.company_master_id,
        alias_name=data.alias_name,
        alias_type=data.alias_type,
        is_primary=data.is_primary,
        source=data.source,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_aliases(db: Session, master_id: UUID) -> list[CompanyAlias]:
    return (
        db.query(CompanyAlias)
        .filter(CompanyAlias.company_master_id == master_id)
        .all()
    )


# ── Source Records ─────────────────────────────────────────────────

def add_source_record(db: Session, data: CompanySourceRecordCreate) -> CompanySourceRecord:
    record = CompanySourceRecord(
        company_master_id=data.company_master_id,
        source_name=data.source_name,
        source_record_id=data.source_record_id,
        source_url=data.source_url,
        fetched_at=data.fetched_at or datetime.now(timezone.utc),
        raw_payload=data.raw_payload,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_source_records(db: Session, master_id: UUID) -> list[CompanySourceRecord]:
    return (
        db.query(CompanySourceRecord)
        .filter(CompanySourceRecord.company_master_id == master_id)
        .order_by(CompanySourceRecord.fetched_at.desc())
        .all()
    )

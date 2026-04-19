"""Downstream export layer for the Company Master Index.

Produces a clean, flat dataset ready for FrictionRadar's pipeline:
careers discovery, ATS detection, and scoring.

Two export modes:
  1. Query-based:  get_downstream_dataset() returns Pydantic models
  2. File-based:   export_downstream_json() writes a JSON file

Readiness statuses:
  - ready_for_careers_discovery:  has resolved primary domain
  - ready_for_domain_resolution:  has domain but unverified
  - needs_domain:                 no domain found
  - needs_review:                 ambiguous or rejected data
  - merged:                       absorbed into another record
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .domain_models import CompanyDomain
from .models import CompanyExternalId, CompanyMaster


# ════════════════════════════════════════════════════════════════════
# Output schema
# ════════════════════════════════════════════════════════════════════

class DownstreamCompany(BaseModel):
    """Flat, export-ready company record for downstream consumption."""

    company_id: str
    legal_name: str
    normalized_name: str
    entity_type: Optional[str] = None
    entity_status: str
    jurisdiction_state: Optional[str] = None
    source_confidence: float

    # Domain
    primary_domain: Optional[str] = None
    official_website: Optional[str] = None
    domain_status: Optional[str] = None
    domain_confidence: Optional[float] = None
    domain_title: Optional[str] = None

    # External IDs
    external_ids: dict[str, str] = Field(default_factory=dict)
    external_id_count: int = 0

    # Readiness
    readiness_status: str
    has_resolved_domain: bool = False
    has_external_ids: bool = False
    high_confidence: bool = False

    # Linking
    linked_company_id: Optional[str] = None

    # Timestamps
    last_verified_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DownstreamSummary(BaseModel):
    """Summary statistics for the downstream dataset."""

    total_companies: int
    ready_for_careers_discovery: int
    ready_for_domain_resolution: int
    needs_domain: int
    needs_review: int
    with_external_ids: int
    high_confidence: int
    by_state: dict[str, int] = Field(default_factory=dict)
    exported_at: str


# ════════════════════════════════════════════════════════════════════
# Query-based export
# ════════════════════════════════════════════════════════════════════

def get_downstream_dataset(
    db: Session,
    *,
    status_filter: str | None = None,
    has_domain: bool | None = None,
    high_confidence_only: bool = False,
    jurisdiction: str | None = None,
    limit: int | None = None,
) -> list[DownstreamCompany]:
    """Query the master index and return downstream-ready records.

    Filters:
        status_filter: readiness_status value to filter by
        has_domain: True=only with domain, False=only without
        high_confidence_only: source_confidence >= 0.70
        jurisdiction: 2-letter state code
        limit: max records to return
    """
    masters = (
        db.query(CompanyMaster)
        .filter(CompanyMaster.entity_status == "active")
        .order_by(CompanyMaster.legal_name)
    )

    if high_confidence_only:
        masters = masters.filter(CompanyMaster.source_confidence >= 0.70)
    if jurisdiction:
        masters = masters.filter(CompanyMaster.jurisdiction_state == jurisdiction.upper())

    all_masters = masters.all()
    results = []

    for m in all_masters:
        record = _build_record(db, m)

        # Apply post-query filters
        if status_filter and record.readiness_status != status_filter:
            continue
        if has_domain is True and not record.has_resolved_domain:
            continue
        if has_domain is False and record.has_resolved_domain:
            continue

        results.append(record)
        if limit and len(results) >= limit:
            break

    return results


def get_downstream_summary(db: Session) -> DownstreamSummary:
    """Get summary statistics for the full downstream dataset."""
    dataset = get_downstream_dataset(db)

    by_status = {}
    by_state: dict[str, int] = {}
    with_ids = 0
    high_conf = 0

    for r in dataset:
        by_status[r.readiness_status] = by_status.get(r.readiness_status, 0) + 1
        if r.jurisdiction_state:
            by_state[r.jurisdiction_state] = by_state.get(r.jurisdiction_state, 0) + 1
        if r.has_external_ids:
            with_ids += 1
        if r.high_confidence:
            high_conf += 1

    return DownstreamSummary(
        total_companies=len(dataset),
        ready_for_careers_discovery=by_status.get("ready_for_careers_discovery", 0),
        ready_for_domain_resolution=by_status.get("ready_for_domain_resolution", 0),
        needs_domain=by_status.get("needs_domain", 0),
        needs_review=by_status.get("needs_review", 0),
        with_external_ids=with_ids,
        high_confidence=high_conf,
        by_state=dict(sorted(by_state.items(), key=lambda x: -x[1])),
        exported_at=datetime.now(timezone.utc).isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# File-based export
# ════════════════════════════════════════════════════════════════════

def export_downstream_json(
    db: Session,
    output_path: str,
    *,
    status_filter: str | None = None,
    has_domain: bool | None = None,
    high_confidence_only: bool = False,
) -> dict:
    """Export the downstream dataset to a JSON file.

    Returns summary dict.
    """
    dataset = get_downstream_dataset(
        db,
        status_filter=status_filter,
        has_domain=has_domain,
        high_confidence_only=high_confidence_only,
    )
    summary = get_downstream_summary(db)

    output = {
        "metadata": {
            "exported_at": summary.exported_at,
            "total_companies": len(dataset),
            "filters": {
                "status_filter": status_filter,
                "has_domain": has_domain,
                "high_confidence_only": high_confidence_only,
            },
        },
        "summary": summary.model_dump(),
        "companies": [r.model_dump() for r in dataset],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")

    return {
        "status": "success",
        "output_path": str(path),
        "total_exported": len(dataset),
        "summary": summary.model_dump(),
    }


# ════════════════════════════════════════════════════════════════════
# Internals
# ════════════════════════════════════════════════════════════════════

def _build_record(db: Session, m: CompanyMaster) -> DownstreamCompany:
    """Build a DownstreamCompany from a master record + related data."""
    # Primary domain
    primary = (
        db.query(CompanyDomain)
        .filter(
            CompanyDomain.company_master_id == m.id,
            CompanyDomain.is_primary == True,
        )
        .first()
    )

    domain = primary.domain if primary else None
    domain_status = primary.domain_status if primary else None
    domain_confidence = float(primary.confidence) if primary and primary.confidence else None
    domain_title = primary.title_tag if primary else None

    # External IDs
    ext_ids = (
        db.query(CompanyExternalId)
        .filter(CompanyExternalId.company_master_id == m.id)
        .all()
    )
    ext_dict = {e.id_type: e.id_value for e in ext_ids}

    # Readiness
    has_resolved = domain is not None and domain_status == "resolved"
    readiness = _compute_readiness(m, domain, domain_status)

    return DownstreamCompany(
        company_id=str(m.id),
        legal_name=m.legal_name,
        normalized_name=m.normalized_name,
        entity_type=m.entity_type,
        entity_status=m.entity_status,
        jurisdiction_state=m.jurisdiction_state,
        source_confidence=float(m.source_confidence) if m.source_confidence else 0.50,
        primary_domain=domain,
        official_website=f"https://{domain}" if domain else None,
        domain_status=domain_status,
        domain_confidence=domain_confidence,
        domain_title=domain_title,
        external_ids=ext_dict,
        external_id_count=len(ext_dict),
        readiness_status=readiness,
        has_resolved_domain=has_resolved,
        has_external_ids=len(ext_dict) > 0,
        high_confidence=float(m.source_confidence or 0) >= 0.70,
        linked_company_id=str(m.linked_company_id) if m.linked_company_id else None,
        last_verified_at=m.last_verified_at.isoformat() if m.last_verified_at else None,
        created_at=m.created_at.isoformat() if m.created_at else None,
        updated_at=m.updated_at.isoformat() if m.updated_at else None,
    )


def _compute_readiness(
    m: CompanyMaster, domain: str | None, domain_status: str | None
) -> str:
    if m.entity_status == "merged":
        return "merged"
    if domain and domain_status == "resolved":
        return "ready_for_careers_discovery"
    if domain and domain_status in ("unresolved", "ambiguous"):
        return "ready_for_domain_resolution"
    if not domain:
        return "needs_domain"
    return "needs_review"

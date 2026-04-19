"""Florida batch selector — filter and slice staged records for import preview.

Queries company_staging_normalized (action='staged') records from Florida
staging runs, applies configurable filters, and returns preview batches.

No writes to company_master. This is a read-only selection tool.

Filters:
  - entity_type: corporation, llc, nonprofit, limited_partnership
  - domestic_only: DOMP, DOMNP, DOMLP, FLAL (exclude FOR*)
  - exclude_irrelevant: drops AGENT, TRUST filing types
  - state: jurisdiction_state filter
  - has_fei: only companies with FEI/EIN number

Batch sizes: any integer, common presets 100/250/500/1000
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.master.models import CompanyMaster
from app.master.staging_models import CompanyStagingNormalized, CompanyStagingRaw, ImportRun


# ════════════════════════════════════════════════════════════════════
# Filing type classification
# ════════════════════════════════════════════════════════════════════

DOMESTIC_FILING_TYPES = {"DOMP", "DOMNP", "DOMLP", "FLAL"}
FOREIGN_FILING_TYPES = {"FORP", "FORNP", "FORLP", "FORL"}
IRRELEVANT_FILING_TYPES = {"AGENT", "TRUST"}

ENTITY_TYPE_LABELS = {
    "corporation": "Corporation (DOMP/FORP)",
    "llc": "LLC (FLAL/FORL)",
    "nonprofit": "Nonprofit (DOMNP/FORNP/NPREG)",
    "limited_partnership": "Limited Partnership (DOMLP/FORLP)",
    "trust": "Trust",
    "registered_agent": "Registered Agent",
}


# ════════════════════════════════════════════════════════════════════
# Filter spec
# ════════════════════════════════════════════════════════════════════

@dataclass
class BatchFilter:
    """Configurable filter for batch selection."""
    entity_types: set[str] | None = None      # e.g. {"corporation", "llc"}
    filing_types: set[str] | None = None       # e.g. {"DOMP", "FLAL"}
    domestic_only: bool = False                 # exclude FOR* filing types
    exclude_irrelevant: bool = True             # exclude AGENT, TRUST
    state: str | None = None                    # e.g. "FL"
    has_fei: bool = False                       # only with FEI/EIN
    run_id: str | None = None                   # specific staging run


# ════════════════════════════════════════════════════════════════════
# Core selection
# ════════════════════════════════════════════════════════════════════

def select_batch(
    db: Session,
    filters: BatchFilter,
    *,
    batch_size: int = 100,
    offset: int = 0,
    check_duplicates: bool = True,
) -> dict:
    """Select a batch of staged Florida records matching filters.

    Returns a preview dict with counts, sample records, and dedup info.
    No writes to any table.
    """
    # Get all matching staged records
    candidates = _query_candidates(db, filters)
    total_candidates = len(candidates)

    # Slice
    batch = candidates[offset:offset + batch_size]

    # Dedup check against company_master
    dedup_info = {}
    if check_duplicates and batch:
        dedup_info = _check_duplicates(db, batch)

    # Build preview
    records = []
    for norm, raw in batch:
        payload = raw.raw_payload or {} if raw else {}
        norm_name = norm.normalized_name
        is_duplicate = norm_name in dedup_info

        records.append({
            "legal_name": norm.legal_name,
            "normalized_name": norm_name,
            "jurisdiction_state": norm.jurisdiction_state,
            "location_raw": norm.location_raw,
            "corp_number": payload.get("corp_number"),
            "filing_type": payload.get("filing_type"),
            "entity_type": payload.get("entity_type"),
            "fei_number": payload.get("fei_number") or None,
            "file_date": payload.get("file_date"),
            "agent_name": payload.get("agent_name"),
            "existing_in_master": is_duplicate,
            "match_master_name": dedup_info.get(norm_name),
        })

    new_count = sum(1 for r in records if not r["existing_in_master"])
    dup_count = sum(1 for r in records if r["existing_in_master"])

    return {
        "total_staged": _count_all_staged(db, filters.run_id),
        "total_candidates": total_candidates,
        "batch_size": batch_size,
        "offset": offset,
        "batch_count": len(records),
        "new_companies": new_count,
        "already_in_master": dup_count,
        "filters_applied": _describe_filters(filters),
        "records": records,
        "has_more": (offset + batch_size) < total_candidates,
        "next_offset": offset + batch_size if (offset + batch_size) < total_candidates else None,
    }


def get_filter_stats(db: Session, run_id: str | None = None) -> dict:
    """Show available filter options and their counts for staged Florida data."""
    base_q = (
        db.query(CompanyStagingNormalized, CompanyStagingRaw)
        .join(CompanyStagingRaw, CompanyStagingNormalized.staging_raw_id == CompanyStagingRaw.id)
        .join(ImportRun, CompanyStagingNormalized.import_run_id == ImportRun.id)
        .filter(
            ImportRun.source_type == "florida_sunbiz",
            CompanyStagingNormalized.action == "staged",
        )
    )
    if run_id:
        base_q = base_q.filter(ImportRun.id == run_id)

    all_records = base_q.all()

    by_entity = {}
    by_filing = {}
    by_state = {}
    domestic = 0
    foreign = 0
    irrelevant = 0
    with_fei = 0

    for norm, raw in all_records:
        p = raw.raw_payload or {}
        et = p.get("entity_type", "unknown") or "unknown"
        ft = p.get("filing_type", "unknown") or "unknown"
        st = norm.jurisdiction_state or "?"

        by_entity[et] = by_entity.get(et, 0) + 1
        by_filing[ft] = by_filing.get(ft, 0) + 1
        by_state[st] = by_state.get(st, 0) + 1

        if ft in DOMESTIC_FILING_TYPES:
            domestic += 1
        elif ft in FOREIGN_FILING_TYPES:
            foreign += 1
        if ft in IRRELEVANT_FILING_TYPES:
            irrelevant += 1
        if p.get("fei_number"):
            with_fei += 1

    return {
        "total_staged": len(all_records),
        "by_entity_type": dict(sorted(by_entity.items(), key=lambda x: -x[1])),
        "by_filing_type": dict(sorted(by_filing.items(), key=lambda x: -x[1])),
        "by_state": dict(sorted(by_state.items(), key=lambda x: -x[1])[:10]),
        "domestic": domestic,
        "foreign": foreign,
        "irrelevant": irrelevant,
        "with_fei": with_fei,
        "after_exclude_irrelevant": len(all_records) - irrelevant,
    }


# ════════════════════════════════════════════════════════════════════
# Internals
# ════════════════════════════════════════════════════════════════════

def _query_candidates(
    db: Session, filters: BatchFilter
) -> list[tuple[CompanyStagingNormalized, CompanyStagingRaw]]:
    """Query staged records matching the filter spec."""
    q = (
        db.query(CompanyStagingNormalized, CompanyStagingRaw)
        .join(CompanyStagingRaw, CompanyStagingNormalized.staging_raw_id == CompanyStagingRaw.id)
        .join(ImportRun, CompanyStagingNormalized.import_run_id == ImportRun.id)
        .filter(
            ImportRun.source_type == "florida_sunbiz",
            CompanyStagingNormalized.action == "staged",
        )
    )

    if filters.run_id:
        q = q.filter(ImportRun.id == filters.run_id)

    if filters.state:
        q = q.filter(CompanyStagingNormalized.jurisdiction_state == filters.state.upper())

    # Apply JSONB-based filters via raw_payload
    if filters.exclude_irrelevant:
        for ft in IRRELEVANT_FILING_TYPES:
            q = q.filter(
                CompanyStagingRaw.raw_payload["filing_type"].astext != ft
            )

    if filters.domestic_only:
        q = q.filter(
            CompanyStagingRaw.raw_payload["filing_type"].astext.in_(DOMESTIC_FILING_TYPES)
        )

    if filters.entity_types:
        q = q.filter(
            CompanyStagingRaw.raw_payload["entity_type"].astext.in_(filters.entity_types)
        )

    if filters.filing_types:
        q = q.filter(
            CompanyStagingRaw.raw_payload["filing_type"].astext.in_(filters.filing_types)
        )

    if filters.has_fei:
        q = q.filter(
            CompanyStagingRaw.raw_payload["fei_number"].astext != "",
        )

    return q.order_by(CompanyStagingNormalized.id).all()


def _count_all_staged(db: Session, run_id: str | None) -> int:
    q = (
        db.query(func.count(CompanyStagingNormalized.id))
        .join(ImportRun, CompanyStagingNormalized.import_run_id == ImportRun.id)
        .filter(
            ImportRun.source_type == "florida_sunbiz",
            CompanyStagingNormalized.action == "staged",
        )
    )
    if run_id:
        q = q.filter(ImportRun.id == run_id)
    return q.scalar() or 0


def _check_duplicates(
    db: Session, batch: list[tuple[CompanyStagingNormalized, CompanyStagingRaw]]
) -> dict[str, str]:
    """Check which normalized names already exist in company_master.

    Returns {normalized_name: existing_legal_name} for matches.
    """
    names = [norm.normalized_name for norm, _ in batch]
    existing = (
        db.query(CompanyMaster.normalized_name, CompanyMaster.legal_name)
        .filter(
            CompanyMaster.normalized_name.in_(names),
            CompanyMaster.entity_status != "merged",
        )
        .all()
    )
    return {row.normalized_name: row.legal_name for row in existing}


def _describe_filters(f: BatchFilter) -> list[str]:
    """Human-readable list of active filters."""
    desc = []
    if f.exclude_irrelevant:
        desc.append("exclude AGENT/TRUST")
    if f.domestic_only:
        desc.append("domestic only (DOMP/DOMNP/DOMLP/FLAL)")
    if f.entity_types:
        desc.append(f"entity types: {', '.join(sorted(f.entity_types))}")
    if f.filing_types:
        desc.append(f"filing types: {', '.join(sorted(f.filing_types))}")
    if f.state:
        desc.append(f"state: {f.state}")
    if f.has_fei:
        desc.append("has FEI/EIN only")
    if f.run_id:
        desc.append(f"run: {f.run_id[:8]}...")
    if not desc:
        desc.append("(no filters)")
    return desc

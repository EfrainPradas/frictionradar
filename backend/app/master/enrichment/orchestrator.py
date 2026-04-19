"""Enrichment orchestrator — runs adapters and persists identifiers.

Coordinates multiple EnrichmentAdapter implementations, deduplicates
results, and persists into company_external_ids with full provenance.

Missing identifiers are handled gracefully:
  - If an adapter returns no matches, the company is simply skipped.
  - If an adapter errors, the error is logged but doesn't block others.
  - No company is required to have any external IDs.
  - The master index works fully without enrichment data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.master.models import CompanyExternalId, CompanyMaster, CompanySourceRecord

from .base import EnrichmentAdapter, EnrichmentResult, IdentifierMatch


def run_enrichment(
    db: Session,
    adapters: list[EnrichmentAdapter],
    *,
    master_ids: list[UUID] | None = None,
    dry_run: bool = False,
) -> dict:
    """Run enrichment across all (or selected) master companies.

    Args:
        db: database session
        adapters: list of enrichment adapter instances
        master_ids: if provided, only enrich these companies
        dry_run: if True, report what would be added without writing

    Returns summary dict.
    """
    q = db.query(CompanyMaster).filter(CompanyMaster.entity_status != "merged")
    if master_ids:
        q = q.filter(CompanyMaster.id.in_(master_ids))
    masters = q.all()

    total_processed = 0
    total_ids_added = 0
    total_ids_skipped = 0
    total_errors = 0
    dry_run_entries = []

    for master in masters:
        total_processed += 1
        all_identifiers: list[tuple[IdentifierMatch, str]] = []

        for adapter in adapters:
            result = adapter.enrich(db, master)
            if result.error:
                total_errors += 1
                continue
            for ident in result.identifiers:
                all_identifiers.append((ident, adapter.name()))

        if not all_identifiers:
            continue

        if dry_run:
            dry_run_entries.append({
                "company": master.legal_name,
                "master_id": str(master.id),
                "identifiers": [
                    {
                        "id_type": ident.id_type,
                        "id_value": ident.id_value,
                        "confidence": ident.confidence,
                        "source": source,
                    }
                    for ident, source in all_identifiers
                ],
            })
            continue

        for ident, source_name in all_identifiers:
            added = _persist_identifier(db, master.id, ident, source_name)
            if added:
                total_ids_added += 1
            else:
                total_ids_skipped += 1

    if not dry_run:
        db.commit()

    if dry_run:
        return {
            "status": "dry_run",
            "total_companies": len(masters),
            "total_processed": total_processed,
            "companies_with_ids": len(dry_run_entries),
            "entries": dry_run_entries,
        }

    return {
        "status": "success",
        "total_companies": len(masters),
        "total_processed": total_processed,
        "total_ids_added": total_ids_added,
        "total_ids_skipped": total_ids_skipped,
        "total_errors": total_errors,
    }


def _persist_identifier(
    db: Session,
    master_id: UUID,
    ident: IdentifierMatch,
    source_name: str,
) -> bool:
    """Persist an identifier if it doesn't already exist.

    Returns True if added, False if already exists (skipped).
    """
    existing = (
        db.query(CompanyExternalId)
        .filter(
            CompanyExternalId.company_master_id == master_id,
            CompanyExternalId.id_type == ident.id_type,
            CompanyExternalId.id_value == ident.id_value,
        )
        .first()
    )

    if existing:
        # Already exists — skip (idempotent)
        return False

    ext_id = CompanyExternalId(
        company_master_id=master_id,
        id_type=ident.id_type,
        id_value=ident.id_value,
        issuing_authority=ident.issuing_authority,
        verified=False,
    )
    db.add(ext_id)

    # Add source provenance
    source_record = CompanySourceRecord(
        company_master_id=master_id,
        source_name=f"enrichment:{source_name}",
        source_record_id=f"{ident.id_type}:{ident.id_value}",
        source_url=ident.source_url,
        raw_payload=ident.raw_payload,
    )
    db.add(source_record)

    db.flush()
    return True


def get_enrichment_summary(db: Session) -> dict:
    """Get a summary of all external identifiers in the system."""
    from sqlalchemy import func

    total_masters = db.query(CompanyMaster).filter(
        CompanyMaster.entity_status != "merged"
    ).count()

    # Count by id_type
    type_counts = (
        db.query(
            CompanyExternalId.id_type,
            func.count(CompanyExternalId.id).label("count"),
            func.count(func.distinct(CompanyExternalId.company_master_id)).label("companies"),
        )
        .group_by(CompanyExternalId.id_type)
        .all()
    )

    by_type = {
        row.id_type: {"count": row.count, "companies": row.companies}
        for row in type_counts
    }

    total_with_ids = db.query(
        func.count(func.distinct(CompanyExternalId.company_master_id))
    ).scalar() or 0

    return {
        "total_companies": total_masters,
        "companies_with_any_id": total_with_ids,
        "companies_without_ids": total_masters - total_with_ids,
        "by_type": by_type,
    }

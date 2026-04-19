"""Florida batch import — upsert filtered staged records into company_master.

Takes a batch from florida_batch_selector and inserts/updates company_master
records with full provenance, external IDs, and idempotent behavior.

Idempotency:
  - Staged records with action='insert' or action='update' are skipped on re-run
  - Only action='staged' records are candidates for import
  - Dedup by normalized_name against existing company_master records
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.master.canonical import normalize_state_code
from app.master.enrichment.base import IdType
from app.master.models import CompanyExternalId, CompanyMaster, CompanySourceRecord
from app.master.staging_models import CompanyStagingNormalized, CompanyStagingRaw

from .florida_batch_selector import BatchFilter, _query_candidates


def import_florida_batch(
    db: Session,
    filters: BatchFilter,
    *,
    batch_size: int = 100,
    offset: int = 0,
    dry_run: bool = False,
) -> dict:
    """Import a filtered batch of Florida staged records into company_master.

    Only processes records with action='staged'. After import, marks them
    as action='insert' or action='update' so re-runs skip them.

    Returns import summary.
    """
    candidates = _query_candidates(db, filters)
    total_candidates = len(candidates)
    batch = candidates[offset:offset + batch_size]

    if dry_run:
        return _preview(batch, total_candidates, batch_size, offset)

    inserted = 0
    updated = 0
    skipped = 0
    errors = 0
    seen_names: set[str] = set()

    for norm, raw in batch:
        try:
            # Skip if already imported (idempotent)
            if norm.action in ("insert", "update", "skip", "error"):
                skipped += 1
                continue

            # Skip batch-internal duplicates
            if norm.normalized_name in seen_names:
                norm.action = "skip"
                norm.match_method = "duplicate_in_batch"
                skipped += 1
                continue
            seen_names.add(norm.normalized_name)

            payload = raw.raw_payload or {}
            corp_number = payload.get("corp_number", "")
            entity_type = payload.get("entity_type")
            fei_number = payload.get("fei_number", "")
            file_date = _parse_date(payload.get("file_date"))

            # Check existing by normalized name
            existing = (
                db.query(CompanyMaster)
                .filter(CompanyMaster.normalized_name == norm.normalized_name)
                .first()
            )

            if existing:
                _merge_fields(existing, norm, entity_type, file_date)
                norm.matched_master_id = existing.id
                norm.match_method = "exact_normalized_name"
                norm.action = "update"
                _add_provenance(db, existing.id, norm, raw, payload)
                _add_external_ids(db, existing.id, corp_number, fei_number)
                updated += 1
            else:
                master = CompanyMaster(
                    legal_name=norm.legal_name,
                    normalized_name=norm.normalized_name,
                    entity_type=entity_type,
                    entity_status="active",
                    jurisdiction_state=norm.jurisdiction_state or "FL",
                    formation_date=file_date,
                    source_priority=40,
                    source_confidence=0.80,
                )
                db.add(master)
                db.flush()

                norm.matched_master_id = master.id
                norm.match_method = "new"
                norm.action = "insert"
                _add_provenance(db, master.id, norm, raw, payload)
                _add_external_ids(db, master.id, corp_number, fei_number)
                inserted += 1

        except Exception as e:
            norm.action = "error"
            raw.status = "error"
            raw.error_message = str(e)[:300]
            errors += 1

    db.commit()

    return {
        "status": "success" if errors == 0 else "partial",
        "total_candidates": total_candidates,
        "batch_size": batch_size,
        "offset": offset,
        "processed": len(batch),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "has_more": (offset + batch_size) < total_candidates,
        "next_offset": offset + batch_size if (offset + batch_size) < total_candidates else None,
    }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _merge_fields(
    master: CompanyMaster,
    norm: CompanyStagingNormalized,
    entity_type: str | None,
    file_date: date | None,
) -> None:
    """Fill in missing fields on existing master record. Never overwrite."""
    if not master.jurisdiction_state and norm.jurisdiction_state:
        master.jurisdiction_state = norm.jurisdiction_state
    if not master.entity_type and entity_type:
        master.entity_type = entity_type
    if not master.formation_date and file_date:
        master.formation_date = file_date
    master.updated_at = datetime.now(timezone.utc)


def _add_provenance(
    db: Session,
    master_id: UUID,
    norm: CompanyStagingNormalized,
    raw: CompanyStagingRaw,
    payload: dict,
) -> None:
    corp_number = payload.get("corp_number", "")
    rec = CompanySourceRecord(
        company_master_id=master_id,
        source_name="florida_dos",
        source_record_id=corp_number or f"row_{raw.row_index}",
        source_url="https://dos.fl.gov/sunbiz/",
        raw_payload=payload,
    )
    db.add(rec)


def _add_external_ids(
    db: Session,
    master_id: UUID,
    corp_number: str,
    fei_number: str,
) -> None:
    """Add state_registry_id and optionally EIN. Skips if already exists."""
    if corp_number:
        exists = (
            db.query(CompanyExternalId)
            .filter(
                CompanyExternalId.company_master_id == master_id,
                CompanyExternalId.id_type == IdType.STATE_REGISTRY_ID,
                CompanyExternalId.id_value == corp_number,
            )
            .first()
        )
        if not exists:
            db.add(CompanyExternalId(
                company_master_id=master_id,
                id_type=IdType.STATE_REGISTRY_ID,
                id_value=corp_number,
                issuing_authority="FL_DOS",
                verified=True,
            ))

    fei_clean = fei_number.strip().replace("-", "") if fei_number else ""
    if fei_clean and len(fei_clean) >= 9 and fei_clean != "000000000":
        formatted = f"{fei_clean[:2]}-{fei_clean[2:]}"
        exists = (
            db.query(CompanyExternalId)
            .filter(
                CompanyExternalId.company_master_id == master_id,
                CompanyExternalId.id_type == IdType.EIN,
                CompanyExternalId.id_value == formatted,
            )
            .first()
        )
        if not exists:
            db.add(CompanyExternalId(
                company_master_id=master_id,
                id_type=IdType.EIN,
                id_value=formatted,
                issuing_authority="IRS",
                verified=False,
            ))


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _preview(batch, total_candidates, batch_size, offset) -> dict:
    """Dry-run preview of what would be imported."""
    records = []
    for norm, raw in batch:
        payload = raw.raw_payload or {}
        records.append({
            "legal_name": norm.legal_name,
            "normalized_name": norm.normalized_name,
            "action": norm.action,
            "filing_type": payload.get("filing_type"),
            "entity_type": payload.get("entity_type"),
            "corp_number": payload.get("corp_number"),
            "would_import": norm.action == "staged",
            "already_imported": norm.action in ("insert", "update"),
        })

    importable = sum(1 for r in records if r["would_import"])
    already = sum(1 for r in records if r["already_imported"])

    return {
        "status": "dry_run",
        "total_candidates": total_candidates,
        "batch_size": batch_size,
        "offset": offset,
        "batch_count": len(records),
        "would_import": importable,
        "already_imported": already,
        "records": records,
        "has_more": (offset + batch_size) < total_candidates,
    }

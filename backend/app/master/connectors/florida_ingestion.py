"""Florida DOS ingestion pipeline.

Orchestrates: parse fixed-width → stage raw → normalize → upsert
into the existing Company Master Index.

Reuses the existing staging tables (import_runs, company_staging_raw,
company_staging_normalized) and master tables (company_master,
company_external_ids, company_source_records).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.master.canonical import normalize_company_name, normalize_state_code
from app.master.models import CompanyAlias, CompanyExternalId, CompanyMaster, CompanySourceRecord
from app.master.staging_models import CompanyStagingNormalized, CompanyStagingRaw, ImportRun
from app.master.enrichment.base import IdType

from .florida import FloridaRecord, parse_file


def ingest_florida_file(
    db: Session,
    file_path: str,
    *,
    limit: int = 100,
    offset: int = 0,
    batch_id: str | None = None,
    active_only: bool = True,
    filing_types: set[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the full Florida ingestion pipeline.

    Args:
        db: database session
        file_path: path to Florida fixed-width data file
        limit: max companies to import (default 100)
        offset: skip first N records
        batch_id: optional batch identifier
        active_only: only import active corporations
        filing_types: filter by filing type (e.g., {"DOMP", "FLAL"})
        dry_run: if True, parse and show without writing to DB

    Returns summary dict.
    """
    if batch_id is None:
        batch_id = f"florida_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Parse records from file
    records = list(parse_file(
        file_path,
        limit=limit,
        offset=offset,
        active_only=active_only,
        filing_types=filing_types,
    ))

    if dry_run:
        return _dry_run_report(records, batch_id)

    # Create import run
    run = ImportRun(
        id=uuid4(),
        batch_id=batch_id,
        source_file=f"florida:{file_path.split('/')[-1] if '/' in file_path else file_path.split(chr(92))[-1]}",
        source_type="florida_sunbiz",
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        # Phase 1: Stage raw
        raw_count = _stage_raw(db, run, records)
        run.total_raw = raw_count
        db.commit()

        # Phase 2: Normalize
        norm_count = _normalize(db, run)
        run.total_normalized = norm_count
        db.commit()

        # Phase 3: Upsert into company_master
        inserted, updated, skipped, errors = _upsert(db, run)
        run.total_inserted = inserted
        run.total_updated = updated
        run.total_skipped = skipped
        run.total_errors = errors

        run.status = "success" if errors == 0 else "partial"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.error_message = str(e)[:500]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise

    return {
        "batch_id": run.batch_id,
        "import_run_id": str(run.id),
        "status": run.status,
        "total_raw": run.total_raw,
        "total_normalized": run.total_normalized,
        "total_inserted": run.total_inserted,
        "total_updated": run.total_updated,
        "total_skipped": run.total_skipped,
        "total_errors": run.total_errors,
    }


# ════════════════════════════════════════════════════════════════════
# Phase 1: Stage Raw
# ════════════════════════════════════════════════════════════════════

def _stage_raw(db: Session, run: ImportRun, records: list[FloridaRecord]) -> int:
    count = 0
    for i, rec in enumerate(records):
        raw = CompanyStagingRaw(
            import_run_id=run.id,
            row_index=i,
            raw_payload=rec.to_dict(),
            raw_name=rec.corp_name,
            raw_domain=None,  # Florida does not provide domains
            status="pending",
        )
        db.add(raw)
        count += 1

    db.flush()
    return count


# ════════════════════════════════════════════════════════════════════
# Phase 2: Normalize
# ════════════════════════════════════════════════════════════════════

def _normalize(db: Session, run: ImportRun) -> int:
    raws = (
        db.query(CompanyStagingRaw)
        .filter(
            CompanyStagingRaw.import_run_id == run.id,
            CompanyStagingRaw.status == "pending",
        )
        .order_by(CompanyStagingRaw.row_index)
        .all()
    )

    count = 0
    for raw in raws:
        if not raw.raw_name:
            raw.status = "skipped"
            raw.error_message = "no name"
            continue

        payload = raw.raw_payload or {}
        legal_name = raw.raw_name.strip()
        normalized_name = normalize_company_name(legal_name)

        if not normalized_name:
            raw.status = "skipped"
            raw.error_message = "empty after normalization"
            continue

        # Extract state from the structured field
        state = normalize_state_code(payload.get("location", "").split(",")[-1].strip()) if payload.get("location") else None
        # Florida records: principal state is in the payload
        if not state:
            raw_state = (raw.raw_payload or {}).get("location", "")
            if raw_state:
                parts = raw_state.split(",")
                if len(parts) >= 2:
                    state = normalize_state_code(parts[-1].strip())

        norm = CompanyStagingNormalized(
            import_run_id=run.id,
            staging_raw_id=raw.id,
            legal_name=legal_name,
            normalized_name=normalized_name,
            domain=None,  # Florida does not provide domains
            industry=None,
            location_raw=payload.get("location"),
            jurisdiction_state=state or "FL",  # Default to FL since source is Florida DOS
            source="florida_dos",
            action="pending",
        )
        db.add(norm)
        raw.status = "normalized"
        count += 1

    db.flush()
    return count


# ════════════════════════════════════════════════════════════════════
# Phase 3: Upsert
# ════════════════════════════════════════════════════════════════════

def _upsert(db: Session, run: ImportRun) -> tuple[int, int, int, int]:
    norms = (
        db.query(CompanyStagingNormalized)
        .filter(
            CompanyStagingNormalized.import_run_id == run.id,
            CompanyStagingNormalized.action == "pending",
        )
        .all()
    )

    inserted = 0
    updated = 0
    skipped = 0
    errors = 0
    seen_names: set[str] = set()

    for norm in norms:
        try:
            # Skip duplicates within batch
            if norm.normalized_name in seen_names:
                norm.action = "skip"
                norm.match_method = "duplicate_in_batch"
                skipped += 1
                continue
            seen_names.add(norm.normalized_name)

            # Try exact normalized name match
            existing = (
                db.query(CompanyMaster)
                .filter(CompanyMaster.normalized_name == norm.normalized_name)
                .first()
            )

            # Get raw record for provenance
            raw = (
                db.query(CompanyStagingRaw)
                .filter(CompanyStagingRaw.id == norm.staging_raw_id)
                .first()
            )
            payload = raw.raw_payload if raw else {}
            corp_number = payload.get("corp_number", "")
            entity_type = payload.get("entity_type")
            fei_number = payload.get("fei_number", "")
            file_date_str = payload.get("file_date")
            file_date = None
            if file_date_str:
                try:
                    from datetime import date as dt_date
                    file_date = dt_date.fromisoformat(file_date_str)
                except (ValueError, TypeError):
                    pass

            if existing:
                # Update: fill in missing fields
                if not existing.jurisdiction_state and norm.jurisdiction_state:
                    existing.jurisdiction_state = norm.jurisdiction_state
                if not existing.entity_type and entity_type:
                    existing.entity_type = entity_type
                if not existing.formation_date and file_date:
                    existing.formation_date = file_date
                existing.updated_at = datetime.now(timezone.utc)

                norm.matched_master_id = existing.id
                norm.match_method = "exact_normalized_name"
                norm.action = "update"
                _add_provenance(db, existing.id, norm, run, payload)
                _add_florida_external_id(db, existing.id, corp_number, fei_number)
                updated += 1
            else:
                # Insert new master record
                master = CompanyMaster(
                    legal_name=norm.legal_name,
                    normalized_name=norm.normalized_name,
                    entity_type=entity_type,
                    entity_status="active",
                    jurisdiction_state=norm.jurisdiction_state or "FL",
                    formation_date=file_date,
                    source_priority=40,       # official state registry → higher priority
                    source_confidence=0.80,   # official source → higher confidence
                )
                db.add(master)
                db.flush()

                norm.matched_master_id = master.id
                norm.match_method = "new"
                norm.action = "insert"

                _add_provenance(db, master.id, norm, run, payload)
                _add_florida_external_id(db, master.id, corp_number, fei_number)
                inserted += 1

        except Exception as e:
            norm.action = "error"
            errors += 1
            if raw:
                raw.status = "error"
                raw.error_message = str(e)[:300]

    db.flush()
    return inserted, updated, skipped, errors


def _add_provenance(
    db: Session, master_id, norm: CompanyStagingNormalized,
    run: ImportRun, payload: dict
) -> None:
    raw = (
        db.query(CompanyStagingRaw)
        .filter(CompanyStagingRaw.id == norm.staging_raw_id)
        .first()
    )
    rec = CompanySourceRecord(
        company_master_id=master_id,
        source_name=f"florida_dos:{run.source_file}",
        source_record_id=payload.get("corp_number"),
        source_url="https://dos.fl.gov/sunbiz/",
        raw_payload=payload,
    )
    db.add(rec)


def _add_florida_external_id(
    db: Session, master_id, corp_number: str, fei_number: str
) -> None:
    """Add state registry ID and optionally EIN from Florida record."""
    if corp_number:
        existing = (
            db.query(CompanyExternalId)
            .filter(
                CompanyExternalId.company_master_id == master_id,
                CompanyExternalId.id_type == IdType.STATE_REGISTRY_ID,
                CompanyExternalId.id_value == corp_number,
            )
            .first()
        )
        if not existing:
            db.add(CompanyExternalId(
                company_master_id=master_id,
                id_type=IdType.STATE_REGISTRY_ID,
                id_value=corp_number,
                issuing_authority="FL_DOS",
                verified=True,
            ))

    # EIN only if present and non-empty (secondary identifier)
    fei_clean = fei_number.strip().replace("-", "") if fei_number else ""
    if fei_clean and len(fei_clean) >= 9 and fei_clean != "000000000":
        formatted_ein = f"{fei_clean[:2]}-{fei_clean[2:]}" if "-" not in fei_number else fei_number.strip()
        existing = (
            db.query(CompanyExternalId)
            .filter(
                CompanyExternalId.company_master_id == master_id,
                CompanyExternalId.id_type == IdType.EIN,
                CompanyExternalId.id_value == formatted_ein,
            )
            .first()
        )
        if not existing:
            db.add(CompanyExternalId(
                company_master_id=master_id,
                id_type=IdType.EIN,
                id_value=formatted_ein,
                issuing_authority="IRS",
                verified=False,  # Derived from state filing, not IRS directly
            ))


# ════════════════════════════════════════════════════════════════════
# Dry Run
# ════════════════════════════════════════════════════════════════════

def _dry_run_report(records: list[FloridaRecord], batch_id: str) -> dict:
    entries = []
    for r in records[:20]:
        entries.append({
            "corp_number": r.corp_number,
            "corp_name": r.corp_name,
            "filing_type": r.filing_type,
            "entity_type": r.entity_type,
            "state": r.state,
            "city": r.city,
            "status": r.status,
            "file_date": r.file_date.isoformat() if r.file_date else None,
            "normalized": normalize_company_name(r.corp_name),
        })

    return {
        "status": "dry_run",
        "batch_id": batch_id,
        "total_parsed": len(records),
        "sample": entries,
        "remaining": max(0, len(records) - 20),
    }

"""Florida staging pipeline — parse raw file → stage → normalize.

Two-phase pipeline that reuses existing staging tables:
  Phase 1: Parse fixed-width → insert into company_staging_raw
  Phase 2: Normalize → insert into company_staging_normalized

NO upsert into company_master. That is a separate phase.
This module is for structured staging and inspection only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.master.canonical import normalize_company_name, normalize_state_code
from app.master.staging_models import CompanyStagingNormalized, CompanyStagingRaw, ImportRun

from .acquisition import RawAcquisitionLog
from .florida import FloridaRecord, parse_file


def stage_florida_file(
    db: Session,
    file_path: str,
    *,
    acquisition_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    active_only: bool = True,
    filing_types: set[str] | None = None,
    batch_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Parse a Florida file and stage records (no master index writes).

    Returns summary dict with counts and optional sample for dry_run.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if batch_id is None:
        batch_id = f"florida_stage_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Parse
    records = list(parse_file(
        file_path,
        limit=limit,
        offset=offset,
        active_only=active_only,
        filing_types=filing_types,
    ))

    if dry_run:
        return _dry_run_report(records, batch_id)

    # Create import run (staging only — total_inserted/updated stay 0)
    run = ImportRun(
        id=uuid4(),
        batch_id=batch_id,
        source_file=f"florida:{path.name}",
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
        norm_count, norm_stats = _normalize(db, run)
        run.total_normalized = norm_count
        run.total_skipped = norm_stats["skipped"]
        run.total_errors = norm_stats["errors"]

        run.status = "success" if norm_stats["errors"] == 0 else "partial"
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
        "status": run.status,
        "batch_id": run.batch_id,
        "import_run_id": str(run.id),
        "total_parsed": len(records),
        "total_raw": run.total_raw,
        "total_normalized": run.total_normalized,
        "total_skipped": run.total_skipped,
        "total_errors": run.total_errors,
        "note": "Staged only. Run Phase 3 to import into company_master.",
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
            raw_domain=None,
            status="pending",
        )
        db.add(raw)
        count += 1

    db.flush()
    return count


# ════════════════════════════════════════════════════════════════════
# Phase 2: Normalize
# ════════════════════════════════════════════════════════════════════

def _normalize(db: Session, run: ImportRun) -> tuple[int, dict]:
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
    skipped = 0
    errors = 0

    for raw in raws:
        if not raw.raw_name:
            raw.status = "skipped"
            raw.error_message = "no name"
            skipped += 1
            continue

        payload = raw.raw_payload or {}

        legal_name = raw.raw_name.strip()
        normalized_name = normalize_company_name(legal_name)

        if not normalized_name:
            raw.status = "skipped"
            raw.error_message = "empty after normalization"
            skipped += 1
            continue

        # State: use the effective_state from payload (already resolved in to_dict)
        raw_state = payload.get("state", "")
        jurisdiction = normalize_state_code(raw_state) if raw_state else None
        if not jurisdiction:
            jurisdiction = "FL"  # Source is Florida DOS

        # Location from structured fields
        city = payload.get("city", "")
        location_raw = f"{city}, {raw_state}" if city else raw_state

        norm = CompanyStagingNormalized(
            import_run_id=run.id,
            staging_raw_id=raw.id,
            legal_name=legal_name,
            normalized_name=normalized_name,
            domain=None,  # Florida does not provide domains
            industry=None,
            location_raw=location_raw or None,
            jurisdiction_state=jurisdiction,
            source="florida_dos",
            action="staged",  # NOT "pending" — we intentionally stop here
        )
        db.add(norm)
        raw.status = "normalized"
        count += 1

    db.flush()
    return count, {"skipped": skipped, "errors": errors}


# ════════════════════════════════════════════════════════════════════
# Inspection queries
# ════════════════════════════════════════════════════════════════════

def inspect_staged(
    db: Session,
    run_id: str | UUID,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Return staged normalized records for inspection."""
    norms = (
        db.query(CompanyStagingNormalized)
        .filter(CompanyStagingNormalized.import_run_id == run_id)
        .order_by(CompanyStagingNormalized.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for n in norms:
        raw = (
            db.query(CompanyStagingRaw)
            .filter(CompanyStagingRaw.id == n.staging_raw_id)
            .first()
        )
        payload = raw.raw_payload if raw else {}
        results.append({
            "legal_name": n.legal_name,
            "normalized_name": n.normalized_name,
            "jurisdiction_state": n.jurisdiction_state,
            "location_raw": n.location_raw,
            "action": n.action,
            "corp_number": payload.get("corp_number"),
            "filing_type": payload.get("filing_type"),
            "entity_type": payload.get("entity_type"),
            "fei_number": payload.get("fei_number"),
            "file_date": payload.get("file_date"),
            "city": payload.get("city"),
            "state": payload.get("state"),
            "agent_name": payload.get("agent_name"),
        })

    return results


def inspect_summary(db: Session, run_id: str | UUID) -> dict:
    """Summary stats for a staging run."""
    from sqlalchemy import func

    run = db.query(ImportRun).filter(ImportRun.id == run_id).first()
    if not run:
        return {"error": f"Run {run_id} not found"}

    # Filing type distribution
    norms = (
        db.query(CompanyStagingNormalized)
        .filter(CompanyStagingNormalized.import_run_id == run_id)
        .all()
    )
    raw_ids = [n.staging_raw_id for n in norms]
    raws = (
        db.query(CompanyStagingRaw)
        .filter(CompanyStagingRaw.id.in_(raw_ids))
        .all()
    ) if raw_ids else []

    by_type: dict[str, int] = {}
    by_state: dict[str, int] = {}
    with_fei = 0
    for r in raws:
        p = r.raw_payload or {}
        ft = p.get("filing_type", "unknown")
        by_type[ft] = by_type.get(ft, 0) + 1
        st = p.get("state", "?")
        by_state[st] = by_state.get(st, 0) + 1
        if p.get("fei_number"):
            with_fei += 1

    return {
        "import_run_id": str(run.id),
        "batch_id": run.batch_id,
        "status": run.status,
        "total_raw": run.total_raw,
        "total_normalized": run.total_normalized,
        "total_skipped": run.total_skipped,
        "by_filing_type": dict(sorted(by_type.items(), key=lambda x: -x[1])),
        "by_state": dict(sorted(by_state.items(), key=lambda x: -x[1])),
        "with_fei_number": with_fei,
    }


# ════════════════════════════════════════════════════════════════════
# Dry Run
# ════════════════════════════════════════════════════════════════════

def _dry_run_report(records: list[FloridaRecord], batch_id: str) -> dict:
    sample = []
    for r in records[:20]:
        sample.append({
            "corp_number": r.corp_number,
            "corp_name": r.corp_name,
            "normalized": normalize_company_name(r.corp_name),
            "filing_type": r.filing_type,
            "entity_type": r.entity_type,
            "city": r.clean_city,
            "state": r.effective_state,
            "status_code": r.status,
            "file_date": r.file_date.isoformat() if r.file_date else None,
            "fei": r.fei_number or None,
            "agent": r.agent_name[:30] if r.agent_name else None,
        })

    return {
        "status": "dry_run",
        "batch_id": batch_id,
        "total_parsed": len(records),
        "sample": sample,
        "remaining": max(0, len(records) - 20),
    }

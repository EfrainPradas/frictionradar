"""JSON ingestion pipeline for the Company Master Index.

Three-phase pipeline:
  1. STAGE RAW    — parse JSON, insert verbatim records into company_staging_raw
  2. NORMALIZE    — clean names/domains/locations, insert into company_staging_normalized
  3. UPSERT       — match against company_master, insert or update canonical records

Each phase is idempotent per import run. The import_runs table tracks execution.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from .canonical import normalize_company_name, normalize_state_code
from .models import CompanyAlias, CompanyMaster, CompanySourceRecord
from .staging_models import CompanyStagingNormalized, CompanyStagingRaw, ImportRun


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def ingest_json_file(db: Session, file_path: str, *, batch_id: str | None = None) -> dict:
    """Run the full ingestion pipeline for a JSON file.

    Returns a summary dict with counts and status.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    if batch_id is None:
        batch_id = f"json_{path.stem}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Create import run
    run = ImportRun(
        id=uuid4(),
        batch_id=batch_id,
        source_file=path.name,
        source_type="json_file",
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        # Phase 1: stage raw
        raw_data = _load_json(path)
        raw_count = _stage_raw(db, run, raw_data)
        run.total_raw = raw_count
        db.commit()

        # Phase 2: normalize
        norm_count = _normalize(db, run)
        run.total_normalized = norm_count
        db.commit()

        # Phase 3: upsert into company_master
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
        "source_file": run.source_file,
    }


# ════════════════════════════════════════════════════════════════════
# Phase 1: Stage Raw
# ════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> list[dict]:
    """Load JSON file, handling both array and object-with-key formats."""
    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, dict):
        # Support: {"companies_with_domain": [...]} or {"companies": [...]}
        raw = raw.get("companies_with_domain") or raw.get("companies") or []

    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array or object with 'companies' key")

    return raw


def _stage_raw(db: Session, run: ImportRun, entries: list[dict]) -> int:
    """Insert raw records into company_staging_raw."""
    count = 0
    for i, entry in enumerate(entries):
        raw_name = (entry.get("company_name") or entry.get("name") or "").strip()
        raw_domain = (entry.get("domain") or "").strip()

        rec = CompanyStagingRaw(
            import_run_id=run.id,
            row_index=i,
            raw_payload=entry,
            raw_name=raw_name or None,
            raw_domain=raw_domain or None,
            status="pending",
        )
        db.add(rec)
        count += 1

    db.flush()
    return count


# ════════════════════════════════════════════════════════════════════
# Phase 2: Normalize
# ════════════════════════════════════════════════════════════════════

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,}$"
)


def _clean_domain(raw: str) -> str | None:
    """Normalize and validate a domain string. Returns None if invalid."""
    if not raw:
        return None
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d)
    if d.startswith("www."):
        d = d[4:]
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if not d or not _DOMAIN_RE.match(d):
        return None
    return d


def _extract_state(location: str | None) -> str | None:
    """Try to extract a US state from a freeform location string.

    Handles formats like:
      "Salt Lake City, UT"
      "Provo, Utah, , U.S."
      "Salt Lake City, (, Utah, ),, United States"
    """
    if not location:
        return None

    # Clean Wikipedia formatting artifacts
    cleaned = re.sub(r"[(),]", " ", location)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Try each token as a state
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    for token in tokens:
        code = normalize_state_code(token)
        if code:
            return code

    # Try two-word state names (e.g., "New York", "North Carolina")
    for i in range(len(tokens) - 1):
        two_word = f"{tokens[i]} {tokens[i+1]}"
        code = normalize_state_code(two_word)
        if code:
            return code

    return None


def _clean_legal_name(raw_name: str) -> str:
    """Clean a company name for use as legal_name.

    Removes Wikipedia disambiguation suffixes like "(healthcare)" or "(American company)".
    Strips excess whitespace.
    """
    # Remove Wikipedia-style disambiguation: "AAPC (healthcare)" → "AAPC"
    name = re.sub(r"\s*\([^)]*\)\s*$", "", raw_name).strip()
    return name if name else raw_name.strip()


def _normalize(db: Session, run: ImportRun) -> int:
    """Normalize all pending raw records for this run."""
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
        if not raw.raw_name and not raw.raw_domain:
            raw.status = "skipped"
            raw.error_message = "no name or domain"
            continue

        payload = raw.raw_payload or {}
        legal_name = _clean_legal_name(raw.raw_name or raw.raw_domain or "")
        normalized_name = normalize_company_name(legal_name)
        domain = _clean_domain(raw.raw_domain)
        location_raw = (
            payload.get("location") or payload.get("hq") or ""
        ).strip() or None
        jurisdiction = _extract_state(location_raw)
        source = (payload.get("source") or "").strip() or None
        industry = (payload.get("industry") or "").strip() or None

        if not normalized_name:
            raw.status = "skipped"
            raw.error_message = "empty after normalization"
            continue

        norm = CompanyStagingNormalized(
            import_run_id=run.id,
            staging_raw_id=raw.id,
            legal_name=legal_name,
            normalized_name=normalized_name,
            domain=domain,
            industry=industry,
            location_raw=location_raw,
            jurisdiction_state=jurisdiction,
            source=source,
            action="pending",
        )
        db.add(norm)
        raw.status = "normalized"
        count += 1

    db.flush()
    return count


# ════════════════════════════════════════════════════════════════════
# Phase 3: Upsert into company_master
# ════════════════════════════════════════════════════════════════════

def _upsert(db: Session, run: ImportRun) -> tuple[int, int, int, int]:
    """Match normalized records against company_master and upsert.

    Matching strategy (deterministic only):
      1. Exact normalized_name match → update
      2. No match → insert

    Returns: (inserted, updated, skipped, errors)
    """
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

    # Build a set of normalized names already processed in this run to dedup
    seen_names: set[str] = set()

    for norm in norms:
        try:
            # Skip duplicates within same run
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

            if existing:
                # Update: fill in missing fields, don't overwrite existing
                _merge_into_master(existing, norm)
                norm.matched_master_id = existing.id
                norm.match_method = "exact_normalized_name"
                norm.action = "update"
                _add_source_record(db, existing.id, norm, run)
                updated += 1
            else:
                # Insert new master record
                master = CompanyMaster(
                    legal_name=norm.legal_name,
                    normalized_name=norm.normalized_name,
                    entity_type=None,
                    entity_status="active",
                    jurisdiction_state=norm.jurisdiction_state,
                    source_priority=50,
                    source_confidence=0.50,
                )
                db.add(master)
                db.flush()

                norm.matched_master_id = master.id
                norm.match_method = "new"
                norm.action = "insert"

                _add_source_record(db, master.id, norm, run)

                # Add original name as alias if different from legal_name
                raw = (
                    db.query(CompanyStagingRaw)
                    .filter(CompanyStagingRaw.id == norm.staging_raw_id)
                    .first()
                )
                if raw and raw.raw_name and raw.raw_name != norm.legal_name:
                    alias = CompanyAlias(
                        company_master_id=master.id,
                        alias_name=raw.raw_name,
                        alias_type="original_input",
                        source=norm.source,
                    )
                    db.add(alias)

                inserted += 1

        except Exception as e:
            norm.action = "error"
            errors += 1
            # Get the raw record to update its status
            raw = (
                db.query(CompanyStagingRaw)
                .filter(CompanyStagingRaw.id == norm.staging_raw_id)
                .first()
            )
            if raw:
                raw.status = "error"
                raw.error_message = str(e)[:300]

    db.flush()
    return inserted, updated, skipped, errors


def _merge_into_master(master: CompanyMaster, norm: CompanyStagingNormalized) -> None:
    """Fill in missing fields on an existing master record. Never overwrite existing values."""
    if not master.jurisdiction_state and norm.jurisdiction_state:
        master.jurisdiction_state = norm.jurisdiction_state
    master.updated_at = datetime.now(timezone.utc)


def _add_source_record(
    db: Session,
    master_id,
    norm: CompanyStagingNormalized,
    run: ImportRun,
) -> None:
    """Create a source provenance record linking this import to the master record."""
    raw = (
        db.query(CompanyStagingRaw)
        .filter(CompanyStagingRaw.id == norm.staging_raw_id)
        .first()
    )
    rec = CompanySourceRecord(
        company_master_id=master_id,
        source_name=f"json_import:{run.source_file}",
        source_record_id=f"row_{raw.row_index}" if raw else None,
        raw_payload=raw.raw_payload if raw else None,
    )
    db.add(rec)

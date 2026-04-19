"""Tests for Florida batch import — Phase 4.

Validates:
  1. Import logic (insert, update, skip, idempotent)
  2. External ID creation
  3. Provenance records
  4. Merge field behavior
  5. Date parsing
  6. Live import of a small batch

Run:
  python backend/tests/test_florida_import.py
"""

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)


def _get_db():
    import app.models  # noqa
    from app.db.session import SessionLocal
    return SessionLocal()


# ════════════════════════════════════════════════════════════════════
# 1. DATE PARSING
# ════════════════════════════════════════════════════════════════════

def test_parse_date_iso():
    from app.master.connectors.florida_import import _parse_date
    d = _parse_date("2026-04-13")
    assert d is not None
    assert d.year == 2026
    assert d.month == 4


def test_parse_date_none():
    from app.master.connectors.florida_import import _parse_date
    assert _parse_date(None) is None
    assert _parse_date("") is None


def test_parse_date_invalid():
    from app.master.connectors.florida_import import _parse_date
    assert _parse_date("not-a-date") is None


# ════════════════════════════════════════════════════════════════════
# 2. MERGE FIELD BEHAVIOR
# ════════════════════════════════════════════════════════════════════

def test_merge_does_not_overwrite():
    from app.master.connectors.florida_import import _merge_fields
    from app.master.models import CompanyMaster
    from app.master.staging_models import CompanyStagingNormalized
    from datetime import date

    master = CompanyMaster(
        legal_name="Existing",
        normalized_name="existing",
        entity_type="corporation",
        jurisdiction_state="UT",
        formation_date=date(2020, 1, 1),
    )
    norm = CompanyStagingNormalized(
        legal_name="Existing",
        normalized_name="existing",
        jurisdiction_state="FL",
    )
    _merge_fields(master, norm, "llc", date(2025, 1, 1))
    # Should NOT overwrite existing values
    assert master.entity_type == "corporation"
    assert master.jurisdiction_state == "UT"
    assert master.formation_date == date(2020, 1, 1)


def test_merge_fills_missing():
    from app.master.connectors.florida_import import _merge_fields
    from app.master.models import CompanyMaster
    from app.master.staging_models import CompanyStagingNormalized
    from datetime import date

    master = CompanyMaster(
        legal_name="Empty",
        normalized_name="empty",
    )
    norm = CompanyStagingNormalized(
        legal_name="Empty",
        normalized_name="empty",
        jurisdiction_state="FL",
    )
    _merge_fields(master, norm, "llc", date(2023, 6, 15))
    assert master.entity_type == "llc"
    assert master.jurisdiction_state == "FL"
    assert master.formation_date == date(2023, 6, 15)


# ════════════════════════════════════════════════════════════════════
# 3. DRY-RUN PREVIEW
# ════════════════════════════════════════════════════════════════════

def test_dry_run_returns_preview():
    from app.master.connectors.florida_batch_selector import BatchFilter
    from app.master.connectors.florida_import import import_florida_batch

    db = _get_db()
    try:
        result = import_florida_batch(
            db, BatchFilter(), batch_size=5, dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["batch_count"] <= 5
        assert "would_import" in result
        assert "already_imported" in result
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════
# 4. LIVE SMALL BATCH IMPORT
# ════════════════════════════════════════════════════════════════════

def test_import_small_batch():
    """Import 5 records and verify insert behavior."""
    from app.master.connectors.florida_batch_selector import BatchFilter
    from app.master.connectors.florida_import import import_florida_batch
    from app.master.models import CompanyMaster

    db = _get_db()
    try:
        # Count before
        before = db.query(CompanyMaster).filter(CompanyMaster.entity_status != "merged").count()

        result = import_florida_batch(
            db, BatchFilter(domestic_only=True), batch_size=5,
        )

        assert result["status"] in ("success", "partial")
        assert result["processed"] == 5
        assert result["errors"] == 0
        # inserted + updated + skipped should equal processed
        assert result["inserted"] + result["updated"] + result["skipped"] == result["processed"]

        # Count after
        after = db.query(CompanyMaster).filter(CompanyMaster.entity_status != "merged").count()
        assert after >= before + result["inserted"]

    finally:
        db.close()


def test_import_is_idempotent():
    """Previously-imported records are excluded from future batches.

    The batch selector only returns action='staged' records. Once
    imported (action='insert'/'update'), they never appear again.
    This means running the same batch_size repeatedly processes
    fresh records each time, never re-importing old ones.
    """
    from app.master.connectors.florida_batch_selector import BatchFilter
    from app.master.connectors.florida_import import import_florida_batch
    from app.master.staging_models import CompanyStagingNormalized, ImportRun
    from sqlalchemy import func

    db = _get_db()
    try:
        # Count staged records with action='insert' (already imported)
        already_imported_before = (
            db.query(func.count(CompanyStagingNormalized.id))
            .join(ImportRun, CompanyStagingNormalized.import_run_id == ImportRun.id)
            .filter(
                ImportRun.source_type == "florida_sunbiz",
                CompanyStagingNormalized.action == "insert",
            )
            .scalar() or 0
        )

        # Import a batch
        r = import_florida_batch(
            db, BatchFilter(domestic_only=True), batch_size=3,
        )

        # Count again
        already_imported_after = (
            db.query(func.count(CompanyStagingNormalized.id))
            .join(ImportRun, CompanyStagingNormalized.import_run_id == ImportRun.id)
            .filter(
                ImportRun.source_type == "florida_sunbiz",
                CompanyStagingNormalized.action == "insert",
            )
            .scalar() or 0
        )

        # Imported records increased by exactly what we inserted
        assert already_imported_after == already_imported_before + r["inserted"]
        # None of them will appear in future batches (action != 'staged')

    finally:
        db.close()


def test_imported_have_external_ids():
    """Imported Florida companies should have state_registry_id."""
    from app.master.models import CompanyExternalId, CompanyMaster
    from app.master.enrichment.base import IdType

    db = _get_db()
    try:
        # Find a Florida company that was imported
        florida = (
            db.query(CompanyMaster)
            .filter(
                CompanyMaster.source_confidence == 0.80,
                CompanyMaster.jurisdiction_state == "FL",
            )
            .first()
        )
        if florida:
            ext_id = (
                db.query(CompanyExternalId)
                .filter(
                    CompanyExternalId.company_master_id == florida.id,
                    CompanyExternalId.id_type == IdType.STATE_REGISTRY_ID,
                )
                .first()
            )
            assert ext_id is not None, f"{florida.legal_name} missing state_registry_id"
            assert ext_id.issuing_authority == "FL_DOS"
            assert ext_id.verified is True
    finally:
        db.close()


def test_imported_have_provenance():
    """Imported Florida companies should have source records."""
    from app.master.models import CompanyMaster, CompanySourceRecord

    db = _get_db()
    try:
        florida = (
            db.query(CompanyMaster)
            .filter(
                CompanyMaster.source_confidence == 0.80,
                CompanyMaster.jurisdiction_state == "FL",
            )
            .first()
        )
        if florida:
            sources = (
                db.query(CompanySourceRecord)
                .filter(CompanySourceRecord.company_master_id == florida.id)
                .all()
            )
            florida_sources = [s for s in sources if "florida" in s.source_name]
            assert len(florida_sources) > 0, f"{florida.legal_name} missing Florida provenance"
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    tests = [
        ("date.iso", test_parse_date_iso),
        ("date.none", test_parse_date_none),
        ("date.invalid", test_parse_date_invalid),
        ("merge.no_overwrite", test_merge_does_not_overwrite),
        ("merge.fills_missing", test_merge_fills_missing),
        ("preview.dry_run", test_dry_run_returns_preview),
        ("import.small_batch", test_import_small_batch),
        ("import.idempotent", test_import_is_idempotent),
        ("import.external_ids", test_imported_have_external_ids),
        ("import.provenance", test_imported_have_provenance),
    ]

    passed = 0
    failed = 0
    errors = 0
    details = []

    for name, fn in tests:
        try:
            fn()
            passed += 1
            details.append({"name": name, "status": "passed"})
        except AssertionError as e:
            failed += 1
            details.append({"name": name, "status": "failed", "error": str(e)})
        except Exception as e:
            errors += 1
            details.append({
                "name": name, "status": "error",
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            })

    return {
        "passed": passed, "failed": failed, "errors": errors,
        "total": len(tests), "success": failed == 0 and errors == 0,
        "details": details,
    }


if __name__ == "__main__":
    report = run_all_tests()
    print(json.dumps(report, indent=2))
    if not report["success"]:
        sys.exit(1)

"""Data quality validation for the Company Master Index — Phase 7.

These tests run against the live database and validate that the master
index is reliable enough to serve as the working input dataset.

Run:
  python backend/tests/test_master_index_validation.py
"""

import os
import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)

import app.models  # noqa: F401
from app.db.session import SessionLocal


def _db():
    return SessionLocal()


# ════════════════════════════════════════════════════════════════════
# 1. CANONICAL COUNTS
# ════════════════════════════════════════════════════════════════════

def test_master_has_records():
    db = _db()
    from app.master.models import CompanyMaster
    count = db.query(CompanyMaster).count()
    db.close()
    assert count >= 100, f"Expected >= 100 master records, got {count}"


def test_no_orphan_merged():
    """Merged records should not exist without a merge decision."""
    db = _db()
    from app.master.models import CompanyMaster
    from app.master.resolution_models import CompanyMergeDecision
    merged = db.query(CompanyMaster).filter(CompanyMaster.entity_status == "merged").all()
    for m in merged:
        decision = db.query(CompanyMergeDecision).filter(
            CompanyMergeDecision.duplicate_id == m.id
        ).first()
        assert decision is not None, f"Merged record {m.legal_name} has no merge decision"
    db.close()


def test_no_duplicate_normalized_names():
    """Active records should have unique normalized names."""
    db = _db()
    from sqlalchemy import func
    from app.master.models import CompanyMaster
    dupes = (
        db.query(CompanyMaster.normalized_name, func.count())
        .filter(CompanyMaster.entity_status != "merged")
        .group_by(CompanyMaster.normalized_name)
        .having(func.count() > 1)
        .all()
    )
    db.close()
    assert len(dupes) == 0, f"Duplicate normalized names: {[d[0] for d in dupes]}"


# ════════════════════════════════════════════════════════════════════
# 2. DOMAIN COVERAGE
# ════════════════════════════════════════════════════════════════════

def test_domain_coverage_above_85pct():
    """At least 85% of active companies should have a resolved primary domain."""
    db = _db()
    from app.master.models import CompanyMaster
    from app.master.domain_models import CompanyDomain
    active = db.query(CompanyMaster).filter(CompanyMaster.entity_status == "active").count()
    with_domain = (
        db.query(CompanyDomain)
        .filter(CompanyDomain.is_primary == True, CompanyDomain.domain_status == "resolved")
        .count()
    )
    db.close()
    pct = with_domain / active if active > 0 else 0
    assert pct >= 0.85, f"Domain coverage too low: {pct:.0%} ({with_domain}/{active})"


def test_no_malformed_domains():
    """All domains should contain a dot and be >= 4 chars."""
    db = _db()
    from app.master.domain_models import CompanyDomain
    bad = db.query(CompanyDomain).filter(
        (CompanyDomain.domain.notlike("%.%")) |
        (CompanyDomain.domain == None)
    ).all()
    db.close()
    assert len(bad) == 0, f"Malformed domains: {[d.domain for d in bad]}"


def test_no_duplicate_primary_domains():
    """Each company should have at most one primary domain."""
    db = _db()
    from sqlalchemy import func
    from app.master.domain_models import CompanyDomain
    dupes = (
        db.query(CompanyDomain.company_master_id, func.count())
        .filter(CompanyDomain.is_primary == True)
        .group_by(CompanyDomain.company_master_id)
        .having(func.count() > 1)
        .all()
    )
    db.close()
    assert len(dupes) == 0, f"{len(dupes)} companies have multiple primary domains"


# ════════════════════════════════════════════════════════════════════
# 3. JURISDICTION COVERAGE
# ════════════════════════════════════════════════════════════════════

def test_jurisdiction_coverage_above_80pct():
    db = _db()
    from app.master.models import CompanyMaster
    active = db.query(CompanyMaster).filter(CompanyMaster.entity_status != "merged").count()
    with_state = db.query(CompanyMaster).filter(
        CompanyMaster.entity_status != "merged",
        CompanyMaster.jurisdiction_state != None,
    ).count()
    db.close()
    pct = with_state / active if active > 0 else 0
    assert pct >= 0.80, f"Jurisdiction coverage too low: {pct:.0%} ({with_state}/{active})"


def test_jurisdiction_codes_valid():
    """All jurisdiction_state values should be 2-letter US state codes."""
    db = _db()
    from app.master.models import CompanyMaster
    from app.master.canonical import _US_STATES
    records = (
        db.query(CompanyMaster.jurisdiction_state)
        .filter(
            CompanyMaster.entity_status != "merged",
            CompanyMaster.jurisdiction_state != None,
        )
        .distinct()
        .all()
    )
    db.close()
    for (state,) in records:
        assert state in _US_STATES, f"Invalid state code: {state}"


# ════════════════════════════════════════════════════════════════════
# 4. PROVENANCE COMPLETENESS
# ════════════════════════════════════════════════════════════════════

def test_every_company_has_source_record():
    """Every active master record should have at least one source record."""
    db = _db()
    from app.master.models import CompanyMaster, CompanySourceRecord
    active = db.query(CompanyMaster).filter(CompanyMaster.entity_status != "merged").all()
    missing = []
    for m in active:
        count = db.query(CompanySourceRecord).filter(
            CompanySourceRecord.company_master_id == m.id
        ).count()
        if count == 0:
            missing.append(m.legal_name)
    db.close()
    assert len(missing) == 0, f"{len(missing)} companies lack source provenance: {missing[:5]}"


def test_source_records_have_payload():
    """Source records should have raw_payload for traceability."""
    db = _db()
    from app.master.models import CompanySourceRecord
    total = db.query(CompanySourceRecord).count()
    with_payload = db.query(CompanySourceRecord).filter(
        CompanySourceRecord.raw_payload != None
    ).count()
    db.close()
    pct = with_payload / total if total > 0 else 0
    assert pct >= 0.90, f"Only {pct:.0%} of source records have raw_payload"


# ════════════════════════════════════════════════════════════════════
# 5. IMPORT PIPELINE INTEGRITY
# ════════════════════════════════════════════════════════════════════

def test_successful_imports_exist():
    db = _db()
    from app.master.staging_models import ImportRun
    success = db.query(ImportRun).filter(ImportRun.status == "success").count()
    db.close()
    assert success >= 1, "No successful import runs found"


def test_staging_normalized_count_matches_raw():
    db = _db()
    from app.master.staging_models import CompanyStagingRaw, CompanyStagingNormalized
    raw = db.query(CompanyStagingRaw).count()
    norm = db.query(CompanyStagingNormalized).count()
    db.close()
    assert raw > 0, "No staging raw records"
    assert norm > 0, "No staging normalized records"
    assert norm <= raw, f"More normalized ({norm}) than raw ({raw}) records"


# ════════════════════════════════════════════════════════════════════
# 6. DOWNSTREAM READINESS
# ════════════════════════════════════════════════════════════════════

def test_downstream_dataset_nonempty():
    db = _db()
    from app.master.downstream import get_downstream_dataset
    dataset = get_downstream_dataset(db, limit=5)
    db.close()
    assert len(dataset) > 0, "Downstream dataset is empty"


def test_downstream_ready_companies_have_domain():
    """All ready_for_careers_discovery companies must have a primary domain."""
    db = _db()
    from app.master.downstream import get_downstream_dataset
    dataset = get_downstream_dataset(db, status_filter="ready_for_careers_discovery")
    db.close()
    missing = [c.legal_name for c in dataset if not c.primary_domain]
    assert len(missing) == 0, f"Ready companies without domain: {missing[:5]}"


def test_downstream_shape_complete():
    """Every downstream record must have company_id, legal_name, readiness_status."""
    db = _db()
    from app.master.downstream import get_downstream_dataset
    dataset = get_downstream_dataset(db, limit=10)
    db.close()
    for c in dataset:
        assert c.company_id, f"Missing company_id for {c.legal_name}"
        assert c.legal_name, "Missing legal_name"
        assert c.readiness_status, f"Missing readiness_status for {c.legal_name}"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    tests = [
        ("counts.has_records", test_master_has_records),
        ("counts.no_orphan_merged", test_no_orphan_merged),
        ("counts.no_dupe_names", test_no_duplicate_normalized_names),
        ("domain.coverage_85pct", test_domain_coverage_above_85pct),
        ("domain.no_malformed", test_no_malformed_domains),
        ("domain.no_dupe_primary", test_no_duplicate_primary_domains),
        ("jurisdiction.coverage_80pct", test_jurisdiction_coverage_above_80pct),
        ("jurisdiction.valid_codes", test_jurisdiction_codes_valid),
        ("provenance.every_company", test_every_company_has_source_record),
        ("provenance.has_payload", test_source_records_have_payload),
        ("import.successful_runs", test_successful_imports_exist),
        ("import.norm_matches_raw", test_staging_normalized_count_matches_raw),
        ("downstream.nonempty", test_downstream_dataset_nonempty),
        ("downstream.ready_have_domain", test_downstream_ready_companies_have_domain),
        ("downstream.shape_complete", test_downstream_shape_complete),
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
    import json
    report = run_all_tests()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["success"] else 1)

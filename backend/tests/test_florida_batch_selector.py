"""Tests for Florida batch selector — Phase 3.

Validates:
  1. BatchFilter defaults and construction
  2. Filter description generation
  3. Filing type classification constants
  4. Dedup check logic
  5. Batch slicing behavior
  6. Live data queries (if DB available)

Run:
  python backend/tests/test_florida_batch_selector.py
"""

import json
import os
import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. FILTER CONSTRUCTION
# ════════════════════════════════════════════════════════════════════

def test_filter_defaults():
    from app.master.connectors.florida_batch_selector import BatchFilter
    f = BatchFilter()
    assert f.entity_types is None
    assert f.domestic_only is False
    assert f.exclude_irrelevant is True
    assert f.has_fei is False
    assert f.state is None


def test_filter_custom():
    from app.master.connectors.florida_batch_selector import BatchFilter
    f = BatchFilter(
        entity_types={"corporation", "llc"},
        domestic_only=True,
        state="FL",
    )
    assert "corporation" in f.entity_types
    assert f.domestic_only is True
    assert f.state == "FL"


# ════════════════════════════════════════════════════════════════════
# 2. FILTER DESCRIPTION
# ════════════════════════════════════════════════════════════════════

def test_describe_default_filters():
    from app.master.connectors.florida_batch_selector import BatchFilter, _describe_filters
    desc = _describe_filters(BatchFilter())
    assert "exclude AGENT/TRUST" in desc


def test_describe_domestic():
    from app.master.connectors.florida_batch_selector import BatchFilter, _describe_filters
    desc = _describe_filters(BatchFilter(domestic_only=True))
    assert any("domestic" in d for d in desc)


def test_describe_entity_types():
    from app.master.connectors.florida_batch_selector import BatchFilter, _describe_filters
    desc = _describe_filters(BatchFilter(entity_types={"llc"}))
    assert any("llc" in d for d in desc)


def test_describe_no_filters():
    from app.master.connectors.florida_batch_selector import BatchFilter, _describe_filters
    desc = _describe_filters(BatchFilter(exclude_irrelevant=False))
    assert "(no filters)" in desc


# ════════════════════════════════════════════════════════════════════
# 3. FILING TYPE CONSTANTS
# ════════════════════════════════════════════════════════════════════

def test_domestic_types():
    from app.master.connectors.florida_batch_selector import DOMESTIC_FILING_TYPES
    assert "DOMP" in DOMESTIC_FILING_TYPES
    assert "FLAL" in DOMESTIC_FILING_TYPES
    assert "FORP" not in DOMESTIC_FILING_TYPES


def test_foreign_types():
    from app.master.connectors.florida_batch_selector import FOREIGN_FILING_TYPES
    assert "FORP" in FOREIGN_FILING_TYPES
    assert "FORL" in FOREIGN_FILING_TYPES
    assert "DOMP" not in FOREIGN_FILING_TYPES


def test_irrelevant_types():
    from app.master.connectors.florida_batch_selector import IRRELEVANT_FILING_TYPES
    assert "AGENT" in IRRELEVANT_FILING_TYPES
    assert "TRUST" in IRRELEVANT_FILING_TYPES
    assert len(IRRELEVANT_FILING_TYPES) == 2


def test_no_overlap_domestic_foreign():
    from app.master.connectors.florida_batch_selector import DOMESTIC_FILING_TYPES, FOREIGN_FILING_TYPES
    assert not DOMESTIC_FILING_TYPES & FOREIGN_FILING_TYPES


# ════════════════════════════════════════════════════════════════════
# 4. LIVE DATA QUERIES
# ════════════════════════════════════════════════════════════════════

def _get_db():
    import app.models  # noqa
    from app.db.session import SessionLocal
    return SessionLocal()


def test_stats_returns_data():
    from app.master.connectors.florida_batch_selector import get_filter_stats
    db = _get_db()
    try:
        stats = get_filter_stats(db)
        assert stats["total_staged"] > 0, "No staged Florida data"
        assert "by_entity_type" in stats
        assert "by_filing_type" in stats
        assert stats["after_exclude_irrelevant"] <= stats["total_staged"]
    finally:
        db.close()


def test_select_default_batch():
    from app.master.connectors.florida_batch_selector import BatchFilter, select_batch
    db = _get_db()
    try:
        result = select_batch(db, BatchFilter(), batch_size=10)
        assert result["batch_count"] <= 10
        assert result["total_candidates"] > 0
        assert result["batch_count"] > 0
        for r in result["records"]:
            assert r["legal_name"]
            assert r["normalized_name"]
            assert "existing_in_master" in r
    finally:
        db.close()


def test_select_domestic_only():
    from app.master.connectors.florida_batch_selector import BatchFilter, select_batch
    db = _get_db()
    try:
        result = select_batch(db, BatchFilter(domestic_only=True), batch_size=20)
        for r in result["records"]:
            assert r["filing_type"] in ("DOMP", "DOMNP", "DOMLP", "FLAL"), \
                f"Non-domestic filing type: {r['filing_type']}"
    finally:
        db.close()


def test_select_entity_type_filter():
    from app.master.connectors.florida_batch_selector import BatchFilter, select_batch
    db = _get_db()
    try:
        result = select_batch(db, BatchFilter(entity_types={"corporation"}), batch_size=20)
        for r in result["records"]:
            assert r["entity_type"] == "corporation", f"Wrong type: {r['entity_type']}"
    finally:
        db.close()


def test_select_with_offset():
    from app.master.connectors.florida_batch_selector import BatchFilter, select_batch
    db = _get_db()
    try:
        first = select_batch(db, BatchFilter(), batch_size=5, offset=0)
        second = select_batch(db, BatchFilter(), batch_size=5, offset=5)
        first_names = {r["normalized_name"] for r in first["records"]}
        second_names = {r["normalized_name"] for r in second["records"]}
        assert not first_names & second_names, "Offset pages should not overlap"
    finally:
        db.close()


def test_select_excludes_irrelevant():
    from app.master.connectors.florida_batch_selector import BatchFilter, select_batch
    db = _get_db()
    try:
        result = select_batch(db, BatchFilter(exclude_irrelevant=True), batch_size=500)
        for r in result["records"]:
            assert r["filing_type"] not in ("AGENT", "TRUST"), \
                f"Irrelevant type not excluded: {r['filing_type']}"
    finally:
        db.close()


def test_dedup_check_runs():
    from app.master.connectors.florida_batch_selector import BatchFilter, select_batch
    db = _get_db()
    try:
        result = select_batch(db, BatchFilter(), batch_size=10, check_duplicates=True)
        # Should have the field even if no duplicates
        for r in result["records"]:
            assert "existing_in_master" in r
    finally:
        db.close()


def test_has_more_flag():
    from app.master.connectors.florida_batch_selector import BatchFilter, select_batch
    db = _get_db()
    try:
        result = select_batch(db, BatchFilter(), batch_size=5)
        if result["total_candidates"] > 5:
            assert result["has_more"] is True
            assert result["next_offset"] == 5
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    tests = [
        ("filter.defaults", test_filter_defaults),
        ("filter.custom", test_filter_custom),
        ("desc.default", test_describe_default_filters),
        ("desc.domestic", test_describe_domestic),
        ("desc.entity_types", test_describe_entity_types),
        ("desc.no_filters", test_describe_no_filters),
        ("const.domestic", test_domestic_types),
        ("const.foreign", test_foreign_types),
        ("const.irrelevant", test_irrelevant_types),
        ("const.no_overlap", test_no_overlap_domestic_foreign),
        ("live.stats", test_stats_returns_data),
        ("live.default_batch", test_select_default_batch),
        ("live.domestic_only", test_select_domestic_only),
        ("live.entity_type", test_select_entity_type_filter),
        ("live.offset", test_select_with_offset),
        ("live.excludes_irrelevant", test_select_excludes_irrelevant),
        ("live.dedup_check", test_dedup_check_runs),
        ("live.has_more", test_has_more_flag),
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

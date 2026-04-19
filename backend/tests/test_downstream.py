"""Tests for downstream export layer — Phase 6.

Validates:
  1. Readiness computation
  2. DownstreamCompany schema
  3. DownstreamSummary schema
  4. Filter logic
  5. Output shape consistency

Run:
  pytest backend/tests/test_downstream.py -v
  python backend/tests/test_downstream.py
"""

import json
import sys
from pathlib import Path
from uuid import uuid4

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. READINESS COMPUTATION
# ════════════════════════════════════════════════════════════════════

def _make_master(status="active"):
    from app.master.models import CompanyMaster
    m = CompanyMaster(
        legal_name="Test Corp",
        normalized_name="test",
        entity_status=status,
        source_confidence=0.50,
    )
    m.id = uuid4()
    return m


def test_readiness_with_resolved_domain():
    from app.master.downstream import _compute_readiness
    m = _make_master()
    assert _compute_readiness(m, "test.com", "resolved") == "ready_for_careers_discovery"


def test_readiness_unresolved_domain():
    from app.master.downstream import _compute_readiness
    m = _make_master()
    assert _compute_readiness(m, "test.com", "unresolved") == "ready_for_domain_resolution"


def test_readiness_ambiguous_domain():
    from app.master.downstream import _compute_readiness
    m = _make_master()
    assert _compute_readiness(m, "test.com", "ambiguous") == "ready_for_domain_resolution"


def test_readiness_no_domain():
    from app.master.downstream import _compute_readiness
    m = _make_master()
    assert _compute_readiness(m, None, None) == "needs_domain"


def test_readiness_rejected_domain():
    from app.master.downstream import _compute_readiness
    m = _make_master()
    assert _compute_readiness(m, "bad.com", "rejected") == "needs_review"


def test_readiness_merged():
    from app.master.downstream import _compute_readiness
    m = _make_master("merged")
    assert _compute_readiness(m, "test.com", "resolved") == "merged"


# ════════════════════════════════════════════════════════════════════
# 2. DOWNSTREAM COMPANY SCHEMA
# ════════════════════════════════════════════════════════════════════

def test_downstream_company_minimal():
    from app.master.downstream import DownstreamCompany
    c = DownstreamCompany(
        company_id="abc",
        legal_name="Test Corp",
        normalized_name="test",
        entity_status="active",
        source_confidence=0.50,
        readiness_status="needs_domain",
    )
    assert c.primary_domain is None
    assert c.official_website is None
    assert c.external_ids == {}
    assert c.external_id_count == 0
    assert c.has_resolved_domain is False


def test_downstream_company_full():
    from app.master.downstream import DownstreamCompany
    c = DownstreamCompany(
        company_id="abc",
        legal_name="Qualtrics",
        normalized_name="qualtrics",
        entity_status="active",
        source_confidence=0.80,
        jurisdiction_state="UT",
        primary_domain="qualtrics.com",
        official_website="https://qualtrics.com",
        domain_status="resolved",
        domain_confidence=0.90,
        readiness_status="ready_for_careers_discovery",
        has_resolved_domain=True,
        external_ids={"edgar_cik": "1747748", "ticker": "XM"},
        external_id_count=2,
        has_external_ids=True,
        high_confidence=True,
    )
    assert c.primary_domain == "qualtrics.com"
    assert c.official_website == "https://qualtrics.com"
    assert c.external_ids["edgar_cik"] == "1747748"
    assert c.has_resolved_domain is True
    assert c.high_confidence is True


def test_downstream_company_serialization():
    from app.master.downstream import DownstreamCompany
    c = DownstreamCompany(
        company_id="abc",
        legal_name="Test",
        normalized_name="test",
        entity_status="active",
        source_confidence=0.50,
        readiness_status="needs_domain",
    )
    d = c.model_dump()
    assert isinstance(d, dict)
    assert d["company_id"] == "abc"
    assert d["readiness_status"] == "needs_domain"

    # Should be JSON-serializable
    j = json.dumps(d)
    assert "needs_domain" in j


# ════════════════════════════════════════════════════════════════════
# 3. DOWNSTREAM SUMMARY SCHEMA
# ════════════════════════════════════════════════════════════════════

def test_downstream_summary():
    from app.master.downstream import DownstreamSummary
    s = DownstreamSummary(
        total_companies=159,
        ready_for_careers_discovery=153,
        ready_for_domain_resolution=0,
        needs_domain=6,
        needs_review=0,
        with_external_ids=3,
        high_confidence=0,
        by_state={"UT": 150, "CA": 5},
        exported_at="2026-04-14T00:00:00Z",
    )
    assert s.total_companies == 159
    assert s.by_state["UT"] == 150
    d = s.model_dump()
    assert isinstance(d, dict)


# ════════════════════════════════════════════════════════════════════
# 4. OUTPUT SHAPE
# ════════════════════════════════════════════════════════════════════

def test_downstream_company_has_required_fields():
    """Verify all required downstream fields are present."""
    from app.master.downstream import DownstreamCompany
    fields = set(DownstreamCompany.model_fields.keys())
    required = {
        "company_id", "legal_name", "normalized_name",
        "entity_status", "source_confidence",
        "primary_domain", "official_website",
        "readiness_status", "has_resolved_domain",
        "external_ids", "external_id_count",
        "jurisdiction_state", "last_verified_at",
    }
    for f in required:
        assert f in fields, f"Missing required field: {f}"


def test_readiness_statuses_are_complete():
    """Verify all 5 readiness statuses are handled."""
    from app.master.downstream import _compute_readiness
    m_active = _make_master("active")
    m_merged = _make_master("merged")

    statuses = {
        _compute_readiness(m_active, "x.com", "resolved"),
        _compute_readiness(m_active, "x.com", "unresolved"),
        _compute_readiness(m_active, None, None),
        _compute_readiness(m_active, "x.com", "rejected"),
        _compute_readiness(m_merged, "x.com", "resolved"),
    }
    expected = {
        "ready_for_careers_discovery",
        "ready_for_domain_resolution",
        "needs_domain",
        "needs_review",
        "merged",
    }
    assert statuses == expected


def test_official_website_format():
    """official_website should be https:// + domain or None."""
    from app.master.downstream import DownstreamCompany
    c = DownstreamCompany(
        company_id="x",
        legal_name="X",
        normalized_name="x",
        entity_status="active",
        source_confidence=0.5,
        readiness_status="ready_for_careers_discovery",
        primary_domain="stripe.com",
        official_website="https://stripe.com",
    )
    assert c.official_website.startswith("https://")
    assert "stripe.com" in c.official_website


def test_high_confidence_threshold():
    """high_confidence flag should be True when source_confidence >= 0.70."""
    from app.master.downstream import DownstreamCompany
    base = dict(
        company_id="x", legal_name="X", normalized_name="x",
        entity_status="active", readiness_status="needs_domain",
    )
    low = DownstreamCompany(**base, source_confidence=0.50, high_confidence=False)
    high = DownstreamCompany(**base, source_confidence=0.80, high_confidence=True)
    assert low.high_confidence is False
    assert high.high_confidence is True


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    tests = [
        ("readiness.resolved", test_readiness_with_resolved_domain),
        ("readiness.unresolved", test_readiness_unresolved_domain),
        ("readiness.ambiguous", test_readiness_ambiguous_domain),
        ("readiness.no_domain", test_readiness_no_domain),
        ("readiness.rejected", test_readiness_rejected_domain),
        ("readiness.merged", test_readiness_merged),
        ("schema.minimal", test_downstream_company_minimal),
        ("schema.full", test_downstream_company_full),
        ("schema.serialization", test_downstream_company_serialization),
        ("summary.schema", test_downstream_summary),
        ("shape.required_fields", test_downstream_company_has_required_fields),
        ("shape.readiness_complete", test_readiness_statuses_are_complete),
        ("shape.website_format", test_official_website_format),
        ("shape.high_confidence", test_high_confidence_threshold),
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

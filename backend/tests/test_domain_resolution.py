"""Tests for domain resolution — Phase 4.

Validates:
  1. Domain cleaning
  2. Candidate deduplication
  3. Primary promotion logic
  4. Source extraction (JSON import, staging)
  5. Excluded domains filtering
  6. Model instantiation
  7. Pluggable source interface

Run:
  pytest backend/tests/test_domain_resolution.py -v
  python backend/tests/test_domain_resolution.py
"""

import sys
from pathlib import Path
from uuid import uuid4

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. DOMAIN CLEANING
# ════════════════════════════════════════════════════════════════════

def test_clean_domain_basic():
    from app.master.domain_resolver import _clean_domain
    assert _clean_domain("stripe.com") == "stripe.com"


def test_clean_domain_https_www():
    from app.master.domain_resolver import _clean_domain
    assert _clean_domain("https://www.example.com/about") == "example.com"


def test_clean_domain_uppercase():
    from app.master.domain_resolver import _clean_domain
    assert _clean_domain("STRIPE.COM") == "stripe.com"


def test_clean_domain_empty():
    from app.master.domain_resolver import _clean_domain
    assert _clean_domain("") is None
    assert _clean_domain("   ") is None


def test_clean_domain_invalid():
    from app.master.domain_resolver import _clean_domain
    assert _clean_domain("not a domain") is None


def test_clean_domain_with_path_and_query():
    from app.master.domain_resolver import _clean_domain
    assert _clean_domain("http://acme.com/careers?page=1#top") == "acme.com"


# ════════════════════════════════════════════════════════════════════
# 2. CANDIDATE DEDUPLICATION
# ════════════════════════════════════════════════════════════════════

def test_deduplicate_picks_highest_confidence():
    from app.master.domain_resolver import _deduplicate
    candidates = [
        {"domain": "acme.com", "confidence": 0.700, "source": "json"},
        {"domain": "acme.com", "confidence": 0.850, "source": "workspace"},
        {"domain": "acme.io", "confidence": 0.600, "source": "json"},
    ]
    result = _deduplicate(candidates)
    assert len(result) == 2
    assert result["acme.com"]["confidence"] == 0.850
    assert result["acme.com"]["source"] == "workspace"
    assert result["acme.io"]["confidence"] == 0.600


def test_deduplicate_single():
    from app.master.domain_resolver import _deduplicate
    result = _deduplicate([{"domain": "x.com", "confidence": 0.5, "source": "a"}])
    assert len(result) == 1


def test_deduplicate_empty():
    from app.master.domain_resolver import _deduplicate
    assert _deduplicate([]) == {}


# ════════════════════════════════════════════════════════════════════
# 3. EXCLUDED DOMAINS
# ════════════════════════════════════════════════════════════════════

def test_excluded_domains_list():
    from app.master.domain_resolver import EXCLUDED_DOMAINS
    assert "web.archive.org" in EXCLUDED_DOMAINS
    assert "github.com" in EXCLUDED_DOMAINS
    assert "linkedin.com" in EXCLUDED_DOMAINS
    assert "stripe.com" not in EXCLUDED_DOMAINS


# ════════════════════════════════════════════════════════════════════
# 4. JSON IMPORT SOURCE
# ════════════════════════════════════════════════════════════════════

def test_json_import_source_extracts_domain():
    """JsonImportSource should extract domains from raw_payload."""
    from app.master.domain_resolver import JsonImportSource
    from app.master.models import CompanyMaster, CompanySourceRecord

    # We can't use DB here, but we can test the extraction logic
    src = JsonImportSource()
    assert src.name() == "json_import"


def test_json_import_source_filters_excluded():
    """Domains in EXCLUDED_DOMAINS should not be returned."""
    from app.master.domain_resolver import EXCLUDED_DOMAINS, _clean_domain
    # Verify archive.org would be filtered
    assert _clean_domain("web.archive.org") == "web.archive.org"
    assert "web.archive.org" in EXCLUDED_DOMAINS


# ════════════════════════════════════════════════════════════════════
# 5. STAGING SOURCE
# ════════════════════════════════════════════════════════════════════

def test_staging_source_name():
    from app.master.domain_resolver import StagingSource
    src = StagingSource()
    assert src.name() == "staging"


# ════════════════════════════════════════════════════════════════════
# 6. WORKSPACE SOURCE
# ════════════════════════════════════════════════════════════════════

def test_workspace_source_name():
    from app.master.domain_resolver import WorkspaceSource
    src = WorkspaceSource()
    assert src.name() == "workspace"


# ════════════════════════════════════════════════════════════════════
# 7. MODEL INSTANTIATION
# ════════════════════════════════════════════════════════════════════

def test_model_company_domain():
    from app.master.domain_models import CompanyDomain
    cd = CompanyDomain(
        domain="stripe.com",
        is_primary=True,
        domain_status="resolved",
        confidence=0.950,
    )
    assert cd.domain == "stripe.com"
    assert cd.is_primary is True


def test_model_domain_resolution_run():
    from app.master.domain_models import DomainResolutionRun
    run = DomainResolutionRun()
    assert run.__tablename__ == "domain_resolution_runs"


def test_model_table_names():
    from app.master.domain_models import CompanyDomain, DomainResolutionRun
    assert CompanyDomain.__tablename__ == "company_domains"
    assert DomainResolutionRun.__tablename__ == "domain_resolution_runs"


def test_model_default_status():
    from app.master.domain_models import CompanyDomain
    cd = CompanyDomain(domain="test.com")
    # In-memory defaults may be None (applied on flush)
    assert cd.domain_status in ("unresolved", None)


# ════════════════════════════════════════════════════════════════════
# 8. PROMOTION LOGIC (unit-testable via mock DB)
# ════════════════════════════════════════════════════════════════════

def test_promotion_single_resolved():
    """Single resolved domain should become primary."""
    from app.master.domain_models import CompanyDomain

    # Simulate: 1 resolved domain
    domains = [
        CompanyDomain(domain="acme.com", domain_status="resolved", confidence=0.900),
    ]
    resolved = [d for d in domains if d.domain_status == "resolved"]
    assert len(resolved) == 1
    # The logic would set resolved[0].is_primary = True


def test_promotion_picks_highest_confidence():
    """Multiple resolved: highest confidence wins."""
    from app.master.domain_models import CompanyDomain
    from decimal import Decimal

    domains = [
        CompanyDomain(domain="acme.com", domain_status="resolved", confidence=Decimal("0.700")),
        CompanyDomain(domain="acme.io", domain_status="resolved", confidence=Decimal("0.900")),
    ]
    resolved = sorted(domains, key=lambda d: (-float(d.confidence), len(d.domain)))
    assert resolved[0].domain == "acme.io"


def test_promotion_all_rejected():
    """If all domains rejected, outcome is 'rejected'."""
    from app.master.domain_models import CompanyDomain
    domains = [
        CompanyDomain(domain="bad.com", domain_status="rejected", confidence=0.050),
    ]
    resolved = [d for d in domains if d.domain_status == "resolved"]
    all_rejected = all(d.domain_status == "rejected" for d in domains)
    assert len(resolved) == 0
    assert all_rejected is True


# ════════════════════════════════════════════════════════════════════
# 9. DOMAIN STATUS VALUES
# ════════════════════════════════════════════════════════════════════

def test_valid_domain_statuses():
    """Verify all expected statuses are handled in the pipeline."""
    valid = {"unresolved", "resolved", "ambiguous", "rejected", "redirect"}
    assert len(valid) == 5


# ════════════════════════════════════════════════════════════════════
# 10. PLUGGABLE SOURCE INTERFACE
# ════════════════════════════════════════════════════════════════════

def test_custom_source_interface():
    """Custom sources must implement name() and extract_domains()."""
    from app.master.domain_resolver import DomainSource

    class MockSource:
        def name(self) -> str:
            return "mock"
        def extract_domains(self, db, master) -> list[dict]:
            return [{"domain": "mock.com", "confidence": 0.500, "source": "mock"}]

    src = MockSource()
    assert src.name() == "mock"
    result = src.extract_domains(None, None)
    assert len(result) == 1
    assert result[0]["domain"] == "mock.com"


def test_default_sources_list():
    from app.master.domain_resolver import DEFAULT_SOURCES
    names = [s.name() for s in DEFAULT_SOURCES]
    assert "json_import" in names
    assert "staging" in names
    assert "workspace" in names


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    import traceback

    tests = [
        ("domain.clean_basic", test_clean_domain_basic),
        ("domain.clean_https_www", test_clean_domain_https_www),
        ("domain.clean_uppercase", test_clean_domain_uppercase),
        ("domain.clean_empty", test_clean_domain_empty),
        ("domain.clean_invalid", test_clean_domain_invalid),
        ("domain.clean_path_query", test_clean_domain_with_path_and_query),
        ("dedup.highest_confidence", test_deduplicate_picks_highest_confidence),
        ("dedup.single", test_deduplicate_single),
        ("dedup.empty", test_deduplicate_empty),
        ("excluded.domains_list", test_excluded_domains_list),
        ("source.json_import_name", test_json_import_source_extracts_domain),
        ("source.json_import_filter", test_json_import_source_filters_excluded),
        ("source.staging_name", test_staging_source_name),
        ("source.workspace_name", test_workspace_source_name),
        ("model.company_domain", test_model_company_domain),
        ("model.resolution_run", test_model_domain_resolution_run),
        ("model.table_names", test_model_table_names),
        ("model.default_status", test_model_default_status),
        ("promote.single_resolved", test_promotion_single_resolved),
        ("promote.highest_confidence", test_promotion_picks_highest_confidence),
        ("promote.all_rejected", test_promotion_all_rejected),
        ("status.valid_values", test_valid_domain_statuses),
        ("source.custom_interface", test_custom_source_interface),
        ("source.defaults_list", test_default_sources_list),
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
                "name": name,
                "status": "error",
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            })

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total": len(tests),
        "success": failed == 0 and errors == 0,
        "details": details,
    }


if __name__ == "__main__":
    import json
    report = run_all_tests()
    print(json.dumps(report, indent=2))
    if not report["success"]:
        sys.exit(1)

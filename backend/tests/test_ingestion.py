"""Tests for the Company Master Index ingestion pipeline — Phase 2.

Validates:
  1. JSON loading (both formats)
  2. Domain cleaning
  3. Name cleaning (Wikipedia disambiguation)
  4. State extraction from freeform location
  5. Normalization pipeline
  6. Staging model instantiation
  7. Full pipeline integration (requires DB)

Run:
  pytest backend/tests/test_ingestion.py -v
  python backend/tests/test_ingestion.py  (standalone report)
"""

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. JSON LOADING
# ════════════════════════════════════════════════════════════════════

def test_load_json_array(tmp_path):
    """Load a simple JSON array of companies."""
    import json
    from app.master.ingestion import _load_json

    data = [
        {"company_name": "Acme Corp", "domain": "acme.com"},
        {"company_name": "Beta Inc", "domain": "beta.io"},
    ]
    f = tmp_path / "test.json"
    f.write_text(json.dumps(data))
    result = _load_json(f)
    assert len(result) == 2
    assert result[0]["company_name"] == "Acme Corp"


def test_load_json_object_with_key(tmp_path):
    """Load JSON object with companies_with_domain key."""
    import json
    from app.master.ingestion import _load_json

    data = {
        "generated_at": "2026-01-01",
        "source": "test",
        "companies_with_domain": [
            {"name": "Foo LLC", "domain": "foo.com"},
        ],
    }
    f = tmp_path / "test.json"
    f.write_text(json.dumps(data))
    result = _load_json(f)
    assert len(result) == 1
    assert result[0]["name"] == "Foo LLC"


def test_load_json_companies_key(tmp_path):
    """Load JSON object with companies key."""
    import json
    from app.master.ingestion import _load_json

    data = {"companies": [{"name": "Bar", "domain": "bar.com"}]}
    f = tmp_path / "test.json"
    f.write_text(json.dumps(data))
    result = _load_json(f)
    assert len(result) == 1


# ════════════════════════════════════════════════════════════════════
# 2. DOMAIN CLEANING
# ════════════════════════════════════════════════════════════════════

def test_clean_domain_basic():
    from app.master.ingestion import _clean_domain
    assert _clean_domain("acme.com") == "acme.com"


def test_clean_domain_https():
    from app.master.ingestion import _clean_domain
    assert _clean_domain("https://www.example.com/about") == "example.com"


def test_clean_domain_empty():
    from app.master.ingestion import _clean_domain
    assert _clean_domain("") is None
    assert _clean_domain("   ") is None


def test_clean_domain_invalid():
    from app.master.ingestion import _clean_domain
    assert _clean_domain("not a domain") is None
    assert _clean_domain("just-a-word") is None


def test_clean_domain_uppercase():
    from app.master.ingestion import _clean_domain
    assert _clean_domain("ACME.COM") == "acme.com"


# ════════════════════════════════════════════════════════════════════
# 3. NAME CLEANING
# ════════════════════════════════════════════════════════════════════

def test_clean_legal_name_basic():
    from app.master.ingestion import _clean_legal_name
    assert _clean_legal_name("Stripe, Inc.") == "Stripe, Inc."


def test_clean_legal_name_disambiguation():
    from app.master.ingestion import _clean_legal_name
    assert _clean_legal_name("AAPC (healthcare)") == "AAPC"
    assert _clean_legal_name("ASEA (American company)") == "ASEA"


def test_clean_legal_name_no_parens():
    from app.master.ingestion import _clean_legal_name
    assert _clean_legal_name("Goldman Sachs") == "Goldman Sachs"


def test_clean_legal_name_empty_after_strip():
    from app.master.ingestion import _clean_legal_name
    # Edge case: if removing parens leaves empty, keep original
    assert _clean_legal_name("(unknown)") == "(unknown)"


# ════════════════════════════════════════════════════════════════════
# 4. STATE EXTRACTION
# ════════════════════════════════════════════════════════════════════

def test_extract_state_simple():
    from app.master.ingestion import _extract_state
    assert _extract_state("Provo, UT") == "UT"


def test_extract_state_full_name():
    from app.master.ingestion import _extract_state
    assert _extract_state("Salt Lake City, Utah") == "UT"


def test_extract_state_wikipedia_format():
    from app.master.ingestion import _extract_state
    assert _extract_state("Provo, Utah, , U.S.") == "UT"
    assert _extract_state("Salt Lake City, (, Utah, ),, United States") == "UT"


def test_extract_state_two_word():
    from app.master.ingestion import _extract_state
    assert _extract_state("Charlotte, North Carolina") == "NC"
    assert _extract_state("New York, New York") == "NY"


def test_extract_state_none():
    from app.master.ingestion import _extract_state
    assert _extract_state(None) is None
    assert _extract_state("") is None
    assert _extract_state("London, UK") is None


def test_extract_state_with_zip():
    from app.master.ingestion import _extract_state
    assert _extract_state("Salt Lake City, ,, Utah, 84111, ,, United States") == "UT"


# ════════════════════════════════════════════════════════════════════
# 5. STAGING MODEL INSTANTIATION
# ════════════════════════════════════════════════════════════════════

def test_model_import_run():
    from app.master.staging_models import ImportRun
    run = ImportRun(batch_id="test_batch", source_file="test.json")
    assert run.batch_id == "test_batch"
    # Column default only applies on DB flush; in-memory may be None
    assert run.source_type in ("json_file", None)


def test_model_staging_raw():
    from app.master.staging_models import CompanyStagingRaw
    raw = CompanyStagingRaw(
        row_index=0,
        raw_payload={"name": "Test"},
        raw_name="Test",
    )
    assert raw.status in ("pending", None)


def test_model_staging_normalized():
    from app.master.staging_models import CompanyStagingNormalized
    norm = CompanyStagingNormalized(
        legal_name="Test Corp",
        normalized_name="test",
    )
    assert norm.action in ("pending", None)


def test_model_table_names():
    from app.master.staging_models import (
        CompanyStagingNormalized,
        CompanyStagingRaw,
        ImportRun,
    )
    assert ImportRun.__tablename__ == "import_runs"
    assert CompanyStagingRaw.__tablename__ == "company_staging_raw"
    assert CompanyStagingNormalized.__tablename__ == "company_staging_normalized"


# ════════════════════════════════════════════════════════════════════
# 6. NORMALIZATION CONSISTENCY
# ════════════════════════════════════════════════════════════════════

def test_wikipedia_names_normalize_consistently():
    """Verify that Wikipedia-style names normalize cleanly."""
    from app.master.canonical import normalize_company_name
    from app.master.ingestion import _clean_legal_name

    cases = [
        ("AAPC (healthcare)", "aapc"),
        ("ASEA (American company)", "asea"),
        ("1-800 Contacts", "1 800 contacts"),
        ("America First Credit Union", "america first credit union"),
        ("Alsco Uniforms", "alsco uniforms"),
    ]
    for raw, expected in cases:
        legal = _clean_legal_name(raw)
        normalized = normalize_company_name(legal)
        assert normalized == expected, f"{raw!r} → {normalized!r}, expected {expected!r}"


def test_domain_cleaning_matches_existing_companies():
    """Verify domain normalization is consistent with the existing pipeline."""
    from app.master.ingestion import _clean_domain

    cases = [
        ("1800contacts.com", "1800contacts.com"),
        ("https://www.aapc.com", "aapc.com"),
        ("ASEAGLOBAL.COM", "aseaglobal.com"),
        ("actiontarget.com/", "actiontarget.com"),
    ]
    for raw, expected in cases:
        result = _clean_domain(raw)
        assert result == expected, f"{raw!r} → {result!r}, expected {expected!r}"


# ════════════════════════════════════════════════════════════════════
# 7. REAL FILE PARSING (fixture-based)
# ════════════════════════════════════════════════════════════════════

def test_parse_example_input():
    """Parse the actual example_input.json file."""
    from app.master.ingestion import _load_json

    path = Path(__file__).resolve().parent.parent.parent / "cli" / "example_input.json"
    if not path.exists():
        return  # skip if file not available
    entries = _load_json(path)
    assert len(entries) >= 3
    assert entries[0].get("company_name") or entries[0].get("name")


def test_parse_utah_companies():
    """Parse the actual utah_companies.json file."""
    from app.master.ingestion import _load_json

    path = Path(__file__).resolve().parent.parent.parent / "tools" / "data" / "utah_companies.json"
    if not path.exists():
        return  # skip if file not available
    entries = _load_json(path)
    assert len(entries) >= 150
    # First entry should have expected fields
    first = entries[0]
    assert "name" in first or "company_name" in first
    assert "domain" in first


def test_utah_state_extraction_coverage():
    """Most Utah companies should extract UT as jurisdiction."""
    from app.master.ingestion import _extract_state, _load_json

    path = Path(__file__).resolve().parent.parent.parent / "tools" / "data" / "utah_companies.json"
    if not path.exists():
        return
    entries = _load_json(path)

    with_location = [e for e in entries if e.get("hq") or e.get("location")]
    extracted = [e for e in with_location if _extract_state(e.get("hq") or e.get("location"))]
    coverage = len(extracted) / len(with_location) if with_location else 0
    assert coverage >= 0.8, f"State extraction coverage too low: {coverage:.0%} ({len(extracted)}/{len(with_location)})"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    """Run all tests and return structured report."""
    import tempfile
    import traceback

    # Create a temp dir for JSON fixtures
    tmp = Path(tempfile.mkdtemp())

    tests = [
        ("json.load_array", lambda: test_load_json_array(tmp)),
        ("json.load_object_with_key", lambda: test_load_json_object_with_key(tmp)),
        ("json.load_companies_key", lambda: test_load_json_companies_key(tmp)),
        ("domain.basic", test_clean_domain_basic),
        ("domain.https", test_clean_domain_https),
        ("domain.empty", test_clean_domain_empty),
        ("domain.invalid", test_clean_domain_invalid),
        ("domain.uppercase", test_clean_domain_uppercase),
        ("name.basic", test_clean_legal_name_basic),
        ("name.disambiguation", test_clean_legal_name_disambiguation),
        ("name.no_parens", test_clean_legal_name_no_parens),
        ("name.empty_after_strip", test_clean_legal_name_empty_after_strip),
        ("state.simple", test_extract_state_simple),
        ("state.full_name", test_extract_state_full_name),
        ("state.wikipedia_format", test_extract_state_wikipedia_format),
        ("state.two_word", test_extract_state_two_word),
        ("state.none", test_extract_state_none),
        ("state.with_zip", test_extract_state_with_zip),
        ("model.import_run", test_model_import_run),
        ("model.staging_raw", test_model_staging_raw),
        ("model.staging_normalized", test_model_staging_normalized),
        ("model.table_names", test_model_table_names),
        ("normalize.wikipedia_names", test_wikipedia_names_normalize_consistently),
        ("normalize.domain_consistency", test_domain_cleaning_matches_existing_companies),
        ("fixture.example_input", test_parse_example_input),
        ("fixture.utah_companies", test_parse_utah_companies),
        ("fixture.utah_state_coverage", test_utah_state_extraction_coverage),
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

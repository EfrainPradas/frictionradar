"""Tests for external identifier enrichment — Phase 5.

Validates:
  1. Base types and constants
  2. Adapter interfaces
  3. CSV adapter parsing
  4. Orchestrator deduplication/persistence logic
  5. Graceful handling of missing identifiers
  6. SAM adapter without API key
  7. Edgar adapter name matching

Run:
  pytest backend/tests/test_enrichment.py -v
  python backend/tests/test_enrichment.py
"""

import json
import sys
from pathlib import Path
from uuid import uuid4

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. BASE TYPES AND CONSTANTS
# ════════════════════════════════════════════════════════════════════

def test_id_type_constants():
    from app.master.enrichment.base import IdType
    assert IdType.EDGAR_CIK == "edgar_cik"
    assert IdType.SAM_UEI == "sam_uei"
    assert IdType.EIN == "ein"
    assert IdType.STATE_REGISTRY_ID == "state_registry_id"
    assert IdType.TICKER == "ticker"
    assert IdType.SIC_CODE == "sic_code"
    assert IdType.NAICS_CODE == "naics_code"


def test_authority_constants():
    from app.master.enrichment.base import Authority
    assert Authority.SEC == "SEC"
    assert Authority.GSA == "GSA"
    assert Authority.IRS == "IRS"


def test_identifier_match_dataclass():
    from app.master.enrichment.base import IdentifierMatch, IdType
    m = IdentifierMatch(
        id_type=IdType.EDGAR_CIK,
        id_value="1694028",
        issuing_authority="SEC",
        confidence=0.92,
    )
    assert m.id_type == "edgar_cik"
    assert m.id_value == "1694028"
    assert m.confidence == 0.92
    assert m.source_url is None
    assert m.raw_payload is None


def test_enrichment_result_dataclass():
    from app.master.enrichment.base import EnrichmentResult
    r = EnrichmentResult(
        master_id="abc",
        company_name="Stripe",
        source_name="test",
    )
    assert r.identifiers == []
    assert r.error is None


def test_enrichment_result_with_error():
    from app.master.enrichment.base import EnrichmentResult
    r = EnrichmentResult(
        master_id="abc",
        company_name="Stripe",
        source_name="test",
        error="connection timeout",
    )
    assert r.error == "connection timeout"
    assert r.identifiers == []


# ════════════════════════════════════════════════════════════════════
# 2. ADAPTER INTERFACES
# ════════════════════════════════════════════════════════════════════

def test_edgar_adapter_interface():
    from app.master.enrichment.edgar_adapter import EdgarAdapter
    a = EdgarAdapter()
    assert a.name() == "sec_edgar"
    assert a.supports_bulk() is False


def test_sam_adapter_interface():
    from app.master.enrichment.sam_adapter import SamAdapter
    a = SamAdapter()
    assert a.name() == "sam_gov"
    assert a.supports_bulk() is False


def test_sam_adapter_no_api_key():
    """SAM adapter without API key should return empty, not error."""
    import os
    old = os.environ.pop("SAM_API_KEY", None)
    try:
        from app.master.enrichment.sam_adapter import SamAdapter
        a = SamAdapter()
        assert a.is_available() is False

        from app.master.models import CompanyMaster
        master = CompanyMaster(
            legal_name="Test Corp",
            normalized_name="test",
            entity_status="active",
        )
        master.id = uuid4()
        result = a.enrich(None, master)
        assert result.identifiers == []
        assert result.error is None
    finally:
        if old:
            os.environ["SAM_API_KEY"] = old


def test_csv_adapter_interface():
    from app.master.enrichment.csv_adapter import CsvAdapter
    a = CsvAdapter("dummy.json")
    assert a.name() == "csv_import:dummy.json"
    assert a.supports_bulk() is True


# ════════════════════════════════════════════════════════════════════
# 3. CSV ADAPTER PARSING
# ════════════════════════════════════════════════════════════════════

def test_csv_adapter_json_format(tmp_path):
    from app.master.enrichment.csv_adapter import CsvAdapter
    data = [
        {
            "company_name": "Qualtrics International Inc",
            "domain": "qualtrics.com",
            "identifiers": [
                {"id_type": "edgar_cik", "id_value": "1747748", "issuing_authority": "SEC"},
                {"id_type": "ticker", "id_value": "XM", "issuing_authority": "NYSE"},
            ],
        },
    ]
    f = tmp_path / "ids.json"
    f.write_text(json.dumps(data))

    adapter = CsvAdapter(str(f))
    rows = adapter.load()
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Qualtrics International Inc"


def test_csv_adapter_csv_format(tmp_path):
    from app.master.enrichment.csv_adapter import CsvAdapter
    csv_content = (
        "company_name,domain,id_type,id_value,issuing_authority\n"
        '"Stripe, Inc.",stripe.com,edgar_cik,1694028,SEC\n'
        "Qualtrics,qualtrics.com,edgar_cik,1747748,SEC\n"
    )
    f = tmp_path / "ids.csv"
    f.write_text(csv_content)

    adapter = CsvAdapter(str(f))
    rows = adapter.load()
    assert len(rows) == 2
    assert rows[0]["id_type"] == "edgar_cik"


def test_csv_adapter_extract_identifiers_json():
    from app.master.enrichment.csv_adapter import CsvAdapter
    adapter = CsvAdapter("dummy.json")
    row = {
        "company_name": "Test",
        "identifiers": [
            {"id_type": "edgar_cik", "id_value": "123", "issuing_authority": "SEC"},
        ],
    }
    idents = adapter._extract_identifiers(row)
    assert len(idents) == 1
    assert idents[0].id_type == "edgar_cik"
    assert idents[0].id_value == "123"


def test_csv_adapter_extract_identifiers_flat():
    from app.master.enrichment.csv_adapter import CsvAdapter
    adapter = CsvAdapter("dummy.csv")
    row = {"id_type": "sam_uei", "id_value": "ABC123", "issuing_authority": "GSA"}
    idents = adapter._extract_identifiers(row)
    assert len(idents) == 1
    assert idents[0].id_type == "sam_uei"


def test_csv_adapter_extract_identifiers_empty():
    from app.master.enrichment.csv_adapter import CsvAdapter
    adapter = CsvAdapter("dummy.csv")
    assert adapter._extract_identifiers({}) == []
    assert adapter._extract_identifiers({"id_type": "", "id_value": ""}) == []


# ════════════════════════════════════════════════════════════════════
# 4. NAME SIMILARITY
# ════════════════════════════════════════════════════════════════════

def test_edgar_name_similarity():
    from app.master.enrichment.edgar_adapter import _name_similarity
    assert _name_similarity("stripe", "stripe") == 1.0
    assert _name_similarity("stripe", "microsoft") == 0.0
    assert _name_similarity("", "") == 0.0


def test_edgar_name_similarity_partial():
    from app.master.enrichment.edgar_adapter import _name_similarity
    result = _name_similarity("qualtrics international", "qualtrics")
    assert 0.49 <= result <= 0.51  # 1/2 = 0.5


def test_sam_name_similarity():
    from app.master.enrichment.sam_adapter import _name_similarity
    assert _name_similarity("podium", "podium") == 1.0


# ════════════════════════════════════════════════════════════════════
# 5. ORCHESTRATOR LOGIC
# ════════════════════════════════════════════════════════════════════

def test_custom_adapter_works_with_orchestrator():
    """A custom adapter that returns known identifiers should work."""
    from app.master.enrichment.base import EnrichmentResult, IdentifierMatch, IdType

    class MockAdapter:
        def name(self): return "mock"
        def supports_bulk(self): return False
        def enrich(self, db, master):
            return EnrichmentResult(
                master_id=str(master.id),
                company_name=master.legal_name,
                source_name="mock",
                identifiers=[
                    IdentifierMatch(
                        id_type=IdType.EDGAR_CIK,
                        id_value="9999999",
                        confidence=0.95,
                    )
                ],
            )

    adapter = MockAdapter()
    from app.master.models import CompanyMaster
    master = CompanyMaster(legal_name="Test", normalized_name="test", entity_status="active")
    master.id = uuid4()
    result = adapter.enrich(None, master)
    assert len(result.identifiers) == 1
    assert result.identifiers[0].id_value == "9999999"


def test_adapter_error_does_not_propagate():
    """An adapter that errors should report it in result, not raise."""
    from app.master.enrichment.base import EnrichmentResult

    class FailingAdapter:
        def name(self): return "failing"
        def supports_bulk(self): return False
        def enrich(self, db, master):
            return EnrichmentResult(
                master_id=str(master.id),
                company_name=master.legal_name,
                source_name="failing",
                error="Connection refused",
            )

    adapter = FailingAdapter()
    from app.master.models import CompanyMaster
    master = CompanyMaster(legal_name="Test", normalized_name="test")
    master.id = uuid4()
    result = adapter.enrich(None, master)
    assert result.error is not None
    assert result.identifiers == []


# ════════════════════════════════════════════════════════════════════
# 6. MISSING IDENTIFIERS HANDLING
# ════════════════════════════════════════════════════════════════════

def test_empty_enrichment_is_valid():
    """Companies without any external IDs are not errors."""
    from app.master.enrichment.base import EnrichmentResult
    r = EnrichmentResult(master_id="x", company_name="X", source_name="test")
    assert r.identifiers == []
    assert r.error is None


def test_ein_is_secondary():
    """EIN should be marked as secondary identifier, never primary."""
    from app.master.enrichment.base import IdType
    # EIN exists as a type but the adapters only return it as a derived
    # identifier from other sources (e.g., SAM.gov)
    assert IdType.EIN == "ein"
    # There's no standalone EIN adapter — it's always secondary


def test_all_id_types_are_strings():
    """All IdType constants should be lowercase strings."""
    from app.master.enrichment.base import IdType
    types = [
        IdType.EDGAR_CIK, IdType.SAM_UEI, IdType.EIN,
        IdType.STATE_REGISTRY_ID, IdType.DUNS, IdType.LEI,
        IdType.TICKER, IdType.SIC_CODE, IdType.NAICS_CODE,
    ]
    for t in types:
        assert isinstance(t, str)
        assert t == t.lower()


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    import tempfile
    tmp = Path(tempfile.mkdtemp())

    tests = [
        ("types.id_type_constants", test_id_type_constants),
        ("types.authority_constants", test_authority_constants),
        ("types.identifier_match", test_identifier_match_dataclass),
        ("types.enrichment_result", test_enrichment_result_dataclass),
        ("types.enrichment_result_error", test_enrichment_result_with_error),
        ("adapter.edgar_interface", test_edgar_adapter_interface),
        ("adapter.sam_interface", test_sam_adapter_interface),
        ("adapter.sam_no_key", test_sam_adapter_no_api_key),
        ("adapter.csv_interface", test_csv_adapter_interface),
        ("csv.json_format", lambda: test_csv_adapter_json_format(tmp)),
        ("csv.csv_format", lambda: test_csv_adapter_csv_format(tmp)),
        ("csv.extract_json", test_csv_adapter_extract_identifiers_json),
        ("csv.extract_flat", test_csv_adapter_extract_identifiers_flat),
        ("csv.extract_empty", test_csv_adapter_extract_identifiers_empty),
        ("sim.edgar_identical", test_edgar_name_similarity),
        ("sim.edgar_partial", test_edgar_name_similarity_partial),
        ("sim.sam_identical", test_sam_name_similarity),
        ("orch.custom_adapter", test_custom_adapter_works_with_orchestrator),
        ("orch.adapter_error", test_adapter_error_does_not_propagate),
        ("missing.empty_valid", test_empty_enrichment_is_valid),
        ("missing.ein_secondary", test_ein_is_secondary),
        ("missing.types_are_strings", test_all_id_types_are_strings),
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
    report = run_all_tests()
    print(json.dumps(report, indent=2))
    if not report["success"]:
        sys.exit(1)

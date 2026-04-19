"""Tests for the Company Master Index — Phase 1.

Validates:
  1. Name normalization (canonical.py)
  2. State code normalization
  3. Schema validation (Pydantic models)
  4. Model instantiation (SQLAlchemy)
  5. Repository functions (requires DB)

Run:
  pytest backend/tests/test_master_index.py -v
  python backend/tests/test_master_index.py  (standalone report)
"""

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. NAME NORMALIZATION
# ════════════════════════════════════════════════════════════════════

def test_normalize_basic():
    from app.master.canonical import normalize_company_name
    assert normalize_company_name("Stripe, Inc.") == "stripe"


def test_normalize_the_prefix():
    from app.master.canonical import normalize_company_name
    assert normalize_company_name("The Goldman Sachs Group, Inc.") == "goldman sachs"


def test_normalize_ampersand():
    from app.master.canonical import normalize_company_name
    result = normalize_company_name("JPMorgan Chase & Co.")
    assert result == "jpmorgan chase"


def test_normalize_llc():
    from app.master.canonical import normalize_company_name
    assert normalize_company_name("Acme Solutions LLC") == "acme solutions"


def test_normalize_multiple_suffixes():
    from app.master.canonical import normalize_company_name
    result = normalize_company_name("Delta Holdings Corporation")
    assert result == "delta"


def test_normalize_empty():
    from app.master.canonical import normalize_company_name
    assert normalize_company_name("") == ""
    assert normalize_company_name("   ") == ""


def test_normalize_unicode():
    from app.master.canonical import normalize_company_name
    result = normalize_company_name("Zürich Insurance Group Ltd.")
    assert result == "zurich insurance"


def test_normalize_preserves_numbers():
    from app.master.canonical import normalize_company_name
    result = normalize_company_name("3M Company")
    assert result == "3m"


def test_normalize_idempotent():
    from app.master.canonical import normalize_company_name
    name = "Meta Platforms, Inc."
    first = normalize_company_name(name)
    second = normalize_company_name(first)
    assert first == second


# ════════════════════════════════════════════════════════════════════
# 2. STATE CODE NORMALIZATION
# ════════════════════════════════════════════════════════════════════

def test_state_code_two_letter():
    from app.master.canonical import normalize_state_code
    assert normalize_state_code("DE") == "DE"
    assert normalize_state_code("ca") == "CA"
    assert normalize_state_code(" ny ") == "NY"


def test_state_code_full_name():
    from app.master.canonical import normalize_state_code
    assert normalize_state_code("Delaware") == "DE"
    assert normalize_state_code("california") == "CA"
    assert normalize_state_code("New York") == "NY"


def test_state_code_invalid():
    from app.master.canonical import normalize_state_code
    assert normalize_state_code("XX") is None
    assert normalize_state_code("") is None
    assert normalize_state_code(None) is None


def test_state_code_dc():
    from app.master.canonical import normalize_state_code
    assert normalize_state_code("DC") == "DC"


# ════════════════════════════════════════════════════════════════════
# 3. PYDANTIC SCHEMA VALIDATION
# ════════════════════════════════════════════════════════════════════

def test_schema_master_create():
    from app.master.schemas import CompanyMasterCreate
    obj = CompanyMasterCreate(
        legal_name="Stripe, Inc.",
        normalized_name="stripe",
        entity_type="corporation",
        jurisdiction_state="DE",
    )
    assert obj.legal_name == "Stripe, Inc."
    assert obj.source_priority == 50
    assert obj.source_confidence == 0.50


def test_schema_master_create_defaults():
    from app.master.schemas import CompanyMasterCreate
    obj = CompanyMasterCreate(
        legal_name="Test Co",
        normalized_name="test",
    )
    assert obj.entity_status == "active"
    assert obj.entity_type is None
    assert obj.jurisdiction_state is None
    assert obj.formation_date is None


def test_schema_external_id_create():
    from uuid import uuid4
    from app.master.schemas import CompanyExternalIdCreate
    obj = CompanyExternalIdCreate(
        company_master_id=uuid4(),
        id_type="ein",
        id_value="12-3456789",
        issuing_authority="IRS",
    )
    assert obj.id_type == "ein"
    assert obj.verified is False


def test_schema_alias_create():
    from uuid import uuid4
    from app.master.schemas import CompanyAliasCreate
    obj = CompanyAliasCreate(
        company_master_id=uuid4(),
        alias_name="AWS",
        alias_type="abbreviation",
    )
    assert obj.alias_type == "abbreviation"
    assert obj.is_primary is False


def test_schema_source_record_create():
    from uuid import uuid4
    from app.master.schemas import CompanySourceRecordCreate
    obj = CompanySourceRecordCreate(
        company_master_id=uuid4(),
        source_name="sec_edgar",
        source_record_id="0001018724",
        raw_payload={"cik": "0001018724", "name": "AMAZON COM INC"},
    )
    assert obj.source_name == "sec_edgar"
    assert obj.raw_payload["cik"] == "0001018724"


def test_schema_priority_bounds():
    from pydantic import ValidationError
    from app.master.schemas import CompanyMasterCreate
    try:
        CompanyMasterCreate(
            legal_name="Bad",
            normalized_name="bad",
            source_priority=101,
        )
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass


def test_schema_confidence_bounds():
    from pydantic import ValidationError
    from app.master.schemas import CompanyMasterCreate
    try:
        CompanyMasterCreate(
            legal_name="Bad",
            normalized_name="bad",
            source_confidence=1.5,
        )
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass


# ════════════════════════════════════════════════════════════════════
# 4. MODEL INSTANTIATION
# ════════════════════════════════════════════════════════════════════

def test_model_company_master():
    from app.master.models import CompanyMaster
    obj = CompanyMaster(
        legal_name="Test Corp",
        normalized_name="test",
        entity_status="active",
    )
    assert obj.legal_name == "Test Corp"
    assert obj.entity_status == "active"


def test_model_external_id():
    from app.master.models import CompanyExternalId
    obj = CompanyExternalId(
        id_type="edgar_cik",
        id_value="0001018724",
        issuing_authority="SEC",
    )
    assert obj.id_type == "edgar_cik"
    # Column default only applies on DB flush; in-memory it's None
    assert obj.verified is None or obj.verified is False


def test_model_alias():
    from app.master.models import CompanyAlias
    obj = CompanyAlias(
        alias_name="Amazon",
        alias_type="trade_name",
        is_primary=True,
    )
    assert obj.is_primary is True


def test_model_source_record():
    from app.master.models import CompanySourceRecord
    obj = CompanySourceRecord(
        source_name="sam_gov",
        source_record_id="ABC123",
    )
    assert obj.source_name == "sam_gov"


def test_model_table_names():
    from app.master.models import (
        CompanyAlias,
        CompanyExternalId,
        CompanyMaster,
        CompanySourceRecord,
    )
    assert CompanyMaster.__tablename__ == "company_master"
    assert CompanyExternalId.__tablename__ == "company_external_ids"
    assert CompanyAlias.__tablename__ == "company_aliases"
    assert CompanySourceRecord.__tablename__ == "company_source_records"


# ════════════════════════════════════════════════════════════════════
# 5. LEGAL SUFFIX COVERAGE
# ════════════════════════════════════════════════════════════════════

def test_suffix_inc():
    from app.master.canonical import normalize_company_name
    assert normalize_company_name("Apple Inc") == "apple"
    assert normalize_company_name("Apple Inc.") == "apple"


def test_suffix_corp():
    from app.master.canonical import normalize_company_name
    assert normalize_company_name("Microsoft Corp") == "microsoft"
    assert normalize_company_name("Microsoft Corp.") == "microsoft"
    assert normalize_company_name("Microsoft Corporation") == "microsoft"


def test_suffix_ltd():
    from app.master.canonical import normalize_company_name
    assert normalize_company_name("Barclays Ltd") == "barclays"
    assert normalize_company_name("Barclays Ltd.") == "barclays"
    assert normalize_company_name("Barclays Limited") == "barclays"


def test_suffix_lp():
    from app.master.canonical import normalize_company_name
    assert normalize_company_name("Blackstone L.P.") == "blackstone"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    """Run all tests and return structured report."""
    import traceback

    tests = [
        ("canonical.normalize_basic", test_normalize_basic),
        ("canonical.normalize_the_prefix", test_normalize_the_prefix),
        ("canonical.normalize_ampersand", test_normalize_ampersand),
        ("canonical.normalize_llc", test_normalize_llc),
        ("canonical.normalize_multiple_suffixes", test_normalize_multiple_suffixes),
        ("canonical.normalize_empty", test_normalize_empty),
        ("canonical.normalize_unicode", test_normalize_unicode),
        ("canonical.normalize_preserves_numbers", test_normalize_preserves_numbers),
        ("canonical.normalize_idempotent", test_normalize_idempotent),
        ("canonical.state_code_two_letter", test_state_code_two_letter),
        ("canonical.state_code_full_name", test_state_code_full_name),
        ("canonical.state_code_invalid", test_state_code_invalid),
        ("canonical.state_code_dc", test_state_code_dc),
        ("schema.master_create", test_schema_master_create),
        ("schema.master_create_defaults", test_schema_master_create_defaults),
        ("schema.external_id_create", test_schema_external_id_create),
        ("schema.alias_create", test_schema_alias_create),
        ("schema.source_record_create", test_schema_source_record_create),
        ("schema.priority_bounds", test_schema_priority_bounds),
        ("schema.confidence_bounds", test_schema_confidence_bounds),
        ("model.company_master", test_model_company_master),
        ("model.external_id", test_model_external_id),
        ("model.alias", test_model_alias),
        ("model.source_record", test_model_source_record),
        ("model.table_names", test_model_table_names),
        ("suffix.inc", test_suffix_inc),
        ("suffix.corp", test_suffix_corp),
        ("suffix.ltd", test_suffix_ltd),
        ("suffix.lp", test_suffix_lp),
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

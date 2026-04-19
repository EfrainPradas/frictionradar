"""Tests for Florida DOS connector.

Validates:
  1. Fixed-width parser field extraction
  2. Record filtering (active, filing types)
  3. Date parsing
  4. Entity type mapping
  5. Normalization integration
  6. Dry-run pipeline
  7. Fixture file parsing

Run:
  python backend/tests/test_florida_connector.py
"""

import json
import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _make_line(
    corp_num="P12345000001",
    name="TEST COMPANY INC",
    status="A",
    filing_type="DOMP",
    city="MIAMI",
    state="FL",
    zipcode="33131",
    country="US",
    file_date="01012020",
    fei="591234567",
):
    """Build a valid 1440-char fixed-width line for testing."""
    line = ""
    line += corp_num.ljust(12)
    line += name.ljust(192)
    line += status
    line += filing_type.ljust(15)
    line += "100 MAIN ST".ljust(42)   # address1
    line += "".ljust(42)              # address2
    line += city.ljust(28)
    line += state.ljust(2)
    line += zipcode.ljust(10)
    line += country.ljust(2)
    line += "".ljust(126)             # mailing address
    line += file_date.ljust(8)
    line += fei.ljust(14)
    line += " "                       # more officers
    line += file_date.ljust(8)
    line += "FL"
    line += "".ljust(39)
    line += "AGENT NAME".ljust(42)
    line += "P"
    remaining = 1440 - len(line)
    line += "".ljust(remaining)
    return line


# ════════════════════════════════════════════════════════════════════
# 1. FIELD EXTRACTION
# ════════════════════════════════════════════════════════════════════

def test_parse_corp_number():
    from app.master.connectors.florida import parse_line
    line = _make_line(corp_num="P99887766001")
    rec = parse_line(line)
    assert rec is not None
    assert rec.corp_number == "P99887766001"


def test_parse_corp_name():
    from app.master.connectors.florida import parse_line
    line = _make_line(name="ACME CORPORATION")
    rec = parse_line(line)
    assert rec.corp_name == "ACME CORPORATION"


def test_parse_status():
    from app.master.connectors.florida import parse_line
    active = parse_line(_make_line(status="A"))
    inactive = parse_line(_make_line(status="I"))
    assert active.status == "A"
    assert inactive.status == "I"


def test_parse_filing_type():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(filing_type="FLAL"))
    assert rec.filing_type == "FLAL"


def test_parse_city_state():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(city="ORLANDO", state="FL"))
    assert rec.city == "ORLANDO"
    assert rec.state == "FL"


def test_parse_fei_number():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(fei="591234567"))
    assert rec.fei_number == "591234567"


def test_parse_empty_fei():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(fei=""))
    assert rec.fei_number == ""


# ════════════════════════════════════════════════════════════════════
# 2. DATE PARSING
# ════════════════════════════════════════════════════════════════════

def test_parse_date_mmddyyyy():
    from app.master.connectors.florida import _parse_date
    d = _parse_date("01152020")
    assert d is not None
    assert d.year == 2020
    assert d.month == 1
    assert d.day == 15


def test_parse_date_empty():
    from app.master.connectors.florida import _parse_date
    assert _parse_date("") is None
    assert _parse_date("        ") is None


def test_parse_date_invalid():
    from app.master.connectors.florida import _parse_date
    assert _parse_date("99999999") is None


# ════════════════════════════════════════════════════════════════════
# 3. ENTITY TYPE MAPPING
# ════════════════════════════════════════════════════════════════════

def test_entity_type_domp():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(filing_type="DOMP"))
    assert rec.entity_type == "corporation"


def test_entity_type_flal():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(filing_type="FLAL"))
    assert rec.entity_type == "llc"


def test_entity_type_domnp():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(filing_type="DOMNP"))
    assert rec.entity_type == "nonprofit"


def test_entity_type_unknown():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(filing_type="ZZZZZ"))
    assert rec.entity_type is None


# ════════════════════════════════════════════════════════════════════
# 4. FILTERING
# ════════════════════════════════════════════════════════════════════

def test_parse_file_active_only(tmp_path):
    from app.master.connectors.florida import parse_file
    f = tmp_path / "test.txt"
    lines = [
        _make_line(name="ACTIVE CO", status="A"),
        _make_line(name="INACTIVE CO", status="I"),
        _make_line(name="ACTIVE TWO", status="A"),
    ]
    f.write_text("\n".join(lines) + "\n", encoding="ascii")
    records = list(parse_file(str(f), active_only=True))
    assert len(records) == 2
    assert all(r.status == "A" for r in records)


def test_parse_file_with_limit(tmp_path):
    from app.master.connectors.florida import parse_file
    f = tmp_path / "test.txt"
    lines = [_make_line(name=f"COMPANY {i}") for i in range(10)]
    f.write_text("\n".join(lines) + "\n", encoding="ascii")
    records = list(parse_file(str(f), limit=3))
    assert len(records) == 3


def test_parse_file_with_offset(tmp_path):
    from app.master.connectors.florida import parse_file
    f = tmp_path / "test.txt"
    lines = [_make_line(name=f"COMPANY {i}", corp_num=f"P0000000000{i}") for i in range(5)]
    f.write_text("\n".join(lines) + "\n", encoding="ascii")
    records = list(parse_file(str(f), offset=2, limit=2))
    assert len(records) == 2
    assert records[0].corp_name == "COMPANY 2"


def test_parse_file_filing_type_filter(tmp_path):
    from app.master.connectors.florida import parse_file
    f = tmp_path / "test.txt"
    lines = [
        _make_line(name="CORP", filing_type="DOMP"),
        _make_line(name="LLC", filing_type="FLAL"),
        _make_line(name="NP", filing_type="DOMNP"),
    ]
    f.write_text("\n".join(lines) + "\n", encoding="ascii")
    records = list(parse_file(str(f), filing_types={"FLAL"}))
    assert len(records) == 1
    assert records[0].corp_name == "LLC"


# ════════════════════════════════════════════════════════════════════
# 5. TO_DICT CONVERSION
# ════════════════════════════════════════════════════════════════════

def test_to_dict_shape():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line(name="ACME INC", city="MIAMI", state="FL"))
    d = rec.to_dict()
    assert d["company_name"] == "ACME INC"
    assert d["source"] == "florida_dos"
    assert d["location"] == "MIAMI, FL"
    assert d["corp_number"] == "P12345000001"
    assert d["filing_type"] == "DOMP"


def test_to_dict_no_domain():
    from app.master.connectors.florida import parse_line
    rec = parse_line(_make_line())
    d = rec.to_dict()
    assert d["domain"] == ""


# ════════════════════════════════════════════════════════════════════
# 6. NORMALIZATION INTEGRATION
# ════════════════════════════════════════════════════════════════════

def test_florida_names_normalize():
    from app.master.canonical import normalize_company_name
    cases = [
        ("SUNSHINE TECH INC", "sunshine tech"),
        ("FLORIDA DIGITAL SOLUTIONS LLC", "florida digital solutions"),
        ("PALM BEACH ANALYTICS CORP", "palm beach analytics"),
        ("GULF COAST MANUFACTURING LLC", "gulf coast manufacturing"),
    ]
    for raw, expected in cases:
        result = normalize_company_name(raw)
        assert result == expected, f"{raw!r} -> {result!r}, expected {expected!r}"


# ════════════════════════════════════════════════════════════════════
# 7. FIXTURE FILE
# ════════════════════════════════════════════════════════════════════

def test_parse_fixture_file():
    from app.master.connectors.florida import parse_file
    fixture = Path(__file__).resolve().parent.parent.parent / "tools" / "data" / "florida_sample.txt"
    if not fixture.exists():
        return  # skip if not available
    records = list(parse_file(str(fixture), active_only=False))
    assert len(records) == 10
    assert records[0].corp_name == "SUNSHINE TECH INC"


def test_fixture_active_filter():
    from app.master.connectors.florida import parse_file
    fixture = Path(__file__).resolve().parent.parent.parent / "tools" / "data" / "florida_sample.txt"
    if not fixture.exists():
        return
    records = list(parse_file(str(fixture), active_only=True))
    # Record 8 (ATLANTIC VENTURES) is inactive
    assert len(records) == 9
    assert all(r.status == "A" for r in records)


def test_count_records_fixture():
    from app.master.connectors.florida import count_records
    fixture = Path(__file__).resolve().parent.parent.parent / "tools" / "data" / "florida_sample.txt"
    if not fixture.exists():
        return
    stats = count_records(str(fixture), active_only=False)
    assert stats["total"] == 10
    assert stats["by_status"]["A"] == 9
    assert stats["by_status"]["I"] == 1


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    import tempfile
    tmp = Path(tempfile.mkdtemp())

    tests = [
        ("parse.corp_number", test_parse_corp_number),
        ("parse.corp_name", test_parse_corp_name),
        ("parse.status", test_parse_status),
        ("parse.filing_type", test_parse_filing_type),
        ("parse.city_state", test_parse_city_state),
        ("parse.fei_number", test_parse_fei_number),
        ("parse.empty_fei", test_parse_empty_fei),
        ("date.mmddyyyy", test_parse_date_mmddyyyy),
        ("date.empty", test_parse_date_empty),
        ("date.invalid", test_parse_date_invalid),
        ("entity.domp", test_entity_type_domp),
        ("entity.flal", test_entity_type_flal),
        ("entity.domnp", test_entity_type_domnp),
        ("entity.unknown", test_entity_type_unknown),
        ("filter.active_only", lambda: test_parse_file_active_only(tmp)),
        ("filter.limit", lambda: test_parse_file_with_limit(tmp)),
        ("filter.offset", lambda: test_parse_file_with_offset(tmp)),
        ("filter.filing_type", lambda: test_parse_file_filing_type_filter(tmp)),
        ("dict.shape", test_to_dict_shape),
        ("dict.no_domain", test_to_dict_no_domain),
        ("normalize.florida_names", test_florida_names_normalize),
        ("fixture.parse", test_parse_fixture_file),
        ("fixture.active_filter", test_fixture_active_filter),
        ("fixture.count", test_count_records_fixture),
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

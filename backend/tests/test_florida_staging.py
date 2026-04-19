"""Tests for Florida staging pipeline — Phase 2.

Validates:
  1. Parser state fallback (state_country when state is empty)
  2. City comma cleanup
  3. to_dict output shape with new fields
  4. Normalization of real Florida company names
  5. Real file parsing (20260413c.txt fixture)
  6. Dry-run report shape

Run:
  python backend/tests/test_florida_staging.py
"""

import json
import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


REAL_FILE = Path(__file__).resolve().parent.parent / "tools" / "data" / "raw" / "florida" / "20260413c.txt"


# ════════════════════════════════════════════════════════════════════
# Helper
# ════════════════════════════════════════════════════════════════════

def _make_line(**overrides):
    """Build a 1440-char line with sensible defaults."""
    defaults = {
        "corp_num": "L26000193660",
        "name": "TEST COMPANY LLC",
        "status": "A",
        "filing_type": "FLAL",
        "address1": "100 MAIN ST",
        "city": "MIAMI,",
        "state": "  ",
        "zipcode": "33131",
        "country": "US",
        "file_date": "04132026",
        "fei": "",
        "state_country": "FL",
        "agent_name": "JOHN DOE",
        "agent_address": "200 AGENT ST",
        "agent_city": "MIAMI",
        "agent_state": "FL",
    }
    d = {**defaults, **overrides}

    line = ""
    line += d["corp_num"].ljust(12)
    line += d["name"].ljust(192)
    line += d["status"]
    line += d["filing_type"].ljust(15)
    line += d["address1"].ljust(42)
    line += "".ljust(42)  # address2
    line += d["city"].ljust(28)
    line += d["state"].ljust(2)
    line += d["zipcode"].ljust(10)
    line += d["country"].ljust(2)
    line += "".ljust(126)  # mailing address
    line += d["file_date"].ljust(8)
    line += d["fei"].ljust(14)
    line += " "  # more officers
    line += d["file_date"].ljust(8)
    line += d["state_country"].ljust(2)
    line += "".ljust(39)
    line += d["agent_name"].ljust(42)
    line += "P"
    line += d["agent_address"].ljust(42)
    line += d["agent_city"].ljust(28)
    line += d["agent_state"].ljust(2)
    line += "".ljust(9)  # agent zip
    remaining = 1440 - len(line)
    line += "".ljust(max(0, remaining))
    return line[:1440]


# ════════════════════════════════════════════════════════════════════
# 1. STATE FALLBACK
# ════════════════════════════════════════════════════════════════════

def test_effective_state_from_state_country():
    from app.master.connectors.florida import parse_line
    line = _make_line(state="  ", state_country="FL")
    rec = parse_line(line)
    assert rec is not None
    assert rec.state == ""
    assert rec.state_country == "FL"
    assert rec.effective_state == "FL"


def test_effective_state_principal_takes_priority():
    from app.master.connectors.florida import parse_line
    line = _make_line(state="CA", state_country="FL")
    rec = parse_line(line)
    assert rec.effective_state == "CA"


def test_effective_state_default_fl():
    from app.master.connectors.florida import parse_line
    line = _make_line(state="  ", state_country="  ")
    rec = parse_line(line)
    assert rec.effective_state == "FL"


# ════════════════════════════════════════════════════════════════════
# 2. CITY CLEANUP
# ════════════════════════════════════════════════════════════════════

def test_clean_city_strips_comma():
    from app.master.connectors.florida import parse_line
    line = _make_line(city="DELTONA,")
    rec = parse_line(line)
    assert rec.clean_city == "DELTONA"


def test_clean_city_no_trailing():
    from app.master.connectors.florida import parse_line
    line = _make_line(city="ORLANDO")
    rec = parse_line(line)
    assert rec.clean_city == "ORLANDO"


def test_clean_city_empty():
    from app.master.connectors.florida import parse_line
    line = _make_line(city="")
    rec = parse_line(line)
    assert rec.clean_city == ""


# ════════════════════════════════════════════════════════════════════
# 3. TO_DICT SHAPE
# ════════════════════════════════════════════════════════════════════

def test_to_dict_has_all_fields():
    from app.master.connectors.florida import parse_line
    line = _make_line()
    rec = parse_line(line)
    d = rec.to_dict()
    required = {
        "company_name", "source", "corp_number", "filing_type",
        "entity_type", "status_code", "fei_number", "file_date",
        "address", "city", "state", "zip", "country",
        "agent_name", "agent_address", "agent_city", "agent_state",
        "location", "domain", "industry",
    }
    for f in required:
        assert f in d, f"Missing field: {f}"


def test_to_dict_state_uses_effective():
    from app.master.connectors.florida import parse_line
    line = _make_line(state="  ", state_country="FL")
    rec = parse_line(line)
    d = rec.to_dict()
    assert d["state"] == "FL"


def test_to_dict_location_format():
    from app.master.connectors.florida import parse_line
    line = _make_line(city="TAMPA,", state="  ", state_country="FL")
    rec = parse_line(line)
    d = rec.to_dict()
    assert d["location"] == "TAMPA, FL"


# ════════════════════════════════════════════════════════════════════
# 4. REAL NAME NORMALIZATION
# ════════════════════════════════════════════════════════════════════

def test_normalize_florida_llc_names():
    from app.master.canonical import normalize_company_name
    cases = [
        ("PRAISE TECH SOLUTIONS, LLC", "praise tech solutions"),
        ("CENTRAL FLORIDA DIRECT PRIMARY CARE, LLC", "central florida direct primary care"),
        ("AGENT97 LLC", "agent97"),
        ("ANCHOR & KEYS NOTARY SERVICES, LLC", "anchor keys notary services"),
    ]
    for raw, expected in cases:
        result = normalize_company_name(raw)
        assert result == expected, f"{raw!r} -> {result!r}, expected {expected!r}"


def test_normalize_florida_corp_names():
    from app.master.canonical import normalize_company_name
    cases = [
        ("SUNSHINE ENTERPRISES INC", "sunshine"),
        ("PALM BEACH HOLDINGS CORP", "palm beach"),
    ]
    for raw, expected in cases:
        result = normalize_company_name(raw)
        assert result == expected, f"{raw!r} -> {result!r}, expected {expected!r}"


# ════════════════════════════════════════════════════════════════════
# 5. REAL FILE PARSING
# ════════════════════════════════════════════════════════════════════

def test_real_file_parses():
    if not REAL_FILE.exists():
        return
    from app.master.connectors.florida import parse_file
    records = list(parse_file(str(REAL_FILE), limit=10, active_only=False))
    assert len(records) == 10
    for r in records:
        assert r.corp_number
        assert r.corp_name
        assert r.effective_state  # should never be empty


def test_real_file_effective_state():
    if not REAL_FILE.exists():
        return
    from app.master.connectors.florida import parse_file
    records = list(parse_file(str(REAL_FILE), limit=50, active_only=False))
    for r in records:
        assert r.effective_state, f"{r.corp_name} has no effective_state"


def test_real_file_to_dict_valid():
    if not REAL_FILE.exists():
        return
    from app.master.connectors.florida import parse_file
    records = list(parse_file(str(REAL_FILE), limit=5))
    for r in records:
        d = r.to_dict()
        assert d["company_name"]
        assert d["source"] == "florida_dos"
        assert d["corp_number"]
        assert d["state"]  # effective_state via to_dict


def test_real_file_agent_fields():
    if not REAL_FILE.exists():
        return
    from app.master.connectors.florida import parse_file
    records = list(parse_file(str(REAL_FILE), limit=10))
    with_agent = [r for r in records if r.agent_name]
    assert len(with_agent) > 0, "Expected at least some records with agent names"


# ════════════════════════════════════════════════════════════════════
# 6. DRY-RUN REPORT
# ════════════════════════════════════════════════════════════════════

def test_dry_run_report_shape():
    from app.master.connectors.florida_staging import _dry_run_report
    from app.master.connectors.florida import parse_line
    line = _make_line(name="DRY RUN TEST LLC")
    rec = parse_line(line)
    report = _dry_run_report([rec], "test_batch")
    assert report["status"] == "dry_run"
    assert report["total_parsed"] == 1
    assert len(report["sample"]) == 1
    assert report["sample"][0]["normalized"] == "dry run test"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    tests = [
        ("state.fallback_state_country", test_effective_state_from_state_country),
        ("state.principal_priority", test_effective_state_principal_takes_priority),
        ("state.default_fl", test_effective_state_default_fl),
        ("city.strips_comma", test_clean_city_strips_comma),
        ("city.no_trailing", test_clean_city_no_trailing),
        ("city.empty", test_clean_city_empty),
        ("dict.all_fields", test_to_dict_has_all_fields),
        ("dict.effective_state", test_to_dict_state_uses_effective),
        ("dict.location_format", test_to_dict_location_format),
        ("norm.llc_names", test_normalize_florida_llc_names),
        ("norm.corp_names", test_normalize_florida_corp_names),
        ("real.parses", test_real_file_parses),
        ("real.effective_state", test_real_file_effective_state),
        ("real.to_dict", test_real_file_to_dict_valid),
        ("real.agent_fields", test_real_file_agent_fields),
        ("dry_run.shape", test_dry_run_report_shape),
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

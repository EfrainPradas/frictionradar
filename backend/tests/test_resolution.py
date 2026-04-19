"""Tests for entity resolution — Phase 3.

Validates:
  1. Token similarity
  2. Pair scoring rules
  3. Canonical selection
  4. Dry-run report
  5. False positive resistance
  6. Model instantiation

Run:
  pytest backend/tests/test_resolution.py -v
  python backend/tests/test_resolution.py
"""

import sys
from pathlib import Path
from uuid import uuid4

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# Helper: create fake CompanyMaster objects for testing
# ════════════════════════════════════════════════════════════════════

def _make_master(legal_name, normalized_name, state=None, _id=None):
    """Create a minimal CompanyMaster-like object for scoring tests."""
    from app.master.models import CompanyMaster
    m = CompanyMaster(
        legal_name=legal_name,
        normalized_name=normalized_name,
        jurisdiction_state=state,
        entity_status="active",
    )
    m.id = _id or uuid4()
    return m


def _empty_indexes():
    from app.master.resolver import _Indexes
    return _Indexes()


# ════════════════════════════════════════════════════════════════════
# 1. TOKEN SIMILARITY
# ════════════════════════════════════════════════════════════════════

def test_token_sim_identical():
    from app.master.resolver import _token_similarity
    assert _token_similarity("stripe", "stripe") == 1.0


def test_token_sim_disjoint():
    from app.master.resolver import _token_similarity
    assert _token_similarity("apple", "microsoft") == 0.0


def test_token_sim_partial():
    from app.master.resolver import _token_similarity
    # "goldman sachs" vs "goldman" → 1 overlap, 2 union → 0.5
    assert _token_similarity("goldman sachs", "goldman") == 0.5


def test_token_sim_high():
    from app.master.resolver import _token_similarity
    # "america first credit union" vs "america first credit" → 3/4 = 0.75
    result = _token_similarity("america first credit union", "america first credit")
    assert 0.74 <= result <= 0.76


def test_token_sim_empty():
    from app.master.resolver import _token_similarity
    assert _token_similarity("", "hello") == 0.0
    assert _token_similarity("", "") == 0.0


# ════════════════════════════════════════════════════════════════════
# 2. PAIR SCORING — EXACT NAME
# ════════════════════════════════════════════════════════════════════

def test_score_exact_name():
    from app.master.resolver import _score_pair, EXACT_NAME
    idx = _empty_indexes()
    a = _make_master("Stripe Inc", "stripe")
    b = _make_master("Stripe, Inc.", "stripe")
    result = _score_pair(a, b, idx)
    assert result is not None
    assert result.confidence == 0.960
    assert result.reason_code == EXACT_NAME


def test_score_different_names_no_match():
    from app.master.resolver import _score_pair
    idx = _empty_indexes()
    a = _make_master("Apple", "apple")
    b = _make_master("Microsoft", "microsoft")
    result = _score_pair(a, b, idx)
    assert result is None


# ════════════════════════════════════════════════════════════════════
# 3. PAIR SCORING — EXACT DOMAIN
# ════════════════════════════════════════════════════════════════════

def test_score_exact_domain():
    from app.master.resolver import _score_pair, EXACT_DOMAIN
    idx = _empty_indexes()
    a = _make_master("Stripe Inc", "stripe")
    b = _make_master("Stripe Technologies", "stripe technologies")
    idx.domains[a.id] = {"stripe.com"}
    idx.domains[b.id] = {"stripe.com"}
    result = _score_pair(a, b, idx)
    assert result is not None
    assert result.confidence == 0.980
    assert result.reason_code == EXACT_DOMAIN


def test_score_different_domains_no_domain_match():
    from app.master.resolver import _score_pair
    idx = _empty_indexes()
    a = _make_master("Acme Corp", "acme")
    b = _make_master("Acme LLC", "acme")
    idx.domains[a.id] = {"acme.com"}
    idx.domains[b.id] = {"acme.io"}
    # Should still match by exact name (acme == acme), not domain
    result = _score_pair(a, b, idx)
    assert result is not None
    assert result.reason_code == "exact_name"


# ════════════════════════════════════════════════════════════════════
# 4. PAIR SCORING — EXTERNAL ID
# ════════════════════════════════════════════════════════════════════

def test_score_exact_ext_id():
    from app.master.resolver import _score_pair, EXACT_EXT_ID
    idx = _empty_indexes()
    a = _make_master("Amazon.com Inc", "amazon com")
    b = _make_master("Amazon Web Services", "amazon web services")
    idx.ext_ids[a.id] = {"ein:91-1646860"}
    idx.ext_ids[b.id] = {"ein:91-1646860"}
    result = _score_pair(a, b, idx)
    assert result is not None
    assert result.confidence == 1.000
    assert result.reason_code == EXACT_EXT_ID


# ════════════════════════════════════════════════════════════════════
# 5. PAIR SCORING — NAME + STATE
# ════════════════════════════════════════════════════════════════════

def test_score_name_plus_state():
    from app.master.resolver import _score_pair, NAME_PLUS_STATE
    idx = _empty_indexes()
    a = _make_master("Bank of Utah Corp", "bank utah", "UT")
    b = _make_master("Bank of Utah Holdings", "bank utah", "UT")
    # Same name + same state but exact_name already fires (same norm)
    result = _score_pair(a, b, idx)
    assert result is not None
    # exact_name has higher confidence (0.960 > 0.850)
    assert result.confidence >= 0.850


def test_score_name_state_different_state():
    from app.master.resolver import _score_pair
    idx = _empty_indexes()
    a = _make_master("First National Bank", "first national bank", "UT")
    b = _make_master("First National Bank", "first national bank", "CA")
    # Exact name match wins (0.960) regardless of state
    result = _score_pair(a, b, idx)
    assert result is not None
    assert result.confidence == 0.960


# ════════════════════════════════════════════════════════════════════
# 6. PAIR SCORING — ALIAS MATCH
# ════════════════════════════════════════════════════════════════════

def test_score_alias_match():
    from app.master.resolver import _score_pair, ALIAS_MATCH
    idx = _empty_indexes()
    a = _make_master("AAPC", "aapc")
    b = _make_master("AAPC Healthcare", "aapc healthcare")
    # a has an alias that matches b's normalized name? No.
    # b has an alias that matches a's normalized name? Let's set it up:
    idx.aliases[b.id] = {"aapc"}  # alias of b matches normalized name of a
    result = _score_pair(a, b, idx)
    assert result is not None
    assert result.confidence == 0.820
    assert result.reason_code == ALIAS_MATCH


# ════════════════════════════════════════════════════════════════════
# 7. PAIR SCORING — FUZZY NAME
# ════════════════════════════════════════════════════════════════════

def test_score_fuzzy_name():
    from app.master.resolver import _score_pair, FUZZY_NAME
    idx = _empty_indexes()
    # "utah jazz basketball" vs "utah jazz sports" → overlap=2/4 = 0.5, too low
    # Need higher overlap: "beneficial financial group" vs "beneficial financial services"
    # overlap = {beneficial, financial} = 2, union = {beneficial, financial, group, services} = 4 → 0.5, still low
    # Let's use: "zions bancorporation holding" vs "zions bancorporation" → 2/3 = 0.667, not enough (need 0.85)
    # "deseret management corp" vs "deseret management" → 2/3 = 0.667
    # For fuzzy to fire we need >= 0.85 token similarity
    # "deseret digital media inc" vs "deseret digital media" → 3/4 = 0.75 — nope
    # "a b c d e f g" vs "a b c d e f" → 6/7 = 0.857 — yes!
    # Need >= 0.85 token sim: 6/7 = 0.857
    a = _make_master("Alpha Beta Gamma Delta Epsilon Zeta Corp", "alpha beta gamma delta epsilon zeta")
    b = _make_master("Alpha Beta Gamma Delta Epsilon Zeta Eta", "alpha beta gamma delta epsilon zeta eta")
    result = _score_pair(a, b, idx)
    assert result is not None
    assert result.confidence == 0.650
    assert result.reason_code == FUZZY_NAME


# ════════════════════════════════════════════════════════════════════
# 8. FALSE POSITIVE RESISTANCE
# ════════════════════════════════════════════════════════════════════

def test_no_match_short_different_names():
    """Short but distinct company names should not match."""
    from app.master.resolver import _score_pair
    idx = _empty_indexes()
    a = _make_master("Podium", "podium")
    b = _make_master("Pluralsight", "pluralsight")
    assert _score_pair(a, b, idx) is None


def test_no_match_partial_overlap():
    """Partial word overlap shouldn't match below threshold."""
    from app.master.resolver import _score_pair
    idx = _empty_indexes()
    a = _make_master("Utah Valley University", "utah valley university")
    b = _make_master("Utah State University", "utah state university")
    # overlap = {utah, university} = 2, union = {utah, valley, state, university} = 4 → 0.5
    result = _score_pair(a, b, idx)
    assert result is None  # 0.5 < REVIEW_THRESHOLD(0.50) — not flagged


def test_no_match_same_industry_different_company():
    """Companies in same industry with similar generic words should not match."""
    from app.master.resolver import _score_pair
    idx = _empty_indexes()
    a = _make_master("Mountain West Financial", "mountain west financial")
    b = _make_master("Western Financial Group", "western financial")
    # overlap = {financial, western} vs {mountain, west, financial} → tricky
    # Actually: tokens_a = {mountain, west, financial}, tokens_b = {western, financial}
    # overlap = {financial} = 1, union = {mountain, west, financial, western} = 4 → 0.25
    result = _score_pair(a, b, idx)
    assert result is None


# ════════════════════════════════════════════════════════════════════
# 9. THRESHOLDS AND CONSTANTS
# ════════════════════════════════════════════════════════════════════

def test_auto_merge_threshold():
    from app.master.resolver import AUTO_MERGE_THRESHOLD
    assert AUTO_MERGE_THRESHOLD == 0.95


def test_review_threshold():
    from app.master.resolver import REVIEW_THRESHOLD
    assert REVIEW_THRESHOLD == 0.50


def test_reason_codes_exist():
    from app.master.resolver import (
        EXACT_EXT_ID, EXACT_DOMAIN, EXACT_NAME,
        NAME_PLUS_STATE, ALIAS_MATCH, FUZZY_NAME,
    )
    codes = {EXACT_EXT_ID, EXACT_DOMAIN, EXACT_NAME, NAME_PLUS_STATE, ALIAS_MATCH, FUZZY_NAME}
    assert len(codes) == 6


# ════════════════════════════════════════════════════════════════════
# 10. MODEL INSTANTIATION
# ════════════════════════════════════════════════════════════════════

def test_model_match_candidate():
    from app.master.resolution_models import CompanyMatchCandidate
    c = CompanyMatchCandidate(
        confidence=0.960,
        reason_code="exact_name",
        reason_detail="test",
    )
    assert c.reason_code == "exact_name"


def test_model_merge_decision():
    from app.master.resolution_models import CompanyMergeDecision
    d = CompanyMergeDecision(
        merge_reason="test merge",
        confidence=0.980,
        merged_by="auto",
    )
    assert d.merged_by == "auto"


def test_model_resolution_log():
    from app.master.resolution_models import CompanyResolutionLog
    log = CompanyResolutionLog()
    assert log.__tablename__ == "company_resolution_log"


def test_model_table_names():
    from app.master.resolution_models import (
        CompanyMatchCandidate,
        CompanyMergeDecision,
        CompanyResolutionLog,
    )
    assert CompanyMatchCandidate.__tablename__ == "company_match_candidates"
    assert CompanyMergeDecision.__tablename__ == "company_merge_decisions"
    assert CompanyResolutionLog.__tablename__ == "company_resolution_log"


# ════════════════════════════════════════════════════════════════════
# 11. DRY RUN REPORT STRUCTURE
# ════════════════════════════════════════════════════════════════════

def test_dry_run_report_structure():
    from app.master.resolver import _dry_run_report, MatchResult
    id1, id2 = uuid4(), uuid4()
    # Ensure canonical ordering
    if id1 > id2:
        id1, id2 = id2, id1
    masters = [
        _make_master("A Corp", "a", _id=id1),
        _make_master("B Corp", "b", _id=id2),
    ]
    candidates = {
        (id1, id2): MatchResult(0.960, "exact_name", "test")
    }
    report = _dry_run_report(candidates, masters)
    assert report["status"] == "dry_run"
    assert report["total_records"] == 2
    assert report["total_candidates"] == 1
    assert report["would_auto_merge"] == 1
    assert len(report["pairs"]) == 1
    assert report["pairs"][0]["confidence"] == 0.960


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    import traceback

    tests = [
        ("sim.identical", test_token_sim_identical),
        ("sim.disjoint", test_token_sim_disjoint),
        ("sim.partial", test_token_sim_partial),
        ("sim.high", test_token_sim_high),
        ("sim.empty", test_token_sim_empty),
        ("score.exact_name", test_score_exact_name),
        ("score.different_names", test_score_different_names_no_match),
        ("score.exact_domain", test_score_exact_domain),
        ("score.diff_domains", test_score_different_domains_no_domain_match),
        ("score.exact_ext_id", test_score_exact_ext_id),
        ("score.name_plus_state", test_score_name_plus_state),
        ("score.name_diff_state", test_score_name_state_different_state),
        ("score.alias_match", test_score_alias_match),
        ("score.fuzzy_name", test_score_fuzzy_name),
        ("fp.short_different", test_no_match_short_different_names),
        ("fp.partial_overlap", test_no_match_partial_overlap),
        ("fp.same_industry", test_no_match_same_industry_different_company),
        ("const.auto_threshold", test_auto_merge_threshold),
        ("const.review_threshold", test_review_threshold),
        ("const.reason_codes", test_reason_codes_exist),
        ("model.match_candidate", test_model_match_candidate),
        ("model.merge_decision", test_model_merge_decision),
        ("model.resolution_log", test_model_resolution_log),
        ("model.table_names", test_model_table_names),
        ("report.dry_run_structure", test_dry_run_report_structure),
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

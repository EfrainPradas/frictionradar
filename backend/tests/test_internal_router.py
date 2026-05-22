"""Tests for /internal/v1 router (NovaWork server-to-server).

Covers:
  1. Auth gate — no token / wrong token → 401; missing env var → 503
  2. _normalize_domain — strips http(s)://, www., trailing slash
  3. _cache_to_snapshot — SmartMatchCache → CompanySnapshot shape
  4. /companies/resolve — 200 when company found, 404 otherwise
  5. /match — calls smart_match_engine and shapes response

The router tests stub the DB dependency + smart_match_engine to avoid
hitting Supabase / OpenAI.

Run:
  python backend/tests/test_internal_router.py
  pytest backend/tests/test_internal_router.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. Domain normalization (pure)
# ════════════════════════════════════════════════════════════════════

def test_normalize_domain_strips_scheme():
    from app.api.routers.internal import _normalize_domain

    assert _normalize_domain("https://stripe.com") == "stripe.com"
    assert _normalize_domain("http://stripe.com") == "stripe.com"


def test_normalize_domain_strips_www():
    from app.api.routers.internal import _normalize_domain

    assert _normalize_domain("www.stripe.com") == "stripe.com"
    assert _normalize_domain("https://www.stripe.com") == "stripe.com"


def test_normalize_domain_strips_trailing_slash_and_lowercases():
    from app.api.routers.internal import _normalize_domain

    assert _normalize_domain("Stripe.COM/") == "stripe.com"
    assert _normalize_domain("  https://WWW.Stripe.com/ ") == "stripe.com"


def test_normalize_domain_handles_empty():
    from app.api.routers.internal import _normalize_domain

    assert _normalize_domain("") == ""
    assert _normalize_domain(None) == ""


# ════════════════════════════════════════════════════════════════════
# 2. Snapshot shaper
# ════════════════════════════════════════════════════════════════════

def _make_cache_row(**overrides):
    base = {
        "company_id": uuid4(),
        "domain": "stripe.com",
        "friction_score": 61.0,
        "diagnostic_state": "operational",
        "main_pain": "hiring scale",
        "where_pain_lives": "eng",
        "what_the_company_needs": "VP Eng",
        "recommended_positioning": "scale-up playbook",
        "confidence": "high",
        "eligibility_gate": "full",
        "inferred_sector": "fintech",
        "evaluation_kpis": {"positioning_readiness": 0.81},
        "refreshed_at": datetime(2026, 4, 18, 1, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_cache_to_snapshot_maps_fields():
    from app.api.routers.internal import _cache_to_snapshot

    row = _make_cache_row()
    snap = _cache_to_snapshot(row)
    assert snap.domain == "stripe.com"
    assert snap.friction_score == 61.0
    assert snap.main_pain == "hiring scale"
    assert snap.recommended_positioning == "scale-up playbook"
    assert snap.inferred_sector == "fintech"
    assert snap.confidence == "high"
    assert snap.kpis == {"positioning_readiness": 0.81}
    assert snap.refreshed_at == "2026-04-18T01:00:00+00:00"


def test_cache_to_snapshot_tolerates_nones():
    from app.api.routers.internal import _cache_to_snapshot

    row = _make_cache_row(
        friction_score=None,
        refreshed_at=None,
        main_pain=None,
        evaluation_kpis=None,
    )
    snap = _cache_to_snapshot(row)
    assert snap.friction_score is None
    assert snap.refreshed_at is None
    assert snap.main_pain is None
    assert snap.kpis is None


# ════════════════════════════════════════════════════════════════════
# 3. Auth gate (verify_internal_token)
# ════════════════════════════════════════════════════════════════════

def test_verify_token_missing_env_raises_503(monkeypatch):
    from fastapi import HTTPException

    from app.api.routers.internal import verify_internal_token

    monkeypatch.delenv("FRICTIONRADAR_INTERNAL_TOKEN", raising=False)
    try:
        verify_internal_token(x_internal_token="anything")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 503


def test_verify_token_missing_header_raises_401(monkeypatch):
    from fastapi import HTTPException

    from app.api.routers.internal import verify_internal_token

    monkeypatch.setenv("FRICTIONRADAR_INTERNAL_TOKEN", "secret")
    try:
        verify_internal_token(x_internal_token=None)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401


def test_verify_token_wrong_header_raises_401(monkeypatch):
    from fastapi import HTTPException

    from app.api.routers.internal import verify_internal_token

    monkeypatch.setenv("FRICTIONRADAR_INTERNAL_TOKEN", "secret")
    try:
        verify_internal_token(x_internal_token="nope")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401


def test_verify_token_match_passes(monkeypatch):
    from app.api.routers.internal import verify_internal_token

    monkeypatch.setenv("FRICTIONRADAR_INTERNAL_TOKEN", "secret")
    # No exception raised
    assert verify_internal_token(x_internal_token="secret") is None


# ════════════════════════════════════════════════════════════════════
# 4. FastAPI endpoint tests (TestClient + dependency overrides)
# ════════════════════════════════════════════════════════════════════

def _build_test_app(monkeypatch):
    """Mount the internal router on a standalone app with get_db overridden."""
    from fastapi import FastAPI

    from app.api.routers import internal as internal_router
    from app.db.session import get_db

    monkeypatch.setenv("FRICTIONRADAR_INTERNAL_TOKEN", "secret")

    app = FastAPI()
    app.include_router(internal_router.router, prefix="/internal/v1")

    fake_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: fake_db
    return app, fake_db


def test_endpoint_requires_token(monkeypatch):
    from fastapi.testclient import TestClient

    app, _ = _build_test_app(monkeypatch)
    client = TestClient(app)
    resp = client.get("/internal/v1/companies/resolve?domain=stripe.com")
    assert resp.status_code == 401


def test_resolve_company_found(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.routers import internal as internal_router

    app, _ = _build_test_app(monkeypatch)
    cid = uuid4()
    company = SimpleNamespace(
        id=cid, domain="stripe.com", name="Stripe", inferred_sector="fintech"
    )
    monkeypatch.setattr(
        internal_router.company_service,
        "find_by_domain",
        lambda db, d: company,
    )

    client = TestClient(app)
    resp = client.get(
        "/internal/v1/companies/resolve?domain=https://www.Stripe.com/",
        headers={"X-Internal-Token": "secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_id"] == str(cid)
    assert body["domain"] == "stripe.com"
    assert body["inferred_sector"] == "fintech"


def test_resolve_company_not_found(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.routers import internal as internal_router

    app, _ = _build_test_app(monkeypatch)
    monkeypatch.setattr(
        internal_router.company_service, "find_by_domain", lambda db, d: None
    )

    client = TestClient(app)
    resp = client.get(
        "/internal/v1/companies/resolve?domain=unknown.com",
        headers={"X-Internal-Token": "secret"},
    )
    assert resp.status_code == 404


def test_resolve_company_missing_domain_returns_400(monkeypatch):
    from fastapi.testclient import TestClient

    app, _ = _build_test_app(monkeypatch)
    client = TestClient(app)
    resp = client.get(
        "/internal/v1/companies/resolve?domain=",
        headers={"X-Internal-Token": "secret"},
    )
    assert resp.status_code == 400


def test_match_endpoint_returns_ranked_results(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.routers import internal as internal_router
    from app.services.smart_match_engine import MatchResult

    app, _ = _build_test_app(monkeypatch)

    snap = {
        "company_id": str(uuid4()),
        "domain": "alpha.com",
        "friction_score": 72.0,
        "diagnostic_state": "operational",
        "main_pain": "hiring scale",
        "where_pain_lives": "eng",
        "what_the_company_needs": "VP Eng",
        "recommended_positioning": "scale-up",
        "confidence": "high",
        "eligibility_gate": "full",
        "inferred_sector": "saas",
        "kpis": {"positioning_readiness": 0.88},
        "refreshed_at": "2026-04-18T01:00:00+00:00",
    }
    fake_matches = [
        MatchResult(
            company_id=snap["company_id"],
            domain="alpha.com",
            fit_score=9.1,
            rationale="strong",
            snapshot=snap,
        )
    ]
    monkeypatch.setattr(
        internal_router.smart_match_engine,
        "rank_companies_for_candidate",
        lambda db, payload, top_k: fake_matches,
    )

    client = TestClient(app)
    resp = client.post(
        "/internal/v1/match",
        headers={"X-Internal-Token": "secret"},
        json={
            "profile_summary": "VP Eng",
            "bullets": ["Grew org 5x"],
            "par_stories": [
                {"problem": "p", "action": "a", "result": "r"}
            ],
            "target_function": "engineering",
            "target_sectors": ["saas"],
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["results"][0]["domain"] == "alpha.com"
    assert body["results"][0]["fit_score"] == 9.1
    assert body["results"][0]["snapshot"]["main_pain"] == "hiring scale"


def test_match_rejects_oversize_top_k(monkeypatch):
    from fastapi.testclient import TestClient

    app, _ = _build_test_app(monkeypatch)
    client = TestClient(app)
    resp = client.post(
        "/internal/v1/match",
        headers={"X-Internal-Token": "secret"},
        json={"top_k": 100, "bullets": [], "par_stories": []},
    )
    # Pydantic Field(le=25) → 422 unprocessable
    assert resp.status_code == 422


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    import pytest

    code = pytest.main([__file__, "-q"])
    return {"exit_code": int(code), "success": code == 0}


if __name__ == "__main__":
    report = run_all_tests()
    print(json.dumps(report, indent=2))
    if not report["success"]:
        sys.exit(1)

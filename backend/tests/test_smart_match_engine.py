"""Tests for smart_match_engine (Smart-Match VIP add-on for NovaWork).

Covers:
  1. Pain/candidate text builders (pure, no network)
  2. embed_pain / embed_candidate with mocked OpenAI client
  3. _parse_rerank_output — robust JSON parsing (array, wrapped, malformed)
  4. _fallback_rank — neutral scoring when LLM unavailable
  5. build_cache_row_values — pure shaper used by nightly refresh
  6. rank_companies_for_candidate — deterministic ordering (engine wired end-to-end
     with stub embeddings + stub OpenAI client)

Run:
  python backend/tests/test_smart_match_engine.py
  pytest backend/tests/test_smart_match_engine.py
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════

def _make_cache_row(**overrides):
    """Build a SmartMatchCache-like object with attribute access."""
    base = {
        "company_id": uuid4(),
        "domain": "example.com",
        "friction_score": 42.5,
        "dominant_friction_type": "hiring_velocity",
        "diagnostic_state": "operational",
        "main_pain": "Can't close senior roles fast enough",
        "where_pain_lives": "Engineering",
        "what_the_company_needs": "Seasoned VP Eng with SaaS scaling reps",
        "best_attack_angle": "Show Series-B scale-up playbook",
        "confidence": "high",
        "eligibility_gate": "full",
        "evaluation_kpis": {"positioning_readiness": 0.82},
        "inferred_sector": "saas",
        "pain_embedding": None,
        "refreshed_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _candidate_payload():
    return {
        "profile_summary": "VP Engineering with 10y scaling SaaS teams from 10→200",
        "bullets": [
            "Grew engineering org 5×",
            "Closed 40 senior hires in 18 months",
            "Stood up hiring ops + panel calibration",
        ],
        "par_stories": [
            {
                "problem": "Stalled senior pipeline",
                "action": "Rebuilt sourcing + panel calibration",
                "result": "12 senior hires in one quarter",
            }
        ],
        "target_function": "engineering",
        "target_sectors": ["saas"],
    }


# ════════════════════════════════════════════════════════════════════
# 1. Text builders
# ════════════════════════════════════════════════════════════════════

def test_pain_text_accepts_dict():
    from app.services.smart_match_engine import _pain_text_for

    row = {"main_pain": "Can't close roles", "inferred_sector": "saas"}
    text = _pain_text_for(row)
    assert "Pain: Can't close roles" in text
    assert "Sector: saas" in text


def test_pain_text_accepts_row_object():
    from app.services.smart_match_engine import _pain_text_for

    row = _make_cache_row()
    text = _pain_text_for(row)
    assert "Pain:" in text
    assert "Needs:" in text
    assert "Best attack angle:" in text
    assert "Sector: saas" in text


def test_pain_text_empty_returns_placeholder():
    from app.services.smart_match_engine import _pain_text_for

    assert _pain_text_for({}) == "(no verdict yet)"


def test_candidate_text_serializes_payload():
    from app.services.smart_match_engine import _candidate_text

    text = _candidate_text(_candidate_payload())
    assert "Profile:" in text
    assert "Recent impact:" in text
    assert "PAR stories:" in text
    assert "Targeting function: engineering" in text
    assert "Targeting sectors: saas" in text


def test_candidate_text_empty_returns_placeholder():
    from app.services.smart_match_engine import _candidate_text

    assert _candidate_text({}) == "(empty candidate payload)"


def test_candidate_text_caps_bullets_and_par():
    from app.services.smart_match_engine import _candidate_text

    payload = {
        "bullets": [f"bullet-{i}" for i in range(20)],
        "par_stories": [
            {"problem": f"p{i}", "action": f"a{i}", "result": f"r{i}"}
            for i in range(10)
        ],
    }
    text = _candidate_text(payload)
    # top 5 bullets only → bullet-0..bullet-4 in, bullet-5 out
    assert "bullet-0" in text
    assert "bullet-4" in text
    assert "bullet-5" not in text
    # top 3 PAR only → p0..p2 in, p3 out
    assert "p0" in text
    assert "p2" in text
    assert "p3" not in text


# ════════════════════════════════════════════════════════════════════
# 2. Embeddings (mocked OpenAI)
# ════════════════════════════════════════════════════════════════════

def _mock_openai_client(embedding_vec=None, rerank_content=None):
    """Build a mock OpenAI client with chainable embeddings + chat."""
    client = MagicMock()
    if embedding_vec is not None:
        emb_resp = MagicMock()
        emb_resp.data = [MagicMock(embedding=embedding_vec)]
        client.embeddings.create.return_value = emb_resp
    if rerank_content is not None:
        chat_resp = MagicMock()
        chat_resp.choices = [MagicMock(message=MagicMock(content=rerank_content))]
        client.chat.completions.create.return_value = chat_resp
    return client


def test_embed_pain_returns_none_without_api_key(monkeypatch):
    from app.services import smart_match_engine

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    smart_match_engine.reset_openai_client_for_tests()
    assert smart_match_engine.embed_pain({"main_pain": "x"}) is None


def test_embed_pain_returns_vector_with_mock(monkeypatch):
    from app.services import smart_match_engine

    vec = [0.1] * smart_match_engine.EMBEDDING_DIM
    client = _mock_openai_client(embedding_vec=vec)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    smart_match_engine.reset_openai_client_for_tests()
    with patch.object(smart_match_engine, "_get_openai_client", return_value=client):
        out = smart_match_engine.embed_pain({"main_pain": "test"})
    assert isinstance(out, list)
    assert len(out) == smart_match_engine.EMBEDDING_DIM


def test_embed_candidate_returns_vector_with_mock(monkeypatch):
    from app.services import smart_match_engine

    vec = [0.2] * smart_match_engine.EMBEDDING_DIM
    client = _mock_openai_client(embedding_vec=vec)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    smart_match_engine.reset_openai_client_for_tests()
    with patch.object(smart_match_engine, "_get_openai_client", return_value=client):
        out = smart_match_engine.embed_candidate(_candidate_payload())
    assert isinstance(out, list)
    assert len(out) == smart_match_engine.EMBEDDING_DIM


# ════════════════════════════════════════════════════════════════════
# 3. Rerank output parsing
# ════════════════════════════════════════════════════════════════════

def test_parse_rerank_accepts_json_array():
    from app.services.smart_match_engine import _parse_rerank_output

    r1 = _make_cache_row()
    r2 = _make_cache_row()
    content = json.dumps(
        [
            {"company_id": str(r1.company_id), "fit_score": 8.5, "rationale": "strong"},
            {"company_id": str(r2.company_id), "fit_score": 6.0, "rationale": "ok"},
        ]
    )
    out = _parse_rerank_output(content, [r1, r2], top_k=5)
    assert len(out) == 2
    assert out[0]["company_id"] == str(r1.company_id)
    assert out[0]["fit_score"] == 8.5


def test_parse_rerank_accepts_wrapped_object():
    from app.services.smart_match_engine import _parse_rerank_output

    r1 = _make_cache_row()
    content = json.dumps(
        {"results": [{"company_id": str(r1.company_id), "fit_score": 9, "rationale": "x"}]}
    )
    out = _parse_rerank_output(content, [r1], top_k=5)
    assert len(out) == 1
    assert out[0]["fit_score"] == 9.0


def test_parse_rerank_accepts_unknown_wrapper_key():
    """gpt-4o-mini has been observed to wrap under 'top_companies'; accept
    any dict-wrapped list-of-dicts even when the key is not in the allow-list."""
    from app.services.smart_match_engine import _parse_rerank_output

    r1 = _make_cache_row()
    content = json.dumps(
        {
            "top_companies": [
                {"company_id": str(r1.company_id), "fit_score": 8, "rationale": "ok"}
            ]
        }
    )
    out = _parse_rerank_output(content, [r1], top_k=5)
    assert len(out) == 1
    assert out[0]["fit_score"] == 8.0
    assert out[0]["rationale"] == "ok"


def test_parse_rerank_falls_back_on_malformed_json():
    from app.services.smart_match_engine import _parse_rerank_output

    r1 = _make_cache_row()
    out = _parse_rerank_output("not json at all", [r1], top_k=5)
    # fallback — neutral 5.0
    assert len(out) == 1
    assert out[0]["fit_score"] == 5.0


def test_parse_rerank_filters_unknown_company_ids():
    from app.services.smart_match_engine import _parse_rerank_output

    r1 = _make_cache_row()
    unknown = uuid4()
    content = json.dumps(
        [
            {"company_id": str(unknown), "fit_score": 10, "rationale": "nope"},
            {"company_id": str(r1.company_id), "fit_score": 7, "rationale": "yes"},
        ]
    )
    out = _parse_rerank_output(content, [r1], top_k=5)
    assert len(out) == 1
    assert out[0]["company_id"] == str(r1.company_id)


def test_parse_rerank_caps_at_top_k():
    from app.services.smart_match_engine import _parse_rerank_output

    rows = [_make_cache_row() for _ in range(8)]
    content = json.dumps(
        [
            {"company_id": str(r.company_id), "fit_score": 5, "rationale": "-"}
            for r in rows
        ]
    )
    out = _parse_rerank_output(content, rows, top_k=3)
    assert len(out) == 3


def test_parse_rerank_dedupes_repeated_ids():
    from app.services.smart_match_engine import _parse_rerank_output

    r1 = _make_cache_row()
    content = json.dumps(
        [
            {"company_id": str(r1.company_id), "fit_score": 9, "rationale": "first"},
            {"company_id": str(r1.company_id), "fit_score": 3, "rationale": "dup"},
        ]
    )
    out = _parse_rerank_output(content, [r1], top_k=5)
    assert len(out) == 1
    assert out[0]["rationale"] == "first"


# ════════════════════════════════════════════════════════════════════
# 4. Fallback rank
# ════════════════════════════════════════════════════════════════════

def test_fallback_rank_neutral_score():
    from app.services.smart_match_engine import _fallback_rank

    rows = [_make_cache_row() for _ in range(3)]
    out = _fallback_rank(rows, top_k=5)
    assert len(out) == 3
    assert all(r["fit_score"] == 5.0 for r in out)
    assert all("cosine" in r["rationale"].lower() for r in out)


def test_fallback_rank_caps_at_top_k():
    from app.services.smart_match_engine import _fallback_rank

    rows = [_make_cache_row() for _ in range(10)]
    out = _fallback_rank(rows, top_k=4)
    assert len(out) == 4


# ════════════════════════════════════════════════════════════════════
# 5. Cache row builder
# ════════════════════════════════════════════════════════════════════

def test_build_cache_row_values_shape():
    from app.services.smart_match_engine import build_cache_row_values

    company = SimpleNamespace(id=uuid4(), domain="Stripe.com", inferred_sector="fintech")
    score = SimpleNamespace(total_score=73.2, dominant_friction_type="hiring_velocity")
    verdict = {
        "main_pain": "can't close roles",
        "where_pain_lives": "eng",
        "what_the_company_needs": "VP Eng",
        "best_attack_angle": "scale-up playbook",
    }
    evaluation = {
        "kpis": {"positioning_readiness": 0.9},
        "diagnostic_state": "operational",
    }
    eligibility = SimpleNamespace(confidence_band="high", gate_passed="full")

    row = build_cache_row_values(
        company=company,
        verdict=verdict,
        score=score,
        evaluation=evaluation,
        eligibility=eligibility,
        run_id="run-123",
    )
    assert row["company_id"] == company.id
    assert row["domain"] == "stripe.com"  # lowercased
    assert row["friction_score"] == 73.2
    assert row["dominant_friction_type"] == "hiring_velocity"
    assert row["main_pain"] == "can't close roles"
    assert row["confidence"] == "high"
    assert row["eligibility_gate"] == "full"
    assert row["evaluation_kpis"] == {"positioning_readiness": 0.9}
    assert row["inferred_sector"] == "fintech"
    assert row["refresh_run_id"] == "run-123"
    assert row["diagnostic_state"] == "operational"


def test_build_cache_row_values_tolerates_nones():
    from app.services.smart_match_engine import build_cache_row_values

    company = SimpleNamespace(id=uuid4(), domain=None, inferred_sector=None)
    row = build_cache_row_values(
        company=company,
        verdict=None,
        score=None,
        evaluation=None,
        eligibility=SimpleNamespace(confidence_band=None, gate_passed=None),
        run_id=None,
    )
    assert row["domain"] == ""
    assert row["friction_score"] is None
    assert row["main_pain"] is None
    assert row["evaluation_kpis"] is None


# ════════════════════════════════════════════════════════════════════
# 6. End-to-end rank (stubbed embeddings + stubbed OpenAI rerank)
# ════════════════════════════════════════════════════════════════════

class _FakeDB:
    """Minimal stub that returns pre-seeded cache rows from _prefilter_candidates."""

    def __init__(self, rows):
        self._rows = rows


def test_rank_companies_for_candidate_deterministic(monkeypatch):
    from app.services import smart_match_engine

    r1 = _make_cache_row(domain="alpha.com")
    r2 = _make_cache_row(domain="beta.com")
    r3 = _make_cache_row(domain="gamma.com")
    rows = [r1, r2, r3]

    # Bypass SQLAlchemy — return our rows straight from the prefilter.
    monkeypatch.setattr(
        smart_match_engine, "_prefilter_candidates", lambda *a, **kw: rows
    )
    # No embeddings needed (rank_companies_for_candidate tolerates None).
    monkeypatch.setattr(smart_match_engine, "embed_candidate", lambda payload: None)

    # Stub the LLM rerank to pick r2 > r1 deterministically.
    rerank_content = json.dumps(
        [
            {"company_id": str(r2.company_id), "fit_score": 9.1, "rationale": "best"},
            {"company_id": str(r1.company_id), "fit_score": 7.4, "rationale": "ok"},
        ]
    )
    client = _mock_openai_client(rerank_content=rerank_content)
    monkeypatch.setattr(smart_match_engine, "_get_openai_client", lambda: client)

    results = smart_match_engine.rank_companies_for_candidate(
        db=_FakeDB(rows), payload=_candidate_payload(), top_k=5
    )

    assert len(results) == 2
    assert results[0].domain == "beta.com"
    assert results[0].fit_score == 9.1
    assert results[1].domain == "alpha.com"
    # snapshot fields surface neutral FR vocabulary for NovaWork to translate
    assert "main_pain" in results[0].snapshot
    assert "best_attack_angle" in results[0].snapshot


def test_rank_companies_empty_prefilter_returns_empty(monkeypatch):
    from app.services import smart_match_engine

    monkeypatch.setattr(smart_match_engine, "_prefilter_candidates", lambda *a, **kw: [])
    monkeypatch.setattr(smart_match_engine, "embed_candidate", lambda payload: None)

    results = smart_match_engine.rank_companies_for_candidate(
        db=_FakeDB([]), payload=_candidate_payload(), top_k=5
    )
    assert results == []


def test_rank_companies_fallback_when_llm_unavailable(monkeypatch):
    from app.services import smart_match_engine

    r1 = _make_cache_row(domain="alpha.com")
    r2 = _make_cache_row(domain="beta.com")

    monkeypatch.setattr(smart_match_engine, "_prefilter_candidates", lambda *a, **kw: [r1, r2])
    monkeypatch.setattr(smart_match_engine, "embed_candidate", lambda payload: None)
    monkeypatch.setattr(smart_match_engine, "_get_openai_client", lambda: None)

    results = smart_match_engine.rank_companies_for_candidate(
        db=_FakeDB([r1, r2]), payload=_candidate_payload(), top_k=5
    )
    assert len(results) == 2
    assert all(r.fit_score == 5.0 for r in results)


def test_match_result_to_dict_shape():
    from app.services.smart_match_engine import MatchResult

    mr = MatchResult(
        company_id="abc",
        domain="x.com",
        fit_score=8.0,
        rationale="r",
        snapshot={"domain": "x.com"},
    )
    d = mr.to_dict()
    assert d == {
        "company_id": "abc",
        "domain": "x.com",
        "fit_score": 8.0,
        "rationale": "r",
        "snapshot": {"domain": "x.com"},
    }


# ════════════════════════════════════════════════════════════════════
# get_open_roles + snapshot enrichment
# ════════════════════════════════════════════════════════════════════

def _make_role(title, functional_area="engineering", confidence=None, url="https://x/job"):
    return SimpleNamespace(
        role_title=title,
        functional_area=functional_area,
        functional_area_confidence=confidence,
        source_url=url,
        role_location=None,
        discovered_at=None,
    )


def test_get_open_roles_prioritizes_matching_area(monkeypatch):
    """Roles whose functional_area equals `prioritize_functional_area` come first."""
    from app.services import smart_match_engine

    roles = [
        _make_role("Accountant", functional_area="finance"),
        _make_role("Senior Backend Engineer", functional_area="engineering"),
        _make_role("Recruiter", functional_area="hr"),
        _make_role("Tech Lead", functional_area="engineering"),
    ]

    class FakeQ:
        def __init__(self, items): self.items = items
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def limit(self, n): self.items = self.items[:n]; return self
        def all(self): return self.items

    class FakeDB:
        def query(self, *a, **k): return FakeQ(list(roles))

    out = smart_match_engine.get_open_roles(
        FakeDB(), company_id="x", prioritize_functional_area="engineering", limit=3
    )
    assert [r["title"] for r in out[:2]] == ["Senior Backend Engineer", "Tech Lead"]
    assert len(out) == 3


def test_get_open_roles_respects_limit():
    from app.services import smart_match_engine

    roles = [_make_role(f"Role {i}") for i in range(10)]

    class FakeQ:
        def __init__(self, items): self.items = items
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def limit(self, n): self.items = self.items[:n]; return self
        def all(self): return self.items

    class FakeDB:
        def query(self, *a, **k): return FakeQ(list(roles))

    out = smart_match_engine.get_open_roles(FakeDB(), company_id="x", limit=4)
    assert len(out) == 4


def test_get_open_roles_filters_benefits_keywords():
    """Titles containing benefits keywords are dropped even when classifier
    flagged them as hr / other valid functional_area."""
    from app.services import smart_match_engine

    roles = [
        _make_role("Paid Vacation & Sick Leave", functional_area="hr"),
        _make_role("Senior Product Manager", functional_area="product"),
        _make_role("Health & Wellness Program", functional_area="hr"),
        _make_role("Teledoc & Mental Wellbeing", functional_area="hr"),
        _make_role("Engineering Manager", functional_area="engineering"),
    ]

    class FakeQ:
        def __init__(self, items): self.items = items
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def limit(self, n): self.items = self.items[:n]; return self
        def all(self): return self.items

    class FakeDB:
        def query(self, *a, **k): return FakeQ(list(roles))

    out = smart_match_engine.get_open_roles(FakeDB(), company_id="x", limit=5)
    titles = [r["title"] for r in out]
    assert "Senior Product Manager" in titles
    assert "Engineering Manager" in titles
    assert not any("Vacation" in t for t in titles)
    assert not any("Wellness" in t for t in titles)
    assert not any("Teledoc" in t for t in titles)


def test_get_detection_evidence_shape():
    from app.services import smart_match_engine
    from datetime import datetime, timezone

    class FakeScalar:
        def __init__(self, v): self._v = v
        def first(self): return (self._v,) if self._v else None

    class FakeQ:
        def __init__(self, count=0, last=None):
            self._count = count
            self._last = last
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def first(self): return (self._last,) if self._last else None
        def count(self): return self._count

    class FakeDB:
        def __init__(self):
            self._calls = 0
        def query(self, *a, **k):
            self._calls += 1
            # 1st: signal count, 2nd: roles count, 3rd: last signal
            if self._calls == 1:
                return FakeQ(count=42)
            if self._calls == 2:
                return FakeQ(count=5)
            return FakeQ(last=datetime(2026, 4, 15, tzinfo=timezone.utc))

    evidence = smart_match_engine.get_detection_evidence(FakeDB(), "cid")
    assert evidence["signals_analyzed"] == 42
    assert evidence["roles_tracked"] == 5
    assert evidence["last_signal_at"] == "2026-04-15"


def test_get_detection_evidence_handles_no_signals():
    from app.services import smart_match_engine

    class FakeQ:
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def first(self): return None
        def count(self): return 0

    class FakeDB:
        def query(self, *a, **k): return FakeQ()

    evidence = smart_match_engine.get_detection_evidence(FakeDB(), "cid")
    assert evidence["signals_analyzed"] == 0
    assert evidence["roles_tracked"] == 0
    assert evidence["last_signal_at"] is None


def test_snapshot_for_no_db_has_empty_open_roles():
    """When called without a db session, snapshot should have open_roles=[]."""
    from app.services.smart_match_engine import _snapshot_for

    row = _make_cache_row()
    snap = _snapshot_for(row)
    assert snap["open_roles"] == []


def test_snapshot_for_with_db_populates_open_roles(monkeypatch):
    from app.services import smart_match_engine

    monkeypatch.setattr(
        smart_match_engine, "get_open_roles",
        lambda db, cid, **kw: [
            {"title": "Tech Lead", "url": "https://x", "functional_area": "engineering", "location": None}
        ],
    )
    row = _make_cache_row()
    snap = smart_match_engine._snapshot_for(row, db=MagicMock())
    assert len(snap["open_roles"]) == 1
    assert snap["open_roles"][0]["title"] == "Tech Lead"


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

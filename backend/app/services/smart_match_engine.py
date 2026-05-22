"""Smart-Match Engine — ranks FrictionRadar's company universe against a
candidate payload for the NovaWork VIP add-on.

Pipeline:
  1. embed_pain(cache_row)           → vector(1536) persisted nightly
  2. embed_candidate(payload)        → vector(1536) computed per /match call
  3. pre-filter SQL (pgvector cosine, eligibility_gate gate)
                                     → top 50 candidates
  4. rerank_with_llm(payload, top50) → top-N JSON [{company_id, fit_score, rationale}]
  5. rank_companies_for_candidate()  → public entrypoint, orchestrates 2→4

The engine never calls out to OpenAI unless `OPENAI_API_KEY` is set — it
falls back to cosine-only ranking so tests and dev environments stay
deterministic and offline-safe.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.smart_match_cache import SmartMatchCache, EMBEDDING_DIM

logger = get_logger(__name__)

# ─── Config ─────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"
RERANK_MODEL = "gpt-4o-mini"
PRE_FILTER_LIMIT = 50
DEFAULT_TOP_K = 10


# ─── OpenAI client (lazy, optional) ─────────────────────────────────────

_openai_client = None
_openai_init_failed = False


def _get_openai_client():
    """Return cached OpenAI client or None if unavailable."""
    global _openai_client, _openai_init_failed
    if _openai_client is not None:
        return _openai_client
    if _openai_init_failed:
        return None
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        _openai_init_failed = True
        return None
    try:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=api_key)
        return _openai_client
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("smart_match_engine: OpenAI client init failed: %s", exc)
        _openai_init_failed = True
        return None


def reset_openai_client_for_tests() -> None:
    """Clear cached client. Tests should call this after mocking env vars."""
    global _openai_client, _openai_init_failed
    _openai_client = None
    _openai_init_failed = False


# ─── Embeddings ─────────────────────────────────────────────────────────

def _pain_text_for(row: SmartMatchCache | dict) -> str:
    """Build the canonical text that represents a company's pain.

    Accepts either a SmartMatchCache row or a plain dict with the same fields.
    """
    def _get(key: str) -> str:
        if isinstance(row, dict):
            return (row.get(key) or "").strip()
        return (getattr(row, key, None) or "").strip()

    main_pain = _get("main_pain")
    needs = _get("what_the_company_needs")
    angle = _get("recommended_positioning")
    where = _get("where_pain_lives")
    sector = _get("inferred_sector")
    ds = _get("diagnostic_state")

    parts = [
        f"Pain: {main_pain}" if main_pain else "",
        f"Lives in: {where}" if where else "",
        f"Needs: {needs}" if needs else "",
        f"Recommended positioning: {angle}" if angle else "",
        f"Sector: {sector}" if sector else "",
        f"Diagnosis: {ds}" if ds else "",
    ]
    return "\n".join([p for p in parts if p]) or "(no verdict yet)"


def _candidate_text(payload: dict) -> str:
    """Serialize candidate payload to the text used for embedding + LLM rerank."""
    summary = (payload.get("profile_summary") or "").strip()
    bullets = payload.get("bullets") or []
    par = payload.get("par_stories") or []
    target_fn = payload.get("target_function")
    target_sectors = payload.get("target_sectors") or []

    parts = []
    if summary:
        parts.append(f"Profile: {summary}")
    if bullets:
        top_bullets = [b.strip() for b in bullets[:5] if b and b.strip()]
        if top_bullets:
            parts.append("Recent impact:\n- " + "\n- ".join(top_bullets))
    if par:
        par_lines = []
        for story in par[:3]:
            if not isinstance(story, dict):
                continue
            problem = (story.get("problem") or "").strip()
            action = (story.get("action") or "").strip()
            result = (story.get("result") or "").strip()
            if problem or action or result:
                par_lines.append(
                    f"Problem: {problem} | Action: {action} | Result: {result}"
                )
        if par_lines:
            parts.append("PAR stories:\n" + "\n".join(par_lines))
    if target_fn:
        parts.append(f"Targeting function: {target_fn}")
    if target_sectors:
        parts.append(f"Targeting sectors: {', '.join(target_sectors)}")

    return "\n\n".join(parts) or "(empty candidate payload)"


def embed_pain(row: SmartMatchCache | dict) -> Optional[list[float]]:
    """Embed the pain text of a cache row. Returns None if OpenAI unavailable."""
    text_val = _pain_text_for(row)
    return _embed(text_val)


def embed_candidate(payload: dict) -> Optional[list[float]]:
    """Embed a candidate payload. Returns None if OpenAI unavailable."""
    return _embed(_candidate_text(payload))


def _embed(text_val: str) -> Optional[list[float]]:
    client = _get_openai_client()
    if client is None:
        return None
    try:
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text_val)
        return list(resp.data[0].embedding)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("smart_match_engine: embedding failed: %s", exc)
        return None


# ─── Pre-filter (pgvector cosine) ───────────────────────────────────────

def _prefilter_candidates(
    db: Session,
    candidate_vec: Optional[list[float]],
    *,
    target_sectors: Optional[list[str]] = None,
    limit: int = PRE_FILTER_LIMIT,
) -> list[SmartMatchCache]:
    """Top-N by cosine distance, filtered to eligible cache rows.

    Falls back to plain SQL without ordering when candidate_vec is None
    (dev / offline mode).
    """
    q = db.query(SmartMatchCache).filter(
        SmartMatchCache.eligibility_gate.in_(["full", "conditional"]),
        ~SmartMatchCache.domain.like("synth-%.test"),
    )
    if target_sectors:
        q = q.filter(SmartMatchCache.inferred_sector.in_(target_sectors))

    if candidate_vec is None:
        # No embedding — return recent rows so downstream rerank still works.
        return q.order_by(SmartMatchCache.refreshed_at.desc()).limit(limit).all()

    # pgvector cosine distance via <=> operator. SQLAlchemy-pgvector
    # exposes l2_distance / cosine_distance helpers on the Vector column.
    return (
        q.order_by(SmartMatchCache.pain_embedding.cosine_distance(candidate_vec))
        .limit(limit)
        .all()
    )


# ─── LLM rerank ─────────────────────────────────────────────────────────

_RERANK_SYSTEM = (
    "You are a matchmaker between a job candidate and companies that have "
    "hiring pain. For each company, judge how well the candidate could "
    "credibly address that pain. Return ONLY JSON — no prose."
)


def _build_rerank_prompt(payload: dict, rows: list[SmartMatchCache], top_k: int) -> str:
    candidate_block = _candidate_text(payload)

    company_lines = []
    for idx, row in enumerate(rows, start=1):
        company_lines.append(
            f"[{idx}] id={row.company_id} domain={row.domain} sector={row.inferred_sector or 'n/a'}\n"
            f"    pain: {row.main_pain or '-'}\n"
            f"    needs: {row.what_the_company_needs or '-'}\n"
            f"    angle: {row.recommended_positioning or '-'}"
        )
    companies_block = "\n".join(company_lines)

    return (
        f"CANDIDATE:\n{candidate_block}\n\n"
        f"COMPANIES ({len(rows)}):\n{companies_block}\n\n"
        f"Pick the top {top_k} companies. Return a JSON array with fields: "
        f"company_id (string), fit_score (0-10 number), rationale (<=120 chars). "
        f"Order by fit_score descending. Return only the JSON array."
    )


def _rerank_with_llm(
    payload: dict, rows: list[SmartMatchCache], top_k: int
) -> list[dict]:
    """Ask the LLM to pick + score top_k of the pre-filtered rows.

    Falls back to cosine order (first top_k rows passed in) when OpenAI is
    unavailable or returns malformed JSON.
    """
    client = _get_openai_client()
    if client is None or not rows:
        return _fallback_rank(rows, top_k)

    prompt = _build_rerank_prompt(payload, rows, top_k)
    try:
        resp = client.chat.completions.create(
            model=RERANK_MODEL,
            messages=[
                {"role": "system", "content": _RERANK_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("smart_match_engine: LLM rerank failed: %s", exc)
        return _fallback_rank(rows, top_k)

    return _parse_rerank_output(content, rows, top_k)


def _parse_rerank_output(
    content: str, rows: list[SmartMatchCache], top_k: int
) -> list[dict]:
    """Parse LLM output robustly. Accepts either a JSON array or a wrapped object."""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("smart_match_engine: rerank JSON parse failed; falling back")
        return _fallback_rank(rows, top_k)

    if isinstance(parsed, dict):
        # Models sometimes wrap the array under a key. Try known names first,
        # then fall back to the first list-of-dicts value in the object so
        # unexpected keys (e.g. "top_companies", "ranking") still work.
        known_keys = ("results", "companies", "matches", "ranked", "data")
        for key in known_keys:
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break
        else:
            for val in parsed.values():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    parsed = val
                    break
            else:
                return _fallback_rank(rows, top_k)

    if not isinstance(parsed, list):
        return _fallback_rank(rows, top_k)

    by_id = {str(r.company_id): r for r in rows}
    ranked: list[dict] = []
    seen: set[str] = set()

    for item in parsed:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("company_id") or "").strip()
        if cid not in by_id or cid in seen:
            continue
        seen.add(cid)
        try:
            fit = float(item.get("fit_score") or 0.0)
        except (TypeError, ValueError):
            fit = 0.0
        rationale = str(item.get("rationale") or "").strip()[:240]
        ranked.append({"company_id": cid, "fit_score": fit, "rationale": rationale})
        if len(ranked) >= top_k:
            break

    if not ranked:
        return _fallback_rank(rows, top_k)
    return ranked


def _fallback_rank(rows: list[SmartMatchCache], top_k: int) -> list[dict]:
    """Cosine-order fallback. Mostly used when OpenAI is not configured."""
    out: list[dict] = []
    for r in rows[:top_k]:
        out.append(
            {
                "company_id": str(r.company_id),
                "fit_score": 5.0,  # neutral; operator will adjust
                "rationale": "Pre-filter cosine match (LLM rerank unavailable).",
            }
        )
    return out


# ─── Public entrypoint ─────────────────────────────────────────────────

@dataclass
class MatchResult:
    company_id: str
    domain: str
    fit_score: float
    rationale: str
    snapshot: dict

    def to_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "domain": self.domain,
            "fit_score": self.fit_score,
            "rationale": self.rationale,
            "snapshot": self.snapshot,
        }


OPEN_ROLES_LIMIT = 5
_JUNK_FUNCTIONAL_AREAS = {"junk", "unknown", None, ""}
_JUNK_CONFIDENCE_PREFIXES = ("none:junk",)

# Titles that match these patterns are benefits / page sections mis-classified
# as jobs by the role extractor (seen on leavitt.com and similar). We strip
# them post-query because SQL regex-casefold is awkward across Postgres.
_BENEFIT_KEYWORDS = (
    "paid vacation", "sick leave", "vacation &", "insurance", "wellness",
    "mental wellbeing", "teledoc", "401k", "retirement", "holiday",
    "employee recognition", "legends", "voluntary products",
    "dental", "medical insurance", "health & wellness",
    "paid time off", "pto", "benefits",
)


def _looks_like_benefit(title: str) -> bool:
    t = (title or "").lower()
    return any(kw in t for kw in _BENEFIT_KEYWORDS)


def get_open_roles(
    db: Session,
    company_id,
    *,
    prioritize_functional_area: Optional[str] = None,
    limit: int = OPEN_ROLES_LIMIT,
) -> list[dict]:
    """Return up to `limit` non-junk open roles for a company.

    Roles whose `functional_area` matches `prioritize_functional_area` are
    returned first; then the rest, both ordered by `discovered_at DESC`.
    The filter rejects titles flagged by the extractor as junk (benefits
    copy, page headings, etc.).
    """
    from app.models.company_job_role import CompanyJobRole

    q = db.query(CompanyJobRole).filter(CompanyJobRole.company_id == company_id)
    # Reject extractor-flagged junk titles.
    q = q.filter(
        (CompanyJobRole.functional_area_confidence.is_(None))
        | (~CompanyJobRole.functional_area_confidence.startswith("none:junk"))
    )
    # Reject generic junk/unknown functional areas.
    q = q.filter(
        CompanyJobRole.functional_area.notin_(["junk", "unknown"])
        | CompanyJobRole.functional_area.is_(None)
    )
    roles = q.order_by(CompanyJobRole.discovered_at.desc()).limit(limit * 4).all()
    roles = [r for r in roles if not _looks_like_benefit(r.role_title)]

    def _shape(r) -> dict:
        return {
            "title": (r.role_title or "").strip(),
            "url": r.source_url,
            "functional_area": r.functional_area,
            "location": r.role_location,
        }

    if prioritize_functional_area:
        target = prioritize_functional_area.strip().lower()
        matched = [r for r in roles if (r.functional_area or "").lower() == target]
        others = [r for r in roles if (r.functional_area or "").lower() != target]
        ordered = matched + others
    else:
        ordered = roles

    return [_shape(r) for r in ordered[:limit]]


def get_detection_evidence(db: Session, company_id) -> dict:
    """Summarize the footprint of signals that led to this company's verdict.

    Returned shape is stable and safe to expose to end users — it explains
    *why* the company is in the match list even when `open_roles` is empty
    (e.g. scraper couldn't pull live titles but historical signals are rich).
    """
    from app.models.company_job_role import CompanyJobRole
    from app.models.company_signal import CompanySignal

    try:
        signals_count = (
            db.query(CompanySignal).filter(CompanySignal.company_id == company_id).count()
        )
    except Exception:
        signals_count = 0
    try:
        roles_count = (
            db.query(CompanyJobRole).filter(CompanyJobRole.company_id == company_id).count()
        )
    except Exception:
        roles_count = 0

    last_signal_at: Optional[str] = None
    try:
        last = (
            db.query(CompanySignal.created_at)
            .filter(CompanySignal.company_id == company_id)
            .order_by(CompanySignal.created_at.desc())
            .first()
        )
        if last and last[0]:
            last_signal_at = last[0].date().isoformat()
    except Exception:
        last_signal_at = None

    return {
        "signals_analyzed": int(signals_count),
        "roles_tracked": int(roles_count),
        "last_signal_at": last_signal_at,
    }


def _snapshot_for(row: SmartMatchCache, *, db: Optional[Session] = None) -> dict:
    """Neutral snapshot returned to NovaWork. NovaWork maps field names to
    user-facing vocabulary before serving to the candidate.

    When `db` is provided, the snapshot is enriched with `open_roles`: up
    to OPEN_ROLES_LIMIT non-junk open positions, ranked so those matching
    the company's `where_pain_lives` area come first.
    """
    open_roles: list[dict] = []
    detection_evidence: dict = {}
    if db is not None:
        try:
            open_roles = get_open_roles(
                db,
                row.company_id,
                prioritize_functional_area=row.where_pain_lives,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "smart_match_engine: get_open_roles failed for %s: %s",
                row.company_id, exc,
            )
            open_roles = []
        try:
            detection_evidence = get_detection_evidence(db, row.company_id)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "smart_match_engine: get_detection_evidence failed for %s: %s",
                row.company_id, exc,
            )
            detection_evidence = {}

    return {
        "company_id": str(row.company_id),
        "domain": row.domain,
        "friction_score": float(row.friction_score) if row.friction_score is not None else None,
        "diagnostic_state": row.diagnostic_state,
        "main_pain": row.main_pain,
        "where_pain_lives": row.where_pain_lives,
        "what_the_company_needs": row.what_the_company_needs,
        "recommended_positioning": row.recommended_positioning,
        "confidence": row.confidence,
        "eligibility_gate": row.eligibility_gate,
        "inferred_sector": row.inferred_sector,
        "kpis": row.evaluation_kpis,
        "open_roles": open_roles,
        "detection_evidence": detection_evidence,
        "refreshed_at": row.refreshed_at.isoformat() if row.refreshed_at else None,
    }


def rank_companies_for_candidate(
    db: Session,
    payload: dict,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[MatchResult]:
    """Full pipeline: embed candidate → pre-filter → LLM rerank → snapshots."""
    candidate_vec = embed_candidate(payload)
    target_sectors = payload.get("target_sectors") or None

    prefiltered = _prefilter_candidates(
        db, candidate_vec, target_sectors=target_sectors, limit=PRE_FILTER_LIMIT
    )
    if not prefiltered:
        logger.info("smart_match_engine: no eligible cache rows")
        return []

    ranked = _rerank_with_llm(payload, prefiltered, top_k)
    by_id = {str(r.company_id): r for r in prefiltered}

    results: list[MatchResult] = []
    for item in ranked:
        row = by_id.get(item["company_id"])
        if row is None:
            continue
        results.append(
            MatchResult(
                company_id=item["company_id"],
                domain=row.domain,
                fit_score=item["fit_score"],
                rationale=item["rationale"],
                snapshot=_snapshot_for(row, db=db),
            )
        )
    return results


# ─── Cache row builder (used by nightly refresh) ───────────────────────

def build_cache_row_values(
    *,
    company,
    verdict: dict,
    score,
    evaluation: dict,
    eligibility,
    run_id: Optional[str] = None,
) -> dict:
    """Shape the fields that get upserted into smart_match_cache.

    Pure function — no DB / OpenAI. The nightly script adds the embedding
    afterwards via embed_pain() and does the upsert itself.
    """
    kpis = evaluation.get("kpis") if evaluation else None
    diagnostic_state = (evaluation or {}).get("diagnostic_state") or ""

    return {
        "company_id": company.id,
        "domain": (company.domain or "").lower(),
        "friction_score": float(getattr(score, "total_score", 0) or 0) if score else None,
        "dominant_friction_type": getattr(score, "dominant_friction_type", None) if score else None,
        "diagnostic_state": diagnostic_state,
        "main_pain": (verdict or {}).get("main_pain"),
        "where_pain_lives": (verdict or {}).get("where_pain_lives"),
        "what_the_company_needs": (verdict or {}).get("what_the_company_needs"),
        "recommended_positioning": (verdict or {}).get("recommended_positioning"),
        "confidence": getattr(eligibility, "confidence_band", None),
        "eligibility_gate": getattr(eligibility, "gate_passed", None),
        "evaluation_kpis": kpis,
        "inferred_sector": getattr(company, "inferred_sector", None),
        "refresh_run_id": run_id,
    }

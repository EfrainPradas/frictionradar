"""Internal server-to-server API for NovaWork.

All endpoints require `X-Internal-Token` equal to `FRICTIONRADAR_INTERNAL_TOKEN`.
Never expose this router publicly — it returns raw FrictionRadar vocabulary
(main_pain, best_attack_angle, etc.) and is assumed to be consumed only
by NovaWork's backend, which translates the field names to neutral
vocabulary before serving them to end users.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.company import Company
from app.models.smart_match_cache import SmartMatchCache
from app.services import company_service
from app.services import smart_match_engine
from app.core.security import verify_token_constant_time

router = APIRouter()


# ─── Auth gate ────────────────────────────────────────────────────────────

def verify_internal_token(x_internal_token: Optional[str] = Header(None)) -> None:
    expected = os.environ.get("FRICTIONRADAR_INTERNAL_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Internal token not configured.",
        )
    if not verify_token_constant_time(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="Invalid internal token.")


# ─── Schemas ──────────────────────────────────────────────────────────────

class CompanyResolveResponse(BaseModel):
    company_id: str
    domain: str
    name: str
    inferred_sector: Optional[str] = None


class CompanyUpsertRequest(BaseModel):
    domain: str = Field(..., description="Company domain, e.g. stripe.com")
    name: Optional[str] = None
    industry: Optional[str] = None


class OpenRole(BaseModel):
    title: str
    url: Optional[str] = None
    functional_area: Optional[str] = None
    location: Optional[str] = None


class DetectionEvidence(BaseModel):
    signals_analyzed: int = 0
    roles_tracked: int = 0
    last_signal_at: Optional[str] = None


class CompanySnapshot(BaseModel):
    company_id: str
    domain: str
    friction_score: Optional[float] = None
    diagnostic_state: Optional[str] = None
    main_pain: Optional[str] = None
    where_pain_lives: Optional[str] = None
    what_the_company_needs: Optional[str] = None
    best_attack_angle: Optional[str] = None
    confidence: Optional[str] = None
    eligibility_gate: Optional[str] = None
    inferred_sector: Optional[str] = None
    kpis: Optional[dict] = None
    open_roles: list[OpenRole] = Field(default_factory=list)
    detection_evidence: Optional[DetectionEvidence] = None
    refreshed_at: Optional[str] = None


class ParStory(BaseModel):
    problem: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None


class MatchRequest(BaseModel):
    profile_summary: Optional[str] = None
    bullets: list[str] = Field(default_factory=list)
    par_stories: list[ParStory] = Field(default_factory=list)
    target_function: Optional[str] = None
    target_sectors: Optional[list[str]] = None
    top_k: int = Field(default=10, ge=1, le=25)


class MatchResultItem(BaseModel):
    company_id: str
    domain: str
    fit_score: float
    rationale: str
    snapshot: CompanySnapshot


class MatchResponse(BaseModel):
    count: int
    results: list[MatchResultItem]


# ─── Helpers ──────────────────────────────────────────────────────────────

def _normalize_domain(raw: str) -> str:
    d = (raw or "").strip().lower()
    if d.startswith("https://"):
        d = d[8:]
    elif d.startswith("http://"):
        d = d[7:]
    if d.startswith("www."):
        d = d[4:]
    return d.rstrip("/")


def _cache_to_snapshot(
    row: SmartMatchCache, *, db: Optional[Session] = None
) -> CompanySnapshot:
    open_roles: list[OpenRole] = []
    detection_evidence: Optional[DetectionEvidence] = None
    if db is not None:
        raw_roles = smart_match_engine.get_open_roles(
            db, row.company_id,
            prioritize_functional_area=row.where_pain_lives,
        )
        open_roles = [OpenRole(**r) for r in raw_roles]
        raw_evidence = smart_match_engine.get_detection_evidence(db, row.company_id)
        detection_evidence = DetectionEvidence(**raw_evidence)

    return CompanySnapshot(
        company_id=str(row.company_id),
        domain=row.domain,
        friction_score=float(row.friction_score) if row.friction_score is not None else None,
        diagnostic_state=row.diagnostic_state,
        main_pain=row.main_pain,
        where_pain_lives=row.where_pain_lives,
        what_the_company_needs=row.what_the_company_needs,
        best_attack_angle=row.best_attack_angle,
        confidence=row.confidence,
        eligibility_gate=row.eligibility_gate,
        inferred_sector=row.inferred_sector,
        kpis=row.evaluation_kpis,
        open_roles=open_roles,
        detection_evidence=detection_evidence,
        refreshed_at=row.refreshed_at.isoformat() if row.refreshed_at else None,
    )


def _recompute_and_upsert_cache(db: Session, company: Company) -> SmartMatchCache:
    """Trigger a single-company recompute + embedding refresh, upsert cache."""
    from app.services.company_evaluation import company_evaluation_engine
    from app.services.positioning_engine import is_company_positioning_eligible
    from app.services.final_verdict_engine import final_verdict_engine
    from app.services.company_type_engine import company_type_engine
    from app.models.friction_score import FrictionScore

    signals = company_service.get_signals(db, company.id)
    collection_runs = company_service.get_collection_runs(db, company.id)
    score = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company.id)
        .order_by(FrictionScore.created_at.desc())
        .first()
    )
    evaluation = company_evaluation_engine.evaluate(company_id=company.id, db=db)
    eligibility = is_company_positioning_eligible(db, company.id)
    type_result = company_type_engine.analyze(
        signals, len(signals), False
    )
    verdict = final_verdict_engine.generate(
        company=company,
        signals=signals,
        score=score,
        hypothesis=None,
        company_type=type_result.get("company_type", "unclear"),
        collection_runs=collection_runs,
        db=db,
    )

    row_values = smart_match_engine.build_cache_row_values(
        company=company,
        verdict=verdict,
        score=score,
        evaluation=evaluation,
        eligibility=eligibility,
        run_id="on_demand",
    )
    row_values["pain_embedding"] = smart_match_engine.embed_pain(row_values)
    row_values["refreshed_at"] = datetime.now(timezone.utc)

    existing = (
        db.query(SmartMatchCache)
        .filter(SmartMatchCache.company_id == company.id)
        .first()
    )
    if existing is None:
        row = SmartMatchCache(**row_values)
        db.add(row)
    else:
        for key, val in row_values.items():
            setattr(existing, key, val)
        row = existing
    db.commit()
    db.refresh(row)
    return row


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.get("/companies/resolve", response_model=CompanyResolveResponse)
def resolve_company(
    domain: str,
    db: Session = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    d = _normalize_domain(domain)
    if not d:
        raise HTTPException(status_code=400, detail="Domain required.")
    company = company_service.find_by_domain(db, d)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    return CompanyResolveResponse(
        company_id=str(company.id),
        domain=company.domain or d,
        name=company.name,
        inferred_sector=company.inferred_sector,
    )


@router.post("/companies/upsert", response_model=CompanyResolveResponse)
def upsert_company(
    request: CompanyUpsertRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    d = _normalize_domain(request.domain)
    if not d:
        raise HTTPException(status_code=400, detail="Domain required.")
    existing = company_service.find_by_domain(db, d)
    if existing:
        return CompanyResolveResponse(
            company_id=str(existing.id),
            domain=existing.domain or d,
            name=existing.name,
            inferred_sector=existing.inferred_sector,
        )
    from app.schemas.company import CompanyCreate
    created = company_service.create_company(
        db,
        CompanyCreate(
            name=request.name or d.split(".")[0].title(),
            domain=d,
            industry=request.industry,
            source_added_from="novawork_internal",
        ),
    )
    return CompanyResolveResponse(
        company_id=str(created.id),
        domain=created.domain or d,
        name=created.name,
        inferred_sector=created.inferred_sector,
    )


@router.get("/companies/{company_id}/snapshot", response_model=CompanySnapshot)
def get_snapshot(
    company_id: UUID,
    refresh: bool = False,
    db: Session = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    company = company_service.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    row = (
        db.query(SmartMatchCache)
        .filter(SmartMatchCache.company_id == company_id)
        .first()
    )

    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    needs_refresh = (
        refresh
        or row is None
        or (row.refreshed_at is not None and row.refreshed_at < stale_cutoff)
    )

    if needs_refresh:
        row = _recompute_and_upsert_cache(db, company)

    return _cache_to_snapshot(row, db=db)


@router.post("/match", response_model=MatchResponse)
def match_candidate(
    request: MatchRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    payload = {
        "profile_summary": request.profile_summary or "",
        "bullets": request.bullets,
        "par_stories": [s.model_dump() for s in request.par_stories],
        "target_function": request.target_function,
        "target_sectors": request.target_sectors,
    }
    matches = smart_match_engine.rank_companies_for_candidate(
        db, payload, top_k=request.top_k
    )
    items = [
        MatchResultItem(
            company_id=m.company_id,
            domain=m.domain,
            fit_score=m.fit_score,
            rationale=m.rationale,
            snapshot=CompanySnapshot(**m.snapshot),
        )
        for m in matches
    ]
    return MatchResponse(count=len(items), results=items)


@router.get("/heatmap/cell")
def get_heatmap_cell(
    sector: str,
    function: str,
    min_companies: int = 1,
    db: Session = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    # Import lazily so importing the router does not pull in the full
    # heatmap script (which performs sys.path munging at import time).
    from scripts.gen_friction_heatmap import compute_cell_companies

    return compute_cell_companies(
        db, sector=sector, function=function, min_companies=min_companies
    )

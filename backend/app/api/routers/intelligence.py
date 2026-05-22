"""Candidate Intelligence & Alignment API endpoints.

Provides endpoints for:
- Extracting candidate intelligence from Ascendia profiles
- Computing alignment between candidates and companies
- Generating VIP opportunities
- Retrieving candidate intelligence profiles
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.candidate_intelligence import (
    CandidateIntelligenceProfile,
    FrictionCandidateMatch,
    FrictionVipOpportunity,
    FrictionPositioningRecommendation,
    FrictionCompanyProfile,
)
from app.services.candidate_intelligence_extractor import candidate_intelligence_extractor
from app.services.alignment_engine import alignment_engine
from app.services.vip_positioning_engine import vip_positioning_engine
from app.services.smart_match_engine import get_open_roles
from app.models.company import Company
from app.models.friction_score import FrictionScore

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────

class StrengthDimensions(BaseModel):
    transformation: float = 0.0
    analytics: float = 0.0
    leadership: float = 0.0
    operational: float = 0.0
    modernization: float = 0.0


class CandidateProfileResponse(BaseModel):
    user_id: str
    dominant_capabilities: list = []
    solved_pain_categories: list = []
    strengths: StrengthDimensions = StrengthDimensions()
    inferred_positioning: Optional[str] = None
    positioning_vectors: list = []
    source_accomplishments_count: int = 0
    source_experience_count: int = 0


class AlignmentResponse(BaseModel):
    user_id: str
    company_id: str
    company_name: Optional[str] = None
    alignment_score: float = 0.0
    alignment_tier: str = "none"
    strategic_fit: Optional[str] = None
    positioning_recommendation: Optional[str] = None
    interview_positioning: Optional[str] = None
    resume_emphasis: list = []
    networking_guidance: Optional[str] = None
    matched_pain_categories: list = []
    matched_strengths: list = []


class OpenRoleResponse(BaseModel):
    title: str
    url: Optional[str] = None
    functional_area: Optional[str] = None
    location: Optional[str] = None


class VipOpportunityResponse(BaseModel):
    company_id: str
    company_name: Optional[str] = None
    alignment_score: float = 0.0
    opportunity_type: Optional[str] = None
    company_pain_summary: Optional[str] = None
    strategic_positioning: Optional[str] = None
    why_you_fit: Optional[str] = None
    why_they_value_you: Optional[str] = None
    resume_emphasis: list = []
    networking_positioning: Optional[str] = None
    interview_positioning: Optional[str] = None
    open_roles: list[OpenRoleResponse] = []


class CompanyPainProfileResponse(BaseModel):
    company_id: str
    company_name: Optional[str] = None
    dominant_pain: Optional[str] = None
    pain_clarity: Optional[str] = None
    diagnostic_state: Optional[str] = None
    recommended_positioning: Optional[str] = None
    candidate_archetype: Optional[str] = None
    positioning_angle: Optional[str] = None
    confidence_band: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/candidates/{user_id}/extract", response_model=CandidateProfileResponse)
def extract_candidate_intelligence(
    user_id: UUID,
    db: Session = Depends(get_db),
):
    """Extract candidate intelligence from Ascendia profile data."""
    profile = candidate_intelligence_extractor.extract(user_id, db)

    return CandidateProfileResponse(
        user_id=str(profile.user_id),
        dominant_capabilities=profile.dominant_capabilities or [],
        solved_pain_categories=profile.solved_pain_categories or [],
        strengths=StrengthDimensions(
            transformation=profile.transformation_strength or 0.0,
            analytics=profile.analytics_strength or 0.0,
            leadership=profile.leadership_strength or 0.0,
            operational=profile.operational_strength or 0.0,
            modernization=profile.modernization_strength or 0.0,
        ),
        inferred_positioning=profile.inferred_positioning,
        positioning_vectors=profile.positioning_vectors or [],
        source_accomplishments_count=profile.source_accomplishments_count or 0,
        source_experience_count=profile.source_experience_count or 0,
    )


@router.get("/candidates/{user_id}/profile", response_model=CandidateProfileResponse)
def get_candidate_profile(
    user_id: UUID,
    db: Session = Depends(get_db),
):
    """Get existing candidate intelligence profile."""
    profile = (
        db.query(CandidateIntelligenceProfile)
        .filter(CandidateIntelligenceProfile.user_id == user_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Run /extract first.")

    return CandidateProfileResponse(
        user_id=str(profile.user_id),
        dominant_capabilities=profile.dominant_capabilities or [],
        solved_pain_categories=profile.solved_pain_categories or [],
        strengths=StrengthDimensions(
            transformation=profile.transformation_strength or 0.0,
            analytics=profile.analytics_strength or 0.0,
            leadership=profile.leadership_strength or 0.0,
            operational=profile.operational_strength or 0.0,
            modernization=profile.modernization_strength or 0.0,
        ),
        inferred_positioning=profile.inferred_positioning,
        positioning_vectors=profile.positioning_vectors or [],
        source_accomplishments_count=profile.source_accomplishments_count or 0,
        source_experience_count=profile.source_experience_count or 0,
    )


@router.post("/candidates/{user_id}/align/{company_id}", response_model=AlignmentResponse)
def align_candidate_to_company(
    user_id: UUID,
    company_id: UUID,
    db: Session = Depends(get_db),
):
    """Compute alignment between a candidate and a specific company."""
    candidate = (
        db.query(CandidateIntelligenceProfile)
        .filter(CandidateIntelligenceProfile.user_id == user_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found. Run /extract first.")

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    score = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company_id)
        .order_by(FrictionScore.computed_at.desc())
        .first()
    )

    result = alignment_engine.align(
        candidate=candidate,
        company=company,
        score=score,
        db=db,
    )

    return AlignmentResponse(
        user_id=str(result.user_id),
        company_id=str(result.company_id),
        company_name=company.name,
        alignment_score=result.alignment_score,
        alignment_tier=result.alignment_tier,
        strategic_fit=result.strategic_fit,
        positioning_recommendation=result.positioning_recommendation,
        interview_positioning=result.interview_positioning,
        resume_emphasis=result.resume_emphasis,
        networking_guidance=result.networking_guidance,
        matched_pain_categories=result.matched_pain_categories,
        matched_strengths=result.matched_strengths,
    )


@router.post("/candidates/{user_id}/align-all")
def align_candidate_to_all_companies(
    user_id: UUID,
    min_score: float = Query(default=0.15, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """Align a candidate against all eligible companies."""
    candidate = (
        db.query(CandidateIntelligenceProfile)
        .filter(CandidateIntelligenceProfile.user_id == user_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found. Run /extract first.")

    matches = alignment_engine.align_candidate_to_all(candidate, db, min_score=min_score)

    return {
        "user_id": str(user_id),
        "total_matches": len(matches),
        "matches": [
            {
                "company_id": str(m.company_id),
                "alignment_score": m.alignment_score,
                "strategic_fit": m.strategic_fit,
                "positioning_recommendation": m.positioning_recommendation,
            }
            for m in matches[:25]
        ],
    }


def _enrich_open_roles(
    opp, candidate: Optional[CandidateIntelligenceProfile], db: Session
) -> list[OpenRoleResponse]:
    """Fetch open roles for a company, prioritizing candidate's strongest areas."""
    prioritize = None
    if candidate and candidate.solved_pain_categories:
        # Map top solved pain to functional area for prioritization
        pain_to_area = {
            "reporting_fragmentation": "analytics",
            "process_inefficiency": "operations",
            "tooling_inconsistency": "engineering",
            "scaling_strain": "operations",
            "customer_experience_friction": "customer_support",
        }
        top_pain = candidate.solved_pain_categories[0].get("category", "")
        prioritize = pain_to_area.get(top_pain)

    raw = get_open_roles(db, opp.company_id, prioritize_functional_area=prioritize)
    return [
        OpenRoleResponse(
            title=r["title"],
            url=r.get("url"),
            functional_area=r.get("functional_area"),
            location=r.get("location"),
        )
        for r in raw
    ]


@router.post("/candidates/{user_id}/vip-opportunities")
def generate_vip_opportunities(
    user_id: UUID,
    top_n: int = Query(default=15, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Generate VIP opportunities for a candidate."""
    # Ensure intelligence profile exists
    candidate = candidate_intelligence_extractor.extract(user_id, db)

    opportunities = vip_positioning_engine.generate_opportunities(user_id, db, top_n=top_n)

    # Enrich with company names and open roles
    results = []
    for opp in opportunities:
        company = db.query(Company).filter(Company.id == opp.company_id).first()
        roles = _enrich_open_roles(opp, candidate, db)
        results.append(VipOpportunityResponse(
            company_id=str(opp.company_id),
            company_name=company.name if company else None,
            alignment_score=opp.alignment_score,
            opportunity_type=opp.opportunity_type,
            company_pain_summary=opp.company_pain_summary,
            strategic_positioning=opp.strategic_positioning,
            why_you_fit=opp.why_you_fit,
            why_they_value_you=opp.why_they_value_you,
            resume_emphasis=opp.resume_emphasis or [],
            networking_positioning=opp.networking_positioning,
            interview_positioning=opp.interview_positioning,
            open_roles=roles,
        ))

    return {"user_id": str(user_id), "count": len(results), "opportunities": results}


@router.get("/candidates/{user_id}/vip-opportunities")
def get_vip_opportunities(
    user_id: UUID,
    db: Session = Depends(get_db),
):
    """Get active VIP opportunities for a candidate."""
    candidate = (
        db.query(CandidateIntelligenceProfile)
        .filter(CandidateIntelligenceProfile.user_id == user_id)
        .first()
    )
    opportunities = vip_positioning_engine.get_active_opportunities(user_id, db)

    results = []
    for opp in opportunities:
        company = db.query(Company).filter(Company.id == opp.company_id).first()
        roles = _enrich_open_roles(opp, candidate, db)
        results.append(VipOpportunityResponse(
            company_id=str(opp.company_id),
            company_name=company.name if company else None,
            alignment_score=opp.alignment_score,
            opportunity_type=opp.opportunity_type,
            company_pain_summary=opp.company_pain_summary,
            strategic_positioning=opp.strategic_positioning,
            why_you_fit=opp.why_you_fit,
            why_they_value_you=opp.why_they_value_you,
            resume_emphasis=opp.resume_emphasis or [],
            networking_positioning=opp.networking_positioning,
            interview_positioning=opp.interview_positioning,
            open_roles=roles,
        ))

    return {"user_id": str(user_id), "count": len(results), "opportunities": results}


@router.get("/companies/{company_id}/pain-profile", response_model=CompanyPainProfileResponse)
def get_company_pain_profile(
    company_id: UUID,
    db: Session = Depends(get_db),
):
    """Get a company's organizational pain profile (for candidate-facing display)."""
    profile = (
        db.query(FrictionCompanyProfile)
        .filter(FrictionCompanyProfile.company_id == company_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Company pain profile not found.")

    company = db.query(Company).filter(Company.id == company_id).first()

    return CompanyPainProfileResponse(
        company_id=str(profile.company_id),
        company_name=company.name if company else None,
        dominant_pain=profile.dominant_pain,
        pain_clarity=profile.pain_clarity,
        diagnostic_state=profile.diagnostic_state,
        recommended_positioning=profile.recommended_positioning,
        candidate_archetype=profile.candidate_archetype,
        positioning_angle=profile.positioning_angle,
        confidence_band=profile.confidence_band,
    )


@router.post("/nightly/run")
def trigger_nightly_run(
    db: Session = Depends(get_db),
):
    """Manually trigger the nightly intelligence refresh pipeline."""
    from app.services.nightly_orchestrator import nightly_orchestrator
    summary = nightly_orchestrator.run(db)
    return summary
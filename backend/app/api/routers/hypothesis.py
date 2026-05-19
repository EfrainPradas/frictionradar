from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.db.session import get_db
from app.models.company import Company
from app.models.friction_score import FrictionScore
from app.models.opportunity_hypothesis import OpportunityHypothesis
from app.schemas.hypothesis import OpportunityHypothesisRead, OpportunityHypothesisLatestRead
from app.services.hypothesis_engine import generate_and_persist_hypothesis

router = APIRouter()


@router.post("/companies/{company_id}/hypothesis")
def trigger_hypothesis(company_id: UUID, db: Session = Depends(get_db)):
    """
    Generate and persist an opportunity hypothesis based on the latest friction score.
    A score must exist before calling this endpoint.
    Returns 200 with a message when evidence is insufficient for a hypothesis.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Fetch latest friction score
    latest_score = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company_id)
        .order_by(FrictionScore.computed_at.desc())
        .first()
    )
    if not latest_score:
        raise HTTPException(
            status_code=400,
            detail="No friction score found. Run POST /companies/{company_id}/score first."
        )

    # Insufficient evidence — no diagnosis possible
    if latest_score.dominant_friction_type == "no_signal":
        return JSONResponse(
            status_code=200,
            content={
                "message": "Insufficient evidence to generate a hypothesis.",
                "diagnosis_status": "insufficient_evidence",
                "company_id": str(company_id),
            },
        )

    hypothesis = generate_and_persist_hypothesis(
        db=db,
        company_id=company_id,
        friction_score=latest_score,
    )
    return hypothesis


@router.get("/companies/{company_id}/hypotheses", response_model=List[OpportunityHypothesisRead])
def get_hypotheses(company_id: UUID, db: Session = Depends(get_db)):
    """Return all opportunity hypotheses for the given company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    hypotheses = (
        db.query(OpportunityHypothesis)
        .filter(OpportunityHypothesis.company_id == company_id)
        .order_by(OpportunityHypothesis.created_at.desc())
        .all()
    )
    return hypotheses


@router.get("/companies/{company_id}/hypotheses/latest", response_model=OpportunityHypothesisLatestRead)
def get_latest_hypothesis(company_id: UUID, db: Session = Depends(get_db)):
    """Return the most recently generated hypothesis for the given company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    hypothesis = (
        db.query(OpportunityHypothesis)
        .filter(OpportunityHypothesis.company_id == company_id)
        .order_by(OpportunityHypothesis.created_at.desc())
        .first()
    )
    if not hypothesis:
        raise HTTPException(
            status_code=404,
            detail="No hypothesis found for this company. Run POST /companies/{company_id}/hypothesis first."
        )

    return hypothesis

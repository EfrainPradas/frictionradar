from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.db.session import get_db
from app.models.company import Company
from app.models.friction_score import FrictionScore
from app.schemas.scoring import FrictionScoreRead, FrictionScoreLatestRead
from app.services.scoring_engine import compute_and_persist_score
from app.core.logging import logger

router = APIRouter()


@router.post("/companies/{company_id}/score", response_model=FrictionScoreRead)
async def trigger_scoring(company_id: UUID, db: Session = Depends(get_db)):
    """Compute and persist a new friction score for the given company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    from app.services.collection_orchestrator import extract_careers_evidence

    open_positions = None
    if company.domain:
        try:
            open_positions = await extract_careers_evidence(
                db, company_id, company.domain
            )
        except Exception as e:
            logger.warning(f"Careers extraction failed during scoring: {e}")

    score = compute_and_persist_score(
        db=db, company_id=company_id, open_positions_count=open_positions
    )
    return score


@router.get("/companies/{company_id}/scores", response_model=List[FrictionScoreRead])
def get_scores(company_id: UUID, db: Session = Depends(get_db)):
    """Return all historical friction scores for the given company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    scores = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company_id)
        .order_by(FrictionScore.computed_at.desc())
        .all()
    )
    return scores


@router.get(
    "/companies/{company_id}/scores/latest", response_model=FrictionScoreLatestRead
)
def get_latest_score(company_id: UUID, db: Session = Depends(get_db)):
    """Return the most recent friction score for the given company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        score = (
            db.query(FrictionScore)
            .filter(FrictionScore.company_id == company_id)
            .order_by(FrictionScore.computed_at.desc())
            .first()
        )
        if not score:
            raise HTTPException(
                status_code=404,
                detail="No friction score found for this company. Run /score first.",
            )

        return score
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching latest score: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving score. Please try running collection again.",
        )

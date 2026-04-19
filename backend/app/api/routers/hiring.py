from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List
from app.db.session import get_db
from app.models.company import Company
from app.core.logging import logger

router = APIRouter()

try:
    from app.models.company_job_role import CompanyJobRole, HiringPattern
    from app.models.company_signal import CompanySignal

    MODELS_AVAILABLE = True
except Exception as e:
    logger.warning(f"Job role models not available: {e}")
    MODELS_AVAILABLE = False
    CompanyJobRole = None
    HiringPattern = None
    CompanySignal = None


@router.get("/companies/{company_id}/hiring-intelligence", response_model=dict)
def get_hiring_intelligence(company_id: UUID, db: Session = Depends(get_db)):
    """Get hiring intelligence data for a company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if not MODELS_AVAILABLE:
        return {"hiring_pattern": None, "job_roles": [], "page_evidence": None}

    # Get hiring pattern
    pattern = None
    try:
        pattern = (
            db.query(HiringPattern)
            .filter(HiringPattern.company_id == company_id)
            .order_by(HiringPattern.created_at.desc())
            .first()
        )
    except Exception as e:
        logger.warning(f"HiringPattern query failed: {e}")

    # Get job roles
    roles = []
    try:
        roles = (
            db.query(CompanyJobRole)
            .filter(CompanyJobRole.company_id == company_id)
            .order_by(CompanyJobRole.created_at.desc())
            .limit(20)
            .all()
        )
    except Exception as e:
        logger.warning(f"CompanyJobRole query failed: {e}")

    # Get signals from dynamic careers collector
    signals = []
    try:
        signals = (
            db.query(CompanySignal)
            .filter(
                CompanySignal.company_id == company_id,
                CompanySignal.source_type == "dynamic_careers",
            )
            .all()
        )
    except Exception as e:
        logger.warning(f"CompanySignal query failed: {e}")

    # Extract page-level evidence
    open_positions = 0
    visible_categories = []
    job_links_count = 0

    for sig in signals:
        if sig.signal_type in [
            "high_open_positions_count_detected",
            "open_positions_count_detected",
        ]:
            open_positions = max(open_positions, int(sig.numeric_value or 0))
        if sig.signal_type == "job_cards_visible_detected":
            job_links_count = max(job_links_count, int(sig.numeric_value or 0))
        if "_hiring_detected" in sig.signal_type:
            visible_categories.append(sig.signal_type.replace("_hiring_detected", ""))

    if not pattern and not roles and not signals:
        return {"hiring_pattern": None, "job_roles": [], "page_evidence": None}

    return {
        "hiring_pattern": {
            "top_functional_areas": pattern.top_functional_areas
            if pattern
            else ", ".join(visible_categories[:5])
            if visible_categories
            else None,
            "total_roles_found": float(pattern.total_roles_found)
            if pattern and pattern.total_roles_found
            else (job_links_count or len(roles)),
            "unique_functions_found": float(pattern.unique_functions_found)
            if pattern and pattern.unique_functions_found
            else len(set(r.functional_area for r in roles if r.functional_area)),
        }
        if pattern or roles or visible_categories
        else None,
        "job_roles": [
            {
                "role_title": r.role_title,
                "functional_area": r.functional_area,
                "functional_area_confidence": r.functional_area_confidence,
                "source_url": r.source_url,
                "has_description": bool(r.role_description),
            }
            for r in roles
        ],
        "page_evidence": {
            "open_positions_count": open_positions,
            "visible_categories": visible_categories,
            "job_cards_count": job_links_count,
            "evidence_quality": "moderate"
            if (open_positions > 10 or job_links_count > 5)
            else "limited",
        }
        if signals
        else None,
    }


@router.post("/companies/{company_id}/extract-jds")
def extract_job_descriptions(
    company_id: UUID,
    max_jds: int = 10,
    db: Session = Depends(get_db),
):
    """Extract real job descriptions from job URLs for a company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    from app.services.jd_scraper_service import extract_jds_for_company

    result = extract_jds_for_company(company_id, db, max_jds=max_jds)
    return {"company_id": str(company_id), "company_name": company.name, **result}


@router.post("/companies/{company_id}/classify-roles")
def classify_company_roles(company_id: UUID, db: Session = Depends(get_db)):
    """Run functional area classification on all roles for a company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    from app.services.hiring_pattern_service import classify_roles

    result = classify_roles(company_id, db)
    return {"company_id": str(company_id), "company_name": company.name, **result}


@router.post("/companies/{company_id}/compute-hiring-pattern")
def compute_hiring_pattern_endpoint(
    company_id: UUID, db: Session = Depends(get_db)
):
    """Full pipeline: classify roles -> aggregate pattern -> generate signals."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    from app.services.hiring_pattern_service import compute_hiring_pattern

    result = compute_hiring_pattern(company_id, db)
    return {"company_id": str(company_id), "company_name": company.name, **result}


@router.post("/companies/{company_id}/deep-intelligence")
def deep_intelligence_pipeline(
    company_id: UUID,
    max_jds: int = 10,
    db: Session = Depends(get_db),
):
    """All-in-one: extract JDs -> classify roles -> compute hiring pattern.

    This runs the full Feature 4 + Feature 5 pipeline for a single company.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    from app.services.jd_scraper_service import extract_jds_for_company
    from app.services.hiring_pattern_service import compute_hiring_pattern

    # Step 1: Extract JDs
    jd_result = extract_jds_for_company(company_id, db, max_jds=max_jds)

    # Step 2: Classify + aggregate + signals
    pattern_result = compute_hiring_pattern(company_id, db)

    return {
        "company_id": str(company_id),
        "company_name": company.name,
        "jd_extraction": jd_result,
        "hiring_pattern": pattern_result,
    }


@router.get("/companies/{company_id}/positioning")
def get_positioning(company_id: UUID, db: Session = Depends(get_db)):
    """Generate positioning guidance for a company.

    Returns candidate positioning based on company diagnostic state.
    Only produces actionable output for companies with sufficient evidence.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    from app.services.positioning_engine import positioning_engine

    result = positioning_engine.generate(company_id=company_id, db=db)
    return result.to_dict()

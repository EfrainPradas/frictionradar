from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from typing import Optional

from app.db.session import get_db
from app.models.company import Company
from app.models.collection_run import CollectionRun
from app.services import company_service
from app.services.company_type_engine import company_type_engine
from app.core.logging import logger
from app.services.final_verdict_engine import final_verdict_engine
from app.services.company_evaluation import company_evaluation_engine
from app.services.collection_orchestrator import run_collection_for_company
from app.services.scoring_engine import compute_and_persist_score
from app.services.hypothesis_engine import generate_and_persist_hypothesis

router = APIRouter()


class AnalyzeCompanyRequest(BaseModel):
    domain: str = Field(..., description="Company domain (e.g., nike.com)")
    name: Optional[str] = Field(None, description="Company name (optional)")
    industry: Optional[str] = Field(None, description="Industry (optional)")


class CompanyResponse(BaseModel):
    id: str
    name: str
    domain: Optional[str]
    industry: Optional[str]
    company_size: Optional[str]
    source_added_from: Optional[str]
    created_at: str


class AnalyzeCompanyResponse(BaseModel):
    company: CompanyResponse
    company_type: str
    analysis_mode: str
    target_fit: str
    company_type_confidence: str
    company_type_reason: str
    signals_count: int
    friction_score: Optional[dict] = None
    hypothesis: Optional[dict] = None
    final_verdict: dict


def normalize_domain(domain: str) -> str:
    """Normalize domain input."""
    domain = domain.strip().lower()

    if domain.startswith("https://"):
        domain = domain[8:]
    elif domain.startswith("http://"):
        domain = domain[7:]

    if domain.startswith("www."):
        domain = domain[4:]

    domain = domain.rstrip("/")

    return domain


def trigger_collection(db: Session, company_id: UUID):
    """Trigger collection synchronously."""
    run_id = uuid4()
    run = CollectionRun(
        id=run_id,
        company_id=company_id,
        collector_type="orchestrator",
        status="pending",
    )
    db.add(run)
    db.commit()

    run_collection_for_company(db, company_id, run_id)

    return run


def trigger_scoring(
    db: Session,
    company_id: UUID,
    skip_extraction: bool = False,
    skip_playwright: bool = False,
):
    """Trigger smart extraction (ATS → HTTP → Playwright) then scoring.

    If skip_extraction=True, skips the expensive extraction chain and
    only re-computes the score from existing signals.
    If skip_playwright=True, runs ATS+HTTP but skips the Playwright fallback.
    """
    try:
        from app.models.company import Company
        from app.models.company_signal import CompanySignal
        from app.extraction.dispatcher import extract_company
        from app.services.collection_orchestrator import _persist_signals_deduped

        company = db.query(Company).filter(Company.id == company_id).first()
        open_positions = None

        if company and company.domain and not skip_extraction:
            # Detect ATS from prior signals
            detected_ats = None
            ats_signal = (
                db.query(CompanySignal)
                .filter(
                    CompanySignal.company_id == company_id,
                    CompanySignal.signal_type.like("%_board_detected"),
                )
                .first()
            )
            if ats_signal:
                detected_ats = ats_signal.signal_type.replace("_board_detected", "")

            # Run extraction chain: ATS API → HTTP static → Playwright
            ext_result = extract_company(
                domain=company.domain,
                company_name=company.name,
                company_id=company_id,
                detected_ats_platform=detected_ats,
                skip_playwright=skip_playwright,
            )

            if ext_result and ext_result.success:
                open_positions = ext_result.open_positions_count

                # Persist extraction signals
                source_type = f"extraction_{ext_result.strategy_used.value}"
                url = ext_result.careers_url or ""
                new_signals = []

                if ext_result.open_positions_count and ext_result.open_positions_count > 0:
                    sig_type = (
                        "high_open_positions_count_detected"
                        if ext_result.open_positions_count >= 100
                        else "open_positions_count_detected"
                    )
                    new_signals.append(CompanySignal(
                        company_id=company_id, source_type=source_type,
                        source_url=url, signal_type=sig_type,
                        signal_text=f"Open positions: {ext_result.open_positions_count}",
                        numeric_value=ext_result.open_positions_count,
                        confidence=ext_result.confidence,
                    ))

                if ext_result.jobs_count > 0:
                    new_signals.append(CompanySignal(
                        company_id=company_id, source_type=source_type,
                        source_url=url, signal_type="job_cards_visible_detected",
                        signal_text=f"Job listings: {ext_result.jobs_count}",
                        numeric_value=ext_result.jobs_count,
                        confidence=ext_result.confidence,
                    ))

                for area in ext_result.hiring_areas[:8]:
                    area_key = area.lower().replace(" ", "_").replace("&", "and")
                    new_signals.append(CompanySignal(
                        company_id=company_id, source_type=source_type,
                        source_url=url,
                        signal_type=f"{area_key}_hiring_detected",
                        signal_text=f"Hiring area: {area}",
                        confidence=0.8,
                    ))

                if ext_result.careers_url:
                    new_signals.append(CompanySignal(
                        company_id=company_id, source_type=source_type,
                        source_url=ext_result.careers_url,
                        signal_type="careers_page_found",
                        signal_text=f"Careers page: {ext_result.careers_url}",
                        confidence=0.95,
                    ))

                if new_signals:
                    _persist_signals_deduped(db, company_id, new_signals)

                logger.info(
                    f"[Analysis] {company.domain}: extraction "
                    f"strategy={ext_result.strategy_used.value} "
                    f"jobs={ext_result.jobs_count} "
                    f"positions={open_positions}"
                )

        score = compute_and_persist_score(
            db, company_id, open_positions_count=open_positions
        )
        return score
    except Exception as e:
        logger.warning(f"trigger_scoring failed for {company_id}: {e}")
        return None


def trigger_hypothesis(db: Session, company_id: UUID):
    """Trigger hypothesis generation using the latest friction score."""
    try:
        from app.models.friction_score import FrictionScore

        score = (
            db.query(FrictionScore)
            .filter(FrictionScore.company_id == company_id)
            .order_by(FrictionScore.created_at.desc())
            .first()
        )
        if score is None:
            logger.warning(
                f"trigger_hypothesis: no friction score yet for {company_id}"
            )
            return None
        return generate_and_persist_hypothesis(db, company_id, score)
    except Exception as e:
        logger.warning(f"trigger_hypothesis failed for {company_id}: {e}")
        return None


def build_response(
    company: Company,
    signals: list,
    score: any,
    hypothesis: any,
    type_result: dict,
    verdict: dict,
) -> AnalyzeCompanyResponse:
    """Build the response object."""
    return AnalyzeCompanyResponse(
        company=CompanyResponse(
            id=str(company.id),
            name=company.name,
            domain=company.domain,
            industry=company.industry,
            company_size=company.company_size,
            source_added_from=company.source_added_from,
            created_at=company.created_at.isoformat() if company.created_at else "",
        ),
        company_type=type_result["company_type"],
        analysis_mode=type_result["analysis_mode"],
        target_fit=type_result["target_fit"],
        company_type_confidence=type_result.get("company_type_confidence", "low"),
        company_type_reason=type_result["company_type_reason"],
        signals_count=len(signals),
        friction_score={
            "total_score": score.total_score,
            "dominant_friction_type": score.dominant_friction_type,
            "computed_at": score.computed_at.isoformat()
            if score and score.computed_at
            else "",
        }
        if score
        else None,
        hypothesis={
            "summary": hypothesis.summary,
            "suggested_opportunity": hypothesis.suggested_opportunity,
            "friction_type": hypothesis.friction_type,
            "llm_confidence": hypothesis.llm_confidence,
            "created_at": hypothesis.created_at.isoformat()
            if hypothesis and hypothesis.created_at
            else "",
        }
        if hypothesis
        else None,
        final_verdict=verdict,
    )


@router.post("/analyze-company", response_model=AnalyzeCompanyResponse)
def analyze_company(request: AnalyzeCompanyRequest, db: Session = Depends(get_db)):
    """One-click company analysis - orchestrates collection, scoring, hypothesis, and verdict."""

    domain = normalize_domain(request.domain)

    existing = company_service.find_by_domain(db, domain)

    if existing:
        company = existing
    else:
        from app.schemas.company import CompanyCreate

        company_create = CompanyCreate(
            name=request.name or domain.split(".")[0].title(),
            domain=domain,
            industry=request.industry,
            source_added_from="dashboard_analysis",
        )
        company = company_service.create_company(db, company_create)

    trigger_collection(db, company.id)
    score = trigger_scoring(db, company.id)
    hypothesis = trigger_hypothesis(db, company.id)

    signals = company_service.get_signals(db, company.id)
    collection_runs = company_service.get_collection_runs(db, company.id)
    type_result = company_type_engine.analyze(
        signals, len(signals), hypothesis is not None
    )

    verdict = final_verdict_engine.generate(
        company=company,
        signals=signals,
        score=score,
        hypothesis=hypothesis,
        company_type=type_result["company_type"],
        collection_runs=collection_runs,
        db=db,
    )

    return build_response(company, signals, score, hypothesis, type_result, verdict)


@router.post(
    "/companies/{company_id}/recalculate-all", response_model=AnalyzeCompanyResponse
)
def recalculate_all(
    company_id: UUID,
    force: bool = False,
    use_playwright: bool = False,
    db: Session = Depends(get_db),
):
    """Recalculate full analysis for an existing company.

    Skips collection+extraction if the company was analyzed in the last 24h
    (unless force=True). Scoring/hypothesis/verdict always run.
    """
    company = company_service.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Skip expensive collection+extraction if recent data exists
    skip_collection = False
    if not force:
        from datetime import datetime, timezone, timedelta
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_run = (
            db.query(CollectionRun)
            .filter(
                CollectionRun.company_id == company.id,
                CollectionRun.status == "completed",
                CollectionRun.started_at >= recent_cutoff,
            )
            .first()
        )
        if recent_run:
            skip_collection = True

    if not skip_collection:
        trigger_collection(db, company.id)

    score = trigger_scoring(
        db, company.id,
        skip_extraction=skip_collection,
        skip_playwright=not use_playwright,
    )
    hypothesis = trigger_hypothesis(db, company.id)

    signals = company_service.get_signals(db, company.id)
    collection_runs = company_service.get_collection_runs(db, company.id)
    type_result = company_type_engine.analyze(
        signals, len(signals), hypothesis is not None
    )

    verdict = final_verdict_engine.generate(
        company=company,
        signals=signals,
        score=score,
        hypothesis=hypothesis,
        company_type=type_result["company_type"],
        collection_runs=collection_runs,
        db=db,
    )

    return build_response(company, signals, score, hypothesis, type_result, verdict)


@router.get("/companies/{company_id}/type", response_model=dict)
def get_company_type(company_id: UUID, db: Session = Depends(get_db)):
    """Get company type analysis for an existing company."""
    company = company_service.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    signals = company_service.get_signals(db, company_id)

    from app.models.friction_score import FrictionScore
    from app.models.opportunity_hypothesis import OpportunityHypothesis

    score = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company_id)
        .order_by(FrictionScore.created_at.desc())
        .first()
    )
    hypothesis = (
        db.query(OpportunityHypothesis)
        .filter(OpportunityHypothesis.company_id == company_id)
        .order_by(OpportunityHypothesis.created_at.desc())
        .first()
    )

    type_result = company_type_engine.analyze(
        signals, len(signals), hypothesis is not None
    )

    return type_result


@router.get("/companies/{company_id}/evaluation", response_model=dict)
def get_company_evaluation(company_id: UUID, db: Session = Depends(get_db)):
    """Return the universal KPI evaluation scorecard for a company."""
    company = company_service.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    signals = company_service.get_signals(db, company_id)
    type_result = company_type_engine.analyze(signals, len(signals), False)

    return company_evaluation_engine.evaluate(
        company_id=company_id,
        db=db,
        signals=signals,
        company_type_confidence=type_result.get("company_type_confidence"),
    )


@router.get("/companies/{company_id}/verdict", response_model=dict)
def get_company_verdict(company_id: UUID, db: Session = Depends(get_db)):
    """Get final verdict for an existing company."""
    company = company_service.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    signals = company_service.get_signals(db, company_id)
    collection_runs = company_service.get_collection_runs(db, company_id)
    type_result = company_type_engine.analyze(signals, len(signals), False)

    from app.models.friction_score import FrictionScore
    from app.models.opportunity_hypothesis import OpportunityHypothesis

    score = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company_id)
        .order_by(FrictionScore.created_at.desc())
        .first()
    )
    hypothesis = (
        db.query(OpportunityHypothesis)
        .filter(OpportunityHypothesis.company_id == company_id)
        .order_by(OpportunityHypothesis.created_at.desc())
        .first()
    )

    verdict = final_verdict_engine.generate(
        company=company,
        signals=signals,
        score=score,
        hypothesis=hypothesis,
        company_type=type_result["company_type"],
        collection_runs=collection_runs,
        db=db,
    )

    evaluation = company_evaluation_engine.evaluate(
        company_id=company_id,
        db=db,
        signals=signals,
        company_type_confidence=type_result.get("company_type_confidence"),
    )

    # Rule D gate: if the framework says we cannot output a specific pain,
    # strip any pain-specific claims from the verdict surface. Positioning
    # UIs should rely on `diagnostic_state` + `summary` instead.
    if not evaluation["allow_specific_pain_output"] and isinstance(verdict, dict):
        verdict = {
            **verdict,
            "main_pain": None,
            "where_pain_lives": None,
            "what_company_needs": None,
            "best_attack_angle": None,
            "gated_reason": evaluation["summary"],
        }

    return {**type_result, "final_verdict": verdict, "evaluation": evaluation}


@router.get("/export-all")
def export_all_companies(db: Session = Depends(get_db)):
    """Export full analysis data for all companies as JSON.

    Returns everything: company info, signals, scores, evaluation,
    company type, and hypothesis for each company in the database.
    Designed for external review by another AI or analyst.
    """
    from app.models.friction_score import FrictionScore
    from app.models.opportunity_hypothesis import OpportunityHypothesis

    companies = company_service.get_companies(db, skip=0, limit=10000)
    results = []

    for company in companies:
        signals = company_service.get_signals(db, company.id)

        score = (
            db.query(FrictionScore)
            .filter(FrictionScore.company_id == company.id)
            .order_by(FrictionScore.created_at.desc())
            .first()
        )

        hypothesis = (
            db.query(OpportunityHypothesis)
            .filter(OpportunityHypothesis.company_id == company.id)
            .order_by(OpportunityHypothesis.created_at.desc())
            .first()
        )

        type_result = company_type_engine.analyze(
            signals, len(signals), hypothesis is not None
        )

        evaluation = company_evaluation_engine.evaluate(
            company_id=company.id,
            db=db,
            signals=signals,
            company_type_confidence=type_result.get("company_type_confidence"),
        )

        signals_data = [
            {
                "signal_type": s.signal_type,
                "signal_text": s.signal_text,
                "source_type": s.source_type,
                "numeric_value": float(s.numeric_value) if s.numeric_value else None,
                "confidence": float(s.confidence) if s.confidence else None,
            }
            for s in signals
        ]

        results.append({
            "company_name": company.name,
            "domain": company.domain,
            "industry": company.industry,
            "company_id": str(company.id),
            "company_type": type_result.get("company_type"),
            "company_type_confidence": type_result.get("company_type_confidence"),
            "signals_count": len(signals),
            "signals": signals_data,
            "friction_score": float(score.total_score) if score else None,
            "dominant_friction_type": score.dominant_friction_type if score else None,
            "hypothesis": {
                "summary": hypothesis.summary,
                "friction_type": hypothesis.friction_type,
                "suggested_opportunity": hypothesis.suggested_opportunity,
            } if hypothesis else None,
            "evaluation": {
                "kpis": evaluation.get("kpis"),
                "diagnostic_state": evaluation.get("diagnostic_state"),
                "summary": evaluation.get("summary"),
            },
            "updated_at": company.updated_at.isoformat() if company.updated_at else None,
        })

    return {
        "total_companies": len(results),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "companies": results,
    }

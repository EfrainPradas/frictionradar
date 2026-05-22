"""Temporal Intelligence API endpoints.

Exposes temporal analysis results (score deltas, signal velocity,
temporal diagnostics, and enriched verdicts) for frontend consumption
and future automation.

All endpoints require company_id and optionally accept lookback_days
to control the analysis window.
"""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.models.company import Company
from app.models.company_signal import CompanySignal
from app.models.company_job_role import CompanyJobRole
from app.models.friction_score import FrictionScore
from app.models.opportunity_hypothesis import OpportunityHypothesis
from app.schemas.score_delta import LookbackWindow, ScoreDeltaResult
from app.schemas.signal_velocity import VelocityWindow, SignalVelocityResult
from app.schemas.temporal_diagnostic import (
    TemporalDiagnosticResult,
    TemporalDiagnosticState,
)
from app.schemas.temporal_api import (
    TemporalDeltasResponse,
    TemporalVelocityResponse,
    TemporalDiagnosticResponse,
    TemporalVerdictResponse,
    TemporalRunAnalysisResponse,
)
from app.services.score_delta_engine import score_delta_engine
from app.services.signal_velocity_tracker import signal_velocity_tracker
from app.services.temporal_diagnostic_engine import temporal_diagnostic_engine
from app.services.final_verdict_engine import final_verdict_engine
from app.services.positioning_engine import check_eligibility
from app.services.company_evaluation import company_evaluation_engine
from app.services.company_type_engine import company_type_engine
from app.services import company_service
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ── Lookback mapping ─────────────────────────────────────────────────

_LOOKBACK_MAP = {
    7: LookbackWindow.D7,
    30: LookbackWindow.D30,
    90: LookbackWindow.D90,
    180: LookbackWindow.D180,
}

_VELOCITY_LOOKBACK_MAP = {
    1: VelocityWindow.DAILY,
    7: VelocityWindow.WEEKLY,
    30: VelocityWindow.ROLLING_30D,
    90: VelocityWindow.ROLLING_90D,
}

_VALID_DELTA_LOOKBACKS = {7, 30, 90, 180}
_VALID_VELOCITY_LOOKBACKS = {1, 7, 30, 90}


# ── Shared helpers ────────────────────────────────────────────────────

def _get_company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _resolve_delta_lookback(lookback_days: int) -> LookbackWindow:
    """Map lookback_days to LookbackWindow enum, raising 400 for invalid values."""
    if lookback_days not in _VALID_DELTA_LOOKBACKS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid lookback_days={lookback_days}. "
                   f"Valid values: {sorted(_VALID_DELTA_LOOKBACKS)}.",
        )
    return _LOOKBACK_MAP[lookback_days]


def _resolve_velocity_lookback(lookback_days: int) -> VelocityWindow:
    """Map lookback_days to VelocityWindow enum, raising 400 for invalid values."""
    if lookback_days not in _VALID_VELOCITY_LOOKBACKS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid lookback_days={lookback_days}. "
                   f"Valid values: {sorted(_VALID_VELOCITY_LOOKBACKS)}.",
        )
    return _VELOCITY_LOOKBACK_MAP[lookback_days]


def _delta_to_response(result: ScoreDeltaResult) -> TemporalDeltasResponse:
    """Convert ScoreDeltaResult to API response, adding insufficient_data flag."""
    return TemporalDeltasResponse(
        company_id=result.company_id,
        lookback_window=result.lookback_window,
        lookback_days=result.lookback_days,
        snapshot_count=result.snapshot_count,
        current_computed_at=result.current_computed_at,
        previous_computed_at=result.previous_computed_at,
        category_deltas=result.category_deltas,
        overall=result.overall,
        insufficient_data=result.snapshot_count < 2,
    )


def _velocity_to_response(result: SignalVelocityResult) -> TemporalVelocityResponse:
    """Convert SignalVelocityResult to API response, adding insufficient_data flag."""
    return TemporalVelocityResponse(
        company_id=result.company_id,
        window=result.window,
        window_days=result.window_days,
        total_signals=result.total_signals,
        scored_signals=result.scored_signals,
        discovery_signals=result.discovery_signals,
        overall_velocity=result.overall_velocity,
        overall_acceleration=result.overall_acceleration,
        overall_pressure=result.overall_pressure,
        category_velocities=result.category_velocities,
        buckets=result.buckets,
        source_summary=result.source_summary,
        spike_detected=result.spike_detected,
        spike_bucket=result.spike_bucket,
        drought_detected=result.drought_detected,
        drought_days=result.drought_days,
        evidence=result.evidence,
        insufficient_data=result.total_signals == 0,
    )


def _diagnostic_to_response(result: TemporalDiagnosticResult) -> TemporalDiagnosticResponse:
    """Convert TemporalDiagnosticResult to API response, adding insufficient_data flag."""
    return TemporalDiagnosticResponse(
        company_id=result.company_id,
        temporal_state=result.temporal_state,
        confidence=result.confidence,
        evidence_strength=result.evidence_strength,
        top_changing_category=result.top_changing_category,
        reasoning_trace=result.reasoning_trace,
        summary=result.summary,
        score_delta_available=result.score_delta_available,
        velocity_available=result.velocity_available,
        evaluation_available=result.evaluation_available,
        score_snapshot_count=result.score_snapshot_count,
        signal_count=result.signal_count,
        scored_signal_count=result.scored_signal_count,
        insufficient_data=result.temporal_state == TemporalDiagnosticState.INSUFFICIENT,
    )


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get(
    "/companies/{company_id}/temporal/deltas",
    response_model=TemporalDeltasResponse,
)
def get_temporal_deltas(
    company_id: UUID,
    lookback_days: int = Query(30, ge=7, le=180, description="Lookback window in days (7, 30, 90, 180)"),
    db: Session = Depends(get_db),
):
    """Return score history deltas for a company over the specified lookback window.

    Returns `insufficient_data: true` when fewer than 2 score snapshots
    exist in the window, meaning delta computation is not possible.
    """
    _get_company_or_404(db, company_id)
    lookback = _resolve_delta_lookback(lookback_days)
    result = score_delta_engine.compute_delta(db, company_id, lookback)
    return _delta_to_response(result)


@router.get(
    "/companies/{company_id}/temporal/signals/velocity",
    response_model=TemporalVelocityResponse,
)
def get_temporal_velocity(
    company_id: UUID,
    lookback_days: int = Query(30, ge=1, le=90, description="Lookback window in days (1, 7, 30, 90)"),
    db: Session = Depends(get_db),
):
    """Return signal velocity analysis for a company over the specified window.

    Returns `insufficient_data: true` when 0 signals exist in the window.
    """
    _get_company_or_404(db, company_id)
    window = _resolve_velocity_lookback(lookback_days)
    result = signal_velocity_tracker.compute_velocity(db, company_id, window)
    return _velocity_to_response(result)


@router.get(
    "/companies/{company_id}/temporal/diagnostic",
    response_model=TemporalDiagnosticResponse,
)
def get_temporal_diagnostic(
    company_id: UUID,
    lookback_days: int = Query(30, ge=7, le=180, description="Lookback window in days (7, 30, 90, 180)"),
    db: Session = Depends(get_db),
):
    """Return temporal diagnostic state for a company.

    Combines score delta and signal velocity to determine whether friction
    is emerging, accelerating, declining, stable, or volatile. Returns
    `insufficient_data: true` when not enough evidence exists.
    """
    _get_company_or_404(db, company_id)
    lookback = _resolve_delta_lookback(lookback_days)

    # Compute inputs for the diagnostic engine.
    delta = score_delta_engine.compute_delta(db, company_id, lookback)

    velocity_window = VelocityWindow.ROLLING_30D if lookback_days <= 30 else VelocityWindow.ROLLING_90D
    velocity = signal_velocity_tracker.compute_velocity(db, company_id, velocity_window)

    # Get company evaluation for the diagnostic engine.
    try:
        evaluation = company_evaluation_engine.evaluate(company_id=company_id, db=db)
    except Exception:
        logger.warning(f"Temporal diagnostic: evaluation failed for {company_id}")
        evaluation = None

    result = temporal_diagnostic_engine.diagnose(
        company_id=company_id,
        score_delta=delta,
        velocity=velocity,
        evaluation=evaluation,
    )
    return _diagnostic_to_response(result)


@router.get(
    "/companies/{company_id}/temporal/verdict",
    response_model=TemporalVerdictResponse,
)
def get_temporal_verdict(
    company_id: UUID,
    lookback_days: int = Query(30, ge=7, le=180, description="Lookback window in days (7, 30, 90, 180)"),
    db: Session = Depends(get_db),
):
    """Return the final verdict enriched with temporal intelligence.

    Combines the static verdict with temporal diagnostic data,
    producing trend direction, top accelerating/declining pain
    categories, and confidence-adjusted wording.
    """
    company = _get_company_or_404(db, company_id)
    lookback = _resolve_delta_lookback(lookback_days)

    # Fetch data needed for verdict.
    signals = company_service.get_signals(db, company_id)
    collection_runs = company_service.get_collection_runs(db, company_id)
    type_result = company_type_engine.analyze(signals, len(signals), False)

    score = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company_id)
        .order_by(FrictionScore.computed_at.desc())
        .first()
    )
    hypothesis = (
        db.query(OpportunityHypothesis)
        .filter(OpportunityHypothesis.company_id == company_id)
        .order_by(OpportunityHypothesis.created_at.desc())
        .first()
    )

    # Compute temporal inputs.
    delta = score_delta_engine.compute_delta(db, company_id, lookback)
    velocity_window = VelocityWindow.ROLLING_30D if lookback_days <= 30 else VelocityWindow.ROLLING_90D
    velocity = signal_velocity_tracker.compute_velocity(db, company_id, velocity_window)

    try:
        evaluation = company_evaluation_engine.evaluate(company_id=company_id, db=db)
    except Exception:
        logger.warning(f"Temporal verdict: evaluation failed for {company_id}")
        evaluation = None

    diagnostic = temporal_diagnostic_engine.diagnose(
        company_id=company_id,
        score_delta=delta,
        velocity=velocity,
        evaluation=evaluation,
    )

    # Generate verdict with temporal enrichment.
    verdict = final_verdict_engine.generate(
        company=company,
        signals=signals,
        score=score,
        hypothesis=hypothesis,
        company_type=type_result["company_type"],
        collection_runs=collection_runs,
        db=db,
        temporal_diagnostic=diagnostic,
        score_delta=delta,
        velocity=velocity,
    )

    # Compute eligibility with temporal override.
    ds = evaluation.get("diagnostic_state", "") if evaluation else ""
    kpis = evaluation.get("kpis", {}) if evaluation else {}

    classified = (
        db.query(CompanyJobRole)
        .filter(
            CompanyJobRole.company_id == company_id,
            CompanyJobRole.functional_area.isnot(None),
            ~CompanyJobRole.functional_area.in_(["junk", "unknown"]),
        )
        .count()
    )
    jds = (
        db.query(CompanyJobRole)
        .filter(
            CompanyJobRole.company_id == company_id,
            CompanyJobRole.role_description.isnot(None),
            CompanyJobRole.role_description != "",
        )
        .count()
    )

    eligibility = check_eligibility(
        diagnostic_state=ds,
        pain_clarity=kpis.get("pain_clarity", "low"),
        function_concentration=kpis.get("function_concentration", "low"),
        positioning_readiness=kpis.get("positioning_readiness", "low"),
        classified_roles=classified,
        jds_extracted=jds,
        temporal_diagnostic=diagnostic,
    )

    return TemporalVerdictResponse(
        company_id=company_id,
        verdict_type=verdict.get("verdict_type", "preliminary"),
        hiring_pressure=verdict.get("hiring_pressure", "low"),
        pain_clarity=verdict.get("pain_clarity", "low"),
        diagnosis_status=verdict.get("diagnosis_status", ""),
        confidence=verdict.get("confidence", "low"),
        what_we_know=verdict.get("what_we_know", ""),
        what_we_do_not_know_yet=verdict.get("what_we_do_not_know_yet"),
        next_best_step=verdict.get("next_best_step"),
        main_pain=verdict.get("main_pain"),
        where_pain_lives=verdict.get("where_pain_lives"),
        what_the_company_needs=verdict.get("what_the_company_needs"),
        recommended_positioning=verdict.get("recommended_positioning"),
        business_read_summary=verdict.get("business_read_summary"),
        evidence_quality=verdict.get("evidence_quality"),
        temporal_status=verdict.get("temporal_status"),
        trend_direction=verdict.get("trend_direction"),
        top_accelerating_pain=verdict.get("top_accelerating_pain"),
        top_declining_pain=verdict.get("top_declining_pain"),
        temporal_confidence=verdict.get("temporal_confidence"),
        temporal_reasoning_trace=verdict.get("temporal_reasoning_trace"),
        eligibility={
            "eligible": eligibility.eligible,
            "gate_passed": eligibility.gate_passed,
            "confidence_band": eligibility.confidence_band,
            "reason": eligibility.reason,
            "temporal_gate_passed": eligibility.temporal_gate_passed,
            "temporal_reason": eligibility.temporal_reason,
            "temporal_opportunity_type": eligibility.temporal_opportunity_type,
        },
    )


@router.post(
    "/companies/{company_id}/temporal/run-analysis",
    response_model=TemporalRunAnalysisResponse,
)
def run_temporal_analysis(
    company_id: UUID,
    lookback_days: int = Query(30, ge=7, le=180, description="Lookback window in days (7, 30, 90, 180)"),
    db: Session = Depends(get_db),
):
    """Run full temporal analysis for a company.

    Computes deltas, velocity, diagnostic state, and enriched verdict
    in a single call. Useful for on-demand refreshes or batch processing.
    """
    company = _get_company_or_404(db, company_id)
    lookback = _resolve_delta_lookback(lookback_days)

    # Compute deltas.
    delta = score_delta_engine.compute_delta(db, company_id, lookback)
    deltas_response = _delta_to_response(delta)

    # Compute velocity.
    velocity_window = VelocityWindow.ROLLING_30D if lookback_days <= 30 else VelocityWindow.ROLLING_90D
    velocity = signal_velocity_tracker.compute_velocity(db, company_id, velocity_window)
    velocity_response = _velocity_to_response(velocity)

    # Compute diagnostic.
    try:
        evaluation = company_evaluation_engine.evaluate(company_id=company_id, db=db)
    except Exception:
        logger.warning(f"Run analysis: evaluation failed for {company_id}")
        evaluation = None

    diagnostic = temporal_diagnostic_engine.diagnose(
        company_id=company_id,
        score_delta=delta,
        velocity=velocity,
        evaluation=evaluation,
    )
    diagnostic_response = _diagnostic_to_response(diagnostic)

    # Compute enriched verdict.
    signals = company_service.get_signals(db, company_id)
    collection_runs = company_service.get_collection_runs(db, company_id)
    type_result = company_type_engine.analyze(signals, len(signals), False)

    score = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company_id)
        .order_by(FrictionScore.computed_at.desc())
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
        temporal_diagnostic=diagnostic,
        score_delta=delta,
        velocity=velocity,
    )

    # Compute eligibility with temporal override.
    ds = evaluation.get("diagnostic_state", "") if evaluation else ""
    kpis = evaluation.get("kpis", {}) if evaluation else {}

    classified = (
        db.query(CompanyJobRole)
        .filter(
            CompanyJobRole.company_id == company_id,
            CompanyJobRole.functional_area.isnot(None),
            ~CompanyJobRole.functional_area.in_(["junk", "unknown"]),
        )
        .count()
    )
    jds = (
        db.query(CompanyJobRole)
        .filter(
            CompanyJobRole.company_id == company_id,
            CompanyJobRole.role_description.isnot(None),
            CompanyJobRole.role_description != "",
        )
        .count()
    )

    eligibility = check_eligibility(
        diagnostic_state=ds,
        pain_clarity=kpis.get("pain_clarity", "low"),
        function_concentration=kpis.get("function_concentration", "low"),
        positioning_readiness=kpis.get("positioning_readiness", "low"),
        classified_roles=classified,
        jds_extracted=jds,
        temporal_diagnostic=diagnostic,
    )

    verdict_response = TemporalVerdictResponse(
        company_id=company_id,
        verdict_type=verdict.get("verdict_type", "preliminary"),
        hiring_pressure=verdict.get("hiring_pressure", "low"),
        pain_clarity=verdict.get("pain_clarity", "low"),
        diagnosis_status=verdict.get("diagnosis_status", ""),
        confidence=verdict.get("confidence", "low"),
        what_we_know=verdict.get("what_we_know", ""),
        what_we_do_not_know_yet=verdict.get("what_we_do_not_know_yet"),
        next_best_step=verdict.get("next_best_step"),
        main_pain=verdict.get("main_pain"),
        where_pain_lives=verdict.get("where_pain_lives"),
        what_the_company_needs=verdict.get("what_the_company_needs"),
        recommended_positioning=verdict.get("recommended_positioning"),
        business_read_summary=verdict.get("business_read_summary"),
        evidence_quality=verdict.get("evidence_quality"),
        temporal_status=verdict.get("temporal_status"),
        trend_direction=verdict.get("trend_direction"),
        top_accelerating_pain=verdict.get("top_accelerating_pain"),
        top_declining_pain=verdict.get("top_declining_pain"),
        temporal_confidence=verdict.get("temporal_confidence"),
        temporal_reasoning_trace=verdict.get("temporal_reasoning_trace"),
        eligibility={
            "eligible": eligibility.eligible,
            "gate_passed": eligibility.gate_passed,
            "confidence_band": eligibility.confidence_band,
            "reason": eligibility.reason,
            "temporal_gate_passed": eligibility.temporal_gate_passed,
            "temporal_reason": eligibility.temporal_reason,
            "temporal_opportunity_type": eligibility.temporal_opportunity_type,
        },
    )

    return TemporalRunAnalysisResponse(
        company_id=company_id,
        deltas=deltas_response,
        velocity=velocity_response,
        diagnostic=diagnostic_response,
        verdict=verdict_response,
    )
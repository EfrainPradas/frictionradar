"""Pydantic response schemas for the Temporal Intelligence API endpoints."""

from datetime import datetime
from typing import Optional, List, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.score_delta import (
    LookbackWindow, TrendDirection, Magnitude,
    CategoryDelta, OverallDelta,
)
from app.schemas.signal_velocity import (
    VelocityWindow, PressureState, SignalClass,
    CategoryVelocity, VelocityBucket, SourceSummary,
)
from app.schemas.temporal_diagnostic import (
    TemporalDiagnosticState, TemporalConfidence, EvidenceStrength,
    TopChangingCategory, ReasoningStep,
)


# ── Deltas endpoint ───────────────────────────────────────────────────

class TemporalDeltasResponse(BaseModel):
    """Response for GET /companies/{company_id}/temporal/deltas."""
    company_id: UUID
    lookback_window: LookbackWindow
    lookback_days: int
    snapshot_count: int
    current_computed_at: Optional[datetime] = None
    previous_computed_at: Optional[datetime] = None
    category_deltas: List[CategoryDelta] = []
    overall: Optional[OverallDelta] = None
    insufficient_data: bool = Field(
        False, description="True when fewer than 2 score snapshots exist."
    )

    model_config = ConfigDict(from_attributes=True)


# ── Velocity endpoint ─────────────────────────────────────────────────

class TemporalVelocityResponse(BaseModel):
    """Response for GET /companies/{company_id}/temporal/signals/velocity."""
    company_id: UUID
    window: VelocityWindow
    window_days: int
    total_signals: int
    scored_signals: int
    discovery_signals: int
    overall_velocity: float
    overall_acceleration: float
    overall_pressure: PressureState
    category_velocities: List[CategoryVelocity] = []
    buckets: List[VelocityBucket] = []
    source_summary: List[SourceSummary] = []
    spike_detected: bool = False
    spike_bucket: Optional[datetime] = None
    drought_detected: bool = False
    drought_days: int = 0
    evidence: str = ""
    insufficient_data: bool = Field(
        False, description="True when 0 signals exist for the window."
    )

    model_config = ConfigDict(from_attributes=True)


# ── Diagnostic endpoint ───────────────────────────────────────────────

class TemporalDiagnosticResponse(BaseModel):
    """Response for GET /companies/{company_id}/temporal/diagnostic."""
    company_id: UUID
    temporal_state: TemporalDiagnosticState
    confidence: TemporalConfidence
    evidence_strength: EvidenceStrength
    top_changing_category: Optional[TopChangingCategory] = None
    reasoning_trace: List[ReasoningStep] = []
    summary: str = ""
    score_delta_available: bool = False
    velocity_available: bool = False
    evaluation_available: bool = False
    score_snapshot_count: int = 0
    signal_count: int = 0
    scored_signal_count: int = 0
    insufficient_data: bool = Field(
        False, description="True when temporal_state is insufficient_temporal_data."
    )

    model_config = ConfigDict(from_attributes=True)


# ── Verdict endpoint ──────────────────────────────────────────────────

class TemporalVerdictResponse(BaseModel):
    """Response for GET /companies/{company_id}/temporal/verdict.

    Combines the final verdict with temporal enrichment fields.
    """
    company_id: UUID
    verdict_type: str
    hiring_pressure: str
    pain_clarity: str
    diagnosis_status: str
    confidence: str
    what_we_know: str
    what_we_do_not_know_yet: Optional[str] = None
    next_best_step: Optional[str] = None
    main_pain: Optional[str] = None
    where_pain_lives: Optional[str] = None
    what_the_company_needs: Optional[str] = None
    recommended_positioning: Optional[str] = None
    # Static fields
    business_read_summary: Optional[str] = None
    evidence_quality: Optional[str] = None
    # Temporal enrichment fields
    temporal_status: Optional[str] = None
    trend_direction: Optional[str] = None
    top_accelerating_pain: Optional[Dict[str, object]] = None
    top_declining_pain: Optional[Dict[str, object]] = None
    temporal_confidence: Optional[str] = None
    temporal_reasoning_trace: Optional[List[Dict[str, str]]] = None
    # Eligibility
    eligibility: Optional[Dict[str, object]] = None

    model_config = ConfigDict(from_attributes=True)


# ── Run-analysis endpoint ─────────────────────────────────────────────

class TemporalRunAnalysisResponse(BaseModel):
    """Response for POST /companies/{company_id}/temporal/run-analysis.

    Returns all temporal intelligence data in a single response.
    """
    company_id: UUID
    deltas: Optional[TemporalDeltasResponse] = None
    velocity: Optional[TemporalVelocityResponse] = None
    diagnostic: TemporalDiagnosticResponse
    verdict: Optional[TemporalVerdictResponse] = None

    model_config = ConfigDict(from_attributes=True)


# ── Error response ────────────────────────────────────────────────────

class TemporalErrorResponse(BaseModel):
    """Standard error response for temporal endpoints."""
    detail: str
    company_id: Optional[str] = None
    error_type: str  # "company_not_found", "no_scores", "invalid_lookback"
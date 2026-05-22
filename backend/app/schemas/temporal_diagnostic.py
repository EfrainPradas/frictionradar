"""Pydantic schemas for the Temporal Diagnostic Engine."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from uuid import UUID


# ── Enums ────────────────────────────────────────────────────────────────

class TemporalDiagnosticState(str, Enum):
    INSUFFICIENT = "insufficient_temporal_data"
    STABLE_LOW = "stable_low_friction"
    STABLE_ELEVATED = "stable_elevated_friction"
    EMERGING_PAIN = "emerging_pain"
    ACCELERATING_PAIN = "accelerating_pain"
    DECLINING_PAIN = "declining_pain"
    VOLATILE = "volatile_friction"


class TemporalConfidence(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    NONE = "none"


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


# ── Top changing category ────────────────────────────────────────────────

class TopChangingCategory(BaseModel):
    """The friction category with the largest temporal change."""
    category: str
    delta: float  # normalized score change
    trend: str  # TrendDirection value
    velocity: float  # signals per period
    evidence_strength: EvidenceStrength

    model_config = ConfigDict(from_attributes=True)


# ── Reasoning trace ───────────────────────────────────────────────────────

class ReasoningStep(BaseModel):
    """A single decision step in the reasoning trace."""
    step: str
    condition: str
    result: str

    model_config = ConfigDict(from_attributes=True)


# ── Full result ────────────────────────────────────────────────────────────

class TemporalDiagnosticResult(BaseModel):
    """Complete temporal diagnostic for a company."""
    company_id: UUID
    temporal_state: TemporalDiagnosticState
    confidence: TemporalConfidence
    evidence_strength: EvidenceStrength
    top_changing_category: Optional[TopChangingCategory] = None
    reasoning_trace: List[ReasoningStep] = []
    summary: str = ""
    # Input references for auditability
    score_delta_available: bool = False
    velocity_available: bool = False
    evaluation_available: bool = False
    score_snapshot_count: int = 0
    signal_count: int = 0
    scored_signal_count: int = 0

    model_config = ConfigDict(from_attributes=True)
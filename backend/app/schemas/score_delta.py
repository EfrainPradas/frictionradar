"""Pydantic schemas for the Score History Delta Engine."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from uuid import UUID


# ── Enums ────────────────────────────────────────────────────────────────

class TrendDirection(str, Enum):
    INSUFFICIENT = "insufficient_temporal_data"
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    VOLATILE = "volatile"


class Magnitude(str, Enum):
    NEGLIGIBLE = "negligible"
    MILD = "mild"
    MODERATE = "moderate"
    STRONG = "strong"


class LookbackWindow(str, Enum):
    D7 = "7d"
    D30 = "30d"
    D90 = "90d"
    D180 = "180d"


# ── Per-category delta ────────────────────────────────────────────────────

class CategoryDelta(BaseModel):
    """Delta for a single friction category."""
    category: str
    current_normalized: float
    previous_normalized: float
    delta: float  # positive = friction increased (worse)
    trend: TrendDirection
    magnitude: Magnitude
    evidence: str  # human-readable explanation

    model_config = ConfigDict(from_attributes=True)


# ── Overall delta ─────────────────────────────────────────────────────────

class OverallDelta(BaseModel):
    """Overall friction delta across all categories."""
    current_total: float
    previous_total: float
    delta: float
    trend: TrendDirection
    magnitude: Magnitude
    dominant_shift: Optional[str] = None  # category that changed most

    model_config = ConfigDict(from_attributes=True)


# ── Full result ───────────────────────────────────────────────────────────

class ScoreDeltaResult(BaseModel):
    """Complete delta analysis for a company over a lookback window."""
    company_id: UUID
    lookback_window: LookbackWindow
    lookback_days: int
    snapshot_count: int  # number of FrictionScore rows used
    current_score_id: Optional[UUID] = None
    previous_score_id: Optional[UUID] = None
    current_computed_at: Optional[datetime] = None
    previous_computed_at: Optional[datetime] = None
    category_deltas: List[CategoryDelta] = []
    overall: Optional[OverallDelta] = None

    model_config = ConfigDict(from_attributes=True)
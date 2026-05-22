"""Pydantic schemas for the Signal Velocity Tracker."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from uuid import UUID


# ── Enums ────────────────────────────────────────────────────────────────

class VelocityWindow(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    ROLLING_30D = "30d_rolling"
    ROLLING_90D = "90d_rolling"


class PressureState(str, Enum):
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"
    STABLE = "stable"
    SPIKE = "signal_spike"
    DROUGHT = "signal_drought"
    INSUFFICIENT = "insufficient_data"


class SignalClass(str, Enum):
    SCORED = "scored"
    DISCOVERY = "discovery"


# ── Per-category velocity ─────────────────────────────────────────────────

class CategoryVelocity(BaseModel):
    """Signal velocity for a single friction category."""
    category: str
    signal_count: int
    scored_count: int
    discovery_count: int
    velocity: float  # signals per period
    acceleration: float  # current_velocity - prior_velocity
    pressure: PressureState

    model_config = ConfigDict(from_attributes=True)


# ── Per-bucket time series ────────────────────────────────────────────────

class VelocityBucket(BaseModel):
    """Signal count in a single time bucket."""
    bucket_start: datetime
    bucket_end: datetime
    total_count: int
    scored_count: int
    discovery_count: int
    category_counts: Dict[str, int] = {}

    model_config = ConfigDict(from_attributes=True)


# ── Source/evidence summary ──────────────────────────────────────────────

class SourceSummary(BaseModel):
    """Summary of signal sources contributing to velocity."""
    source_type: str
    signal_count: int
    latest_signal_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Full result ────────────────────────────────────────────────────────────

class SignalVelocityResult(BaseModel):
    """Complete velocity analysis for a company over a time window."""
    company_id: UUID
    window: VelocityWindow
    window_days: int
    total_signals: int
    scored_signals: int
    discovery_signals: int
    overall_velocity: float  # total signals per period
    overall_acceleration: float
    overall_pressure: PressureState
    category_velocities: List[CategoryVelocity] = []
    buckets: List[VelocityBucket] = []
    source_summary: List[SourceSummary] = []
    spike_detected: bool = False
    spike_bucket: Optional[datetime] = None  # start of the spike bucket
    drought_detected: bool = False
    drought_days: int = 0  # consecutive days with 0 scored signals
    evidence: str = ""

    model_config = ConfigDict(from_attributes=True)
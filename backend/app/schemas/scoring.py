from pydantic import BaseModel, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any, List


class CategoryBreakdown(BaseModel):
    """Legacy v1 breakdown — raw score and matched signals only."""
    score: float
    matched_signals: List[str]


class CategoryBreakdownV2(BaseModel):
    """Normalized v2 breakdown — raw, max_possible, and normalized_score."""
    raw_score: float
    max_possible: float
    normalized_score: float
    matched_signals: List[str]


class ConfidenceMetrics(BaseModel):
    """Confidence metrics based on signal diversity and evidence breadth."""
    signal_diversity: int
    contributing_signal_count: int
    evidence_breadth: int
    confidence_level: str  # "high" | "medium" | "low" | "none"


class FrictionScoreRead(BaseModel):
    id: UUID
    company_id: UUID
    total_score: float
    dominant_friction_type: Optional[str] = None  # null when insufficient evidence
    scoring_breakdown_json: Dict[str, Any]
    scoring_version: Optional[str] = None
    computed_at: datetime
    created_at: datetime
    open_positions_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("dominant_friction_type", mode="before")
    @classmethod
    def translate_no_signal(cls, v):
        """Convert internal 'no_signal' sentinel to null for API consumers."""
        if v == "no_signal":
            return None
        return v

    @property
    def normalized_scores(self) -> Dict[str, float]:
        """Extract normalized scores from the breakdown JSON.

        Returns per-category normalized scores (0.0-1.0).
        Works with both v1.0.0 and v2.0.0 formats.
        """
        breakdown = self.scoring_breakdown_json or {}
        # v2.0.0 format: {"categories": {...}, "confidence": {...}}
        if "categories" in breakdown:
            return {
                cat: data.get("normalized_score", 0.0)
                for cat, data in breakdown["categories"].items()
            }
        # v1.0.0 format: no normalized scores available
        return {}


class FrictionScoreLatestRead(FrictionScoreRead):
    """Alias for the latest score — same shape, used for clarity in the API."""
    pass
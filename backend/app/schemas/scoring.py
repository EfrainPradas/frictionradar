from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any, List


class CategoryBreakdown(BaseModel):
    score: float
    matched_signals: List[str]


class FrictionScoreRead(BaseModel):
    id: UUID
    company_id: UUID
    total_score: float
    dominant_friction_type: str
    scoring_breakdown_json: Dict[str, Any]
    scoring_version: Optional[str] = None
    computed_at: datetime
    created_at: datetime
    open_positions_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class FrictionScoreLatestRead(FrictionScoreRead):
    """Alias for the latest score — same shape, used for clarity in the API."""

    pass

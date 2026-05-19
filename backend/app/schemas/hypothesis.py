from pydantic import BaseModel, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any


class OpportunityHypothesisRead(BaseModel):
    id: UUID
    company_id: UUID
    friction_score_id: Optional[UUID] = None
    summary: str
    friction_type: Optional[str] = None  # null when insufficient evidence
    suggested_opportunity: str
    rationale_json: Optional[Dict[str, Any]] = None
    llm_confidence: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("friction_type", mode="before")
    @classmethod
    def translate_no_signal(cls, v):
        """Convert internal 'no_signal' sentinel to null for API consumers."""
        if v == "no_signal":
            return None
        return v


class OpportunityHypothesisLatestRead(OpportunityHypothesisRead):
    """Alias for the latest hypothesis — same shape, used for clarity in the API."""
    pass
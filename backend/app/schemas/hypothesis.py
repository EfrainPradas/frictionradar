from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any


class OpportunityHypothesisRead(BaseModel):
    id: UUID
    company_id: UUID
    friction_score_id: Optional[UUID] = None
    summary: str
    friction_type: str
    suggested_opportunity: str
    rationale_json: Optional[Dict[str, Any]] = None
    llm_confidence: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OpportunityHypothesisLatestRead(OpportunityHypothesisRead):
    """Alias for the latest hypothesis — same shape, used for clarity in the API."""
    pass

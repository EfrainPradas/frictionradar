from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

class SignalBase(BaseModel):
    source_type: str
    source_url: Optional[str] = None
    signal_type: str
    signal_text: str
    numeric_value: Optional[float] = None
    confidence: Optional[float] = None

class SignalCreate(SignalBase):
    pass

class SignalRead(SignalBase):
    id: UUID
    company_id: UUID
    captured_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

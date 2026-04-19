from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any

class CollectionRunBase(BaseModel):
    collector_type: str
    status: str
    error_message: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None

class CollectionRunRead(CollectionRunBase):
    id: UUID
    company_id: UUID
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

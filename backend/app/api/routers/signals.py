from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.db.session import get_db
from app.models.company_signal import CompanySignal
from app.schemas.signal import SignalRead

router = APIRouter()

@router.get("/companies/{company_id}/signals", response_model=List[SignalRead])
def read_company_signals(company_id: UUID, db: Session = Depends(get_db)):
    signals = db.query(CompanySignal).filter(CompanySignal.company_id == company_id).all()
    return signals

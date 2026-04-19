from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from pydantic import BaseModel

from app.db.session import get_db
from app.schemas.company import CompanyCreate, CompanyRead
from app.services import company_service

router = APIRouter()


class SkippedInfo(BaseModel):
    name: str
    domain: str
    matched_name: str

class BatchCreateResponse(BaseModel):
    created: int
    skipped: int
    errors: List[str]
    skipped_details: List[SkippedInfo] = []


@router.post("/", response_model=CompanyRead)
def create_company(company: CompanyCreate, db: Session = Depends(get_db)):
    return company_service.create_company(db=db, company=company)


@router.post("/batch", response_model=BatchCreateResponse)
def batch_create_companies(companies: List[CompanyCreate], db: Session = Depends(get_db)):
    """Create multiple companies at once, skipping duplicates by domain."""
    created = 0
    skipped = 0
    errors: List[str] = []
    skipped_details: List[SkippedInfo] = []

    for comp in companies:
        try:
            if comp.domain:
                existing = company_service.find_by_domain(db, comp.domain)
                if existing:
                    skipped += 1
                    skipped_details.append(SkippedInfo(
                        name=comp.name,
                        domain=comp.domain,
                        matched_name=existing.name,
                    ))
                    continue
            company_service.create_company(db=db, company=comp)
            created += 1
        except Exception as e:
            errors.append(f"{comp.name}: {str(e)}")
            db.rollback()

    return BatchCreateResponse(created=created, skipped=skipped, errors=errors, skipped_details=skipped_details)


@router.get("/", response_model=List[CompanyRead])
def read_companies(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return company_service.get_companies(db, skip=skip, limit=limit)


@router.get("/{company_id}", response_model=CompanyRead)
def read_company(company_id: UUID, db: Session = Depends(get_db)):
    db_company = company_service.get_company(db, company_id=company_id)
    if db_company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return db_company


@router.delete("/{company_id}")
def delete_company(company_id: UUID, db: Session = Depends(get_db)):
    """Delete a company and all its associated data (signals, scores, hypotheses, collection runs)."""
    success = company_service.delete_company(db, company_id=company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"message": "Company deleted successfully"}

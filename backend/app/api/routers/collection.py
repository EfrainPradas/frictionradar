from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.db.session import get_db
from app.models.company import Company
from app.models.collection_run import CollectionRun
from app.schemas.collection import CollectionRunRead
from app.services.collection_orchestrator import run_collection_for_company

router = APIRouter()


@router.post("/companies/{company_id}/collect", response_model=dict)
def trigger_collection(
    company_id: UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Create a pending collection run entry
    run = CollectionRun(
        company_id=company.id, collector_type="orchestrator", status="pending"
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Schedule the synchronous orchestration to run in the background
    background_tasks.add_task(run_collection_for_company, db, company.id, run.id)

    return {"message": "Collection started", "run_id": run.id}


@router.get(
    "/companies/{company_id}/collection-runs", response_model=List[CollectionRunRead]
)
def get_collection_runs(company_id: UUID, db: Session = Depends(get_db)):
    runs = (
        db.query(CollectionRun)
        .filter(CollectionRun.company_id == company_id)
        .order_by(CollectionRun.started_at.desc())
        .all()
    )
    return runs

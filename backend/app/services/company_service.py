from sqlalchemy.orm import Session
from uuid import UUID
from app.models.company import Company
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.models.opportunity_hypothesis import OpportunityHypothesis
from app.models.collection_run import CollectionRun
from app.schemas.company import CompanyCreate


def get_company(db: Session, company_id: UUID):
    return db.query(Company).filter(Company.id == company_id).first()


def get_companies(db: Session, skip: int = 0, limit: int = 20):
    return db.query(Company).offset(skip).limit(limit).all()


def find_by_domain(db: Session, domain: str):
    """Find company by domain (case-insensitive)."""
    return db.query(Company).filter(Company.domain.ilike(domain)).first()


def get_signals(db: Session, company_id: UUID):
    """Get all signals for a company."""
    return db.query(CompanySignal).filter(CompanySignal.company_id == company_id).all()


def get_collection_runs(db: Session, company_id: UUID):
    """Get all collection runs for a company."""
    return (
        db.query(CollectionRun)
        .filter(CollectionRun.company_id == company_id)
        .order_by(CollectionRun.started_at.desc())
        .all()
    )


def create_company(db: Session, company: CompanyCreate):
    db_company = Company(
        name=company.name,
        domain=company.domain,
        industry=company.industry,
        company_size=company.company_size,
        source_added_from=company.source_added_from,
    )
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company


def delete_company(db: Session, company_id: UUID) -> bool:
    """Delete a company and all its associated data."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return False

    # Delete associated data (cascade should handle most, but explicit is safer)
    db.query(CompanySignal).filter(CompanySignal.company_id == company_id).delete()
    db.query(FrictionScore).filter(FrictionScore.company_id == company_id).delete()
    db.query(OpportunityHypothesis).filter(
        OpportunityHypothesis.company_id == company_id
    ).delete()
    db.query(CollectionRun).filter(CollectionRun.company_id == company_id).delete()

    # Delete company
    db.delete(company)
    db.commit()
    return True

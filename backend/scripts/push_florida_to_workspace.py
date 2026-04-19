"""Push Florida master records with verified domains to the workspace (companies table)."""
import sys
import os
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)

from datetime import datetime, timezone

import app.models
from app.db.session import SessionLocal
from app.master.models import CompanyMaster
from app.master.domain_models import CompanyDomain
from app.models.company import Company


def main():
    db = SessionLocal()

    # Get all Florida master records that have a resolved domain but no linked_company_id
    results = (
        db.query(CompanyMaster, CompanyDomain)
        .join(CompanyDomain, CompanyDomain.company_master_id == CompanyMaster.id)
        .filter(
            CompanyMaster.source_confidence == 0.80,
            CompanyMaster.jurisdiction_state == "FL",
            CompanyMaster.linked_company_id.is_(None),
            CompanyDomain.domain_status == "resolved",
            CompanyDomain.is_primary == True,
        )
        .all()
    )

    print(f"Florida master records with domain but no workspace record: {len(results)}")

    created = 0
    skipped = 0
    linked = 0

    for master, domain_rec in results:
        # Check if domain already exists in workspace
        existing = db.query(Company).filter(Company.domain == domain_rec.domain).first()

        if existing:
            # Link master to existing workspace record
            master.linked_company_id = existing.id
            linked += 1
        else:
            # Create new workspace record
            company = Company(
                name=master.legal_name,
                domain=domain_rec.domain,
                industry=master.entity_type,
                source_added_from="florida_dos",
            )
            db.add(company)
            db.flush()

            master.linked_company_id = company.id
            created += 1

    db.commit()

    # Count totals
    total_workspace = db.query(Company).filter(Company.source_added_from == "florida_dos").count()
    total_all = db.query(Company).count()

    db.close()

    print(f"Created: {created}")
    print(f"Linked to existing: {linked}")
    print(f"Total Florida in workspace: {total_workspace}")
    print(f"Total companies in workspace: {total_all}")


if __name__ == "__main__":
    main()

"""Infer sector bucket for every company and persist it.

Workflow:
  1. Ensure inferred_sector / source / confidence columns exist (idempotent).
  2. For each company: gather its classified roles, call sector_inference.
  3. Upsert the sector into companies.

Usage:
  python scripts/infer_sector.py --dry-run        (default)
  python scripts/infer_sector.py --execute
  python scripts/infer_sector.py --execute --only-null   (skip companies that already have it)
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.services.sector_inference import infer_sector

EXCLUDED_AREAS = {None, "", "junk", "unknown", "Technology"}

DDL = [
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS inferred_sector VARCHAR;",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS inferred_sector_source VARCHAR;",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS inferred_sector_confidence VARCHAR;",
    "CREATE INDEX IF NOT EXISTS ix_companies_inferred_sector ON companies (inferred_sector);",
]


def ensure_columns():
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--only-null", action="store_true",
                    help="Only infer for companies where inferred_sector is NULL")
    args = ap.parse_args()

    print("Ensuring columns exist...")
    ensure_columns()

    db = SessionLocal()

    companies = db.query(Company).all()
    print(f"Total companies: {len(companies)}")

    # Prefetch functional_area counts per company
    fn_counts_by_company: dict = defaultdict(Counter)
    for row in db.query(
        CompanyJobRole.company_id, CompanyJobRole.functional_area
    ).all():
        if row.functional_area in EXCLUDED_AREAS:
            continue
        fn_counts_by_company[row.company_id][row.functional_area] += 1

    sector_counter = Counter()
    source_counter = Counter()
    confidence_counter = Counter()
    changes = 0
    skipped = 0

    for c in companies:
        if args.only_null and c.inferred_sector:
            skipped += 1
            sector_counter[c.inferred_sector] += 1
            continue

        fn_counts = fn_counts_by_company.get(c.id, Counter())
        result = infer_sector(
            name=c.name or "",
            domain=c.domain,
            industry_text=c.industry,
            fn_counts=fn_counts,
        )
        sector_counter[result.sector] += 1
        source_counter[result.source] += 1
        confidence_counter[result.confidence] += 1

        if (
            c.inferred_sector != result.sector
            or c.inferred_sector_source != result.source
            or c.inferred_sector_confidence != result.confidence
        ):
            changes += 1
            if args.execute:
                c.inferred_sector = result.sector
                c.inferred_sector_source = result.source
                c.inferred_sector_confidence = result.confidence

    print(f"\nChanges: {changes}   Skipped (already set): {skipped}")

    print(f"\nSector distribution:")
    for s, n in sector_counter.most_common():
        print(f"  {n:5d}  {s}")

    print(f"\nSignal source:")
    for s, n in source_counter.most_common():
        print(f"  {n:5d}  {s}")

    print(f"\nConfidence:")
    for s, n in confidence_counter.most_common():
        print(f"  {n:5d}  {s}")

    if args.execute:
        db.commit()
        print(f"\nCommitted {changes} updates.")
    else:
        print("\n[DRY RUN] No changes. Re-run with --execute.")

    db.close()


if __name__ == "__main__":
    main()

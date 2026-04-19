"""
Phase 9 Migration — Dataset Governance columns + data cleanup.

Adds governance fields to companies table:
  - normalized_name, geography, entity_type, priority_tier
  - dataset_status, careers_url, careers_accessibility
  - last_collection_at, last_analysis_run_id
  - latest_diagnostic_state, positioning_eligible, notes

Also:
  - Migrates legal entity types from industry to entity_type
  - Populates normalized_name for all companies
  - Backfills dataset_status from existing data
  - Creates company_coverage view

Usage:
    cd backend
    python scripts/migrate_dataset_governance.py              # run migration
    python scripts/migrate_dataset_governance.py --dry-run    # show what would happen
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


# ── Name normalization ───────────────────────────────────────────────

LEGAL_SUFFIXES = [
    ', llc', ', inc.', ', inc', ', corp.', ', corp', ', ltd.', ', ltd',
    ', l.l.c.', ', l.p.', ', p.a.', ', p.l.', ', lp',
    ' llc', ' inc.', ' inc', ' corp.', ' corp', ' corporation',
    ' ltd.', ' ltd', ' co.', ' co', ' company', ' holdings',
    ' group', ' international', ' enterprises', ' services',
    ' l.l.c.', ' l.p.', ' p.a.', ' p.l.', ' lp',
]

LEGAL_ENTITY_TYPES = {
    'llc', 'corporation', 'nonprofit', 'limited partnership',
    'general partnership', 'limited liability company',
    'professional association', 'limited liability partnership',
}


def normalize_company_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    for suffix in sorted(LEGAL_SUFFIXES, key=len, reverse=True):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
            break
    n = re.sub(r'[^a-z0-9\s]', '', n)
    return re.sub(r'\s+', ' ', n).strip()


# ── SQL statements ───────────────────────────────────────────────────

ADD_COLUMNS_SQL = """
DO $$
BEGIN
    -- governance fields
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='normalized_name') THEN
        ALTER TABLE companies ADD COLUMN normalized_name text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='geography') THEN
        ALTER TABLE companies ADD COLUMN geography text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='entity_type') THEN
        ALTER TABLE companies ADD COLUMN entity_type text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='priority_tier') THEN
        ALTER TABLE companies ADD COLUMN priority_tier smallint;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='dataset_status') THEN
        ALTER TABLE companies ADD COLUMN dataset_status text DEFAULT 'imported';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='careers_url') THEN
        ALTER TABLE companies ADD COLUMN careers_url text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='careers_accessibility') THEN
        ALTER TABLE companies ADD COLUMN careers_accessibility text DEFAULT 'unknown';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='last_collection_at') THEN
        ALTER TABLE companies ADD COLUMN last_collection_at timestamptz;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='last_analysis_run_id') THEN
        ALTER TABLE companies ADD COLUMN last_analysis_run_id text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='latest_diagnostic_state') THEN
        ALTER TABLE companies ADD COLUMN latest_diagnostic_state text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='positioning_eligible') THEN
        ALTER TABLE companies ADD COLUMN positioning_eligible boolean DEFAULT false;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='notes') THEN
        ALTER TABLE companies ADD COLUMN notes text;
    END IF;
END $$;
"""

CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS ix_companies_normalized_name ON companies (normalized_name);
CREATE INDEX IF NOT EXISTS ix_companies_dataset_status ON companies (dataset_status);
CREATE INDEX IF NOT EXISTS ix_companies_priority_tier ON companies (priority_tier);
CREATE INDEX IF NOT EXISTS ix_companies_geography ON companies (geography);
CREATE INDEX IF NOT EXISTS ix_companies_positioning_eligible ON companies (positioning_eligible);
"""

MIGRATE_ENTITY_TYPE_SQL = """
UPDATE companies
SET entity_type = LOWER(industry),
    industry = NULL
WHERE LOWER(industry) IN ('llc', 'corporation', 'nonprofit',
    'limited partnership', 'general partnership',
    'limited liability company', 'professional association',
    'limited liability partnership');
"""

BACKFILL_GEOGRAPHY_SQL = """
UPDATE companies
SET geography = 'FL'
WHERE source_added_from = 'florida_dos' AND (geography IS NULL OR geography = '');

UPDATE companies
SET geography = 'TX'
WHERE source_added_from = 'json_import' AND (geography IS NULL OR geography = '');

UPDATE companies
SET geography = 'UT'
WHERE source_added_from = 'wikidata_ut' AND (geography IS NULL OR geography = '');
"""

BACKFILL_COLLECTION_SQL = """
UPDATE companies c
SET last_collection_at = cr.max_finished
FROM (
    SELECT company_id, MAX(finished_at) as max_finished
    FROM collection_runs
    WHERE status = 'completed'
    GROUP BY company_id
) cr
WHERE c.id = cr.company_id AND c.last_collection_at IS NULL;
"""

BACKFILL_DATASET_STATUS_SQL = """
-- Mark collected
UPDATE companies
SET dataset_status = 'collected'
WHERE last_collection_at IS NOT NULL AND dataset_status = 'imported';

-- Mark analyzed (has classified roles)
UPDATE companies c
SET dataset_status = 'analyzed'
WHERE EXISTS (
    SELECT 1 FROM company_job_roles jr
    WHERE jr.company_id = c.id
    AND jr.functional_area IS NOT NULL
    AND jr.functional_area NOT IN ('junk', 'unknown')
    HAVING COUNT(*) >= 2
)
AND dataset_status IN ('imported', 'collected');

-- Mark enriched (has JDs)
UPDATE companies c
SET dataset_status = 'enriched'
WHERE EXISTS (
    SELECT 1 FROM company_job_roles jr
    WHERE jr.company_id = c.id
    AND jr.role_description IS NOT NULL
    AND jr.role_description != ''
    HAVING COUNT(*) >= 2
)
AND dataset_status IN ('imported', 'collected', 'analyzed');
"""

CREATE_COVERAGE_VIEW_SQL = """
CREATE OR REPLACE VIEW company_coverage AS
SELECT
    c.id,
    c.name,
    c.normalized_name,
    c.domain,
    c.dataset_status,
    c.priority_tier,
    c.geography,
    c.industry,
    c.entity_type,
    c.careers_accessibility,
    c.latest_diagnostic_state,
    c.positioning_eligible,
    c.last_collection_at,
    c.last_analysis_run_id,
    COALESCE(roles.total, 0) as roles_detected,
    COALESCE(roles.classified, 0) as roles_classified,
    COALESCE(roles.junk, 0) as roles_junk,
    COALESCE(roles.with_jd, 0) as jds_extracted,
    COALESCE(signals.cnt, 0) as signal_count,
    CASE
        WHEN COALESCE(roles.classified, 0) >= 5 AND COALESCE(roles.with_jd, 0) >= 3 THEN 'deep'
        WHEN COALESCE(roles.classified, 0) >= 2 THEN 'partial'
        WHEN COALESCE(signals.cnt, 0) > 0 THEN 'shallow'
        WHEN c.domain IS NOT NULL AND c.domain != '' THEN 'identified'
        ELSE 'stub'
    END as evidence_band
FROM companies c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE functional_area NOT IN ('junk', 'unknown') AND functional_area IS NOT NULL) as classified,
        COUNT(*) FILTER (WHERE functional_area = 'junk') as junk,
        COUNT(*) FILTER (WHERE role_description IS NOT NULL AND role_description != '') as with_jd
    FROM company_job_roles WHERE company_id = c.id
) roles ON true
LEFT JOIN LATERAL (
    SELECT COUNT(*) as cnt FROM company_signals WHERE company_id = c.id
) signals ON true;
"""


def main():
    parser = argparse.ArgumentParser(description="Dataset governance migration")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    args = parser.parse_args()

    db = SessionLocal()

    steps = [
        ("Add governance columns", ADD_COLUMNS_SQL),
        ("Create indexes", CREATE_INDEXES_SQL),
        ("Migrate entity_type from industry", MIGRATE_ENTITY_TYPE_SQL),
        ("Backfill geography from source", BACKFILL_GEOGRAPHY_SQL),
        ("Backfill last_collection_at", BACKFILL_COLLECTION_SQL),
        ("Backfill dataset_status", BACKFILL_DATASET_STATUS_SQL),
        ("Create company_coverage view", CREATE_COVERAGE_VIEW_SQL),
    ]

    if args.dry_run:
        print("DRY RUN — would execute:")
        for i, (name, sql) in enumerate(steps):
            print(f"\n  Step {i+1}: {name}")
            print(f"  SQL preview: {sql[:120].strip()}...")
        print("\nAlso: normalize names for all companies (Python)")
        db.close()
        return

    for i, (name, sql) in enumerate(steps):
        print(f"[{i+1}/{len(steps)}] {name}...", end=" ", flush=True)
        try:
            db.execute(text(sql))
            db.commit()
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            db.rollback()

    # Normalize names (requires Python)
    print(f"[{len(steps)+1}] Normalizing company names...", end=" ", flush=True)
    rows = db.execute(text("SELECT id, name FROM companies WHERE normalized_name IS NULL")).fetchall()
    count = 0
    for row in rows:
        nn = normalize_company_name(row[1])
        if nn:
            db.execute(
                text("UPDATE companies SET normalized_name = :nn WHERE id = :id"),
                {"nn": nn, "id": row[0]}
            )
            count += 1
    db.commit()
    print(f"OK ({count} names normalized)")

    # Summary
    print("\n" + "=" * 60)
    print("  Migration Summary")
    print("=" * 60)

    for label, query in [
        ("Total companies", "SELECT COUNT(*) FROM companies"),
        ("With domain", "SELECT COUNT(*) FROM companies WHERE domain IS NOT NULL"),
        ("With normalized_name", "SELECT COUNT(*) FROM companies WHERE normalized_name IS NOT NULL"),
        ("With geography", "SELECT COUNT(*) FROM companies WHERE geography IS NOT NULL"),
        ("With entity_type", "SELECT COUNT(*) FROM companies WHERE entity_type IS NOT NULL"),
        ("With real industry", "SELECT COUNT(*) FROM companies WHERE industry IS NOT NULL"),
    ]:
        val = db.execute(text(query)).scalar()
        print(f"  {label:30s}: {val}")

    print("\n  Dataset status distribution:")
    statuses = db.execute(text(
        "SELECT dataset_status, COUNT(*) FROM companies GROUP BY 1 ORDER BY 2 DESC"
    )).fetchall()
    for status, cnt in statuses:
        print(f"    {status or 'NULL':20s}: {cnt}")

    print("\n  Evidence band distribution (from view):")
    try:
        bands = db.execute(text(
            "SELECT evidence_band, COUNT(*) FROM company_coverage GROUP BY 1 ORDER BY 2 DESC"
        )).fetchall()
        for band, cnt in bands:
            print(f"    {band:20s}: {cnt}")
    except Exception as e:
        print(f"    Error reading view: {e}")
        db.rollback()

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()

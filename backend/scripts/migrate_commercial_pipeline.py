"""
Phase 11 Migration — Creates commercial pipeline tables.

Creates:
  - pipeline_entries: company review workflow tracking
  - pipeline_events: audit log for all state transitions

Usage:
    cd backend
    python scripts/migrate_commercial_pipeline.py
    python scripts/migrate_commercial_pipeline.py --dry-run
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


CREATE_PIPELINE_ENTRIES = """
CREATE TABLE IF NOT EXISTS pipeline_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    stage TEXT NOT NULL DEFAULT 'radar',
    priority SMALLINT,
    diagnostic_state_at_intake TEXT,
    confidence_band_at_intake TEXT,
    dominant_function TEXT,
    classified_roles_count SMALLINT,
    jds_count SMALLINT,
    positioning_eligible BOOLEAN DEFAULT FALSE,
    reviewer TEXT,
    review_notes TEXT,
    review_decision TEXT,
    reviewed_at TIMESTAMPTZ,
    candidate_archetype TEXT,
    positioning_angle TEXT,
    target_profile_notes TEXT,
    message_angle_draft TEXT,
    intake_source TEXT,
    batch_run_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_pipeline_company UNIQUE (company_id)
);
"""

CREATE_PIPELINE_EVENTS = """
CREATE TABLE IF NOT EXISTS pipeline_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_entry_id UUID NOT NULL REFERENCES pipeline_entries(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    from_stage TEXT,
    to_stage TEXT,
    actor TEXT,
    note TEXT,
    metadata_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_pipeline_entries_company_id ON pipeline_entries(company_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_entries_stage ON pipeline_entries(stage);
CREATE INDEX IF NOT EXISTS ix_pipeline_entries_priority ON pipeline_entries(priority);
CREATE INDEX IF NOT EXISTS ix_pipeline_events_entry_id ON pipeline_events(pipeline_entry_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_events_created ON pipeline_events(created_at);
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()

    steps = [
        ("Create pipeline_entries table", CREATE_PIPELINE_ENTRIES),
        ("Create pipeline_events table", CREATE_PIPELINE_EVENTS),
        ("Create indexes", CREATE_INDEXES),
    ]

    if args.dry_run:
        print("DRY RUN:")
        for name, sql in steps:
            print(f"\n  {name}")
            print(f"  {sql[:100].strip()}...")
        db.close()
        return

    for name, sql in steps:
        print(f"  {name}...", end=" ", flush=True)
        try:
            db.execute(text(sql))
            db.commit()
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            db.rollback()

    # Verify
    cnt = db.execute(text("SELECT COUNT(*) FROM pipeline_entries")).scalar()
    print(f"\n  pipeline_entries: {cnt} rows")
    cnt = db.execute(text("SELECT COUNT(*) FROM pipeline_events")).scalar()
    print(f"  pipeline_events: {cnt} rows")

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()

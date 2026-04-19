"""Remove the 722 ashby_board_detected false positives and their
accompanying careers_page_found signals that point to jobs.ashbyhq.com.

Context: the `ats_public` collector's `_try_all_ats` helper matched ANY
slug against jobs.ashbyhq.com — Ashby serves a 6KB SPA shell with HTTP
200 for every slug, so the weak `_has_job_elements` check passed.
The collector has been patched (F1b) and will no longer emit these
signals going forward. This one-shot script cleans up the existing
polluted rows.

Verification: the canonical backfill (scripts/backfill_ashby_roles.py)
confirmed 0/722 slugs resolve to a real Ashby workspace via GraphQL,
so the deletion is safe — none of these are real.

Usage:
  python scripts/cleanup_ashby_false_positives.py --dry-run
  python scripts/cleanup_ashby_false_positives.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()

    ashby_count = db.execute(text("""
        SELECT COUNT(*) FROM company_signals
        WHERE signal_type = 'ashby_board_detected'
    """)).scalar()

    careers_count = db.execute(text("""
        SELECT COUNT(*) FROM company_signals
        WHERE signal_type = 'careers_page_found'
          AND source_url LIKE '%jobs.ashbyhq.com%'
          AND source_type IN ('ats_public', 'careers')
    """)).scalar()

    print(f"Will delete:")
    print(f"  {ashby_count} ashby_board_detected signals")
    print(f"  {careers_count} careers_page_found signals "
          f"(source_type=ats_public, pointing to jobs.ashbyhq.com)")

    if args.dry_run:
        print("\n[DRY RUN] no changes applied.")
        db.close()
        return

    result1 = db.execute(text("""
        DELETE FROM company_signals
        WHERE signal_type = 'ashby_board_detected'
    """))
    result2 = db.execute(text("""
        DELETE FROM company_signals
        WHERE signal_type = 'careers_page_found'
          AND source_url LIKE '%jobs.ashbyhq.com%'
          AND source_type IN ('ats_public', 'careers')
    """))
    db.commit()

    print(f"\nDeleted:")
    print(f"  {result1.rowcount} ashby_board_detected rows")
    print(f"  {result2.rowcount} careers_page_found rows")

    db.close()


if __name__ == "__main__":
    main()

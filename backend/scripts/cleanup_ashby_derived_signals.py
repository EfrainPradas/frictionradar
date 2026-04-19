"""Extension of F1b cleanup: delete the 4370 residual signals that were
derived from Ashby SPA shells.

Context:
  F1b fixed `careers_url_finder._try_all_ats` and cleaned up
  `ashby_board_detected` + `careers_page_found` signals pointing to
  jobs.ashbyhq.com. BUT the derived signals from those polluted careers
  pages were never cleaned up:
    - {category}_hiring_detected (careers/dynamic_careers/hybrid_careers_v2
      emitted because the 6KB Ashby shell matched keywords)
    - career-related signals from extraction_http_static/playwright that
      landed on Ashby URLs via the old weak detection

This keeps 634 companies classified as broad_hiring_pattern_detected
with 100% false-positive evidence.

SCOPE: delete signals WHERE source_url LIKE '%jobs.ashbyhq.com%' AND
source_type IN allowed set. Preserves source_type='extraction_ats_api'
(the real Ashby GraphQL path, confirmed working in F1).

Usage:
  python scripts/cleanup_ashby_derived_signals.py --dry-run
  python scripts/cleanup_ashby_derived_signals.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


POLLUTED_SOURCE_TYPES = (
    "careers",
    "dynamic_careers",
    "hybrid_careers_v2",
    "company_site",
    "extraction_playwright",
    "extraction_http_static",
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()

    total = db.execute(text("""
        SELECT COUNT(*) FROM company_signals
        WHERE source_url LIKE '%jobs.ashbyhq.com%'
          AND source_type IN :sts
    """).bindparams(sts=tuple(POLLUTED_SOURCE_TYPES))).scalar()

    print(f"Signals to delete (source_url LIKE jobs.ashbyhq.com AND source_type in polluted set): {total}")

    breakdown = db.execute(text("""
        SELECT signal_type, source_type, COUNT(*) AS n
        FROM company_signals
        WHERE source_url LIKE '%jobs.ashbyhq.com%'
          AND source_type IN :sts
        GROUP BY signal_type, source_type
        ORDER BY n DESC
    """).bindparams(sts=tuple(POLLUTED_SOURCE_TYPES))).fetchall()

    print("\nBreakdown:")
    for r in breakdown:
        print(f"  {r.signal_type:40s} [{r.source_type:22s}] {r.n:>5d}")

    preserved = db.execute(text("""
        SELECT COUNT(*) FROM company_signals
        WHERE source_url LIKE '%jobs.ashbyhq.com%'
          AND source_type = 'extraction_ats_api'
    """)).scalar()
    print(f"\nPreserved (source_type='extraction_ats_api' — legit Ashby): {preserved}")

    affected = db.execute(text("""
        SELECT COUNT(DISTINCT company_id) FROM company_signals
        WHERE source_url LIKE '%jobs.ashbyhq.com%'
          AND source_type IN :sts
    """).bindparams(sts=tuple(POLLUTED_SOURCE_TYPES))).scalar()
    print(f"Distinct companies affected: {affected}")

    if args.dry_run:
        print("\n[DRY RUN] no changes applied.")
        db.close()
        return

    print("\nExecuting delete...")
    result = db.execute(text("""
        DELETE FROM company_signals
        WHERE source_url LIKE '%jobs.ashbyhq.com%'
          AND source_type IN :sts
    """).bindparams(sts=tuple(POLLUTED_SOURCE_TYPES)))
    db.commit()
    print(f"Deleted {result.rowcount} rows.")

    db.close()


if __name__ == "__main__":
    main()

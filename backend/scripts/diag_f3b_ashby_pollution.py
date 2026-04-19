"""Quantify residual Ashby-shell pollution: _hiring_detected signals
pointing to jobs.ashbyhq.com that leaked through the F1b cleanup.

F1b cleanup deleted:
  - ashby_board_detected signals
  - careers_page_found signals with source_url LIKE '%jobs.ashbyhq.com%'

But did NOT clean the derived:
  - *_hiring_detected signals (emitted because keywords matched in the
    Ashby shell HTML)
  - open_positions_count_detected / job_cards_visible_detected signals
    that may have been parsed from the shell

These residuals keep companies passing the 5-category eligibility threshold
with 100% false-positive evidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


def main():
    db = SessionLocal()

    print("=" * 80)
    print("RESIDUAL ASHBY POLLUTION — signals pointing to jobs.ashbyhq.com")
    print("=" * 80)

    total = db.execute(text("""
        SELECT COUNT(*) FROM company_signals
        WHERE source_url LIKE '%jobs.ashbyhq.com%'
    """)).scalar()
    print(f"\nTotal signals with source_url containing jobs.ashbyhq.com: {total}")

    rows = db.execute(text("""
        SELECT signal_type, source_type, COUNT(*) AS n
        FROM company_signals
        WHERE source_url LIKE '%jobs.ashbyhq.com%'
        GROUP BY signal_type, source_type
        ORDER BY n DESC
    """)).fetchall()

    print("\nBreakdown by (signal_type, source_type):")
    for r in rows:
        print(f"  {r.signal_type:40s} [{r.source_type or '-':20s}] {r.n:>5d}")

    affected = db.execute(text("""
        SELECT COUNT(DISTINCT company_id) FROM company_signals
        WHERE source_url LIKE '%jobs.ashbyhq.com%'
    """)).scalar()
    print(f"\nDistinct companies affected: {affected}")

    with_pattern = db.execute(text("""
        SELECT COUNT(DISTINCT c.id)
        FROM companies c
        JOIN company_signals s ON s.company_id = c.id
        WHERE s.source_url LIKE '%jobs.ashbyhq.com%'
          AND s.signal_type LIKE '%_hiring_detected'
    """)).scalar()
    print(f"Distinct companies with >=1 _hiring_detected Ashby-shell signal: {with_pattern}")

    no_other_hiring = db.execute(text("""
        WITH ashby_companies AS (
            SELECT DISTINCT company_id
            FROM company_signals
            WHERE source_url LIKE '%jobs.ashbyhq.com%'
              AND signal_type LIKE '%_hiring_detected'
        )
        SELECT COUNT(*)
        FROM ashby_companies ac
        WHERE NOT EXISTS (
            SELECT 1 FROM company_signals s
            WHERE s.company_id = ac.company_id
              AND s.signal_type LIKE '%_hiring_detected'
              AND (s.source_url IS NULL OR s.source_url NOT LIKE '%jobs.ashbyhq.com%')
        )
    """)).scalar()
    print(f"  of those, companies where ALL _hiring_detected come from Ashby shells: {no_other_hiring}")

    db.close()


if __name__ == "__main__":
    main()

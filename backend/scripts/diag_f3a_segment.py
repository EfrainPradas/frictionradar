"""Segment the 65 silent-failure companies by WHICH path emitted the
evidence signal: collector-only (careers, dynamic_careers) vs
extraction-* (batch_runner's extract_company succeeded).

This tells us where the fix has to go:
  - collector-only -> collectors never call persist_job_role (bug A)
  - extraction-*   -> persist_job_role path raised/silently failed (bug B)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


def main():
    db = SessionLocal()

    rows = db.execute(text("""
        WITH target AS (
            SELECT c.id
            FROM companies c
            WHERE c.last_collection_at IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)
              AND EXISTS (
                  SELECT 1 FROM company_signals s
                  WHERE s.company_id = c.id
                    AND s.signal_type IN (
                        'job_cards_visible_detected',
                        'job_links_extracted'
                    )
              )
        )
        SELECT
            t.id,
            (SELECT COUNT(*) FROM company_signals s
             WHERE s.company_id = t.id
               AND s.source_type LIKE 'extraction_%'
               AND s.signal_type = 'job_cards_visible_detected') AS ext_cards,
            (SELECT COUNT(*) FROM company_signals s
             WHERE s.company_id = t.id
               AND s.source_type IN ('dynamic_careers', 'hybrid_careers_v2', 'playwright_careers')
               AND s.signal_type = 'job_cards_visible_detected') AS col_cards,
            (SELECT COUNT(*) FROM company_signals s
             WHERE s.company_id = t.id
               AND s.source_type = 'careers'
               AND s.signal_type = 'job_links_extracted') AS col_links,
            (SELECT COUNT(*) FROM company_signals s
             WHERE s.company_id = t.id
               AND s.source_type LIKE 'extraction_%') AS any_extraction
        FROM target t
    """)).fetchall()

    total = len(rows)
    ext_cards_with_persist_fail = 0
    col_only_cards = 0
    col_only_links = 0
    mixed = 0
    no_extraction_at_all = 0

    for r in rows:
        cid, ext_cards, col_cards, col_links, any_ext = r
        if ext_cards > 0:
            ext_cards_with_persist_fail += 1
        elif any_ext == 0:
            no_extraction_at_all += 1
            if col_cards and not col_links:
                col_only_cards += 1
            elif col_links and not col_cards:
                col_only_links += 1
            else:
                mixed += 1

    print(f"Total silent-failure companies with cards/links signals: {total}")
    print()
    print(f"A. ext_* job_cards emitted but 0 roles persisted (batch_runner bug B):  {ext_cards_with_persist_fail}")
    print(f"B. NO extraction_* signal at all (batch_runner never ran or failed):    {no_extraction_at_all}")
    print(f"   - of which collector cards only (dynamic_careers etc):               {col_only_cards}")
    print(f"   - of which collector links only (careers collector):                 {col_only_links}")
    print(f"   - of which mixed/other:                                              {mixed}")

    db.close()


if __name__ == "__main__":
    main()

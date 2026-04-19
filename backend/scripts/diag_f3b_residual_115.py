"""Investigate the 115 companies remaining in 'some signals but no
careers_page_found' bucket AFTER the Ashby cleanup. These are real
companies with newsroom/funding/scaling signals but no discovered
careers page.

Question: are any recoverable via a second careers discovery pass,
or are they fundamentally careers-less (agencies, holding companies,
discontinued brands)?
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


def main():
    db = SessionLocal()

    rows = db.execute(text("""
        SELECT c.id, c.name, c.domain, c.geography,
               (SELECT COUNT(*) FROM company_signals s WHERE s.company_id = c.id) AS total_sig,
               ARRAY(
                 SELECT DISTINCT signal_type FROM company_signals
                 WHERE company_id = c.id
               )::text AS signal_types
        FROM companies c
        WHERE c.last_collection_at IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)
          AND NOT EXISTS (
              SELECT 1 FROM company_signals s
              WHERE s.company_id = c.id AND s.signal_type = 'careers_page_found'
          )
          AND EXISTS (
              SELECT 1 FROM company_signals s WHERE s.company_id = c.id
          )
        ORDER BY c.name
    """)).fetchall()

    total = len(rows)
    print(f"Residual F3b bucket: {total} companies with signals but no careers_page_found")
    print("=" * 80)

    geo_counter: Counter = Counter()
    llc_count = 0
    with_newsroom = 0
    with_funding = 0
    with_scaling = 0
    with_hiring_news = 0
    with_hiring_signal = 0

    for r in rows:
        geo_counter[r.geography or "n/a"] += 1
        if r.name and ("LLC" in r.name.upper() or " INC" in r.name.upper() or " CORP" in r.name.upper()):
            llc_count += 1
        sigs = r.signal_types or ""
        if "newsroom_found" in sigs:
            with_newsroom += 1
        if "funding_detected" in sigs:
            with_funding += 1
        if "scaling_language_detected" in sigs:
            with_scaling += 1
        if "hiring_news_detected" in sigs:
            with_hiring_news += 1
        if "_hiring_detected" in sigs:
            with_hiring_signal += 1

    print(f"\nGeo distribution:")
    for g, n in geo_counter.most_common():
        print(f"  {g:10s} {n:>4d}")

    print(f"\nHas LLC/Inc/Corp suffix: {llc_count}/{total}")
    print(f"Has any _hiring_detected (non-Ashby): {with_hiring_signal}/{total}")
    print(f"Has newsroom_found:        {with_newsroom}/{total}")
    print(f"Has funding_detected:      {with_funding}/{total}")
    print(f"Has scaling_language:      {with_scaling}/{total}")
    print(f"Has hiring_news_detected:  {with_hiring_news}/{total}")

    recoverable = [r for r in rows if r.signal_types and (
        "funding_detected" in r.signal_types or
        "hiring_news_detected" in r.signal_types or
        "scaling_language_detected" in r.signal_types
    )]
    print(f"\nStrong recovery candidates (funding|hiring_news|scaling): {len(recoverable)}")
    for r in recoverable[:25]:
        print(f"  [{(r.geography or 'n/a'):10s}] {r.name:45s} domain={r.domain}")

    db.close()


if __name__ == "__main__":
    main()

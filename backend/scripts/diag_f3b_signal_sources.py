"""For the 522 companies (no careers_page_found), find which source_type
emits the universal _hiring_detected signals and what the source_url points to.

If these are false positives, that's a bug feeding noise into the eligibility
evaluation — they pass evidence thresholds without real evidence.
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
        SELECT s.source_type, s.signal_type, s.source_url
        FROM company_signals s
        JOIN companies c ON c.id = s.company_id
        WHERE c.last_collection_at IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)
          AND NOT EXISTS (
              SELECT 1 FROM company_signals s2
              WHERE s2.company_id = c.id AND s2.signal_type = 'careers_page_found'
          )
          AND s.signal_type LIKE '%_hiring_detected'
    """)).fetchall()

    print(f"Total _hiring_detected signals for 522 companies: {len(rows)}")
    print()

    by_source_type: Counter = Counter()
    by_signal_and_source: Counter = Counter()
    url_samples: dict = {}

    for r in rows:
        by_source_type[r.source_type or "(none)"] += 1
        key = (r.source_type, r.signal_type)
        by_signal_and_source[key] += 1
        if key not in url_samples and r.source_url:
            url_samples[key] = r.source_url

    print("source_type distribution:")
    for src, n in by_source_type.most_common():
        print(f"  {src:30s} {n:>6d}")

    print()
    print("sample source_url per (source_type, signal_type):")
    for (src, sig), n in sorted(by_signal_and_source.items()):
        url = url_samples.get((src, sig), "(no url)")[:80]
        print(f"  [{src:25s}] {sig:40s} n={n:>4d}  url={url}")

    db.close()


if __name__ == "__main__":
    main()

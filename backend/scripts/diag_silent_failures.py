"""Segment the ~688 'collected_no_roles' companies by which signals they
emitted, to pinpoint where the extraction pipeline breaks down.

Buckets (a company falls in the first one that matches):
  a. No careers page ever found — collector failed to locate any
  b. careers_page_found but NO job_links_extracted and NO job_cards — extractor saw nothing
  c. job_links_extracted emitted but 0 roles persisted — role_ingest path broken
  d. job_cards_visible_detected but 0 roles persisted — Playwright extracted cards but persist_job_role failed
  e. Has open_positions_count signal but 0 roles — counter-only extraction
  f. Other (catch-all)

Prints counts + 5 samples per bucket.
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


def main():
    db = SessionLocal()

    rows = db.execute(text("""
        SELECT c.id, c.name, c.domain, c.geography,
               (SELECT COUNT(*) FROM company_signals s
                WHERE s.company_id = c.id AND s.signal_type = 'careers_page_found') AS has_careers,
               (SELECT COUNT(*) FROM company_signals s
                WHERE s.company_id = c.id AND s.signal_type = 'job_links_extracted') AS has_links,
               (SELECT COUNT(*) FROM company_signals s
                WHERE s.company_id = c.id AND s.signal_type = 'job_cards_visible_detected') AS has_cards,
               (SELECT COUNT(*) FROM company_signals s
                WHERE s.company_id = c.id
                  AND s.signal_type IN ('open_positions_count_detected',
                                        'high_open_positions_count_detected')) AS has_count,
               (SELECT COUNT(*) FROM company_signals s
                WHERE s.company_id = c.id) AS total_signals
        FROM companies c
        WHERE c.last_collection_at IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)
    """)).fetchall()

    total = len(rows)
    buckets: Counter = Counter()
    samples: dict = defaultdict(list)

    for r in rows:
        cid, name, domain, geo, has_careers, has_links, has_cards, has_count, total_sig = r
        if has_cards:
            b = "d_cards_no_roles"
        elif has_links:
            b = "c_links_no_roles"
        elif has_count:
            b = "e_count_only"
        elif has_careers:
            b = "b_careers_no_extraction"
        elif total_sig == 0:
            b = "a0_no_signals_at_all"
        else:
            b = "a_no_careers_found"

        buckets[b] += 1
        if len(samples[b]) < 5:
            samples[b].append({
                "name": name, "domain": domain, "geo": geo,
                "careers": has_careers, "links": has_links,
                "cards": has_cards, "count": has_count,
                "total": total_sig,
            })

    print("=" * 80)
    print(f"SILENT FAILURE DIAGNOSIS — {total} companies (collected, 0 roles)")
    print("=" * 80)
    print()

    order = [
        "a0_no_signals_at_all",
        "a_no_careers_found",
        "b_careers_no_extraction",
        "c_links_no_roles",
        "d_cards_no_roles",
        "e_count_only",
    ]
    labels = {
        "a0_no_signals_at_all":    "No signals at all (collector never emitted anything)",
        "a_no_careers_found":      "Some signals but no careers_page_found",
        "b_careers_no_extraction": "careers_page_found but NO links/cards/count (extractor saw 0)",
        "c_links_no_roles":        "job_links_extracted but 0 roles persisted",
        "d_cards_no_roles":        "job_cards_visible_detected but 0 roles persisted",
        "e_count_only":            "Only open_positions_count (counter-only extraction)",
    }
    for b in order:
        n = buckets.get(b, 0)
        pct = n / total * 100 if total else 0
        print(f"  {labels[b]:60s} {n:>4d}  ({pct:>5.1f}%)")

    print()
    print("=" * 80)
    print("SAMPLES")
    print("=" * 80)
    for b in order:
        if not samples.get(b):
            continue
        print()
        print(f"── {labels[b]} ({buckets[b]} total) ──")
        for s in samples[b][:5]:
            print(f"  [{(s['geo'] or 'n/a')[:10]:10s}] {(s['name'] or '')[:35]:35s} "
                  f"careers={s['careers']} links={s['links']} cards={s['cards']} count={s['count']} total={s['total']}")

    db.close()


if __name__ == "__main__":
    main()

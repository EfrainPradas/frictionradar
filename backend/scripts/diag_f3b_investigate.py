"""Deep-dive F3b: understand the 521 silent-failure companies that have
signals but NO careers_page_found.

Questions to answer:
  1. Geography distribution (FL LLCs vs real companies)
  2. What signals DO they have? (scaling_language, newsroom, funding, etc.)
  3. Do they have a domain that resolves? (i.e. real website vs shell)
  4. What fraction look like recoverable real businesses?
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
               (SELECT COUNT(*) FROM company_signals s WHERE s.company_id = c.id) AS total_sig,
               ARRAY(
                 SELECT DISTINCT signal_type FROM company_signals
                 WHERE company_id = c.id
                 ORDER BY signal_type
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
    print(f"F3b TARGET: {total} companies with signals but no careers_page_found")
    print("=" * 80)

    # 1) Geography distribution
    geo_counter: Counter = Counter()
    for r in rows:
        geo_counter[r.geography or "n/a"] += 1
    print("\nGeography distribution:")
    for geo, n in geo_counter.most_common():
        pct = n / total * 100
        print(f"  {geo:15s} {n:>4d}  ({pct:>5.1f}%)")

    # 2) LLC/Corp suffix heuristic
    llc_count = sum(1 for r in rows if r.name and (
        " LLC" in r.name.upper() or r.name.upper().endswith("LLC") or
        r.name.upper().endswith(" INC") or r.name.upper().endswith(", INC.") or
        r.name.upper().endswith(" CORP") or r.name.upper().endswith("CORPORATION")
    ))
    print(f"\nName contains LLC/Inc/Corp suffix: {llc_count}/{total} ({llc_count/total*100:.1f}%)")

    # 3) Signal type frequency
    sig_counter: Counter = Counter()
    for r in rows:
        # signal_types is a text representation like '{sig1,sig2,sig3}'
        s = (r.signal_types or "{}").strip("{}")
        if s:
            for t in s.split(","):
                sig_counter[t.strip()] += 1
    print(f"\nMost common signal types across 521:")
    for sig, n in sig_counter.most_common(15):
        pct = n / total * 100
        print(f"  {sig:45s} {n:>4d}  ({pct:>5.1f}%)")

    # 4) Companies with newsroom_found (real businesses, more recoverable)
    with_newsroom = sum(1 for r in rows if r.signal_types and "newsroom_found" in r.signal_types)
    with_funding = sum(1 for r in rows if r.signal_types and "funding_detected" in r.signal_types)
    with_scaling = sum(1 for r in rows if r.signal_types and "scaling_language_detected" in r.signal_types)
    print(f"\n'Real business' markers:")
    print(f"  has newsroom_found:        {with_newsroom}/{total} ({with_newsroom/total*100:.1f}%)")
    print(f"  has funding_detected:      {with_funding}/{total} ({with_funding/total*100:.1f}%)")
    print(f"  has scaling_language:      {with_scaling}/{total} ({with_scaling/total*100:.1f}%)")

    # 5) Segment: FL LLCs vs everything else
    fl_llcs = [r for r in rows if r.geography == "FL" and r.name and "LLC" in (r.name or "").upper()]
    print(f"\nFL + LLC in name: {len(fl_llcs)} ({len(fl_llcs)/total*100:.1f}%)")

    # 6) Non-LLC non-FL samples (plausibly recoverable)
    recoverable_candidates = [
        r for r in rows
        if not (r.geography == "FL" and r.name and "LLC" in (r.name or "").upper())
    ]
    print(f"\nNon-FL-LLC candidates (potentially recoverable): {len(recoverable_candidates)}")
    for r in recoverable_candidates[:20]:
        print(f"  [{(r.geography or 'n/a'):10s}] {r.name:40s} domain={r.domain} sig={r.total_sig}")

    db.close()


if __name__ == "__main__":
    main()

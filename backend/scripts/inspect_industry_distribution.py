"""Inspect industry distribution in companies table.

Prints:
  - total companies, null industry rate
  - top industries by raw value
  - industry × positioning_eligible cross-tab
  - industry × latest_diagnostic_state cross-tab (top 30 industries)
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.company import Company


def main():
    db = SessionLocal()

    companies = db.query(Company).all()
    total = len(companies)
    null_industry = sum(1 for c in companies if not c.industry)
    print(f"Total companies: {total}")
    print(f"Null industry:   {null_industry} ({null_industry/total*100:.1f}%)")
    print(f"With industry:   {total - null_industry}")

    counter = Counter()
    for c in companies:
        counter[(c.industry or "").strip().lower() or "(null)"] += 1

    print(f"\nTop 40 industries (raw):")
    for ind, n in counter.most_common(40):
        print(f"  {n:5d}  {ind[:80]}")

    eligible_by_industry = Counter()
    state_by_industry = defaultdict(Counter)
    for c in companies:
        key = (c.industry or "").strip().lower() or "(null)"
        if c.positioning_eligible:
            eligible_by_industry[key] += 1
        state_by_industry[key][c.latest_diagnostic_state or "(null)"] += 1

    print(f"\nEligibles by industry (top 20):")
    for ind, n in eligible_by_industry.most_common(20):
        total_ind = counter[ind]
        print(f"  {n:3d}/{total_ind:5d}  ({n/total_ind*100:4.1f}%)  {ind[:70]}")

    print(f"\nSample industries with >= 3 companies and diagnostic breakdown:")
    rich_inds = [i for i, n in counter.most_common(30) if n >= 3]
    for ind in rich_inds[:30]:
        states = state_by_industry[ind]
        line = f"  {counter[ind]:4d}  {ind[:45]:45s}"
        for st in [
            "ready_for_positioning",
            "specific_pain_identified",
            "specific_pain_emerging",
            "broad_hiring_pattern_detected",
            "insufficient_evidence",
            "(null)",
        ]:
            line += f" | {st[:18]}={states.get(st, 0)}"
        print(line)

    db.close()


if __name__ == "__main__":
    main()

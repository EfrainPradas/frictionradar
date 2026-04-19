"""Inspect how eligibles map across inferred_sector buckets.

Uses the same on-the-fly eligibility recount that positioning_engine applies:
  - full: diagnostic in {ready_for_positioning, specific_pain_identified}
  - conditional: specific_pain_emerging AND classified>=3 with top_share>=0.35
                 OR broad_hiring_pattern_detected AND
                    (classified>=5 AND top_share>=0.35)  OR  classified>=15
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole

EXCLUDED_AREAS = {None, "", "junk", "unknown", "Technology"}


def main():
    db = SessionLocal()

    companies = db.query(Company).all()

    roles_by_company = defaultdict(list)
    for r in db.query(CompanyJobRole).all():
        roles_by_company[r.company_id].append(r)

    def classify_eligibility(c: Company):
        roles = roles_by_company.get(c.id, [])
        fn_counts = Counter(
            r.functional_area for r in roles if r.functional_area not in EXCLUDED_AREAS
        )
        classified = sum(fn_counts.values())
        top_share = (
            max(fn_counts.values()) / classified if classified else 0.0
        )

        ds = c.latest_diagnostic_state
        if ds in ("ready_for_positioning", "specific_pain_identified"):
            return "full"
        if ds == "specific_pain_emerging" and classified >= 3 and top_share >= 0.35:
            return "conditional"
        if ds == "broad_hiring_pattern_detected":
            if classified >= 5 and top_share >= 0.35:
                return "conditional"
            if classified >= 15:
                return "conditional"
        return None

    sector_totals = Counter()
    sector_full = Counter()
    sector_conditional = Counter()

    for c in companies:
        sector = c.inferred_sector or "Other"
        sector_totals[sector] += 1
        status = classify_eligibility(c)
        if status == "full":
            sector_full[sector] += 1
        elif status == "conditional":
            sector_conditional[sector] += 1

    print(f"{'Sector':35s} {'Total':>6s} {'Full':>5s} {'Cond':>5s} {'Elig%':>6s}")
    print("-" * 65)
    for sector in sorted(
        sector_totals,
        key=lambda s: -(sector_full[s] + sector_conditional[s])
    ):
        tot = sector_totals[sector]
        f = sector_full[sector]
        cd = sector_conditional[sector]
        pct = (f + cd) / tot * 100 if tot else 0.0
        print(f"{sector[:34]:35s} {tot:6d} {f:5d} {cd:5d} {pct:5.1f}%")

    total_full = sum(sector_full.values())
    total_cond = sum(sector_conditional.values())
    print("-" * 65)
    print(f"{'TOTAL':35s} {sum(sector_totals.values()):6d} {total_full:5d} {total_cond:5d}")
    print(f"\nTotal eligibles: {total_full + total_cond}")

    db.close()


if __name__ == "__main__":
    main()

"""Diagnose per-company outcome for the wikidata import.

Shows each of the 33 wikidata companies with:
  - careers URL found?
  - roles detected / classified
  - diagnostic state
  - eligibility

Usage:
  python scripts/diag_wikidata_results.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.positioning_engine import compute_eligibility_snapshot


def main():
    db = SessionLocal()

    print("Loading eligibility snapshot...")
    snap = compute_eligibility_snapshot(db)
    elig_map = {str(c["company_id"]): c for c in snap["by_company"]}

    rows = db.execute(text("""
        SELECT
          c.id::text AS id, c.name, c.domain, c.careers_url,
          c.dataset_status, c.latest_diagnostic_state,
          c.positioning_eligible,
          (SELECT COUNT(*) FROM company_job_roles r WHERE r.company_id = c.id) AS roles,
          (SELECT COUNT(*) FROM company_job_roles r
             WHERE r.company_id = c.id
               AND r.functional_area IS NOT NULL
               AND r.functional_area NOT IN ('junk', 'unknown')) AS classified
        FROM companies c
        WHERE c.source_added_from = 'wikidata'
        ORDER BY c.positioning_eligible DESC NULLS LAST, classified DESC, roles DESC, c.name
    """)).fetchall()

    print(f"\n{'Company':<30s} {'Careers':<5s} {'Roles':>5s} {'Cls':>4s} {'DS':<22s} {'Elig':<5s}")
    print("-" * 95)

    cnt_no_careers = cnt_no_roles = cnt_no_classified = cnt_elig = 0

    for r in rows:
        has_careers = "Y" if r.careers_url else "-"
        ds = (r.latest_diagnostic_state or "-")[:21]
        elig_info = elig_map.get(str(r.id), {})
        elig_flag = "YES" if elig_info.get("eligible") else ("cond" if elig_info.get("conditional") else "-")

        if not r.careers_url: cnt_no_careers += 1
        elif r.roles == 0: cnt_no_roles += 1
        elif r.classified == 0: cnt_no_classified += 1
        if elig_info.get("eligible") or elig_info.get("conditional"): cnt_elig += 1

        print(f"{r.name[:29]:30s} {has_careers:<5s} {r.roles:>5d} {r.classified:>4d} {ds:<22s} {elig_flag:<5s}")

    print("-" * 95)
    print(f"\nBreakdown:")
    print(f"  No careers URL found:    {cnt_no_careers}")
    print(f"  Careers OK, 0 roles:     {cnt_no_roles}")
    print(f"  Roles OK, 0 classified:  {cnt_no_classified}")
    print(f"  Eligible:                {cnt_elig}")

    print(f"\nGlobal snapshot: full={snap['full']} conditional={snap['conditional']}")

    db.close()


if __name__ == "__main__":
    main()

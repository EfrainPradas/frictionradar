"""Dump junk/unknown role titles for wikidata companies to diagnose classifier gaps.

Output is grouped by company and shows:
  - all unclassified (junk/unknown/null) titles
  - helps identify patterns: modern AI titles, SaaS ops, ISP engineering, etc.

Usage:
  python scripts/diag_junk_titles_wikidata.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


TARGETS = [
    "Anysphere, Inc.",
    "Holywater Tech",
    "Sonic.net",
    "Xfinity",
    "Hostsharing eG",
    "Unikie",
    "Tidio",
    "Jotform",
    "Etheric Networks",
    "OCLC, Inc.",
    "Procedure Technologies",
]


def main():
    db = SessionLocal()
    rows = db.execute(text("""
        SELECT c.name AS company, r.role_title, r.functional_area
        FROM company_job_roles r
        JOIN companies c ON c.id = r.company_id
        WHERE c.name = ANY(:names)
          AND (r.functional_area IS NULL
               OR r.functional_area IN ('junk', 'unknown'))
        ORDER BY c.name, r.role_title
    """), {"names": TARGETS}).fetchall()

    by_company: dict[str, list] = defaultdict(list)
    all_titles = Counter()
    for r in rows:
        by_company[r.company].append((r.role_title, r.functional_area or "null"))
        all_titles[r.role_title.lower().strip()] += 1

    for company, titles in by_company.items():
        print(f"\n=== {company} ({len(titles)} unclassified) ===")
        for t, fa in titles[:25]:
            print(f"  [{fa:7s}] {t}")
        if len(titles) > 25:
            print(f"  ... +{len(titles) - 25} more")

    print(f"\n\n=== Top 40 title patterns across all targets ===")
    for title, cnt in all_titles.most_common(40):
        print(f"  {cnt:3d}x  {title}")

    db.close()


if __name__ == "__main__":
    main()

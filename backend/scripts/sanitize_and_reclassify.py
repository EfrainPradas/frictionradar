"""Sanitize polluted role_titles in DB and reclassify them.

Targets rows where role_title contains the gunk patterns from non-ATS
scrapers (interpunct separators, "Apply →" suffixes, dept-glued-to-title).

Does two things per affected role:
  1. Updates role_title = sanitize_title(role_title)
  2. Reclassifies via classify_title() — updates functional_area +
     functional_area_confidence

Usage:
  python scripts/sanitize_and_reclassify.py --dry-run   (default)
  python scripts/sanitize_and_reclassify.py --execute
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import or_

from app.db.session import SessionLocal
from app.models.company_job_role import CompanyJobRole
from app.services.role_ingest import sanitize_title, classify_title


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()

    # Candidates: titles with interpunct, "Apply" suffix, or suspicious length.
    candidates = db.query(CompanyJobRole).filter(
        or_(
            CompanyJobRole.role_title.like("%·%"),
            CompanyJobRole.role_title.like("%•%"),
            CompanyJobRole.role_title.ilike("%Apply →%"),
            CompanyJobRole.role_title.ilike("%Apply >%"),
        )
    ).all()

    print(f"Candidates (pattern-match): {len(candidates)}")

    before_area = Counter()
    after_area = Counter()
    title_changes = 0
    area_changes = 0
    sample = []

    for r in candidates:
        old_title = r.role_title
        old_area = r.functional_area
        before_area[old_area or "NULL"] += 1

        new_title = sanitize_title(old_title)
        if not new_title:
            continue

        if new_title != old_title:
            title_changes += 1

        new_area, new_conf = classify_title(new_title, r.role_description)
        after_area[new_area or "NULL"] += 1

        if new_area != old_area:
            area_changes += 1
            if len(sample) < 15:
                sample.append(
                    f"  [{(old_area or 'NULL'):8s} → {(new_area or 'NULL'):18s}] "
                    f"{old_title[:55]} => {new_title[:50]}"
                )

        if args.execute:
            r.role_title = new_title
            r.functional_area = new_area
            r.functional_area_confidence = new_conf

    print(f"\nTitles changed:  {title_changes}")
    print(f"Areas changed:   {area_changes}")

    print(f"\nBefore area distribution (polluted rows):")
    for a, c in before_area.most_common(15):
        print(f"  {a:20s} {c}")

    print(f"\nAfter area distribution (same rows, reclassified):")
    for a, c in after_area.most_common(15):
        print(f"  {a:20s} {c}")

    print(f"\nSample area transitions:")
    for line in sample:
        print(line)

    if not args.execute:
        print("\n[DRY RUN] No changes. Re-run with --execute to apply.")
        db.close()
        return

    db.commit()
    print(f"\nCommitted changes to {len(candidates)} rows.")
    db.close()


if __name__ == "__main__":
    main()

"""Reclassify only rows currently marked junk/unknown/null.

Faster than full reclassify — only touches rows the current classifier
failed on, giving new keyword rules a chance to pick them up without
rewriting 25K+ already-correct rows.

Usage:
  python scripts/reclassify_unknowns.py --dry-run
  python scripts/reclassify_unknowns.py --execute
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
from app.services.role_ingest import classify_title


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()

    candidates = db.query(CompanyJobRole).filter(
        or_(
            CompanyJobRole.functional_area.is_(None),
            CompanyJobRole.functional_area == "junk",
            CompanyJobRole.functional_area == "unknown",
        )
    ).all()

    print(f"Candidates (current junk/unknown/null): {len(candidates)}")

    before = Counter()
    after = Counter()
    changes = 0
    sample = []

    for r in candidates:
        before[r.functional_area or "NULL"] += 1
        new_area, new_conf = classify_title(r.role_title, r.role_description)
        after[new_area or "NULL"] += 1

        if new_area != r.functional_area:
            changes += 1
            if (r.functional_area or "NULL") in ("junk", "unknown", "NULL") and new_area not in ("junk", "unknown", None):
                if len(sample) < 20:
                    sample.append(
                        f"  [{(r.functional_area or 'NULL'):8s} → {new_area:18s}] {r.role_title[:60]}"
                    )
            if args.execute:
                r.functional_area = new_area
                r.functional_area_confidence = new_conf

    print(f"\nRows changed: {changes}")
    print(f"\nBefore:")
    for a, c in before.most_common(10):
        print(f"  {a:20s} {c}")
    print(f"\nAfter:")
    for a, c in after.most_common(10):
        print(f"  {a:20s} {c}")

    print(f"\nSample promotions (junk/unknown → real):")
    for line in sample:
        print(line)

    if not args.execute:
        print("\n[DRY RUN] No changes. Re-run with --execute.")
        db.close()
        return

    db.commit()
    print(f"\nCommitted {changes} updates.")
    db.close()


if __name__ == "__main__":
    main()

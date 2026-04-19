"""
Integration smoke test for role_ingest.persist_job_role.

Proves that the centralized ingest helper:
  - Writes CompanyJobRole rows with canonical functional_area
  - Tags junk/invalid titles correctly at persistence time
  - Does NOT require a post-hoc reclassify to produce correct labels

Uses a real DB session with a real company_id, but rolls back — no data is
committed. Read scripts/reclassify_all_roles.py if you want to see how
the classifier performs on rows already in DB.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.role_ingest import persist_job_role
from app.models.company_job_role import CompanyJobRole


TEST_CASES = [
    # (raw_title, expected_area, note)
    ("Senior Software Engineer", "engineering", "classic SWE"),
    ("Flight Attendant", "transportation", "new family: transportation"),
    ("Community Pharmacist", "healthcare", "new family: healthcare"),
    ("Shift Leader", "food_service", "new family: food_service"),
    ("HVAC Technician", "trades", "new family: trades"),
    ("Data Analyst", "analytics", "data family (canonicalized)"),
    ("About Us", "junk", "dept label → junk"),
    ("Saved jobs (0)", "junk", "nav element → junk"),
    ("  ", None, "empty string → None (not persisted)"),
]


def main():
    db = SessionLocal()

    # Pick any real company_id so FK holds
    cid = db.execute(text("SELECT id FROM companies LIMIT 1")).scalar()
    if not cid:
        print("ERR: no companies in DB — cannot run integration test")
        return 1

    print(f"Using company_id={cid} (rolled back, no commit)\n")
    print(f"{'raw_title':40s}  {'expected':16s}  {'actual':16s}  "
          f"{'confidence':25s}  result")
    print("-" * 115)

    passes = 0
    fails = 0
    persisted = []

    for raw_title, expected, note in TEST_CASES:
        role = persist_job_role(
            db,
            company_id=cid,
            raw_title=raw_title,
            source_url="https://test.example/jobs/1",
        )

        if role is None:
            actual = "(not persisted)"
            confidence = "-"
        else:
            db.flush()  # assign ID, but don't commit
            persisted.append(role)
            actual = role.functional_area
            confidence = role.functional_area_confidence or "-"

        ok = (
            (expected is None and role is None)
            or (role is not None and actual == expected)
        )
        mark = "PASS" if ok else "FAIL"
        if ok:
            passes += 1
        else:
            fails += 1

        print(f"{raw_title!r:40s}  {str(expected):16s}  {actual:16s}  "
              f"{confidence:25s}  [{mark}] {note}")

    print("-" * 115)
    print(f"\n{passes} passed, {fails} failed. Rolling back.")
    db.rollback()
    db.close()
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

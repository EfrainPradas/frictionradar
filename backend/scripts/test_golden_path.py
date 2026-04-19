"""
Test 3 — Golden path end-to-end.

Runs the live collector (extract_careers_evidence → Playwright + hybrid
extractor → _persist_job_roles) on ONE company, then verifies the roles
were written with canonical functional_area values at first save, without
needing reclassify.

Pass: all persisted roles have functional_area in the canonical set
      (or 'junk'/'unknown'), NOT legacy Title-Case values from the old
      _extract_area path like 'Retail', 'Technology', 'Hr People'.

Usage:
    python scripts/test_golden_path.py <domain>
    python scripts/test_golden_path.py adventisthealthcare.com
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.collection_orchestrator import extract_careers_evidence
from app.services.role_ingest import CANONICAL


# Canonical functional_area values that should be persisted by the
# centralized helper. Anything outside this set (e.g. "Technology",
# "Hr People", "Retail") would indicate the old _extract_area path
# leaked through.
CANONICAL_AREAS = {
    # FUNCTION_KEYWORDS keys after _canonical() rename:
    "analytics", "finance", "operations", "supply_chain", "marketing",
    "sales", "customer_support", "product", "engineering", "hr",
    "recruiting", "legal", "manufacturing", "retail", "it",
    "healthcare", "hospitality", "education", "trades", "transportation",
    "food_service", "design",
    # Diagnostic labels — still acceptable, classifier emitted them:
    "junk", "unknown",
}


async def run_test(domain: str):
    db = SessionLocal()

    company = db.execute(text("""
        SELECT id, name, careers_url FROM companies WHERE domain = :d
    """), {"d": domain}).fetchone()

    if not company:
        print(f"ERR: no company found for domain={domain!r}")
        return 1

    company_id, name, careers_url = company
    print(f"Target: {name}  ({domain})  company_id={company_id}")
    print(f"Known careers_url: {careers_url or '(none, will discover)'}\n")

    # Snapshot role count before
    before_count = db.execute(text("""
        SELECT COUNT(*) FROM company_job_roles WHERE company_id = :cid
    """), {"cid": company_id}).scalar()
    print(f"Roles before: {before_count}\n")

    print("Running extract_careers_evidence (live, up to 60s)...")
    try:
        result = await extract_careers_evidence(
            db, company_id, domain, known_careers_url=careers_url
        )
        print(f"Extraction returned: {result}")
    except Exception as exc:
        print(f"ERR: extraction raised {type(exc).__name__}: {exc}")
        db.close()
        return 2

    # Re-open a fresh session to read what was committed by the orchestrator
    db.close()
    db = SessionLocal()

    after_rows = db.execute(text("""
        SELECT role_title, functional_area, functional_area_confidence
        FROM company_job_roles
        WHERE company_id = :cid
        ORDER BY discovered_at DESC
        LIMIT 30
    """), {"cid": company_id}).fetchall()

    print(f"\nRoles after: {len(after_rows)}\n")
    if not after_rows:
        print("(no roles persisted — collector may have failed or page had no jobs)")
        db.close()
        return 3

    print(f"{'functional_area':20s}  {'confidence':25s}  role_title")
    print("-" * 110)
    non_canonical = []
    for title, area, conf in after_rows:
        flag = "" if area in CANONICAL_AREAS else "  *** NON-CANONICAL ***"
        print(f"{(area or 'NULL'):20s}  {(conf or '-'):25s}  {title[:55]}{flag}")
        if area not in CANONICAL_AREAS:
            non_canonical.append((title, area))

    db.close()

    print("\n" + "=" * 60)
    if non_canonical:
        print(f"FAIL: {len(non_canonical)} roles persisted with non-canonical "
              f"functional_area:")
        for t, a in non_canonical:
            print(f"  {a!r:20s}  {t}")
        return 4

    print(f"PASS: all {len(after_rows)} roles have canonical functional_area.")
    print("      Classifier ran at ingest time — no reclassify needed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_golden_path.py <domain>")
        sys.exit(1)
    domain = sys.argv[1]
    sys.exit(asyncio.run(run_test(domain)))

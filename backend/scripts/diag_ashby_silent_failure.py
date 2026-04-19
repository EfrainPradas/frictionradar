"""Diagnose why 693 Ashby-detected companies have 0 roles persisted.

Distinguishes three failure modes:
  (a) Extraction never ran (batch_runner path was skipped). Signature:
      ashby_board_detected exists but NO signal with source_type='extraction_ats_api'.
  (b) Extraction ran but AshbyAdapter failed (slug / GraphQL error). Signature:
      some ats_api signals exist on the company but 0 job_cards and 0 roles.
  (c) Adapter worked but role persistence failed. Signature:
      source_type='extraction_ats_api' + job_cards_visible_detected signal + 0 roles.

Also picks 3 sample Ashby companies, tries the adapter live, and prints results.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.extraction.adapters import ATS_ADAPTERS
from app.extraction.constants import ATSPlatform


def main():
    db = SessionLocal()

    print("=" * 78)
    print("ASHBY SILENT FAILURE DIAGNOSIS")
    print("=" * 78)

    # 1. Universe — companies with ashby detected
    total_ashby = db.execute(text("""
        SELECT COUNT(DISTINCT c.id)
        FROM companies c
        JOIN company_signals s ON s.company_id = c.id
        WHERE s.signal_type = 'ashby_board_detected'
    """)).scalar()
    print(f"\nTotal companies with ashby_board_detected: {total_ashby}")

    # 2. Of those, how many have any extraction_ats_api signal?
    ran_extraction = db.execute(text("""
        SELECT COUNT(DISTINCT c.id)
        FROM companies c
        JOIN company_signals s1 ON s1.company_id = c.id
          AND s1.signal_type = 'ashby_board_detected'
        WHERE EXISTS (
            SELECT 1 FROM company_signals s2
            WHERE s2.company_id = c.id
              AND s2.source_type LIKE 'extraction_%'
        )
    """)).scalar()
    print(f"  … that also ran extract_company (any extraction_* source): {ran_extraction}")

    ran_ats_api = db.execute(text("""
        SELECT COUNT(DISTINCT c.id)
        FROM companies c
        JOIN company_signals s1 ON s1.company_id = c.id
          AND s1.signal_type = 'ashby_board_detected'
        WHERE EXISTS (
            SELECT 1 FROM company_signals s2
            WHERE s2.company_id = c.id
              AND s2.source_type = 'extraction_ats_api'
        )
    """)).scalar()
    print(f"  … that reached ATS_API strategy specifically: {ran_ats_api}")

    # 3. Of those that ran ATS_API, how many have job_cards_visible_detected from that source?
    got_jobs = db.execute(text("""
        SELECT COUNT(DISTINCT c.id)
        FROM companies c
        JOIN company_signals s ON s.company_id = c.id
        WHERE s.source_type = 'extraction_ats_api'
          AND s.signal_type = 'job_cards_visible_detected'
          AND EXISTS (
            SELECT 1 FROM company_signals s2
            WHERE s2.company_id = c.id AND s2.signal_type = 'ashby_board_detected'
          )
    """)).scalar()
    print(f"  … that got job_cards_visible_detected via ATS_API: {got_jobs}")

    # 4. Of those, how many have roles persisted?
    got_roles = db.execute(text("""
        SELECT COUNT(DISTINCT c.id)
        FROM companies c
        JOIN company_signals s ON s.company_id = c.id
          AND s.signal_type = 'ashby_board_detected'
        WHERE EXISTS (
            SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id
        )
    """)).scalar()
    print(f"  … with at least 1 role in company_job_roles: {got_roles}")

    # 5. Bucketing
    print("\n" + "-" * 78)
    print("FAILURE MODE BUCKETING")
    print("-" * 78)
    never_extracted = total_ashby - ran_extraction
    print(f"  (a) Never ran extract_company:       {never_extracted:>4d}  "
          f"<- collection_orchestrator only, no batch_runner")
    extraction_ran_no_ats = ran_extraction - ran_ats_api
    print(f"  (b) Ran extraction, ATS_API skipped: {extraction_ran_no_ats:>4d}  "
          f"<- dispatcher fell through to HTTP/Playwright")
    ats_ran_no_jobs = ran_ats_api - got_jobs
    print(f"  (c) ATS_API ran but 0 jobs returned: {ats_ran_no_jobs:>4d}  "
          f"<- adapter failed (slug/GraphQL)")
    jobs_no_roles = got_jobs - got_roles
    print(f"  (d) Jobs detected but 0 roles saved: {jobs_no_roles:>4d}  "
          f"<- persistence path broken")
    print(f"  (e) Healthy (ATS_API -> jobs -> roles): {got_roles:>4d}")

    # 6. Sample 3 Ashby companies and try the adapter live
    print("\n" + "=" * 78)
    print("LIVE ADAPTER TEST (3 random Ashby companies with 0 roles)")
    print("=" * 78)

    samples = db.execute(text("""
        SELECT c.id, c.name, c.domain
        FROM companies c
        JOIN company_signals s ON s.company_id = c.id
          AND s.signal_type = 'ashby_board_detected'
        LEFT JOIN company_job_roles r ON r.company_id = c.id
        WHERE r.id IS NULL
        GROUP BY c.id, c.name, c.domain
        ORDER BY random()
        LIMIT 3
    """)).fetchall()

    adapter = ATS_ADAPTERS[ATSPlatform.ASHBY]
    for row in samples:
        company_id, name, domain = row
        print(f"\n── {name} ({domain}) ──")
        try:
            result = adapter.extract(
                domain=domain,
                company_name=name,
            )
            print(f"  success:          {result.success}")
            print(f"  strategy:         {result.strategy_used.value if result.strategy_used else 'n/a'}")
            print(f"  reason_code:      {result.reason_code.value if result.reason_code else 'n/a'}")
            print(f"  jobs_count:       {result.jobs_count}")
            print(f"  careers_url:      {result.careers_url}")
            print(f"  error:            {result.error}")
            if result.jobs:
                print(f"  sample titles:")
                for j in result.jobs[:5]:
                    print(f"    - {j.title[:60]:60s} [{j.location or 'n/a'}]")
        except Exception as e:
            print(f"  EXCEPTION: {type(e).__name__}: {e}")

    db.close()


if __name__ == "__main__":
    main()

"""Trace extract_company() for 5 known silent-failure companies and
dump the NormalizedJobsResult contents (jobs, titles, URLs) to see
whether jobs come back with titles, whether persist_job_role would
have had valid input, etc.

Run:  python scripts/diag_f3a_extract_trace.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.extraction.dispatcher import extract_company


SAMPLES = [
    ("Angel Studios",         "angel.com",              None),
    ("Ally Bank",             "ally.com",               None),
    ("Alpine Air Express",    "alpine-air.com",         None),
    ("Antarctic Logistics",   "antarctic-logistics.com", None),
]


def main():
    db = SessionLocal()

    for name, domain, detected_ats in SAMPLES:
        print("=" * 100)
        print(f"[{name}] domain={domain}  detected_ats={detected_ats}")
        print("=" * 100)
        try:
            r = extract_company(
                domain=domain,
                company_name=name,
                detected_ats_platform=detected_ats,
                skip_playwright=False,
            )
        except Exception as e:
            print(f"   !! extract_company RAISED: {type(e).__name__}: {e}")
            continue

        print(f"  strategy_used  : {r.strategy_used.value}")
        print(f"  reason_code    : {r.reason_code.value}")
        print(f"  careers_url    : {r.careers_url}")
        print(f"  success        : {r.success}")
        print(f"  confidence     : {r.confidence}")
        print(f"  quality        : {r.evidence_quality}")
        print(f"  open_positions : {r.open_positions_count}")
        print(f"  jobs_count     : {r.jobs_count}")
        print(f"  hiring_areas   : {r.hiring_areas[:5]}")
        print(f"  error          : {r.error}")

        if r.jobs:
            print(f"  first 5 jobs:")
            for j in r.jobs[:5]:
                t = (j.title or "(NO TITLE)")[:70]
                u = (j.job_url or "")[:60]
                print(f"    title='{t}'  url={u}")
            nulls = sum(1 for j in r.jobs if not j.title)
            print(f"  jobs with NO title: {nulls}/{len(r.jobs)}")

    db.close()


if __name__ == "__main__":
    main()

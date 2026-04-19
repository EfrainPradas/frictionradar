"""
Test cohorte FL — corre collector + extractor sobre N empresas FL sin roles.

Valida que la centralización del ingest funcione sobre data nueva real, y
reporta KPIs de clasificación: classification rate, family distribution,
unknown/junk rate.

Sin arg: 20 empresas. Usa `--n 50` para más. Tiempo estimado: 30-60s por empresa.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.collection_orchestrator import extract_careers_evidence


def pick_fl_cohort(db, n: int) -> list[tuple]:
    rows = db.execute(text("""
        SELECT c.id, c.name, c.domain
        FROM companies c
        LEFT JOIN company_job_roles r ON r.company_id = c.id
        WHERE c.geography = 'FL'
          AND c.domain IS NOT NULL AND c.domain != ''
        GROUP BY c.id, c.name, c.domain
        HAVING COUNT(r.id) = 0
        ORDER BY c.name
        LIMIT :n
    """), {"n": n}).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def count_roles(db, company_id) -> dict:
    rows = db.execute(text("""
        SELECT functional_area, COUNT(*)
        FROM company_job_roles
        WHERE company_id = :cid
        GROUP BY functional_area
    """), {"cid": company_id}).fetchall()
    return {r[0] or "NULL": r[1] for r in rows}


async def run_cohort(n: int):
    db = SessionLocal()
    cohort = pick_fl_cohort(db, n)
    db.close()

    print(f"=" * 78)
    print(f"FL COHORT TEST — {len(cohort)} companies without roles")
    print(f"=" * 78)

    t0 = time.monotonic()
    aggregate = Counter()
    per_company_summary = []
    errors = 0
    any_roles_count = 0

    for i, (cid, name, domain) in enumerate(cohort, 1):
        elapsed = time.monotonic() - t0
        print(f"\n[{i}/{len(cohort)}] ({elapsed:.0f}s) {name[:35]:35s} {domain}")

        db = SessionLocal()
        try:
            result = await extract_careers_evidence(db, cid, domain)
            db.close()
        except Exception as exc:
            errors += 1
            print(f"  ERR: {type(exc).__name__}: {exc}")
            db.close()
            continue

        db = SessionLocal()
        dist = count_roles(db, cid)
        db.close()

        total = sum(dist.values())
        classified = sum(v for k, v in dist.items()
                         if k not in ("junk", "unknown", "NULL"))
        if total > 0:
            any_roles_count += 1

        for area, cnt in dist.items():
            aggregate[area] += cnt

        per_company_summary.append({
            "name": name,
            "domain": domain,
            "total": total,
            "classified": classified,
            "dist": dist,
        })

        print(f"  -> open_positions_signal={result}  roles_persisted={total}  "
              f"classified={classified}")
        if dist:
            top3 = sorted(dist.items(), key=lambda x: -x[1])[:3]
            print(f"     top: {', '.join(f'{k}={v}' for k, v in top3)}")

    elapsed = time.monotonic() - t0
    total_roles = sum(aggregate.values())
    classified_total = sum(v for k, v in aggregate.items()
                           if k not in ("junk", "unknown", "NULL"))
    junk_total = aggregate.get("junk", 0)
    unknown_total = aggregate.get("unknown", 0)

    print(f"\n{'=' * 78}")
    print(f"COHORT SUMMARY ({elapsed:.0f}s, errors={errors})")
    print(f"{'=' * 78}")
    print(f"  Companies with ≥1 role: {any_roles_count}/{len(cohort)} "
          f"({any_roles_count/max(len(cohort),1):.0%})")
    print(f"  Total roles persisted:  {total_roles}")
    print(f"  Classified:             {classified_total} "
          f"({classified_total/max(total_roles,1):.0%})")
    print(f"  Junk:                   {junk_total} "
          f"({junk_total/max(total_roles,1):.0%})")
    print(f"  Unknown:                {unknown_total} "
          f"({unknown_total/max(total_roles,1):.0%})")

    print(f"\n  Family distribution (aggregate):")
    for fam, cnt in sorted(aggregate.items(), key=lambda x: -x[1]):
        if fam in ("junk", "unknown", "NULL"):
            continue
        print(f"    {fam:22s} {cnt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20,
                    help="Number of FL companies to process (default 20)")
    args = ap.parse_args()
    asyncio.run(run_cohort(args.n))


if __name__ == "__main__":
    main()

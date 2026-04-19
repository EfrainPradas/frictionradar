"""Recompute the funnel snapshot WITHOUT reclassifying roles.

Validates Fix A (counter) + Fix B (default type_confidence=MODERATE) against
the persisted DB state. This does NOT modify any rows — it only re-evaluates
each company with the current code and reports the new eligibility counts.

Usage:
  python scripts/recompute_funnel_snapshot.py [--out RUN_ID]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.services.company_evaluation import CompanyEvaluationEngine
from app.services.positioning_engine import ELIGIBLE_DS, check_eligibility

eval_engine = CompanyEvaluationEngine()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="Optional run_id to write summary under runs/")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    companies = db.query(Company).all()
    print(f"Evaluating {len(companies)} companies...")

    ds_counts = Counter()
    eligible_full = 0
    eligible_conditional = 0
    eligible_sample_full = []
    eligible_sample_conditional = []
    errors = 0

    # Preload classified counts per company for the conditional gate.
    classified_rows = (
        db.query(CompanyJobRole.company_id, CompanyJobRole.functional_area)
        .filter(
            CompanyJobRole.functional_area.isnot(None),
            ~CompanyJobRole.functional_area.in_(["junk", "unknown"]),
        )
        .all()
    )
    classified_by_company: dict = {}
    counts_by_company: dict = {}
    for cid, area in classified_rows:
        classified_by_company.setdefault(cid, Counter())[area] += 1
    for cid, counter in classified_by_company.items():
        total = sum(counter.values())
        top = max(counter.values()) if counter else 0
        counts_by_company[cid] = {
            "total": total,
            "top_share": (top / total) if total else 0,
        }

    # JD count (for check_eligibility confidence_band).
    jd_counts: dict = {}
    for cid, role_desc in (
        db.query(CompanyJobRole.company_id, CompanyJobRole.role_description).all()
    ):
        if role_desc:
            jd_counts[cid] = jd_counts.get(cid, 0) + 1

    for i, c in enumerate(companies, 1):
        try:
            ev = eval_engine.evaluate(company_id=c.id, db=db)
            ds = ev.get("diagnostic_state", "")
            kpis = ev.get("kpis", {})
        except Exception as e:
            ds = f"error:{type(e).__name__}"
            kpis = {}
            errors += 1
            db.rollback()
        ds_counts[ds] += 1

        stats = counts_by_company.get(c.id, {"total": 0, "top_share": 0})
        # Use the engine's own eligibility check — single source of truth.
        # This prevents the snapshot from counting companies the engine
        # would later reject (e.g. specific_pain_emerging with classified<3).
        elig = check_eligibility(
            diagnostic_state=ds,
            pain_clarity=kpis.get("pain_clarity", "low"),
            function_concentration=kpis.get("function_concentration", "low"),
            positioning_readiness=kpis.get("positioning_readiness", "low"),
            classified_roles=stats["total"],
            jds_extracted=jd_counts.get(c.id, 0),
        )
        if elig.eligible:
            if elig.gate_passed == "full":
                eligible_full += 1
                if len(eligible_sample_full) < 15:
                    eligible_sample_full.append(
                        (c.name, ds, stats["total"], round(stats["top_share"], 2))
                    )
            elif elig.gate_passed == "conditional":
                eligible_conditional += 1
                if len(eligible_sample_conditional) < 15:
                    eligible_sample_conditional.append(
                        (c.name, ds, stats["total"], round(stats["top_share"], 2))
                    )

        if args.verbose and i % 200 == 0:
            print(f"  [{i}/{len(companies)}] so far: full={eligible_full} cond={eligible_conditional}")

    total = len(companies)
    print()
    print("=" * 70)
    print("FUNNEL SNAPSHOT (no reclassification)")
    print("=" * 70)
    print(f"Total companies evaluated: {total}  (errors: {errors})")
    print()
    print("Diagnostic state distribution:")
    for ds, count in ds_counts.most_common():
        pct = count / total * 100 if total else 0
        print(f"  {ds:40s}  {count:5d}  ({pct:5.1f}%)")

    print()
    print("Eligibility (new counter logic):")
    print(f"  Full gate (ready + specific_pain_*):   {eligible_full}")
    print(f"  Conditional (broad + classified>=5 +")
    print(f"               top_share>=0.35):          {eligible_conditional}")
    print(f"  TOTAL ELIGIBLE (full + conditional):   {eligible_full + eligible_conditional}")

    print()
    print("Sample — FULL gate (first 15):")
    for name, ds, total_c, share in eligible_sample_full:
        print(f"  {(name or '')[:30]:30s}  {ds:28s}  roles={total_c:3d}  top_share={share}")

    print()
    print("Sample — CONDITIONAL gate (first 15):")
    for name, ds, total_c, share in eligible_sample_conditional:
        print(f"  {(name or '')[:30]:30s}  {ds:28s}  roles={total_c:3d}  top_share={share}")

    # Optionally write summary
    if args.out:
        out_dir = Path(__file__).resolve().parents[1] / "runs" / args.out
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_companies": total,
            "errors": errors,
            "diagnostic_state_distribution": dict(ds_counts),
            "eligible_positioning_full": eligible_full,
            "eligible_positioning_conditional": eligible_conditional,
            "eligible_positioning_total": eligible_full + eligible_conditional,
            "sample_full": eligible_sample_full,
            "sample_conditional": eligible_sample_conditional,
        }
        (out_dir / "funnel_snapshot.json").write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nWrote runs/{args.out}/funnel_snapshot.json")

    db.close()


if __name__ == "__main__":
    main()

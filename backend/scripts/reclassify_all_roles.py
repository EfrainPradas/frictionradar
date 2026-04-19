"""Reclassify all CompanyJobRole records with the current classifier.

Applies Fix C (word boundaries) + D (inside_ removed) + E (keyword gaps)
+ F (reason codes) to the persisted DB state — without re-running
extraction or JD scraping.

Usage:
  python scripts/reclassify_all_roles.py --limit 100    # small test
  python scripts/reclassify_all_roles.py                # full dataset
  python scripts/reclassify_all_roles.py --dry-run      # preview, no writes

It iterates companies, calls compute_hiring_pattern (which classifies +
aggregates + persists signals), and reports before/after distributions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.services.function_inference_engine import function_inference_engine
from app.services.hiring_pattern_service import compute_hiring_pattern


def snapshot_distribution(db) -> dict:
    """Snapshot current functional_area distribution across all roles."""
    rows = (
        db.query(CompanyJobRole.functional_area, func.count(CompanyJobRole.id))
        .group_by(CompanyJobRole.functional_area)
        .all()
    )
    return {(area or "NULL"): count for area, count in rows}


def dry_run_preview(db, limit: int):
    """Preview what reclassification would do — no writes."""
    roles = db.query(CompanyJobRole).limit(limit * 20).all() if limit else db.query(CompanyJobRole).all()
    before_areas = Counter()
    after_areas = Counter()
    reason_codes = Counter()
    changed = 0

    for r in roles:
        before_areas[r.functional_area or "NULL"] += 1
        result = function_inference_engine.infer_functional_area(
            r.role_title, r.role_description
        )
        new_area = result["area"]
        # Mirror _canonical() from hiring_pattern_service
        canonical_map = {
            "data_analytics": "analytics", "hr_people": "hr",
            "customer_success": "customer_support",
            "recruiting_talent": "recruiting", "legal_compliance": "legal",
        }
        new_area_canon = canonical_map.get(new_area, new_area)
        after_areas[new_area_canon] += 1
        reason_codes[result.get("reason_code") or "unspecified"] += 1
        if (r.functional_area or "NULL") != new_area_canon:
            changed += 1

    print(f"\nDRY RUN — evaluated {len(roles)} roles, no writes.")
    print(f"Would change: {changed} roles")
    print("\nBefore → After distribution:")
    all_keys = sorted(set(list(before_areas.keys()) + list(after_areas.keys())))
    for k in all_keys:
        b = before_areas.get(k, 0)
        a = after_areas.get(k, 0)
        delta = a - b
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else " ")
        print(f"  {k:20s}  {b:5d} → {a:5d}  {arrow} {delta:+d}")
    print("\nReason code distribution (after):")
    for k, v in reason_codes.most_common():
        print(f"  {k:30s}  {v}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="Max companies to reclassify (omit = all)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview changes, no DB writes")
    ap.add_argument("--label", default=None,
                    help="Tag for the run summary file")
    args = ap.parse_args()

    db = SessionLocal()

    print("=" * 70)
    print("BEFORE — current functional_area distribution")
    print("=" * 70)
    before_dist = snapshot_distribution(db)
    total_roles = sum(before_dist.values())
    for area, count in sorted(before_dist.items(), key=lambda x: -x[1]):
        pct = count / total_roles * 100 if total_roles else 0
        print(f"  {area:20s}  {count:5d}  ({pct:5.1f}%)")
    print(f"  {'TOTAL':20s}  {total_roles}")

    if args.dry_run:
        dry_run_preview(db, args.limit or 0)
        db.close()
        return

    # Pick target companies (those with at least one role)
    q = (
        db.query(Company.id, Company.name)
        .join(CompanyJobRole, CompanyJobRole.company_id == Company.id)
        .distinct()
        .order_by(Company.name)
    )
    if args.limit:
        q = q.limit(args.limit)
    companies = q.all()

    print()
    print("=" * 70)
    print(f"RECLASSIFYING {len(companies)} companies "
          f"(limit={args.limit or 'all'})")
    print("=" * 70)

    t0 = time.monotonic()
    aggregated_reasons: Counter = Counter()
    companies_done = 0
    errors = 0

    for cid, name in companies:
        try:
            result = compute_hiring_pattern(cid, db)
            for reason, count in (result.get("classification", {}).get("reason_counts") or {}).items():
                aggregated_reasons[reason] += count
            companies_done += 1
        except Exception as e:
            errors += 1
            db.rollback()
            print(f"  [ERR] {name}: {type(e).__name__}: {e}")
            continue

        if companies_done % 50 == 0:
            elapsed = time.monotonic() - t0
            rate = companies_done / elapsed if elapsed else 0
            eta = (len(companies) - companies_done) / rate if rate else 0
            print(f"  [{companies_done}/{len(companies)}] "
                  f"elapsed={elapsed:.0f}s  rate={rate:.1f}/s  eta={eta:.0f}s")

    elapsed = time.monotonic() - t0
    print()
    print("=" * 70)
    print(f"DONE — {companies_done} companies reclassified in {elapsed:.1f}s "
          f"(errors: {errors})")
    print("=" * 70)

    print("\nReason codes across all reclassified roles:")
    for reason, count in aggregated_reasons.most_common():
        print(f"  {reason:35s}  {count}")

    print()
    print("AFTER — new functional_area distribution")
    print("-" * 70)
    after_dist = snapshot_distribution(db)
    total_after = sum(after_dist.values())
    all_keys = sorted(set(list(before_dist.keys()) + list(after_dist.keys())))
    for k in all_keys:
        b = before_dist.get(k, 0)
        a = after_dist.get(k, 0)
        delta = a - b
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else " ")
        pct = a / total_after * 100 if total_after else 0
        print(f"  {k:20s}  {b:5d} → {a:5d}  ({pct:5.1f}%)  {arrow} {delta:+d}")

    # Write summary
    label = args.label or (f"reclassify_{args.limit}" if args.limit else "reclassify_full")
    out_dir = Path(__file__).resolve().parents[1] / "runs" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limit": args.limit,
        "companies_reclassified": companies_done,
        "errors": errors,
        "elapsed_sec": round(elapsed, 1),
        "before_distribution": before_dist,
        "after_distribution": after_dist,
        "reason_codes": dict(aggregated_reasons),
    }
    (out_dir / "reclassify_summary.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )
    print(f"\nWrote runs/{label}/reclassify_summary.json")

    db.close()


if __name__ == "__main__":
    main()

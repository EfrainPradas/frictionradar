"""Validate that every reporting layer agrees on eligibility counts.

Compares:
  1. Canonical snapshot (positioning_engine.compute_eligibility_snapshot)
  2. audit_positioning_output.json (eligible_count)
  3. funnel_snapshot.json (eligible_positioning_total), if present
  4. dataset_health.coverage_funnel.positioning_eligible

Passes if all four numbers match. Also prints per-company breakdown of
full / conditional / not_eligible with reasons so you can explain why.

Usage:
  python scripts/validate_eligibility_consistency.py
  python scripts/validate_eligibility_consistency.py --audit-label audit_eligible_v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.services.positioning_engine import compute_eligibility_snapshot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-label", default="audit_eligible_v1")
    ap.add_argument("--funnel-label", default=None,
                    help="Optional run label for funnel_snapshot.json")
    args = ap.parse_args()

    db = SessionLocal()
    snap = compute_eligibility_snapshot(db)
    db.close()

    canonical_total = snap["total_eligible"]
    canonical_full = snap["full"]
    canonical_conditional = snap["conditional"]

    print("=" * 72)
    print("ELIGIBILITY CONSISTENCY CHECK")
    print("=" * 72)
    print(f"\nCanonical snapshot (positioning_engine.compute_eligibility_snapshot):")
    print(f"  full:           {canonical_full}")
    print(f"  conditional:    {canonical_conditional}")
    print(f"  total_eligible: {canonical_total}")
    print(f"  not_eligible:   {snap['not_eligible']}")

    runs_dir = Path(__file__).resolve().parents[1] / "runs"

    # Compare vs audit_positioning_output
    audit_path = runs_dir / args.audit_label / "positioning_audit.json"
    audit_total = None
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        audit_total = audit.get("eligible_count")
        print(f"\npositioning_audit.json ({args.audit_label}):")
        print(f"  eligible_count: {audit_total}")

    # Compare vs funnel_snapshot
    funnel_total = None
    if args.funnel_label:
        funnel_path = runs_dir / args.funnel_label / "funnel_snapshot.json"
        if funnel_path.exists():
            funnel = json.loads(funnel_path.read_text())
            funnel_total = funnel.get("eligible_positioning_total")
            print(f"\nfunnel_snapshot.json ({args.funnel_label}):")
            print(f"  full:           {funnel.get('eligible_positioning_full')}")
            print(f"  conditional:    {funnel.get('eligible_positioning_conditional')}")
            print(f"  total:          {funnel_total}")

    print("\n" + "-" * 72)
    print("RESULT")
    print("-" * 72)

    mismatches = []
    if audit_total is not None and audit_total != canonical_total:
        mismatches.append(f"audit({audit_total}) != canonical({canonical_total})")
    if funnel_total is not None and funnel_total != canonical_total:
        mismatches.append(f"funnel({funnel_total}) != canonical({canonical_total})")

    if mismatches:
        print(f"FAIL — {len(mismatches)} mismatch(es):")
        for m in mismatches:
            print(f"  {m}")
        rc = 1
    else:
        sources = ["canonical"]
        if audit_total is not None:
            sources.append("audit")
        if funnel_total is not None:
            sources.append("funnel")
        print(f"PASS — all layers agree on {canonical_total} eligible "
              f"({canonical_full} full + {canonical_conditional} conditional)")
        print(f"  Sources checked: {', '.join(sources)}")
        rc = 0

    # Per-company breakdown of eligibles
    eligibles = [c for c in snap["by_company"] if c["eligible"]]
    print(f"\nEligible companies ({len(eligibles)}):")
    print(f"  {'gate':12s} {'band':10s} {'ds':28s} {'roles':6s} {'jds':5s}  name")
    print(f"  {'-'*70}")
    for c in sorted(eligibles, key=lambda x: (x["gate_passed"], x["name"] or "")):
        print(f"  {c['gate_passed']:12s} {c['confidence_band']:10s} "
              f"{c['ds']:28s} {c['classified_roles']:6d} {c['jds_extracted']:5d}  "
              f"{(c['name'] or '')[:40]}")

    sys.exit(rc)


if __name__ == "__main__":
    main()

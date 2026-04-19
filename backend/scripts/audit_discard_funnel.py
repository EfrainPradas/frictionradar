"""Discard funnel audit — why are we dropping 1257/1292 companies?

Uses the canonical eligibility snapshot and cross-references with upstream
state (domain, collection, roles, signals) to bucket every non-eligible
company into the exact stage where it got filtered out.

Output: a funnel from total → eligible, with segmentation by geography
and dataset_status so you can tell if the low rate is gate-strictness or
denominator contamination.

Usage:
  python scripts/audit_discard_funnel.py
  python scripts/audit_discard_funnel.py --segment geography
  python scripts/audit_discard_funnel.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.positioning_engine import compute_eligibility_snapshot


# Discard buckets (ordered — a company is assigned to the FIRST matching one)
STAGES = [
    "0_no_domain",
    "1_domain_no_collection",
    "2_collected_no_roles",
    "3_roles_but_all_junk_unknown",
    "4_ds_insufficient_evidence",
    "5_ds_broad_classified_lt_5",
    "6_ds_broad_concentration_low",
    "7_ds_specific_emerging_classified_lt_3",
    "8_error_in_evaluation",
    "ELIGIBLE_full",
    "ELIGIBLE_conditional",
]

STAGE_LABEL = {
    "0_no_domain":                             "No domain on record (shell company)",
    "1_domain_no_collection":                  "Domain exists but never collected",
    "2_collected_no_roles":                    "Collected but 0 roles extracted",
    "3_roles_but_all_junk_unknown":            "Roles extracted but 0 classified",
    "4_ds_insufficient_evidence":              "DS=insufficient_evidence (no hiring pattern)",
    "5_ds_broad_classified_lt_5":              "DS=broad_hiring + classified<5",
    "6_ds_broad_concentration_low":            "DS=broad_hiring + concentration=low",
    "7_ds_specific_emerging_classified_lt_3":  "DS=specific_pain_emerging + classified<3",
    "8_error_in_evaluation":                   "Evaluation engine errored",
    "ELIGIBLE_full":                           "Eligible — full gate",
    "ELIGIBLE_conditional":                    "Eligible — conditional gate",
}


def load_upstream_state(db) -> dict:
    """Load per-company upstream booleans: has_domain, collected, has_roles,
    has_classified, geography, dataset_status."""
    rows = db.execute(text("""
        SELECT c.id,
               COALESCE(c.geography, 'unknown') as geo,
               COALESCE(c.dataset_status, 'null') as ds_status,
               (c.domain IS NOT NULL AND c.domain != '') as has_domain,
               (c.last_collection_at IS NOT NULL) as collected,
               (SELECT COUNT(*) FROM company_job_roles r WHERE r.company_id = c.id) as total_roles,
               (SELECT COUNT(*) FROM company_job_roles r
                WHERE r.company_id = c.id
                  AND r.functional_area IS NOT NULL
                  AND r.functional_area NOT IN ('junk', 'unknown')
               ) as classified_roles
        FROM companies c
    """)).fetchall()
    return {r[0]: {
        "geography": r[1],
        "dataset_status": r[2],
        "has_domain": bool(r[3]),
        "collected": bool(r[4]),
        "total_roles": r[5] or 0,
        "classified_roles": r[6] or 0,
    } for r in rows}


def classify_discard(company_elig: dict, upstream: dict) -> str:
    """Assign a company to its first matching discard bucket."""

    # Eligible — done
    if company_elig["eligible"]:
        return f"ELIGIBLE_{company_elig['gate_passed']}"

    # Upstream filters
    if not upstream["has_domain"]:
        return "0_no_domain"
    if not upstream["collected"]:
        return "1_domain_no_collection"
    if upstream["total_roles"] == 0:
        return "2_collected_no_roles"
    if upstream["classified_roles"] == 0:
        return "3_roles_but_all_junk_unknown"

    # DS-based filters
    ds = company_elig["ds"]
    classified = upstream["classified_roles"]

    if ds.startswith("error:"):
        return "8_error_in_evaluation"
    if ds == "insufficient_evidence":
        return "4_ds_insufficient_evidence"
    if ds == "broad_hiring_pattern_detected":
        if classified < 5:
            return "5_ds_broad_classified_lt_5"
        # must be concentration=low since gate failed and classified>=5
        return "6_ds_broad_concentration_low"
    if ds == "specific_pain_emerging":
        return "7_ds_specific_emerging_classified_lt_3"

    # Fallback — should be rare
    return "8_error_in_evaluation"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segment", choices=["geography", "dataset_status"],
                    default=None,
                    help="Break down the funnel by this dimension")
    ap.add_argument("--samples", type=int, default=5,
                    help="Names to show per discard bucket")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    print("Loading canonical eligibility snapshot (~1 min for 1.3k companies)...")
    snap = compute_eligibility_snapshot(db)
    print("Loading upstream state...")
    upstream = load_upstream_state(db)
    db.close()

    total = len(snap["by_company"])
    stage_counts: Counter = Counter()
    stage_samples: dict = defaultdict(list)
    segment_counts: dict = defaultdict(lambda: Counter())

    for c in snap["by_company"]:
        up = upstream.get(c["company_id"])
        if not up:
            continue
        stage = classify_discard(c, up)
        stage_counts[stage] += 1
        if len(stage_samples[stage]) < args.samples:
            stage_samples[stage].append({
                "name": c["name"],
                "ds": c["ds"],
                "classified": up["classified_roles"],
                "jds": c["jds_extracted"],
                "geography": up["geography"],
                "dataset_status": up["dataset_status"],
            })
        if args.segment:
            key = up[args.segment]
            segment_counts[key][stage] += 1

    if args.json:
        payload = {
            "total": total,
            "stage_counts": {s: stage_counts.get(s, 0) for s in STAGES},
            "samples": dict(stage_samples),
            "segments": {k: dict(v) for k, v in segment_counts.items()},
        }
        print(json.dumps(payload, indent=2, default=str))
        return

    # Human-readable funnel
    print()
    print("=" * 88)
    print(f"DISCARD FUNNEL — {total} companies total")
    print("=" * 88)
    print()
    print(f"{'bucket':50s} {'count':>7s} {'pct':>7s}")
    print("-" * 88)

    cumulative_dropped = 0
    for stage in STAGES:
        n = stage_counts.get(stage, 0)
        pct = n / total * 100 if total else 0
        label = STAGE_LABEL[stage]
        if stage.startswith("ELIGIBLE"):
            print()
            print(f"  {label:48s} {n:>7d} {pct:>6.1f}%")
        else:
            cumulative_dropped += n
            print(f"  {label:48s} {n:>7d} {pct:>6.1f}%")

    eligible_full = stage_counts.get("ELIGIBLE_full", 0)
    eligible_cond = stage_counts.get("ELIGIBLE_conditional", 0)
    print()
    print("-" * 88)
    print(f"  {'Discarded total':48s} {cumulative_dropped:>7d} "
          f"{cumulative_dropped/max(total,1)*100:>6.1f}%")
    print(f"  {'Eligible total':48s} {eligible_full+eligible_cond:>7d} "
          f"{(eligible_full+eligible_cond)/max(total,1)*100:>6.1f}%")

    # Segment breakdown
    if args.segment and segment_counts:
        print()
        print("=" * 88)
        print(f"FUNNEL BY {args.segment.upper()}")
        print("=" * 88)
        # Sort segments by total company count desc
        segments_sorted = sorted(
            segment_counts.items(),
            key=lambda kv: -sum(kv[1].values()),
        )
        print()
        header = f"{'segment':20s} {'total':>6s} " + " ".join(
            f"{s[:14]:>14s}" for s in [
                "no_domain", "no_collect", "no_roles", "all_junk",
                "ds_insuff", "broad<5", "broad_lo", "spec<3", "eligible",
            ])
        print(header)
        print("-" * len(header))
        for seg_name, counts in segments_sorted:
            seg_total = sum(counts.values())
            eligible_here = (counts.get("ELIGIBLE_full", 0)
                             + counts.get("ELIGIBLE_conditional", 0))
            elig_pct = eligible_here / max(seg_total, 1) * 100
            row = [
                f"{seg_name[:20]:20s}",
                f"{seg_total:>6d}",
                f"{counts.get('0_no_domain', 0):>14d}",
                f"{counts.get('1_domain_no_collection', 0):>14d}",
                f"{counts.get('2_collected_no_roles', 0):>14d}",
                f"{counts.get('3_roles_but_all_junk_unknown', 0):>14d}",
                f"{counts.get('4_ds_insufficient_evidence', 0):>14d}",
                f"{counts.get('5_ds_broad_classified_lt_5', 0):>14d}",
                f"{counts.get('6_ds_broad_concentration_low', 0):>14d}",
                f"{counts.get('7_ds_specific_emerging_classified_lt_3', 0):>14d}",
                f"{eligible_here:>10d} ({elig_pct:4.1f}%)",
            ]
            print(" ".join(row))

    # Samples from each discard bucket
    print()
    print("=" * 88)
    print("SAMPLES PER DISCARD BUCKET")
    print("=" * 88)
    for stage in STAGES:
        if stage.startswith("ELIGIBLE"):
            continue
        samples = stage_samples.get(stage, [])
        if not samples:
            continue
        print()
        print(f"── {STAGE_LABEL[stage]} ({stage_counts[stage]} total) ──")
        for s in samples:
            print(f"  [{s['geography']:10s} {s['dataset_status']:18s}] "
                  f"{(s['name'] or '')[:40]:40s}  "
                  f"ds={s['ds']:28s} classified={s['classified']} jds={s['jds']}")


if __name__ == "__main__":
    main()

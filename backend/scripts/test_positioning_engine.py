"""
Test Positioning Engine — runs against all companies with classified roles.

Shows eligibility, confidence, archetype, and guardrails for each.

Usage:
    cd backend
    python scripts/test_positioning_engine.py
    python scripts/test_positioning_engine.py --json
    python scripts/test_positioning_engine.py --company-id <uuid>
"""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.positioning_engine import positioning_engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--company-id", type=str, default=None)
    args = parser.parse_args()

    db = SessionLocal()

    if args.company_id:
        result = positioning_engine.generate(UUID(args.company_id), db)
        print(json.dumps(result.to_dict(), indent=2, default=str))
        db.close()
        return

    # Get all companies with 2+ classified roles
    rows = db.execute(text("""
        SELECT DISTINCT c.id, c.name
        FROM companies c
        JOIN company_job_roles jr ON jr.company_id = c.id
        WHERE jr.functional_area IS NOT NULL
        AND jr.functional_area NOT IN ('junk', 'unknown')
        GROUP BY c.id, c.name
        HAVING COUNT(*) >= 2
        ORDER BY COUNT(*) DESC
    """)).fetchall()

    results = []
    eligible_count = 0
    total = len(rows)

    print(f"\nTesting positioning engine on {total} companies...\n")
    print(f"{'Company':<30s} {'Eligible':<10s} {'Band':<10s} {'Gate':<15s} {'Archetype':<30s} {'Overclaims'}")
    print("-" * 120)

    for cid, name in rows:
        result = positioning_engine.generate(cid, db)
        results.append(result.to_dict())

        if result.eligible:
            eligible_count += 1

        overclaim_count = len(result.do_not_overclaim)
        print(
            f"{str(name)[:29]:<30s} "
            f"{'YES' if result.eligible else 'no':<10s} "
            f"{result.confidence_band:<10s} "
            f"{result.gate_passed:<15s} "
            f"{result.candidate_archetype[:29]:<30s} "
            f"{overclaim_count} flags"
        )

    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print(f"  Total companies tested: {total}")
    print(f"  Eligible for positioning: {eligible_count} ({eligible_count/total*100:.0f}%)")
    print(f"  Not eligible: {total - eligible_count}")

    # Confidence band distribution
    from collections import Counter
    bands = Counter(r["confidence_band"] for r in results if r["eligible"])
    gates = Counter(r["gate_passed"] for r in results if r["eligible"])
    archetypes = Counter(r["candidate_archetype"] for r in results if r["eligible"])

    print(f"\n  Confidence bands: {dict(bands)}")
    print(f"  Gate types: {dict(gates)}")
    print(f"\n  Archetypes:")
    for arch, cnt in archetypes.most_common():
        print(f"    {arch}: {cnt}")

    # Show example output for highest-confidence company
    best = [r for r in results if r["confidence_band"] == "high"]
    if not best:
        best = [r for r in results if r["eligible"]]
    if best:
        example = best[0]
        print(f"\n{'='*80}")
        print(f"  EXAMPLE OUTPUT: {example['company_name']}")
        print(f"{'='*80}")
        print(f"  Confidence: {example['confidence_band']} ({example['assertiveness_level']})")
        print(f"  Archetype: {example['candidate_archetype']}")
        print(f"\n  Pain Summary:")
        print(f"    {example['pain_summary']}")
        print(f"\n  Evidence Summary:")
        print(f"    {example['evidence_summary']}")
        print(f"\n  Positioning Angle:")
        print(f"    {example['positioning_angle']}")
        print(f"\n  Resume Emphasis:")
        for item in example["resume_emphasis"]:
            print(f"    - {item}")
        print(f"\n  Networking Angle:")
        print(f"    {example['networking_angle']}")
        print(f"\n  Interview Themes:")
        for item in example["interview_themes"]:
            print(f"    - {item}")
        print(f"\n  Do Not Overclaim:")
        for item in example["do_not_overclaim"]:
            print(f"    [!] {item}")
        print(f"\n  Evidence Caveats:")
        for item in example["evidence_caveats"]:
            print(f"    [*] {item}")

    if args.json:
        outfile = Path(__file__).resolve().parent.parent / "output" / "positioning_test.json"
        with open(outfile, "w") as f:
            json.dump(results, indent=2, default=str, fp=f)
        print(f"\n  Full results: {outfile}")

    db.close()


if __name__ == "__main__":
    main()

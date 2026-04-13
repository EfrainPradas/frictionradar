#!/usr/bin/env python
"""
retroactive_qa_tiering.py — Apply QA + tiering to an existing all_results.json
without re-running the full collection pipeline.

Usage:
    python cli/retroactive_qa_tiering.py --input ./results/all_results.json --output ./results_qa
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is importable
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.qa_engine import evaluate_qa
from app.services.tiering_engine import assign_tier, safe_tier_summary
from app.services.operational_state_mapper import (
    attach_qa_fields,
    build_run_summary,
)


def main():
    parser = argparse.ArgumentParser(description="Retroactive QA + tiering")
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output or args.input.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.input, "r", encoding="utf-8") as f:
        companies = json.load(f)

    print(f"Loaded {len(companies)} companies from {args.input}")

    enriched = []
    for company in companies:
        qa = evaluate_qa(company, companies)
        tier, rationale = assign_tier(company, qa)
        result = attach_qa_fields(company, qa, tier, rationale)
        result["summary"] = safe_tier_summary(tier, company)
        enriched.append(result)

    # Partition
    positioning = [r for r in enriched if r.get("operational_state") == "position_now"]
    review = [r for r in enriched if r.get("operational_state") == "inspect_human"]
    recollect = [r for r in enriched if r.get("operational_state") == "collect_more"]
    excluded = [r for r in enriched if r.get("operational_state") == "exclude"]

    summary = build_run_summary(
        enriched,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
    )

    def write(name, data):
        p = output_dir / name
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"  Wrote {p} ({len(data) if isinstance(data, list) else 'summary'})")

    write("all_results_qa.json", enriched)
    write("ready_for_positioning.json", positioning)
    write("ready_for_review_qa.json", review)
    write("needs_recollection_qa.json", recollect)
    write("excluded_qa.json", excluded)
    write("run_summary_qa.json", summary)

    # Print summary
    print("\n" + "=" * 50)
    print("QA + TIERING SUMMARY")
    print(f"  Total:                          {summary['total_companies']}")
    print(f"  Tier 1 (position_now):          {summary['tier_1_ready_for_positioning']}")
    print(f"  Tier 2 (inspect_human):         {summary['tier_2_ready_for_review']}")
    print(f"  Tier 3 (collect_more):          {summary['tier_3_needs_recollection']}")
    print(f"  Tier 4 (exclude):               {summary['tier_4_excluded']}")
    print(f"  QA high:                        {summary['qa_high']}")
    print(f"  QA medium:                      {summary['qa_medium']}")
    print(f"  QA low:                         {summary['qa_low']}")
    print(f"\n  Top QA flags:")
    for flag, count in summary.get("top_qa_flags", {}).items():
        print(f"    {flag:<45s}{count}")
    print("=" * 50)

    # Show tier 1 companies
    if positioning:
        print("\nTier 1 (Ready for Positioning):")
        for r in positioning:
            print(f"  - {r['company_name']}: friction={r.get('friction_score')}, "
                  f"signals={r.get('signals_count')}, "
                  f"pain_clarity={r.get('pain_clarity')}, "
                  f"function_concentration={r.get('function_concentration')}")
    else:
        print("\nNo companies reached Tier 1. (Expected — tier 1 is intentionally strict.)")

    print()


if __name__ == "__main__":
    main()

"""
Audit Sample — selects companies for manual review from a completed run.

Picks 10 companies per diagnostic state category:
  - specific_pain_identified
  - specific_pain_emerging
  - broad_hiring_pattern_detected

For each, shows: name, domain, top_function, classified, jds, direction, share.

Usage:
    cd backend
    python scripts/audit_sample.py --run-id <RUN_ID>
    python scripts/audit_sample.py --run-id <RUN_ID> --per-group 5
    python scripts/audit_sample.py --run-id <RUN_ID> --json
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RUNS_DIR = Path(__file__).resolve().parent.parent / "output" / "runs"

TARGET_STATES = [
    "specific_pain_identified",
    "specific_pain_emerging",
    "broad_hiring_pattern_detected",
]


def load_progress(run_id: str) -> list[dict]:
    progress_path = RUNS_DIR / run_id / "progress.jsonl"
    if not progress_path.exists():
        print(f"Progress file not found: {progress_path}")
        sys.exit(1)
    entries = []
    with open(progress_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def select_sample(entries: list[dict], per_group: int = 10) -> dict:
    ok = [e for e in entries if e.get("status") == "ok"]

    groups = {}
    for ds in TARGET_STATES:
        matching = [e for e in ok if e.get("after", {}).get("ds") == ds]
        # Sort by classified desc, then pick up to per_group
        matching.sort(key=lambda x: x.get("classified", 0), reverse=True)
        if len(matching) > per_group:
            # Take top half by evidence, random sample the rest
            top_half = per_group // 2
            selected = matching[:top_half]
            remaining = matching[top_half:]
            random.seed(42)  # Reproducible
            selected += random.sample(remaining, min(per_group - top_half, len(remaining)))
        else:
            selected = matching

        groups[ds] = selected

    return groups


def print_sample(groups: dict, run_id: str):
    total_selected = sum(len(g) for g in groups.values())
    print(f"\n{'='*90}")
    print(f"  AUDIT SAMPLE — Run: {run_id}")
    print(f"  {total_selected} companies selected for manual review")
    print(f"{'='*90}")

    for ds, companies in groups.items():
        print(f"\n  {'-'*86}")
        print(f"  {ds.upper()} ({len(companies)} companies)")
        print(f"  {'-'*86}")
        print(f"  {'#':>3s}  {'Company':<30s} {'Domain':<25s} {'Top Fn':<15s} {'Cls':>4s} {'JD':>4s} {'Share':>6s} {'Dir':<8s}")

        for i, e in enumerate(companies):
            name = e.get("name", "")[:29]
            domain = e.get("domain", "")[:24]
            top_fn = (e.get("top_function") or "-")[:14]
            classified = e.get("classified", 0)
            jds = e.get("descriptions", 0)
            share = e.get("top_share", 0)
            direction = e.get("direction", "same")

            print(
                f"  {i+1:3d}  {name:<30s} {domain:<25s} {top_fn:<15s} "
                f"{classified:4d} {jds:4d} {share:5.0%} {direction:<8s}"
            )

        if not companies:
            print(f"  (no companies in this state)")


def main():
    parser = argparse.ArgumentParser(description="Audit sample from batch run")
    parser.add_argument("--run-id", type=str, required=True, help="Run ID to sample from")
    parser.add_argument("--per-group", type=int, default=10, help="Companies per diagnostic state (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    entries = load_progress(args.run_id)
    groups = select_sample(entries, per_group=args.per_group)

    if args.json:
        output = {ds: companies for ds, companies in groups.items()}
        print(json.dumps(output, indent=2, default=str))
    else:
        print_sample(groups, args.run_id)


if __name__ == "__main__":
    main()

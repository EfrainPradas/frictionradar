"""
Coverage Report — reads a batch run's progress.jsonl and produces
the full coverage funnel metrics.

Measures:
  - Total empresas procesadas
  - Con careers page utilizable
  - Con roles detectados
  - Con roles clasificados
  - Con JDs extraídas
  - Con demasiados unknown
  - Elegibles para positioning
  - Distribución por diagnostic_state
  - Comparación vs muestra anterior

Usage:
    cd backend
    python scripts/coverage_report.py --run-id <RUN_ID>
    python scripts/coverage_report.py --run-id <RUN_ID> --json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RUNS_DIR = Path(__file__).resolve().parent.parent / "output" / "runs"

ELIGIBLE_DS = {
    "ready_for_positioning",
    "specific_pain_identified",
    "specific_pain_emerging",
}

# Companies need classified_roles >= 3 for conditional eligibility
CONDITIONAL_DS = {"broad_hiring_pattern_detected"}


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


def compute_coverage(entries: list[dict]) -> dict:
    ok = [e for e in entries if e.get("status") == "ok"]
    errors = [e for e in entries if e.get("status") == "error"]

    total = len(entries)
    total_ok = len(ok)

    # Funnel metrics
    with_roles = [e for e in ok if e.get("total_roles", 0) > 0]
    with_classified = [e for e in ok if e.get("classified", 0) > 0]
    with_classified_2plus = [e for e in ok if e.get("classified", 0) >= 2]
    with_jds = [e for e in ok if e.get("descriptions", 0) > 0 or e.get("jds_extracted", 0) > 0]
    with_too_many_unknown = [
        e for e in ok
        if e.get("unknown", 0) > e.get("classified", 0) and e.get("total_roles", 0) > 0
    ]

    # Careers page: check if extraction_coverage >= moderate (ec in before/after)
    with_careers = [
        e for e in ok
        if e.get("after", {}).get("ec") in ("moderate", "high")
    ]

    # Positioning eligibility
    eligible = []
    for e in ok:
        ds = e.get("after", {}).get("ds", "")
        classified = e.get("classified", 0)
        if ds in ELIGIBLE_DS:
            eligible.append(e)
        elif ds in CONDITIONAL_DS and classified >= 5:
            eligible.append(e)

    # Diagnostic state distribution
    ds_dist = Counter(e.get("after", {}).get("ds", "unknown") for e in ok)

    # KPI distributions
    fc_dist = Counter(e.get("after", {}).get("fc", "low") for e in ok)
    pc_dist = Counter(e.get("after", {}).get("pc", "low") for e in ok)
    pr_dist = Counter(e.get("after", {}).get("pr", "low") for e in ok)
    hp_dist = Counter(e.get("after", {}).get("hp", "low") for e in ok)
    ec_dist = Counter(e.get("after", {}).get("ec", "low") for e in ok)

    # Top functions among companies with roles
    func_dist = Counter()
    for e in ok:
        tf = e.get("top_function")
        if tf:
            func_dist[tf] += 1

    # Direction distribution
    dir_dist = Counter(e.get("direction", "same") for e in ok)

    return {
        "total_in_run": total,
        "total_ok": total_ok,
        "total_errors": len(errors),
        "coverage_funnel": {
            "with_careers_page": len(with_careers),
            "with_roles_detected": len(with_roles),
            "with_roles_classified": len(with_classified),
            "with_roles_classified_2plus": len(with_classified_2plus),
            "with_jds_extracted": len(with_jds),
            "with_too_many_unknown": len(with_too_many_unknown),
            "eligible_for_positioning": len(eligible),
        },
        "diagnostic_state": dict(ds_dist.most_common()),
        "function_concentration": dict(fc_dist),
        "pain_clarity": dict(pc_dist),
        "positioning_readiness": dict(pr_dist),
        "hiring_pressure": dict(hp_dist),
        "extraction_coverage": dict(ec_dist),
        "top_functions": dict(func_dist.most_common(15)),
        "direction": dict(dir_dist),
    }


def print_coverage(cov: dict, run_id: str):
    total = cov["total_ok"]
    funnel = cov["coverage_funnel"]

    print(f"\n{'='*70}")
    print(f"  COVERAGE REPORT — Run: {run_id}")
    print(f"  {total} companies processed, {cov['total_errors']} errors")
    print(f"{'='*70}")

    print(f"\n  Coverage Funnel:")
    for key, val in funnel.items():
        pct = val / total * 100 if total else 0
        bar = "#" * int(pct / 2)
        print(f"    {key:35s}: {val:5d} ({pct:5.1f}%) {bar}")

    print(f"\n  Diagnostic State:")
    for ds, cnt in cov["diagnostic_state"].items():
        pct = cnt / total * 100 if total else 0
        print(f"    {ds:40s}: {cnt:5d} ({pct:5.1f}%)")

    print(f"\n  Extraction Coverage:")
    for level, cnt in cov["extraction_coverage"].items():
        pct = cnt / total * 100 if total else 0
        print(f"    {level:15s}: {cnt:5d} ({pct:5.1f}%)")

    print(f"\n  Hiring Pressure:")
    for level, cnt in cov["hiring_pressure"].items():
        pct = cnt / total * 100 if total else 0
        print(f"    {level:15s}: {cnt:5d} ({pct:5.1f}%)")

    print(f"\n  Function Concentration:")
    for level, cnt in cov["function_concentration"].items():
        pct = cnt / total * 100 if total else 0
        print(f"    {level:15s}: {cnt:5d} ({pct:5.1f}%)")

    print(f"\n  Pain Clarity:")
    for level, cnt in cov["pain_clarity"].items():
        pct = cnt / total * 100 if total else 0
        print(f"    {level:15s}: {cnt:5d} ({pct:5.1f}%)")

    print(f"\n  Positioning Readiness:")
    for level, cnt in cov["positioning_readiness"].items():
        pct = cnt / total * 100 if total else 0
        print(f"    {level:15s}: {cnt:5d} ({pct:5.1f}%)")

    if cov["top_functions"]:
        print(f"\n  Top Functions (companies with classified roles):")
        for fn, cnt in cov["top_functions"].items():
            print(f"    {fn:25s}: {cnt}")

    print(f"\n  Direction (before vs after this run):")
    for d, cnt in cov["direction"].items():
        print(f"    {d:15s}: {cnt}")

    # Comparison with 35-company baseline
    print(f"\n  {'-'*66}")
    print(f"  Comparison: 35-company sample vs full dataset")
    print(f"  {'-'*66}")
    ds = cov["diagnostic_state"]
    spi = ds.get("specific_pain_identified", 0)
    spe = ds.get("specific_pain_emerging", 0)
    bhp = ds.get("broad_hiring_pattern_detected", 0)
    ie = ds.get("insufficient_evidence", 0)
    advanced = spi + spe
    print(f"    Previous 35-co sample: 13 spi + 12 spe = 25 advanced (71%)")
    print(f"    Full dataset {total}-co:  {spi} spi + {spe} spe = {advanced} advanced ({advanced/total*100:.1f}%)" if total else "")
    print(f"    insufficient_evidence: {ie} ({ie/total*100:.1f}%)" if total else "")
    print(f"    broad_hiring: {bhp} ({bhp/total*100:.1f}%)" if total else "")


def main():
    parser = argparse.ArgumentParser(description="Coverage report from batch run")
    parser.add_argument("--run-id", type=str, required=True, help="Run ID to analyze")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    entries = load_progress(args.run_id)
    cov = compute_coverage(entries)

    if args.json:
        print(json.dumps(cov, indent=2))
    else:
        print_coverage(cov, args.run_id)


if __name__ == "__main__":
    main()

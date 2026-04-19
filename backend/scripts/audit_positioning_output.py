"""Audit positioning_engine output on all eligible companies.

Iterates every company whose diagnostic_state is in ELIGIBLE_DS (or
conditional gate for broad_hiring_pattern_detected), calls
positioning_engine.generate(), and validates the output is coherent.

Checks:
  1. eligible=True (sanity — these came from eligible filter)
  2. dominant_function is non-empty
  3. candidate_archetype != "" and != "Functional Specialist" (default)
  4. resume_emphasis has >=3 items
  5. positioning_angle, networking_angle are non-empty
  6. pain_summary is non-empty
  7. scoring_engine produces a non-zero friction score

Outputs:
  - runs/<label>/positioning_audit.json     (full per-company detail)
  - runs/<label>/positioning_audit.md       (human-readable digest)
  - stdout summary with counts of issues found

Usage:
  python scripts/audit_positioning_output.py
  python scripts/audit_positioning_output.py --label audit_eligible_v1
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

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.services.company_evaluation import CompanyEvaluationEngine
from app.services.positioning_engine import (
    positioning_engine,
    ELIGIBLE_DS,
    check_eligibility,
)
from app.models.company_job_role import CompanyJobRole as _CJR
from app.services.scoring_engine import compute_and_persist_score


def _compute_top_share(db, company_id):
    """Replicate the top_share logic used in recompute_funnel_snapshot."""
    roles = (
        db.query(CompanyJobRole)
        .filter(CompanyJobRole.company_id == company_id)
        .all()
    )
    counts: dict[str, int] = {}
    for r in roles:
        area = r.functional_area
        if area and area not in ("junk", "unknown"):
            counts[area] = counts.get(area, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return 0, 0
    top = max(counts.values())
    return total, top / total


def _select_eligible(db):
    """Return list of (company_id, name, ds, classified, top_share, gate)
    for every company the positioning engine would accept.

    Uses check_eligibility() directly so this script agrees with
    positioning_engine.generate() on who is eligible.
    """
    evaluator = CompanyEvaluationEngine()
    companies = db.query(Company.id, Company.name).all()

    # JD count per company (for check_eligibility confidence_band).
    jd_counts: dict = {}
    for cid, rd in (
        db.query(_CJR.company_id, _CJR.role_description).all()
    ):
        if rd:
            jd_counts[cid] = jd_counts.get(cid, 0) + 1

    eligible = []
    for cid, name in companies:
        try:
            ev = evaluator.evaluate(company_id=cid, db=db)
        except Exception:
            continue
        ds = ev.get("diagnostic_state", "")
        kpis = ev.get("kpis", {})
        classified, top_share = _compute_top_share(db, cid)

        elig = check_eligibility(
            diagnostic_state=ds,
            pain_clarity=kpis.get("pain_clarity", "low"),
            function_concentration=kpis.get("function_concentration", "low"),
            positioning_readiness=kpis.get("positioning_readiness", "low"),
            classified_roles=classified,
            jds_extracted=jd_counts.get(cid, 0),
        )
        if elig.eligible:
            eligible.append(
                (cid, name, ds, classified, top_share, elig.gate_passed)
            )

    return eligible


def _validate(out) -> list[str]:
    """Return list of issues with a PositioningOutput."""
    issues = []
    if not out.eligible:
        issues.append("output.eligible is False")
    if not out.dominant_function:
        issues.append("dominant_function empty")
    if not out.candidate_archetype:
        issues.append("archetype empty")
    elif out.candidate_archetype == "Functional Specialist":
        issues.append(f"fell to default archetype (dominant_function={out.dominant_function})")
    if len(out.resume_emphasis) < 3:
        issues.append(f"resume_emphasis has only {len(out.resume_emphasis)} items")
    if not out.positioning_angle:
        issues.append("positioning_angle empty")
    if not out.networking_angle:
        issues.append("networking_angle empty")
    if not out.pain_summary:
        issues.append("pain_summary empty")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="audit_eligible_v1")
    ap.add_argument("--skip-scoring", action="store_true",
                    help="Skip friction score computation (faster)")
    args = ap.parse_args()

    db = SessionLocal()
    t0 = time.monotonic()

    print("Selecting eligible companies...")
    eligible = _select_eligible(db)
    print(f"  → {len(eligible)} eligible")

    per_company = []
    issues_counter: Counter = Counter()
    archetype_counter: Counter = Counter()
    function_counter: Counter = Counter()
    score_distribution: list[float] = []
    zero_score_eligible: list[str] = []
    default_archetype_companies: list[str] = []

    for cid, name, ds, classified, top_share, gate in eligible:
        try:
            out = positioning_engine.generate(cid, db)
        except Exception as e:
            issues_counter["positioning_exception"] += 1
            per_company.append({
                "name": name, "ds": ds, "gate": gate,
                "error": f"positioning: {type(e).__name__}: {e}",
            })
            continue

        issues = _validate(out)
        for i in issues:
            issues_counter[i.split(" (")[0].split(" has")[0]] += 1

        if out.candidate_archetype == "Functional Specialist":
            default_archetype_companies.append(name)

        archetype_counter[out.candidate_archetype or "(empty)"] += 1
        if out.dominant_function:
            function_counter[out.dominant_function] += 1

        # Scoring
        score_value = None
        score_dominant = None
        if not args.skip_scoring:
            try:
                fs = compute_and_persist_score(db, cid)
                score_value = fs.total_score
                score_dominant = fs.dominant_friction_type
                score_distribution.append(score_value)
                if score_value == 0:
                    zero_score_eligible.append(name)
            except Exception as e:
                issues_counter["scoring_exception"] += 1
                score_value = None

        per_company.append({
            "name": name,
            "ds": ds,
            "gate": gate,
            "classified": classified,
            "top_share": round(top_share, 2),
            "dominant_function": out.dominant_function,
            "archetype": out.candidate_archetype,
            "confidence_band": out.confidence_band,
            "assertiveness": out.assertiveness_level,
            "score": score_value,
            "score_dominant_friction": score_dominant,
            "issues": issues,
        })

    elapsed = time.monotonic() - t0

    # Console report
    print()
    print("=" * 70)
    print(f"POSITIONING AUDIT — {len(eligible)} companies in {elapsed:.1f}s")
    print("=" * 70)

    print("\n── Dominant function distribution (eligible companies) ──")
    for fn, c in function_counter.most_common():
        print(f"  {fn:20s}  {c:4d}")

    print("\n── Archetype distribution ──")
    for arch, c in archetype_counter.most_common():
        print(f"  {arch:45s}  {c:4d}")

    print("\n── Validation issues ──")
    if not issues_counter:
        print("  (none — all eligible companies produced complete positioning)")
    for issue, c in issues_counter.most_common():
        print(f"  {c:4d}  {issue}")

    if default_archetype_companies:
        print(f"\n── {len(default_archetype_companies)} fell to DEFAULT archetype ──")
        for n in default_archetype_companies[:20]:
            print(f"  {n}")

    if score_distribution:
        score_distribution.sort()
        mid = score_distribution[len(score_distribution) // 2]
        print(f"\n── Scoring distribution ──")
        print(f"  n={len(score_distribution)}  "
              f"min={min(score_distribution):.2f}  "
              f"median={mid:.2f}  "
              f"max={max(score_distribution):.2f}")
        if zero_score_eligible:
            print(f"  ⚠ {len(zero_score_eligible)} eligible with score=0:")
            for n in zero_score_eligible[:10]:
                print(f"    {n}")

    # Consistency check: does scoring.dominant_friction match positioning.dominant_function?
    mismatches = 0
    for row in per_company:
        df = row.get("dominant_function")
        sf = row.get("score_dominant_friction")
        if df and sf and df != sf:
            mismatches += 1
    print(f"\n── Positioning↔Scoring consistency ──")
    print(f"  {mismatches} companies where dominant_function ≠ dominant_friction")

    # Write artifacts
    out_dir = Path(__file__).resolve().parents[1] / "runs" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eligible_count": len(eligible),
        "issues_counter": dict(issues_counter),
        "archetype_counter": dict(archetype_counter),
        "function_counter": dict(function_counter),
        "mismatches_positioning_vs_scoring": mismatches,
        "default_archetype_companies": default_archetype_companies,
        "zero_score_eligible": zero_score_eligible,
        "per_company": per_company,
    }
    (out_dir / "positioning_audit.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )

    # Markdown digest
    md_lines = [
        f"# Positioning Audit — {args.label}",
        f"_Generated at {payload['generated_at']}_",
        "",
        f"- Eligible companies: **{len(eligible)}**",
        f"- Issues: **{sum(issues_counter.values())}** "
        f"across {len([v for v in issues_counter.values() if v > 0])} categories",
        f"- Dominant-function distribution: "
        + ", ".join(f"{fn}={c}" for fn, c in function_counter.most_common(5)),
        "",
        "## Sample — top 20 eligible",
        "",
        "| Company | DS | Gate | Func | Share | Archetype | Score |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in per_company[:20]:
        md_lines.append(
            f"| {row['name']} | {row['ds']} | {row['gate']} | "
            f"{row.get('dominant_function','')} | "
            f"{row.get('top_share','')} | "
            f"{row.get('archetype','')[:40]} | "
            f"{row.get('score','')} |"
        )
    (out_dir / "positioning_audit.md").write_text("\n".join(md_lines))

    print(f"\nWrote runs/{args.label}/positioning_audit.{{json,md}}")
    db.close()


if __name__ == "__main__":
    main()

"""
Batch Validation Rerun — measures impact of all fixes on KPIs.

Runs deep-intelligence + evaluation on a set of companies,
captures before/after snapshots, and generates a comparative report.

Usage:
    cd backend
    python scripts/batch_validation_rerun.py --tier 29     # focused 29
    python scripts/batch_validation_rerun.py --tier 100    # expanded 100
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func as sqlfunc
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole, HiringPattern
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.services.company_evaluation import CompanyEvaluationEngine
from app.services.jd_scraper_service import extract_jds_for_company
from app.services.hiring_pattern_service import compute_hiring_pattern

evaluation_engine = CompanyEvaluationEngine()
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

DS_RANKS = {
    "insufficient_evidence": 0,
    "broad_hiring_pattern_detected": 1,
    "specific_pain_emerging": 2,
    "specific_pain_identified": 3,
    "ready_for_positioning": 4,
}


def select_companies(db, limit: int) -> list[dict]:
    """Select companies that have roles (the ones that can be evaluated)."""
    role_counts = (
        db.query(
            CompanyJobRole.company_id,
            sqlfunc.count(CompanyJobRole.id).label("cnt"),
        )
        .group_by(CompanyJobRole.company_id)
        .having(sqlfunc.count(CompanyJobRole.id) >= 2)
        .all()
    )

    candidates = []
    for cid, cnt in role_counts:
        c = db.query(Company).filter(Company.id == cid).first()
        if not c or not c.domain:
            continue

        score = (
            db.query(FrictionScore)
            .filter(FrictionScore.company_id == cid)
            .order_by(FrictionScore.computed_at.desc())
            .first()
        )

        candidates.append({
            "id": cid,
            "name": c.name,
            "domain": c.domain,
            "roles": cnt,
            "score": float(score.total_score) if score and score.total_score else 0,
        })

    candidates.sort(key=lambda x: x["roles"], reverse=True)
    return candidates[:limit]


def snapshot_kpis(db, company_id) -> dict:
    """Capture current KPI state."""
    ev = evaluation_engine.evaluate(company_id=company_id, db=db)
    kpis = ev.get("kpis", {})
    return {
        "fc": kpis.get("function_concentration", "low"),
        "pc": kpis.get("pain_clarity", "low"),
        "pr": kpis.get("positioning_readiness", "low"),
        "ds": ev.get("diagnostic_state", ""),
        "ec": kpis.get("extraction_coverage", "low"),
        "hp": kpis.get("hiring_pressure", "low"),
    }


def process_company(db, company_id, name, domain) -> dict:
    """Run deep intelligence and capture before/after."""
    before = snapshot_kpis(db, company_id)

    # Count current state
    roles = db.query(CompanyJobRole).filter(CompanyJobRole.company_id == company_id).all()
    junk_count = sum(1 for r in roles if r.functional_area == "junk")
    unknown_count = sum(1 for r in roles if r.functional_area in ("unknown", None))
    classified_count = sum(1 for r in roles if r.functional_area and r.functional_area not in ("junk", "unknown"))
    desc_count = sum(1 for r in roles if r.role_description)

    # Run pipeline
    jd_result = extract_jds_for_company(company_id, db, max_jds=10, delay=0.5)
    pattern_result = compute_hiring_pattern(company_id, db)

    after = snapshot_kpis(db, company_id)

    # Determine changes
    changes = {}
    for key in ["fc", "pc", "pr", "ds"]:
        if before[key] != after[key]:
            changes[key] = {"before": before[key], "after": after[key]}

    ds_before_rank = DS_RANKS.get(before["ds"], 0)
    ds_after_rank = DS_RANKS.get(after["ds"], 0)
    if ds_after_rank > ds_before_rank:
        direction = "improved"
    elif ds_after_rank < ds_before_rank:
        direction = "degraded"
    else:
        direction = "same"

    pattern = pattern_result.get("pattern") or {}

    return {
        "name": name,
        "domain": domain,
        "total_roles": len(roles),
        "junk": junk_count,
        "unknown": unknown_count,
        "classified": classified_count,
        "descriptions": desc_count + jd_result.get("successful", 0),
        "jds_extracted": jd_result.get("successful", 0),
        "top_function": pattern.get("dominant_function"),
        "top_share": pattern.get("dominant_share", 0),
        "unique_areas": pattern.get("unique_functions", 0),
        "distribution": pattern.get("function_distribution", {}),
        "before": before,
        "after": after,
        "changes": changes,
        "direction": direction,
    }


def credibility_assessment(result: dict) -> str:
    """Assess if a diagnostic state change is credible."""
    if result["direction"] == "same":
        return "unchanged"

    classified = result["classified"]
    descs = result["descriptions"]
    share = result.get("top_share", 0)

    if classified >= 5 and descs >= 3 and share >= 0.4:
        return "credible"
    elif classified >= 3 and share >= 0.35:
        return "borderline"
    elif result["direction"] == "degraded":
        return "correction"
    else:
        return "forced"


def run_batch(db, companies: list[dict]) -> list[dict]:
    results = []
    for i, c in enumerate(companies):
        print(f"[{i+1}/{len(companies)}] {c['name']:35s} ", end="", flush=True)
        try:
            r = process_company(db, c["id"], c["name"], c["domain"])
            results.append(r)
            marker = ">>>" if r["direction"] == "improved" else "<<<" if r["direction"] == "degraded" else "   "
            print(f"{marker} fc:{r['after']['fc']:8s} pc:{r['after']['pc']:8s} ds:{r['after']['ds']}")
        except Exception as e:
            results.append({"name": c["name"], "domain": c["domain"], "error": str(e)})
            print(f"ERROR: {e}")
            db.rollback()
    return results


def generate_report(results: list[dict], label: str) -> dict:
    valid = [r for r in results if "error" not in r]
    if not valid:
        return {"label": label, "total": len(results), "valid": 0}

    before_ds = Counter(r["before"]["ds"] for r in valid)
    after_ds = Counter(r["after"]["ds"] for r in valid)
    before_fc = Counter(r["before"]["fc"] for r in valid)
    after_fc = Counter(r["after"]["fc"] for r in valid)
    before_pc = Counter(r["before"]["pc"] for r in valid)
    after_pc = Counter(r["after"]["pc"] for r in valid)
    before_pr = Counter(r["before"]["pr"] for r in valid)
    after_pr = Counter(r["after"]["pr"] for r in valid)

    improved = [r for r in valid if r["direction"] == "improved"]
    degraded = [r for r in valid if r["direction"] == "degraded"]
    changed = [r for r in valid if r["changes"]]

    credibility = Counter(credibility_assessment(r) for r in valid if r["direction"] != "same")

    return {
        "label": label,
        "total": len(results),
        "valid": len(valid),
        "errors": len(results) - len(valid),
        "improved": len(improved),
        "degraded": len(degraded),
        "changed": len(changed),
        "credibility": dict(credibility),
        "diagnostic_state": {"before": dict(before_ds), "after": dict(after_ds)},
        "function_concentration": {"before": dict(before_fc), "after": dict(after_fc)},
        "pain_clarity": {"before": dict(before_pc), "after": dict(after_pc)},
        "positioning_readiness": {"before": dict(before_pr), "after": dict(after_pr)},
        "company_details": [
            {
                "name": r["name"],
                "domain": r["domain"],
                "classified": r.get("classified", 0),
                "descriptions": r.get("descriptions", 0),
                "top_function": r.get("top_function"),
                "top_share": r.get("top_share", 0),
                "before_ds": r["before"]["ds"],
                "after_ds": r["after"]["ds"],
                "before_fc": r["before"]["fc"],
                "after_fc": r["after"]["fc"],
                "direction": r["direction"],
                "credibility": credibility_assessment(r),
                "distribution": r.get("distribution", {}),
            }
            for r in valid
        ],
    }


def print_report(report: dict):
    label = report["label"]
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"  {report['valid']} companies, {report['errors']} errors")
    print(f"{'='*80}")

    print(f"\n  Improved: {report['improved']}  |  Degraded: {report['degraded']}  |  Changed: {report['changed']}")
    if report.get("credibility"):
        print(f"  Credibility: {report['credibility']}")

    for kpi_name in ["diagnostic_state", "function_concentration", "pain_clarity", "positioning_readiness"]:
        kpi = report.get(kpi_name, {})
        before = kpi.get("before", {})
        after = kpi.get("after", {})
        all_keys = sorted(set(list(before.keys()) + list(after.keys())))
        if not all_keys:
            continue

        print(f"\n  {kpi_name}:")
        for k in all_keys:
            b = before.get(k, 0)
            a = after.get(k, 0)
            delta = a - b
            marker = f" (+{delta})" if delta > 0 else f" ({delta})" if delta < 0 else ""
            if b or a:
                print(f"    {k:40s}: {b:3d} -> {a:3d}{marker}")

    # Per-company audit for changed
    changed = [d for d in report.get("company_details", []) if d["direction"] != "same"]
    if changed:
        print(f"\n  {'─'*76}")
        print(f"  COMPANIES THAT CHANGED ({len(changed)}):")
        print(f"  {'─'*76}")
        for d in changed:
            cred_marker = {"credible": "[OK]", "borderline": "[~~]", "forced": "[!!]", "correction": "[<<]"}.get(d["credibility"], "[??]")
            print(f"  {cred_marker} {d['name']} ({d['domain']})")
            print(f"      ds: {d['before_ds']} -> {d['after_ds']}")
            print(f"      fc: {d['before_fc']} -> {d['after_fc']}")
            print(f"      top: {d['top_function']} ({d['top_share']:.0%}), {d['classified']} classified, {d['descriptions']} descs")
            print(f"      dist: {d['distribution']}")
            print(f"      verdict: {d['credibility']}")
            print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", type=int, default=29, help="Number of companies")
    args = parser.parse_args()

    db = SessionLocal()

    print(f"Selecting up to {args.tier} companies with roles...")
    companies = select_companies(db, limit=args.tier)
    print(f"Selected {len(companies)}")

    results = run_batch(db, companies)
    report = generate_report(results, f"Validation Rerun — {len(companies)} companies")
    print_report(report)

    # Save
    outfile = OUTPUT_DIR / f"validation_rerun_{len(companies)}.json"
    with open(outfile, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nSaved to {outfile}")

    db.close()


if __name__ == "__main__":
    main()

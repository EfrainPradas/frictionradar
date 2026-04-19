"""
Batch JD Intelligence MVP — Phase 7 validation.

Selects a subset of ~75 companies, runs deep-intelligence on each,
captures before/after KPI snapshots, and produces a validation report.

Usage:
    cd backend
    python scripts/batch_jd_intelligence.py                    # run full batch
    python scripts/batch_jd_intelligence.py --resume           # skip already processed
    python scripts/batch_jd_intelligence.py --limit 10         # test with 10 companies
    python scripts/batch_jd_intelligence.py --company-id UUID  # single company
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# Setup path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, text
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_signal import CompanySignal
from app.models.company_job_role import CompanyJobRole, HiringPattern
from app.models.friction_score import FrictionScore
from app.services.company_evaluation import CompanyEvaluationEngine
from app.services.jd_scraper_service import extract_jds_for_company
from app.services.hiring_pattern_service import compute_hiring_pattern
from app.services.company_type_engine import company_type_engine

evaluation_engine = CompanyEvaluationEngine()

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
RESULTS_FILE = OUTPUT_DIR / "jd_intelligence_results.json"


# ── Subset selection ──────────────────────────────────────────────────

def select_subset(db, limit: int = 75) -> list[dict]:
    """Select companies for the MVP batch based on tiers."""

    # Get all companies with their latest score and signal count
    companies = db.query(Company).all()

    candidates = []
    for c in companies:
        if not c.domain:
            continue

        score_row = (
            db.query(FrictionScore)
            .filter(FrictionScore.company_id == c.id)
            .order_by(FrictionScore.computed_at.desc())
            .first()
        )
        if not score_row:
            continue

        signal_count = (
            db.query(func.count(CompanySignal.id))
            .filter(CompanySignal.company_id == c.id)
            .scalar()
        )

        role_count = (
            db.query(func.count(CompanyJobRole.id))
            .filter(CompanyJobRole.company_id == c.id)
            .scalar()
        )

        # Get current evaluation
        ev = evaluation_engine.evaluate(company_id=c.id, db=db)
        kpis = ev.get("kpis", {})

        ec = kpis.get("extraction_coverage", "low")
        hp = kpis.get("hiring_pressure", "low")

        if ec not in ("high", "moderate") or hp not in ("high", "moderate"):
            continue

        candidates.append({
            "id": c.id,
            "name": c.name,
            "domain": c.domain,
            "score": float(score_row.total_score) if score_row.total_score else 0,
            "friction_type": score_row.dominant_friction_type,
            "signals": signal_count,
            "roles": role_count,
            "kpis": kpis,
            "diagnostic_state": ev.get("diagnostic_state", ""),
        })

    # Sort into tiers
    tier1 = [c for c in candidates if c["score"] >= 8 and c["kpis"].get("pain_clarity") == "low" and c["signals"] >= 10]
    tier2 = [c for c in candidates if 5 <= c["score"] < 8 and c["kpis"].get("extraction_coverage") == "high"]
    tier3 = [c for c in candidates if c["kpis"].get("pain_clarity") in ("moderate", "high")]

    # Remove duplicates across tiers
    seen = set()
    selected = []

    for tier, max_n in [(tier1, 30), (tier2, 25), (tier3, 20)]:
        tier.sort(key=lambda x: x["score"], reverse=True)
        for c in tier:
            cid = str(c["id"])
            if cid not in seen and len(selected) < limit:
                seen.add(cid)
                selected.append(c)
                if len([s for s in selected if s in tier]) >= max_n:
                    break

    # Fill remaining with top-scored candidates not yet selected
    if len(selected) < limit:
        remaining = [c for c in candidates if str(c["id"]) not in seen]
        remaining.sort(key=lambda x: x["score"], reverse=True)
        for c in remaining:
            if len(selected) >= limit:
                break
            selected.append(c)

    return selected[:limit]


# ── Single company pipeline ──────────────────────────────────────────

def process_company(db, company_id: UUID) -> dict:
    """Run JD intelligence pipeline for one company, return before/after."""

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "not_found", "company_id": str(company_id)}

    # BEFORE snapshot
    before_ev = evaluation_engine.evaluate(company_id=company_id, db=db)
    before_kpis = before_ev.get("kpis", {})
    before_ds = before_ev.get("diagnostic_state", "")

    # Count existing roles with descriptions
    existing_descriptions = (
        db.query(func.count(CompanyJobRole.id))
        .filter(
            CompanyJobRole.company_id == company_id,
            CompanyJobRole.role_description.isnot(None),
            CompanyJobRole.role_description != "",
        )
        .scalar()
    )

    # Step 1: Extract JDs
    t0 = time.monotonic()
    jd_result = extract_jds_for_company(company_id, db, max_jds=10, delay=0.5)
    jd_time = time.monotonic() - t0

    # Step 2: Classify roles + compute pattern + generate signals
    t1 = time.monotonic()
    pattern_result = compute_hiring_pattern(company_id, db)
    pattern_time = time.monotonic() - t1

    # Step 3: Re-evaluate KPIs
    after_ev = evaluation_engine.evaluate(company_id=company_id, db=db)
    after_kpis = after_ev.get("kpis", {})
    after_ds = after_ev.get("diagnostic_state", "")

    # Compute diff
    kpi_changes = {}
    for key in ["function_concentration", "pain_clarity", "positioning_readiness"]:
        b = before_kpis.get(key, "low")
        a = after_kpis.get(key, "low")
        if a != b:
            kpi_changes[key] = {"before": b, "after": a}

    ds_changed = after_ds != before_ds
    improved = (
        ds_changed and
        _ds_rank(after_ds) > _ds_rank(before_ds)
    )

    return {
        "company_id": str(company_id),
        "company_name": company.name,
        "domain": company.domain,
        "friction_type": (pattern_result.get("pattern") or {}).get("dominant_function", ""),

        "jd_extraction": {
            "attempted": jd_result.get("total_attempted", 0),
            "successful": jd_result.get("successful", 0),
            "existing_descriptions": existing_descriptions,
            "time_s": round(jd_time, 1),
        },

        "classification": pattern_result.get("classification", {}),
        "pattern": pattern_result.get("pattern"),
        "signals_generated": pattern_result.get("signals_generated", 0),

        "before": {
            "function_concentration": before_kpis.get("function_concentration", "low"),
            "pain_clarity": before_kpis.get("pain_clarity", "low"),
            "positioning_readiness": before_kpis.get("positioning_readiness", "low"),
            "diagnostic_state": before_ds,
        },
        "after": {
            "function_concentration": after_kpis.get("function_concentration", "low"),
            "pain_clarity": after_kpis.get("pain_clarity", "low"),
            "positioning_readiness": after_kpis.get("positioning_readiness", "low"),
            "diagnostic_state": after_ds,
        },

        "kpi_changes": kpi_changes,
        "diagnostic_changed": ds_changed,
        "improved": improved,
        "direction": "improved" if improved else ("degraded" if ds_changed and not improved else "same"),
        "total_time_s": round(jd_time + pattern_time, 1),
    }


DS_RANKS = {
    "insufficient_evidence": 0,
    "broad_hiring_pattern_detected": 1,
    "specific_pain_emerging": 2,
    "specific_pain_identified": 3,
    "ready_for_positioning": 4,
}

def _ds_rank(ds: str) -> int:
    return DS_RANKS.get(ds, 0)


# ── Batch orchestrator ───────────────────────────────────────────────

def run_batch(subset: list[dict], resume: bool = False) -> list[dict]:
    """Run JD intelligence on a list of companies."""

    # Load previous results for resume
    done_ids = set()
    previous_results = []
    if resume and RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            prev = json.load(f)
            previous_results = prev.get("results", [])
            done_ids = {r["company_id"] for r in previous_results if "error" not in r}
        print(f"[Resume] {len(done_ids)} already processed, skipping")

    pending = [c for c in subset if str(c["id"]) not in done_ids]
    print(f"\n{'='*60}")
    print(f"  JD Intelligence Batch — {len(pending)} companies to process")
    print(f"  ({len(done_ids)} already done, {len(subset)} total)")
    print(f"{'='*60}\n")

    results = list(previous_results)
    errors = 0
    t_start = time.monotonic()

    for i, company in enumerate(pending):
        cid = company["id"]
        name = company["name"]
        domain = company["domain"]

        elapsed = time.monotonic() - t_start
        avg = elapsed / (i + 1) if i > 0 else 0
        eta = avg * (len(pending) - i - 1) if i > 0 else 0

        print(f"[{i+1}/{len(pending)}] {name} ({domain}) ", end="", flush=True)

        db = SessionLocal()
        try:
            result = process_company(db, cid)
            results.append(result)

            if "error" in result:
                errors += 1
                print(f"ERROR: {result['error']}")
            else:
                jds = result["jd_extraction"]["successful"]
                direction = result["direction"]
                ds_after = result["after"]["diagnostic_state"]
                t = result["total_time_s"]
                marker = ">>>" if direction == "improved" else "   "
                print(f"{marker} {jds} JDs | {direction:8s} | {ds_after} | {t:.1f}s")

        except Exception as e:
            errors += 1
            results.append({"company_id": str(cid), "company_name": name, "error": str(e)})
            print(f"EXCEPTION: {e}")
            db.rollback()
        finally:
            db.close()

        # Save progress after each company
        _save_results(results, subset)

    total_time = time.monotonic() - t_start
    print(f"\n{'='*60}")
    print(f"  Done: {len(pending)} companies in {total_time:.0f}s ({total_time/max(len(pending),1):.1f}s avg)")
    print(f"  Errors: {errors}")
    print(f"{'='*60}\n")

    return results


def _save_results(results: list[dict], subset: list[dict]):
    """Persist results to JSON file."""
    report = generate_report(results)
    report["subset_info"] = {
        "total_selected": len(subset),
        "tiers": {
            "tier1_high_score_low_clarity": len([s for s in subset if s["score"] >= 8]),
            "tier2_medium_score": len([s for s in subset if 5 <= s["score"] < 8]),
            "tier3_existing_clarity": len([s for s in subset if s["kpis"].get("pain_clarity") in ("moderate", "high")]),
        },
    }
    report["results"] = results

    with open(RESULTS_FILE, "w") as f:
        json.dump(report, f, indent=2, default=str)


# ── Report generator ─────────────────────────────────────────────────

def generate_report(results: list[dict]) -> dict:
    """Generate validation report from results."""

    valid = [r for r in results if "error" not in r]
    if not valid:
        return {"status": "no_valid_results", "total": len(results)}

    # JD extraction stats
    total_jds_attempted = sum(r["jd_extraction"]["attempted"] for r in valid)
    total_jds_extracted = sum(r["jd_extraction"]["successful"] for r in valid)
    companies_with_jds = len([r for r in valid if r["jd_extraction"]["successful"] >= 3])

    # KPI movement
    fc_moved = [r for r in valid if r["before"]["function_concentration"] != r["after"]["function_concentration"]]
    pc_moved = [r for r in valid if r["before"]["pain_clarity"] != r["after"]["pain_clarity"]]
    pr_moved = [r for r in valid if r["before"]["positioning_readiness"] != r["after"]["positioning_readiness"]]
    ds_improved = [r for r in valid if r["direction"] == "improved"]

    # Diagnostic state distribution
    before_ds = Counter(r["before"]["diagnostic_state"] for r in valid)
    after_ds = Counter(r["after"]["diagnostic_state"] for r in valid)

    # Pain clarity distribution
    before_pc = Counter(r["before"]["pain_clarity"] for r in valid)
    after_pc = Counter(r["after"]["pain_clarity"] for r in valid)

    # Positioning readiness distribution
    before_pr = Counter(r["before"]["positioning_readiness"] for r in valid)
    after_pr = Counter(r["after"]["positioning_readiness"] for r in valid)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_companies": len(results),
        "valid_companies": len(valid),
        "errors": len(results) - len(valid),

        "jd_extraction": {
            "total_attempted": total_jds_attempted,
            "total_extracted": total_jds_extracted,
            "extraction_rate": round(total_jds_extracted / max(total_jds_attempted, 1), 2),
            "companies_with_3plus_jds": companies_with_jds,
            "companies_with_3plus_jds_pct": round(companies_with_jds / max(len(valid), 1) * 100),
        },

        "kpi_movement": {
            "function_concentration_changed": len(fc_moved),
            "pain_clarity_changed": len(pc_moved),
            "positioning_readiness_changed": len(pr_moved),
            "diagnostic_state_improved": len(ds_improved),
        },

        "diagnostic_state": {
            "before": dict(before_ds),
            "after": dict(after_ds),
        },

        "pain_clarity": {
            "before": dict(before_pc),
            "after": dict(after_pc),
        },

        "positioning_readiness": {
            "before": dict(before_pr),
            "after": dict(after_pr),
        },

        "success_criteria": {
            "jd_extraction_60pct": companies_with_jds >= len(valid) * 0.6,
            "ds_improved_40pct": len(ds_improved) >= len(valid) * 0.4,
            "pain_clarity_up_30pct": len(pc_moved) >= len(valid) * 0.3,
            "positioning_readiness_up_20pct": len(pr_moved) >= len(valid) * 0.2,
        },
    }


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch JD Intelligence MVP")
    parser.add_argument("--limit", type=int, default=75, help="Max companies to process")
    parser.add_argument("--resume", action="store_true", help="Skip already processed companies")
    parser.add_argument("--company-id", type=str, help="Process a single company by UUID")
    args = parser.parse_args()

    db = SessionLocal()

    if args.company_id:
        print(f"Processing single company: {args.company_id}")
        result = process_company(db, UUID(args.company_id))
        print(json.dumps(result, indent=2, default=str))
        db.close()
        return

    print("Selecting subset...")
    subset = select_subset(db, limit=args.limit)
    db.close()

    if not subset:
        print("No companies matched selection criteria.")
        return

    print(f"Selected {len(subset)} companies")
    print(f"  Score range: {min(c['score'] for c in subset):.1f} - {max(c['score'] for c in subset):.1f}")
    friction_dist = Counter(c["friction_type"] for c in subset)
    for ft, n in friction_dist.most_common():
        print(f"  {ft}: {n}")

    results = run_batch(subset, resume=args.resume)

    # Print summary
    report = generate_report(results)
    print("\n" + "="*60)
    print("  VALIDATION REPORT")
    print("="*60)
    print(f"\nJD Extraction:")
    jd = report["jd_extraction"]
    print(f"  {jd['total_extracted']}/{jd['total_attempted']} extracted ({jd['extraction_rate']:.0%})")
    print(f"  {jd['companies_with_3plus_jds']}/{report['valid_companies']} companies with 3+ JDs ({jd['companies_with_3plus_jds_pct']}%)")

    print(f"\nKPI Movement:")
    km = report["kpi_movement"]
    print(f"  function_concentration changed: {km['function_concentration_changed']}")
    print(f"  pain_clarity changed: {km['pain_clarity_changed']}")
    print(f"  positioning_readiness changed: {km['positioning_readiness_changed']}")
    print(f"  diagnostic_state improved: {km['diagnostic_state_improved']}")

    print(f"\nDiagnostic State (before -> after):")
    for state in DS_RANKS:
        b = report["diagnostic_state"]["before"].get(state, 0)
        a = report["diagnostic_state"]["after"].get(state, 0)
        if b or a:
            arrow = ">>>" if a > b else "   "
            print(f"  {arrow} {state}: {b} -> {a}")

    print(f"\nPain Clarity (before -> after):")
    for level in ["low", "moderate", "high"]:
        b = report["pain_clarity"]["before"].get(level, 0)
        a = report["pain_clarity"]["after"].get(level, 0)
        if b or a:
            arrow = ">>>" if a > b else "   "
            print(f"  {arrow} {level}: {b} -> {a}")

    print(f"\nSuccess Criteria:")
    sc = report["success_criteria"]
    for k, v in sc.items():
        status = "PASS" if v else "FAIL"
        print(f"  [{status}] {k}")

    print(f"\nFull results: {RESULTS_FILE}")


if __name__ == "__main__":
    main()

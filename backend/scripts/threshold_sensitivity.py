"""
Threshold Sensitivity Test — controlled simulation over 29 companies.

Does NOT modify production. Simulates 3 scenarios for function_concentration
thresholds and reports before/after for all downstream KPIs.
"""

import sys, json
from pathlib import Path
from uuid import UUID
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.company_job_role import CompanyJobRole, HiringPattern
from app.models.company_signal import CompanySignal
from app.models.company import Company

SCENARIOS = {
    "baseline": {
        "high_share": 0.50, "high_min_top": 3, "high_max_areas": 3,
        "mod_share": 0.35, "mod_min_top": 2, "mod_max_areas": 4,
    },
    "moderate": {
        "high_share": 0.40, "high_min_top": 3, "high_max_areas": 4,
        "mod_share": 0.30, "mod_min_top": 2, "mod_max_areas": 5,
    },
    "flexible": {
        "high_share": 0.35, "high_min_top": 3, "high_max_areas": 5,
        "mod_share": 0.25, "mod_min_top": 2, "mod_max_areas": 6,
    },
}


def load_profiles():
    """Load real data for the 29 companies from the focused batch."""
    results_path = Path(__file__).resolve().parent.parent / "output" / "jd_intelligence_focused.json"
    with open(results_path) as f:
        data = json.load(f)

    company_ids = [r["company_id"] for r in data["results"] if "error" not in r]

    db = SessionLocal()
    profiles = []

    for cid_str in company_ids:
        cid = UUID(cid_str)
        c = db.query(Company).filter(Company.id == cid).first()
        if not c:
            continue

        roles = db.query(CompanyJobRole).filter(CompanyJobRole.company_id == cid).all()
        hp = (
            db.query(HiringPattern)
            .filter(HiringPattern.company_id == cid)
            .order_by(HiringPattern.created_at.desc())
            .first()
        )
        signals = db.query(CompanySignal).filter(CompanySignal.company_id == cid).all()

        classified = [r for r in roles if r.functional_area and r.functional_area != "unknown"]
        with_desc = [r for r in roles if r.role_description]

        fc = {}
        for r in classified:
            fc[r.functional_area] = fc.get(r.functional_area, 0) + 1

        total_classified = sum(fc.values())
        top_count = max(fc.values()) if fc else 0
        top_func = max(fc, key=fc.get) if fc else None
        share = top_count / total_classified if total_classified > 0 else 0
        unique_areas = len(fc)

        # Hiring areas from signals
        hiring_area_set = set()
        for s in signals:
            st = s.signal_type or ""
            if st.endswith("_hiring_detected"):
                hiring_area_set.add(st.replace("_hiring_detected", ""))
        hiring_areas = max(len(hiring_area_set), unique_areas)

        # Open positions
        open_pos = 0
        for s in signals:
            if s.signal_type in ("open_positions_count_detected", "high_open_positions_count_detected"):
                try:
                    v = int(s.numeric_value or 0)
                    if v > open_pos:
                        open_pos = v
                except (TypeError, ValueError):
                    pass

        profiles.append({
            "name": c.name,
            "domain": c.domain,
            "total_roles": len(roles),
            "classified": total_classified,
            "with_desc": len(with_desc),
            "top_func": top_func,
            "top_count": top_count,
            "share": round(share, 2),
            "unique_areas": unique_areas,
            "hiring_areas": hiring_areas,
            "open_positions": open_pos,
            "has_hp": hp is not None,
            "distribution": dict(sorted(fc.items(), key=lambda x: x[1], reverse=True)),
        })

    db.close()
    return profiles


def sim_fc(p, s):
    if p["classified"] == 0:
        return "low"
    # Use unique_areas (from classified roles) when available, not hiring_areas (from signals)
    areas = p["unique_areas"] if p["classified"] > 0 else p["hiring_areas"]
    if areas >= 5 and p["classified"] < 3:
        return "low"
    if p["top_count"] >= s["high_min_top"] and p["share"] >= s["high_share"] and areas <= s["high_max_areas"]:
        return "high"
    if p["top_count"] >= s["mod_min_top"] and p["share"] >= s["mod_share"] and areas <= s["mod_max_areas"]:
        return "moderate"
    return "low"


def sim_pc(p):
    top = p["top_count"]
    share = p["share"]
    has_hp = p["has_hp"]
    descs = p["with_desc"]
    classified = p["classified"]

    if (top >= 3 and share >= 0.5) or (has_hp and descs >= 3 and share >= 0.5):
        return "high"
    if top >= 2 or has_hp or classified >= 3:
        return "moderate"
    return "low"


def sim_hp(p):
    if p["open_positions"] >= 100 or p["hiring_areas"] >= 5:
        return "high"
    if p["open_positions"] >= 20 or p["hiring_areas"] >= 2:
        return "moderate"
    return "low"


def sim_pr(hp, pc, fc, ctc="high"):
    order = {"low": 0, "moderate": 1, "high": 2}
    if pc == "low":
        return "low"
    if pc == "high" and order.get(fc, 0) >= 1 and order.get(ctc, 0) >= 1 and order.get(hp, 0) >= 1:
        return "high"
    if order.get(pc, 0) >= 1 and order.get(fc, 0) >= 1 and order.get(hp, 0) >= 1:
        return "moderate"
    return "low"


def sim_ds(hp, pc, fc, pr):
    order = {"low": 0, "moderate": 1, "high": 2}
    if pr == "high":
        return "ready_for_positioning"
    if order.get(pc, 0) >= 1 and order.get(fc, 0) >= 1:
        if pc == "high":
            return "specific_pain_identified"
        return "specific_pain_emerging"
    if pc == "moderate" and fc == "low":
        if hp == "high":
            return "broad_hiring_pattern_detected"
        return "specific_pain_emerging"
    if hp == "high" and pc == "low":
        return "broad_hiring_pattern_detected"
    if order.get(hp, 0) >= 1:
        return "broad_hiring_pattern_detected"
    return "insufficient_evidence"


def run_scenario(profiles, scenario_name, thresholds):
    results = []
    for p in profiles:
        fc = sim_fc(p, thresholds)
        pc = sim_pc(p)
        hp = sim_hp(p)
        pr = sim_pr(hp, pc, fc)
        ds = sim_ds(hp, pc, fc, pr)
        results.append({
            "name": p["name"],
            "domain": p["domain"],
            "fc": fc, "pc": pc, "hp": hp, "pr": pr, "ds": ds,
            "profile": p,
        })
    return results


def credibility_audit(baseline_results, scenario_results, scenario_name):
    """For each company that changed, assess credibility."""
    audits = []
    for base, scen in zip(baseline_results, scenario_results):
        if base["ds"] == scen["ds"]:
            continue

        p = scen["profile"]
        # Credibility assessment
        if p["classified"] >= 5 and p["with_desc"] >= 3 and p["share"] >= 0.35:
            credibility = "credible"
            reason = f"{p['classified']} classified roles, {p['with_desc']} descriptions, {p['share']:.0%} concentration in {p['top_func']}"
        elif p["classified"] >= 3 and p["share"] >= 0.30:
            credibility = "borderline"
            reason = f"{p['classified']} classified roles, {p['share']:.0%} in {p['top_func']} — limited evidence depth"
        else:
            credibility = "forced"
            reason = f"Only {p['classified']} classified, {p['share']:.0%} share — threshold change drove this, not evidence"

        audits.append({
            "name": p["name"],
            "domain": p["domain"],
            "ds_change": f"{base['ds']} -> {scen['ds']}",
            "fc_change": f"{base['fc']} -> {scen['fc']}",
            "pr_change": f"{base['pr']} -> {scen['pr']}",
            "top_func": p["top_func"],
            "share": p["share"],
            "classified": p["classified"],
            "with_desc": p["with_desc"],
            "distribution": p["distribution"],
            "credibility": credibility,
            "reason": reason,
        })
    return audits


def main():
    print("Loading company profiles...")
    profiles = load_profiles()
    print(f"Loaded {len(profiles)} companies\n")

    # Run all scenarios
    all_results = {}
    for sname, thresholds in SCENARIOS.items():
        all_results[sname] = run_scenario(profiles, sname, thresholds)

    baseline = all_results["baseline"]

    # Print comparison
    print("=" * 80)
    print("  THRESHOLD SENSITIVITY TEST — 3 Scenarios")
    print("=" * 80)

    for sname, thresholds in SCENARIOS.items():
        results = all_results[sname]
        fc_dist = Counter(r["fc"] for r in results)
        pc_dist = Counter(r["pc"] for r in results)
        pr_dist = Counter(r["pr"] for r in results)
        ds_dist = Counter(r["ds"] for r in results)

        print(f"\n{'─'*80}")
        t = thresholds
        print(f"  {sname.upper()}")
        print(f"  HIGH: share>={t['high_share']:.0%}, top>={t['high_min_top']}, areas<={t['high_max_areas']}")
        print(f"  MOD:  share>={t['mod_share']:.0%}, top>={t['mod_min_top']}, areas<={t['mod_max_areas']}")
        print(f"{'─'*80}")
        print(f"  function_concentration:  low={fc_dist.get('low',0)}  moderate={fc_dist.get('moderate',0)}  high={fc_dist.get('high',0)}")
        print(f"  pain_clarity:            low={pc_dist.get('low',0)}  moderate={pc_dist.get('moderate',0)}  high={pc_dist.get('high',0)}")
        print(f"  positioning_readiness:   low={pr_dist.get('low',0)}  moderate={pr_dist.get('moderate',0)}  high={pr_dist.get('high',0)}")
        print(f"  diagnostic_state:")
        for ds_name in ["broad_hiring_pattern_detected", "specific_pain_emerging", "specific_pain_identified", "ready_for_positioning"]:
            count = ds_dist.get(ds_name, 0)
            base_count = Counter(r["ds"] for r in baseline).get(ds_name, 0)
            delta = count - base_count
            marker = f" (+{delta})" if delta > 0 else f" ({delta})" if delta < 0 else ""
            if count > 0 or base_count > 0:
                print(f"    {ds_name}: {count}{marker}")

    # Credibility audits
    for sname in ["moderate", "flexible"]:
        results = all_results[sname]
        audits = credibility_audit(baseline, results, sname)

        if not audits:
            continue

        print(f"\n{'='*80}")
        print(f"  CREDIBILITY AUDIT — {sname.upper()} scenario")
        print(f"  {len(audits)} companies changed diagnostic_state")
        print(f"{'='*80}")

        cred_counts = Counter(a["credibility"] for a in audits)
        print(f"\n  Summary: {cred_counts.get('credible',0)} credible, {cred_counts.get('borderline',0)} borderline, {cred_counts.get('forced',0)} forced\n")

        for a in audits:
            marker = {"credible": "[OK]", "borderline": "[~~]", "forced": "[!!]"}[a["credibility"]]
            print(f"  {marker} {a['name']} ({a['domain']})")
            print(f"      ds: {a['ds_change']}")
            print(f"      fc: {a['fc_change']}  |  pr: {a['pr_change']}")
            print(f"      top: {a['top_func']} ({a['share']:.0%}), {a['classified']} classified, {a['with_desc']} descs")
            print(f"      dist: {a['distribution']}")
            print(f"      verdict: {a['credibility']} — {a['reason']}")
            print()

    # Final recommendation
    print("=" * 80)
    print("  RECOMMENDATION")
    print("=" * 80)

    mod_audits = credibility_audit(baseline, all_results["moderate"], "moderate")
    flex_audits = credibility_audit(baseline, all_results["flexible"], "flexible")

    mod_credible = sum(1 for a in mod_audits if a["credibility"] == "credible")
    mod_forced = sum(1 for a in mod_audits if a["credibility"] == "forced")
    flex_credible = sum(1 for a in flex_audits if a["credibility"] == "credible")
    flex_forced = sum(1 for a in flex_audits if a["credibility"] == "forced")

    print(f"\n  Moderate: {len(mod_audits)} changed, {mod_credible} credible, {mod_forced} forced")
    print(f"  Flexible: {len(flex_audits)} changed, {flex_credible} credible, {flex_forced} forced")

    # Check if the real problem is function granularity
    broad_companies = [p for p in profiles if p["unique_areas"] >= 4 and p["classified"] >= 5]
    could_benefit_from_macro = []
    for p in broad_companies:
        # Check if merging related functions would create concentration
        ops_like = sum(p["distribution"].get(k, 0) for k in ["operations", "supply_chain", "manufacturing", "logistics"])
        tech_like = sum(p["distribution"].get(k, 0) for k in ["engineering", "it", "product"])
        biz_like = sum(p["distribution"].get(k, 0) for k in ["finance", "analytics", "legal"])
        people_like = sum(p["distribution"].get(k, 0) for k in ["hr", "recruiting"])
        customer_like = sum(p["distribution"].get(k, 0) for k in ["sales", "marketing", "customer_support", "retail"])

        macro_counts = {k: v for k, v in [
            ("ops_manufacturing", ops_like),
            ("tech_product", tech_like),
            ("biz_finance", biz_like),
            ("people_talent", people_like),
            ("customer_growth", customer_like),
        ] if v > 0}

        if macro_counts:
            total = sum(macro_counts.values())
            top_macro = max(macro_counts.values())
            macro_share = top_macro / total if total > 0 else 0
            if macro_share >= 0.40 and p["share"] < 0.35:
                could_benefit_from_macro.append({
                    "name": p["name"],
                    "current_share": p["share"],
                    "macro_share": round(macro_share, 2),
                    "macro_dist": macro_counts,
                    "original_dist": p["distribution"],
                })

    print(f"\n  Companies that would benefit from macro-family grouping: {len(could_benefit_from_macro)}")
    for m in could_benefit_from_macro:
        print(f"    {m['name']}: current top share {m['current_share']:.0%} -> macro share {m['macro_share']:.0%}")
        print(f"      original: {m['original_dist']}")
        print(f"      macro:    {m['macro_dist']}")


if __name__ == "__main__":
    main()

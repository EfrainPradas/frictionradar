"""
Dataset Health Report — measures quality KPIs for the company dataset.

Reports coverage funnel, evidence bands, staleness, and composite health score.

Usage:
    cd backend
    python scripts/dataset_health.py              # full report
    python scripts/dataset_health.py --json        # JSON output for automation
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.positioning_engine import compute_eligibility_snapshot


def compute_health(db) -> dict:
    """Compute all dataset health KPIs."""

    # Total companies
    total = db.execute(text("SELECT COUNT(*) FROM companies")).scalar()
    if total == 0:
        return {"total": 0, "health_score": 0}

    # Domain coverage
    with_domain = db.execute(text(
        "SELECT COUNT(*) FROM companies WHERE domain IS NOT NULL AND domain != ''"
    )).scalar()

    # Collection coverage
    collected = db.execute(text(
        "SELECT COUNT(*) FROM companies WHERE last_collection_at IS NOT NULL"
    )).scalar()
    # Fallback if last_collection_at not yet backfilled
    if collected == 0:
        collected = db.execute(text("""
            SELECT COUNT(DISTINCT company_id) FROM collection_runs WHERE status = 'completed'
        """)).scalar()

    # Role detection
    with_roles = db.execute(text("""
        SELECT COUNT(DISTINCT company_id) FROM company_job_roles
        WHERE functional_area IS NOT NULL
        AND functional_area NOT IN ('junk', 'unknown')
        GROUP BY company_id HAVING COUNT(*) >= 2
    """)).rowcount or 0
    # Fix: the above returns rows not count
    with_roles_result = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT company_id FROM company_job_roles
            WHERE functional_area IS NOT NULL
            AND functional_area NOT IN ('junk', 'unknown')
            GROUP BY company_id HAVING COUNT(*) >= 2
        ) sub
    """)).scalar()

    # Total roles and classification quality
    total_roles = db.execute(text("SELECT COUNT(*) FROM company_job_roles")).scalar()
    classified_roles = db.execute(text("""
        SELECT COUNT(*) FROM company_job_roles
        WHERE functional_area IS NOT NULL AND functional_area NOT IN ('junk', 'unknown')
    """)).scalar()
    junk_roles = db.execute(text("""
        SELECT COUNT(*) FROM company_job_roles WHERE functional_area = 'junk'
    """)).scalar()

    # JD extraction
    roles_with_url = db.execute(text("""
        SELECT COUNT(*) FROM company_job_roles
        WHERE source_url IS NOT NULL AND source_url != ''
    """)).scalar()
    roles_with_jd = db.execute(text("""
        SELECT COUNT(*) FROM company_job_roles
        WHERE role_description IS NOT NULL AND role_description != ''
    """)).scalar()
    companies_with_jd = db.execute(text("""
        SELECT COUNT(DISTINCT company_id) FROM company_job_roles
        WHERE role_description IS NOT NULL AND role_description != ''
    """)).scalar()

    # Signal coverage
    with_signals = db.execute(text("""
        SELECT COUNT(DISTINCT company_id) FROM company_signals
    """)).scalar()

    # Dataset status distribution
    status_dist = dict(db.execute(text(
        "SELECT COALESCE(dataset_status, 'null'), COUNT(*) FROM companies GROUP BY 1 ORDER BY 2 DESC"
    )).fetchall())

    # Evidence band distribution (if view exists)
    evidence_bands = {}
    try:
        evidence_bands = dict(db.execute(text(
            "SELECT evidence_band, COUNT(*) FROM company_coverage GROUP BY 1"
        )).fetchall())
    except Exception:
        db.rollback()

    # Geography distribution
    geo_dist = dict(db.execute(text(
        "SELECT COALESCE(geography, 'unknown'), COUNT(*) FROM companies GROUP BY 1 ORDER BY 2 DESC"
    )).fetchall())

    # Industry fill rate (real industries, not entity types)
    with_industry = db.execute(text("""
        SELECT COUNT(*) FROM companies
        WHERE industry IS NOT NULL AND industry != ''
        AND LOWER(industry) NOT IN ('llc', 'corporation', 'nonprofit')
    """)).scalar()

    # Staleness (companies collected > 30 days ago)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stale_count = db.execute(text("""
        SELECT COUNT(*) FROM companies
        WHERE last_collection_at IS NOT NULL AND last_collection_at < :cutoff
    """), {"cutoff": stale_cutoff}).scalar()

    # Positioning eligible — uses canonical snapshot from positioning_engine
    # (NOT the stale companies.positioning_eligible column, which is never
    # written and always returns 0).
    elig_snapshot = compute_eligibility_snapshot(db)
    positioning_full = elig_snapshot["full"]
    positioning_conditional = elig_snapshot["conditional"]
    positioning_count = elig_snapshot["total_eligible"]

    # Diagnostic state distribution
    ds_dist = {}
    try:
        ds_dist = dict(db.execute(text(
            "SELECT COALESCE(latest_diagnostic_state, 'null'), COUNT(*) FROM companies GROUP BY 1 ORDER BY 2 DESC"
        )).fetchall())
    except Exception:
        db.rollback()

    # Classifier diagnostics (dataset-agnostic — works for any new dataset):
    # Family yield tells us which functional buckets carry real coverage
    # and where a new dataset might be hitting a blind spot.
    family_yield = dict(db.execute(text("""
        SELECT functional_area, COUNT(*)
        FROM company_job_roles
        WHERE functional_area IS NOT NULL
          AND functional_area NOT IN ('junk', 'unknown')
        GROUP BY functional_area
        ORDER BY 2 DESC
    """)).fetchall())

    # Roles with a valid title but no keyword match → classifier blind spot.
    no_keyword_roles = db.execute(text("""
        SELECT COUNT(*) FROM company_job_roles
        WHERE functional_area = 'unknown'
          AND functional_area_confidence LIKE 'low:no_keyword_match%'
    """)).scalar() or 0

    # Samples: top recurring titles that are still unknown (new family
    # candidates) vs. still reaching 'junk' (junk-filter candidates).
    # Uses role_title GROUP BY to surface patterns, not one-offs.
    sample_unknown_titles = [
        row[0] for row in db.execute(text("""
            SELECT role_title FROM company_job_roles
            WHERE functional_area = 'unknown' AND role_title IS NOT NULL
            GROUP BY role_title
            HAVING COUNT(*) >= 2
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """)).fetchall()
    ]
    sample_junk_titles = [
        row[0] for row in db.execute(text("""
            SELECT role_title FROM company_job_roles
            WHERE functional_area = 'junk' AND role_title IS NOT NULL
            GROUP BY role_title
            HAVING COUNT(*) >= 2
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """)).fetchall()
    ]

    no_keyword_rate = no_keyword_roles / max(total_roles, 1)

    # Compute rates
    domain_coverage = with_domain / total if total else 0
    collection_coverage = collected / total if total else 0
    role_detection_rate = with_roles_result / max(collected, 1)
    classification_quality = classified_roles / max(total_roles - junk_roles, 1) if total_roles > 0 else 0
    # Simpler: non-junk non-unknown / total non-junk
    classification_quality = classified_roles / max(classified_roles + db.execute(text(
        "SELECT COUNT(*) FROM company_job_roles WHERE functional_area = 'unknown' OR functional_area IS NULL"
    )).scalar(), 1)
    jd_extraction_rate = roles_with_jd / max(roles_with_url, 1) if roles_with_url > 0 else 0
    industry_fill = with_industry / total if total else 0
    stale_ratio = stale_count / max(collected, 1) if collected > 0 else 0

    # Composite health score
    health_score = round(
        0.15 * domain_coverage +
        0.20 * collection_coverage +
        0.25 * role_detection_rate +
        0.15 * classification_quality +
        0.15 * jd_extraction_rate +
        0.10 * (1 - stale_ratio),
        4
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_companies": total,
        "coverage_funnel": {
            "with_domain": with_domain,
            "collected": collected,
            "with_signals": with_signals,
            "with_roles_2plus": with_roles_result,
            "with_jds": companies_with_jd,
            "positioning_eligible": positioning_count,
            "positioning_eligible_full": positioning_full,
            "positioning_eligible_conditional": positioning_conditional,
        },
        "rates": {
            "domain_coverage": round(domain_coverage, 4),
            "collection_coverage": round(collection_coverage, 4),
            "role_detection_rate": round(role_detection_rate, 4),
            "classification_quality": round(classification_quality, 4),
            "jd_extraction_rate": round(jd_extraction_rate, 4),
            "industry_fill_rate": round(industry_fill, 4),
            "stale_ratio": round(stale_ratio, 4),
            "no_keyword_match_rate": round(no_keyword_rate, 4),
        },
        "classifier_diagnostics": {
            "family_yield": family_yield,
            "no_keyword_match_roles": no_keyword_roles,
            "sample_unknown_titles": sample_unknown_titles,
            "sample_junk_titles": sample_junk_titles,
        },
        "roles": {
            "total": total_roles,
            "classified": classified_roles,
            "junk": junk_roles,
            "with_jd": roles_with_jd,
            "with_url": roles_with_url,
        },
        "distributions": {
            "dataset_status": status_dist,
            "evidence_bands": evidence_bands,
            "geography": geo_dist,
            "diagnostic_state": ds_dist,
        },
        "health_score": health_score,
    }


def print_report(h: dict):
    print(f"\n{'='*70}")
    print(f"  DATASET HEALTH REPORT")
    print(f"  {h['generated_at']}")
    print(f"{'='*70}")

    print(f"\n  Health Score: {h['health_score']:.1%}")

    print(f"\n  Coverage Funnel:")
    funnel = h["coverage_funnel"]
    total = h["total_companies"]
    for key, val in funnel.items():
        pct = val / total * 100 if total else 0
        bar = "#" * int(pct / 2)
        print(f"    {key:25s}: {val:6d} ({pct:5.1f}%) {bar}")

    print(f"\n  Quality Rates:")
    for key, val in h["rates"].items():
        status = "OK" if val >= 0.5 else "LOW" if val >= 0.2 else "CRITICAL"
        print(f"    {key:30s}: {val:6.1%}  [{status}]")

    print(f"\n  Roles:")
    for key, val in h["roles"].items():
        print(f"    {key:20s}: {val}")

    if h["distributions"].get("dataset_status"):
        print(f"\n  Dataset Status:")
        for status, cnt in h["distributions"]["dataset_status"].items():
            print(f"    {status:20s}: {cnt}")

    if h["distributions"].get("evidence_bands"):
        print(f"\n  Evidence Bands:")
        for band, cnt in h["distributions"]["evidence_bands"].items():
            print(f"    {band:20s}: {cnt}")

    if h["distributions"].get("geography"):
        print(f"\n  Geography:")
        for geo, cnt in list(h["distributions"]["geography"].items())[:10]:
            print(f"    {geo:20s}: {cnt}")

    cd = h.get("classifier_diagnostics", {})
    if cd.get("family_yield"):
        print(f"\n  Family Yield (classified roles per functional area):")
        for fam, cnt in cd["family_yield"].items():
            print(f"    {fam:20s}: {cnt}")

    if cd.get("sample_unknown_titles"):
        print(f"\n  Top recurring UNKNOWN titles (classifier blind spots):")
        for title in cd["sample_unknown_titles"]:
            print(f"    - {title}")

    if cd.get("sample_junk_titles"):
        print(f"\n  Top recurring JUNK titles (filter validation):")
        for title in cd["sample_junk_titles"]:
            print(f"    - {title}")


def main():
    parser = argparse.ArgumentParser(description="Dataset health report")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of formatted report")
    args = parser.parse_args()

    db = SessionLocal()
    health = compute_health(db)
    db.close()

    if args.json:
        print(json.dumps(health, indent=2, default=str))
    else:
        print_report(health)


if __name__ == "__main__":
    main()

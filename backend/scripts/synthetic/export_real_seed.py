"""Export the real FrictionRadar corpus (companies + domains + roles) to a
JSON seed file. The synthetic generator consumes this file as the demographic
spine — synthetic companies copy real distribution shape (sector / size /
geography mix) without copying identity-bearing content.

Usage:
  python backend/scripts/synthetic/export_real_seed.py
  # writes: backend/data/synthetic/seed/real_seed.json

Read-only against the DB. No prod data is mutated.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

from sqlalchemy import text
from app.db.session import SessionLocal


SEED_VERSION = "seed-v1"
DEFAULT_OUT = BACKEND_ROOT / "data" / "synthetic" / "seed" / "real_seed.json"


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else dt.isoformat()


def export_companies(db) -> list[dict]:
    rows = db.execute(text("""
        SELECT
            id::text                AS id,
            name,
            domain,
            industry,
            company_size,
            geography,
            entity_type,
            priority_tier,
            dataset_status,
            careers_url,
            careers_accessibility,
            positioning_eligible,
            source_added_from,
            inferred_sector,
            inferred_sector_source,
            inferred_sector_confidence,
            last_collection_at,
            latest_diagnostic_state
        FROM companies
        WHERE domain IS NOT NULL AND domain <> ''
        ORDER BY name
    """)).mappings().all()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "domain": r["domain"],
            "industry": r["industry"],
            "company_size": r["company_size"],
            "geography": r["geography"],
            "entity_type": r["entity_type"],
            "priority_tier": r["priority_tier"],
            "dataset_status": r["dataset_status"],
            "careers_url": r["careers_url"],
            "careers_accessibility": r["careers_accessibility"],
            "positioning_eligible": r["positioning_eligible"],
            "source_added_from": r["source_added_from"],
            "inferred_sector": r["inferred_sector"],
            "inferred_sector_source": r["inferred_sector_source"],
            "inferred_sector_confidence": r["inferred_sector_confidence"],
            "last_collection_at": _iso(r["last_collection_at"]),
            "latest_diagnostic_state": r["latest_diagnostic_state"],
        }
        for r in rows
    ]


def export_roles(db) -> list[dict]:
    rows = db.execute(text("""
        SELECT
            company_id::text          AS company_id,
            role_title,
            role_location,
            role_department,
            role_description,
            functional_area,
            functional_area_confidence,
            source_url,
            discovered_at
        FROM company_job_roles
        ORDER BY company_id, discovered_at DESC NULLS LAST
    """)).mappings().all()
    return [
        {
            "company_id": r["company_id"],
            "role_title": r["role_title"],
            "role_location": r["role_location"],
            "role_department": r["role_department"],
            "role_description": r["role_description"],
            "functional_area": r["functional_area"],
            "functional_area_confidence": r["functional_area_confidence"],
            "source_url": r["source_url"],
            "discovered_at": _iso(r["discovered_at"]),
        }
        for r in rows
    ]


def export_domain_aliases(db) -> dict[str, list[str]]:
    """Map company_id → list of additional domains from the master index.

    The companies table holds a single canonical domain. The master index
    (company_domains) may track aliases / acquired-brand domains we want to
    preserve in the seed.
    """
    aliases: dict[str, list[str]] = {}
    try:
        rows = db.execute(text("""
            SELECT cd.company_master_id::text AS master_id, cd.domain
            FROM company_domains cd
            WHERE cd.domain IS NOT NULL AND cd.domain <> ''
        """)).mappings().all()
        for r in rows:
            aliases.setdefault(r["master_id"], []).append(r["domain"])
    except Exception:
        # Master index may not be present in this environment.
        return {}
    return aliases


def aggregate_distributions(companies: list[dict], roles: list[dict]) -> dict:
    """Cheap shape stats — useful sanity check pre-generation."""
    from collections import Counter

    sector_counts = Counter(c["inferred_sector"] or "(null)" for c in companies)
    geo_counts = Counter(c["geography"] or "(null)" for c in companies)
    size_counts = Counter(c["company_size"] or "(null)" for c in companies)
    fa_counts = Counter(r["functional_area"] or "(null)" for r in roles)

    roles_per_company = Counter(r["company_id"] for r in roles)
    roles_dist = Counter(roles_per_company.values())

    return {
        "sector_counts": dict(sector_counts.most_common()),
        "geography_counts": dict(geo_counts.most_common(20)),
        "company_size_counts": dict(size_counts.most_common()),
        "functional_area_counts": dict(fa_counts.most_common(20)),
        "roles_per_company_histogram": {str(k): v for k, v in sorted(roles_dist.items())},
        "companies_with_roles": sum(1 for c in companies if roles_per_company.get(c["id"], 0) > 0),
    }


def main(out_path: Path = DEFAULT_OUT) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        print("[export_real_seed] fetching companies...")
        companies = export_companies(db)
        print(f"  ->{len(companies)} companies")

        print("[export_real_seed] fetching roles...")
        roles = export_roles(db)
        print(f"  ->{len(roles)} roles")

        print("[export_real_seed] computing distributions...")
        distributions = aggregate_distributions(companies, roles)

        seed = {
            "schema_version": SEED_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "companies": len(companies),
                "roles": len(roles),
            },
            "distributions": distributions,
            "companies": companies,
            "roles": roles,
        }

        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(seed, fh, ensure_ascii=False, indent=2, default=str)

        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"[export_real_seed] wrote {out_path} ({size_mb:.2f} MB)")
        print("[export_real_seed] top sectors:")
        for sector, n in list(distributions["sector_counts"].items())[:8]:
            print(f"    {sector}: {n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

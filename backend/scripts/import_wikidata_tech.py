"""Import relevant tech companies from Wikidata SPARQL exports.

Sources:
  - C:\\Users\\ADM\\Downloads\\tech1.json (broad tech dump; filter by industry)
  - C:\\Users\\ADM\\Downloads\\tech2.json (curated AI/tech; keep all)

Logic:
  1. Load both files, dedupe by Wikidata Q-ID.
  2. Filter tech1 to only relevant industries (IT/Internet/cloud/software/AI).
  3. Extract domain from website URL.
  4. Dedupe against existing corpus by domain AND normalized_name.
  5. Insert with source_added_from='wikidata', dataset_status='imported',
     priority_tier=2, careers_accessibility='unknown'.

Usage (dry-run is default):
  python scripts/import_wikidata_tech.py --dry-run
  python scripts/import_wikidata_tech.py --execute
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.master.canonical import normalize_company_name


# Only these industries survive from tech1.json (rest is brewing, telco, retail, food)
RELEVANT_INDUSTRIES = {
    "information technology",
    "information technology consulting",
    "internet",
    "internet industry",
    "internet service provider",
    "cloud computing",
    "software",
    "software industry",
    "application software",
    "technology industry",
    "artificial intelligence",
    "saas",
    "service on internet",
    "computer hardware",
    "computer software",
    "fintech",
    "financial technology",
}

TECH1 = Path(r"C:\Users\ADM\Downloads\tech1.json")
TECH2 = Path(r"C:\Users\ADM\Downloads\tech2.json")


def extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower().strip()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def load_file(path: Path, filter_by_industry: bool):
    """Return dict[qid] -> {name, domain, industries:set}."""
    if not path.exists():
        print(f"  [WARN] {path} not found — skipping")
        return {}

    with open(path, "r", encoding="utf-8") as fh:
        rows = json.load(fh)

    by_q: dict[str, dict] = {}
    for r in rows:
        qid = r.get("company", "")
        if not qid:
            continue
        name = r.get("companyLabel", "").strip()
        if not name or name.startswith("Q"):  # Q-id-only fallback, no label
            continue
        website = r.get("website", "")
        industry = (r.get("industryLabel") or "").strip().lower()

        if qid not in by_q:
            by_q[qid] = {
                "name": name,
                "domain": extract_domain(website),
                "website": website,
                "industries": set(),
            }
        by_q[qid]["industries"].add(industry)

    if filter_by_industry:
        kept = {
            q: v
            for q, v in by_q.items()
            if v["industries"] & RELEVANT_INDUSTRIES
        }
        print(f"  {path.name}: {len(by_q)} unique → {len(kept)} relevant")
        return kept
    else:
        print(f"  {path.name}: {len(by_q)} unique (no filter)")
        return by_q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    print("Loading Wikidata exports...")
    t1 = load_file(TECH1, filter_by_industry=True)
    t2 = load_file(TECH2, filter_by_industry=False)

    merged: dict[str, dict] = {}
    merged.update(t1)
    for q, v in t2.items():
        if q in merged:
            merged[q]["industries"].update(v["industries"])
        else:
            merged[q] = v

    # Must have domain
    merged = {q: v for q, v in merged.items() if v["domain"]}
    print(f"\nMerged unique (with domain): {len(merged)}")

    db = SessionLocal()

    # Dedupe vs existing corpus
    existing_domains = {
        r[0].lower()
        for r in db.execute(
            text("SELECT domain FROM companies WHERE domain IS NOT NULL")
        ).fetchall()
    }
    existing_norms = {
        (r[0] or "").lower()
        for r in db.execute(
            text("SELECT normalized_name FROM companies WHERE normalized_name IS NOT NULL")
        ).fetchall()
    }

    new_rows = []
    dup_domain = 0
    dup_name = 0
    for qid, v in merged.items():
        dom = v["domain"].lower()
        norm = normalize_company_name(v["name"])
        if dom in existing_domains:
            dup_domain += 1
            continue
        if norm and norm in existing_norms:
            dup_name += 1
            continue
        new_rows.append(
            {
                "name": v["name"],
                "domain": dom,
                "normalized_name": norm,
                "industry": ", ".join(sorted(v["industries"]))[:200],
            }
        )

    print(f"\nDedupe vs corpus:")
    print(f"  duplicates by domain:  {dup_domain}")
    print(f"  duplicates by name:    {dup_name}")
    print(f"  NEW to insert:         {len(new_rows)}")

    print(f"\nSample 20 new:")
    for r in new_rows[:20]:
        print(f"  {r['name'][:35]:35s} {r['domain'][:30]:30s} [{r['industry'][:40]}]")

    if not args.execute:
        print("\n[DRY RUN] No changes. Re-run with --execute to insert.")
        db.close()
        return

    print("\nInserting...")
    inserted = 0
    for r in new_rows:
        try:
            db.execute(
                text(
                    """
                    INSERT INTO companies
                      (name, domain, industry, normalized_name,
                       source_added_from, dataset_status,
                       priority_tier, careers_accessibility, positioning_eligible)
                    VALUES
                      (:name, :domain, :industry, :normalized_name,
                       'wikidata', 'imported', 2, 'unknown', false)
                    ON CONFLICT (domain) DO NOTHING
                    """
                ),
                r,
            )
            inserted += 1
        except Exception as e:
            print(f"  [ERR] {r['name']}: {e}")
    db.commit()

    total = db.execute(text("SELECT COUNT(*) FROM companies")).scalar()
    print(f"\nInserted {inserted} companies. Corpus now: {total}")
    db.close()


if __name__ == "__main__":
    main()

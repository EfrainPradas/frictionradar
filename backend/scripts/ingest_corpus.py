"""End-to-end corpus ingestion from a JSON file.

Single command: you give it a JSON + source tag, it does everything:

  1. Parse JSON (auto-detect Wikidata vs generic format).
  2. Optionally filter by relevant industries (AI/SaaS/tech/fintech).
  3. Dedupe vs existing corpus (by domain + normalized_name).
  4. Insert new rows with source_added_from=<tag>.
  5. Export new rows as shard for parallel collection.
  6. Run full pipeline (careers -> extract -> classify -> evaluate) in parallel.
  7. Sanitize polluted titles + reclassify junk/unknown with current classifier.
  8. Print before/after eligibility delta + new eligibles.

Usage:
  python scripts/ingest_corpus.py --file C:/Users/ADM/Downloads/wikidata.json --source-tag wikidata_ai
  python scripts/ingest_corpus.py --file data/x.json --source-tag custom --industry-filter
  python scripts/ingest_corpus.py --file data/x.json --source-tag custom --processes 6
  python scripts/ingest_corpus.py --file data/x.json --source-tag custom --skip-collection

Supported JSON formats (auto-detected):
  A. Wikidata with website:  [{company, companyLabel, industryLabel, website, ...}]
  B. Wikidata with domain:   [{company, companyLabel, industryLabel, domain, ...}]
  C. Generic corpus:          [{name, domain, industry?}]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.master.canonical import normalize_company_name
from app.services.positioning_engine import compute_eligibility_snapshot


BACKEND_DIR = Path(__file__).resolve().parent.parent

# Industry whitelist for --industry-filter (matches tech1-like dumps)
RELEVANT_INDUSTRIES = {
    "information technology", "information technology consulting",
    "internet", "internet industry", "internet service provider",
    "cloud computing", "software", "software industry",
    "application software", "technology industry",
    "artificial intelligence", "saas", "service on internet",
    "computer hardware", "computer software",
    "fintech", "financial technology",
}


def extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower().strip()
        if not host and "://" not in url:
            host = url.lower().strip()
        if host.startswith("www."):
            host = host[4:]
        return host.strip("/")
    except Exception:
        return ""


def normalize_entries(rows: list, filter_industry: bool) -> list[dict]:
    """Accept any of the 3 formats and return [{name, domain, industry}]."""
    normalized: dict[str, dict] = {}  # keyed by domain to dedupe within file

    for r in rows:
        if not isinstance(r, dict):
            continue

        # --- Name ---
        name = (r.get("companyLabel") or r.get("name") or r.get("company_name") or "").strip()
        if not name or name.startswith("Q"):
            continue

        # --- Domain ---
        dom = (r.get("domain") or "").strip().lower()
        if not dom:
            dom = extract_domain(r.get("website", ""))
        if not dom:
            continue

        # --- Industry ---
        ind = (r.get("industryLabel") or r.get("industry") or "").strip().lower()

        if filter_industry and ind and ind not in RELEVANT_INDUSTRIES:
            continue

        # Dedupe within file by domain, accumulate industry labels
        if dom not in normalized:
            normalized[dom] = {"name": name, "domain": dom, "industries": set()}
        if ind:
            normalized[dom]["industries"].add(ind)

    out = []
    for d, v in normalized.items():
        out.append({
            "name": v["name"],
            "domain": d,
            "industry": ", ".join(sorted(v["industries"]))[:200],
        })
    return out


def insert_new_companies(db, entries: list[dict], source_tag: str) -> list[dict]:
    """Dedupe vs DB and insert new. Returns list of inserted rows with IDs."""
    existing_domains = {
        r[0].lower()
        for r in db.execute(text("SELECT domain FROM companies WHERE domain IS NOT NULL")).fetchall()
    }
    existing_norms = {
        (r[0] or "").lower()
        for r in db.execute(
            text("SELECT normalized_name FROM companies WHERE normalized_name IS NOT NULL")
        ).fetchall()
    }

    new = []
    dup_d = dup_n = 0
    for e in entries:
        dom = e["domain"].lower()
        norm = normalize_company_name(e["name"])
        if dom in existing_domains:
            dup_d += 1
            continue
        if norm and norm in existing_norms:
            dup_n += 1
            continue
        new.append({"name": e["name"], "domain": dom, "industry": e["industry"], "normalized_name": norm})

    print(f"  duplicates by domain: {dup_d}")
    print(f"  duplicates by name:   {dup_n}")
    print(f"  to insert:            {len(new)}")

    inserted_ids = []
    for r in new:
        try:
            row = db.execute(
                text("""
                    INSERT INTO companies
                      (name, domain, industry, normalized_name,
                       source_added_from, dataset_status,
                       priority_tier, careers_accessibility, positioning_eligible)
                    VALUES
                      (:name, :domain, :industry, :normalized_name,
                       :source_tag, 'imported', 2, 'unknown', false)
                    ON CONFLICT (domain) DO NOTHING
                    RETURNING id::text
                """),
                {**r, "source_tag": source_tag},
            ).first()
            if row:
                inserted_ids.append({"id": row[0], "name": r["name"], "domain": r["domain"], "roles": 0})
        except Exception as ex:
            print(f"  [ERR] {r['name']}: {ex}")
    db.commit()
    return inserted_ids


def export_targets(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def run_subprocess(cmd: list[str], label: str) -> int:
    print(f"\n--- {label} ---")
    print("   cmd:", " ".join(cmd))
    rc = subprocess.run(cmd, cwd=str(BACKEND_DIR)).returncode
    if rc != 0:
        print(f"   [WARN] {label} exited with code {rc}")
    return rc


def eligibility_totals(db) -> tuple[int, int, set]:
    snap = compute_eligibility_snapshot(db)
    ids = {str(c["company_id"]) for c in snap["by_company"] if c.get("eligible")}
    return snap["full"], snap["conditional"], ids


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="JSON file path")
    ap.add_argument("--source-tag", required=True, help="Value for source_added_from column")
    ap.add_argument("--industry-filter", action="store_true",
                    help="Keep only AI/SaaS/tech/fintech industries (reject cervecerías/telco/retail)")
    ap.add_argument("--processes", type=int, default=4, help="Parallel workers for collection")
    ap.add_argument("--run-id", default=None, help="Run identifier (default: auto-generated)")
    ap.add_argument("--skip-collection", action="store_true",
                    help="Only import + dedupe, don't run pipeline")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show parse/dedupe stats without inserting")
    args = ap.parse_args()

    run_id = args.run_id or f"ingest_{args.source_tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERR] File not found: {file_path}")
        sys.exit(1)

    print("=" * 70)
    print(f"  INGEST CORPUS: {file_path.name}")
    print(f"  source tag:        {args.source_tag}")
    print(f"  industry filter:   {args.industry_filter}")
    print(f"  processes:         {args.processes}")
    print(f"  run id:            {run_id}")
    print("=" * 70)

    # ── Phase 1: Parse ───────────────────────────────────────────────
    print("\n[1/6] Parsing JSON...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)

    if not isinstance(raw, list):
        print("[ERR] Expected a JSON array at top level")
        sys.exit(1)

    entries = normalize_entries(raw, filter_industry=args.industry_filter)
    print(f"  raw rows:          {len(raw)}")
    print(f"  normalized w/dom:  {len(entries)}")

    # Show industry distribution
    inds = Counter()
    for e in entries:
        for i in e["industry"].split(", "):
            if i:
                inds[i] += 1
    print(f"  top industries (first 5):")
    for ind, c in inds.most_common(5):
        print(f"    {c:>4d}  {ind}")

    if not entries:
        print("[WARN] No importable entries. Exiting.")
        sys.exit(0)

    if args.dry_run:
        print("\n[2/6] Dedupe preview (dry-run)...")
        db = SessionLocal()
        existing_domains = {
            r[0].lower() for r in db.execute(text("SELECT domain FROM companies WHERE domain IS NOT NULL")).fetchall()
        }
        existing_norms = {
            (r[0] or "").lower() for r in db.execute(text("SELECT normalized_name FROM companies WHERE normalized_name IS NOT NULL")).fetchall()
        }
        dup_d = sum(1 for e in entries if e["domain"] in existing_domains)
        dup_n = sum(1 for e in entries
                    if e["domain"] not in existing_domains
                    and normalize_company_name(e["name"]) in existing_norms)
        new = len(entries) - dup_d - dup_n
        db.close()
        print(f"  duplicates by domain: {dup_d}")
        print(f"  duplicates by name:   {dup_n}")
        print(f"  would insert:         {new}")
        print("\n[DRY RUN] No DB writes. Re-run without --dry-run.")
        return

    # ── Phase 2: Insert ──────────────────────────────────────────────
    print("\n[2/6] Inserting into corpus...")
    db = SessionLocal()
    full_before, cond_before, eligible_before = eligibility_totals(db)
    print(f"  eligibility snapshot (pre): full={full_before}  conditional={cond_before}")

    inserted = insert_new_companies(db, entries, source_tag=args.source_tag)
    corpus_now = db.execute(text("SELECT COUNT(*) FROM companies")).scalar()
    print(f"  inserted:       {len(inserted)}")
    print(f"  corpus now:     {corpus_now}")
    db.close()

    if not inserted:
        print("\n[INFO] Nothing new to insert (all duplicates). Exiting.")
        return

    if args.skip_collection:
        print("\n[SKIP] --skip-collection set. Import done, pipeline not run.")
        return

    # ── Phase 3: Export targets for parallel runner ──────────────────
    print("\n[3/6] Exporting targets for parallel pipeline...")
    targets_path = BACKEND_DIR / "output" / f"targets_{run_id}.json"
    export_targets(inserted, targets_path)
    print(f"  wrote: {targets_path}")

    # ── Phase 4: Parallel collection ─────────────────────────────────
    print(f"\n[4/6] Running pipeline with {args.processes} workers...")
    t0 = time.monotonic()
    run_subprocess(
        [sys.executable, "scripts/run_parallel_batch.py",
         "--input", str(targets_path),
         "--processes", str(args.processes),
         "--run-id", run_id],
        label="parallel pipeline",
    )
    print(f"  elapsed: {time.monotonic() - t0:.0f}s")

    # ── Phase 5: Sanitize + reclassify ───────────────────────────────
    print("\n[5/6] Cleaning polluted titles + reclassifying...")
    run_subprocess(
        [sys.executable, "scripts/sanitize_and_reclassify.py", "--execute"],
        label="sanitize titles",
    )
    run_subprocess(
        [sys.executable, "scripts/reclassify_unknowns.py", "--execute"],
        label="reclassify unknowns",
    )

    # ── Phase 6: Report eligibility delta ────────────────────────────
    print("\n[6/6] Final eligibility snapshot...")
    db = SessionLocal()
    full_after, cond_after, eligible_after = eligibility_totals(db)
    new_ids = eligible_after - eligible_before
    inserted_ids = {r["id"] for r in inserted}
    new_from_this_ingest = new_ids & inserted_ids

    # Get names for new eligibles
    if new_ids:
        rows = db.execute(text("""
            SELECT id::text AS id, name, domain FROM companies WHERE id::text = ANY(:ids)
        """), {"ids": list(new_ids)}).fetchall()
        new_eligibles_info = {str(r.id): (r.name, r.domain) for r in rows}
    else:
        new_eligibles_info = {}
    db.close()

    print("=" * 70)
    print(f"  ELIGIBILITY DELTA")
    print("=" * 70)
    print(f"  before:  full={full_before:3d}  conditional={cond_before:3d}  total={full_before + cond_before}")
    print(f"  after:   full={full_after:3d}  conditional={cond_after:3d}  total={full_after + cond_after}")
    print(f"  delta:   +{full_after - full_before:<2d} full, +{cond_after - cond_before:<2d} conditional")
    print(f"  net new eligibles across corpus:  {len(new_ids)}")
    print(f"  of which from this ingest:        {len(new_from_this_ingest)}")

    if new_ids:
        print(f"\n  New eligibles:")
        for cid in new_ids:
            name, dom = new_eligibles_info.get(cid, ("?", "?"))
            origin = "[ingest]" if cid in inserted_ids else "[reclassify]"
            print(f"    {origin} {name[:40]:40s} {dom}")

    print("=" * 70)
    print(f"\n  Artifacts:")
    print(f"    Run output:   output/parallel_runs/{run_id}/")
    print(f"    Targets file: {targets_path}")
    print()


if __name__ == "__main__":
    main()

"""Sample and categorize titles that landed in no_keyword_match.

Pulls all CompanyJobRole rows where functional_area='unknown' and
confidence contains 'no_keyword_match', then clusters them by heuristic
token patterns so we can see what keywords are missing.

Usage:
  python scripts/sample_no_keyword_match.py
  python scripts/sample_no_keyword_match.py --out runs/no_kw_sample.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.company_job_role import CompanyJobRole


# Rough token families — if a title contains ANY of these tokens, it hints
# at the likely missing keyword family. Order matters (first match wins).
PROBE_FAMILIES = [
    ("engineering", [
        "architect", "sdet", "fullstack", "back-end", "front-end",
        "ios", "android", "mobile", "embedded", "firmware", "reliability",
        "automation engineer", "test engineer", "qa", "quality engineer",
        "cybersecurity", "infosec", "devsecops", "cloud", "kubernetes",
        "salesforce developer", "salesforce engineer", "salesforce admin",
        "sap", "oracle developer", "etl developer",
    ]),
    ("data_analytics", [
        "data", "report", "analysis", "analytic", "statistic", "quant",
        "research scientist", "research analyst",
    ]),
    ("finance", [
        "accountant", "accounts", "payable", "receivable", "ledger",
        "audit", "tax", "revenue", "treasury", "collections",
    ]),
    ("operations", [
        "operations", "operator", "supervisor", "coordinator", "lead",
        "administrator", "admin", "assistant", "support specialist",
        "program", "project", "specialist", "planner",
    ]),
    ("supply_chain", [
        "warehouse", "forklift", "shipping", "receiving", "logistics",
        "truck", "driver", "dispatcher", "picker", "packer",
        "material handler", "loader",
    ]),
    ("manufacturing", [
        "machine", "operator", "technician", "assembly", "production",
        "welder", "fabricator", "mechanic", "shop", "press",
        "quality inspector", "qa inspector",
    ]),
    ("retail", [
        "clerk", "cashier", "associate", "stocker", "sales floor",
        "store", "shift", "shift lead", "shift supervisor", "crew",
        "barista", "server", "cook", "host",
    ]),
    ("customer_support", [
        "customer", "call center", "service rep", "service representative",
        "agent", "contact center", "concierge",
    ]),
    ("sales", [
        "sales", "account exec", "business development", "inside sales",
        "outside sales", "territory", "channel partner",
    ]),
    ("marketing", [
        "marketing", "brand", "content", "communications", "pr ",
        "copywriter", "designer", "graphic", "social",
    ]),
    ("product", [
        "product", "ux", "ui", "user experience", "user research",
    ]),
    ("hr_people", [
        "human resources", "hr ", "people", "compensation", "benefits",
        "payroll", "employee",
    ]),
    ("recruiting_talent", [
        "recruit", "talent", "sourcer", "staffing",
    ]),
    ("legal_compliance", [
        "legal", "attorney", "lawyer", "compliance", "regulatory",
        "paralegal", "contracts",
    ]),
    ("it", [
        "it ", "helpdesk", "help desk", "network", "sysadmin",
        "system admin", "desktop support",
    ]),
    ("healthcare", [
        "nurse", "rn", "lpn", "physician", "doctor", "md ",
        "pharmacist", "pharmacy", "medical", "clinical", "therapist",
        "radiology", "surgeon", "patient", "caregiver", "cna",
        "phlebotom", "respiratory", "dietitian", "sonographer",
    ]),
    ("education", [
        "teacher", "tutor", "instructor", "professor", "educator",
        "curriculum", "counselor", "principal", "coach",
    ]),
    ("construction_trades", [
        "electrician", "plumber", "carpenter", "roofer", "hvac",
        "installer", "construction", "laborer", "painter", "mason",
    ]),
    ("security_safety", [
        "security officer", "security guard", "patrol", "safety",
        "ehs", "environmental health",
    ]),
    ("transportation_driver", [
        "driver", "cdl", "chauffeur", "pilot", "conductor",
    ]),
    ("food_service", [
        "chef", "cook", "kitchen", "barista", "server", "bartender",
        "dishwasher", "host", "waitstaff",
    ]),
]


def categorize(title: str) -> tuple[str, str | None]:
    """Return (family, matched_probe_token). family='uncategorized' if none."""
    t = title.lower()
    for family, probes in PROBE_FAMILIES:
        for probe in probes:
            if re.search(r"\b" + re.escape(probe) + r"\b", t):
                return family, probe
    return "uncategorized", None


def tokenize(title: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", title.lower()) if len(w) >= 4]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/no_keyword_sample.json")
    ap.add_argument("--top", type=int, default=50,
                    help="Top N sample titles per family to preview")
    args = ap.parse_args()

    db = SessionLocal()
    q = (
        db.query(CompanyJobRole.role_title, CompanyJobRole.functional_area_confidence)
        .filter(CompanyJobRole.functional_area == "unknown")
        .filter(CompanyJobRole.functional_area_confidence.like("%no_keyword_match%"))
    )
    rows = q.all()
    print(f"Total no_keyword_match roles: {len(rows)}\n")

    family_titles: dict[str, list[str]] = defaultdict(list)
    family_probes: dict[str, Counter] = defaultdict(Counter)
    for title, _conf in rows:
        if not title:
            continue
        fam, probe = categorize(title)
        family_titles[fam].append(title)
        if probe:
            family_probes[fam][probe] += 1

    # Report
    print("=" * 70)
    print("FAMILY DISTRIBUTION (heuristic bucketing)")
    print("=" * 70)
    total = len(rows)
    families_sorted = sorted(family_titles.items(), key=lambda x: -len(x[1]))
    for fam, titles in families_sorted:
        pct = len(titles) / total * 100 if total else 0
        print(f"  {fam:25s}  {len(titles):4d}  ({pct:5.1f}%)")

    print()
    print("=" * 70)
    print("TOP PROBE TOKENS PER FAMILY (tells us what to add)")
    print("=" * 70)
    for fam, _ in families_sorted:
        if fam == "uncategorized":
            continue
        probes = family_probes[fam].most_common(10)
        if not probes:
            continue
        print(f"\n[{fam}]")
        for p, c in probes:
            print(f"  {c:4d}  {p}")

    # Sample titles per family
    print()
    print("=" * 70)
    print(f"SAMPLE TITLES (up to {args.top} per family)")
    print("=" * 70)
    for fam, titles in families_sorted:
        print(f"\n--- {fam} ({len(titles)}) ---")
        for t in titles[:args.top]:
            print(f"  {t}")

    # Uncategorized token frequency — surfaces missing domains
    uncat = family_titles.get("uncategorized", [])
    if uncat:
        print()
        print("=" * 70)
        print("UNCATEGORIZED — most frequent tokens (>=4 chars)")
        print("=" * 70)
        tok_counter: Counter = Counter()
        for t in uncat:
            tok_counter.update(tokenize(t))
        for tok, c in tok_counter.most_common(40):
            print(f"  {c:4d}  {tok}")

    # Dump payload
    out_path = Path(__file__).resolve().parents[1] / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total": total,
        "family_counts": {k: len(v) for k, v in family_titles.items()},
        "family_probes": {k: dict(v) for k, v in family_probes.items()},
        "samples": {k: v[:args.top] for k, v in family_titles.items()},
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path}")

    db.close()


if __name__ == "__main__":
    main()

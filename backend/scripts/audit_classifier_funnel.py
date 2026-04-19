"""Audit the classifier funnel after the full_p12_v2_pw run.

Answers the diagnostic questions:
  1. How many roles exist total? How many classified / junk / unknown / null?
  2. Which companies have JDs but no classified roles?
  3. What raw titles are failing (junk/unknown) vs passing?
  4. Eligibility counter bug: how many companies ACTUALLY hit ELIGIBLE_DS vs only ready_for_positioning?

Read-only. No DB writes.
"""
from __future__ import annotations

import sys
import os
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.services.function_inference_engine import function_inference_engine, _is_junk_title
from app.services.title_normalizer import is_valid_job_title, _rejection_reason
from app.services.company_evaluation import CompanyEvaluationEngine
from app.services.positioning_engine import ELIGIBLE_DS

eval_engine = CompanyEvaluationEngine()

db = SessionLocal()

print("=" * 80)
print("STAGE 1 — ROLE INVENTORY")
print("=" * 80)

total_roles = db.query(func.count(CompanyJobRole.id)).scalar()
with_desc = db.query(func.count(CompanyJobRole.id)).filter(
    CompanyJobRole.role_description.isnot(None)
).scalar()

area_counts = dict(
    db.query(CompanyJobRole.functional_area, func.count(CompanyJobRole.id))
    .group_by(CompanyJobRole.functional_area)
    .all()
)
print(f"Total CompanyJobRole rows: {total_roles}")
print(f"Rows with role_description: {with_desc}")
print("\nFunctional area distribution:")
for area, count in sorted(area_counts.items(), key=lambda x: -x[1]):
    pct = count / total_roles * 100 if total_roles else 0
    print(f"  {area or 'NULL':20s}  {count:5d}  ({pct:5.1f}%)")

print("\nConfidence distribution:")
conf_counts = dict(
    db.query(CompanyJobRole.functional_area_confidence, func.count(CompanyJobRole.id))
    .group_by(CompanyJobRole.functional_area_confidence)
    .all()
)
for conf, count in sorted(conf_counts.items(), key=lambda x: -x[1]):
    print(f"  {conf or 'NULL':10s}  {count}")

print()
print("=" * 80)
print("STAGE 2 — FAILURE MODE SAMPLE (100 raw titles)")
print("=" * 80)

# Sample junk
junk_rows = (
    db.query(CompanyJobRole.role_title, Company.name)
    .join(Company, CompanyJobRole.company_id == Company.id)
    .filter(CompanyJobRole.functional_area == "junk")
    .limit(40)
    .all()
)
print(f"\n-- 40 JUNK titles --")
for title, company in junk_rows:
    # Which junk pattern matched?
    from app.services.function_inference_engine import _JUNK_PATTERNS
    hit = next((p for p in _JUNK_PATTERNS if p in (title or "").lower()), None)
    reason = "junk_title"
    if hit is None:
        # maybe invalid_title path
        if not is_valid_job_title(title or ""):
            reason = f"invalid_title:{_rejection_reason(title or '')}"
    print(f"  [{reason:35s}] [{(company or '')[:25]:25s}] {(title or '')[:90]}")

# Sample unknown
unknown_rows = (
    db.query(CompanyJobRole.role_title, Company.name, CompanyJobRole.role_description)
    .join(Company, CompanyJobRole.company_id == Company.id)
    .filter(CompanyJobRole.functional_area == "unknown")
    .limit(40)
    .all()
)
print(f"\n-- 40 UNKNOWN titles (raw title, should have matched something) --")
for title, company, desc in unknown_rows:
    print(f"  [{(company or '')[:25]:25s}] {(title or '')[:90]}")

# Sample classified
classified_rows = (
    db.query(
        CompanyJobRole.role_title,
        CompanyJobRole.functional_area,
        CompanyJobRole.functional_area_confidence,
        Company.name,
    )
    .join(Company, CompanyJobRole.company_id == Company.id)
    .filter(
        CompanyJobRole.functional_area.isnot(None),
        ~CompanyJobRole.functional_area.in_(["junk", "unknown"]),
    )
    .limit(20)
    .all()
)
print(f"\n-- 20 CLASSIFIED titles (sample of the 'good' ones) --")
for title, area, conf, company in classified_rows:
    print(f"  [{area:18s} {conf or '?':8s}] [{(company or '')[:20]:20s}] {(title or '')[:90]}")

print()
print("=" * 80)
print("STAGE 3 — RECLASSIFICATION OF UNKNOWN/JUNK ON THE FLY")
print("=" * 80)
# For all unknown/null/junk titles, see what infer_functional_area returns now.
# This tells us if the current classifier would do BETTER if we re-ran it.
sample = (
    db.query(CompanyJobRole.role_title, CompanyJobRole.role_description, CompanyJobRole.functional_area)
    .filter(CompanyJobRole.functional_area.in_(["junk", "unknown"]))
    .limit(300)
    .all()
)

reclass_counter = Counter()
for title, desc, current_area in sample:
    r = function_inference_engine.infer_functional_area(title, desc)
    key = f"{current_area}->{r['area']}"
    reclass_counter[key] += 1

print(f"\nSampled {len(sample)} junk/unknown rows, re-ran inference (should match current state):")
for k, v in reclass_counter.most_common():
    print(f"  {k:30s}  {v}")

print()
print("=" * 80)
print("STAGE 4 — ELIGIBILITY COUNTER BUG TEST")
print("=" * 80)
# For all companies, compute diagnostic_state and count how many would be eligible
# under ELIGIBLE_DS (full gate from positioning_engine) vs only ready_for_positioning.
companies = db.query(Company).all()
ds_counts = Counter()
eligible_broad = 0  # ELIGIBLE_DS
eligible_strict = 0  # only ready_for_positioning
eligible_conditional = 0  # broad_hiring_pattern_detected

for c in companies:
    try:
        ev = eval_engine.evaluate(company_id=c.id, db=db)
        ds = ev.get("diagnostic_state", "")
    except Exception as e:
        ds = f"error:{type(e).__name__}"
    ds_counts[ds] += 1
    if ds in ELIGIBLE_DS:
        eligible_broad += 1
    if ds == "ready_for_positioning":
        eligible_strict += 1
    if ds == "broad_hiring_pattern_detected":
        eligible_conditional += 1

print(f"\nDiagnostic state distribution across {len(companies)} companies:")
for ds, count in ds_counts.most_common():
    print(f"  {ds:40s}  {count}")

print(f"\nCounter comparison:")
print(f"  batch_runner counts (only ready_for_positioning): {eligible_strict}")
print(f"  ELIGIBLE_DS (ready + specific_pain_*):            {eligible_broad}")
print(f"  + broad_hiring_pattern_detected (conditional):    {eligible_conditional}")
print(f"  TOTAL potentially eligible:                        {eligible_broad + eligible_conditional}")

print()
print("=" * 80)
print("STAGE 5 — CARRIES+0 CLASSIFIED COMPANIES (funnel leak)")
print("=" * 80)
# Companies with >=5 roles but 0 classified (not junk/unknown)
subq = (
    db.query(
        CompanyJobRole.company_id,
        func.count(CompanyJobRole.id).label("total"),
        func.sum(
            func.cast(
                (CompanyJobRole.functional_area.notin_(["junk", "unknown"])) &
                (CompanyJobRole.functional_area.isnot(None)),
                type_=__import__("sqlalchemy").Integer,
            )
        ).label("classified"),
    )
    .group_by(CompanyJobRole.company_id)
    .subquery()
)
rows = (
    db.query(Company.name, subq.c.total, subq.c.classified)
    .join(subq, Company.id == subq.c.company_id)
    .filter(subq.c.total >= 3)
    .filter(subq.c.classified == 0)
    .limit(30)
    .all()
)
print(f"\nCompanies with 3+ roles but 0 classified (first 30):")
for name, total, classified in rows:
    print(f"  {(name or '')[:30]:30s}  total={total}  classified={classified or 0}")

db.close()
print("\nDONE.")

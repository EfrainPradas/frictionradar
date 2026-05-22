"""FrictionRadar synthetic dataset generator (v1).

Consumes:
  - backend/data/synthetic/seed/real_seed.json   (real shape calibration)
  - backend/scripts/synthetic/archetypes.yaml    (parameter packs)

Produces (under backend/data/synthetic/<dataset_version>/):
  - companies.json
  - roles.json
  - signals.json
  - manifest.json

Design notes:
  - D1 (storage): JSON sidecar only. NO database writes.
  - D2 (distribution): n per archetype defined in archetypes.yaml.
  - D3 (null friction): allowed in synthetic_meta when score_band starts at 0.
  - D4 (window): T0=2025-04-01, T1=2026-04-01 (12 months).
  - D5 (no LLM): templates only, deterministic, offline.
  - Hybrid demographics: archetype weights drive sector/geo/size, calibrated
    against real seed when the sector exists in the real corpus.

Usage:
  python backend/scripts/synthetic/generate_dataset.py
  python backend/scripts/synthetic/generate_dataset.py --seed 42 --version synth-2026-04-27-v1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
DEFAULT_SEED_PATH = BACKEND_ROOT / "data" / "synthetic" / "seed" / "real_seed.json"
DEFAULT_ARCH_PATH = BACKEND_ROOT / "scripts" / "synthetic" / "archetypes.yaml"
DEFAULT_OUT_ROOT = BACKEND_ROOT / "data" / "synthetic"

GENERATOR_VERSION = "0.1.0"

# Closed vocabularies — see backend/docs/synthetic_data_spec.md §0
SECTORS = [
    "Software & SaaS", "AI & Machine Learning", "Semiconductors & Hardware",
    "Fintech & Financial Services", "Ecommerce & Consumer", "Healthcare & Biotech",
    "Media & Entertainment", "Gaming", "Retail & Hospitality",
    "Manufacturing & Industrial", "Logistics & Transportation",
    "Telco & Internet Infra", "Education", "Real Estate & Construction",
    "Energy & Utilities", "Professional Services", "Other",
]
DIAGNOSTIC_STATES = {
    "insufficient_evidence", "broad_hiring_pattern_detected",
    "specific_pain_emerging", "specific_pain_identified",
    "ready_for_positioning",
}
FRICTION_TYPES = {
    "reporting_fragmentation", "process_inefficiency", "tooling_inconsistency",
    "scaling_strain", "customer_experience_friction",
}
ELIGIBILITY_GATES = {"full", "conditional", "blocked", "none"}


# ─── Templates (no LLM) ─────────────────────────────────────────────────

NAME_PREFIXES = [
    "Helix", "Vortex", "Arcadia", "Quantum", "Mosaic", "Forge", "Apex",
    "Cipher", "Lumen", "Nexus", "Atlas", "Beacon", "Citrine", "Drift",
    "Ember", "Fjord", "Granite", "Harbor", "Indigo", "Junction",
]
NAME_SUFFIXES = {
    "Software & SaaS": ["Cloud", "Stack", "Hub", "Sync", "Ops", "Labs"],
    "AI & Machine Learning": ["AI", "ML", "Compute", "Cortex", "Mind"],
    "Fintech & Financial Services": ["Capital", "Pay", "Ledger", "Bank", "Finance"],
    "Healthcare & Biotech": ["Health", "Bio", "Therapeutics", "Clinical"],
    "Media & Entertainment": ["Media", "Studios", "Press", "Network"],
    "Gaming": ["Studios", "Games", "Interactive", "Worlds"],
    "Retail & Hospitality": ["Retail", "Hospitality", "Group", "Brands"],
    "Manufacturing & Industrial": ["Industries", "Manufacturing", "Works"],
    "Logistics & Transportation": ["Logistics", "Freight", "Transport"],
    "Telco & Internet Infra": ["Networks", "Telecom", "Comms"],
    "Education": ["Learning", "Press", "Edu", "Academy"],
    "Real Estate & Construction": ["Realty", "Construction", "Development"],
    "Energy & Utilities": ["Energy", "Power", "Utilities"],
    "Professional Services": ["Advisory", "Partners", "Consulting"],
    "Semiconductors & Hardware": ["Semi", "Hardware", "Devices", "Silicon"],
    "Ecommerce & Consumer": ["Goods", "Marketplace", "Direct"],
    "Other": ["Group", "Co", "Holdings"],
}

ROLE_TITLES_BY_FA = {
    "engineering": [
        "Senior Backend Engineer", "Staff Software Engineer",
        "Engineering Manager", "Senior Frontend Engineer",
        "Principal Engineer", "Site Reliability Engineer",
        "Mobile Engineer (iOS)", "Backend Engineer, Payments",
    ],
    "product": [
        "Senior Product Manager", "Group Product Manager",
        "Principal PM, Platform", "Director of Product",
    ],
    "data": [
        "Senior Data Scientist", "Staff Data Engineer",
        "Analytics Engineer", "Director of Data",
    ],
    "sales": [
        "Account Executive", "Senior Account Executive",
        "Sales Development Representative", "Director of Sales",
        "Enterprise Account Executive",
    ],
    "marketing": [
        "Senior Marketing Manager", "Content Marketing Lead",
        "Performance Marketing Manager", "Director of Demand Gen",
    ],
    "operations": [
        "Operations Manager", "Director of Operations",
        "Revenue Operations Lead", "Business Operations Analyst",
    ],
    "customer_success": [
        "Customer Success Manager", "Senior CSM, Enterprise",
        "Director of Customer Success",
    ],
    "finance": [
        "Senior Financial Analyst", "FP&A Manager",
        "Controller", "Director of Finance",
    ],
    "editorial": [
        "Senior Editor", "Acquisitions Editor", "Managing Editor",
    ],
    "content": [
        "Content Strategist", "Content Producer", "Senior Copywriter",
    ],
    "teaching": [
        "Curriculum Designer", "Instructional Designer", "Senior Course Author",
    ],
    "other": [
        "Office Manager", "People Operations Specialist",
        "Recruiter", "IT Support Specialist",
    ],
}

LOCATION_BY_GEO = {
    "US-CA": ["San Francisco, CA", "Palo Alto, CA", "San Jose, CA", "Los Angeles, CA"],
    "US-NY": ["New York, NY", "Brooklyn, NY"],
    "US-multi": ["Austin, TX", "Denver, CO", "Chicago, IL", "Boston, MA",
                 "Seattle, WA", "Atlanta, GA", "Remote (US)"],
    "EU": ["Berlin, Germany", "London, UK", "Amsterdam, Netherlands",
           "Paris, France", "Dublin, Ireland", "Remote (EU)"],
    "UK": ["London, UK", "Manchester, UK", "Edinburgh, UK"],
    "LATAM": ["Mexico City, Mexico", "São Paulo, Brazil", "Bogotá, Colombia",
              "Buenos Aires, Argentina"],
    "APAC": ["Tokyo, Japan", "Singapore", "Sydney, Australia"],
    "ES": ["Madrid, Spain", "Barcelona, Spain"],
    "MX": ["Mexico City, Mexico", "Guadalajara, Mexico"],
    "IN": ["Bangalore, India", "Mumbai, India"],
    "Other": ["Remote (Global)"],
}

# Friction signature → list of (signal_type, signal_text, functional_area).
# All variants of a signature are emitted (not sampled) to give the scoring
# engine multiple matched rules per signature.
SIGNATURE_TO_SIGNALS: dict[str, list[tuple[str, str, str | None]]] = {
    "high_eng_concentration": [
        ("engineering_concentration_high",
         "Engineering team accounts for 55% of all open roles", "engineering"),
        ("technology_hiring_detected",
         "Heavy concentration of backend and platform engineering hires", "engineering"),
        ("software_engineering_hiring_detected",
         "Multiple senior software engineering openings detected", "engineering"),
    ],
    "monotone_role_growth": [
        ("high_hiring_volume",
         "Hiring volume grew 30% quarter-over-quarter", None),
        ("growth_language_detected",
         "Company is scaling rapidly across functions", None),
        ("multiple_open_roles",
         "20+ open positions, hiring across engineering and product", None),
    ],
    "evergreen_long_ttl": [
        ("multiple_open_roles",
         "12 open roles aged >180 days, multiple openings", None),
        ("process_language_detected",
         "Manual coordination across teams creates handoff bottlenecks", None),
        ("operations_concentration_high",
         "Operations roles dominate hiring with workflow ownership", "operations"),
    ],
    "repost_cycles_3plus": [
        ("process_language_detected",
         "Repost cycles indicate workflow bottleneck in hiring process", None),
        ("operations_hiring_detected",
         "Continuous reposting of operations and ops manager roles", "operations"),
    ],
    "title_downleveling": [
        ("growth_language_detected",
         "Recently downleveled senior roles to mid-level after scaling pause", None),
        ("technology_hiring_detected",
         "Refilling engineering org at lower seniority bands", "engineering"),
    ],
    "q4_close_q1_reopen": [
        ("growth_language_detected",
         "Layoff in Q4 followed by aggressive Q1 hiring expansion", None),
        ("high_hiring_volume",
         "Q1 hiring spike across engineering and product after Q4 reduction", None),
    ],
    "rapid_open_close_reopen": [
        ("multiple_open_roles",
         "Sales reqs cycle every 14-30 days, multiple openings", "sales"),
        ("operations_hiring_detected",
         "RevOps and sales operations churning through roles", "operations"),
    ],
    "sales_role_churn": [
        ("technology_hiring_detected",
         "Heavy hiring of Salesforce admins and HubSpot specialists", "engineering"),
        ("engineering_concentration_high",
         "Sales/CRM tooling team 30% of engineering hires", "engineering"),
        ("revops_role_detected",
         "RevOps and revenue operations leadership openings", "operations"),
    ],
    "small_team_role_concentration": [
        ("analytics_role_detected",
         "Hiring data analyst to consolidate editorial reporting", "data"),
        ("reporting_language_detected",
         "Quarterly reporting and dashboard ownership in scope", None),
    ],
    "editorial_content_imbalance": [
        ("reporting_language_detected",
         "Need clearer reporting and metrics on content KPIs", None),
        ("data_hiring_detected",
         "Hiring analytics support for editorial visibility", "data"),
    ],
    "clear_pain_signal_cluster": [
        ("growth_language_detected",
         "Series C high-growth phase, scaling product org", None),
        ("high_hiring_volume",
         "Multiple open roles across engineering, product, and data", None),
        ("newsroom_found",
         "Series C funding announced; expansion to EU and APAC", None),
        ("software_engineering_hiring_detected",
         "Critical engineering hires for platform scale-out", "engineering"),
    ],
    "high_eng_data_concentration": [
        ("engineering_concentration_high",
         "Engineering and data combined are 60% of all roles", "engineering"),
        ("data_hiring_detected",
         "Heavy hiring in data and analytics team", "data"),
        ("analytics_role_detected",
         "Multiple analytics engineer and data scientist openings", "data"),
    ],
    # No-op signatures (intentional — arquetipo de bajo score):
    "third_party_listing_pattern": [],
    "extreme_function_dispersion": [],
    "critical_only_label": [],
    "flat_role_count": [],
}

# Ambient signals — emitted independently of friction_signatures, calibrated
# by `signal_density`. These reflect background "noise" the real collector
# would pick up: company description language, careers page boilerplate.
#
# Pools are scoped by expected_dominant_friction_type so ambient noise does
# not bleed into a different category (e.g. analytics_role_detected hitting
# reporting_fragmentation when the archetype targets scaling_strain).
_AMBIENT_DENSITY_COUNT = {
    "very_high": (6, 8),
    "high":      (4, 6),
    "moderate":  (2, 4),
    "low":       (0, 1),
    "very_low":  (0, 0),
}
_AMBIENT_POOL_BY_FRICTION: dict[str, list[tuple[str, str, str | None]]] = {
    "scaling_strain": [
        ("growth_language_detected",
         "Mission statement emphasizes growth and expanding our team", None),
        ("multiple_open_roles",
         "Careers page lists multiple open positions", None),
        ("growth_language_detected",
         "We are scaling rapidly across the org", None),
        ("high_hiring_volume",
         "High volume of open roles signals fast scaling phase", None),
        ("newsroom_found",
         "Recent funding round announced; expansion underway", None),
        ("multiple_open_roles",
         "We are growing — join our team across multiple openings", None),
        ("growth_language_detected",
         "High growth phase, hiring across functions", None),
        ("newsroom_found",
         "Series funding raised; headcount expansion planned", None),
    ],
    "reporting_fragmentation": [
        ("analytics_role_detected",
         "Analytics and reporting infrastructure investment ongoing", "data"),
        ("data_hiring_detected",
         "Data team is expanding with multiple analytics roles", "data"),
        ("reporting_language_detected",
         "Quarterly reporting cadence mentioned in role descriptions", None),
        ("reporting_language_detected",
         "Visibility and dashboard ownership across teams", None),
        ("analytics_role_detected",
         "Hiring business intelligence analysts to consolidate reporting", "data"),
        ("multiple_open_roles",
         "Multiple openings in data and analytics teams", None),
        ("data_hiring_detected",
         "Analytics and BI team expansion in progress", "data"),
        ("reporting_language_detected",
         "Metrics and quarterly reporting ownership in scope", None),
    ],
    "process_inefficiency": [
        ("process_language_detected",
         "Manual coordination and workflow handoffs cause bottlenecks", None),
        ("operations_hiring_detected",
         "Operations and program management roles open", "operations"),
        ("revops_role_detected",
         "Revenue operations and ops leadership openings", "operations"),
        ("process_language_detected",
         "Spreadsheet and ad hoc workflow consolidation needed", None),
        ("operations_hiring_detected",
         "Ops manager and business operations roles open", "operations"),
        ("process_language_detected",
         "Process and workflow ownership critical for this role", None),
        ("operations_concentration_high",
         "Operations roles dominate hiring this quarter", "operations"),
        ("multiple_open_roles",
         "Multiple operations openings detected on careers page", None),
    ],
    "tooling_inconsistency": [
        ("technology_hiring_detected",
         "Engineering and technology roles dominate the careers page", "engineering"),
        ("software_engineering_hiring_detected",
         "Multiple software engineering openings detected", "engineering"),
        ("engineering_concentration_high",
         "Engineering team dominates current hiring", "engineering"),
        ("technology_hiring_detected",
         "Salesforce, HubSpot, and tooling integration work in scope", "engineering"),
        ("software_engineering_hiring_detected",
         "Backend and platform engineering hires across teams", "engineering"),
        ("engineering_concentration_moderate",
         "Engineering hires are a steady share of open roles", "engineering"),
        ("technology_hiring_detected",
         "Tool stack consolidation and platform integration projects", "engineering"),
        ("multiple_open_roles",
         "Multiple engineering openings on the careers page", None),
    ],
    "customer_experience_friction": [
        ("customer_success_hiring_detected",
         "Customer success team is hiring", "customer_success"),
        ("customer_support_concentration_high",
         "Customer support roles dominate hiring", "customer_success"),
        ("customer_success_hiring_detected",
         "CSM and enterprise customer success roles open", "customer_success"),
        ("multiple_open_roles",
         "Multiple openings across customer-facing teams", None),
    ],
    # Used for archetypes with no targeted dominant (noise_floor, intermediary,
    # hiring_freeze). Generic, non-friction-leaning surface text.
    "_generic": [
        ("multiple_open_roles",
         "Careers page lists open positions", None),
        ("growth_language_detected",
         "We continue to grow our team", None),
    ],
}


# ─── Helpers ────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    vals = list(weights.values())
    return rng.choices(keys, weights=vals, k=1)[0]


def _lognormal_ttl(rng: random.Random, p50: int, p95: int) -> int:
    """Sample a TTL in days from a log-normal whose median = p50 and 95th ≈ p95."""
    mu = math.log(p50)
    # 1.645 = z-score for 95th percentile of standard normal
    sigma = max(0.01, (math.log(p95) - mu) / 1.645)
    val = rng.lognormvariate(mu, sigma)
    return max(1, int(round(val)))


def _sha256_of(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _archetype_rng(master_seed: int, archetype_id: str) -> random.Random:
    """Per-archetype sub-seed for stable diffs when one archetype changes."""
    h = hashlib.sha256(f"{master_seed}::{archetype_id}".encode()).hexdigest()
    return random.Random(int(h[:16], 16))


# ─── Calibration from real seed ─────────────────────────────────────────

def calibrate_from_seed(seed_data: dict) -> dict:
    """Per-sector marginals from the real corpus. Used to softly bias
    archetype-driven samples toward observed real-world shape."""
    by_sector_size: dict[str, Counter] = defaultdict(Counter)
    by_sector_geo: dict[str, Counter] = defaultdict(Counter)
    for c in seed_data.get("companies", []):
        sector = c.get("inferred_sector") or "Other"
        if c.get("company_size"):
            by_sector_size[sector][c["company_size"]] += 1
        if c.get("geography"):
            by_sector_geo[sector][c["geography"]] += 1
    return {
        "size_by_sector": {k: dict(v) for k, v in by_sector_size.items()},
        "geo_by_sector": {k: dict(v) for k, v in by_sector_geo.items()},
    }


# ─── Company / role generation ──────────────────────────────────────────

def _gen_name_and_domain(rng: random.Random, sector: str, idx: int) -> tuple[str, str]:
    prefix = rng.choice(NAME_PREFIXES)
    suffix = rng.choice(NAME_SUFFIXES.get(sector, ["Co"]))
    name = f"{prefix} {suffix}"
    slug = _slug(f"{prefix}-{suffix}-{idx:04d}")
    domain = f"synth-{slug}.test"
    return name, domain


def _gen_size_band(rng: random.Random, archetype: dict) -> str:
    lo, hi = archetype["demographics"]["size_band"]
    val = rng.randint(lo, hi)
    if val < 50:
        return "1-50"
    if val < 200:
        return "51-200"
    if val < 1000:
        return "201-1000"
    if val < 5000:
        return "1001-5000"
    if val < 10000:
        return "5001-10000"
    return "10000+"


def _gen_location(rng: random.Random, geo: str) -> str:
    pool = LOCATION_BY_GEO.get(geo, ["Remote (Global)"])
    return rng.choice(pool)


def _phase_lambda_for(archetype: dict, day: date) -> float:
    """For archetypes with `cohort_phases`, return the lambda modifier active
    at `day`. Otherwise returns 1.0."""
    bp = archetype.get("behavioral_pattern", {})
    phases = bp.get("cohort_phases")
    if not phases:
        return 1.0
    for ph in phases:
        start, end = ph["window"]
        if isinstance(start, str):
            start = date.fromisoformat(start)
        if isinstance(end, str):
            end = date.fromisoformat(end)
        if start <= day <= end:
            return float(ph.get("lambda_modifier", 1.0))
    return 1.0


def _generate_roles(
    rng: random.Random,
    archetype: dict,
    company: dict,
    t0: date,
    t1: date,
) -> list[dict]:
    rg = archetype["roles_generation"]
    fa_mix = rg["functional_area_mix"]
    ttl_p50 = rg["ttl_open_days"]["p50"]
    ttl_p95 = rg["ttl_open_days"]["p95"]
    p_repost = rg["repost_probability"]
    p_drift = rg["title_drift_probability"]
    p_evergreen = rg["evergreen_probability"]
    base_lambda_quarter = rg["poisson_lambda_quarter"]

    roles: list[dict] = []

    # Walk quarter by quarter so cohort_phases can modulate lambda.
    cur = t0
    while cur < t1:
        q_end = min(cur + timedelta(days=92), t1)
        phase_mod = _phase_lambda_for(archetype, cur)
        lam = base_lambda_quarter * phase_mod
        n_new = rng.gauss(lam, max(1.0, lam * 0.25))
        n_new = max(0, int(round(n_new)))

        for _ in range(n_new):
            fa = _weighted_choice(rng, fa_mix)
            title_pool = ROLE_TITLES_BY_FA.get(fa, ROLE_TITLES_BY_FA["other"])
            base_title = rng.choice(title_pool)

            # First post within this quarter
            span_days = max(1, (q_end - cur).days)
            first_posted = cur + timedelta(days=rng.randint(0, span_days - 1))

            is_evergreen = rng.random() < p_evergreen
            ttl = _lognormal_ttl(rng, ttl_p50, ttl_p95)
            if is_evergreen:
                ttl = max(ttl, 365)
            last_seen = min(t1, first_posted + timedelta(days=ttl))

            # Reposts
            repost_count = 0
            cur_first = first_posted
            cur_last = last_seen
            title_drift_history = []
            current_title = base_title
            while (
                cur_last < t1
                and rng.random() < p_repost
                and repost_count < 5
            ):
                repost_count += 1
                gap = rng.randint(15, 60)
                next_first = cur_last + timedelta(days=gap)
                if next_first >= t1:
                    break
                next_ttl = _lognormal_ttl(rng, ttl_p50, ttl_p95)
                if rng.random() < p_drift:
                    drifted = current_title.replace("Senior ", "").replace("Staff ", "Senior ")
                    if drifted != current_title:
                        title_drift_history.append({
                            "from": current_title, "to": drifted,
                            "at": next_first.isoformat(),
                        })
                        current_title = drifted
                cur_first = next_first
                cur_last = min(t1, next_first + timedelta(days=next_ttl))

            # We emit ONE row per role (latest state). The lifecycle metadata
            # in synthetic_meta carries first_posted / repost_count / drift.
            location = _gen_location(rng, _weighted_choice(
                rng, archetype["demographics"]["geography_weights"]
            ))
            role = {
                "company_id": company["id"],
                "role_title": current_title,
                "role_location": location,
                "role_department": fa.replace("_", " ").title() if fa != "other" else None,
                "role_description": _gen_description(rng, current_title, fa),
                "functional_area": fa,
                "functional_area_confidence": "high",
                "source_url": f"https://{company['domain']}/careers/{_slug(current_title)}-{rng.randint(1000,9999)}",
                "discovered_at": cur_last.isoformat(),
                "synthetic_meta": {
                    "is_synthetic": True,
                    "parent_company_synth_id": company["synth_id"],
                    "role_template_id": f"tpl-{fa}-{_slug(base_title)}",
                    "lifecycle": {
                        "first_posted": first_posted.isoformat(),
                        "last_seen": cur_last.isoformat(),
                        "repost_count": repost_count,
                        "is_evergreen": is_evergreen,
                        "title_drift_history": title_drift_history,
                    },
                    "is_friction_signal": is_evergreen or repost_count >= 2 or bool(title_drift_history),
                },
            }
            roles.append(role)
        cur = q_end

    return roles


def _gen_description(rng: random.Random, title: str, fa: str) -> str:
    base = (
        f"We are looking for a {title} to join our growing team. "
        f"You will work cross-functionally to drive impact in our {fa.replace('_', ' ')} org."
    )
    return base


# ─── Signals ────────────────────────────────────────────────────────────

def _generate_signals(
    rng: random.Random,
    archetype: dict,
    company: dict,
    roles: list[dict],
) -> list[dict]:
    signals: list[dict] = []
    bp = archetype.get("behavioral_pattern", {})
    signatures = bp.get("friction_signatures", []) or []
    density = bp.get("signal_density", "moderate")

    # 1. Signature-driven signals (deterministic per signature)
    for sig in signatures:
        for sig_type, sig_text, fa in SIGNATURE_TO_SIGNALS.get(sig, []):
            signals.append({
                "company_id": company["id"],
                "signal_type": sig_type,
                "signal_text": sig_text,
                "functional_area": fa,
                "confidence": 0.85,
                "synthetic_meta": {
                    "is_synthetic": True,
                    "from_signature": sig,
                },
            })

    # 2. Ambient signals based on signal_density, biased by expected dominant
    #    so noise reinforces (rather than dilutes) the targeted category.
    lo, hi = _AMBIENT_DENSITY_COUNT.get(density, (1, 2))
    n_ambient = rng.randint(lo, hi) if hi > 0 else 0
    if n_ambient > 0:
        target_friction = (
            company.get("synthetic_meta", {}).get("expected_dominant_friction_type")
        )
        pool = _AMBIENT_POOL_BY_FRICTION.get(target_friction or "_generic",
                                             _AMBIENT_POOL_BY_FRICTION["_generic"])
        chosen = rng.sample(pool, k=min(n_ambient, len(pool)))
        for sig_type, sig_text, fa in chosen:
            signals.append({
                "company_id": company["id"],
                "signal_type": sig_type,
                "signal_text": sig_text,
                "functional_area": fa,
                "confidence": 0.65,
                "synthetic_meta": {"is_synthetic": True, "from_signature": "ambient"},
            })

    # 3. Auto open_positions signal proportional to role count
    if len(roles) > 0:
        if len(roles) >= 10:
            sig_type = "high_open_positions_count_detected"
        else:
            sig_type = "open_positions_count_detected"
        signals.append({
            "company_id": company["id"],
            "signal_type": sig_type,
            "signal_text": f"{len(roles)} open positions detected on careers page",
            "functional_area": None,
            "confidence": 0.90,
            "synthetic_meta": {"is_synthetic": True, "from_signature": "auto_role_count"},
        })

    return signals


# ─── Adversarial noise ──────────────────────────────────────────────────

NOISE_TRANSFORMS = {
    "html_residual": lambda txt, rng: (txt or "") + " &amp; <p>extra</p>&nbsp;",
    "case_chaos": lambda txt, rng: (txt or "").upper() if rng.random() < 0.5 else "".join(
        c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(txt or "")
    ),
    "lang_mix": lambda txt, rng: (txt or "") + " — buscamos talento excepcional para nuestro equipo.",
    "mojibake": lambda txt, rng: (txt or "").replace("é", "Ã©").replace("ñ", "Ã±"),
    "title_with_emoji": lambda txt, rng: (txt or "") + " 🚀",
    "location_garbage": lambda txt, rng: "Remote – EMEA preferred (occasional travel to NYC)",
}


def _apply_noise(rng: random.Random, company: dict, roles: list[dict],
                 signals: list[dict], transformations: list[str]) -> None:
    for tx in transformations:
        if tx == "null_injection":
            for r in roles:
                if rng.random() < 0.30:
                    r["role_department"] = None
                if rng.random() < 0.05:
                    r["role_description"] = None
        elif tx == "dup_partial":
            if roles:
                src = rng.choice(roles)
                dup = dict(src)
                dup["source_url"] = (src.get("source_url") or "") + "?ref=2"
                dup["synthetic_meta"] = dict(src["synthetic_meta"])
                roles.append(dup)
        elif tx == "empty_signals":
            signals.clear()
        elif tx == "location_garbage":
            for r in roles:
                if rng.random() < 0.4:
                    r["role_location"] = NOISE_TRANSFORMS["location_garbage"](r.get("role_location"), rng)
        elif tx in NOISE_TRANSFORMS:
            fn = NOISE_TRANSFORMS[tx]
            for r in roles:
                if tx == "title_with_emoji" and rng.random() < 0.3:
                    r["role_title"] = fn(r.get("role_title"), rng)
                elif tx == "case_chaos" and rng.random() < 0.4:
                    r["role_title"] = fn(r.get("role_title"), rng)
                elif tx == "html_residual" and rng.random() < 0.5:
                    r["role_description"] = fn(r.get("role_description"), rng)
                elif tx == "lang_mix" and rng.random() < 0.4:
                    r["role_description"] = fn(r.get("role_description"), rng)
                elif tx == "mojibake" and rng.random() < 0.3:
                    r["role_description"] = fn(r.get("role_description"), rng)


# ─── Counterfactuals ────────────────────────────────────────────────────

def _build_counterfactual(
    rng: random.Random,
    company: dict,
    roles: list[dict],
    archetype_cf_baseline_band: list[int],
    pair_id: str,
    cf_idx: int,
) -> tuple[dict, list[dict], list[dict]]:
    """Same demographics, no friction signatures, baseline score band."""
    cf_company = dict(company)
    cf_id = str(uuid.UUID(int=int(uuid.UUID(company["id"]).int) ^ (1 << 120)))
    cf_company["id"] = cf_id
    cf_company["synth_id"] = company["synth_id"] + "-cf"
    cf_company["domain"] = "synth-cf-" + company["domain"].removeprefix("synth-")
    cf_company["name"] = company["name"] + " (CF)"

    cf_meta = dict(company["synthetic_meta"])
    cf_meta["archetype_id"] = company["synthetic_meta"]["archetype_id"] + "_cf"
    cf_meta["expected_friction_score_band"] = list(archetype_cf_baseline_band)
    cf_meta["expected_diagnostic_state"] = "insufficient_evidence"
    cf_meta["expected_dominant_friction_type"] = None
    cf_meta["expected_eligibility_gate"] = "blocked"
    cf_meta["expected_confidence"] = "low"
    cf_meta["expected_smart_match_hit"] = False
    cf_meta["friction_signatures"] = []
    cf_meta["counterfactual_pair_id"] = pair_id
    cf_meta["is_counterfactual"] = True
    cf_company["synthetic_meta"] = cf_meta

    # Mirror the original synthetic_meta on the source side
    company["synthetic_meta"]["counterfactual_pair_id"] = pair_id

    # CFs strip the role roster entirely. Why: the engine's extraction_coverage
    # KPI is evidence-based — any roster ≥1 with parsed titles trips it to
    # MODERATE and unlocks broad_hiring_pattern_detected, making
    # insufficient_evidence structurally unreachable. Empty roster + empty
    # signals is the only path to LOW coverage.
    cf_roles: list[dict] = []
    cf_signals: list[dict] = []
    return cf_company, cf_roles, cf_signals


# ─── Main orchestrator ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--version", type=str, default=None,
                        help="Dataset version slug. Default: synth-<today>-v1")
    parser.add_argument("--seed-path", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument("--archetypes-path", type=Path, default=DEFAULT_ARCH_PATH)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date().isoformat()
    version = args.version or f"synth-{today}-v1"
    out_dir = args.out_root / version
    out_dir.mkdir(parents=True, exist_ok=True)

    seed_data = json.loads(args.seed_path.read_text(encoding="utf-8"))
    arch_data = yaml.safe_load(args.archetypes_path.read_text(encoding="utf-8"))

    calibration = calibrate_from_seed(seed_data)

    def _as_date(v):
        return v if isinstance(v, date) else date.fromisoformat(v)
    t0 = _as_date(arch_data["simulated_window"]["t0"])
    t1 = _as_date(arch_data["simulated_window"]["t1"])

    archetype_index = {a["id"]: a for a in arch_data["archetypes"]}
    primary_archetypes = [a for a in arch_data["archetypes"] if "inherits_from" not in a]
    chaos_archetypes = [a for a in arch_data["archetypes"] if "inherits_from" in a]

    all_companies: list[dict] = []
    all_roles: list[dict] = []
    all_signals: list[dict] = []

    cf_eligible_pool: list[dict] = []  # for counterfactual selection later

    # --- Primary archetypes ---
    global_idx = 0
    for arch in primary_archetypes:
        rng = _archetype_rng(args.seed, arch["id"])
        for i in range(arch["n"]):
            company, roles, signals = _generate_one(
                rng=rng, archetype=arch, idx=global_idx,
                t0=t0, t1=t1,
            )
            all_companies.append(company)
            all_roles.extend(roles)
            all_signals.extend(signals)
            if arch.get("cf_eligible"):
                cf_eligible_pool.append((arch, company, roles))
            global_idx += 1

    # --- data_quality_chaos: inherit + inject noise ---
    for chaos_arch in chaos_archetypes:
        rng = _archetype_rng(args.seed, chaos_arch["id"])
        candidates = chaos_arch["inherits_from"]["candidates"]
        jitter = chaos_arch["inherits_from"]["score_band_jitter"]
        catalog = chaos_arch["noise_injection"]["catalog"]
        n_per_lo, n_per_hi = chaos_arch["noise_injection"]["transformations_per_company"]

        for i in range(chaos_arch["n"]):
            parent_id = rng.choice(candidates)
            parent = archetype_index[parent_id]
            company, roles, signals = _generate_one(
                rng=rng, archetype=parent, idx=global_idx,
                t0=t0, t1=t1,
            )
            # Override identity to mark as chaos
            company["synthetic_meta"]["archetype_id"] = chaos_arch["id"]
            company["synthetic_meta"]["chaos_parent_archetype"] = parent_id
            band = list(company["synthetic_meta"]["expected_friction_score_band"])
            company["synthetic_meta"]["expected_friction_score_band"] = [
                max(0, band[0] - jitter), band[1] + jitter
            ]
            n_tx = rng.randint(n_per_lo, n_per_hi)
            transformations = rng.sample(catalog, k=min(n_tx, len(catalog)))
            company["synthetic_meta"]["noise_injected"] = transformations
            _apply_noise(rng, company, roles, signals, transformations)
            all_companies.append(company)
            all_roles.extend(roles)
            all_signals.extend(signals)
            global_idx += 1

    # --- Counterfactuals ---
    cf_target = arch_data["counterfactual"]["cf_count_target"]
    cf_baseline_band = arch_data["counterfactual"]["cf_score_band_baseline"]
    cf_rng = random.Random(args.seed ^ 0xC0FFEE)
    chosen_cf = cf_rng.sample(
        cf_eligible_pool, k=min(cf_target, len(cf_eligible_pool))
    )
    cf_pair_idx = 0
    for arch, src_company, src_roles in chosen_cf:
        pair_id = f"pair-{cf_pair_idx:04d}"
        cf_co, cf_roles, cf_sigs = _build_counterfactual(
            cf_rng, src_company, src_roles, cf_baseline_band, pair_id, cf_pair_idx,
        )
        all_companies.append(cf_co)
        all_roles.extend(cf_roles)
        all_signals.extend(cf_sigs)
        cf_pair_idx += 1

    # --- Manifest ---
    archetype_dist = Counter(c["synthetic_meta"]["archetype_id"] for c in all_companies)
    manifest = {
        "dataset_version": version,
        "generator_version": GENERATOR_VERSION,
        "seed": args.seed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "simulated_window": {"t0": t0.isoformat(), "t1": t1.isoformat()},
        "source_real_export": str(args.seed_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "totals": {
            "companies": len(all_companies),
            "roles": len(all_roles),
            "signals": len(all_signals),
        },
        "archetype_distribution": dict(archetype_dist.most_common()),
        "counterfactual_pairs": cf_pair_idx,
        "vocabularies_pinned": {
            "sectors": _sha256_of(SECTORS),
            "diagnostic_states": _sha256_of(sorted(DIAGNOSTIC_STATES)),
            "friction_categories": _sha256_of(sorted(FRICTION_TYPES)),
            "eligibility_gates": _sha256_of(sorted(ELIGIBILITY_GATES)),
        },
    }

    # --- Write out ---
    (out_dir / "companies.json").write_text(
        json.dumps(all_companies, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "roles.json").write_text(
        json.dumps(all_roles, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "signals.json").write_text(
        json.dumps(all_signals, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[generate_dataset] wrote {out_dir}")
    print(f"  companies: {len(all_companies)}")
    print(f"  roles:     {len(all_roles)}")
    print(f"  signals:   {len(all_signals)}")
    print(f"  cf pairs:  {cf_pair_idx}")
    print(f"  archetype distribution:")
    for k, v in archetype_dist.most_common():
        print(f"    {k:<30} {v}")


def _generate_one(
    *,
    rng: random.Random,
    archetype: dict,
    idx: int,
    t0: date,
    t1: date,
) -> tuple[dict, list[dict], list[dict]]:
    sector = _weighted_choice(rng, archetype["demographics"]["sectors"])
    geo = _weighted_choice(rng, archetype["demographics"]["geography_weights"])
    name, domain = _gen_name_and_domain(rng, sector, idx)
    size = _gen_size_band(rng, archetype)
    company_uuid = str(uuid.UUID(int=rng.getrandbits(128)))

    eo = archetype["expected_outputs"]
    company = {
        "id": company_uuid,
        "synth_id": f"synth-co-{idx:05d}",
        "name": name,
        "domain": domain,
        "industry": sector,
        "company_size": size,
        "geography": geo,
        "entity_type": archetype["demographics"].get("entity_type", "operating_company"),
        "inferred_sector": sector,
        "inferred_sector_source": "archetype_generator",
        "inferred_sector_confidence": "high",
        "careers_url": f"https://{domain}/careers",
        "careers_accessibility": "ats_supported",
        "positioning_eligible": eo["eligibility_gate"] == "full",
        "source_added_from": "synthetic_generator",
        "synthetic_meta": {
            "is_synthetic": True,
            "archetype_id": archetype["id"],
            "expected_diagnostic_state": eo["diagnostic_state"],
            "expected_dominant_friction_type": eo["dominant_friction_type"],
            "expected_friction_score_band": eo["friction_score_band"],
            "expected_eligibility_gate": eo["eligibility_gate"],
            "expected_confidence": eo["confidence"],
            "expected_smart_match_hit": eo["smart_match_hit"],
            "friction_signatures": list(
                archetype.get("behavioral_pattern", {}).get("friction_signatures", []) or []
            ),
            "noise_injected": [],
            "counterfactual_pair_id": None,
            "ground_truth_immutable": True,
        },
    }
    roles = _generate_roles(rng, archetype, company, t0, t1)
    signals = _generate_signals(rng, archetype, company, roles)
    return company, roles, signals


if __name__ == "__main__":
    main()

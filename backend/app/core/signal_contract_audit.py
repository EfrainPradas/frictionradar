"""
Signal Contract Audit — verifies that every emitted signal_type
has a scoring rule and every scoring rule has a real emitter.

Run as:
    python -m app.core.signal_contract_audit          # CLI report
    pytest tests/test_signal_contract_audit.py          # CI gate
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

from app.core.friction_categories import FRICTION_CATEGORIES
from app.core.scoring_rules import SCORING_RULES, INTENTIONALLY_UNSCORED_SIGNALS


# ------------------------------------------------------------------
# Emitter registries — single source of truth for what the code
# actually emits.  Each entry maps a signal_type string to
# (source_file, line_or_note) so the audit can trace it.
# ------------------------------------------------------------------

# Static signal types emitted as literal strings
STATIC_EMITTERS: Dict[str, Tuple[str, str]] = {
    # --- CareersCollector ---
    "careers_page_found":              ("collectors/careers.py", "CareersCollector.collect"),
    "high_open_positions_count_detected": ("collectors/careers.py", "CareersCollector.collect (count>=100)"),
    "open_positions_count_detected":    ("collectors/careers.py", "CareersCollector.collect"),
    "multiple_open_roles":             ("collectors/careers.py", "CareersCollector.collect"),
    "analytics_role_detected":         ("collectors/careers.py", "CareersCollector.collect"),
    # --- CompanySiteCollector ---
    "company_size_detected":           ("collectors/company_site.py", "CompanySiteCollector.collect"),
    "revops_language_detected":        ("collectors/company_site.py", "CompanySiteCollector FRICTION_KEYWORDS"),
    "scaling_language_detected":       ("collectors/company_site.py", "CompanySiteCollector FRICTION_KEYWORDS"),
    "hiring_language_detected":        ("collectors/company_site.py", "CompanySiteCollector FRICTION_KEYWORDS"),
    "cross_team_language_detected":    ("collectors/company_site.py", "CompanySiteCollector FRICTION_KEYWORDS"),
    # --- NewsroomCollector ---
    "newsroom_found":                  ("collectors/newsroom.py", "NewsroomCollector._scan_page"),
    "expansion_language_detected":     ("collectors/newsroom.py", "NewsroomCollector GROWTH_KEYWORDS"),
    "funding_detected":                ("collectors/newsroom.py", "NewsroomCollector GROWTH_KEYWORDS"),
    "acquisition_detected":            ("collectors/newsroom.py", "NewsroomCollector GROWTH_KEYWORDS"),
    "reporting_language_detected":     ("collectors/newsroom.py", "NewsroomCollector GROWTH_KEYWORDS"),
    "partnership_detected":            ("collectors/newsroom.py", "NewsroomCollector GROWTH_KEYWORDS"),
    "growth_language_detected":        ("collectors/newsroom.py", "NewsroomCollector GROWTH_KEYWORDS"),
    "hiring_news_detected":            ("collectors/newsroom.py", "NewsroomCollector GROWTH_KEYWORDS"),
    # --- AtsPublicCollector ---
    # (dynamic — see ATS_BOARD_SIGNALS below)
    # --- DynamicCareersCollector ---
    "job_cards_visible_detected":      ("collectors/dynamic_careers.py", "DynamicCareersCollector.collect"),
    # --- CollectionOrchestrator (Playwright) ---
    # (duplicates high_open_positions / open_positions / job_cards — same types)
    # --- HiringPatternService ---
    "high_hiring_volume":              ("services/hiring_pattern_service.py", "_generate_pattern_signals"),
    "broad_hiring_pattern":            ("services/hiring_pattern_service.py", "_generate_pattern_signals"),
    "narrow_hiring_focus":             ("services/hiring_pattern_service.py", "_generate_pattern_signals"),
    # --- CareersPageSignals schema ---
    "visible_hiring_area_detected":    ("schemas/careers_page.py", "CareersPageSignals.to_signal_list"),
    "job_links_extracted":             ("schemas/careers_page.py", "CareersPageSignals.to_signal_list"),
}

# Dynamic signal patterns — keys/areas that produce signal_type strings
ATS_PLATFORMS: List[str] = [
    "greenhouse", "lever", "ashby", "smartrecruiters",
    "jobvite", "icims", "workday", "myworkdayjobs",
]

ATS_BOARD_SIGNALS: Dict[str, Tuple[str, str]] = {
    f"{p}_board_detected": ("collectors/ats_public.py", f"ATS_SIGNAL_MAP['{p}']")
    for p in ATS_PLATFORMS
}

ATS_EMBED_SIGNALS: Dict[str, Tuple[str, str]] = {
    f"ats_embed_detected_{p}": ("collectors/company_site.py", f"ATS_PLATFORMS['{p}']")
    for p in ATS_PLATFORMS
}

# CareersCollector CATEGORY_KEYWORDS keys → "{key}_hiring_detected"
CAREERS_CATEGORIES: List[str] = [
    "retail", "distribution", "manufacturing", "technology", "supply_chain",
    "marketing", "sales", "finance", "hr_people", "operations",
    "customer_success", "product", "design", "legal", "healthcare",
]
CAREERS_HIRING_SIGNALS: Dict[str, Tuple[str, str]] = {
    f"{cat}_hiring_detected": ("collectors/careers.py", f"CareersCollector CATEGORY_KEYWORDS['{cat}']")
    for cat in CAREERS_CATEGORIES
}

# DynamicCareersCollector CATEGORY_KEYWORDS keys (subset)
DYNAMIC_CAREERS_CATEGORIES: List[str] = [
    "retail", "distribution", "manufacturing", "technology", "supply_chain",
    "marketing", "sales", "finance", "hr_people", "operations", "customer_success",
]
DYNAMIC_HIRING_SIGNALS: Dict[str, Tuple[str, str]] = {
    f"{cat}_hiring_detected": ("collectors/dynamic_careers.py", f"DynamicCareersCollector CATEGORY_KEYWORDS['{cat}']")
    for cat in DYNAMIC_CAREERS_CATEGORIES
}

# Canonical areas from role_ingest CANONICAL + FUNCTION_KEYWORDS
# These produce "{area}_concentration_high" and "{area}_concentration_moderate"
CANONICAL_AREAS: List[str] = [
    "analytics", "finance", "operations", "supply_chain", "marketing", "sales",
    "customer_support", "product", "engineering", "hr", "recruiting", "legal",
    "manufacturing", "retail", "it", "healthcare", "hospitality", "education",
    "trades", "transportation", "food_service", "design",
]
CONCENTRATION_SIGNALS: Dict[str, Tuple[str, str]] = {}
for _area in CANONICAL_AREAS:
    CONCENTRATION_SIGNALS[f"{_area}_concentration_high"] = (
        "services/hiring_pattern_service.py", f"_canonical('{_area}') → concentration_high"
    )
    CONCENTRATION_SIGNALS[f"{_area}_concentration_moderate"] = (
        "services/hiring_pattern_service.py", f"_canonical('{_area}') → concentration_moderate"
    )

# FunctionInferenceEngine._generate_signal_type produces "{mapped}_hiring" suffix
# These are NOT persisted as CompanySignal — they are internal use only.
# We list them here so the audit can flag them as "internal-only, not in DB".
FIE_SIGNAL_MAP: Dict[str, str] = {
    "data_analytics": "analytics_hiring",
    "finance": "finance_hiring",
    "operations": "operations_hiring",
    "supply_chain": "supply_chain_hiring",
    "marketing": "marketing_hiring",
    "sales": "sales_hiring",
    "customer_success": "cs_hiring",
    "product": "product_hiring",
    "engineering": "engineering_hiring",
    "hr_people": "hr_hiring",
    "recruiting_talent": "recruiting_hiring",
    "legal_compliance": "legal_hiring",
    "manufacturing": "manufacturing_hiring",
    "retail": "retail_hiring",
    "it": "it_hiring",
    "healthcare": "healthcare_hiring",
    "hospitality": "hospitality_hiring",
    "education": "education_hiring",
    "trades": "trades_hiring",
    "transportation": "transportation_hiring",
    "food_service": "food_service_hiring",
    "design": "design_hiring",
}

# ------------------------------------------------------------------
# Aggregate ALL emitted signal types into one registry
# ------------------------------------------------------------------

ALL_EMITTERS: Dict[str, Tuple[str, str]] = {}
ALL_EMITTERS.update(STATIC_EMITTERS)
ALL_EMITTERS.update(ATS_BOARD_SIGNALS)
ALL_EMITTERS.update(ATS_EMBED_SIGNALS)
ALL_EMITTERS.update(CAREERS_HIRING_SIGNALS)
# DynamicCareer signals overlap with Careers — they produce the same
# signal_type strings for the 11 shared categories, so we skip adding
# them separately to avoid duplicates.
ALL_EMITTERS.update(CONCENTRATION_SIGNALS)


# ------------------------------------------------------------------
# Audit data structures
# ------------------------------------------------------------------

@dataclass
class OrphanSignal:
    """A signal_type that is emitted but has no matching scoring rule."""
    signal_type: str
    source_file: str
    source_note: str
    suggestion: str


@dataclass
class GhostRule:
    """A scoring rule signal_type that no emitter produces."""
    signal_type: str
    category: str
    rule_label: str
    suggestion: str


@dataclass
class KeywordOnlyRule:
    """A scoring rule that relies solely on keyword matching (no signal_type)."""
    category: str
    rule_label: str
    keywords: List[str]
    risk_note: str


@dataclass
class CategoryCoverage:
    """Whether a friction category has at least one active signal path."""
    category: str
    has_signal_type_rule: bool
    has_active_emitter: bool
    active_paths: List[str]


@dataclass
class AuditResult:
    orphans: List[OrphanSignal] = field(default_factory=list)
    ghosts: List[GhostRule] = field(default_factory=list)
    keyword_only: List[KeywordOnlyRule] = field(default_factory=list)
    category_coverage: List[CategoryCoverage] = field(default_factory=list)
    weight_imbalance: Dict[str, float] = field(default_factory=dict)
    passed: bool = True
    errors: List[str] = field(default_factory=list)


def run_audit() -> AuditResult:
    """Run the full signal contract audit and return results."""

    result = AuditResult()

    # ---- 1. Build the set of all signal_types referenced in scoring rules ----
    scoring_signal_types: Set[str] = set()
    for category, rules in SCORING_RULES.items():
        for rule in rules:
            for st in rule.get("signal_types", []):
                scoring_signal_types.add(st)

    # ---- 2. Find ORPHANS: emitted but not scored ----
    emitted_types = set(ALL_EMITTERS.keys())
    orphan_types = emitted_types - scoring_signal_types - INTENTIONALLY_UNSCORED_SIGNALS

    # Suggestion mapping for known orphans
    ORPHAN_SUGGESTIONS = {
        # ATS board signals → add to scaling_strain or create discovery category
        "_board_detected": "Add a scoring rule in an appropriate category (e.g., scaling_strain for ATS detection signals) or create a 'discovery' meta-signal that feeds into evidence quality.",
        # ATS embed signals → same
        "ats_embed_detected_": "Same as ATS board signals — map to evidence quality or scoring category.",
        # Discovery signals
        "careers_page_found": "This is a discovery signal. Either add to evidence_threshold_engine directly or create a scoring rule with low weight.",
        "company_size_detected": "Discovery signal. Feed into company_type_engine or evidence quality, not scoring.",
        "visible_hiring_area_detected": "Discovery signal. Feed into evidence quality or scoring if it indicates a specific friction area.",
        "job_links_extracted": "Discovery/extraction signal. Does not indicate friction. Safe to leave unscored.",
        # CompanySite keyword signals
        "scaling_language_detected": "No scoring rule exists. Consider adding to scaling_strain or merging with growth_language_detected.",
        "hiring_language_detected": "No scoring rule. Consider merging with scaling_strain 'multiple_open_roles' keyword list.",
        "cross_team_language_detected": "No scoring rule. Could indicate process_inefficiency or scaling_strain.",
        # Newsroom signals without rules
        "expansion_language_detected": "Add to scaling_strain with appropriate weight, or merge with growth_language_detected.",
        "funding_detected": "Add to scaling_strain — funding signals indicate growth pressure.",
        "acquisition_detected": "Add to scaling_strain or process_inefficiency — acquisitions create integration friction.",
        "partnership_detected": "Low-value signal. Consider adding to process_inefficiency with low weight.",
        "hiring_news_detected": "Merge with hiring_language_detected or add to scaling_strain.",
        # Unscored hiring category signals
        "_hiring_detected": "Add a scoring rule in the appropriate friction category, or map to an existing rule.",
        # Unscored concentration signals
        "_concentration_high": "Add a concentration rule in the appropriate category, or map to an existing concentration rule.",
        "_concentration_moderate": "Add a concentration rule in the appropriate category, or map to an existing concentration rule.",
    }

    for st in sorted(orphan_types):
        source_file, source_note = ALL_EMITTERS[st]
        # Find best suggestion
        suggestion = "Add a scoring rule or map to an existing one."
        for pattern, sug in ORPHAN_SUGGESTIONS.items():
            if pattern in st:
                suggestion = sug
                break
        result.orphans.append(OrphanSignal(
            signal_type=st,
            source_file=source_file,
            source_note=source_note,
            suggestion=suggestion,
        ))

    # ---- 3. Find GHOSTS: scoring rule signal_types with no emitter ----
    ghost_types = scoring_signal_types - emitted_types

    for st in sorted(ghost_types):
        # Find which category and rule this belongs to
        for category, rules in SCORING_RULES.items():
            for rule in rules:
                if st in rule.get("signal_types", []):
                    suggestion = f"Rename to match an existing emitter, or create an emitter."
                    # Specific suggestions for known ghosts
                    if st == "data_hiring_detected":
                        suggestion = "Rename to 'analytics_role_detected' or add a 'data_hiring_detected' emitter to the CareersCollector."
                    elif st == "process_language_detected":
                        suggestion = "Add a process_language_detected signal to CompanySiteCollector or merge keywords into an existing rule."
                    elif st == "revops_role_detected":
                        suggestion = "Rule already matches via 'revops_language_detected'. Remove this phantom signal_type from the rule."
                    elif st == "software_engineering_hiring_detected":
                        suggestion = "Collectors emit 'technology_hiring_detected'. Remove this phantom or add a mapping."
                    elif st == "manufacturing_engineering_hiring_detected":
                        suggestion = "Collectors emit 'manufacturing_hiring_detected'. Remove this phantom or add a mapping."

                    result.ghosts.append(GhostRule(
                        signal_type=st,
                        category=category,
                        rule_label=rule["label"],
                        suggestion=suggestion,
                    ))
                    break

    # ---- 4. Find KEYWORD-ONLY rules (no signal_type, rely on text matching) ----
    for category, rules in SCORING_RULES.items():
        for rule in rules:
            if not rule.get("signal_types") and rule.get("keywords"):
                risk = "Keyword-only rules fire on accidental text matches in other signals' signal_text. Reliability depends on what text other emitters produce."
                result.keyword_only.append(KeywordOnlyRule(
                    category=category,
                    rule_label=rule["label"],
                    keywords=rule["keywords"],
                    risk_note=risk,
                ))

    # ---- 5. Category coverage: does each category have ≥1 active signal path? ----
    for cat in FRICTION_CATEGORIES:
        rules = SCORING_RULES.get(cat, [])
        has_signal_type_rule = any(r.get("signal_types") for r in rules)
        # Check if any scoring rule's signal_types are actually emitted
        active_paths = []
        for rule in rules:
            for st in rule.get("signal_types", []):
                if st in emitted_types:
                    active_paths.append(st)
        has_active_emitter = len(active_paths) > 0
        result.category_coverage.append(CategoryCoverage(
            category=cat,
            has_signal_type_rule=has_signal_type_rule,
            has_active_emitter=has_active_emitter,
            active_paths=active_paths,
        ))

    # ---- 6. Weight imbalance: max achievable score per category ----
    for cat in FRICTION_CATEGORIES:
        rules = SCORING_RULES.get(cat, [])
        max_score = sum(r["weight"] for r in rules)
        result.weight_imbalance[cat] = max_score

    # ---- 7. Determine pass/fail ----
    # FAIL if any category has zero active signal paths
    for cov in result.category_coverage:
        if not cov.has_active_emitter:
            result.errors.append(
                f"Category '{cov.category}' has no active signal path — "
                f"no scoring rule signal_type is produced by any emitter."
            )
            result.passed = False

    # FAIL if ghost rules exist
    if result.ghosts:
        result.errors.append(
            f"{len(result.ghosts)} ghost rule signal_type(s) have no emitter. "
            f"Scoring may never fire these rules."
        )
        result.passed = False

    # WARN (but don't fail) on orphans and keyword-only rules
    # These are tracked but not blocking — they represent wasted collection
    # effort or fragile matching, but don't break the scoring pipeline.

    return result


def format_report(result: AuditResult) -> str:
    """Format audit results as a human-readable report."""
    lines = []
    lines.append("=" * 72)
    lines.append("FRICTIONRADAR — SIGNAL CONTRACT AUDIT REPORT")
    lines.append("=" * 72)
    lines.append("")

    # --- Orphan signals ---
    lines.append(f"ORPHAN SIGNALS (emitted, not scored): {len(result.orphans)}")
    lines.append("-" * 72)
    if result.orphans:
        # Group by category for readability
        ats_orphans = [o for o in result.orphans if "_board_detected" in o.signal_type or "ats_embed_detected_" in o.signal_type]
        concentration_orphans = [o for o in result.orphans if "_concentration_" in o.signal_type]
        hiring_orphans = [o for o in result.orphans if "_hiring_detected" in o.signal_type and "_concentration_" not in o.signal_type]
        other_orphans = [o for o in result.orphans if o not in ats_orphans and o not in concentration_orphans and o not in hiring_orphans]

        if ats_orphans:
            lines.append(f"\n  ATS Detection ({len(ats_orphans)} signals):")
            for o in ats_orphans:
                lines.append(f"    • {o.signal_type}")
                lines.append(f"      Source: {o.source_file} — {o.source_note}")
                lines.append(f"      Action: {o.suggestion}")

        if hiring_orphans:
            lines.append(f"\n  Hiring Category ({len(hiring_orphans)} signals):")
            for o in hiring_orphans:
                lines.append(f"    • {o.signal_type}")
                lines.append(f"      Source: {o.source_file} — {o.source_note}")
                lines.append(f"      Action: {o.suggestion}")

        if concentration_orphans:
            lines.append(f"\n  Concentration ({len(concentration_orphans)} signals):")
            for o in concentration_orphans:
                lines.append(f"    • {o.signal_type}")
                lines.append(f"      Source: {o.source_file} — {o.source_note}")
                lines.append(f"      Action: {o.suggestion}")

        if other_orphans:
            lines.append(f"\n  Other ({len(other_orphans)} signals):")
            for o in other_orphans:
                lines.append(f"    • {o.signal_type}")
                lines.append(f"      Source: {o.source_file} — {o.source_note}")
                lines.append(f"      Action: {o.suggestion}")
    else:
        lines.append("  None — all emitted signals have scoring rules.")

    # --- Ghost rules ---
    lines.append("")
    lines.append(f"GHOST RULES (in scoring, no emitter): {len(result.ghosts)}")
    lines.append("-" * 72)
    if result.ghosts:
        for g in result.ghosts:
            lines.append(f"  • {g.signal_type}")
            lines.append(f"    Category: {g.category} | Rule: {g.rule_label}")
            lines.append(f"    Action: {g.suggestion}")
    else:
        lines.append("  None — all scoring rule signal_types have emitters.")

    # --- Keyword-only rules ---
    lines.append("")
    lines.append(f"KEYWORD-ONLY RULES (no signal_type, text-match only): {len(result.keyword_only)}")
    lines.append("-" * 72)
    if result.keyword_only:
        for kw in result.keyword_only:
            lines.append(f"  • {kw.rule_label} [{kw.category}]")
            lines.append(f"    Keywords: {', '.join(kw.keywords)}")
            lines.append(f"    Risk: {kw.risk_note}")
    else:
        lines.append("  None — all rules have at least one signal_type.")

    # --- Category coverage ---
    lines.append("")
    lines.append("CATEGORY COVERAGE (active signal paths):")
    lines.append("-" * 72)
    for cov in result.category_coverage:
        status = "ACTIVE" if cov.has_active_emitter else "INACTIVE"
        paths = ", ".join(cov.active_paths[:5])
        if len(cov.active_paths) > 5:
            paths += f", +{len(cov.active_paths) - 5} more"
        lines.append(f"  {cov.category}: {status}")
        if paths:
            lines.append(f"    Paths: {paths}")
        else:
            lines.append(f"    Paths: NONE — no scoring rule has an active emitter")

    # --- Weight imbalance ---
    lines.append("")
    lines.append("WEIGHT IMBALANCE (max achievable score per category):")
    lines.append("-" * 72)
    min_score = min(result.weight_imbalance.values())
    max_score = max(result.weight_imbalance.values())
    for cat, score in sorted(result.weight_imbalance.items(), key=lambda x: -x[1]):
        ratio = f"{score / min_score:.1f}x" if min_score > 0 else "∞"
        bar = "█" * int(score / 0.5)
        lines.append(f"  {cat:32s} {score:5.2f}  ({ratio}) {bar}")
    if max_score / min_score > 1.5:
        lines.append(f"  ⚠ Max/min ratio is {max_score / min_score:.1f}x — categories above 1.5x will dominate scoring.")

    # --- Summary ---
    lines.append("")
    lines.append("=" * 72)
    lines.append(f"RESULT: {'PASS' if result.passed else 'FAIL'}")
    lines.append(f"  Orphans:        {len(result.orphans)}")
    lines.append(f"  Ghosts:         {len(result.ghosts)}")
    lines.append(f"  Keyword-only:  {len(result.keyword_only)}")
    if result.errors:
        lines.append(f"  Errors:")
        for err in result.errors:
            lines.append(f"    ✗ {err}")
    lines.append("=" * 72)

    return "\n".join(lines)


def main():
    """CLI entry point."""
    result = run_audit()
    report = format_report(result)
    print(report)
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
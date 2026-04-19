"""QA Engine — post-collection quality assurance checks.

Runs deterministic checks against each company result to flag data-quality
issues before tiering. Does NOT generate insights; only detects problems.

Checks:
    A — suspicious_open_positions_count
    B — deep_extraction_skipped_too_early
    C — interpretation_exceeds_evidence
    D — shallow_source_dependence
    E — invalid_or_low_value_target
"""

from __future__ import annotations

from collections import Counter
from typing import Any


# ── Check A: Suspicious open_positions_count ────────────────────────

def check_suspicious_open_positions(
    company: dict[str, Any],
    all_companies: list[dict[str, Any]],
) -> list[str]:
    """Detect repeated or suspicious open_positions_count values."""
    flags: list[str] = []
    op_count = company.get("open_positions_count", 0)

    if op_count is None or op_count == 0:
        return flags

    # Count how many other companies share the same exact open_positions_count
    same_count = sum(
        1 for c in all_companies
        if c.get("domain") != company.get("domain")
        and c.get("open_positions_count") == op_count
    )

    # If >10% of companies have the exact same count, it's suspicious
    total = len(all_companies)
    if total > 0 and same_count / total > 0.10:
        flags.append("repeated_open_positions_pattern")

    # Round numbers like 50, 100, 200 are common ATS pagination defaults
    suspicious_defaults = {10, 20, 25, 50, 100, 200, 500}
    if op_count in suspicious_defaults:
        flags.append("suspicious_open_positions_count")

    return flags


# ── Check B: Deep extraction skipped too early ──────────────────────

def check_deep_extraction_skipped(
    company: dict[str, Any],
) -> list[str]:
    """Flag when Playwright was skipped but evidence is still thin."""
    flags: list[str] = []

    extraction_coverage = company.get("extraction_coverage", "low")
    pain_clarity = company.get("pain_clarity", "low")
    function_concentration = company.get("function_concentration", "low")
    signals_count = company.get("signals_count", 0)
    pipeline_log = company.get("pipeline_log", [])

    # Was Playwright skipped?
    playwright_skipped = any(
        "Playwright skipped" in line for line in pipeline_log
    )
    if not playwright_skipped:
        return flags

    # Only flag if Playwright was skipped AND evidence is genuinely thin.
    # If sync collectors (especially careers) found rich evidence, skipping
    # Playwright is justified even if pain_clarity remains low.
    if extraction_coverage == "low" and pain_clarity == "low":
        flags.append("deep_extraction_skipped_too_early")

    # Flag if function concentration is low AND signals are very scarce
    if function_concentration == "low" and signals_count < 6:
        flags.append("deep_extraction_skipped_too_early")

    # Deduplicate
    return list(set(flags))


# ── Check C: Interpretation exceeds evidence ────────────────────────

def check_interpretation_vs_evidence(
    company: dict[str, Any],
) -> list[str]:
    """Flag contradictions between evidence quality and recommendations."""
    flags: list[str] = []

    extraction_coverage = company.get("extraction_coverage", "low")
    pain_clarity = company.get("pain_clarity", "low")
    function_concentration = company.get("function_concentration", "low")
    positioning_readiness = company.get("positioning_readiness", "low")
    diagnosis_status = company.get("diagnosis_status", "")
    open_positions = company.get("open_positions_count", 0)

    # Low extraction but high positioning recommendation
    if extraction_coverage == "low" and positioning_readiness in ("high", "moderate"):
        flags.append("positioning_too_early")

    # Low pain clarity but diagnosis says pain is identified
    if pain_clarity == "low" and "identified" in (diagnosis_status or ""):
        flags.append("interpretation_exceeds_evidence")

    # Broad hiring pattern but function_concentration says otherwise
    if (diagnosis_status == "broad_hiring_pattern_detected"
            and function_concentration in ("high",)):
        flags.append("interpretation_exceeds_evidence")

    # Low role-family evidence but high readiness
    if (function_concentration == "low"
            and positioning_readiness in ("high", "moderate")):
        flags.append("positioning_too_early")

    # Many signals but 0 open positions with high positioning readiness
    if open_positions == 0 and positioning_readiness in ("high", "moderate"):
        flags.append("positioning_too_early")

    return list(set(flags))


# ── Check D: Collector imbalance / shallow source dependence ───────

def check_shallow_source_dependence(
    company: dict[str, Any],
) -> list[str]:
    """Flag when nearly all evidence comes from one shallow source."""
    flags: list[str] = []

    collection_meta = company.get("collection_meta", {})
    collectors = collection_meta.get("collectors", [])

    if not collectors:
        flags.append("shallow_source_dependence")
        return flags

    # Normalize collectors — handle both dict and string formats
    normalized: list[dict[str, Any]] = []
    for c in collectors:
        if isinstance(c, dict):
            normalized.append(c)
        elif isinstance(c, str):
            # PowerShell format: "@{collector=company_site; signals=2; status=ok}"
            import re
            match = re.match(r'@\{(.+)\}', c)
            if match:
                parts = {}
                for part in match.group(1).split('; '):
                    if '=' in part:
                        k, v = part.split('=', 1)
                        parts[k.strip()] = v.strip()
                normalized.append(parts)

    producing_collectors = [
        c for c in normalized
        if int(c.get("signals", 0)) > 0
    ]

    # If only 1 source produced signals
    if len(producing_collectors) == 1:
        source = producing_collectors[0].get("collector", "unknown")
        # dynamic_careers alone without corroboration is weak
        if source in ("dynamic_careers", "ats_public"):
            flags.append("shallow_source_dependence")
        # careers only with few signals
        signals = int(producing_collectors[0].get("signals", 0))
        if signals <= 3:
            flags.append("shallow_source_dependence")

    # No company_site or newsroom corroboration
    producing_names = {c.get("collector", "") for c in producing_collectors}
    if producing_names and "company_site" not in producing_names and "newsroom" not in producing_names:
        if len(producing_collectors) <= 2:
            # Only 1-2 sources, neither from company itself
            flags.append("shallow_source_dependence")

    return list(set(flags))


# ── Check E: Invalid or low-value target ───────────────────────────

def check_invalid_target(
    company: dict[str, Any],
    all_companies: list[dict[str, Any]],
) -> list[str]:
    """Flag duplicates, broken domains, irrelevant targets."""
    flags: list[str] = []

    domain = company.get("domain", "")
    name = company.get("company_name", "")

    # Broken / very short domain (likely truncated)
    if domain and len(domain) < 6 and "." in domain:
        flags.append("invalid_domain")

    # Domain without TLD
    if domain and "." not in domain:
        flags.append("invalid_domain")

    # Duplicate check (same domain, different name)
    domain_count = sum(
        1 for c in all_companies
        if c.get("domain") == domain and c.get("company_name") != name
    )
    if domain_count > 0:
        flags.append("duplicate_record")

    # Same company name, different domain
    name_count = sum(
        1 for c in all_companies
        if c.get("company_name") == name and c.get("domain") != domain
    )
    if name_count > 0:
        flags.append("duplicate_record")

    # Known low-value company types
    company_type = company.get("company_type", "")
    if company_type == "job_market_intermediary":
        flags.append("target_review_required")

    # Pre-excluded entries
    pipeline_log = company.get("pipeline_log", [])
    if any("Excluded:" in line for line in pipeline_log):
        flags.append("excluded_pre_pipeline")

    return list(set(flags))


# ── Master QA evaluation ────────────────────────────────────────────

def evaluate_qa(
    company: dict[str, Any],
    all_companies: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run all QA checks and return QA fields."""
    all_flags: list[str] = []

    all_flags.extend(check_suspicious_open_positions(company, all_companies))
    all_flags.extend(check_deep_extraction_skipped(company))
    all_flags.extend(check_interpretation_vs_evidence(company))
    all_flags.extend(check_shallow_source_dependence(company))
    all_flags.extend(check_invalid_target(company, all_companies))

    all_flags = list(set(all_flags))

    # Compute qa_score
    # Major flags: anything suggesting data is unreliable
    major_flags = {
        "suspicious_open_positions_count",
        "repeated_open_positions_pattern",
        "interpretation_exceeds_evidence",
        "invalid_domain",
        "duplicate_record",
        "excluded_pre_pipeline",
        "deep_extraction_skipped_too_early",
    }
    minor_flags = {
        "positioning_too_early",
        "shallow_source_dependence",
        "target_review_required",
    }

    all_flags_set = set(all_flags)
    major_count = len(all_flags_set & major_flags)
    minor_count = len(all_flags_set & minor_flags)

    if major_count >= 2 or (major_count >= 1 and minor_count >= 2):
        qa_score = "low"
        qa_pass = False
    elif major_count >= 1 or minor_count >= 3:
        qa_score = "medium"
        qa_pass = False
    elif minor_count >= 1:
        qa_score = "medium"
        qa_pass = True
    else:
        qa_score = "high"
        qa_pass = True

    return {
        "qa_pass": qa_pass,
        "qa_score": qa_score,
        "qa_flags": sorted(all_flags),
        "data_quality_status": qa_score,
    }

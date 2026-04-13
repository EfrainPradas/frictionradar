"""Tiering Engine — assigns target_tier based on evidence quality + QA flags.

Tiers:
    tier_1_ready_for_positioning  — high-confidence, actionable
    tier_2_ready_for_review       — worth human inspection
    tier_3_needs_recollection     — needs more/better data
    tier_4_excluded               — not a valid target

This is a governance layer. It does not generate insights.
"""

from __future__ import annotations

from typing import Any

# Canonical tier values
TIER_1_POSITIONING = "tier_1_ready_for_positioning"
TIER_2_REVIEW = "tier_2_ready_for_review"
TIER_3_RECOLLECT = "tier_3_needs_recollection"
TIER_4_EXCLUDED = "tier_4_excluded"

ALL_TIERS = [TIER_1_POSITIONING, TIER_2_REVIEW, TIER_3_RECOLLECT, TIER_4_EXCLUDED]


def assign_tier(
    company: dict[str, Any],
    qa: dict[str, Any],
) -> tuple[str, str]:
    """Return (target_tier, tier_rationale).

    Order matters: we check exclusion first, then Tier 1 (strictest),
    then fall through to Tier 3, with Tier 2 as the default for
    review-worthy companies.
    """
    extraction = company.get("extraction_coverage", "low")
    hiring = company.get("hiring_pressure", "low")
    pain = company.get("pain_clarity", "low")
    function = company.get("function_concentration", "low")
    type_conf = company.get("company_type_confidence", "low")
    positioning = company.get("positioning_readiness", "low")
    signals = company.get("signals_count", 0)
    open_positions = company.get("open_positions_count", 0)
    diagnosis = company.get("diagnosis_status", "")
    qa_flags = set(qa.get("qa_flags", []))
    qa_pass = qa.get("qa_pass", False)

    # ── Tier 4: Excluded ────────────────────────────────────────────
    if "invalid_domain" in qa_flags:
        return TIER_4_EXCLUDED, "Invalid or broken domain"
    if "duplicate_record" in qa_flags:
        return TIER_4_EXCLUDED, "Duplicate company record"
    if "excluded_pre_pipeline" in qa_flags:
        return TIER_4_EXCLUDED, "Pre-excluded by input validation"
    if company.get("status") == "excluded":
        return TIER_4_EXCLUDED, "Already marked as excluded"

    # ── Tier 1: Ready for positioning (STRICT) ─────────────────────
    # ALL conditions must be true — this tier should be rare
    tier_1_checks = {
        "extraction_coverage >= moderate": extraction in ("moderate", "high"),
        "hiring_pressure meaningful": hiring in ("high", "moderate"),
        "pain_clarity >= moderate": pain in ("moderate", "high"),
        "function_concentration >= moderate": function in ("moderate", "high"),
        "company_type_confidence != low": type_conf in ("high", "medium"),
        "positioning_readiness >= moderate": positioning in ("moderate", "high"),
        "qa_pass": qa_pass,
        "no major QA flags": not qa_flags & {
            "suspicious_open_positions_count",
            "repeated_open_positions_pattern",
            "interpretation_exceeds_evidence",
            "deep_extraction_skipped_too_early",
            "shallow_source_dependence",
            "invalid_domain",
            "duplicate_record",
        },
        "has role-level evidence": function in ("moderate", "high"),
        "diagnosis beyond broad": diagnosis in (
            "specific_pain_emerging",
            "specific_pain_identified",
            "ready_for_positioning",
        ),
        "meaningful signal count": signals >= 8,
    }

    failed_checks = [
        name for name, passed in tier_1_checks.items() if not passed
    ]

    if not failed_checks:
        return TIER_1_POSITIONING, "All Tier 1 criteria met"

    # ── Tier 3: Needs recollection ──────────────────────────────────
    tier_3_indicators = []

    if extraction == "low":
        tier_3_indicators.append("extraction_coverage is low")

    if signals < 4:
        tier_3_indicators.append("too few signals")

    if "deep_extraction_skipped_too_early" in qa_flags:
        tier_3_indicators.append("deep extraction skipped while evidence is thin")

    if qa.get("qa_score") == "low":
        tier_3_indicators.append("overall QA score is low")

    if "shallow_source_dependence" in qa_flags and signals < 8:
        tier_3_indicators.append("evidence comes from a single shallow source")

    if company.get("status") == "needs_recollection":
        tier_3_indicators.append("pipeline already flagged as needs_recollection")

    if tier_3_indicators:
        return TIER_3_RECOLLECT, "; ".join(tier_3_indicators)

    # ── Tier 2: Ready for review (default for valid companies) ──────
    review_reasons: list[str] = []

    if failed_checks:
        review_reasons.append(
            f"not ready for positioning: {failed_checks[0]}"
        )

    if "positioning_too_early" in qa_flags:
        review_reasons.append("positioning may be premature")

    if "target_review_required" in qa_flags:
        review_reasons.append("company type needs verification")

    if qa.get("qa_score") == "medium":
        review_reasons.append("some quality concerns detected")

    if not review_reasons:
        review_reasons.append("company has useful evidence but does not meet strict positioning criteria")

    return TIER_2_REVIEW, "; ".join(review_reasons)


def safe_tier_summary(tier: str, company: dict[str, Any]) -> str:
    """Return a business-safe summary for a company's tier.

    Does NOT imply positioning readiness unless the company is actually Tier 1.
    """
    name = company.get("company_name", "Unknown")
    if tier == TIER_1_POSITIONING:
        return (
            f"{name} has enough evidence and pain clarity to support targeted positioning."
        )
    elif tier == TIER_2_REVIEW:
        return (
            f"{name} is worth human review, but the dominant pain is not yet "
            f"isolated enough for precise positioning."
        )
    elif tier == TIER_3_RECOLLECT:
        return (
            f"{name} needs stronger evidence before it can be reviewed confidently."
        )
    else:
        return f"{name} is excluded from targeting."

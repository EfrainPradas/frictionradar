"""Operational State Mapper — translates target_tier into a direct action state.

Mapping:
    tier_1_ready_for_positioning → position_now
    tier_2_ready_for_review       → inspect_human
    tier_3_needs_recollection     → collect_more
    tier_4_excluded               → exclude
"""

from __future__ import annotations

from typing import Any

# Canonical operational states
POSITION_NOW = "position_now"
INSPECT_HUMAN = "inspect_human"
COLLECT_MORE = "collect_more"
EXCLUDE = "exclude"

TIER_TO_STATE: dict[str, str] = {
    "tier_1_ready_for_positioning": POSITION_NOW,
    "tier_2_ready_for_review": INSPECT_HUMAN,
    "tier_3_needs_recollection": COLLECT_MORE,
    "tier_4_excluded": EXCLUDE,
}

ALL_OPERATIONAL_STATES = [POSITION_NOW, INSPECT_HUMAN, COLLECT_MORE, EXCLUDE]


def map_operational_state(target_tier: str) -> str:
    """Map a target_tier to its operational state."""
    return TIER_TO_STATE.get(target_tier, COLLECT_MORE)


def build_run_summary(
    results: list[dict[str, Any]],
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    """Build a run-level summary grouped by tier and operational state.

    This is the main control panel for batch workflow visibility.
    """
    from collections import Counter

    tiers = Counter(r.get("target_tier", "unknown") for r in results)
    states = Counter(r.get("operational_state", "unknown") for r in results)
    qa_scores = Counter(r.get("data_quality_status", "unknown") for r in results)
    original_statuses = Counter(r.get("status", "unknown") for r in results)

    summary: dict[str, Any] = {
        "total_companies": len(results),
        # Tier breakdown
        "tier_1_ready_for_positioning": tiers.get("tier_1_ready_for_positioning", 0),
        "tier_2_ready_for_review": tiers.get("tier_2_ready_for_review", 0),
        "tier_3_needs_recollection": tiers.get("tier_3_needs_recollection", 0),
        "tier_4_excluded": tiers.get("tier_4_excluded", 0),
        # Operational state breakdown
        "position_now": states.get("position_now", 0),
        "inspect_human": states.get("inspect_human", 0),
        "collect_more": states.get("collect_more", 0),
        "exclude": states.get("exclude", 0),
        # QA breakdown
        "qa_high": qa_scores.get("high", 0),
        "qa_medium": qa_scores.get("medium", 0),
        "qa_low": qa_scores.get("low", 0),
        # Original pipeline status
        "original_ready_for_review": original_statuses.get("ready_for_review", 0),
        "original_needs_recollection": original_statuses.get("needs_recollection", 0),
        "original_excluded": original_statuses.get("excluded", 0),
    }

    if started_at:
        summary["started_at"] = started_at
    if finished_at:
        summary["finished_at"] = finished_at

    # Top QA flags
    all_flags: list[str] = []
    for r in results:
        all_flags.extend(r.get("qa_flags", []))
    flag_counts = Counter(all_flags)
    summary["top_qa_flags"] = dict(flag_counts.most_common(10))

    return summary


def attach_qa_fields(
    company: dict[str, Any],
    qa: dict[str, Any],
    tier: str,
    tier_rationale: str,
) -> dict[str, Any]:
    """Attach QA, tiering, and operational state fields to a company result.

    Returns a new dict with all fields merged in.
    """
    result = dict(company)
    result["qa_pass"] = qa.get("qa_pass", False)
    result["qa_score"] = qa.get("qa_score", "low")
    result["qa_flags"] = qa.get("qa_flags", [])
    result["data_quality_status"] = qa.get("data_quality_status", "low")
    result["target_tier"] = tier
    result["tier_rationale"] = tier_rationale
    result["operational_state"] = map_operational_state(tier)

    return result

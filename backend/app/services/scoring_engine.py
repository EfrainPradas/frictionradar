"""
Friction Radar — Scoring Engine (Rule-Based, Normalized)

Scoring formula (v2.0):

  1. For each friction category, compute raw_score:
     raw_score = sum(weight for each matched rule in category)

  2. Compute max_possible_score per category:
     max_possible_score = sum(weight for ALL rules in category)
     (This is the score a company would get if every rule matched.)

  3. Compute normalized_score per category:
     normalized_score = raw_score / max_possible_score
     (Clamped to [0.0, 1.0]. 0.0 = no evidence, 1.0 = all rules matched.)

  4. dominant_friction_type = category with highest normalized_score.
     If all normalized_scores are 0.0 and no signals exist, returns "no_signal".

  5. total_score = sum of all category raw_scores (preserved for audit).

  6. confidence is adjusted by:
     a) signal_diversity: how many distinct signal types contributed
     b) evidence breadth: how many categories had non-zero scores

  Why normalization?
    Without it, scaling_strain (max 10.50) almost always dominates
    tooling_inconsistency (max 6.00) even when both have matched the same
    proportion of their available rules. Normalization makes the dominant
    type reflect which category has the *strongest proportional evidence*,
    not which category has the most rules.

  Backward compatibility:
    raw_score, total_score, and scoring_breakdown_json are preserved exactly
    as before. New fields (normalized_score, max_possible_score, signal_diversity,
    evidence_breadth) are added alongside. The SCORING_VERSION is bumped to
    "2.0.0" so consumers can detect the new format.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.friction_categories import FRICTION_CATEGORIES
from app.core.scoring_rules import SCORING_RULES
from app.core.logging import logger
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore

# Pre-compute max_possible_score per category (static, from rules definition)
MAX_POSSIBLE_SCORES: Dict[str, float] = {}
for _cat in FRICTION_CATEGORIES:
    _rules = SCORING_RULES.get(_cat, [])
    MAX_POSSIBLE_SCORES[_cat] = round(sum(r.get("weight", 1.0) for r in _rules), 4)

# Bump version to indicate normalized scoring
SCORING_VERSION_V2 = "2.0.0"


def _evaluate_rules(signals: List[CompanySignal]) -> Dict[str, Dict]:
    """
    Core rule evaluation. Returns the scoring breakdown dict.

    Each category entry contains:
      - score: raw category score (sum of matched rule weights)
      - matched_signals: list of matched rule labels
      - max_possible: maximum achievable score for this category
      - normalized_score: raw / max_possible, clamped to [0.0, 1.0]
    """
    breakdown: Dict[str, Dict] = {}

    for category in FRICTION_CATEGORIES:
        rules = SCORING_RULES.get(category, [])
        category_score = 0.0
        matched_labels = []

        for rule in rules:
            rule_matched = False
            signal_types = set(rule.get("signal_types", []))
            keywords = [kw.lower() for kw in rule.get("keywords", [])]
            weight = rule.get("weight", 1.0)

            for signal in signals:
                # Match by signal_type
                if signal.signal_type in signal_types:
                    rule_matched = True
                    break
                # Match by keyword in signal_text
                if signal.signal_text and any(
                    kw in signal.signal_text.lower() for kw in keywords
                ):
                    rule_matched = True
                    break

            if rule_matched:
                category_score += weight
                matched_labels.append(label if (label := rule.get("label")) else rule.get("label", ""))

        max_possible = MAX_POSSIBLE_SCORES.get(category, 1.0)
        normalized = round(category_score / max_possible, 4) if max_possible > 0 else 0.0
        normalized = max(0.0, min(1.0, normalized))

        breakdown[category] = {
            "score": round(category_score, 2),
            "matched_signals": matched_labels,
            "max_possible": round(max_possible, 4),
            "normalized_score": normalized,
        }

    return breakdown


def _compute_confidence(
    breakdown: Dict[str, Dict],
    signals: List[CompanySignal],
) -> Dict[str, Any]:
    """
    Compute confidence metrics based on signal diversity and evidence breadth.

    signal_diversity: count of distinct signal_types that contributed to scoring.
    evidence_breadth: count of categories with non-zero normalized_score.
    confidence_level: high/medium/low based on diversity and breadth.
    """
    # Signal diversity: count distinct signal types that actually matched a rule
    all_signal_types = set()
    all_keywords_matched = set()
    for signal in signals:
        if signal.signal_type:
            all_signal_types.add(signal.signal_type)

    # Count categories with non-zero scores
    categories_with_evidence = sum(
        1 for cat in breakdown.values() if cat["normalized_score"] > 0
    )

    # Count distinct signal types that contributed
    contributing_types = set()
    contributing_labels = set()
    for cat_data in breakdown.values():
        for label in cat_data.get("matched_signals", []):
            contributing_labels.add(label)

    signal_diversity = len(all_signal_types)
    contributing_signal_count = len(contributing_labels)
    evidence_breadth = categories_with_evidence

    # Confidence levels based on diversity and breadth
    if contributing_signal_count >= 6 and evidence_breadth >= 3:
        confidence_level = "high"
    elif contributing_signal_count >= 3 and evidence_breadth >= 2:
        confidence_level = "medium"
    elif contributing_signal_count >= 1:
        confidence_level = "low"
    else:
        confidence_level = "none"

    return {
        "signal_diversity": signal_diversity,
        "contributing_signal_count": contributing_signal_count,
        "evidence_breadth": evidence_breadth,
        "confidence_level": confidence_level,
    }


def compute_and_persist_score(
    db: Session, company_id: UUID, open_positions_count: Optional[int] = None
) -> FrictionScore:
    """
    Compute a fresh friction score for the given company, persist and return it.

    The scoring uses normalized scores to determine the dominant friction type,
    which corrects for structural bias across categories with different numbers
    of rules. Raw scores are preserved for auditability.
    """
    logger.info(f"[ScoringEngine] Starting scoring for company: {company_id}")

    signals = (
        db.query(CompanySignal).filter(CompanySignal.company_id == company_id).all()
    )
    logger.info(f"[ScoringEngine] Loaded {len(signals)} signals for scoring.")

    if not signals:
        logger.warning(
            f"[ScoringEngine] No signals found for company {company_id}. "
            f"Producing zero-score result."
        )

    breakdown = _evaluate_rules(signals)

    # Total score = sum of raw category scores (preserved for backward compat)
    total_score = round(sum(cat["score"] for cat in breakdown.values()), 2)

    # Dominant = highest NORMALIZED score category
    # This is the key change: normalized_score prevents categories with more
    # rules from dominating just because they have more rules.
    if any(cat["normalized_score"] > 0 for cat in breakdown.values()):
        dominant = max(
            breakdown,
            key=lambda c: breakdown[c]["normalized_score"],
        )
    else:
        # No signals matched any rule — no dominant friction type
        dominant = "no_signal"

    # Confidence adjustment
    confidence = _compute_confidence(breakdown, signals)

    logger.info(
        f"[ScoringEngine] Scoring complete. "
        f"Total: {total_score}, Dominant: {dominant} "
        f"(normalized), Confidence: {confidence['confidence_level']}"
    )

    # Build the full breakdown for JSON storage
    # Include both raw and normalized scores for each category
    scoring_breakdown = {}
    for category, cat_data in breakdown.items():
        scoring_breakdown[category] = {
            "raw_score": cat_data["score"],
            "max_possible": cat_data["max_possible"],
            "normalized_score": cat_data["normalized_score"],
            "matched_signals": cat_data["matched_signals"],
        }

    score = FrictionScore(
        company_id=company_id,
        total_score=total_score,
        dominant_friction_type=dominant,
        scoring_breakdown_json={
            "categories": scoring_breakdown,
            "confidence": confidence,
            "scoring_version": SCORING_VERSION_V2,
        },
        scoring_version=SCORING_VERSION_V2,
        open_positions_count=open_positions_count,
        computed_at=datetime.now(timezone.utc),
    )

    db.add(score)
    db.commit()
    db.refresh(score)

    return score
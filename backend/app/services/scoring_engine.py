"""
Friction Radar — Scoring Engine (Rule-Based)

How it works:
  1. Load all signals for the given company from the DB.
  2. For each friction category, iterate over its rules.
  3. A rule "matches" if:
       - Any signal's signal_type appears in rule["signal_types"], OR
       - Any signal's signal_text contains one of rule["keywords"] (case-insensitive).
  4. Each matched rule contributes its weight to the category score.
  5. Deduplication: each rule label counts only once per category
     (even if multiple signals match the same rule).
  6. Total score = sum of all category scores.
  7. Dominant friction type = category with highest score.
  8. Result is saved to friction_scores table.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.friction_categories import FRICTION_CATEGORIES, SCORING_VERSION
from app.core.scoring_rules import SCORING_RULES
from app.core.logging import logger
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore


def _evaluate_rules(signals: List[CompanySignal]) -> Dict[str, Any]:
    """
    Core rule evaluation. Returns the scoring breakdown dict.
    """
    breakdown: Dict[str, Dict] = {}

    for category in FRICTION_CATEGORIES:
        rules = SCORING_RULES.get(category, [])
        category_score = 0.0
        matched_labels = []

        for rule in rules:
            rule_matched = False
            label = rule["label"]
            signal_types = set(rule.get("signal_types", []))
            keywords = [kw.lower() for kw in rule.get("keywords", [])]
            weight = rule.get("weight", 1.0)

            for signal in signals:
                # Match by signal_type
                if signal.signal_type in signal_types:
                    rule_matched = True
                    break
                # Match by keyword in signal_text
                if any(kw in signal.signal_text.lower() for kw in keywords):
                    rule_matched = True
                    break

            if rule_matched:
                category_score += weight
                matched_labels.append(label)

        breakdown[category] = {
            "score": round(category_score, 2),
            "matched_signals": matched_labels,
        }

    return breakdown


def compute_and_persist_score(
    db: Session, company_id: UUID, open_positions_count: Optional[int] = None
) -> FrictionScore:
    """
    Compute a fresh friction score for the given company, persist and return it.
    """
    logger.info(f"[ScoringEngine] Starting scoring for company: {company_id}")

    signals = (
        db.query(CompanySignal).filter(CompanySignal.company_id == company_id).all()
    )
    logger.info(f"[ScoringEngine] Loaded {len(signals)} signals for scoring.")

    if not signals:
        logger.warning(
            f"[ScoringEngine] No signals found for company {company_id}. Producing zero-score result."
        )

    breakdown = _evaluate_rules(signals)

    total_score = round(sum(cat["score"] for cat in breakdown.values()), 2)

    # Dominant = highest-scoring category (fallback to first if all zero)
    dominant = max(
        breakdown, key=lambda c: breakdown[c]["score"], default=FRICTION_CATEGORIES[0]
    )

    logger.info(
        f"[ScoringEngine] Scoring complete. Total: {total_score}, Dominant: {dominant}"
    )

    score = FrictionScore(
        company_id=company_id,
        total_score=total_score,
        dominant_friction_type=dominant,
        scoring_breakdown_json=breakdown,
        scoring_version=SCORING_VERSION,
        open_positions_count=open_positions_count,
        computed_at=datetime.now(timezone.utc),
    )

    db.add(score)
    db.commit()
    db.refresh(score)

    return score

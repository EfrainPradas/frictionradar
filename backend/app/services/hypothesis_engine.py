"""
Friction Radar — Hypothesis Engine

Reads the latest friction score and signals for a company, then generates
a structured opportunity hypothesis using the template-based prompt builder.

Designed to support a future LLM integration without structural changes:
  - Replace `build_hypothesis_from_template(...)` with an LLM call
  - Keep the same return contract
  - The rest of the system stays the same
"""

from uuid import UUID
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.company import Company
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.models.opportunity_hypothesis import OpportunityHypothesis
from app.services.prompt_builders import build_hypothesis_from_template


def generate_and_persist_hypothesis(
    db: Session,
    company_id: UUID,
    friction_score: FrictionScore,
) -> OpportunityHypothesis:
    """
    Use the latest friction score to generate and persist an opportunity hypothesis.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise ValueError(f"Company {company_id} not found.")

    logger.info(f"[HypothesisEngine] Generating hypothesis for company: {company.name}")

    breakdown: dict = friction_score.scoring_breakdown_json or {}
    dominant = friction_score.dominant_friction_type

    # Gather top matched signal labels from all categories
    all_matched_signals = []
    for cat_data in breakdown.values():
        all_matched_signals.extend(cat_data.get("matched_signals", []))

    # Top categories sorted by score
    top_categories = sorted(
        breakdown.keys(),
        key=lambda c: breakdown[c].get("score", 0),
        reverse=True,
    )[:3]

    # Remove duplicates while preserving order
    seen = set()
    top_signals = []
    for s in all_matched_signals:
        if s not in seen:
            seen.add(s)
            top_signals.append(s)

    # Generate text from template builder (swappable with LLM call)
    generated = build_hypothesis_from_template(
        company_name=company.name,
        dominant_friction_type=dominant,
        top_signals=top_signals,
        top_categories=top_categories,
    )

    rationale = {
        "top_signals": top_signals[:5],
        "top_categories": top_categories,
        "total_score": float(friction_score.total_score),
        "scoring_version": friction_score.scoring_version,
    }

    # Deterministic confidence: based on signal richness (max 1.0)
    confidence = min(round(len(top_signals) / 10, 2), 1.0)

    logger.info(
        f"[HypothesisEngine] Generated hypothesis for '{company.name}' "
        f"(dominant: {dominant}, confidence: {confidence})"
    )

    hypothesis = OpportunityHypothesis(
        company_id=company_id,
        friction_score_id=friction_score.id,
        summary=generated["summary"],
        friction_type=dominant,
        suggested_opportunity=generated["suggested_opportunity"],
        rationale_json=rationale,
        llm_confidence=confidence,
    )

    db.add(hypothesis)
    db.commit()
    db.refresh(hypothesis)

    return hypothesis

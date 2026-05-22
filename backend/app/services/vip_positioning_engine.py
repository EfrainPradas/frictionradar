"""VIP Positioning Engine — generates differentiated opportunities for Ascendia VIP users.

For each VIP user, this engine:
  1. Loads their candidate intelligence profile
  2. Aligns against all eligible companies
  3. Filters to top matches
  4. Generates differentiated positioning guidance
  5. Persists FrictionVipOpportunity records

The output is designed to help VIP users understand:
  - WHERE their experience is most strategically valuable
  - WHY specific companies may value them
  - HOW they should position themselves
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.candidate_intelligence import (
    CandidateIntelligenceProfile,
    FrictionVipOpportunity,
    FrictionPositioningRecommendation,
)
from app.models.company import Company
from app.services.alignment_engine import alignment_engine, AlignmentResult
from app.services.candidate_intelligence_extractor import candidate_intelligence_extractor
from app.services.positioning_engine import CANDIDATE_ARCHETYPES
from app.core.friction_categories import FRICTION_CATEGORY_LABELS

logger = get_logger(__name__)

# Maximum opportunities per VIP user
MAX_VIP_OPPORTUNITIES = 25


class VipPositioningEngine:
    """Generate differentiated VIP opportunities for Ascendia VIP users."""

    def generate_opportunities(
        self,
        user_id: UUID,
        db: Session,
        top_n: int = 15,
    ) -> list[FrictionVipOpportunity]:
        """Generate VIP opportunities for a user.

        Steps:
          1. Extract/update candidate intelligence profile
          2. Align against all eligible companies
          3. Select top matches
          4. Generate differentiated guidance
          5. Persist opportunities
        """
        # Step 1: Extract candidate intelligence
        candidate = candidate_intelligence_extractor.extract(user_id, db)

        if not candidate.solved_pain_categories and not candidate.positioning_vectors:
            logger.info(f"VIP: No intelligence extracted for user {user_id}")
            return []

        # Step 2: Align against all eligible companies
        alignment_results = self._align_all(candidate, db)

        if not alignment_results:
            return []

        # Step 3: Sort and select top matches
        alignment_results.sort(key=lambda r: r.alignment_score, reverse=True)
        top_results = alignment_results[:top_n]

        # Step 4-5: Generate and persist opportunities
        opportunities = []
        for result in top_results:
            opp = self._generate_and_persist_opportunity(
                candidate, result, db
            )
            if opp:
                opportunities.append(opp)

        # Deactivate old opportunities that didn't make the cut
        self._deactivate_stale_opportunities(user_id, opportunities, db)

        logger.info(
            f"VIP: Generated {len(opportunities)} opportunities for user {user_id}"
        )
        return opportunities

    def get_active_opportunities(
        self,
        user_id: UUID,
        db: Session,
    ) -> list[FrictionVipOpportunity]:
        """Get currently active VIP opportunities for a user."""
        return (
            db.query(FrictionVipOpportunity)
            .filter(
                FrictionVipOpportunity.user_id == user_id,
                FrictionVipOpportunity.is_active == True,  # noqa: E712
            )
            .order_by(FrictionVipOpportunity.alignment_score.desc())
            .all()
        )

    def _align_all(
        self,
        candidate: CandidateIntelligenceProfile,
        db: Session,
    ) -> list[AlignmentResult]:
        """Align candidate against all eligible companies.

        Companies qualify if they are positioning_eligible AND have at least one of:
        - Classified job roles (hiring evidence)
        - Detected signals
        - A concrete diagnostic state (not 'insufficient_evidence')
        """
        from app.models.friction_score import FrictionScore

        CONCRETE_STATES = {
            "ready_for_positioning",
            "specific_pain_identified",
            "specific_pain_emerging",
            "broad_hiring_pattern_detected",
        }

        companies = (
            db.query(Company)
            .filter(Company.positioning_eligible == True)  # noqa: E712
            .filter(
                Company.latest_diagnostic_state.in_(CONCRETE_STATES)
            )
            .all()
        )

        results = []
        for company in companies:
            try:
                score = (
                    db.query(FrictionScore)
                    .filter(FrictionScore.company_id == company.id)
                    .order_by(FrictionScore.computed_at.desc())
                    .first()
                )

                result = alignment_engine.align(
                    candidate=candidate,
                    company=company,
                    score=score,
                    db=db,
                )

                if result.alignment_tier != "none":
                    results.append(result)
            except Exception as e:
                logger.warning(f"VIP alignment failed for company {company.id}: {e}")
                continue

        return results

    def _generate_and_persist_opportunity(
        self,
        candidate: CandidateIntelligenceProfile,
        alignment: AlignmentResult,
        db: Session,
    ) -> Optional[FrictionVipOpportunity]:
        """Generate and persist a VIP opportunity from an alignment result."""
        company = db.query(Company).filter(Company.id == alignment.company_id).first()
        if not company:
            return None

        # Determine opportunity type
        opp_type = self._determine_opportunity_type(alignment)

        # Build company pain summary
        pain_summary = self._build_pain_summary(company, alignment)

        # Build positioning guidance
        positioning = self._build_strategic_positioning(candidate, alignment, company)

        # Build why_you_fit / why_they_value_you
        why_fit = self._build_why_you_fit(candidate, alignment)
        why_value = self._build_why_they_value_you(candidate, alignment, company)

        # Build resume emphasis
        resume = alignment.resume_emphasis or []

        # Build networking positioning
        networking = alignment.networking_guidance or ""

        # Build interview positioning
        interview = alignment.interview_positioning or ""

        # Upsert
        existing = (
            db.query(FrictionVipOpportunity)
            .filter(
                FrictionVipOpportunity.user_id == candidate.user_id,
                FrictionVipOpportunity.company_id == company.id,
                FrictionVipOpportunity.is_active == True,  # noqa: E712
            )
            .first()
        )

        values = {
            "alignment_score": alignment.alignment_score,
            "opportunity_type": opp_type,
            "company_pain_summary": pain_summary,
            "strategic_positioning": positioning,
            "resume_emphasis": resume,
            "networking_positioning": networking,
            "interview_positioning": interview,
            "why_you_fit": why_fit,
            "why_they_value_you": why_value,
        }

        if existing:
            for key, val in values.items():
                setattr(existing, key, val)
            db.commit()
            db.refresh(existing)
            return existing

        opp = FrictionVipOpportunity(
            user_id=candidate.user_id,
            company_id=company.id,
            is_active=True,
            **values,
        )
        db.add(opp)
        db.commit()
        db.refresh(opp)

        # Also create detailed positioning recommendation
        self._persist_positioning_recommendation(
            candidate, alignment, company, db
        )

        return opp

    def _determine_opportunity_type(self, alignment: AlignmentResult) -> str:
        """Map alignment tier to opportunity type."""
        if alignment.alignment_tier == "strong":
            return "stable_fit"
        if alignment.alignment_tier == "moderate":
            return "accelerated_positioning"
        return "early_positioning"

    def _build_pain_summary(
        self,
        company: Company,
        alignment: AlignmentResult,
    ) -> str:
        """Build a concise summary of the company's organizational pain."""
        pain_parts = []

        if alignment.matched_pain_categories:
            for match in alignment.matched_pain_categories[:3]:
                cat_label = FRICTION_CATEGORY_LABELS.get(
                    match["category"], match["category"]
                )
                pain_parts.append(f"{cat_label}")

        if not pain_parts:
            return f"{company.name} shows hiring patterns that suggest organizational pressure."

        return f"{company.name} shows signals of {', '.join(pain_parts).lower()}."

    def _build_strategic_positioning(
        self,
        candidate: CandidateIntelligenceProfile,
        alignment: AlignmentResult,
        company: Company,
    ) -> str:
        """Build strategic positioning guidance."""
        solved = candidate.solved_pain_categories or []
        top_solved = solved[0]["label"] if solved else "your area"

        if alignment.alignment_tier == "strong":
            return (
                f"Your experience in {top_solved.lower()} strongly aligns with "
                f"{company.name}'s current organizational needs. Position yourself "
                f"as someone who can address their pain directly, drawing from "
                f"your demonstrated outcomes in similar contexts."
            )
        elif alignment.alignment_tier == "moderate":
            return (
                f"Your background in {top_solved.lower()} has relevant overlap "
                f"with {company.name}'s needs. Emphasize transferable outcomes "
                f"and ask probing questions to confirm alignment in early conversations."
            )
        return (
            f"Early signals suggest potential alignment with {company.name}. "
            f"Use exploratory conversations to validate whether their pain matches "
            f"your {top_solved.lower()} experience."
        )

    def _build_why_you_fit(
        self,
        candidate: CandidateIntelligenceProfile,
        alignment: AlignmentResult,
    ) -> str:
        """Build 'why you fit' explanation."""
        strengths = alignment.matched_strengths or []
        top = strengths[0] if strengths else None

        if not top:
            return "Your experience has relevant overlap with this company's needs."

        dim_label = top["dimension"].replace("_strength", "").replace("_", " ")
        return (
            f"Your {dim_label} capabilities directly address the type of "
            f"organizational pressure this company is experiencing."
        )

    def _build_why_they_value_you(
        self,
        candidate: CandidateIntelligenceProfile,
        alignment: AlignmentResult,
        company: Company,
    ) -> str:
        """Build 'why they value you' explanation."""
        solved = candidate.solved_pain_categories or []
        if not solved:
            return "Your professional experience is relevant to their current hiring needs."

        top_solved = solved[0]
        return (
            f"Companies experiencing {top_solved['label'].lower()} pressure "
            f"like {company.name} value professionals who have already solved "
            f"similar challenges — they need proven execution, not just theory."
        )

    def _persist_positioning_recommendation(
        self,
        candidate: CandidateIntelligenceProfile,
        alignment: AlignmentResult,
        company: Company,
        db: Session,
    ) -> None:
        """Persist a detailed positioning recommendation."""
        # Check if exists
        existing = (
            db.query(FrictionPositioningRecommendation)
            .filter(
                FrictionPositioningRecommendation.user_id == candidate.user_id,
                FrictionPositioningRecommendation.company_id == company.id,
            )
            .first()
        )

        values = {
            "why_you_fit": self._build_why_you_fit(candidate, alignment),
            "why_they_value_you": self._build_why_they_value_you(candidate, alignment, company),
            "positioning_summary": alignment.positioning_recommendation,
            "suggested_resume_emphasis": alignment.resume_emphasis or [],
            "networking_positioning": alignment.networking_guidance or "",
            "interview_positioning": alignment.interview_positioning or "",
            "company_pain_summary": self._build_pain_summary(company, alignment),
        }

        if existing:
            for key, val in values.items():
                setattr(existing, key, val)
            db.commit()
            return

        rec = FrictionPositioningRecommendation(
            user_id=candidate.user_id,
            company_id=company.id,
            **values,
        )
        db.add(rec)
        db.commit()

    def _deactivate_stale_opportunities(
        self,
        user_id: UUID,
        active_opportunities: list[FrictionVipOpportunity],
        db: Session,
    ) -> None:
        """Deactivate opportunities that are no longer in the top set."""
        active_ids = {opp.company_id for opp in active_opportunities}

        stale = (
            db.query(FrictionVipOpportunity)
            .filter(
                FrictionVipOpportunity.user_id == user_id,
                FrictionVipOpportunity.is_active == True,  # noqa: E712
                ~FrictionVipOpportunity.company_id.in_(active_ids),
            )
            .all()
        )

        for opp in stale:
            opp.is_active = False

        if stale:
            db.commit()
            logger.info(f"VIP: Deactivated {len(stale)} stale opportunities for user {user_id}")


vip_positioning_engine = VipPositioningEngine()
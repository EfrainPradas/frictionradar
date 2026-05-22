"""Candidate ↔ Organizational Pain Alignment Engine.

Core principle: Companies hire around pain. Candidates reveal solved pain
through accomplishments. The engine connects both.

Pipeline:
  1. Load candidate intelligence profile (solved pain, strengths, vectors)
  2. Load company friction profile (dominant pain, dimensions, evidence)
  3. Compute alignment: match candidate solved-pain against company pain
  4. Generate strategic fit explanation
  5. Generate positioning recommendation
  6. Produce interview / resume / networking guidance

The alignment is deterministic and auditable (no LLM calls).
"""
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.friction_categories import FRICTION_CATEGORIES, FRICTION_CATEGORY_LABELS
from app.core.logging import get_logger
from app.models.candidate_intelligence import (
    CandidateIntelligenceProfile,
    FrictionCandidateMatch,
    FrictionAlignmentScore,
)
from app.models.company import Company
from app.models.friction_score import FrictionScore
from app.models.company_signal import CompanySignal
from app.services.positioning_engine import positioning_engine, CANDIDATE_ARCHETYPES

logger = get_logger(__name__)


# ── Pain category to archetype strength mapping ────────────────────────────
# Maps a company's dominant pain category to the candidate strength
# dimensions that most strongly align with that pain.

PAIN_STRENGTH_ALIGNMENT = {
    "reporting_fragmentation": {
        "primary": ["analytics_strength", "transformation_strength"],
        "secondary": ["operational_strength", "modernization_strength"],
    },
    "process_inefficiency": {
        "primary": ["operational_strength", "transformation_strength"],
        "secondary": ["analytics_strength", "leadership_strength"],
    },
    "tooling_inconsistency": {
        "primary": ["modernization_strength", "operational_strength"],
        "secondary": ["transformation_strength", "analytics_strength"],
    },
    "scaling_strain": {
        "primary": ["leadership_strength", "transformation_strength"],
        "secondary": ["operational_strength", "modernization_strength"],
    },
    "customer_experience_friction": {
        "primary": ["analytics_strength", "operational_strength"],
        "secondary": ["leadership_strength", "transformation_strength"],
    },
}


# ── Positioning templates by alignment strength ─────────────────────────────

POSITIONING_TEMPLATES = {
    "strong": {
        "prefix": "Your experience strongly aligns with",
        "fit_template": (
            "Your experience in {solved_pain} strongly aligns with companies "
            "currently experiencing {company_pain}. "
            "Your {strength_area} positions you as someone who can address this pain directly."
        ),
        "interview_template": (
            "In interviews, emphasize how your work in {solved_pain} prepared you "
            "to help organizations facing {company_pain}. Share specific examples "
            "of how you diagnosed and resolved similar challenges."
        ),
        "resume_template": (
            "On your resume, highlight accomplishments in {solved_pain} — "
            "especially quantified outcomes that demonstrate your ability to "
            "address {company_pain}."
        ),
    },
    "moderate": {
        "prefix": "Your experience partially aligns with",
        "fit_template": (
            "Your background includes relevant experience in {solved_pain} "
            "that could benefit companies experiencing {company_pain}. "
            "Consider emphasizing your {strength_area} in your positioning."
        ),
        "interview_template": (
            "In interviews, explore whether the company's {company_pain} aligns "
            "with areas where you have {solved_pain} experience. "
            "Ask questions that reveal the depth of their pain."
        ),
        "resume_template": (
            "On your resume, include accomplishments that demonstrate "
            "capability in areas related to {company_pain}."
        ),
    },
    "exploratory": {
        "prefix": "Early signals suggest potential alignment with",
        "fit_template": (
            "Based on available signals, there may be alignment between "
            "your experience and companies experiencing {company_pain}. "
            "Further exploration is recommended."
        ),
        "interview_template": (
            "Use the interview to validate whether the company's pain "
            "matches your strengths. Ask about their biggest operational "
            "challenges and listen for {company_pain} signals."
        ),
        "resume_template": (
            "Include relevant experience on your resume but don't "
            "overemphasize without confirming the company's actual needs."
        ),
    },
}


@dataclass
class AlignmentResult:
    """Complete alignment result for a candidate-company pair."""
    user_id: UUID
    company_id: UUID
    alignment_score: float = 0.0
    alignment_tier: str = "none"  # strong, moderate, exploratory, none

    strategic_fit: str = ""
    positioning_recommendation: str = ""
    interview_positioning: str = ""
    resume_emphasis: list = field(default_factory=list)
    networking_guidance: str = ""

    matched_pain_categories: list = field(default_factory=list)
    matched_strengths: list = field(default_factory=list)

    pain_category_scores: dict = field(default_factory=dict)
    strength_category_scores: dict = field(default_factory=dict)


class AlignmentEngine:
    """Matches candidate strengths against organizational pain."""

    def align(
        self,
        candidate: CandidateIntelligenceProfile,
        company: Company,
        score: Optional[FrictionScore] = None,
        signals: Optional[list] = None,
        db: Optional[Session] = None,
    ) -> AlignmentResult:
        """Compute alignment between a candidate and a company.

        Steps:
          1. Identify company's dominant pain from friction score
          2. Match candidate solved-pain categories against company pain
          3. Weight by strength dimension alignment
          4. Compute overall alignment score
          5. Generate positioning guidance
        """
        result = AlignmentResult(
            user_id=candidate.user_id,
            company_id=company.id,
        )

        # Store db session for company pain lookup
        self._db = db

        # Step 1: Determine company's pain profile
        company_pain = self._get_company_pain(company, score, signals)

        # Step 2: Direct pain category matching
        direct_matches = self._match_pain_categories(candidate, company_pain)
        result.matched_pain_categories = direct_matches

        # Step 3: Strength dimension matching
        strength_matches = self._match_strengths(candidate, company_pain)
        result.matched_strengths = strength_matches

        # Step 4: Compute alignment score
        alignment_score = self._compute_alignment_score(
            direct_matches, strength_matches, candidate, company_pain
        )
        result.alignment_score = round(alignment_score, 3)

        # Step 5: Determine tier
        if alignment_score >= 0.65:
            result.alignment_tier = "strong"
        elif alignment_score >= 0.35:
            result.alignment_tier = "moderate"
        elif alignment_score >= 0.15:
            result.alignment_tier = "exploratory"
        else:
            result.alignment_tier = "none"

        # Step 6: Generate guidance
        if result.alignment_tier != "none":
            templates = POSITIONING_TEMPLATES.get(result.alignment_tier, POSITIONING_TEMPLATES["exploratory"])

            top_solved = candidate.solved_pain_categories[0]["label"] if candidate.solved_pain_categories else "your area"
            top_company_pain = FRICTION_CATEGORY_LABELS.get(
                company_pain.get("dominant_friction", ""), "organizational pain"
            )
            top_strength = self._get_top_strength_label(candidate)

            result.strategic_fit = templates["fit_template"].format(
                solved_pain=top_solved.lower(),
                company_pain=top_company_pain.lower(),
                strength_area=top_strength,
            )
            result.interview_positioning = templates["interview_template"].format(
                solved_pain=top_solved.lower(),
                company_pain=top_company_pain.lower(),
            )
            result.resume_emphasis = self._build_resume_emphasis(candidate, company_pain)
            result.networking_guidance = self._build_networking_guidance(candidate, company_pain)

            # Combine fit + positioning
            result.positioning_recommendation = result.strategic_fit

        # Category scores
        result.pain_category_scores = {
            m["category"]: m["score"] for m in direct_matches
        }
        result.strength_category_scores = {
            m["dimension"]: m["alignment"] for m in strength_matches
        }

        return result

    def align_and_persist(
        self,
        candidate: CandidateIntelligenceProfile,
        company: Company,
        db: Session,
        score: Optional[FrictionScore] = None,
        signals: Optional[list] = None,
    ) -> FrictionCandidateMatch:
        """Align and persist the result to friction_candidate_matches."""
        result = self.align(candidate, company, score, signals, db)

        # Upsert
        existing = (
            db.query(FrictionCandidateMatch)
            .filter(
                FrictionCandidateMatch.user_id == candidate.user_id,
                FrictionCandidateMatch.company_id == company.id,
            )
            .first()
        )

        values = {
            "alignment_score": result.alignment_score,
            "strategic_fit": result.strategic_fit,
            "positioning_recommendation": result.positioning_recommendation,
            "interview_positioning": result.interview_positioning,
            "resume_emphasis": result.resume_emphasis,
            "networking_guidance": result.networking_guidance,
            "matched_pain_categories": result.matched_pain_categories,
            "matched_strengths": result.matched_strengths,
            "computation_version": "1.0.0",
        }

        if existing:
            for key, val in values.items():
                setattr(existing, key, val)
            db.commit()
            db.refresh(existing)
            return existing

        match = FrictionCandidateMatch(
            user_id=candidate.user_id,
            company_id=company.id,
            **values,
        )
        db.add(match)
        db.commit()
        db.refresh(match)
        return match

    def align_candidate_to_all(
        self,
        candidate: CandidateIntelligenceProfile,
        db: Session,
        min_score: float = 0.15,
    ) -> list[FrictionCandidateMatch]:
        """Align a candidate against all eligible companies.

        Returns matches with alignment_score >= min_score.
        """
        from app.services.positioning_engine import is_company_positioning_eligible

        companies = db.query(Company).filter(
            Company.positioning_eligible == True  # noqa: E712
        ).all()

        matches = []
        for company in companies:
            try:
                match = self.align_and_persist(candidate, company, db)
                if match.alignment_score >= min_score:
                    matches.append(match)
            except Exception as e:
                logger.warning(f"Alignment failed for company {company.id}: {e}")
                continue

        matches.sort(key=lambda m: m.alignment_score, reverse=True)
        return matches

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_company_pain(
        self,
        company: Company,
        score: Optional[FrictionScore],
        signals: Optional[list],
    ) -> dict:
        """Extract company pain profile from friction_company_profile, score, or signals."""
        dominant = "scaling_strain"  # default
        category_scores = {}

        # Prefer friction_company_profile if available
        if hasattr(self, '_db') and self._db:
            from app.models.candidate_intelligence import FrictionCompanyProfile
            profile = (
                self._db.query(FrictionCompanyProfile)
                .filter(FrictionCompanyProfile.company_id == company.id)
                .first()
            )
            if profile and profile.dominant_pain:
                dominant = profile.dominant_pain
                if profile.pain_dimensions:
                    category_scores = profile.pain_dimensions if isinstance(profile.pain_dimensions, dict) else {}

        # Fallback to FrictionScore
        if not category_scores and score:
            dominant = score.dominant_friction_type or dominant
            if score.dominant_friction_type == "no_signal":
                dominant = "scaling_strain"

            breakdown = score.scoring_breakdown_json or {}
            categories = breakdown.get("categories", {})
            for cat, data in categories.items():
                category_scores[cat] = data.get("normalized_score", 0.0)

        return {
            "dominant_friction": dominant,
            "category_scores": category_scores,
        }

    def _match_pain_categories(
        self,
        candidate: CandidateIntelligenceProfile,
        company_pain: dict,
    ) -> list[dict]:
        """Match candidate solved-pain categories against company pain."""
        matches = []

        # Build candidate pain-category strength map
        candidate_pain_strength = {}
        for vec in (candidate.positioning_vectors or []):
            cat = vec.get("pain_category", "")
            strength = vec.get("match_strength", 0.0)
            candidate_pain_strength[cat] = max(
                candidate_pain_strength.get(cat, 0), strength
            )

        # Also check solved_pain_categories
        for pain in (candidate.solved_pain_categories or []):
            cat = pain.get("category", "")
            evidence = pain.get("evidence_count", 0)
            strength = min(0.95, round(evidence * 0.2, 2))
            candidate_pain_strength[cat] = max(
                candidate_pain_strength.get(cat, 0), strength
            )

        # Match against company pain
        company_scores = company_pain.get("category_scores", {})
        dominant = company_pain.get("dominant_friction", "")

        for category, cand_strength in candidate_pain_strength.items():
            comp_strength = company_scores.get(category, 0.0)
            # If this is the company's dominant pain, add base weight
            if category == dominant and comp_strength == 0:
                comp_strength = 0.3  # implicit weight for dominant

            # Alignment = min(candidate_solved, company_pain)
            # High candidate strength + high company pain = strong alignment
            alignment = min(cand_strength, max(comp_strength, 0.3 if category == dominant else 0.0))

            if alignment >= 0.1:
                matches.append({
                    "category": category,
                    "candidate_strength": round(cand_strength, 2),
                    "company_pain": round(comp_strength, 2),
                    "score": round(alignment, 2),
                })

        matches.sort(key=lambda m: m["score"], reverse=True)
        return matches

    def _match_strengths(
        self,
        candidate: CandidateIntelligenceProfile,
        company_pain: dict,
    ) -> list[dict]:
        """Match candidate strength dimensions against company pain needs."""
        dominant = company_pain.get("dominant_friction", "")
        alignment_config = PAIN_STRENGTH_ALIGNMENT.get(dominant, {})

        primary_dims = alignment_config.get("primary", [])
        secondary_dims = alignment_config.get("secondary", [])

        matches = []
        strength_map = {
            "transformation_strength": candidate.transformation_strength or 0,
            "analytics_strength": candidate.analytics_strength or 0,
            "leadership_strength": candidate.leadership_strength or 0,
            "operational_strength": candidate.operational_strength or 0,
            "modernization_strength": candidate.modernization_strength or 0,
        }

        for dim, value in strength_map.items():
            if value < 0.1:
                continue

            # Weight: primary dims get 1.0x, secondary get 0.6x
            if dim in primary_dims:
                alignment = round(value * 1.0, 2)
            elif dim in secondary_dims:
                alignment = round(value * 0.6, 2)
            else:
                alignment = round(value * 0.3, 2)

            matches.append({
                "dimension": dim,
                "candidate_value": value,
                "alignment": alignment,
                "role": "primary" if dim in primary_dims else (
                    "secondary" if dim in secondary_dims else "supplementary"
                ),
            })

        matches.sort(key=lambda m: m["alignment"], reverse=True)
        return matches

    def _compute_alignment_score(
        self,
        direct_matches: list[dict],
        strength_matches: list[dict],
        candidate: CandidateIntelligenceProfile,
        company_pain: dict,
    ) -> float:
        """Compute overall alignment score (0.0-1.0).

        Formula:
          score = (pain_component * 0.6) + (strength_component * 0.4)

        pain_component: weighted average of direct match scores, weighted by
                        company pain intensity for each matched category.
                        This differentiates companies where our solved pain
                        aligns with their STRONGEST pain vs. a secondary pain.
        strength_component: weighted average of primary strength matches
        """
        # Pain component — weight by company pain intensity
        pain_score = 0.0
        if direct_matches:
            category_scores = company_pain.get("category_scores", {})
            total_weight = 0.0
            weighted_sum = 0.0
            for match in direct_matches:
                cat = match["category"]
                company_intensity = category_scores.get(cat, 0.3)
                weight = company_intensity + 0.2  # base weight so low-intensity still counts
                weighted_sum += match["score"] * weight
                total_weight += weight
            if total_weight > 0:
                pain_score = weighted_sum / total_weight
            else:
                pain_score = direct_matches[0]["score"]

        # Strength component
        strength_score = 0.0
        primary_matches = [m for m in strength_matches if m["role"] == "primary"]
        if primary_matches:
            strength_score = sum(m["alignment"] for m in primary_matches) / len(primary_matches)

        total = (pain_score * 0.6) + (strength_score * 0.4)
        return min(1.0, total)

    def _get_top_strength_label(self, candidate: CandidateIntelligenceProfile) -> str:
        """Get human-readable label for top strength dimension."""
        strengths = {
            "transformation": candidate.transformation_strength or 0,
            "analytics": candidate.analytics_strength or 0,
            "leadership": candidate.leadership_strength or 0,
            "operational": candidate.operational_strength or 0,
            "modernization": candidate.modernization_strength or 0,
        }
        if not any(strengths.values()):
            return "general experience"

        labels = {
            "transformation": "transformation experience",
            "analytics": "analytics and data expertise",
            "leadership": "leadership capabilities",
            "operational": "operational execution skills",
            "modernization": "modernization experience",
        }
        top = max(strengths, key=strengths.get)
        return labels.get(top, "professional experience")

    def _build_resume_emphasis(
        self,
        candidate: CandidateIntelligenceProfile,
        company_pain: dict,
    ) -> list[str]:
        """Build resume emphasis recommendations."""
        emphasis = []
        dominant = company_pain.get("dominant_friction", "")

        archetype = CANDIDATE_ARCHETYPES.get(dominant, {})
        if archetype:
            emphasis = list(archetype.get("resume_emphasis", []))

        # Add candidate-specific solved pain as emphasis
        for pain in (candidate.solved_pain_categories or [])[:2]:
            emphasis.append(
                f"Experience addressing {pain['label'].lower()} challenges"
            )

        return emphasis[:5]

    def _build_networking_guidance(
        self,
        candidate: CandidateIntelligenceProfile,
        company_pain: dict,
    ) -> str:
        """Build networking positioning guidance."""
        dominant = company_pain.get("dominant_friction", "")

        archetype = CANDIDATE_ARCHETYPES.get(dominant, {})
        if archetype and archetype.get("networking_angle"):
            return archetype["networking_angle"]

        return (
            "Ask about their biggest operational challenge. "
            "The specificity of their answer reveals the pain you can address."
        )


alignment_engine = AlignmentEngine()
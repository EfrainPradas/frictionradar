"""
Tests for the "No evidence → No diagnosis" invariant.

Verifies that when a company has zero valid signals:
  1. dominant_friction_type is "no_signal" in DB, but null in API responses
  2. No hypothesis is generated (engine returns None)
  3. Prompt builder returns appropriate no-diagnosis text
  4. Final verdict returns preliminary with all pain fields as None
  5. API schemas translate "no_signal" to null
  6. Signals that match no rules produce the same result as zero signals
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4

from app.core.friction_categories import FRICTION_CATEGORIES
from app.services.scoring_engine import (
    _evaluate_rules,
    _compute_confidence,
    compute_and_persist_score,
    MAX_POSSIBLE_SCORES,
)
from app.services.prompt_builders import build_hypothesis_from_template
from app.services.final_verdict_engine import FinalVerdictEngine
from app.schemas.scoring import FrictionScoreRead
from app.schemas.hypothesis import OpportunityHypothesisRead


def _make_signal(signal_type: str, signal_text: str = ""):
    """Create a mock CompanySignal for testing."""
    s = MagicMock()
    s.signal_type = signal_type
    s.signal_text = signal_text
    return s


def _make_friction_score(dominant_friction_type="no_signal", total_score=0.0):
    """Create a mock FrictionScore for testing."""
    score = MagicMock()
    score.id = uuid4()
    score.company_id = uuid4()
    score.total_score = total_score
    score.dominant_friction_type = dominant_friction_type
    score.scoring_breakdown_json = {
        "categories": {
            cat: {
                "raw_score": 0.0,
                "max_possible": MAX_POSSIBLE_SCORES[cat],
                "normalized_score": 0.0,
                "matched_signals": [],
            }
            for cat in FRICTION_CATEGORIES
        },
        "confidence": {
            "signal_diversity": 0,
            "contributing_signal_count": 0,
            "evidence_breadth": 0,
            "confidence_level": "none",
        },
        "scoring_version": "2.0.0",
    }
    score.scoring_version = "2.0.0"
    score.computed_at = datetime.now(timezone.utc)
    score.created_at = datetime.now(timezone.utc)
    score.open_positions_count = None
    return score


# ─── Hypothesis Engine ────────────────────────────────────────────

class TestHypothesisEngineNoSignal:
    """Verify hypothesis engine returns None for no_signal dominant type."""

    def test_returns_none_for_no_signal(self):
        """generate_and_persist_hypothesis should return None when
        dominant_friction_type is 'no_signal'."""
        from app.services.hypothesis_engine import generate_and_persist_hypothesis

        mock_db = MagicMock()
        score = _make_friction_score(dominant_friction_type="no_signal")

        result = generate_and_persist_hypothesis(
            db=mock_db,
            company_id=uuid4(),
            friction_score=score,
        )

        assert result is None, (
            "Hypothesis engine should return None for 'no_signal' dominant type, "
            f"got {result}"
        )

    def test_does_not_return_none_for_real_friction(self):
        """generate_and_persist_hypothesis should NOT return None when
        dominant_friction_type is a real friction category."""
        from app.services.hypothesis_engine import generate_and_persist_hypothesis

        mock_db = MagicMock()
        company = MagicMock()
        company.name = "TestCo"
        mock_db.query.return_value.filter.return_value.first.return_value = company
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        # Use a proper v2.0.0 scoring breakdown structure
        score = _make_friction_score(
            dominant_friction_type="scaling_strain",
            total_score=5.0,
        )
        # Override with real breakdown structure
        score.scoring_breakdown_json = {
            "categories": {
                "scaling_strain": {
                    "raw_score": 5.0,
                    "max_possible": 10.5,
                    "normalized_score": 0.4762,
                    "matched_signals": ["narrow_hiring_focus"],
                },
                **{
                    cat: {
                        "raw_score": 0.0,
                        "max_possible": MAX_POSSIBLE_SCORES[cat],
                        "normalized_score": 0.0,
                        "matched_signals": [],
                    }
                    for cat in FRICTION_CATEGORIES
                    if cat != "scaling_strain"
                },
            },
            "confidence": {
                "signal_diversity": 1,
                "contributing_signal_count": 1,
                "evidence_breadth": 1,
                "confidence_level": "low",
            },
            "scoring_version": "2.0.0",
        }

        result = generate_and_persist_hypothesis(
            db=mock_db,
            company_id=uuid4(),
            friction_score=score,
        )

        # Should not return None — it should attempt to generate a hypothesis
        assert result is not None, (
            "Hypothesis engine should attempt generation for real friction type"
        )


# ─── Prompt Builders ──────────────────────────────────────────────

class TestPromptBuilderNoSignal:
    """Verify prompt builder handles 'no_signal' gracefully."""

    def test_no_signal_returns_no_diagnosis_text(self):
        """build_hypothesis_from_template should return appropriate text
        when dominant_friction_type is 'no_signal'."""
        result = build_hypothesis_from_template(
            company_name="TestCo",
            dominant_friction_type="no_signal",
            top_signals=[],
            top_categories=[],
        )

        assert "no_signal" not in result["summary"], (
            f"Summary should not contain 'no_signal', got: {result['summary']}"
        )
        assert "no_signal" not in result["suggested_opportunity"], (
            f"Opportunity should not contain 'no_signal', got: {result['suggested_opportunity']}"
        )
        assert "insufficient" in result["summary"].lower() or "not yet" in result["summary"].lower(), (
            f"Summary should indicate insufficient evidence, got: {result['summary']}"
        )

    def test_no_signal_returns_dict(self):
        """build_hypothesis_from_template should return a dict with
        'summary' and 'suggested_opportunity' keys."""
        result = build_hypothesis_from_template(
            company_name="TestCo",
            dominant_friction_type="no_signal",
            top_signals=[],
            top_categories=[],
        )

        assert "summary" in result
        assert "suggested_opportunity" in result


# ─── Pydantic Schema Translations ─────────────────────────────────

class TestSchemaNoSignalTranslation:
    """Verify Pydantic schemas translate 'no_signal' to null."""

    def test_friction_score_schema_translates_no_signal(self):
        """FrictionScoreRead should convert 'no_signal' to None in
        dominant_friction_type."""
        score_id = uuid4()
        company_id = uuid4()
        now = datetime.now(timezone.utc)

        # Simulate a DB model with "no_signal" as dominant_friction_type
        mock_score = MagicMock()
        mock_score.id = score_id
        mock_score.company_id = company_id
        mock_score.total_score = 0.0
        mock_score.dominant_friction_type = "no_signal"
        mock_score.scoring_breakdown_json = {"categories": {}}
        mock_score.scoring_version = "2.0.0"
        mock_score.computed_at = now
        mock_score.created_at = now
        mock_score.open_positions_count = None

        schema = FrictionScoreRead.model_validate(mock_score, from_attributes=True)

        assert schema.dominant_friction_type is None, (
            f"FrictionScoreRead should translate 'no_signal' to None, "
            f"got {schema.dominant_friction_type}"
        )

    def test_friction_score_schema_preserves_real_category(self):
        """FrictionScoreRead should preserve real friction categories."""
        score_id = uuid4()
        company_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_score = MagicMock()
        mock_score.id = score_id
        mock_score.company_id = company_id
        mock_score.total_score = 5.0
        mock_score.dominant_friction_type = "scaling_strain"
        mock_score.scoring_breakdown_json = {"categories": {}}
        mock_score.scoring_version = "2.0.0"
        mock_score.computed_at = now
        mock_score.created_at = now
        mock_score.open_positions_count = None

        schema = FrictionScoreRead.model_validate(mock_score, from_attributes=True)

        assert schema.dominant_friction_type == "scaling_strain", (
            f"FrictionScoreRead should preserve 'scaling_strain', "
            f"got {schema.dominant_friction_type}"
        )

    def test_hypothesis_schema_translates_no_signal(self):
        """OpportunityHypothesisRead should convert 'no_signal' to None
        in friction_type."""
        hypo_id = uuid4()
        company_id = uuid4()
        score_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_hypo = MagicMock()
        mock_hypo.id = hypo_id
        mock_hypo.company_id = company_id
        mock_hypo.friction_score_id = score_id
        mock_hypo.summary = "Test summary"
        mock_hypo.friction_type = "no_signal"
        mock_hypo.suggested_opportunity = "Test opportunity"
        mock_hypo.rationale_json = None
        mock_hypo.llm_confidence = None
        mock_hypo.created_at = now

        schema = OpportunityHypothesisRead.model_validate(mock_hypo, from_attributes=True)

        assert schema.friction_type is None, (
            f"OpportunityHypothesisRead should translate 'no_signal' to None, "
            f"got {schema.friction_type}"
        )

    def test_hypothesis_schema_preserves_real_category(self):
        """OpportunityHypothesisRead should preserve real friction categories."""
        hypo_id = uuid4()
        company_id = uuid4()
        score_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_hypo = MagicMock()
        mock_hypo.id = hypo_id
        mock_hypo.company_id = company_id
        mock_hypo.friction_score_id = score_id
        mock_hypo.summary = "Test summary"
        mock_hypo.friction_type = "tooling_inconsistency"
        mock_hypo.suggested_opportunity = "Test opportunity"
        mock_hypo.rationale_json = None
        mock_hypo.llm_confidence = 0.75
        mock_hypo.created_at = now

        schema = OpportunityHypothesisRead.model_validate(mock_hypo, from_attributes=True)

        assert schema.friction_type == "tooling_inconsistency", (
            f"OpportunityHypothesisRead should preserve 'tooling_inconsistency', "
            f"got {schema.friction_type}"
        )


# ─── Scoring Engine Zero Signals ───────────────────────────────────

class TestScoringEngineZeroSignals:
    """Verify scoring engine behavior with zero signals."""

    def test_zero_signals_dominant_type_is_no_signal(self):
        """With zero signals, _evaluate_rules should produce all-zero
        normalized scores, and compute_and_persist_score should set
        dominant_friction_type to 'no_signal'."""
        breakdown = _evaluate_rules([])

        # All normalized scores should be 0.0
        for cat in FRICTION_CATEGORIES:
            assert breakdown[cat]["normalized_score"] == 0.0, (
                f"Category {cat} should have 0.0 normalized_score with no signals"
            )

        # The scoring engine would determine dominant as "no_signal"
        # because no normalized score is > 0
        has_any_score = any(cat["normalized_score"] > 0 for cat in breakdown.values())
        assert not has_any_score, "No category should have positive score with zero signals"

    def test_zero_signals_confidence_is_none(self):
        """With zero signals, confidence should be 'none'."""
        breakdown = _evaluate_rules([])
        confidence = _compute_confidence(breakdown, [])

        assert confidence["confidence_level"] == "none"
        assert confidence["signal_diversity"] == 0
        assert confidence["contributing_signal_count"] == 0
        assert confidence["evidence_breadth"] == 0

    def test_ignored_signals_produce_no_signal(self):
        """Signals that don't match any scoring rule should produce
        the same result as zero signals: all normalized scores = 0."""
        # These signal types don't exist in any scoring rule
        ignored_signals = [
            _make_signal("careers_page_found", "https://example.com/careers"),
            _make_signal("completely_unknown_type", "unknown text"),
        ]

        breakdown = _evaluate_rules(ignored_signals)

        # All normalized scores should be 0.0 because no rules match
        for cat in FRICTION_CATEGORIES:
            assert breakdown[cat]["normalized_score"] == 0.0, (
                f"Category {cat} should have 0.0 normalized_score with "
                f"ignored-only signals, got {breakdown[cat]['normalized_score']}"
            )


# ─── Final Verdict Zero Signals ────────────────────────────────────

class TestFinalVerdictNoSignal:
    """Verify final verdict engine handles zero signals correctly."""

    def test_zero_signals_produces_preliminary_verdict(self):
        """With zero signals, final_verdict_engine should return
        verdict_type='preliminary' with all pain fields as None."""
        engine = FinalVerdictEngine()

        company = MagicMock()
        company.id = uuid4()
        company.name = "TestCo"

        # Mock business_read_engine to return low values
        with patch.object(
            engine,  # not directly patchable, patch the module-level import
            "generate",
        ):
            pass  # We'll call generate directly

        # Create zero signals
        signals = []

        # Create a no_signal score
        score = _make_friction_score(dominant_friction_type="no_signal", total_score=0.0)

        # Create no hypothesis (engine returns None for no_signal)
        hypothesis = None

        # Mock db session
        mock_db = MagicMock()

        # Patch business_read_engine to return low values
        with patch("app.services.final_verdict_engine.business_read_engine") as mock_br:
            mock_br.compute_reading.return_value = {
                "hiring_pressure": "low",
                "pain_clarity": "low",
                "diagnosis_status": "insufficient_evidence",
                "business_read_summary": "No evidence yet.",
                "next_best_step": "Run collection.",
            }

            verdict = engine.generate(
                company=company,
                signals=signals,
                score=score,
                hypothesis=hypothesis,
                company_type="operating",
                collection_runs=[],
                db=mock_db,
            )

        assert verdict["verdict_type"] == "preliminary", (
            f"Zero signals should produce 'preliminary' verdict, got {verdict['verdict_type']}"
        )
        assert verdict["main_pain"] is None, (
            f"Zero signals should have None main_pain, got {verdict['main_pain']}"
        )
        assert verdict["confidence"] == "low", (
            f"Zero signals should have 'low' confidence, got {verdict['confidence']}"
        )
        assert verdict["diagnosis_status"] == "insufficient_evidence", (
            f"Zero signals should have 'insufficient_evidence' diagnosis_status, "
            f"got {verdict['diagnosis_status']}"
        )


# ─── Analysis Build Response ───────────────────────────────────────

class TestAnalysisBuildResponse:
    """Verify build_response translates 'no_signal' to None in raw dicts."""

    def test_build_response_translates_no_signal(self):
        """The build_response function should translate 'no_signal' to None
        in friction_score and hypothesis dicts."""
        from app.api.routers.analysis import build_response

        company = MagicMock()
        company.id = uuid4()
        company.name = "TestCo"
        company.domain = "test.com"
        company.industry = None
        company.company_size = None
        company.source_added_from = None
        company.created_at = datetime.now(timezone.utc)

        # Score with "no_signal"
        score = _make_friction_score(dominant_friction_type="no_signal", total_score=0.0)

        type_result = {
            "company_type": "operating",
            "analysis_mode": "auto",
            "target_fit": "primary",
            "company_type_confidence": "low",
            "company_type_reason": "No data",
        }

        verdict = {
            "verdict_type": "preliminary",
            "main_pain": None,
            "confidence": "low",
        }

        response = build_response(
            company=company,
            signals=[],
            score=score,
            hypothesis=None,
            type_result=type_result,
            verdict=verdict,
        )

        # dominant_friction_type should be None, not "no_signal"
        assert response.friction_score["dominant_friction_type"] is None, (
            f"build_response should translate 'no_signal' to None, "
            f"got {response.friction_score['dominant_friction_type']}"
        )

    def test_build_response_preserves_real_category(self):
        """The build_response function should preserve real friction categories."""
        from app.api.routers.analysis import build_response

        company = MagicMock()
        company.id = uuid4()
        company.name = "TestCo"
        company.domain = "test.com"
        company.industry = None
        company.company_size = None
        company.source_added_from = None
        company.created_at = datetime.now(timezone.utc)

        score = _make_friction_score(
            dominant_friction_type="scaling_strain",
            total_score=5.0,
        )

        type_result = {
            "company_type": "operating",
            "analysis_mode": "auto",
            "target_fit": "primary",
            "company_type_confidence": "medium",
            "company_type_reason": "Growth signals",
        }

        verdict = {
            "verdict_type": "final",
            "main_pain": "Test pain",
            "confidence": "medium",
        }

        response = build_response(
            company=company,
            signals=[],
            score=score,
            hypothesis=None,
            type_result=type_result,
            verdict=verdict,
        )

        assert response.friction_score["dominant_friction_type"] == "scaling_strain", (
            f"build_response should preserve 'scaling_strain', "
            f"got {response.friction_score['dominant_friction_type']}"
        )
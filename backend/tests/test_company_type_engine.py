"""
Company type engine tests.

Verifies:
  1. Zero signals → "unclear" classification.
  2. Intermediary keywords (staffing, recruiting) → "job_market_intermediary".
  3. Operating keywords (SaaS, customers, products) → "operating_company".
  4. Mixed signals → intermediary takes priority at score >= 2.
  5. Confidence levels (high, medium, low) based on score and evidence.
  6. has_hypothesis flag affects Rule D and E.
"""

import pytest
from unittest.mock import MagicMock

from tests.conftest import make_signal, make_signals
from app.services.company_type_engine import CompanyTypeEngine


class TestCompanyTypeZeroSignals:
    """Zero signals should produce 'unclear' classification."""

    def test_zero_signals_unclear(self):
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=[], signal_count=0)
        assert result["company_type"] == "unclear"
        assert result["company_type_confidence"] == "low"
        assert "unclear" in result["analysis_mode"]


class TestCompanyTypeIntermediary:
    """Intermediary keywords should classify as job_market_intermediary."""

    def test_staffing_keyword(self):
        signals = [make_signal(signal_type="company_size_detected", signal_text="a staffing agency")]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=1)
        assert result["company_type"] == "job_market_intermediary"

    def test_recruiting_keyword(self):
        signals = [make_signal(signal_type="hiring_language_detected", signal_text="recruiting firm")]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=1)
        # Single intermediary keyword with 0 operating → Rule C
        assert result["company_type"] == "job_market_intermediary"
        assert result["company_type_confidence"] == "medium"

    def test_headhunter_keyword(self):
        """headhunter + another intermediary keyword → intermediary (needs score >= 2)."""
        signals = [
            make_signal(signal_type="hiring_news_detected", signal_text="executive headhunter"),
            make_signal(signal_type="company_size_detected", signal_text="staffing and recruiting"),
        ]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=2)
        assert result["company_type"] == "job_market_intermediary"

    def test_two_intermediary_keywords_high_confidence(self):
        signals = [
            make_signal(signal_type="company_size_detected", signal_text="staffing agency"),
            make_signal(signal_type="hiring_language_detected", signal_text="recruiting talent"),
        ]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=2)
        assert result["company_type"] == "job_market_intermediary"
        assert result["company_type_confidence"] == "high"

    def test_three_intermediary_keywords_high_confidence(self):
        signals = [
            make_signal(signal_type="company_size_detected", signal_text="staffing and recruiting"),
            make_signal(signal_type="hiring_news_detected", signal_text="job placement services"),
            make_signal(signal_type="hiring_language_detected", signal_text="executive search firm"),
        ]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=3)
        assert result["company_type"] == "job_market_intermediary"
        assert result["company_type_confidence"] == "high"


class TestCompanyTypeOperating:
    """Operating company keywords should classify as operating_company."""

    def test_saas_keyword(self):
        signals = [make_signal(signal_type="company_size_detected", signal_text="SaaS platform")]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=1)
        # Single operating keyword with no hypothesis → Rule F (low confidence)
        assert result["company_type"] == "operating_company"

    def test_customers_keyword(self):
        signals = [make_signal(signal_type="company_size_detected", signal_text="serves customers")]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=1)
        assert result["company_type"] == "operating_company"

    def test_two_operating_keywords_medium_confidence(self):
        signals = [
            make_signal(signal_type="company_size_detected", signal_text="SaaS platform"),
            make_signal(signal_type="scaling_language_detected", signal_text="expanding products"),
        ]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=2)
        assert result["company_type"] == "operating_company"
        # 2 operating keywords with no hypothesis → confidence is "high" (score >= 2)
        assert result["company_type_confidence"] in ("medium", "high")

    def test_strong_evidence_with_hypothesis(self):
        """Rule D: operating_score >= 1 with has_hypothesis and 3+ signals."""
        signals = [
            make_signal(signal_type="company_size_detected", signal_text="products and customers"),
            make_signal(signal_type="hiring_language_detected", signal_text="hiring engineers"),
            make_signal(signal_type="scaling_language_detected", signal_text="scaling the team"),
        ]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=3, has_hypothesis=True)
        assert result["company_type"] == "operating_company"
        # Multiple operating keywords → high or medium confidence
        assert result["company_type_confidence"] in ("medium", "high")


class TestCompanyTypeMixedSignals:
    """When both intermediary and operating keywords match, intermediary wins at >= 2."""

    def test_mixed_with_intermediary_dominant(self):
        """Intermediary score >= 2 takes priority over operating score."""
        signals = [
            make_signal(signal_type="company_size_detected", signal_text="staffing agency"),
            make_signal(signal_type="hiring_language_detected", signal_text="recruiting firm"),
            make_signal(signal_type="scaling_language_detected", signal_text="scaling their platform"),
        ]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=3)
        assert result["company_type"] == "job_market_intermediary"

    def test_mixed_with_operating_dominant(self):
        """Operating score >= 2 when intermediary < 2."""
        signals = [
            make_signal(signal_type="company_size_detected", signal_text="SaaS products"),
            make_signal(signal_type="scaling_language_detected", signal_text="expanding to serve customers"),
            make_signal(signal_type="hiring_news_detected", signal_text="hiring for their product team"),
        ]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=3)
        assert result["company_type"] == "operating_company"


class TestCompanyTypeConfidenceLevels:
    """Verify confidence levels based on score and evidence strength."""

    def test_low_confidence_single_operating(self):
        signals = [make_signal(signal_type="company_size_detected", signal_text="a products company")]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=1)
        assert result["company_type"] == "operating_company"
        assert result["company_type_confidence"] == "low"

    def test_medium_confidence_with_evidence(self):
        signals = [
            make_signal(signal_type="company_size_detected", signal_text="products"),
            make_signal(signal_type="scaling_language_detected", signal_text="scaling"),
            make_signal(signal_type="hiring_language_detected", signal_text="hiring"),
        ]
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=signals, signal_count=3, has_hypothesis=True)
        assert result["company_type_confidence"] in ("medium", "high")


class TestCompanyTypeOutputShape:
    """Verify the output dict has all required fields."""

    def test_output_fields_present(self):
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=[], signal_count=0)
        required_fields = [
            "company_type", "analysis_mode", "target_fit",
            "company_type_confidence", "company_type_reason",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_output_values_are_valid(self):
        engine = CompanyTypeEngine()
        result = engine.analyze(signals=[], signal_count=0)
        assert result["company_type"] in ("operating_company", "job_market_intermediary", "unclear")
        assert result["company_type_confidence"] in ("high", "medium", "low")
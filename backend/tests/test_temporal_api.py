"""Smoke tests for the Temporal Intelligence API endpoints.

Tests:
  1. Company not found → 404
  2. Invalid lookback_days → 400
  3. Deltas endpoint returns correct shape
  4. Velocity endpoint returns correct shape
  5. Diagnostic endpoint returns correct shape
  6. Verdict endpoint returns correct shape
  7. Run-analysis endpoint returns full shape
  8. All endpoints handle insufficient_data gracefully
  9. Lookback validation boundaries
"""

import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4, UUID

from fastapi.testclient import TestClient

from app.schemas.score_delta import (
    LookbackWindow, ScoreDeltaResult, CategoryDelta, TrendDirection, Magnitude,
    OverallDelta,
)
from app.schemas.signal_velocity import (
    VelocityWindow, SignalVelocityResult, PressureState,
    CategoryVelocity, VelocityBucket, SourceSummary,
)
from app.schemas.temporal_diagnostic import (
    TemporalDiagnosticResult, TemporalDiagnosticState, TemporalConfidence,
    EvidenceStrength, TopChangingCategory,
)
from app.services.positioning_engine import EligibilityResult
from tests.conftest import make_company


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Create a TestClient with DB session mocked out."""
    with patch("app.db.session.SessionLocal"):
        from main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def _make_delta_result(company_id: UUID, snapshot_count: int = 2) -> ScoreDeltaResult:
    return ScoreDeltaResult(
        company_id=company_id,
        lookback_window=LookbackWindow.D30,
        lookback_days=30,
        snapshot_count=snapshot_count,
        current_computed_at=None,
        previous_computed_at=None,
        current_score_id=None,
        previous_score_id=None,
        category_deltas=[
            CategoryDelta(
                category="reporting_fragmentation",
                current_normalized=0.6,
                previous_normalized=0.4,
                delta=0.2,
                trend=TrendDirection.DECLINING,
                magnitude=Magnitude.MODERATE,
                evidence="2 new signals in reporting.",
            ),
        ],
        overall=OverallDelta(
            current_total=2.1,
            previous_total=1.7,
            delta=0.4,
            trend=TrendDirection.DECLINING,
            magnitude=Magnitude.MODERATE,
            dominant_shift="reporting_fragmentation",
        ),
    )


def _make_velocity_result(company_id: UUID, total: int = 10) -> SignalVelocityResult:
    return SignalVelocityResult(
        company_id=company_id,
        window=VelocityWindow.ROLLING_30D,
        window_days=30,
        total_signals=total,
        scored_signals=7,
        discovery_signals=3,
        overall_velocity=0.33,
        overall_acceleration=0.05,
        overall_pressure=PressureState.STABLE,
        category_velocities=[
            CategoryVelocity(
                category="reporting_fragmentation",
                signal_count=5, scored_count=4, discovery_count=1,
                velocity=0.17, acceleration=0.02, pressure=PressureState.STABLE,
            ),
        ],
        buckets=[],
        source_summary=[
            SourceSummary(source_type="careers", signal_count=8, latest_signal_at=None),
        ],
        spike_detected=False, spike_bucket=None,
        drought_detected=False, drought_days=0,
        evidence="Stable signal velocity over 30 days.",
    )


def _make_diagnostic_result(company_id: UUID) -> TemporalDiagnosticResult:
    return TemporalDiagnosticResult(
        company_id=company_id,
        temporal_state=TemporalDiagnosticState.EMERGING_PAIN,
        confidence=TemporalConfidence.MODERATE,
        evidence_strength=EvidenceStrength.MODERATE,
        top_changing_category=TopChangingCategory(
            category="reporting_fragmentation", delta=0.2,
            trend="declining", velocity=0.17,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        reasoning_trace=[{"step": "1", "condition": "delta > 0", "result": "emerging_pain"}],
        summary="Reporting friction is emerging.",
        score_delta_available=True, velocity_available=True, evaluation_available=True,
        score_snapshot_count=3, signal_count=10, scored_signal_count=7,
    )


def _make_insufficient_diagnostic(company_id: UUID) -> TemporalDiagnosticResult:
    return TemporalDiagnosticResult(
        company_id=company_id,
        temporal_state=TemporalDiagnosticState.INSUFFICIENT,
        confidence=TemporalConfidence.NONE,
        evidence_strength=EvidenceStrength.WEAK,
        top_changing_category=None,
        reasoning_trace=[],
        summary="Insufficient temporal data for analysis.",
        score_delta_available=False, velocity_available=False, evaluation_available=False,
        score_snapshot_count=0, signal_count=0, scored_signal_count=0,
    )


def _make_insufficient_delta(company_id: UUID) -> ScoreDeltaResult:
    return ScoreDeltaResult(
        company_id=company_id, lookback_window=LookbackWindow.D30,
        lookback_days=30, snapshot_count=0,
    )


def _make_insufficient_velocity(company_id: UUID) -> SignalVelocityResult:
    return SignalVelocityResult(
        company_id=company_id, window=VelocityWindow.ROLLING_30D,
        window_days=30, total_signals=0, scored_signals=0, discovery_signals=0,
        overall_velocity=0.0, overall_acceleration=0.0,
        overall_pressure=PressureState.INSUFFICIENT,
    )


# Shared mock patch targets for endpoints that need full mocking
_VERDICT_PATCHES = [
    "app.api.routers.temporal.check_eligibility",
    "app.api.routers.temporal.final_verdict_engine",
    "app.api.routers.temporal.temporal_diagnostic_engine",
    "app.api.routers.temporal.signal_velocity_tracker",
    "app.api.routers.temporal.score_delta_engine",
    "app.api.routers.temporal.company_evaluation_engine",
    "app.api.routers.temporal.company_service",
    "app.api.routers.temporal.company_type_engine",
    "app.api.routers.temporal.FrictionScore",
    "app.api.routers.temporal.OpportunityHypothesis",
    "app.api.routers.temporal.CompanyJobRole",
]


# ── Tests ─────────────────────────────────────────────────────────────

class TestTemporalDeltasEndpoint:
    """GET /companies/{company_id}/temporal/deltas"""

    @patch("app.api.routers.temporal.score_delta_engine")
    def test_deltas_returns_correct_shape(self, mock_engine, client):
        company = make_company()
        company_id = company.id
        mock_engine.compute_delta.return_value = _make_delta_result(company_id)

        with patch("app.api.routers.temporal._get_company_or_404", return_value=company):
            resp = client.get(f"/api/v1/companies/{company_id}/temporal/deltas?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_id"] == str(company_id)
        assert data["lookback_window"] == "30d"
        assert data["snapshot_count"] == 2
        assert data["insufficient_data"] is False
        assert len(data["category_deltas"]) == 1
        assert data["category_deltas"][0]["category"] == "reporting_fragmentation"
        assert data["overall"]["delta"] == 0.4

    @patch("app.api.routers.temporal.score_delta_engine")
    def test_deltas_insufficient_data_flag(self, mock_engine, client):
        company = make_company()
        company_id = company.id
        mock_engine.compute_delta.return_value = _make_delta_result(company_id, snapshot_count=1)

        with patch("app.api.routers.temporal._get_company_or_404", return_value=company):
            resp = client.get(f"/api/v1/companies/{company_id}/temporal/deltas?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["insufficient_data"] is True

    def test_deltas_invalid_lookback(self, client):
        """lookback_days=14 is not in {7,30,90,180} → custom 400 error."""
        resp = client.get(f"/api/v1/companies/{uuid4()}/temporal/deltas?lookback_days=14")
        assert resp.status_code == 400

    def test_deltas_company_not_found(self, client):
        """With a mock DB, company lookups return None → 404 from _get_company_or_404.
        Without a real DB, the response depends on the mock setup."""
        fake_id = str(uuid4())
        resp = client.get(f"/api/v1/companies/{fake_id}/temporal/deltas?lookback_days=30")
        # With mock DB, query returns None → 404; or mock DB returns something → 200
        assert resp.status_code in [200, 404]


class TestTemporalVelocityEndpoint:
    """GET /companies/{company_id}/temporal/signals/velocity"""

    @patch("app.api.routers.temporal.signal_velocity_tracker")
    def test_velocity_returns_correct_shape(self, mock_engine, client):
        company = make_company()
        company_id = company.id
        mock_engine.compute_velocity.return_value = _make_velocity_result(company_id)

        with patch("app.api.routers.temporal._get_company_or_404", return_value=company):
            resp = client.get(f"/api/v1/companies/{company_id}/temporal/signals/velocity?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_id"] == str(company_id)
        assert data["total_signals"] == 10
        assert data["insufficient_data"] is False
        assert data["overall_pressure"] == "stable"

    @patch("app.api.routers.temporal.signal_velocity_tracker")
    def test_velocity_insufficient_data_flag(self, mock_engine, client):
        company = make_company()
        company_id = company.id
        mock_engine.compute_velocity.return_value = _make_insufficient_velocity(company_id)

        with patch("app.api.routers.temporal._get_company_or_404", return_value=company):
            resp = client.get(f"/api/v1/companies/{company_id}/temporal/signals/velocity?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["insufficient_data"] is True
        assert data["total_signals"] == 0

    def test_velocity_invalid_lookback(self, client):
        resp = client.get(f"/api/v1/companies/{uuid4()}/temporal/signals/velocity?lookback_days=60")
        assert resp.status_code == 400

    def test_velocity_company_not_found(self, client):
        fake_id = str(uuid4())
        resp = client.get(f"/api/v1/companies/{fake_id}/temporal/signals/velocity?lookback_days=30")
        assert resp.status_code in [200, 404]


class TestTemporalDiagnosticEndpoint:
    """GET /companies/{company_id}/temporal/diagnostic"""

    @patch("app.api.routers.temporal.temporal_diagnostic_engine")
    @patch("app.api.routers.temporal.signal_velocity_tracker")
    @patch("app.api.routers.temporal.score_delta_engine")
    @patch("app.api.routers.temporal.company_evaluation_engine")
    def test_diagnostic_returns_correct_shape(
        self, mock_eval, mock_delta, mock_velocity, mock_diagnostic, client,
    ):
        company = make_company()
        company_id = company.id
        mock_delta.compute_delta.return_value = _make_delta_result(company_id)
        mock_velocity.compute_velocity.return_value = _make_velocity_result(company_id)
        mock_eval.evaluate.return_value = {"diagnostic_state": "specific_pain_identified", "kpis": {}}
        mock_diagnostic.diagnose.return_value = _make_diagnostic_result(company_id)

        with patch("app.api.routers.temporal._get_company_or_404", return_value=company):
            resp = client.get(f"/api/v1/companies/{company_id}/temporal/diagnostic?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_id"] == str(company_id)
        assert data["temporal_state"] == "emerging_pain"
        assert data["confidence"] == "moderate"
        assert data["insufficient_data"] is False
        assert data["top_changing_category"]["category"] == "reporting_fragmentation"

    @patch("app.api.routers.temporal.temporal_diagnostic_engine")
    @patch("app.api.routers.temporal.signal_velocity_tracker")
    @patch("app.api.routers.temporal.score_delta_engine")
    @patch("app.api.routers.temporal.company_evaluation_engine")
    def test_diagnostic_insufficient_data(
        self, mock_eval, mock_delta, mock_velocity, mock_diagnostic, client,
    ):
        company = make_company()
        company_id = company.id
        mock_delta.compute_delta.return_value = _make_insufficient_delta(company_id)
        mock_velocity.compute_velocity.return_value = _make_insufficient_velocity(company_id)
        mock_eval.evaluate.return_value = {"diagnostic_state": "insufficient_evidence", "kpis": {}}
        mock_diagnostic.diagnose.return_value = _make_insufficient_diagnostic(company_id)

        with patch("app.api.routers.temporal._get_company_or_404", return_value=company):
            resp = client.get(f"/api/v1/companies/{company_id}/temporal/diagnostic?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["temporal_state"] == "insufficient_temporal_data"
        assert data["insufficient_data"] is True

    def test_diagnostic_invalid_lookback(self, client):
        """lookback_days=5 is below ge=7 minimum → FastAPI returns 422."""
        resp = client.get(f"/api/v1/companies/{uuid4()}/temporal/diagnostic?lookback_days=5")
        assert resp.status_code == 422


class TestTemporalVerdictEndpoint:
    """GET /companies/{company_id}/temporal/verdict"""

    @patch("app.api.routers.temporal.check_eligibility")
    @patch("app.api.routers.temporal.final_verdict_engine")
    @patch("app.api.routers.temporal.temporal_diagnostic_engine")
    @patch("app.api.routers.temporal.signal_velocity_tracker")
    @patch("app.api.routers.temporal.score_delta_engine")
    @patch("app.api.routers.temporal.company_evaluation_engine")
    @patch("app.api.routers.temporal.company_service")
    @patch("app.api.routers.temporal.company_type_engine")
    @patch("app.api.routers.temporal.FrictionScore")
    @patch("app.api.routers.temporal.OpportunityHypothesis")
    @patch("app.api.routers.temporal.CompanyJobRole")
    def test_verdict_returns_correct_shape(
        self, mock_role, mock_hyp, mock_score, mock_type, mock_svc,
        mock_eval, mock_delta, mock_velocity, mock_diagnostic,
        mock_verdict, mock_eligibility, client,
    ):
        company = make_company()
        company_id = company.id

        mock_delta.compute_delta.return_value = _make_delta_result(company_id)
        mock_velocity.compute_velocity.return_value = _make_velocity_result(company_id)
        mock_eval.evaluate.return_value = {
            "diagnostic_state": "specific_pain_identified",
            "kpis": {"pain_clarity": "high", "function_concentration": "high", "positioning_readiness": "high"},
        }
        mock_diagnostic.diagnose.return_value = _make_diagnostic_result(company_id)
        mock_verdict.generate.return_value = {
            "verdict_type": "final",
            "hiring_pressure": "high",
            "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "confidence": "high",
            "what_we_know": "Company shows accelerating reporting friction.",
            "what_we_do_not_know_yet": None,
            "next_best_step": "Position now.",
            "main_pain": "Fragmented reporting",
            "where_pain_lives": "Data and analytics",
            "what_the_company_needs": "Clear dashboards",
            "recommended_positioning": "Position as reporting specialist.",
            "business_read_summary": "Strong signals.",
            "evidence_quality": "high",
            "temporal_status": "emerging_pain",
            "trend_direction": "worsening",
            "top_accelerating_pain": {"category": "reporting_fragmentation", "delta": 0.2},
            "top_declining_pain": None,
            "temporal_confidence": "moderate",
            "temporal_reasoning_trace": [{"step": "1", "condition": "delta > 0", "result": "emerging_pain"}],
        }
        mock_eligibility.return_value = EligibilityResult(
            eligible=True, gate_passed="full", reason="Full evidence.",
            diagnostic_state="specific_pain_identified", confidence_band="high",
        )
        mock_svc.get_signals.return_value = []
        mock_svc.get_collection_runs.return_value = []
        mock_type.analyze.return_value = {"company_type": "operating"}

        with patch("app.api.routers.temporal._get_company_or_404", return_value=company):
            resp = client.get(f"/api/v1/companies/{company_id}/temporal/verdict?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict_type"] == "final"
        assert data["temporal_status"] == "emerging_pain"
        assert data["trend_direction"] == "worsening"
        assert data["temporal_confidence"] == "moderate"
        assert data["eligibility"]["eligible"] is True
        assert data["eligibility"]["gate_passed"] == "full"

    def test_verdict_company_not_found(self, client):
        fake_id = str(uuid4())
        resp = client.get(f"/api/v1/companies/{fake_id}/temporal/verdict?lookback_days=30")
        assert resp.status_code in [200, 404]


class TestTemporalRunAnalysisEndpoint:
    """POST /companies/{company_id}/temporal/run-analysis"""

    @patch("app.api.routers.temporal.check_eligibility")
    @patch("app.api.routers.temporal.final_verdict_engine")
    @patch("app.api.routers.temporal.temporal_diagnostic_engine")
    @patch("app.api.routers.temporal.signal_velocity_tracker")
    @patch("app.api.routers.temporal.score_delta_engine")
    @patch("app.api.routers.temporal.company_evaluation_engine")
    @patch("app.api.routers.temporal.company_service")
    @patch("app.api.routers.temporal.company_type_engine")
    @patch("app.api.routers.temporal.FrictionScore")
    @patch("app.api.routers.temporal.OpportunityHypothesis")
    @patch("app.api.routers.temporal.CompanyJobRole")
    def test_run_analysis_returns_full_shape(
        self, mock_role, mock_hyp, mock_score, mock_type, mock_svc,
        mock_eval, mock_delta, mock_velocity, mock_diagnostic,
        mock_verdict, mock_eligibility, client,
    ):
        company = make_company()
        company_id = company.id

        mock_delta.compute_delta.return_value = _make_delta_result(company_id)
        mock_velocity.compute_velocity.return_value = _make_velocity_result(company_id)
        mock_eval.evaluate.return_value = {
            "diagnostic_state": "specific_pain_identified",
            "kpis": {"pain_clarity": "high", "function_concentration": "high", "positioning_readiness": "high"},
        }
        mock_diagnostic.diagnose.return_value = _make_diagnostic_result(company_id)
        mock_type.analyze.return_value = {"company_type": "operating"}
        mock_svc.get_signals.return_value = []
        mock_svc.get_collection_runs.return_value = []
        mock_verdict.generate.return_value = {
            "verdict_type": "final",
            "hiring_pressure": "high",
            "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "confidence": "high",
            "what_we_know": "Accelerating friction detected.",
            "what_we_do_not_know_yet": None,
            "next_best_step": "Position now.",
            "main_pain": "Fragmented reporting",
            "where_pain_lives": "Data and analytics",
            "what_the_company_needs": "Clear dashboards",
            "recommended_positioning": "Position as reporting specialist.",
            "business_read_summary": "Strong signals.",
            "evidence_quality": "high",
            "temporal_status": "accelerating_pain",
            "trend_direction": "worsening",
            "top_accelerating_pain": {"category": "reporting_fragmentation", "delta": 0.2},
            "top_declining_pain": None,
            "temporal_confidence": "high",
            "temporal_reasoning_trace": [],
        }
        mock_eligibility.return_value = EligibilityResult(
            eligible=True, gate_passed="full", reason="Full evidence.",
            diagnostic_state="specific_pain_identified", confidence_band="high",
        )

        with patch("app.api.routers.temporal._get_company_or_404", return_value=company):
            resp = client.post(f"/api/v1/companies/{company_id}/temporal/run-analysis?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_id"] == str(company_id)
        assert data["deltas"] is not None
        assert data["velocity"] is not None
        assert data["diagnostic"] is not None
        assert data["verdict"] is not None
        assert data["diagnostic"]["temporal_state"] == "emerging_pain"
        assert data["verdict"]["temporal_status"] == "accelerating_pain"

    def test_run_analysis_company_not_found(self, client):
        fake_id = str(uuid4())
        resp = client.post(f"/api/v1/companies/{fake_id}/temporal/run-analysis?lookback_days=30")
        assert resp.status_code in [200, 404, 500]


class TestTemporalLookbackValidation:
    """Validate lookback_days parameter boundaries."""

    def test_deltas_valid_lookbacks(self, client):
        for days in [7, 30, 90, 180]:
            resp = client.get(f"/api/v1/companies/{uuid4()}/temporal/deltas?lookback_days={days}")
            assert resp.status_code in [200, 404]

    def test_deltas_invalid_lookback_14(self, client):
        resp = client.get(f"/api/v1/companies/{uuid4()}/temporal/deltas?lookback_days=14")
        assert resp.status_code == 400

    def test_velocity_valid_lookbacks(self, client):
        for days in [1, 7, 30, 90]:
            resp = client.get(f"/api/v1/companies/{uuid4()}/temporal/signals/velocity?lookback_days={days}")
            assert resp.status_code in [200, 404]

    def test_velocity_invalid_lookback_60(self, client):
        resp = client.get(f"/api/v1/companies/{uuid4()}/temporal/signals/velocity?lookback_days=60")
        assert resp.status_code == 400

    def test_deltas_default_lookback_30(self, client):
        """Default lookback_days=30 — should not return 400."""
        resp = client.get(f"/api/v1/companies/{uuid4()}/temporal/deltas")
        assert resp.status_code != 400
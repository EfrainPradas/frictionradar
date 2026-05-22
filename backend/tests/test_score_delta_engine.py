"""Tests for the Score History Delta Engine.

Covers:
  - Per-category delta computation (normalized scores only)
  - Trend direction classification (improving, stable, declining, volatile, insufficient)
  - Magnitude classification (negligible, mild, moderate, strong)
  - Evidence summary generation
  - Edge cases: 0 snapshots, 1 snapshot, 2+ snapshots
  - All four lookback windows
  - Integration-style tests with multiple FrictionScore snapshots
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.friction_categories import FRICTION_CATEGORIES
from app.schemas.score_delta import (
    CategoryDelta,
    LookbackWindow,
    Magnitude,
    OverallDelta,
    ScoreDeltaResult,
    TrendDirection,
)
from app.services.score_delta_engine import (
    MAGNITUDE_THRESHOLDS,
    OVERALL_MAGNITUDE_THRESHOLDS,
    MIN_SNAPSHOTS,
    STABLE_THRESHOLD,
    ScoreDeltaEngine,
    _classify_magnitude,
    _classify_trend,
    _extract_normalized,
    _extract_matched_signals,
    _build_evidence,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def _make_breakdown(categories: dict[str, float]) -> dict:
    """Build a v2.0.0 scoring breakdown with given normalized scores.

    categories: {category_name: normalized_score}
    """
    cats = {}
    for cat in FRICTION_CATEGORIES:
        score = categories.get(cat, 0.0)
        cats[cat] = {
            "raw_score": score * 10.0,
            "max_possible": 10.0,
            "normalized_score": score,
            "matched_signals": [f"test_{cat}"] if score > 0 else [],
        }
    return {
        "categories": cats,
        "confidence": {
            "signal_diversity": 3,
            "contributing_signal_count": 5,
            "evidence_breadth": 2,
            "confidence_level": "medium",
        },
        "scoring_version": "2.0.0",
    }


def _make_score(
    company_id: uuid4,
    breakdown: dict,
    computed_at: datetime,
) -> MagicMock:
    """Create a mock FrictionScore with a specific computed_at."""
    s = MagicMock()
    s.id = uuid4()
    s.company_id = company_id
    s.scoring_breakdown_json = breakdown
    s.computed_at = computed_at
    s.dominant_friction_type = "scaling_strain"
    s.total_score = sum(
        breakdown["categories"][c]["raw_score"] for c in FRICTION_CATEGORIES
    )
    return s


NOW = datetime.now(timezone.utc)
COMPANY_ID = uuid4()


# ── Unit tests: magnitude ─────────────────────────────────────────────

class TestClassifyMagnitude:
    def test_negligible(self):
        assert _classify_magnitude(0.005) == Magnitude.NEGLIGIBLE

    def test_negligible_at_boundary(self):
        assert _classify_magnitude(0.019) == Magnitude.NEGLIGIBLE

    def test_mild(self):
        assert _classify_magnitude(0.03) == Magnitude.MILD

    def test_mild_at_boundary(self):
        assert _classify_magnitude(0.049) == Magnitude.MILD

    def test_moderate(self):
        assert _classify_magnitude(0.10) == Magnitude.MODERATE

    def test_moderate_at_boundary(self):
        assert _classify_magnitude(0.149) == Magnitude.MODERATE

    def test_strong(self):
        assert _classify_magnitude(0.20) == Magnitude.STRONG

    def test_strong_large_delta(self):
        assert _classify_magnitude(0.80) == Magnitude.STRONG

    def test_zero_delta_is_negligible(self):
        assert _classify_magnitude(0.0) == Magnitude.NEGLIGIBLE


# ── Unit tests: trend ─────────────────────────────────────────────────

class TestClassifyTrend:
    def test_improving(self):
        # Decreasing friction = improving
        assert _classify_trend([], 0.1, 0.3) == TrendDirection.IMPROVING

    def test_declining(self):
        # Increasing friction = declining
        assert _classify_trend([], 0.5, 0.3) == TrendDirection.DECLINING

    def test_stable(self):
        # Change within threshold
        assert _classify_trend([], 0.3, 0.31) == TrendDirection.STABLE

    def test_stable_zero_change(self):
        assert _classify_trend([], 0.3, 0.3) == TrendDirection.STABLE

    def test_volatile_with_flips(self):
        # 2+ direction flips → volatile
        deltas = [0.1, -0.05, 0.08]  # up, down, up → 2 flips
        assert _classify_trend(deltas, 0.4, 0.3) == TrendDirection.VOLATILE

    def test_not_volatile_single_flip(self):
        # Only 1 flip → not volatile
        deltas = [0.1, -0.05]
        result = _classify_trend(deltas, 0.4, 0.3)
        assert result != TrendDirection.VOLATILE


# ── Unit tests: extract helpers ───────────────────────────────────────

class TestExtractNormalized:
    def test_extracts_all_categories(self):
        breakdown = _make_breakdown({
            "reporting_fragmentation": 0.3,
            "process_inefficiency": 0.1,
        })
        norms = _extract_normalized(breakdown)
        assert norms["reporting_fragmentation"] == 0.3
        assert norms["process_inefficiency"] == 0.1
        assert norms["tooling_inconsistency"] == 0.0

    def test_empty_breakdown(self):
        norms = _extract_normalized({})
        assert all(v == 0.0 for v in norms.values())


class TestExtractMatchedSignals:
    def test_extracts_signals(self):
        breakdown = _make_breakdown({"scaling_strain": 0.5})
        signals = _extract_matched_signals(breakdown, "scaling_strain")
        assert "test_scaling_strain" in signals

    def test_missing_category_returns_empty(self):
        breakdown = _make_breakdown({})
        signals = _extract_matched_signals(breakdown, "scaling_strain")
        assert signals == []


class TestBuildEvidence:
    def test_increase_with_new_signals(self):
        evidence = _build_evidence(
            "scaling_strain",
            ["high_open_positions", "growth_language"],
            ["growth_language"],
            0.15,
        )
        assert "increased" in evidence
        assert "new signals: high_open_positions" in evidence

    def test_decrease_with_lost_signals(self):
        evidence = _build_evidence(
            "process_inefficiency",
            [],
            ["revops_language_detected"],
            -0.10,
        )
        assert "decreased" in evidence
        assert "lost signals: revops_language_detected" in evidence

    def test_stable_no_change(self):
        evidence = _build_evidence("tooling_inconsistency", [], [], 0.005)
        assert "unchanged" in evidence


# ── Integration tests: full engine ────────────────────────────────────

class TestScoreDeltaEngine:
    """Tests using mock DB sessions with multiple score snapshots."""

    def _mock_db_with_scores(self, scores):
        """Create a mock DB that returns the given scores."""
        db = MagicMock()
        # Mock the SQLAlchemy select chain
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = scores
        mock_result.scalars.return_value = mock_scalars
        db.execute.return_value = mock_result
        return db

    def test_zero_snapshots_returns_insufficient(self):
        db = self._mock_db_with_scores([])
        engine = ScoreDeltaEngine()
        result = engine.compute_delta(db, COMPANY_ID, LookbackWindow.D30)
        assert result.snapshot_count == 0
        assert result.overall is None
        assert result.category_deltas == []

    def test_one_snapshot_returns_insufficient(self):
        score = _make_score(COMPANY_ID, _make_breakdown({}), NOW)
        db = self._mock_db_with_scores([score])
        engine = ScoreDeltaEngine()
        result = engine.compute_delta(db, COMPANY_ID, LookbackWindow.D30)
        assert result.snapshot_count == 1
        assert result.overall is None

    def test_two_snapshots_computes_deltas(self):
        prev = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.3,
            "reporting_fragmentation": 0.1,
        }), NOW - timedelta(days=7))
        curr = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.5,
            "reporting_fragmentation": 0.1,
        }), NOW)

        db = self._mock_db_with_scores([prev, curr])
        engine = ScoreDeltaEngine()
        result = engine.compute_delta(db, COMPANY_ID, LookbackWindow.D30)

        assert result.snapshot_count == 2
        assert result.current_computed_at == curr.computed_at
        assert result.previous_computed_at == prev.computed_at
        assert len(result.category_deltas) == 5

        # Scaling strain increased from 0.3 → 0.5
        ss_delta = next(d for d in result.category_deltas if d.category == "scaling_strain")
        assert ss_delta.delta == pytest.approx(0.2, abs=0.01)
        assert ss_delta.trend == TrendDirection.DECLINING
        assert ss_delta.magnitude == Magnitude.STRONG

        # Reporting unchanged
        rf_delta = next(d for d in result.category_deltas if d.category == "reporting_fragmentation")
        assert rf_delta.delta == pytest.approx(0.0, abs=0.01)
        assert rf_delta.trend == TrendDirection.STABLE

    def test_improving_trend(self):
        """Friction decreasing → improving direction."""
        prev = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.5,
        }), NOW - timedelta(days=7))
        curr = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.2,
        }), NOW)

        db = self._mock_db_with_scores([prev, curr])
        engine = ScoreDeltaEngine()
        result = engine.compute_delta(db, COMPANY_ID, LookbackWindow.D30)

        ss_delta = next(d for d in result.category_deltas if d.category == "scaling_strain")
        assert ss_delta.delta < 0
        assert ss_delta.trend == TrendDirection.IMPROVING

    def test_overall_delta(self):
        """Overall delta is sum of per-category deltas."""
        prev = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.3,
            "process_inefficiency": 0.2,
        }), NOW - timedelta(days=7))
        curr = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.5,
            "process_inefficiency": 0.1,
        }), NOW)

        db = self._mock_db_with_scores([prev, curr])
        engine = ScoreDeltaEngine()
        result = engine.compute_delta(db, COMPANY_ID, LookbackWindow.D30)

        assert result.overall is not None
        # prev_total = 0.5, curr_total = 0.6 → delta = 0.1
        assert result.overall.current_total == pytest.approx(0.6, abs=0.01)
        assert result.overall.previous_total == pytest.approx(0.5, abs=0.01)
        assert result.overall.delta == pytest.approx(0.1, abs=0.01)
        assert result.overall.dominant_shift is not None

    def test_volatile_trend_with_multiple_snapshots(self):
        """3+ snapshots with direction flips → volatile."""
        s1 = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.1,
        }), NOW - timedelta(days=30))
        s2 = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.5,
        }), NOW - timedelta(days=15))
        s3 = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.2,
        }), NOW - timedelta(days=7))
        s4 = _make_score(COMPANY_ID, _make_breakdown({
            "scaling_strain": 0.6,
        }), NOW)

        db = self._mock_db_with_scores([s1, s2, s3, s4])
        engine = ScoreDeltaEngine()
        result = engine.compute_delta(db, COMPANY_ID, LookbackWindow.D30)

        ss_delta = next(d for d in result.category_deltas if d.category == "scaling_strain")
        # Deltas: +0.4, -0.3, +0.4 → 2 flips → volatile
        assert ss_delta.trend == TrendDirection.VOLATILE

    def test_all_lookback_windows(self):
        """All four lookback windows produce valid results."""
        scores = [
            _make_score(COMPANY_ID, _make_breakdown({"scaling_strain": 0.1}), NOW - timedelta(days=60)),
            _make_score(COMPANY_ID, _make_breakdown({"scaling_strain": 0.3}), NOW),
        ]
        db = self._mock_db_with_scores(scores)
        engine = ScoreDeltaEngine()

        for window in LookbackWindow:
            result = engine.compute_delta(db, COMPANY_ID, window)
            assert result.snapshot_count == 2
            assert result.lookback_window == window

    def test_compute_all_windows(self):
        """compute_all_windows returns results for every window."""
        scores = [
            _make_score(COMPANY_ID, _make_breakdown({"scaling_strain": 0.2}), NOW - timedelta(days=5)),
            _make_score(COMPANY_ID, _make_breakdown({"scaling_strain": 0.3}), NOW),
        ]
        db = self._mock_db_with_scores(scores)
        engine = ScoreDeltaEngine()

        results = engine.compute_all_windows(db, COMPANY_ID)
        assert len(results) == 4
        for window in LookbackWindow:
            assert window in results

    def test_evidence_summary_includes_gained_and_lost(self):
        """Evidence summary lists gained and lost signals."""
        prev_breakdown = _make_breakdown({"scaling_strain": 0.2})
        prev_breakdown["categories"]["scaling_strain"]["matched_signals"] = ["growth_language"]

        curr_breakdown = _make_breakdown({"scaling_strain": 0.4})
        curr_breakdown["categories"]["scaling_strain"]["matched_signals"] = [
            "growth_language", "high_open_positions"
        ]

        prev = _make_score(COMPANY_ID, prev_breakdown, NOW - timedelta(days=7))
        curr = _make_score(COMPANY_ID, curr_breakdown, NOW)

        db = self._mock_db_with_scores([prev, curr])
        engine = ScoreDeltaEngine()
        result = engine.compute_delta(db, COMPANY_ID, LookbackWindow.D7)

        ss_delta = next(d for d in result.category_deltas if d.category == "scaling_strain")
        assert "increased" in ss_delta.evidence
        assert "new signals" in ss_delta.evidence
        assert "high_open_positions" in ss_delta.evidence

    def test_category_deltas_use_normalized_not_raw(self):
        """Verify deltas are based on normalized_score, not raw_score."""
        prev = _make_score(COMPANY_ID, _make_breakdown({
            "tooling_inconsistency": 0.5,
        }), NOW - timedelta(days=7))
        curr = _make_score(COMPANY_ID, _make_breakdown({
            "tooling_inconsistency": 0.7,
        }), NOW)

        db = self._mock_db_with_scores([prev, curr])
        engine = ScoreDeltaEngine()
        result = engine.compute_delta(db, COMPANY_ID, LookbackWindow.D30)

        ti_delta = next(d for d in result.category_deltas if d.category == "tooling_inconsistency")
        # Delta should be 0.2 (normalized), not 2.0 (raw)
        assert ti_delta.delta == pytest.approx(0.2, abs=0.01)
        assert ti_delta.current_normalized == pytest.approx(0.7, abs=0.01)
        assert ti_delta.previous_normalized == pytest.approx(0.5, abs=0.01)


class TestScoreDeltaResultSchema:
    """Verify the Pydantic schema works correctly."""

    def test_result_serialization(self):
        result = ScoreDeltaResult(
            company_id=COMPANY_ID,
            lookback_window=LookbackWindow.D30,
            lookback_days=30,
            snapshot_count=2,
        )
        d = result.model_dump()
        assert d["lookback_window"] == "30d"
        assert d["snapshot_count"] == 2

    def test_category_delta_serialization(self):
        delta = CategoryDelta(
            category="scaling_strain",
            current_normalized=0.5,
            previous_normalized=0.3,
            delta=0.2,
            trend=TrendDirection.DECLINING,
            magnitude=Magnitude.STRONG,
            evidence="Scaling Strain increased; new signals: high_open_positions",
        )
        d = delta.model_dump()
        assert d["trend"] == "declining"
        assert d["magnitude"] == "strong"
        assert d["delta"] == 0.2

    def test_overall_delta_serialization(self):
        overall = OverallDelta(
            current_total=1.5,
            previous_total=1.2,
            delta=0.3,
            trend=TrendDirection.DECLINING,
            magnitude=Magnitude.MODERATE,
            dominant_shift="scaling_strain",
        )
        d = overall.model_dump()
        assert d["dominant_shift"] == "scaling_strain"
        assert d["delta"] == 0.3

    def test_json_round_trip(self):
        result = ScoreDeltaResult(
            company_id=COMPANY_ID,
            lookback_window=LookbackWindow.D90,
            lookback_days=90,
            snapshot_count=3,
            category_deltas=[
                CategoryDelta(
                    category="process_inefficiency",
                    current_normalized=0.4,
                    previous_normalized=0.2,
                    delta=0.2,
                    trend=TrendDirection.DECLINING,
                    magnitude=Magnitude.STRONG,
                    evidence="Process Inefficiency increased",
                ),
            ],
            overall=OverallDelta(
                current_total=0.4,
                previous_total=0.2,
                delta=0.2,
                trend=TrendDirection.DECLINING,
                magnitude=Magnitude.MODERATE,
                dominant_shift="process_inefficiency",
            ),
        )
        json_str = result.model_dump_json()
        restored = ScoreDeltaResult.model_validate_json(json_str)
        assert restored.snapshot_count == 3
        assert len(restored.category_deltas) == 1
        assert restored.overall.delta == 0.2
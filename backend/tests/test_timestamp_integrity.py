"""Timestamp integrity and design ghost-rule fix tests.

Covers:
  - Primary temporal keys (captured_at, computed_at) have nullable=False + server_default + index
  - All created_at columns on core models have nullable=False + server_default
  - Intentionally nullable timestamps remain nullable
  - Design keywords are present in FunctionInferenceEngine.FUNCTION_KEYWORDS
  - Design roles classify correctly
  - Design concentration scoring rules fire when design signals are present
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models.company_signal import CompanySignal
from app.models.company import Company
from app.models.collection_run import CollectionRun
from app.models.company_job_role import CompanyJobRole, CompanyRoleSignal, HiringPattern
from app.models.page_capture import PageCapture
from app.models.extraction import CompanyAtsDetection, CompanyExtractionCache, CompanyExtractionAttempt
from app.models.review_queue import ReviewQueue
from app.models.commercial_pipeline import PipelineEntry, PipelineEvent
from app.models.friction_score import FrictionScore
from app.models.opportunity_hypothesis import OpportunityHypothesis
from app.services.function_inference_engine import function_inference_engine as fie
from app.core.scoring_rules import SCORING_RULES


# ── Helpers ──────────────────────────────────────────────────────────────

def _col(model, column_name: str):
    """Get a SQLAlchemy Column object by name."""
    return getattr(model, column_name)


def _has_index(model, column_name: str) -> bool:
    """Check if a column has an index (single-column index on the column itself)."""
    col = _col(model, column_name)
    return bool(col.index)


# ── TestModelTimestamps ──────────────────────────────────────────────────

class TestModelTimestamps:
    """Verify timestamp columns have correct nullable/server_default settings."""

    # -- Primary temporal keys --

    def test_captured_at_not_nullable(self):
        assert CompanySignal.captured_at.nullable is False

    def test_captured_at_has_server_default(self):
        assert CompanySignal.captured_at.server_default is not None

    def test_captured_at_is_indexed(self):
        assert _has_index(CompanySignal, "captured_at")

    def test_computed_at_not_nullable(self):
        assert FrictionScore.computed_at.nullable is False

    def test_computed_at_has_server_default(self):
        assert FrictionScore.computed_at.server_default is not None

    def test_computed_at_is_indexed(self):
        assert _has_index(FrictionScore, "computed_at")

    # -- Core model created_at columns --

    @pytest.mark.parametrize("model,col_name", [
        (CompanySignal, "created_at"),
        (Company, "created_at"),
        (CollectionRun, "created_at"),
        (CompanyJobRole, "created_at"),
        (CompanyJobRole, "discovered_at"),
        (CompanyRoleSignal, "created_at"),
        (HiringPattern, "created_at"),
        (HiringPattern, "generated_at"),
        (PageCapture, "captured_at"),
        (CompanyAtsDetection, "detected_at"),
        (CompanyExtractionCache, "cached_at"),
        (CompanyExtractionAttempt, "attempted_at"),
        (ReviewQueue, "created_at"),
        (PipelineEntry, "created_at"),
        (PipelineEvent, "created_at"),
        (OpportunityHypothesis, "created_at"),
    ])
    def test_core_timestamp_not_nullable(self, model, col_name):
        assert _col(model, col_name).nullable is False

    @pytest.mark.parametrize("model,col_name", [
        (CompanySignal, "created_at"),
        (Company, "created_at"),
        (CollectionRun, "created_at"),
        (CollectionRun, "started_at"),
        (CompanyJobRole, "created_at"),
        (CompanyJobRole, "discovered_at"),
        (CompanyRoleSignal, "created_at"),
        (HiringPattern, "created_at"),
        (HiringPattern, "generated_at"),
        (PageCapture, "captured_at"),
        (CompanyAtsDetection, "detected_at"),
        (CompanyExtractionCache, "cached_at"),
        (CompanyExtractionAttempt, "attempted_at"),
        (ReviewQueue, "created_at"),
        (PipelineEntry, "created_at"),
        (PipelineEvent, "created_at"),
    ])
    def test_core_timestamp_has_server_default(self, model, col_name):
        assert _col(model, col_name).server_default is not None

    # -- Intentionally nullable timestamps (must stay nullable) --

    @pytest.mark.parametrize("model,col_name", [
        (CollectionRun, "finished_at"),
        (Company, "last_collection_at"),
        (CompanyExtractionCache, "expires_at"),
        (PipelineEntry, "reviewed_at"),
        (ReviewQueue, "reviewed_at"),
    ])
    def test_intentionally_nullable_timestamps(self, model, col_name):
        assert _col(model, col_name).nullable is True

    # -- Company.updated_at has server_default --

    def test_company_updated_at_has_server_default(self):
        assert Company.updated_at.server_default is not None

    def test_pipeline_entry_updated_at_has_server_default(self):
        assert PipelineEntry.updated_at.server_default is not None


# ── TestDesignKeywords ──────────────────────────────────────────────────

class TestDesignKeywords:
    """Verify design functional area is wired into FunctionInferenceEngine."""

    def test_design_in_function_keywords(self):
        assert "design" in fie.FUNCTION_KEYWORDS, "design key missing from FUNCTION_KEYWORDS"

    def test_design_classifies_ux_designer(self):
        r = fie.infer_functional_area("Senior UX Designer")
        assert r["area"] == "design", f"Expected 'design', got '{r['area']}'"

    def test_design_classifies_ux_researcher(self):
        r = fie.infer_functional_area("UX Researcher")
        assert r["area"] == "design"

    def test_design_classifies_graphic_designer(self):
        r = fie.infer_functional_area("Graphic Designer")
        assert r["area"] == "design"

    def test_design_classifies_interaction_designer(self):
        r = fie.infer_functional_area("Interaction Designer")
        assert r["area"] == "design"

    def test_design_signal_mapped_in_fie_signal_map(self):
        """Verify signal_contract_audit maps design -> design_hiring."""
        from app.core.signal_contract_audit import FIE_SIGNAL_MAP
        assert FIE_SIGNAL_MAP.get("design") == "design_hiring", (
            f"Expected FIE_SIGNAL_MAP['design'] == 'design_hiring', "
            f"got {FIE_SIGNAL_MAP.get('design')}"
        )

    def test_design_concentration_rules_fire(self):
        """Design concentration scoring rules should match when design signals are present."""
        tooling_rules = SCORING_RULES.get("tooling_inconsistency", [])
        design_rules = [r for r in tooling_rules if "design_concentration" in r.get("label", "")]
        assert len(design_rules) > 0, "No design_concentration rules found in tooling_inconsistency"

        # Verify the rules reference design_concentration signal types
        for rule in design_rules:
            assert any(
                "design_concentration" in st for st in rule["signal_types"]
            ), f"Rule '{rule['label']}' missing design_concentration signal_type"

    def test_design_hiring_rule_exists(self):
        """Design hiring signal should have a matching scoring rule."""
        tooling_rules = SCORING_RULES.get("tooling_inconsistency", [])
        design_hiring_rules = [
            r for r in tooling_rules
            if "design_hiring_detected" in r.get("signal_types", [])
        ]
        assert len(design_hiring_rules) > 0, "No rule matches design_hiring_detected"
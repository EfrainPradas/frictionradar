"""
Signal Contract Audit — pytest tests.

These tests verify that the signal pipeline is intact:
  1. Every emitted signal_type has at least one scoring rule (or is intentionally unscored).
  2. Every scoring rule signal_type has at least one real emitter.
  3. Each friction category has at least one active signal path.
  4. No category has a weight imbalance beyond threshold.
  5. Intentionally unscored signals are documented.

Run:  pytest tests/test_signal_contract_audit.py -v
"""

import pytest

from app.core.signal_contract_audit import (
    ALL_EMITTERS,
    CANONICAL_AREAS,
    CAREERS_CATEGORIES,
    CONCENTRATION_SIGNALS,
    ATS_BOARD_SIGNALS,
    ATS_EMBED_SIGNALS,
    FIE_SIGNAL_MAP,
    run_audit,
    AuditResult,
    OrphanSignal,
    GhostRule,
)
from app.core.friction_categories import FRICTION_CATEGORIES
from app.core.scoring_rules import SCORING_RULES, INTENTIONALLY_UNSCORED_SIGNALS


class TestSignalContract:
    """Contract tests that should never break if the pipeline is healthy."""

    @pytest.fixture(autouse=True)
    def _run_audit(self):
        """Run the audit once for all tests in this class."""
        self.result = run_audit()

    # ---------------------------------------------------------------
    # 1. No ghost rules: every scoring rule signal_type must have an emitter
    # ---------------------------------------------------------------
    def test_no_ghost_rules(self):
        """After the 2026-05-18 contract fix, there should be ZERO ghost rules.

        Ghost rules are signal_types in scoring_rules that no collector produces.
        They were fixed by:
          - Removing phantom signal_types from rules
          - Mapping orphan signals to existing rules
          - Adding new rules for previously unscored signals
        """
        ghosts = self.result.ghosts
        if ghosts:
            details = "\n".join(
                f"  - {g.signal_type} (category: {g.category}, rule: {g.rule_label})"
                for g in ghosts
            )
            pytest.fail(
                f"Found {len(ghosts)} ghost rule(s) — signal_types in scoring_rules "
                f"with no emitter:\n{details}"
            )

    # ---------------------------------------------------------------
    # 2. Orphan signal count should not exceed baseline
    # ---------------------------------------------------------------
    def test_orphan_count_does_not_exceed_baseline(self):
        """Orphan signals (emitted but not scored) should not grow beyond baseline.

        After the 2026-05-18 contract fix, only 4 intentionally unscored
        discovery signals remain as orphans. All others have scoring rules.

        These 4 are: careers_page_found, company_size_detected,
        visible_hiring_area_detected, job_links_extracted.
        """
        MAX_ORPHANS = 10  # generous ceiling; current count is ~4
        orphans = self.result.orphans
        if len(orphans) > MAX_ORPHANS:
            new_orphans = [o.signal_type for o in orphans]
            pytest.fail(
                f"Orphan signal count ({len(orphans)}) exceeds ceiling ({MAX_ORPHANS}). "
                f"New signals added without scoring rules:\n"
                + "\n".join(f"  - {s}" for s in new_orphans)
            )

    # ---------------------------------------------------------------
    # 3. Every friction category has at least one active signal path
    # ---------------------------------------------------------------
    def test_every_category_has_active_path(self):
        """Each friction category must have at least one scoring rule with a
        signal_type that is actually emitted by some collector or service."""
        for cov in self.result.category_coverage:
            if not cov.has_active_emitter:
                pytest.fail(
                    f"Category '{cov.category}' has no active signal path — "
                    f"its scoring rules reference signal_types that no emitter produces."
                )

    # ---------------------------------------------------------------
    # 4. No category weight imbalance beyond 2.5x
    # ---------------------------------------------------------------
    def test_weight_imbalance_within_threshold(self):
        """The max achievable score ratio between categories should not exceed 2.5x.

        After the contract fix, many new signals were added to underweight
        categories. The threshold is generous (2.5x) to allow for the
        current state; tightening it is a separate decision.
        """
        weights = self.result.weight_imbalance
        min_w = min(weights.values())
        max_w = max(weights.values())
        ratio = max_w / min_w if min_w > 0 else float("inf")
        if ratio > 2.5:
            details = "\n".join(
                f"  {cat}: {w:.2f}"
                for cat, w in sorted(weights.items(), key=lambda x: -x[1])
            )
            pytest.fail(
                f"Weight imbalance ratio is {ratio:.1f}x (max={max_w:.2f}, "
                f"min={min_w:.2f}). This exceeds the 2.5x threshold.\n"
                f"Category weights:\n{details}"
            )

    # ---------------------------------------------------------------
    # 5. FRICTION_CATEGORIES matches SCORING_RULES keys
    # ---------------------------------------------------------------
    def test_categories_match_scoring_rules(self):
        """Every category in FRICTION_CATEGORIES must have scoring rules,
        and every key in SCORING_RULES must be in FRICTION_CATEGORIES."""
        categories_set = set(FRICTION_CATEGORIES)
        rules_keys = set(SCORING_RULES.keys())

        missing_in_rules = categories_set - rules_keys
        missing_in_categories = rules_keys - categories_set

        errors = []
        if missing_in_rules:
            errors.append(f"Categories without scoring rules: {missing_in_rules}")
        if missing_in_categories:
            errors.append(f"Scoring rules without category definition: {missing_in_categories}")
        if errors:
            pytest.fail("; ".join(errors))

    # ---------------------------------------------------------------
    # 6. All emitters have valid source metadata
    # ---------------------------------------------------------------
    def test_emitter_registry_integrity(self):
        """Every entry in ALL_EMITTERS should have non-empty source_file and source_note."""
        invalid = [
            (st, src) for st, (src, note) in ALL_EMITTERS.items()
            if not src or not note
        ]
        if invalid:
            pytest.fail(
                f"Emitter entries with missing metadata: {invalid}"
            )

    # ---------------------------------------------------------------
    # 7. No duplicate signal_types in emitter registry
    # ---------------------------------------------------------------
    def test_no_duplicate_emitter_entries(self):
        """Each signal_type should appear exactly once in ALL_EMITTERS."""
        assert len(ALL_EMITTERS) == len(set(ALL_EMITTERS.keys()))

    # ---------------------------------------------------------------
    # 8. Concentration signals cover all canonical areas
    # ---------------------------------------------------------------
    def test_concentration_signals_complete(self):
        """Every canonical area should produce both _high and _moderate signals."""
        for area in CANONICAL_AREAS:
            high = f"{area}_concentration_high"
            moderate = f"{area}_concentration_moderate"
            assert high in CONCENTRATION_SIGNALS, f"Missing concentration signal: {high}"
            assert moderate in CONCENTRATION_SIGNALS, f"Missing concentration signal: {moderate}"

    # ---------------------------------------------------------------
    # 9. ATS board and embed signals are consistent
    # ---------------------------------------------------------------
    def test_ats_signal_consistency(self):
        """ATS board and embed signals should cover the same platforms."""
        board_platforms = {s.replace("_board_detected", "") for s in ATS_BOARD_SIGNALS}
        embed_platforms = {s.replace("ats_embed_detected_", "") for s in ATS_EMBED_SIGNALS}
        assert board_platforms == embed_platforms, (
            f"Platform mismatch between board ({board_platforms}) "
            f"and embed ({embed_platforms}) signals"
        )

    # ---------------------------------------------------------------
    # 10. Scoring rule labels are unique within each category
    # ---------------------------------------------------------------
    def test_rule_labels_unique_per_category(self):
        """Each rule label should be unique within its category."""
        for cat, rules in SCORING_RULES.items():
            labels = [r["label"] for r in rules]
            dupes = [l for l in labels if labels.count(l) > 1]
            if dupes:
                pytest.fail(
                    f"Category '{cat}' has duplicate rule labels: {set(dupes)}"
                )

    # ---------------------------------------------------------------
    # 11. Careers collector covers all its category keywords
    # ---------------------------------------------------------------
    def test_careers_hiring_signals_complete(self):
        """Every CAREERS_CATEGORIES key should produce a _hiring_detected signal."""
        for cat in CAREERS_CATEGORIES:
            signal = f"{cat}_hiring_detected"
            assert signal in ALL_EMITTERS, (
                f"Careers category '{cat}' has no corresponding emitter signal '{signal}'"
            )

    # ---------------------------------------------------------------
    # 12. Keyword-only rules are flagged and documented
    # ---------------------------------------------------------------
    def test_keyword_only_rules_documented(self):
        """Keyword-only rules should be tracked in the audit result."""
        assert isinstance(self.result.keyword_only, list)
        for kw in self.result.keyword_only:
            assert kw.category in FRICTION_CATEGORIES
            assert len(kw.keywords) > 0

    # ---------------------------------------------------------------
    # 13. FIE internal signals are not in DB emitter registry
    # ---------------------------------------------------------------
    def test_fie_internal_signals_not_in_db_registry(self):
        """FunctionInferenceEngine _hiring signals (internal-only) should
        NOT be in the DB emitter registry."""
        fie_types = set(FIE_SIGNAL_MAP.values())
        db_types = set(ALL_EMITTERS.keys())
        overlap = fie_types & db_types
        assert overlap == set(), (
            f"FIE internal signals found in DB emitter registry: {overlap}"
        )

    # ---------------------------------------------------------------
    # 14. Intentionally unscored signals are documented
    # ---------------------------------------------------------------
    def test_intentionally_unscored_signals_exist_and_are_valid(self):
        """The INTENTIONALLY_UNSCORED_SIGNALS set should contain only
        signal types that are actually emitted but deliberately not scored."""
        for sig in INTENTIONALLY_UNSCORED_SIGNALS:
            assert sig in ALL_EMITTERS, (
                f"Intentionally unscored signal '{sig}' is not emitted by any collector. "
                f"Remove it from INTENTIONALLY_UNSCORED_SIGNALS or add an emitter."
            )

    # ---------------------------------------------------------------
    # 15. Audit passes (green gate for CI)
    # ---------------------------------------------------------------
    def test_audit_overall_pass(self):
        """The overall audit should pass — no ghost rules or dead categories."""
        if not self.result.passed:
            errors = "\n".join(f"  - {e}" for e in self.result.errors)
            pytest.fail(
                f"Signal contract audit FAILED:\n{errors}"
            )

    # ---------------------------------------------------------------
    # 16. All previously-ghost signal_types have been removed from rules
    # ---------------------------------------------------------------
    def test_no_ghost_signal_types_in_scoring_rules(self):
        """These signal_types were removed as ghosts in the 2026-05-18 fix.
        Verify they are not accidentally re-added."""
        REMOVED_GHOSTS = {
            "data_hiring_detected",
            "manufacturing_engineering_hiring_detected",
            "revops_role_detected",
            "software_engineering_hiring_detected",
        }
        all_signal_types = set()
        for category, rules in SCORING_RULES.items():
            for rule in rules:
                for st in rule.get("signal_types", []):
                    all_signal_types.add(st)

        reappeared = REMOVED_GHOSTS & all_signal_types
        if reappeared:
            pytest.fail(
                f"Previously removed ghost signal_types found in scoring rules: {reappeared}. "
                f"These were removed because no emitter produces them."
            )


class TestAuditReportFormat:
    """Test that the audit report is readable and complete."""

    def test_report_contains_all_sections(self):
        from app.core.signal_contract_audit import format_report
        result = run_audit()
        report = format_report(result)

        assert "ORPHAN SIGNALS" in report
        assert "GHOST RULES" in report
        assert "KEYWORD-ONLY RULES" in report
        assert "CATEGORY COVERAGE" in report
        assert "WEIGHT IMBALANCE" in report
        assert "RESULT:" in report
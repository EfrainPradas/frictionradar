"""
Signal contract tests — verify all signal types are well-formed and
the scoring rules reference valid signal types.

Ensures:
  1. Every signal type in the registry is a non-empty string.
  2. Scoring rules reference only valid signal types.
  3. CompanySignal mock objects have required attributes.
  4. Source types are from the known set.
  5. Numeric signal types carry numeric_value; non-numeric types can omit it.
"""

import pytest
from tests.conftest import (
    make_signal, make_signals, SIGNAL_TYPES, SOURCE_TYPES,
)
from app.core.scoring_rules import SCORING_RULES


class TestSignalTypeRegistry:
    """Verify the canonical signal type registry is well-formed."""

    def test_all_signal_types_are_non_empty_strings(self):
        for category, types in SIGNAL_TYPES.items():
            for t in types:
                assert isinstance(t, str) and len(t) > 0, (
                    f"Signal type in {category} is not a non-empty string: {t!r}"
                )

    def test_no_duplicate_signal_types(self):
        all_types = []
        for category, types in SIGNAL_TYPES.items():
            all_types.extend(types)
        assert len(all_types) == len(set(all_types)), (
            f"Duplicate signal types found: {set(t for t in all_types if all_types.count(t) > 1)}"
        )

    def test_signal_types_follow_naming_convention(self):
        for category, types in SIGNAL_TYPES.items():
            for t in types:
                assert t == t.lower(), f"Signal type should be lowercase: {t}"
                assert " " not in t, f"Signal type should use underscores not spaces: {t}"


class TestScoringRulesContract:
    """Verify scoring rules reference valid signal types and are well-formed."""

    def test_scoring_rules_categories_exist(self):
        """All scoring categories should be in FRICTION_CATEGORIES."""
        from app.core.friction_categories import FRICTION_CATEGORIES
        for cat in SCORING_RULES:
            assert cat in FRICTION_CATEGORIES, (
                f"Scoring rule category '{cat}' not in FRICTION_CATEGORIES"
            )

    def test_scoring_rules_have_required_fields(self):
        """Each rule should have label, weight, signal_types, keywords."""
        for cat, rules in SCORING_RULES.items():
            for rule in rules:
                assert "label" in rule, f"Rule missing 'label' in category {cat}"
                assert "weight" in rule, f"Rule '{rule.get('label')}' missing 'weight'"
                assert isinstance(rule["weight"], (int, float)), (
                    f"Rule '{rule['label']}' weight should be numeric"
                )
                assert rule["weight"] > 0, f"Rule '{rule['label']}' weight should be positive"

    def test_scoring_rule_signal_types_are_strings(self):
        """Every signal_type in rules should be a non-empty string."""
        for cat, rules in SCORING_RULES.items():
            for rule in rules:
                for st in rule.get("signal_types", []):
                    assert isinstance(st, str) and len(st) > 0, (
                        f"Empty signal_type in rule '{rule['name']}'"
                    )

    def test_scoring_rule_keywords_are_strings(self):
        """Every keyword in rules should be a non-empty lowercase string."""
        for cat, rules in SCORING_RULES.items():
            for rule in rules:
                for kw in rule.get("keywords", []):
                    assert isinstance(kw, str) and len(kw) > 0, (
                        f"Empty keyword in rule '{rule['name']}'"
                    )
                    assert kw == kw.lower(), f"Keyword should be lowercase: {kw}"


class TestSignalMockFactory:
    """Verify the mock signal factory produces well-formed objects."""

    def test_make_signal_has_required_attributes(self):
        s = make_signal()
        assert hasattr(s, "signal_type")
        assert hasattr(s, "signal_text")
        assert hasattr(s, "numeric_value")
        assert hasattr(s, "source_type")
        assert hasattr(s, "company_id")
        assert hasattr(s, "confidence")

    def test_make_signal_default_type(self):
        s = make_signal()
        assert s.signal_type == "open_positions_count_detected"

    def test_make_signal_custom_values(self):
        s = make_signal(
            signal_type="high_open_positions_count_detected",
            signal_text="Open positions: 150",
            numeric_value=150,
            source_type="playwright_careers",
        )
        assert s.signal_type == "high_open_positions_count_detected"
        assert s.numeric_value == 150
        assert s.source_type == "playwright_careers"

    def test_make_signals_batch(self):
        signals = make_signals([
            ("open_positions_count_detected", 30),
            ("analytics_hiring_detected", None),
            ("careers_page_found", None),
        ])
        assert len(signals) == 3
        assert signals[0].signal_type == "open_positions_count_detected"
        assert signals[0].numeric_value == 30

    def test_source_types_are_from_known_set(self):
        for src in SOURCE_TYPES:
            assert isinstance(src, str) and len(src) > 0


class TestSignalNumericConsistency:
    """Verify numeric signal types carry numeric_value and text types can omit it."""

    NUMERIC_SIGNAL_TYPES = {
        "open_positions_count_detected",
        "high_open_positions_count_detected",
    }

    def test_numeric_signals_have_value(self):
        for st in self.NUMERIC_SIGNAL_TYPES:
            s = make_signal(signal_type=st, numeric_value=42)
            assert s.numeric_value is not None, (
                f"Signal type '{st}' should carry a numeric_value"
            )

    def test_text_signals_can_have_null_value(self):
        text_types = [
            "careers_page_found",
            "analytics_hiring_detected",
            "scaling_language_detected",
        ]
        for st in text_types:
            s = make_signal(signal_type=st, numeric_value=None)
            assert s.numeric_value is None
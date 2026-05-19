from typing import Final, List

# -----------------------------------------------
# Friction Categories — Central Definition
# Used by: scoring engine, hypothesis engine, APIs
# -----------------------------------------------

FRICTION_CATEGORIES: Final[List[str]] = [
    "reporting_fragmentation",
    "process_inefficiency",
    "tooling_inconsistency",
    "scaling_strain",
    "customer_experience_friction",
]

# Human-readable labels for display / hypothesis generation
FRICTION_CATEGORY_LABELS: Final[dict] = {
    "reporting_fragmentation":       "Reporting Fragmentation",
    "process_inefficiency":          "Process Inefficiency",
    "tooling_inconsistency":         "Tooling Inconsistency",
    "scaling_strain":                "Scaling Strain",
    "customer_experience_friction":  "Customer Experience Friction",
}

SCORING_VERSION: Final[str] = "2.0.0"

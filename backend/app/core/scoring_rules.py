"""
Scoring rules configuration for Friction Radar.

Structure:
  SCORING_RULES: dict[category] -> list of rule dicts
  Each rule: { "signal_types": [...], "keywords": [...], "weight": float, "label": str }

Rules are evaluated against collected CompanySignal records.
Match logic:
  1. If signal_type matches any entry in "signal_types" → match
  2. If signal_text contains any keyword in "keywords" (case-insensitive) → match
  A matched rule contributes its full weight to the category score.
"""

SCORING_RULES: dict = {
    "reporting_fragmentation": [
        {
            "label": "analytics_role_detected",
            "signal_types": ["analytics_role_detected"],
            "keywords": [
                "analytics",
                "data analyst",
                "bi analyst",
                "business intelligence",
            ],
            "weight": 1.5,
        },
        {
            "label": "analytics_concentration",
            "signal_types": ["analytics_concentration_high", "analytics_concentration_moderate"],
            "keywords": [],
            "weight": 1.5,
        },
        {
            "label": "reporting_language_detected",
            "signal_types": ["reporting_language_detected"],
            "keywords": [
                "reporting",
                "quarterly",
                "visibility",
                "dashboard",
                "metrics",
            ],
            "weight": 1.0,
        },
        {
            "label": "multiple_open_roles",
            "signal_types": [
                "multiple_open_roles",
                "high_open_positions_count_detected",
                "open_positions_count_detected",
            ],
            "keywords": ["open roles", "open positions", "multiple openings"],
            "weight": 0.5,
        },
        {
            "label": "data_hiring_detected",
            "signal_types": ["data_hiring_detected"],
            "keywords": [],
            "weight": 1.0,
        },
    ],
    "process_inefficiency": [
        {
            "label": "process_language_detected",
            "signal_types": ["process_language_detected"],
            "keywords": [
                "process",
                "workflow",
                "manual",
                "coordination",
                "bottleneck",
                "handoff",
            ],
            "weight": 1.5,
        },
        {
            "label": "revops_role_detected",
            "signal_types": ["revops_role_detected", "revops_language_detected"],
            "keywords": ["revops", "revenue operations", "operations", "ops"],
            "weight": 1.5,
        },
        {
            "label": "manual_work_language",
            "signal_types": [],
            "keywords": ["manual", "spreadsheet", "excel", "copy-paste", "ad hoc"],
            "weight": 1.0,
        },
        {
            "label": "operations_hiring_detected",
            "signal_types": ["operations_hiring_detected"],
            "keywords": [],
            "weight": 0.75,
        },
        {
            "label": "operations_concentration",
            "signal_types": ["operations_concentration_high", "operations_concentration_moderate"],
            "keywords": [],
            "weight": 1.5,
        },
    ],
    "tooling_inconsistency": [
        {
            "label": "mixed_tool_references",
            "signal_types": [],
            "keywords": [
                "salesforce",
                "hubspot",
                "jira",
                "notion",
                "asana",
                "monday",
                "microsoft",
                "google workspace",
            ],
            "weight": 0.75,
        },
        {
            "label": "stack_inconsistency_language",
            "signal_types": [],
            "keywords": [
                "multiple tools",
                "tool stack",
                "platform",
                "integration",
                "conflicting systems",
            ],
            "weight": 1.0,
        },
        {
            "label": "technology_hiring_detected",
            "signal_types": [
                "technology_hiring_detected",
                "software_engineering_hiring_detected",
            ],
            "keywords": [],
            "weight": 0.75,
        },
        {
            "label": "engineering_it_concentration",
            "signal_types": ["engineering_concentration_high", "it_concentration_high", "engineering_concentration_moderate", "it_concentration_moderate"],
            "keywords": [],
            "weight": 1.5,
        },
    ],
    "scaling_strain": [
        {
            "label": "growth_language_detected",
            "signal_types": ["growth_language_detected"],
            "keywords": [
                "growth",
                "scale",
                "scaling",
                "growing rapidly",
                "expanding",
                "high growth",
            ],
            "weight": 1.5,
        },
        {
            "label": "multiple_open_roles",
            "signal_types": [
                "multiple_open_roles",
                "high_open_positions_count_detected",
                "open_positions_count_detected",
                "job_cards_visible_detected",
            ],
            "keywords": [
                "hiring",
                "open roles",
                "we are growing",
                "join our team",
                "positions",
            ],
            "weight": 0.75,
        },
        {
            "label": "newsroom_growth_signals",
            "signal_types": ["newsroom_found"],
            "keywords": ["series", "funding", "raised", "expansion", "headcount"],
            "weight": 1.0,
        },
        {
            "label": "retail_hiring_detected",
            "signal_types": ["retail_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "manufacturing_hiring_detected",
            "signal_types": [
                "manufacturing_hiring_detected",
                "manufacturing_engineering_hiring_detected",
            ],
            "keywords": [],
            "weight": 0.75,
        },
        {
            "label": "distribution_hiring_detected",
            "signal_types": [
                "distribution_hiring_detected",
                "supply_chain_hiring_detected",
            ],
            "keywords": [],
            "weight": 0.75,
        },
        {
            "label": "high_hiring_volume",
            "signal_types": ["high_hiring_volume", "broad_hiring_pattern"],
            "keywords": [],
            "weight": 1.0,
        },
        {
            "label": "narrow_hiring_focus",
            "signal_types": ["narrow_hiring_focus"],
            "keywords": [],
            "weight": 0.75,
        },
    ],
    "customer_experience_friction": [
        {
            "label": "complaint_language_detected",
            "signal_types": [],
            "keywords": [
                "complaint",
                "issue",
                "frustrating",
                "confusing",
                "unreliable",
                "slow",
                "difficult",
            ],
            "weight": 1.5,
        },
        {
            "label": "support_pain_language",
            "signal_types": [],
            "keywords": [
                "support ticket",
                "customer feedback",
                "churn",
                "usability",
                "friction",
            ],
            "weight": 1.0,
        },
        {
            "label": "customer_success_hiring_detected",
            "signal_types": ["customer_success_hiring_detected"],
            "keywords": [],
            "weight": 0.75,
        },
        {
            "label": "customer_support_concentration",
            "signal_types": ["customer_support_concentration_high", "customer_support_concentration_moderate"],
            "keywords": [],
            "weight": 1.5,
        },
    ],
}

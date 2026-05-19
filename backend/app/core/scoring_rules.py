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

Signal contract (2026-05-18 audit):
  - Every signal_type in "signal_types" must have a real emitter (no ghosts).
  - Every emitter signal_type should appear in at least one rule (no orphans).
  - Discovery signals (careers_page_found, company_size_detected,
    visible_hiring_area_detected, job_links_extracted) are intentionally
    unscored — they feed evidence quality, not friction scoring.
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
        # --- New: finance signals map to reporting/visibility friction ---
        {
            "label": "finance_concentration",
            "signal_types": ["finance_concentration_high", "finance_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "finance_hiring_detected",
            "signal_types": ["finance_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
        },
    ],
    "process_inefficiency": [
        {
            # Keyword-only rule: no emitter produces "process_language_detected".
            # Keywords match signal_text from other collectors (newsroom, site).
            "label": "process_language_detected",
            "signal_types": [],  # was ["process_language_detected"] — ghost removed
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
            # "revops_role_detected" was a ghost — no emitter ever produced it.
            # The rule fires via "revops_language_detected" (CompanySiteCollector)
            # and keyword matching.
            "label": "revops_language_detected",
            "signal_types": ["revops_language_detected"],  # was ["revops_role_detected", "revops_language_detected"]
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
        # --- New: secondary process-inefficiency signals ---
        {
            "label": "supply_chain_concentration",
            "signal_types": ["supply_chain_concentration_high", "supply_chain_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "marketing_concentration",
            "signal_types": ["marketing_concentration_high", "marketing_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "hr_concentration",
            "signal_types": ["hr_concentration_high", "hr_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "legal_concentration",
            "signal_types": ["legal_concentration_high", "legal_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "education_concentration",
            "signal_types": ["education_concentration_high", "education_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "hr_people_hiring_detected",
            "signal_types": ["hr_people_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "legal_hiring_detected",
            "signal_types": ["legal_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "marketing_hiring_detected",
            "signal_types": ["marketing_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "cross_team_friction",
            "signal_types": ["cross_team_language_detected"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "partnership_complexity",
            "signal_types": ["partnership_detected"],
            "keywords": [],
            "weight": 0.5,
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
            # "software_engineering_hiring_detected" was a ghost — no emitter.
            # Canonical emitter is "technology_hiring_detected" (CareersCollector).
            "label": "technology_hiring_detected",
            "signal_types": ["technology_hiring_detected"],  # was ["technology_hiring_detected", "software_engineering_hiring_detected"]
            "keywords": [],
            "weight": 0.75,
        },
        {
            "label": "engineering_it_concentration",
            "signal_types": ["engineering_concentration_high", "it_concentration_high", "engineering_concentration_moderate", "it_concentration_moderate"],
            "keywords": [],
            "weight": 1.5,
        },
        # --- New: product/design signals map to tooling friction ---
        {
            "label": "product_concentration",
            "signal_types": ["product_concentration_high", "product_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "design_concentration",
            "signal_types": ["design_concentration_high", "design_concentration_moderate"],  # design is not in CANONICAL_AREAS — see note
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "product_hiring_detected",
            "signal_types": ["product_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "design_hiring_detected",
            "signal_types": ["design_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
        },
    ],
    "scaling_strain": [
        {
            # Expanded: added expansion_language_detected, scaling_language_detected,
            # hiring_news_detected from CompanySiteCollector and NewsroomCollector.
            "label": "growth_language_detected",
            "signal_types": [
                "growth_language_detected",
                "expansion_language_detected",
                "scaling_language_detected",
                "hiring_news_detected",
            ],
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
            # Expanded: added hiring_language_detected (CompanySiteCollector)
            # and all 8 ATS board + 8 ATS embed signals.
            "label": "multiple_open_roles",
            "signal_types": [
                "multiple_open_roles",
                "high_open_positions_count_detected",
                "open_positions_count_detected",
                "job_cards_visible_detected",
                "hiring_language_detected",
                # ATS board detection — company uses a hiring platform
                "greenhouse_board_detected",
                "lever_board_detected",
                "ashby_board_detected",
                "smartrecruiters_board_detected",
                "jobvite_board_detected",
                "icims_board_detected",
                "workday_board_detected",
                "myworkdayjobs_board_detected",
                # ATS embed detection — ATS scripts found on homepage
                "ats_embed_detected_greenhouse",
                "ats_embed_detected_lever",
                "ats_embed_detected_ashby",
                "ats_embed_detected_smartrecruiters",
                "ats_embed_detected_jobvite",
                "ats_embed_detected_icims",
                "ats_embed_detected_workday",
                "ats_embed_detected_myworkdayjobs",
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
            # Expanded: added funding_detected, acquisition_detected from NewsroomCollector.
            "label": "newsroom_growth_signals",
            "signal_types": ["newsroom_found", "funding_detected", "acquisition_detected"],
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
            # "manufacturing_engineering_hiring_detected" was a ghost —
            # canonical emitter is "manufacturing_hiring_detected".
            "label": "manufacturing_hiring_detected",
            "signal_types": ["manufacturing_hiring_detected"],  # was ["manufacturing_hiring_detected", "manufacturing_engineering_hiring_detected"]
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
        # --- New: secondary scaling-strain signals ---
        {
            "label": "sales_concentration",
            "signal_types": ["sales_concentration_high", "sales_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "recruiting_concentration",
            "signal_types": ["recruiting_concentration_high", "recruiting_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "manufacturing_concentration",
            "signal_types": ["manufacturing_concentration_high", "manufacturing_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "trades_concentration",
            "signal_types": ["trades_concentration_high", "trades_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "transportation_concentration",
            "signal_types": ["transportation_concentration_high", "transportation_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "sales_hiring_detected",
            "signal_types": ["sales_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "healthcare_hiring_detected",
            "signal_types": ["healthcare_hiring_detected"],
            "keywords": [],
            "weight": 0.5,
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
        # --- New: customer-facing concentration signals ---
        {
            "label": "retail_concentration",
            "signal_types": ["retail_concentration_high", "retail_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "healthcare_concentration",
            "signal_types": ["healthcare_concentration_high", "healthcare_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "hospitality_concentration",
            "signal_types": ["hospitality_concentration_high", "hospitality_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
        {
            "label": "food_service_concentration",
            "signal_types": ["food_service_concentration_high", "food_service_concentration_moderate"],
            "keywords": [],
            "weight": 0.5,
        },
    ],
}

# Intentionally unscored signals — these are discovery/evidence-quality signals
# that do NOT feed into friction scoring directly. They influence evidence
# thresholds and company classification instead.
INTENTIONALLY_UNSCORED_SIGNALS: set = {
    "careers_page_found",            # Discovery: page exists, no friction signal
    "company_size_detected",         # Context: feeds company_type, not scoring
    "visible_hiring_area_detected",  # Extraction: area detection metadata
    "job_links_extracted",           # Extraction: link count metadata
}
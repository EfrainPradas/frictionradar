"""
Positioning Engine — Phase 10: translates company diagnostics into
actionable positioning guidance for NovaWork candidates.

The engine does NOT activate for all companies. It requires sufficient
evidence (eligibility gates) and modulates assertiveness based on
confidence band.

Pipeline:
  1. ELIGIBILITY: Is there enough evidence to position?
  2. DIAGNOSIS: What pain does the company have?
  3. POSITIONING: How should a candidate present themselves?
  4. GUARDRAILS: What should we NOT claim?

Output is deterministic, auditable, and template-driven (no LLM calls).
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.company_job_role import CompanyJobRole, HiringPattern
from app.models.company_signal import CompanySignal
from app.services.company_evaluation import CompanyEvaluationEngine
from app.services.title_normalizer import get_macro_family, MACRO_FAMILIES
from app.core.logging import get_logger

logger = get_logger(__name__)

evaluation_engine = CompanyEvaluationEngine()


# ── Eligibility gates ────────────────────────────────────────────────

ELIGIBLE_DS = {
    "ready_for_positioning",
    "specific_pain_identified",
    "specific_pain_emerging",
}

# broad_hiring_pattern_detected is conditionally eligible (see below)
CONDITIONAL_DS = {"broad_hiring_pattern_detected"}


@dataclass
class EligibilityResult:
    eligible: bool
    gate_passed: str  # "full", "conditional", "none"
    reason: str
    diagnostic_state: str
    confidence_band: str  # "high", "moderate", "low"


def check_eligibility(
    diagnostic_state: str,
    pain_clarity: str,
    function_concentration: str,
    positioning_readiness: str,
    classified_roles: int,
    jds_extracted: int,
) -> EligibilityResult:
    """Determine if a company has enough evidence for positioning."""

    if diagnostic_state in ("ready_for_positioning",):
        return EligibilityResult(
            eligible=True,
            gate_passed="full",
            reason="Full evidence — ready for confident positioning.",
            diagnostic_state=diagnostic_state,
            confidence_band="high",
        )

    if diagnostic_state == "specific_pain_identified":
        band = "high" if jds_extracted >= 3 and classified_roles >= 5 else "moderate"
        return EligibilityResult(
            eligible=True,
            gate_passed="full",
            reason="Specific pain identified with concentrated evidence.",
            diagnostic_state=diagnostic_state,
            confidence_band=band,
        )

    if diagnostic_state == "specific_pain_emerging":
        if classified_roles >= 3:
            return EligibilityResult(
                eligible=True,
                gate_passed="conditional",
                reason="Pain emerging — positioning possible with caveats.",
                diagnostic_state=diagnostic_state,
                confidence_band="moderate",
            )
        return EligibilityResult(
            eligible=False,
            gate_passed="none",
            reason="Pain emerging but insufficient classified roles.",
            diagnostic_state=diagnostic_state,
            confidence_band="low",
        )

    if diagnostic_state == "broad_hiring_pattern_detected":
        if classified_roles >= 5 and function_concentration != "low":
            return EligibilityResult(
                eligible=True,
                gate_passed="conditional",
                reason="Broad pattern but enough concentration for directional positioning.",
                diagnostic_state=diagnostic_state,
                confidence_band="low",
            )
        if classified_roles >= 15:
            return EligibilityResult(
                eligible=True,
                gate_passed="conditional",
                reason="High-volume generalist hiring — growth-stage buyer profile.",
                diagnostic_state=diagnostic_state,
                confidence_band="low",
            )
        return EligibilityResult(
            eligible=False,
            gate_passed="none",
            reason="Broad hiring pattern without enough concentration or volume.",
            diagnostic_state=diagnostic_state,
            confidence_band="low",
        )

    return EligibilityResult(
        eligible=False,
        gate_passed="none",
        reason=f"Diagnostic state '{diagnostic_state}' does not support positioning.",
        diagnostic_state=diagnostic_state,
        confidence_band="low",
    )


# ── Shared eligibility snapshot (single source of truth) ─────────────
#
# Canonical batch evaluator used by ALL reporting layers (dataset_health,
# audit_positioning_output, recompute_funnel_snapshot, master summary).
# Replicates the pattern that was duplicated across scripts so every
# layer reports identical counts.

def is_company_positioning_eligible(db, company_id) -> "EligibilityResult":
    """Single-company canonical eligibility check.

    Loads the inputs (diagnostic_state, kpis, classified_roles, jds) for
    one company and runs check_eligibility() on them. This is the one
    function every layer should call when asked "is company X eligible?".
    """
    from app.models.company_job_role import CompanyJobRole

    ev = evaluation_engine.evaluate(company_id=company_id, db=db)
    ds = ev.get("diagnostic_state", "")
    kpis = ev.get("kpis", {})

    classified = (
        db.query(CompanyJobRole)
        .filter(
            CompanyJobRole.company_id == company_id,
            CompanyJobRole.functional_area.isnot(None),
            ~CompanyJobRole.functional_area.in_(["junk", "unknown"]),
        )
        .count()
    )
    jds = (
        db.query(CompanyJobRole)
        .filter(
            CompanyJobRole.company_id == company_id,
            CompanyJobRole.role_description.isnot(None),
            CompanyJobRole.role_description != "",
        )
        .count()
    )

    return check_eligibility(
        diagnostic_state=ds,
        pain_clarity=kpis.get("pain_clarity", "low"),
        function_concentration=kpis.get("function_concentration", "low"),
        positioning_readiness=kpis.get("positioning_readiness", "low"),
        classified_roles=classified,
        jds_extracted=jds,
    )


def compute_eligibility_snapshot(db) -> dict:
    """Batch canonical eligibility snapshot for the whole dataset.

    Returns the exact shape every reporting layer should consume:

        {
          "full": int,
          "conditional": int,
          "not_eligible": int,
          "total_eligible": int,
          "ds_distribution": {ds: count, ...},
          "by_company": [
              {company_id, name, ds, gate_passed, eligible,
               confidence_band, reason, classified_roles, jds_extracted},
              ...
          ],
        }

    This is the SINGLE place that decides eligibility counts. Any script
    that reports a different number is wrong and should be pointed here.
    """
    from collections import Counter
    from app.models.company import Company
    from app.models.company_job_role import CompanyJobRole

    companies = db.query(Company.id, Company.name).all()

    # Preload classified_roles per company.
    classified_by_company: dict = {}
    for cid, area in (
        db.query(CompanyJobRole.company_id, CompanyJobRole.functional_area)
        .filter(
            CompanyJobRole.functional_area.isnot(None),
            ~CompanyJobRole.functional_area.in_(["junk", "unknown"]),
        )
        .all()
    ):
        classified_by_company[cid] = classified_by_company.get(cid, 0) + 1

    # Preload JD counts per company.
    jd_counts: dict = {}
    for cid, desc in (
        db.query(CompanyJobRole.company_id, CompanyJobRole.role_description).all()
    ):
        if desc:
            jd_counts[cid] = jd_counts.get(cid, 0) + 1

    full = 0
    conditional = 0
    not_eligible = 0
    ds_dist: Counter = Counter()
    by_company: list = []

    for cid, name in companies:
        try:
            ev = evaluation_engine.evaluate(company_id=cid, db=db)
            ds = ev.get("diagnostic_state", "")
            kpis = ev.get("kpis", {})
        except Exception as exc:
            ds = f"error:{type(exc).__name__}"
            kpis = {}
            db.rollback()

        ds_dist[ds] += 1
        elig = check_eligibility(
            diagnostic_state=ds,
            pain_clarity=kpis.get("pain_clarity", "low"),
            function_concentration=kpis.get("function_concentration", "low"),
            positioning_readiness=kpis.get("positioning_readiness", "low"),
            classified_roles=classified_by_company.get(cid, 0),
            jds_extracted=jd_counts.get(cid, 0),
        )

        if elig.eligible and elig.gate_passed == "full":
            full += 1
        elif elig.eligible and elig.gate_passed == "conditional":
            conditional += 1
        else:
            not_eligible += 1

        by_company.append({
            "company_id": cid,
            "name": name,
            "ds": ds,
            "gate_passed": elig.gate_passed,
            "eligible": elig.eligible,
            "confidence_band": elig.confidence_band,
            "reason": elig.reason,
            "classified_roles": classified_by_company.get(cid, 0),
            "jds_extracted": jd_counts.get(cid, 0),
        })

    return {
        "full": full,
        "conditional": conditional,
        "not_eligible": not_eligible,
        "total_eligible": full + conditional,
        "ds_distribution": dict(ds_dist),
        "by_company": by_company,
    }


# ── Positioning output contract ──────────────────────────────────────

@dataclass
class PositioningOutput:
    """Full positioning output for a company-candidate pair."""

    # Identity
    company_name: str
    company_domain: str
    company_id: str

    # Eligibility
    eligible: bool
    confidence_band: str  # "high", "moderate", "low"
    gate_passed: str

    # Diagnosis (what the company needs)
    pain_summary: str = ""
    evidence_summary: str = ""
    likely_business_need: str = ""
    dominant_function: str = ""
    macro_family: str = ""
    supporting_functions: list = field(default_factory=list)

    # Positioning (how candidate should present)
    candidate_archetype: str = ""
    positioning_angle: str = ""
    resume_emphasis: list = field(default_factory=list)
    networking_angle: str = ""
    interview_themes: list = field(default_factory=list)

    # Guardrails
    do_not_overclaim: list = field(default_factory=list)
    evidence_caveats: list = field(default_factory=list)
    assertiveness_level: str = ""  # "confident", "directional", "exploratory"

    # Metadata
    generated_from_ds: str = ""
    evidence_depth: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Candidate archetype mapping ──────────────────────────────────────

CANDIDATE_ARCHETYPES = {
    # Keys use the CANONICAL functional_area names (as persisted by
    # hiring_pattern_service._canonical). The old engine names
    # (data_analytics, hr_people, customer_success, recruiting_talent,
    # legal_compliance) are not stored in the DB — lookups use canonical.
    "analytics": {
        "archetype": "Data-to-Decisions Specialist",
        "angle": "You solve the gap between raw data and clear business decisions. Position yourself as someone who builds the reporting infrastructure leadership actually trusts.",
        "resume_emphasis": [
            "Dashboards and reporting systems you built from scratch",
            "Decisions influenced by your analysis (with business outcomes)",
            "Data tools and platforms you standardized across teams",
            "Metrics frameworks you designed that became team standards",
        ],
        "networking_angle": "Ask about their data maturity — most companies at this stage have data but can't turn it into action. Your opening is: 'What does your reporting workflow look like today?'",
        "interview_themes": [
            "How they currently track KPIs (manual vs automated)",
            "Who consumes their data products (leadership vs individual teams)",
            "Where data requests get stuck (tooling, access, interpretation)",
        ],
    },
    "finance": {
        "archetype": "Financial Operations Architect",
        "angle": "You bring clarity to financial chaos. Position yourself as someone who can own the forecasting-to-reporting pipeline and make the numbers trustworthy.",
        "resume_emphasis": [
            "Close processes you streamlined (days reduced, error rates)",
            "Forecasting models you built or improved",
            "Audit readiness you achieved or maintained",
            "Systems you migrated or consolidated (ERP, GL)",
        ],
        "networking_angle": "Ask about their close cycle and forecasting accuracy. Companies hiring multiple finance roles usually have a visibility problem, not just a headcount problem.",
        "interview_themes": [
            "Close cycle timeline and pain points",
            "Forecasting accuracy and cadence",
            "ERP/GL system maturity and planned migrations",
        ],
    },
    "operations": {
        "archetype": "Operational Clarity Builder",
        "angle": "You turn coordination chaos into repeatable systems. Position yourself as the person who makes scaling not hurt.",
        "resume_emphasis": [
            "Processes you designed that teams actually adopted",
            "Cross-functional coordination you established",
            "Efficiency gains with concrete metrics (time, cost, throughput)",
            "Tools and workflows you standardized",
        ],
        "networking_angle": "Ask about what breaks when they scale — the answer reveals whether they need a process person, a systems person, or a people-coordinator. Tailor your pitch accordingly.",
        "interview_themes": [
            "How cross-functional handoffs work today",
            "Where bottlenecks appear as volume increases",
            "What happens when a key person is out (bus factor)",
        ],
    },
    "supply_chain": {
        "archetype": "Supply Chain Visibility Specialist",
        "angle": "You connect demand signals to delivery execution. Position yourself as someone who makes the planning-to-fulfillment loop reliable.",
        "resume_emphasis": [
            "Demand planning accuracy improvements",
            "Inventory optimization results (turns, stockouts reduced)",
            "Vendor management and sourcing wins",
            "S&OP processes you established or improved",
        ],
        "networking_angle": "Ask about their forecast accuracy and safety stock strategy. If they can't answer quickly, that's the pain you solve.",
        "interview_themes": [
            "Planning horizon and accuracy",
            "Supplier diversification strategy",
            "WMS/ERP integration maturity",
        ],
    },
    "marketing": {
        "archetype": "Growth and Performance Marketer",
        "angle": "You connect marketing spend to revenue outcomes. Position yourself as someone who makes marketing measurable and accountable.",
        "resume_emphasis": [
            "Campaigns with clear ROI attribution",
            "Marketing-to-pipeline conversion improvements",
            "Channel strategy decisions with before/after metrics",
            "Marketing tech stack you built or optimized",
        ],
        "networking_angle": "Ask how they currently measure marketing effectiveness. Companies hiring multiple marketing roles often can't answer this clearly — that's your entry.",
        "interview_themes": [
            "Attribution model maturity",
            "Marketing-sales handoff and alignment",
            "Content strategy and distribution channels",
        ],
    },
    "sales": {
        "archetype": "Revenue Engine Builder",
        "angle": "You build predictable pipeline, not just close deals. Position yourself as someone who can make revenue generation systematic.",
        "resume_emphasis": [
            "Pipeline metrics you improved (velocity, conversion rates)",
            "Sales processes you formalized or scaled",
            "Revenue growth in specific segments or territories",
            "CRM and forecasting discipline you established",
        ],
        "networking_angle": "Ask about their pipeline visibility and forecast accuracy. If leadership can't predict next quarter's revenue, your process skills are what they need.",
        "interview_themes": [
            "Pipeline stages and conversion rates",
            "Forecast accuracy and methodology",
            "Sales enablement and onboarding maturity",
        ],
    },
    "customer_support": {
        "archetype": "Customer Retention Strategist",
        "angle": "You turn reactive support into proactive success. Position yourself as someone who makes customer relationships predictable and profitable.",
        "resume_emphasis": [
            "Retention and churn improvements with metrics",
            "Customer health scoring systems you built",
            "Support-to-success transitions you managed",
            "NPS/CSAT improvements with specific actions taken",
        ],
        "networking_angle": "Ask about their churn rate and how they currently identify at-risk accounts. The answer reveals whether they need a process builder or a relationship manager.",
        "interview_themes": [
            "Customer health scoring methodology",
            "Escalation and renewal processes",
            "Product feedback loops from CS to product",
        ],
    },
    "product": {
        "archetype": "Product Clarity Driver",
        "angle": "You turn feature chaos into strategic roadmap. Position yourself as someone who makes product decisions defensible and aligned to business outcomes.",
        "resume_emphasis": [
            "Roadmap prioritization frameworks you used",
            "Features you shipped with measurable impact",
            "Stakeholder alignment processes you built",
            "Discovery and validation methods you applied",
        ],
        "networking_angle": "Ask how they decide what to build next. If the answer involves stakeholder opinions more than data, that's your opening.",
        "interview_themes": [
            "Roadmap prioritization process",
            "Discovery and validation cadence",
            "How success metrics are defined for features",
        ],
    },
    "engineering": {
        "archetype": "Engineering Reliability Builder",
        "angle": "You make engineering delivery predictable. Position yourself as someone who reduces surprises in deployment and improves team velocity.",
        "resume_emphasis": [
            "Deployment frequency and reliability improvements",
            "Technical debt reduction with business impact",
            "System reliability metrics (uptime, MTTR)",
            "CI/CD or infrastructure improvements you drove",
        ],
        "networking_angle": "Ask about their deployment cadence and incident frequency. Engineers who can talk about reliability in business terms are rare — lean into that.",
        "interview_themes": [
            "Deployment frequency and rollback process",
            "On-call and incident management maturity",
            "Tech debt management approach",
        ],
    },
    "hr": {
        "archetype": "People Operations Architect",
        "angle": "You build people systems that scale. Position yourself as someone who makes HR feel like an operating system, not a help desk.",
        "resume_emphasis": [
            "HRIS or people systems you implemented",
            "Employee experience programs with measurable outcomes",
            "Compliance and policy frameworks you built",
            "Manager enablement or training programs you launched",
        ],
        "networking_angle": "Ask about their employee lifecycle — onboarding to exit. The gaps they can't describe clearly are where you add value.",
        "interview_themes": [
            "HRIS maturity and integration",
            "Employee engagement measurement",
            "Compliance and policy standardization",
        ],
    },
    "recruiting": {
        "archetype": "Talent Pipeline Optimizer",
        "angle": "You make hiring fast without making it reckless. Position yourself as someone who builds repeatable recruiting systems, not just fills seats.",
        "resume_emphasis": [
            "Time-to-fill improvements with quality maintained",
            "Sourcing channels you built or optimized",
            "ATS and workflow automation you implemented",
            "Employer brand initiatives with measurable reach",
        ],
        "networking_angle": "Ask about their current time-to-fill and offer acceptance rate. Companies hiring recruiters usually can't answer this accurately — that's the systemic problem you fix.",
        "interview_themes": [
            "Requisition volume and prioritization",
            "Sourcing strategy and channel effectiveness",
            "Hiring manager satisfaction and feedback loops",
        ],
    },
    "legal": {
        "archetype": "Compliance and Risk Navigator",
        "angle": "You make compliance a strategic advantage, not a bottleneck. Position yourself as someone who prevents problems before they become crises.",
        "resume_emphasis": [
            "Compliance programs you built or overhauled",
            "Risk assessments you led with business-relevant outcomes",
            "Contract management systems you streamlined",
            "Regulatory changes you navigated successfully",
        ],
        "networking_angle": "Ask about their biggest compliance concern right now. The specificity of their answer tells you whether they need a generalist or a specialist.",
        "interview_themes": [
            "Regulatory landscape and upcoming changes",
            "Contract review volume and turnaround time",
            "Audit readiness and cadence",
        ],
    },
    "manufacturing": {
        "archetype": "Production Excellence Leader",
        "angle": "You make production reliable and measurable. Position yourself as someone who connects shop floor execution to business outcomes.",
        "resume_emphasis": [
            "OEE or throughput improvements",
            "Quality programs (Six Sigma, lean, SPC) with results",
            "Production scaling you managed",
            "Safety record and compliance achievements",
        ],
        "networking_angle": "Ask about their biggest production constraint today. Is it capacity, quality, or labor? Each answer opens a different positioning path.",
        "interview_themes": [
            "Production KPIs tracked and cadence",
            "Quality control methodology",
            "Workforce planning and shift management",
        ],
    },
    "retail": {
        "archetype": "Retail Operations Optimizer",
        "angle": "You turn store-level chaos into consistent performance. Position yourself as someone who makes multi-location management scalable.",
        "resume_emphasis": [
            "Store performance metrics you improved (comp sales, conversion)",
            "Multi-location standardization you drove",
            "Labor scheduling optimization with results",
            "Customer experience improvements with measurable impact",
        ],
        "networking_angle": "Ask about their store-to-store variance in performance. High variance = broken systems, which is what you fix.",
        "interview_themes": [
            "Store performance benchmarking approach",
            "Labor model and scheduling methodology",
            "Inventory management at store level",
        ],
    },
    "it": {
        "archetype": "IT Stability and Enablement Lead",
        "angle": "You make internal IT invisible — because it just works. Position yourself as someone who turns IT from a complaint department into an enablement function.",
        "resume_emphasis": [
            "System uptime improvements",
            "Ticket resolution improvements (time, satisfaction)",
            "IT infrastructure modernization you led",
            "Security posture improvements with compliance context",
        ],
        "networking_angle": "Ask about their biggest internal IT frustration. The pain is always specific — listen for whether it's infrastructure, tooling, or support.",
        "interview_themes": [
            "ITSM maturity and ticket volumes",
            "Infrastructure (cloud vs on-prem) strategy",
            "Security and compliance requirements",
        ],
    },
    "healthcare": {
        "archetype": "Clinical Operations Stabilizer",
        "angle": "You keep patient care reliable when staffing is stretched. Position yourself as someone who holds clinical operations together without compromising quality or compliance.",
        "resume_emphasis": [
            "Patient throughput or wait-time improvements with metrics",
            "Staffing ratios you managed through volume changes",
            "Quality/compliance outcomes (HCAHPS, Joint Commission, CMS)",
            "Clinical protocols or workflows you standardized across units",
        ],
        "networking_angle": "Ask about their biggest staffing pressure — which units, which shifts, which credentials. The specificity tells you whether they need a clinical leader or an operations person with healthcare context.",
        "interview_themes": [
            "Staffing model and current vacancy pressure",
            "Quality and patient-safety metrics tracked",
            "Credentialing, licensing, and compliance workflows",
        ],
    },
    "hospitality": {
        "archetype": "Guest Experience Operator",
        "angle": "You make hotel and guest operations feel effortless to the guest. Position yourself as someone who scales service quality across properties without losing the human touch.",
        "resume_emphasis": [
            "Guest satisfaction scores (NPS, review scores) you improved with specific actions",
            "Multi-property or multi-shift standardization you implemented",
            "Service recovery and exception handling processes you built",
            "Occupancy or revenue-per-room improvements with operational changes",
        ],
        "networking_angle": "Ask about their review scores and biggest guest complaint themes. The specific complaints reveal whether they need service training, systems, or leadership.",
        "interview_themes": [
            "Guest feedback channels and response workflows",
            "Staff training and cross-shift consistency",
            "Peak-season staffing and scheduling approach",
        ],
    },
    "education": {
        "archetype": "Learning Outcomes Builder",
        "angle": "You connect instruction to measurable student progress. Position yourself as someone who makes curriculum execution consistent without losing pedagogy.",
        "resume_emphasis": [
            "Student outcome improvements with data (completion, proficiency, retention)",
            "Curriculum or program design with measurable adoption",
            "Instructor training or coaching programs you built",
            "Assessment and evaluation frameworks you implemented",
        ],
        "networking_angle": "Ask how they currently measure student outcomes — if the answer is fuzzy, that's where you add value.",
        "interview_themes": [
            "Student outcome measurement and benchmarking",
            "Curriculum delivery consistency across instructors or locations",
            "Program evaluation and iteration cadence",
        ],
    },
    "trades": {
        "archetype": "Field Service Reliability Lead",
        "angle": "You make on-site work predictable. Position yourself as someone who delivers quality craftsmanship while training apprentices and meeting schedule commitments.",
        "resume_emphasis": [
            "First-time-fix rates or rework reduction with metrics",
            "Safety record and incident reduction programs",
            "Apprentice or journeyman development you mentored",
            "Scope-to-completion reliability on complex projects",
        ],
        "networking_angle": "Ask about their callback rate and biggest scheduling constraint. The answer reveals whether they need craftspeople, coordinators, or supervisors.",
        "interview_themes": [
            "Scheduling, dispatching, and route optimization",
            "Quality control and inspection processes",
            "Training and certification pipeline",
        ],
    },
    "transportation": {
        "archetype": "Transit Operations Steadier",
        "angle": "You keep the schedule intact when things go sideways. Position yourself as someone who holds service reliability while managing crew, equipment, and exceptions.",
        "resume_emphasis": [
            "On-time performance improvements with operational changes",
            "Crew scheduling optimization with measurable results",
            "Safety and regulatory compliance achievements",
            "Disruption management and recovery processes you built",
        ],
        "networking_angle": "Ask about their on-time performance and biggest crew availability problem. The answer tells you if they need dispatchers, trainers, or scheduling systems.",
        "interview_themes": [
            "On-time performance tracking and recovery processes",
            "Crew scheduling and availability management",
            "Regulatory compliance and safety programs",
        ],
    },
    "food_service": {
        "archetype": "Kitchen Operations Steadier",
        "angle": "You turn kitchen chaos into consistent output. Position yourself as someone who holds food quality and ticket times when volume spikes.",
        "resume_emphasis": [
            "Ticket time or kitchen speed improvements with metrics",
            "Food safety and health inspection outcomes",
            "Menu engineering or cost-of-goods improvements",
            "Training and cross-training programs that stabilized crew turnover",
        ],
        "networking_angle": "Ask about their peak-hour ticket times and food cost. If either is volatile, that's where your operational discipline matters.",
        "interview_themes": [
            "Kitchen throughput and station standardization",
            "Food safety and compliance record",
            "Recipe adherence and menu execution consistency",
        ],
    },
}

# Default archetype for functions not in the map
_DEFAULT_ARCHETYPE = {
    "archetype": "Functional Specialist",
    "angle": "Position yourself around the specific outcomes this company needs based on their hiring pattern.",
    "resume_emphasis": [
        "Measurable outcomes in your functional area",
        "Systems or processes you built that scaled",
        "Cross-functional collaboration examples",
    ],
    "networking_angle": "Ask about their biggest challenge in this function. Listen for whether it's a people, process, or tools problem.",
    "interview_themes": [
        "Current team structure and growth plans",
        "Key metrics they track in this function",
        "Biggest constraint or bottleneck",
    ],
}


# ── Assertiveness calibration ────────────────────────────────────────

ASSERTIVENESS_LEVELS = {
    "high": {
        "level": "confident",
        "prefix": "Based on strong evidence, this company",
        "caveats": [],
    },
    "moderate": {
        "level": "directional",
        "prefix": "Evidence suggests this company likely",
        "caveats": [
            "This assessment is based on visible hiring patterns and may not reflect internal priorities.",
            "Validate this direction in early conversations before committing your positioning.",
        ],
    },
    "low": {
        "level": "exploratory",
        "prefix": "Early signals indicate this company may",
        "caveats": [
            "This is a directional hypothesis based on limited evidence.",
            "Use this as a starting point for discovery, not a definitive positioning.",
            "The company's actual priorities may differ significantly from what hiring patterns suggest.",
        ],
    },
}


# ── Do-not-overclaim rules ───────────────────────────────────────────

def _build_overclaim_flags(
    confidence_band: str,
    classified_roles: int,
    jds_extracted: int,
    top_share: float,
    unique_areas: int,
) -> list[str]:
    """Generate list of things the candidate should NOT claim."""
    flags = []

    if confidence_band != "high":
        flags.append(
            "Do not claim to know their internal pain with certainty. "
            "Frame it as 'based on what I see in your hiring patterns'."
        )

    if jds_extracted < 3:
        flags.append(
            "Do not reference specific job description language — "
            "we haven't confirmed what they're actually asking for in detail."
        )

    if classified_roles < 5:
        flags.append(
            "Do not claim this is their 'biggest' challenge. "
            "Small sample size means other functions may be equally important."
        )

    if top_share < 0.4:
        flags.append(
            "Do not position as if there's a single dominant need. "
            "Hiring is spread across multiple functions."
        )

    if unique_areas >= 5:
        flags.append(
            "This company hires broadly. Avoid narrow positioning — "
            "keep your angle flexible until you learn more."
        )

    return flags


# ── Evidence summary builder ─────────────────────────────────────────

def _build_evidence_summary(
    classified_roles: int,
    jds_extracted: int,
    total_roles: int,
    top_function: str,
    top_count: int,
    top_share: float,
    unique_areas: int,
    supporting_functions: list[str],
) -> str:
    """Build human-readable evidence summary."""
    parts = []

    parts.append(
        f"We analyzed {total_roles} visible job postings and classified "
        f"{classified_roles} into {unique_areas} functional area(s)."
    )

    if top_function:
        fn_label = top_function.replace("_", " ").title()
        parts.append(
            f"The dominant hiring area is {fn_label} "
            f"({top_count} roles, {top_share:.0%} of classified)."
        )

    if jds_extracted > 0:
        parts.append(
            f"{jds_extracted} job descriptions were analyzed for deeper insight."
        )

    if supporting_functions:
        labels = [f.replace("_", " ").title() for f in supporting_functions[:2]]
        parts.append(
            f"Supporting hiring activity in: {', '.join(labels)}."
        )

    return " ".join(parts)


# ── Main engine ──────────────────────────────────────────────────────

class PositioningEngine:
    """Translates company diagnostics into candidate positioning guidance."""

    def generate(
        self,
        company_id: UUID,
        db: Session,
    ) -> PositioningOutput:
        """Generate positioning output for a company.

        Returns PositioningOutput with eligible=False if evidence is insufficient.
        """
        from app.models.company import Company

        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return PositioningOutput(
                company_name="",
                company_domain="",
                company_id=str(company_id),
                eligible=False,
                confidence_band="low",
                gate_passed="none",
                evidence_caveats=["Company not found."],
            )

        # Step 1: Evaluate
        ev = evaluation_engine.evaluate(company_id=company_id, db=db)
        kpis = ev.get("kpis", {})
        ds = ev.get("diagnostic_state", "insufficient_evidence")

        # Step 2: Get role data
        roles = (
            db.query(CompanyJobRole)
            .filter(CompanyJobRole.company_id == company_id)
            .all()
        )
        function_counts = {}
        for r in roles:
            area = r.functional_area
            if area and area not in ("junk", "unknown"):
                function_counts[area] = function_counts.get(area, 0) + 1

        total_classified = sum(function_counts.values())
        jds_extracted = sum(1 for r in roles if r.role_description)
        unique_areas = len(function_counts)

        sorted_functions = sorted(
            function_counts.items(), key=lambda x: x[1], reverse=True
        )
        top_function = sorted_functions[0][0] if sorted_functions else ""
        top_count = sorted_functions[0][1] if sorted_functions else 0
        top_share = top_count / total_classified if total_classified > 0 else 0
        supporting = [f[0] for f in sorted_functions[1:3]]

        # Step 3: Check eligibility
        eligibility = check_eligibility(
            diagnostic_state=ds,
            pain_clarity=kpis.get("pain_clarity", "low"),
            function_concentration=kpis.get("function_concentration", "low"),
            positioning_readiness=kpis.get("positioning_readiness", "low"),
            classified_roles=total_classified,
            jds_extracted=jds_extracted,
        )

        output = PositioningOutput(
            company_name=company.name,
            company_domain=company.domain or "",
            company_id=str(company_id),
            eligible=eligibility.eligible,
            confidence_band=eligibility.confidence_band,
            gate_passed=eligibility.gate_passed,
            generated_from_ds=ds,
            evidence_depth={
                "total_roles": len(roles),
                "classified_roles": total_classified,
                "jds_extracted": jds_extracted,
                "unique_areas": unique_areas,
                "top_function": top_function,
                "top_share": round(top_share, 3),
            },
        )

        if not eligibility.eligible:
            output.evidence_caveats = [eligibility.reason]
            return output

        # Step 4: Build positioning
        macro = get_macro_family(top_function)
        archetype_data = CANDIDATE_ARCHETYPES.get(
            top_function, _DEFAULT_ARCHETYPE
        )
        assertiveness = ASSERTIVENESS_LEVELS[eligibility.confidence_band]

        # Pain summary — modulated by confidence
        from app.services.function_inference_engine import FunctionInferenceEngine
        pain_data = FunctionInferenceEngine.PAIN_INFERENCE.get(top_function, {})

        pain_prefix = assertiveness["prefix"]
        raw_pain = pain_data.get("main_pain", "shows hiring activity that suggests operational pressure.")
        output.pain_summary = f"{pain_prefix} {raw_pain[0].lower()}{raw_pain[1:]}" if raw_pain else ""

        output.evidence_summary = _build_evidence_summary(
            classified_roles=total_classified,
            jds_extracted=jds_extracted,
            total_roles=len(roles),
            top_function=top_function,
            top_count=top_count,
            top_share=top_share,
            unique_areas=unique_areas,
            supporting_functions=supporting,
        )

        output.likely_business_need = pain_data.get("what_need", "")
        output.dominant_function = top_function
        output.macro_family = macro
        output.supporting_functions = supporting

        output.candidate_archetype = archetype_data["archetype"]
        output.positioning_angle = archetype_data["angle"]
        output.resume_emphasis = archetype_data["resume_emphasis"]
        output.networking_angle = archetype_data["networking_angle"]
        output.interview_themes = archetype_data.get("interview_themes", [])

        output.assertiveness_level = assertiveness["level"]
        output.evidence_caveats = list(assertiveness["caveats"])

        output.do_not_overclaim = _build_overclaim_flags(
            confidence_band=eligibility.confidence_band,
            classified_roles=total_classified,
            jds_extracted=jds_extracted,
            top_share=top_share,
            unique_areas=unique_areas,
        )

        return output


positioning_engine = PositioningEngine()

from app.models.company import Company
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.models.opportunity_hypothesis import OpportunityHypothesis
from app.models.collection_run import CollectionRun
from app.services.evidence_threshold_engine import evidence_threshold_engine
from app.services.business_read_engine import business_read_engine
from app.services.company_evaluation import company_evaluation_engine

from app.schemas.score_delta import ScoreDeltaResult, TrendDirection
from app.schemas.signal_velocity import SignalVelocityResult
from app.schemas.temporal_diagnostic import (
    TemporalDiagnosticResult,
    TemporalDiagnosticState,
    TemporalConfidence,
    EvidenceStrength,
)


class FinalVerdictEngine:
    """Generates the final business verdicts for each company with anti-hallucination logic.

    Uses the canonical CompanyEvaluationEngine for all KPI and diagnostic computations.
    BusinessReadEngine and EvidenceThresholdEngine are still called for backward-compatible
    API fields, but they now delegate to the same canonical source.

    Temporal enrichment: when temporal data is available and confidence is high enough,
    the verdict includes temporal_status, trend_direction, and product wording that
    reflects how friction is changing over time. Static verdict fields are preserved
    unchanged — temporal fields are additive.
    """

    OPERATING_PAIN_MAP = {
        "reporting_fragmentation": {
            "main_pain": "The company likely struggles to maintain clear visibility across data and metrics as teams grow.",
            "where_pain_lives": "Data, analytics, and cross-functional reporting.",
            "what_the_company_needs": "Someone who can structure reporting, build metrics, and turn data into clear business decisions.",
            "recommended_positioning": "Position yourself as someone who can improve cross-functional reporting clarity and help decision-makers use cleaner, more actionable data.",
        },
        "scaling_strain": {
            "main_pain": "The company faces coordination challenges as multiple teams grow and operate in parallel.",
            "where_pain_lives": "Operations, team coordination, and cross-functional alignment.",
            "what_the_company_needs": "Someone who can build coordination frameworks and enable clear communication across growing teams.",
            "recommended_positioning": "Position yourself as someone who can create alignment and process clarity in fast-growing environments.",
        },
        "tooling_inconsistency": {
            "main_pain": "The company deals with fragmented tools that do not communicate well with each other.",
            "where_pain_lives": "Tooling, infrastructure, and workflow automation.",
            "what_the_company_needs": "Someone who can consolidate tools and create unified workflows.",
            "recommended_positioning": "Position yourself as someone who can evaluate, consolidate, and streamline tool stacks.",
        },
        "process_inefficiency": {
            "main_pain": "The company relies on manual or inefficient processes that slow down execution.",
            "where_pain_lives": "Operations and business processes.",
            "what_the_company_needs": "Someone who can streamline processes and identify bottlenecks.",
            "recommended_positioning": "Position yourself as someone who can create efficiency and remove operational bottlenecks.",
        },
        "customer_experience_friction": {
            "main_pain": "Customers may experience confusion or frustration when interacting with the company.",
            "where_pain_lives": "Customer success, user experience, and support operations.",
            "what_the_company_needs": "Someone who can map and improve customer touchpoints.",
            "recommended_positioning": "Position yourself as someone who can create consistent customer journey experiences.",
        },
    }

    INTERMEDIARY_PAIN_MAP = {
        "reporting_fragmentation": {
            "main_pain": "The company may struggle to measure and report on placement success and recruiter performance.",
            "where_pain_lives": "Recruiting analytics, placement metrics, and performance reporting.",
            "what_the_company_needs": "Someone who can build recruiting performance metrics and data visibility.",
            "recommended_positioning": "Position yourself as someone who can create clear recruiting KPIs and placement analytics.",
        },
        "scaling_strain": {
            "main_pain": "The company faces challenges in scaling recruiting operations and maintaining placement quality.",
            "where_pain_lives": "Recruiting operations and candidate flow management.",
            "what_the_company_needs": "Someone who can build scalable recruiting workflows and quality controls.",
            "recommended_positioning": "Position yourself as someone who can create efficient recruiting operations at scale.",
        },
        "tooling_inconsistency": {
            "main_pain": "The company uses fragmented tools that hinder candidate matching and workflow efficiency.",
            "where_pain_lives": "Recruiting software stack and ATS integration.",
            "what_the_company_needs": "Someone who can unify recruiting tools and improve candidate workflow.",
            "recommended_positioning": "Position yourself as someone who can optimize recruiting tech stack and integrations.",
        },
        "process_inefficiency": {
            "main_pain": "The company has manual processes that slow down candidate placement and hiring.",
            "where_pain_lives": "Candidate screening, placement workflow, and requisition processing.",
            "what_the_company_needs": "Someone who can streamline recruiting operations and eliminate bottlenecks.",
            "recommended_positioning": "Position yourself as someone who can accelerate recruiting workflows.",
        },
        "customer_experience_friction": {
            "main_pain": "Candidates or employers may have poor experiences with the company's hiring or placement process.",
            "where_pain_lives": "Candidate experience, employer relationships, and placement communication.",
            "what_the_company_needs": "Someone who can improve candidate journey and client communication.",
            "recommended_positioning": "Position yourself as someone who can enhance recruiting experience quality.",
        },
    }

    def generate(
        self,
        company: Company,
        signals: list[CompanySignal],
        score: FrictionScore | None,
        hypothesis: OpportunityHypothesis | None,
        company_type: str = "unclear",
        collection_runs: list[CollectionRun] | None = None,
        db=None,
        temporal_diagnostic: TemporalDiagnosticResult | None = None,
        score_delta: ScoreDeltaResult | None = None,
        velocity: SignalVelocityResult | None = None,
    ) -> dict:
        """Generate final verdict based on all available data with anti-hallucination.

        Uses CompanyEvaluationEngine (canonical) for KPIs and diagnostic state.
        Falls back to EvidenceThresholdEngine and BusinessReadEngine for
        backward-compatible verdict fields.

        Temporal enrichment is additive: existing verdict fields are preserved,
        and temporal fields are appended when data is available.
        """

        # Get canonical evaluation
        evaluation = company_evaluation_engine.evaluate(
            company_id=company.id,
            db=db,
            signals=signals,
        )

        kpis = evaluation["kpis"]
        diagnostic_state = evaluation["diagnostic_state"]
        hiring_pressure = kpis["hiring_pressure"]
        pain_clarity = kpis["pain_clarity"]
        allow_specific_pain = evaluation["allow_specific_pain_output"]

        # Get business read for backward-compatible fields
        business_read = business_read_engine.compute_reading(
            company_id=company.id,
            db=db,
            signals=signals,
        )

        # Get evidence for backward-compatible fields
        evidence = evidence_threshold_engine.evaluate_evidence(
            signals=signals,
            score=score,
            collection_runs=collection_runs,
            company_id=company.id,
            db=db,
        )

        # Compute temporal enrichment (additive, does not alter static verdict)
        temporal = self._enrich_temporal(
            temporal_diagnostic=temporal_diagnostic,
            score_delta=score_delta,
            velocity=velocity,
        )

        # Rule C: If hiring pressure is high but pain clarity is low,
        # do NOT produce definitive pain
        if hiring_pressure == "high" and pain_clarity == "low":
            return {
                "verdict_type": "preliminary",
                "hiring_pressure": hiring_pressure,
                "pain_clarity": pain_clarity,
                "diagnosis_status": diagnostic_state,
                "business_read_summary": business_read.get("business_read_summary"),
                "confidence": evidence.get("confidence", "low"),
                "main_pain": None,
                "where_pain_lives": None,
                "what_the_company_needs": None,
                "recommended_positioning": None,
                "what_we_know": business_read.get("business_read_summary"),
                "what_we_do_not_know_yet": "We do not yet know which specific internal function is under the most pressure.",
                "next_best_step": business_read.get("next_best_step"),
                **temporal,
            }

        # Pain clarity is moderate or high - can generate verdict
        if pain_clarity in ["moderate", "high"]:
            if not allow_specific_pain:
                return {
                    "verdict_type": "preliminary",
                    "hiring_pressure": hiring_pressure,
                    "pain_clarity": pain_clarity,
                    "diagnosis_status": diagnostic_state,
                    "business_read_summary": business_read.get("business_read_summary"),
                    "confidence": evidence.get("confidence", "low"),
                    "main_pain": None,
                    "where_pain_lives": None,
                    "what_the_company_needs": None,
                    "recommended_positioning": None,
                    "what_we_know": "We have some evidence of hiring activity but need more to isolate specific pain.",
                    "what_we_do_not_know_yet": "The specific internal pain has not been clearly identified yet.",
                    "next_best_step": "Collect more role-level evidence to confirm the pain pattern.",
                    **temporal,
                }

            # Evidence is strong enough - generate final verdict
            verdict = self._generate_final_verdict(
                company=company,
                signals=signals,
                score=score,
                hypothesis=hypothesis,
                company_type=company_type,
                evidence=evidence,
            )

            verdict["hiring_pressure"] = hiring_pressure
            verdict["pain_clarity"] = pain_clarity
            verdict["diagnosis_status"] = diagnostic_state
            verdict["business_read_summary"] = business_read.get("business_read_summary")

            # If temporal confidence is high and changes the dominant friction,
            # update the pain wording. Otherwise, just append temporal fields.
            if temporal_diagnostic and temporal_diagnostic.confidence in (
                TemporalConfidence.HIGH, TemporalConfidence.MODERATE,
            ):
                verdict = self._apply_temporal_to_verdict(verdict, temporal_diagnostic)

            verdict.update(temporal)
            return verdict

        # Default: low hiring pressure or unclear
        return {
            "verdict_type": "preliminary",
            "hiring_pressure": hiring_pressure,
            "pain_clarity": pain_clarity,
            "diagnosis_status": diagnostic_state,
            "business_read_summary": business_read.get("business_read_summary") or "Not enough evidence to determine hiring pressure or pain clarity.",
            "confidence": evidence.get("confidence", "low"),
            "main_pain": None,
            "where_pain_lives": None,
            "what_the_company_needs": None,
            "recommended_positioning": None,
            "what_we_know": "We don't have enough data to analyze yet.",
            "what_we_do_not_know_yet": "Need more signals to determine company status.",
            "next_best_step": "Run collection to gather more signals.",
            **temporal,
        }

    def _generate_final_verdict(
        self,
        company: Company,
        signals: list[CompanySignal],
        score: FrictionScore | None,
        hypothesis: OpportunityHypothesis | None,
        company_type: str,
        evidence: dict,
    ) -> dict:
        """Generate full final verdict when evidence is strong.

        Uses normalized_score from the scoring breakdown to determine
        dominant friction type, which corrects for structural category bias.
        Falls back to hypothesis.friction_type, then score.dominant_friction_type,
        then signal-based inference.
        """

        dominant_friction = None
        if hypothesis and hypothesis.friction_type:
            dominant_friction = hypothesis.friction_type
        elif score and score.dominant_friction_type:
            # v2 scoring may return "no_signal" when no rules matched
            if score.dominant_friction_type != "no_signal":
                dominant_friction = score.dominant_friction_type

        if not dominant_friction:
            dominant_friction = self._infer_friction_from_signals(signals)

        if not dominant_friction:
            dominant_friction = "scaling_strain"

        pain_map = self._get_pain_map(company_type)

        verdict = pain_map.get(dominant_friction, self._default_verdict(company_type))

        return {
            "verdict_type": "final",
            "evidence_quality": evidence.get("evidence_quality", "medium"),
            "confidence": evidence.get("confidence", "medium"),
            "hiring_pressure": None,
            "pain_clarity": None,
            "diagnosis_status": None,
            "business_read_summary": None,
            "main_pain": verdict.get("main_pain"),
            "where_pain_lives": verdict.get("where_pain_lives"),
            "what_the_company_needs": verdict.get("what_the_company_needs"),
            "recommended_positioning": verdict.get("recommended_positioning"),
            "what_we_know": "We have enough evidence to identify the internal pain.",
            "what_we_do_not_know_yet": None,
            "next_best_step": "Use this insight for targeted positioning.",
        }

    def _infer_friction_from_signals(self, signals: list[CompanySignal]) -> str | None:
        """Infer dominant friction from signals when not available from score/hypothesis."""
        if not signals:
            return None

        all_text = " ".join([s.signal_text.lower() for s in signals]).lower()

        if any(
            k in all_text
            for k in [
                "report",
                "metric",
                "analytics",
                "data",
                "dashboard",
                "bi",
                "insight",
            ]
        ):
            return "reporting_fragmentation"
        if any(
            k in all_text
            for k in ["tool", "software", "platform", "system", "integration"]
        ):
            return "tooling_inconsistency"
        if any(
            k in all_text
            for k in ["process", "manual", "workflow", "efficiency", "bottleneck"]
        ):
            return "process_inefficiency"
        if any(
            k in all_text
            for k in ["growth", "scale", "expand", "hire", "team", "hiring"]
        ):
            return "scaling_strain"
        if any(
            k in all_text
            for k in ["customer", "client", "user", "experience", "support"]
        ):
            return "customer_experience_friction"

        return None

    def _get_pain_map(self, company_type: str) -> dict:
        """Get pain map based on company type."""
        if company_type == "job_market_intermediary":
            return self.INTERMEDIARY_PAIN_MAP
        return self.OPERATING_PAIN_MAP

    def _default_verdict(self, company_type: str) -> dict:
        """Return default verdict when friction is unclear but evidence is reasonable."""
        if company_type == "job_market_intermediary":
            return {
                "main_pain": "The company appears to be scaling recruiting operations, which may create workflow and efficiency challenges.",
                "where_pain_lives": "Recruiting operations and candidate flow management.",
                "what_the_company_needs": "Someone who can optimize recruiting workflows and improve placement efficiency.",
                "recommended_positioning": "Position yourself as someone who can improve recruiting operations and workflow efficiency.",
            }

        return {
            "main_pain": "The company appears to be experiencing growth-related operational challenges.",
            "where_pain_lives": "Operations, coordination, and cross-functional alignment.",
            "what_the_company_needs": "Someone who can improve coordination and process clarity as the company scales.",
            "recommended_positioning": "Position yourself as someone who can help the company scale more efficiently.",
        }

    # ── Temporal enrichment ────────────────────────────────────────────────

    def _enrich_temporal(
        self,
        temporal_diagnostic: TemporalDiagnosticResult | None,
        score_delta: ScoreDeltaResult | None,
        velocity: SignalVelocityResult | None,
    ) -> dict:
        """Build additive temporal fields for the verdict.

        Returns a dict that can be spread into any verdict path. If temporal
        data is insufficient, returns minimal placeholder fields.
        """
        if temporal_diagnostic is None:
            return {
                "temporal_status": None,
                "trend_direction": None,
                "top_accelerating_pain": None,
                "top_declining_pain": None,
                "temporal_confidence": None,
                "temporal_reasoning_trace": None,
            }

        state = temporal_diagnostic.temporal_state

        # Derive trend direction from temporal state.
        trend_map = {
            TemporalDiagnosticState.INSUFFICIENT: None,
            TemporalDiagnosticState.STABLE_LOW: "stable",
            TemporalDiagnosticState.STABLE_ELEVATED: "stable",
            TemporalDiagnosticState.EMERGING_PAIN: "worsening",
            TemporalDiagnosticState.ACCELERATING_PAIN: "worsening",
            TemporalDiagnosticState.DECLINING_PAIN: "improving",
            TemporalDiagnosticState.VOLATILE: "volatile",
        }
        trend_direction = trend_map.get(state)

        # Identify top accelerating and declining categories.
        # Prefer score_delta (category-level detail), fall back to
        # temporal_diagnostic.top_changing_category when delta not available.
        top_accelerating = None
        top_declining = None
        if score_delta and score_delta.category_deltas:
            for cd in score_delta.category_deltas:
                if cd.delta > 0:
                    if top_accelerating is None or cd.delta > top_accelerating.delta:
                        top_accelerating = cd
                elif cd.delta < 0:
                    if top_declining is None or cd.delta < top_declining.delta:
                        top_declining = cd
        elif temporal_diagnostic.top_changing_category:
            tc = temporal_diagnostic.top_changing_category
            if tc.delta > 0:
                top_accelerating = tc
            elif tc.delta < 0:
                top_declining = tc

        return {
            "temporal_status": state.value,
            "trend_direction": trend_direction,
            "top_accelerating_pain": (
                {"category": top_accelerating.category, "delta": top_accelerating.delta}
                if top_accelerating else None
            ),
            "top_declining_pain": (
                {"category": top_declining.category, "delta": top_declining.delta}
                if top_declining else None
            ),
            "temporal_confidence": temporal_diagnostic.confidence.value,
            "temporal_reasoning_trace": [
                {"step": s.step, "condition": s.condition, "result": s.result}
                for s in temporal_diagnostic.reasoning_trace
            ],
        }

    def _apply_temporal_to_verdict(
        self,
        verdict: dict,
        temporal_diagnostic: TemporalDiagnosticResult,
    ) -> dict:
        """Optionally enhance verdict wording when temporal confidence is high.

        Does NOT change static diagnosis fields — only adds temporal context
        to what_we_know and recommended_positioning when the trend is clear.
        """
        state = temporal_diagnostic.temporal_state

        if state == TemporalDiagnosticState.INSUFFICIENT:
            return verdict

        top_cat = temporal_diagnostic.top_changing_category
        cat_label = (
            top_cat.category.replace("_", " ").title()
            if top_cat else "operations"
        )

        if state == TemporalDiagnosticState.ACCELERATING_PAIN:
            verdict["what_we_know"] = (
                f"Friction appears to be accelerating in {cat_label} workflows."
            )
        elif state == TemporalDiagnosticState.EMERGING_PAIN:
            verdict["what_we_know"] = (
                f"Friction is beginning to emerge in {cat_label} workflows."
            )
        elif state == TemporalDiagnosticState.DECLINING_PAIN:
            verdict["what_we_know"] = (
                f"Friction in {cat_label} workflows appears to be easing."
            )
        elif state in (TemporalDiagnosticState.STABLE_LOW, TemporalDiagnosticState.STABLE_ELEVATED):
            verdict["what_we_know"] = (
                "Signals are stable; no material temporal shift detected."
            )
        elif state == TemporalDiagnosticState.VOLATILE:
            verdict["what_we_know"] = (
                f"Friction direction is volatile — {cat_label} signals are fluctuating."
            )

        return verdict


final_verdict_engine = FinalVerdictEngine()
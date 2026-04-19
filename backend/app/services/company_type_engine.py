from app.models.company_signal import CompanySignal


class CompanyTypeEngine:
    """Determines whether a company is an operating company or job market intermediary."""

    # Keywords that strongly indicate job market intermediary (need strong evidence)
    JOB_INTERMEDIARY_KEYWORDS = [
        "staffing",
        "recruiting",
        "recruiters",
        "talent solutions",
        "find jobs",
        "employers",
        "job seekers",
        "placements",
        "candidates",
        "hire talent",
        "workforce solutions",
        "recruiting services",
        "staffing agency",
        "job board",
        "hiring marketplace",
        "talent marketplace",
        "placement services",
        "job search",
        "resume",
        "headhunter",
        "executive search",
        "temporary staffing",
        "temp agency",
        "employment agency",
        "career services",
        "hiring platform",
        "staffing firm",
        "recruiting firm",
        "talent firm",
    ]

    # Keywords that indicate operating company
    OPERATING_COMPANY_KEYWORDS = [
        "products",
        "customers",
        "stores",
        "logistics",
        "supply chain",
        "retail",
        "manufacturing",
        "services",
        "shipping",
        "platform",
        "operations",
        "brand",
        "commerce",
        "product development",
        "distribution",
        "software",
        "saas",
        "enterprise",
        "solutions",
        "healthcare",
        "finance",
        "banking",
        "insurance",
        "consumer",
        "wholesale",
        "technology",
        "app",
        "digital",
        "cloud",
        "growth",
        "scaling",
        "expansion",
        "hiring",
        "open roles",
        "analytics",
        "data",
        "bi",
        "reporting",
        "metrics",
    ]

    def analyze(
        self,
        signals: list[CompanySignal],
        signal_count: int = 0,
        has_hypothesis: bool = False,
    ) -> dict:
        """Analyze signals to determine company type with confidence level."""

        if not signals:
            return self._build_result(
                company_type="unclear",
                analysis_mode="unclear_analysis",
                target_fit="unclear",
                confidence="low",
                reason="No signals available to determine company type.",
            )

        all_text = " ".join(
            [s.signal_text.lower() + " " + s.signal_type.lower() for s in signals]
        ).lower()

        # Count keyword matches
        intermediary_matches = [
            kw for kw in self.JOB_INTERMEDIARY_KEYWORDS if kw in all_text
        ]
        operating_matches = [
            kw for kw in self.OPERATING_COMPANY_KEYWORDS if kw in all_text
        ]

        intermediary_score = len(set(intermediary_matches))
        operating_score = len(set(operating_matches))

        # Check for strong evidence
        has_strong_evidence = signal_count >= 3 or has_hypothesis

        # Decision logic
        # Rule A: Strong intermediary indicators -> job_market_intermediary
        if intermediary_score >= 2:
            return self._build_result(
                company_type="job_market_intermediary",
                analysis_mode="recruiting_marketplace_analysis",
                target_fit="secondary",
                confidence="high" if intermediary_score >= 3 else "medium",
                reason=f"Strong indicators of recruiting/staffing: {', '.join(intermediary_matches[:3])}. This company appears to be a job-market intermediary.",
            )

        # Rule B: Strong operating company indicators -> operating_company
        if operating_score >= 2:
            return self._build_result(
                company_type="operating_company",
                analysis_mode="direct_employer_analysis",
                target_fit="primary",
                confidence="high" if operating_score >= 3 else "medium",
                reason=f"Signals indicate internal operations, growth, and business functions: {', '.join(operating_matches[:3])}. This appears to be an operating company.",
            )

        # Rule C: Moderate intermediary but strong evidence -> likely intermediary
        if intermediary_score == 1 and operating_score == 0:
            return self._build_result(
                company_type="job_market_intermediary",
                analysis_mode="recruiting_marketplace_analysis",
                target_fit="secondary",
                confidence="medium",
                reason=f"Some indicators suggest recruiting or staffing: {intermediary_matches[0] if intermediary_matches else 'recruiting-related signals'}. Likely a job-market intermediary.",
            )

        # Rule D: Moderate operating indicators with strong evidence -> likely operating_company
        if operating_score == 1 and has_strong_evidence:
            return self._build_result(
                company_type="operating_company",
                analysis_mode="direct_employer_analysis",
                target_fit="primary",
                confidence="medium",
                reason="Signals suggest internal scaling, growth, or business operations. No strong indicators of staffing/recruiting business model.",
            )

        # Rule E: Single weak signal but strong overall evidence
        if has_strong_evidence and (signal_count >= 5 or has_hypothesis):
            return self._build_result(
                company_type="operating_company",
                analysis_mode="direct_employer_analysis",
                target_fit="primary",
                confidence="medium",
                reason="Strong analytical evidence (signals + hypothesis) suggests an operating company. No staffing/recruiting indicators detected.",
            )

        # Rule F: Some operating indicators but no strong evidence
        if operating_score >= 1:
            return self._build_result(
                company_type="operating_company",
                analysis_mode="direct_employer_analysis",
                target_fit="primary",
                confidence="low",
                reason="Some operational indicators detected. Likely an operating company rather than a recruiting intermediary.",
            )

        # Rule G: Intermediary with weak signal
        if intermediary_score == 1:
            return self._build_result(
                company_type="job_market_intermediary",
                analysis_mode="recruiting_marketplace_analysis",
                target_fit="secondary",
                confidence="low",
                reason="Weak indicators suggest this may be a recruiting/staffing company.",
            )

        # Truly unclear - no meaningful signals
        return self._build_result(
            company_type="unclear",
            analysis_mode="unclear_analysis",
            target_fit="unclear",
            confidence="low",
            reason="Insufficient evidence to determine company type. Need more signals.",
        )

    def _build_result(
        self,
        company_type: str,
        analysis_mode: str,
        target_fit: str,
        confidence: str,
        reason: str,
    ) -> dict:
        return {
            "company_type": company_type,
            "analysis_mode": analysis_mode,
            "target_fit": target_fit,
            "company_type_confidence": confidence,
            "company_type_reason": reason,
        }


company_type_engine = CompanyTypeEngine()

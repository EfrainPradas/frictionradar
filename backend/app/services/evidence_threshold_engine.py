from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.models.collection_run import CollectionRun


class EvidenceThresholdEngine:
    """Determines evidence quality and thresholds to prevent hallucination."""

    FUNCTION_SIGNAL_KEYWORDS = {
        "data": [
            "analytics",
            "data",
            "metric",
            "dashboard",
            "bi",
            "business intelligence",
            "reporting",
            " insights",
            "visualization",
        ],
        "operations": [
            "process",
            "workflow",
            "efficiency",
            "coordination",
            "operations",
            "logistics",
            "supply chain",
        ],
        "recruiting": [
            "recruit",
            "talent",
            "hire",
            "candidate",
            "placement",
            "staffing",
            "employer",
            "job seeker",
        ],
        "customer": ["customer", "client", "user", "experience", "support", "success"],
    }

    GENERIC_SIGNAL_KEYWORDS = [
        "page found",
        "homepage",
        "careers page",
        "exists",
        "found",
        "detected",
    ]

    def evaluate_evidence(
        self,
        signals: list[CompanySignal],
        score: FrictionScore | None,
        collection_runs: list[CollectionRun] | None,
    ) -> dict:
        """Evaluate evidence quality and determine thresholds."""

        unique_signals = self._get_unique_signals(signals)
        unique_signal_count = len(unique_signals)
        total_signal_count = len(signals) if signals else 0
        source_types = self._get_source_types(signals)
        source_type_count = len(source_types)

        function_specific_signals = self._detect_function_specific_signals(signals)
        function_type = function_specific_signals.get("function_type")

        friction_score_value = (
            score.total_score if score and score.total_score is not None else 0.0
        )

        # Count dynamic careers signals for better evidence
        dynamic_signals = self._count_dynamic_careers_signals(signals)
        visible_job_count = dynamic_signals.get("visible_job_count", 0)
        visible_categories_count = dynamic_signals.get("visible_categories_count", 0)
        has_high_volume = dynamic_signals.get("has_high_volume", False)

        signal_diversity = self._calculate_signal_diversity(signals)
        has_repeated_signals = self._has_repeated_signals(collection_runs, signals)

        evidence_quality = self._determine_evidence_quality(
            unique_signal_count=unique_signal_count,
            source_type_count=source_type_count,
            friction_score_value=friction_score_value,
            function_type=function_type,
            signal_diversity=signal_diversity,
            has_repeated_signals=has_repeated_signals,
            visible_job_count=visible_job_count,
            visible_categories_count=visible_categories_count,
            has_high_volume=has_high_volume,
        )

        confidence = self._calculate_confidence(
            evidence_quality=evidence_quality,
            unique_signal_count=unique_signal_count,
            source_type_count=source_type_count,
            function_type=function_type,
            friction_score_value=friction_score_value,
            signal_diversity=signal_diversity,
        )

        is_strong_enough = evidence_quality in ["high", "medium"]

        return {
            "evidence_quality": evidence_quality,
            "confidence": confidence,
            "is_strong_enough": is_strong_enough,
            "unique_signal_count": unique_signal_count,
            "total_signal_count": total_signal_count,
            "source_type_count": source_type_count,
            "friction_score": friction_score_value,
            "function_type": function_type,
            "signal_diversity": signal_diversity,
            "has_repeated_signals": has_repeated_signals,
            "function_specific_signals": function_specific_signals,
            "visible_job_count": visible_job_count,
            "visible_categories_count": visible_categories_count,
            "has_high_volume": has_high_volume,
        }

    def _get_unique_signals(self, signals: list[CompanySignal]) -> list[str]:
        """Get unique signal texts to avoid duplicates."""
        if not signals:
            return []
        unique_texts = set()
        unique = []
        for s in signals:
            text = s.signal_text.strip().lower()
            if text and text not in unique_texts:
                unique_texts.add(text)
                unique.append(s.signal_text)
        return unique

    def _get_source_types(self, signals: list[CompanySignal]) -> set:
        """Get unique source types."""
        if not signals:
            return set()
        return set(s.source_type for s in signals if s.source_type)

    def _count_dynamic_careers_signals(self, signals: list[CompanySignal]) -> dict:
        """Count dynamic careers evidence signals."""
        if not signals:
            return {
                "visible_job_count": 0,
                "visible_categories_count": 0,
                "has_high_volume": False,
            }

        visible_job_count = 0
        visible_categories = set()
        has_high_volume = False

        for s in signals:
            signal_type = s.signal_type or ""

            if signal_type in ["job_cards_visible_detected", "job_links_extracted"]:
                try:
                    visible_job_count += int(s.numeric_value or 0)
                except:
                    visible_job_count += 1

            if signal_type == "high_open_positions_count_detected":
                has_high_volume = True

            # Count category-specific signals
            if "_hiring_detected" in signal_type:
                visible_categories.add(signal_type.replace("_hiring_detected", ""))

        return {
            "visible_job_count": visible_job_count,
            "visible_categories_count": len(visible_categories),
            "has_high_volume": has_high_volume,
        }

    def _detect_function_specific_signals(self, signals: list[CompanySignal]) -> dict:
        """Detect if signals contain function-specific evidence."""
        if not signals:
            return {
                "has_function_specific": False,
                "function_type": None,
                "details": [],
            }

        all_text = " ".join([s.signal_text.lower() for s in signals])

        function_counts = {func: 0 for func in self.FUNCTION_SIGNAL_KEYWORDS}
        function_details = {func: [] for func in self.FUNCTION_SIGNAL_KEYWORDS}

        for func, keywords in self.FUNCTION_SIGNAL_KEYWORDS.items():
            for keyword in keywords:
                if keyword in all_text:
                    function_counts[func] += 1
                    function_details[func].append(keyword)

        detected_function = max(function_counts, key=function_counts.get)
        count = function_counts.get(detected_function, 0)

        if count >= 2:
            return {
                "has_function_specific": True,
                "function_type": detected_function,
                "details": function_details[detected_function],
                "confidence": "high" if count >= 4 else "medium",
            }

        return {
            "has_function_specific": False,
            "function_type": None,
            "details": [],
            "confidence": None,
        }

    def _calculate_signal_diversity(self, signals: list[CompanySignal]) -> str:
        """Calculate signal diversity (high/medium/low)."""
        if not signals:
            return "none"

        unique_types = set(s.signal_type for s in signals if s.signal_type)
        type_count = len(unique_types)

        if type_count >= 4:
            return "high"
        if type_count >= 2:
            return "medium"
        return "low"

    def _has_repeated_signals(
        self, collection_runs: list[CollectionRun] | None, signals: list[CompanySignal]
    ) -> bool:
        """Check if multiple runs found only the same signals."""
        if not collection_runs or len(collection_runs) < 2:
            return False

        if not signals:
            return False

        unique_texts = set(s.signal_text.strip().lower() for s in signals)
        return len(unique_texts) <= 2

    def _determine_evidence_quality(
        self,
        unique_signal_count: int,
        source_type_count: int,
        friction_score_value: float,
        function_type: str | None,
        signal_diversity: str,
        has_repeated_signals: bool,
        visible_job_count: int = 0,
        visible_categories_count: int = 0,
        has_high_volume: bool = False,
    ) -> str:
        """Determine overall evidence quality."""
        high_evidence_indicators = 0

        if unique_signal_count >= 4:
            high_evidence_indicators += 1
        if source_type_count >= 2:
            high_evidence_indicators += 1
        if friction_score_value > 0:
            high_evidence_indicators += 1
        if function_type:
            high_evidence_indicators += 1

        # Bonus for dynamic careers evidence
        if visible_job_count >= 10:
            high_evidence_indicators += 1
        if visible_categories_count >= 2:
            high_evidence_indicators += 1
        if has_high_volume:
            high_evidence_indicators += 1

        weak_evidence_indicators = 0

        if unique_signal_count <= 2:
            weak_evidence_indicators += 1
        if source_type_count <= 1:
            weak_evidence_indicators += 1
        if friction_score_value == 0:
            weak_evidence_indicators += 1
        if not function_type:
            weak_evidence_indicators += 1
        if signal_diversity == "low":
            weak_evidence_indicators += 1
        if has_repeated_signals:
            weak_evidence_indicators += 1

        if weak_evidence_indicators >= 3 or unique_signal_count == 0:
            return "low"

        if high_evidence_indicators >= 3:
            return "high"
        if high_evidence_indicators >= 2:
            return "medium"

        return "low"

    def _calculate_confidence(
        self,
        evidence_quality: str,
        unique_signal_count: int,
        source_type_count: int,
        function_type: str | None,
        friction_score_value: float,
        signal_diversity: str,
    ) -> str:
        """Calculate confidence based on evidence quality."""
        if evidence_quality == "high":
            score = 0
            if unique_signal_count >= 6:
                score += 2
            elif unique_signal_count >= 4:
                score += 1
            if source_type_count >= 3:
                score += 1
            elif source_type_count >= 2:
                score += 1
            if function_type:
                score += 2
            if friction_score_value > 5:
                score += 2
            elif friction_score_value > 0:
                score += 1
            if signal_diversity == "high":
                score += 1

            if score >= 7:
                return "high"
            return "medium"

        if evidence_quality == "medium":
            return "medium"

        return "low"

    def generate_preliminary_verdict(
        self,
        company_name: str,
        signals: list[CompanySignal],
        evidence: dict,
    ) -> dict:
        """Generate preliminary verdict when evidence is weak."""
        what_we_know = self._summarize_what_we_know(signals, evidence)
        what_we_dont_know = self._summarize_what_we_dont_know(evidence)
        next_step = self._recommend_next_step(evidence)

        return {
            "verdict_type": "preliminary",
            "evidence_quality": evidence.get("evidence_quality", "low"),
            "confidence": evidence.get("confidence", "low"),
            "what_we_know": what_we_know,
            "what_we_do_not_know_yet": what_we_dont_know,
            "next_best_step": next_step,
        }

    def _summarize_what_we_know(
        self, signals: list[CompanySignal], evidence: dict
    ) -> str:
        """Summarize what we actually know from the data."""
        if not signals:
            return "We have limited data on this company so far."

        unique_signals = self._get_unique_signals(signals)
        signal_summary = []

        for text in unique_signals[:3]:
            if "careers page" in text.lower():
                signal_summary.append("the company appears to be actively hiring")
            elif "newsroom" in text.lower():
                signal_summary.append("the company publishes news and updates")
            elif "about" in text.lower():
                signal_summary.append(
                    "the company has an about page with company information"
                )
            elif "homepage" in text.lower():
                signal_summary.append("the company has an active web presence")
            else:
                signal_summary.append(text)

        if signal_summary:
            return f"We have found: {', '.join(signal_summary)}."

        return "We have confirmed the company exists, but do not have detailed signals yet."

    def _summarize_what_we_dont_know(self, evidence: dict) -> str:
        """Explain what we don't know due to weak evidence."""
        quality = evidence.get("evidence_quality", "low")
        func = evidence.get("function_type")

        if quality == "low":
            if not func:
                return "We do not yet have enough evidence to identify whether the main pain is in data, operations, reporting, recruiting, or another functional area."
            return f"We have some hints about {func} but need more signals to confirm the primary business challenge."

        return "We need more diverse signals to confidently identify the main business pain."

    def _recommend_next_step(self, evidence: dict) -> str:
        """Recommend next collection step."""
        quality = evidence.get("evidence_quality", "low")
        unique_count = evidence.get("unique_signal_count", 0)

        if quality == "low":
            if unique_count == 0:
                return "Collect initial signals from the careers page, about page, and homepage to establish baseline company information."
            if unique_count <= 2:
                return "Gather deeper signals from job descriptions, about pages, newsroom content, and function-specific hiring clues before generating a stronger recommendation."
            return "Conduct additional collection runs to gather more diverse signals across different source types."

        return "Additional collection may help refine the analysis."


evidence_threshold_engine = EvidenceThresholdEngine()

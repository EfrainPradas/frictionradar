import re

from app.models.company_job_role import CompanyJobRole, CompanyRoleSignal


# Keyword matching uses word-boundary regex, not substring `in`.
# Why: substrings like "ar" (for accounts receivable) or "ta" (talent)
# match inside unrelated words ("area", "portal"), generating massive
# false positives. Word boundaries make matching reliable on any dataset.
_KEYWORD_RE_CACHE: dict[str, re.Pattern] = {}


def _kw_regex(keyword: str) -> re.Pattern:
    pat = _KEYWORD_RE_CACHE.get(keyword)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(keyword.strip().lower()) + r"\b")
        _KEYWORD_RE_CACHE[keyword] = pat
    return pat


_JUNK_PATTERNS = [
    "about us", "what we", "how we", "our culture", "filter result", "filter job",
    "knowledge base", "homepage", "open job", "open position", "view open",
    "current opening", "iabv2", "added option", "bring passion",
    "win together", "we deliver", "life at",
    # Removed "inside " — it also matches legitimate titles like
    # "Inside Sales Representative". Prefer specific UI junk patterns.
    "visa classic", "visa platinum", "visa signature", "visa activation", "secured visa",
    "cookie", "privacy", "terms of", "sign in", "log in", "subscribe",
    "post date:", "location:", "industry:", "posted:", "job id:",
    "what you", "ready to make", "together, we", "jobs based on",
    "be well program", "check out our", "we're sorry", "can't find",
    "featured team", "french (", "german (", "english (", "selected",
    "posting date", "relevance", "other post-graduate",
    "internship &", "medical residencies", "brno m",
    # Fix G1 — new junk patterns harvested from no_keyword_match sample.
    # Product/pricing listings (not roles):
    "debit card", "limited edition", "pro series", "regular price",
    # Corporate PR / announcements (not roles):
    "supports local", "celebrates", "most admired", "world's most",
    "america's best", "recognized leader", "award-winning",
    "best professional", "leading the way in", "newslearn",
    # Site navigation / UI chrome:
    "saved jobs", "search by", "job search filter",
    "all departments", "all locations", "tips & tricks",
    "tips and tricks", "who we are", "meet our", "customer stories",
    "partner directory", "developers for hire", "department:",
    "fortune ®", "learn about leading",
    "page not found", "404 error", "oops",
    # Marketing section headers:
    "contact center leaders", "digital leaders", "r&d leadership",
    "bench scientists", "leading brands", "grow their business",
    # Benefits / perks page sections (leavitt.com and similar):
    # The raw scraper mistakes benefit-page headings for job cards.
    # Patterns here are chosen to be unlikely substrings of real titles
    # (e.g. "paid vacation" won't appear inside "Senior Vacation Planner").
    "paid vacation", "sick leave", "mental wellbeing", "wellness program",
    "employee recognition", "voluntary products", "teledoc",
    "paid time off", "retirement plan", "health & wellness", "holiday pay",
    "401(k)", "pto policy",
]

# Exact-match department/section labels. These short strings pass
# is_valid_job_title because they contain substring role indicators
# ("engineering" contains "engineer", "leadership" contains "lead"),
# but they are navigation headers, not roles.
_DEPARTMENT_LABELS = {
    "engineering", "software engineering", "hardware engineering",
    "engineering services", "it engineering & architecture",
    "architecture, engineering, & construction",
    "leadership", "marketing", "operations", "sales", "finance",
    "product", "design", "internships", "internship program",
    "business & strategy", "editorial & content",
    "medical & medical research", "our culture", "our people",
    "our team", "meet our people", "board", "advisory",
    "engineering & architecture", "central functions",
    "internet of things", "field leader", "service leader",
    "kitchen leader",
    # Harvested from dataset_health unknown-titles sample:
    "board of directors", "executive leadership", "leadership team",
    "job categories", "career areas", "corporate",
    "open internet", "executive team", "senior leadership",
    "about us", "contact us",
}


def _is_junk_title(title: str) -> bool:
    """Return True if the title is scraped noise, not a real job."""
    if not title or len(title.strip()) < 3:
        return True
    stripped = title.strip()
    t = stripped.lower()
    if len(t) > 80:
        return True
    # Exact-match single- or multi-word department labels
    if t in _DEPARTMENT_LABELS:
        return True
    # Testimonial prefix: "– Name, Role ..." or "— Name, Role ..."
    if t[0] in {"–", "—", "-"} and "," in t[:40]:
        return True
    # Structural guards (dataset-agnostic):
    # Trademark / registered marks almost always denote brand / product
    # names, not jobs ("Fortune ® 500", "TrueCare ™").
    if "®" in stripped or "™" in stripped or "©" in stripped:
        return True
    # Truncated UI elements ending in ellipsis.
    if stripped.endswith("...") or stripped.endswith("…"):
        return True
    # Pure-number titles ("123", "2024") are scraper artifacts.
    if stripped.replace(" ", "").replace("-", "").isdigit():
        return True
    # Scraper concat noise: nav button text "View" fused directly to an
    # adjacent capitalized word without whitespace — e.g.
    # "Meet AishwaryaViewSoftware EngineerView". Real job titles never
    # have "View" glued to a following capital letter.
    if re.search(r"View[A-Z]", stripped):
        return True
    if any(p in t for p in _JUNK_PATTERNS):
        return True
    return False


class FunctionInferenceEngine:
    """Determines functional area from job titles and descriptions."""

    # Keywords are matched with \b word boundaries (see _kw_regex).
    # Principles:
    #   - No <=2-char tokens (ar, ap, bi, ta, cs, pm, ae, bd, ml, oe) —
    #     they match unrelated words even with boundaries (e.g., "ap"
    #     still matches the standalone word "AP" which is ambiguous).
    #   - No overly generic single words ("talent", "support", "security",
    #     "development") that collide across families.
    #   - Prefer compound keywords ("tech lead", "account manager") that
    #     are self-disambiguating.
    FUNCTION_KEYWORDS = {
        "data_analytics": [
            "analytics", "analyst", "business intelligence",
            "bi analyst", "bi developer", "data analyst",
            "reporting", "dashboard", "dashboards", "metrics",
            "insights", "sql", "tableau", "power bi",
            "data visualization", "visualization", "etl",
            "data engineer", "data science", "data scientist",
            "machine learning", "ml engineer",
            # Data leadership titles — were falling to unknown because the
            # bare token "data" wasn't in the list and these compounds
            # weren't either.
            "director of data", "head of data", "vp of data",
            "chief data officer", "data platform", "data infrastructure",
            "analytics engineer", "data warehouse",
        ],
        "finance": [
            "finance", "financial", "accountant", "accounting",
            "cpa", "controller", "forecasting", "budget",
            "budgeting", "treasury", "auditor", "financial analyst",
            "bookkeeper", "reconciliation", "payroll",
            "tax analyst", "fp&a", "accounting manager", "fixed asset",
            "billing", "accounts receivable", "accounts payable",
            "accounts payable specialist", "accounts receivable specialist",
            "staff accountant", "senior accountant",
        ],
        "operations": [
            "operations", "operational", "program operations",
            "process improvement", "workflow", "coordination",
            "operational excellence", "project coordinator",
            "program manager", "project manager", "operations manager",
            "business operations", "field operations",
            "laborer", "general labor", "seasonal", "pen rider",
            "grain operator", "facility maintenance",
            "maintenance technician", "maintenance mechanic",
            "incinerator", "day laborer",
            # Coverage gaps seen in audit sample:
            "coordinator", "facilities", "facility", "maintenance",
            "administrative coordinator", "general manager",
            "operations director", "chief operating officer",
            # Fix G2 — real misses from no_keyword_match sample:
            "administrative assistant", "assistant manager",
            "executive assistant", "personal assistant",
            "executive personal assistant",
            "lab supervisor", "lab manager",
            "patient access specialist",
        ],
        "supply_chain": [
            "supply chain", "procurement", "sourcing specialist",
            "buyer", "inventory", "demand planning", "supply planning",
            "logistics", "distribution", "fulfillment", "warehouse",
            "transportation", "freight", "material planning",
            "supply planner", "demand planner",
            # Fix G2 — driver/trucking roles (often a big slice of
            # hiring for logistics-heavy companies):
            "driver", "cdl driver", "truck driver", "otr driver",
            "delivery driver", "forklift operator",
            "warehouse associate",
        ],
        "marketing": [
            "marketing", "digital marketing", "content marketing",
            "brand manager", "social media", "seo", "sem",
            "advertising", "campaign manager", "creative director",
            "growth marketing", "performance marketing",
            "materials designer", "crm", "brand strategist",
            # Fix G2 — designer variants (standalone "designer" is too
            # ambiguous; require a qualifier):
            "motion designer", "graphic designer", "brand designer",
            "senior designer", "visual designer",
            # Growth/paid acquisition titles (AI-native scaleups):
            "user acquisition", "ad monetization", "paid media",
            "paid social", "google ads", "paid acquisition",
            "growth manager", "growth specialist",
        ],
        "sales": [
            "sales", "account executive", "sales representative",
            "business development", "enterprise sales", "inside sales",
            "outside sales", "sales engineer", "account manager",
            "territory manager", "field sales", "sales development",
            "sales development representative", "revenue operations",
        ],
        "customer_success": [
            "customer success", "customer support", "customer service",
            "account management", "customer success manager", "csm",
            "help desk", "technical support", "client success",
            "customer experience", "cx manager",
        ],
        "product": [
            "product", "product manager", "product owner",
            "associate product", "senior product", "group product",
            "technical product", "api product", "product marketing",
            "product designer", "product analyst",
        ],
        "engineering": [
            "engineer", "developer", "software engineer", "backend",
            "frontend", "full stack", "devops", "sre",
            "site reliability", "infrastructure", "platform engineer",
            "programmer",
            # Coverage gaps:
            "tech lead", "technical lead", "cloud engineer",
            "security engineer",
            "staff engineer", "principal engineer", "qa engineer",
            # Fix G2 — architect variants:
            "solution architect", "software architect",
            "data architect", "enterprise architect",
            "cloud architect", "security architect",
            "data warehousing architect",
        ],
        "hr_people": [
            "human resources", "people ops", "people operations",
            "hrbp", "hr business partner", "hr generalist",
            "compensation", "benefits", "learning and development",
            "people partner", "employee experience",
        ],
        "recruiting_talent": [
            "recruit", "recruiter", "talent acquisition",
            "sourcer", "technical recruiter", "recruiting coordinator",
            "staffing", "talent partner", "talent manager",
        ],
        "legal_compliance": [
            "legal", "lawyer", "attorney", "compliance",
            "regulatory", "contracts", "counsel", "paralegal",
            "legal ops", "general counsel",
        ],
        "manufacturing": [
            "manufacturing", "production", "factory", "assembly",
            "plant", "quality control", "lean", "six sigma",
            "process engineer", "manufacturing engineer",
            "production supervisor", "cnc", "machinist",
            "fabrication", "industrial engineer", "machine operator",
            "food safety", "dairy technician",
            "quality assurance supervisor",
        ],
        "retail": [
            "retail", "store manager", "cashier", "sales floor",
            "merchandising", "visual merchandiser", "loss prevention",
            "store associate", "district manager", "regional manager",
            "athlete",
        ],
        "it": [
            "information technology", "helpdesk", "help desk",
            "system admin", "sysadmin", "network admin",
            "it support", "it manager", "database admin", "dba",
            "desktop support", "it operations", "it director",
            "systems administrator", "network engineer",
        ],
        # Fix G3 — healthcare family. Previously all nurses, physicians,
        # and clinical roles fell into unknown, which hid signal for any
        # hospital/clinic dataset.
        "healthcare": [
            "nurse", "nursing", "registered nurse", "rn",
            "licensed practical nurse", "lpn",
            "nurse practitioner", "np",
            "physician", "doctor", "md",
            "pharmacist", "pharmacists", "pharmacy",
            "pharmacy technician", "pharm tech",
            "medical assistant", "medical technician",
            "clinical", "clinician", "clinical coordinator",
            "therapist", "physical therapist", "occupational therapist",
            "respiratory therapist", "speech therapist",
            "dentist", "dental hygienist", "dental assistant",
            "radiologist", "radiology technician",
            "sonographer", "ultrasound technician",
            "phlebotomist", "dietitian", "nutritionist",
            "caregiver", "cna", "certified nursing assistant",
            "surgeon", "surgical technician",
            "patient care", "patient coordinator",
            "healthcare administrator", "hospital administrator",
        ],
        # Phase 1 families — added to cover service, education, trades,
        # transportation, and food operations which previously fell into
        # unknown for hotel/school/construction/airline/restaurant datasets.
        "hospitality": [
            "hospitality", "hotel", "hotel manager", "hotel director",
            "hotel general manager", "general manager hotel",
            "concierge", "front desk", "front desk agent",
            "guest services", "guest experience", "housekeeping",
            "housekeeper", "valet", "bellhop", "butler",
            "room attendant", "reservations agent",
            "reservations specialist", "resort", "spa attendant",
            "banquet", "event coordinator", "event planner",
        ],
        "education": [
            "teacher", "teaching", "tutor", "professor", "instructor",
            "faculty", "lecturer", "educator", "curriculum",
            "curriculum developer", "instructional designer",
            "instructional coach", "principal", "school administrator",
            "academic coordinator", "academic advisor",
            "education coordinator", "learning specialist",
            "substitute teacher", "special education",
            "classroom aide", "teacher assistant",
        ],
        "trades": [
            "electrician", "plumber", "welder", "carpenter",
            "hvac", "hvac technician", "painter", "roofer",
            "glazier", "mason", "locksmith", "millwright",
            "pipefitter", "boilermaker", "journeyman",
            "apprentice electrician", "apprentice plumber",
            "field technician", "service technician",
            "installation technician", "installer",
            "auto mechanic", "diesel mechanic",
        ],
        "transportation": [
            "pilot", "first officer", "flight attendant",
            "aircraft mechanic", "airline", "airport operations",
            "conductor", "train operator", "bus driver",
            "chauffeur", "courier", "fleet manager",
            "fleet operations", "fleet supervisor",
            "transit operator", "ramp agent", "gate agent",
        ],
        "design": [
            "design", "designer", "ux", "ui", "user experience",
            "product designer", "ux designer", "ui designer", "ux researcher",
            "interaction designer", "visual designer", "graphic designer",
            "creative director", "design lead", "design manager",
            "experience designer", "service designer", "motion designer",
            "brand designer", "art director",
        ],
        "food_service": [
            "cook", "line cook", "prep cook", "sous chef",
            "executive chef", "pastry chef", "head chef",
            "baker", "bartender", "barista", "dishwasher",
            "busser", "waiter", "waitress", "food server",
            "kitchen manager", "restaurant manager",
            "catering manager", "catering coordinator",
            "food runner", "expeditor", "crew member",
            "team member", "shift leader", "shift supervisor",
        ],
    }

    # Keys use CANONICAL functional_area names (as persisted by
    # hiring_pattern_service._canonical). positioning_engine looks up
    # this dict using the DB-stored canonical names.
    PAIN_INFERENCE = {
        "analytics": {
            "main_pain": "The company struggles with clear visibility into business metrics and reporting across functions.",
            "pain_area": "Business intelligence, reporting clarity, and decision support.",
            "what_need": "Someone who can build metrics, reporting infrastructure, and turn data into actionable insights.",
            "positioning": "Position yourself as someone who can create transparent reporting and dashboard capabilities.",
        },
        "finance": {
            "main_pain": "The company faces challenges with financial visibility, forecasting accuracy, or accounting controls.",
            "pain_area": "Financial planning, reporting, and accounting operations.",
            "what_need": "Someone who can improve financial processes, forecasting, or accounting efficiency.",
            "positioning": "Position yourself as someone who can strengthen financial operations and reporting.",
        },
        "operations": {
            "main_pain": "The company faces coordination challenges as multiple teams and initiatives scale.",
            "pain_area": "Operations coordination, process efficiency, and cross-functional alignment.",
            "what_need": "Someone who can create operational clarity and process standardization.",
            "positioning": "Position yourself as someone who can drive efficiency and process improvement.",
        },
        "supply_chain": {
            "main_pain": "The company faces complexity in planning, sourcing, or delivering products.",
            "pain_area": "Supply chain planning, inventory management, and logistics coordination.",
            "what_need": "Someone who can improve supply chain visibility and planning accuracy.",
            "positioning": "Position yourself as someone who can optimize planning and fulfillment.",
        },
        "marketing": {
            "main_pain": "The company struggles to generate or measure marketing impact effectively.",
            "pain_area": "Marketing effectiveness, brand awareness, and customer acquisition.",
            "what_need": "Someone who can improve marketing ROI and campaign performance.",
            "positioning": "Position yourself as someone who can drive measurable growth.",
        },
        "sales": {
            "main_pain": "The company faces challenges in pipeline development or sales execution.",
            "pain_area": "Sales effectiveness, pipeline management, and revenue growth.",
            "what_need": "Someone who can improve sales process and revenue generation.",
            "positioning": "Position yourself as someone who can drive revenue growth and pipeline health.",
        },
        "customer_support": {
            "main_pain": "The company faces challenges in customer satisfaction or support efficiency.",
            "pain_area": "Customer experience, support operations, and retention.",
            "what_need": "Someone who can improve customer success processes and outcomes.",
            "positioning": "Position yourself as someone who can enhance customer experience and retention.",
        },
        "product": {
            "main_pain": "The company struggles to prioritize or execute on product roadmap effectively.",
            "pain_area": "Product strategy, roadmap prioritization, and feature delivery.",
            "what_need": "Someone who can drive product clarity and execution.",
            "positioning": "Position yourself as someone who can clarify roadmap and delivery.",
        },
        "engineering": {
            "main_pain": "The company faces challenges in engineering execution, system reliability, or delivery.",
            "pain_area": "Engineering velocity, system reliability, and technical debt.",
            "what_need": "Someone who can improve engineering productivity or system stability.",
            "positioning": "Position yourself as someone who can improve delivery and reliability.",
        },
        "hr": {
            "main_pain": "The company faces challenges in people operations, culture, or employee experience.",
            "pain_area": "HR operations, employee engagement, and organizational development.",
            "what_need": "Someone who can improve people operations and employee experience.",
            "positioning": "Position yourself as someone who can strengthen people operations.",
        },
        "recruiting": {
            "main_pain": "The company struggles to hire fast enough or find the right talent efficiently.",
            "pain_area": "Recruiting operations, talent pipeline, and hiring velocity.",
            "what_need": "Someone who can improve recruiting efficiency and talent pipeline.",
            "positioning": "Position yourself as someone who can accelerate hiring and improve quality.",
        },
        "legal": {
            "main_pain": "The company faces regulatory pressure or contract management challenges.",
            "pain_area": "Legal operations, compliance, and risk management.",
            "what_need": "Someone who can manage legal risk and compliance effectively.",
            "positioning": "Position yourself as someone who can manage risk and compliance.",
        },
        "manufacturing": {
            "main_pain": "The company faces production scaling or quality control challenges.",
            "pain_area": "Manufacturing operations, production efficiency, and quality assurance.",
            "what_need": "Someone who can optimize production processes and quality standards.",
            "positioning": "Position yourself as someone who can drive production excellence.",
        },
        "retail": {
            "main_pain": "The company faces challenges in store operations or customer-facing execution.",
            "pain_area": "Retail operations, store management, and merchandising.",
            "what_need": "Someone who can improve store performance and customer experience.",
            "positioning": "Position yourself as someone who can drive store-level results.",
        },
        "it": {
            "main_pain": "The company faces IT infrastructure or internal systems challenges.",
            "pain_area": "IT operations, infrastructure management, and internal support.",
            "what_need": "Someone who can stabilize IT operations and improve internal tools.",
            "positioning": "Position yourself as someone who can strengthen infrastructure and support.",
        },
        "healthcare": {
            "main_pain": "The company faces clinical staffing pressure or patient-care capacity challenges.",
            "pain_area": "Clinical operations, patient care, and healthcare delivery.",
            "what_need": "Someone who can strengthen clinical staffing, quality of care, or patient throughput.",
            "positioning": "Position yourself as someone who can stabilize clinical operations and patient outcomes.",
        },
        "hospitality": {
            "main_pain": "The company faces pressure on guest-facing service quality and operational consistency across shifts or properties.",
            "pain_area": "Guest experience, service operations, and staffing consistency.",
            "what_need": "Someone who can stabilize service delivery and improve guest satisfaction at scale.",
            "positioning": "Position yourself as someone who can standardize guest experience across locations.",
        },
        "education": {
            "main_pain": "The company faces enrollment, curriculum delivery, or student-outcome pressure as it scales programs.",
            "pain_area": "Curriculum delivery, instructional quality, and student outcomes.",
            "what_need": "Someone who can strengthen instructional quality, curriculum design, or student engagement.",
            "positioning": "Position yourself as someone who can improve learning outcomes and program effectiveness.",
        },
        "trades": {
            "main_pain": "The company faces field-service capacity, installation quality, or skilled-trades shortage challenges.",
            "pain_area": "Field service execution, installation quality, and technical craftsmanship.",
            "what_need": "Someone who can deliver reliable on-site work and mentor apprentice technicians.",
            "positioning": "Position yourself as someone who can hold quality while scaling field capacity.",
        },
        "transportation": {
            "main_pain": "The company faces capacity, on-time performance, or crew availability pressure in transportation operations.",
            "pain_area": "Transit operations, crew scheduling, and service reliability.",
            "what_need": "Someone who can keep transportation operations running on time with available crew.",
            "positioning": "Position yourself as someone who can hold schedule integrity at scale.",
        },
        "food_service": {
            "main_pain": "The company faces kitchen throughput, food-safety, or staffing continuity pressure across shifts.",
            "pain_area": "Kitchen operations, food safety, and service-line execution.",
            "what_need": "Someone who can keep kitchen output consistent and trainable under volume.",
            "positioning": "Position yourself as someone who can standardize kitchen operations across locations.",
        },
    }

    def infer_functional_area(
        self, role_title: str, role_description: str | None = None
    ) -> dict:
        """Infer functional area from role title and optional description.

        Returns a dict with:
          - area: one of FUNCTION_KEYWORDS keys, or "unknown", or "junk"
          - confidence: "high" | "medium" | "low" | "none"
          - signal: signal_type string (only for matched areas)
          - score: keyword hit count
          - reason_code: "matched" | "no_keyword_match" | "junk_title"
                       | "invalid_title:<detail>"
        """
        from app.services.title_normalizer import (
            is_valid_job_title,
            clean_title,
            _rejection_reason,
        )

        if not role_title or _is_junk_title(role_title):
            return {
                "area": "junk",
                "confidence": "none",
                "signal": None,
                "score": 0,
                "reason_code": "junk_title",
            }

        if not is_valid_job_title(role_title):
            return {
                "area": "junk",
                "confidence": "none",
                "signal": None,
                "score": 0,
                "reason_code": f"invalid_title:{_rejection_reason(role_title)}",
            }

        role_title = clean_title(role_title)
        text = f"{role_title} {role_description or ''}".lower()

        # Two parallel tallies:
        #   scores[area]       = hit count (drives confidence threshold)
        #   specificity[area]  = sum of word counts of matched keywords
        #                        (breaks ties — multi-word matches are more
        #                        diagnostic than single-word matches)
        scores = {area: 0 for area in self.FUNCTION_KEYWORDS}
        specificity = {area: 0 for area in self.FUNCTION_KEYWORDS}
        for area, keywords in self.FUNCTION_KEYWORDS.items():
            for keyword in keywords:
                if _kw_regex(keyword).search(text):
                    scores[area] += 1
                    specificity[area] += len(keyword.split())

        if not scores or max(scores.values()) == 0:
            return {
                "area": "unknown",
                "confidence": "low",
                "signal": None,
                "score": 0,
                "reason_code": "no_keyword_match",
            }

        # argmax by (hit_count, specificity). Ties on both are broken by
        # insertion order of the dict — acceptable.
        best_area = max(
            self.FUNCTION_KEYWORDS.keys(),
            key=lambda a: (scores[a], specificity[a]),
        )
        score = scores[best_area]
        confidence = "high" if score >= 3 else "medium" if score >= 1 else "low"
        signal_type = self._generate_signal_type(best_area)

        return {
            "area": best_area,
            "confidence": confidence,
            "signal": signal_type,
            "score": score,
            "reason_code": "matched",
        }

    def _generate_signal_type(self, area: str) -> str | None:
        """Generate signal type from functional area."""
        mapping = {
            "data_analytics": "analytics_hiring",
            "finance": "finance_hiring",
            "operations": "operations_hiring",
            "supply_chain": "supply_chain_hiring",
            "marketing": "marketing_hiring",
            "sales": "sales_hiring",
            "customer_success": "cs_hiring",
            "product": "product_hiring",
            "engineering": "engineering_hiring",
            "hr_people": "hr_hiring",
            "recruiting_talent": "recruiting_hiring",
            "legal_compliance": "legal_hiring",
            "manufacturing": "manufacturing_hiring",
            "retail": "retail_hiring",
            "it": "it_hiring",
            "healthcare": "healthcare_hiring",
            "hospitality": "hospitality_hiring",
            "education": "education_hiring",
            "trades": "trades_hiring",
            "transportation": "transportation_hiring",
            "food_service": "food_service_hiring",
        }
        return mapping.get(area)

    def infer_pain_from_patterns(self, functional_areas: list[str]) -> dict:
        """Infer likely business pain from repeated functional hiring patterns."""
        if not functional_areas:
            return {
                "main_pain": "Not enough evidence to determine pain area.",
                "pain_area": "Unknown",
                "what_need": "Need more role-level data.",
                "positioning": "Gather more hiring intelligence.",
            }

        area_counts: dict[str, int] = {}
        for area in functional_areas:
            area_counts[area] = area_counts.get(area, 0) + 1

        top_areas = sorted(area_counts.items(), key=lambda x: x[1], reverse=True)[:3]

        if not top_areas:
            return {
                "main_pain": "Not enough evidence to determine pain area.",
                "pain_area": "Unknown",
                "what_need": "Need more role-level data.",
                "positioning": "Gather more hiring intelligence.",
            }

        primary_area = top_areas[0][0]
        pain = self.PAIN_INFERENCE.get(primary_area, self.PAIN_INFERENCE["operations"])

        supporting_areas = [a[0] for a in top_areas[1:]] if len(top_areas) > 1 else []

        if len(top_areas) > 1:
            pain["main_pain"] = (
                f"The company shows hiring pressure across {primary_area.replace('_', ' ')} and {', '.join(supporting_areas).replace('_', ', ')}, suggesting multiple areas of operational stress."
            )
        elif area_counts[primary_area] >= 3:
            pain["main_pain"] = (
                f"The company is actively hiring {area_counts[primary_area]} roles in {primary_area.replace('_', ' ')}, indicating significant pressure in this function."
            )

        return {
            "main_pain": pain["main_pain"],
            "pain_area": pain["pain_area"],
            "what_need": pain["what_need"],
            "positioning": pain["positioning"],
            "top_areas": [{"area": a[0], "count": a[1]} for a in top_areas],
            "primary_function": primary_area,
            "confidence": "high" if top_areas[0][1] >= 3 else "medium",
        }


function_inference_engine = FunctionInferenceEngine()

"""Candidate Intelligence Extraction Layer.

Reads Ascendia profile data (profiles, work_experience, accomplishments,
career_vision_profiles) via PostgREST and extracts:
- dominant capabilities
- solved pain categories
- strength dimensions
- inferred positioning
- positioning vectors

Core principle: Accomplishments reveal SOLVED organizational pain.
"Improved SQL reporting performance by 40%" → reporting optimization,
operational visibility, analytics acceleration.

This service reads from the Ascendia Supabase project via REST API.
It only reads — never writes to Ascendia source tables.
"""
import re
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.candidate_intelligence import CandidateIntelligenceProfile

logger = get_logger(__name__)


# ── Pain category keyword mapping ────────────────────────────────────────

PAIN_CATEGORY_KEYWORDS = {
    "reporting_fragmentation": {
        "keywords": [
            "report", "dashboard", "metric", "kpi", "analytics", "bi ",
            "business intelligence", "data visualization", "sql", "tableau",
            "power bi", "insight", "reporting", "data pipeline", "etl",
            "data warehouse", "data lake", "reporting infrastructure",
            "measurement", "tracking", "visibility", "monitoring",
        ],
        "label": "Reporting & Analytics",
    },
    "process_inefficiency": {
        "keywords": [
            "process", "workflow", "efficiency", "bottleneck", "automation",
            "streamline", "optimize", "manual", "reduction", "cycle time",
            "throughput", "lean", "six sigma", "continuous improvement",
            "operational excellence", "standardize", "sop",
        ],
        "label": "Process & Operations",
    },
    "tooling_inconsistency": {
        "keywords": [
            "tool", "platform", "system", "integration", "infrastructure",
            "migration", "consolidat", "tech stack", "software", "saas",
            "implementation", "deploy", "rollout", "erp", "crm", "ats",
            "architect", "cloud", "devops", "ci/cd",
        ],
        "label": "Tooling & Infrastructure",
    },
    "scaling_strain": {
        "keywords": [
            "scale", "growth", "expand", "hire", "team build", "headcount",
            "launch", "new market", "go-to-market", "revenue growth",
            "acquisition", "merger", "integration", "onboard",
            "cross-functional", "multi-team", "organizational design",
        ],
        "label": "Scaling & Growth",
    },
    "customer_experience_friction": {
        "keywords": [
            "customer", "client", "user experience", "ux", "cx",
            "nps", "csat", "retention", "churn", "satisfaction",
            "journey", "touchpoint", "support", "success",
        ],
        "label": "Customer Experience",
    },
}


# ── Strength dimension mapping ────────────────────────────────────────────

STRENGTH_KEYWORDS = {
    "transformation": [
        "transform", "overhaul", "moderniz", "digitiz", "migrate",
        "rebuild", "restructur", "reorgani", "change management",
        "turnaround", "pivot", "reinvent",
    ],
    "analytics": [
        "data", "analyt", "insight", "metric", "report", "dashboard",
        "bi ", "business intelligence", "measurement", "quantif",
        "predict", "model", "statistical",
    ],
    "leadership": [
        "leadership", "manage", "direct", "vp ", "chief", "head of",
        "director", "executive", "strateg", "vision",
        "mentor", "coach", "develop team",
    ],
    "operational": [
        "operat", "process", "efficien", "streamline", "optimize",
        "automat", "workflow", "coordina", "execute", "deliver",
        "scale", "implement",
    ],
    "modernization": [
        "moderniz", "cloud", "api", "microservice", "agile",
        "devops", "digital", "saas", "platform", "tech debt",
        "refactor", "rearchitect",
    ],
}


# ── Capability extraction ─────────────────────────────────────────────────

CAPABILITY_PATTERNS = [
    (r"improved.*(?:performance|efficiency|productivity|throughput)", "Performance Improvement"),
    (r"reduced.*(?:cost|spend|budget|overhead|waste)", "Cost Reduction"),
    (r"increased.*(?:revenue|sales|growth|conversion|retention)", "Revenue Growth"),
    (r"built.*(?:team|organization|department|function|practice)", "Team Building"),
    (r"launched.*(?:product|feature|service|program|initiative)", "Product Launch"),
    (r"established.*(?:process|framework|system|standard|governance)", "Process Design"),
    (r"managed.*(?:budget|p&l|portfolio|program|operation)", "Operational Management"),
    (r"led.*(?:strategy|initiative|transformation|migration|integration)", "Strategic Leadership"),
    (r"created.*(?:dashboard|report|metric|kpi|framework)", "Analytics Creation"),
    (r"designed.*(?:architecture|solution|system|platform|workflow)", "Solution Architecture"),
    (r"automated.*(?:process|workflow|pipeline|report|task)", "Process Automation"),
    (r"scaled.*(?:team|operation|infrastructure|platform|system)", "Scale Execution"),
    (r"implement.*(?:system|tool|platform|framework|standard)", "Implementation"),
    (r"migrated.*(?:system|platform|infrastructure|data|application)", "System Migration"),
    (r"consolidated.*(?:tool|system|platform|data|process)", "Tool Consolidation"),
]


class CandidateIntelligenceExtractor:
    """Extracts intelligence from Ascendia candidate profile data.

    Reads profile, work experience, and accomplishment data via PostgREST.
    Outputs a CandidateIntelligenceProfile with solved-pain categories,
    strength dimensions, and positioning vectors.
    """

    def _ascendia_get(self, table: str, params: dict | None = None) -> list[dict]:
        """GET from Ascendia PostgREST."""
        url = f"{settings.ASCENDIA_SUPABASE_URL}/rest/v1/{table}"
        headers = {
            "apikey": settings.ASCENDIA_SUPABASE_KEY,
            "Authorization": f"Bearer {settings.ASCENDIA_SUPABASE_KEY}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
            if resp.status_code == 200:
                return resp.json()
            logger.debug(f"Ascendia GET {table} returned {resp.status_code}")
            return []
        except Exception as e:
            logger.debug(f"Ascendia GET {table} failed: {e}")
            return []

    def extract(self, user_id: UUID, db: Session) -> CandidateIntelligenceProfile:
        profile_data = self._load_ascendia_data(user_id)

        accomplishments_text = profile_data.get("accomplishments_text", "")
        experience_text = profile_data.get("experience_text", "")
        all_text = f"{accomplishments_text} {experience_text}".strip()

        if not all_text:
            logger.warning(f"No profile text found for user {user_id}")
            return self._create_minimal_profile(user_id, db)

        capabilities = self._extract_capabilities(all_text)
        solved_pain = self._extract_solved_pain(all_text)
        strengths = self._compute_strengths(all_text)
        positioning = self._infer_positioning(capabilities, solved_pain, strengths)
        vectors = self._build_positioning_vectors(capabilities, solved_pain, strengths)

        existing = (
            db.query(CandidateIntelligenceProfile)
            .filter(CandidateIntelligenceProfile.user_id == user_id)
            .first()
        )

        if existing:
            existing.dominant_capabilities = capabilities
            existing.solved_pain_categories = solved_pain
            existing.transformation_strength = strengths["transformation"]
            existing.analytics_strength = strengths["analytics"]
            existing.leadership_strength = strengths["leadership"]
            existing.operational_strength = strengths["operational"]
            existing.modernization_strength = strengths["modernization"]
            existing.inferred_positioning = positioning
            existing.positioning_vectors = vectors
            existing.source_accomplishments_count = profile_data.get("accomplishments_count", 0)
            existing.source_experience_count = profile_data.get("experience_count", 0)
            existing.extraction_version = "1.1.0"
            db.commit()
            db.refresh(existing)
            return existing

        profile = CandidateIntelligenceProfile(
            user_id=user_id,
            dominant_capabilities=capabilities,
            solved_pain_categories=solved_pain,
            transformation_strength=strengths["transformation"],
            analytics_strength=strengths["analytics"],
            leadership_strength=strengths["leadership"],
            operational_strength=strengths["operational"],
            modernization_strength=strengths["modernization"],
            inferred_positioning=positioning,
            positioning_vectors=vectors,
            source_accomplishments_count=profile_data.get("accomplishments_count", 0),
            source_experience_count=profile_data.get("experience_count", 0),
            extraction_version="1.1.0",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    def _load_ascendia_data(self, user_id: UUID) -> dict:
        """Load profile data from Ascendia via PostgREST (bulk queries)."""
        if not settings.ASCENDIA_SUPABASE_URL or not settings.ASCENDIA_SUPABASE_KEY:
            logger.warning("Ascendia Supabase credentials not configured")
            return {"accomplishments_text": "", "experience_text": "", "accomplishments_count": 0, "experience_count": 0}

        accomplishments_parts = []
        experience_parts = []
        accomplishments_count = 0
        experience_count = 0
        uid = str(user_id)

        # 1. Find user's resumes
        resumes = self._ascendia_get("user_resumes", {"user_id": f"eq.{uid}", "select": "id,profile_summary"})
        resume_ids = [r["id"] for r in resumes]
        for r in resumes:
            if r.get("profile_summary"):
                experience_parts.append(r["profile_summary"])

        if not resume_ids:
            logger.debug(f"No resumes found for user {uid}")
            return {"accomplishments_text": "", "experience_text": "", "accomplishments_count": 0, "experience_count": 0}

        # 2. Bulk load ALL work_experience for those resumes
        or_filter = ",".join(resume_ids)
        we_rows = self._ascendia_get("work_experience", {
            "resume_id": f"in.({or_filter})",
            "select": "id,job_title,company_name,scope_description,role_explanation,tools_systems",
            "order": "order_index.asc",
            "limit": 200,
        })

        we_ids = []
        for row in we_rows:
            we_ids.append(row["id"])
            parts = [
                row.get("job_title", ""),
                row.get("company_name", ""),
                row.get("scope_description", ""),
                row.get("role_explanation", ""),
            ]
            text = " ".join(p for p in parts if p)
            tools = row.get("tools_systems")
            if tools and isinstance(tools, list):
                text += " Tools: " + ", ".join(str(t) for t in tools[:10])
            if text.strip():
                experience_parts.append(text)
                experience_count += 1

        # 3. Bulk load ALL accomplishments for those work_experiences
        if we_ids:
            # PostgREST allows max ~50 items in `in.` filter, so batch
            for i in range(0, len(we_ids), 50):
                batch = we_ids[i:i+50]
                or_filter = ",".join(batch)
                acc_rows = self._ascendia_get("accomplishments", {
                    "work_experience_id": f"in.({or_filter})",
                    "select": "bullet_text,raw_bullet,verb,scope,action,metric",
                    "limit": 500,
                })
                for acc in acc_rows:
                    parts = [acc.get("bullet_text", ""), acc.get("raw_bullet", "")]
                    verb = acc.get("verb")
                    scope = acc.get("scope")
                    action = acc.get("action")
                    metric = acc.get("metric")
                    if verb or scope or action or metric:
                        structured = f"{verb or ''} {scope or ''} {action or ''} {metric or ''}".strip()
                        parts.append(structured)
                    text = " ".join(p for p in parts if p)
                    if text.strip():
                        accomplishments_parts.append(text)
                        accomplishments_count += 1

        # 4. Load career vision
        cv_rows = self._ascendia_get("career_vision_profiles", {
            "user_id": f"eq.{uid}",
            "select": "career_vision_statement,skills_knowledge,interests,job_history_insights",
            "limit": 1,
        })
        for cv in cv_rows:
            for field in ["career_vision_statement", "skills_knowledge", "interests", "job_history_insights"]:
                val = cv.get(field)
                if val:
                    if isinstance(val, list):
                        experience_parts.extend(str(v) for v in val)
                    else:
                        experience_parts.append(str(val))

        return {
            "accomplishments_text": " ".join(accomplishments_parts),
            "experience_text": " ".join(experience_parts),
            "accomplishments_count": accomplishments_count,
            "experience_count": experience_count,
        }

    def _extract_capabilities(self, text: str) -> list[str]:
        text_lower = text.lower()
        capabilities = []
        for pattern, name in CAPABILITY_PATTERNS:
            if re.search(pattern, text_lower):
                capabilities.append(name)

        seen = set()
        unique = []
        for cap in capabilities:
            if cap not in seen:
                seen.add(cap)
                unique.append(cap)

        return unique[:8]

    def _extract_solved_pain(self, text: str) -> list[dict]:
        text_lower = text.lower()
        solved = []

        for category, config in PAIN_CATEGORY_KEYWORDS.items():
            count = sum(1 for kw in config["keywords"] if kw in text_lower)
            if count >= 2:
                solved.append({
                    "category": category,
                    "label": config["label"],
                    "evidence_count": count,
                })

        solved.sort(key=lambda x: x["evidence_count"], reverse=True)
        return solved

    def _compute_strengths(self, text: str) -> dict[str, float]:
        """Compute strength dimensions from text.

        Uses keyword occurrence frequency (not just presence) to differentiate.
        For profiles with extensive text, simple presence/absence saturates
        because nearly every keyword appears. Counting occurrences and
        comparing relative frequency across dimensions creates real separation.
        """
        text_lower = text.lower()
        raw = {}

        for dimension, keywords in STRENGTH_KEYWORDS.items():
            total_occurrences = 0
            for kw in keywords:
                total_occurrences += text_lower.count(kw)
            raw[dimension] = total_occurrences

        total_all = sum(raw.values())
        if total_all == 0:
            return {d: 0.15 for d in STRENGTH_KEYWORDS}

        # Convert to relative frequency, then scale so top dimension = 1.0
        max_freq = max(raw.values())
        strengths = {}
        for dim, count in raw.items():
            if count == 0:
                strengths[dim] = 0.15
            else:
                ratio = count / max_freq
                # Power curve: spreads out the middle values
                # 1.0→1.0, 0.8→0.78, 0.6→0.55, 0.4→0.35, 0.2→0.16
                strengths[dim] = round(ratio ** 0.8, 2)

        return strengths

    def _infer_positioning(
        self,
        capabilities: list[str],
        solved_pain: list[dict],
        strengths: dict[str, float],
    ) -> str:
        if not solved_pain and not capabilities:
            return "Insufficient profile data to determine positioning."

        top_pain = solved_pain[0]["label"] if solved_pain else None
        top_strength = max(strengths, key=strengths.get) if strengths else None
        strength_labels = {
            "transformation": "organizational transformation",
            "analytics": "data and analytics",
            "leadership": "strategic leadership",
            "operational": "operational execution",
            "modernization": "technology modernization",
        }

        parts = []
        if top_pain and top_strength:
            parts.append(
                f"Strong fit for companies experiencing {top_pain.lower()} pressure."
            )
            parts.append(
                f"Core strength in {strength_labels.get(top_strength, top_strength)} "
                f"positions you as a solution for organizations that need to address this pain."
            )
        elif capabilities:
            top_caps = capabilities[:3]
            parts.append(
                f"Capabilities in {', '.join(top_caps)} align with companies "
                f"experiencing organizational pain in those areas."
            )

        return " ".join(parts) if parts else "Positioning requires more profile data."

    def _build_positioning_vectors(
        self,
        capabilities: list[str],
        solved_pain: list[dict],
        strengths: dict[str, float],
    ) -> list[dict]:
        vectors = []

        for pain in solved_pain:
            category = pain["category"]
            evidence = pain["evidence_count"]
            strength = min(0.95, round(evidence * 0.2, 2))
            vectors.append({
                "pain_category": category,
                "match_strength": strength,
                "source": "accomplishment_evidence",
            })

        strength_to_pain = {
            "analytics": "reporting_fragmentation",
            "operational": "process_inefficiency",
            "modernization": "tooling_inconsistency",
            "transformation": "scaling_strain",
            "leadership": "scaling_strain",
        }
        for strength_dim, score in strengths.items():
            if score >= 0.3:
                pain_cat = strength_to_pain.get(strength_dim)
                if pain_cat:
                    existing = any(v["pain_category"] == pain_cat for v in vectors)
                    if not existing:
                        vectors.append({
                            "pain_category": pain_cat,
                            "match_strength": round(score * 0.7, 2),
                            "source": "inferred_strength",
                        })

        return vectors

    def _create_minimal_profile(self, user_id: UUID, db: Session) -> CandidateIntelligenceProfile:
        existing = (
            db.query(CandidateIntelligenceProfile)
            .filter(CandidateIntelligenceProfile.user_id == user_id)
            .first()
        )
        if existing:
            return existing

        profile = CandidateIntelligenceProfile(
            user_id=user_id,
            dominant_capabilities=[],
            solved_pain_categories=[],
            transformation_strength=0.0,
            analytics_strength=0.0,
            leadership_strength=0.0,
            operational_strength=0.0,
            modernization_strength=0.0,
            inferred_positioning="Insufficient profile data.",
            positioning_vectors=[],
            source_accomplishments_count=0,
            source_experience_count=0,
            extraction_version="1.1.0",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile


candidate_intelligence_extractor = CandidateIntelligenceExtractor()
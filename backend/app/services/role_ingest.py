"""
Role ingest — single source of truth for persisting a CompanyJobRole.

All collector/extractor paths MUST use persist_job_role() instead of
constructing CompanyJobRole directly. This closes the historical divergence
where each extractor wrote its own AREA_KEYWORDS-derived guess into
functional_area, and the canonical classifier only ran post-hoc via
reclassify_all_roles.py.

The classify_title() helper is the one place that binds:
  - function_inference_engine.infer_functional_area  (taxonomy + junk filter)
  - hiring_pattern_service._canonical                (name canonicalization)
  - confidence:reason_code formatting                (diagnostics)

classify_roles() in hiring_pattern_service.py also uses classify_title() so
that first-ingest and post-hoc reclassify produce identical labels.
"""
from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.company_job_role import CompanyJobRole
from app.services.function_inference_engine import function_inference_engine


CANONICAL = {
    "data_analytics": "analytics",
    "hr_people": "hr",
    "customer_success": "customer_support",
    "recruiting_talent": "recruiting",
    "legal_compliance": "legal",
}


def _canonical(area: str) -> str:
    return CANONICAL.get(area, area)


# Title sanitizer — strips pollution from non-ATS careers pages where the
# generic scraper glued title + department + location + CTA into one blob.
# Example observed on Cursor/Anysphere careers:
#   "AI Deployment ManagerSolutions·Full-time·San Francisco; New YorkApply →"
# Goal is to recover "AI Deployment Manager".
_INTERPUNCT_SPLIT = re.compile(r"\s*[·•]\s*")
_APPLY_SUFFIX = re.compile(r"\s*Apply\s*[→>]*\s*$", re.IGNORECASE)
_DEPT_SUFFIXES = [
    # Multi-word first (longest match wins via alternation order)
    "Revenue Operations",
    "People Operations",
    "Customer Success",
    "Customer Support",
    "Product Marketing",
    "Field Engineering",
    "Research & Development",
    # Single word
    "Engineering",
    "Solutions",
    "Marketing",
    "Recruiting",
    "Operations",
    "Security",
    "Research",
    "Product",
    "Finance",
    "Support",
    "Design",
    "Sales",
    "Legal",
    "People",
    "Data",
]
_DEPT_SUFFIX_RE = re.compile(
    r"(" + "|".join(re.escape(d) for d in _DEPT_SUFFIXES) + r")$"
)


def sanitize_title(raw: str) -> str:
    """Strip suffix pollution glued onto role titles by non-ATS scrapers.

    Safe on already-clean titles: only strips department suffixes when they
    are glued directly to a lowercase boundary (e.g., "ManagerEngineering"),
    so "Director of Engineering" stays intact.
    """
    if not raw:
        return raw
    s = raw.strip()
    # Split at first interpunct — dept/location/type come after.
    parts = _INTERPUNCT_SPLIT.split(s, maxsplit=1)
    s = parts[0].strip() if parts else s
    # Trailing "Apply →" / "Apply >" / "Apply"
    s = _APPLY_SUFFIX.sub("", s).strip()
    # Department word glued to end without space (e.g., "ManagerSolutions")
    m = _DEPT_SUFFIX_RE.search(s)
    if m:
        start = m.start()
        # Only strip when preceding char is lowercase — protects titles like
        # "Director of Engineering" or "VP, Marketing".
        if start > 0 and s[start - 1].islower():
            s = s[:start].rstrip()
    return s


def classify_title(
    role_title: str, role_description: Optional[str] = None
) -> tuple[str, str]:
    """Return (canonical_area, confidence_label) for a raw title.

    confidence_label is either the plain confidence ("high"/"medium"/"low")
    when the title matched, or "<confidence>:<reason_code>" for diagnostic
    cases ("low:no_keyword_match", "none:junk_title",
    "none:invalid_title:too_short_no_role", etc.).
    """
    result = function_inference_engine.infer_functional_area(
        role_title, role_description
    )
    area = _canonical(result["area"])
    confidence = result["confidence"]
    reason = result.get("reason_code") or ""
    label = confidence if reason in ("matched", "") else f"{confidence}:{reason}"
    return area, label


def persist_job_role(
    db: Session,
    *,
    company_id: UUID,
    raw_title: str,
    source_url: Optional[str] = None,
    role_location: Optional[str] = None,
    role_department: Optional[str] = None,
    role_description: Optional[str] = None,
) -> Optional[CompanyJobRole]:
    """Classify and stage a CompanyJobRole. Returns None if title is empty.

    Caller owns db.commit(). This helper only does db.add().

    Rows are persisted for ALL outcomes (including junk/unknown) so the
    collector log stays observable — post-hoc audits filter by
    functional_area NOT IN ('junk','unknown'), matching reclassify's model.
    """
    if not raw_title or not raw_title.strip():
        return None

    clean_title = sanitize_title(raw_title)
    if not clean_title:
        return None

    area, confidence_label = classify_title(clean_title, role_description)

    role = CompanyJobRole(
        company_id=company_id,
        source_url=source_url,
        role_title=clean_title,
        role_location=role_location,
        role_department=role_department,
        role_description=role_description,
        functional_area=area,
        functional_area_confidence=confidence_label,
    )
    db.add(role)
    return role

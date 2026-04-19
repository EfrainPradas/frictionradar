"""
Title Normalizer — validates and normalizes job titles before classification.

Three-stage pipeline:
  1. GATE: Is this actually a job title? (reject noise)
  2. CLEAN: Strip location, prefix, suffix noise from valid titles
  3. ENRICH: Add macro_family mapping after classification

This module does NOT classify — it prepares titles for the
FunctionInferenceEngine and validates its output.
"""

import re
from dataclasses import dataclass
from typing import Optional


# ── Stage 1: Title validation gate ─────────────────────────────────────

_SENTENCE_STARTS = [
    "we ", "our ", "you ", "the ", "is ", "are ", "that ", "with ",
    "for the", "of the", "at the", "in the", "a ", "an ",
    "together", "check out", "ready to", "can't find",
    "explore ", "discover ", "learn ", "join ",
]

_MARKETING_WORDS = [
    "empowers", "elevate", "fueling", "remarkable", "innovative",
    "leading the way", "pursuit of", "streamline", "solutions",
    "career-defining", "crossroads", "transform", "revolutionize",
    "reimagine", "cutting-edge", "world-class",
]

_NAV_PATTERNS = [
    "view details", "view all", "explore all", "see all", "apply now",
    "open jobs", "openings", "contact us", "get in touch",
    "actively hiring", "added options", "limit increase",
    "learn more", "read more", "sign up", "log in", "subscribe",
    "filter result", "filter job", "clear filter", "sort by",
    "posting date", "relevance", "selected", "search location",
]

_DATE_PATTERNS = [
    re.compile(r"\d{2}/\d{2}/\d{2,4}"),
    re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}", re.I),
    re.compile(r"^\d{1,2}\s+(weeks?|months?|days?|years?)\s+ago", re.I),
]

_ROLE_INDICATORS = [
    "manager", "director", "engineer", "analyst", "specialist",
    "coordinator", "assistant", "associate", "lead", "senior",
    "junior", "intern", "supervisor", "technician", "developer",
    "designer", "consultant", "representative", "officer", "admin",
    "operator", "worker", "driver", "laborer", "agent", "buyer",
    "planner", "recruiter", "attorney", "counsel", "auditor",
    "scientist", "researcher", "teacher", "nurse", "physician",
    "coach", "trainer", "writer", "editor", "producer",
    "accountant", "bookkeeper", "clerk", "secretary", "coder",
    "rider", "chef", "architect", "vp", "head of", "chief",
    "president", "executive", "strategist", "advisor", "partner",
    "attendant", "member", "crew",
    # Healthcare role words — allow 2-word titles like
    # "Community Pharmacist", "Physical Therapist" through validation.
    "pharmacist", "therapist", "phlebotomist", "dentist",
    "hygienist", "sonographer", "dietitian", "nutritionist",
    "caregiver", "surgeon", "clinician", "radiologist",
    "pediatrician",
    # Hospitality role words.
    "concierge", "valet", "housekeeper", "housekeeping", "butler",
    "bellhop",
    # Education role words.
    "tutor", "professor", "instructor", "faculty", "lecturer",
    "educator", "principal",
    # Skilled trades role words.
    "electrician", "plumber", "welder", "carpenter", "mechanic",
    "hvac", "painter", "roofer", "glazier", "mason", "locksmith",
    "millwright", "pipefitter", "boilermaker", "apprentice",
    "journeyman", "machinist",
    # Transportation role words.
    "pilot", "conductor", "chauffeur", "courier",
    # Food service role words.
    "cook", "baker", "bartender", "barista", "dishwasher",
    "busser", "waiter", "waitress",
]


def is_valid_job_title(title: str) -> bool:
    """Return True if the string looks like a real job title."""
    if not title or len(title.strip()) < 3:
        return False

    t = title.strip()
    lower = t.lower()

    # Too long — likely scraped prose
    if len(t) > 80:
        return False

    # Contains dates
    for pat in _DATE_PATTERNS:
        if pat.search(t):
            return False

    # Starts like a sentence
    if any(lower.startswith(m) for m in _SENTENCE_STARTS):
        return False

    # Marketing copy
    if any(m in lower for m in _MARKETING_WORDS):
        return False

    # Navigation/UI element
    if any(n in lower for n in _NAV_PATTERNS):
        return False

    # Must have a role-related word OR at least 2 words with "Job:" prefix
    has_role = any(r in lower for r in _ROLE_INDICATORS)
    has_job_prefix = lower.startswith("job:") or lower.startswith("job ")
    has_dept_prefix = lower.startswith("department:")

    if has_role or has_job_prefix or has_dept_prefix:
        return True

    # Short (1-2 words) without role indicator = likely noise
    if len(t.split()) <= 2:
        return False

    # Longer phrases: accept if no disqualifiers
    return True


# ── Stage 2: Title cleaning ───────────────────────────────────────────

_PREFIX_PATTERNS = [
    re.compile(r"^Job[:\s]+", re.I),
    re.compile(r"^Department[:\s]+", re.I),
    re.compile(r"^Position[:\s]+", re.I),
]

_SUFFIX_PATTERNS = [
    # Location in parentheses at end: "Engineer (Remote)" or "(NYC, NY)"
    re.compile(r"\s*\([^)]*(?:remote|hybrid|onsite|on-site)[^)]*\)\s*$", re.I),
    # City, State pattern at end
    re.compile(r"\s*[-–]\s*[A-Z][a-z]+(?:,\s*[A-Z]{2})?\s*$"),
    # Workday location suffix: "Beaverton, Oregon"
    re.compile(r"\s+[A-Z][a-z]+,\s+[A-Z][a-z]+\s*$"),
]


def clean_title(raw_title: str) -> str:
    """Strip prefixes, suffixes, and noise from a job title."""
    if not raw_title:
        return ""

    title = raw_title.strip()

    # Strip prefixes
    for pat in _PREFIX_PATTERNS:
        title = pat.sub("", title).strip()

    # Strip suffixes (only if title is long enough after stripping)
    for pat in _SUFFIX_PATTERNS:
        cleaned = pat.sub("", title).strip()
        if len(cleaned) >= 5:
            title = cleaned

    # Normalize whitespace
    title = re.sub(r"\s+", " ", title).strip()

    return title


# ── Stage 3: Macro-family mapping ─────────────────────────────────────

MACRO_FAMILIES = {
    "operational_execution": ["operations", "supply_chain", "manufacturing"],
    "revenue_and_customer": ["sales", "marketing", "customer_support", "customer_success", "retail"],
    "data_and_visibility": ["analytics", "data_analytics", "finance"],
    "people_and_talent": ["hr", "hr_people", "recruiting", "recruiting_talent"],
    "product_and_build": ["engineering", "product", "it", "design"],
    "corporate_support": ["legal", "legal_compliance"],
    "clinical_care": ["healthcare"],
    "frontline_service": ["hospitality", "food_service"],
    "field_execution": ["trades", "transportation"],
    "learning_and_development": ["education"],
}

_FUNC_TO_MACRO = {}
for macro, funcs in MACRO_FAMILIES.items():
    for f in funcs:
        _FUNC_TO_MACRO[f] = macro


def get_macro_family(function: str) -> str:
    """Map a normalized function to its macro-family."""
    return _FUNC_TO_MACRO.get(function, "other")


# ── Combined pipeline ─────────────────────────────────────────────────

@dataclass
class NormalizedTitle:
    raw_title: str
    normalized_title: str
    is_valid: bool
    rejection_reason: Optional[str] = None


def normalize_title(raw_title: str) -> NormalizedTitle:
    """Full normalization pipeline for a single title."""
    if not is_valid_job_title(raw_title):
        reason = _rejection_reason(raw_title)
        return NormalizedTitle(
            raw_title=raw_title or "",
            normalized_title="",
            is_valid=False,
            rejection_reason=reason,
        )

    cleaned = clean_title(raw_title)
    return NormalizedTitle(
        raw_title=raw_title,
        normalized_title=cleaned,
        is_valid=True,
    )


def _rejection_reason(title: str) -> str:
    if not title or len(title.strip()) < 3:
        return "too_short"
    if len(title.strip()) > 80:
        return "too_long"
    lower = title.strip().lower()
    for pat in _DATE_PATTERNS:
        if pat.search(title):
            return "contains_date"
    if any(lower.startswith(m) for m in _SENTENCE_STARTS):
        return "sentence_fragment"
    if any(m in lower for m in _MARKETING_WORDS):
        return "marketing_copy"
    if any(n in lower for n in _NAV_PATTERNS):
        return "navigation_element"
    if len(title.split()) <= 2:
        return "too_short_no_role"
    return "no_role_indicator"

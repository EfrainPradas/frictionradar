"""HTTP static careers page extractor.

Parses a pre-fetched HTML careers page to extract:
  - Open positions count (from text patterns or JSON-LD)
  - Job cards (title, location, department, URL)
  - Hiring areas (from department/category keywords)

This extractor only uses the raw HTML from an HTTP GET — no browser,
no JavaScript execution. If the page is a SPA shell, the classifier
should have routed to Playwright instead.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.extraction.constants import ExtractionStrategy, ReasonCode
from app.extraction.schemas import NormalizedJob, NormalizedJobsResult
from app.core.logging import get_logger

logger = get_logger(__name__)

# Minimum confidence to accept an HTTP static extraction.
# Below this, the dispatcher should escalate to Playwright.
MIN_ACCEPTANCE_CONFIDENCE = 0.4

# ── Area keywords (reused from existing schema) ─────────────────────
AREA_KEYWORDS = {
    "retail": ["retail", "store", "cashier", "sales floor", "associate", "merchandising"],
    "distribution": ["distribution", "warehouse", "fulfillment", "logistics", "shipping"],
    "manufacturing": ["manufacturing", "production", "factory", "assembly"],
    "technology": ["technology", "engineering", "software", "developer", "data", "security"],
    "finance": ["finance", "accounting", "financial", "controller"],
    "operations": ["operations", "ops", "program manager", "project manager"],
    "marketing": ["marketing", "digital marketing", "brand", "content", "creative"],
    "sales": ["sales", "account executive", "business development"],
    "customer_success": ["customer success", "support", "customer service"],
    "supply_chain": ["supply chain", "procurement", "sourcing"],
    "hr_people": ["human resources", "people", "talent", "recruiting"],
    "design": ["design", "ux", "ui", "user experience"],
    "legal": ["legal", "compliance", "regulatory"],
    "healthcare": ["healthcare", "medical", "clinical", "nursing"],
}


def extract_from_html(
    html: str,
    url: str,
    domain: str,
) -> NormalizedJobsResult:
    """Parse a static careers HTML page into NormalizedJobsResult.

    Args:
        html: Raw HTML from HTTP GET (pre-fetched by discovery).
        url: The careers page URL.
        domain: Company domain.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text_lower = text.lower()

    # ── 1. Try JSON-LD extraction (highest quality) ─────────────
    jsonld_jobs = _extract_json_ld_jobs(html, url)

    # ── 2. Extract job cards from DOM ───────────────────────────
    dom_jobs = _extract_job_cards(soup, url)

    # ── 3. Extract position count ───────────────────────────────
    position_count = _extract_position_count(text_lower)

    # ── 4. Merge results (prefer JSON-LD, supplement with DOM) ──
    if jsonld_jobs:
        jobs = jsonld_jobs
        if dom_jobs and len(dom_jobs) > len(jsonld_jobs):
            # DOM found more — use DOM
            jobs = dom_jobs
    else:
        jobs = dom_jobs

    if not position_count and jobs:
        position_count = len(jobs)

    # ── 5. Extract hiring areas from jobs ───────────────────────
    hiring_areas = _infer_hiring_areas(jobs, text_lower)
    locations = _extract_locations(jobs)

    # ── 6. Assess quality ───────────────────────────────────────
    quality, confidence = _assess_quality(jobs, position_count, hiring_areas)

    return NormalizedJobsResult(
        domain=domain,
        careers_url=url,
        strategy_used=ExtractionStrategy.HTTP_STATIC,
        reason_code=ReasonCode.STATIC_CAREERS_PAGE_DETECTED,
        open_positions_count=position_count,
        jobs=jobs,
        hiring_areas=sorted(hiring_areas),
        locations=sorted(locations),
        evidence_quality=quality,
        confidence=confidence,
    )


# ── JSON-LD extraction ──────────────────────────────────────────────

def _extract_json_ld_jobs(html: str, base_url: str) -> List[NormalizedJob]:
    """Extract jobs from JSON-LD (schema.org/JobPosting) blocks."""
    jobs: List[NormalizedJob] = []
    pattern = re.compile(
        r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.I | re.DOTALL,
    )

    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            continue

        # Could be a single JobPosting or an array
        items = []
        if isinstance(data, dict):
            if data.get("@type") == "JobPosting":
                items = [data]
            elif isinstance(data.get("@graph"), list):
                items = [i for i in data["@graph"] if isinstance(i, dict) and i.get("@type") == "JobPosting"]
        elif isinstance(data, list):
            items = [i for i in data if isinstance(i, dict) and i.get("@type") == "JobPosting"]

        for item in items:
            title = item.get("title")
            if not title:
                continue

            loc = None
            job_loc = item.get("jobLocation")
            if isinstance(job_loc, dict):
                addr = job_loc.get("address", {})
                if isinstance(addr, dict):
                    loc = addr.get("addressLocality") or addr.get("name")
            elif isinstance(job_loc, list) and job_loc:
                first = job_loc[0]
                if isinstance(first, dict):
                    addr = first.get("address", {})
                    if isinstance(addr, dict):
                        loc = addr.get("addressLocality")

            dept = item.get("industry") or item.get("occupationalCategory")
            job_url = item.get("url")

            desc = (item.get("description") or "")
            desc = re.sub(r"<[^>]+>", " ", desc)
            desc = re.sub(r"\s+", " ", desc).strip()[:200]

            jobs.append(NormalizedJob(
                title=title,
                location=loc,
                department=dept,
                job_url=job_url,
                description_snippet=desc or None,
            ))

    return jobs


# ── DOM job card extraction ─────────────────────────────────────────

# Selectors for common job card containers
JOB_CARD_SELECTORS = [
    "[data-testid='job']",
    "[data-testid='posting']",
    ".job-card", ".job-listing", ".job-item", ".job-post",
    ".posting-item", ".position-card", ".career-item",
    ".opening", ".vacancy",
    "li.position", "li.job", "li.opening",
    "tr.job", "tr.position",
    "article.job", "article.posting",
]

# Title patterns within a card
TITLE_SELECTORS = ["h2", "h3", "h4", ".title", ".job-title", ".position-title", "a"]

# Location patterns within a card
LOCATION_SELECTORS = [
    ".location", ".job-location", ".city",
    "[data-testid='location']", "span.loc",
]

# Department patterns within a card
DEPT_SELECTORS = [
    ".department", ".team", ".category",
    "[data-testid='department']", "[data-testid='team']",
]


def _extract_job_cards(soup: BeautifulSoup, base_url: str) -> List[NormalizedJob]:
    """Extract job cards from the DOM using common CSS selectors."""
    jobs: List[NormalizedJob] = []
    seen_titles: Set[str] = set()

    # Try each selector, use the one that finds the most cards
    best_cards = []
    for selector in JOB_CARD_SELECTORS:
        cards = soup.select(selector)
        if len(cards) > len(best_cards):
            best_cards = cards

    for card in best_cards[:50]:
        title = _extract_field(card, TITLE_SELECTORS)
        if not title or len(title) < 3 or len(title) > 150:
            continue

        title_key = title.lower().strip()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        location = _extract_field(card, LOCATION_SELECTORS)
        department = _extract_field(card, DEPT_SELECTORS)

        # Try to find job URL
        job_url = None
        link = card.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("http"):
                job_url = href
            elif href.startswith("/"):
                job_url = urljoin(base_url, href)

        jobs.append(NormalizedJob(
            title=title,
            location=location,
            department=department,
            job_url=job_url,
        ))

    # ── Fallback: scan all links for job-like anchors ───────────
    if not jobs:
        jobs = _extract_from_links(soup, base_url)

    return jobs


def _extract_field(element, selectors: List[str]) -> Optional[str]:
    """Try selectors to extract a text field from an element."""
    for sel in selectors:
        found = element.select_one(sel)
        if found:
            text = found.get_text(strip=True)
            if text and len(text) >= 2:
                return text
    return None


def _extract_from_links(soup: BeautifulSoup, base_url: str) -> List[NormalizedJob]:
    """Fallback: extract jobs from <a> tags that look like job listings."""
    jobs: List[NormalizedJob] = []
    seen: Set[str] = set()

    job_keywords = {
        "engineer", "manager", "analyst", "developer", "designer",
        "coordinator", "director", "specialist", "associate",
        "lead", "senior", "junior", "intern", "consultant",
        "architect", "scientist", "administrator", "officer",
        "representative", "advisor", "strategist",
    }

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if not text or len(text) < 5 or len(text) > 150:
            continue

        text_lower = text.lower()
        if not any(kw in text_lower for kw in job_keywords):
            continue

        # Skip nav/footer links
        if any(skip in text_lower for skip in [
            "learn more", "read more", "view all", "see all", "back to",
            "cookie", "privacy", "terms", "login", "sign in",
        ]):
            continue

        key = text_lower.strip()
        if key in seen:
            continue
        seen.add(key)

        href = a.get("href", "")
        job_url = None
        if href.startswith("http"):
            job_url = href
        elif href.startswith("/"):
            job_url = urljoin(base_url, href)

        jobs.append(NormalizedJob(title=text, job_url=job_url))

    return jobs[:50]


# ── Position count extraction ───────────────────────────────────────

def _extract_position_count(text_lower: str) -> Optional[int]:
    """Try to extract open positions count from page text."""
    patterns = [
        r"(\d{1,3}(?:,\d{3})*)\s*(?:open\s*)?(?:positions?|jobs?|roles?|openings?)",
        r"(?:open\s*)?(?:positions?|jobs?|roles?|openings?)\s*:?\s*(\d{1,3}(?:,\d{3})*)",
        r"showing\s+\d+\s*[-–]\s*\d+\s+of\s+(\d{1,3}(?:,\d{3})*)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            try:
                num = int(m.replace(",", ""))
                if 1 <= num <= 10000:
                    return num
            except (ValueError, TypeError):
                continue
    return None


# ── Hiring areas inference ──────────────────────────────────────────

def _infer_hiring_areas(jobs: List[NormalizedJob], text_lower: str) -> List[str]:
    """Infer hiring areas from job departments and page text."""
    areas: Set[str] = set()

    # From job departments
    for job in jobs:
        if job.department:
            dept_lower = job.department.lower()
            for area, keywords in AREA_KEYWORDS.items():
                if any(kw in dept_lower for kw in keywords):
                    areas.add(area)
                    break

    # From job titles
    for job in jobs:
        if job.title:
            title_lower = job.title.lower()
            for area, keywords in AREA_KEYWORDS.items():
                if any(kw in title_lower for kw in keywords):
                    areas.add(area)
                    break

    return list(areas)


def _extract_locations(jobs: List[NormalizedJob]) -> List[str]:
    """Collect unique locations from extracted jobs."""
    locs: Set[str] = set()
    for job in jobs:
        if job.location:
            locs.add(job.location)
    return list(locs)


# ── Quality assessment ──────────────────────────────────────────────

def _assess_quality(
    jobs: List[NormalizedJob],
    position_count: Optional[int],
    hiring_areas: List[str],
) -> tuple:
    """Return (quality: str, confidence: float)."""
    score = 0.0

    if len(jobs) >= 10:
        score += 0.4
    elif len(jobs) >= 5:
        score += 0.3
    elif len(jobs) >= 1:
        score += 0.15

    if position_count and position_count > 0:
        score += 0.2

    if len(hiring_areas) >= 3:
        score += 0.2
    elif len(hiring_areas) >= 1:
        score += 0.1

    # Bonus for jobs with full data (title + department + location)
    rich_jobs = sum(1 for j in jobs if j.title and j.department)
    if rich_jobs >= 5:
        score += 0.2
    elif rich_jobs >= 1:
        score += 0.1

    confidence = min(score, 1.0)

    if confidence >= 0.7:
        quality = "high"
    elif confidence >= 0.4:
        quality = "moderate"
    elif confidence > 0:
        quality = "limited"
    else:
        quality = "none"

    return quality, confidence

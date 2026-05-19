"""
Feature 4: Extract real Job Descriptions from job URLs.

Visits individual job page URLs already stored in CompanyJobRole.source_url,
extracts the full JD text, and stores it in CompanyJobRole.role_description.

Strategies (in order):
  1. ATS API detail fetch (Greenhouse, Lever) — cheapest/most reliable
  2. HTTP GET + BeautifulSoup — works for server-rendered pages
  3. Skip (Playwright is too expensive per-JD; HTTP covers most cases)
"""

import re
import time
from typing import Optional
from uuid import UUID

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.company_job_role import CompanyJobRole
from app.core.logging import get_logger
from app.core.security import get_ssl_verify

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json",
}

MAX_DESC_LENGTH = 5000

# Selectors to find the main JD content area (priority order)
JD_SELECTORS = [
    "[class*='job-description']",
    "[class*='job_description']",
    "[class*='jobDescription']",
    "[class*='posting-body']",
    "[class*='postingBody']",
    "[class*='job-detail']",
    "[class*='jobDetail']",
    "[data-testid='description']",
    "[class*='description']",
    "article",
    "[role='main']",
    ".content",
    "main",
]


def _extract_from_greenhouse_api(job_url: str) -> Optional[str]:
    """Try to fetch JD via Greenhouse board API for a single job."""
    # URL pattern: https://boards.greenhouse.io/{slug}/jobs/{id}
    match = re.search(r"boards\.greenhouse\.io/([^/]+)/jobs/(\d+)", job_url)
    if not match:
        match = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", job_url)
    if not match:
        return None

    slug, job_id = match.group(1), match.group(2)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"

    try:
        resp = requests.get(api_url, headers={"Accept": "application/json"}, timeout=12, verify=get_ssl_verify())
        if resp.status_code != 200:
            return None
        data = resp.json()
        content = data.get("content", "")
        if content:
            text = re.sub(r"<[^>]+>", " ", content)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:MAX_DESC_LENGTH] if text else None
    except Exception as e:
        logger.debug(f"Greenhouse API detail failed for {job_url}: {e}")
    return None


def _extract_from_lever_api(job_url: str) -> Optional[str]:
    """Try to fetch JD via Lever posting API."""
    # URL pattern: https://jobs.lever.co/{company}/{posting_id}
    match = re.search(r"jobs\.lever\.co/([^/]+)/([a-f0-9-]+)", job_url)
    if not match:
        return None

    company, posting_id = match.group(1), match.group(2)
    api_url = f"https://api.lever.co/v0/postings/{company}/{posting_id}"

    try:
        resp = requests.get(api_url, headers={"Accept": "application/json"}, timeout=12, verify=get_ssl_verify())
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Lever returns description as HTML in 'descriptionPlain' or 'description'
        text = data.get("descriptionPlain", "")
        if not text:
            html = data.get("description", "")
            if html:
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()
        # Also grab lists content
        lists = data.get("lists", [])
        for lst in lists:
            list_text = lst.get("text", "")
            list_content = lst.get("content", "")
            if list_content:
                clean = re.sub(r"<[^>]+>", " ", list_content)
                clean = re.sub(r"\s+", " ", clean).strip()
                text += f"\n{list_text}: {clean}"
        return text[:MAX_DESC_LENGTH] if text.strip() else None
    except Exception as e:
        logger.debug(f"Lever API detail failed for {job_url}: {e}")
    return None


def _extract_from_http(job_url: str) -> Optional[str]:
    """Fetch the job page via HTTP and extract JD text with BeautifulSoup."""
    try:
        resp = requests.get(job_url, headers=HEADERS, timeout=15, verify=get_ssl_verify(), allow_redirects=True)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "iframe"]):
            tag.decompose()

        # Try targeted selectors first
        for selector in JD_SELECTORS:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) >= 100:  # Minimum viable JD length
                    return text[:MAX_DESC_LENGTH]

        # Fallback: largest text block in body
        body = soup.find("body")
        if body:
            divs = body.find_all("div")
            best = ""
            for div in divs:
                t = div.get_text(separator=" ", strip=True)
                if len(t) > len(best):
                    best = t
            if len(best) >= 100:
                return best[:MAX_DESC_LENGTH]

    except Exception as e:
        logger.debug(f"HTTP JD extraction failed for {job_url}: {e}")
    return None


def _extract_from_workday_api(job_url: str) -> Optional[str]:
    """Try to fetch JD via Workday CXS API."""
    # URL pattern: https://{company}.wd{N}.myworkdayjobs.com/{board}/job/{path}/apply
    match = re.search(
        r"(\w+)\.wd(\d+)\.myworkdayjobs\.com/([^/]+)/job/(.+?)(?:/apply)?$",
        job_url,
    )
    if not match:
        return None

    company, wd_num, board, job_path = match.groups()
    # Use full path (not just ID) — Workday requires the slug
    api_url = (
        f"https://{company}.wd{wd_num}.myworkdayjobs.com"
        f"/wday/cxs/{company}/{board}/job/{job_path}"
    )

    try:
        resp = requests.get(
            api_url,
            headers={"Accept": "application/json", **HEADERS},
            timeout=12,
            verify=get_ssl_verify(),
        )
        if resp.status_code != 200:
            return None
        data = resp.json()

        # Workday nests description in jobPostingInfo.jobDescription
        jpi = data.get("jobPostingInfo", {})
        desc = jpi.get("jobDescription", "")
        if desc:
            text = re.sub(r"<[^>]+>", " ", desc)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) >= 50:
                return text[:MAX_DESC_LENGTH]

        # Fallback: additionalInformation or qualifications
        for field in ["additionalInformation", "qualifications"]:
            val = jpi.get(field, "")
            if val:
                text = re.sub(r"<[^>]+>", " ", val)
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) >= 50:
                    return text[:MAX_DESC_LENGTH]

    except Exception as e:
        logger.debug(f"Workday API detail failed for {job_url}: {e}")
    return None


def _is_generic_url(job_url: str) -> bool:
    """Check if a URL points to a generic careers page, not a specific job."""
    if not job_url:
        return True
    path = re.sub(r"https?://[^/]+", "", job_url).rstrip("/").lower()
    return path in ("", "/careers", "/jobs", "/job", "/career", "/join", "/join-us")


def extract_single_jd(job_url: str) -> Optional[str]:
    """Extract JD text from a single URL using best available strategy."""
    if not job_url:
        return None

    # Skip generic careers page URLs — they don't have individual JD content
    if _is_generic_url(job_url):
        return None

    url_lower = job_url.lower()

    # Try ATS APIs first (cheapest, most reliable)
    if "greenhouse.io" in url_lower:
        result = _extract_from_greenhouse_api(job_url)
        if result:
            return result

    if "lever.co" in url_lower:
        result = _extract_from_lever_api(job_url)
        if result:
            return result

    if "myworkdayjobs.com" in url_lower:
        result = _extract_from_workday_api(job_url)
        if result:
            return result

    # Fallback to HTTP scraping
    return _extract_from_http(job_url)


def extract_jds_for_company(
    company_id: UUID, db: Session, max_jds: int = 10, delay: float = 1.0
) -> dict:
    """Extract JDs for a company's job roles.

    Selects up to max_jds roles with source_url but no role_description,
    diversifying across functional_area.
    """
    # Get roles that need JD extraction
    roles = (
        db.query(CompanyJobRole)
        .filter(
            CompanyJobRole.company_id == company_id,
            CompanyJobRole.source_url.isnot(None),
            CompanyJobRole.source_url != "",
            (CompanyJobRole.role_description.is_(None) | (CompanyJobRole.role_description == "")),
        )
        .all()
    )

    if not roles:
        return {"total_attempted": 0, "successful": 0, "failed": 0, "already_done": 0}

    # Diversify: pick up to 2 per functional_area
    by_area: dict[str, list] = {}
    for r in roles:
        area = r.functional_area or "unknown"
        by_area.setdefault(area, []).append(r)

    selected = []
    for area_roles in by_area.values():
        selected.extend(area_roles[:2])
    selected = selected[:max_jds]

    successful = 0
    failed = 0

    for i, role in enumerate(selected):
        if i > 0:
            time.sleep(delay)

        logger.info(f"Extracting JD {i+1}/{len(selected)}: {role.role_title} -> {role.source_url}")
        text = extract_single_jd(role.source_url)

        if text and len(text) >= 50:
            role.role_description = text
            successful += 1
        else:
            failed += 1

    db.commit()

    return {
        "total_attempted": len(selected),
        "successful": successful,
        "failed": failed,
        "total_roles_available": len(roles),
    }

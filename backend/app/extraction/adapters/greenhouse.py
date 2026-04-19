"""Greenhouse ATS adapter.

Public API docs: https://developers.greenhouse.io/job-board.html

Key endpoints:
  - Board info:  GET https://boards-api.greenhouse.io/v1/boards/{slug}
  - All jobs:    GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
  - With content: append ?content=true for descriptions

The slug is typically the domain prefix or a slugified company name.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.extraction.adapters.base import BaseATSAdapter, slugify_company
from app.extraction.constants import ATSPlatform, ExtractionStrategy, ReasonCode
from app.extraction.schemas import NormalizedJob, NormalizedJobsResult
from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseAdapter(BaseATSAdapter):

    platform = ATSPlatform.GREENHOUSE

    # ── Detection ───────────────────────────────────────────────────

    def detect(self, html: str) -> bool:
        return bool(
            re.search(r"boards\.greenhouse\.io|greenhouse\.io/embed", html, re.I)
        )

    # ── Endpoint resolution ─────────────────────────────────────────

    def resolve_endpoint(
        self, domain: str, company_name: Optional[str] = None
    ) -> Optional[str]:
        slugs = slugify_company(company_name or "", domain)

        for slug in slugs:
            url = f"{BASE_URL}/{slug}/jobs"
            data = self._get_json(url)
            if data is not None and isinstance(data, dict) and "jobs" in data:
                logger.info(
                    f"[Greenhouse] Resolved endpoint: {url} "
                    f"(slug={slug}, jobs={len(data['jobs'])})"
                )
                return url

        logger.debug(
            f"[Greenhouse] No valid endpoint for {domain} "
            f"(tried slugs: {slugs})"
        )
        return None

    # ── Fetch ───────────────────────────────────────────────────────

    def fetch_jobs(self, api_url: str) -> Optional[Dict[str, Any]]:
        # Append content=true to get description snippets
        url = api_url
        if "content=true" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}content=true"

        data = self._get_json(url, timeout=15)
        if data is None:
            return None

        if isinstance(data, dict) and "jobs" in data:
            return data
        return None

    # ── Parse ───────────────────────────────────────────────────────

    def parse_jobs(
        self, raw_data: Any, api_url: str, domain: str
    ) -> NormalizedJobsResult:
        jobs_raw: list = raw_data.get("jobs", [])
        total = raw_data.get("meta", {}).get("total") or len(jobs_raw)

        jobs: List[NormalizedJob] = []
        departments: set = set()
        locations: set = set()

        for j in jobs_raw:
            title = j.get("title")
            if not title:
                continue

            loc_obj = j.get("location", {})
            loc = loc_obj.get("name") if isinstance(loc_obj, dict) else None

            dept_list = j.get("departments", [])
            dept = dept_list[0].get("name") if dept_list else None

            desc = ""
            content = j.get("content", "")
            if content:
                # Strip HTML tags for snippet
                desc = re.sub(r"<[^>]+>", " ", content)
                desc = re.sub(r"\s+", " ", desc).strip()[:200]

            job_url = j.get("absolute_url")

            jobs.append(NormalizedJob(
                title=title,
                location=loc,
                department=dept,
                job_url=job_url,
                description_snippet=desc or None,
            ))

            if dept:
                departments.add(dept)
            if loc:
                locations.add(loc)

        quality = "high" if len(jobs) >= 5 else "moderate" if len(jobs) >= 1 else "none"
        confidence = 0.95 if len(jobs) >= 5 else 0.8 if len(jobs) >= 1 else 0.0

        return NormalizedJobsResult(
            domain=domain,
            careers_url=api_url,
            ats_platform=self.platform.value,
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
            open_positions_count=int(total) if total else len(jobs),
            jobs=jobs,
            hiring_areas=sorted(departments),
            locations=sorted(locations),
            evidence_quality=quality,
            confidence=confidence,
        )

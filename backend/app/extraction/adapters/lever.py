"""Lever ATS adapter.

Public API (no auth required for public postings):
  - All postings: GET https://api.lever.co/v0/postings/{slug}?mode=json
  - Returns a flat JSON array of posting objects.

The slug is typically the domain prefix or company name slug.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.extraction.adapters.base import BaseATSAdapter, slugify_company
from app.extraction.constants import ATSPlatform, ExtractionStrategy, ReasonCode
from app.extraction.schemas import NormalizedJob, NormalizedJobsResult
from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.lever.co/v0/postings"


class LeverAdapter(BaseATSAdapter):

    platform = ATSPlatform.LEVER

    # ── Detection ───────────────────────────────────────────────────

    def detect(self, html: str) -> bool:
        return bool(
            re.search(r"jobs\.lever\.co|lever\.co/embed", html, re.I)
        )

    # ── Endpoint resolution ─────────────────────────────────────────

    def resolve_endpoint(
        self, domain: str, company_name: Optional[str] = None
    ) -> Optional[str]:
        slugs = slugify_company(company_name or "", domain)

        for slug in slugs:
            url = f"{BASE_URL}/{slug}?mode=json"
            data = self._get_json(url)
            if data is not None and isinstance(data, list):
                logger.info(
                    f"[Lever] Resolved endpoint: {url} "
                    f"(slug={slug}, jobs={len(data)})"
                )
                return url

        logger.debug(
            f"[Lever] No valid endpoint for {domain} "
            f"(tried slugs: {slugs})"
        )
        return None

    # ── Fetch ─────────���───────────────────────────���─────────────────

    def fetch_jobs(self, api_url: str) -> Optional[Any]:
        data = self._get_json(api_url, timeout=15)
        if data is None:
            return None
        # Lever returns a list directly
        if isinstance(data, list):
            return data
        return None

    # ── Parse ───────────────────────────────────────────────────────

    def parse_jobs(
        self, raw_data: Any, api_url: str, domain: str
    ) -> NormalizedJobsResult:
        postings: list = raw_data if isinstance(raw_data, list) else []

        jobs: List[NormalizedJob] = []
        departments: set = set()
        locations: set = set()

        for p in postings:
            title = p.get("text")
            if not title:
                continue

            # Location
            loc = None
            categories = p.get("categories", {})
            if isinstance(categories, dict):
                loc = categories.get("location")
                dept = categories.get("team") or categories.get("department")
            else:
                dept = None

            # Description snippet from descriptionPlain
            desc = (p.get("descriptionPlain") or "")[:200].strip() or None

            job_url = p.get("hostedUrl") or p.get("applyUrl")

            jobs.append(NormalizedJob(
                title=title,
                location=loc,
                department=dept,
                job_url=job_url,
                description_snippet=desc,
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
            open_positions_count=len(postings),
            jobs=jobs,
            hiring_areas=sorted(departments),
            locations=sorted(locations),
            evidence_quality=quality,
            confidence=confidence,
        )

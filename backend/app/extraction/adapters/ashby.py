"""Ashby ATS adapter.

Ashby uses a non-user GraphQL endpoint for public job boards:
  POST https://jobs.ashbyhq.com/api/non-user-graphql
  Body: {"operationName": "ApiJobBoardWithTeams", "variables": {"organizationHostedJobsPageName": "{slug}"}}

The response contains job postings, departments, and locations.
The slug matches the path in jobs.ashbyhq.com/{slug}.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.extraction.adapters.base import BaseATSAdapter, slugify_company, DEFAULT_TIMEOUT
from app.extraction.constants import ATSPlatform, ExtractionStrategy, ReasonCode
from app.extraction.schemas import NormalizedJob, NormalizedJobsResult
from app.core.logging import get_logger
from app.core.security import get_ssl_verify

logger = get_logger(__name__)

GRAPHQL_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"

QUERY_PAYLOAD = {
    "operationName": "ApiJobBoardWithTeams",
    "variables": {},
    "query": """
        query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
            jobBoard: jobBoardWithTeams(
                organizationHostedJobsPageName: $organizationHostedJobsPageName
            ) {
                teams {
                    id
                    name
                    parentTeamId
                }
                jobPostings {
                    id
                    title
                    teamId
                    locationName
                    employmentType
                    secondaryLocations {
                        locationName
                    }
                }
            }
        }
    """,
}


class AshbyAdapter(BaseATSAdapter):

    platform = ATSPlatform.ASHBY

    # ── Detection ───────────────────────────────────────────────────

    def detect(self, html: str) -> bool:
        return bool(re.search(r"ashbyhq\.com", html, re.I))

    # ── Endpoint resolution ─────────────────────────────────────────

    def resolve_endpoint(
        self, domain: str, company_name: Optional[str] = None
    ) -> Optional[str]:
        slugs = slugify_company(company_name or "", domain)

        for slug in slugs:
            data = self._ashby_query(slug)
            if data is not None:
                logger.info(
                    f"[Ashby] Resolved endpoint for slug={slug}"
                )
                # Return the slug as the "URL" — Ashby uses POST, not GET
                return slug

        logger.debug(
            f"[Ashby] No valid endpoint for {domain} "
            f"(tried slugs: {slugs})"
        )
        return None

    # ── Fetch ───────────────────────────────────────────────────────

    def fetch_jobs(self, api_url: str) -> Optional[Dict[str, Any]]:
        # api_url is actually the slug for Ashby
        return self._ashby_query(api_url)

    # ── Parse ���──────────────────────────────────────────────────────

    def parse_jobs(
        self, raw_data: Any, api_url: str, domain: str
    ) -> NormalizedJobsResult:
        teams: list = []
        postings: list = []
        try:
            teams = raw_data["data"]["jobBoard"]["teams"] or []
            postings = raw_data["data"]["jobBoard"]["jobPostings"] or []
        except (KeyError, TypeError):
            pass

        team_name_by_id = {t.get("id"): t.get("name", "") for t in teams if t.get("id")}

        jobs: List[NormalizedJob] = []
        departments: set = set()
        locations: set = set()

        for j in postings:
            title = j.get("title")
            if not title:
                continue

            team_name = team_name_by_id.get(j.get("teamId"), "")
            if team_name:
                departments.add(team_name)

            loc = j.get("locationName")
            job_url = f"https://jobs.ashbyhq.com/{api_url}/{j['id']}" if j.get("id") else None

            jobs.append(NormalizedJob(
                title=title,
                location=loc,
                department=team_name or None,
                job_url=job_url,
            ))

            if loc:
                locations.add(loc)

        quality = "high" if len(jobs) >= 5 else "moderate" if len(jobs) >= 1 else "none"
        confidence = 0.95 if len(jobs) >= 5 else 0.8 if len(jobs) >= 1 else 0.0

        return NormalizedJobsResult(
            domain=domain,
            careers_url=f"https://jobs.ashbyhq.com/{api_url}",
            ats_platform=self.platform.value,
            strategy_used=ExtractionStrategy.ATS_API,
            reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
            open_positions_count=len(jobs),
            jobs=jobs,
            hiring_areas=sorted(departments),
            locations=sorted(locations),
            evidence_quality=quality,
            confidence=confidence,
        )

    # ── Ashby-specific helper ───────────────────────────────────────

    def _ashby_query(self, slug: str) -> Optional[Dict[str, Any]]:
        """Execute the Ashby GraphQL query for a given slug."""
        payload = dict(QUERY_PAYLOAD)
        payload["variables"] = {
            "organizationHostedJobsPageName": slug,
        }

        try:
            data = self._post_json(GRAPHQL_URL, payload, timeout=DEFAULT_TIMEOUT)
            if data is None:
                return None

            # Validate the slug resolved to a real job board. An empty board
            # is still a valid resolution — only missing jobBoard means the
            # slug was wrong.
            job_board = data.get("data", {}).get("jobBoard")
            if job_board is None:
                return None

            return data

        except Exception as exc:
            logger.debug(f"[Ashby] GraphQL query failed for slug={slug}: {exc}")
            return None

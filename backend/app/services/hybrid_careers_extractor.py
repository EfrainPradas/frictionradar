import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass

from bs4 import BeautifulSoup
from app.schemas.careers_page import (
    CareersPageExtraction,
    CareersPageSignals,
    VisibleJobCard,
    AREA_KEYWORDS,
    HIGH_VOLUME_THRESHOLD,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HybridExtractionResult:
    page_type: str = "unknown"
    open_positions_count: Optional[int] = None
    visible_hiring_areas: List[str] = None
    visible_role_cards: List[VisibleJobCard] = None
    visible_locations: List[str] = None
    evidence_quality: str = "unknown"
    what_is_clearly_visible: List[str] = None
    what_is_still_unclear: List[str] = None

    source_of_truth: str = "unknown"
    source_details: str = ""

    raw_api_data: Optional[Dict[str, Any]] = None
    raw_embedded_json: Optional[Dict[str, Any]] = None


class HybridCareersExtractor:
    """Hybrid extraction strategy that prioritizes structured sources."""

    def __init__(self):
        pass

    async def extract(
        self,
        rendered_html: str,
        visible_text: str,
        visible_links: List[Dict[str, str]],
        network_requests: List[Dict[str, Any]],
        network_responses: List[Dict[str, Any]],
        embedded_json: List[Dict[str, Any]],
        page_state: Optional[Dict[str, Any]],
        source_url: str,
        preload_state: Optional[Dict[str, Any]] = None,
    ) -> HybridExtractionResult:
        """Extract using hybrid strategy in priority order."""

        result = HybridExtractionResult(
            visible_hiring_areas=[],
            visible_role_cards=[],
            what_is_clearly_visible=[],
            what_is_still_unclear=[],
        )

        extracted_from_api = self._try_api_extraction(
            network_responses, network_requests
        )

        if extracted_from_api:
            self._apply_extraction(result, extracted_from_api)
            result.source_of_truth = "api"
            result.source_details = f"Extracted from API responses: {len(network_responses)} responses analyzed"

            if result.open_positions_count:
                return result

        extracted_from_json = self._try_embedded_json_extraction(
            embedded_json, page_state, rendered_html, preload_state
        )

        if extracted_from_json:
            if not result.open_positions_count and extracted_from_json.get(
                "open_positions_count"
            ):
                result.open_positions_count = extracted_from_json[
                    "open_positions_count"
                ]

            if not result.visible_hiring_areas and extracted_from_json.get(
                "visible_hiring_areas"
            ):
                result.visible_hiring_areas = extracted_from_json[
                    "visible_hiring_areas"
                ]

            if not result.visible_role_cards and extracted_from_json.get(
                "visible_role_cards"
            ):
                result.visible_role_cards = extracted_from_json["visible_role_cards"]

            if result.source_of_truth == "unknown":
                result.source_of_truth = "embedded_json"
                result.source_details = (
                    f"Extracted from embedded JSON: {len(embedded_json)} sources"
                )
            else:
                result.source_of_truth = "api+embedded_json"
                result.source_details += (
                    f" + embedded JSON: {len(embedded_json)} sources"
                )

        extracted_from_dom = self._try_dom_extraction(
            rendered_html, visible_text, visible_links
        )

        if extracted_from_dom:
            if not result.open_positions_count:
                result.open_positions_count = extracted_from_dom.get(
                    "open_positions_count"
                )

            if not result.visible_hiring_areas:
                result.visible_hiring_areas = extracted_from_dom.get(
                    "visible_hiring_areas", []
                )

            if not result.visible_role_cards:
                result.visible_role_cards = extracted_from_dom.get(
                    "visible_role_cards", []
                )

            if result.source_of_truth == "unknown":
                result.source_of_truth = "dom"
                result.source_details = "Extracted from DOM parsing"
            else:
                result.source_of_truth = result.source_of_truth + "+dom"
                result.source_details += " + DOM fallback"

            result.raw_embedded_json = extracted_from_dom.get("raw_data")

        result.page_type = self._determine_page_type(
            visible_text, rendered_html, result.visible_role_cards
        )
        result.visible_locations = self._extract_locations(result.visible_role_cards)
        result.evidence_quality = self._assess_quality(result)
        result.what_is_clearly_visible = self._build_visible_list(result)
        result.what_is_still_unclear = self._build_unclear_list(result)

        return result

    def _try_api_extraction(
        self,
        network_responses: List[Dict[str, Any]],
        network_requests: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Try to extract from API responses captured by Playwright."""

        result = {
            "open_positions_count": None,
            "visible_hiring_areas": [],
            "visible_role_cards": [],
        }

        for resp in network_responses:
            url = resp.get("url", "")
            content_type = resp.get("content_type", "")
            body = resp.get("body", "")

            # Only look at JSON responses
            if "json" not in content_type or not body:
                continue

            url_lower = url.lower()

            try:
                data = json.loads(body)
                if not isinstance(data, dict):
                    # Could be a list of jobs
                    if isinstance(data, list) and len(data) > 0:
                        count = len(data)
                        if count > (result["open_positions_count"] or 0):
                            result["open_positions_count"] = count
                        for job in data[:20]:
                            title = None
                            loc = None
                            if isinstance(job, dict):
                                title = job.get("title") or job.get("name") or job.get("text")
                                loc = job.get("location") or job.get("office") or job.get("city")
                            if title:
                                result["visible_role_cards"].append(
                                    VisibleJobCard(title=title, location=loc)
                                )
                    continue

                # Look for total count in common API patterns
                # Greenhouse: { "jobs": [...], "meta": { "total": N } }
                # Lever: { "data": [...] }
                # Generic: { "total": N, "count": N, "results": [...] }

                # Try to find count in top-level fields
                for count_key in ["total", "count", "total_count", "num_results", "totalCount"]:
                    val = data.get(count_key)
                    if isinstance(val, (int, float)) and val > (result["open_positions_count"] or 0):
                        result["open_positions_count"] = int(val)
                        break

                # Check meta.total (Greenhouse pattern)
                meta = data.get("meta", {})
                if isinstance(meta, dict):
                    total = meta.get("total")
                    if isinstance(total, (int, float)) and total > (result["open_positions_count"] or 0):
                        result["open_positions_count"] = int(total)

                # Check pagination
                for pag_key in ["pagination", "paging"]:
                    pag = data.get(pag_key, {})
                    if isinstance(pag, dict):
                        total = pag.get("totalCount") or pag.get("total") or pag.get("total_count")
                        if isinstance(total, (int, float)) and total > (result["open_positions_count"] or 0):
                            result["open_positions_count"] = int(total)

                # Extract jobs list
                jobs = []
                for jobs_key in ["jobs", "data", "results", "positions", "items", "openings"]:
                    jobs_list = data.get(jobs_key)
                    if isinstance(jobs_list, list) and len(jobs_list) > 0:
                        if len(jobs_list) > len(jobs):
                            jobs = jobs_list
                        break

                for job in jobs[:20]:
                    if not isinstance(job, dict):
                        continue
                    title = (
                        job.get("title") or job.get("name") or job.get("text") or job.get("jobTitle")
                    )
                    loc = (
                        job.get("location") or job.get("office") or job.get("city")
                        or job.get("jobLocation", {}).get("name") if isinstance(job.get("jobLocation"), dict) else None
                    )
                    dept = job.get("department") or job.get("category") or job.get("team")
                    job_url = job.get("absolute_url") or job.get("url") or job.get("applyUrl")

                    if title:
                        result["visible_role_cards"].append(
                            VisibleJobCard(title=title, location=loc, area=dept, job_url=job_url)
                        )

                # Extract departments/categories
                departments = data.get("departments", [])
                if isinstance(departments, list):
                    for dept in departments:
                        if isinstance(dept, dict):
                            name = dept.get("name")
                            if name:
                                result["visible_hiring_areas"].append(name)

                result["source"] = "api"

            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        if result.get("open_positions_count") or result.get("visible_role_cards") or result.get("visible_hiring_areas"):
            return result

        return None

    def _try_embedded_json_extraction(
        self,
        embedded_json: List[Dict[str, Any]],
        page_state: Optional[Dict[str, Any]],
        rendered_html: str,
        preload_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Try to extract from embedded JSON in the page."""

        if preload_state:
            result = self._extract_from_preload_state(preload_state)
            if result:
                return result

        soup = BeautifulSoup(rendered_html, "html.parser")

        ld_json_scripts = soup.find_all("script", type="application/ld+json")
        for script in ld_json_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    result = self._parse_ld_json(data)
                    if result:
                        return result
            except:
                continue

        for ej in embedded_json:
            source = ej.get("source", "")
            keys = ej.get("keys", [])

            if (
                "job" in str(keys).lower()
                or "position" in str(keys).lower()
                or "total" in str(keys).lower()
            ):
                return {"source": source, "keys": keys}

        return None

    def _parse_ld_json(self, data: dict) -> Optional[Dict[str, Any]]:
        """Parse JSON-LD structured data."""

        if isinstance(data, list):
            for item in data:
                result = self._parse_ld_json(item)
                if result:
                    return result

        if not isinstance(data, dict):
            return None

        if data.get("@type") in ["JobPosting", "JobPostingList"]:
            return {
                "job_postings": [data]
                if data.get("@type") == "JobPosting"
                else data.get("itemListElement", [])
            }

        if "numberOfJobs" in data:
            return {"open_positions_count": data["numberOfJobs"]}

        return None

    def _extract_from_preload_state(
        self, preload_state: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract data from __PRELOAD_STATE__ (e.g., Nike)."""

        result = {
            "open_positions_count": None,
            "visible_hiring_areas": [],
            "visible_role_cards": [],
        }

        if "jobSearch" in preload_state:
            job_search = preload_state["jobSearch"]

            if "totalJob" in job_search:
                result["open_positions_count"] = job_search["totalJob"]

            if "jobs" in job_search:
                jobs = job_search["jobs"]
                for job in jobs[:20]:
                    if isinstance(job, dict):
                        title = job.get("title")
                        location = None
                        if job.get("locations") and isinstance(job["locations"], list):
                            loc = job["locations"][0]
                            location = (
                                loc.get("cityState")
                                or loc.get("city")
                                or loc.get("locationText")
                            )

                        area = None
                        if job.get("jobCardExtraFields"):
                            for field in job["jobCardExtraFields"]:
                                if field.get(
                                    "attribute_name"
                                ) == "job_categories" and field.get("value"):
                                    area = (
                                        field["value"][0]
                                        if isinstance(field["value"], list)
                                        else field["value"]
                                    )

                        job_url = job.get("applyURL") or job.get("originalURL")

                        if title:
                            result["visible_role_cards"].append(
                                VisibleJobCard(
                                    title=title,
                                    location=location,
                                    area=area,
                                    job_url=job_url,
                                )
                            )

            if "facets" in job_search and isinstance(job_search["facets"], list):
                for facet in job_search["facets"]:
                    if isinstance(facet, dict):
                        alias = facet.get("alias", "")
                        if alias == "Career Areas":
                            buckets = facet.get("facet_field_keyvalue", [])
                            for bucket in buckets[:10]:
                                if isinstance(bucket, dict):
                                    name = bucket.get("custom_value", "") or bucket.get(
                                        "original_value", ""
                                    )
                                    count = bucket.get("doc_count", 0)
                                    if (
                                        name
                                        and count > 0
                                        and name not in result["visible_hiring_areas"]
                                    ):
                                        result["visible_hiring_areas"].append(name)

        if result["open_positions_count"] or result["visible_role_cards"]:
            return result

        return None

    def _try_dom_extraction(
        self,
        rendered_html: str,
        visible_text: str,
        visible_links: List[Dict[str, str]],
    ) -> Optional[Dict[str, Any]]:
        """Fallback: extract from DOM (HTML, text, links)."""

        result = {
            "open_positions_count": None,
            "visible_hiring_areas": [],
            "visible_role_cards": [],
            "raw_data": None,
        }

        result["open_positions_count"] = self._find_position_count(visible_text)

        result["visible_hiring_areas"] = self._find_hiring_areas(
            visible_text, rendered_html
        )

        result["visible_role_cards"] = self._extract_job_cards(
            rendered_html, visible_links
        )

        return result

    def _find_position_count(self, text: str) -> Optional[int]:
        """Find position count from visible text."""

        text_lower = text.lower()

        patterns = [
            r"(\d{3,4})\s*(?:open\s*)?positions?",
            r"(\d{3,4})\s*(?:total\s*)?(?:jobs?|roles?)",
            r"of\s+(\d{3,4})\s*(?:jobs?|positions?)",
            r"(\d{3,4})\s*available",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                try:
                    num = int(match)
                    if 100 <= num <= 50000:
                        return num
                except:
                    continue

        return None

    def _find_hiring_areas(self, text: str, html: str) -> List[str]:
        """Extract hiring areas from text and HTML."""

        areas = []
        text_lower = text.lower()

        for area_name, keywords in AREA_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    area_label = area_name.replace("_", " ").title()
                    if area_label not in areas:
                        areas.append(area_label)

        soup = BeautifulSoup(html, "html.parser")

        for elem in soup.find_all(["button", "a", "li", "span", "div"]):
            text_content = elem.get_text(strip=True)
            if text_content and 2 < len(text_content) < 50:
                for area_name, keywords in AREA_KEYWORDS.items():
                    if any(kw in text_content.lower() for kw in keywords):
                        area_label = area_name.replace("_", " ").title()
                        if area_label not in areas:
                            areas.append(area_label)

        return areas[:10]

    def _extract_job_cards(
        self,
        rendered_html: str,
        visible_links: List[Dict[str, str]],
    ) -> List[VisibleJobCard]:
        """Extract visible job cards from DOM."""

        job_cards = []
        seen_titles = set()

        soup = BeautifulSoup(rendered_html, "html.parser")

        job_selectors = [
            {
                "class": lambda x: (
                    x and any(t in str(x).lower() for t in ["job", "card", "listing"])
                )
            },
            {"data-testid": lambda x: x and "job" in str(x).lower()},
            {"role": "article"},
        ]

        for selector in job_selectors:
            for card in soup.find_all("div", selector)[:30]:
                card_text = card.get_text(separator=" ", strip=True)
                if not card_text or len(card_text) < 10:
                    continue

                title = self._extract_title_from_card(card_text, card)
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                location = self._extract_location_from_card(card_text)
                area = self._extract_area_from_text(title)

                link_elem = card.find("a", href=True)
                job_url = None
                if link_elem:
                    job_url = link_elem.get("href", "")
                    if job_url and not job_url.startswith("http"):
                        job_url = None

                if not job_url:
                    for link in visible_links:
                        if title.lower() in link.get("text", "").lower():
                            job_url = link.get("href", "")
                            break

                job_cards.append(
                    VisibleJobCard(
                        title=title,
                        location=location,
                        area=area,
                        job_url=job_url,
                    )
                )

                if len(job_cards) >= 20:
                    break
            if len(job_cards) >= 20:
                break

        return job_cards

    def _extract_title_from_card(self, text: str, element) -> Optional[str]:
        heading = element.find(["h1", "h2", "h3", "h4"])
        if heading:
            title = heading.get_text(strip=True)
            if 5 < len(title) < 150:
                return title

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines[:3]:
            if 10 < len(line) < 100 and not line.isdigit():
                return line

        return None

    def _extract_location_from_card(self, text: str) -> Optional[str]:
        patterns = [
            r"([A-Z][a-z]+(?:[\s,][A-Z][a-z]+){0,3},\s*[A-Z]{2})",
            r"(?:location)[:\s]*([^-]+?)(?:\||$)",
            r"(remote|hybrid|on-site)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_area_from_text(self, text: str) -> Optional[str]:
        # Produces a free-text department hint for CompanyJobRole.role_department.
        # NOT the canonical functional_area — that is assigned by
        # role_ingest.classify_title from the role title at persistence time.
        text_lower = text.lower()
        for area_name, keywords in AREA_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return area_name.replace("_", " ").title()
        return None

    def _extract_locations(self, job_cards: List[VisibleJobCard]) -> List[str]:
        locations = []
        for card in job_cards:
            if card.location and card.location not in locations:
                locations.append(card.location)
        return locations[:10]

    def _determine_page_type(
        self, text: str, rendered_html: str, job_cards: List[VisibleJobCard]
    ) -> str:
        text_lower = text.lower()
        html_lower = rendered_html.lower()

        if job_cards and len(job_cards) >= 3:
            if any(
                ats in html_lower
                for ats in [
                    "lever.co",
                    "greenhouse.io",
                    "workday.com",
                    "myworkdayjobs.com",
                ]
            ):
                return "ats_platform"
            return "careers_listing"

        if "search" in text_lower and "filter" in text_lower:
            return "jobs_search"

        return "unknown"

    def _assess_quality(self, result: HybridExtractionResult) -> str:
        score = 0

        if result.open_positions_count and result.open_positions_count > 0:
            score += 2
        if result.visible_role_cards and len(result.visible_role_cards) >= 5:
            score += 2
        elif result.visible_role_cards and len(result.visible_role_cards) >= 1:
            score += 1
        if result.visible_hiring_areas and len(result.visible_hiring_areas) >= 2:
            score += 2
        elif result.visible_hiring_areas and len(result.visible_hiring_areas) >= 1:
            score += 1

        if score >= 5:
            return "high"
        elif score >= 3:
            return "moderate"
        elif score >= 1:
            return "limited"
        return "none"

    def _build_visible_list(self, result: HybridExtractionResult) -> List[str]:
        visible = []

        if result.open_positions_count:
            visible.append(
                f"Open positions count visible: {result.open_positions_count}"
            )

        if result.visible_role_cards and len(result.visible_role_cards) > 0:
            visible.append(
                f"Job cards visible: {len(result.visible_role_cards)} listings"
            )

        if result.visible_hiring_areas and len(result.visible_hiring_areas) > 0:
            visible.append(
                f"Hiring areas visible: {', '.join(result.visible_hiring_areas[:3])}"
            )

        return visible

    def _build_unclear_list(self, result: HybridExtractionResult) -> List[str]:
        unclear = []

        if not result.open_positions_count:
            unclear.append("Open positions count not found")

        if not result.visible_role_cards or len(result.visible_role_cards) == 0:
            unclear.append("No job cards extracted")

        unclear.append("Job descriptions not parsed yet")

        return unclear

    def _apply_extraction(self, result: HybridExtractionResult, data: Dict[str, Any]):
        """Apply extracted data to result object."""

        if data.get("open_positions_count"):
            result.open_positions_count = data["open_positions_count"]

        if data.get("visible_hiring_areas"):
            result.visible_hiring_areas = data["visible_hiring_areas"]

        if data.get("visible_role_cards"):
            result.visible_role_cards = data["visible_role_cards"]


hybrid_careers_extractor = HybridCareersExtractor()

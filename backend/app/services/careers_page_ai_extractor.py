import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
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


class CareersPageAIExtractor:
    """AI extraction layer for careers pages.

    This service provides a structured interface for extracting careers page
    information. It can integrate with LLMs for AI extraction, but falls back
    to deterministic extraction when AI is unavailable or fails.
    """

    def __init__(self):
        self.ai_enabled = False

    async def extract(
        self,
        rendered_html: str,
        visible_text: str,
        visible_links: List[Dict[str, str]],
        source_url: str,
        screenshot_bytes: Optional[bytes] = None,
    ) -> CareersPageExtraction:
        """Extract structured careers page data from rendered content.

        Args:
            rendered_html: The full rendered HTML from the browser
            visible_text: Extracted visible text from the page
            visible_links: List of visible links with href and text
            source_url: The original URL that was captured
            screenshot_bytes: Optional screenshot for potential AI analysis

        Returns:
            CareersPageExtraction with structured data
        """
        if self.ai_enabled and screenshot_bytes:
            try:
                result = await self._extract_with_ai(
                    visible_text, visible_links, source_url, screenshot_bytes
                )
                if result:
                    result.extraction_method = "ai"
                    return result
            except Exception as e:
                logger.warning(
                    f"AI extraction failed, falling back to deterministic: {e}"
                )

        result = self._extract_deterministic(
            rendered_html, visible_text, visible_links, source_url
        )
        result.extraction_method = "deterministic"
        return result

    async def _extract_with_ai(
        self,
        visible_text: str,
        visible_links: List[Dict[str, str]],
        source_url: str,
        screenshot_bytes: bytes,
    ) -> Optional[CareersPageExtraction]:
        return None

    def _extract_deterministic(
        self,
        rendered_html: str,
        visible_text: str,
        visible_links: List[Dict[str, str]],
        source_url: str,
    ) -> CareersPageExtraction:
        """Deterministic extraction fallback."""

        open_positions_count = self._find_open_positions_count(visible_text)

        visible_hiring_areas = self._find_visible_hiring_areas(
            visible_text, rendered_html
        )

        visible_role_cards = self._extract_visible_job_cards(
            visible_text, visible_links, rendered_html
        )

        visible_locations = self._extract_visible_locations(visible_role_cards)

        page_type = self._determine_page_type(
            visible_text, rendered_html, visible_role_cards
        )

        evidence_quality = self._assess_evidence_quality(
            open_positions_count, visible_role_cards, visible_hiring_areas
        )

        what_is_clearly_visible = self._build_visible_list(
            open_positions_count, visible_role_cards, visible_hiring_areas
        )

        what_is_still_unclear = self._build_unclear_list(
            open_positions_count, visible_role_cards
        )

        return CareersPageExtraction(
            page_type=page_type,
            open_positions_count=open_positions_count,
            visible_hiring_areas=visible_hiring_areas,
            visible_role_cards=visible_role_cards,
            visible_locations=visible_locations,
            evidence_quality=evidence_quality,
            what_is_clearly_visible=what_is_clearly_visible,
            what_is_still_unclear=what_is_still_unclear,
            source_url=source_url,
            captured_at=datetime.now(),
        )

    def _find_open_positions_count(self, text: str) -> Optional[int]:
        """Extract open positions count from visible text."""

        patterns = [
            r"(\d{1,3}(?:,\d{3})*)\s*(?:open\s*)?positions?",
            r"(\d+)\s*(?:available|open)\s*(?:jobs|positions|roles)",
            r"(\d+)\s*(?:job\s*)?openings?",
            r"(\d+)\s*opportunities?",
            r"we['\u2019]re\s+hiring\s+(\d+)",
            r"hiring\s+(\d+)",
            r"(\d+)\s*total\s*(?:jobs|positions)",
            r"(\d+)\s*available\s*roles?",
            r"(\d+)\s*jobs?\s*available",
            r"showing\s+(\d+)\s*(?:of\s+\d+)?\s*(?:jobs|positions)",
        ]

        text_lower = text.lower()

        for pattern in patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                try:
                    num_str = match.replace(",", "").strip()
                    num = int(num_str)
                    if 1 <= num <= 50000:
                        return num
                except (ValueError, AttributeError):
                    continue

        return None

    def _find_visible_hiring_areas(self, text: str, rendered_html: str) -> List[str]:
        """Extract visible hiring areas/categories from the page."""
        areas = []
        text_lower = text.lower()

        for area_name, keywords in AREA_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    area_label = area_name.replace("_", " ").title()
                    if area_label not in areas:
                        areas.append(area_label)
                    break

        soup = BeautifulSoup(rendered_html, "html.parser")

        tab_patterns = [
            (
                "button",
                {
                    "class": lambda x: (
                        x
                        and any(
                            t in str(x).lower() for t in ["tab", "filter", "category"]
                        )
                    )
                },
            ),
            (
                "a",
                {
                    "class": lambda x: (
                        x and any(t in str(x).lower() for t in ["tab", "filter", "nav"])
                    )
                },
            ),
            (
                "li",
                {
                    "class": lambda x: (
                        x and any(t in str(x).lower() for t in ["tab", "filter"])
                    )
                },
            ),
        ]

        for tag, attrs in tab_patterns:
            for elem in soup.find_all(tag, attrs):
                text_content = elem.get_text(strip=True)
                if text_content and len(text_content) > 2 and len(text_content) < 50:
                    for area_name, keywords in AREA_KEYWORDS.items():
                        if any(kw in text_content.lower() for kw in keywords):
                            area_label = area_name.replace("_", " ").title()
                            if area_label not in areas:
                                areas.append(area_label)

        return areas[:10]

    def _extract_visible_job_cards(
        self, text: str, links: List[Dict[str, str]], rendered_html: str
    ) -> List[VisibleJobCard]:
        """Extract up to 20 visible job cards from the page."""
        job_cards = []
        seen_titles = set()

        soup = BeautifulSoup(rendered_html, "html.parser")

        job_card_patterns = [
            {
                "class": lambda x: (
                    x
                    and any(
                        t in str(x).lower()
                        for t in ["job", "card", "listing", "position", "role"]
                    )
                )
            },
            {"data-testid": lambda x: x and "job" in str(x).lower()},
            {"role": lambda x: x and "article" in str(x).lower()},
        ]

        for pattern in job_card_patterns:
            for card in soup.find_all("div", pattern)[:30]:
                card_text = card.get_text(separator=" ", strip=True)
                if not card_text or len(card_text) < 10:
                    continue

                title = self._extract_job_title(card_text, card)
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                location = self._extract_location(card_text)
                area = self._extract_area(card_text)

                link_elem = card.find("a", href=True)
                job_url = None
                if link_elem:
                    job_url = link_elem.get("href", "")
                    if job_url and not job_url.startswith("http"):
                        job_url = None

                if not job_url:
                    for link in links:
                        if (
                            title.lower() in link.get("text", "").lower()
                            or link.get("text", "").lower() in title.lower()
                        ):
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

        if not job_cards:
            for link in links:
                link_text = link.get("text", "")
                if not link_text or len(link_text) < 5:
                    continue

                if any(kw in link_text.lower() for kw in ["job", "position", "role"]):
                    title = link_text.strip()
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)

                    job_url = link.get("href", "")

                    area = self._extract_area(title)

                    job_cards.append(
                        VisibleJobCard(
                            title=title,
                            area=area,
                            job_url=job_url,
                        )
                    )

                    if len(job_cards) >= 20:
                        break

        return job_cards

    def _extract_job_title(self, text: str, element) -> Optional[str]:
        title_patterns = [
            r"^([^-|]+(?:job|position|role)[^-|]+)",
            r"(?:job|position|role)[:\s]+([^-|]+)",
            r"^([A-Z][^-|]{5,60})",
        ]

        for pattern in title_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                if len(title) > 5 and len(title) < 100:
                    return title

        heading = element.find(["h1", "h2", "h3", "h4"])
        if heading:
            return heading.get_text(strip=True)

        return None

    def _extract_location(self, text: str) -> Optional[str]:
        location_patterns = [
            r"([A-Z][a-z]+(?:[\s,][A-Z][a-z]+){0,3},\s*[A-Z]{2})",
            r"(?:location|site)[:\s]*([^-]+?)(?:\||$)",
            r"([A-Z][a-z]+,\s*[A-Z]{2}\s*USA?)",
            r"(remote|hybrid|on-site)",
        ]

        for pattern in location_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_area(self, text: str) -> Optional[str]:
        # Produces a free-text department hint (e.g. "Retail", "Technology")
        # for CompanyJobRole.role_department. This is NOT the canonical
        # functional_area — that is assigned by role_ingest.classify_title
        # from the role title at persistence time.
        text_lower = text.lower()
        for area_name, keywords in AREA_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return area_name.replace("_", " ").title()
        return None

    def _extract_visible_locations(self, job_cards: List[VisibleJobCard]) -> List[str]:
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
                ats_domain in html_lower
                for ats_domain in [
                    "lever.co",
                    "greenhouse.io",
                    "workday.com",
                    "jobvite",
                    "bamboohr",
                ]
            ):
                return "ats_platform"
            return "careers_listing"

        if any(kw in text_lower for kw in ["search", "filter", "sort by"]):
            return "jobs_search"

        if "apply" in text_lower and "job" in text_lower:
            return "job_application"

        return "unknown"

    def _assess_evidence_quality(
        self,
        open_positions: Optional[int],
        job_cards: List[VisibleJobCard],
        areas: List[str],
    ) -> str:
        score = 0

        if open_positions and open_positions > 0:
            score += 2
        if job_cards and len(job_cards) >= 5:
            score += 2
        elif job_cards and len(job_cards) >= 1:
            score += 1
        if areas and len(areas) >= 2:
            score += 2
        elif areas and len(areas) >= 1:
            score += 1

        if score >= 5:
            return "high"
        elif score >= 3:
            return "moderate"
        elif score >= 1:
            return "limited"
        return "none"

    def _build_visible_list(
        self,
        open_positions: Optional[int],
        job_cards: List[VisibleJobCard],
        areas: List[str],
    ) -> List[str]:
        visible = []

        if open_positions:
            visible.append(f"Open positions count is visible: {open_positions}")

        if job_cards and len(job_cards) > 0:
            visible.append(f"Job cards are visible: {len(job_cards)} listings")

        if areas and len(areas) > 0:
            visible.append(f"Hiring areas visible: {', '.join(areas[:3])}")

        return visible

    def _build_unclear_list(
        self, open_positions: Optional[int], job_cards: List[VisibleJobCard]
    ) -> List[str]:
        unclear = []

        if not open_positions:
            unclear.append("Open positions count not found")

        if not job_cards or len(job_cards) == 0:
            unclear.append("No job cards extracted")

        unclear.append("Job descriptions not parsed yet")

        return unclear

    def extract_signals(self, extraction: CareersPageExtraction) -> CareersPageSignals:
        """Extract signals from the careers page extraction."""
        signals = CareersPageSignals()

        if extraction.open_positions_count:
            signals.open_positions_count_detected = True
            if extraction.open_positions_count >= HIGH_VOLUME_THRESHOLD:
                signals.high_open_positions_count_detected = True

        if extraction.visible_role_cards and len(extraction.visible_role_cards) > 0:
            signals.job_cards_visible_detected = True

        if extraction.visible_hiring_areas and len(extraction.visible_hiring_areas) > 0:
            signals.visible_hiring_area_detected = True

        if any(card.job_url for card in extraction.visible_role_cards):
            signals.job_links_extracted = True

        for area in extraction.visible_hiring_areas:
            area_lower = area.lower()
            for area_name in AREA_KEYWORDS.keys():
                if any(kw in area_lower for kw in AREA_KEYWORDS[area_name]):
                    setattr(signals, f"{area_name}_hiring_detected", True)
                    break

        return signals


careers_page_ai_extractor = CareersPageAIExtractor()

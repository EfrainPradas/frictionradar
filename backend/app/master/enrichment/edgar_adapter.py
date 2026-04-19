"""SEC EDGAR enrichment adapter.

Uses the EDGAR full-text search API to find CIK numbers and SIC codes
for companies by name. The EDGAR API is public and free.

API: https://efts.sec.gov/LATEST/search-index?q="{company_name}"&dateRange=custom&startdt=2020-01-01
Simpler: https://www.sec.gov/cgi-bin/browse-edgar?company={name}&CIK=&type=10-K&dateb=&owner=include&count=10&search_text=&action=getcompany

We use the EFTS (full-text search) JSON API which returns structured results.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from app.master.canonical import normalize_company_name
from app.master.models import CompanyMaster

from .base import Authority, EnrichmentResult, IdType, IdentifierMatch

# EDGAR EFTS JSON API
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_COMPANY_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

TIMEOUT = 15
USER_AGENT = "FrictionRadar/1.0 (research@frictionradar.com)"


class EdgarAdapter:
    """Enrich companies with SEC EDGAR CIK and SIC codes.

    Strategy:
      1. Search EDGAR company database by name
      2. Match results against our normalized name
      3. Return CIK + SIC code if confidence is sufficient
    """

    def name(self) -> str:
        return "sec_edgar"

    def supports_bulk(self) -> bool:
        return False

    def enrich(self, db: Session, master: CompanyMaster) -> EnrichmentResult:
        result = EnrichmentResult(
            master_id=str(master.id),
            company_name=master.legal_name,
            source_name=self.name(),
        )

        try:
            matches = self._search_edgar(master.legal_name, master.normalized_name)
            result.identifiers = matches
        except Exception as e:
            result.error = f"{type(e).__name__}: {str(e)[:200]}"

        return result

    def _search_edgar(
        self, legal_name: str, normalized_name: str
    ) -> list[IdentifierMatch]:
        """Search EDGAR company database and return matching identifiers."""
        # Use the company search endpoint
        params = {
            "company": legal_name,
            "CIK": "",
            "type": "10-K",
            "dateb": "",
            "owner": "include",
            "count": "10",
            "search_text": "",
            "action": "getcompany",
            "output": "atom",
        }

        resp = requests.get(
            EDGAR_COMPANY_URL,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml"},
            timeout=TIMEOUT,
        )

        if resp.status_code != 200:
            return []

        return self._parse_atom_response(resp.text, normalized_name)

    def _parse_atom_response(
        self, xml_text: str, normalized_name: str
    ) -> list[IdentifierMatch]:
        """Parse EDGAR Atom XML response for CIK matches."""
        identifiers = []

        # Extract company entries from Atom XML
        # Format: <company-name>NAME</company-name> ... <CIK>0001234567</CIK>
        entries = re.findall(
            r"<company-name>([^<]+)</company-name>.*?<CIK>([^<]+)</CIK>"
            r"(?:.*?<SIC>([^<]+)</SIC>)?",
            xml_text,
            re.DOTALL,
        )

        for edgar_name, cik, sic in entries:
            edgar_normalized = normalize_company_name(edgar_name.strip())
            similarity = _name_similarity(normalized_name, edgar_normalized)

            if similarity < 0.60:
                continue

            # CIK
            confidence = min(similarity, 0.95)
            identifiers.append(IdentifierMatch(
                id_type=IdType.EDGAR_CIK,
                id_value=cik.strip().lstrip("0") or "0",
                issuing_authority=Authority.SEC,
                confidence=confidence,
                source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik.strip()}&type=10-K",
            ))

            # SIC code if present
            if sic:
                identifiers.append(IdentifierMatch(
                    id_type=IdType.SIC_CODE,
                    id_value=sic.strip(),
                    issuing_authority=Authority.SEC,
                    confidence=confidence,
                    source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik.strip()}&type=10-K",
                ))

            # Only take top match
            break

        return identifiers


def _name_similarity(a: str, b: str) -> float:
    """Token-based Jaccard similarity."""
    if not a or not b:
        return 0.0
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

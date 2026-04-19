"""SAM.gov enrichment adapter.

Uses the SAM.gov Entity Management API to find UEI (Unique Entity Identifier)
for companies by name. The public API requires an API key from api.sam.gov.

API docs: https://open.gsa.gov/api/entity-api/

Note: Without an API key, this adapter will return empty results gracefully.
The interface is ready for when API access is configured.
"""

from __future__ import annotations

import os

import requests
from sqlalchemy.orm import Session

from app.master.canonical import normalize_company_name
from app.master.models import CompanyMaster

from .base import Authority, EnrichmentResult, IdType, IdentifierMatch

SAM_API_URL = "https://api.sam.gov/entity-information/v3/entities"
TIMEOUT = 15
USER_AGENT = "FrictionRadar/1.0"


class SamAdapter:
    """Enrich companies with SAM.gov UEI identifiers.

    Requires SAM_API_KEY environment variable. Without it, returns
    empty results (no error) — enrichment is optional.
    """

    def __init__(self):
        self.api_key = os.getenv("SAM_API_KEY", "")

    def name(self) -> str:
        return "sam_gov"

    def supports_bulk(self) -> bool:
        return False

    def is_available(self) -> bool:
        return bool(self.api_key)

    def enrich(self, db: Session, master: CompanyMaster) -> EnrichmentResult:
        result = EnrichmentResult(
            master_id=str(master.id),
            company_name=master.legal_name,
            source_name=self.name(),
        )

        if not self.api_key:
            # Gracefully skip — enrichment is optional
            return result

        try:
            matches = self._search_sam(master.legal_name, master.normalized_name)
            result.identifiers = matches
        except Exception as e:
            result.error = f"{type(e).__name__}: {str(e)[:200]}"

        return result

    def _search_sam(
        self, legal_name: str, normalized_name: str
    ) -> list[IdentifierMatch]:
        params = {
            "api_key": self.api_key,
            "legalBusinessName": legal_name,
            "registrationStatus": "A",  # Active
            "purposeOfRegistrationCode": "Z2",  # All
        }

        resp = requests.get(
            SAM_API_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )

        if resp.status_code != 200:
            return []

        data = resp.json()
        entities = data.get("entityData", [])
        if not entities:
            return []

        identifiers = []
        for entity in entities[:3]:  # top 3 matches
            reg = entity.get("entityRegistration", {})
            uei = reg.get("ueiSAM", "")
            sam_name = reg.get("legalBusinessName", "")

            if not uei:
                continue

            sam_normalized = normalize_company_name(sam_name)
            similarity = _name_similarity(normalized_name, sam_normalized)

            if similarity < 0.60:
                continue

            confidence = min(similarity, 0.90)

            identifiers.append(IdentifierMatch(
                id_type=IdType.SAM_UEI,
                id_value=uei,
                issuing_authority=Authority.GSA,
                confidence=confidence,
                source_url=f"https://sam.gov/entity/{uei}",
                raw_payload={
                    "legalBusinessName": sam_name,
                    "ueiSAM": uei,
                    "physicalAddress": reg.get("physicalAddress"),
                },
            ))

            # Also extract EIN if present (secondary only)
            core = entity.get("coreData", {})
            ein = core.get("entityInformation", {}).get("entityEINInformation", {}).get("entityEIN", "")
            if ein:
                identifiers.append(IdentifierMatch(
                    id_type=IdType.EIN,
                    id_value=ein,
                    issuing_authority=Authority.IRS,
                    confidence=confidence * 0.9,  # slightly lower — derived
                    source_url=f"https://sam.gov/entity/{uei}",
                ))

            break  # top match only

        return identifiers


def _name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

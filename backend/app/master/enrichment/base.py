"""Base interface and types for external identifier enrichment.

Every enrichment adapter implements EnrichmentAdapter and returns
EnrichmentResult objects. The orchestrator handles deduplication,
provenance, and persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from app.master.models import CompanyMaster


# ════════════════════════════════════════════════════════════════════
# Identifier types (canonical names used in company_external_ids.id_type)
# ════════════════════════════════════════════════════════════════════

class IdType:
    """Canonical identifier type names.

    Use these constants instead of raw strings to prevent typos.
    """
    EDGAR_CIK = "edgar_cik"               # SEC EDGAR Central Index Key
    SAM_UEI = "sam_uei"                    # SAM.gov Unique Entity Identifier
    EIN = "ein"                            # IRS Employer Identification Number (secondary only)
    STATE_REGISTRY_ID = "state_registry_id" # State Secretary of State filing number
    DUNS = "duns"                           # Dun & Bradstreet
    LEI = "lei"                            # Legal Entity Identifier
    TICKER = "ticker"                      # Stock ticker symbol
    SIC_CODE = "sic_code"                  # Standard Industrial Classification
    NAICS_CODE = "naics_code"              # North American Industry Classification


# Issuing authorities
class Authority:
    SEC = "SEC"
    GSA = "GSA"
    IRS = "IRS"
    DUNS_BRADSTREET = "D&B"


@dataclass
class IdentifierMatch:
    """A single external identifier found for a company."""
    id_type: str                    # from IdType constants
    id_value: str                   # the identifier value
    issuing_authority: str | None = None
    confidence: float = 0.0         # 0.0–1.0
    source_url: str | None = None   # where this was found
    raw_payload: dict | None = None # raw data from the source


@dataclass
class EnrichmentResult:
    """Result of enriching a single company."""
    master_id: str
    company_name: str
    identifiers: list[IdentifierMatch] = field(default_factory=list)
    error: str | None = None
    source_name: str = ""


class EnrichmentAdapter(Protocol):
    """Interface for external identifier enrichment sources.

    Implementations:
      - EdgarAdapter:       SEC EDGAR full-text search
      - SamAdapter:         SAM.gov entity search
      - ManualCsvAdapter:   bulk import from CSV/JSON files
      - StateRegistryAdapter: state SOS filing lookup (future)
    """

    def name(self) -> str:
        """Human-readable name of this source."""
        ...

    def enrich(self, db: Session, master: CompanyMaster) -> EnrichmentResult:
        """Look up external identifiers for a single company.

        Must not raise — return errors in EnrichmentResult.error instead.
        """
        ...

    def supports_bulk(self) -> bool:
        """Whether this adapter can process multiple companies at once."""
        ...

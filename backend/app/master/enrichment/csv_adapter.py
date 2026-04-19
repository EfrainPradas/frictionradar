"""Manual CSV/JSON bulk import adapter for external identifiers.

Supports bulk loading of identifiers from a structured file where
each row maps a company name/domain to one or more external IDs.

Expected CSV format:
    company_name,domain,id_type,id_value,issuing_authority
    "Stripe, Inc.",stripe.com,edgar_cik,1694028,SEC
    "Qualtrics International",qualtrics.com,edgar_cik,1747748,SEC

Expected JSON format:
    [
      {
        "company_name": "Stripe, Inc.",
        "domain": "stripe.com",
        "identifiers": [
          {"id_type": "edgar_cik", "id_value": "1694028", "issuing_authority": "SEC"}
        ]
      }
    ]
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.master.canonical import normalize_company_name
from app.master.models import CompanyMaster

from .base import EnrichmentResult, IdentifierMatch


class CsvAdapter:
    """Bulk import external identifiers from CSV or JSON files."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._data: list[dict[str, Any]] | None = None

    def name(self) -> str:
        return f"csv_import:{self.file_path.name}"

    def supports_bulk(self) -> bool:
        return True

    def load(self) -> list[dict[str, Any]]:
        """Load and parse the file. Call before enrich()."""
        if self._data is not None:
            return self._data

        suffix = self.file_path.suffix.lower()
        if suffix == ".json":
            self._data = self._load_json()
        elif suffix in (".csv", ".tsv"):
            self._data = self._load_csv()
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        return self._data

    def enrich(self, db: Session, master: CompanyMaster) -> EnrichmentResult:
        result = EnrichmentResult(
            master_id=str(master.id),
            company_name=master.legal_name,
            source_name=self.name(),
        )

        if self._data is None:
            self.load()

        for row in self._data or []:
            if self._matches(row, master):
                result.identifiers = self._extract_identifiers(row)
                break

        return result

    def enrich_all(self, db: Session) -> list[EnrichmentResult]:
        """Bulk enrich: match each file row to a master record."""
        if self._data is None:
            self.load()

        results = []
        masters = (
            db.query(CompanyMaster)
            .filter(CompanyMaster.entity_status != "merged")
            .all()
        )
        master_by_name = {m.normalized_name: m for m in masters}

        for row in self._data or []:
            raw_name = row.get("company_name", "")
            normalized = normalize_company_name(raw_name)

            master = master_by_name.get(normalized)
            if not master:
                continue

            identifiers = self._extract_identifiers(row)
            if identifiers:
                results.append(EnrichmentResult(
                    master_id=str(master.id),
                    company_name=master.legal_name,
                    identifiers=identifiers,
                    source_name=self.name(),
                ))

        return results

    def _matches(self, row: dict, master: CompanyMaster) -> bool:
        raw_name = row.get("company_name", "")
        normalized = normalize_company_name(raw_name)
        if normalized and normalized == master.normalized_name:
            return True

        domain = row.get("domain", "").strip().lower()
        if domain:
            # Check against master's domains
            from app.master.domain_models import CompanyDomain
            # Simple name match is sufficient for CSV import
            pass

        return False

    def _extract_identifiers(self, row: dict) -> list[IdentifierMatch]:
        # JSON format: row has "identifiers" array
        if "identifiers" in row:
            return [
                IdentifierMatch(
                    id_type=ident["id_type"],
                    id_value=str(ident["id_value"]),
                    issuing_authority=ident.get("issuing_authority"),
                    confidence=float(ident.get("confidence", 0.90)),
                    source_url=ident.get("source_url"),
                )
                for ident in row["identifiers"]
                if ident.get("id_type") and ident.get("id_value")
            ]

        # CSV flat format: single id_type + id_value per row
        if row.get("id_type") and row.get("id_value"):
            return [
                IdentifierMatch(
                    id_type=row["id_type"],
                    id_value=str(row["id_value"]),
                    issuing_authority=row.get("issuing_authority"),
                    confidence=float(row.get("confidence", 0.90)),
                )
            ]

        return []

    def _load_json(self) -> list[dict]:
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("companies") or raw.get("identifiers") or []
        return raw if isinstance(raw, list) else []

    def _load_csv(self) -> list[dict]:
        with open(self.file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

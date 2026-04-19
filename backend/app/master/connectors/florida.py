"""Florida Division of Corporations (sunbiz.org) data parser.

Parses fixed-width corporate data files from Florida DOS.
File spec: https://dos.sunbiz.org/data-definitions/cor.html
Record length: 1440 characters, ASCII fixed-width.

Field positions are 1-based in the official spec.
Python slicing uses 0-based offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator


# ════════════════════════════════════════════════════════════════════
# Field layout (0-based Python slices)
# ════════════════════════════════════════════════════════════════════

# fmt: off
FIELDS = {
    "corp_number":       (0,   12),
    "corp_name":         (12,  204),
    "status":            (204, 205),
    "filing_type":       (205, 220),
    "address1":          (220, 262),
    "address2":          (262, 304),
    "city":              (304, 332),
    "state":             (332, 334),
    "zip":               (334, 344),
    "country":           (344, 346),
    "mail_address1":     (346, 388),
    "mail_address2":     (388, 430),
    "mail_city":         (430, 458),
    "mail_state":        (458, 460),
    "mail_zip":          (460, 470),
    "mail_country":      (470, 472),
    "file_date":         (472, 480),
    "fei_number":        (480, 494),
    "more_officers":     (494, 495),
    "last_transaction":  (495, 503),
    "state_country":     (503, 505),
    "agent_name":        (544, 586),
    "agent_type":        (586, 587),
    "agent_address":     (587, 629),
    "agent_city":        (629, 657),
    "agent_state":       (657, 659),
    "agent_zip":         (659, 668),
}
# fmt: on

# Filing type → entity_type mapping
FILING_TYPE_MAP = {
    "DOMP":   "corporation",       # Domestic Profit
    "DOMNP":  "nonprofit",         # Domestic Non-Profit
    "FORP":   "corporation",       # Foreign Profit
    "FORNP":  "nonprofit",         # Foreign Non-Profit
    "DOMLP":  "limited_partnership",
    "FORLP":  "limited_partnership",
    "FLAL":   "llc",               # Florida LLC
    "FORL":   "llc",               # Foreign LLC
    "NPREG":  "nonprofit",         # Non-Profit Registration
    "TRUST":  "trust",
    "AGENT":  "registered_agent",
}


@dataclass
class FloridaRecord:
    """Parsed record from Florida corporate data file."""
    corp_number: str
    corp_name: str
    status: str           # A or I
    filing_type: str
    entity_type: str | None
    address1: str
    city: str
    state: str            # from principal address (may be empty)
    state_country: str    # from state/country field (fallback)
    zip_code: str
    country: str
    file_date: date | None
    fei_number: str       # Federal EIN
    last_transaction: str
    agent_name: str
    agent_address: str
    agent_city: str
    agent_state: str
    raw_line: str         # original line for provenance

    @property
    def effective_state(self) -> str:
        """Best available state code: principal → state_country → 'FL' default."""
        return self.state or self.state_country or "FL"

    @property
    def clean_city(self) -> str:
        """City name with trailing comma/punctuation stripped."""
        return self.city.rstrip(",. ") if self.city else ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to full provenance dict for staging."""
        city = self.clean_city
        state = self.effective_state
        return {
            "company_name": self.corp_name,
            "domain": "",  # Florida registry does not provide domains
            "industry": None,
            "location": f"{city}, {state}" if city else state,
            "source": "florida_dos",
            # Structured fields
            "corp_number": self.corp_number,
            "filing_type": self.filing_type,
            "entity_type": self.entity_type,
            "status_code": self.status,
            "fei_number": self.fei_number,
            "file_date": self.file_date.isoformat() if self.file_date else None,
            "last_transaction": self.last_transaction,
            # Principal address
            "address": self.address1,
            "city": city,
            "state": state,
            "zip": self.zip_code,
            "country": self.country,
            # Registered agent
            "agent_name": self.agent_name,
            "agent_address": self.agent_address,
            "agent_city": self.agent_city,
            "agent_state": self.agent_state,
        }


def parse_line(line: str) -> FloridaRecord | None:
    """Parse a single fixed-width line into a FloridaRecord.

    Returns None if the line is too short or unparseable.
    """
    if len(line) < 505:
        return None

    def _f(name: str) -> str:
        start, end = FIELDS[name]
        return line[start:end].strip()

    corp_name = _f("corp_name")
    if not corp_name:
        return None

    filing_type = _f("filing_type")
    entity_type = FILING_TYPE_MAP.get(filing_type)

    file_date = _parse_date(_f("file_date"))

    return FloridaRecord(
        corp_number=_f("corp_number"),
        corp_name=corp_name,
        status=_f("status"),
        filing_type=filing_type,
        entity_type=entity_type,
        address1=_f("address1"),
        city=_f("city"),
        state=_f("state"),
        state_country=_f("state_country"),
        zip_code=_f("zip"),
        country=_f("country"),
        file_date=file_date,
        fei_number=_f("fei_number"),
        last_transaction=_f("last_transaction"),
        agent_name=_f("agent_name"),
        agent_address=_f("agent_address"),
        agent_city=_f("agent_city"),
        agent_state=_f("agent_state"),
        raw_line=line,
    )


def parse_file(
    path: str | Path,
    *,
    limit: int | None = None,
    offset: int = 0,
    active_only: bool = True,
    filing_types: set[str] | None = None,
) -> Iterator[FloridaRecord]:
    """Stream-parse a Florida corporate data file.

    Args:
        path: path to fixed-width text file
        limit: max records to yield
        offset: skip first N valid records
        active_only: if True, only yield status="A" records
        filing_types: if provided, only yield these filing types
    """
    path = Path(path)
    yielded = 0
    skipped = 0

    with open(path, "r", encoding="ascii", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n\r")
            if not line or len(line) < 505:
                continue

            record = parse_line(line)
            if record is None:
                continue

            # Filters
            if active_only and record.status != "A":
                continue
            if filing_types and record.filing_type not in filing_types:
                continue

            # Offset
            if skipped < offset:
                skipped += 1
                continue

            yield record
            yielded += 1

            if limit and yielded >= limit:
                return


def count_records(path: str | Path, *, active_only: bool = True) -> dict:
    """Quick scan to count records by status and filing type."""
    path = Path(path)
    total = 0
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}

    with open(path, "r", encoding="ascii", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n\r")
            if not line or len(line) < 505:
                continue
            record = parse_line(line)
            if record is None:
                continue
            total += 1
            by_status[record.status] = by_status.get(record.status, 0) + 1
            by_type[record.filing_type] = by_type.get(record.filing_type, 0) + 1

    return {
        "total": total,
        "by_status": by_status,
        "by_filing_type": by_type,
    }


def _parse_date(s: str) -> date | None:
    """Parse MMDDYYYY or YYYYMMDD date string."""
    if not s or len(s) != 8 or not s.isdigit():
        return None
    try:
        # Try MMDDYYYY first (Florida's format)
        return date(int(s[4:8]), int(s[0:2]), int(s[2:4]))
    except ValueError:
        try:
            # Fallback YYYYMMDD
            return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None

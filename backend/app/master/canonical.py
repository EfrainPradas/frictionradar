"""Name normalization utilities for the Company Master Index.

Provides deterministic, repeatable normalization so that entity matching
in later phases has a clean foundation to work with.
"""

from __future__ import annotations

import re
import unicodedata

# Common legal suffixes to strip for matching (order matters: longest first)
LEGAL_SUFFIXES = [
    "incorporated",
    "corporation",
    "limited liability company",
    "limited partnership",
    "limited",
    "company",
    "group",
    "holdings",
    "enterprises",
    "international",
    "inc.",
    "inc",
    "corp.",
    "corp",
    "llc",
    "l.l.c.",
    "ltd.",
    "ltd",
    "l.p.",
    "lp",
    "co.",
    "co",
    "plc",
    "n.a.",
    "n.v.",
]

# Dotted abbreviations like "L.P.", "N.A." must match before word-boundary patterns
_DOTTED_ABBREVS = [s for s in LEGAL_SUFFIXES if "." in s]
_PLAIN_SUFFIXES = [s for s in LEGAL_SUFFIXES if "." not in s]

# Build pattern: try dotted abbreviations first (they contain literal dots),
# then plain word-boundary suffixes
_DOTTED_PART = "|".join(re.escape(s) for s in _DOTTED_ABBREVS)
_PLAIN_PART = "|".join(re.escape(s) for s in _PLAIN_SUFFIXES)
_SUFFIX_PATTERN = re.compile(
    r"(?:" + _DOTTED_PART + r"|\b(?:" + _PLAIN_PART + r")\b)\.?",
    re.IGNORECASE,
)

_MULTI_SPACE = re.compile(r"\s+")
_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9\s]")


def normalize_company_name(name: str) -> str:
    """Normalize a company name for deduplication and matching.

    Steps:
      1. Unicode NFKD normalization → ASCII
      2. Lowercase
      3. Strip legal suffixes (Inc., LLC, Corp., etc.)
      4. Remove punctuation (keep alphanumeric + spaces)
      5. Collapse whitespace
      6. Strip leading/trailing whitespace

    Examples:
      "Stripe, Inc."           → "stripe"
      "The Goldman Sachs Group, Inc." → "goldman sachs"
      "JPMorgan Chase & Co."   → "jpmorgan chase"
      "Meta Platforms, Inc."   → "meta platforms"
    """
    if not name:
        return ""

    # Unicode → ASCII approximation
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Lowercase
    text = text.lower()

    # Strip "the " prefix
    if text.startswith("the "):
        text = text[4:]

    # Remove legal suffixes
    text = _SUFFIX_PATTERN.sub("", text)

    # Remove non-alphanumeric (keep spaces)
    text = _NON_ALNUM_SPACE.sub(" ", text)

    # Collapse whitespace
    text = _MULTI_SPACE.sub(" ", text).strip()

    return text


def normalize_state_code(state: str | None) -> str | None:
    """Normalize a US state identifier to 2-letter uppercase code.

    Accepts 2-letter codes or common full names. Returns None if unrecognized.
    """
    if not state:
        return None

    state = state.strip().upper()

    # Already a 2-letter code
    if len(state) == 2 and state.isalpha():
        return state if state in _US_STATES else None

    # Full name lookup
    return _STATE_NAME_MAP.get(state.title())


_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

_STATE_NAME_MAP = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District Of Columbia": "DC",
}

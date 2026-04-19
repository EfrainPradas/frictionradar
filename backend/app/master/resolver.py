"""Entity resolution engine for the Company Master Index.

Finds and scores duplicate pairs among company_master records using
deterministic and lightweight probabilistic rules. No LLMs.

Matching strategy (ordered by confidence):

  TIER 1 — Auto-merge (confidence >= 0.95):
    - exact_ext_id:       same external ID (EIN, CIK, UEI)     → 1.000
    - exact_domain:       same normalized domain                → 0.980
    - exact_name:         same normalized_name                  → 0.960

  TIER 2 — High confidence (0.80 <= confidence < 0.95):
    - name_plus_state:    similar name + same jurisdiction      → 0.850
    - alias_match:        alias of A matches normalized name of B → 0.820

  TIER 3 — Review needed (0.50 <= confidence < 0.80):
    - fuzzy_name:         high token similarity, no state match → 0.650

  Below 0.50: not reported.

Design decisions:
  - Pair ordering: always master_id_a < master_id_b (prevents duplicates)
  - Canonical selection: record with more source_records wins, then older
  - Auto-merge threshold: >= 0.95 confidence
  - No blocking/indexing optimization needed at 159 records; O(n^2) is fine
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from .canonical import normalize_company_name
from .models import CompanyAlias, CompanyExternalId, CompanyMaster, CompanySourceRecord
from .resolution_models import (
    CompanyMatchCandidate,
    CompanyMergeDecision,
    CompanyResolutionLog,
)


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

AUTO_MERGE_THRESHOLD = 0.95
REVIEW_THRESHOLD = 0.50

# Domains that should never be used for matching (hosting, archive, generic)
BLOCKED_DOMAINS = {
    "web.archive.org", "archive.org", "github.com", "linkedin.com",
    "facebook.com", "twitter.com", "wikipedia.org", "en.wikipedia.org",
    "google.com", "youtube.com", "bloomberg.com", "crunchbase.com",
}

# Reason codes
EXACT_EXT_ID = "exact_ext_id"
EXACT_DOMAIN = "exact_domain"
EXACT_NAME = "exact_name"
NAME_PLUS_STATE = "name_plus_state"
ALIAS_MATCH = "alias_match"
FUZZY_NAME = "fuzzy_name"


class MatchResult(NamedTuple):
    confidence: float
    reason_code: str
    reason_detail: str


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def run_resolution(db: Session, *, auto_merge: bool = True, dry_run: bool = False) -> dict:
    """Run full entity resolution across all active company_master records.

    Args:
        db: database session
        auto_merge: if True, automatically merge pairs above AUTO_MERGE_THRESHOLD
        dry_run: if True, find candidates but don't write merge decisions

    Returns summary dict.
    """
    run_log = CompanyResolutionLog(id=uuid4(), status="running")
    if not dry_run:
        db.add(run_log)
        db.commit()
        db.refresh(run_log)

    try:
        # Load all active master records
        masters = (
            db.query(CompanyMaster)
            .filter(CompanyMaster.entity_status != "merged")
            .order_by(CompanyMaster.created_at)
            .all()
        )

        # Build lookup indexes
        idx = _build_indexes(db, masters)

        # Find all candidate pairs
        candidates = _find_candidates(masters, idx)
        run_log.total_compared = len(masters) * (len(masters) - 1) // 2
        run_log.total_candidates = len(candidates)

        if dry_run:
            return _dry_run_report(candidates, masters)

        # Persist candidates
        auto_merged = 0
        flagged = 0

        for (id_a, id_b), match in candidates.items():
            status = "auto_merged" if (auto_merge and match.confidence >= AUTO_MERGE_THRESHOLD) else "pending"

            cand = CompanyMatchCandidate(
                master_id_a=id_a,
                master_id_b=id_b,
                confidence=match.confidence,
                reason_code=match.reason_code,
                reason_detail=match.reason_detail,
                status=status,
                resolution_run_id=run_log.id,
            )
            db.add(cand)
            db.flush()

            if status == "auto_merged":
                canonical_id, duplicate_id = _pick_canonical(
                    db, id_a, id_b, masters
                )
                _execute_merge(db, canonical_id, duplicate_id, cand)
                cand.resolved_at = datetime.now(timezone.utc)
                auto_merged += 1
            else:
                flagged += 1

        run_log.total_auto_merged = auto_merged
        run_log.total_flagged = flagged
        run_log.status = "success"
        run_log.finished_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        db.rollback()
        run_log.status = "failed"
        run_log.error_message = str(e)[:500]
        run_log.finished_at = datetime.now(timezone.utc)
        try:
            db.add(run_log)
            db.commit()
        except Exception:
            pass
        raise

    return {
        "status": run_log.status,
        "total_records": len(masters),
        "total_compared": run_log.total_compared,
        "total_candidates": run_log.total_candidates,
        "auto_merged": run_log.total_auto_merged,
        "flagged_for_review": run_log.total_flagged,
        "resolution_run_id": str(run_log.id),
    }


# ════════════════════════════════════════════════════════════════════
# Index Building
# ════════════════════════════════════════════════════════════════════

class _Indexes:
    """Pre-computed lookup tables for matching."""

    def __init__(self):
        self.domains: dict[UUID, set[str]] = {}       # master_id → {domain1, domain2}
        self.ext_ids: dict[UUID, set[str]] = {}        # master_id → {"ein:123", "cik:456"}
        self.aliases: dict[UUID, set[str]] = {}         # master_id → {normalized alias names}
        self.source_counts: dict[UUID, int] = {}        # master_id → source record count


def _build_indexes(db: Session, masters: list[CompanyMaster]) -> _Indexes:
    idx = _Indexes()
    master_ids = [m.id for m in masters]

    # Domains from source records
    source_records = (
        db.query(CompanySourceRecord)
        .filter(CompanySourceRecord.company_master_id.in_(master_ids))
        .all()
    )
    for sr in source_records:
        mid = sr.company_master_id
        idx.source_counts[mid] = idx.source_counts.get(mid, 0) + 1
        if sr.raw_payload and isinstance(sr.raw_payload, dict):
            raw_domain = sr.raw_payload.get("domain", "")
            if raw_domain:
                domain = raw_domain.strip().lower()
                if domain.startswith("http"):
                    import re
                    domain = re.sub(r"^https?://", "", domain)
                if domain.startswith("www."):
                    domain = domain[4:]
                domain = domain.split("/")[0]
                if domain:
                    idx.domains.setdefault(mid, set()).add(domain)

    # External IDs
    ext_ids = (
        db.query(CompanyExternalId)
        .filter(CompanyExternalId.company_master_id.in_(master_ids))
        .all()
    )
    for eid in ext_ids:
        key = f"{eid.id_type}:{eid.id_value}"
        idx.ext_ids.setdefault(eid.company_master_id, set()).add(key)

    # Aliases (normalized)
    aliases = (
        db.query(CompanyAlias)
        .filter(CompanyAlias.company_master_id.in_(master_ids))
        .all()
    )
    for a in aliases:
        norm = normalize_company_name(a.alias_name)
        if norm:
            idx.aliases.setdefault(a.company_master_id, set()).add(norm)

    return idx


# ════════════════════════════════════════════════════════════════════
# Candidate Finding
# ════════════════════════════════════════════════════════════════════

def _find_candidates(
    masters: list[CompanyMaster], idx: _Indexes
) -> dict[tuple[UUID, UUID], MatchResult]:
    """Compare all pairs, keep best match per pair above REVIEW_THRESHOLD."""
    candidates: dict[tuple[UUID, UUID], MatchResult] = {}

    for i in range(len(masters)):
        for j in range(i + 1, len(masters)):
            a, b = masters[i], masters[j]
            # Enforce canonical ordering
            id_a, id_b = (a.id, b.id) if a.id < b.id else (b.id, a.id)
            if id_a == id_b:
                continue

            match = _score_pair(a, b, idx)
            if match and match.confidence >= REVIEW_THRESHOLD:
                key = (id_a, id_b)
                if key not in candidates or match.confidence > candidates[key].confidence:
                    candidates[key] = match

    return candidates


def _score_pair(
    a: CompanyMaster, b: CompanyMaster, idx: _Indexes
) -> MatchResult | None:
    """Score a pair of master records. Returns best match or None."""
    best: MatchResult | None = None

    # Rule 1: Exact external ID match → 1.000
    ids_a = idx.ext_ids.get(a.id, set())
    ids_b = idx.ext_ids.get(b.id, set())
    common_ids = ids_a & ids_b
    if common_ids:
        sample = next(iter(common_ids))
        return MatchResult(
            1.000, EXACT_EXT_ID, f"shared external ID: {sample}"
        )

    # Rule 2: Exact domain match → 0.980
    doms_a = idx.domains.get(a.id, set()) - BLOCKED_DOMAINS
    doms_b = idx.domains.get(b.id, set()) - BLOCKED_DOMAINS
    common_doms = doms_a & doms_b
    if common_doms:
        sample = next(iter(common_doms))
        return MatchResult(
            0.980, EXACT_DOMAIN, f"shared domain: {sample}"
        )

    # Rule 3: Exact normalized name match → 0.960
    if a.normalized_name and b.normalized_name and a.normalized_name == b.normalized_name:
        return MatchResult(
            0.960, EXACT_NAME, f"identical normalized name: {a.normalized_name}"
        )

    # Rule 4: Alias of A matches normalized name of B (or vice versa) → 0.820
    aliases_a = idx.aliases.get(a.id, set())
    aliases_b = idx.aliases.get(b.id, set())
    if b.normalized_name in aliases_a:
        return MatchResult(
            0.820, ALIAS_MATCH,
            f"alias of '{a.legal_name}' matches '{b.legal_name}'"
        )
    if a.normalized_name in aliases_b:
        return MatchResult(
            0.820, ALIAS_MATCH,
            f"alias of '{b.legal_name}' matches '{a.legal_name}'"
        )

    # Rule 5: Name similarity + same state → 0.850
    name_sim = _token_similarity(a.normalized_name, b.normalized_name)
    same_state = (
        a.jurisdiction_state
        and b.jurisdiction_state
        and a.jurisdiction_state == b.jurisdiction_state
    )
    if name_sim >= 0.80 and same_state:
        best = MatchResult(
            0.850, NAME_PLUS_STATE,
            f"name_sim={name_sim:.2f} + same state {a.jurisdiction_state}: "
            f"'{a.normalized_name}' vs '{b.normalized_name}'"
        )

    # Rule 6: High fuzzy name similarity without state → 0.650
    if name_sim >= 0.85 and (best is None or 0.650 > best.confidence):
        best = MatchResult(
            0.650, FUZZY_NAME,
            f"name_sim={name_sim:.2f}: '{a.normalized_name}' vs '{b.normalized_name}'"
        )

    return best


def _token_similarity(a: str, b: str) -> float:
    """Jaccard similarity on word tokens. Returns 0.0 – 1.0."""
    if not a or not b:
        return 0.0
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# ════════════════════════════════════════════════════════════════════
# Merge Execution
# ════════════════════════════════════════════════════════════════════

def _pick_canonical(
    db: Session, id_a: UUID, id_b: UUID, masters: list[CompanyMaster]
) -> tuple[UUID, UUID]:
    """Choose which record becomes canonical and which is the duplicate.

    Heuristics:
      1. More source records → canonical (better provenance)
      2. Tie: older record → canonical (was there first)
    """
    master_map = {m.id: m for m in masters}
    a = master_map.get(id_a)
    b = master_map.get(id_b)

    count_a = db.query(CompanySourceRecord).filter(
        CompanySourceRecord.company_master_id == id_a
    ).count()
    count_b = db.query(CompanySourceRecord).filter(
        CompanySourceRecord.company_master_id == id_b
    ).count()

    if count_a > count_b:
        return id_a, id_b
    elif count_b > count_a:
        return id_b, id_a
    else:
        # Older wins
        if a and b and a.created_at and b.created_at:
            return (id_a, id_b) if a.created_at <= b.created_at else (id_b, id_a)
        return id_a, id_b


def _execute_merge(
    db: Session,
    canonical_id: UUID,
    duplicate_id: UUID,
    candidate: CompanyMatchCandidate,
) -> CompanyMergeDecision:
    """Execute a merge: move children from duplicate to canonical, mark duplicate as merged."""
    # Create decision record
    decision = CompanyMergeDecision(
        canonical_id=canonical_id,
        duplicate_id=duplicate_id,
        match_candidate_id=candidate.id,
        merge_reason=f"{candidate.reason_code}: {candidate.reason_detail}",
        confidence=candidate.confidence,
        merged_by="auto",
    )
    db.add(decision)

    # Move source records from duplicate → canonical
    db.query(CompanySourceRecord).filter(
        CompanySourceRecord.company_master_id == duplicate_id
    ).update({"company_master_id": canonical_id})

    # Move aliases from duplicate → canonical
    db.query(CompanyAlias).filter(
        CompanyAlias.company_master_id == duplicate_id
    ).update({"company_master_id": canonical_id})

    # Move external IDs from duplicate → canonical
    db.query(CompanyExternalId).filter(
        CompanyExternalId.company_master_id == duplicate_id
    ).update({"company_master_id": canonical_id})

    # If duplicate had a linked_company_id and canonical doesn't, transfer it
    canonical = db.query(CompanyMaster).filter(CompanyMaster.id == canonical_id).first()
    duplicate = db.query(CompanyMaster).filter(CompanyMaster.id == duplicate_id).first()
    if duplicate and canonical:
        if duplicate.linked_company_id and not canonical.linked_company_id:
            canonical.linked_company_id = duplicate.linked_company_id

    # Mark duplicate as merged
    if duplicate:
        duplicate.entity_status = "merged"
        duplicate.updated_at = datetime.now(timezone.utc)

    # Add the duplicate's legal name as an alias on the canonical
    if duplicate and canonical and duplicate.legal_name != canonical.legal_name:
        alias = CompanyAlias(
            company_master_id=canonical_id,
            alias_name=duplicate.legal_name,
            alias_type="former_name",
            source="entity_resolution",
        )
        db.add(alias)

    db.flush()
    return decision


# ════════════════════════════════════════════════════════════════════
# Dry Run Report
# ════════════════════════════════════════════════════════════════════

def _dry_run_report(
    candidates: dict[tuple[UUID, UUID], MatchResult],
    masters: list[CompanyMaster],
) -> dict:
    master_map = {m.id: m for m in masters}
    pairs = []
    for (id_a, id_b), match in sorted(
        candidates.items(), key=lambda x: -x[1].confidence
    ):
        a = master_map.get(id_a)
        b = master_map.get(id_b)
        pairs.append({
            "company_a": a.legal_name if a else str(id_a),
            "company_b": b.legal_name if b else str(id_b),
            "confidence": float(match.confidence),
            "reason_code": match.reason_code,
            "reason_detail": match.reason_detail,
            "would_auto_merge": match.confidence >= AUTO_MERGE_THRESHOLD,
        })

    return {
        "status": "dry_run",
        "total_records": len(masters),
        "total_candidates": len(candidates),
        "would_auto_merge": sum(1 for p in pairs if p["would_auto_merge"]),
        "would_flag": sum(1 for p in pairs if not p["would_auto_merge"]),
        "pairs": pairs,
    }

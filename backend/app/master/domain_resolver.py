"""Domain resolution pipeline for the Company Master Index.

Three-phase pipeline:
  1. SEED     — extract domains from source_records raw_payload and staging data
  2. VERIFY   — HTTP HEAD/GET check to validate domains are alive and relevant
  3. PROMOTE  — set primary domain and final status per company

Sources (current phase):
  - json_import raw_payload → domain field
  - company_staging_normalized → domain field

Future sources (pluggable via register_source):
  - SEC EDGAR filings
  - SAM.gov registrations
  - State SOS records
  - Manual entry

Domain statuses:
  unresolved → resolved | rejected | ambiguous | redirect
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

import requests
from sqlalchemy.orm import Session

from app.core.security import get_ssl_verify
from .domain_models import CompanyDomain, DomainResolutionRun
from .models import CompanyMaster, CompanySourceRecord
from .staging_models import CompanyStagingNormalized


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,}$"
)

# Domains that are not company websites
EXCLUDED_DOMAINS = {
    "web.archive.org", "archive.org", "github.com", "linkedin.com",
    "facebook.com", "twitter.com", "wikipedia.org", "en.wikipedia.org",
    "google.com", "youtube.com", "bloomberg.com", "crunchbase.com",
    "sec.gov", "sam.gov",
}

HTTP_TIMEOUT = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ════════════════════════════════════════════════════════════════════
# Pluggable source protocol
# ════════════════════════════════════════════════════════════════════

class DomainSource(Protocol):
    """Interface for domain discovery sources.

    Implement this to add new sources (SEC, SAM, SOS, etc.).
    """
    def name(self) -> str: ...
    def extract_domains(self, db: Session, master: CompanyMaster) -> list[dict]:
        """Return list of {"domain": str, "confidence": float, "source": str}."""
        ...


# ════════════════════════════════════════════════════════════════════
# Built-in sources
# ════════════════════════════════════════════════════════════════════

class JsonImportSource:
    """Extract domains from source_records raw_payload."""

    def name(self) -> str:
        return "json_import"

    def extract_domains(self, db: Session, master: CompanyMaster) -> list[dict]:
        records = (
            db.query(CompanySourceRecord)
            .filter(CompanySourceRecord.company_master_id == master.id)
            .all()
        )
        results = []
        seen = set()
        for sr in records:
            if not sr.raw_payload or not isinstance(sr.raw_payload, dict):
                continue
            raw = sr.raw_payload.get("domain", "")
            domain = _clean_domain(raw)
            if domain and domain not in seen and domain not in EXCLUDED_DOMAINS:
                seen.add(domain)
                results.append({
                    "domain": domain,
                    "confidence": 0.700,
                    "source": f"json_import:{sr.source_name}",
                })
        return results


class StagingSource:
    """Extract domains from staging_normalized records."""

    def name(self) -> str:
        return "staging"

    def extract_domains(self, db: Session, master: CompanyMaster) -> list[dict]:
        norms = (
            db.query(CompanyStagingNormalized)
            .filter(CompanyStagingNormalized.matched_master_id == master.id)
            .all()
        )
        results = []
        seen = set()
        for n in norms:
            if n.domain and n.domain not in seen and n.domain not in EXCLUDED_DOMAINS:
                seen.add(n.domain)
                results.append({
                    "domain": n.domain,
                    "confidence": 0.700,
                    "source": f"staging:{n.source or 'unknown'}",
                })
        return results


class WorkspaceSource:
    """Extract domains from the existing companies workspace table."""

    def name(self) -> str:
        return "workspace"

    def extract_domains(self, db: Session, master: CompanyMaster) -> list[dict]:
        if not master.linked_company_id:
            return []
        from .models import CompanyMaster  # avoid circular
        from app.models.company import Company
        company = db.query(Company).filter(Company.id == master.linked_company_id).first()
        if company and company.domain:
            domain = _clean_domain(company.domain)
            if domain and domain not in EXCLUDED_DOMAINS:
                return [{"domain": domain, "confidence": 0.850, "source": "workspace"}]
        return []


# Default sources
DEFAULT_SOURCES: list[DomainSource] = [
    JsonImportSource(),
    StagingSource(),
    WorkspaceSource(),
]


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def resolve_domains(
    db: Session,
    *,
    verify_http: bool = True,
    dry_run: bool = False,
    sources: list[DomainSource] | None = None,
) -> dict:
    """Run domain resolution for all master companies without a primary domain.

    Args:
        db: database session
        verify_http: if True, do HTTP checks on new domains
        dry_run: if True, report what would happen without writing
        sources: list of DomainSource implementations (defaults to all built-in)
    """
    if sources is None:
        sources = DEFAULT_SOURCES

    run = DomainResolutionRun(id=uuid4(), status="running")
    if not dry_run:
        db.add(run)
        db.commit()
        db.refresh(run)

    try:
        # Get all active master records
        masters = (
            db.query(CompanyMaster)
            .filter(CompanyMaster.entity_status != "merged")
            .all()
        )

        processed = 0
        resolved = 0
        rejected = 0
        ambiguous = 0
        errors = 0
        report_entries = []

        for master in masters:
            # Collect domains from all sources
            candidates = _collect_candidates(db, master, sources)
            if not candidates:
                continue

            processed += 1

            if dry_run:
                report_entries.append({
                    "company": master.legal_name,
                    "master_id": str(master.id),
                    "candidates": candidates,
                })
                continue

            # Deduplicate and pick best per domain
            best_by_domain = _deduplicate(candidates)

            for domain, info in best_by_domain.items():
                # Check if already exists
                existing = (
                    db.query(CompanyDomain)
                    .filter(
                        CompanyDomain.company_master_id == master.id,
                        CompanyDomain.domain == domain,
                    )
                    .first()
                )
                if existing:
                    continue

                cd = CompanyDomain(
                    company_master_id=master.id,
                    domain=domain,
                    is_primary=False,
                    domain_status="unresolved",
                    confidence=info["confidence"],
                    source=info["source"],
                )
                db.add(cd)

            db.flush()

            # Phase 2: Verify via HTTP
            unverified = (
                db.query(CompanyDomain)
                .filter(
                    CompanyDomain.company_master_id == master.id,
                    CompanyDomain.domain_status == "unresolved",
                )
                .all()
            )

            for cd in unverified:
                if verify_http:
                    _verify_domain(cd)
                else:
                    # Trust the source without HTTP check
                    cd.domain_status = "resolved"
                    cd.confidence = min(cd.confidence + 0.100, 1.000)

            db.flush()

            # Phase 3: Promote primary
            result = _promote_primary(db, master.id)
            if result == "resolved":
                resolved += 1
            elif result == "ambiguous":
                ambiguous += 1
            elif result == "rejected":
                rejected += 1
            else:
                errors += 1

        if not dry_run:
            run.total_processed = processed
            run.total_resolved = resolved
            run.total_rejected = rejected
            run.total_ambiguous = ambiguous
            run.total_errors = errors
            run.status = "success"
            run.finished_at = datetime.now(timezone.utc)
            db.commit()

    except Exception as e:
        if not dry_run:
            db.rollback()
            run.status = "failed"
            run.error_message = str(e)[:500]
            run.finished_at = datetime.now(timezone.utc)
            db.add(run)
            db.commit()
        raise

    if dry_run:
        return {
            "status": "dry_run",
            "total_companies": len(masters),
            "with_candidates": processed,
            "entries": report_entries,
        }

    return {
        "status": run.status,
        "run_id": str(run.id),
        "total_processed": processed,
        "total_resolved": resolved,
        "total_rejected": rejected,
        "total_ambiguous": ambiguous,
        "total_errors": errors,
    }


def get_primary_domain(db: Session, master_id: UUID) -> str | None:
    """Get the primary resolved domain for a master company. Returns None if unresolved."""
    cd = (
        db.query(CompanyDomain)
        .filter(
            CompanyDomain.company_master_id == master_id,
            CompanyDomain.is_primary == True,
            CompanyDomain.domain_status == "resolved",
        )
        .first()
    )
    return cd.domain if cd else None


# ════════════════════════════════════════════════════════════════════
# Internals
# ════════════════════════════════════════════════════════════════════

def _clean_domain(raw: str) -> str | None:
    if not raw:
        return None
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d)
    if d.startswith("www."):
        d = d[4:]
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if not d or not _DOMAIN_RE.match(d):
        return None
    return d


def _collect_candidates(
    db: Session, master: CompanyMaster, sources: list[DomainSource]
) -> list[dict]:
    all_candidates = []
    for src in sources:
        try:
            candidates = src.extract_domains(db, master)
            all_candidates.extend(candidates)
        except Exception:
            pass
    return all_candidates


def _deduplicate(candidates: list[dict]) -> dict[str, dict]:
    """Keep highest-confidence entry per domain."""
    best: dict[str, dict] = {}
    for c in candidates:
        domain = c["domain"]
        if domain not in best or c["confidence"] > best[domain]["confidence"]:
            best[domain] = c
    return best


def _verify_domain(cd: CompanyDomain) -> None:
    """HTTP check a domain. Updates status, http_status, title_tag, redirects_to."""
    url = f"https://{cd.domain}"
    cd.last_checked_at = datetime.now(timezone.utc)

    try:
        resp = requests.get(
            url,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
            verify=get_ssl_verify(),
        )
        cd.http_status = resp.status_code

        # Check for redirect to different domain
        final_domain = _clean_domain(resp.url)
        if final_domain and final_domain != cd.domain:
            cd.redirects_to = final_domain
            cd.domain_status = "redirect"
            cd.confidence = 0.400
            return

        if resp.status_code < 400:
            # Extract title
            title_match = re.search(
                r"<title[^>]*>([^<]{1,200})</title>",
                resp.text[:5000],
                re.IGNORECASE,
            )
            if title_match:
                cd.title_tag = title_match.group(1).strip()

            cd.domain_status = "resolved"
            cd.confidence = min(cd.confidence + 0.200, 1.000)
            cd.last_verified_at = datetime.now(timezone.utc)
        elif resp.status_code in (403, 429):
            # Server is alive but blocking scrapers — domain is valid
            cd.domain_status = "resolved"
            cd.confidence = min(cd.confidence + 0.050, 0.750)
            cd.last_verified_at = datetime.now(timezone.utc)
        else:
            cd.domain_status = "rejected"
            cd.confidence = 0.100

    except requests.exceptions.SSLError:
        # Try HTTP fallback
        try:
            resp = requests.get(
                f"http://{cd.domain}",
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
            cd.http_status = resp.status_code
            if resp.status_code < 400:
                cd.domain_status = "resolved"
                cd.confidence = min(cd.confidence + 0.100, 1.000)
                cd.last_verified_at = datetime.now(timezone.utc)
            else:
                cd.domain_status = "rejected"
                cd.confidence = 0.100
        except Exception:
            cd.domain_status = "rejected"
            cd.confidence = 0.050

    except requests.exceptions.ConnectionError:
        cd.domain_status = "rejected"
        cd.confidence = 0.050

    except requests.exceptions.Timeout:
        cd.domain_status = "rejected"
        cd.confidence = 0.100

    except Exception:
        cd.domain_status = "rejected"
        cd.confidence = 0.050


def _promote_primary(db: Session, master_id: UUID) -> str:
    """Promote the best resolved domain to primary. Returns outcome status."""
    domains = (
        db.query(CompanyDomain)
        .filter(CompanyDomain.company_master_id == master_id)
        .all()
    )

    if not domains:
        return "error"

    resolved = [d for d in domains if d.domain_status == "resolved"]
    if not resolved:
        # All rejected?
        if all(d.domain_status == "rejected" for d in domains):
            return "rejected"
        return "ambiguous"

    if len(resolved) == 1:
        resolved[0].is_primary = True
        return "resolved"

    # Multiple resolved: pick highest confidence, then shortest domain
    resolved.sort(key=lambda d: (-float(d.confidence), len(d.domain)))
    resolved[0].is_primary = True
    return "resolved"

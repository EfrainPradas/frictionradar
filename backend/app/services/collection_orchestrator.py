"""
Collection Orchestrator — runs all collectors and optionally the Playwright pipeline.

Changes from original:
  - Removed the fire-and-forget thread that duplicated careers extraction + scoring.
  - Added per-company logging with structured metadata.
  - The caller (batch_processor or API endpoint) is now responsible for calling
    extract_careers_evidence separately if desired.
"""

import asyncio
import time as _time
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timezone
from typing import List, Optional

from app.models.company import Company
from app.models.company_signal import CompanySignal
from app.models.collection_run import CollectionRun
from app.collectors import ACTIVE_COLLECTORS
from app.core.logging import logger


async def find_careers_url(domain: str) -> Optional[str]:
    """Use careers_url_finder to find the best careers URL.

    Falls back to Playwright-based probing for pages that need JS rendering.
    """
    from app.collectors.careers_url_finder import careers_url_finder

    # Step 1: Fast HTTP-based discovery
    url, strategy, meta = careers_url_finder.find(domain)
    if url:
        logger.info(f"Careers URL found via {strategy}: {url}")
        return url

    # Step 2: Playwright fallback for JS-rendered pages
    logger.info(f"HTTP discovery failed for {domain}, trying Playwright fallback")
    return await _playwright_careers_fallback(domain)


async def _playwright_careers_fallback(domain: str) -> Optional[str]:
    """Try Playwright-based careers page discovery as a fallback."""
    paths = [
        "/careers",
        "/jobs",
        "/careers/jobs",
        "/about/careers",
        "/company/careers",
        "/join-us",
        "/work-with-us",
        "/people",
        "/team",
        "/opportunities",
    ]
    subdomains = ["careers", "jobs"]

    from app.services.browser_capture_service import BrowserCaptureService

    service = BrowserCaptureService()
    await service.initialize()

    try:
        # Try subdomains first (more likely to be dedicated careers pages)
        for sub in subdomains:
            url = f"https://{sub}.{domain}"
            try:
                capture = await service.capture_page(url, timeout_ms=12000)
                if not capture.error and capture.visible_text:
                    text = capture.visible_text.lower()
                    if any(
                        kw in text
                        for kw in ["open position", "job", "career", "join our team", "we're hiring", "we are hiring", "open roles", "current openings"]
                    ):
                        logger.info(f"Playwright found careers at: {url}")
                        return url
            except Exception:
                continue

        # Try paths on main domain
        for path in paths:
            url = f"https://{domain}{path}"
            try:
                capture = await service.capture_page(url, timeout_ms=12000)
                if not capture.error and capture.visible_text:
                    text = capture.visible_text.lower()
                    if any(
                        kw in text
                        for kw in ["open position", "job", "career", "join our team", "we're hiring", "we are hiring", "open roles", "current openings"]
                    ):
                        logger.info(f"Playwright found careers at: {url}")
                        return url
            except Exception:
                continue

        # Try www prefix
        for path in ["/careers", "/jobs"]:
            url = f"https://www.{domain}{path}"
            try:
                capture = await service.capture_page(url, timeout_ms=10000)
                if not capture.error and capture.visible_text:
                    text = capture.visible_text.lower()
                    if any(kw in text for kw in ["open position", "job", "career"]):
                        logger.info(f"Playwright found careers at: {url}")
                        return url
            except Exception:
                continue

        return None
    finally:
        await service.cleanup()


async def extract_careers_evidence(
    db: Session, company_id: UUID, domain: str, known_careers_url: Optional[str] = None
) -> Optional[int]:
    """Use Playwright + hybrid extractor to capture deep careers evidence.

    Wall-clock bounded at 60s so a single slow/complex careers page (e.g. a
    JS-heavy enterprise site that never hits networkidle) can't stall the
    whole parallel worker and trigger watchdog false positives.
    """
    try:
        return await asyncio.wait_for(
            _extract_careers_evidence_inner(db, company_id, domain, known_careers_url),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[Playwright] Extraction timed out (>60s) for {domain}")
        return None


async def _extract_careers_evidence_inner(
    db: Session, company_id: UUID, domain: str, known_careers_url: Optional[str] = None
) -> Optional[int]:
    """Inner implementation — see extract_careers_evidence for the bounded wrapper.

    Args:
        known_careers_url: If the sync collectors already found a careers URL,
            pass it here to skip redundant discovery.
    """
    from app.services.browser_capture_service import BrowserCaptureService
    from app.services.hybrid_careers_extractor import hybrid_careers_extractor

    logger.info(f"[Playwright] Starting careers extraction for {domain}")

    # Step 1: Find the careers URL (use known URL if available)
    if known_careers_url:
        careers_url = known_careers_url
        logger.info(f"[Playwright] Using known careers URL: {careers_url}")
    else:
        careers_url = await find_careers_url(domain)

    if not careers_url:
        logger.warning(f"[Playwright] No careers URL found for {domain}")
        return None

    # Step 2: Capture with Playwright
    service = BrowserCaptureService()
    await service.initialize()

    try:
        capture = await service.capture_page(
            url=careers_url,
            timeout_ms=30000,
            intercept_network=True,
        )

        if capture.error:
            logger.warning(
                f"[Playwright] Browser capture error for {domain}: {capture.error}"
            )
            return None

        if not capture.rendered_html or len(capture.rendered_html) < 200:
            # Some ATS pages start empty and load via JS — try waiting longer
            logger.warning(
                f"[Playwright] Short HTML for {domain} ({len(capture.rendered_html or '')} chars), retrying with longer wait"
            )
            try:
                page = await service._context.new_page()
                await page.goto(careers_url, wait_until="domcontentloaded", timeout=12000)
                # Wait for job listings to appear — cap the whole loop at 10s
                # so a site with many misses can't burn 30s (6 × 5s).
                selector_deadline = _time.monotonic() + 10.0
                for selector in ["[data-testid='job']", ".job-card", ".posting", ".job-listing", "[class*='job']", "[class*='posting']"]:
                    remaining_ms = int((selector_deadline - _time.monotonic()) * 1000)
                    if remaining_ms <= 0:
                        break
                    try:
                        await page.wait_for_selector(
                            selector, timeout=min(3000, remaining_ms)
                        )
                        break
                    except Exception:
                        continue
                capture2_html = await page.content()
                capture2_text = await page.evaluate("document.body?.innerText || ''")
                if len(capture2_html) > len(capture.rendered_html or ''):
                    capture.rendered_html = capture2_html
                    capture.visible_text = capture2_text
                    logger.info(f"[Playwright] Retry got {len(capture2_html)} chars HTML")
                await page.close()
            except Exception as retry_err:
                logger.warning(f"[Playwright] Retry failed: {retry_err}")

        if not capture.rendered_html or len(capture.rendered_html) < 200:
            logger.warning(
                f"[Playwright] Empty/short HTML for {domain} ({len(capture.rendered_html or '')} chars)"
            )
            return None

        logger.info(
            f"[Playwright] Captured {domain}: "
            f"{len(capture.rendered_html)} chars HTML, "
            f"{len(capture.visible_text)} chars text, "
            f"{len(capture.api_calls)} API calls, "
            f"load_time={capture.load_time_ms}ms"
        )

        # Step 3: Hybrid extraction
        extraction = await hybrid_careers_extractor.extract(
            rendered_html=capture.rendered_html,
            visible_text=capture.visible_text,
            visible_links=capture.visible_links,
            network_requests=capture.network_requests,
            network_responses=capture.network_responses,
            embedded_json=capture.embedded_json,
            page_state=capture.page_state,
            source_url=capture.final_url or careers_url,
            preload_state=capture.preload_state,
        )

        # Step 4: Persist signals
        new_signals: List[CompanySignal] = []

        if extraction.open_positions_count:
            signal_type = (
                "high_open_positions_count_detected"
                if extraction.open_positions_count >= 100
                else "open_positions_count_detected"
            )
            new_signals.append(
                CompanySignal(
                    company_id=company_id,
                    source_type="playwright_careers",
                    source_url=capture.final_url or careers_url,
                    signal_type=signal_type,
                    signal_text=f"Open positions: {extraction.open_positions_count}",
                    numeric_value=extraction.open_positions_count,
                    confidence=0.9,
                )
            )

        if extraction.visible_role_cards:
            new_signals.append(
                CompanySignal(
                    company_id=company_id,
                    source_type="playwright_careers",
                    source_url=capture.final_url or careers_url,
                    signal_type="job_cards_visible_detected",
                    signal_text=f"Visible job listings: {len(extraction.visible_role_cards)} jobs",
                    numeric_value=len(extraction.visible_role_cards),
                    confidence=0.85,
                )
            )

        if extraction.visible_hiring_areas:
            for area in extraction.visible_hiring_areas[:5]:
                area_key = (
                    area.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
                )
                new_signals.append(
                    CompanySignal(
                        company_id=company_id,
                        source_type="playwright_careers",
                        source_url=capture.final_url or careers_url,
                        signal_type=f"{area_key}_hiring_detected",
                        signal_text=f"Hiring area detected: {area}",
                        confidence=0.8,
                    )
                )

        # Persist with deduplication
        if new_signals:
            _persist_signals_deduped(db, company_id, new_signals)

        # Step 5: Persist job roles if table exists
        job_roles_saved = 0
        if extraction.visible_role_cards:
            job_roles_saved = _persist_job_roles(db, company_id, extraction.visible_role_cards, careers_url)

        logger.info(
            f"[Playwright] Extraction complete for {domain}: "
            f"{len(new_signals)} signals, {job_roles_saved} job roles, "
            f"source={extraction.source_of_truth}, "
            f"quality={extraction.evidence_quality}"
        )

        return extraction.open_positions_count if extraction else None

    except Exception as e:
        logger.error(f"[Playwright] Extraction failed for {domain}: {e}")
        return None
    finally:
        await service.cleanup()


def run_collection_for_company(
    company_id: UUID, run_id: UUID
) -> dict:
    """
    Run all synchronous collectors for a company SEQUENTIALLY.

    Creates its own DB session to avoid using a closed session from
    the request lifecycle (BackgroundTasks outlive the response).

    Returns a dict with metadata about the run.
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        return _run_collection_inner(db, company_id, run_id)
    finally:
        db.close()


def _run_collection_inner(db: Session, company_id: UUID, run_id: UUID) -> dict:
    """Inner implementation — runs inside a dedicated DB session."""
    logger.info(f"[Collector] Starting collection for company {company_id}, run {run_id}")

    company = db.query(Company).filter(Company.id == company_id).first()
    run = db.query(CollectionRun).filter(CollectionRun.id == run_id).first()

    if not company or not run:
        logger.error("[Collector] Company or Run not found. Aborting.")
        return {"status": "error", "message": "Company or Run not found"}

    collector_results = []

    try:
        run.status = "running"
        db.commit()

        new_signals: List[CompanySignal] = []

        # Run each collector sequentially — safe, simple, no shared state
        for collector in ACTIVE_COLLECTORS:
            cname = collector.collector_type
            try:
                extracted = collector.collect(company)
                count = len(extracted)
                for sig in extracted:
                    new_signals.append(
                        CompanySignal(
                            company_id=company.id,
                            source_type=sig.source_type,
                            source_url=sig.source_url,
                            signal_type=sig.signal_type,
                            signal_text=sig.signal_text,
                            numeric_value=sig.numeric_value,
                            confidence=sig.confidence,
                        )
                    )
                collector_results.append(
                    {"collector": cname, "signals": count, "status": "ok"}
                )
                logger.info(
                    f"[Collector] {cname}: {count} signals for {company.domain}"
                )
            except Exception as e:
                collector_results.append(
                    {"collector": cname, "signals": 0, "status": f"error: {e}"}
                )
                logger.error(
                    f"[Collector] {cname} FAILED for {company.domain}: {e}",
                    exc_info=True,
                )

        # Deduplicate against existing + current batch
        persisted_count = _persist_signals_deduped(db, company_id, new_signals)

        # Update run status
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.metadata_json = {
            "signals_extracted": persisted_count,
            "collectors_run": collector_results,
            "total_raw_signals": len(new_signals),
        }
        db.commit()

        # Structured summary log
        careers_found = any(
            s.signal_type == "careers_page_found" for s in new_signals
        )
        roles_found = sum(
            1 for s in new_signals
            if s.signal_type in ("job_cards_visible_detected", "job_links_extracted")
        )
        errors = [r for r in collector_results if r["status"].startswith("error")]

        logger.info(
            f"[Collector] DONE {company.domain}: "
            f"persisted={persisted_count}, raw={len(new_signals)}, "
            f"careers={'YES' if careers_found else 'NO'}, "
            f"role_signals={roles_found}, "
            f"errors={len(errors)}/{len(ACTIVE_COLLECTORS)}"
        )

        return {
            "status": "completed",
            "signals_persisted": persisted_count,
            "signals_raw": len(new_signals),
            "careers_found": careers_found,
            "collectors": collector_results,
        }

    except Exception as e:
        logger.error(f"[Collector] Orchestration FAILED for run {run_id}: {e}", exc_info=True)
        run.status = "failed"
        run.error_message = str(e)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "error", "message": str(e), "collectors": collector_results}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _persist_signals_deduped(
    db: Session, company_id: UUID, new_signals: List[CompanySignal]
) -> int:
    """Persist signals, deduplicating by signal_type within a company.

    When a signal_type already exists, the new signal replaces it only if
    it has more evidence (non-zero numeric_value) or higher confidence.
    """
    if not new_signals:
        return 0

    existing = (
        db.query(CompanySignal.signal_type, CompanySignal.numeric_value, CompanySignal.confidence)
        .filter(CompanySignal.company_id == company_id)
        .all()
    )
    seen_types = {}  # signal_type -> (numeric_value, confidence)
    for s in existing:
        seen_types[s.signal_type] = (s.numeric_value or 0, s.confidence or 0)

    deduped = []
    for s in new_signals:
        old_val, old_conf = seen_types.get(s.signal_type, (0, 0))
        new_val = s.numeric_value or 0
        new_conf = s.confidence or 0

        if s.signal_type not in seen_types:
            # New signal type — always persist
            seen_types[s.signal_type] = (new_val, new_conf)
            deduped.append(s)
        elif new_val > old_val or new_conf > old_conf:
            # Better evidence — update existing
            existing_signal = (
                db.query(CompanySignal)
                .filter(
                    CompanySignal.company_id == company_id,
                    CompanySignal.signal_type == s.signal_type,
                )
                .first()
            )
            if existing_signal:
                existing_signal.numeric_value = s.numeric_value
                existing_signal.confidence = s.confidence
                existing_signal.signal_text = s.signal_text
                existing_signal.source_url = s.source_url
                seen_types[s.signal_type] = (new_val, new_conf)
                # Don't add to deduped (update, not insert)

    if deduped:
        db.add_all(deduped)
        db.commit()
        logger.info(
            f"[Dedup] {len(deduped)}/{len(new_signals)} signals persisted "
            f"({len(new_signals) - len(deduped)} duplicates skipped)"
        )

    return len(deduped)


def _persist_job_roles(
    db: Session, company_id: UUID, role_cards: list, careers_url: str
) -> int:
    """Persist job roles if the table exists. Returns count saved."""
    try:
        from app.services.role_ingest import persist_job_role

        saved = 0
        for card in role_cards[:20]:
            if persist_job_role(
                db,
                company_id=company_id,
                raw_title=card.title,
                source_url=card.job_url or careers_url,
                role_location=card.location,
            ) is not None:
                saved += 1
        db.commit()
        return saved

    except Exception as e:
        logger.debug(f"[JobRoles] Could not persist (table may not exist): {e}")
        db.rollback()
        return 0

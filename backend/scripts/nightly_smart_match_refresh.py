"""Nightly refresh of smart_match_cache (cron 1 AM).

For every company (or a subset when `--limit` is given) this script:

  1. Recomputes the verdict (reuses final_verdict_engine / company_evaluation /
     positioning_engine — the same logic used by the dashboard).
  2. Builds the denormalized cache row.
  3. Embeds the pain text into vector(1536) via OpenAI.
  4. Upserts into `smart_match_cache`.

The script is idempotent. Each company is skipped if its cache row was
refreshed within the last 18h (unless `--force` is passed).

Parallelism: `--parallel N` dispatches companies to a ThreadPoolExecutor,
each worker owns its own SQLAlchemy session. I/O-bound work (OpenAI +
Supabase) benefits from this. Default is 4 workers.

Usage
-----
    python scripts/nightly_smart_match_refresh.py              # all companies, 4 workers
    python scripts/nightly_smart_match_refresh.py --limit 5    # smoke test
    python scripts/nightly_smart_match_refresh.py --dry-run    # no DB writes
    python scripts/nightly_smart_match_refresh.py --force      # ignore 18h skip window
    python scripts/nightly_smart_match_refresh.py --parallel 8 # 8 concurrent workers
    python scripts/nightly_smart_match_refresh.py --parallel 1 # sequential

Cron
----
    0 1 * * * cd /path/frictionradar/backend && \\
        venv/bin/python scripts/nightly_smart_match_refresh.py >> \\
        /var/log/friction/nightly.log 2>&1
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env BEFORE importing app modules so OPENAI_API_KEY is visible to
# smart_match_engine._get_openai_client() (uses os.environ.get directly).
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.core.logging import get_logger, setup_logging
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.friction_score import FrictionScore
from app.models.smart_match_cache import SmartMatchCache
from app.services import company_service, smart_match_engine
from app.services.company_evaluation import company_evaluation_engine
from app.services.company_type_engine import company_type_engine
from app.services.final_verdict_engine import final_verdict_engine
from app.services.positioning_engine import is_company_positioning_eligible

logger = get_logger("nightly_smart_match_refresh")


SKIP_WINDOW_SECONDS = 18 * 3600  # 18h — 6h tail after 1 AM run completes


def _process_company(
    db, company: Company, run_id: str, *, dry_run: bool
) -> tuple[str, bool]:
    """Compute + upsert cache for one company.

    Returns (gate_label, had_embedding).
    had_embedding = True iff embed_pain returned a non-null vector.
    """
    signals = company_service.get_signals(db, company.id)
    collection_runs = company_service.get_collection_runs(db, company.id)
    score = (
        db.query(FrictionScore)
        .filter(FrictionScore.company_id == company.id)
        .order_by(FrictionScore.created_at.desc())
        .first()
    )
    evaluation = company_evaluation_engine.evaluate(company_id=company.id, db=db)
    eligibility = is_company_positioning_eligible(db, company.id)
    type_result = company_type_engine.analyze(signals, len(signals), False)
    verdict = final_verdict_engine.generate(
        company=company,
        signals=signals,
        score=score,
        hypothesis=None,
        company_type=type_result.get("company_type", "unclear"),
        collection_runs=collection_runs,
        db=db,
    )

    row_values = smart_match_engine.build_cache_row_values(
        company=company,
        verdict=verdict,
        score=score,
        evaluation=evaluation,
        eligibility=eligibility,
        run_id=run_id,
    )
    embedding = smart_match_engine.embed_pain(row_values)
    row_values["pain_embedding"] = embedding
    row_values["refreshed_at"] = datetime.now(timezone.utc)
    had_embedding = embedding is not None

    gate = row_values.get("eligibility_gate") or "none"
    if dry_run:
        return gate, had_embedding

    existing = (
        db.query(SmartMatchCache)
        .filter(SmartMatchCache.company_id == company.id)
        .first()
    )
    if existing is None:
        db.add(SmartMatchCache(**row_values))
    else:
        for key, val in row_values.items():
            setattr(existing, key, val)
    db.commit()
    return gate, had_embedding


def _worker(
    company_id: UUID, run_id: str, *, force: bool, dry_run: bool
) -> tuple[UUID, str, str | None, bool]:
    """Owns its own DB session. Returns (company_id, outcome, detail, had_embedding).

    outcome ∈ {'processed', 'skipped_recent', 'error'}
    detail holds the gate label on processed, or the error repr on error.
    had_embedding is True iff the row was persisted with a non-null pain_embedding.
    """
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company is None:
            return company_id, "error", "company not found", False

        if not force:
            cached = (
                db.query(SmartMatchCache)
                .filter(SmartMatchCache.company_id == company_id)
                .first()
            )
            cutoff = datetime.now(timezone.utc).timestamp() - SKIP_WINDOW_SECONDS
            if cached and cached.refreshed_at and cached.refreshed_at.timestamp() > cutoff:
                return company_id, "skipped_recent", None, False

        try:
            gate, had_embedding = _process_company(db, company, run_id, dry_run=dry_run)
            return company_id, "processed", gate, had_embedding
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            logger.exception(
                "smart_match_refresh: company=%s (%s) failed",
                company.name,
                company.domain,
            )
            return company_id, "error", f"{type(exc).__name__}: {exc}", False
    finally:
        db.close()


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Nightly smart_match_cache refresh")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N companies")
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not upsert")
    parser.add_argument("--force", action="store_true", help="Ignore 18h skip window")
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Concurrent workers (ThreadPoolExecutor). Default: 4.",
    )
    args = parser.parse_args()
    parallel = max(1, int(args.parallel))

    run_id = f"nightly-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}"
    logger.info(
        "smart_match_refresh run_id=%s dry_run=%s force=%s parallel=%s",
        run_id, args.dry_run, args.force, parallel,
    )

    started_at = time.time()

    # Load company IDs in the main thread (workers open their own sessions).
    main_db = SessionLocal()
    try:
        q = main_db.query(Company.id).filter(
            Company.source_added_from != "synthetic_generator"
        )
        if args.limit:
            q = q.limit(args.limit)
        company_ids = [row.id for row in q.all()]
    finally:
        main_db.close()

    total = len(company_ids)
    gate_counts: Counter = Counter()
    processed = 0
    skipped_recent = 0
    errors = 0
    embeddings_generated = 0
    embeddings_null = 0
    progress_lock = threading.Lock()

    def _log_progress(i: int) -> None:
        if i % 25 == 0 or i == total:
            logger.info(
                "progress: %s/%s processed=%s skipped_recent=%s errors=%s",
                i, total, processed, skipped_recent, errors,
            )

    if parallel == 1:
        for idx, cid in enumerate(company_ids, start=1):
            _, outcome, detail, had_emb = _worker(
                cid, run_id, force=args.force, dry_run=args.dry_run
            )
            if outcome == "processed":
                processed += 1
                gate_counts[detail or "none"] += 1
                if had_emb:
                    embeddings_generated += 1
                else:
                    embeddings_null += 1
            elif outcome == "skipped_recent":
                skipped_recent += 1
            else:
                errors += 1
            _log_progress(idx)
    else:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(
                    _worker, cid, run_id, force=args.force, dry_run=args.dry_run
                ): cid
                for cid in company_ids
            }
            done_count = 0
            for fut in as_completed(futures):
                done_count += 1
                try:
                    _, outcome, detail, had_emb = fut.result()
                except Exception as exc:
                    # worker() already catches; this is belt & suspenders
                    errors += 1
                    logger.exception("worker crashed: %s", exc)
                    with progress_lock:
                        _log_progress(done_count)
                    continue

                if outcome == "processed":
                    processed += 1
                    gate_counts[detail or "none"] += 1
                    if had_emb:
                        embeddings_generated += 1
                    else:
                        embeddings_null += 1
                elif outcome == "skipped_recent":
                    skipped_recent += 1
                else:
                    errors += 1
                with progress_lock:
                    _log_progress(done_count)

    elapsed = time.time() - started_at
    logger.info(
        "smart_match_refresh done run_id=%s total=%s processed=%s skipped_recent=%s errors=%s "
        "gates=%s embeddings_generated=%s embeddings_null=%s elapsed=%.1fs",
        run_id, total, processed, skipped_recent, errors,
        dict(gate_counts), embeddings_generated, embeddings_null, elapsed,
    )
    if embeddings_null > 0 and embeddings_generated == 0:
        logger.warning(
            "All embeddings came back null — OPENAI_API_KEY is likely missing or "
            "invalid. Smart-Match cosine ranking will fall back to recency order."
        )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

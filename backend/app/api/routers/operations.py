"""Operations API — pipeline status, run history, and manual trigger."""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.collection_run import CollectionRun
from app.models.company_signal import CompanySignal
from app.models.candidate_intelligence import FrictionVipOpportunity

router = APIRouter()

RUNS_DIR = Path("runs")
LOCK_FILE = RUNS_DIR / "nightly_running.lock"
RESULT_FILE = RUNS_DIR / "nightly_last_result.json"

STEP_LABELS = {
    "1_ats_refresh": "ATS Refresh",
    "2_careers_refresh": "Careers Refresh",
    "3_signal_extraction": "Signal Extraction",
    "4_pain_recomputation": "Pain Recomputation",
    "5_heatmap_regen": "Heatmap Regeneration",
    "6_candidate_alignment": "Candidate Alignment",
    "7_vip_regeneration": "VIP Regeneration",
    "8_snapshot_persistence": "Snapshot Persistence",
    "9_temporal_tracking": "Temporal Tracking",
    "10_delta_computation": "Delta Computation",
}


def _read_last_result() -> Optional[Dict[str, Any]]:
    if RESULT_FILE.exists():
        try:
            return json.loads(RESULT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _is_running() -> bool:
    return LOCK_FILE.exists()


def _run_nightly_background():
    """Run the nightly orchestrator in a background process, writing result files."""
    from app.db.session import SessionLocal
    from app.services.nightly_orchestrator import nightly_orchestrator

    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        summary = nightly_orchestrator.run(db)
        RESULT_FILE.write_text(json.dumps(summary, default=str))
    except Exception as e:
        RESULT_FILE.write_text(json.dumps({"error": str(e)}, default=str))
    finally:
        db.close()
        if LOCK_FILE.exists():
            LOCK_FILE.unlink(missing_ok=True)


@router.get("/pipeline/status")
def pipeline_status(db: Session = Depends(get_db)):
    """Return current pipeline status: last run, collection stats, signal freshness, VIP stats, cron jobs."""
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    # ── Nightly run result ──────────────────────────────────────
    nightly_run = _read_last_result()
    nightly_running = _is_running()

    # ── Collection run stats (last 24h) ───────────────────────
    collection_stats = (
        db.query(
            CollectionRun.status,
            func.count(CollectionRun.id),
        )
        .filter(CollectionRun.started_at >= cutoff_24h)
        .group_by(CollectionRun.status)
        .all()
    )
    stats_24h = {status: count for status, count in collection_stats}
    collection_summary = {
        "total_runs_24h": sum(stats_24h.values()),
        "completed_24h": stats_24h.get("completed", 0),
        "failed_24h": stats_24h.get("failed", 0),
        "running_now": stats_24h.get("running", 0) + stats_24h.get("pending", 0),
    }

    # ── Signal freshness ────────────────────────────────────────
    try:
        freshness_rows = db.execute(text("""
            SELECT
                COUNT(DISTINCT cs.company_id) FILTER (WHERE cs.created_at >= :cutoff_24h) AS last_24h,
                COUNT(DISTINCT cs.company_id) FILTER (WHERE cs.created_at >= :cutoff_7d) AS last_7d,
                COUNT(DISTINCT cs.company_id) AS total
            FROM company_signals cs
        """), {"cutoff_24h": cutoff_24h, "cutoff_7d": now - timedelta(days=7)}).one()

        total_companies = db.query(func.count()).select_from(
            db.query(CompanySignal.company_id).distinct().subquery()
        ).scalar() or freshness_rows.total

        signal_freshness = {
            "total_companies": total_companies or freshness_rows.total,
            "signal_last_24h": freshness_rows.last_24h or 0,
            "signal_last_7d": freshness_rows.last_7d or 0,
            "signal_older": (freshness_rows.total or 0) - (freshness_rows.last_7d or 0),
        }
    except Exception:
        signal_freshness = {"total_companies": 0, "signal_last_24h": 0, "signal_last_7d": 0, "signal_older": 0}

    # ── VIP stats ──────────────────────────────────────────────
    try:
        vip_row = db.query(
            func.count(FrictionVipOpportunity.id).filter(FrictionVipOpportunity.is_active == True),  # noqa: E712
            func.max(FrictionVipOpportunity.generated_at),
        ).filter(FrictionVipOpportunity.user_id.isnot(None)).one()

        vip_summary = {
            "active_opportunities": vip_row[0] or 0,
            "last_generated_at": vip_row[1].isoformat() if vip_row[1] else None,
        }
    except Exception:
        vip_summary = {"active_opportunities": 0, "last_generated_at": None}

    # ── Cron jobs ──────────────────────────────────────────────
    cron_jobs: List[Dict] = []
    try:
        cron_rows = db.execute(text("""
            SELECT j.jobid, j.schedule, j.command, j.active,
                   jr.start_time, jr.end_time, jr.status, jr.return_message
            FROM cron.job j
            LEFT JOIN LATERAL (
                SELECT jr2.start_time, jr2.end_time, jr2.status, jr2.return_message
                FROM cron.job_run_details jr2
                WHERE jr2.jobid = j.jobid
                ORDER BY jr2.start_time DESC
                LIMIT 5
            ) jr ON true
            ORDER BY j.jobid, jr.start_time DESC NULLS LAST
        """)).fetchall()

        jobs_map: Dict[int, Dict] = {}
        for row in cron_rows:
            job_id = row[0]
            if job_id not in jobs_map:
                jobs_map[job_id] = {
                    "job_name": row[2].strip().split("(")[0].replace("SELECT ", "") if row[2] else "",
                    "schedule": row[1],
                    "command": row[2],
                    "active": row[3],
                    "last_runs": [],
                }
            if row[4]:  # has run details
                jobs_map[job_id]["last_runs"].append({
                    "start_time": row[4].isoformat() if row[4] else None,
                    "end_time": row[5].isoformat() if row[5] else None,
                    "status": row[6],
                    "return_message": row[7],
                })
        cron_jobs = list(jobs_map.values())
    except Exception:
        cron_jobs = []

    return {
        "nightly_run": nightly_run,
        "nightly_running": nightly_running,
        "collection_stats": collection_summary,
        "signal_freshness": signal_freshness,
        "vip_stats": vip_summary,
        "cron_jobs": cron_jobs,
    }


@router.post("/pipeline/trigger")
def trigger_nightly(background_tasks: BackgroundTasks):
    """Trigger the nightly pipeline as a background task."""
    if _is_running():
        raise HTTPException(status_code=409, detail="Pipeline already running")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    run_id = f"nightly-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    LOCK_FILE.write_text(json.dumps({"run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat()}))

    background_tasks.add_task(_run_nightly_background)

    return {"status": "started", "run_id": run_id}
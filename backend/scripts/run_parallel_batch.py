"""
Parallel Batch Orchestrator - multi-process execution for Friction Radar.

Launches N independent OS processes, each running batch_runner.py on a
separate shard of companies. Each worker is fully sequential internally
(no threads, no shared sessions). The master only reads progress files
and displays a live dashboard.

Architecture:
    Master (this script)
      ├── reads all companies from DB
      ├── splits into N shards
      ├── writes shard_NN.json files
      ├── launches N subprocess workers
      ├── polls progress.json files every few seconds
      ├── displays live table in console
      └── consolidates master_summary.json at end

    Worker (batch_runner.py --shard-file ...)
      ├── reads companies from shard JSON file
      ├── processes each company sequentially (full pipeline)
      ├── writes progress.json after each company (atomic)
      ├── writes summary.json at completion
      └── writes standard JSONL progress + manifest

Usage from PowerShell:

    # 4 processes
    python scripts/run_parallel_batch.py --processes 4 --run-id test_p4

    # 6 processes
    python scripts/run_parallel_batch.py --processes 6 --run-id test_p6

    # 8 processes, custom poll interval
    python scripts/run_parallel_batch.py --processes 8 --run-id test_p8 --poll-interval 10

    # Dry run (show shard plan without executing)
    python scripts/run_parallel_batch.py --processes 4 --run-id test_p4 --dry-run

    # Verbose logging
    python scripts/run_parallel_batch.py --processes 4 --run-id test_p4 --verbose
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Constants ────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent.parent
BATCH_RUNNER = BACKEND_DIR / "scripts" / "batch_runner.py"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "output" / "parallel_runs"


# ── Company selection (reuses DB logic from batch_runner) ────────────

def load_companies_from_db(limit: int | None = None) -> list[dict]:
    """Load all companies with domain from the database."""
    from sqlalchemy import func as sqlfunc
    from app.db.session import SessionLocal
    from app.models.company import Company
    from app.models.company_job_role import CompanyJobRole

    db = SessionLocal()
    try:
        role_map = {}
        role_counts = (
            db.query(
                CompanyJobRole.company_id,
                sqlfunc.count(CompanyJobRole.id).label("cnt"),
            )
            .group_by(CompanyJobRole.company_id)
            .all()
        )
        for cid, cnt in role_counts:
            role_map[cid] = cnt

        query = db.query(Company).filter(
            Company.domain.isnot(None), Company.domain != ""
        )
        if limit:
            query = query.limit(limit)

        all_companies = query.all()

        candidates = []
        for c in all_companies:
            roles = role_map.get(c.id, 0)
            candidates.append({
                "id": str(c.id),
                "name": c.name,
                "domain": c.domain,
                "roles": roles,
            })

        # Sort: companies with roles first (desc), then rest alphabetically
        candidates.sort(key=lambda x: (-x["roles"], x["name"].lower()))
        return candidates
    finally:
        db.close()


def load_companies_from_file(path: str) -> list[dict]:
    """Load companies from a JSON export file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        companies = []
        for item in data:
            companies.append({
                "id": str(item.get("id", "")),
                "name": item.get("name", item.get("company_name", "")),
                "domain": item.get("domain", ""),
                "roles": item.get("roles", 0),
            })
        return [c for c in companies if c["domain"]]
    raise ValueError(f"Unexpected JSON format in {path}")


# ── Sharding ─────────────────────────────────────────────────────────

def split_into_shards(companies: list[dict], n: int) -> list[list[dict]]:
    """Split company list into N roughly equal shards."""
    shards = [[] for _ in range(n)]
    for i, company in enumerate(companies):
        shards[i % n].append(company)
    return shards


# ── Process management ───────────────────────────────────────────────

def launch_worker(
    shard_index: int,
    shard_total: int,
    shard_file: Path,
    shard_dir: Path,
    parent_run_id: str,
    full_pipeline: bool,
    verbose: bool,
) -> subprocess.Popen:
    """Launch a single worker subprocess running batch_runner.py in shard mode."""
    cmd = [
        sys.executable, str(BATCH_RUNNER),
        "--shard-file", str(shard_file),
        "--shard-index", str(shard_index),
        "--shard-total", str(shard_total),
        "--shard-progress-dir", str(shard_dir),
        "--parent-run-id", parent_run_id,
        "--label", f"shard_{shard_index:02d}",
    ]
    if full_pipeline:
        cmd.append("--full-pipeline")

    log_file = shard_dir / "logs" / "worker.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    stdout_target = None if verbose else open(log_file, "w", encoding="utf-8")
    stderr_target = subprocess.STDOUT if not verbose else None

    proc = subprocess.Popen(
        cmd,
        stdout=stdout_target,
        stderr=stderr_target if not verbose else subprocess.STDOUT,
        cwd=str(BACKEND_DIR),
        env={**os.environ},
    )
    return proc


# ── Progress monitoring ──────────────────────────────────────────────

def read_shard_progress(shard_dir: Path) -> dict | None:
    """Read progress.json from a shard directory. Returns None if not ready."""
    progress_file = shard_dir / "progress.json"
    if not progress_file.exists():
        return None
    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def format_eta(seconds: int) -> str:
    """Format seconds as HH:MM:SS."""
    if seconds <= 0:
        return "--:--:--"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as HH:MM:SS."""
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def clear_lines(n: int):
    """Move cursor up N lines and clear them."""
    for _ in range(n):
        sys.stdout.write("\033[A\033[2K")
    sys.stdout.flush()


def print_dashboard(
    run_id: str,
    process_count: int,
    shard_dirs: list[Path],
    procs: list[subprocess.Popen],
    start_time: float,
    total_companies: int,
    prev_lines: int,
) -> int:
    """Print live dashboard. Returns number of lines printed."""
    if prev_lines > 0:
        clear_lines(prev_lines)

    progresses = []
    for sd in shard_dirs:
        p = read_shard_progress(sd)
        progresses.append(p)

    # Global aggregates
    global_processed = 0
    global_success = 0
    global_failed = 0
    global_careers = 0
    global_roles = 0
    global_classified = 0
    global_jds = 0
    global_eligible = 0

    for p in progresses:
        if p:
            global_processed += p.get("processed", 0)
            global_success += p.get("success", 0)
            global_failed += p.get("failed", 0)
            global_careers += p.get("careers_found", 0)
            global_roles += p.get("roles_detected", 0)
            global_classified += p.get("roles_classified", 0)
            global_jds += p.get("jds_extracted", 0)
            global_eligible += p.get("eligible_positioning", 0)

    elapsed = time.monotonic() - start_time
    global_pct = global_processed / max(total_companies, 1) * 100
    if global_processed > 0:
        avg = elapsed / global_processed
        global_eta = avg * (total_companies - global_processed)
    else:
        global_eta = 0

    lines = []
    lines.append(f"")
    lines.append(f"  Run: {run_id}")
    lines.append(f"  Processes: {process_count}  |  Global: {global_processed}/{total_companies} ({global_pct:.1f}%)  |  Elapsed: {format_elapsed(elapsed)}  |  ETA: {format_eta(int(global_eta))}")
    lines.append(f"  Success: {global_success}  |  Failed: {global_failed}  |  Careers: {global_careers}  |  Roles: {global_roles}  |  Classified: {global_classified}  |  JDs: {global_jds}  |  Eligible: {global_eligible}")
    lines.append(f"  {'-'*110}")

    # Header
    lines.append(
        f"  {'PID':<8s} {'Shard':<8s} {'Done/Total':<12s} {'%':>6s}  "
        f"{'OK':>5s} {'Fail':>5s}  {'Current Company':<28s} {'Stage':<14s} {'ETA':>10s}"
    )
    lines.append(f"  {'-'*110}")

    for i, (p, proc) in enumerate(zip(progresses, procs)):
        pid = proc.pid if proc else "?"
        alive = proc.poll() is None if proc else False

        if p:
            done = p.get("processed", 0)
            total = p.get("total_in_shard", 0)
            pct = p.get("percent", 0)
            ok = p.get("success", 0)
            fail = p.get("failed", 0)
            company = p.get("current_company_name", "")[:27]
            stage = p.get("current_stage", "")[:13]
            eta = format_eta(p.get("eta_sec", 0))
            status_marker = "" if alive else " [DONE]" if p.get("status") == "completed" else " [EXIT]"
            lines.append(
                f"  {pid:<8} {i}/{process_count:<6} {done}/{total:<10} {pct:>5.1f}%  "
                f"{ok:>5d} {fail:>5d}  {company:<28s} {stage:<14s} {eta:>10s}{status_marker}"
            )
        else:
            status = "starting..." if alive else "not started"
            lines.append(
                f"  {pid:<8} {i}/{process_count:<6} {'--':>10}  {'--':>5}%  "
                f"{'--':>5} {'--':>5}  {status:<28s} {'':14s} {'--:--:--':>10s}"
            )

    lines.append(f"  {'-'*110}")
    lines.append(f"  Press Ctrl+C to stop gracefully")

    output = "\n".join(lines)
    print(output)
    return len(lines)


# ── Consolidation ────────────────────────────────────────────────────

def consolidate_results(
    run_dir: Path,
    run_id: str,
    process_count: int,
    total_companies: int,
    shard_dirs: list[Path],
    start_time: float,
):
    """Read all shard summaries and produce master_summary.json."""
    elapsed = time.monotonic() - start_time
    shard_summaries = []

    global_processed = 0
    global_success = 0
    global_failed = 0
    global_skipped = 0
    global_careers = 0
    global_roles = 0
    global_classified = 0
    global_jds = 0
    global_eligible = 0
    error_messages = []

    for sd in shard_dirs:
        summary_file = sd / "summary.json"
        progress_file = sd / "progress.json"

        data = None
        for f in [summary_file, progress_file]:
            if f.exists():
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    break
                except (json.JSONDecodeError, OSError):
                    continue

        if data:
            shard_summaries.append(data)
            global_processed += data.get("processed", 0)
            global_success += data.get("success", 0)
            global_failed += data.get("failed", 0)
            global_skipped += data.get("skipped", 0)
            global_careers += data.get("careers_found", 0)
            global_roles += data.get("roles_detected", 0)
            global_classified += data.get("roles_classified", 0)
            global_jds += data.get("jds_extracted", 0)
            global_eligible += data.get("eligible_positioning", 0)
            if data.get("last_error_message"):
                error_messages.append({
                    "shard": data.get("shard_index", "?"),
                    "message": data["last_error_message"],
                })

    throughput = global_processed / max(elapsed / 60, 0.001)
    avg_sec = elapsed / max(global_processed, 1)

    master_summary = {
        "run_id": run_id,
        "process_count": process_count,
        "total_companies": total_companies,
        "processed": global_processed,
        "success": global_success,
        "failed": global_failed,
        "skipped": global_skipped,
        "duration_sec": round(elapsed),
        "avg_sec_per_company": round(avg_sec, 2),
        "throughput_companies_per_min": round(throughput, 2),
        "coverage_funnel": {
            "careers_found": global_careers,
            "roles_detected": global_roles,
            "roles_classified": global_classified,
            "jds_extracted": global_jds,
            "eligible_positioning": global_eligible,
        },
        "top_failure_reasons": error_messages[:20],
        "shard_summaries": shard_summaries,
        "started_at": datetime.fromtimestamp(
            time.time() - elapsed, tz=timezone.utc
        ).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    summary_path = run_dir / "master_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(master_summary, f, indent=2, default=str)

    return master_summary


def print_final_summary(summary: dict):
    """Print the final consolidated summary."""
    print(f"\n{'='*80}")
    print(f"  FINAL SUMMARY - {summary['run_id']}")
    print(f"{'='*80}")
    print(f"  Processes:          {summary['process_count']}")
    print(f"  Total companies:    {summary['total_companies']}")
    print(f"  Processed:          {summary['processed']}")
    print(f"  Success:            {summary['success']}")
    print(f"  Failed:             {summary['failed']}")
    print(f"  Duration:           {format_elapsed(summary['duration_sec'])}")
    print(f"  Avg/company:        {summary['avg_sec_per_company']:.1f}s")
    print(f"  Throughput:         {summary['throughput_companies_per_min']:.1f} companies/min")
    print()
    funnel = summary.get("coverage_funnel", {})
    print(f"  Coverage Funnel:")
    print(f"    Careers found:        {funnel.get('careers_found', 0)}")
    print(f"    Roles detected:       {funnel.get('roles_detected', 0)}")
    print(f"    Roles classified:     {funnel.get('roles_classified', 0)}")
    print(f"    JDs extracted:        {funnel.get('jds_extracted', 0)}")
    print(f"    Eligible positioning: {funnel.get('eligible_positioning', 0)}")

    errors = summary.get("top_failure_reasons", [])
    if errors:
        print(f"\n  Top failures:")
        for e in errors[:5]:
            print(f"    Shard {e['shard']}: {e['message'][:80]}")

    print(f"\n  Per-shard breakdown:")
    for ss in summary.get("shard_summaries", []):
        idx = ss.get("shard_index", "?")
        proc = ss.get("processed", 0)
        ok = ss.get("success", 0)
        fail = ss.get("failed", 0)
        el = ss.get("elapsed_sec", 0)
        avg = ss.get("avg_sec_per_company", 0)
        print(f"    Shard {idx}: {proc} processed, {ok} ok, {fail} fail, {format_elapsed(el)}, {avg:.1f}s/co")

    print(f"{'='*80}")


# ── Dynamic scheduling (chunk-queue mode) ───────────────────────────

def split_into_chunks(companies: list[dict], chunk_size: int) -> list[list[dict]]:
    """Split companies into fixed-size chunks (last chunk may be smaller)."""
    return [companies[i:i + chunk_size] for i in range(0, len(companies), chunk_size)]


def launch_dynamic_worker(
    worker_id: int,
    queue_dir: Path,
    worker_dir: Path,
    parent_run_id: str,
    full_pipeline: bool,
    verbose: bool,
) -> subprocess.Popen:
    """Launch a subprocess worker that claims chunks from queue_dir."""
    cmd = [
        sys.executable, str(BATCH_RUNNER),
        "--queue-dir", str(queue_dir),
        "--worker-id", str(worker_id),
        "--worker-dir", str(worker_dir),
        "--parent-run-id", parent_run_id,
        "--label", f"worker_{worker_id:02d}",
    ]
    if full_pipeline:
        cmd.append("--full-pipeline")

    log_file = worker_dir / "logs" / "worker.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Append mode so relaunched workers don't clobber debug info from the
    # killed predecessor's log — useful for post-mortem on poison companies.
    stdout_target = None if verbose else open(log_file, "a", encoding="utf-8")
    stderr_target = subprocess.STDOUT

    proc = subprocess.Popen(
        cmd,
        stdout=stdout_target,
        stderr=stderr_target,
        cwd=str(BACKEND_DIR),
        env={**os.environ},
    )
    return proc


def read_worker_progress(worker_dir: Path) -> dict | None:
    f = worker_dir / "progress.json"
    if not f.exists():
        return None
    try:
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def write_master_progress(
    run_dir: Path,
    run_id: str,
    process_count: int,
    total_companies: int,
    total_chunks: int,
    start_time: float,
    worker_dirs: list[Path],
    queue_dir: Path,
):
    """Write master_progress.json atomically (can be polled by external tools)."""
    from scripts import chunk_queue as cq

    counts = cq.queue_state_counts(queue_dir)
    workers = [read_worker_progress(wd) for wd in worker_dirs]
    elapsed = time.monotonic() - start_time

    global_processed = sum(w.get("companies_processed", 0) for w in workers if w)
    global_success = sum(w.get("companies_success", 0) for w in workers if w)
    global_failed = sum(w.get("companies_failed", 0) for w in workers if w)

    state = {
        "run_id": run_id,
        "mode": "dynamic",
        "process_count": process_count,
        "total_companies": total_companies,
        "total_chunks": total_chunks,
        "chunks_pending": counts["pending"],
        "chunks_running": counts["running"],
        "chunks_completed": counts["completed"],
        "chunks_failed": counts["failed"],
        "processed": global_processed,
        "success": global_success,
        "failed": global_failed,
        "elapsed_sec": round(elapsed),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    path = run_dir / "master_progress.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    tmp.replace(path)


def print_dynamic_dashboard(
    run_id: str,
    process_count: int,
    worker_dirs: list[Path],
    procs: list[subprocess.Popen],
    queue_dir: Path,
    start_time: float,
    total_companies: int,
    total_chunks: int,
    prev_lines: int,
    stall_events: list[dict] | None = None,
) -> int:
    """Print live dashboard for dynamic scheduling mode."""
    from scripts import chunk_queue as cq

    if prev_lines > 0:
        clear_lines(prev_lines)

    counts = cq.queue_state_counts(queue_dir)
    workers = [read_worker_progress(wd) for wd in worker_dirs]

    global_processed = sum(w.get("companies_processed", 0) for w in workers if w)
    global_success = sum(w.get("companies_success", 0) for w in workers if w)
    global_failed = sum(w.get("companies_failed", 0) for w in workers if w)
    global_careers = sum(w.get("careers_found", 0) for w in workers if w)
    global_roles = sum(w.get("roles_detected", 0) for w in workers if w)
    global_classified = sum(w.get("roles_classified", 0) for w in workers if w)
    global_jds = sum(w.get("jds_extracted", 0) for w in workers if w)
    global_eligible = sum(w.get("eligible_positioning", 0) for w in workers if w)

    elapsed = time.monotonic() - start_time
    global_pct = global_processed / max(total_companies, 1) * 100
    if global_processed > 0:
        avg = elapsed / global_processed
        global_eta = avg * (total_companies - global_processed)
    else:
        global_eta = 0

    lines = []
    lines.append("")
    lines.append(f"  Run: {run_id}  (dynamic scheduling)")
    lines.append(
        f"  Workers: {process_count}  |  Global: {global_processed}/{total_companies} "
        f"({global_pct:.1f}%)  |  Elapsed: {format_elapsed(elapsed)}  |  "
        f"ETA: {format_eta(int(global_eta))}"
    )
    lines.append(
        f"  Chunks: pending {counts['pending']:>3d}  running {counts['running']:>3d}  "
        f"completed {counts['completed']:>3d}  failed {counts['failed']:>3d}  "
        f"total {total_chunks}"
    )
    lines.append(
        f"  Success: {global_success}  |  Failed: {global_failed}  |  "
        f"Careers: {global_careers}  |  Roles: {global_roles}  |  "
        f"Classified: {global_classified}  |  JDs: {global_jds}  |  "
        f"Eligible: {global_eligible}"
    )
    lines.append(f"  {'-'*120}")
    lines.append(
        f"  {'W#':<4s} {'PID':<8s} {'Chunk':<7s} {'ChunkDone':<12s} "
        f"{'Chunks':>7s} {'Cos':>5s}  {'OK':>5s} {'Fail':>5s}  "
        f"{'Current Company':<28s} {'Stage':<14s}"
    )
    lines.append(f"  {'-'*120}")

    for i, (w, proc) in enumerate(zip(workers, procs)):
        pid = proc.pid if proc else "?"
        alive = proc.poll() is None if proc else False

        if w:
            cur_chunk = w.get("current_chunk_id")
            cur_chunk_s = f"{cur_chunk:04d}" if cur_chunk is not None else "--"
            cp = w.get("current_chunk_processed", 0)
            cs = w.get("current_chunk_size", 0)
            chunks_done = w.get("chunks_completed", 0)
            cos = w.get("companies_processed", 0)
            ok = w.get("companies_success", 0)
            fail = w.get("companies_failed", 0)
            company = (w.get("current_company_name", "") or "")[:27]
            stage = (w.get("current_stage", "") or "")[:13]
            if not alive:
                status_marker = " [EXIT]"
            elif w.get("status") == "completed":
                status_marker = " [DONE]"
            else:
                status_marker = ""
            lines.append(
                f"  {i:<4d} {pid:<8} {cur_chunk_s:<7s} {cp}/{cs:<10} "
                f"{chunks_done:>7d} {cos:>5d}  {ok:>5d} {fail:>5d}  "
                f"{company:<28s} {stage:<14s}{status_marker}"
            )
        else:
            status = "starting..." if alive else "not started"
            lines.append(
                f"  {i:<4d} {pid:<8} {'--':<7s} {'--':<12s} "
                f"{0:>7d} {0:>5d}  {0:>5d} {0:>5d}  "
                f"{status:<28s} {'':<14s}"
            )

    lines.append(f"  {'-'*120}")

    # Watchdog summary (recent kills)
    if stall_events:
        total_kills = len(stall_events)
        poisons_removed = sum(1 for e in stall_events if e.get("poison_removed"))
        recent = stall_events[-3:]
        lines.append(
            f"  Watchdog kills: {total_kills}  "
            f"(poison companies removed: {poisons_removed})  "
            f"showing last {len(recent)}"
        )
        for ev in recent:
            ts = (ev.get("ts") or "")[11:19]  # HH:MM:SS
            dest = ev.get("chunk_destination", "?")
            poison = "+poison removed" if ev.get("poison_removed") else "no skip"
            lines.append(
                f"    [{ts}] W{ev['worker_id']:>2d}  PID {ev['old_pid']}->{ev['new_pid']}  "
                f"chunk {ev['chunk_id']:04d} -> {dest}  idle {ev['idle_sec']}s  "
                f"on '{ev['company'][:30]}' ({poison})"
            )
        lines.append(f"  {'-'*120}")

    lines.append(f"  Press Ctrl+C for graceful shutdown")

    output = "\n".join(lines)
    print(output)
    return len(lines)


def consolidate_dynamic_results(
    run_dir: Path,
    run_id: str,
    process_count: int,
    total_companies: int,
    total_chunks: int,
    worker_dirs: list[Path],
    queue_dir: Path,
    start_time: float,
) -> dict:
    """Consolidate from completed/failed chunks (source of truth) plus
    per-worker summaries (for visibility).

    Why chunks and not worker progress.json: when the watchdog kills and
    relaunches a worker, the new PID starts with fresh counters, so the
    per-worker state reflects only the *last* PID's work. Chunk files in
    completed/ contain every company result that actually landed.
    """
    from scripts import chunk_queue as cq

    elapsed = time.monotonic() - start_time

    # --- Aggregate from completed/ chunks (authoritative) ---
    completed_chunks = cq.list_completed_chunks(queue_dir)
    failed_chunks = cq.list_failed_chunks(queue_dir)

    global_success = 0
    global_failed = 0
    global_careers = 0
    global_roles = 0
    global_classified = 0
    global_jds = 0
    global_eligible = 0
    error_messages = []

    for ch in completed_chunks:
        for r in ch.get("results", []):
            if r.get("status") == "ok":
                global_success += 1
                after = r.get("after") or {}
                ds = after.get("ds", "")
                # Mirror positioning_engine gates — see batch_runner writers.
                classified = r.get("classified", 0)
                top_share = r.get("top_share", 0)
                if ds in ("ready_for_positioning", "specific_pain_identified"):
                    global_eligible += 1
                elif ds == "specific_pain_emerging" and classified >= 3:
                    global_eligible += 1
                elif ds == "broad_hiring_pattern_detected":
                    if classified >= 5 and top_share >= 0.35:
                        global_eligible += 1
                    elif classified >= 15:
                        global_eligible += 1
                global_jds += r.get("jds_extracted", 0)
                if r.get("classified", 0) > 0:
                    global_classified += 1
                if r.get("total_roles", 0) > 0:
                    global_roles += 1
                # "Careers found" proxy: any company that moved above insufficient.
                from scripts.batch_runner import DS_RANKS
                if DS_RANKS.get(ds, 0) >= 1:
                    global_careers += 1
            else:
                global_failed += 1
                msg = r.get("error") or ""
                if msg:
                    error_messages.append({
                        "chunk_id": ch.get("chunk_id"),
                        "company": r.get("name", ""),
                        "message": msg[:200],
                    })

    # Failed chunks (e.g., watchdog max_returned exceeded): count each
    # remaining company as failed so total_companies still reconciles.
    for ch in failed_chunks:
        # If the chunk has results (rare: partial), count those.
        for r in ch.get("results", []):
            if r.get("status") == "ok":
                global_success += 1
            else:
                global_failed += 1
        # Companies that never got a result entry count as failed.
        cos = ch.get("companies", [])
        results_ids = {r.get("company_id") for r in ch.get("results", [])}
        for co in cos:
            if co.get("id") not in results_ids:
                global_failed += 1

    # --- Per-worker snapshot (best-effort, for visibility only) ---
    worker_summaries = []
    for wd in worker_dirs:
        summary_file = wd / "summary.json"
        progress_file = wd / "progress.json"
        data = None
        for f in [summary_file, progress_file]:
            if f.exists():
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    break
                except (json.JSONDecodeError, OSError):
                    continue
        if data:
            worker_summaries.append(data)

    global_processed = global_success + global_failed
    counts = cq.queue_state_counts(queue_dir)
    throughput = global_processed / max(elapsed / 60, 0.001)
    avg_sec = elapsed / max(global_processed, 1)

    master_summary = {
        "run_id": run_id,
        "mode": "dynamic",
        "process_count": process_count,
        "chunk_size_hint": None,  # set by caller
        "total_companies": total_companies,
        "total_chunks": total_chunks,
        "chunks_completed": counts["completed"],
        "chunks_failed": counts["failed"],
        "chunks_pending": counts["pending"],
        "chunks_running": counts["running"],
        "processed": global_processed,
        "success": global_success,
        "failed": global_failed,
        "duration_sec": round(elapsed),
        "avg_sec_per_company": round(avg_sec, 2),
        "throughput_companies_per_min": round(throughput, 2),
        "coverage_funnel": {
            "careers_found": global_careers,
            "roles_detected": global_roles,
            "roles_classified": global_classified,
            "jds_extracted": global_jds,
            "eligible_positioning": global_eligible,
        },
        "top_failure_reasons": error_messages[:20],
        "worker_summaries": worker_summaries,
        "started_at": datetime.fromtimestamp(
            time.time() - elapsed, tz=timezone.utc
        ).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    summary_path = run_dir / "master_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(master_summary, f, indent=2, default=str)

    return master_summary


def print_final_dynamic_summary(summary: dict):
    """Print final consolidated summary for dynamic runs."""
    print(f"\n{'='*80}")
    print(f"  FINAL SUMMARY (dynamic) - {summary['run_id']}")
    print(f"{'='*80}")
    print(f"  Workers:             {summary['process_count']}")
    print(f"  Total companies:     {summary['total_companies']}")
    print(f"  Total chunks:        {summary['total_chunks']}")
    print(f"  Chunks completed:    {summary['chunks_completed']}")
    print(f"  Chunks failed:       {summary['chunks_failed']}")
    print(f"  Chunks pending:      {summary['chunks_pending']}")
    print(f"  Chunks running:      {summary['chunks_running']}")
    print(f"  Processed:           {summary['processed']}")
    print(f"  Success:             {summary['success']}")
    print(f"  Failed:              {summary['failed']}")
    print(f"  Duration:            {format_elapsed(summary['duration_sec'])}")
    print(f"  Avg/company:         {summary['avg_sec_per_company']:.1f}s")
    print(f"  Throughput:          {summary['throughput_companies_per_min']:.1f} companies/min")

    funnel = summary.get("coverage_funnel", {})
    print(f"\n  Coverage Funnel:")
    print(f"    Careers found:        {funnel.get('careers_found', 0)}")
    print(f"    Roles detected:       {funnel.get('roles_detected', 0)}")
    print(f"    Roles classified:     {funnel.get('roles_classified', 0)}")
    print(f"    JDs extracted:        {funnel.get('jds_extracted', 0)}")
    print(f"    Eligible positioning: {funnel.get('eligible_positioning', 0)}")

    print(f"\n  Per-worker breakdown:")
    for ws in summary.get("worker_summaries", []):
        wid = ws.get("worker_id", "?")
        chunks = ws.get("chunks_completed", 0)
        chunks_fail = ws.get("chunks_failed", 0)
        cos = ws.get("companies_processed", 0)
        ok = ws.get("companies_success", 0)
        fail = ws.get("companies_failed", 0)
        el = ws.get("elapsed_sec", 0)
        avg = ws.get("avg_sec_per_company", 0)
        print(
            f"    Worker {wid}: {chunks} chunks ({chunks_fail} fail), "
            f"{cos} companies ({ok} ok, {fail} fail), "
            f"{format_elapsed(el)}, {avg:.1f}s/co"
        )

    print(f"{'='*80}")


def _parse_iso_utc(s: str) -> datetime | None:
    """Parse ISO-8601 UTC timestamp; tolerate 'Z' suffix and trailing fractions."""
    if not s:
        return None
    try:
        # fromisoformat handles +00:00; strip trailing Z just in case.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def check_and_handle_stalls(
    procs: list[subprocess.Popen],
    worker_dirs: list[Path],
    queue_dir: Path,
    parent_run_id: str,
    full_pipeline: bool,
    verbose: bool,
    stall_threshold_sec: int,
    watchdog_grace_sec: int,
    last_kill_at: list[float],
    stall_events: list[dict],
) -> int:
    """Detect stalled workers, terminate them, requeue their chunk, relaunch.

    A worker is stalled if:
      - its Popen is still alive (poll() is None), AND
      - progress.json exists with status=="running" and current_chunk_id is set,
        AND
      - progress.json `updated_at` is older than stall_threshold_sec.

    Workers idle between chunks are not flagged (status=="idle" or no chunk).
    Kills are rate-limited per slot by watchdog_grace_sec — the new worker
    needs a moment to write its own fresh progress.json.

    Mutates:
      - procs: replaces the Popen for each killed slot with a new one
      - last_kill_at: updates the kill timestamp for each affected slot
      - stall_events: appends one dict per kill for dashboard display

    Returns the number of kills performed this tick.
    """
    from scripts import chunk_queue as cq

    kills = 0
    now = datetime.now(timezone.utc)
    now_mono = time.monotonic()

    for i, proc in enumerate(procs):
        # Respect grace period: a freshly-relaunched worker needs time to
        # write its first progress.json, otherwise we'd kill it on sight.
        if now_mono - last_kill_at[i] < watchdog_grace_sec:
            continue

        # Dead workers aren't "stalled" — let the monitor loop handle EXIT.
        if proc.poll() is not None:
            continue

        wp = read_worker_progress(worker_dirs[i])
        if not wp:
            # No progress.json yet. The worker is either starting or has
            # never written. Don't kill — wait another tick.
            continue

        status = wp.get("status")
        cur_chunk = wp.get("current_chunk_id")
        if status != "running" or cur_chunk is None:
            # Worker is between chunks, not stalled.
            continue

        updated_at = _parse_iso_utc(wp.get("updated_at", ""))
        if not updated_at:
            continue

        age = (now - updated_at).total_seconds()
        if age < stall_threshold_sec:
            continue

        # --- Stalled: terminate, requeue chunk, relaunch. ---
        old_pid = proc.pid
        company = (wp.get("current_company_name") or "").strip() or "(unknown)"
        stage = wp.get("current_stage", "?")

        print(
            f"\n  [WATCHDOG] Worker {i} (PID {old_pid}) stalled on chunk "
            f"{cur_chunk:04d} / '{company}' (stage={stage}), idle for "
            f"{int(age)}s > {stall_threshold_sec}s. Terminating."
        )

        try:
            proc.terminate()
        except Exception as e:
            print(f"  [WATCHDOG] terminate() failed on worker {i}: {e}")
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"  [WATCHDOG] Worker {i} didn't exit on SIGTERM; calling kill().")
            try:
                proc.kill()
            except Exception as e:
                print(f"  [WATCHDOG] kill() failed on worker {i}: {e}")
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        except Exception as e:
            print(f"  [WATCHDOG] wait() error on worker {i}: {e}")

        # Requeue the chunk claimed by this worker slot.
        skip_name = company if company and company != "(unknown)" else None
        returned, skipped_info, dest = cq.return_chunk_by_worker(
            queue_dir,
            worker_id=i,
            skip_company_name=skip_name,
            max_returned=3,
        )
        if returned:
            skip_note = ""
            if skipped_info:
                skip_note = (
                    f" (poisoned '{skipped_info['name'][:30]}' removed from chunk)"
                )
            print(
                f"  [WATCHDOG] Chunk {cur_chunk:04d} -> {dest}/{skip_note} "
                f"({returned.name})"
            )
        else:
            # The worker may have finished the chunk rename race just before
            # being killed, or claimed_by_worker metadata got out of sync.
            # Fall back to a generic orphan sweep so nothing rots in running/.
            swept = cq.recover_orphaned_running(queue_dir)
            if swept:
                print(
                    f"  [WATCHDOG] Couldn't match chunk to worker {i}; "
                    f"swept {swept} orphan(s) back to pending/."
                )

        # Clear stale progress.json / summary.json so the grace period doesn't
        # see the old dead file and let the new PID get blamed by mistake.
        for fname in ("progress.json", "summary.json"):
            p = worker_dirs[i] / fname
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        # Relaunch a fresh worker in the same slot.
        try:
            new_proc = launch_dynamic_worker(
                worker_id=i,
                queue_dir=queue_dir,
                worker_dir=worker_dirs[i],
                parent_run_id=parent_run_id,
                full_pipeline=full_pipeline,
                verbose=verbose,
            )
            procs[i] = new_proc
            last_kill_at[i] = now_mono
            kills += 1
            stall_events.append({
                "ts": now.isoformat(),
                "worker_id": i,
                "old_pid": old_pid,
                "new_pid": new_proc.pid,
                "chunk_id": cur_chunk,
                "company": company,
                "stage": stage,
                "idle_sec": int(age),
                "chunk_requeued": returned is not None,
                "chunk_destination": dest,
                "poison_removed": skipped_info is not None,
            })
            print(f"  [WATCHDOG] Relaunched worker {i}: new PID {new_proc.pid}\n")
        except Exception as e:
            print(f"  [WATCHDOG] Failed to relaunch worker {i}: {e}")
            last_kill_at[i] = now_mono  # still mark, so we don't spam retries

    return kills


def write_stall_events(run_dir: Path, stall_events: list[dict]) -> None:
    """Append/persist stall events so they survive run restarts."""
    if not stall_events:
        return
    path = run_dir / "watchdog_events.json"
    try:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"events": stall_events}, f, indent=2, default=str)
        tmp.replace(path)
    except Exception:
        pass


def run_dynamic_mode(args, companies: list[dict], run_dir: Path, run_id: str,
                     full_pipeline: bool):
    """Full flow for --dynamic-scheduling. Returns master_summary dict."""
    from scripts import chunk_queue as cq

    n_proc = args.processes
    chunk_size = args.chunk_size

    # ── Queue directory setup ────────────────────────────────────────
    queue_dir = run_dir / "queue"
    workers_root = run_dir / "workers"
    logs_dir = run_dir / "logs"
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    workers_root.mkdir(parents=True, exist_ok=True)
    cq.init_queue_dir(queue_dir)

    # ── Resume handling ──────────────────────────────────────────────
    if args.resume:
        recovered = cq.recover_orphaned_running(queue_dir)
        if recovered:
            print(f"  Recovered {recovered} orphaned running chunks back to pending")
        counts = cq.queue_state_counts(queue_dir)
        existing_total = sum(counts.values())
        if existing_total > 0:
            print(
                f"  Resuming: queue has {counts['pending']} pending, "
                f"{counts['running']} running, {counts['completed']} completed, "
                f"{counts['failed']} failed (total {existing_total})"
            )
            total_chunks = existing_total
        else:
            print(f"  Resume flag set but no existing queue. Creating chunks...")
            chunks = split_into_chunks(companies, chunk_size)
            for i, ch in enumerate(chunks):
                cq.write_pending_chunk(queue_dir, i, ch)
            total_chunks = len(chunks)
    else:
        chunks = split_into_chunks(companies, chunk_size)
        print(f"\n  Chunking plan:")
        print(f"    Chunk size: {chunk_size}")
        print(f"    Total chunks: {len(chunks)}")
        print(f"    Last chunk size: {len(chunks[-1]) if chunks else 0}")

        if args.dry_run:
            print(f"\n  DRY RUN - would create {len(chunks)} chunks for {n_proc} workers")
            for i, ch in enumerate(chunks[:5]):
                print(f"    Chunk {i:04d}: {len(ch)} companies (first: {ch[0]['name'][:40]})")
            if len(chunks) > 5:
                print(f"    ... and {len(chunks) - 5} more chunks")
            return None

        for i, ch in enumerate(chunks):
            cq.write_pending_chunk(queue_dir, i, ch)
        total_chunks = len(chunks)
        print(f"  Wrote {total_chunks} pending chunks to {queue_dir}")

    if args.dry_run:
        return None

    # ── Worker directories ───────────────────────────────────────────
    worker_dirs = []
    for i in range(n_proc):
        wd = workers_root / f"worker_{i:02d}"
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "logs").mkdir(exist_ok=True)
        worker_dirs.append(wd)

    # ── Master manifest ──────────────────────────────────────────────
    master_manifest = {
        "run_id": run_id,
        "mode": "dynamic",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "process_count": n_proc,
        "chunk_size": chunk_size,
        "total_companies": len(companies),
        "total_chunks": total_chunks,
        "full_pipeline": full_pipeline,
        "input_source": args.input or "database",
        "queue_dir": str(queue_dir),
        "workers_root": str(workers_root),
        "resumed": bool(args.resume),
    }
    with open(run_dir / "master_manifest.json", "w", encoding="utf-8") as f:
        json.dump(master_manifest, f, indent=2, default=str)

    # ── Launch workers ───────────────────────────────────────────────
    print(f"\n  Launching {n_proc} dynamic workers...")
    start_time = time.monotonic()
    procs: list[subprocess.Popen] = []

    for i in range(n_proc):
        proc = launch_dynamic_worker(
            worker_id=i,
            queue_dir=queue_dir,
            worker_dir=worker_dirs[i],
            parent_run_id=run_id,
            full_pipeline=full_pipeline,
            verbose=args.verbose,
        )
        procs.append(proc)
        print(f"    Worker {i}: PID {proc.pid}")

    watchdog_enabled = not args.disable_watchdog
    if watchdog_enabled:
        print(
            f"\n  Watchdog enabled: stall threshold {args.stall_threshold_sec}s, "
            f"grace {args.watchdog_grace_sec}s (running in background thread)"
        )
    else:
        print(f"\n  Watchdog DISABLED (--disable-watchdog)")

    print(f"\n  All workers launched. Monitoring...\n")

    # ── Monitor loop ─────────────────────────────────────────────────
    prev_lines = 0
    stop_requested = False
    # Seed with start_time so every slot gets a grace period during worker
    # boot (imports, DB pool init) before the watchdog can flag it.
    last_kill_at = [start_time] * n_proc
    stall_events: list[dict] = []

    # --- Async watchdog thread: runs terminate+requeue+relaunch without
    # blocking the main dashboard loop. Prior sync design froze the
    # dashboard for 10-30s per kill cycle.
    watchdog_stop_event = threading.Event()

    def _watchdog_loop():
        while not watchdog_stop_event.wait(timeout=5):
            if stop_requested:
                return
            try:
                kills = check_and_handle_stalls(
                    procs=procs,
                    worker_dirs=worker_dirs,
                    queue_dir=queue_dir,
                    parent_run_id=run_id,
                    full_pipeline=full_pipeline,
                    verbose=args.verbose,
                    stall_threshold_sec=args.stall_threshold_sec,
                    watchdog_grace_sec=args.watchdog_grace_sec,
                    last_kill_at=last_kill_at,
                    stall_events=stall_events,
                )
                if kills:
                    write_stall_events(run_dir, stall_events)
            except Exception as e:
                print(f"\n  [WATCHDOG] thread error (non-fatal): {e}")

    watchdog_thread: threading.Thread | None = None
    if watchdog_enabled:
        watchdog_thread = threading.Thread(
            target=_watchdog_loop, name="watchdog", daemon=True,
        )
        watchdog_thread.start()

    prev_lines_kills_seen = 0

    def handle_sigint(signum, frame):
        nonlocal stop_requested
        if stop_requested:
            print("\n\n  Force killing workers...")
            for p in procs:
                try:
                    p.kill()
                except Exception:
                    pass
            sys.exit(1)
        stop_requested = True
        print("\n\n  Graceful shutdown requested. Waiting for workers to finish current chunk...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        while True:
            # If watchdog printed recently, its lines stacked above our dashboard —
            # reset the clear region so we don't wipe the wrong rows.
            if stall_events and len(stall_events) != prev_lines_kills_seen:
                prev_lines = 0
                prev_lines_kills_seen = len(stall_events)

            all_done = all(p.poll() is not None for p in procs)

            prev_lines = print_dynamic_dashboard(
                run_id=run_id,
                process_count=n_proc,
                worker_dirs=worker_dirs,
                procs=procs,
                queue_dir=queue_dir,
                start_time=start_time,
                total_companies=len(companies),
                total_chunks=total_chunks,
                prev_lines=prev_lines,
                stall_events=stall_events,
            )
            write_master_progress(
                run_dir=run_dir,
                run_id=run_id,
                process_count=n_proc,
                total_companies=len(companies),
                total_chunks=total_chunks,
                start_time=start_time,
                worker_dirs=worker_dirs,
                queue_dir=queue_dir,
            )

            if all_done or stop_requested:
                for p in procs:
                    try:
                        p.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        p.kill()
                break

            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\n\n  Terminating workers...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
    finally:
        # Stop the async watchdog thread so it doesn't try to relaunch
        # workers while we're consolidating / shutting down.
        watchdog_stop_event.set()
        if watchdog_thread is not None:
            try:
                watchdog_thread.join(timeout=10)
            except Exception:
                pass

    # ── Consolidate ──────────────────────────────────────────────────
    print(f"\n  Consolidating results...")
    summary = consolidate_dynamic_results(
        run_dir=run_dir,
        run_id=run_id,
        process_count=n_proc,
        total_companies=len(companies),
        total_chunks=total_chunks,
        worker_dirs=worker_dirs,
        queue_dir=queue_dir,
        start_time=start_time,
    )
    summary["chunk_size_hint"] = chunk_size
    summary["watchdog"] = {
        "enabled": watchdog_enabled,
        "stall_threshold_sec": args.stall_threshold_sec,
        "grace_sec": args.watchdog_grace_sec,
        "kills": len(stall_events),
        "events": stall_events,
    }
    with open(run_dir / "master_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print_final_dynamic_summary(summary)

    print(f"\n  Artifacts:")
    print(f"    Master manifest:  {run_dir / 'master_manifest.json'}")
    print(f"    Master progress:  {run_dir / 'master_progress.json'}")
    print(f"    Master summary:   {run_dir / 'master_summary.json'}")
    print(f"    Queue dir:        {queue_dir}")
    print(f"    Workers root:     {workers_root}")
    print()

    return summary


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Parallel Batch Orchestrator - multi-process execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_parallel_batch.py --processes 4 --run-id test_p4
  python scripts/run_parallel_batch.py --processes 6 --run-id test_p6
  python scripts/run_parallel_batch.py --processes 8 --run-id test_p8 --dry-run
  python scripts/run_parallel_batch.py --processes 4 --run-id test_p4 --input data/export.json
        """,
    )
    parser.add_argument("--input", type=str, default=None,
                        help="JSON file with company list (default: load from DB)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--processes", type=int, required=True,
                        help="Number of parallel worker processes")
    parser.add_argument("--run-id", type=str, required=True,
                        help="Unique identifier for this parallel run")
    parser.add_argument("--poll-interval", type=int, default=5,
                        help="Seconds between progress polls (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show shard plan without executing")
    parser.add_argument("--verbose", action="store_true",
                        help="Show worker stdout in console (noisy)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max companies to process")
    parser.add_argument("--no-full-pipeline", action="store_true",
                        help="Skip collection/extraction (evaluation only)")

    # Dynamic scheduling
    parser.add_argument("--dynamic-scheduling", action="store_true",
                        help="Use dynamic chunk-queue scheduling (workers claim chunks from central queue)")
    parser.add_argument("--chunk-size", type=int, default=20,
                        help="Companies per chunk in dynamic mode (default: 20)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume an existing dynamic run (preserves completed chunks)")
    parser.add_argument("--stall-threshold-sec", type=int, default=300,
                        help="Seconds without progress.json updates before a worker is "
                             "declared stalled and terminated (default: 300 = 5 min)")
    parser.add_argument("--watchdog-grace-sec", type=int, default=45,
                        help="Grace period after a watchdog kill before the slot can be "
                             "flagged again (default: 45s)")
    parser.add_argument("--disable-watchdog", action="store_true",
                        help="Disable the master watchdog (not recommended)")

    args = parser.parse_args()

    n_proc = args.processes
    run_id = args.run_id
    output_base = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    run_dir = output_base / run_id
    full_pipeline = not args.no_full_pipeline

    # ── Load companies ───────────────────────────────────────────────
    print(f"\n  Loading companies...", end=" ", flush=True)
    if args.input:
        companies = load_companies_from_file(args.input)
    else:
        companies = load_companies_from_db(limit=args.limit)
    print(f"{len(companies)} companies loaded")

    if not companies:
        print("  No companies found. Exiting.")
        return

    # ── Dynamic scheduling branch ────────────────────────────────────
    if args.dynamic_scheduling:
        run_dynamic_mode(
            args=args,
            companies=companies,
            run_dir=run_dir,
            run_id=run_id,
            full_pipeline=full_pipeline,
        )
        return

    # ── Shard ────────────────────────────────────────────────────────
    shards = split_into_shards(companies, n_proc)

    print(f"\n  Sharding plan ({n_proc} processes):")
    print(f"  {'-'*50}")
    for i, shard in enumerate(shards):
        print(f"    Shard {i}: {len(shard)} companies")
    print(f"  {'-'*50}")
    print(f"  Total: {sum(len(s) for s in shards)} companies")

    # ── Dry run ──────────────────────────────────────────────────────
    if args.dry_run:
        print(f"\n  DRY RUN - would create {n_proc} workers")
        print(f"  Run directory: {run_dir}")
        for i, shard in enumerate(shards):
            print(f"\n  Shard {i} ({len(shard)} companies):")
            for j, c in enumerate(shard[:5]):
                print(f"    {j+1}. {c['name'][:40]:40s} {c['domain']}")
            if len(shard) > 5:
                print(f"    ... and {len(shard) - 5} more")
        return

    # ── Create run directory structure ───────────────────────────────
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    shards_dir = run_dir / "shards"

    shard_dirs = []
    shard_files = []
    for i, shard in enumerate(shards):
        sd = shards_dir / f"shard_{i:02d}"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "logs").mkdir(exist_ok=True)
        shard_dirs.append(sd)

        sf = sd / f"companies.json"
        with open(sf, "w", encoding="utf-8") as f:
            json.dump(shard, f, indent=2, default=str)
        shard_files.append(sf)

    # Write master manifest
    master_manifest = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "process_count": n_proc,
        "total_companies": len(companies),
        "full_pipeline": full_pipeline,
        "input_source": args.input or "database",
        "shards": [
            {
                "index": i,
                "count": len(shard),
                "shard_file": str(shard_files[i]),
                "shard_dir": str(shard_dirs[i]),
            }
            for i, shard in enumerate(shards)
        ],
    }
    with open(run_dir / "master_manifest.json", "w", encoding="utf-8") as f:
        json.dump(master_manifest, f, indent=2, default=str)

    # ── Launch workers ───────────────────────────────────────────────
    print(f"\n  Launching {n_proc} workers...")
    start_time = time.monotonic()
    procs: list[subprocess.Popen] = []

    for i in range(n_proc):
        proc = launch_worker(
            shard_index=i,
            shard_total=n_proc,
            shard_file=shard_files[i],
            shard_dir=shard_dirs[i],
            parent_run_id=run_id,
            full_pipeline=full_pipeline,
            verbose=args.verbose,
        )
        procs.append(proc)
        print(f"    Worker {i}: PID {proc.pid}, {len(shards[i])} companies")

    print(f"\n  All workers launched. Monitoring progress...\n")

    # ── Monitor loop ─────────────────────────────────────────────────
    prev_lines = 0
    stop_requested = False

    def handle_sigint(signum, frame):
        nonlocal stop_requested
        if stop_requested:
            print("\n\n  Force killing workers...")
            for p in procs:
                try:
                    p.kill()
                except Exception:
                    pass
            sys.exit(1)
        stop_requested = True
        print("\n\n  Graceful shutdown requested. Waiting for workers to finish current company...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        while True:
            # Check if all workers done
            all_done = all(p.poll() is not None for p in procs)

            prev_lines = print_dashboard(
                run_id=run_id,
                process_count=n_proc,
                shard_dirs=shard_dirs,
                procs=procs,
                start_time=start_time,
                total_companies=len(companies),
                prev_lines=prev_lines,
            )

            if all_done or stop_requested:
                # Wait for all procs to actually terminate
                for p in procs:
                    try:
                        p.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        p.kill()
                break

            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\n\n  Terminating workers...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()

    # ── Consolidate ──────────────────────────────────────────────────
    print(f"\n  Consolidating results...")
    summary = consolidate_results(
        run_dir=run_dir,
        run_id=run_id,
        process_count=n_proc,
        total_companies=len(companies),
        shard_dirs=shard_dirs,
        start_time=start_time,
    )
    print_final_summary(summary)

    print(f"\n  Artifacts:")
    print(f"    Master manifest:  {run_dir / 'master_manifest.json'}")
    print(f"    Master summary:   {run_dir / 'master_summary.json'}")
    for i, sd in enumerate(shard_dirs):
        print(f"    Shard {i} dir:      {sd}")
    print()


if __name__ == "__main__":
    main()

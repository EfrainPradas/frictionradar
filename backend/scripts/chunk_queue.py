"""
File-based chunk queue for dynamic work distribution.

Each chunk is a JSON file containing a list of companies. Chunks live
in one of four subdirectories of queue_dir:

  pending/    chunks waiting to be claimed
  running/    chunks currently being processed (includes claim metadata)
  completed/  chunks successfully processed (includes per-company results)
  failed/     chunks that failed catastrophically

Claims use os.rename() - atomic on both POSIX and Windows. A worker
that loses a race gets FileNotFoundError and tries the next chunk.
No locks, no inter-process sync needed.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path


CHUNK_NAME_TEMPLATE = "chunk_{chunk_id:04d}.json"
SUBDIRS = ("pending", "running", "completed", "failed")


def init_queue_dir(queue_dir: Path) -> None:
    """Create queue_dir/{pending,running,completed,failed} and sweep .tmp dust."""
    queue_dir = Path(queue_dir)
    for sub in SUBDIRS:
        sub_dir = queue_dir / sub
        sub_dir.mkdir(parents=True, exist_ok=True)
        # Sweep orphaned .tmp files from prior crashes.
        for tmp in sub_dir.glob("*.tmp"):
            try:
                tmp.unlink()
            except Exception:
                pass


def write_pending_chunk(queue_dir: Path, chunk_id: int, companies: list) -> Path:
    """Persist a new chunk in pending/."""
    queue_dir = Path(queue_dir)
    chunk_file = queue_dir / "pending" / CHUNK_NAME_TEMPLATE.format(chunk_id=chunk_id)
    payload = {
        "chunk_id": chunk_id,
        "status": "pending",
        "total": len(companies),
        "companies": companies,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(chunk_file, payload)
    return chunk_file


def claim_next_chunk(queue_dir: Path, worker_id: int, pid: int) -> dict | None:
    """Atomically move a pending chunk to running/. Returns chunk dict or None.

    Uses os.rename() which is atomic on both POSIX and Windows. If two
    workers race for the same chunk, one wins the rename and the loser
    gets FileNotFoundError and tries the next file.
    """
    queue_dir = Path(queue_dir)
    pending_dir = queue_dir / "pending"
    running_dir = queue_dir / "running"

    candidates = list(pending_dir.glob("chunk_*.json"))
    if not candidates:
        return None
    random.shuffle(candidates)

    for src in candidates:
        dst = running_dir / src.name
        try:
            os.rename(str(src), str(dst))
        except (FileNotFoundError, PermissionError, OSError):
            continue

        try:
            with open(dst, "r", encoding="utf-8") as f:
                chunk = json.load(f)
        except (OSError, json.JSONDecodeError):
            # Corrupt chunk after a successful rename: quarantine to failed/
            # so it doesn't clog running/ forever.
            try:
                os.rename(str(dst), str(queue_dir / "failed" / dst.name))
            except Exception:
                pass
            continue

        chunk["status"] = "running"
        chunk["claimed_by_worker"] = worker_id
        chunk["claimed_by_pid"] = pid
        chunk["started_at"] = datetime.now(timezone.utc).isoformat()
        chunk["_running_file"] = str(dst)
        _atomic_write_json(dst, chunk)
        return chunk

    return None


def mark_chunk_completed(
    queue_dir: Path,
    chunk: dict,
    success: int,
    failed: int,
    elapsed_sec: float,
    results: list,
) -> Path | None:
    """Move chunk from running/ to completed/. Defensive: no raise on partial state."""
    chunk["status"] = "completed"
    chunk["finished_at"] = datetime.now(timezone.utc).isoformat()
    chunk["success"] = success
    chunk["failed"] = failed
    chunk["elapsed_sec"] = round(elapsed_sec, 1)
    chunk["results"] = results
    return _move_running_to(queue_dir, chunk, "completed")


def mark_chunk_failed(queue_dir: Path, chunk: dict, error: str) -> Path | None:
    """Move chunk from running/ to failed/. Defensive: no raise on partial state."""
    chunk["status"] = "failed"
    chunk["finished_at"] = datetime.now(timezone.utc).isoformat()
    chunk["error"] = (error or "")[:500]
    return _move_running_to(queue_dir, chunk, "failed")


def _move_running_to(queue_dir: Path, chunk: dict, dest_subdir: str) -> Path | None:
    """Persist updated chunk state to src, then rename into dest_subdir/.

    Defensive rules:
      - Missing _running_file -> return None (nothing to do, not an error).
      - Src already gone -> nothing to rename; return None.
      - Dst already exists -> overwrite (rare: crash-replay or duplicate claim).
      - _running_file is only popped from `chunk` after a successful rename,
        so a caller can fall back to the failed/ path if the completed/ path
        raises partway through.
    """
    running_file = chunk.get("_running_file")
    if not running_file:
        return None
    src = Path(running_file)
    dst = Path(queue_dir) / dest_subdir / src.name

    # Strip _running_file from the serialized payload (internal-only key).
    chunk_to_persist = {k: v for k, v in chunk.items() if k != "_running_file"}

    if src.exists():
        try:
            _atomic_write_json(src, chunk_to_persist)
        except Exception:
            pass  # Proceed with rename even if state couldn't be updated.

    moved = False
    try:
        os.rename(str(src), str(dst))
        moved = True
    except FileExistsError:
        try:
            dst.unlink()
            os.rename(str(src), str(dst))
            moved = True
        except Exception:
            pass
    except FileNotFoundError:
        # Src vanished between exists() and rename. Nothing to do.
        pass
    except OSError:
        pass

    if moved:
        chunk.pop("_running_file", None)
        return dst
    return None


def return_chunk_by_worker(
    queue_dir: Path,
    worker_id: int,
    skip_company_name: str | None = None,
    max_returned: int = 3,
) -> tuple[Path | None, dict | None, str]:
    """Find the chunk in running/ claimed by worker_id and move it back.

    Behavior:
      - If skip_company_name is given and matches a company in the chunk,
        that company is REMOVED from `companies` and recorded in the chunk's
        `watchdog_skipped` list as a pre-cooked failure result. This breaks
        the ping-pong where every new worker hangs on the same poison company.
      - If returned_count would exceed max_returned, the chunk is sent to
        failed/ instead of pending/ as a safety stop.

    Returns (path, skipped_info, destination) where destination is one of
    "pending" | "failed" | "none".
    """
    queue_dir = Path(queue_dir)
    running = queue_dir / "running"
    pending = queue_dir / "pending"
    failed = queue_dir / "failed"

    for f in list(running.glob("chunk_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                chunk = json.load(fh)
        except Exception:
            continue
        if chunk.get("claimed_by_worker") != worker_id:
            continue

        # Remove poison company (if provided and match found).
        skipped_info = None
        if skip_company_name:
            norm_target = skip_company_name.strip().lower()
            remaining = []
            for co in chunk.get("companies", []):
                if (
                    skipped_info is None
                    and (co.get("name", "").strip().lower() == norm_target)
                ):
                    skipped_info = {
                        "company_id": co.get("id"),
                        "name": co.get("name"),
                        "domain": co.get("domain"),
                        "status": "error",
                        "error": "watchdog_skipped: worker stalled on this company",
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                    continue
                remaining.append(co)
            chunk["companies"] = remaining
            chunk["total"] = len(remaining)
            if skipped_info is not None:
                wsl = list(chunk.get("watchdog_skipped", []))
                wsl.append(skipped_info)
                chunk["watchdog_skipped"] = wsl

        # Clean claim metadata.
        chunk.pop("claimed_by_worker", None)
        chunk.pop("claimed_by_pid", None)
        chunk.pop("started_at", None)
        chunk.pop("_running_file", None)
        chunk["returned_to_pending_at"] = datetime.now(timezone.utc).isoformat()
        chunk["returned_count"] = int(chunk.get("returned_count", 0)) + 1

        # Safety: if we've bounced this chunk too many times, give up.
        if chunk["returned_count"] > max_returned:
            chunk["status"] = "failed"
            chunk["finished_at"] = datetime.now(timezone.utc).isoformat()
            chunk["error"] = (
                f"watchdog: exceeded max_returned={max_returned} requeues"
            )
            try:
                _atomic_write_json(f, chunk)
                dst = failed / f.name
                os.rename(str(f), str(dst))
                return dst, skipped_info, "failed"
            except Exception:
                continue

        chunk["status"] = "pending"
        # If we removed the ONLY company, nothing left to process → send to completed/.
        if chunk["total"] == 0:
            chunk["status"] = "completed"
            chunk["finished_at"] = datetime.now(timezone.utc).isoformat()
            chunk["success"] = 0
            chunk["failed"] = len(chunk.get("watchdog_skipped", []))
            chunk["elapsed_sec"] = 0
            chunk["results"] = list(chunk.get("watchdog_skipped", []))
            try:
                _atomic_write_json(f, chunk)
                dst = queue_dir / "completed" / f.name
                os.rename(str(f), str(dst))
                return dst, skipped_info, "completed"
            except Exception:
                continue

        try:
            _atomic_write_json(f, chunk)
            dst = pending / f.name
            os.rename(str(f), str(dst))
            return dst, skipped_info, "pending"
        except Exception:
            continue

    return None, None, "none"


def recover_orphaned_running(queue_dir: Path) -> int:
    """Move any chunks sitting in running/ back to pending/.

    Called at startup to recover work from workers that died mid-chunk.
    """
    queue_dir = Path(queue_dir)
    running = queue_dir / "running"
    pending = queue_dir / "pending"
    recovered = 0
    for f in list(running.glob("chunk_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                chunk = json.load(fh)
            chunk["status"] = "pending"
            chunk.pop("claimed_by_worker", None)
            chunk.pop("claimed_by_pid", None)
            chunk.pop("started_at", None)
            chunk.pop("_running_file", None)
            _atomic_write_json(f, chunk)
            os.rename(str(f), str(pending / f.name))
            recovered += 1
        except Exception:
            continue
    return recovered


def queue_state_counts(queue_dir: Path) -> dict:
    """Return counts of chunks in each state."""
    queue_dir = Path(queue_dir)
    return {
        sub: len(list((queue_dir / sub).glob("chunk_*.json"))) for sub in SUBDIRS
    }


def list_running_chunks(queue_dir: Path) -> list[dict]:
    """Return parsed metadata of chunks currently in running/."""
    return _load_all(Path(queue_dir) / "running")


def list_completed_chunks(queue_dir: Path) -> list[dict]:
    """Return parsed metadata of chunks currently in completed/."""
    return _load_all(Path(queue_dir) / "completed")


def list_failed_chunks(queue_dir: Path) -> list[dict]:
    """Return parsed metadata of chunks currently in failed/."""
    return _load_all(Path(queue_dir) / "failed")


def _load_all(dir_path: Path) -> list[dict]:
    out = []
    for f in dir_path.glob("chunk_*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                out.append(json.load(fh))
        except Exception:
            continue
    return out


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str, indent=2)
    tmp.replace(path)

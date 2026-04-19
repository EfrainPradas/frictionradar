"""Raw source acquisition — download and store external registry files.

This module handles ONLY the download and local storage of raw files.
No parsing, no staging, no company import.

Supports:
  - SFTP download (Florida sunbiz.org)
  - SHA-256 checksumming for integrity and dedup
  - Acquisition tracking in raw_acquisition_log table
  - Skip-if-duplicate by checksum
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, String, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session

from app.db.base import Base


# ════════════════════════════════════════════════════════════════════
# Model
# ════════════════════════════════════════════════════════════════════

class RawAcquisitionLog(Base):
    """Tracks every raw source file downloaded from external registries."""

    __tablename__ = "raw_acquisition_log"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    source_name = Column(String, nullable=False, index=True)
    artifact_name = Column(String, nullable=False)
    artifact_type = Column(String, nullable=False, default="fixed_width")

    downloaded_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    file_size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String, nullable=True, index=True)
    local_path = Column(String, nullable=True)

    status = Column(String, nullable=False, default="completed", index=True)
    error_message = Column(Text, nullable=True)

    batch_id = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# ════════════════════════════════════════════════════════════════════
# Default storage path
# ════════════════════════════════════════════════════════════════════

def get_raw_storage_dir() -> Path:
    """Return the directory where raw acquisition artifacts are stored."""
    base = Path(__file__).resolve().parent.parent.parent.parent  # repo root
    raw_dir = base / "tools" / "data" / "raw" / "florida"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


# ════════════════════════════════════════════════════════════════════
# Checksum
# ════════════════════════════════════════════════════════════════════

def compute_sha256(file_path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file, streaming to handle large files."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ════════════════════════════════════════════════════════════════════
# SFTP Download
# ════════════════════════════════════════════════════════════════════

# Florida DOS public SFTP credentials (documented at dos.fl.gov)
FL_SFTP_HOST = "sftp.floridados.gov"
FL_SFTP_USER = "Public"
FL_SFTP_PASS = "PubAccess1845!"
FL_SFTP_PORT = 22


def list_florida_files(remote_dir: str = "/") -> list[dict]:
    """List files available on the Florida SFTP server.

    Returns list of {name, size, modified} dicts.
    """
    import paramiko

    transport = paramiko.Transport((FL_SFTP_HOST, FL_SFTP_PORT))
    transport.connect(username=FL_SFTP_USER, password=FL_SFTP_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)

    try:
        entries = sftp.listdir_attr(remote_dir)
        files = []
        for entry in entries:
            files.append({
                "name": entry.filename,
                "size": entry.st_size,
                "modified": datetime.fromtimestamp(
                    entry.st_mtime, tz=timezone.utc
                ).isoformat() if entry.st_mtime else None,
            })
        return sorted(files, key=lambda f: f["name"])
    finally:
        sftp.close()
        transport.close()


def download_florida_file(
    remote_path: str,
    *,
    local_dir: str | Path | None = None,
) -> dict:
    """Download a single file from Florida SFTP.

    Args:
        remote_path: full path on the SFTP server (e.g., "/cor_20260414.txt")
        local_dir: where to save locally (defaults to raw storage dir)

    Returns metadata dict: {local_path, artifact_name, file_size_bytes, sha256}
    """
    import paramiko

    if local_dir is None:
        local_dir = get_raw_storage_dir()
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    artifact_name = Path(remote_path).name
    local_path = local_dir / artifact_name

    transport = paramiko.Transport((FL_SFTP_HOST, FL_SFTP_PORT))
    transport.connect(username=FL_SFTP_USER, password=FL_SFTP_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)

    try:
        sftp.get(remote_path, str(local_path))
    finally:
        sftp.close()
        transport.close()

    file_size = local_path.stat().st_size
    checksum = compute_sha256(local_path)

    return {
        "local_path": str(local_path),
        "artifact_name": artifact_name,
        "file_size_bytes": file_size,
        "sha256": checksum,
    }


# ════════════════════════════════════════════════════════════════════
# Acquisition orchestrator
# ════════════════════════════════════════════════════════════════════

def acquire_florida_file(
    db: Session,
    remote_path: str,
    *,
    batch_id: str | None = None,
    skip_if_exists: bool = True,
) -> dict:
    """Download a Florida file and record the acquisition.

    If skip_if_exists is True and a file with the same checksum already
    exists in the log, the download is marked as 'duplicate' and skipped.

    Returns acquisition summary.
    """
    artifact_name = Path(remote_path).name

    if batch_id is None:
        batch_id = f"florida_acq_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Create log entry (downloading)
    log = RawAcquisitionLog(
        source_name="florida_dos",
        artifact_name=artifact_name,
        artifact_type="fixed_width",
        status="downloading",
        batch_id=batch_id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    try:
        meta = download_florida_file(remote_path)

        # Check for duplicate by checksum
        if skip_if_exists:
            existing = (
                db.query(RawAcquisitionLog)
                .filter(
                    RawAcquisitionLog.sha256 == meta["sha256"],
                    RawAcquisitionLog.status == "completed",
                )
                .first()
            )
            if existing:
                log.status = "duplicate"
                log.sha256 = meta["sha256"]
                log.file_size_bytes = meta["file_size_bytes"]
                log.local_path = meta["local_path"]
                log.downloaded_at = datetime.now(timezone.utc)
                db.commit()
                return {
                    "status": "duplicate",
                    "artifact_name": artifact_name,
                    "sha256": meta["sha256"],
                    "existing_id": str(existing.id),
                    "message": f"File already acquired on {existing.downloaded_at}",
                }

        log.status = "completed"
        log.file_size_bytes = meta["file_size_bytes"]
        log.sha256 = meta["sha256"]
        log.local_path = meta["local_path"]
        log.downloaded_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "status": "completed",
            "acquisition_id": str(log.id),
            "artifact_name": artifact_name,
            "local_path": meta["local_path"],
            "file_size_bytes": meta["file_size_bytes"],
            "sha256": meta["sha256"],
            "batch_id": batch_id,
        }

    except Exception as e:
        log.status = "failed"
        log.error_message = str(e)[:500]
        log.downloaded_at = datetime.now(timezone.utc)
        db.commit()
        raise


def register_local_file(
    db: Session,
    local_path: str,
    *,
    source_name: str = "florida_dos",
    batch_id: str | None = None,
    skip_if_exists: bool = True,
) -> dict:
    """Register a locally-available file (already downloaded or manually placed).

    Use this when you already have the file and just want to track it.
    """
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")

    artifact_name = path.name
    file_size = path.stat().st_size
    checksum = compute_sha256(path)

    if batch_id is None:
        batch_id = f"{source_name}_local_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Check for duplicate
    if skip_if_exists:
        existing = (
            db.query(RawAcquisitionLog)
            .filter(
                RawAcquisitionLog.sha256 == checksum,
                RawAcquisitionLog.status == "completed",
            )
            .first()
        )
        if existing:
            return {
                "status": "duplicate",
                "artifact_name": artifact_name,
                "sha256": checksum,
                "existing_id": str(existing.id),
            }

    log = RawAcquisitionLog(
        source_name=source_name,
        artifact_name=artifact_name,
        artifact_type="fixed_width",
        file_size_bytes=file_size,
        sha256=checksum,
        local_path=str(path.resolve()),
        status="completed",
        batch_id=batch_id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "status": "completed",
        "acquisition_id": str(log.id),
        "artifact_name": artifact_name,
        "local_path": str(path.resolve()),
        "file_size_bytes": file_size,
        "sha256": checksum,
        "batch_id": batch_id,
    }


def get_acquisition_history(
    db: Session, *, source_name: str | None = None, limit: int = 20
) -> list[dict]:
    """Get recent acquisition history."""
    q = db.query(RawAcquisitionLog).order_by(RawAcquisitionLog.downloaded_at.desc())
    if source_name:
        q = q.filter(RawAcquisitionLog.source_name == source_name)
    records = q.limit(limit).all()

    return [
        {
            "id": str(r.id),
            "source_name": r.source_name,
            "artifact_name": r.artifact_name,
            "status": r.status,
            "file_size_bytes": r.file_size_bytes,
            "sha256": r.sha256[:16] + "..." if r.sha256 else None,
            "local_path": r.local_path,
            "downloaded_at": r.downloaded_at.isoformat() if r.downloaded_at else None,
        }
        for r in records
    ]

"""CLI entry point for acquiring raw Florida DOS data files.

Usage:
    # List files on Florida SFTP server
    python cli/acquire_florida.py --list

    # Download a specific file
    python cli/acquire_florida.py --download cor_20260414.txt

    # Register a local file (already downloaded manually)
    python cli/acquire_florida.py --register tools/data/florida_sample.txt

    # Show acquisition history
    python cli/acquire_florida.py --history

Run from the repo root directory.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ORIG_CWD = Path.cwd()
_BACKEND = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)

import app.models  # noqa: F401


def main():
    parser = argparse.ArgumentParser(
        description="Acquire raw Florida DOS data files"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List files on Florida SFTP")
    group.add_argument("--download", metavar="FILENAME", help="Download a file from SFTP")
    group.add_argument("--register", metavar="LOCAL_PATH", help="Register a local file")
    group.add_argument("--history", action="store_true", help="Show acquisition history")

    parser.add_argument("--batch-id", help="Optional batch identifier")
    parser.add_argument("--remote-dir", default="/", help="SFTP remote directory (default: /)")
    parser.add_argument("--force", action="store_true", help="Download even if duplicate checksum")

    args = parser.parse_args()

    if args.list:
        _list_files(args.remote_dir)
    elif args.download:
        _download(args)
    elif args.register:
        _register(args)
    elif args.history:
        _show_history()


def _list_files(remote_dir: str):
    from app.master.connectors.acquisition import list_florida_files

    print(f"\nListing files on {remote_dir} ...")
    try:
        files = list_florida_files(remote_dir)
        print()
        print("=" * 65)
        print("  FLORIDA SFTP FILES")
        print("=" * 65)
        if not files:
            print("  (no files found)")
        for f in files:
            size_mb = f["size"] / (1024 * 1024) if f["size"] else 0
            print(f"  {f['name']:40s}  {size_mb:8.1f} MB  {f['modified'] or ''}")
        print("=" * 65)
    except Exception as e:
        print(f"\nERROR connecting to SFTP: {e}")
        sys.exit(1)


def _download(args):
    from app.db.session import SessionLocal
    from app.master.connectors.acquisition import acquire_florida_file

    remote_path = args.download
    if not remote_path.startswith("/"):
        remote_path = f"/{remote_path}"

    db = SessionLocal()
    try:
        print(f"\nDownloading: {remote_path}")
        result = acquire_florida_file(
            db, remote_path,
            batch_id=args.batch_id,
            skip_if_exists=not args.force,
        )
        _print_result(result)
    except Exception as e:
        print(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def _register(args):
    from app.db.session import SessionLocal
    from app.master.connectors.acquisition import register_local_file

    local_path = str((_ORIG_CWD / args.register).resolve())
    if not Path(local_path).exists():
        print(f"ERROR: File not found: {local_path}")
        sys.exit(1)

    db = SessionLocal()
    try:
        print(f"\nRegistering: {local_path}")
        result = register_local_file(
            db, local_path,
            batch_id=args.batch_id,
            skip_if_exists=not args.force,
        )
        _print_result(result)
    except Exception as e:
        print(f"\nFATAL: {e}")
        sys.exit(1)
    finally:
        db.close()


def _show_history():
    from app.db.session import SessionLocal
    from app.master.connectors.acquisition import get_acquisition_history

    db = SessionLocal()
    try:
        history = get_acquisition_history(db, source_name="florida_dos")
        print()
        print("=" * 75)
        print("  ACQUISITION HISTORY")
        print("=" * 75)
        if not history:
            print("  No acquisitions recorded yet.")
        for h in history:
            size_mb = h["file_size_bytes"] / (1024 * 1024) if h["file_size_bytes"] else 0
            print(f"  [{h['status']:10s}] {h['artifact_name']:30s} {size_mb:6.1f} MB  sha={h['sha256'] or 'n/a'}")
            print(f"              {h['downloaded_at'] or 'n/a'}  {h['local_path'] or ''}")
        print("=" * 75)
    finally:
        db.close()


def _print_result(result: dict):
    print()
    print("=" * 55)
    if result["status"] == "duplicate":
        print("  ACQUISITION: DUPLICATE (skipped)")
        print("=" * 55)
        print(f"  Artifact:   {result['artifact_name']}")
        print(f"  SHA-256:    {result['sha256']}")
        print(f"  Message:    {result.get('message', 'Already acquired')}")
    elif result["status"] == "completed":
        print("  ACQUISITION: COMPLETED")
        print("=" * 55)
        print(f"  Artifact:   {result['artifact_name']}")
        print(f"  Local path: {result['local_path']}")
        size_mb = result["file_size_bytes"] / (1024 * 1024) if result.get("file_size_bytes") else 0
        print(f"  Size:       {size_mb:.2f} MB ({result.get('file_size_bytes', 0):,} bytes)")
        print(f"  SHA-256:    {result['sha256']}")
        print(f"  Batch ID:   {result.get('batch_id', 'n/a')}")
    else:
        print(f"  ACQUISITION: {result['status'].upper()}")
        print("=" * 55)
        for k, v in result.items():
            print(f"  {k}: {v}")
    print("=" * 55)


if __name__ == "__main__":
    main()

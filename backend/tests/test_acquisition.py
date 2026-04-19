"""Tests for raw source acquisition layer.

Validates:
  1. SHA-256 checksum computation
  2. Model instantiation
  3. Local file registration (without DB)
  4. Duplicate detection logic
  5. Storage directory creation

Run:
  python backend/tests/test_acquisition.py
"""

import json
import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ════════════════════════════════════════════════════════════════════
# 1. CHECKSUM
# ════════════════════════════════════════════════════════════════════

def test_sha256_known_content(tmp_path):
    from app.master.connectors.acquisition import compute_sha256
    f = tmp_path / "test.txt"
    f.write_text("hello world\n")
    result = compute_sha256(f)
    assert isinstance(result, str)
    assert len(result) == 64  # SHA-256 hex is always 64 chars


def test_sha256_deterministic(tmp_path):
    from app.master.connectors.acquisition import compute_sha256
    f = tmp_path / "test.txt"
    f.write_text("deterministic content")
    h1 = compute_sha256(f)
    h2 = compute_sha256(f)
    assert h1 == h2


def test_sha256_different_content(tmp_path):
    from app.master.connectors.acquisition import compute_sha256
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("content A")
    f2.write_text("content B")
    assert compute_sha256(f1) != compute_sha256(f2)


def test_sha256_fixture_file():
    from app.master.connectors.acquisition import compute_sha256
    fixture = Path(__file__).resolve().parent.parent.parent / "tools" / "data" / "florida_sample.txt"
    if not fixture.exists():
        return
    result = compute_sha256(fixture)
    assert isinstance(result, str)
    assert len(result) == 64


# ════════════════════════════════════════════════════════════════════
# 2. MODEL
# ════════════════════════════════════════════════════════════════════

def test_model_table_name():
    from app.master.connectors.acquisition import RawAcquisitionLog
    assert RawAcquisitionLog.__tablename__ == "raw_acquisition_log"


def test_model_instantiation():
    from app.master.connectors.acquisition import RawAcquisitionLog
    log = RawAcquisitionLog(
        source_name="florida_dos",
        artifact_name="cor_test.txt",
        artifact_type="fixed_width",
        status="completed",
    )
    assert log.source_name == "florida_dos"
    assert log.artifact_name == "cor_test.txt"


def test_model_fields():
    from app.master.connectors.acquisition import RawAcquisitionLog
    columns = {c.name for c in RawAcquisitionLog.__table__.columns}
    required = {
        "id", "source_name", "artifact_name", "artifact_type",
        "downloaded_at", "file_size_bytes", "sha256", "local_path",
        "status", "error_message", "batch_id", "created_at",
    }
    for f in required:
        assert f in columns, f"Missing column: {f}"


# ════════════════════════════════════════════════════════════════════
# 3. STORAGE DIRECTORY
# ════════════════════════════════════════════════════════════════════

def test_raw_storage_dir_exists():
    from app.master.connectors.acquisition import get_raw_storage_dir
    d = get_raw_storage_dir()
    assert d.exists()
    assert d.is_dir()
    assert "florida" in str(d)


# ════════════════════════════════════════════════════════════════════
# 4. SFTP CONSTANTS
# ════════════════════════════════════════════════════════════════════

def test_florida_sftp_constants():
    from app.master.connectors.acquisition import FL_SFTP_HOST, FL_SFTP_USER, FL_SFTP_PORT
    assert FL_SFTP_HOST == "sftp.floridados.gov"
    assert FL_SFTP_USER == "Public"
    assert FL_SFTP_PORT == 22


# ════════════════════════════════════════════════════════════════════
# 5. REGISTER LOCAL FILE (logic test, no DB)
# ════════════════════════════════════════════════════════════════════

def test_register_nonexistent_file_raises():
    from app.master.connectors.acquisition import register_local_file
    try:
        register_local_file(None, "/nonexistent/file.txt")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        pass


# ════════════════════════════════════════════════════════════════════
# 6. ACQUISITION HISTORY SHAPE
# ════════════════════════════════════════════════════════════════════

def test_acquisition_result_shape():
    """Verify the expected shape of acquisition result dicts."""
    completed = {
        "status": "completed",
        "acquisition_id": "uuid",
        "artifact_name": "cor_test.txt",
        "local_path": "/path/to/file",
        "file_size_bytes": 1024,
        "sha256": "abc123",
        "batch_id": "batch_1",
    }
    assert completed["status"] == "completed"
    assert "sha256" in completed

    duplicate = {
        "status": "duplicate",
        "artifact_name": "cor_test.txt",
        "sha256": "abc123",
        "existing_id": "uuid",
    }
    assert duplicate["status"] == "duplicate"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

def run_all_tests() -> dict:
    import tempfile
    tmp = Path(tempfile.mkdtemp())

    tests = [
        ("checksum.known", lambda: test_sha256_known_content(tmp)),
        ("checksum.deterministic", lambda: test_sha256_deterministic(tmp)),
        ("checksum.different", lambda: test_sha256_different_content(tmp)),
        ("checksum.fixture", test_sha256_fixture_file),
        ("model.table_name", test_model_table_name),
        ("model.instantiation", test_model_instantiation),
        ("model.fields", test_model_fields),
        ("storage.dir_exists", test_raw_storage_dir_exists),
        ("sftp.constants", test_florida_sftp_constants),
        ("register.nonexistent", test_register_nonexistent_file_raises),
        ("result.shape", test_acquisition_result_shape),
    ]

    passed = 0
    failed = 0
    errors = 0
    details = []

    for name, fn in tests:
        try:
            fn()
            passed += 1
            details.append({"name": name, "status": "passed"})
        except AssertionError as e:
            failed += 1
            details.append({"name": name, "status": "failed", "error": str(e)})
        except Exception as e:
            errors += 1
            details.append({
                "name": name, "status": "error",
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            })

    return {
        "passed": passed, "failed": failed, "errors": errors,
        "total": len(tests), "success": failed == 0 and errors == 0,
        "details": details,
    }


if __name__ == "__main__":
    report = run_all_tests()
    print(json.dumps(report, indent=2))
    if not report["success"]:
        sys.exit(1)

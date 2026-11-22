"""Startup guidance reads indexed metadata without touching any original photos."""

import pytest
from fastapi.testclient import TestClient

from backend.app import duplicates
from backend.app.main import create_app
from backend.app.scanner import scan_root
from backend.app.settings import save_root_exclusions
from tests.test_m19_dynamic_folders import _setup


@pytest.fixture
def indexed(tmp_path, monkeypatch):
    monkeypatch.setattr(duplicates, "job_status", lambda _: {"state": "idle"})
    conn, root_id, root = _setup(tmp_path)
    scan_root(conn, root_id)
    yield conn, root_id, root
    conn.close()


def test_missing_complete_and_cloud_metadata(indexed):
    conn, root_id, _ = indexed
    assert duplicates.index_readiness(conn, root_id) == {
        "root_id": root_id,
        "total": 2,
        "pending": 2,
        "cloud_placeholder": 0,
        "duplicate_scan_state": "idle",
    }
    duplicates.index_photos(conn, root_id)
    assert duplicates.index_readiness(conn, root_id)["pending"] == 0
    with conn:
        conn.execute("UPDATE photo SET cloud_placeholder=1 WHERE id=(SELECT MIN(id) FROM photo)")
    result = duplicates.index_readiness(conn, root_id)
    assert result["total"] == 2 and result["pending"] == 0
    assert result["cloud_placeholder"] == 1


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE photo_fingerprint SET algorithm='old'",
        "UPDATE photo_fingerprint SET mtime_ns=0",
        "UPDATE photo_fingerprint SET size_bytes=0",
        "DELETE FROM photo_fingerprint",
    ],
)
def test_stale_fingerprints_need_guidance(indexed, change):
    conn, root_id, _ = indexed
    duplicates.index_photos(conn, root_id)
    with conn:
        conn.execute(change)
    assert duplicates.index_readiness(conn, root_id)["pending"] == 2


def test_exclusions_root_isolation_and_empty_library(indexed):
    conn, root_id, _ = indexed
    save_root_exclusions(conn, root_id, ["備份資料"])
    with conn:
        other = conn.execute(
            "INSERT INTO root(label,path) VALUES ('other','/synthetic-offline')"
        ).lastrowid
    assert duplicates.index_readiness(conn, root_id)["pending"] == 1
    assert duplicates.index_readiness(conn, other)["total"] == 0
    assert duplicates.index_readiness(conn, other)["pending"] == 0
    with pytest.raises(duplicates.DuplicateError):
        duplicates.index_readiness(conn, 999999)


def test_readiness_never_reads_disk_hashes_or_writes(indexed, monkeypatch):
    conn, root_id, _ = indexed

    def forbidden(*args, **kwargs):
        pytest.fail("Readiness must be SQLite-only")

    for name in ("_root", "_safe_stat", "_hash_checked", "_photos", "start_scan"):
        monkeypatch.setattr(duplicates, name, forbidden)
    monkeypatch.setattr(duplicates, "job_status", lambda _: {"state": "running"})
    before = conn.total_changes
    queries = []
    conn.set_trace_callback(queries.append)
    result = duplicates.index_readiness(conn, root_id)
    assert result["pending"] == 2 and result["duplicate_scan_state"] == "running"
    assert conn.total_changes == before
    assert all(q.lstrip().upper().startswith("SELECT") for q in queries)


def test_readiness_api_and_unknown_root(indexed, tmp_path, monkeypatch):
    _, root_id, _ = indexed
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        response = client.get(f"/api/duplicates/{root_id}/readiness")
        assert response.status_code == 200
        assert response.json()["pending"] == 2
        assert client.get("/api/duplicates/999999/readiness").status_code == 404

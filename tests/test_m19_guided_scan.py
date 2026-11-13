"""M19-F: uploads guide the user to a manual scan when fingerprints are incomplete.

Synthetic photo roots only. No user/Google Drive originals are modified.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.scanner import scan_root
from tests.test_m19_cross_duplicates import _with_cross_equipment
from tests.test_m19_dynamic_folders import _jpeg_bytes


def test_api_index_required_guides_to_manual_scan_then_upload(tmp_path, monkeypatch):
    conn, root_id, root, _, another = _with_cross_equipment(tmp_path)
    try:
        for index in range(12):
            folder = root / "水帶" / "倉庫" / f"暫-{index:02d}"
            folder.mkdir()
            (folder / "前.jpg").write_bytes(_jpeg_bytes(f"#{index:02x}b379"))
        scan_root(conn, root_id)
        dest_id = int(conn.execute("SELECT id FROM item WHERE code='F-19-13'").fetchone()[0])
    finally:
        conn.close()

    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        endpoint = f"/api/items/{dest_id}/slots/中/photos"
        data = {"file": ("paste.jpg", _jpeg_bytes("purple"), "image/jpeg")}
        blocked = client.post(endpoint, files=data)
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "duplicate_index_required"
        assert "掃描" in blocked.json()["detail"]["message"]
        assert not (another / "中.jpg").exists()

        idle = client.get(f"/api/duplicates/{root_id}/scan")
        assert idle.status_code == 200
        assert idle.json()["state"] != "running", "upload must not auto-scan"

        started = client.post(f"/api/duplicates/{root_id}/scan", json={"full": False})
        assert started.status_code == 202
        completed = None
        for _ in range(180):
            completed = client.get(f"/api/duplicates/{root_id}/scan").json()
            if completed["state"] != "running":
                break
            time.sleep(0.02)
        assert completed is not None and completed["state"] == "completed", completed

        retry = client.post(endpoint, files=data)
        assert retry.status_code == 200, retry.text
        assert retry.json()["offline_queued"] is False
        assert (another / "中.jpg").is_file()

        duplicate = client.post(f"/api/items/{dest_id}/slots/後/photos", files=data)
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "duplicate_photo"
        assert duplicate.json()["detail"]["matches"]


def test_index_required_does_not_mislabel_an_existing_duplicate(tmp_path, monkeypatch):
    """When all fingerprints exist, the old cross-equipment prompt stays intact."""
    from backend.app.duplicates import index_photos

    conn, root_id, _, _, _ = _with_cross_equipment(tmp_path)
    try:
        index_photos(conn, root_id)
        dest_id = int(conn.execute("SELECT id FROM item WHERE code='F-19-13'").fetchone()[0])
    finally:
        conn.close()

    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        response = client.post(
            f"/api/items/{dest_id}/slots/中/photos",
            files={"file": ("red.jpg", _jpeg_bytes("red"), "image/jpeg")},
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "duplicate_photo"
        assert detail["matches"]

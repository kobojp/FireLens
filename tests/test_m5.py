from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from backend.app.cache import (
    content_file,
    list_offline_queue,
    queue_offline_import,
    root_status,
    sync_offline_queue,
    thumbnail_file,
)
from backend.app.db import SCHEMA_VERSION, connect
from backend.app.scanner import FILE_ATTRIBUTE_OFFLINE, _is_cloud_placeholder_stat, scan_root


def jpeg_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (80, 60), "white").save(stream, format="JPEG")
    return stream.getvalue()


def make_valid_root(tmp_path: Path) -> Path:
    root = tmp_path / "photos"
    item = root / "滅火器" / "2026年" / "10月份更換" / "中正樓" / "中-01-01"
    item.mkdir(parents=True)
    (item / "編號.jpg").write_bytes(jpeg_bytes())
    return root


def add_root(conn, root: Path, *, cloud: bool = True) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO root(label, path, is_cloud_stream) VALUES ('測試', ?, ?)",
            (str(root), int(cloud)),
        )
    return int(cursor.lastrowid)


def test_schema_v5_and_placeholder_flag(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 5
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "offline_import_queue" in tables
        assert _is_cloud_placeholder_stat(
            SimpleNamespace(st_file_attributes=FILE_ATTRIBUTE_OFFLINE)
        )
        assert not _is_cloud_placeholder_stat(SimpleNamespace(st_file_attributes=0))
    finally:
        conn.close()


def test_thumbnail_survives_root_disconnect(db_path: Path, tmp_path: Path) -> None:
    root = make_valid_root(tmp_path)
    conn = connect(db_path)
    try:
        root_id = add_root(conn, root)
        scan_root(conn, root_id)
        photo_id = int(conn.execute("SELECT id FROM photo LIMIT 1").fetchone()[0])
        cached = thumbnail_file(conn, photo_id)
        assert cached.is_file()
        connected = root_status(conn, root_id)
        assert connected["connected"] is True
        assert connected["cached_thumbnails"] == 1

        offline = root.with_name("photos-offline")
        root.rename(offline)
        status = root_status(conn, root_id)
        assert status["connected"] is False
        assert status["cached_items"] == 1
        assert status["cached_photos"] == 1
        fallback, is_cached = content_file(conn, photo_id)
        assert is_cached is True
        assert fallback == cached
    finally:
        conn.close()


def test_offline_import_queue_syncs_after_reconnect(db_path: Path, tmp_path: Path) -> None:
    root = make_valid_root(tmp_path)
    conn = connect(db_path)
    try:
        root_id = add_root(conn, root)
        scan_root(conn, root_id)
        item_id = int(conn.execute("SELECT id FROM item LIMIT 1").fetchone()[0])
        offline = root.with_name("photos-offline")
        root.rename(offline)

        queued = queue_offline_import(
            conn,
            item_id=item_id,
            slot="藥劑",
            source_name="camera.jpg",
            data=jpeg_bytes(),
        )
        assert queued["state"] == "pending"
        assert root_status(conn, root_id)["pending_imports"] == 1
        assert len(list_offline_queue(conn, root_id)) == 1

        offline.rename(root)
        result = sync_offline_queue(conn, root_id)
        assert result["failed"] == []
        assert result["synced"] == [queued["id"]]
        assert (
            root / "滅火器" / "2026年" / "10月份更換" / "中正樓" / "中-01-01" / "藥劑.jpg"
        ).is_file()
        row = conn.execute(
            "SELECT state, synced_at FROM offline_import_queue WHERE id=?", (queued["id"],)
        ).fetchone()
        assert row["state"] == "synced"
        assert row["synced_at"]
        assert root_status(conn, root_id)["pending_imports"] == 0
    finally:
        conn.close()


def test_failed_sync_keeps_payload_and_queue(db_path: Path, tmp_path: Path) -> None:
    root = make_valid_root(tmp_path)
    conn = connect(db_path)
    try:
        root_id = add_root(conn, root)
        scan_root(conn, root_id)
        item_id = int(conn.execute("SELECT id FROM item LIMIT 1").fetchone()[0])
        offline = root.with_name("photos-offline")
        root.rename(offline)
        queued = queue_offline_import(
            conn,
            item_id=item_id,
            slot="編號",
            source_name="conflict.jpg",
            data=jpeg_bytes(),
        )
        offline.rename(root)
        import shutil

        shutil.rmtree(root / "滅火器" / "2026年" / "10月份更換" / "中正樓" / "中-01-01")
        result = sync_offline_queue(conn, root_id)
        assert result["synced"] == []
        assert result["failed"]
        row = conn.execute(
            "SELECT state, payload_name, last_error FROM offline_import_queue WHERE id=?",
            (queued["id"],),
        ).fetchone()
        assert row["state"] == "error"
        assert row["last_error"]
        from backend.app.config import get_offline_dir

        assert (get_offline_dir() / row["payload_name"]).is_file()
    finally:
        conn.close()


def test_upload_api_queues_when_root_is_offline(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    root = make_valid_root(tmp_path)
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/roots",
            json={"path": str(root), "label": "離線 API", "is_cloud_stream": True},
        )
        assert created.status_code == 201
        root_id = int(created.json()["id"])
        assert client.post(f"/api/roots/{root_id}/scan").status_code == 200
        tree = client.get(f"/api/roots/{root_id}/tree").json()
        item_id = int(tree[0]["children"][0]["children"][0]["children"][0]["children"][0]["id"])
        root.rename(root.with_name("photos-offline"))
        uploaded = client.post(
            f"/api/items/{item_id}/slots/藥劑/photos",
            files={"file": ("offline.jpg", jpeg_bytes(), "image/jpeg")},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["offline_queued"] is True
        queue = client.get(f"/api/roots/{root_id}/offline-queue")
        assert queue.status_code == 200
        assert len(queue.json()) == 1
        assert queue.json()[0]["state"] == "pending"

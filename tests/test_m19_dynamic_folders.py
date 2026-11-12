"""M19: synthetic root folder discovery, exclusions and duplicate photo confirmation."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.db import connect, initialize_database
from backend.app.main import create_app
from backend.app.scanner import scan_root
from backend.app.settings import SettingsError, get_settings, save_settings
from backend.app.storage import DuplicatePhotoConflict, import_photo
from backend.app.tree import build_tree


def _jpeg_bytes(color: str = "red") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(output, format="JPEG", quality=95)
    return output.getvalue()


def _setup(tmp_path):
    root = tmp_path / "pictures"
    root.mkdir(parents=True)
    (root / "水帶" / "倉庫" / "水-01").mkdir(parents=True)
    (root / "水帶" / "倉庫" / "水-01" / "前.jpg").write_bytes(_jpeg_bytes())
    (root / "備份資料" / "臨時" / "備-01").mkdir(parents=True)
    (root / "備份資料" / "臨時" / "備-01" / "照片.jpg").write_bytes(_jpeg_bytes("blue"))
    (root / "FireLens-共享異常資料" / "events").mkdir(parents=True)
    (root / "FireLens-共享異常資料" / "events" / "event.jpg").write_bytes(_jpeg_bytes())
    db_path = tmp_path / "data" / "firelens.sqlite3"
    initialize_database(db_path)
    conn = connect(db_path)
    with conn:
        root_id = conn.execute(
            "INSERT INTO root(label,path) VALUES (?,?)", ("synthetic", str(root))
        ).lastrowid
    return conn, root_id, root


def test_dynamic_categories_exclusion_and_rescan(tmp_path):
    conn, root_id, root = _setup(tmp_path)
    try:
        initial = scan_root(conn, root_id)
        assert initial.items == 2
        tree = build_tree(conn, root_id)
        labels = {node["label"] for node in tree}
        assert "水帶" in labels and "備份資料" in labels
        assert "FireLens-共享異常資料" not in labels

        row = conn.execute(
            """SELECT i.id, i.year, i.period, i.building, i.status, c.slots_json
               FROM item i JOIN category c ON c.id=i.category_id
               WHERE i.code=?""",
            ("水-01",),
        ).fetchone()
        assert row is not None and row["slots_json"] == '["前", "中", "後"]'
        assert row["year"] == "(未分類)"
        assert row["period"] == "(未分類)"
        assert row["building"] == "倉庫"
        assert row["status"] == "partial"
        from backend.app.photo_quality import gallery

        code = conn.execute("SELECT code FROM category WHERE name='水帶'").fetchone()[0]
        quality = gallery(conn, root_id, category=code, problem_only=False)
        assert quality["total"] == 1
        assert quality["items"][0]["slots"] == ["前", "中", "後"]

        settings = save_settings(conn, {"excluded_root_folders": ["備份資料"]})
        assert settings["excluded_root_folders"] == ["備份資料"]
        result = scan_root(conn, root_id)
        assert result.items == 1
        labels = {node["label"] for node in build_tree(conn, root_id)}
        assert labels == {"水帶"}
        assert (root / "備份資料" / "臨時" / "備-01" / "照片.jpg").exists()

        with pytest.raises(SettingsError):
            save_settings(conn, {"excluded_root_folders": ["../outside"]})
        with pytest.raises(SettingsError):
            save_settings(conn, {"excluded_root_folders": ["水帶/倉庫"]})
        assert get_settings(conn)["excluded_root_folders"] == ["備份資料"]
    finally:
        conn.close()


def test_exclusion_setting_api_and_new_category_create(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "isolated"))
    with TestClient(create_app()) as client:
        saved = client.put("/api/settings", json={"excluded_root_folders": ["備份資料"]})
        assert saved.status_code == 200
        assert client.get("/api/settings").json()["excluded_root_folders"] == ["備份資料"]
        bad = client.put("/api/settings", json={"excluded_root_folders": ["../outside"]})
        assert bad.status_code == 400

    conn, root_id, root = _setup(tmp_path / "creation")
    try:
        scan_root(conn, root_id)
        code = conn.execute("SELECT code FROM category WHERE name='水帶'").fetchone()[0]
        from backend.app.storage import create_year_folder

        create_year_folder(conn, root_id, code, "2027年")
        assert (root / "水帶" / "2027年").is_dir()
    finally:
        conn.close()


def test_duplicate_image_requires_explicit_confirmation(tmp_path):
    conn, root_id, root = _setup(tmp_path)
    try:
        scan_root(conn, root_id)
        item_id = conn.execute("SELECT id FROM item WHERE code='水-01'").fetchone()[0]
        image = _jpeg_bytes()
        folder = root / "水帶" / "倉庫" / "水-01"
        before = {path.name for path in folder.iterdir()}
        with pytest.raises(DuplicatePhotoConflict, match="前.jpg"):
            import_photo(conn, item_id, "前", "repeat.jpg", image)
        assert {path.name for path in folder.iterdir()} == before

        created = import_photo(conn, item_id, "前", "repeat.jpg", image, allow_duplicate=True)
        assert created["filename"] == "前-1.jpg"
        assert (folder / "前-1.jpg").read_bytes() == image

        unique = import_photo(conn, item_id, "前", "another.jpg", _jpeg_bytes("green"))
        assert unique["filename"] == "前-2.jpg"
    finally:
        conn.close()

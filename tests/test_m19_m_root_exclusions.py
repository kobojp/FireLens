"""M19-M synthetic, isolated per-root exclusions and safe legacy migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.db import connect, initialize_database
from backend.app.main import create_app
from backend.app.settings import (
    SettingsError,
    excluded_root_folders,
    save_root_exclusions,
    saved_root_exclusions,
)


def _root(conn, path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    with conn:
        return int(
            conn.execute(
                "INSERT INTO root(label,path) VALUES (?,?)", (path.name, str(path))
            ).lastrowid
        )


def test_migration_preserves_old_global_for_existing_roots_only(tmp_path: Path):
    db = tmp_path / "data" / "firelens.sqlite3"
    initialize_database(db)
    conn = connect(db)
    try:
        a = _root(conn, tmp_path / "A")
        b = _root(conn, tmp_path / "B")
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO setting(key,value_json) VALUES (?,?)",
                ("excluded_root_folders", json.dumps(["暫存照片"], ensure_ascii=False)),
            )
            conn.execute("DELETE FROM setting WHERE key='excluded_root_folders_by_root'")
            conn.execute("PRAGMA user_version = 13")
    finally:
        conn.close()
    initialize_database(db)
    assert db.with_suffix(".sqlite3.backup-v13").exists()
    conn = connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 14
        assert saved_root_exclusions(conn, a) == ["暫存照片"]
        assert saved_root_exclusions(conn, b) == ["暫存照片"]
        c = _root(conn, tmp_path / "C")
        assert saved_root_exclusions(conn, c) == []
        save_root_exclusions(conn, a, ["只排除A"])
        assert saved_root_exclusions(conn, a) == ["只排除A"]
        assert saved_root_exclusions(conn, b) == ["暫存照片"]
        assert "只排除a" in excluded_root_folders(conn, a)
        assert "只排除a" not in excluded_root_folders(conn, b)
        assert "firelens-共享異常資料" in excluded_root_folders(conn, c)
    finally:
        conn.close()


def test_two_roots_same_folder_and_api_readonly_listing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    db = initialize_database()
    conn = connect(db)
    try:
        a_dir, b_dir = tmp_path / "A", tmp_path / "B"
        a = _root(conn, a_dir)
        b = _root(conn, b_dir)
        for folder in (a_dir, b_dir):
            (folder / "暫存照片").mkdir()
            (folder / "燈具").mkdir()
            (folder / "FireLens-共享異常資料").mkdir()
        save_root_exclusions(conn, a, ["暫存照片"])
        assert "暫存照片".casefold() in excluded_root_folders(conn, a)
        assert "暫存照片".casefold() not in excluded_root_folders(conn, b)
    finally:
        conn.close()

    with TestClient(create_app()) as client:
        result = client.get(f"/api/roots/{a}/excluded-folders")
        assert result.status_code == 200
        response = result.json()
        assert response["saved"] == ["暫存照片"]
        assert response["folders"]
        folders = {v["name"]: v for v in response["folders"]}
        assert folders["暫存照片"]["excluded"]
        assert folders["FireLens-共享異常資料"]["locked"]
        assert not folders["燈具"]["excluded"]
        assert client.get(f"/api/roots/{b}/excluded-folders").json()["saved"] == []
        selected = client.put(f"/api/roots/{b}/excluded-folders", json={"names": ["燈具"]})
        assert selected.status_code == 200
        assert selected.json()["rescan_required"]
        assert client.get(f"/api/roots/{a}/excluded-folders").json()["saved"] == ["暫存照片"]
        for bad in (["../private"], ["FireLens-共享異常資料"]):
            refused = client.put(f"/api/roots/{b}/excluded-folders", json={"names": bad})
            assert refused.status_code == 400
        assert client.put("/api/roots/999/excluded-folders", json={"names": []}).status_code == 400

        (b_dir / "燈具").rename(b_dir / "舊燈具")
        missing = client.get(f"/api/roots/{b}/excluded-folders").json()
        saved_missing = [f for f in missing["folders"] if f["name"] == "燈具"]
        assert saved_missing == [
            {"name": "燈具", "present": False, "locked": False, "excluded": True}
        ]
        assert client.get(f"/api/roots/{a}/excluded-folders").json()["saved"] == ["暫存照片"]

        a_dir.rename(tmp_path / "A-offline")
        offline = client.get(f"/api/roots/{a}/excluded-folders")
        assert offline.status_code == 409

    conn = connect(db)
    try:
        assert saved_root_exclusions(conn, a) == ["暫存照片"]
        assert saved_root_exclusions(conn, b) == ["燈具"]
        with pytest.raises(SettingsError):
            save_root_exclusions(conn, b, ["燈具/其他"])
    finally:
        conn.close()

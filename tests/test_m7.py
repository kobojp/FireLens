from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.backup import BackupError, export_backup, restore_backup
from backend.app.db import connect, initialize_database
from backend.app.logging_config import configure_logging, get_logger
from backend.app.main import create_app
from backend.app.settings import (
    SettingsError,
    get_settings,
    save_settings,
    update_category_aliases,
)
from desktop.version import __version__


def test_settings_persist_and_validate(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        updated = save_settings(
            conn,
            {
                "theme": "dark",
                "thumbnail_quality": 91,
                "slot_order": {
                    "extinguisher": ["完成", "藥劑", "編號"],
                    "box": ["後", "中", "前"],
                    "lamp": ["前", "後", "中"],
                },
                "quick_create": {
                    "category_code": "extinguisher",
                    "year": "2026年",
                    "period": "10月份更換",
                    "building": "中正樓",
                },
            },
        )
        assert updated["theme"] == "dark"
        assert updated["thumbnail_quality"] == 91
        conn.close()
        conn = connect(db_path)
        persisted = get_settings(conn)
        assert persisted["slot_order"]["extinguisher"] == ["完成", "藥劑", "編號"]
        assert persisted["quick_create"]["building"] == "中正樓"
        with pytest.raises(SettingsError):
            save_settings(conn, {"thumbnail_quality": 20})
        with pytest.raises(SettingsError):
            save_settings(conn, {"slot_order": {"extinguisher": ["完成"]}})
        with pytest.raises(SettingsError):
            save_settings(conn, {"quick_create": {"category_code": "unknown"}})
    finally:
        conn.close()


def test_category_alias_edit_is_guarded(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        result = update_category_aliases(
            conn,
            "extinguisher",
            {"有效日期": "藥劑", "編輯": "編號"},
        )
        assert result["filename_aliases"]["編輯"] == "編號"
        with pytest.raises(SettingsError):
            update_category_aliases(conn, "extinguisher", {"錯誤": "不存在槽位"})
    finally:
        conn.close()


def test_protected_backup_round_trip_without_photo_index(monkeypatch, tmp_path: Path) -> None:
    source_data = tmp_path / "source-data"
    target_data = tmp_path / "target-data"
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(source_data))
    source_db = initialize_database(source_data / "firelens.sqlite3")
    source = connect(source_db)
    try:
        with source:
            root_id = int(
                source.execute(
                    """
                    INSERT INTO root(label, path, is_cloud_stream)
                    VALUES ('H Drive', 'H:/photos', 1)
                    """
                ).lastrowid
            )
            ledger_id = int(
                source.execute(
                    """
                    INSERT INTO ledger(name, source_type, source_sha256)
                    VALUES ('2026', 'xlsx', 'abc')
                    """
                ).lastrowid
            )
            source.execute(
                """
                INSERT INTO ledger_row(ledger_id, row_no, section, device_no)
                VALUES (?, 1, '中正樓1F', '中-01-01')
                """,
                (ledger_id,),
            )
            source.execute(
                """
                INSERT INTO alias_map(alias_type, source_value, target_value, confirmed)
                VALUES ('building', '第一門診', '一門診', 1)
                """
            )
            source.execute("INSERT INTO setting(key, value_json) VALUES ('theme', '\"dark\"')")
            category_id = int(
                source.execute("SELECT id FROM category WHERE code='extinguisher'").fetchone()[0]
            )
            source.execute(
                """
                INSERT INTO item(root_id, category_id, year, period, building, code, relative_path)
                VALUES (?, ?, '2026年', '10月份更換', '中正樓', '中-01-01', 'x')
                """,
                (root_id, category_id),
            )
        blob, _ = export_backup(source)
    finally:
        source.close()

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        data = json.loads(archive.read("data.json"))
        assert "items" not in data
        assert "photos" not in data
        assert data["ledgers"][0]["rows"][0]["device_no"] == "中-01-01"

    monkeypatch.setenv("FIRELENS_DATA_DIR", str(target_data))
    target_db = initialize_database(target_data / "firelens.sqlite3")
    target = connect(target_db)
    try:
        restored = restore_backup(target, blob, db_path=target_db)
        assert restored["restored"] is True
        assert Path(restored["snapshot_path"]).is_file()
        assert target.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 0
        assert target.execute("SELECT COUNT(*) FROM ledger").fetchone()[0] == 1
        assert (
            target.execute("SELECT value_json FROM setting WHERE key='theme'").fetchone()[0]
            == '"dark"'
        )
        root = target.execute("SELECT label, path, is_cloud_stream FROM root").fetchone()
        assert tuple(root) == ("H Drive", "H:/photos", 1)
    finally:
        target.close()


def test_backup_rejects_tampered_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    db = initialize_database(tmp_path / "data" / "firelens.sqlite3")
    conn = connect(db)
    try:
        blob, _ = export_backup(conn)
        source = zipfile.ZipFile(io.BytesIO(blob))
        output = io.BytesIO()
        with source, zipfile.ZipFile(output, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "data.json":
                    content += b" "
                target.writestr(info.filename, content)
        with pytest.raises(BackupError, match="SHA-256"):
            restore_backup(conn, output.getvalue(), db_path=db)
    finally:
        conn.close()


def test_settings_api_and_app_info(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as client:
        settings = client.get("/api/settings")
        assert settings.status_code == 200
        assert settings.json()["theme"] == "system"
        assert settings.json()["quick_create"]["category_code"] == "extinguisher"
        updated = client.put(
            "/api/settings",
            json={"theme": "light", "thumbnail_quality": 88},
        )
        assert updated.status_code == 200
        assert updated.json()["thumbnail_quality"] == 88
        info = client.get("/api/app-info")
        assert info.status_code == 200
        assert info.json()["version"] == __version__
        assert info.json()["online_update_enabled"] is False


def test_rotating_log_written_under_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    path = configure_logging()
    get_logger("firelens.test").info("m7-log-test")
    for handler in get_logger("firelens").handlers:
        handler.flush()
    assert path.is_file()
    assert "m7-log-test" in path.read_text(encoding="utf-8")

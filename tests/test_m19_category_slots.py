"""M19-B: category slot defaults, safe v10 migration and user-configurable slots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.db import connect, initialize_database
from backend.app.main import create_app
from backend.app.photo_quality import gallery
from backend.app.scanner import scan_root
from backend.app.settings import SettingsError, update_category_slots
from tests.test_m19_dynamic_folders import _jpeg_bytes, _setup


def _hose(conn, root_id: int):
    code = str(conn.execute("SELECT code FROM category WHERE name='水帶'").fetchone()[0])
    item = conn.execute("SELECT id FROM item WHERE code='水-01'").fetchone()
    assert item is not None
    return code, int(item["id"])


def test_hose_three_photo_slots_and_quality(tmp_path: Path) -> None:
    conn, root_id, root = _setup(tmp_path)
    try:
        folder = root / "水帶" / "倉庫" / "水-01"
        (folder / "中.jpg").write_bytes(_jpeg_bytes("green"))
        (folder / "後.jpg").write_bytes(_jpeg_bytes("blue"))
        scan_root(conn, root_id)
        code, item_id = _hose(conn, root_id)
        photos = conn.execute(
            "SELECT filename,slot FROM photo WHERE item_id=? ORDER BY filename",
            (item_id,),
        ).fetchall()
        assert {p["filename"]: p["slot"] for p in photos} == {
            "前.jpg": "前",
            "中.jpg": "中",
            "後.jpg": "後",
        }
        status = conn.execute("SELECT status FROM item WHERE id=?", (item_id,)).fetchone()[0]
        assert status == "complete"
        result = gallery(conn, root_id, category=code, problem_only=False)
        assert result["total"] == 1
        assert result["items"][0]["missing_slots"] == []
        assert result["items"][0]["slots"] == ["前", "中", "後"]
    finally:
        conn.close()


def test_v10_single_photo_upgrade_preserves_photo_files_and_rows(tmp_path: Path) -> None:
    conn, root_id, root = _setup(tmp_path)
    db_path = tmp_path / "data" / "firelens.sqlite3"
    folder = root / "水帶" / "倉庫" / "水-01"
    original = (folder / "前.jpg").read_bytes()
    try:
        scan_root(conn, root_id)
        code, item_id = _hose(conn, root_id)
        photo_id = conn.execute("SELECT id FROM photo WHERE item_id=?", (item_id,)).fetchone()[0]
        with conn:
            conn.execute(
                "UPDATE category SET slots_json=? WHERE code=?",
                ('["照片"]', code),
            )
            conn.execute(
                "INSERT OR REPLACE INTO setting(key,value_json) VALUES ('slot_order',?)",
                (json.dumps({code: ["照片"]}, ensure_ascii=False),),
            )
            conn.execute("PRAGMA user_version = 10")
    finally:
        conn.close()
    initialize_database(db_path)
    upgraded = connect(db_path)
    try:
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 11
        slots = json.loads(
            upgraded.execute(
                "SELECT slots_json FROM category WHERE code=?",
                (code,),
            ).fetchone()[0]
        )
        assert slots == ["前", "中", "後"]
        order = json.loads(
            upgraded.execute(
                "SELECT value_json FROM setting WHERE key='slot_order'",
            ).fetchone()[0]
        )
        assert order[code] == ["前", "中", "後"]
        scan_root(upgraded, root_id)
        assert upgraded.execute("SELECT id FROM item WHERE code='水-01'").fetchone()[0] == item_id
        assert (folder / "前.jpg").read_bytes() == original
        assert (
            upgraded.execute("SELECT slot FROM photo WHERE item_id=?", (item_id,)).fetchone()[0]
            == "前"
        )
        assert photo_id > 0
    finally:
        upgraded.close()


def test_custom_slot_rename_is_confirmed_and_files_stay_unchanged(tmp_path: Path) -> None:
    conn, root_id, root = _setup(tmp_path)
    try:
        scan_root(conn, root_id)
        code, item_id = _hose(conn, root_id)
        filename = root / "水帶" / "倉庫" / "水-01" / "前.jpg"
        original = filename.read_bytes()
        original_photo_id = conn.execute(
            "SELECT id FROM photo WHERE item_id=?",
            (item_id,),
        ).fetchone()[0]
        with pytest.raises(SettingsError, match="再次確認"):
            update_category_slots(conn, code, ["進場", "中", "後"])
        updated = update_category_slots(
            conn,
            code,
            ["進場", "中", "後"],
            confirm_unmapped=True,
        )
        assert updated["slots"] == ["進場", "中", "後"]
        assert filename.read_bytes() == original
        photo = conn.execute(
            "SELECT id, slot FROM photo WHERE item_id=?",
            (item_id,),
        ).fetchone()
        assert photo["id"] == original_photo_id
        assert photo["slot"] is None
        result = gallery(conn, root_id, category=code, problem_only=False)
        assert "未對應照片" in result["items"][0]["slots"]
        assert "進場" in result["items"][0]["missing_slots"]
        with pytest.raises(SettingsError, match="至少"):
            update_category_slots(conn, code, [])
        with pytest.raises(SettingsError, match="重複"):
            update_category_slots(conn, code, ["前", "前"])
        with pytest.raises(SettingsError, match="槽位名稱"):
            update_category_slots(conn, code, ["../bad"])
    finally:
        conn.close()


def test_original_categories_allow_customization_and_protect_aliases(tmp_path: Path) -> None:
    conn, _, _ = _setup(tmp_path)
    try:
        changed = update_category_slots(conn, "extinguisher", ["編號", "藥劑", "完成", "巡檢"])
        assert changed["slots"] == ["編號", "藥劑", "完成", "巡檢"]
        assert changed["filename_aliases"]["有效日期"] == "藥劑"
        assert update_category_slots(conn, "box", ["前", "中", "後", "設備外觀"])["slots"] == [
            "前",
            "中",
            "後",
            "設備外觀",
        ]
        assert update_category_slots(conn, "lamp", ["前", "中", "後", "檢查"])["slots"] == [
            "前",
            "中",
            "後",
            "檢查",
        ]
        with pytest.raises(SettingsError, match="同義詞"):
            update_category_slots(
                conn, "extinguisher", ["編號", "藥劑", "完成", "巡檢", "有效日期"]
            )
    finally:
        conn.close()


def test_category_slots_http_endpoint(tmp_path: Path, monkeypatch) -> None:
    conn, root_id, _ = _setup(tmp_path)
    try:
        scan_root(conn, root_id)
        code, _ = _hose(conn, root_id)
    finally:
        conn.close()
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        response = client.put(
            f"/api/categories/{code}/slots",
            json={"slots": ["前", "中", "後", "環境"]},
        )
        assert response.status_code == 200, response.text
        categories = {value["code"]: value for value in client.get("/api/categories").json()}
        assert categories[code]["slots"] == ["前", "中", "後", "環境"]
        denied = client.put(
            f"/api/categories/{code}/slots",
            json={"slots": ["進場", "中", "後"]},
        )
        assert denied.status_code == 400
        allowed = client.put(
            f"/api/categories/{code}/slots",
            json={"slots": ["進場", "中", "後"], "confirm_unmapped": True},
        )
        assert allowed.status_code == 200

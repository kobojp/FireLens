"""M19-I synthetic tests: atomic chip layout and historic API compatibility."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.scanner import scan_root
from backend.app.settings import SettingsError, get_settings, update_category_slots
from tests.test_m19_dynamic_folders import _setup


def _context(tmp_path: Path):
    conn, root_id, root = _setup(tmp_path)
    scan_root(conn, root_id)
    cat = conn.execute("SELECT code FROM category WHERE name='水帶'").fetchone()
    assert cat is not None
    return conn, root_id, root, str(cat["code"])


def _snapshot(
    conn, code: str
) -> tuple[str, str, list[str], list[str], list[tuple[int, str | None]]]:
    row = conn.execute(
        "SELECT slots_json, filename_aliases_json FROM category WHERE code=?", (code,)
    ).fetchone()
    prefs = get_settings(conn)
    photos = conn.execute(
        """SELECT p.id,p.slot FROM photo p JOIN item i ON i.id=p.item_id
           JOIN category c ON c.id=i.category_id WHERE c.code=? ORDER BY p.id""",
        (code,),
    ).fetchall()
    return (
        row["slots_json"],
        row["filename_aliases_json"],
        prefs["slot_order"].get(code, []),
        prefs["custom_slots"].get(code, []),
        [(photo["id"], photo["slot"]) for photo in photos],
    )


def test_hose_chip_layout_is_atomic_ordered_and_preserves_original_photo(tmp_path: Path):
    conn, _, root, code = _context(tmp_path)
    original_file = root / "水帶" / "倉庫" / "水-01" / "前.jpg"
    before_bytes = original_file.read_bytes()
    before_id = conn.execute("SELECT id FROM photo WHERE filename='前.jpg'").fetchone()["id"]
    try:
        changed = update_category_slots(
            conn,
            code,
            ["前", "中", "後", "俯視"],
            slot_order=["後", "俯視", "前", "中"],
            custom_slots=["側面", "壓力錶"],
        )
        assert changed["slots"] == ["前", "中", "後", "俯視"]
        settings = get_settings(conn)
        assert settings["slot_order"][code] == ["後", "俯視", "前", "中"]
        assert settings["custom_slots"][code] == ["側面", "壓力錶"]
        assert original_file.read_bytes() == before_bytes
        assert (
            conn.execute("SELECT id,slot FROM photo WHERE id=?", (before_id,)).fetchone()["slot"]
            == "前"
        )
        assert conn.execute("SELECT id FROM photo WHERE id=?", (before_id,)).fetchone() is not None
        assert (
            conn.execute("SELECT name FROM category WHERE code=?", (code,)).fetchone() is not None
        )
    finally:
        conn.close()


def test_invalid_order_or_optional_name_rolls_back_all_fields(tmp_path: Path):
    conn, _, root, code = _context(tmp_path)
    original = (root / "水帶" / "倉庫" / "水-01" / "前.jpg").read_bytes()
    before = _snapshot(conn, code)
    try:
        cases = [
            (["前", "中", "後"], ["後", "前"], ["側面"]),
            (["前", "中", "後"], ["前", "前", "後"], ["側面"]),
            (["前", "中", "後"], ["前", "中", "後"], ["前"]),
            (["前", "中", "後"], ["前", "中", "後"], ["側面", "側面"]),
            (["前", "中", "後"], ["前", "中", "後"], ["../../壞"]),
            (["前", "中", "後"], ["前", "中", "後"], ["A" * 21]),
        ]
        for slots, order, optional in cases:
            with pytest.raises(SettingsError):
                update_category_slots(conn, code, slots, slot_order=order, custom_slots=optional)
            assert _snapshot(conn, code) == before
        with pytest.raises(SettingsError, match="再次確認"):
            update_category_slots(
                conn,
                code,
                ["進場", "中", "後"],
                slot_order=["中", "進場", "後"],
                custom_slots=["俯視"],
            )
        assert _snapshot(conn, code) == before
        assert (root / "水帶" / "倉庫" / "水-01" / "前.jpg").read_bytes() == original
    finally:
        conn.close()


def test_old_category_slots_api_still_resets_only_its_category_and_filters_custom(tmp_path: Path):
    conn, _, _, code = _context(tmp_path)
    try:
        update_category_slots(
            conn,
            code,
            ["前", "中", "後"],
            slot_order=["後", "前", "中"],
            custom_slots=["側面"],
        )
        response = update_category_slots(conn, code, ["前", "中", "後", "側面"])
        assert response["slots"] == ["前", "中", "後", "側面"]
        assert get_settings(conn)["slot_order"][code] == ["前", "中", "後", "側面"]
        assert get_settings(conn)["custom_slots"][code] == []
    finally:
        conn.close()


def test_removing_optional_chip_requires_confirm_and_keeps_source_bytes(tmp_path: Path):
    from tests.test_m19_dynamic_folders import _jpeg_bytes

    conn, root_id, root = _setup(tmp_path)
    photo_path = root / "水帶" / "倉庫" / "水-01" / "側面.jpg"
    photo_path.write_bytes(_jpeg_bytes("purple"))
    original = photo_path.read_bytes()
    scan_root(conn, root_id)
    category = conn.execute("SELECT code FROM category WHERE name='水帶'").fetchone()
    assert category is not None
    code = str(category["code"])
    try:
        update_category_slots(
            conn,
            code,
            ["前", "中", "後"],
            slot_order=["後", "前", "中"],
            custom_slots=["側面"],
        )
        matched = conn.execute("SELECT id,slot FROM photo WHERE filename='側面.jpg'").fetchone()
        assert matched is not None and matched["slot"] == "側面"
        old_state = _snapshot(conn, code)

        with pytest.raises(SettingsError, match="再次確認"):
            update_category_slots(
                conn,
                code,
                ["前", "中", "後"],
                slot_order=["後", "前", "中"],
                custom_slots=[],
            )
        assert _snapshot(conn, code) == old_state
        assert photo_path.read_bytes() == original

        update_category_slots(
            conn,
            code,
            ["前", "中", "後"],
            confirm_unmapped=True,
            slot_order=["後", "前", "中"],
            custom_slots=[],
        )
        assert photo_path.read_bytes() == original
        after = conn.execute("SELECT id,slot FROM photo WHERE id=?", (matched["id"],)).fetchone()
        assert after["id"] == matched["id"]
        assert after["slot"] is None
        assert get_settings(conn)["slot_order"][code] == ["後", "前", "中"]
        assert get_settings(conn)["custom_slots"][code] == []
    finally:
        conn.close()


def test_chips_api_returns_persistent_layout_and_rejects_invalid_payload(
    tmp_path: Path, monkeypatch
):
    conn, _, root, code = _context(tmp_path)
    original = (root / "水帶" / "倉庫" / "水-01" / "前.jpg").read_bytes()
    before = _snapshot(conn, code)
    conn.close()
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        invalid = client.put(
            f"/api/categories/{code}/slots",
            json={
                "slots": ["進場", "中", "後"],
                "confirm_unmapped": True,
                "slot_order": ["中", "進場", "後"],
                "custom_slots": ["進場"],
            },
        )
        assert invalid.status_code == 400, invalid.text
        assert invalid.json()["detail"]
        current = client.get("/api/settings").json()
        assert current["slot_order"].get(code, []) == before[2]

        saved = client.put(
            f"/api/categories/{code}/slots",
            json={
                "slots": ["前", "中", "後"],
                "slot_order": ["後", "中", "前"],
                "custom_slots": ["側面"],
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["slots"] == ["前", "中", "後"]
        newest = client.get("/api/settings").json()
        assert newest["slot_order"][code] == ["後", "中", "前"]
        assert newest["custom_slots"][code] == ["側面"]
        assert (root / "水帶" / "倉庫" / "水-01" / "前.jpg").read_bytes() == original

        legacy = client.put(f"/api/categories/{code}/slots", json={"slots": ["前", "中", "後"]})
        assert legacy.status_code == 200
        assert client.get("/api/settings").json()["custom_slots"][code] == ["側面"]

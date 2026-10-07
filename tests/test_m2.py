from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import storage
from backend.app.db import connect
from backend.app.main import create_app
from backend.app.scanner import scan_root


def jpeg_bytes(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (24, 16), color).save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def find_item(nodes: list[dict[str, object]], label: str) -> dict[str, object]:
    for node in nodes:
        if node.get("type") == "item" and node.get("label") == label:
            return node
        children = node.get("children")
        if isinstance(children, list):
            try:
                return find_item(children, label)
            except LookupError:
                pass
    raise LookupError(label)


def setup_client(monkeypatch, tmp_path: Path, sample_source: Path) -> tuple[TestClient, int, Path]:
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(appdata))
    client = TestClient(create_app())
    client.__enter__()
    created = client.post(
        "/api/roots",
        json={"path": str(sample_source), "label": "M2 合成測試"},
    )
    assert created.status_code == 201
    root_id = int(created.json()["id"])
    scan = client.post(f"/api/roots/{root_id}/scan")
    assert scan.status_code == 200
    return client, root_id, appdata / "firelens.sqlite3"


def test_category_slot_definitions(monkeypatch, tmp_path: Path, sample_source: Path) -> None:
    client, _, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        response = client.get("/api/categories")
        assert response.status_code == 200
        categories = {row["code"]: row for row in response.json()}
        assert categories["extinguisher"]["slots"] == ["編號", "藥劑", "完成"]
        assert categories["extinguisher"]["filename_aliases"] == {"有效日期": "藥劑"}
        assert categories["box"]["slots"] == ["前", "中", "後"]
        assert categories["lamp"]["slots"] == ["前", "中", "後"]
    finally:
        client.__exit__(None, None, None)


def test_import_no_overwrite_replace_and_audit(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    source_file = tmp_path / "camera.JPG"
    original = jpeg_bytes((220, 40, 20))
    source_file.write_bytes(original)
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()

    try:
        tree = client.get(f"/api/roots/{root_id}/tree").json()
        empty_item = find_item(tree, "中-01-02")
        item_id = int(empty_item["id"])

        imported = client.post(
            f"/api/items/{item_id}/slots/編號/photos",
            files={"file": (source_file.name, source_file.read_bytes(), "image/jpeg")},
        )
        assert imported.status_code == 200
        detail = imported.json()
        number_photo = next(photo for photo in detail["photos"] if photo["slot"] == "編號")
        target = (
            sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02" / "編號.jpg"
        )
        assert target.read_bytes() == original
        assert hashlib.sha256(source_file.read_bytes()).hexdigest() == source_hash

        before_conflict = target.read_bytes()
        second = client.post(
            f"/api/items/{item_id}/slots/編號/photos",
            files={"file": ("again.jpg", jpeg_bytes((10, 20, 30)), "image/jpeg")},
        )
        assert second.status_code == 200
        assert target.read_bytes() == before_conflict
        assert (target.parent / "編號-1.jpg").is_file()
        number_photo = next(
            photo for photo in second.json()["photos"] if photo["filename"] == "編號.jpg"
        )

        replacement_source = tmp_path / "replacement.jpg"
        replacement_bytes = jpeg_bytes((20, 80, 220))
        replacement_source.write_bytes(replacement_bytes)
        replacement_hash = hashlib.sha256(replacement_source.read_bytes()).hexdigest()
        replaced = client.post(
            f"/api/items/{item_id}/slots/編號/photos",
            params={"replace_photo_id": number_photo["id"]},
            files={
                "file": (
                    replacement_source.name,
                    replacement_source.read_bytes(),
                    "image/jpeg",
                )
            },
        )
        assert replaced.status_code == 200
        assert target.read_bytes() == replacement_bytes
        assert hashlib.sha256(replacement_source.read_bytes()).hexdigest() == replacement_hash
        assert not list(target.parent.glob(".firelens-*"))

        preview_id = next(
            photo["id"] for photo in replaced.json()["photos"] if photo["filename"] == "編號.jpg"
        )
        preview = client.get(f"/api/photos/{preview_id}/content")
        assert preview.status_code == 200
        assert preview.content == replacement_bytes

        conn = connect(db_path)
        try:
            actions = [
                row[0]
                for row in conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()
            ]
        finally:
            conn.close()
        assert actions == ["import_photo", "import_photo", "replace_photo"]
    finally:
        client.__exit__(None, None, None)


def test_box_slot_uses_incrementing_names(monkeypatch, tmp_path: Path, sample_source: Path) -> None:
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        item = find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-02-C124")
        item_id = int(item["id"])
        payload = jpeg_bytes((60, 180, 80))
        first = client.post(
            f"/api/items/{item_id}/slots/前/photos",
            files={"file": ("front.jpg", payload, "image/jpeg")},
        )
        second = client.post(
            f"/api/items/{item_id}/slots/前/photos",
            files={"file": ("front2.jpg", payload, "image/jpeg")},
        )
        assert first.status_code == second.status_code == 200
        names = {photo["filename"] for photo in second.json()["photos"] if photo["slot"] == "前"}
        assert names == {"前.jpg", "前-1.jpg"}
    finally:
        client.__exit__(None, None, None)


def test_create_item_folder_and_reject_traversal(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        created = client.post(
            "/api/items",
            json={
                "root_id": root_id,
                "category_code": "box",
                "year": "2026年",
                "period": "10月份更換",
                "building": "新棟",
                "code": "箱-01",
            },
        )
        assert created.status_code == 201
        assert created.json()["code"] == "箱-01"
        target = sample_source / "放置盒" / "2026年" / "10月份更換" / "新棟" / "箱-01"
        assert target.is_dir()
        assert created.json()["photos"] == []

        duplicate = client.post(
            "/api/items",
            json={
                "root_id": root_id,
                "category_code": "box",
                "year": "2026年",
                "period": "10月份更換",
                "building": "新棟",
                "code": "箱-01",
            },
        )
        assert duplicate.status_code == 409

        traversal = client.post(
            "/api/items",
            json={
                "root_id": root_id,
                "category_code": "box",
                "year": "../2026年",
                "period": "10月份更換",
                "building": "新棟",
                "code": "箱-02",
            },
        )
        assert traversal.status_code == 400

        conn = connect(db_path)
        try:
            audit = conn.execute(
                "SELECT action, target_path FROM audit_log WHERE action = 'create_item_folder'"
            ).fetchone()
        finally:
            conn.close()
        assert audit is not None
        assert audit[1].endswith("放置盒/2026年/10月份更換/新棟/箱-01")
    finally:
        client.__exit__(None, None, None)


def test_create_empty_period_and_building_are_structural_not_fake_items(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        period = client.post(
            "/api/folders/period",
            json={
                "root_id": root_id,
                "category_code": "extinguisher",
                "year": "2026年",
                "period": "11月份更換",
            },
        )
        assert period.status_code == 201
        assert (sample_source / "滅火器" / "2026年" / "11月份更換").is_dir()

        tree = client.get(f"/api/roots/{root_id}/tree").json()
        extinguisher = next(node for node in tree if node["key"] == "extinguisher")
        year = next(node for node in extinguisher["children"] if node["key"] == "2026年")
        empty_period = next(node for node in year["children"] if node["key"] == "11月份更換")
        assert empty_period["children"] == []

        building = client.post(
            "/api/folders/building",
            json={
                "root_id": root_id,
                "category_code": "extinguisher",
                "year": "2026年",
                "period": "11月份更換",
                "building": "新棟",
            },
        )
        assert building.status_code == 201
        assert (sample_source / "滅火器" / "2026年" / "11月份更換" / "新棟").is_dir()

        rescanned = client.post(f"/api/roots/{root_id}/scan")
        assert rescanned.status_code == 200
        tree = client.get(f"/api/roots/{root_id}/tree").json()
        extinguisher = next(node for node in tree if node["key"] == "extinguisher")
        year = next(node for node in extinguisher["children"] if node["key"] == "2026年")
        period_node = next(node for node in year["children"] if node["key"] == "11月份更換")
        building_node = next(node for node in period_node["children"] if node["key"] == "新棟")
        assert building_node["type"] == "building"
        assert building_node["children"] == []
        with pytest.raises(LookupError):
            find_item(tree, "新棟")

        created = client.post(
            "/api/items",
            json={
                "root_id": root_id,
                "category_code": "extinguisher",
                "year": "2026年",
                "period": "11月份更換",
                "building": "新棟",
                "code": "新-01-01",
            },
        )
        assert created.status_code == 201
        assert (sample_source / "滅火器" / "2026年" / "11月份更換" / "新棟" / "新-01-01").is_dir()
    finally:
        client.__exit__(None, None, None)


def test_preview_blocks_relative_path_escape(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(jpeg_bytes((1, 2, 3)))
    try:
        item = find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-01-02")
        conn = connect(db_path)
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO photo(
                        item_id, filename, relative_path, extension, slot, size_bytes, mtime_ns
                    ) VALUES (?, 'outside.jpg', '../outside.jpg', '.jpg', NULL, 1, 1)
                    """,
                    (int(item["id"]),),
                )
            photo_id = int(cursor.lastrowid)
        finally:
            conn.close()

        response = client.get(f"/api/photos/{photo_id}/content")
        assert response.status_code == 400
        assert "超出" in response.json()["detail"]
    finally:
        client.__exit__(None, None, None)


def test_heic_import_converts_to_jpeg(monkeypatch, tmp_path: Path, sample_source: Path) -> None:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    heic_source = tmp_path / "camera.heic"
    Image.new("RGB", (30, 18), (120, 40, 210)).save(heic_source, format="HEIF", quality=95)
    before = heic_source.read_bytes()

    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        item = find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-01-02")
        response = client.post(
            f"/api/items/{item['id']}/slots/編號/photos",
            files={"file": (heic_source.name, heic_source.read_bytes(), "image/heic")},
        )
        assert response.status_code == 200
        target = (
            sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02" / "編號.jpg"
        )
        assert target.is_file()
        with Image.open(target) as converted:
            assert converted.format == "JPEG"
            assert converted.size == (30, 18)
        assert heic_source.read_bytes() == before
    finally:
        client.__exit__(None, None, None)


def test_exif_orientation_is_applied_without_changing_source(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    source = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (10, 20), (20, 180, 220)).save(
        source,
        format="JPEG",
        quality=95,
        exif=exif,
    )
    before = source.read_bytes()

    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        item = find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-01-02")
        response = client.post(
            f"/api/items/{item['id']}/slots/藥劑/photos",
            files={"file": (source.name, source.read_bytes(), "image/jpeg")},
        )
        assert response.status_code == 200
        target = (
            sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02" / "藥劑.jpg"
        )
        with Image.open(target) as corrected:
            assert corrected.size == (20, 10)
            assert corrected.getexif().get(274, 1) in (None, 1)
        assert source.read_bytes() == before
    finally:
        client.__exit__(None, None, None)


def _direct_item(conn, sample_source: Path) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO root(label, path, is_cloud_stream) VALUES ('direct', ?, 0)",
            (str(sample_source.resolve()),),
        )
    root_id = int(cursor.lastrowid)
    scan_root(conn, root_id)
    row = conn.execute("SELECT id FROM item WHERE code = '中-01-02'").fetchone()
    assert row is not None
    return int(row[0])


def test_new_import_rolls_back_when_audit_fails(
    monkeypatch, db_path: Path, sample_source: Path
) -> None:
    conn = connect(db_path)
    try:
        item_id = _direct_item(conn, sample_source)
        target = (
            sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02" / "編號.jpg"
        )

        def fail_audit(*_args, **_kwargs):
            raise RuntimeError("simulated audit failure")

        monkeypatch.setattr(storage, "_audit", fail_audit)
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            storage.import_photo(conn, item_id, "編號", "camera.jpg", jpeg_bytes((20, 30, 40)))

        assert not target.exists()
        assert not list(target.parent.glob(".firelens-*"))
        row = conn.execute("SELECT photo_count FROM item WHERE id = ?", (item_id,)).fetchone()
        assert row is not None and row[0] == 0
    finally:
        conn.close()


def test_replace_rolls_back_when_audit_fails(
    monkeypatch, db_path: Path, sample_source: Path
) -> None:
    conn = connect(db_path)
    try:
        item_id = _direct_item(conn, sample_source)
        first = jpeg_bytes((180, 30, 30))
        storage.import_photo(conn, item_id, "編號", "first.jpg", first)
        photo = conn.execute(
            "SELECT id FROM photo WHERE item_id = ? AND slot = '編號'", (item_id,)
        ).fetchone()
        assert photo is not None
        target = (
            sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02" / "編號.jpg"
        )
        original_hash = hashlib.sha256(target.read_bytes()).hexdigest()

        def fail_audit(*_args, **_kwargs):
            raise RuntimeError("simulated audit failure")

        monkeypatch.setattr(storage, "_audit", fail_audit)
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            storage.import_photo(
                conn,
                item_id,
                "編號",
                "replacement.jpg",
                jpeg_bytes((30, 30, 200)),
                replace_photo_id=int(photo[0]),
            )

        assert hashlib.sha256(target.read_bytes()).hexdigest() == original_hash
        assert not list(target.parent.glob(".firelens-*"))
        indexed = conn.execute(
            "SELECT filename, slot FROM photo WHERE item_id = ?", (item_id,)
        ).fetchall()
        assert [(row[0], row[1]) for row in indexed] == [("編號.jpg", "編號")]
        audit_actions = [
            row[0] for row in conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()
        ]
        assert audit_actions == ["import_photo"]
    finally:
        conn.close()

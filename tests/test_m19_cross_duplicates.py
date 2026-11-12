"""M19-C: fully synthetic cross-equipment duplicate detection and index safety."""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.app.db import connect
from backend.app.duplicates import (
    AUTO_HASH_LIMIT,
    grouped,
    index_photos,
    preflight,
)
from backend.app.main import create_app
from backend.app.scanner import scan_root
from backend.app.storage import DuplicatePhotoConflict, import_photo, sha256_file
from tests.test_m19_dynamic_folders import _jpeg_bytes, _setup


def _with_cross_equipment(tmp_path: Path):
    conn, root_id, root = _setup(tmp_path)
    source = root / "滅火器" / "2026年" / "11月" / "三館" / "三-07-25"
    source.mkdir(parents=True)
    (source / "編號.jpg").write_bytes(_jpeg_bytes("red"))
    another = root / "水帶" / "倉庫" / "F-19-13"
    another.mkdir(parents=True)
    (another / "前.jpg").write_bytes(_jpeg_bytes("red"))
    scan_root(conn, root_id)
    return conn, root_id, root, source, another


def test_cross_category_exact_duplicate_and_import_prompt(tmp_path):
    conn, root_id, root, source, another = _with_cross_equipment(tmp_path)
    try:
        old_hash = sha256_file(source / "編號.jpg")
        photo_count = conn.execute(
            "SELECT COUNT(*) FROM photo WHERE item_id IN (SELECT id FROM item WHERE root_id=?)",
            (root_id,),
        ).fetchone()[0]
        first = index_photos(conn, root_id)
        assert first["analyzed"] >= 3
        assert first["pending"] == 0
        assert index_photos(conn, root_id)["analyzed"] == 0
        results = grouped(conn, root_id)
        assert results["total"] == 1
        assert results["groups"][0]["device_count"] == 3  # original water, new water, extinguisher
        codes = {p["code"] for p in results["groups"][0]["photos"]}
        assert {"三-07-25", "F-19-13", "水-01"} <= codes

        dest_id = conn.execute("SELECT id FROM item WHERE code=?", ("F-19-13",)).fetchone()[0]
        with pytest.raises(DuplicatePhotoConflict) as conflict:
            import_photo(conn, dest_id, "中", "triple.jpg", _jpeg_bytes("red"))
        assert any(p["code"] == "三-07-25" for p in conflict.value.matches)
        assert not (another / "中.jpg").exists()
        assert sha256_file(source / "編號.jpg") == old_hash
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM photo WHERE item_id IN (SELECT id FROM item WHERE root_id=?)",
                (root_id,),
            ).fetchone()[0]
            == photo_count
        )

        accepted = import_photo(
            conn,
            dest_id,
            "中",
            "approved.jpg",
            _jpeg_bytes("red"),
            allow_duplicate=True,
        )
        assert accepted["filename"] == "中.jpg"
        assert (another / "中.jpg").read_bytes() == _jpeg_bytes("red")
        assert grouped(conn, root_id)["total"] == 1
        # Reindex incremental recognizes the newly created photo.
        assert index_photos(conn, root_id)["analyzed"] >= 1
        assert grouped(conn, root_id)["groups"][0]["count"] == 4
    finally:
        conn.close()


def test_explorer_copy_incremental_and_deleted_photos(tmp_path):
    conn, root_id, root, source, another = _with_cross_equipment(tmp_path)
    try:
        index_photos(conn, root_id)
        prev = root / "水帶" / "倉庫" / "水-01" / "前.jpg"
        prev.write_bytes(_jpeg_bytes("green"))
        scan_root(conn, root_id)
        delta = index_photos(conn, root_id)
        assert delta["analyzed"] == 1
        assert delta["cached"] >= 2
        before = sha256_file(prev)
        assert grouped(conn, root_id)["groups"][0]["count"] == 2
        assert (source / "編號.jpg").read_bytes() == (another / "前.jpg").read_bytes()
        (another / "前.jpg").unlink()
        scan_root(conn, root_id)
        index_photos(conn, root_id)
        assert grouped(conn, root_id)["total"] == 0
        assert sha256_file(prev) == before
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM photo_fingerprint WHERE root_id=?",
                (root_id,),
            ).fetchone()[0]
            == 3
        )
    finally:
        conn.close()


def test_hash_not_filename_and_unscanned_limits(tmp_path):
    conn, root_id, root, _, another = _with_cross_equipment(tmp_path)
    try:
        result = index_photos(conn, root_id, full=True)
        assert result["analyzed"] >= 3
        # Re-rendering with equivalent pixel contents but different bytes is NOT identical.
        (another / "前.jpg").write_bytes(_jpeg_bytes("green"))
        scan_root(conn, root_id)
        index_photos(conn, root_id)
        digest = sha256_file(another / "前.jpg")
        assert len(preflight(conn, root_id, digest)) == 1
        assert grouped(conn, root_id)["groups"][0]["count"] == 2
        (another / "前.jpg").unlink()
        scan_root(conn, root_id)
        # old hash at a deleted relative path cannot match
        assert not any(p["code"] == "F-19-13" for p in preflight(conn, root_id, digest))
        assert AUTO_HASH_LIMIT > 0
    finally:
        conn.close()


def test_api_scan_and_csv_xlsx_complete_and_cloud_safe(tmp_path, monkeypatch):
    conn, root_id, root, source, another = _with_cross_equipment(tmp_path)
    conn.close()
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        initial = client.get(f"/api/duplicates/{root_id}")
        assert initial.status_code == 200
        assert initial.json()["pending"] >= 3
        response = client.post(f"/api/duplicates/{root_id}/scan", json={"full": False})
        assert response.status_code == 202, response.text
        outcome = None
        for _ in range(150):
            outcome = client.get(f"/api/duplicates/{root_id}/scan").json()
            if outcome["state"] != "running":
                break
            time.sleep(0.02)
        assert outcome and outcome["state"] == "completed", outcome

        groups = client.get(f"/api/duplicates/{root_id}").json()
        assert groups["total"] == 1
        assert groups["groups"][0]["device_count"] == 3
        for fmt in ("csv", "xlsx"):
            result = client.get(f"/api/duplicates/{root_id}/export", params={"fmt": fmt})
            assert result.status_code == 200
            if fmt == "csv":
                values = list(csv.reader(io.StringIO(result.content.decode("utf-8-sig"))))
                assert len(values) == 4
                assert "三-07-25" in repr(values)
            else:
                sheet = load_workbook(io.BytesIO(result.content)).active
                assert sheet.max_row == 4
                assert any(row[3] == "三-07-25" for row in sheet.iter_rows(values_only=True))
        invalid = client.post(
            f"/api/duplicates/{root_id}/export/save",
            json={"format": "pdf"},
        )
        assert invalid.status_code == 400
        content = client.post(
            f"/api/items/{_find_item_id(tmp_path, 'F-19-13')}/slots/中/photos",
            files={"file": ("repeat.jpg", _jpeg_bytes("red"), "image/jpeg")},
        )
        assert content.status_code == 409, content.text
        body = content.json()["detail"]
        assert body["code"] == "duplicate_photo"
        assert any(match["code"] == "三-07-25" for match in body["matches"])


def test_export_all_groups_beyond_page_limit(tmp_path):
    from backend.app.duplicates import export_groups

    conn, root_id, root, _, _ = _with_cross_equipment(tmp_path)
    try:
        for n in range(45):
            color = f"#{n * 5:02x}23cc"
            payload = _jpeg_bytes(color)
            for prefix in ("A", "B"):
                folder = root / "水帶" / "倉庫" / f"{prefix}-{n:02d}"
                folder.mkdir()
                (folder / "前.jpg").write_bytes(payload)
        scan_root(conn, root_id)
        scan = index_photos(conn, root_id)
        assert scan["pending"] == 0
        assert grouped(conn, root_id, limit=20)["total"] == 46
        all_groups = grouped(conn, root_id, limit=200)["groups"]
        content, _ = export_groups(all_groups, "csv")
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
        assert len(rows) == 94  # header + 45×2 + the original 3
        assert any(row[3] == "三-07-25" for row in rows)
    finally:
        conn.close()


def test_cloud_placeholder_skipped_without_claiming_clean(tmp_path):
    conn, root_id, _, _, _ = _with_cross_equipment(tmp_path)
    try:
        relative = conn.execute(
            "SELECT relative_path FROM photo WHERE filename='編號.jpg'"
        ).fetchone()[0]
        with conn:
            conn.execute(
                "UPDATE photo SET cloud_placeholder=1 WHERE relative_path=?",
                (relative,),
            )
        status = index_photos(conn, root_id)
        assert status["skipped"] >= 1
        results = grouped(conn, root_id)
        assert results["skipped"] >= 1
        assert results["groups"][0]["count"] == 2
    finally:
        conn.close()


def test_large_unindexed_root_requires_manual_scan(tmp_path, monkeypatch):
    import backend.app.duplicates as duplicate_module

    conn, root_id, _, source, _ = _with_cross_equipment(tmp_path)
    try:
        monkeypatch.setattr(duplicate_module, "AUTO_HASH_LIMIT", 1)
        with pytest.raises(duplicate_module.DuplicateIndexRequired, match="手動重複掃描"):
            preflight(conn, root_id, sha256_file(source / "編號.jpg"))
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM photo_fingerprint WHERE root_id=?",
                (root_id,),
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()


def _find_item_id(tmp_path: Path, code: str) -> int:
    conn = connect(tmp_path / "data" / "firelens.sqlite3")
    try:
        return int(conn.execute("SELECT id FROM item WHERE code=?", (code,)).fetchone()[0])
    finally:
        conn.close()

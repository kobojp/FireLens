"""M18 synthetic photo quality tests; never touch field photos."""

from __future__ import annotations

import io
import os
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image, ImageDraw

from backend.app.db import connect, initialize_database
from backend.app.photo_quality import (
    _run,
    export_quality,
    gallery,
    quality_algorithm,
    quality_score,
    review_photo,
)
from tests.test_m3 import add_root_and_scan


def _image(path: Path, sharp: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (800, 640), "#dddddd")
    if sharp:
        drawer = ImageDraw.Draw(image)
        for i in range(30):
            x = i * 24
            drawer.rectangle((x, 40, x + 12, 590), fill="black")
            drawer.line((0, i * 20, 799, i * 20), fill="white", width=2)
    image.save(path)


def _setup(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(data_dir))
    db = initialize_database()
    root = tmp_path / "synthetic"
    first = root / "滅火器" / "2026年" / "10月份更換" / "致德樓8F" / "致-08-66"
    first.mkdir(parents=True)
    _image(first / "編號.jpg")
    _image(first / "藥劑.jpg", sharp=False)
    rid = add_root_and_scan(db, root)
    return db, rid, first


def _job():
    return {
        "state": "running",
        "total": 0,
        "done": 0,
        "analyzed": 0,
        "cached": 0,
        "skipped": 0,
        "flagged": 0,
        "cancel": False,
        "error": "",
        "full": False,
    }


def test_manual_incremental_then_full_rescan_and_review(tmp_path, monkeypatch):
    db_path, root_id, folder = _setup(tmp_path, monkeypatch)
    with connect(db_path) as conn:
        before = gallery(conn, root_id, problem_only=False)
        assert before["total"] == 1
        assert len(before["items"][0]["missing_slots"]) == 1
        assert all(photo["status"] == "unscanned" for photo in before["items"][0]["photos"])
    first = _job()
    _run(root_id, "", "", first)
    assert first["state"] == "completed", first["error"]
    assert first["analyzed"] == 2 and first["cached"] == 0
    second = _job()
    _run(root_id, "", "", second)
    assert second["cached"] == 2 and second["analyzed"] == 0
    with connect(db_path) as conn:
        results = gallery(conn, root_id)
        assert results["total"] == 1
        assert any(p["status"] != "normal" for p in results["items"][0]["photos"])
        photo = results["items"][0]["photos"][0]
        review_photo(conn, photo["id"], "reshoot")
        updated = gallery(conn, root_id, problem_only=False)
        assert updated["items"][0]["photos"][0]["review"] == "reshoot"
        csv_content, _ = export_quality(updated["items"], "csv")
        assert "致-08-66" in csv_content.decode("utf-8-sig")
        xlsx, _ = export_quality(updated["items"], "xlsx")
        assert load_workbook(io.BytesIO(xlsx), read_only=True).active.max_row >= 2
    full = _job()
    full["full"] = True
    _run(root_id, "", "", full)
    assert full["analyzed"] == 2 and full["cached"] == 0
    with connect(db_path) as conn:
        assert (
            gallery(conn, root_id, problem_only=False)["items"][0]["photos"][0]["review"]
            == "reshoot"
        )
    assert (folder / "編號.jpg").is_file()


def test_blur_score_is_read_only_and_ignores_low_texture(tmp_path):
    sharp, blank, broken = tmp_path / "sharp.png", tmp_path / "white.png", tmp_path / "broken.jpg"
    _image(sharp)
    _image(blank, sharp=False)
    broken.write_bytes(b"not-a-photo")
    before = {p: p.read_bytes() for p in (sharp, blank, broken)}
    assert quality_score(sharp, "extinguisher", "編號")["status"] in ("normal", "possible")
    assert quality_score(blank, "lamp", "後")["status"] == "uncertain"
    assert "decode" in quality_score(broken, "box", "前")["issues"]
    assert all(p.read_bytes() == data for p, data in before.items())


def test_empty_root_and_cancel_do_not_wipe_records(tmp_path, monkeypatch):
    db_path, root_id, folder = _setup(tmp_path, monkeypatch)
    job = _job()
    job["cancel"] = True
    _run(root_id, "", "", job)
    assert job["state"] == "cancelled" and job["analyzed"] == 0
    with connect(db_path) as conn:
        assert gallery(conn, root_id, problem_only=False)["total"] == 1
    folder.parents[4].rename(tmp_path / "offline")
    failed = _job()
    _run(root_id, "", "", failed)
    assert failed["state"] == "error"
    with connect(db_path) as conn:
        assert gallery(conn, root_id, problem_only=False)["total"] == 1


def test_incremental_added_and_changed_files_with_index_refresh(tmp_path, monkeypatch):
    db_path, root_id, folder = _setup(tmp_path, monkeypatch)
    first = _job()
    _run(root_id, "extinguisher", "10月份更換", first)
    assert first["state"] == "completed" and first["analyzed"] == 2

    original = folder / "編號.jpg"
    previous = original.stat().st_mtime_ns
    _image(original, sharp=False)
    os.utime(original, ns=(previous + 2_000_000_000, previous + 2_000_000_000))
    _image(folder / "完成.jpg", sharp=True)
    incremental = _job()
    _run(root_id, "extinguisher", "10月份更換", incremental)
    assert incremental["state"] == "completed", incremental["error"]
    assert incremental["total"] == 3
    assert incremental["analyzed"] == 2
    assert incremental["cached"] == 1
    unchanged = _job()
    _run(root_id, "", "", unchanged)
    assert unchanged["analyzed"] == 0
    assert unchanged["cached"] == 3
    full = _job()
    full["full"] = True
    _run(root_id, "", "", full)
    assert full["analyzed"] == 3
    assert full["cached"] == 0
    with connect(db_path) as conn:
        versions = list(
            conn.execute("SELECT algorithm FROM photo_quality WHERE root_id=?", (root_id,))
        )
        assert len(versions) == 3
        assert all(row["algorithm"] == quality_algorithm(1.0) for row in versions)


def test_missing_slot_and_excel_formula_injection_safe(tmp_path, monkeypatch):
    db_path, root_id, _ = _setup(tmp_path, monkeypatch)
    with connect(db_path) as conn:
        info = gallery(conn, root_id, problem_only=True)
        assert info["total"] == 1
        assert info["items"][0]["missing_slots"] == ["完成"]
        csv_bytes, _ = export_quality(info["items"], "csv")
        assert "缺照片" in csv_bytes.decode("utf-8-sig")
        dangerous = {**info["items"][0], "code": "=SUM(A1:A9)"}
        csv_bytes, _ = export_quality([dangerous], "csv")
        assert "'=SUM(A1:A9)" in csv_bytes.decode("utf-8-sig")
        xlsx_bytes, _ = export_quality([dangerous], "xlsx")
        book = load_workbook(io.BytesIO(xlsx_bytes))
        try:
            assert str(book.active["A2"].value).startswith("'=")
        finally:
            book.close()


def test_photo_quality_filter_review_and_m18_schema_are_separate(tmp_path, monkeypatch):
    db_path, root_id, _ = _setup(tmp_path, monkeypatch)
    with connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 13
        before = gallery(conn, root_id, problem_only=False)
        photo = before["items"][0]["photos"][0]
        review_photo(conn, photo["id"], "wrong_content")
        matched = gallery(conn, root_id, problem_only=False, review_filter="wrong_content")
        assert matched["total"] == 1
        wrong = gallery(conn, root_id, problem_only=False, review_filter="reshoot")
        assert wrong["total"] == 0
        assert gallery(conn, root_id, status_filter="missing")["total"] == 1
        assert conn.execute("SELECT COUNT(*) FROM item_issue").fetchone()[0] == 0


def test_m18_http_endpoints_scan_review_export_and_reject_invalid_inputs(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    db_path, root_id, folder = _setup(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        base = f"/api/quality/{root_id}"
        listing = client.get(base, params={"problem_only": "false"})
        assert listing.status_code == 200, listing.text
        assert listing.json()["total"] == 1
        assert client.get(base, params={"category": "invalid"}).status_code == 400
        assert client.get(base, params={"status_filter": "unknown"}).status_code == 400
        assert client.get(base + "/export", params={"fmt": "pdf"}).status_code == 400

        manual = client.post(base + "/scan", json={"full": False, "category": "extinguisher"})
        assert manual.status_code == 202, manual.text
        from time import sleep

        state = None
        for _ in range(80):
            state = client.get(base + "/scan").json()
            if state["state"] != "running":
                break
            sleep(0.025)
        assert state is not None and state["state"] == "completed", state
        assert state["started_at"] is not None
        assert state["analysis_started_at"] is not None
        assert state["analyzed"] == 2
        new = client.post(base + "/scan", json={"full": False})
        assert new.status_code == 202, new.text
        for _ in range(80):
            state = client.get(base + "/scan").json()
            if state["state"] != "running":
                break
            sleep(0.025)
        assert state is not None and state["cached"] == 2, state

        photo_id = listing.json()["items"][0]["photos"][0]["id"]
        set_review = client.post(
            f"/api/quality/photos/{photo_id}/review", json={"review": "wrong_content"}
        )
        assert set_review.status_code == 200, set_review.text
        assert client.get(base, params={"review_filter": "wrong_content"}).json()["total"] == 1
        exported = client.get(base + "/export", params={"fmt": "csv"})
        assert exported.status_code == 200
        assert "缺照片" in exported.content.decode("utf-8-sig")
        assert client.get(base + "/export", params={"fmt": "xlsx"}).status_code == 200
        # Desktop exports use the same safe save/open registry as other FireLens pages.
        monkeypatch.setenv("FIRELENS_EXPORT_DIR", str(tmp_path / "quality-exports"))
        for format_name in ("csv", "xlsx"):
            saved = client.post(
                base + "/export/save",
                json={
                    "format": format_name,
                    "problem_only": False,
                    "review_filter": "wrong_content",
                },
            )
            assert saved.status_code == 200, saved.text
            result = saved.json()
            output = Path(result["path"])
            assert output.exists() and output.suffix == "." + format_name
            assert result["open_token"]
            if format_name == "csv":
                assert output.read_bytes().startswith(bytes((0xEF, 0xBB, 0xBF)))
                assert "編號.jpg" in output.read_text(encoding="utf-8-sig")
            else:
                assert load_workbook(output, read_only=True).active.max_row >= 2
        assert client.post(base + "/export/save", json={"format": "pdf"}).status_code == 400
        assert (
            client.post(
                base + "/export/save",
                json={"format": "csv", "category": "invalid"},
            ).status_code
            == 400
        )
        empty = client.post(
            base + "/export/save",
            json={"format": "csv", "query": "不存在的設備"},
        )
        assert empty.status_code == 200
        assert Path(empty.json()["path"]).read_bytes().startswith(bytes((0xEF, 0xBB, 0xBF)))
    assert (folder / "編號.jpg").is_file()


def test_quality_export_saves_all_filtered_devices_not_just_first_page(tmp_path, monkeypatch):
    import csv

    from fastapi.testclient import TestClient

    from backend.app.main import create_app
    from backend.app.scanner import scan_root

    db_path, root_id, first = _setup(tmp_path, monkeypatch)
    root = first.parents[4]
    for number in range(45):
        folder = root / "滅火器" / "2026年" / "10月份更換" / "致德樓8F" / f"致-99-{number:03}"
        folder.mkdir(parents=True)
        Image.new("RGB", (8, 8), "red").save(folder / "編號.jpg")
    with connect(db_path) as conn:
        scan_root(conn, root_id)
    monkeypatch.setenv("FIRELENS_EXPORT_DIR", str(tmp_path / "export-all"))
    with TestClient(create_app()) as client:
        base = f"/api/quality/{root_id}"
        page = client.get(base)
        assert page.status_code == 200
        assert page.json()["total"] == 46
        assert len(page.json()["items"]) == 40
        saved = client.post(base + "/export/save", json={"format": "csv"})
        assert saved.status_code == 200, saved.text
        with Path(saved.json()["path"]).open(encoding="utf-8-sig", newline="") as handle:
            records = list(csv.reader(handle))
        assert len(records) >= 47  # header and at least one row for each of 46 devices
        assert any("致-99-044" in row for row in records)


def test_quality_gallery_organizer_filename_suggestions_and_multi_slot(tmp_path, monkeypatch):
    from backend.app.scanner import scan_root

    db_path, root_id, folder = _setup(tmp_path, monkeypatch)
    _image(folder / "編輯.jpg")
    _image(folder / "編號-1.jpg")
    _image(folder / "完成.jpg")
    with connect(db_path) as conn:
        scan_root(conn, root_id)
        result = gallery(conn, root_id, problem_only=True)
        assert result["total"] == 1
        item = result["items"][0]
        assert "編號" in item["duplicate_slots"]
        assert not item["missing_slots"]
        dirty = next(p for p in item["photos"] if p["filename"] == "編輯.jpg")
        assert dirty["suggested_filename"] == "編號.jpg"
        assert dirty["filename_issue"]
        assert gallery(conn, root_id, status_filter="dirty_name")["total"] == 1
        assert gallery(conn, root_id, status_filter="multi_slot")["total"] == 1
        csv_content, _ = export_quality(result["items"], "csv")
        assert "建議檔名：編號.jpg" in csv_content.decode("utf-8-sig")
        assert "同槽多圖" in csv_content.decode("utf-8-sig")
        assert conn.execute("SELECT COUNT(*) FROM item_issue").fetchone()[0] == 0


def test_special_periods_are_exempt_but_selectable(tmp_path, monkeypatch):
    from backend.app.reconcile import SPECIAL_PERIODS
    from backend.app.scanner import scan_root

    db_path, root_id, ordinary = _setup(tmp_path, monkeypatch)
    root = ordinary.parents[4]
    for index, period in enumerate(sorted(SPECIAL_PERIODS)):
        folder = root / "滅火器" / "2026年" / period / "致德樓8F" / f"特-{index}-01"
        _image(folder / "未分類.jpg")
        _image(folder / "編號.jpg")
        _image(folder / "編號-1.jpg")
    with connect(db_path) as conn:
        scan_root(conn, root_id)
        specials = gallery(conn, root_id, status_filter="special")
        assert specials["total"] == len(SPECIAL_PERIODS)
        for item in specials["items"]:
            assert item["special"]
            assert item["slots"] == ["特例照片"]
            assert item["missing_slots"] == []
            assert item["duplicate_slots"] == []
            assert all(p["display_slot"] == "特例照片" for p in item["photos"])
            assert all(not p["filename_issue"] and not p["multi_slot"] for p in item["photos"])
        # Special classification alone does not flag images in the default problem-only view.
        assert all(not item["special"] for item in gallery(conn, root_id)["items"])
        assert gallery(conn, root_id, status_filter="missing")["total"] == 1
        assert gallery(conn, root_id, status_filter="multi_slot")["total"] == 0


def test_variant_name_filter_export_and_preserved_source(tmp_path, monkeypatch):
    from backend.app.scanner import scan_root

    db_path, root_id, ordinary = _setup(tmp_path, monkeypatch)
    root = ordinary.parents[4]
    variant_folder = root / "滅火器" / "2026年" / "10月份更換" / "致徳樓8F" / "致-08-90"
    _image(variant_folder / "編號.jpg")
    _image(variant_folder / "藥劑.jpg")
    _image(variant_folder / "完成.jpg")
    before = {p: p.read_bytes() for p in variant_folder.iterdir()}
    with connect(db_path) as conn:
        scan_root(conn, root_id)
        filtered = gallery(conn, root_id, status_filter="variant_name")
        assert filtered["total"] == 1
        item = filtered["items"][0]
        assert item["name_variants"][0]["suggestion"] == "致德樓8F"
        assert not item["missing_slots"]
        csv_data, _ = export_quality(filtered["items"], "csv")
        assert "棟別異體字" in csv_data.decode("utf-8-sig")
        assert "致德樓8F" in csv_data.decode("utf-8-sig")
        xlsx_data, _ = export_quality(filtered["items"], "xlsx")
        assert load_workbook(io.BytesIO(xlsx_data), read_only=True).active.max_row >= 2
        assert conn.execute("SELECT COUNT(*) FROM item_issue").fetchone()[0] == 0
    assert {p: p.read_bytes() for p in variant_folder.iterdir()} == before


def test_one_hundred_then_three_changed_photo_incremental(tmp_path, monkeypatch):
    from PIL import Image

    data_dir = tmp_path / "data"
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(data_dir))
    db_path = initialize_database()
    root = tmp_path / "photos"
    folder = root / "滅火器" / "2026年" / "10月份更換" / "致德樓8F" / "致-08-66"
    folder.mkdir(parents=True)
    for index in range(100):
        Image.new("RGB", (160, 120), (index * 3 % 255, 120, 55)).save(
            folder / f"編號-{index:03d}.jpg"
        )
    rid = add_root_and_scan(db_path, root)
    first = _job()
    _run(rid, "", "", first)
    assert first["total"] == first["analyzed"] == 100, first["error"]
    second = _job()
    _run(rid, "", "", second)
    assert second["analyzed"] == 0 and second["cached"] == 100

    changed = folder / "編號-004.jpg"
    old_ns = changed.stat().st_mtime_ns
    Image.new("RGB", (160, 120), (255, 0, 0)).save(changed)
    os.utime(changed, ns=(old_ns + 3_000_000_000, old_ns + 3_000_000_000))
    for index in (100, 101):
        Image.new("RGB", (160, 120), (20, 255, 100)).save(folder / f"編號-{index:03d}.jpg")
    third = _job()
    _run(rid, "", "", third)
    assert third["total"] == 102
    assert third["analyzed"] == 3
    assert third["cached"] == 99
    fourth = _job()
    fourth["full"] = True
    _run(rid, "", "", fourth)
    assert fourth["analyzed"] == 102 and fourth["cached"] == 0


def test_sensitivity_change_invalidates_old_photo_scores(tmp_path, monkeypatch):
    from backend.app.photo_quality import save_sensitivity

    db_path, root_id, folder = _setup(tmp_path, monkeypatch)
    first = _job()
    _run(root_id, "", "", first)
    assert first["analyzed"] == 2
    with connect(db_path) as conn:
        assert save_sensitivity(conn, root_id, 1.4)["sensitivity"] == 1.4
        stale = gallery(conn, root_id, problem_only=False)
        assert all(photo["stale"] for photo in stale["items"][0]["photos"])
        assert all(photo["status"] == "unscanned" for photo in stale["items"][0]["photos"])
    second = _job()
    _run(root_id, "", "", second)
    assert second["analyzed"] == 2 and second["cached"] == 0
    with connect(db_path) as conn:
        assert not any(
            photo["stale"]
            for photo in gallery(
                conn,
                root_id,
                problem_only=False,
            )["items"][0]["photos"]
        )


def test_blur_dark_exposure_and_low_resolution_are_conservative(tmp_path):
    from PIL import ImageFilter

    sharp = tmp_path / "sharp.png"
    blurred = tmp_path / "blurred.png"
    dark = tmp_path / "dark.png"
    bright = tmp_path / "bright.png"
    tiny = tmp_path / "tiny.png"
    _image(sharp)
    with Image.open(sharp) as original:
        original.filter(ImageFilter.GaussianBlur(radius=4)).save(blurred)
    Image.new("RGB", (800, 640), (2, 2, 2)).save(dark)
    Image.new("RGB", (800, 640), (252, 252, 252)).save(bright)
    Image.new("RGB", (320, 240), (120, 120, 120)).save(tiny)
    old_bytes = {path: path.read_bytes() for path in (sharp, blurred, dark, bright, tiny)}
    focused = quality_score(sharp, "extinguisher", "編號")
    soft = quality_score(blurred, "extinguisher", "編號")
    assert focused["score"] > soft["score"]
    assert "dark" in quality_score(dark, "lamp", "後")["issues"]
    assert "bright" in quality_score(bright, "box", "前")["issues"]
    assert "resolution" in quality_score(tiny, "extinguisher", "編號")["issues"]
    assert all(path.read_bytes() == content for path, content in old_bytes.items())


def test_legacy_box_does_not_create_false_missing_photo_slots(
    db_path: Path,
    sample_source: Path,
):
    rid = add_root_and_scan(db_path, sample_source)
    with connect(db_path) as conn:
        legacy = gallery(conn, rid, category="box", problem_only=False)
        assert legacy["total"] > 0
        old_style = next(item for item in legacy["items"] if item["category"] == "box")
        assert old_style["missing_slots"] == []
        assert old_style["slots"] == ["舊制照片"]
        assert all(p["display_slot"] == "舊制照片" for p in old_style["photos"])

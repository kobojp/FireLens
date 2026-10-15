from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from backend.app import scan_jobs
from backend.app.db import connect, initialize_database
from backend.app.scan_jobs import (
    ScanAlreadyRunning,
    cancel_scan_job,
    scan_job_status,
    start_scan_job,
)
from backend.app.scanner import ScanCancelled, ScanSummary, scan_root
from backend.app.settings import get_settings, save_settings


def _add_root(conn, source: Path) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO root(label, path, is_cloud_stream) VALUES ('M8', ?, 1)",
            (str(source),),
        )
    return int(cursor.lastrowid)


def test_incremental_scan_preserves_unchanged_ids_hashes_and_thumbnail(
    db_path: Path, sample_source: Path
) -> None:
    conn = connect(db_path)
    try:
        root_id = _add_root(conn, sample_source)
        first = scan_root(conn, root_id)
        item = conn.execute(
            "SELECT id FROM item WHERE root_id=? AND code='中-01-01'", (root_id,)
        ).fetchone()
        assert item is not None
        item_id = int(item["id"])
        photo = conn.execute(
            "SELECT id FROM photo WHERE item_id=? AND filename='編號.JPG'", (item_id,)
        ).fetchone()
        assert photo is not None
        photo_id = int(photo["id"])
        with conn:
            conn.execute(
                "UPDATE photo SET sha256='keep-me', thumbnail_path='thumb-cache.jpg' WHERE id=?",
                (photo_id,),
            )

        second = scan_root(conn, root_id)
        same_item = conn.execute("SELECT id FROM item WHERE id=?", (item_id,)).fetchone()
        same_photo = conn.execute(
            "SELECT id, sha256, thumbnail_path FROM photo WHERE id=?", (photo_id,)
        ).fetchone()
    finally:
        conn.close()

    assert first.items == second.items == 4
    assert second.added_items == 0
    assert second.updated_items == 0
    assert second.removed_items == 0
    assert second.added_photos == 0
    assert second.updated_photos == 0
    assert second.removed_photos == 0
    assert same_item is not None and same_item["id"] == item_id
    assert same_photo is not None and same_photo["id"] == photo_id
    assert same_photo["sha256"] == "keep-me"
    assert same_photo["thumbnail_path"] == "thumb-cache.jpg"


def test_incremental_scan_reflects_external_add_delete_and_photo_rename(
    db_path: Path, sample_source: Path
) -> None:
    conn = connect(db_path)
    try:
        root_id = _add_root(conn, sample_source)
        scan_root(conn, root_id)
        stable_item_id = int(
            conn.execute(
                "SELECT id FROM item WHERE root_id=? AND code='中-01-01'", (root_id,)
            ).fetchone()[0]
        )
        stable_photo_id = int(
            conn.execute(
                "SELECT id FROM photo WHERE item_id=? AND filename='編號.JPG'", (stable_item_id,)
            ).fetchone()[0]
        )
        with conn:
            conn.execute("UPDATE photo SET sha256='stable-sha' WHERE id=?", (stable_photo_id,))

        old_empty = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"
        old_empty.rmdir()
        new_item = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-03"
        new_item.mkdir()
        (new_item / "編號.jpg").write_bytes(b"new-number")
        original_done = (
            sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01" / "完成.jpg"
        )
        original_done.rename(original_done.with_name("完成改名.jpg"))

        summary = scan_root(conn, root_id)
        stable_item = conn.execute(
            "SELECT id, status FROM item WHERE id=?", (stable_item_id,)
        ).fetchone()
        stable_photo = conn.execute(
            "SELECT id, sha256 FROM photo WHERE id=?", (stable_photo_id,)
        ).fetchone()
        codes = {
            row["code"] for row in conn.execute("SELECT code FROM item WHERE root_id=?", (root_id,))
        }
        renamed = conn.execute(
            "SELECT filename FROM photo WHERE item_id=? AND filename='完成改名.jpg'",
            (stable_item_id,),
        ).fetchone()
    finally:
        conn.close()

    assert summary.added_items == 1
    assert summary.removed_items == 1
    assert summary.updated_items >= 1
    assert summary.added_photos == 2
    assert summary.removed_photos == 1
    assert "中-01-02" not in codes and "中-01-03" in codes
    assert stable_item is not None and stable_item["id"] == stable_item_id
    assert stable_item["status"] == "partial"
    assert stable_photo is not None and stable_photo["id"] == stable_photo_id
    assert stable_photo["sha256"] == "stable-sha"
    assert renamed is not None


def test_offline_scan_keeps_cached_index(db_path: Path, sample_source: Path) -> None:
    conn = connect(db_path)
    root_id = _add_root(conn, sample_source)
    try:
        scan_root(conn, root_id)
        before = (
            conn.execute("SELECT COUNT(*) FROM item WHERE root_id=?", (root_id,)).fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM photo p JOIN item i ON i.id=p.item_id WHERE i.root_id=?",
                (root_id,),
            ).fetchone()[0],
        )
        offline = sample_source.with_name("source-offline")
        sample_source.rename(offline)
        with pytest.raises(FileNotFoundError, match="根目錄不存在或無法讀取"):
            scan_root(conn, root_id)
        after = (
            conn.execute("SELECT COUNT(*) FROM item WHERE root_id=?", (root_id,)).fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM photo p JOIN item i ON i.id=p.item_id WHERE i.root_id=?",
                (root_id,),
            ).fetchone()[0],
        )
    finally:
        conn.close()
    assert before == after == (4, 7)


def test_cancelled_scan_does_not_apply_new_snapshot(db_path: Path, sample_source: Path) -> None:
    conn = connect(db_path)
    try:
        root_id = _add_root(conn, sample_source)
        scan_root(conn, root_id)
        new_item = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-99"
        new_item.mkdir()
        with pytest.raises(ScanCancelled):
            scan_root(conn, root_id, cancel_check=lambda: True)
        count = int(
            conn.execute("SELECT COUNT(*) FROM item WHERE root_id=?", (root_id,)).fetchone()[0]
        )
    finally:
        conn.close()
    assert count == 4


def test_scan_job_allows_only_one_job_per_root_and_can_cancel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(data_dir))
    db_path = initialize_database(data_dir / "firelens.sqlite3")
    root = tmp_path / "photos"
    root.mkdir()
    conn = connect(db_path)
    try:
        root_id = _add_root(conn, root)
    finally:
        conn.close()

    started = threading.Event()

    def blocking_scan(conn, root_id: int, *, cancel_check=None) -> ScanSummary:
        started.set()
        while cancel_check is None or not cancel_check():
            time.sleep(0.01)
        raise ScanCancelled("掃描已取消")

    monkeypatch.setattr(scan_jobs, "scan_root", blocking_scan)
    started_job = start_scan_job(root_id)
    assert started_job["state"] == "running"
    assert started.wait(timeout=1)
    with pytest.raises(ScanAlreadyRunning, match="掃描進行中"):
        start_scan_job(root_id)
    cancel_scan_job(root_id)

    deadline = time.monotonic() + 2
    status = scan_job_status(root_id)
    while status["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
        status = scan_job_status(root_id)
    assert status["state"] == "cancelled"


def test_auto_scan_and_new_item_panel_settings_persist(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        defaults = get_settings(conn)
        assert defaults["auto_scan_on_start"] is True
        assert defaults["auto_scan_min_interval_minutes"] == 5
        assert defaults["new_item_panel_open"] is True
        save_settings(
            conn,
            {
                "auto_scan_on_start": False,
                "auto_scan_min_interval_minutes": 30,
                "new_item_panel_open": False,
            },
        )
        conn.close()
        conn = connect(db_path)
        persisted = get_settings(conn)
    finally:
        conn.close()
    assert persisted["auto_scan_on_start"] is False
    assert persisted["auto_scan_min_interval_minutes"] == 30
    assert persisted["new_item_panel_open"] is False


def test_v5_to_v6_migration_backs_up_before_adding_incremental_scan_column(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy" / "firelens.sqlite3"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE category (
                id INTEGER PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL UNIQUE,
                slots_json TEXT NOT NULL DEFAULT '[]',
                filename_aliases_json TEXT NOT NULL DEFAULT '{}',
                item_regex TEXT
            );
            CREATE TABLE item (
                id INTEGER PRIMARY KEY,
                root_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                year TEXT NOT NULL,
                period TEXT NOT NULL,
                building TEXT NOT NULL,
                code TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unknown',
                photo_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE setting (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO setting(key, value_json) VALUES ('theme', '"dark"');
            PRAGMA user_version = 5;
            """
        )
        conn.commit()
    finally:
        conn.close()

    initialize_database(db_path)
    backup = db_path.with_suffix(db_path.suffix + ".backup-v5")
    upgraded = connect(db_path)
    try:
        columns = {row[1] for row in upgraded.execute("PRAGMA table_info(item)")}
        theme = upgraded.execute("SELECT value_json FROM setting WHERE key='theme'").fetchone()[0]
        version = upgraded.execute("PRAGMA user_version").fetchone()[0]
    finally:
        upgraded.close()

    assert backup.is_file()
    assert "dir_mtime_ns" in columns
    assert theme == '"dark"'
    assert version == 6

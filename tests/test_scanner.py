from __future__ import annotations

from pathlib import Path

from backend.app.db import connect
from backend.app.scanner import scan_root


def file_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {
        path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def add_root(db_path: Path, source: Path) -> int:
    conn = connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO root(label, path, is_cloud_stream) VALUES (?, ?, 0)",
                ("sample", str(source)),
            )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)
    finally:
        conn.close()


def test_scanner_handles_realistic_shapes_without_touching_source(
    db_path: Path, sample_source: Path
) -> None:
    before = file_snapshot(sample_source)
    root_id = add_root(db_path, sample_source)

    conn = connect(db_path)
    try:
        summary = scan_root(conn, root_id)
        items = conn.execute(
            """
            SELECT c.code AS category, i.code, i.building, i.status, i.photo_count
            FROM item AS i JOIN category AS c ON c.id = i.category_id
            WHERE i.root_id = ? ORDER BY c.code, i.code
            """,
            (root_id,),
        ).fetchall()
        photos = conn.execute(
            "SELECT filename, extension, slot FROM photo ORDER BY filename"
        ).fetchall()
    finally:
        conn.close()

    after = file_snapshot(sample_source)

    assert before == after
    assert summary.items == 4
    assert summary.photos == 7
    assert summary.categories == {"extinguisher": 2, "box": 1, "lamp": 1}

    indexed = {(row["category"], row["code"]): row for row in items}
    assert indexed[("extinguisher", "中-01-01")]["status"] == "complete"
    assert indexed[("extinguisher", "中-01-01")]["photo_count"] == 3
    assert indexed[("extinguisher", "中-01-02")]["status"] == "empty"
    assert indexed[("box", "中-02-C124")]["status"] == "legacy"
    assert indexed[("lamp", "D-05-04")]["building"] == "立體停車場 / 立體5樓"

    photo_names = {row["filename"] for row in photos}
    assert "desktop.ini" not in photo_names
    assert "編號.JPG" in photo_names
    effective_date = next(row for row in photos if row["filename"] == "有效日期.jpg")
    assert effective_date["slot"] == "藥劑"
    upper_png = next(row for row in photos if row["filename"] == "2.PNG")
    assert upper_png["extension"] == ".png"


def test_rescan_rebuilds_only_indexes_and_keeps_settings(
    db_path: Path, sample_source: Path
) -> None:
    root_id = add_root(db_path, sample_source)
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("INSERT INTO setting(key, value_json) VALUES ('theme', '\"light\"')")
        first = scan_root(conn, root_id)
        second = scan_root(conn, root_id)
        setting = conn.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone()
        item_count = conn.execute(
            "SELECT COUNT(*) FROM item WHERE root_id = ?", (root_id,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert first.items == second.items == item_count == 4
    assert setting is not None and setting[0] == '"light"'


def test_scan_index_survives_database_reopen(db_path: Path, sample_source: Path) -> None:
    root_id = add_root(db_path, sample_source)
    conn = connect(db_path)
    try:
        scan_root(conn, root_id)
    finally:
        conn.close()

    reopened = connect(db_path)
    try:
        root = reopened.execute("SELECT label FROM root WHERE id = ?", (root_id,)).fetchone()
        item_count = reopened.execute(
            "SELECT COUNT(*) FROM item WHERE root_id = ?", (root_id,)
        ).fetchone()[0]
        photo_count = reopened.execute(
            """
            SELECT COUNT(*) FROM photo
            WHERE item_id IN (SELECT id FROM item WHERE root_id = ?)
            """,
            (root_id,),
        ).fetchone()[0]
    finally:
        reopened.close()

    assert root is not None and root[0] == "sample"
    assert item_count == 4
    assert photo_count == 7

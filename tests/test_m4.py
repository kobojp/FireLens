from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import organizer
from backend.app.db import connect
from backend.app.main import create_app
from backend.app.scanner import scan_root


def add_item(root: Path, period: str, building: str, code: str, files: dict[str, bytes]) -> Path:
    path = root / "滅火器" / "2026年" / period / building / code
    path.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (path / name).write_bytes(content)
    return path


def setup_index(conn, root: Path) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO root(label, path, is_cloud_stream) VALUES ('M4', ?, 0)",
            (str(root.resolve()),),
        )
    root_id = int(cursor.lastrowid)
    scan_root(conn, root_id)
    return root_id


def prepare_m4_source(sample_source: Path) -> None:
    add_item(
        sample_source,
        "8月份更換",
        "中正樓",
        "中-01-01",
        {"完成.jpg": b"other-month"},
    )
    add_item(
        sample_source,
        "9月份更換",
        "中正樓",
        "中-01-010",
        {"完成.jpg": b"near"},
    )
    add_item(
        sample_source,
        "9月份更換",
        "中正樓",
        "中-01-03",
        {"完成.jpg": b"done", "完成..jpg": b"dirty-second", "12345.jpg": b"unknown-dirty"},
    )
    add_item(
        sample_source,
        "9月份更換",
        "中正樓",
        "中-01-04",
        {"編輯.jpg": b"edit", "編號.jpg": b"existing"},
    )
    add_item(
        sample_source,
        "9月份更換",
        "致徳樓",
        "致-01-01",
        {"完成.jpg": b"variant"},
    )


def find_candidate(analysis: dict[str, object], source_name: str) -> dict[str, object]:
    rows = analysis["rename_candidates"]
    assert isinstance(rows, list)
    return next(row for row in rows if row["source_name"] == source_name)


def exact_filenames(path: Path) -> set[str]:
    return {entry.name for entry in path.iterdir() if entry.is_file()}


def test_analysis_detects_dirty_duplicate_near_and_variant(
    db_path: Path, sample_source: Path
) -> None:
    prepare_m4_source(sample_source)
    conn = connect(db_path)
    try:
        root_id = setup_index(conn, sample_source)
        result = organizer.analyze_root(conn, root_id)

        upper = find_candidate(result, "編號.JPG")
        assert upper["target_name"] == "編號.jpg"
        assert upper["safe"] is True

        collision = find_candidate(result, "編輯.jpg")
        assert collision["target_name"] == "編號.jpg"
        assert collision["safe"] is False
        assert "存在" in str(collision["blocked_reason"])

        unknown = next(row for row in result["dirty_files"] if row["source_name"] == "12345.jpg")
        assert unknown["candidate_id"] is None
        assert unknown["target_name"] is None
        assert "人工確認" in str(unknown["blocked_reason"])

        duplicate_groups = result["duplicate_photos"]
        assert any(
            {photo["code"] for photo in group["photos"]} >= {"中-01-01", "中-01-03"}
            for group in duplicate_groups
        )
        assert any(row["code"] == "中-01-01" for row in result["duplicate_codes"])
        assert any(
            {row["first"], row["second"]} == {"中-01-01", "中-01-010"}
            for row in result["near_codes"]
        )
        assert any(
            issue["value"] == "致徳樓" and issue["suggestion"] == "致德樓"
            for issue in result["variant_issues"]
        )
    finally:
        conn.close()


def test_selected_only_rename_logs_and_undo(db_path: Path, sample_source: Path) -> None:
    prepare_m4_source(sample_source)
    conn = connect(db_path)
    try:
        root_id = setup_index(conn, sample_source)
        analysis = organizer.analyze_root(conn, root_id)
        first = find_candidate(analysis, "編號.JPG")
        second = find_candidate(analysis, "完成..jpg")

        result = organizer.execute_renames(conn, root_id, [str(first["candidate_id"])])
        assert len(result["executed"]) == 1
        assert result["failed"] == []
        item_dir = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
        assert "編號.JPG" not in exact_filenames(item_dir)
        assert (item_dir / "編號.jpg").read_bytes() == b"number"

        second_path = sample_source / Path(str(second["source_relative"]))
        assert second_path.exists()

        log = conn.execute(
            "SELECT id, source_path, target_path, sha256, reverted_at, root_id FROM rename_log"
        ).fetchone()
        assert log is not None
        assert log["root_id"] == root_id
        assert log["reverted_at"] is None
        actions = [row[0] for row in conn.execute("SELECT action FROM audit_log ORDER BY id")]
        assert "rename_photo" in actions

        undone = organizer.undo_rename(conn, root_id, int(log["id"]))
        assert undone["reverted_at"] is not None
        assert (item_dir / "編號.JPG").read_bytes() == b"number"
        assert "編號.jpg" not in exact_filenames(item_dir)
        actions = [row[0] for row in conn.execute("SELECT action FROM audit_log ORDER BY id")]
        assert actions[-1] == "undo_rename"
    finally:
        conn.close()


def test_rename_rolls_back_when_logging_fails(
    monkeypatch, db_path: Path, sample_source: Path
) -> None:
    conn = connect(db_path)
    try:
        root_id = setup_index(conn, sample_source)
        analysis = organizer.analyze_root(conn, root_id)
        candidate = find_candidate(analysis, "編號.JPG")
        item_dir = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"

        def fail_record(*_args, **_kwargs):
            raise RuntimeError("simulated rename log failure")

        monkeypatch.setattr(organizer, "_record_rename", fail_record)
        result = organizer.execute_renames(conn, root_id, [str(candidate["candidate_id"])])
        assert len(result["failed"]) == 1
        assert (item_dir / "編號.JPG").read_bytes() == b"number"
        assert "編號.jpg" not in exact_filenames(item_dir)
        assert conn.execute("SELECT COUNT(*) FROM rename_log").fetchone()[0] == 0
    finally:
        conn.close()


def test_undo_requires_matching_sha_and_no_collision(db_path: Path, sample_source: Path) -> None:
    conn = connect(db_path)
    try:
        root_id = setup_index(conn, sample_source)
        candidate = find_candidate(organizer.analyze_root(conn, root_id), "編號.JPG")
        result = organizer.execute_renames(conn, root_id, [str(candidate["candidate_id"])])
        log_id = int(result["executed"][0]["rename_log_id"])
        item_dir = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
        target = item_dir / "編號.jpg"
        target.write_bytes(b"changed-after-rename")
        with pytest.raises(organizer.OrganizerConflict, match="SHA-256"):
            organizer.undo_rename(conn, root_id, log_id)
        assert target.read_bytes() == b"changed-after-rename"

        # A case-insensitive Windows filesystem cannot contain 編號.JPG and
        # 編號.jpg as two distinct files, so this collision state is only
        # representable on case-sensitive filesystems.
        if os.name != "nt":
            target.write_bytes(b"number")
            (item_dir / "編號.JPG").write_bytes(b"new-file")
            with pytest.raises(organizer.OrganizerConflict, match="已存在"):
                organizer.undo_rename(conn, root_id, log_id)
            assert (item_dir / "編號.JPG").read_bytes() == b"new-file"
            assert target.read_bytes() == b"number"
    finally:
        conn.close()


def test_api_preview_execute_history_and_undo(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as client:
        root = client.post("/api/roots", json={"path": str(sample_source), "label": "M4 API"})
        assert root.status_code == 201
        root_id = int(root.json()["id"])
        assert client.post(f"/api/roots/{root_id}/scan").status_code == 200

        analysis = client.get(f"/api/organizer/{root_id}")
        assert analysis.status_code == 200
        candidate = next(
            row for row in analysis.json()["rename_candidates"] if row["source_name"] == "編號.JPG"
        )
        preview = client.post(
            f"/api/organizer/{root_id}/rename/preview",
            json={"candidate_ids": [candidate["candidate_id"]]},
        )
        assert preview.status_code == 200
        assert preview.json()["safe_count"] == 1

        executed = client.post(
            f"/api/organizer/{root_id}/rename",
            json={"candidate_ids": [candidate["candidate_id"]]},
        )
        assert executed.status_code == 200
        log_id = executed.json()["executed"][0]["rename_log_id"]
        history = client.get(f"/api/organizer/{root_id}/history")
        assert history.status_code == 200
        assert history.json()[0]["id"] == log_id
        undone = client.post(f"/api/organizer/{root_id}/undo/{log_id}")
        assert undone.status_code == 200
        assert undone.json()["reverted_at"] is not None

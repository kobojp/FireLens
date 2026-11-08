"""Two-client Google Drive Desktop folder sync, with entirely synthetic data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app import shared_issues as sync
from backend.app.db import connect, initialize_database
from backend.app.issues import set_item_issue, update_label


def _client(tmp_path: Path, shared_root: Path, name: str, monkeypatch):
    data_dir = tmp_path / name
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(data_dir))
    db_path = data_dir / "state.sqlite3"
    initialize_database(db_path)
    conn = connect(db_path)
    with conn:
        root_id = conn.execute(
            "INSERT INTO root(label,path,is_cloud_stream) VALUES (?,?,1)",
            (name, str(shared_root)),
        ).lastrowid
        cat_id = conn.execute("SELECT id FROM category WHERE code='extinguisher'").fetchone()[0]
        item_id = conn.execute(
            """INSERT INTO item(root_id,category_id,year,period,building,code,relative_path)
            VALUES (?,?,?,?,?,?,?)""",
            (
                root_id,
                cat_id,
                "2026年",
                "11月份更換",
                "致德樓8F",
                "致-08-66",
                "滅火器/2026年/11月份更換/致德樓8F/致-08-66",
            ),
        ).lastrowid
    return data_dir, conn, int(root_id), int(item_id)


def _as(monkeypatch, path: Path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(path))


def _labels(conn):
    return [
        dict(row)
        for row in conn.execute("SELECT id,name,sort_order,active FROM issue_label ORDER BY id")
    ]


def _existing_label(conn, name: str) -> dict:
    row = conn.execute(
        "SELECT id,name,sort_order,active FROM issue_label WHERE name=?",
        (name,),
    ).fetchone()
    assert row is not None, name
    return dict(row)


def _issue_label(conn, root_id):
    row = conn.execute("SELECT label_id FROM item_issue WHERE root_id=?", (root_id,)).fetchone()
    return int(row[0]) if row else None


def test_two_windows_clients_merge_and_manual_conflict_resolution(tmp_path, monkeypatch):
    folder = tmp_path / "shared-google-drive" / "滅火器更換照片"
    folder.mkdir(parents=True)
    a_dir, a, ar, ai = _client(tmp_path, folder, "pc-a", monkeypatch)
    b_dir, b, br, bi = _client(tmp_path, folder, "pc-b", monkeypatch)
    try:
        _as(monkeypatch, a_dir)
        first = _existing_label(a, "瓶身超過10年")
        other = _existing_label(a, "壓力錶故障")
        assert sync.configure(a, ar, True)["enabled"]
        result = sync.synchronize(a, ar)
        assert result["verified_events"] >= 2

        _as(monkeypatch, b_dir)
        assert sync.configure(b, br, True)["enabled"]
        result = sync.synchronize(b, br)
        assert not result["conflicts"]
        assert {row["name"] for row in _labels(b)} >= {"瓶身超過10年", "壓力錶故障"}

        _as(monkeypatch, a_dir)
        set_item_issue(a, ai, int(first["id"]))
        sync.record_item(a, ai, int(first["id"]))
        assert sync.synchronize(a, ar)["applied"] >= 1
        _as(monkeypatch, b_dir)
        sync.synchronize(b, br)
        assert _issue_label(b, br) is not None
        label = b.execute(
            "SELECT name FROM issue_label WHERE id=?", (_issue_label(b, br),)
        ).fetchone()
        assert label[0] == "瓶身超過10年"

        # A and B both edit the same issue based on the same previous event.
        _as(monkeypatch, a_dir)
        set_item_issue(a, ai, int(other["id"]))
        sync.record_item(a, ai, int(other["id"]))
        _as(monkeypatch, b_dir)
        set_item_issue(b, bi, None)
        sync.record_item(b, bi, None)
        sync.synchronize(b, br)
        _as(monkeypatch, a_dir)
        result = sync.synchronize(a, ar)
        assert len(result["conflicts"]) == 1
        assert _issue_label(a, ar) == int(other["id"])  # no silent remote overwrite

        # The user explicitly chooses B's clear, creating a causal merge event.
        conflict = result["conflicts"][0]
        clear_candidate = next(
            c for c in conflict["candidates"] if c["value"]["label_guid"] is None
        )
        result = sync.resolve(a, ar, conflict["key"], clear_candidate["event_id"])
        assert not result["conflicts"]
        assert _issue_label(a, ar) is None
        _as(monkeypatch, b_dir)
        sync.synchronize(b, br)
        assert _issue_label(b, br) is None

        # Local backup(s) exist and contain verifiable data.
        _as(monkeypatch, a_dir)
        history = sync.backups(a, ar)
        assert history and all(i["items"] >= 0 for i in history)
        preview = sync.backup_preview(a, ar, history[0]["id"])
        assert preview["id"] == history[0]["id"]
    finally:
        a.close()
        b.close()


def test_offline_and_cloud_deleted_event_never_wipes_local(tmp_path, monkeypatch):
    folder = tmp_path / "drive"
    folder.mkdir()
    a_dir, a, root_id, item_id = _client(tmp_path, folder, "pc-a", monkeypatch)
    try:
        _as(monkeypatch, a_dir)
        label = _existing_label(a, "無法辨識")
        sync.configure(a, root_id, True)
        set_item_issue(a, item_id, int(label["id"]))
        sync.record_item(a, item_id, int(label["id"]))
        sync.synchronize(a, root_id)
        original = _issue_label(a, root_id)
        events = folder / "FireLens-共享異常資料" / "events"
        missing = next(events.glob("*.json"))
        missing.unlink()
        with pytest.raises(sync.SyncError, match="缺少"):
            sync.synchronize(a, root_id)
        assert _issue_label(a, root_id) == original
        repaired = sync.recover_missing_shared_events(a, root_id, confirm=True)
        assert repaired["restored"] == 1
        sync.synchronize(a, root_id)

        renamed = folder.with_name("drive-offline")
        folder.rename(renamed)
        with pytest.raises(sync.SyncError, match="離線"):
            sync.synchronize(a, root_id)
        assert _issue_label(a, root_id) == original
    finally:
        a.close()


def test_corrupt_shared_json_rejected_and_local_backups_restore(tmp_path, monkeypatch):
    folder = tmp_path / "drive"
    folder.mkdir()
    data_dir, conn, root, item = _client(tmp_path, folder, "pc1", monkeypatch)
    try:
        _as(monkeypatch, data_dir)
        label = _existing_label(conn, "瓶身超過10年")
        sync.configure(conn, root, True)
        sync.synchronize(conn, root)
        set_item_issue(conn, item, int(label["id"]))
        sync.record_item(conn, item, int(label["id"]))
        sync.synchronize(conn, root)
        history = sync.backups(conn, root)
        assert history
        result = sync.restore(conn, root, history[0]["id"], confirm=True)
        assert result["restored_locally"]
        assert sync.status(conn, root)["manual_review"]
        with pytest.raises(sync.SyncError, match="需確認"):
            sync.synchronize(conn, root)
        sync.resume_after_restore(conn, root, True)

        events = folder / "FireLens-共享異常資料" / "events"
        latest = next(events.glob("*.json"))
        payload = json.loads(latest.read_text(encoding="utf-8"))
        payload["value"] = {"malicious": "bad"}
        latest.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(sync.SyncError, match="完整性"):
            sync.synchronize(conn, root)
    finally:
        conn.close()


def test_offline_change_replays_with_previous_verified_lineage(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    data_dir, conn, root_id, item_id = _client(tmp_path, shared, "pc-offline", monkeypatch)
    try:
        _as(monkeypatch, data_dir)
        sync.configure(conn, root_id, True)
        sync.synchronize(conn, root_id)
        label = _existing_label(conn, "無法辨識")
        set_item_issue(conn, item_id, label["id"])
        sync.record_item(conn, item_id, label["id"])
        sync.synchronize(conn, root_id)
        assert sync.status(conn, root_id)["pending"] == 0

        # The Drive root vanishes, local edits must be journaled in local outbox.
        offline = tmp_path / "temporarily-offline"
        shared.rename(offline)
        set_item_issue(conn, item_id, None)
        sync.record_item(conn, item_id, None)
        assert sync.status(conn, root_id)["pending"] == 1
        assert _issue_label(conn, root_id) is None
        with pytest.raises(sync.SyncError, match="離線"):
            sync.synchronize(conn, root_id)

        offline.rename(shared)
        merged = sync.synchronize(conn, root_id)
        assert merged["pending"] == 0
        assert merged["conflicts"] == []
        assert _issue_label(conn, root_id) is None
    finally:
        conn.close()


def test_label_name_change_propagates_across_separate_sqlite_ids(tmp_path, monkeypatch):
    shared = tmp_path / "drive-folder"
    shared.mkdir()
    a_dir, a, ar, _ = _client(tmp_path, shared, "pc-1", monkeypatch)
    b_dir, b, br, _ = _client(tmp_path, shared, "pc-2", monkeypatch)
    try:
        _as(monkeypatch, a_dir)
        sync.configure(a, ar, True)
        sync.synchronize(a, ar)
        _as(monkeypatch, b_dir)
        sync.configure(b, br, True)
        sync.synchronize(b, br)
        _as(monkeypatch, a_dir)
        old = _existing_label(a, "瓶身超過10年")
        update_label(a, old["id"], name="瓶身期限異常")
        sync.record_label(a, old["id"])
        sync.synchronize(a, ar)
        _as(monkeypatch, b_dir)
        response = sync.synchronize(b, br)
        assert response["conflicts"] == []
        assert _existing_label(b, "瓶身期限異常")
    finally:
        a.close()
        b.close()


def test_invalid_remote_parent_and_path_rejected_without_db_mutation(tmp_path, monkeypatch):
    shared = tmp_path / "drive-folder"
    shared.mkdir()
    data_dir, conn, rid, _ = _client(tmp_path, shared, "pc", monkeypatch)
    try:
        _as(monkeypatch, data_dir)
        sync.configure(conn, rid, True)
        sync.synchronize(conn, rid)
        initial = conn.execute("SELECT COUNT(*) FROM item_issue").fetchone()[0]
        event_id = "e" * 32
        event = {
            "v": 1,
            "id": event_id,
            "device": "d" * 32,
            "kind": "issue",
            "key": "issue:box:../outside",
            "value": {"category": "box", "path": "../outside", "code": "BAD", "label_guid": None},
            "parents": ["f" * 32],
            "at": "2026-11-08T00:00:00+00:00",
        }
        sync._safe_event(shared / "FireLens-共享異常資料" / "events" / (event_id + ".json"), event)
        with pytest.raises(sync.SyncError):
            sync.synchronize(conn, rid)
        assert conn.execute("SELECT COUNT(*) FROM item_issue").fetchone()[0] == initial
    finally:
        conn.close()


def test_device_folder_rename_clears_old_shared_path_and_moves_label(tmp_path, monkeypatch):
    folder = tmp_path / "drive-folder"
    folder.mkdir()
    a_dir, a, ar, ai = _client(tmp_path, folder, "pc-a", monkeypatch)
    b_dir, b, br, bi = _client(tmp_path, folder, "pc-b", monkeypatch)
    try:
        _as(monkeypatch, a_dir)
        sync.configure(a, ar, True)
        sync.synchronize(a, ar)
        label = _existing_label(a, "無法辨識")
        set_item_issue(a, ai, label["id"])
        sync.record_item(a, ai, label["id"])
        sync.synchronize(a, ar)
        _as(monkeypatch, b_dir)
        sync.configure(b, br, True)
        sync.synchronize(b, br)
        assert _issue_label(b, br) is not None

        _as(monkeypatch, a_dir)
        old = a.execute("SELECT relative_path,code FROM item WHERE id=?", (ai,)).fetchone()
        new_path = old["relative_path"] + "(需更換)"
        with a:
            a.execute(
                "UPDATE item SET relative_path=?,code=? WHERE id=?",
                (new_path, "致-08-66(需更換)", ai),
            )
            a.execute(
                "UPDATE item_issue SET item_relative_path=?,device_code=? "
                "WHERE root_id=? AND item_relative_path=?",
                (new_path, "致-08-66(需更換)", ar, old["relative_path"]),
            )
        sync.record_renamed_item(a, ai, old["relative_path"], old["code"])
        merged = sync.synchronize(a, ar)
        assert merged["conflicts"] == []
        _as(monkeypatch, b_dir)
        sync.synchronize(b, br)
        items = list(b.execute("SELECT item_relative_path FROM item_issue WHERE root_id=?", (br,)))
        assert [r[0] for r in items] == [new_path]
    finally:
        a.close()
        b.close()


def test_shared_issue_api_endpoints_are_explicit_opt_in(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.config import get_database_path
    from backend.app.main import create_app

    data_dir = tmp_path / "app-data"
    root_path = tmp_path / "drive-root"
    root_path.mkdir()
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(data_dir))
    with TestClient(create_app()) as client:
        db = connect(get_database_path())
        try:
            with db:
                root_id = int(
                    db.execute(
                        "INSERT INTO root(label,path,is_cloud_stream) VALUES (?,?,1)",
                        ("合成共用根目錄", str(root_path)),
                    ).lastrowid
                )
        finally:
            db.close()
        base = f"/api/issues/sync/{root_id}"
        state = client.get(base)
        assert state.status_code == 200
        assert state.json()["enabled"] is False
        assert not (root_path / "FireLens-共享異常資料").exists()
        forbidden = client.post(base + "/run")
        assert forbidden.status_code == 409
        enabled = client.post(base + "/configure", json={"enabled": True})
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["enabled"] is True
        result = client.post(base + "/run")
        assert result.status_code == 200, result.text
        assert result.json()["verified_events"] >= 3
        assert client.get(base + "/backups").status_code == 200
        assert client.get(base + "/conflicts").status_code == 200
        assert client.post(base + "/recover-shared", json={"confirm": False}).status_code == 409
        assert client.get(base + "/backups/../../etc/passwd").status_code in (400, 404)
        disabled = client.post(base + "/configure", json={"enabled": False})
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        assert (root_path / "FireLens-共享異常資料").is_dir()


def test_windows_desktop_ini_is_ignored_but_unknown_files_still_fail(tmp_path, monkeypatch):
    shared = tmp_path / "synced-drive-root"
    shared.mkdir()
    local_dir, conn, root_id, item_id = _client(tmp_path, shared, "pc-windows", monkeypatch)
    try:
        _as(monkeypatch, local_dir)
        sync.configure(conn, root_id, True)
        events = shared / "FireLens-共享異常資料" / "events"
        # Windows metadata is an ordinary system sidecar, NOT an event.
        (events / "desktop.ini").write_text("[.ShellClassInfo]\n", encoding="utf-8")
        result = sync.synchronize(conn, root_id)
        assert result["verified_events"] >= 3
        assert not result["conflicts"]
        assert (events / "desktop.ini").is_file()  # never delete metadata
        assert sync.synchronize(conn, root_id)["conflicts"] == []

        # Names that look like other metadata aren't silently ignored.
        unknown = events / "random.txt"
        unknown.write_text("unrelated", encoding="utf-8")
        with pytest.raises(sync.SyncError, match="非同步資料"):
            sync.synchronize(conn, root_id)
        unknown.unlink()

        invalid = events / ("f" * 32 + ".json")
        invalid.write_text("{}", encoding="utf-8")
        with pytest.raises(sync.SyncError, match="完整性"):
            sync.synchronize(conn, root_id)
    finally:
        conn.close()

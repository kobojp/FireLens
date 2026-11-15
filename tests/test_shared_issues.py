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
    a_dir, a, ar, ai = _client(tmp_path, shared, "pc-1", monkeypatch)
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
        set_item_issue(a, ai, old["id"])
        sync.record_item(a, ai, old["id"])
        sync.synchronize(a, ar)
        _as(monkeypatch, b_dir)
        sync.synchronize(b, br)
        _as(monkeypatch, a_dir)
        update_label(a, old["id"], name="瓶身期限異常")
        sync.record_label(a, old["id"])
        sync.synchronize(a, ar)
        _as(monkeypatch, b_dir)
        response = sync.synchronize(b, br)
        assert response["conflicts"] == []
        assert _existing_label(b, "瓶身期限異常")
        assert response["summary"]["updated"] == 0
        assert response["changes"] == []
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


def test_dynamic_category_journal_uses_version_two_and_merges(tmp_path, monkeypatch):
    import hashlib

    folder = tmp_path / "shared"
    folder.mkdir()
    ad, a, ar, ai = _client(tmp_path, folder, "dynamic-a", monkeypatch)
    bd, b, br, _ = _client(tmp_path, folder, "dynamic-b", monkeypatch)
    code = "folder_" + hashlib.sha256("水帶".encode()).hexdigest()[:24]
    path = "水帶/2026年/11月/F-19-13"
    try:
        with a:
            category = a.execute(
                "INSERT INTO category(code,name,slots_json) VALUES (?,?,?)",
                (code, "水帶", '["前","中","後"]'),
            ).lastrowid
            a.execute(
                "UPDATE item SET category_id=?,relative_path=? WHERE id=?", (category, path, ai)
            )
        _as(monkeypatch, ad)
        label = _existing_label(a, "瓶身超過10年")
        set_item_issue(a, ai, label["id"])
        sync.configure(a, ar, True)
        result = sync.synchronize(a, ar)
        assert not result["conflicts"]
        events = sync._events(folder)
        issue = next(event for event in events.values() if event["kind"] == "issue")
        assert issue["v"] == 2
        _as(monkeypatch, bd)
        sync.configure(b, br, True)
        result = sync.synchronize(b, br)
        assert result["summary"]["added"] == 1
        assert result["changes"][0]["category"] == code
        assert result["changes"][0]["category_name"] == "水帶"
        assert b.execute("SELECT category_code FROM item_issue").fetchone()[0] == code
        issue["v"] = 1
        with pytest.raises(sync.SyncError, match="類別"):
            sync._value(issue)
        issue["v"] = 2
        issue["value"]["category"] = "folder_" + "0" * 24
        with pytest.raises(sync.SyncError, match="類別"):
            sync._value(issue)
    finally:
        a.close()
        b.close()


def test_sync_summary_counts_sqlite_differences_and_noop(tmp_path, monkeypatch):
    folder = tmp_path / "shared"
    folder.mkdir()
    ad, a, ar, ai = _client(tmp_path, folder, "summary-a", monkeypatch)
    bd, b, br, bi = _client(tmp_path, folder, "summary-b", monkeypatch)
    try:
        _as(monkeypatch, ad)
        sync.configure(a, ar, True)
        sync.synchronize(a, ar)
        _as(monkeypatch, bd)
        sync.configure(b, br, True)
        sync.synchronize(b, br)
        label = _existing_label(b, "瓶身超過10年")
        set_item_issue(b, bi, label["id"])
        sync.record_item(b, bi, label["id"])
        # Local journal publication is not a newly added local issue.
        assert sync.synchronize(b, br)["summary"]["added"] == 0
        _as(monkeypatch, ad)
        first = sync.synchronize(a, ar)
        assert first["summary"] == {"added": 1, "updated": 0, "cleared": 0, "conflicts": 0}
        assert first["local_total"] == 1
        assert first["changes"][0]["before"] is None
        assert first["changes"][0]["after"] == label["name"]
        assert first["changes"][0]["device"]
        assert sync.status(a, ar)["last_result"] == first["last_result"]
        again = sync.synchronize(a, ar)
        assert again["summary"] == {"added": 0, "updated": 0, "cleared": 0, "conflicts": 0}
        assert again["changes"] == []
        _as(monkeypatch, bd)
        replacement = _existing_label(b, "無法辨識")
        set_item_issue(b, bi, replacement["id"])
        sync.record_item(b, bi, replacement["id"])
        sync.synchronize(b, br)
        _as(monkeypatch, ad)
        result = sync.synchronize(a, ar)
        assert result["summary"]["updated"] == 1
        assert result["changes"][0]["before"] == label["name"]
        assert result["changes"][0]["after"] == replacement["name"]
        _as(monkeypatch, bd)
        set_item_issue(b, bi, None)
        sync.record_item(b, bi, None)
        sync.synchronize(b, br)
        _as(monkeypatch, ad)
        result = sync.synchronize(a, ar)
        assert result["summary"]["cleared"] == 1
        assert result["changes"][0]["after"] is None
        assert result["local_total"] == 0
    finally:
        a.close()
        b.close()


def test_initial_divergent_same_equipment_requires_manual_choice(tmp_path, monkeypatch):
    folder = tmp_path / "shared"
    folder.mkdir()
    ad, a, ar, ai = _client(tmp_path, folder, "initial-a", monkeypatch)
    bd, b, br, bi = _client(tmp_path, folder, "initial-b", monkeypatch)
    try:
        la = _existing_label(a, "瓶身超過10年")
        lb = _existing_label(b, "壓力錶故障")
        set_item_issue(a, ai, la["id"])
        set_item_issue(b, bi, lb["id"])
        _as(monkeypatch, ad)
        sync.configure(a, ar, True)
        sync.synchronize(a, ar)
        _as(monkeypatch, bd)
        sync.configure(b, br, True)
        result = sync.synchronize(b, br)
        assert result["summary"]["conflicts"] == 1
        assert result["summary"]["updated"] == 0
        conflict = result["conflicts"][0]
        assert {c["label_name"] for c in conflict["candidates"]} == {la["name"], lb["name"]}
        assert _issue_label(b, br) == lb["id"]
        _as(monkeypatch, ad)
        assert len(sync.synchronize(a, ar)["conflicts"]) == 1
        assert _issue_label(a, ar) == la["id"]
    finally:
        a.close()
        b.close()


def test_initial_distinct_equipment_merges_and_later_addition_preserves_history(
    tmp_path, monkeypatch
):
    folder = tmp_path / "shared"
    folder.mkdir()
    ad, a, ar, ai = _client(tmp_path, folder, "distinct-a", monkeypatch)
    bd, b, br, bi = _client(tmp_path, folder, "distinct-b", monkeypatch)
    try:
        with b:
            b.execute("UPDATE item SET code='乙',relative_path='滅火器/乙' WHERE id=?", (bi,))
        la = _existing_label(a, "瓶身超過10年")
        lb = _existing_label(b, "壓力錶故障")
        set_item_issue(a, ai, la["id"])
        set_item_issue(b, bi, lb["id"])
        _as(monkeypatch, ad)
        sync.configure(a, ar, True)
        sync.synchronize(a, ar)
        _as(monkeypatch, bd)
        sync.configure(b, br, True)
        result = sync.synchronize(b, br)
        assert result["local_total"] == 2 and not result["conflicts"]
        assert result["summary"]["added"] == 1
        _as(monkeypatch, ad)
        assert sync.synchronize(a, ar)["local_total"] == 2
        _as(monkeypatch, bd)
        with b:
            ci = b.execute(
                "INSERT INTO item(root_id,category_id,year,period,building,code,relative_path) "
                "SELECT root_id,category_id,year,period,building,'丙','滅火器/丙' "
                "FROM item WHERE id=?",
                (bi,),
            ).lastrowid
        set_item_issue(b, ci, lb["id"])
        sync.record_item(b, ci, lb["id"])
        sync.synchronize(b, br)
        _as(monkeypatch, ad)
        result = sync.synchronize(a, ar)
        assert result["local_total"] == 3
        assert result["summary"] == {"added": 1, "updated": 0, "cleared": 0, "conflicts": 0}
        assert result["changes"][0]["code"] == "丙"
        assert sync.synchronize(a, ar)["summary"]["added"] == 0
    finally:
        a.close()
        b.close()


@pytest.mark.parametrize("mode", ["unknown_version", "hidden_cycle", "placeholder"])
def test_untrusted_history_is_rejected_before_sqlite_changes(tmp_path, monkeypatch, mode):
    folder = tmp_path / "shared"
    folder.mkdir()
    local, conn, rid, item = _client(tmp_path, folder, "unsafe", monkeypatch)
    try:
        _as(monkeypatch, local)
        sync.configure(conn, rid, True)
        sync.synchronize(conn, rid)
        label = _existing_label(conn, "無法辨識")
        set_item_issue(conn, item, label["id"])
        sync.record_item(conn, item, label["id"])
        sync.synchronize(conn, rid)
        initial = [tuple(row) for row in conn.execute("SELECT * FROM item_issue")]
        if mode == "placeholder":
            monkeypatch.setattr(sync, "_is_cloud_placeholder_stat", lambda info: True)
        else:
            event_id = "e" * 32
            value = {"category": "box", "path": "放置盒/測試", "code": "測試", "label_guid": None}
            event = {
                "v": 9 if mode == "unknown_version" else 1,
                "id": event_id,
                "device": "d" * 32,
                "kind": "issue",
                "key": "issue:box:放置盒/測試",
                "value": value,
                "parents": ["f" * 32] if mode == "hidden_cycle" else [],
                "at": "2026-11-14",
            }
            directory = folder / sync._SYNC_DIR / "events"
            sync._safe_event(directory / (event_id + ".json"), event)
            if mode == "hidden_cycle":
                sync._safe_event(
                    directory / ("f" * 32 + ".json"),
                    {**event, "id": "f" * 32, "parents": [event_id]},
                )
                sync._safe_event(
                    directory / ("a" * 32 + ".json"),
                    {**event, "id": "a" * 32, "parents": [event_id]},
                )
        with pytest.raises(sync.SyncError):
            sync.synchronize(conn, rid)
        assert [tuple(row) for row in conn.execute("SELECT * FROM item_issue")] == initial
        if mode != "placeholder":
            assert sync.status(conn, rid)["state"] == "incomplete"
            assert sync.status(conn, rid)["sync_error"]
    finally:
        conn.close()


def test_backup_preview_lists_affected_equipment_before_confirmation(tmp_path, monkeypatch):
    folder = tmp_path / "shared"
    folder.mkdir()
    local, conn, rid, item = _client(tmp_path, folder, "preview", monkeypatch)
    try:
        _as(monkeypatch, local)
        old = _existing_label(conn, "瓶身超過10年")
        new = _existing_label(conn, "壓力錶故障")
        set_item_issue(conn, item, old["id"])
        backup_id = sync._backup(folder, conn, rid, reason="合成復原預覽")
        set_item_issue(conn, item, new["id"])
        preview = sync.backup_preview(conn, rid, backup_id)
        assert preview["changing"] == 1
        assert preview["changes"] == [
            {
                "path": "滅火器/2026年/11月份更換/致德樓8F/致-08-66",
                "before": new["name"],
                "after": old["name"],
                "kind": "updated",
            }
        ]
        assert _issue_label(conn, rid) == new["id"]
        with pytest.raises(sync.SyncError, match="確認"):
            sync.restore(conn, rid, backup_id, False)
        assert _issue_label(conn, rid) == new["id"]
    finally:
        conn.close()


def _donor_sync_view(conn, root_id):
    # The merged API has one authoritative nested report, not two implementations.
    response = sync.synchronize(conn, root_id)
    report = response["last_result"]
    return {
        **response,
        "changes": {k: report["summary"][k] for k in ("added", "updated", "cleared")},
        "change_details": [
            {**row, "source_device": row["device"], "event_at": row["at"]}
            for row in report["changes"]
        ],
    }


def _another_item(conn, root_id, code):
    first = conn.execute(
        "SELECT category_id,year,period,building FROM item WHERE root_id=? LIMIT 1",
        (root_id,),
    ).fetchone()
    relative = f"滅火器/{first['year']}/{first['period']}/{first['building']}/{code}"
    with conn:
        result = conn.execute(
            """INSERT INTO item(root_id,category_id,year,period,building,code,relative_path)
               VALUES (?,?,?,?,?,?,?)""",
            (
                root_id,
                first["category_id"],
                first["year"],
                first["period"],
                first["building"],
                code,
                relative,
            ),
        )
    return int(result.lastrowid)


def test_manual_sync_counts_actual_local_device_changes_not_event_count(tmp_path, monkeypatch):
    shared = tmp_path / "shared-folder"
    shared.mkdir()
    a_dir, a, ar, ai = _client(tmp_path, shared, "summary-pc-a", monkeypatch)
    b_dir, b, br, _ = _client(tmp_path, shared, "summary-pc-b", monkeypatch)
    try:
        bi = _another_item(b, br, "致-08-77")
        _as(monkeypatch, a_dir)
        a_first = _existing_label(a, "瓶身超過10年")
        set_item_issue(a, ai, int(a_first["id"]))
        sync.configure(a, ar, True)
        assert _donor_sync_view(a, ar)["changes"] == {"added": 0, "updated": 0, "cleared": 0}
        _as(monkeypatch, b_dir)
        b_first = _existing_label(b, "壓力錶故障")
        set_item_issue(b, bi, int(b_first["id"]))
        sync.configure(b, br, True)
        first_b = _donor_sync_view(b, br)
        assert first_b["changes"]["added"] == 1
        assert first_b["local_total"] == 2
        assert first_b["change_details"][0]["source_device"]
        _as(monkeypatch, a_dir)
        first_a = _donor_sync_view(a, ar)
        assert first_a["changes"] == {"added": 1, "updated": 0, "cleared": 0}
        assert first_a["change_details"][0]["code"] == "致-08-77"
        assert first_a["change_details"][0]["after"] == "壓力錶故障"
        again = _donor_sync_view(a, ar)
        assert again["changes"] == {"added": 0, "updated": 0, "cleared": 0}
        assert again["change_details"] == []

        _as(monkeypatch, b_dir)
        b_other = _existing_label(b, "瓶身超過10年")
        set_item_issue(b, bi, int(b_other["id"]))
        sync.record_item(b, bi, int(b_other["id"]))
        _donor_sync_view(b, br)
        _as(monkeypatch, a_dir)
        changed = _donor_sync_view(a, ar)
        assert changed["changes"] == {"added": 0, "updated": 1, "cleared": 0}
        assert changed["change_details"][0]["before"] == "壓力錶故障"
        assert changed["change_details"][0]["after"] == "瓶身超過10年"

        _as(monkeypatch, b_dir)
        set_item_issue(b, bi, None)
        sync.record_item(b, bi, None)
        _donor_sync_view(b, br)
        _as(monkeypatch, a_dir)
        cleared = _donor_sync_view(a, ar)
        assert cleared["changes"] == {"added": 0, "updated": 0, "cleared": 1}
        assert cleared["change_details"][0]["before"] == "瓶身超過10年"
        assert cleared["change_details"][0]["after"] is None
        assert _donor_sync_view(a, ar)["changes"] == {"added": 0, "updated": 0, "cleared": 0}
    finally:
        a.close()
        b.close()


def test_dynamic_category_sync_event_requires_matching_hashed_root_folder():
    import hashlib

    folder = "水帶"
    code = "folder_" + hashlib.sha256(folder.encode("utf-8")).hexdigest()[:24]
    path = f"{folder}/2026年/11月份更換/中正樓/帶-01"
    value = {"path": path, "category": code, "code": "帶-01", "label_guid": None}
    event = {"v": 2, "kind": "issue", "key": "issue:" + code + ":" + path, "value": value}
    assert sync._value(event) == value
    with pytest.raises(sync.SyncError, match="設備類別"):
        sync._value({**event, "value": {**value, "category": "folder_" + "0" * 24}})
    with pytest.raises(sync.SyncError, match="設備相對路徑不安全"):
        sync._value({**event, "value": {**value, "path": "../bad"}})
    with pytest.raises(sync.SyncError, match="設備類別"):
        sync._value({**event, "value": {**value, "category": "folder_fake"}})


def test_dynamic_folder_category_is_merged_without_any_photo_changes(tmp_path, monkeypatch):
    import hashlib

    shared = tmp_path / "dynamic-shared-root"
    shared.mkdir()
    a_dir, a, ar, _ = _client(tmp_path, shared, "dynamic-a", monkeypatch)
    b_dir, b, br, _ = _client(tmp_path, shared, "dynamic-b", monkeypatch)
    try:
        folder = "水帶"
        category_code = "folder_" + hashlib.sha256(folder.encode("utf-8")).hexdigest()[:24]
        relative = f"{folder}/2026年/11月份更換/中正樓/帶-01"
        with b:
            category_id = b.execute(
                """INSERT INTO category(code,name,slots_json,filename_aliases_json)
                   VALUES (?,?,?,?)""",
                (category_code, folder, '["前","中","後"]', "{}"),
            ).lastrowid
            item_id = b.execute(
                """INSERT INTO item(root_id,category_id,year,period,building,code,relative_path)
                   VALUES (?,?,?,?,?,?,?)""",
                (br, category_id, "2026年", "11月份更換", "中正樓", "帶-01", relative),
            ).lastrowid
        b_label = _existing_label(b, "瓶身超過10年")
        set_item_issue(b, item_id, int(b_label["id"]))
        _as(monkeypatch, a_dir)
        sync.configure(a, ar, True)
        _donor_sync_view(a, ar)
        _as(monkeypatch, b_dir)
        sync.configure(b, br, True)
        _donor_sync_view(b, br)
        _as(monkeypatch, a_dir)
        result = _donor_sync_view(a, ar)
        assert result["changes"] == {"added": 1, "updated": 0, "cleared": 0}
        assert result["change_details"][0]["category"] == category_code
        saved = a.execute(
            "SELECT category_code,item_relative_path FROM item_issue "
            "WHERE root_id=? AND item_relative_path=?",
            (ar, relative),
        ).fetchone()
        assert saved is not None and saved["category_code"] == category_code
        assert not any(shared.rglob("*.jpg"))  # no image created or modified
        assert _donor_sync_view(a, ar)["changes"]["added"] == 0
    finally:
        a.close()
        b.close()

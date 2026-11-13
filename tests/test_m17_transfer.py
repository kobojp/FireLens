"""M17 transfer: preview / confirmation / collision and failure safety."""

from pathlib import Path

from backend.app.db import connect
from tests.test_m2 import setup_client
from tests.test_m11 import _photo_for


def test_move_to_empty_slot_and_sha_guard(monkeypatch, tmp_path: Path, sample_source: Path) -> None:
    folder = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"
    (folder / "編號.jpg").write_bytes(b"number-content")
    client, _, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        item_id, source_id = _photo_for(client, 1, "中-01-02", "編號.jpg")
        preview = client.post(
            f"/api/photos/{source_id}/transfer/preview", json={"target_slot": "藥劑"}
        )
        assert preview.status_code == 200, preview.text
        payload = preview.json()
        assert payload["mode"] == "move"
        assert payload["target_name"] == "藥劑.jpg"
        failed = client.post(
            f"/api/photos/{source_id}/transfer",
            json={"target_slot": "藥劑", "expected_source_sha256": "incorrect"},
        )
        assert failed.status_code == 409
        assert (folder / "編號.jpg").read_bytes() == b"number-content"
        done = client.post(
            f"/api/photos/{source_id}/transfer",
            json={"target_slot": "藥劑", "expected_source_sha256": payload["source_sha256"]},
        )
        assert done.status_code == 200, done.text
        assert not (folder / "編號.jpg").exists()
        assert (folder / "藥劑.jpg").read_bytes() == b"number-content"
        assert done.json()["item"]["id"] == item_id
        restored = client.post(f"/api/slot-transfers/1/undo/{done.json()['transfer_log_id']}")
        assert restored.status_code == 200, restored.text
        assert (folder / "編號.jpg").read_bytes() == b"number-content"
        assert not (folder / "藥劑.jpg").exists()
        conn = connect(db_path)
        try:
            event = conn.execute(
                "SELECT action FROM audit_log WHERE action='transfer_photo_slot' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert event is not None
        finally:
            conn.close()
    finally:
        client.__exit__(None, None, None)


def test_swap_existing_and_reject_wrong_item(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    folder = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"
    (folder / "編號.jpg").write_bytes(b"actual-drug")
    (folder / "藥劑.jpg").write_bytes(b"actual-number")
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        _, src = _photo_for(client, root_id, "中-01-02", "編號.jpg")
        _, dst = _photo_for(client, root_id, "中-01-02", "藥劑.jpg")
        _, other = _photo_for(client, root_id, "中-01-01", "完成.jpg")
        rejected = client.post(
            f"/api/photos/{src}/transfer/preview",
            json={"target_slot": "藥劑", "target_photo_id": other},
        )
        assert rejected.status_code == 400
        assert (folder / "編號.jpg").read_bytes() == b"actual-drug"
        preview = client.post(
            f"/api/photos/{src}/transfer/preview",
            json={"target_slot": "藥劑", "target_photo_id": dst},
        )
        assert preview.status_code == 200, preview.text
        data = preview.json()
        assert data["mode"] == "swap"
        execute = client.post(
            f"/api/photos/{src}/transfer",
            json={
                "target_slot": "藥劑",
                "target_photo_id": dst,
                "expected_source_sha256": data["source_sha256"],
                "expected_target_sha256": data["target_sha256"],
            },
        )
        assert execute.status_code == 200, execute.text
        assert (folder / "編號.jpg").read_bytes() == b"actual-number"
        assert (folder / "藥劑.jpg").read_bytes() == b"actual-drug"
        assert not list(folder.glob(".firelens-transfer-*"))
        log_id = execute.json()["transfer_log_id"]
        history = client.get(f"/api/items/{execute.json()['item']['id']}/slot-transfers")
        assert history.status_code == 200
        assert history.json()[0]["id"] == log_id
        assert history.json()[0]["reverted_at"] is None
        restored = client.post(f"/api/slot-transfers/{root_id}/undo/{log_id}")
        assert restored.status_code == 200, restored.text
        assert restored.json()["reverted"] is True
        assert (folder / "編號.jpg").read_bytes() == b"actual-drug"
        assert (folder / "藥劑.jpg").read_bytes() == b"actual-number"
        assert not list(folder.glob(".firelens-transfer-*"))
        repeated = client.post(f"/api/slot-transfers/{root_id}/undo/{log_id}")
        assert repeated.status_code == 409
    finally:
        client.__exit__(None, None, None)


def test_swap_rolls_back_when_second_file_move_fails(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    from backend.app import photo_transfer

    folder = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"
    (folder / "編號.jpg").write_bytes(b"source-safe")
    (folder / "藥劑.jpg").write_bytes(b"target-safe")
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        _, src = _photo_for(client, root_id, "中-01-02", "編號.jpg")
        _, dst = _photo_for(client, root_id, "中-01-02", "藥劑.jpg")
        preview = client.post(
            f"/api/photos/{src}/transfer/preview",
            json={"target_slot": "藥劑", "target_photo_id": dst},
        ).json()
        original = photo_transfer._rename_no_overwrite
        count = 0

        def fail_on_second(a, b):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("injected move failure")
            return original(a, b)

        monkeypatch.setattr(photo_transfer, "_rename_no_overwrite", fail_on_second)
        failed = client.post(
            f"/api/photos/{src}/transfer",
            json={
                "target_slot": "藥劑",
                "target_photo_id": dst,
                "expected_source_sha256": preview["source_sha256"],
                "expected_target_sha256": preview["target_sha256"],
            },
        )
        assert failed.status_code == 400
        assert (folder / "編號.jpg").read_bytes() == b"source-safe"
        assert (folder / "藥劑.jpg").read_bytes() == b"target-safe"
        assert not list(folder.glob(".firelens-transfer-*"))
    finally:
        client.__exit__(None, None, None)


def test_undo_blocks_when_content_was_changed(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    folder = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"
    (folder / "編號.jpg").write_bytes(b"original")
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        _, src = _photo_for(client, root_id, "中-01-02", "編號.jpg")
        preview = client.post(
            f"/api/photos/{src}/transfer/preview", json={"target_slot": "藥劑"}
        ).json()
        transferred = client.post(
            f"/api/photos/{src}/transfer",
            json={"target_slot": "藥劑", "expected_source_sha256": preview["source_sha256"]},
        )
        assert transferred.status_code == 200
        (folder / "藥劑.jpg").write_bytes(b"changed-by-another-user")
        refused = client.post(
            f"/api/slot-transfers/{root_id}/undo/{transferred.json()['transfer_log_id']}"
        )
        assert refused.status_code == 409
        assert (folder / "藥劑.jpg").read_bytes() == b"changed-by-another-user"
        assert not (folder / "編號.jpg").exists()
    finally:
        client.__exit__(None, None, None)


def test_migration_8_to_9_preserves_data_and_creates_backup(db_path: Path) -> None:
    from backend.app.db import connect, initialize_database

    conn = connect(db_path)
    try:
        with conn:
            conn.execute("INSERT INTO ledger(name, source_type) VALUES ('歷史清冊', 'text')")
            conn.execute("DROP TABLE slot_transfer_log")
            conn.execute("PRAGMA user_version=8")
    finally:
        conn.close()
    initialize_database(db_path)
    conn = connect(db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 13
        assert conn.execute("SELECT name FROM ledger").fetchone()[0] == "歷史清冊"
        columns = {row[1] for row in conn.execute("PRAGMA table_info(slot_transfer_log)")}
        assert {"source_before", "source_after", "reverted_at"} <= columns
    finally:
        conn.close()
    assert db_path.with_suffix(".sqlite3.backup-v8").is_file()


def test_swap_different_extensions_and_collision_is_rejected(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    folder = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"
    (folder / "編號.jpg").write_bytes(b"number-bytes")
    (folder / "藥劑.png").write_bytes(b"drug-bytes")
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        _, source_id = _photo_for(client, root_id, "中-01-02", "編號.jpg")
        _, target_id = _photo_for(client, root_id, "中-01-02", "藥劑.png")
        payload = client.post(
            f"/api/photos/{source_id}/transfer/preview",
            json={"target_slot": "藥劑", "target_photo_id": target_id},
        )
        assert payload.status_code == 200
        data = payload.json()
        assert data["target_name"] == "藥劑.jpg"
        assert data["target_new_name"] == "編號.png"
        done = client.post(
            f"/api/photos/{source_id}/transfer",
            json={
                "target_slot": "藥劑",
                "target_photo_id": target_id,
                "expected_source_sha256": data["source_sha256"],
                "expected_target_sha256": data["target_sha256"],
            },
        )
        assert done.status_code == 200, done.text
        assert (folder / "藥劑.jpg").read_bytes() == b"number-bytes"
        assert (folder / "編號.png").read_bytes() == b"drug-bytes"
        assert not (folder / "編號.jpg").exists()
        assert not (folder / "藥劑.png").exists()
    finally:
        client.__exit__(None, None, None)


def test_transfer_blocks_cloud_placeholder_and_busy_scan(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    from backend.app import main as main_module

    folder = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"
    (folder / "編號.jpg").write_bytes(b"original-bytes")
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        _, photo_id = _photo_for(client, root_id, "中-01-02", "編號.jpg")
        conn = connect(db_path)
        try:
            with conn:
                conn.execute("UPDATE photo SET cloud_placeholder=1 WHERE id=?", (photo_id,))
        finally:
            conn.close()
        blocked = client.post(
            f"/api/photos/{photo_id}/transfer/preview", json={"target_slot": "藥劑"}
        )
        assert blocked.status_code == 409
        conn = connect(db_path)
        try:
            with conn:
                conn.execute("UPDATE photo SET cloud_placeholder=0 WHERE id=?", (photo_id,))
        finally:
            conn.close()
        monkeypatch.setattr(main_module, "scan_job_status", lambda root: {"state": "running"})
        scanning = client.post(
            f"/api/photos/{photo_id}/transfer/preview", json={"target_slot": "藥劑"}
        )
        assert scanning.status_code == 409
        assert (folder / "編號.jpg").read_bytes() == b"original-bytes"
        assert not (folder / "藥劑.jpg").exists()
    finally:
        client.__exit__(None, None, None)

from __future__ import annotations

import hashlib
from pathlib import Path

from backend.app.db import connect
from tests.test_m2 import find_item, setup_client


def _empty_extinguisher_dir(sample_source: Path) -> Path:
    return sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-02"


def _photo_for(client, root_id: int, code: str, filename: str) -> tuple[int, int]:
    tree = client.get(f"/api/roots/{root_id}/tree").json()
    item_id = int(find_item(tree, code)["id"])
    detail = client.get(f"/api/items/{item_id}").json()
    photo = next(row for row in detail["photos"] if row["filename"] == filename)
    return item_id, int(photo["id"])


def test_unmapped_photo_can_be_assigned_to_slot_and_undone(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    item_dir = _empty_extinguisher_dir(sample_source)
    source = item_dir / "46459.jpg"
    source.write_bytes(b"m11-unmapped-photo")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        item_id, photo_id = _photo_for(client, root_id, "中-01-02", "46459.jpg")
        preview = client.post(
            f"/api/photos/{photo_id}/rename/preview",
            json={"target_filename": "完成.jpg", "reason": "拖曳歸槽：完成"},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["safe"] is True
        assert preview.json()["source_name"] == "46459.jpg"
        assert preview.json()["target_name"] == "完成.jpg"
        assert preview.json()["sha256"] == digest

        renamed = client.post(
            f"/api/photos/{photo_id}/rename",
            json={
                "target_filename": "完成.jpg",
                "expected_sha256": digest,
                "reason": "拖曳歸槽：完成",
            },
        )
        assert renamed.status_code == 200, renamed.text
        body = renamed.json()
        assert not source.exists()
        target = item_dir / "完成.jpg"
        assert target.is_file()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
        assert body["item"]["id"] == item_id
        updated_photo = next(row for row in body["item"]["photos"] if row["id"] == photo_id)
        assert updated_photo["filename"] == "完成.jpg"
        assert updated_photo["slot"] == "完成"

        conn = connect(db_path)
        try:
            log = conn.execute(
                """
                SELECT id, source_path, target_path, sha256
                FROM rename_log ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            assert log is not None
            assert log["sha256"] == digest
            action = conn.execute(
                "SELECT action FROM audit_log WHERE action='rename_photo' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert action is not None
        finally:
            conn.close()

        undone = client.post(f"/api/organizer/{root_id}/undo/{body['rename_log_id']}")
        assert undone.status_code == 200, undone.text
        assert source.is_file()
        assert not target.exists()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    finally:
        client.__exit__(None, None, None)


def test_photo_rename_blocks_collision_invalid_filename_and_sha_change(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    item_dir = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
    source = item_dir / "46459.jpg"
    source.write_bytes(b"rename-source")

    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        _, photo_id = _photo_for(client, root_id, "中-01-01", "46459.jpg")

        collision = client.post(
            f"/api/photos/{photo_id}/rename/preview",
            json={"target_filename": "完成.jpg"},
        )
        assert collision.status_code == 200
        assert collision.json()["safe"] is False
        assert "已存在" in collision.json()["blocked_reason"]

        for invalid in ("../完成.jpg", "bad:name.jpg", "CON.jpg", "改成.png"):
            response = client.post(
                f"/api/photos/{photo_id}/rename/preview",
                json={"target_filename": invalid},
            )
            assert response.status_code == 400, (invalid, response.text)

        preview = client.post(
            f"/api/photos/{photo_id}/rename/preview",
            json={"target_filename": "編號2.jpg"},
        )
        assert preview.status_code == 200
        old_digest = preview.json()["sha256"]
        source.write_bytes(b"changed-after-preview")
        execute = client.post(
            f"/api/photos/{photo_id}/rename",
            json={"target_filename": "編號2.jpg", "expected_sha256": old_digest},
        )
        assert execute.status_code == 409
        assert source.is_file()
        assert not (item_dir / "編號2.jpg").exists()
    finally:
        client.__exit__(None, None, None)


def test_photo_rename_blocks_cloud_placeholder_offline_and_running_scan(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    item_dir = _empty_extinguisher_dir(sample_source)
    source = item_dir / "46459.jpg"
    source.write_bytes(b"blocked-photo")
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        _, photo_id = _photo_for(client, root_id, "中-01-02", "46459.jpg")
        conn = connect(db_path)
        try:
            with conn:
                conn.execute("UPDATE photo SET cloud_placeholder=1 WHERE id=?", (photo_id,))
        finally:
            conn.close()

        placeholder = client.post(
            f"/api/photos/{photo_id}/rename/preview",
            json={"target_filename": "完成.jpg"},
        )
        assert placeholder.status_code == 200
        assert placeholder.json()["safe"] is False
        assert "雲端未下載" in placeholder.json()["blocked_reason"]

        conn = connect(db_path)
        try:
            with conn:
                conn.execute("UPDATE photo SET cloud_placeholder=0 WHERE id=?", (photo_id,))
        finally:
            conn.close()

        monkeypatch.setattr(
            "backend.app.main.scan_job_status",
            lambda _root_id: {"state": "running"},
        )
        running = client.post(
            f"/api/photos/{photo_id}/rename/preview",
            json={"target_filename": "完成.jpg"},
        )
        assert running.status_code == 409
        assert "掃描進行中" in running.json()["detail"]

        monkeypatch.undo()
        monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
        moved = tmp_path / "source-offline"
        sample_source.rename(moved)
        offline = client.post(
            f"/api/photos/{photo_id}/rename/preview",
            json={"target_filename": "完成.jpg"},
        )
        assert offline.status_code == 400
        assert "根目錄不存在" in offline.json()["detail"]
    finally:
        client.__exit__(None, None, None)

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

from openpyxl import load_workbook

from backend.app import item_folders
from backend.app.db import SCHEMA_VERSION, connect, initialize_database
from tests.scan_helpers import run_scan
from tests.test_m2 import find_item, setup_client


def test_schema_7_to_8_is_backup_safe_and_idempotent(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("INSERT INTO ledger(name,source_type) VALUES ('保留清冊','text')")
            conn.execute("PRAGMA user_version=7")
    finally:
        conn.close()
    initialize_database(db_path)
    initialize_database(db_path)
    conn = connect(db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 9
        assert db_path.with_suffix(".sqlite3.backup-v7").is_file()
        assert conn.execute("SELECT name FROM ledger").fetchone()[0] == "保留清冊"
        assert {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }.issuperset({"issue_label", "item_issue", "ledger", "ledger_row", "reshoot_mark"})
        assert [
            row[0] for row in conn.execute("SELECT name FROM issue_label ORDER BY sort_order")
        ] == ["瓶身超過10年", "無法辨識", "壓力錶故障"]
    finally:
        conn.close()


def test_issue_single_choice_statistic_label_management_and_folder_rename(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    original = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
    before_hash = hashlib.sha256((original / "完成.jpg").read_bytes()).hexdigest()
    try:
        item_id = int(find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-01-01")["id"])
        labels = client.get("/api/issues/labels").json()
        first, second = labels[0]["id"], labels[2]["id"]
        assert client.get(f"/api/items/{item_id}/issue").json()["label_id"] is None

        marked = client.put(f"/api/items/{item_id}/issue", json={"label_id": first})
        assert marked.status_code == 200
        assert marked.json()["label_id"] == first
        assert client.get("/api/issues/statistics").json()["total"] == 1

        marked = client.put(f"/api/items/{item_id}/issue", json={"label_id": second})
        assert marked.status_code == 200
        stats = client.get(f"/api/issues/statistics?root_id={root_id}").json()
        assert stats["total"] == 1
        counts = {row["id"]: row["count"] for row in stats["labels"]}
        assert counts[first] == 0 and counts[second] == 1
        invalid_issue = client.put(f"/api/items/{item_id}/issue", json={"label_id": 999999})
        assert invalid_issue.status_code == 400

        created = client.post("/api/issues/labels", json={"name": "瓶身損傷"})
        assert created.status_code == 201, created.text
        new_id = created.json()["id"]
        assert client.post("/api/issues/labels", json={"name": " 瓶身損傷 "}).status_code == 409
        renamed_label = client.put(f"/api/issues/labels/{new_id}", json={"name": "瓶身破損"})
        assert renamed_label.status_code == 200
        moved_label = client.put(f"/api/issues/labels/{new_id}", json={"sort_order": 0})
        assert moved_label.status_code == 200
        assert client.get("/api/issues/labels").json()[0]["id"] == new_id
        selected = client.put(f"/api/items/{item_id}/issue", json={"label_id": new_id})
        assert selected.status_code == 200
        assert client.put(f"/api/issues/labels/{new_id}", json={"active": False}).status_code == 200
        assert client.get(f"/api/items/{item_id}/issue").json()["label_name"] == "瓶身破損"

        assert (
            client.post(f"/api/items/{item_id}/rename", json={"new_name": "中-01-02"}).status_code
            == 409
        )
        for name in ("CON", "../outside", "test.", "中:01", " "):
            assert client.post(
                f"/api/items/{item_id}/rename", json={"new_name": name}
            ).status_code in (400, 409, 422)
        renamed = client.post(f"/api/items/{item_id}/rename", json={"new_name": "中-01-05"})
        assert renamed.status_code == 200, renamed.text
        target = original.with_name("中-01-05")
        assert target.is_dir() and not original.exists()
        assert hashlib.sha256((target / "完成.jpg").read_bytes()).hexdigest() == before_hash
        assert client.get(f"/api/items/{item_id}").json()["code"] == "中-01-05"
        assert all(
            "中-01-05" in photo["relative_path"]
            for photo in client.get(f"/api/items/{item_id}").json()["photos"]
        )
        assert client.get(f"/api/items/{item_id}/issue").json()["label_name"] == "瓶身破損"
        run_scan(client, root_id)
        assert client.get(f"/api/items/{item_id}").status_code == 200
        stats = client.get("/api/issues/statistics").json()
        assert stats["total"] == 1
        assert stats["items"][0]["device_code"] == "中-01-05"

        cleared = client.put(f"/api/items/{item_id}/issue", json={"label_id": None})
        assert cleared.status_code == 200
        assert client.get("/api/issues/statistics").json()["total"] == 0
        conn = connect(db_path)
        try:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE action='rename_item_folder'"
                ).fetchone()[0]
                == 1
            )
        finally:
            conn.close()
    finally:
        client.__exit__(None, None, None)


def test_folder_rename_blocks_cloud_placeholder_and_retains_issues(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        item_id = int(find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-01-01")["id"])
        first = client.get("/api/issues/labels").json()[0]["id"]
        selected = client.put(f"/api/items/{item_id}/issue", json={"label_id": first})
        assert selected.status_code == 200
        conn = connect(db_path)
        try:
            with conn:
                conn.execute("UPDATE root SET is_cloud_stream=1 WHERE id=?", (root_id,))
                conn.execute("UPDATE photo SET cloud_placeholder=1 WHERE item_id=?", (item_id,))
        finally:
            conn.close()
        response = client.post(f"/api/items/{item_id}/rename", json={"new_name": "中-01-88"})
        assert response.status_code == 409
        assert client.get(f"/api/items/{item_id}/issue").json()["label_id"] == first
        assert client.get("/api/issues/statistics").json()["total"] == 1
        # 雲端串流模式本身不是永久禁止更名：佔位旗標清除後，同層更名可操作。
        conn = connect(db_path)
        try:
            with conn:
                conn.execute("UPDATE photo SET cloud_placeholder=0 WHERE item_id=?", (item_id,))
        finally:
            conn.close()
        allowed = client.post(f"/api/items/{item_id}/rename", json={"new_name": "中-01-88"})
        assert allowed.status_code == 200, allowed.text
        assert client.get(f"/api/items/{item_id}/issue").json()["label_id"] == first
    finally:
        client.__exit__(None, None, None)


def test_reconcile_exports_save_real_csv_xlsx_and_no_overwrite(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    export_dir = tmp_path / "匯出測試 有空白"
    monkeypatch.setenv("FIRELENS_EXPORT_DIR", str(export_dir))
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        created = client.post(
            "/api/ledgers/text",
            json={"name": "異常測試", "text": "中-01-01\n中-01-02\n中-01-99"},
        )
        assert created.status_code == 201, created.text
        ledger_id = created.json()["id"]
        saved_paths: list[Path] = []
        for file_format in ("csv", "xlsx", "csv"):
            response = client.post(
                "/api/reconcile/export/save",
                json={"root_id": root_id, "ledger_id": ledger_id, "format": file_format},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            path = Path(body["path"])
            assert body["saved"] and path.is_file() and path.stat().st_size == body["size"] > 0
            assert path.suffix == "." + file_format
            saved_paths.append(path)
            if file_format == "csv":
                text = path.read_text(encoding="utf-8-sig")
                records = list(csv.reader(io.StringIO(text)))
                assert records[0][:3] == ["類別", "設備編號", "棟別樓層"]
                assert any("中-01-99" in row for row in records)
                assert not any("中-01-01" in row for row in records[1:])
            else:
                workbook = load_workbook(path, read_only=True)
                try:
                    records = list(workbook.active.values)
                    assert "設備編號" in records[0]
                    assert any("中-01-99" in row for row in records)
                finally:
                    workbook.close()
        assert len(set(saved_paths)) == 3
        assert (
            client.post(
                "/api/reconcile/export/save",
                json={"root_id": root_id, "ledger_id": ledger_id, "format": "exe"},
            ).status_code
            == 400
        )
    finally:
        client.__exit__(None, None, None)


def test_rename_rolls_back_on_database_failure_and_does_not_touch_photos(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    original = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
    target = original.with_name("中-01-06")
    try:
        item_id = int(find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-01-01")["id"])
        conn = connect(db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TRIGGER fail_rename_item BEFORE UPDATE OF code ON item
                    BEGIN SELECT RAISE(ABORT, 'forced-test-failure'); END;
                    """
                )
        finally:
            conn.close()
        response = client.post(f"/api/items/{item_id}/rename", json={"new_name": "中-01-06"})
        assert response.status_code == 400, response.text
        assert original.is_dir() and (original / "完成.jpg").is_file()
        assert not target.exists()
        assert client.get(f"/api/items/{item_id}").json()["code"] == "中-01-01"
    finally:
        client.__exit__(None, None, None)


def test_issue_survives_external_folder_disappearance_as_unresolved(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    original = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
    try:
        item_id = int(find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-01-01")["id"])
        label_id = client.get("/api/issues/labels").json()[0]["id"]
        assert (
            client.put(f"/api/items/{item_id}/issue", json={"label_id": label_id}).status_code
            == 200
        )
        original.rename(original.with_name("中-01-88"))
        run_scan(client, root_id)
        assert client.get(f"/api/items/{item_id}").status_code == 404
        summary = client.get("/api/issues/statistics").json()
        assert summary["total"] == 1
        assert summary["items"][0]["item_id"] is None
        assert summary["items"][0]["device_code"] == "中-01-01"
    finally:
        client.__exit__(None, None, None)


def test_rename_blocks_scanning_offline_and_permission_failure(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    client, root_id, db_path = setup_client(monkeypatch, tmp_path, sample_source)
    original = sample_source / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
    try:
        item_id = int(find_item(client.get(f"/api/roots/{root_id}/tree").json(), "中-01-01")["id"])
        with monkeypatch.context() as patched:
            patched.setattr(item_folders, "scan_job_status", lambda _: {"state": "running"})
            response = client.post(f"/api/items/{item_id}/rename", json={"new_name": "中-01-78"})
            assert response.status_code == 409

        conn = connect(db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE root SET path=? WHERE id=?",
                    (str(tmp_path / "offline-missing"), root_id),
                )
        finally:
            conn.close()
        response = client.post(f"/api/items/{item_id}/rename", json={"new_name": "中-01-78"})
        assert response.status_code == 400
        conn = connect(db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE root SET path=? WHERE id=?",
                    (str(sample_source), root_id),
                )
        finally:
            conn.close()

        def deny_rename(*_args: object) -> None:
            raise PermissionError("synthetic permission denied")

        with monkeypatch.context() as patched:
            patched.setattr(item_folders.os, "rename", deny_rename)
            response = client.post(f"/api/items/{item_id}/rename", json={"new_name": "中-01-78"})
        assert response.status_code == 400, response.text
        assert original.is_dir() and (original / "完成.jpg").is_file()
        assert not original.with_name("中-01-78").exists()
    finally:
        client.__exit__(None, None, None)


def test_export_when_nothing_is_missing_still_creates_valid_header_files(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    monkeypatch.setenv("FIRELENS_EXPORT_DIR", str(tmp_path / "empty-export"))
    complete_root = tmp_path / "完整設備專用測試"
    item = complete_root / "滅火器" / "2026年" / "9月份更換" / "中正樓" / "中-01-01"
    item.mkdir(parents=True)
    for photo in ("編號.jpg", "藥劑.jpg", "完成.jpg"):
        (item / photo).write_bytes(b"synthetic-photo")
    client, root_id, _ = setup_client(monkeypatch, tmp_path, complete_root)
    try:
        created = client.post(
            "/api/ledgers/text",
            json={"name": "無缺失清冊", "text": "中-01-01"},
        )
        assert created.status_code == 201
        ledger_id = created.json()["id"]
        csv_result = client.post(
            "/api/reconcile/export/save",
            json={"root_id": root_id, "ledger_id": ledger_id, "format": "csv"},
        )
        assert csv_result.status_code == 200
        csv_text = Path(csv_result.json()["path"]).read_text(encoding="utf-8-sig")
        assert csv_text.startswith("類別,設備編號,棟別樓層")
        assert "中-01-01" not in csv_text
        xlsx_result = client.post(
            "/api/reconcile/export/save",
            json={"root_id": root_id, "ledger_id": ledger_id, "format": "xlsx"},
        )
        assert xlsx_result.status_code == 200
        workbook = load_workbook(xlsx_result.json()["path"], read_only=True)
        try:
            rows = list(workbook.active.values)
            assert len(rows) == 1
            assert rows[0][1] == "設備編號"
        finally:
            workbook.close()
    finally:
        client.__exit__(None, None, None)


def test_export_storage_failure_does_not_claim_success(
    monkeypatch, tmp_path: Path, sample_source: Path
) -> None:
    blocked_directory = tmp_path / "不可當作資料夾的檔案"
    blocked_directory.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("FIRELENS_EXPORT_DIR", str(blocked_directory))
    client, root_id, _ = setup_client(monkeypatch, tmp_path, sample_source)
    try:
        created = client.post(
            "/api/ledgers/text",
            json={"name": "匯出錯誤", "text": "中-01-99"},
        )
        assert created.status_code == 201
        response = client.post(
            "/api/reconcile/export/save",
            json={
                "root_id": root_id,
                "ledger_id": created.json()["id"],
                "format": "csv",
            },
        )
        assert response.status_code == 500
        assert "檔案儲存失敗" in response.json()["detail"]
        assert blocked_directory.read_text(encoding="utf-8") == "not a directory"
    finally:
        client.__exit__(None, None, None)

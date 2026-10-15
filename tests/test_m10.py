from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app import db as db_module
from backend.app.db import connect, initialize_database
from backend.app.main import create_app

TEXT_LEDGER = (
    "區段\t設備名稱\t型式規格\t上次更換日\n"
    "中正樓1F\t中-01-80\t10P\t2026/10/01\n"
    "中正樓2F\t中-02-20\t20P\t2026/10/02\n"
)


def _create_v6_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            conn.executescript(db_module.MIGRATION_1)
            conn.executescript(db_module.MIGRATION_2)
            conn.executescript(db_module.MIGRATION_3)
            conn.execute("PRAGMA user_version = 3")
        db_module._migrate_4(conn)
        db_module._migrate_5(conn)
        db_module._migrate_6(conn)
        with conn:
            conn.execute(
                """
                INSERT INTO ledger(name, source_type, source_sha256)
                VALUES ('舊清冊', 'text', 'abc')
                """
            )
    finally:
        conn.close()


def test_v6_to_v7_migration_preserves_ledgers_and_creates_backup(tmp_path: Path) -> None:
    path = tmp_path / "firelens.sqlite3"
    _create_v6_database(path)

    initialize_database(path)

    assert path.with_suffix(".sqlite3.backup-v6").is_file()
    conn = connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        columns = {row[1] for row in conn.execute("PRAGMA table_info(ledger)")}
        assert {"source_text", "source_filename"}.issubset(columns)
        row = conn.execute(
            "SELECT name, source_text, source_filename FROM ledger WHERE name='舊清冊'"
        ).fetchone()
        assert row is not None
        assert row["source_text"] is None
        assert row["source_filename"] is None
    finally:
        conn.close()


def test_text_ledger_survives_restart_can_rename_and_delete(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "appdata"
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(data_dir))

    with TestClient(create_app()) as client:
        created = client.post(
            "/api/ledgers/text",
            json={"name": "2026/10 滅火器清冊", "text": TEXT_LEDGER},
        )
        assert created.status_code == 201, created.text
        ledger_id = int(created.json()["id"])
        assert created.json()["row_count"] == 2

    with TestClient(create_app()) as client:
        detail = client.get(f"/api/ledgers/{ledger_id}")
        assert detail.status_code == 200
        assert detail.json()["source_text"] == TEXT_LEDGER
        assert [row["device_no"] for row in detail.json()["rows"]] == ["中-01-80", "中-02-20"]

        renamed = client.put(f"/api/ledgers/{ledger_id}", json={"name": "2026/10 滅火器正式清冊"})
        assert renamed.status_code == 200
        assert renamed.json()["id"] == ledger_id
        assert renamed.json()["name"] == "2026/10 滅火器正式清冊"
        assert len(renamed.json()["rows"]) == 2

        deleted = client.delete(f"/api/ledgers/{ledger_id}")
        assert deleted.status_code == 200
        assert deleted.json()["row_count"] == 2
        assert client.get(f"/api/ledgers/{ledger_id}").status_code == 404

    conn = connect(data_dir / "firelens.sqlite3")
    try:
        actions = [
            row["action"] for row in conn.execute("SELECT action FROM audit_log ORDER BY id")
        ]
        assert "rename_ledger" in actions
        assert "delete_ledger" in actions
    finally:
        conn.close()


def test_excel_ledger_keeps_original_filename(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["區段", "設備名稱", "型式規格", "上次更換日"])
    sheet.append(["中正樓1F", "中-01-80", "10P", "2026/10/01"])
    payload = io.BytesIO()
    workbook.save(payload)
    workbook.close()

    with TestClient(create_app()) as client:
        created = client.post(
            "/api/ledgers/excel",
            files={
                "file": (
                    "2026-10-滅火器.xlsx",
                    payload.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["source_filename"] == "2026-10-滅火器.xlsx"
        detail = client.get(f"/api/ledgers/{created.json()['id']}").json()
        assert detail["source_filename"] == "2026-10-滅火器.xlsx"
        assert detail["source_text"] is None
        assert detail["row_count"] == 1

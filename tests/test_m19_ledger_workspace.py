"""M19-L: protected ledger names and persistent list options; synthetic databases."""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.db import connect
from backend.app.main import create_app
from backend.app.reconcile import ReconcileError, import_ledger, parse_text_rows, rename_ledger

TEXT = "棟別樓層\t設備編號\n致德樓8F\t致-08-19\n中正樓B2F\t中-B2-05"
TEXT2 = "動-01-15\n動-03-08"


def _xlsx_bytes() -> bytes:
    book = Workbook()
    book.active.append(["棟別樓層", "設備編號"])
    book.active.append(["中正樓B2F", "中-B2-05"])
    out = io.BytesIO()
    book.save(out)
    book.close()
    return out.getvalue()


def test_text_excel_rename_conflicts_are_409_and_dont_delete_rows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as client:
        first = client.post("/api/ledgers/text", json={"name": "2026/11 滅火器清冊", "text": TEXT})
        assert first.status_code == 201, first.text
        first_id = first.json()["id"]
        assert first.json()["row_count"] == 2

        duplicates = [
            client.post("/api/ledgers/text", json={"name": " 2026/11 滅火器清冊 ", "text": TEXT2}),
            client.post(
                "/api/ledgers/text", json={"name": "２０２６／１１ 滅火器清冊", "text": TEXT2}
            ),
            client.post(
                "/api/ledgers/excel",
                params={"name": "2026/11 滅火器清冊"},
                files={
                    "file": (
                        "new.xlsx",
                        _xlsx_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            ),
        ]
        for response in duplicates:
            assert response.status_code == 409, response.text
            assert "清冊名稱已存在" in response.json()["detail"]

        second = client.post("/api/ledgers/text", json={"name": "另一份清冊", "text": TEXT2})
        assert second.status_code == 201, second.text
        rename_collision = client.put(
            f"/api/ledgers/{second.json()['id']}", json={"name": "2026/11 滅火器清冊"}
        )
        assert rename_collision.status_code == 409
        assert client.get(f"/api/ledgers/{first_id}").json()["row_count"] == 2
        assert client.get(f"/api/ledgers/{second.json()['id']}").json()["name"] == "另一份清冊"

        unchanged = client.put(f"/api/ledgers/{first_id}", json={"name": "2026/11 滅火器清冊"})
        assert unchanged.status_code == 200
        assert len(client.get("/api/ledgers").json()) == 2

        for name in ["   ", "x" * 201]:
            failed = client.post("/api/ledgers/text", json={"name": name, "text": TEXT2})
            assert failed.status_code in (400, 422)
        assert len(client.get("/api/ledgers").json()) == 2


def test_legacy_duplicated_ledgers_survive_unique_name_checks(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()):
        conn = connect(tmp_path / "appdata" / "firelens.sqlite3")
        try:
            with conn:
                conn.execute(
                    "INSERT INTO ledger(name,source_type) VALUES (?,?)", ("貼上清冊", "text")
                )
                conn.execute(
                    "INSERT INTO ledger(name,source_type) VALUES (?,?)", ("貼上清冊", "text")
                )
            rows = conn.execute("SELECT id FROM ledger ORDER BY id").fetchall()
            assert len(rows) == 2
            with pytest.raises(ReconcileError, match="已存在"):
                import_ledger(
                    conn, name="貼上清冊", source_type="text", rows=parse_text_rows(TEXT2)
                )
            assert conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0] == 2
            same = rename_ledger(conn, rows[0]["id"], "貼上清冊")
            assert same["name"] == "貼上清冊"
            renamed = rename_ledger(conn, rows[0]["id"], "不重複的新名稱")
            assert renamed["name"] == "不重複的新名稱"
            assert conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0] == 2
        finally:
            conn.close()


def test_concurrent_imports_with_same_name_are_serialized(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as client:

        def submit(index: int):
            return client.post(
                "/api/ledgers/text",
                json={
                    "name": "雙機同時清冊",
                    "text": f"動-01-0{index}",
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(submit, [1, 2]))
        assert sorted(statuses) == [201, 409], statuses
        assert [row["name"] for row in client.get("/api/ledgers").json()] == ["雙機同時清冊"]


def test_ledger_manager_setting_defaults_validate_and_survive_restart(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as client:
        defaults = client.get("/api/settings").json()
        assert defaults["ledger_list_collapsed"] is False
        assert defaults["ledger_page_size"] == 5
        changed = client.put(
            "/api/settings",
            json={
                "ledger_list_collapsed": True,
                "ledger_page_size": 10,
            },
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["ledger_list_collapsed"] is True
        assert changed.json()["ledger_page_size"] == 10
        for value in [0, True, 6, "5", -1, 50]:
            invalid = client.put("/api/settings", json={"ledger_page_size": value})
            assert invalid.status_code in (400, 422)
            assert client.get("/api/settings").json()["ledger_page_size"] == 10
        for value in [0, "false", None]:
            assert client.put(
                "/api/settings", json={"ledger_list_collapsed": value}
            ).status_code in (400, 422)

    with TestClient(create_app()) as client:
        latest = client.get("/api/settings").json()
        assert latest["ledger_list_collapsed"] is True
        assert latest["ledger_page_size"] == 10
        assert latest["auto_scan_on_start"] == defaults["auto_scan_on_start"]

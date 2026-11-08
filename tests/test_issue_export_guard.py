"""Regression tests for Filtered Issue Statistics export guard and file output."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.app.export_files import export_issue_rows
from backend.app.main import create_app


def fake_stats():
    return {
        "labels": [
            {"id": 1, "name": "瓶身超過10年"},
            {"id": 2, "name": "無法辨識"},
        ],
        "items": [
            {
                "label_id": 1,
                "device_code": "致-08-001",
                "root_name": "根目錄甲",
                "item_relative_path": "滅火器/致-08-001",
                "building": "致德樓8F",
                "year": "2026年",
                "period": "11月",
                "updated_at": "2026-11-08",
            },
            {
                "label_id": 2,
                "device_code": "動-03-18",
                "root_name": "根目錄甲",
                "item_relative_path": "滅火器/動-03-18",
                "building": "動力中心3F",
                "year": "2026年",
                "period": "10月",
                "updated_at": "2026-11-07",
            },
            {
                "label_id": 1,
                "device_code": "=1+2",
                "root_name": "根目錄乙",
                "item_relative_path": "滅火器/=1+2",
                "building": "致德樓8F",
                "year": "2026年",
                "period": "11月",
                "updated_at": "2026-11-06",
            },
        ],
    }


def test_csv_excel_render_same_filtered_order_and_safe_text():
    stats = fake_stats()
    csv_bytes, count = export_issue_rows(stats, file_format="csv", label_id=1, building="致德樓8F")
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    parsed = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    assert count == 2
    assert parsed[0] == [
        "設備編號",
        "異常分類",
        "棟別樓層",
        "年份",
        "月份／批次",
        "根目錄",
        "標記時間",
        "照片相對路徑",
    ]
    assert parsed[1][0] == "致-08-001"
    assert parsed[2][0] == "'=1+2"
    assert parsed[1][1] == parsed[2][1] == "瓶身超過10年"

    excel_bytes, excel_count = export_issue_rows(
        stats, file_format="xlsx", label_id=1, building="致德樓8F"
    )
    assert excel_count == count
    wb = load_workbook(io.BytesIO(excel_bytes))
    ws = wb.active
    assert [c.value for c in ws[1]] == parsed[0]
    assert [c.value for c in ws[2]] == parsed[1]
    assert [c.value for c in ws[3]] == parsed[2]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:H3"
    assert ws["A3"].data_type == "s"
    wb.close()


def test_issue_export_conflict_does_not_write_file(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIRELENS_EXPORT_DIR", str(tmp_path / "exports"))
    # Synthetic Google-independent API response, no user photo or ledger reads.
    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "issue_statistics", lambda conn, root_id: fake_stats())
    with TestClient(create_app()) as client:
        mismatch = client.post(
            "/api/issues/export/save",
            json={
                "format": "csv",
                "expected_row_count": 1,
                "label_id": 1,
                "building": "致德樓8F",
            },
        )
        assert mismatch.status_code == 409, mismatch.text
        assert list((tmp_path / "exports").glob("*")) == []

        saved = client.post(
            "/api/issues/export/save",
            json={
                "format": "xlsx",
                "expected_row_count": 2,
                "label_id": 1,
                "building": "致德樓8F",
            },
        )
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["saved"] is True and body["row_count"] == 2
        assert Path(body["path"]).is_file()
        assert Path(body["path"]).suffix == ".xlsx"
        assert body["filename"].startswith("FireLens-異常設備清單-")
        assert len(body["open_token"]) > 10
        assert len(list((tmp_path / "exports").glob("*.xlsx"))) == 1

        zero = client.post(
            "/api/issues/export/save",
            json={"format": "csv", "expected_row_count": 0, "query": "no-matches"},
        )
        assert zero.status_code == 400
        assert len(list((tmp_path / "exports").glob("*"))) == 1

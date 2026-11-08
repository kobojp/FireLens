"""Isolation of extinguisher/box/lamp reconciliation and exports, using synthetic photos."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from openpyxl import load_workbook

from backend.app.db import connect
from backend.app.reconcile import build_reconciliation, export_reconciliation, import_ledger
from tests.test_m3 import add_root_and_scan
from tests.test_m17 import _folder


def test_three_category_search_period_and_exports_are_independent(
    db_path: Path, sample_source: Path
) -> None:
    code = "致-08-66"
    # Same code in all 3 categories, and two extinguisher periods.
    _folder(sample_source, "滅火器", "10月份更換", code, ("編號", "藥劑", "完成"))
    _folder(sample_source, "滅火器", "11月份更換", code, ())
    _folder(sample_source, "放置盒", "11月份更換", code, ("前", "中"))
    _folder(sample_source, "燈具", "12月份更換", code, ("前", "中", "後"))
    _folder(sample_source, "放置盒", "11月份更換", "致-08-67", ("前", "中", "後"))
    root_id = add_root_and_scan(db_path, sample_source)
    conn = connect(db_path)
    try:
        ledger_id = import_ledger(
            conn,
            name="三類核對合成清冊",
            source_type="text",
            rows=[
                {"section": "", "device_no": code, "specification": "", "last_replacement_date": ""}
            ],
        )
        expected = [
            ("extinguisher", "10月份更換", "complete", []),
            ("extinguisher", "11月份更換", "empty_folder", ["編號", "藥劑", "完成"]),
            ("box", "11月份更換", "missing_photo", ["後"]),
            ("lamp", "12月份更換", "complete", []),
            ("box", "10月份更換", "no_folder", []),
            ("lamp", "11月份更換", "no_folder", []),
        ]
        for category, period, status, missing in expected:
            result = build_reconciliation(
                conn,
                root_id=root_id,
                ledger_id=ledger_id,
                category_code=category,
                period=period,
            )
            assert result["category_code"] == category
            assert result["period"] == period
            assert result["total"] == len(result["rows"]) == 1
            row = result["rows"][0]
            assert row["category"] == category
            assert row["device_no"] == code
            assert row["status"] == status
            if status not in {"no_folder", "complete"}:
                assert row["missing_slots"] == missing
            folder_label = {
                "extinguisher": "滅火器",
                "box": "放置盒",
                "lamp": "燈具",
            }[category]
            assert all(folder_label in found["relative_path"] for found in row["found"])

            csv_bytes, _, _ = export_reconciliation(result, "csv")
            data = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
            assert len(data) == (1 if status == "complete" else 2)
            if status != "complete":
                assert (
                    data[1][0]
                    == {"extinguisher": "滅火器", "box": "放置盒", "lamp": "燈具"}[category]
                )
                assert data[1][1] == code
                if category == "box" and period == "11月份更換":
                    assert "後" in data[1][4]
                assert "致-08-67" not in str(data)
            xlsx_bytes, _, _ = export_reconciliation(result, "xlsx")
            book = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
            try:
                assert book.active.max_row == len(data)
                if status != "complete":
                    assert book.active["B2"].value == code
            finally:
                book.close()

        # Omitting period means all months of only the chosen category, so
        # duplicate same-category codes are correctly reported, not cross-category.
        all_extinguishers = build_reconciliation(
            conn, root_id=root_id, ledger_id=ledger_id, category_code="extinguisher"
        )
        assert all_extinguishers["rows"][0]["status"] == "duplicate_number"
        all_boxes = build_reconciliation(
            conn, root_id=root_id, ledger_id=ledger_id, category_code="box"
        )
        assert all_boxes["rows"][0]["status"] == "missing_photo"
        assert all_boxes["total"] == 1  # extra folder not counted
    finally:
        conn.close()

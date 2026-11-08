"""Trailing parenthetical annotation matching without false prefix or category crossover."""

from __future__ import annotations

import csv
import io

from openpyxl import load_workbook

from backend.app.db import connect
from backend.app.reconcile import (
    build_reconciliation,
    export_reconciliation,
    import_ledger,
    reshoot_text,
)
from tests.test_m3 import add_root_and_scan
from tests.test_m17 import _folder


def _ledger(conn, device: str):
    return import_ledger(
        conn,
        name="備註安全核對",
        source_type="text",
        rows=[
            {"section": "", "device_no": device, "specification": "", "last_replacement_date": ""}
        ],
    )


def test_exact_name_overrides_annotation_and_never_false_prefix(db_path, sample_source):
    _folder(sample_source, "滅火器", "11月份更換", "致-08-66", ("編號", "藥劑", "完成"))
    _folder(sample_source, "滅火器", "11月份更換", "致-08-66(失壓)", ("編號",))
    _folder(sample_source, "滅火器", "11月份更換", "致-08-660(失壓)", ("編號",))
    _folder(sample_source, "滅火器", "11月份更換", "致-08-67(失壓)", ("編號",))
    root = add_root_and_scan(db_path, sample_source)
    conn = connect(db_path)
    try:
        ledger = _ledger(conn, "致-08-66")
        result = build_reconciliation(
            conn,
            root_id=root,
            ledger_id=ledger,
            category_code="extinguisher",
            period="11月份更換",
        )
        row = result["rows"][0]
        assert row["classification"] == "complete"
        assert not row["matched_by_note"]
        assert row["matched_folder_name"] == "致-08-66"
        assert row["found"][0]["relative_path"].endswith("/致-08-66")
        assert reshoot_text(result) == ""
    finally:
        conn.close()


def test_unique_fullwidth_note_matches_csv_excel_and_reshoot(db_path, sample_source):
    _folder(sample_source, "滅火器", "11月份更換", "致-08-66（壓力錶故障）", ("編號",))
    _folder(sample_source, "放置盒", "11月份更換", "致-08-66", ("前", "中", "後"))
    root = add_root_and_scan(db_path, sample_source)
    conn = connect(db_path)
    try:
        ledger = _ledger(conn, "致-08-66")
        result = build_reconciliation(
            conn,
            root_id=root,
            ledger_id=ledger,
            category_code="extinguisher",
        )
        row = result["rows"][0]
        assert row["device_no"] == "致-08-66"
        assert row["matched_by_note"] is True
        assert row["matched_folder_name"] == "致-08-66（壓力錶故障）"
        assert row["missing_slots"] == ["藥劑", "完成"]
        assert "實際資料夾：致-08-66（壓力錶故障）" in reshoot_text(result)
        csv_bytes, _, _ = export_reconciliation(result, "csv")
        csv_rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
        assert len(csv_rows) == 2
        assert csv_rows[1][-2:] == ["致-08-66（壓力錶故障）", "忽略尾端備註"]
        xlsx_bytes, _, _ = export_reconciliation(result, "xlsx")
        wb = load_workbook(io.BytesIO(xlsx_bytes), read_only=True)
        try:
            assert wb.active["K2"].value == "致-08-66（壓力錶故障）"
            assert wb.active["L2"].value == "忽略尾端備註"
        finally:
            wb.close()
    finally:
        conn.close()


def test_ambiguous_note_match_and_cross_months_never_choose_randomly(db_path, sample_source):
    _folder(sample_source, "滅火器", "11月份更換", "致-08-66(失壓)", ("編號",))
    _folder(sample_source, "滅火器", "10月份更換", "致-08-66（故障）", ("編號",))
    root = add_root_and_scan(db_path, sample_source)
    conn = connect(db_path)
    try:
        ledger = _ledger(conn, "致-08-66")
        across = build_reconciliation(conn, root_id=root, ledger_id=ledger)
        assert across["rows"][0]["status"] == "duplicate_number"
        assert across["rows"][0]["matched_folder_name"] is None
        scoped = build_reconciliation(
            conn,
            root_id=root,
            ledger_id=ledger,
            period="11月份更換",
        )
        assert scoped["rows"][0]["matched_by_note"] is True
        assert len(scoped["rows"][0]["found"]) == 1
    finally:
        conn.close()


def test_prefix_nonterminal_and_different_category_do_not_match(db_path, sample_source):
    _folder(sample_source, "滅火器", "11月份更換", "致-08-660", ("編號",))
    _folder(sample_source, "放置盒", "11月份更換", "致-08-66(失壓)", ("前", "中", "後"))
    root = add_root_and_scan(db_path, sample_source)
    conn = connect(db_path)
    try:
        ledger = _ledger(conn, "致-08-66")
        result = build_reconciliation(
            conn,
            root_id=root,
            ledger_id=ledger,
            category_code="extinguisher",
            period="11月份更換",
        )
        assert result["rows"][0]["status"] in ("near_number", "no_folder")
        assert result["rows"][0]["matched_by_note"] is False
        assert result["rows"][0]["found"] == []
    finally:
        conn.close()

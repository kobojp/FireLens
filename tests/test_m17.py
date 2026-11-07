"""M17: category-isolated reconciliation and safe trailing-note folder matching."""

from pathlib import Path

import pytest

from backend.app.db import connect
from backend.app.reconcile import ReconcileError, build_reconciliation, import_ledger
from tests.test_m3 import add_root_and_scan


def _folder(root: Path, category: str, period: str, code: str, slots: tuple[str, ...]) -> None:
    folder = root / category / "2026年" / period / "中正樓" / code
    folder.mkdir(parents=True, exist_ok=True)
    for slot in slots:
        (folder / f"{slot}.jpg").write_bytes(slot.encode())


def test_category_selection_and_annotation_safety(db_path: Path, sample_source: Path) -> None:
    _folder(sample_source, "滅火器", "11月份更換", "致-08-66(失壓)", ("編號", "藥劑", "完成"))
    _folder(sample_source, "滅火器", "11月份更換", "致-08-67", ("編號",))
    _folder(sample_source, "放置盒", "10月份更換", "致-08-66", ("前", "中", "後"))
    _folder(sample_source, "燈具", "9月份更換", "致-08-66（故障）", ("前", "中", "後"))
    root_id = add_root_and_scan(db_path, sample_source)
    conn = connect(db_path)
    try:
        ledger_id = import_ledger(
            conn,
            name="M17",
            source_type="text",
            rows=[
                {
                    "section": "",
                    "device_no": "致-08-66",
                    "specification": "",
                    "last_replacement_date": "",
                },
                {
                    "section": "",
                    "device_no": "致-08-68",
                    "specification": "",
                    "last_replacement_date": "",
                },
            ],
        )
        for category, matched, period in [
            ("extinguisher", True, "11月份更換"),
            ("box", False, "10月份更換"),
            ("lamp", True, "9月份更換"),
        ]:
            result = build_reconciliation(
                conn, root_id=root_id, ledger_id=ledger_id, category_code=category
            )
            assert len(result["rows"]) == 2
            assert result["category_code"] == category
            first, second = result["rows"]
            assert first["status"] == "complete"
            assert first["matched_by_note"] is matched
            assert first["found"][0]["period"] == period
            assert second["status"] == "no_folder"
        with pytest.raises(ReconcileError):
            build_reconciliation(
                conn, root_id=root_id, ledger_id=ledger_id, category_code="invalid"
            )
        scoped = build_reconciliation(
            conn,
            root_id=root_id,
            ledger_id=ledger_id,
            category_code="extinguisher",
            period="10月份更換",
        )
        assert scoped["rows"][0]["status"] == "no_folder"
    finally:
        conn.close()


def test_annotation_ambiguity_never_auto_selects(db_path: Path, sample_source: Path) -> None:
    for code in ("致-08-66(失壓)", "致-08-66（故障）"):
        _folder(sample_source, "滅火器", "11月份更換", code, ("編號", "藥劑", "完成"))
    root_id = add_root_and_scan(db_path, sample_source)
    conn = connect(db_path)
    try:
        ledger_id = import_ledger(
            conn,
            name="ambiguous",
            source_type="text",
            rows=[
                {
                    "section": "",
                    "device_no": "致-08-66",
                    "specification": "",
                    "last_replacement_date": "",
                }
            ],
        )
        row = build_reconciliation(conn, root_id=root_id, ledger_id=ledger_id)["rows"][0]
        assert row["status"] == "duplicate_number"
        assert len(row["found"]) == 2
        assert row["matched_folder_name"] is None
    finally:
        conn.close()


def test_issue_export_filters_and_safe_file_capability(tmp_path: Path, monkeypatch) -> None:
    import csv
    import io

    from openpyxl import load_workbook

    from backend.app.export_files import ExportActionError, ExportRegistry, export_issue_rows

    stats = {
        "labels": [{"id": 1, "name": "瓶身超過10年"}, {"id": 2, "name": "無法辨識"}],
        "items": [
            {
                "label_id": 1,
                "building": "中正樓",
                "device_code": "致-08-66",
                "root_name": "滅火器更換照片",
                "item_relative_path": "滅火器/致-08-66",
                "year": "2026年",
                "period": "11月份更換",
                "updated_at": "2026-11-07",
            },
            {
                "label_id": 2,
                "building": "思源樓",
                "device_code": "=danger",
                "root_name": "滅火器更換照片",
                "item_relative_path": "滅火器/=danger",
                "year": "2026年",
                "period": "10月份更換",
                "updated_at": "2026-11-07",
            },
        ],
    }
    csv_bytes, count = export_issue_rows(stats, file_format="csv", label_id=1, building="中正樓")
    assert count == 1
    assert "致-08-66" in csv_bytes.decode("utf-8-sig")
    assert "=danger" not in csv_bytes.decode("utf-8-sig")
    all_csv, _ = export_issue_rows(stats, file_format="csv")
    cells = list(csv.reader(io.StringIO(all_csv.decode("utf-8-sig"))))
    assert cells[2][0] == "'=danger"
    xlsx_bytes, excel_count = export_issue_rows(stats, file_format="xlsx", query="致-08-66")
    assert excel_count == 1
    book = load_workbook(io.BytesIO(xlsx_bytes), read_only=True)
    assert book.active.max_row == 2
    book.close()
    with pytest.raises(ExportActionError):
        export_issue_rows(stats, file_format="csv", query="not-found")

    monkeypatch.setenv("FIRELENS_EXPORT_DIR", str(tmp_path))
    registry = ExportRegistry()
    saved = registry.save(prefix="測試", content=csv_bytes, extension="csv")
    assert Path(saved["path"]).read_bytes() == csv_bytes
    with pytest.raises(ExportActionError):
        registry.open(token="arbitrary-path-token", mode="file")
    Path(saved["path"]).unlink()
    with pytest.raises(ExportActionError, match="刪除"):
        registry.open(token=str(saved["open_token"]), mode="file")


def test_create_year_folder_scoped_to_category(db_path: Path, sample_source: Path) -> None:
    from backend.app.storage import create_year_folder
    from backend.app.tree import build_tree

    root_id = add_root_and_scan(db_path, sample_source)
    conn = connect(db_path)
    try:
        created = create_year_folder(conn, root_id, "lamp", "2027年")
        assert created["created"] is True
        assert (sample_source / "燈具" / "2027年").is_dir()
        tree = build_tree(conn, root_id)
        lamp = next(x for x in tree if x["key"] == "lamp")
        assert any(year["label"] == "2027年" for year in lamp["children"])
        duplicate = create_year_folder(conn, root_id, "lamp", "2027年")
        assert duplicate["created"] is False
    finally:
        conn.close()

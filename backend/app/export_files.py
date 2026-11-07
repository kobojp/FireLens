"""Safe local exports; only freshly-created files may be opened from the UI."""

from __future__ import annotations

import csv
import io
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
from uuid import uuid4

from openpyxl import Workbook


class ExportActionError(ValueError):
    pass


def _escape_cell(value: object) -> str:
    """Prevent spreadsheet formula injection from user-supplied names/codes."""
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def export_issue_rows(
    stats: dict[str, object],
    *,
    label_id: int | None = None,
    building: str = "",
    query: str = "",
    file_format: str,
) -> tuple[bytes, int]:
    if file_format not in {"csv", "xlsx"}:
        raise ExportActionError("僅支援匯出 CSV 或 Excel")
    label_names = {int(label["id"]): str(label["name"]) for label in stats["labels"]}
    filtered = []
    for item in stats["items"]:
        if label_id is not None and item["label_id"] != label_id:
            continue
        if building and item["building"] != building:
            continue
        if (
            query
            and query.casefold()
            not in " ".join(
                str(item.get(key) or "")
                for key in ("device_code", "root_name", "item_relative_path")
            ).casefold()
        ):
            continue
        filtered.append(item)
    if not filtered:
        raise ExportActionError("目前篩選條件沒有可匯出的異常設備")
    headers = [
        "設備編號",
        "異常分類",
        "棟別樓層",
        "年份",
        "月份／批次",
        "根目錄",
        "標記時間",
        "照片相對路徑",
    ]
    rows = [
        [
            item["device_code"],
            label_names.get(int(item["label_id"]), ""),
            item["building"] or "來源未連線／待重新關聯",
            item["year"] or "",
            item["period"] or "",
            item["root_name"],
            item["updated_at"],
            item["item_relative_path"],
        ]
        for item in filtered
    ]
    if file_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows([[_escape_cell(cell) for cell in row] for row in rows])
        return output.getvalue().encode("utf-8-sig"), len(rows)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "異常設備清單"
    sheet.append(headers)
    for row in rows:
        sheet.append([_escape_cell(cell) for cell in row])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column, width in {
        "A": 21,
        "B": 24,
        "C": 23,
        "D": 12,
        "E": 22,
        "F": 25,
        "G": 22,
        "H": 65,
    }.items():
        sheet.column_dimensions[column].width = width
    data = io.BytesIO()
    workbook.save(data)
    workbook.close()
    return data.getvalue(), len(rows)


class ExportRegistry:
    def __init__(self) -> None:
        self._files: dict[str, tuple[Path, Path, int]] = {}
        self._lock = Lock()

    def save(self, *, prefix: str, content: bytes, extension: str) -> dict[str, object]:
        if extension not in {"csv", "xlsx"}:
            raise ExportActionError("不支援的匯出格式")
        folder = Path(
            os.environ.get("FIRELENS_EXPORT_DIR") or Path.home() / "Downloads" / "FireLens"
        )
        folder.mkdir(parents=True, exist_ok=True)
        target = (
            folder
            / f"FireLens-{prefix}-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.{extension}"
        )
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=folder, prefix=".firelens-", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.rename(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        token = token_urlsafe(24)
        with self._lock:
            # Limit in-memory capabilities; restart revokes all old tokens.
            if len(self._files) >= 60:
                self._files.pop(next(iter(self._files)))
            self._files[token] = (target.resolve(), folder.resolve(), len(content))
        return {
            "saved": True,
            "path": str(target),
            "filename": target.name,
            "size": len(content),
            "open_token": token,
        }

    def open(self, *, token: str, mode: str) -> None:
        if mode not in {"file", "folder"}:
            raise ExportActionError("不支援的開啟方式")
        with self._lock:
            selected = self._files.get(token)
        if selected is None:
            raise ExportActionError("匯出檔案已過期，請重新匯出")
        path, folder, expected_size = selected
        if (
            not path.is_file()
            or path.is_symlink()
            or path.suffix.lower() not in {".csv", ".xlsx"}
            or path.parent.resolve() != folder
            or path.stat().st_size != expected_size
        ):
            raise ExportActionError("匯出檔案已移動、刪除或變更，請重新匯出")
        if os.name != "nt":
            raise ExportActionError("開啟本機檔案僅支援 Windows 桌面版")
        if mode == "file":
            os.startfile(str(path))
        else:
            subprocess.Popen(["explorer.exe", str(folder)], shell=False)

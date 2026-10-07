from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

REQUIRED_HEADERS = ("區段", "設備名稱", "型式規格", "上次更換日")
REQUIRED_SLOTS = ("編號", "藥劑", "完成")
SPECIAL_PERIODS = {
    "5P 二氧化碳滅火器",
    "壓力錶壞",
    "新增5P 二氧化碳(含放置盒)",
}
DEFAULT_ALIASES = {
    "第一區": "一區",
    "第二區": "二區",
    "B棟異體": "B棟",
}
FLOOR_SUFFIX_RE = re.compile(r"(?:B\d+F|\d+F|1X|1M|RF)$", re.IGNORECASE)
STATUS_LABELS = {
    "complete": "完整",
    "missing_photo": "缺照片",
    "no_folder": "無資料夾",
    "empty_folder": "空資料夾",
    "zero_byte": "0 byte",
    "cloud_not_downloaded": "雲端未下載",
    "invalid_naming": "命名異常",
    "extra_folder": "清冊外資料夾",
    "duplicate_number": "重複編號",
    "near_number": "近似編號",
    "legacy": "舊制／待確認",
    "special": "特例",
}
CATEGORY_LABELS = {"extinguisher": "滅火器", "box": "放置盒", "lamp": "燈具"}


class ReconcileError(ValueError):
    pass


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _date_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value)


def _row(
    section: object, device: object, specification: object, replaced: object
) -> dict[str, str]:
    return {
        "section": _text(section),
        "device_no": _text(device),
        "specification": _text(specification),
        "last_replacement_date": _date_text(replaced),
    }


def parse_excel_bytes(data: bytes) -> list[dict[str, str]]:
    if not data:
        raise ReconcileError("Excel 檔案是空的")
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ReconcileError("無法讀取 Excel，請確認是有效的 .xlsx 檔案") from exc

    try:
        sheet = workbook.active
        iterator = sheet.iter_rows(values_only=True)
        header = next(iterator, None)
        if header is None:
            raise ReconcileError("Excel 沒有資料")
        header_map = {_text(value): index for index, value in enumerate(header)}
        missing = [name for name in REQUIRED_HEADERS if name not in header_map]
        if missing:
            raise ReconcileError(f"Excel 缺少欄位：{'、'.join(missing)}")

        rows: list[dict[str, str]] = []
        for values in iterator:
            device = (
                values[header_map["設備名稱"]] if header_map["設備名稱"] < len(values) else None
            )
            if not _text(device):
                continue
            rows.append(
                _row(
                    values[header_map["區段"]] if header_map["區段"] < len(values) else None,
                    device,
                    values[header_map["型式規格"]]
                    if header_map["型式規格"] < len(values)
                    else None,
                    values[header_map["上次更換日"]]
                    if header_map["上次更換日"] < len(values)
                    else None,
                )
            )
        if not rows:
            raise ReconcileError("Excel 找不到有效設備資料")
        return rows
    finally:
        workbook.close()


def parse_text_rows(text: str) -> list[dict[str, str]]:
    lines = [line.strip("\ufeff\r") for line in text.splitlines() if line.strip()]
    if not lines:
        raise ReconcileError("貼上的清冊文字是空的")

    delimiter = "\t" if any("\t" in line for line in lines[:3]) else ","
    parsed = list(csv.reader(lines, delimiter=delimiter))
    if len(parsed[0]) == 1 and delimiter == ",":
        parsed = [re.split(r"\s{2,}", line.strip()) for line in lines]

    first = [_text(value) for value in parsed[0]]
    has_header = "設備名稱" in first
    rows: list[dict[str, str]] = []
    if has_header:
        header_map = {name: index for index, name in enumerate(first)}
        if "設備名稱" not in header_map:
            raise ReconcileError("文字清冊缺少設備名稱欄位")
        body = parsed[1:]
        for values in body:
            device_index = header_map["設備名稱"]
            device = values[device_index] if device_index < len(values) else ""
            if not _text(device):
                continue
            rows.append(
                _row(
                    values[header_map["區段"]]
                    if "區段" in header_map and header_map["區段"] < len(values)
                    else "",
                    device,
                    values[header_map["型式規格"]]
                    if "型式規格" in header_map and header_map["型式規格"] < len(values)
                    else "",
                    values[header_map["上次更換日"]]
                    if "上次更換日" in header_map and header_map["上次更換日"] < len(values)
                    else "",
                )
            )
    else:
        for values in parsed:
            values = [_text(value) for value in values]
            if not values:
                continue
            if len(values) == 1:
                rows.append(_row("", values[0], "", ""))
            else:
                padded = (values + ["", "", "", ""])[:4]
                rows.append(_row(*padded))

    if not rows:
        raise ReconcileError("文字清冊找不到有效設備資料")
    return rows


def import_ledger(
    conn: sqlite3.Connection,
    *,
    name: str,
    source_type: str,
    rows: list[dict[str, str]],
    source_bytes: bytes | None = None,
) -> int:
    if source_type not in {"xlsx", "text"}:
        raise ReconcileError("不支援的清冊來源類型")
    if not rows:
        raise ReconcileError("清冊沒有有效資料")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest() if source_bytes is not None else None
    with conn:
        cursor = conn.execute(
            "INSERT INTO ledger(name, source_type, source_sha256) VALUES (?, ?, ?)",
            (name.strip() or "未命名清冊", source_type, source_sha256),
        )
        ledger_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO ledger_row(
                ledger_id, row_no, section, device_no, specification,
                last_replacement_date, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    ledger_id,
                    index,
                    row["section"],
                    row["device_no"],
                    row["specification"],
                    row["last_replacement_date"],
                    json.dumps(row, ensure_ascii=False),
                )
                for index, row in enumerate(rows, start=1)
            ],
        )
    return ledger_id


def list_ledgers(conn: sqlite3.Connection) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT l.id, l.name, l.source_type, l.imported_at, l.source_sha256,
                   COUNT(r.id) AS row_count
            FROM ledger AS l
            LEFT JOIN ledger_row AS r ON r.ledger_id = l.id
            GROUP BY l.id
            ORDER BY l.id DESC
            """
        )
    ]


def seed_default_aliases(conn: sqlite3.Connection) -> None:
    with conn:
        for source, target in DEFAULT_ALIASES.items():
            conn.execute(
                """
                INSERT INTO alias_map(alias_type, source_value, target_value, confirmed)
                VALUES ('building', ?, ?, 1)
                ON CONFLICT(alias_type, source_value) DO NOTHING
                """,
                (source, target),
            )


def list_aliases(conn: sqlite3.Connection) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, alias_type, source_value, target_value, confirmed
            FROM alias_map ORDER BY source_value
            """
        )
    ]


def save_alias(
    conn: sqlite3.Connection,
    source_value: str,
    target_value: str,
    *,
    confirmed: bool = True,
) -> dict[str, object]:
    source = source_value.strip()
    target = target_value.strip()
    if not source or not target:
        raise ReconcileError("別名來源與目標都不可為空")
    with conn:
        conn.execute(
            """
            INSERT INTO alias_map(alias_type, source_value, target_value, confirmed)
            VALUES ('building', ?, ?, ?)
            ON CONFLICT(alias_type, source_value)
            DO UPDATE SET target_value = excluded.target_value, confirmed = excluded.confirmed
            """,
            (source, target, int(confirmed)),
        )
    row = conn.execute(
        """
        SELECT id, alias_type, source_value, target_value, confirmed
        FROM alias_map WHERE alias_type='building' AND source_value=?
        """,
        (source,),
    ).fetchone()
    assert row is not None
    return dict(row)


def _alias_map(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row["source_value"]: row["target_value"]
        for row in conn.execute(
            """
            SELECT source_value, target_value FROM alias_map
            WHERE alias_type='building' AND confirmed=1
            """
        )
    }


def normalize_building(value: str, aliases: dict[str, str]) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().replace(" ", "")
    for source in sorted(aliases, key=len, reverse=True):
        source_normalized = unicodedata.normalize("NFKC", source).replace(" ", "")
        if normalized.startswith(source_normalized):
            target = unicodedata.normalize("NFKC", aliases[source]).replace(" ", "")
            normalized = target + normalized[len(source_normalized) :]
            break
    normalized = FLOOR_SUFFIX_RE.sub("", normalized)
    return normalized


def _dirty_name_suggestion(filename: str) -> str | None:
    stem = Path(filename).stem.strip()
    cleaned = stem.replace("‵", "").replace("`", "").strip(" ._")
    cleaned = re.sub(r"\s*\(\d+\)$", "", cleaned)
    aliases = {
        "編輯": "編號",
        "編號": "編號",
        "藥劑": "藥劑",
        "有效日期": "藥劑",
        "成": "完成",
        "完成": "完成",
    }
    suggestion = aliases.get(cleaned)
    if suggestion and f"{suggestion}.jpg".casefold() != filename.casefold():
        return f"{suggestion}.jpg"
    return None


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def _near_candidates(device_no: str, item_codes: list[str]) -> list[str]:
    target_parts = device_no.split("-")
    if len(target_parts) < 2:
        return []
    candidates: list[str] = []
    for code in item_codes:
        parts = code.split("-")
        if len(parts) != len(target_parts):
            continue
        if parts[:-1] != target_parts[:-1]:
            continue
        target_tail = target_parts[-1]
        candidate_tail = parts[-1]
        if abs(len(candidate_tail) - len(target_tail)) != 1:
            continue
        if _levenshtein(candidate_tail, target_tail) == 1:
            candidates.append(code)
    return sorted(set(candidates))[:5]


def _item_payload(conn: sqlite3.Connection, item: sqlite3.Row) -> dict[str, object]:
    photos = list(
        conn.execute(
            """
            SELECT id, filename, relative_path, slot, size_bytes, cloud_placeholder
            FROM photo WHERE item_id=? ORDER BY filename COLLATE NOCASE
            """,
            (item["id"],),
        )
    )
    slots = {row["slot"] for row in photos if row["slot"]}
    missing_slots = [slot for slot in REQUIRED_SLOTS if slot not in slots]
    suggestions = [
        {"filename": row["filename"], "suggestion": suggestion}
        for row in photos
        if row["slot"] is None and (suggestion := _dirty_name_suggestion(row["filename"]))
    ]
    if any(row["cloud_placeholder"] for row in photos):
        status = "cloud_not_downloaded"
    elif any(int(row["size_bytes"]) <= 0 for row in photos):
        status = "zero_byte"
    elif suggestions:
        status = "invalid_naming"
    elif missing_slots:
        status = "missing_photo"
    else:
        status = "complete"
    if not photos:
        status = "empty_folder"
    return {
        "item_id": item["id"],
        "year": item["year"],
        "period": item["period"],
        "building": item["building"],
        "relative_path": item["relative_path"],
        "photo_count": item["photo_count"],
        "missing_slots": missing_slots,
        "naming_suggestions": suggestions,
        "status": status,
    }


def _slot_only_payload(conn: sqlite3.Connection, item: sqlite3.Row) -> dict[str, object]:
    photos = list(
        conn.execute(
            """
            SELECT id, filename, relative_path, slot, size_bytes, cloud_placeholder
            FROM photo WHERE item_id=? ORDER BY filename COLLATE NOCASE
            """,
            (item["id"],),
        )
    )
    required_slots = tuple(json.loads(item["slots_json"]))
    present_slots = {row["slot"] for row in photos if row["slot"]}
    missing_slots = [slot for slot in required_slots if slot not in present_slots]
    if item["period"] in SPECIAL_PERIODS:
        status = "special"
        missing_slots = []
    elif item["status"] == "legacy" or (
        item["category_code"] == "lamp" and item["status"] == "unknown"
    ):
        status = "legacy"
        missing_slots = []
    elif not photos:
        status = "empty_folder"
    elif any(row["cloud_placeholder"] for row in photos):
        status = "cloud_not_downloaded"
    elif any(int(row["size_bytes"]) <= 0 for row in photos):
        status = "zero_byte"
    elif not missing_slots:
        status = "complete"
    elif present_slots:
        status = "missing_photo"
    else:
        status = "invalid_naming"
    return {
        "item_id": item["id"],
        "year": item["year"],
        "period": item["period"],
        "building": item["building"],
        "relative_path": item["relative_path"],
        "photo_count": item["photo_count"],
        "missing_slots": missing_slots,
        "naming_suggestions": [],
        "status": status,
    }


def set_reshoot_mark(
    conn: sqlite3.Connection,
    *,
    root_id: int,
    ledger_id: int,
    category_code: str,
    device_no: str,
    marked: bool,
) -> None:
    if not device_no.strip():
        raise ReconcileError("設備編號不可為空")
    with conn:
        conn.execute(
            """
            INSERT INTO reshoot_mark(
                root_id, ledger_id, category_code, device_no, marked, marked_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(root_id, ledger_id, category_code, device_no)
            DO UPDATE SET marked=excluded.marked, marked_at=CURRENT_TIMESTAMP
            """,
            (root_id, ledger_id, category_code, device_no, int(marked)),
        )


def _reshoot_marks(conn: sqlite3.Connection, root_id: int, ledger_id: int) -> set[tuple[str, str]]:
    return {
        (row["category_code"], row["device_no"])
        for row in conn.execute(
            """
            SELECT category_code, device_no FROM reshoot_mark
            WHERE root_id=? AND ledger_id=? AND marked=1
            """,
            (root_id, ledger_id),
        )
    }


def build_reconciliation(
    conn: sqlite3.Connection,
    *,
    root_id: int,
    ledger_id: int,
    period: str | None = None,
) -> dict[str, object]:
    seed_default_aliases(conn)
    root = conn.execute("SELECT id FROM root WHERE id=?", (root_id,)).fetchone()
    if root is None:
        raise ReconcileError("找不到指定照片根目錄")
    ledger = conn.execute("SELECT id, name FROM ledger WHERE id=?", (ledger_id,)).fetchone()
    if ledger is None:
        raise ReconcileError("找不到指定清冊")

    aliases = _alias_map(conn)
    marked_pairs = _reshoot_marks(conn, root_id, ledger_id)
    ledger_rows = list(
        conn.execute(
            """
            SELECT row_no, section, device_no, specification, last_replacement_date
            FROM ledger_row WHERE ledger_id=? ORDER BY row_no
            """,
            (ledger_id,),
        )
    )
    item_query = """
        SELECT i.id, i.code, i.year, i.period, i.building, i.relative_path,
               i.status, i.photo_count
        FROM item AS i
        JOIN category AS c ON c.id=i.category_id
        WHERE i.root_id=? AND c.code='extinguisher'
    """
    params: list[object] = [root_id]
    if period:
        item_query += " AND i.period=?"
        params.append(period)
    items = list(conn.execute(item_query, params))

    items_by_code: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for item in items:
        items_by_code[item["code"]].append(item)
    item_codes = list(items_by_code)
    ledger_ids = [row["device_no"] for row in ledger_rows]
    ledger_id_counts = Counter(ledger_ids)
    rows: list[dict[str, object]] = []

    for ledger_row in ledger_rows:
        device_no = ledger_row["device_no"]
        expected_building = normalize_building(ledger_row["section"] or "", aliases)
        matches = items_by_code.get(device_no, [])
        base: dict[str, object] = {
            "kind": "ledger",
            "category": "extinguisher",
            "row_no": ledger_row["row_no"],
            "section": ledger_row["section"] or "",
            "expected_building": expected_building,
            "device_no": device_no,
            "specification": ledger_row["specification"] or "",
            "last_replacement_date": ledger_row["last_replacement_date"] or "",
            "found": [],
            "missing_slots": [],
            "naming_suggestions": [],
            "near_candidates": [],
            "marked_reshot": ("extinguisher", device_no) in marked_pairs,
        }
        if ledger_id_counts[device_no] > 1 or len(matches) > 1:
            base["status"] = "duplicate_number"
            base["found"] = [_item_payload(conn, item) for item in matches]
        elif not matches:
            near = _near_candidates(device_no, item_codes)
            base["near_candidates"] = near
            base["status"] = "near_number" if near else "no_folder"
        else:
            payload = _item_payload(conn, matches[0])
            base["status"] = payload["status"]
            base["found"] = [payload]
            base["missing_slots"] = payload["missing_slots"]
            base["naming_suggestions"] = payload["naming_suggestions"]
            actual_building = normalize_building(matches[0]["building"], aliases)
            base["building_match"] = not expected_building or expected_building == actual_building
        rows.append(base)

    ledger_set = set(ledger_ids)
    for code, code_items in sorted(items_by_code.items()):
        if code in ledger_set:
            continue
        for item in code_items:
            payload = _item_payload(conn, item)
            is_special = item["period"] in SPECIAL_PERIODS
            rows.append(
                {
                    "kind": "special" if is_special else "extra",
                    "category": "extinguisher",
                    "row_no": None,
                    "section": "",
                    "expected_building": "",
                    "device_no": code,
                    "specification": "",
                    "last_replacement_date": "",
                    "status": "special" if is_special else "extra_folder",
                    "found": [payload],
                    "missing_slots": [] if is_special else payload["missing_slots"],
                    "naming_suggestions": ([] if is_special else payload["naming_suggestions"]),
                    "near_candidates": [],
                    "marked_reshot": ("extinguisher", code) in marked_pairs,
                }
            )

    slot_query = """
        SELECT i.id, i.code, i.year, i.period, i.building, i.relative_path,
               i.status, i.photo_count, c.code AS category_code, c.name AS category_name,
               c.slots_json
        FROM item AS i
        JOIN category AS c ON c.id=i.category_id
        WHERE i.root_id=? AND c.code IN ('box', 'lamp')
    """
    slot_params: list[object] = [root_id]
    if period:
        slot_query += " AND i.period=?"
        slot_params.append(period)
    for slot_item in conn.execute(slot_query, slot_params):
        payload = _slot_only_payload(conn, slot_item)
        rows.append(
            {
                "kind": "slot_only",
                "category": slot_item["category_code"],
                "row_no": None,
                "section": slot_item["building"],
                "expected_building": normalize_building(slot_item["building"], aliases),
                "device_no": slot_item["code"],
                "specification": slot_item["category_name"],
                "last_replacement_date": "",
                "status": payload["status"],
                "found": [payload],
                "missing_slots": payload["missing_slots"],
                "naming_suggestions": [],
                "near_candidates": [],
                "marked_reshot": (slot_item["category_code"], slot_item["code"]) in marked_pairs,
            }
        )

    ledger_result_rows = [row for row in rows if row["kind"] == "ledger"]
    counts = Counter(str(row["status"]) for row in rows)
    complete_count = sum(row["status"] == "complete" for row in ledger_result_rows)
    total = len(ledger_result_rows)
    progress_acc: dict[str, Counter[str]] = defaultdict(Counter)
    for row in ledger_result_rows:
        building = str(row["expected_building"] or row["section"] or "未分類")
        progress_acc[building]["total"] += 1
        if row["status"] == "complete":
            progress_acc[building]["complete"] += 1
    building_progress = [
        {
            "building": building,
            "total": values["total"],
            "complete": values["complete"],
            "rate": round(values["complete"] * 100 / values["total"], 1)
            if values["total"]
            else 0.0,
        }
        for building, values in sorted(progress_acc.items())
    ]
    return {
        "root_id": root_id,
        "ledger_id": ledger_id,
        "ledger_name": ledger["name"],
        "period": period,
        "total": total,
        "complete": complete_count,
        "completion_rate": round(complete_count * 100 / total, 1) if total else 0.0,
        "counts": dict(sorted(counts.items())),
        "building_progress": building_progress,
        "rows": rows,
    }


def reshoot_rows(result: dict[str, object]) -> list[dict[str, object]]:
    return [
        row
        for row in result["rows"]  # type: ignore[index]
        if row["status"] not in {"complete", "legacy", "special"}
    ]


def reshoot_text(result: dict[str, object]) -> str:
    lines: list[str] = []
    for row in reshoot_rows(result):
        missing = "、".join(row.get("missing_slots", []))
        status_label = STATUS_LABELS.get(str(row["status"]), str(row["status"]))
        detail = f"缺：{missing}" if missing else status_label
        category = CATEGORY_LABELS.get(str(row.get("category", "")), str(row.get("category", "")))
        lines.append(f"{category}\t{row['device_no']}\t{row.get('section', '')}\t{detail}")
    return "\n".join(lines)


def export_reconciliation(result: dict[str, object], file_format: str) -> tuple[bytes, str, str]:
    rows = reshoot_rows(result)
    headers = [
        "類別",
        "設備編號",
        "區段",
        "狀態",
        "缺少槽位",
        "找到月份",
        "找到棟別",
        "相對路徑",
        "近似編號",
        "已補拍",
    ]
    body_rows: list[list[str]] = []
    for row in rows:
        found = row.get("found", [])
        found_periods = "、".join(str(item.get("period", "")) for item in found)
        found_buildings = "、".join(str(item.get("building", "")) for item in found)
        paths = "、".join(str(item.get("relative_path", "")) for item in found)
        body_rows.append(
            [
                CATEGORY_LABELS.get(str(row.get("category", "")), str(row.get("category", ""))),
                str(row.get("device_no", "")),
                str(row.get("section", "")),
                STATUS_LABELS.get(str(row.get("status", "")), str(row.get("status", ""))),
                "、".join(row.get("missing_slots", [])),
                found_periods,
                found_buildings,
                paths,
                "、".join(row.get("near_candidates", [])),
                "是" if row.get("marked_reshot") else "否",
            ]
        )

    if file_format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(body_rows)
        return stream.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "補拍清單.csv"
    if file_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "補拍清單"
        sheet.append(headers)
        for body in body_rows:
            sheet.append(body)
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            width = min(max(len(str(cell.value or "")) for cell in column) + 2, 60)
            sheet.column_dimensions[column[0].column_letter].width = width
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        return (
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "補拍清單.xlsx",
        )
    raise ReconcileError("匯出格式只支援 csv 或 xlsx")

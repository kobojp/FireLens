from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

DEFAULT_SETTINGS: dict[str, object] = {
    "theme": "system",
    "thumbnail_quality": 86,
    "slot_order": {
        "extinguisher": ["編號", "藥劑", "完成"],
        "box": ["前", "中", "後"],
        "lamp": ["前", "中", "後"],
    },
    "quick_create": {
        "category_code": "extinguisher",
        "year": "",
        "period": "",
        "building": "",
    },
    "custom_slots": {},
    "auto_scan_on_start": True,
    "auto_scan_min_interval_minutes": 5,
    "new_item_panel_open": True,
    "excluded_root_folders": [],
}

MAX_CUSTOM_SLOT_LENGTH = 20
MAX_CUSTOM_SLOTS_PER_CATEGORY = 30
_ILLEGAL_SLOT_CHARS = set('<>:"/\\|?*\x00')
_SUFFIX_RE = re.compile(r"-\d+$")


class SettingsError(ValueError):
    pass


def _decode(raw: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SettingsError("設定資料格式損壞") from exc


def get_setting(conn: sqlite3.Connection, key: str, default: object | None = None) -> object:
    row = conn.execute("SELECT value_json FROM setting WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    return _decode(str(row["value_json"]))


def get_settings(conn: sqlite3.Connection) -> dict[str, object]:
    settings = dict(DEFAULT_SETTINGS)
    rows = conn.execute("SELECT key, value_json FROM setting ORDER BY key").fetchall()
    for row in rows:
        key = str(row["key"])
        if key in DEFAULT_SETTINGS:
            settings[key] = _decode(str(row["value_json"]))
    return settings


def _validate_slot_order(conn: sqlite3.Connection, value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise SettingsError("槽位顯示順序格式不正確")
    known = {
        str(row["code"]): list(json.loads(str(row["slots_json"])))
        for row in conn.execute("SELECT code, slots_json FROM category")
    }
    result: dict[str, list[str]] = {}
    for code, slots in known.items():
        requested = value.get(code, slots)
        if not isinstance(requested, list) or not all(isinstance(slot, str) for slot in requested):
            raise SettingsError(f"{code} 的槽位順序格式不正確")
        if len(requested) != len(slots) or set(requested) != set(slots):
            raise SettingsError(f"{code} 的槽位順序必須包含且只能包含既有槽位")
        result[code] = list(requested)
    return result


def _validate_quick_create(conn: sqlite3.Connection, value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise SettingsError("快速建立設定格式不正確")
    allowed = {"category_code", "year", "period", "building"}
    unknown = set(value) - allowed
    if unknown:
        raise SettingsError(f"快速建立包含不支援欄位：{', '.join(sorted(unknown))}")
    defaults = DEFAULT_SETTINGS["quick_create"]
    assert isinstance(defaults, dict)
    result: dict[str, str] = {}
    for key in allowed:
        raw = value.get(key, defaults[key])
        if not isinstance(raw, str):
            raise SettingsError("快速建立設定必須是文字")
        clean = raw.strip()
        if len(clean) > 200:
            raise SettingsError("快速建立設定文字過長")
        result[key] = clean
    known_categories = {
        str(row["code"]) for row in conn.execute("SELECT code FROM category ORDER BY id")
    }
    if result["category_code"] not in known_categories:
        raise SettingsError("快速建立的類別不存在")
    return result


def custom_slots_for(conn: sqlite3.Connection, category_code: str) -> tuple[str, ...]:
    try:
        value = get_setting(conn, "custom_slots", {})
    except SettingsError:
        return ()
    if not isinstance(value, dict):
        return ()
    slots = value.get(category_code, [])
    if not isinstance(slots, list):
        return ()
    return tuple(slot for slot in slots if isinstance(slot, str))


def _validate_custom_slots(conn: sqlite3.Connection, value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise SettingsError("自訂槽位格式不正確")
    categories = {
        str(row["code"]): (
            list(json.loads(str(row["slots_json"]))),
            dict(json.loads(str(row["filename_aliases_json"]))),
        )
        for row in conn.execute("SELECT code, slots_json, filename_aliases_json FROM category")
    }
    unknown = set(value) - set(categories)
    if unknown:
        raise SettingsError(f"自訂槽位包含不存在的類別：{', '.join(sorted(unknown))}")
    result: dict[str, list[str]] = {}
    for code, (required, aliases) in categories.items():
        requested = value.get(code, [])
        if not isinstance(requested, list):
            raise SettingsError(f"{code} 的自訂槽位格式不正確")
        if len(requested) > MAX_CUSTOM_SLOTS_PER_CATEGORY:
            raise SettingsError(f"每個類別最多 {MAX_CUSTOM_SLOTS_PER_CATEGORY} 個自訂槽位")
        reserved = {name.casefold() for name in [*required, *aliases]}
        seen: set[str] = set()
        cleaned: list[str] = []
        for raw in requested:
            if not isinstance(raw, str):
                raise SettingsError("自訂槽位名稱必須是文字")
            name = raw.strip()
            if not name:
                raise SettingsError("自訂槽位名稱不可為空")
            if len(name) > MAX_CUSTOM_SLOT_LENGTH:
                raise SettingsError(f"自訂槽位名稱不可超過 {MAX_CUSTOM_SLOT_LENGTH} 字")
            if any(ord(ch) < 32 or ch in _ILLEGAL_SLOT_CHARS for ch in name):
                raise SettingsError(f"自訂槽位「{name}」含有不可用於檔名的字元")
            if name.endswith(".") or _SUFFIX_RE.search(name):
                raise SettingsError(f"自訂槽位「{name}」不可以句點或「-數字」結尾")
            key = name.casefold()
            if key in reserved:
                raise SettingsError(f"自訂槽位「{name}」與既有槽位或同義詞重複")
            if key in seen:
                raise SettingsError(f"自訂槽位「{name}」重複")
            seen.add(key)
            cleaned.append(name)
        result[code] = cleaned
    return result


# Hardcoded application directories are never eligible to be scanned as photos.
SYSTEM_EXCLUDED_ROOT_FOLDERS = frozenset(
    {"firelens-共享異常資料", "system volume information", "$recycle.bin"}
)


def excluded_root_folders(conn: sqlite3.Connection) -> frozenset[str]:
    value = get_setting(conn, "excluded_root_folders", [])
    if not isinstance(value, list):
        return SYSTEM_EXCLUDED_ROOT_FOLDERS
    return SYSTEM_EXCLUDED_ROOT_FOLDERS | frozenset(
        value_item.casefold() for value_item in value if isinstance(value_item, str)
    )


def _validate_excluded_root_folders(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 100:
        raise SettingsError("排除資料夾必須是最多 100 個名稱的清單")
    result: list[str] = []
    used: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            raise SettingsError("排除資料夾名稱必須是文字")
        name = raw.strip()
        if (
            not name
            or len(name) > 100
            or name in {".", ".."}
            or any(char in name for char in '/\\:*?"<>|\x00')
            or name.endswith(".")
            or name.endswith(" ")
        ):
            raise SettingsError("排除資料夾只允許有效的單層資料夾名稱")
        if name.casefold() not in used:
            used.add(name.casefold())
            result.append(name)
    return result


def save_settings(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, object]:
    allowed = {
        "theme",
        "thumbnail_quality",
        "slot_order",
        "quick_create",
        "custom_slots",
        "auto_scan_on_start",
        "auto_scan_min_interval_minutes",
        "new_item_panel_open",
        "excluded_root_folders",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise SettingsError(f"不支援的設定：{', '.join(sorted(unknown))}")

    updates: dict[str, object] = {}
    if "theme" in payload:
        theme = payload["theme"]
        if theme not in {"system", "light", "dark"}:
            raise SettingsError("主題只接受 system、light 或 dark")
        updates["theme"] = theme
    if "thumbnail_quality" in payload:
        quality = payload["thumbnail_quality"]
        if isinstance(quality, bool) or not isinstance(quality, int) or not 60 <= quality <= 95:
            raise SettingsError("縮圖品質必須是 60～95 的整數")
        updates["thumbnail_quality"] = quality
    if "slot_order" in payload:
        updates["slot_order"] = _validate_slot_order(conn, payload["slot_order"])
    if "quick_create" in payload:
        updates["quick_create"] = _validate_quick_create(conn, payload["quick_create"])
    if "custom_slots" in payload:
        updates["custom_slots"] = _validate_custom_slots(conn, payload["custom_slots"])
    if "auto_scan_on_start" in payload:
        enabled = payload["auto_scan_on_start"]
        if not isinstance(enabled, bool):
            raise SettingsError("啟動時自動掃描必須是布林值")
        updates["auto_scan_on_start"] = enabled
    if "auto_scan_min_interval_minutes" in payload:
        interval = payload["auto_scan_min_interval_minutes"]
        if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 1440:
            raise SettingsError("自動掃描間隔必須是 1～1440 分鐘的整數")
        updates["auto_scan_min_interval_minutes"] = interval
    if "excluded_root_folders" in payload:
        updates["excluded_root_folders"] = _validate_excluded_root_folders(
            payload["excluded_root_folders"]
        )
    if "new_item_panel_open" in payload:
        expanded = payload["new_item_panel_open"]
        if not isinstance(expanded, bool):
            raise SettingsError("新增編號資料夾展開狀態必須是布林值")
        updates["new_item_panel_open"] = expanded

    with conn:
        for key, value in updates.items():
            conn.execute(
                """
                INSERT INTO setting(key, value_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (key, json.dumps(value, ensure_ascii=False, separators=(",", ":"))),
            )
        if updates:
            conn.execute(
                """
                INSERT INTO audit_log(action, detail_json)
                VALUES ('update_settings', ?)
                """,
                (json.dumps({"keys": sorted(updates)}, ensure_ascii=False),),
            )
    return get_settings(conn)


def thumbnail_quality(conn: sqlite3.Connection) -> int:
    value = get_setting(conn, "thumbnail_quality", DEFAULT_SETTINGS["thumbnail_quality"])
    if isinstance(value, int) and not isinstance(value, bool) and 60 <= value <= 95:
        return value
    return int(DEFAULT_SETTINGS["thumbnail_quality"])


def update_category_slots(
    conn: sqlite3.Connection,
    category_code: str,
    slots: list[str],
    *,
    confirm_unmapped: bool = False,
) -> dict[str, object]:
    """Change slot labels without modifying a single source photo."""
    from .scanner import _slot_for, _status_for

    row = conn.execute(
        "SELECT id,name,slots_json,filename_aliases_json FROM category WHERE code=?",
        (category_code,),
    ).fetchone()
    if row is None:
        raise SettingsError("找不到指定類別")
    if not isinstance(slots, list) or not 1 <= len(slots) <= 30:
        raise SettingsError("每類至少要有 1 個槽位，最多 30 個")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in slots:
        if not isinstance(raw, str):
            raise SettingsError("槽位名稱必須是文字")
        name = raw.strip()
        if (
            not name
            or len(name) > MAX_CUSTOM_SLOT_LENGTH
            or name.endswith(".")
            or _SUFFIX_RE.search(name)
            or any(ord(ch) < 32 or ch in _ILLEGAL_SLOT_CHARS for ch in name)
        ):
            raise SettingsError("槽位名稱不可為空、過長、含檔名禁用字元或 -數字 結尾")
        if name.casefold() in seen:
            raise SettingsError("同一類別的槽位名稱不可重複")
        seen.add(name.casefold())
        cleaned.append(name)
    old = list(json.loads(str(row["slots_json"])))
    removed = set(old) - set(cleaned)
    if removed and not confirm_unmapped:
        raise SettingsError("改名或移除槽位會讓舊檔名照片顯示在「未對應照片」；需再次確認")
    aliases = dict(json.loads(str(row["filename_aliases_json"])))
    aliases = {source: target for source, target in aliases.items() if target in cleaned}
    collision = [
        source
        for source, target in aliases.items()
        if source.casefold() in seen and source.casefold() != target.casefold()
    ]
    if collision:
        raise SettingsError("槽位名稱與已設定的檔名同義詞衝突，請先調整同義詞")
    custom = [slot for slot in custom_slots_for(conn, category_code) if slot not in cleaned]
    items = conn.execute("SELECT id FROM item WHERE category_id=?", (row["id"],)).fetchall()
    order = get_setting(conn, "slot_order", {})
    if not isinstance(order, dict):
        order = {}
    order[category_code] = cleaned
    custom_all = get_setting(conn, "custom_slots", {})
    if not isinstance(custom_all, dict):
        custom_all = {}
    custom_all[category_code] = custom
    with conn:
        conn.execute(
            "UPDATE category SET slots_json=?, filename_aliases_json=? WHERE id=?",
            (
                json.dumps(cleaned, ensure_ascii=False),
                json.dumps(aliases, ensure_ascii=False),
                row["id"],
            ),
        )
        for key, value in (("slot_order", order), ("custom_slots", custom_all)):
            conn.execute(
                """INSERT INTO setting(key,value_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                       updated_at=CURRENT_TIMESTAMP""",
                (key, json.dumps(value, ensure_ascii=False)),
            )
        for item in items:
            iid = int(item["id"])
            photos = conn.execute(
                "SELECT id,filename FROM photo WHERE item_id=?", (iid,)
            ).fetchall()
            for photo in photos:
                slot = _slot_for(
                    category_code,
                    str(photo["filename"]),
                    tuple(custom),
                    tuple(cleaned),
                    aliases,
                )
                conn.execute("UPDATE photo SET slot=? WHERE id=?", (slot, photo["id"]))
            conn.execute(
                "UPDATE item SET status=? WHERE id=?",
                (
                    _status_for(
                        category_code,
                        [str(photo["filename"]) for photo in photos],
                        tuple(cleaned),
                        tuple(custom),
                        aliases,
                    ),
                    iid,
                ),
            )
        conn.execute(
            "INSERT INTO audit_log(action,target_path,detail_json) VALUES(?,?,?)",
            (
                "update_category_slots",
                category_code,
                json.dumps(
                    {
                        "old": old,
                        "new": cleaned,
                        "affected_items": len(items),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    return {
        "code": category_code,
        "name": row["name"],
        "slots": cleaned,
        "filename_aliases": aliases,
    }


def update_category_aliases(
    conn: sqlite3.Connection, category_code: str, aliases: dict[str, str]
) -> dict[str, object]:
    row = conn.execute(
        "SELECT id, code, name, slots_json FROM category WHERE code=?", (category_code,)
    ).fetchone()
    if row is None:
        raise SettingsError("找不到指定類別")
    slots = set(json.loads(str(row["slots_json"])))
    cleaned: dict[str, str] = {}
    for source, target in aliases.items():
        if not isinstance(source, str) or not isinstance(target, str):
            raise SettingsError("同義詞的來源與目標都必須是文字")
        source = source.strip()
        target = target.strip()
        if not source:
            raise SettingsError("同義詞來源不可為空")
        if target not in slots:
            raise SettingsError(f"同義詞 {source} 的目標必須是既有槽位")
        cleaned[source] = target
    encoded = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
    with conn:
        conn.execute("UPDATE category SET filename_aliases_json=? WHERE id=?", (encoded, row["id"]))
        conn.execute(
            """
            INSERT INTO audit_log(action, target_path, detail_json)
            VALUES ('update_category_aliases', ?, ?)
            """,
            (
                category_code,
                json.dumps({"alias_count": len(cleaned)}, ensure_ascii=False),
            ),
        )
    return {
        "code": row["code"],
        "name": row["name"],
        "slots": list(json.loads(str(row["slots_json"]))),
        "filename_aliases": cleaned,
    }


def update_root_settings(
    conn: sqlite3.Connection, root_id: int, *, label: str, is_cloud_stream: bool
) -> dict[str, object]:
    clean_label = label.strip()
    if not clean_label:
        raise SettingsError("根目錄名稱不可為空")
    row = conn.execute("SELECT id FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        raise SettingsError("找不到指定照片根目錄")
    with conn:
        conn.execute(
            "UPDATE root SET label=?, is_cloud_stream=? WHERE id=?",
            (clean_label, int(is_cloud_stream), root_id),
        )
        conn.execute(
            """
            INSERT INTO audit_log(action, target_path, detail_json)
            VALUES ('update_root_settings', ?, ?)
            """,
            (
                str(root_id),
                json.dumps(
                    {"label": clean_label, "is_cloud_stream": bool(is_cloud_stream)},
                    ensure_ascii=False,
                ),
            ),
        )
    result = conn.execute("SELECT * FROM root WHERE id=?", (root_id,)).fetchone()
    assert result is not None
    return dict(result)

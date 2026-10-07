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


def save_settings(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, object]:
    allowed = {"theme", "thumbnail_quality", "slot_order", "quick_create", "custom_slots"}
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

from __future__ import annotations

import hashlib
import json
import sqlite3


def _catalog_key(conn: sqlite3.Connection, root_id: int) -> str:
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        return f"folder_catalog:missing:{root_id}"
    digest = hashlib.sha256(str(row["path"]).encode("utf-8")).hexdigest()
    return f"folder_catalog:{digest}"


def _empty_catalog() -> dict[str, list[dict[str, str]]]:
    return {"periods": [], "buildings": []}


def load_folder_catalog(conn: sqlite3.Connection, root_id: int) -> dict[str, list[dict[str, str]]]:
    row = conn.execute(
        "SELECT value_json FROM setting WHERE key=?",
        (_catalog_key(conn, root_id),),
    ).fetchone()
    if row is None:
        return _empty_catalog()
    try:
        decoded = json.loads(str(row["value_json"]))
    except json.JSONDecodeError:
        return _empty_catalog()
    if not isinstance(decoded, dict):
        return _empty_catalog()
    result = _empty_catalog()
    for kind in ("periods", "buildings"):
        rows = decoded.get(kind, [])
        if not isinstance(rows, list):
            continue
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            required = (
                ("category_code", "year", "period")
                if kind == "periods"
                else (
                    "category_code",
                    "year",
                    "period",
                    "building",
                )
            )
            clean: dict[str, str] = {}
            valid = True
            for key in required:
                value = entry.get(key)
                if not isinstance(value, str) or not value.strip():
                    valid = False
                    break
                clean[key] = value.strip()
            if valid:
                result[kind].append(clean)
    return result


def _save_folder_catalog(
    conn: sqlite3.Connection,
    root_id: int,
    catalog: dict[str, list[dict[str, str]]],
) -> None:
    conn.execute(
        """
        INSERT INTO setting(key, value_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value_json=excluded.value_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            _catalog_key(conn, root_id),
            json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
        ),
    )


def register_period(
    conn: sqlite3.Connection,
    root_id: int,
    category_code: str,
    year: str,
    period: str,
) -> None:
    catalog = load_folder_catalog(conn, root_id)
    entry = {"category_code": category_code, "year": year, "period": period}
    if entry not in catalog["periods"]:
        catalog["periods"].append(entry)
    _save_folder_catalog(conn, root_id, catalog)


def register_building(
    conn: sqlite3.Connection,
    root_id: int,
    category_code: str,
    year: str,
    period: str,
    building: str,
) -> None:
    catalog = load_folder_catalog(conn, root_id)
    period_entry = {"category_code": category_code, "year": year, "period": period}
    building_entry = {**period_entry, "building": building}
    if period_entry not in catalog["periods"]:
        catalog["periods"].append(period_entry)
    if building_entry not in catalog["buildings"]:
        catalog["buildings"].append(building_entry)
    _save_folder_catalog(conn, root_id, catalog)


def managed_buildings(
    conn: sqlite3.Connection,
    root_id: int,
    category_code: str,
    year: str,
    period: str,
) -> set[str]:
    catalog = load_folder_catalog(conn, root_id)
    return {
        row["building"]
        for row in catalog["buildings"]
        if row["category_code"] == category_code and row["year"] == year and row["period"] == period
    }

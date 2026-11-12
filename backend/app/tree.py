from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .folder_catalog import load_folder_catalog
from .settings import excluded_root_folders


def build_tree(conn: sqlite3.Connection, root_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT i.id, c.code AS category_code, c.name AS category_name,
               i.year, i.period, i.building, i.code, i.status, i.photo_count
        FROM item AS i
        JOIN category AS c ON c.id = i.category_id
        WHERE i.root_id = ?
        ORDER BY c.id, i.year, i.period, i.building, i.code
        """,
        (root_id,),
    ).fetchall()

    category_names = {
        str(row["code"]): str(row["name"])
        for row in conn.execute("SELECT code, name FROM category ORDER BY id")
    }
    grouped: dict[str, dict[str, Any]] = {}

    def ensure_path(
        category_code: str,
        year_value: str,
        period_value: str,
        building_value: str | None = None,
    ) -> dict[str, Any] | None:
        category = grouped.setdefault(
            category_code,
            {
                "type": "category",
                "key": category_code,
                "label": category_names.get(category_code, category_code),
                "children": {},
            },
        )
        year = category["children"].setdefault(
            year_value,
            {"type": "year", "key": year_value, "label": year_value, "children": {}},
        )
        period = year["children"].setdefault(
            period_value,
            {"type": "period", "key": period_value, "label": period_value, "children": {}},
        )
        if building_value is None:
            return None
        building = period["children"].setdefault(
            building_value,
            {"type": "building", "key": building_value, "label": building_value, "children": []},
        )
        return building

    for row in rows:
        building = ensure_path(
            str(row["category_code"]),
            str(row["year"]),
            str(row["period"]),
            str(row["building"]),
        )
        assert building is not None
        building["children"].append(
            {
                "type": "item",
                "key": str(row["id"]),
                "id": row["id"],
                "label": row["code"],
                "status": row["status"],
                "photo_count": row["photo_count"],
            }
        )

    # Show discovered empty top-level categories as navigable nodes too.
    root = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    root_path = Path(str(root["path"])) if root else None
    excluded = excluded_root_folders(conn)
    for category in conn.execute("SELECT code, name FROM category ORDER BY id"):
        code = str(category["code"])
        name = str(category["name"])
        if code.startswith("folder_") and name.casefold() not in excluded and code not in grouped:
            path = root_path / name if root_path else None
            if path is not None and path.is_dir() and not path.is_symlink():
                grouped[code] = {
                    "type": "category",
                    "key": code,
                    "label": name,
                    "children": {},
                }

    catalog = load_folder_catalog(conn, root_id)
    for entry in catalog["years"]:
        if category_names.get(entry["category_code"], "").casefold() in excluded:
            continue
        category = grouped.setdefault(
            entry["category_code"],
            {
                "type": "category",
                "key": entry["category_code"],
                "label": category_names.get(entry["category_code"], entry["category_code"]),
                "children": {},
            },
        )
        category["children"].setdefault(
            entry["year"],
            {"type": "year", "key": entry["year"], "label": entry["year"], "children": {}},
        )
    for entry in catalog["periods"]:
        if category_names.get(entry["category_code"], "").casefold() in excluded:
            continue
        ensure_path(entry["category_code"], entry["year"], entry["period"])
    for entry in catalog["buildings"]:
        if category_names.get(entry["category_code"], "").casefold() in excluded:
            continue
        ensure_path(
            entry["category_code"],
            entry["year"],
            entry["period"],
            entry["building"],
        )

    def collapse(node: dict[str, Any]) -> dict[str, Any]:
        children = node.get("children")
        if isinstance(children, dict):
            node["children"] = [collapse(child) for child in children.values()]
        return node

    return [collapse(category) for category in grouped.values()]

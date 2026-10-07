from __future__ import annotations

import sqlite3
from typing import Any

from .folder_catalog import load_folder_catalog


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

    catalog = load_folder_catalog(conn, root_id)
    for entry in catalog["periods"]:
        ensure_path(entry["category_code"], entry["year"], entry["period"])
    for entry in catalog["buildings"]:
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

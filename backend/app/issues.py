"""持久保存單一設備異常，獨立於可重新掃描的 item/photo 索引。"""

from __future__ import annotations

import json
import sqlite3


class IssueError(ValueError):
    pass


class IssueConflict(IssueError):
    pass


def _label_name(name: str) -> str:
    clean = name.strip()
    if not clean or len(clean) > 80 or any(ord(char) < 32 for char in clean):
        raise IssueError("異常分類須為 1～80 個可顯示字元")
    return clean


def list_labels(conn: sqlite3.Connection) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT id, name, sort_order, active FROM issue_label ORDER BY sort_order, id"
        )
    ]


def create_label(conn: sqlite3.Connection, name: str) -> dict[str, object]:
    clean = _label_name(name)
    if conn.execute("SELECT 1 FROM issue_label WHERE name=? COLLATE NOCASE", (clean,)).fetchone():
        raise IssueConflict("異常分類名稱已存在")
    with conn:
        order = conn.execute("SELECT COALESCE(MAX(sort_order), -1)+1 FROM issue_label").fetchone()[
            0
        ]
        cursor = conn.execute(
            "INSERT INTO issue_label(name, sort_order) VALUES (?, ?)", (clean, order)
        )
        _audit(conn, "create_issue_label", {"label_id": cursor.lastrowid, "name": clean})
    return dict(
        conn.execute(
            "SELECT id, name, sort_order, active FROM issue_label WHERE id=?",
            (cursor.lastrowid,),
        ).fetchone()
    )


def update_label(
    conn: sqlite3.Connection,
    label_id: int,
    *,
    name: str | None = None,
    active: bool | None = None,
    sort_order: int | None = None,
) -> dict[str, object]:
    current = conn.execute("SELECT * FROM issue_label WHERE id=?", (label_id,)).fetchone()
    if current is None:
        raise IssueError("找不到異常分類")
    clean = _label_name(name) if name is not None else str(current["name"])
    if conn.execute(
        "SELECT 1 FROM issue_label WHERE name=? COLLATE NOCASE AND id<>?",
        (clean, label_id),
    ).fetchone():
        raise IssueConflict("異常分類名稱已存在")
    if sort_order is not None and (sort_order < 0 or sort_order > 100000):
        raise IssueError("排序值超出允許範圍")
    with conn:
        conn.execute(
            "UPDATE issue_label SET name=?, active=? WHERE id=?",
            (clean, int(current["active"]) if active is None else int(active), label_id),
        )
        if sort_order is not None:
            ordered_ids = [
                int(row["id"])
                for row in conn.execute("SELECT id FROM issue_label ORDER BY sort_order,id")
                if int(row["id"]) != label_id
            ]
            ordered_ids.insert(min(sort_order, len(ordered_ids)), label_id)
            for rank, row_id in enumerate(ordered_ids):
                conn.execute("UPDATE issue_label SET sort_order=? WHERE id=?", (rank, row_id))
        _audit(conn, "update_issue_label", {"label_id": label_id, "name": clean})
    return dict(
        conn.execute(
            "SELECT id, name, sort_order, active FROM issue_label WHERE id=?", (label_id,)
        ).fetchone()
    )


def _audit(conn: sqlite3.Connection, action: str, detail: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO audit_log(action, detail_json) VALUES (?, ?)",
        (action, json.dumps(detail, ensure_ascii=False)),
    )


def item_issue(conn: sqlite3.Connection, item_id: int) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT i.root_id, i.relative_path, i.code,
               x.label_id, l.name AS label_name
        FROM item i
        LEFT JOIN item_issue x ON x.root_id=i.root_id AND x.item_relative_path=i.relative_path
        LEFT JOIN issue_label l ON l.id=x.label_id
        WHERE i.id=?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise IssueError("找不到指定設備")
    return dict(row)


def set_item_issue(
    conn: sqlite3.Connection, item_id: int, label_id: int | None
) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT i.root_id, i.relative_path, i.code, c.code AS category_code
        FROM item i JOIN category c ON c.id=i.category_id WHERE i.id=?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise IssueError("找不到指定設備")
    if label_id is not None:
        label = conn.execute(
            "SELECT id FROM issue_label WHERE id=? AND active=1", (label_id,)
        ).fetchone()
        if label is None:
            raise IssueError("異常分類不存在或已停用")
    with conn:
        if label_id is None:
            conn.execute(
                "DELETE FROM item_issue WHERE root_id=? AND item_relative_path=?",
                (row["root_id"], row["relative_path"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO item_issue(root_id, item_relative_path, category_code,
                                       device_code, label_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(root_id, item_relative_path)
                DO UPDATE SET label_id=excluded.label_id, updated_at=CURRENT_TIMESTAMP
                """,
                (
                    row["root_id"],
                    row["relative_path"],
                    row["category_code"],
                    row["code"],
                    label_id,
                ),
            )
        _audit(
            conn,
            "set_item_issue",
            {
                "item_id": item_id,
                "root_id": row["root_id"],
                "relative_path": row["relative_path"],
                "label_id": label_id,
            },
        )
    return item_issue(conn, item_id)


def issue_statistics(conn: sqlite3.Connection, root_id: int | None = None) -> dict[str, object]:
    labels = list_labels(conn)
    query = """
        SELECT x.root_id, r.label AS root_name, x.item_relative_path, x.category_code,
               x.device_code, x.label_id, x.created_at, x.updated_at,
               i.id AS item_id, i.building, i.year, i.period
        FROM item_issue x
        JOIN root r ON r.id=x.root_id
        LEFT JOIN item i ON i.root_id=x.root_id
                        AND i.relative_path=x.item_relative_path
    """
    params: tuple[int, ...] = ()
    if root_id is not None:
        query += " WHERE x.root_id=?"
        params = (root_id,)
    query += " ORDER BY x.updated_at DESC, x.root_id, x.device_code"
    rows = [dict(row) for row in conn.execute(query, params)]
    counts = {int(label["id"]): 0 for label in labels}
    for row in rows:
        counts[int(row["label_id"])] += 1
    return {
        "labels": [{**label, "count": counts[int(label["id"])]} for label in labels],
        "total": len(rows),
        "items": rows,
    }

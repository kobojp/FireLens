from __future__ import annotations

from pathlib import Path

from backend.app.db import SCHEMA_VERSION, connect, initialize_database


def test_schema_is_idempotent_and_protected_data_survives(db_path: Path) -> None:
    conn = connect(db_path)
    with conn:
        conn.execute("INSERT INTO setting(key, value_json) VALUES ('theme', '\"dark\"')")
        conn.execute(
            "INSERT INTO root(label, path, is_cloud_stream) VALUES (?, ?, 0)",
            ("測試", str(db_path.parent)),
        )
    conn.close()

    initialize_database(db_path)

    conn = connect(db_path)
    try:
        value = conn.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone()
        root = conn.execute("SELECT label FROM root WHERE label = '測試'").fetchone()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert value is not None and value[0] == '"dark"'
    assert root is not None and root[0] == "測試"
    assert version == SCHEMA_VERSION
    assert {
        "category",
        "root",
        "item",
        "photo",
        "ledger",
        "ledger_row",
        "alias_map",
        "rename_log",
        "audit_log",
        "setting",
        "reshoot_mark",
    } <= tables

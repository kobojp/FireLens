from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .config import get_database_path

SCHEMA_VERSION = 5

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS category (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    slots_json TEXT NOT NULL DEFAULT '[]',
    filename_aliases_json TEXT NOT NULL DEFAULT '{}',
    item_regex TEXT
);

CREATE TABLE IF NOT EXISTS root (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    is_cloud_stream INTEGER NOT NULL DEFAULT 0 CHECK (is_cloud_stream IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scan_at TEXT
);

CREATE TABLE IF NOT EXISTS item (
    id INTEGER PRIMARY KEY,
    root_id INTEGER NOT NULL REFERENCES root(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES category(id),
    year TEXT NOT NULL,
    period TEXT NOT NULL,
    building TEXT NOT NULL,
    code TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown',
    photo_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(root_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_item_root_category ON item(root_id, category_id);
CREATE INDEX IF NOT EXISTS idx_item_tree ON item(root_id, year, period, building, code);

CREATE TABLE IF NOT EXISTS photo (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    extension TEXT NOT NULL,
    slot TEXT,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    sha256 TEXT,
    thumbnail_path TEXT,
    cloud_placeholder INTEGER NOT NULL DEFAULT 0 CHECK (cloud_placeholder IN (0, 1)),
    UNIQUE(item_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_photo_item ON photo(item_id);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_sha256 TEXT
);

CREATE TABLE IF NOT EXISTS ledger_row (
    id INTEGER PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    row_no INTEGER NOT NULL,
    section TEXT,
    device_no TEXT NOT NULL,
    specification TEXT,
    last_replacement_date TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(ledger_id, row_no)
);

CREATE TABLE IF NOT EXISTS alias_map (
    id INTEGER PRIMARY KEY,
    alias_type TEXT NOT NULL,
    source_value TEXT NOT NULL,
    target_value TEXT NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    UNIQUE(alias_type, source_value)
);

CREATE TABLE IF NOT EXISTS rename_log (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    sha256 TEXT,
    reverted_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,
    source_path TEXT,
    target_path TEXT,
    sha256 TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS setting (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


MIGRATION_2 = """
CREATE INDEX IF NOT EXISTS idx_ledger_row_device ON ledger_row(ledger_id, device_no);
CREATE INDEX IF NOT EXISTS idx_alias_type_source ON alias_map(alias_type, source_value);
"""


MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS reshoot_mark (
    id INTEGER PRIMARY KEY,
    root_id INTEGER NOT NULL REFERENCES root(id) ON DELETE CASCADE,
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    category_code TEXT NOT NULL,
    device_no TEXT NOT NULL,
    marked INTEGER NOT NULL DEFAULT 1 CHECK (marked IN (0, 1)),
    marked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(root_id, ledger_id, category_code, device_no)
);
CREATE INDEX IF NOT EXISTS idx_reshot_mark_lookup
ON reshoot_mark(root_id, ledger_id, category_code, device_no);
"""


MIGRATION_4_INDEX = """
CREATE INDEX IF NOT EXISTS idx_rename_log_root ON rename_log(root_id, id);
"""


def _migrate_4(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(rename_log)")}
    with conn:
        if "root_id" not in columns:
            conn.execute("ALTER TABLE rename_log ADD COLUMN root_id INTEGER REFERENCES root(id)")
        conn.executescript(MIGRATION_4_INDEX)
        conn.execute("PRAGMA user_version = 4")


MIGRATION_5 = """
CREATE TABLE IF NOT EXISTS offline_import_queue (
    id INTEGER PRIMARY KEY,
    root_id INTEGER NOT NULL REFERENCES root(id) ON DELETE CASCADE,
    item_relative_path TEXT NOT NULL,
    slot TEXT NOT NULL,
    source_name TEXT NOT NULL,
    payload_name TEXT NOT NULL UNIQUE,
    replace_relative_path TEXT,
    expected_original_sha256 TEXT,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'error', 'synced')),
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    synced_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_offline_import_queue_root_state
ON offline_import_queue(root_id, state, id);
"""


def _migrate_5(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(MIGRATION_5)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(offline_import_queue)")}
    with conn:
        if "replace_relative_path" not in columns:
            conn.execute("ALTER TABLE offline_import_queue ADD COLUMN replace_relative_path TEXT")
        if "expected_original_sha256" not in columns:
            conn.execute(
                "ALTER TABLE offline_import_queue ADD COLUMN expected_original_sha256 TEXT"
            )
        conn.execute("PRAGMA user_version = 5")


CATEGORY_SEED = (
    (
        "extinguisher",
        "滅火器",
        '["編號","藥劑","完成"]',
        '{"有效日期":"藥劑"}',
    ),
    ("box", "放置盒", '["前","中","後"]', "{}"),
    ("lamp", "燈具", '["前","中","後"]', "{}"),
)


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _backup_before_upgrade(path: Path, current_version: int) -> None:
    if not path.exists() or current_version == 0:
        return
    backup = path.with_suffix(path.suffix + f".backup-v{current_version}")
    if not backup.exists():
        source = sqlite3.connect(path)
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()


def initialize_database(db_path: Path | None = None) -> Path:
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"資料庫 schema 版本 {current_version} 高於程式支援版本 {SCHEMA_VERSION}"
            )
        if current_version < SCHEMA_VERSION:
            conn.close()
            _backup_before_upgrade(path, current_version)
            conn = connect(path)

        if current_version < 1:
            with conn:
                conn.executescript(MIGRATION_1)
                conn.execute("PRAGMA user_version = 1")
            current_version = 1

        if current_version < 2:
            with conn:
                conn.executescript(MIGRATION_2)
                conn.execute("PRAGMA user_version = 2")
            current_version = 2

        if current_version < 3:
            with conn:
                conn.executescript(MIGRATION_3)
                conn.execute("PRAGMA user_version = 3")
            current_version = 3

        if current_version < 4:
            _migrate_4(conn)
            current_version = 4

        if current_version < 5:
            _migrate_5(conn)
            current_version = 5

        with conn:
            conn.executemany(
                """
                INSERT INTO category(code, name, slots_json, filename_aliases_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO NOTHING
                """,
                CATEGORY_SEED,
            )
    finally:
        conn.close()
    return path


@contextmanager
def database(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = initialize_database(db_path)
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()

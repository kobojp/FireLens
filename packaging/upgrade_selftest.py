from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def run() -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from backend.app.db import SCHEMA_VERSION, connect, initialize_database

    with tempfile.TemporaryDirectory(prefix="firelens-upgrade-") as temp:
        db = Path(temp) / "firelens.sqlite3"
        # Start from a complete isolated database, then simulate the last real v4 state
        # by removing only the v5 table and lowering user_version. No real user DB is touched.
        initialize_database(db)
        conn = connect(db)
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO setting(key, value_json) "
                    "VALUES ('upgrade_probe', '\"kept\"')"
                )
                conn.execute("DROP TABLE offline_import_queue")
                conn.execute("PRAGMA user_version = 4")
        finally:
            conn.close()

        initialize_database(db)
        check = connect(db)
        try:
            version = int(check.execute("PRAGMA user_version").fetchone()[0])
            value = check.execute(
                "SELECT value_json FROM setting WHERE key='upgrade_probe'"
            ).fetchone()[0]
            queue = check.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='offline_import_queue'"
            ).fetchone()
            backup = db.with_suffix(db.suffix + ".backup-v4")
        finally:
            check.close()
        if version != SCHEMA_VERSION or value != '"kept"' or queue is None or not backup.is_file():
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

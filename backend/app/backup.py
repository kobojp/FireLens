from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from desktop.version import __version__

from .config import get_backup_dir, get_database_path, get_offline_dir
from .db import SCHEMA_VERSION

BACKUP_FORMAT = "firelens-protected-backup"
BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 256 * 1024 * 1024


class BackupError(ValueError):
    pass


def _rows(
    conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()
) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params)]


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def protected_snapshot(conn: sqlite3.Connection) -> dict[str, object]:
    ledgers = _rows(conn, "SELECT * FROM ledger ORDER BY id")
    return {
        "schema_version": SCHEMA_VERSION,
        "settings": _rows(conn, "SELECT * FROM setting ORDER BY key"),
        "categories": _rows(conn, "SELECT * FROM category ORDER BY id"),
        "roots": _rows(conn, "SELECT * FROM root ORDER BY id"),
        "ledgers": [
            {
                **ledger,
                "rows": _rows(
                    conn,
                    "SELECT * FROM ledger_row WHERE ledger_id=? ORDER BY row_no",
                    (ledger["id"],),
                ),
            }
            for ledger in ledgers
        ],
        "aliases": _rows(conn, "SELECT * FROM alias_map ORDER BY id"),
        "rename_logs": _rows(conn, "SELECT * FROM rename_log ORDER BY id"),
        "audit_logs": _rows(conn, "SELECT * FROM audit_log ORDER BY id"),
        "reshoot_marks": _rows(conn, "SELECT * FROM reshoot_mark ORDER BY id"),
        "offline_queue": _rows(conn, "SELECT * FROM offline_import_queue ORDER BY id"),
    }


def export_backup(conn: sqlite3.Connection) -> tuple[bytes, str]:
    data = protected_snapshot(conn)
    data_bytes = _json_bytes(data)
    payload_hashes: dict[str, str] = {}
    offline_dir = get_offline_dir().resolve()
    queue = data["offline_queue"]
    assert isinstance(queue, list)
    payloads: dict[str, bytes] = {}
    for row in queue:
        if not isinstance(row, dict) or row.get("state") == "synced":
            continue
        name = str(row.get("payload_name") or "")
        if not name or PurePosixPath(name).name != name:
            continue
        path = (offline_dir / name).resolve()
        if not path.is_relative_to(offline_dir) or not path.is_file():
            continue
        content = path.read_bytes()
        digest = _sha256(content)
        if row.get("sha256") and digest != row["sha256"]:
            raise BackupError(f"離線暫存檔 {name} SHA-256 不一致，已停止備份")
        payloads[name] = content
        payload_hashes[name] = digest

    manifest = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "app_version": __version__,
        "schema_version": SCHEMA_VERSION,
        "data_sha256": _sha256(data_bytes),
        "offline_payload_sha256": payload_hashes,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("data.json", data_bytes)
        for name, content in payloads.items():
            archive.writestr(f"offline/{name}", content)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output.getvalue(), f"firelens-backup-{timestamp}.zip"


def _load_package(blob: bytes) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    if not blob or len(blob) > MAX_BACKUP_BYTES:
        raise BackupError("備份檔不可為空，且大小不可超過 256 MB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise BackupError("不是有效的 FireLens 備份 ZIP") from exc
    with archive:
        names = archive.namelist()
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise BackupError("備份檔包含不安全路徑")
        if "manifest.json" not in names or "data.json" not in names:
            raise BackupError("備份檔缺少 manifest.json 或 data.json")
        try:
            manifest = json.loads(archive.read("manifest.json"))
            data_bytes = archive.read("data.json")
            data = json.loads(data_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
            raise BackupError("備份檔 JSON 格式損壞") from exc
        if not isinstance(manifest, dict) or not isinstance(data, dict):
            raise BackupError("備份資料格式不正確")
        if manifest.get("format") != BACKUP_FORMAT or manifest.get("version") != BACKUP_VERSION:
            raise BackupError("不支援的 FireLens 備份版本")
        if manifest.get("data_sha256") != _sha256(data_bytes):
            raise BackupError("備份資料 SHA-256 驗證失敗")
        declared = manifest.get("offline_payload_sha256", {})
        if not isinstance(declared, dict):
            raise BackupError("離線暫存檔清單格式不正確")
        payloads: dict[str, bytes] = {}
        for name, expected in declared.items():
            if not isinstance(name, str) or PurePosixPath(name).name != name:
                raise BackupError("離線暫存檔名稱不安全")
            archive_name = f"offline/{name}"
            if archive_name not in names:
                raise BackupError(f"備份缺少離線暫存檔：{name}")
            content = archive.read(archive_name)
            if _sha256(content) != expected:
                raise BackupError(f"離線暫存檔 {name} SHA-256 驗證失敗")
            payloads[name] = content
    return manifest, data, payloads


def create_database_snapshot(db_path: Path | None = None) -> Path:
    source_path = db_path or get_database_path()
    get_backup_dir().mkdir(parents=True, exist_ok=True)
    target = (
        get_backup_dir()
        / f"pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.sqlite3"
    )
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


def _require_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise BackupError(f"備份欄位 {key} 格式不正確")
    return value


def restore_backup(
    conn: sqlite3.Connection, blob: bytes, *, db_path: Path | None = None
) -> dict[str, object]:
    manifest, data, payloads = _load_package(blob)
    backup_schema = data.get("schema_version")
    if not isinstance(backup_schema, int) or backup_schema > SCHEMA_VERSION:
        raise BackupError("備份資料庫版本高於目前 FireLens 支援版本")

    categories = _require_list(data, "categories")
    roots = _require_list(data, "roots")
    ledgers = _require_list(data, "ledgers")
    aliases = _require_list(data, "aliases")
    settings = _require_list(data, "settings")
    rename_logs = _require_list(data, "rename_logs")
    audit_logs = _require_list(data, "audit_logs")
    reshoot_marks = _require_list(data, "reshoot_marks")
    offline_queue = _require_list(data, "offline_queue")

    snapshot = create_database_snapshot(db_path)
    offline_dir = get_offline_dir()
    offline_dir.mkdir(parents=True, exist_ok=True)
    created_payloads: list[Path] = []
    root_map: dict[int, int] = {}
    ledger_map: dict[int, int] = {}
    payload_name_map: dict[str, str] = {}
    counts = {"roots": 0, "ledgers": 0, "aliases": 0, "settings": 0, "offline": 0}

    try:
        # Stage verified offline payloads under collision-safe final names.
        # These are app cache files, never files in photo roots.
        # Remove them again if the database merge fails.
        for original, content in payloads.items():
            desired = original
            target = offline_dir / desired
            if target.exists():
                if _sha256(target.read_bytes()) == _sha256(content):
                    payload_name_map[original] = desired
                    continue
                desired = f"{uuid.uuid4().hex}.payload"
                target = offline_dir / desired
            temp = offline_dir / f".{desired}.{uuid.uuid4().hex}.tmp"
            temp.write_bytes(content)
            if _sha256(temp.read_bytes()) != _sha256(content):
                temp.unlink(missing_ok=True)
                raise BackupError("還原離線暫存檔時 SHA-256 驗證失敗")
            temp.replace(target)
            created_payloads.append(target)
            payload_name_map[original] = desired

        conn.execute("BEGIN IMMEDIATE")
        for row in categories:
            code = str(row.get("code") or "")
            aliases_json = str(row.get("filename_aliases_json") or "{}")
            existing = conn.execute(
                "SELECT id, slots_json FROM category WHERE code=?", (code,)
            ).fetchone()
            if existing is None:
                continue
            # Validate alias JSON before persisting.
            # Slot definitions remain local product definitions.
            parsed_aliases = json.loads(aliases_json)
            if not isinstance(parsed_aliases, dict):
                raise BackupError("類別同義詞格式不正確")
            slots = set(json.loads(existing["slots_json"]))
            if any(not isinstance(k, str) or v not in slots for k, v in parsed_aliases.items()):
                raise BackupError("類別同義詞包含未知槽位")
            conn.execute(
                "UPDATE category SET filename_aliases_json=? WHERE id=?",
                (json.dumps(parsed_aliases, ensure_ascii=False), existing["id"]),
            )

        for row in roots:
            old_id = int(row["id"])
            path = str(row.get("path") or "").strip()
            label = str(row.get("label") or "").strip() or path
            if not path:
                raise BackupError("備份根目錄缺少路徑")
            existing = conn.execute("SELECT id FROM root WHERE path=?", (path,)).fetchone()
            if existing:
                new_id = int(existing["id"])
                conn.execute(
                    "UPDATE root SET label=?, is_cloud_stream=? WHERE id=?",
                    (label, int(bool(row.get("is_cloud_stream"))), new_id),
                )
            else:
                cursor = conn.execute(
                    "INSERT INTO root(label, path, is_cloud_stream) VALUES (?, ?, ?)",
                    (label, path, int(bool(row.get("is_cloud_stream")))),
                )
                new_id = int(cursor.lastrowid)
                counts["roots"] += 1
            root_map[old_id] = new_id

        for ledger in ledgers:
            old_id = int(ledger["id"])
            sha = ledger.get("source_sha256")
            existing = None
            if sha:
                existing = conn.execute(
                    "SELECT id FROM ledger WHERE source_sha256=? ORDER BY id LIMIT 1", (sha,)
                ).fetchone()
            if existing:
                ledger_map[old_id] = int(existing["id"])
                continue
            cursor = conn.execute(
                """
                INSERT INTO ledger(name, source_type, imported_at, source_sha256)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(ledger.get("name") or "還原清冊"),
                    str(ledger.get("source_type") or "backup"),
                    str(ledger.get("imported_at") or datetime.now(UTC).isoformat()),
                    sha,
                ),
            )
            new_id = int(cursor.lastrowid)
            ledger_map[old_id] = new_id
            rows = ledger.get("rows", [])
            if not isinstance(rows, list):
                raise BackupError("清冊列格式不正確")
            for item in rows:
                if not isinstance(item, dict):
                    raise BackupError("清冊列格式不正確")
                conn.execute(
                    """
                    INSERT INTO ledger_row(
                        ledger_id, row_no, section, device_no, specification,
                        last_replacement_date, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id,
                        int(item["row_no"]),
                        item.get("section"),
                        str(item.get("device_no") or ""),
                        item.get("specification"),
                        item.get("last_replacement_date"),
                        str(item.get("raw_json") or "{}"),
                    ),
                )
            counts["ledgers"] += 1

        for row in aliases:
            source = str(row.get("source_value") or "").strip()
            target = str(row.get("target_value") or "").strip()
            alias_type = str(row.get("alias_type") or "building").strip()
            if not source or not target:
                continue
            conn.execute(
                """
                INSERT INTO alias_map(alias_type, source_value, target_value, confirmed)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(alias_type, source_value) DO UPDATE SET
                    target_value=excluded.target_value, confirmed=excluded.confirmed
                """,
                (alias_type, source, target, int(bool(row.get("confirmed")))),
            )
            counts["aliases"] += 1

        for row in settings:
            key = str(row.get("key") or "").strip()
            raw = str(row.get("value_json") or "null")
            if not key:
                continue
            json.loads(raw)
            conn.execute(
                """
                INSERT INTO setting(key, value_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP
                """,
                (key, raw),
            )
            counts["settings"] += 1

        for row in rename_logs:
            old_root = row.get("root_id")
            root_id = root_map.get(int(old_root)) if old_root is not None else None
            values = (
                root_id,
                str(row.get("created_at") or ""),
                str(row.get("source_path") or ""),
                str(row.get("target_path") or ""),
                row.get("sha256"),
                row.get("reverted_at"),
            )
            exists = conn.execute(
                """
                SELECT 1 FROM rename_log
                WHERE root_id IS ? AND created_at=? AND source_path=?
                  AND target_path=? AND sha256 IS ?
                LIMIT 1
                """,
                values[:5],
            ).fetchone()
            if not exists and values[2] and values[3]:
                conn.execute(
                    """
                    INSERT INTO rename_log(
                        root_id, created_at, source_path, target_path, sha256, reverted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )

        for row in audit_logs:
            values = (
                str(row.get("created_at") or ""),
                str(row.get("action") or ""),
                row.get("source_path"),
                row.get("target_path"),
                row.get("sha256"),
                str(row.get("detail_json") or "{}"),
            )
            exists = conn.execute(
                """
                SELECT 1 FROM audit_log
                WHERE created_at=? AND action=? AND source_path IS ?
                  AND target_path IS ? AND sha256 IS ?
                LIMIT 1
                """,
                values[:5],
            ).fetchone()
            if not exists and values[1]:
                conn.execute(
                    """
                    INSERT INTO audit_log(
                        created_at, action, source_path, target_path, sha256, detail_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )

        for row in reshoot_marks:
            root_id = root_map.get(int(row["root_id"]))
            ledger_id = ledger_map.get(int(row["ledger_id"]))
            if root_id is None or ledger_id is None:
                continue
            conn.execute(
                """
                INSERT INTO reshoot_mark(
                    root_id, ledger_id, category_code, device_no, marked, marked_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(root_id, ledger_id, category_code, device_no) DO UPDATE SET
                    marked=excluded.marked, marked_at=excluded.marked_at
                """,
                (
                    root_id,
                    ledger_id,
                    str(row.get("category_code") or ""),
                    str(row.get("device_no") or ""),
                    int(bool(row.get("marked"))),
                    str(row.get("marked_at") or datetime.now(UTC).isoformat()),
                ),
            )

        for row in offline_queue:
            old_root = int(row["root_id"])
            root_id = root_map.get(old_root)
            if root_id is None or row.get("state") == "synced":
                continue
            original_payload = str(row.get("payload_name") or "")
            mapped_payload = payload_name_map.get(original_payload)
            if not mapped_payload:
                continue
            digest = str(row.get("sha256") or "")
            exists = conn.execute(
                """
                SELECT 1 FROM offline_import_queue
                WHERE root_id=? AND item_relative_path=? AND slot=? AND sha256=? AND state!='synced'
                LIMIT 1
                """,
                (
                    root_id,
                    str(row.get("item_relative_path") or ""),
                    str(row.get("slot") or ""),
                    digest,
                ),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO offline_import_queue(
                    root_id, item_relative_path, slot, source_name, payload_name,
                    replace_relative_path, expected_original_sha256, sha256, size_bytes,
                    state, last_error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    root_id,
                    str(row.get("item_relative_path") or ""),
                    str(row.get("slot") or ""),
                    str(row.get("source_name") or "backup"),
                    mapped_payload,
                    row.get("replace_relative_path"),
                    row.get("expected_original_sha256"),
                    digest,
                    int(row.get("size_bytes") or 0),
                    "pending" if row.get("state") not in {"pending", "error"} else row["state"],
                    row.get("last_error"),
                    str(row.get("created_at") or datetime.now(UTC).isoformat()),
                ),
            )
            counts["offline"] += 1

        conn.execute(
            """
            INSERT INTO audit_log(action, detail_json)
            VALUES ('restore_protected_backup', ?)
            """,
            (
                json.dumps(
                    {
                        "backup_version": manifest.get("version"),
                        "app_version": manifest.get("app_version"),
                        "counts": counts,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        for path in created_payloads:
            path.unlink(missing_ok=True)
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"備份還原失敗：{exc}") from exc

    return {
        "restored": True,
        "snapshot_path": str(snapshot),
        "counts": counts,
        "source_app_version": manifest.get("app_version"),
    }

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from contextlib import suppress
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import get_offline_dir, get_thumbnail_dir
from .scanner import scan_root
from .settings import custom_slots_for, thumbnail_quality
from .storage import (
    MAX_UPLOAD_BYTES,
    UPLOAD_EXTENSIONS,
    StorageConflict,
    StorageError,
    import_photo,
    sha256_file,
)

THUMBNAIL_SIZE = (480, 360)


class CacheError(ValueError):
    pass


class CacheUnavailable(CacheError):
    pass


def _root_row(conn: sqlite3.Connection, root_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, path, is_cloud_stream, last_scan_at FROM root WHERE id=?", (root_id,)
    ).fetchone()
    if row is None:
        raise CacheError("找不到指定照片根目錄")
    return row


def _safe_cache_path(base: Path, relative: str) -> Path:
    base = base.expanduser().resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise CacheError("快取路徑超出 FireLens 快取目錄")
    return target


def _thumbnail_key(root_id: int, relative_path: str, mtime_ns: int) -> str:
    raw = f"{root_id}\0{relative_path}\0{mtime_ns}".encode()
    return hashlib.sha256(raw).hexdigest()


def _thumbnail_path(root_id: int, relative_path: str, mtime_ns: int) -> Path:
    folder = get_thumbnail_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{_thumbnail_key(root_id, relative_path, mtime_ns)}.jpg"


def _photo_row(conn: sqlite3.Connection, photo_id: int) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT p.id, p.relative_path, p.mtime_ns, p.cloud_placeholder, p.thumbnail_path,
               i.root_id, r.path AS root_path
        FROM photo AS p
        JOIN item AS i ON i.id=p.item_id
        JOIN root AS r ON r.id=i.root_id
        WHERE p.id=?
        """,
        (photo_id,),
    ).fetchone()
    if row is None:
        raise CacheError("找不到指定照片")
    return row


def root_status(conn: sqlite3.Connection, root_id: int) -> dict[str, object]:
    row = _root_row(conn, root_id)
    root_path = Path(row["path"]).expanduser()
    connected = root_path.is_dir()
    items = int(conn.execute("SELECT COUNT(*) FROM item WHERE root_id=?", (root_id,)).fetchone()[0])
    photos = int(
        conn.execute(
            "SELECT COUNT(*) FROM photo p JOIN item i ON i.id=p.item_id WHERE i.root_id=?",
            (root_id,),
        ).fetchone()[0]
    )
    placeholders = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM photo p JOIN item i ON i.id=p.item_id
            WHERE i.root_id=? AND p.cloud_placeholder=1
            """,
            (root_id,),
        ).fetchone()[0]
    )
    pending = int(
        conn.execute(
            "SELECT COUNT(*) FROM offline_import_queue WHERE root_id=? AND state!='synced'",
            (root_id,),
        ).fetchone()[0]
    )
    cached_thumbnails = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM photo p JOIN item i ON i.id=p.item_id
            WHERE i.root_id=? AND p.thumbnail_path IS NOT NULL
            """,
            (root_id,),
        ).fetchone()[0]
    )
    return {
        "root_id": root_id,
        "connected": connected,
        "is_cloud_stream": bool(row["is_cloud_stream"]),
        "last_scan_at": row["last_scan_at"],
        "cached_items": items,
        "cached_photos": photos,
        "cached_thumbnails": cached_thumbnails,
        "cloud_placeholders": placeholders,
        "pending_imports": pending,
    }


def thumbnail_file(conn: sqlite3.Connection, photo_id: int, *, allow_generate: bool = True) -> Path:
    row = _photo_row(conn, photo_id)
    expected = _thumbnail_path(int(row["root_id"]), str(row["relative_path"]), int(row["mtime_ns"]))
    if expected.is_file():
        with conn:
            conn.execute("UPDATE photo SET thumbnail_path=? WHERE id=?", (str(expected), photo_id))
        return expected
    old = row["thumbnail_path"]
    if old:
        old_path = Path(old)
        if old_path.is_file():
            return old_path
    if not allow_generate:
        raise CacheUnavailable("此照片尚未建立縮圖快取")
    if row["cloud_placeholder"]:
        raise CacheUnavailable("照片仍是雲端未下載佔位檔，FireLens 不會強制下載")
    root = Path(row["root_path"]).expanduser().resolve()
    source = (root / row["relative_path"]).resolve()
    if not source.is_relative_to(root) or not source.is_file() or source.is_symlink():
        raise CacheUnavailable("照片來源目前離線，且沒有可用縮圖快取")
    temp = expected.with_name(f".{expected.name}.{uuid.uuid4().hex}.tmp")
    try:
        try:
            with Image.open(source) as image:
                image.load()
                transformed = ImageOps.exif_transpose(image)
                if transformed.mode != "RGB":
                    transformed = transformed.convert("RGB")
                transformed.thumbnail(THUMBNAIL_SIZE)
                transformed.save(
                    temp, format="JPEG", quality=thumbnail_quality(conn), optimize=True
                )
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise CacheError("無法建立照片縮圖") from exc
        os.replace(temp, expected)
        with conn:
            conn.execute("UPDATE photo SET thumbnail_path=? WHERE id=?", (str(expected), photo_id))
        return expected
    finally:
        temp.unlink(missing_ok=True)


def prime_thumbnail_cache(
    conn: sqlite3.Connection, root_id: int, *, limit: int | None = None
) -> dict[str, int]:
    _root_row(conn, root_id)
    query = """
        SELECT p.id FROM photo p JOIN item i ON i.id=p.item_id
        WHERE i.root_id=? AND p.cloud_placeholder=0 ORDER BY p.id
    """
    params: list[object] = [root_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(max(0, int(limit)))
    created = 0
    failed = 0
    for row in conn.execute(query, params):
        try:
            before = conn.execute(
                "SELECT thumbnail_path FROM photo WHERE id=?", (row["id"],)
            ).fetchone()[0]
            path = thumbnail_file(conn, int(row["id"]))
            if not before and path.is_file():
                created += 1
        except CacheError:
            failed += 1
    return {"created": created, "failed": failed}


def content_file(conn: sqlite3.Connection, photo_id: int) -> tuple[Path, bool]:
    row = _photo_row(conn, photo_id)
    if not row["cloud_placeholder"]:
        root = Path(row["root_path"]).expanduser().resolve()
        source = (root / row["relative_path"]).resolve()
        if not source.is_relative_to(root):
            raise CacheError("照片路徑超出設定的照片根目錄")
        if source.is_file() and not source.is_symlink():
            return source, False
    return thumbnail_file(conn, photo_id, allow_generate=False), True


def _validate_offline_upload(source_name: str, data: bytes) -> None:
    if not source_name:
        raise CacheError("離線匯入缺少來源檔名")
    if not data:
        raise CacheError("離線匯入不可為空檔")
    if len(data) > MAX_UPLOAD_BYTES:
        raise CacheError("單張照片不可超過 100 MB")
    if Path(source_name).suffix.casefold() not in UPLOAD_EXTENSIONS:
        raise CacheError("只接受 JPG、JPEG、PNG、HEIC 或 HEIF 圖片")


def queue_offline_import(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    slot: str,
    source_name: str,
    data: bytes,
    replace_photo_id: int | None = None,
) -> dict[str, object]:
    _validate_offline_upload(source_name, data)
    item = conn.execute(
        """
        SELECT i.root_id, i.relative_path, c.slots_json
        FROM item i JOIN category c ON c.id=i.category_id WHERE i.id=?
        """,
        (item_id,),
    ).fetchone()
    if item is None:
        raise CacheError("找不到指定項目")
    import json

    category_code = conn.execute(
        "SELECT c.code FROM item i JOIN category c ON c.id=i.category_id WHERE i.id=?",
        (item_id,),
    ).fetchone()["code"]
    if slot not in (*json.loads(item["slots_json"]), *custom_slots_for(conn, category_code)):
        raise CacheError("指定槽位不屬於此類別")
    replace_relative_path: str | None = None
    expected_original_sha256: str | None = None
    if replace_photo_id is not None:
        replace_row = conn.execute(
            """
            SELECT relative_path, sha256, slot FROM photo
            WHERE id=? AND item_id=?
            """,
            (replace_photo_id, item_id),
        ).fetchone()
        if replace_row is None or replace_row["slot"] != slot:
            raise CacheError("找不到要離線換圖的原照片")
        if not replace_row["sha256"]:
            raise CacheError("離線換圖缺少原照片 SHA-256，請重新連線後再換圖")
        replace_relative_path = str(replace_row["relative_path"])
        expected_original_sha256 = str(replace_row["sha256"])
    root = _root_row(conn, int(item["root_id"]))
    if Path(root["path"]).expanduser().is_dir():
        raise CacheError("照片根目錄目前可用，不需要建立離線佇列")

    digest = hashlib.sha256(data).hexdigest()
    offline_dir = get_offline_dir()
    offline_dir.mkdir(parents=True, exist_ok=True)
    payload_name = f"{uuid.uuid4().hex}.payload"
    target = offline_dir / payload_name
    temp = offline_dir / f".{payload_name}.tmp"
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target.unlink(missing_ok=True)
            raise CacheError("離線匯入快取 SHA-256 驗證失敗")
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO offline_import_queue(
                        root_id, item_relative_path, slot, source_name, payload_name,
                        replace_relative_path, expected_original_sha256, sha256, size_bytes, state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        item["root_id"],
                        item["relative_path"],
                        slot,
                        source_name,
                        payload_name,
                        replace_relative_path,
                        expected_original_sha256,
                        digest,
                        len(data),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO audit_log(action, source_path, target_path, sha256, detail_json)
                    VALUES ('queue_offline_import', ?, ?, ?, json_object('queue_id', ?, 'slot', ?))
                    """,
                    (source_name, item["relative_path"], digest, cursor.lastrowid, slot),
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
    finally:
        temp.unlink(missing_ok=True)
    return dict(
        conn.execute(
            "SELECT * FROM offline_import_queue WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
    )


def list_offline_queue(conn: sqlite3.Connection, root_id: int) -> list[dict[str, object]]:
    _root_row(conn, root_id)
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, root_id, item_relative_path, slot, source_name, replace_relative_path,
                   expected_original_sha256, sha256, size_bytes, state, last_error,
                   created_at, synced_at
            FROM offline_import_queue WHERE root_id=? ORDER BY id
            """,
            (root_id,),
        )
    ]


def sync_offline_queue(conn: sqlite3.Connection, root_id: int) -> dict[str, object]:
    root = _root_row(conn, root_id)
    if not Path(root["path"]).expanduser().is_dir():
        raise CacheUnavailable("照片根目錄仍離線，無法同步")
    scan_root(conn, root_id)
    pending = list(
        conn.execute(
            """
            SELECT * FROM offline_import_queue
            WHERE root_id=? AND state!='synced' ORDER BY id
            """,
            (root_id,),
        )
    )
    synced: list[int] = []
    failed: list[dict[str, object]] = []
    offline_dir = get_offline_dir().resolve()
    for row in pending:
        item = conn.execute(
            "SELECT id FROM item WHERE root_id=? AND relative_path=?",
            (root_id, row["item_relative_path"]),
        ).fetchone()
        if item is None:
            error = "重新連線後找不到原設備資料夾"
            with conn:
                conn.execute(
                    "UPDATE offline_import_queue SET state='error', last_error=? WHERE id=?",
                    (error, row["id"]),
                )
            failed.append({"id": row["id"], "error": error})
            continue
        payload = _safe_cache_path(offline_dir, row["payload_name"])
        try:
            if not payload.is_file():
                raise CacheError("離線匯入暫存檔遺失")
            data = payload.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != row["sha256"]:
                raise CacheError("離線匯入暫存檔 SHA-256 不一致")
            replace_photo_id = None
            if row["replace_relative_path"]:
                replace = conn.execute(
                    "SELECT id, relative_path FROM photo WHERE item_id=? AND relative_path=?",
                    (item["id"], row["replace_relative_path"]),
                ).fetchone()
                if replace is None:
                    raise CacheError("重新連線後找不到要換掉的原照片")
                root_path = Path(root["path"]).expanduser().resolve()
                target = (root_path / replace["relative_path"]).resolve()
                if not target.is_relative_to(root_path) or not target.is_file():
                    raise CacheError("重新連線後原照片不存在")
                if sha256_file(target) != row["expected_original_sha256"]:
                    raise CacheError("原照片內容已變更，已停止離線換圖同步")
                replace_photo_id = int(replace["id"])
            import_photo(
                conn,
                int(item["id"]),
                str(row["slot"]),
                str(row["source_name"]),
                data,
                replace_photo_id=replace_photo_id,
            )
            with conn:
                conn.execute(
                    """
                    UPDATE offline_import_queue
                    SET state='synced', last_error=NULL, synced_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (row["id"],),
                )
                conn.execute(
                    """
                    INSERT INTO audit_log(action, source_path, target_path, sha256, detail_json)
                    VALUES ('sync_offline_import', ?, ?, ?, json_object('queue_id', ?))
                    """,
                    (row["source_name"], row["item_relative_path"], row["sha256"], row["id"]),
                )
            payload.unlink(missing_ok=True)
            synced.append(int(row["id"]))
        except (CacheError, StorageError, StorageConflict, OSError, ValueError) as exc:
            error = str(exc)
            with suppress(Exception), conn:
                conn.execute(
                    "UPDATE offline_import_queue SET state='error', last_error=? WHERE id=?",
                    (error, row["id"]),
                )
            failed.append({"id": row["id"], "error": error})
    return {"root_id": root_id, "synced": synced, "failed": failed, "remaining": len(failed)}

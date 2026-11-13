"""M19-C: read-only, incremental SHA-256 duplicate discovery per photo root."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import sqlite3
import stat
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from openpyxl import Workbook

from .db import database
from .scan_jobs import scan_job_status
from .scanner import CLOUD_PLACEHOLDER_FLAGS, ScanCancelled, scan_root
from .settings import excluded_root_folders

ALGORITHM = "sha256-1"
MAX_HASH_BYTES = 100 * 1024 * 1024
AUTO_HASH_LIMIT = 128
AUTO_BYTES_LIMIT = 64 * 1024 * 1024
AUTO_BOOTSTRAP_LIMIT = 8
AUTO_BOOTSTRAP_BYTES = 8 * 1024 * 1024
_LOCK = threading.Lock()
_JOBS: dict[int, dict] = {}


class DuplicateError(ValueError):
    pass


class DuplicateCancelled(DuplicateError):
    pass


class DuplicateIndexRequired(DuplicateError):
    pass


def _root(conn: sqlite3.Connection, root_id: int) -> Path:
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        raise DuplicateError("找不到照片根目錄")
    root = Path(str(row["path"])).expanduser()
    if not root.is_dir():
        raise DuplicateError("照片根目錄目前離線，未修改重複索引")
    return root.resolve()


def _safe_stat(root: Path, relative: str) -> tuple[Path, os.stat_result] | None:
    """Reject traversal, symlinks, reparse points, stream placeholders and unsafe files."""
    path_relative = Path(relative)
    if (
        path_relative.is_absolute()
        or not path_relative.parts
        or any(part in ("", ".", "..") for part in path_relative.parts)
    ):
        return None
    current = root
    try:
        for part in path_relative.parts:
            current = current / part
            info = current.lstat()
            attributes = int(getattr(info, "st_file_attributes", 0) or 0)
            if stat.S_ISLNK(info.st_mode) or attributes & (CLOUD_PLACEHOLDER_FLAGS | 0x400):
                return None
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_HASH_BYTES:
            return None
        if not current.resolve().is_relative_to(root):
            return None
        return current, info
    except (OSError, ValueError):
        return None


def _hash_checked(path: Path, size: int, mtime_ns: int) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        after = path.lstat()
        if after.st_size != size or after.st_mtime_ns != mtime_ns:
            return None
        if int(getattr(after, "st_file_attributes", 0) or 0) & (CLOUD_PLACEHOLDER_FLAGS | 0x400):
            return None
        return digest.hexdigest()
    except OSError:
        return None


def _photos(conn: sqlite3.Connection, root_id: int) -> list[dict]:
    excluded = excluded_root_folders(conn)
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT p.id,p.item_id,p.relative_path,p.filename,p.slot,
                   p.size_bytes,p.mtime_ns,p.cloud_placeholder,
                   i.code,i.year,i.period,i.building,c.name AS category,c.code AS category_code,
                   f.sha256,f.size_bytes AS h_size,f.mtime_ns AS h_mtime,f.algorithm AS h_algo
            FROM photo p JOIN item i ON i.id=p.item_id
            JOIN category c ON c.id=i.category_id
            LEFT JOIN photo_fingerprint f
              ON f.root_id=i.root_id AND f.relative_path=p.relative_path
            WHERE i.root_id=? ORDER BY p.id
            """,
            (root_id,),
        )
        if str(row["relative_path"]).split("/", 1)[0].casefold() not in excluded
    ]


def _valid_cache(row: dict) -> bool:
    return (
        row["sha256"] is not None
        and row["h_size"] == row["size_bytes"]
        and row["h_mtime"] == row["mtime_ns"]
        and row["h_algo"] == ALGORITHM
        and not row["cloud_placeholder"]
    )


def _pending(rows: list[dict]) -> list[dict]:
    return [row for row in rows if not row["cloud_placeholder"] and not _valid_cache(row)]


def index_photos(
    conn: sqlite3.Connection,
    root_id: int,
    *,
    full: bool = False,
    max_new: int | None = None,
    max_bytes: int | None = None,
    cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """Never touches original photo contents or mtime; safe for re-scanning."""
    root = _root(conn, root_id)
    records = _photos(conn, root_id)
    candidates = [r for r in records if not r["cloud_placeholder"]]
    candidates_to_hash = [r for r in candidates if full or not _valid_cache(r)]
    if max_new is not None and len(candidates_to_hash) > max_new:
        raise DuplicateIndexRequired("重複圖片索引尚未建立完成；請到照片品質檢查執行手動重複掃描")
    if max_bytes is not None and sum(int(r["size_bytes"]) for r in candidates_to_hash) > max_bytes:
        raise DuplicateIndexRequired("照片數量較多，請先到照片品質檢查執行手動重複掃描")
    result = {
        "total": len(records),
        "done": 0,
        "analyzed": 0,
        "cached": 0,
        "skipped": 0,
        "pending": 0,
    }
    updates: list[tuple] = []
    for record in records:
        if cancelled and cancelled():
            raise DuplicateCancelled("已取消重複掃描")
        if record["cloud_placeholder"]:
            result["skipped"] += 1
        else:
            local = _safe_stat(root, record["relative_path"])
            if local is None:
                result["skipped"] += 1
            else:
                path, disk = local
                if disk.st_size != record["size_bytes"] or disk.st_mtime_ns != record["mtime_ns"]:
                    result["skipped"] += 1
                elif not full and _valid_cache(record):
                    result["cached"] += 1
                else:
                    sha = _hash_checked(path, disk.st_size, disk.st_mtime_ns)
                    if sha is None:
                        result["skipped"] += 1
                    else:
                        updates.append(
                            (
                                root_id,
                                record["relative_path"],
                                disk.st_size,
                                disk.st_mtime_ns,
                                ALGORITHM,
                                sha,
                            )
                        )
                        result["analyzed"] += 1
                        if len(updates) >= 32:
                            _upsert(conn, updates)
                            updates.clear()
        result["done"] += 1
        if on_progress and (result["done"] % 8 == 0 or result["done"] == result["total"]):
            on_progress(dict(result))
    if updates:
        _upsert(conn, updates)
    # Only prune after a fully completed scan; valid hashes are matched against
    # current photo rows and metadata, so partial/cancelled scans are safe.
    with conn:
        conn.execute(
            """
            DELETE FROM photo_fingerprint WHERE root_id=?
            AND relative_path NOT IN (
                SELECT p.relative_path FROM photo p JOIN item i ON i.id=p.item_id
                WHERE i.root_id=?
            )
            """,
            (root_id, root_id),
        )
    result["pending"] = len(_pending(_photos(conn, root_id)))
    return result


def _upsert(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    with conn:
        conn.executemany(
            """
            INSERT INTO photo_fingerprint(
                root_id,relative_path,size_bytes,mtime_ns,algorithm,sha256
            ) VALUES (?,?,?,?,?,?)
            ON CONFLICT(root_id,relative_path) DO UPDATE SET
                size_bytes=excluded.size_bytes,mtime_ns=excluded.mtime_ns,
                algorithm=excluded.algorithm,sha256=excluded.sha256,
                checked_at=CURRENT_TIMESTAMP
            """,
            rows,
        )


def _excluded_filter(conn: sqlite3.Connection, alias: str = "p") -> tuple[str, list[str]]:
    """Keep excluded top-level folders outside both completeness and match checks."""
    excluded = sorted(excluded_root_folders(conn))
    if not excluded:
        return "", []
    placeholders = ",".join("?" for _ in excluded)
    first = f"lower(substr({alias}.relative_path, 1, instr({alias}.relative_path, '/') - 1))"
    return f" AND {first} NOT IN ({placeholders})", excluded


def _missing_index_rows(
    conn: sqlite3.Connection,
    root_id: int,
    *,
    limit: int,
) -> list[dict]:
    clause, exclusions = _excluded_filter(conn)
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT p.relative_path,p.size_bytes,p.mtime_ns
              FROM item i JOIN photo p ON p.item_id=i.id
              LEFT JOIN photo_fingerprint f
                ON f.root_id=i.root_id AND f.relative_path=p.relative_path
             WHERE i.root_id=? AND p.cloud_placeholder=0
               AND (f.sha256 IS NULL OR f.algorithm!=?
                    OR f.size_bytes!=p.size_bytes OR f.mtime_ns!=p.mtime_ns)
               {clause}
             LIMIT ?
            """,
            (root_id, ALGORITHM, *exclusions, limit),
        )
    ]


def _index_missing_small(
    conn: sqlite3.Connection,
    root_id: int,
    missing: list[dict],
) -> None:
    """On-demand bootstrap hashes only missing photos, never all cached files."""
    root = _root(conn, root_id)
    rows = []
    for photo in missing:
        checked = _safe_stat(root, str(photo["relative_path"]))
        if checked is None:
            raise DuplicateIndexRequired(
                "有圖片尚未同步或無法安全讀取，請到照片品質檢查執行手動重複掃描"
            )
        path, info = checked
        if info.st_size != photo["size_bytes"] or info.st_mtime_ns != photo["mtime_ns"]:
            raise DuplicateIndexRequired("照片索引已變動，請先執行手動重複掃描")
        digest = _hash_checked(path, info.st_size, info.st_mtime_ns)
        if digest is None:
            raise DuplicateIndexRequired("照片讀取期間已變動，請先執行手動重複掃描")
        rows.append(
            (root_id, photo["relative_path"], info.st_size, info.st_mtime_ns, ALGORITHM, digest)
        )
    if rows:
        _upsert(conn, rows)


def index_imported_photo(
    conn: sqlite3.Connection,
    root_id: int,
    relative: str,
    expected_digest: str,
) -> None:
    """Write the verified import's fingerprint immediately; no disk-wide recheck."""
    root = _root(conn, root_id)
    photo = conn.execute(
        """SELECT p.relative_path,p.size_bytes,p.mtime_ns,p.cloud_placeholder
           FROM photo p JOIN item i ON i.id=p.item_id
           WHERE i.root_id=? AND p.relative_path=?""",
        (root_id, relative),
    ).fetchone()
    if photo is None or photo["cloud_placeholder"]:
        raise DuplicateIndexRequired("匯入後照片索引不存在或尚未同步")
    checked = _safe_stat(root, relative)
    if checked is None:
        raise DuplicateIndexRequired("匯入後檔案無法安全讀取")
    path, info = checked
    if info.st_size != photo["size_bytes"] or info.st_mtime_ns != photo["mtime_ns"]:
        raise DuplicateIndexRequired("匯入後檔案狀態已變更")
    # The installed bytes have already passed _install_new/_replace_atomic
    # and the final disk SHA-256 check in storage.import_photo.
    _upsert(conn, [(root_id, relative, info.st_size, info.st_mtime_ns, ALGORITHM, expected_digest)])


def find_duplicates(
    conn: sqlite3.Connection,
    root_id: int,
    digest: str,
    *,
    exclude_relative: str = "",
) -> list[dict]:
    """Indexed SQLite digest lookup; read ONLY genuine digest candidates."""
    root = _root(conn, root_id)
    clause, exclusions = _excluded_filter(conn)
    rows = conn.execute(
        f"""
        SELECT p.id AS photo_id,p.item_id,p.relative_path,p.filename,p.slot,
               p.size_bytes,p.mtime_ns,i.code,i.year,i.period,i.building,
               c.name AS category,c.code AS category_code
          FROM photo_fingerprint f INDEXED BY idx_photo_fingerprint_digest
          JOIN photo p INDEXED BY idx_photo_relative_path ON p.relative_path=f.relative_path
          JOIN item i ON i.id=p.item_id AND i.root_id=f.root_id
          JOIN category c ON c.id=i.category_id
         WHERE f.root_id=? AND f.sha256=? AND f.algorithm=?
           AND f.size_bytes=p.size_bytes AND f.mtime_ns=p.mtime_ns
           AND p.cloud_placeholder=0 AND p.relative_path!=?
           {clause}
         ORDER BY p.id
        """,
        (root_id, digest, ALGORITHM, exclude_relative, *exclusions),
    ).fetchall()
    results = []
    for row in rows:
        local = _safe_stat(root, str(row["relative_path"]))
        if local is None:
            raise DuplicateIndexRequired("命中照片無法安全讀取，請完成同步後再檢查")
        path, info = local
        if info.st_size != row["size_bytes"] or info.st_mtime_ns != row["mtime_ns"]:
            raise DuplicateIndexRequired("命中照片在外部被修改，請執行手動重複掃描")
        if _hash_checked(path, info.st_size, info.st_mtime_ns) != digest:
            raise DuplicateIndexRequired("照片索引與檔案內容不同，請重新執行重複掃描")
        results.append(
            {
                "photo_id": row["photo_id"],
                "item_id": row["item_id"],
                "filename": row["filename"],
                "relative_path": row["relative_path"],
                "category": row["category"],
                "category_code": row["category_code"],
                "code": row["code"],
                "year": row["year"],
                "period": row["period"],
                "building": row["building"],
                "slot": row["slot"],
                "mtime_ns": row["mtime_ns"],
            }
        )
    return results


def preflight(
    conn: sqlite3.Connection, root_id: int, digest: str, *, exclude_relative: str = ""
) -> list[dict]:
    if job_status(root_id)["state"] == "running":
        raise DuplicateIndexRequired("重複圖片索引正在建立中，請完成後再加入照片")
    # A SQLite metadata-only check replaces the old disk-wide cached file walk.
    # Bootstrap only a handful of newly seen photos; otherwise require the
    # existing explicit, cancellable duplicate scan rather than stall the paste.
    missing = _missing_index_rows(conn, root_id, limit=AUTO_BOOTSTRAP_LIMIT + 1)
    if (
        len(missing) > AUTO_BOOTSTRAP_LIMIT
        or sum(int(row["size_bytes"]) for row in missing) > AUTO_BOOTSTRAP_BYTES
    ):
        raise DuplicateIndexRequired("部分照片尚未建立指紋，請到照片品質檢查執行手動重複掃描")
    if missing:
        _index_missing_small(conn, root_id, missing)
    return find_duplicates(conn, root_id, digest, exclude_relative=exclude_relative)


def grouped(
    conn: sqlite3.Connection,
    root_id: int,
    *,
    category: str = "",
    query: str = "",
    offset: int = 0,
    limit: int = 40,
) -> dict:
    root = _root(conn, root_id)
    records = _photos(conn, root_id)
    by_hash: dict[str, list[dict]] = defaultdict(list)
    pending = 0
    skipped = 0
    for record in records:
        if record["cloud_placeholder"]:
            skipped += 1
            continue
        if not _valid_cache(record):
            pending += 1
            continue
        local = _safe_stat(root, record["relative_path"])
        if local is None:
            skipped += 1
            continue
        _, info = local
        if info.st_size != record["size_bytes"] or info.st_mtime_ns != record["mtime_ns"]:
            pending += 1
            continue
        by_hash[str(record["sha256"])].append(
            {
                "photo_id": record["id"],
                "item_id": record["item_id"],
                "filename": record["filename"],
                "relative_path": record["relative_path"],
                "slot": record["slot"],
                "mtime_ns": record["mtime_ns"],
                "code": record["code"],
                "year": record["year"],
                "period": record["period"],
                "building": record["building"],
                "category": record["category"],
                "category_code": record["category_code"],
            }
        )
    groups = []
    for sha, photos in by_hash.items():
        if len(photos) < 2:
            continue
        if not any(
            (not category or record["category_code"] == category)
            and (not query or query.casefold() in record["code"].casefold())
            for record in photos
        ):
            continue
        devices = len({record["item_id"] for record in photos})
        groups.append(
            {
                "sha256": sha,
                "count": len(photos),
                "device_count": devices,
                "photos": photos,
            }
        )
    groups.sort(key=lambda g: (-g["device_count"], -g["count"], g["sha256"]))
    total = len(groups)
    return {
        "total": total,
        "total_photos": sum(g["count"] for g in groups),
        "total_devices": len({p["item_id"] for g in groups for p in g["photos"]}),
        "pending": pending,
        "skipped": skipped,
        "groups": groups[offset : offset + limit],
    }


def job_status(root_id: int) -> dict:
    with _LOCK:
        return dict(
            _JOBS.get(
                root_id,
                {
                    "state": "idle",
                    "phase": "",
                    "full": False,
                    "total": 0,
                    "done": 0,
                    "analyzed": 0,
                    "cached": 0,
                    "skipped": 0,
                    "pending": 0,
                    "error": "",
                    "started_at": None,
                },
            )
        )


def start_scan(root_id: int, *, full: bool = False) -> dict:
    with _LOCK:
        if _JOBS.get(root_id, {}).get("state") == "running":
            raise DuplicateError("重複圖片掃描已在進行中")
        job = {
            "state": "running",
            "phase": "indexing",
            "full": full,
            "total": 0,
            "done": 0,
            "analyzed": 0,
            "cached": 0,
            "skipped": 0,
            "pending": 0,
            "error": "",
            "cancel": False,
            "started_at": time.time(),
        }
        _JOBS[root_id] = job
    thread = threading.Thread(
        target=_run,
        args=(root_id, job),
        name=f"duplicates-{root_id}",
        daemon=True,
    )
    thread.start()
    return dict(job)


def cancel_scan(root_id: int) -> dict:
    with _LOCK:
        if root_id in _JOBS:
            _JOBS[root_id]["cancel"] = True
    return job_status(root_id)


def _run(root_id: int, job: dict) -> None:
    try:
        with database() as conn:
            from .photo_quality import job_status as quality_job_status

            if quality_job_status(root_id)["state"] == "running":
                raise DuplicateError("照片品質掃描正在進行中，請完成後再執行重複掃描")
            if scan_job_status(root_id)["state"] == "running":
                raise DuplicateError("原照片索引正在掃描，請完成後再執行")
            # Refresh photo metadata first to see copies made in Explorer.
            scan_root(conn, root_id, cancel_check=lambda: job["cancel"])
            job["phase"] = "hashing"

            def progress(value: dict) -> None:
                job.update(value)

            result = index_photos(
                conn,
                root_id,
                full=bool(job["full"]),
                cancelled=lambda: bool(job["cancel"]),
                on_progress=progress,
            )
            job.update(result)
            job["state"] = "completed"
    except (DuplicateCancelled, ScanCancelled):
        job["state"] = "cancelled"
    except Exception as exc:
        job["state"] = "error"
        job["error"] = str(exc)[:240]


def export_groups(groups: list[dict], fmt: str) -> tuple[bytes, str]:
    headings = (
        "重複群組",
        "照片編號",
        "設備類別",
        "設備編號",
        "年份",
        "月份",
        "棟別",
        "槽位",
        "檔名",
        "相對路徑",
        "SHA-256",
    )
    rows = []
    for index, group in enumerate(groups, start=1):
        for photo in group["photos"]:
            rows.append(
                (
                    index,
                    photo["photo_id"],
                    photo["category"],
                    photo["code"],
                    photo["year"],
                    photo["period"],
                    photo["building"],
                    photo["slot"] or "",
                    photo["filename"],
                    photo["relative_path"],
                    group["sha256"],
                )
            )

    def safe(value: object) -> object:
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    rows = [tuple(safe(cell) for cell in row) for row in rows]
    if fmt == "csv":
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerow(headings)
        writer.writerows(rows)
        return ("\ufeff" + text.getvalue()).encode("utf-8"), "text/csv; charset=utf-8"
    if fmt == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "重複圖片"
        sheet.append(headings)
        for row in rows:
            sheet.append(row)
        output = io.BytesIO()
        workbook.save(output)
        return (
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    raise DuplicateError("不支援的匯出格式")

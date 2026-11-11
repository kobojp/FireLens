"""Read-only manual photo-quality checks; separate from device issues."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageFilter, ImageOps, ImageStat

from .db import database
from .organizer import _canonical_filename
from .scan_jobs import scan_job_status
from .scanner import CLOUD_PLACEHOLDER_FLAGS, ScanCancelled, scan_root

ALGORITHM = "laplacian-pillow-1"
SLOTS = {
    "extinguisher": ("編號", "藥劑", "完成"),
    "box": ("前", "中", "後"),
    "lamp": ("前", "中", "後"),
}
_LOCK = threading.Lock()
_JOBS: dict[int, dict] = {}
_SEMAPHORE = threading.Semaphore(1)  # prevent simultaneous expensive picture decodes


class QualityError(ValueError):
    pass


def quality_algorithm(sensitivity: float) -> str:
    return f"{ALGORITHM}@{sensitivity:.2f}"


def version_key(size: int, mtime: int, sensitivity: float = 1.0) -> str:
    return f"{size}:{mtime}:{quality_algorithm(sensitivity)}"


def sensitivity_for(conn: sqlite3.Connection, root_id: int) -> float:
    row = conn.execute(
        "SELECT sensitivity FROM photo_quality_setting WHERE root_id=?", (root_id,)
    ).fetchone()
    return float(row["sensitivity"]) if row else 1.0


def save_sensitivity(conn: sqlite3.Connection, root_id: int, value: float) -> dict:
    if not (0.5 <= value <= 1.5):
        raise QualityError("偵測靈敏度必須在 0.5 至 1.5 之間")
    if not conn.execute("SELECT 1 FROM root WHERE id=?", (root_id,)).fetchone():
        raise QualityError("找不到根目錄")
    with conn:
        conn.execute(
            "INSERT INTO photo_quality_setting(root_id,sensitivity) VALUES (?,?) "
            "ON CONFLICT(root_id) DO UPDATE SET sensitivity=excluded.sensitivity",
            (root_id, value),
        )
    return {"root_id": root_id, "sensitivity": value}


def quality_score(path: Path, category: str, slot: str, sensitivity: float = 1.0) -> dict:
    """Analyze an in-memory working image derived from the original."""
    try:
        with Image.open(path) as image:
            if image.width * image.height > 50_000_000:
                raise ValueError("影像尺寸超出安全上限")
            width, height = image.size
            work = ImageOps.exif_transpose(image)
            work.thumbnail((900, 900), Image.Resampling.LANCZOS)
            gray = work.convert("L")
            mean, texture = ImageStat.Stat(gray).mean[0], ImageStat.Stat(gray).stddev[0]
            edges = gray.filter(
                ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)
            )
            sharp = ImageStat.Stat(edges).var[0]
            issues, reasons = [], []
            if min(width, height) < 480:
                issues.append("resolution")
                reasons.append("原圖解析度不足")
            if mean < 42:
                issues.append("dark")
                reasons.append("照片過暗")
            if mean > 226:
                issues.append("bright")
                reasons.append("照片過曝")
            threshold = (
                (90 if slot in ("編號", "藥劑") else 65)
                * (0.7 if category == "lamp" else 1)
                * sensitivity
            )
            if texture < 15:
                status = "uncertain"
                reasons.append("低紋理畫面無法可靠判斷模糊")
            elif sharp < threshold * 0.43:
                status = "high"
                issues.append("blur")
                reasons.append("高度疑似失焦")
            elif sharp < threshold:
                status = "possible"
                issues.append("blur")
                reasons.append("疑似模糊")
            else:
                status = "normal"
            if issues and status == "normal":
                status = "possible"
            return {
                "status": status,
                "score": round(sharp, 2),
                "issues": issues,
                "reason": "、".join(reasons),
            }
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        return {
            "status": "uncertain",
            "score": None,
            "issues": ["decode"],
            "reason": f"無法安全解碼：{type(exc).__name__}",
        }


def _root(conn: sqlite3.Connection, root_id: int) -> Path:
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if not row:
        raise QualityError("根目錄不存在")
    path = Path(str(row["path"])).expanduser()
    if not path.is_dir():
        raise QualityError("根目錄離線，不變更原本紀錄")
    return path.resolve()


def _candidates(conn: sqlite3.Connection, root_id: int, category: str, period: str) -> list[dict]:
    if category and category not in SLOTS:
        raise QualityError("設備類別不正確")
    return [
        dict(row)
        for row in conn.execute(
            """
        SELECT p.id, p.relative_path, p.slot, p.size_bytes, p.mtime_ns,
               p.cloud_placeholder, c.code AS category
        FROM photo p JOIN item i ON i.id=p.item_id
        JOIN category c ON c.id=i.category_id
        WHERE i.root_id=? AND (?='' OR c.code=?) AND (?='' OR i.period=?)
        ORDER BY p.id
        """,
            (root_id, category, category, period, period),
        )
    ]


def scan_quality(root_id: int, *, full: bool = False, category: str = "", period: str = "") -> dict:
    with _LOCK:
        if _JOBS.get(root_id, {}).get("state") == "running":
            raise QualityError("照片品質掃描已在進行中")
        job = {
            "state": "running",
            "total": 0,
            "done": 0,
            "analyzed": 0,
            "cached": 0,
            "skipped": 0,
            "flagged": 0,
            "cancel": False,
            "error": "",
            "full": full,
            "phase": "indexing",
        }
        _JOBS[root_id] = job
    thread = threading.Thread(
        target=_run,
        args=(root_id, category, period, job),
        name=f"quality-{root_id}",
        daemon=True,
    )
    thread.start()
    return dict(job)


def _run(root_id: int, category: str, period: str, job: dict) -> None:
    try:
        with database() as conn:
            root = _root(conn, root_id)
            sensitivity = sensitivity_for(conn, root_id)
            algorithm = quality_algorithm(sensitivity)
            # Manual quality scan refreshes the metadata index first, so a
            # newly added or changed photo is eligible for incremental scoring.
            # Never run alongside an existing regular photo-index scan.
            if scan_job_status(root_id)["state"] == "running":
                raise QualityError("照片索引正在掃描，請完成後再執行品質掃描")
            with _SEMAPHORE:
                scan_root(conn, root_id, cancel_check=lambda: bool(job["cancel"]))
            job["phase"] = "analyzing"
            photos = _candidates(conn, root_id, category, period)
            job["total"] = len(photos)
            for record in photos:
                if job["cancel"]:
                    job["state"] = "cancelled"
                    break
                relative = record["relative_path"]
                if record["cloud_placeholder"]:
                    job["skipped"] += 1
                    job["done"] += 1
                    continue
                path = root / relative
                if (
                    path.is_symlink()
                    or not path.resolve().is_relative_to(root)
                    or not path.is_file()
                ):
                    job["skipped"] += 1
                    job["done"] += 1
                    continue
                stat = path.stat()
                if (
                    stat.st_size == 0
                    or stat.st_size > 100 * 1024 * 1024
                    or int(getattr(stat, "st_file_attributes", 0) or 0) & CLOUD_PLACEHOLDER_FLAGS
                ):
                    job["skipped"] += 1
                    job["done"] += 1
                    continue
                # Prevent inaccurate cache matches when disk changed after the
                # latest normal FireLens folder index scan.
                if stat.st_size != record["size_bytes"] or stat.st_mtime_ns != record["mtime_ns"]:
                    job["skipped"] += 1
                    job["done"] += 1
                    continue
                old = conn.execute(
                    "SELECT size_bytes,mtime_ns,algorithm FROM photo_quality "
                    "WHERE root_id=? AND relative_path=?",
                    (root_id, relative),
                ).fetchone()
                if (
                    not job["full"]
                    and old
                    and (
                        old["size_bytes"] == record["size_bytes"]
                        and old["mtime_ns"] == record["mtime_ns"]
                        and old["algorithm"] == algorithm
                    )
                ):
                    job["cached"] += 1
                    job["done"] += 1
                    continue
                with _SEMAPHORE:
                    if job["cancel"]:
                        job["state"] = "cancelled"
                        break
                    result = quality_score(
                        path, record["category"], record["slot"] or "", sensitivity
                    )
                with conn:
                    conn.execute(
                        """
                        INSERT INTO photo_quality(root_id,relative_path,size_bytes,mtime_ns,
                            algorithm,status,score,issues_json,reason)
                        VALUES (?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(root_id,relative_path) DO UPDATE SET
                          size_bytes=excluded.size_bytes,mtime_ns=excluded.mtime_ns,
                          algorithm=excluded.algorithm,status=excluded.status,
                          score=excluded.score,issues_json=excluded.issues_json,
                          reason=excluded.reason,checked_at=CURRENT_TIMESTAMP
                        """,
                        (
                            root_id,
                            relative,
                            record["size_bytes"],
                            record["mtime_ns"],
                            algorithm,
                            result["status"],
                            result["score"],
                            json.dumps(result["issues"]),
                            result["reason"],
                        ),
                    )
                job["analyzed"] += 1
                job["done"] += 1
                job["flagged"] += result["status"] != "normal"
            if job["state"] == "running":
                job["state"] = "completed"
    except ScanCancelled:
        job["state"] = "cancelled"
    except Exception as exc:
        job["state"] = "error"
        job["error"] = str(exc)[:240]


def job_status(root_id: int) -> dict:
    with _LOCK:
        return dict(
            _JOBS.get(
                root_id,
                {
                    "state": "idle",
                    "total": 0,
                    "done": 0,
                    "analyzed": 0,
                    "cached": 0,
                    "skipped": 0,
                    "flagged": 0,
                    "cancel": False,
                    "error": "",
                },
            )
        )


def cancel_quality(root_id: int) -> dict:
    with _LOCK:
        if root_id in _JOBS:
            _JOBS[root_id]["cancel"] = True
    return job_status(root_id)


def gallery(
    conn: sqlite3.Connection,
    root_id: int,
    *,
    category: str = "",
    period: str = "",
    building: str = "",
    query: str = "",
    problem_only: bool = True,
    status_filter: str = "",
    review_filter: str = "",
    sort_by: str = "latest",
    limit: int = 40,
    offset: int = 0,
) -> dict:
    if category and category not in SLOTS:
        raise QualityError("設備類別不正確")
    if status_filter not in (
        "",
        "high",
        "possible",
        "normal",
        "uncertain",
        "unscanned",
        "missing",
        "unmapped",
        "dirty_name",
        "multi_slot",
    ):
        raise QualityError("品質篩選不正確")
    if review_filter not in ("", "confirmed", "ignore", "reshoot", "wrong_content", "pending"):
        raise QualityError("人工覆核篩選不正確")
    if sort_by not in ("latest", "code", "severity"):
        raise QualityError("排序方式不正確")
    if not conn.execute("SELECT 1 FROM root WHERE id=?", (root_id,)).fetchone():
        raise QualityError("找不到根目錄")
    rows = [
        dict(row)
        for row in conn.execute(
            """
        SELECT i.id,i.code,i.year,i.period,i.building,i.status AS item_status,
               c.code AS category
        FROM item i JOIN category c ON c.id=i.category_id
        WHERE i.root_id=? AND (?='' OR c.code=?) AND (?='' OR i.period=?)
          AND (?='' OR i.building=?) AND instr(i.code,?)>0
        ORDER BY i.year DESC,i.period DESC,i.building,i.code
        """,
            (root_id, category, category, period, period, building, building, query),
        )
    ]
    sensitivity = sensitivity_for(conn, root_id)
    algorithm = quality_algorithm(sensitivity)
    photos: dict[int, list[dict]] = {}
    for row in conn.execute(
        """
        SELECT p.item_id,p.id,p.filename,p.relative_path,p.extension,p.slot,
               p.size_bytes,p.mtime_ns,p.cloud_placeholder,q.status,q.score,
               q.issues_json,q.reason,q.review,q.review_version,
               q.size_bytes AS q_size,q.mtime_ns AS q_time,q.algorithm AS q_algorithm
        FROM photo p JOIN item i ON i.id=p.item_id
        LEFT JOIN photo_quality q ON q.root_id=i.root_id AND q.relative_path=p.relative_path
        WHERE i.root_id=? ORDER BY p.id
        """,
        (root_id,),
    ):
        data = dict(row)
        data["stale"] = (
            data["q_size"] != data["size_bytes"]
            or data["q_time"] != data["mtime_ns"]
            or data["q_algorithm"] != algorithm
        )
        if data["stale"]:
            data["status"] = "unscanned"
            data["reason"] = ""
            data["score"] = None
            data["issues_json"] = "[]"
        data["review"] = data["review"] or ""
        if data["review_version"] != version_key(data["size_bytes"], data["mtime_ns"], sensitivity):
            data["review"] = ""
        data["issues"] = json.loads(data.pop("issues_json") or "[]")
        for key in ("q_size", "q_time", "q_algorithm", "review_version"):
            data.pop(key, None)
        photos.setdefault(row["item_id"], []).append(data)
    items = []
    for item in rows:
        pictures = photos.get(item["id"], [])
        legacy = item["category"] == "box" and item["item_status"] == "legacy"
        slots = ["舊制照片"] if legacy else list(SLOTS[item["category"]])
        if not legacy and any(p["slot"] is None for p in pictures):
            slots.append("未對應照片")
        for image in pictures:
            # Share the Organizer filename suggestion rule without hashing or renaming files.
            suggested, filename_reason = (
                _canonical_filename(image["filename"])
                if item["category"] == "extinguisher" and not legacy
                else (None, None)
            )
            image["suggested_filename"] = suggested
            image["filename_reason"] = filename_reason
            image["display_slot"] = "舊制照片" if legacy else (image["slot"] or "未對應照片")
            image["filename_issue"] = not legacy and image["slot"] is None
        slot_counts = (
            {slot: sum(p["slot"] == slot for p in pictures) for slot in SLOTS[item["category"]]}
            if not legacy
            else {}
        )
        duplicate_slots = [slot for slot, count in slot_counts.items() if count > 1]
        for image in pictures:
            image["multi_slot"] = image["slot"] in duplicate_slots if not legacy else False
        missing = (
            []
            if legacy
            else [
                slot
                for slot in SLOTS[item["category"]]
                if slot not in {p["slot"] for p in pictures}
            ]
        )
        problems = sum(
            p["status"] not in (None, "normal", "unscanned") and p["review"] != "ignore"
            for p in pictures
        )
        problems += sum(p["review"] in ("reshoot", "wrong_content") for p in pictures)
        problems += sum(p["filename_issue"] for p in pictures)
        problems += sum(bool(p["suggested_filename"]) for p in pictures)
        problems += sum(slot_counts[slot] - 1 for slot in duplicate_slots)
        if problem_only and not (problems or missing):
            continue
        if status_filter and not (
            (status_filter == "missing" and missing)
            or (status_filter == "unmapped" and any(p["filename_issue"] for p in pictures))
            or (status_filter == "dirty_name" and any(p["suggested_filename"] for p in pictures))
            or (status_filter == "multi_slot" and bool(duplicate_slots))
            or any(p["status"] == status_filter for p in pictures)
        ):
            continue
        if review_filter and not any(
            (p["review"] == review_filter if review_filter != "pending" else not p["review"])
            for p in pictures
        ):
            continue
        items.append(
            {
                **item,
                "photos": pictures,
                "slots": slots,
                "missing_slots": missing,
                "duplicate_slots": duplicate_slots,
                "problems": problems,
            }
        )
    if sort_by == "code":
        items.sort(key=lambda item: (item["code"].casefold(), item["id"]))
    elif sort_by == "severity":
        items.sort(key=lambda item: (-item["problems"], -len(item["missing_slots"]), item["code"]))
    return {
        "total": len(items),
        "total_devices": len(rows),
        "flagged_photos": sum(i["problems"] for i in items),
        "items": items[offset : offset + limit],
    }


def review_photo(conn: sqlite3.Connection, photo_id: int, review: str) -> dict:
    if review not in ("", "confirmed", "ignore", "reshoot", "wrong_content"):
        raise QualityError("覆核狀態不正確")
    photo = conn.execute(
        "SELECT i.root_id,p.relative_path,p.size_bytes,p.mtime_ns "
        "FROM photo p JOIN item i ON i.id=p.item_id WHERE p.id=?",
        (photo_id,),
    ).fetchone()
    if photo is None:
        raise QualityError("照片不存在")
    sensitivity = sensitivity_for(conn, photo["root_id"])
    with conn:
        conn.execute(
            """
            INSERT INTO photo_quality(root_id,relative_path,size_bytes,mtime_ns,
                algorithm,status,issues_json,review,review_version)
            VALUES (?,?,?,?,?,'unscanned','[]',?,?)
            ON CONFLICT(root_id,relative_path) DO UPDATE SET
              review=excluded.review,review_version=excluded.review_version
            """,
            (
                photo["root_id"],
                photo["relative_path"],
                photo["size_bytes"],
                photo["mtime_ns"],
                quality_algorithm(sensitivity),
                review,
                version_key(photo["size_bytes"], photo["mtime_ns"], sensitivity),
            ),
        )
    return {"photo_id": photo_id, "review": review}


def _problem_description(photo: dict) -> str:
    details = [photo["reason"] or (photo["status"] if photo["status"] != "normal" else "")]
    if photo.get("suggested_filename"):
        details.append(f"建議檔名：{photo['suggested_filename']}")
    if photo.get("multi_slot"):
        details.append("同槽多圖")
    if photo.get("filename_issue"):
        details.append("未辨識用途")
    return "、".join(filter(None, details))


def export_quality(items: list[dict], fmt: str) -> tuple[bytes, str]:
    headers = (
        "設備編號",
        "類別",
        "年份",
        "批次",
        "棟別",
        "照片槽位",
        "檔名",
        "問題",
        "清晰分數",
        "人工狀態",
        "照片相對路徑",
    )
    rows = [
        [
            item["code"],
            item["category"],
            item["year"],
            item["period"],
            item["building"],
            p["slot"] or "未對應",
            p["filename"],
            _problem_description(p),
            p["score"],
            p["review"],
            p["relative_path"],
        ]
        for item in items
        for p in item["photos"]
        if p["status"] not in (None, "normal", "unscanned")
        or p["review"] in ("reshoot", "wrong_content")
        or p.get("filename_issue")
        or p.get("suggested_filename")
        or p.get("multi_slot")
    ]
    # Include missing expected slots as actionable photo-quality problems.
    for item in items:
        for slot in item["missing_slots"]:
            rows.append(
                [
                    item["code"],
                    item["category"],
                    item["year"],
                    item["period"],
                    item["building"],
                    slot,
                    "",
                    "缺照片",
                    None,
                    "",
                    "",
                ]
            )

    # Excel and spreadsheet apps must never evaluate user-supplied filenames
    # or equipment codes as formulas.
    def safe(cell: object) -> object:
        if isinstance(cell, str) and cell.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + cell
        return cell

    rows = [[safe(cell) for cell in row] for row in rows]
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return ("\ufeff" + buffer.getvalue()).encode("utf-8"), "text/csv; charset=utf-8"
    if fmt == "xlsx":
        book = Workbook()
        sheet = book.active
        sheet.title = "照片品質"
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        buffer = io.BytesIO()
        book.save(buffer)
        return (
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    raise QualityError("不支援的匯出格式")

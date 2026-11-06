"""設備資料夾原位更名；照片內容和受保護清冊永不更動。"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
from pathlib import Path

from .scan_jobs import scan_job_status
from .storage import StorageConflict, StorageError

WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def validate_item_folder_name(value: str) -> str:
    if not value or value != value.strip() or value.endswith("."):
        raise StorageError("資料夾名稱不可為空、不可有前後空白或尾端句點")
    if (
        len(value) > 120
        or value in {".", ".."}
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
        or value.split(".")[0].upper() in WINDOWS_RESERVED
    ):
        raise StorageError("資料夾名稱包含 Windows 不允許的字元或保留名稱")
    return value


def _reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def rename_item_folder(
    conn: sqlite3.Connection,
    item_id: int,
    new_name: str,
) -> dict[str, object]:
    clean = validate_item_folder_name(new_name)
    row = conn.execute(
        """
        SELECT i.id, i.root_id, i.code, i.relative_path, r.path AS root_path,
               r.is_cloud_stream
        FROM item i JOIN root r ON r.id=i.root_id WHERE i.id=?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise StorageError("找不到指定設備")
    if scan_job_status(int(row["root_id"]))["state"] == "running":
        raise StorageConflict("正在掃描，請先等待掃描完成後再更名")
    pending = conn.execute(
        """
        SELECT COUNT(*) FROM offline_import_queue
        WHERE root_id=? AND item_relative_path=? AND state IN ('pending', 'error')
        """,
        (row["root_id"], row["relative_path"]),
    ).fetchone()[0]
    if pending:
        raise StorageConflict("此設備仍有離線匯入工作，請先同步後再更名")
    if conn.execute(
        "SELECT 1 FROM photo WHERE item_id=? AND cloud_placeholder=1", (item_id,)
    ).fetchone():
        raise StorageConflict("設備內有雲端未下載照片，無法安全更名")

    root = Path(str(row["root_path"])).expanduser().resolve()
    relative = Path(str(row["relative_path"]))
    source = root / relative
    if not root.is_dir() or not source.is_dir():
        raise StorageError("照片根目錄離線或設備資料夾不存在")
    if source.resolve() != source.absolute() or _reparse(source):
        raise StorageError("來源資料夾含有符號連結或重解析點")
    if source.name != row["code"] or source.name == clean:
        raise StorageConflict("名稱沒有改變，或索引與磁碟資料夾不一致")
    if not source.resolve().is_relative_to(root):
        raise StorageError("來源資料夾超出照片根目錄")
    parent = source.parent
    if parent.resolve() != parent.absolute() or not parent.is_relative_to(root):
        raise StorageError("資料夾路徑不安全")
    # Windows 大小寫不敏感，包含僅變更大小寫都視為撞名。
    if any(sibling.name.casefold() == clean.casefold() for sibling in parent.iterdir()):
        raise StorageConflict("同層已存在同名資料夾，不可覆蓋")
    target = parent / clean
    if target.exists() or target.is_symlink():
        raise StorageConflict("目標路徑已存在")
    old_relative = relative.as_posix()
    new_relative = (relative.parent / clean).as_posix()
    photos = conn.execute(
        "SELECT id, relative_path FROM photo WHERE item_id=?", (item_id,)
    ).fetchall()
    if any(not str(photo["relative_path"]).startswith(old_relative + "/") for photo in photos):
        raise StorageError("照片索引路徑與設備資料夾不一致，請先重新掃描")

    renamed = False
    try:
        with conn:
            os.rename(source, target)
            renamed = True
            conn.execute(
                """
                UPDATE item SET code=?, relative_path=?, dir_mtime_ns=? WHERE id=?
                """,
                (clean, new_relative, target.stat().st_mtime_ns, item_id),
            )
            for photo in photos:
                new_photo_path = new_relative + str(photo["relative_path"])[len(old_relative) :]
                conn.execute(
                    "UPDATE photo SET relative_path=?, thumbnail_path=NULL WHERE id=?",
                    (new_photo_path, photo["id"]),
                )
            conn.execute(
                """
                UPDATE item_issue SET item_relative_path=?, device_code=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE root_id=? AND item_relative_path=?
                """,
                (new_relative, clean, row["root_id"], old_relative),
            )
            conn.execute(
                """
                INSERT INTO audit_log(action, source_path, target_path, detail_json)
                VALUES ('rename_item_folder', ?, ?, ?)
                """,
                (
                    old_relative,
                    new_relative,
                    json.dumps({"item_id": item_id, "photos": len(photos)}, ensure_ascii=False),
                ),
            )
    except (OSError, sqlite3.Error) as exc:
        if renamed:
            try:
                os.rename(target, source)
            except OSError as rollback_exc:
                raise StorageError(
                    "資料夾索引更新失敗且無法還原磁碟名稱，"
                    f"請停止操作並檢查 {target}：{rollback_exc}"
                ) from exc
        raise StorageError(f"設備資料夾更名失敗，原資料仍保留：{exc}") from exc
    return {
        "id": item_id,
        "root_id": int(row["root_id"]),
        "old_name": str(row["code"]),
        "new_name": clean,
        "old_relative_path": old_relative,
        "relative_path": new_relative,
        "photo_count": len(photos),
    }

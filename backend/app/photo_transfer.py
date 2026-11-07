"""Conservative photo-slot move/swap for a single device folder.

The filesystem is authoritative. Never overwrite a filename; all paths and
hashes are checked again immediately before executing a previewed operation.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import suppress
from pathlib import Path

from .organizer import (
    OrganizerConflict,
    OrganizerError,
    _photo_row_for_rename,
    _rename_no_overwrite,
    _root_path,
    _safe_file_path_preserve_name,
)
from .scanner import refresh_item_index
from .settings import custom_slots_for
from .storage import sha256_file


def preview_slot_transfer(
    conn: sqlite3.Connection, source_id: int, target_slot: str, target_id: int | None = None
) -> dict[str, object]:
    source = _photo_row_for_rename(conn, source_id)
    if source["cloud_placeholder"]:
        raise OrganizerConflict("來源照片尚未下載，請先讓 Google Drive 檔案可離線使用")
    item = conn.execute(
        """SELECT c.slots_json, c.code AS category_code
           FROM item i JOIN category c ON c.id=i.category_id WHERE i.id=?""",
        (source["item_id"],),
    ).fetchone()
    if item is None:
        raise OrganizerError("找不到設備")
    import json

    allowed = set(json.loads(item["slots_json"])) | set(
        custom_slots_for(conn, item["category_code"])
    )
    if target_slot not in allowed:
        raise OrganizerError("目的照片槽位不屬於此設備類別")
    if target_slot == source["slot"]:
        raise OrganizerError("來源與目的照片槽位相同")
    if source["slot"] not in allowed:
        raise OrganizerError("未對應照片請使用原有歸槽功能")
    root = _root_path(conn, int(source["root_id"]))
    source_path = _safe_file_path_preserve_name(root, str(source["relative_path"]))
    if not source_path.is_file() or source_path.is_symlink():
        raise OrganizerConflict("來源照片已不存在或不是一般檔案")
    dest = None
    dest_path = None
    if target_id is not None:
        dest = _photo_row_for_rename(conn, target_id)
        if dest["item_id"] != source["item_id"] or dest["root_id"] != source["root_id"]:
            raise OrganizerError("只能交換同一台設備的照片")
        if dest["slot"] != target_slot or dest["cloud_placeholder"]:
            raise OrganizerConflict("目的照片槽位或雲端狀態已改變")
        dest_path = _safe_file_path_preserve_name(root, str(dest["relative_path"]))
        if not dest_path.is_file() or dest_path.is_symlink():
            raise OrganizerConflict("目的照片已不存在或不是一般檔案")
    else:
        existing = conn.execute(
            "SELECT COUNT(*) FROM photo WHERE item_id=? AND slot=?",
            (source["item_id"], target_slot),
        ).fetchone()[0]
        if existing:
            raise OrganizerConflict("目的槽位已有照片，請選擇要交換的照片")

    source_target = source_path.with_name(f"{target_slot}{source_path.suffix}")
    dest_target = dest_path.with_name(f"{source['slot']}{dest_path.suffix}") if dest_path else None
    paths = [source_path, source_target]
    if dest_path:
        paths.extend((dest_path, dest_target))
    if len({str(path).casefold() for path in paths if path is not None}) != len(paths) and not (
        dest_path is not None and source_target == dest_path and dest_target == source_path
    ):
        raise OrganizerConflict("交換後檔名與既有檔案重複")
    allowed_existing = {source_path}
    if dest_path is not None:
        allowed_existing.add(dest_path)
    for proposed in (source_target, dest_target):
        if proposed is not None and proposed.exists() and proposed not in allowed_existing:
            raise OrganizerConflict(f"目的檔名 {proposed.name} 已存在，不允許覆蓋")

    if source_path.parent != source_target.parent or (
        dest_path is not None and dest_path.parent != source_path.parent
    ):
        raise OrganizerError("只允許在同一設備資料夾內交換照片")
    return {
        "mode": "swap" if dest is not None else "move",
        "item_id": int(source["item_id"]),
        "root_id": int(source["root_id"]),
        "source_photo_id": source_id,
        "target_photo_id": target_id,
        "source_slot": str(source["slot"]),
        "target_slot": target_slot,
        "source_name": source_path.name,
        "target_name": source_target.name,
        "target_source_name": dest_path.name if dest_path else None,
        "target_new_name": dest_target.name if dest_target else None,
        "source_sha256": sha256_file(source_path),
        "target_sha256": sha256_file(dest_path) if dest_path else None,
    }


def execute_slot_transfer(
    conn: sqlite3.Connection,
    source_id: int,
    target_slot: str,
    target_id: int | None,
    expected_source_sha256: str,
    expected_target_sha256: str | None,
) -> dict[str, object]:
    preview = preview_slot_transfer(conn, source_id, target_slot, target_id)
    if preview["source_sha256"] != expected_source_sha256 or (
        preview["target_sha256"] != expected_target_sha256
    ):
        raise OrganizerConflict("照片內容或目標已變更，請重新預覽")
    root = _root_path(conn, int(preview["root_id"]))
    source = _photo_row_for_rename(conn, source_id)
    src = _safe_file_path_preserve_name(root, str(source["relative_path"]))
    src_final = src.with_name(str(preview["target_name"]))
    dst = None
    dst_final = None
    if target_id is not None:
        target = _photo_row_for_rename(conn, target_id)
        dst = _safe_file_path_preserve_name(root, str(target["relative_path"]))
        dst_final = dst.with_name(str(preview["target_new_name"]))
    stage = src.with_name(f".firelens-transfer-{uuid.uuid4().hex}.tmp")
    steps: list[tuple[Path, Path]] = []
    try:
        _rename_no_overwrite(src, stage)
        steps.append((src, stage))
        if dst is not None and dst_final is not None:
            _rename_no_overwrite(dst, dst_final)
            steps.append((dst, dst_final))
        _rename_no_overwrite(stage, src_final)
        steps.append((stage, src_final))
        if sha256_file(src_final) != expected_source_sha256:
            raise OrganizerConflict("移動後來源照片驗證失敗")
        if dst_final is not None and sha256_file(dst_final) != expected_target_sha256:
            raise OrganizerConflict("交換後目的照片驗證失敗")
        refresh_item_index(conn, int(preview["item_id"]))
        with conn:
            log = conn.execute(
                """INSERT INTO slot_transfer_log(
                    root_id, item_relative_path, source_before, source_after,
                    target_before, target_after, source_sha256, target_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    preview["root_id"],
                    src.parent.relative_to(root).as_posix(),
                    src.relative_to(root).as_posix(),
                    src_final.relative_to(root).as_posix(),
                    dst.relative_to(root).as_posix() if dst is not None else None,
                    dst_final.relative_to(root).as_posix() if dst_final is not None else None,
                    expected_source_sha256,
                    expected_target_sha256,
                ),
            )
            preview["transfer_log_id"] = int(log.lastrowid)
            conn.execute(
                """INSERT INTO audit_log(action, source_path, target_path, sha256, detail_json)
                   VALUES ('transfer_photo_slot', ?, ?, ?, json_object('source_id', ?,
                       'target_id', ?, 'source_slot', ?, 'target_slot', ?))""",
                (
                    source["relative_path"],
                    src_final.relative_to(root).as_posix(),
                    expected_source_sha256,
                    source_id,
                    target_id,
                    preview["source_slot"],
                    target_slot,
                ),
            )
    except Exception as exc:
        for before, after in reversed(steps):
            if after.exists() and not before.exists():
                with suppress(Exception):
                    _rename_no_overwrite(after, before)
        with suppress(Exception):
            refresh_item_index(conn, int(preview["item_id"]))
        if isinstance(exc, OrganizerError):
            raise
        raise OrganizerError(f"交換照片失敗，已嘗試還原原始檔名：{exc}") from exc
    return preview


def undo_slot_transfer(conn: sqlite3.Connection, root_id: int, log_id: int) -> dict[str, object]:
    row = conn.execute(
        "SELECT * FROM slot_transfer_log WHERE id=? AND root_id=?", (log_id, root_id)
    ).fetchone()
    if row is None:
        raise OrganizerError("找不到照片交換歷史紀錄")
    if row["reverted_at"]:
        raise OrganizerConflict("這次照片交換已復原")
    root = _root_path(conn, root_id)
    source_current = _safe_file_path_preserve_name(root, row["source_after"])
    source_before = _safe_file_path_preserve_name(root, row["source_before"])
    target_current = (
        _safe_file_path_preserve_name(root, row["target_after"]) if row["target_after"] else None
    )
    target_before = (
        _safe_file_path_preserve_name(root, row["target_before"]) if row["target_before"] else None
    )
    if source_current.parent != source_before.parent or (
        target_current and target_current.parent != source_before.parent
    ):
        raise OrganizerError("復原僅允許同一設備目錄")
    if (
        not source_current.is_file()
        or source_current.is_symlink()
        or (sha256_file(source_current) != row["source_sha256"])
    ):
        raise OrganizerConflict("已交換照片內容不同，停止復原避免覆蓋")
    if target_current is not None and (
        not target_current.is_file()
        or target_current.is_symlink()
        or sha256_file(target_current) != row["target_sha256"]
    ):
        raise OrganizerConflict("另一張已交換照片內容不同，停止復原避免覆蓋")
    current = {source_current}
    if target_current is not None:
        current.add(target_current)
    for original in (source_before, target_before):
        if original is not None and original.exists() and original not in current:
            raise OrganizerConflict("原始檔名已被其他照片使用，無法安全復原")

    item = conn.execute(
        "SELECT id FROM item WHERE root_id=? AND relative_path=?",
        (root_id, row["item_relative_path"]),
    ).fetchone()
    if item is None:
        raise OrganizerConflict("原始設備資料夾不存在，無法復原")
    stage = source_current.with_name(f".firelens-transfer-undo-{uuid.uuid4().hex}.tmp")
    steps: list[tuple[Path, Path]] = []
    try:
        _rename_no_overwrite(source_current, stage)
        steps.append((source_current, stage))
        if target_current is not None and target_before is not None:
            _rename_no_overwrite(target_current, target_before)
            steps.append((target_current, target_before))
        _rename_no_overwrite(stage, source_before)
        steps.append((stage, source_before))
        if sha256_file(source_before) != row["source_sha256"] or (
            target_before is not None and sha256_file(target_before) != row["target_sha256"]
        ):
            raise OrganizerConflict("復原後檔案 SHA-256 驗證失敗")
        refresh_item_index(conn, int(item["id"]))
        with conn:
            cursor = conn.execute(
                "UPDATE slot_transfer_log SET reverted_at=CURRENT_TIMESTAMP "
                "WHERE id=? AND reverted_at IS NULL",
                (log_id,),
            )
            if cursor.rowcount != 1:
                raise OrganizerConflict("交換紀錄已被另一操作更新")
            conn.execute(
                """INSERT INTO audit_log(action, source_path, target_path, sha256, detail_json)
                VALUES ('undo_slot_transfer', ?, ?, ?, json_object('transfer_log_id', ?))""",
                (row["source_after"], row["source_before"], row["source_sha256"], log_id),
            )
    except Exception as exc:
        for before, after in reversed(steps):
            if after.exists() and not before.exists():
                with suppress(Exception):
                    _rename_no_overwrite(after, before)
        with suppress(Exception):
            refresh_item_index(conn, int(item["id"]))
        if isinstance(exc, OrganizerError):
            raise
        raise OrganizerError(f"照片交換復原失敗：{exc}") from exc
    return {"reverted": True, "transfer_log_id": log_id, "item_id": int(item["id"])}

from __future__ import annotations

import errno
import hashlib
import io
import json
import os
import sqlite3
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from .folder_catalog import register_building, register_period
from .scanner import CATEGORY_DIRS, refresh_item_index, scan_root
from .settings import custom_slots_for

register_heif_opener()

UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


class StorageError(ValueError):
    pass


class StorageConflict(StorageError):
    pass


@dataclass(frozen=True)
class ItemContext:
    item_id: int
    root_id: int
    root_path: Path
    item_dir: Path
    category_code: str
    slots: tuple[str, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_resolve(root: Path, relative: str) -> Path:
    root_resolved = root.expanduser().resolve()
    candidate = (root_resolved / relative).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise StorageError("路徑超出設定的照片根目錄")
    return candidate


def _item_context(conn: sqlite3.Connection, item_id: int) -> ItemContext:
    row = conn.execute(
        """
        SELECT i.id, i.root_id, i.relative_path, r.path AS root_path,
               c.code AS category_code, c.slots_json
        FROM item AS i
        JOIN root AS r ON r.id = i.root_id
        JOIN category AS c ON c.id = i.category_id
        WHERE i.id = ?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise StorageError("找不到指定項目")
    root_path = Path(row["root_path"]).expanduser().resolve()
    item_dir = _safe_resolve(root_path, row["relative_path"])
    if not item_dir.is_dir():
        raise StorageError("照片資料夾不存在或無法讀取")
    return ItemContext(
        item_id=row["id"],
        root_id=row["root_id"],
        root_path=root_path,
        item_dir=item_dir,
        category_code=row["category_code"],
        slots=tuple(json.loads(row["slots_json"])),
    )


def _validate_upload(filename: str, data: bytes) -> str:
    if not filename:
        raise StorageError("上傳檔案缺少檔名")
    if not data:
        raise StorageError("上傳檔案是空檔")
    if len(data) > MAX_UPLOAD_BYTES:
        raise StorageError("單張照片不可超過 100 MB")
    extension = Path(filename).suffix.casefold()
    if extension not in UPLOAD_EXTENSIONS:
        raise StorageError("只接受 JPG、JPEG、PNG、HEIC 或 HEIF 圖片")
    return extension


def _open_transposed(data: bytes) -> Image.Image:
    try:
        source = Image.open(io.BytesIO(data))
        source.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise StorageError("無法讀取圖片內容，檔案可能已損壞") from exc
    image = ImageOps.exif_transpose(source)
    if image is not source:
        source.close()
    return image


def _has_orientation(data: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            return image.getexif().get(274, 1) not in (None, 1)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise StorageError("無法讀取圖片內容，檔案可能已損壞") from exc


def _save_encoded(data: bytes, destination: Path, output_extension: str) -> None:
    image = _open_transposed(data)
    try:
        if output_extension in {".jpg", ".jpeg"}:
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A")
                background.paste(image.convert("RGB"), mask=alpha)
                image.close()
                image = background
            elif image.mode != "RGB":
                converted = image.convert("RGB")
                image.close()
                image = converted
            image.save(destination, format="JPEG", quality=95, optimize=True)
        elif output_extension == ".png":
            image.save(destination, format="PNG", optimize=True)
        elif output_extension in {".heic", ".heif"}:
            image.save(destination, format="HEIF", quality=95)
        else:
            raise StorageError("不支援的目標圖片格式")
    finally:
        image.close()


def _save_stage(
    data: bytes,
    source_extension: str,
    destination: Path,
    output_extension: str,
) -> None:
    raw_copy = (
        source_extension in {".jpg", ".jpeg"}
        and output_extension in {".jpg", ".jpeg"}
        and not _has_orientation(data)
    ) or (source_extension == ".png" and output_extension == ".png" and not _has_orientation(data))
    if raw_copy:
        destination.write_bytes(data)
    else:
        _save_encoded(data, destination, output_extension)
    # Windows does not allow os.fsync() on a read-only file descriptor.
    # Re-open the staged file read/write so durability verification works on
    # both Windows and POSIX without changing the file contents.
    with destination.open("r+b") as handle:
        os.fsync(handle.fileno())


def _install_new(stage: Path, target: Path, expected_hash: str) -> None:
    if target.exists():
        raise StorageConflict("目標檔名已存在，不會覆蓋既有照片")
    try:
        if os.name == "nt":
            os.rename(stage, target)
        else:
            os.link(stage, target)
            stage.unlink()
    except FileExistsError as exc:
        raise StorageConflict("目標檔名已存在，不會覆蓋既有照片") from exc
    except OSError as exc:
        if os.name != "nt" and exc.errno in {errno.EPERM, errno.EOPNOTSUPP, errno.EXDEV}:
            raise StorageError("目前檔案系統不支援安全的原子新增，已取消匯入") from exc
        raise
    if sha256_file(target) != expected_hash:
        target.unlink(missing_ok=True)
        raise StorageError("照片寫入後 SHA-256 驗證失敗")


def _replace_atomic(stage: Path, target: Path, expected_hash: str) -> tuple[Path, str]:
    if not target.is_file() or target.is_symlink():
        raise StorageError("要替換的照片不存在或不可安全寫入")
    backup = target.with_name(f".firelens-{uuid.uuid4().hex}.bak")
    original_hash = sha256_file(target)
    os.replace(target, backup)
    try:
        os.replace(stage, target)
        if sha256_file(target) != expected_hash:
            raise StorageError("替換後照片 SHA-256 驗證失敗")
    except Exception as exc:
        target.unlink(missing_ok=True)
        os.replace(backup, target)
        if sha256_file(target) != original_hash:
            raise StorageError("照片替換失敗，且舊檔還原驗證失敗") from exc
        raise
    return backup, original_hash


def _next_slot_name(item_dir: Path, slot: str, multiple: bool) -> str:
    names = {path.name.casefold() for path in item_dir.iterdir() if path.is_file()}
    first = f"{slot}.jpg"
    if first.casefold() not in names:
        return first
    if not multiple:
        raise StorageConflict("此槽位已有照片，請使用換圖功能")
    index = 1
    while f"{slot}-{index}.jpg".casefold() in names:
        index += 1
    return f"{slot}-{index}.jpg"


def _audit(
    conn: sqlite3.Connection,
    action: str,
    source_name: str | None,
    target_relative: str,
    digest: str | None,
    detail: dict[str, object] | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO audit_log(action, source_path, target_path, sha256, detail_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                action,
                source_name,
                target_relative,
                digest,
                json.dumps(detail or {}, ensure_ascii=False),
            ),
        )


def import_photo(
    conn: sqlite3.Connection,
    item_id: int,
    slot: str,
    source_name: str,
    data: bytes,
    replace_photo_id: int | None = None,
) -> dict[str, object]:
    context = _item_context(conn, item_id)
    if slot not in (*context.slots, *custom_slots_for(conn, context.category_code)):
        raise StorageError("指定槽位不屬於此類別")
    source_extension = _validate_upload(source_name, data)

    replace_row = None
    if replace_photo_id is not None:
        replace_row = conn.execute(
            "SELECT id, filename, relative_path, slot FROM photo WHERE id = ? AND item_id = ?",
            (replace_photo_id, item_id),
        ).fetchone()
        if replace_row is None:
            raise StorageError("找不到要替換的照片")
        if replace_row["slot"] != slot:
            raise StorageError("要替換的照片不在指定槽位")
        target = _safe_resolve(context.root_path, replace_row["relative_path"])
        if target.parent != context.item_dir:
            raise StorageError("要替換的照片路徑不符合目前項目")
        target_name = target.name
        output_extension = target.suffix.casefold()
    else:
        target_name = _next_slot_name(context.item_dir, slot, multiple=True)
        target = context.item_dir / target_name
        output_extension = ".jpg"

    stage = context.item_dir / f".firelens-{uuid.uuid4().hex}.tmp"
    backup: Path | None = None
    original_hash: str | None = None
    new_installed = False
    try:
        _save_stage(data, source_extension, stage, output_extension)
        staged_hash = sha256_file(stage)
        if replace_row is None:
            _install_new(stage, target, staged_hash)
            new_installed = True
            action = "import_photo"
        else:
            backup, original_hash = _replace_atomic(stage, target, staged_hash)
            action = "replace_photo"

        final_hash = sha256_file(target)
        target_relative = target.relative_to(context.root_path).as_posix()
        refresh_item_index(conn, item_id, {target_name: final_hash})
        _audit(
            conn,
            action,
            source_name,
            target_relative,
            final_hash,
            {"item_id": item_id, "slot": slot, "filename": target_name},
        )
    except Exception as exc:
        if backup is not None and backup.exists():
            target.unlink(missing_ok=True)
            os.replace(backup, target)
            if original_hash is not None and sha256_file(target) != original_hash:
                raise StorageError("寫入後續處理失敗，且舊照片還原驗證失敗") from exc
        elif new_installed:
            target.unlink(missing_ok=True)
        with suppress(Exception):
            refresh_item_index(conn, item_id)
        raise
    finally:
        stage.unlink(missing_ok=True)

    if backup is not None:
        backup.unlink(missing_ok=True)
    return {
        "item_id": item_id,
        "slot": slot,
        "filename": target_name,
        "sha256": final_hash,
        "action": action,
    }


def delete_photo(conn: sqlite3.Connection, photo_id: int) -> int:
    row = conn.execute(
        """
        SELECT p.id, p.item_id, p.relative_path, p.filename, p.sha256, r.path AS root_path
        FROM photo p
        JOIN item i ON i.id = p.item_id
        JOIN root r ON r.id = i.root_id
        WHERE p.id = ?
        """,
        (photo_id,),
    ).fetchone()
    if row is None:
        raise StorageError("找不到指定照片")

    root_path = Path(row["root_path"]).expanduser().resolve()
    target = _safe_resolve(root_path, row["relative_path"])
    item_id = row["item_id"]

    if target.exists():
        if target.is_symlink():
            raise StorageError("不支援刪除符號連結")
        try:
            target.unlink()
        except OSError as exc:
            raise StorageError(f"刪除檔案失敗: {exc}") from exc

    _audit(
        conn,
        "delete_photo",
        row["filename"],
        row["relative_path"],
        row["sha256"],
        {"item_id": item_id, "photo_id": photo_id},
    )
    refresh_item_index(conn, item_id)
    return item_id


def reorder_photos(
    conn: sqlite3.Connection, item_id: int, slot: str, photo_ids: list[int]
) -> dict[str, object]:
    context = _item_context(conn, item_id)

    rows = conn.execute(
        """
        SELECT id, filename, relative_path
        FROM photo
        WHERE item_id = ? AND slot = ?
        """,
        (item_id, slot),
    ).fetchall()

    existing = {row["id"]: dict(row) for row in rows}
    if len(existing) != len(photo_ids) or set(existing.keys()) != set(photo_ids):
        raise StorageError("提供的照片清單與目前槽位內的照片不符")

    # Generate target names
    targets = []
    for i, pid in enumerate(photo_ids):
        row = existing[pid]
        ext = Path(row["filename"]).suffix
        target_name = f"{slot}{ext}" if i == 0 else f"{slot}-{i}{ext}"
        targets.append((pid, target_name))

    # Check if any renames are actually needed
    needs_rename = False
    for pid, target_name in targets:
        if existing[pid]["filename"].casefold() != target_name.casefold():
            needs_rename = True
            break

    if not needs_rename:
        return {"item_id": item_id, "status": "unchanged"}

    # Stage 1: Rename all to temp names to avoid conflicts
    temp_moves = []
    for pid in photo_ids:
        row = existing[pid]
        source_path = _safe_resolve(context.root_path, row["relative_path"])
        if not source_path.is_file():
            raise StorageError(f"找不到檔案: {row['filename']}")
        temp_name = f".firelens-reorder-{uuid.uuid4().hex}{Path(row['filename']).suffix}"
        temp_path = context.item_dir / temp_name
        os.rename(source_path, temp_path)
        temp_moves.append((pid, temp_path))

    # Stage 2: Rename temp files to target names
    try:
        for (pid, target_name), (_, temp_path) in zip(targets, temp_moves, strict=True):
            target_path = context.item_dir / target_name
            os.rename(temp_path, target_path)

            # Audit log
            _audit(
                conn,
                "reorder_photo",
                existing[pid]["filename"],
                target_path.relative_to(context.root_path).as_posix(),
                None,
                {
                    "item_id": item_id,
                    "slot": slot,
                    "old_name": existing[pid]["filename"],
                    "new_name": target_name,
                },
            )
    except Exception as exc:
        # If something fails here, we should try to restore from temp_moves, but it's tricky.
        # Calling refresh_item_index will at least resync DB with whatever state the disk is in.
        refresh_item_index(conn, item_id)
        raise StorageError(f"重新排序時發生錯誤: {exc}") from exc

    refresh_item_index(conn, item_id)
    return {"item_id": item_id, "status": "ok"}


def photo_file(conn: sqlite3.Connection, photo_id: int) -> Path:
    row = conn.execute(
        """
        SELECT p.relative_path, r.path AS root_path
        FROM photo AS p
        JOIN item AS i ON i.id = p.item_id
        JOIN root AS r ON r.id = i.root_id
        WHERE p.id = ?
        """,
        (photo_id,),
    ).fetchone()
    if row is None:
        raise StorageError("找不到指定照片")
    root = Path(row["root_path"]).expanduser().resolve()
    target = _safe_resolve(root, row["relative_path"])
    if not target.is_file() or target.is_symlink():
        raise StorageError("照片檔案不存在或不可安全讀取")
    return target


def _plain_component(value: str, label: str) -> str:
    value = value.strip()
    if not value or value in {".", ".."}:
        raise StorageError(f"{label}不可為空")
    if "/" in value or "\\" in value or "\x00" in value:
        raise StorageError(f"{label}不可包含路徑分隔符號")
    if any(ord(character) < 32 for character in value):
        raise StorageError(f"{label}包含不可使用的控制字元")
    return value


def _structure_context(
    conn: sqlite3.Connection,
    root_id: int,
    category_code: str,
) -> tuple[Path, str]:
    root_row = conn.execute("SELECT path FROM root WHERE id = ?", (root_id,)).fetchone()
    category_row = conn.execute(
        "SELECT name FROM category WHERE code = ?", (category_code,)
    ).fetchone()
    if root_row is None:
        raise StorageError("找不到指定根目錄")
    if category_row is None or category_row["name"] not in CATEGORY_DIRS:
        raise StorageError("找不到指定類別")
    root_path = Path(root_row["path"]).expanduser().resolve()
    if not root_path.is_dir():
        raise StorageError("照片根目錄不存在或目前無法讀取")
    return root_path, str(category_row["name"])


def create_period_folder(
    conn: sqlite3.Connection,
    root_id: int,
    category_code: str,
    year: str,
    period: str,
) -> dict[str, object]:
    root_path, category_name = _structure_context(conn, root_id, category_code)
    clean_year = _plain_component(year, "年份")
    clean_period = _plain_component(period, "月份/批次")
    target = (root_path / category_name / clean_year / clean_period).resolve()
    if not target.is_relative_to(root_path):
        raise StorageError("新增資料夾路徑超出根目錄")
    if target.exists() and not target.is_dir():
        raise StorageConflict("同名路徑已存在，但不是資料夾")
    created = not target.exists()
    target.mkdir(parents=True, exist_ok=True)
    relative = target.relative_to(root_path).as_posix()
    with conn:
        register_period(conn, root_id, category_code, clean_year, clean_period)
        _audit(
            conn,
            "create_period_folder",
            None,
            relative,
            None,
            {"category": category_code, "year": clean_year, "period": clean_period},
        )
    return {
        "root_id": root_id,
        "category_code": category_code,
        "year": clean_year,
        "period": clean_period,
        "relative_path": relative,
        "created": created,
    }


def create_building_folder(
    conn: sqlite3.Connection,
    root_id: int,
    category_code: str,
    year: str,
    period: str,
    building: str,
) -> dict[str, object]:
    root_path, category_name = _structure_context(conn, root_id, category_code)
    clean_year = _plain_component(year, "年份")
    clean_period = _plain_component(period, "月份/批次")
    building_parts = [_plain_component(part, "棟別") for part in building.split(" / ")]
    clean_building = " / ".join(building_parts)
    target = root_path / category_name / clean_year / clean_period
    for part in building_parts:
        target /= part
    target = target.resolve()
    if not target.is_relative_to(root_path):
        raise StorageError("新增資料夾路徑超出根目錄")
    if target.exists() and not target.is_dir():
        raise StorageConflict("同名路徑已存在，但不是資料夾")
    created = not target.exists()
    target.mkdir(parents=True, exist_ok=True)
    relative = target.relative_to(root_path).as_posix()
    with conn:
        register_building(
            conn,
            root_id,
            category_code,
            clean_year,
            clean_period,
            clean_building,
        )
        _audit(
            conn,
            "create_building_folder",
            None,
            relative,
            None,
            {
                "category": category_code,
                "year": clean_year,
                "period": clean_period,
                "building": clean_building,
            },
        )
    scan_root(conn, root_id)
    return {
        "root_id": root_id,
        "category_code": category_code,
        "year": clean_year,
        "period": clean_period,
        "building": clean_building,
        "relative_path": relative,
        "created": created,
    }


def create_item_folder(
    conn: sqlite3.Connection,
    root_id: int,
    category_code: str,
    year: str,
    period: str,
    building: str,
    code: str,
) -> int:
    root_row = conn.execute("SELECT path FROM root WHERE id = ?", (root_id,)).fetchone()
    category_row = conn.execute(
        "SELECT name FROM category WHERE code = ?", (category_code,)
    ).fetchone()
    if root_row is None:
        raise StorageError("找不到指定根目錄")
    if category_row is None or category_row["name"] not in CATEGORY_DIRS:
        raise StorageError("找不到指定類別")

    clean_year = _plain_component(year, "年份")
    clean_period = _plain_component(period, "月份/批次")
    clean_code = _plain_component(code, "編號")
    building_parts = [_plain_component(part, "棟別") for part in building.split(" / ")]
    root_path = Path(root_row["path"]).expanduser().resolve()
    target = root_path / category_row["name"] / clean_year / clean_period
    for part in building_parts:
        target /= part
    target /= clean_code
    target = target.resolve()
    if not target.is_relative_to(root_path):
        raise StorageError("新增資料夾路徑超出根目錄")
    if target.exists():
        raise StorageConflict("此編號資料夾已存在")

    target.mkdir(parents=True, exist_ok=False)
    target_relative = target.relative_to(root_path).as_posix()
    _audit(
        conn,
        "create_item_folder",
        None,
        target_relative,
        None,
        {"category": category_code, "code": clean_code},
    )
    scan_root(conn, root_id)
    row = conn.execute(
        "SELECT id FROM item WHERE root_id = ? AND relative_path = ?",
        (root_id, target_relative),
    ).fetchone()
    if row is None:
        raise StorageError("資料夾已建立，但重新掃描後找不到新項目")
    return int(row["id"])


def delete_item_folder(conn: sqlite3.Connection, item_id: int) -> dict[str, object]:
    import shutil

    context = _item_context(conn, item_id)

    if context.item_dir.exists():
        if not context.item_dir.is_dir() or context.item_dir.is_symlink():
            raise StorageError("無法安全刪除：目標不是一般資料夾")
        try:
            shutil.rmtree(context.item_dir)
        except OSError as exc:
            raise StorageError(f"刪除資料夾失敗: {exc}") from exc

    relative_path = context.item_dir.relative_to(context.root_path).as_posix()
    _audit(
        conn,
        "delete_item_folder",
        None,
        relative_path,
        None,
        {"item_id": item_id, "category_code": context.category_code},
    )

    scan_root(conn, context.root_id)
    return {"status": "ok", "deleted": True, "root_id": context.root_id}

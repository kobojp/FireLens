from __future__ import annotations

import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from .folder_catalog import managed_buildings
from .settings import custom_slots_for

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
CATEGORY_DIRS = {
    "滅火器": "extinguisher",
    "放置盒": "box",
    "燈具": "lamp",
}
LEGACY_BOX_RE = re.compile(r"^(新增-?\d+|編號|完成)$")
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
CLOUD_PLACEHOLDER_FLAGS = (
    FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)


@dataclass(frozen=True)
class ScanSummary:
    root_id: int
    items: int
    photos: int
    categories: dict[str, int]


def _is_cloud_placeholder_stat(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    return bool(attributes & CLOUD_PLACEHOLDER_FLAGS)


def _image_metadata(path: Path) -> tuple[int, int, bool] | None:
    if path.suffix.casefold() not in IMAGE_EXTENSIONS:
        return None
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return info.st_size, info.st_mtime_ns, _is_cloud_placeholder_stat(info)


def _is_image(path: Path) -> bool:
    return _image_metadata(path) is not None


_NUMBERED_RE = re.compile(r"^(?P<base>.+)-(?P<index>\d+)$")
EXTINGUISHER_ALIASES = {"編號": "編號", "藥劑": "藥劑", "有效日期": "藥劑", "完成": "完成"}


def _slot_for(category_code: str, filename: str, custom_slots: tuple[str, ...] = ()) -> str | None:
    stem = Path(filename).stem
    numbered = _NUMBERED_RE.match(stem)
    bases = [stem] + ([numbered.group("base")] if numbered else [])
    if category_code == "extinguisher":
        for base in bases:
            if base in EXTINGUISHER_ALIASES:
                return EXTINGUISHER_ALIASES[base]
    if category_code in {"box", "lamp"}:
        for slot in ("前", "中", "後"):
            if stem == slot or stem.startswith(f"{slot}-"):
                return slot
    folded = {slot.casefold(): slot for slot in custom_slots}
    for base in bases:
        if base.casefold() in folded:
            return folded[base.casefold()]
    return None


def _status_for(category_code: str, filenames: list[str]) -> str:
    if not filenames:
        return "empty"
    stems = [Path(name).stem for name in filenames]
    if category_code == "extinguisher":
        slots = {_slot_for(category_code, name) for name in filenames}
        required = {"編號", "藥劑", "完成"}
        return "complete" if required <= slots else "partial"
    if category_code == "box" and any(LEGACY_BOX_RE.match(stem) for stem in stems):
        return "legacy"
    slots = {_slot_for(category_code, name) for name in filenames}
    if {"前", "中", "後"} <= slots:
        return "complete"
    if slots - {None}:
        return "partial"
    return "unknown"


def _candidate_item_dirs(period_dir: Path, structural_dirs: set[Path] | None = None) -> list[Path]:
    candidates: list[Path] = []
    structural = structural_dirs or set()
    for current, dirnames, filenames in os.walk(period_dir, followlinks=False):
        current_path = Path(current)
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        direct_images = [
            current_path / name for name in filenames if _is_image(current_path / name)
        ]
        is_leaf = current_path != period_dir and not dirnames
        if current_path.resolve() in structural:
            continue
        if direct_images or is_leaf:
            candidates.append(current_path)
    return candidates


def scan_root(conn: sqlite3.Connection, root_id: int) -> ScanSummary:
    root_row = conn.execute("SELECT id, path FROM root WHERE id = ?", (root_id,)).fetchone()
    if root_row is None:
        raise ValueError("找不到指定的根目錄")

    root_path = Path(root_row["path"]).expanduser()
    if not root_path.is_dir():
        raise FileNotFoundError(f"根目錄不存在或無法讀取：{root_path}")

    category_rows = {
        row["code"]: row["id"] for row in conn.execute("SELECT id, code FROM category")
    }
    item_rows: list[tuple[object, ...]] = []
    photo_rows_by_relative: dict[str, list[tuple[str, str, str, str | None, int, int, int]]] = {}
    counts: dict[str, int] = {code: 0 for code in CATEGORY_DIRS.values()}
    custom_by_category = {code: custom_slots_for(conn, code) for code in CATEGORY_DIRS.values()}

    for category_name, category_code in CATEGORY_DIRS.items():
        category_dir = root_path / category_name
        if not category_dir.is_dir():
            continue
        category_id = category_rows[category_code]

        for year_dir in sorted(
            (path for path in category_dir.iterdir() if path.is_dir()), key=lambda path: path.name
        ):
            for period_dir in sorted(
                (path for path in year_dir.iterdir() if path.is_dir()), key=lambda path: path.name
            ):
                structural_dirs = {
                    (period_dir / Path(*building.split(" / "))).resolve()
                    for building in managed_buildings(
                        conn,
                        root_id,
                        category_code,
                        year_dir.name,
                        period_dir.name,
                    )
                }
                for item_dir in _candidate_item_dirs(period_dir, structural_dirs):
                    relative_item = item_dir.relative_to(root_path).as_posix()
                    location_parts = item_dir.relative_to(period_dir).parts[:-1]
                    building = " / ".join(location_parts) if location_parts else "(未分棟)"
                    image_paths = sorted(
                        (path for path in item_dir.iterdir() if _is_image(path)),
                        key=lambda path: path.name.casefold(),
                    )
                    filenames = [path.name for path in image_paths]
                    item_rows.append(
                        (
                            root_id,
                            category_id,
                            year_dir.name,
                            period_dir.name,
                            building,
                            item_dir.name,
                            relative_item,
                            _status_for(category_code, filenames),
                            len(image_paths),
                        )
                    )
                    photo_rows: list[tuple[str, str, str, str | None, int, int, int]] = []
                    for path in image_paths:
                        metadata = _image_metadata(path)
                        if metadata is None:
                            continue
                        size_bytes, mtime_ns, cloud_placeholder = metadata
                        photo_rows.append(
                            (
                                path.name,
                                path.relative_to(root_path).as_posix(),
                                path.suffix.casefold(),
                                _slot_for(
                                    category_code, path.name, custom_by_category[category_code]
                                ),
                                size_bytes,
                                mtime_ns,
                                int(cloud_placeholder),
                            )
                        )
                    photo_rows_by_relative[relative_item] = photo_rows
                    counts[category_code] += 1

    with conn:
        conn.execute("DELETE FROM item WHERE root_id = ?", (root_id,))
        conn.executemany(
            """
            INSERT INTO item(
                root_id, category_id, year, period, building, code, relative_path,
                status, photo_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            item_rows,
        )
        item_ids = {
            row["relative_path"]: row["id"]
            for row in conn.execute(
                "SELECT id, relative_path FROM item WHERE root_id = ?", (root_id,)
            )
        }
        all_photos: list[tuple[object, ...]] = []
        for relative_item, photos in photo_rows_by_relative.items():
            item_id = item_ids[relative_item]
            all_photos.extend((item_id, *photo) for photo in photos)
        conn.executemany(
            """
            INSERT INTO photo(
                item_id, filename, relative_path, extension, slot, size_bytes, mtime_ns,
                cloud_placeholder
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            all_photos,
        )
        conn.execute(
            "UPDATE root SET last_scan_at = CURRENT_TIMESTAMP WHERE id = ?",
            (root_id,),
        )

    return ScanSummary(
        root_id=root_id,
        items=len(item_rows),
        photos=sum(len(photos) for photos in photo_rows_by_relative.values()),
        categories=counts,
    )


def refresh_item_index(
    conn: sqlite3.Connection,
    item_id: int,
    known_sha256: dict[str, str] | None = None,
) -> None:
    row = conn.execute(
        """
        SELECT i.id, i.relative_path, r.path AS root_path, c.code AS category_code
        FROM item AS i
        JOIN root AS r ON r.id = i.root_id
        JOIN category AS c ON c.id = i.category_id
        WHERE i.id = ?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise ValueError("找不到指定項目")

    root_path = Path(row["root_path"]).expanduser().resolve()
    item_dir = (root_path / row["relative_path"]).resolve()
    if not item_dir.is_relative_to(root_path) or not item_dir.is_dir():
        raise FileNotFoundError("照片資料夾不存在或已離開根目錄")

    image_paths = sorted(
        (path for path in item_dir.iterdir() if _is_image(path)),
        key=lambda path: path.name.casefold(),
    )
    filenames = [path.name for path in image_paths]
    custom_slots = custom_slots_for(conn, row["category_code"])
    known = known_sha256 or {}
    photo_rows = []
    for path in image_paths:
        metadata = _image_metadata(path)
        if metadata is None:
            continue
        size_bytes, mtime_ns, cloud_placeholder = metadata
        photo_rows.append(
            (
                item_id,
                path.name,
                path.relative_to(root_path).as_posix(),
                path.suffix.casefold(),
                _slot_for(row["category_code"], path.name, custom_slots),
                size_bytes,
                mtime_ns,
                known.get(path.name),
                int(cloud_placeholder),
            )
        )

    with conn:
        conn.execute("DELETE FROM photo WHERE item_id = ?", (item_id,))
        conn.executemany(
            """
            INSERT INTO photo(
                item_id, filename, relative_path, extension, slot, size_bytes, mtime_ns, sha256,
                cloud_placeholder
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            photo_rows,
        )
        conn.execute(
            "UPDATE item SET status = ?, photo_count = ? WHERE id = ?",
            (_status_for(row["category_code"], filenames), len(image_paths), item_id),
        )

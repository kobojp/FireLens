from __future__ import annotations

import hashlib
import os
import sqlite3
import unicodedata
import uuid
from collections import defaultdict
from contextlib import suppress
from pathlib import Path

from .scanner import refresh_item_index
from .storage import sha256_file

VARIANT_CHARACTERS = {"徳": "德"}


class OrganizerError(ValueError):
    pass


class OrganizerConflict(OrganizerError):
    pass


def _safe_path(root: Path, relative: str) -> Path:
    root = root.expanduser().resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise OrganizerError("路徑超出設定的照片根目錄")
    return candidate


def _safe_file_path_preserve_name(root: Path, relative: str) -> Path:
    """Validate the parent path while preserving the requested final filename spelling.

    Windows ``Path.resolve()`` normalizes a case-only destination to the casing
    of the already-existing source file.  Renames therefore need the parent to
    be resolved for traversal/symlink safety, but the final component must stay
    lexical so ``編號.JPG -> 編號.jpg`` can actually change the on-disk casing.
    """
    root_resolved = root.expanduser().resolve()
    relative_path = Path(relative)
    parent = (root_resolved / relative_path.parent).resolve()
    if not parent.is_relative_to(root_resolved) or relative_path.name in {"", ".", ".."}:
        raise OrganizerError("路徑超出設定的照片根目錄")
    return parent / relative_path.name


def _root_path(conn: sqlite3.Connection, root_id: int) -> Path:
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        raise OrganizerError("找不到指定照片根目錄")
    root = Path(row["path"]).expanduser().resolve()
    if not root.is_dir():
        raise OrganizerError("照片根目錄不存在或無法讀取")
    return root


def _canonical_filename(filename: str) -> tuple[str | None, str | None]:
    path = Path(filename)
    stem = path.stem.strip()
    cleaned = stem.replace("‵", "").replace("`", "").strip(" ._")
    while cleaned.endswith("."):
        cleaned = cleaned[:-1].rstrip()
    if cleaned.endswith(")") and " (" in cleaned:
        prefix, suffix = cleaned.rsplit(" (", 1)
        if suffix[:-1].isdigit():
            cleaned = prefix.rstrip()

    aliases = {
        "編輯": "編號",
        "編號": "編號",
        "藥劑": "藥劑",
        "完成": "完成",
        "成": "完成",
    }
    canonical = aliases.get(cleaned)
    if canonical is None:
        return None, None

    suffix = path.suffix
    target_suffix = ".jpg" if suffix.casefold() in {".jpg", ".jpeg"} else suffix.casefold()
    target = f"{canonical}{target_suffix}"
    if target == filename:
        return None, None

    reason_parts: list[str] = []
    if canonical != stem:
        reason_parts.append("檔名不合規")
    if suffix != target_suffix:
        reason_parts.append("副檔名正規化")
    return target, "、".join(reason_parts) or "檔名正規化"


def _candidate_id(root_id: int, source: str, target: str, digest: str) -> str:
    payload = f"{root_id}\0{source}\0{target}\0{digest}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _same_code_prefix(a: str, b: str) -> bool:
    parts_a = a.split("-")
    parts_b = b.split("-")
    if len(parts_a) < 2 or len(parts_a) != len(parts_b):
        return False
    if parts_a[:-1] != parts_b[:-1]:
        return False
    tail_a, tail_b = parts_a[-1], parts_b[-1]
    if abs(len(tail_a) - len(tail_b)) != 1:
        return False
    shorter, longer = (tail_a, tail_b) if len(tail_a) < len(tail_b) else (tail_b, tail_a)
    return any(longer[:index] + longer[index + 1 :] == shorter for index in range(len(longer)))


def _variant_issues(
    value: str, *, issue_type: str, context: dict[str, object]
) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    suggested = value
    reasons: list[str] = []
    for source, target in VARIANT_CHARACTERS.items():
        if source in suggested:
            suggested = suggested.replace(source, target)
            reasons.append(f"{source}→{target}")
    nfkc = unicodedata.normalize("NFKC", suggested)
    if nfkc != suggested:
        suggested = nfkc
        reasons.append("Unicode NFKC 正規化")
    if suggested != value:
        issues.append(
            {
                "type": issue_type,
                "value": value,
                "suggestion": suggested,
                "reason": "、".join(reasons),
                **context,
            }
        )
    return issues


def analyze_root(conn: sqlite3.Connection, root_id: int) -> dict[str, object]:
    root = _root_path(conn, root_id)
    photo_rows = list(
        conn.execute(
            """
            SELECT p.id, p.item_id, p.filename, p.relative_path, p.sha256, p.slot,
                   p.cloud_placeholder, i.code, i.building, i.period,
                   c.code AS category_code, c.name AS category_name
            FROM photo AS p
            JOIN item AS i ON i.id=p.item_id
            JOIN category AS c ON c.id=i.category_id
            WHERE i.root_id=?
            ORDER BY p.relative_path COLLATE NOCASE
            """,
            (root_id,),
        )
    )

    hashes: dict[int, str] = {}
    hash_errors: list[dict[str, object]] = []
    duplicate_map: dict[str, list[dict[str, object]]] = defaultdict(list)
    rename_candidates: list[dict[str, object]] = []
    unresolved_dirty: list[dict[str, object]] = []

    for row in photo_rows:
        path = _safe_path(root, row["relative_path"])
        if row["cloud_placeholder"]:
            continue
        try:
            if not path.is_file() or path.is_symlink():
                raise OSError("檔案不存在或不是一般檔案")
            digest = sha256_file(path)
        except OSError as exc:
            hash_errors.append({"relative_path": row["relative_path"], "error": str(exc)})
            continue
        hashes[int(row["id"])] = digest
        duplicate_map[digest].append(
            {
                "photo_id": row["id"],
                "item_id": row["item_id"],
                "category": row["category_code"],
                "category_name": row["category_name"],
                "code": row["code"],
                "building": row["building"],
                "period": row["period"],
                "filename": row["filename"],
                "relative_path": row["relative_path"],
            }
        )

        target_name, reason = _canonical_filename(row["filename"])
        if target_name is None:
            if row["category_code"] == "extinguisher" and row["slot"] is None:
                unresolved_dirty.append(
                    {
                        "candidate_id": None,
                        "photo_id": row["id"],
                        "item_id": row["item_id"],
                        "category": row["category_code"],
                        "category_name": row["category_name"],
                        "code": row["code"],
                        "building": row["building"],
                        "period": row["period"],
                        "source_relative": row["relative_path"],
                        "target_relative": None,
                        "source_name": row["filename"],
                        "target_name": None,
                        "sha256": digest,
                        "reason": "未對應滅火器標準槽位",
                        "safe": False,
                        "blocked_reason": "無法安全推測用途，需人工確認",
                    }
                )
            continue
        source_relative = Path(row["relative_path"])
        target_relative = source_relative.with_name(target_name).as_posix()
        target_path = _safe_file_path_preserve_name(root, target_relative)
        blocked_reason = None
        if target_path.exists() and target_path != path:
            blocked_reason = "目標檔名已存在"
        candidate = {
            "candidate_id": _candidate_id(root_id, row["relative_path"], target_relative, digest),
            "photo_id": row["id"],
            "item_id": row["item_id"],
            "category": row["category_code"],
            "category_name": row["category_name"],
            "code": row["code"],
            "building": row["building"],
            "period": row["period"],
            "source_relative": row["relative_path"],
            "target_relative": target_relative,
            "source_name": row["filename"],
            "target_name": target_name,
            "sha256": digest,
            "reason": reason,
            "safe": blocked_reason is None,
            "blocked_reason": blocked_reason,
        }
        rename_candidates.append(candidate)

    targets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for candidate in rename_candidates:
        targets[str(candidate["target_relative"])].append(candidate)
    for rows in targets.values():
        if len(rows) > 1:
            for candidate in rows:
                candidate["safe"] = False
                candidate["blocked_reason"] = "多筆候選指向同一目標檔名"

    if hashes:
        with conn:
            conn.executemany(
                "UPDATE photo SET sha256=? WHERE id=?",
                [(digest, photo_id) for photo_id, digest in hashes.items()],
            )

    dirty_files = sorted(
        [*rename_candidates, *unresolved_dirty],
        key=lambda row: str(row["source_relative"]).casefold(),
    )

    duplicate_photos = [
        {"sha256": digest, "count": len(rows), "photos": rows}
        for digest, rows in sorted(duplicate_map.items())
        if len(rows) > 1
    ]

    item_rows = list(
        conn.execute(
            """
            SELECT i.id, i.code, i.building, i.period, i.relative_path,
                   c.code AS category_code, c.name AS category_name
            FROM item AS i JOIN category AS c ON c.id=i.category_id
            WHERE i.root_id=? ORDER BY c.code, i.code, i.relative_path
            """,
            (root_id,),
        )
    )
    item_groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in item_rows:
        item_groups[(row["category_code"], row["code"])].append(row)
    duplicate_codes = [
        {
            "category": category,
            "category_name": rows[0]["category_name"],
            "code": code,
            "count": len(rows),
            "items": [
                {
                    "item_id": row["id"],
                    "building": row["building"],
                    "period": row["period"],
                    "relative_path": row["relative_path"],
                }
                for row in rows
            ],
        }
        for (category, code), rows in sorted(item_groups.items())
        if len(rows) > 1
    ]

    near_codes: list[dict[str, object]] = []
    by_category: dict[str, list[str]] = defaultdict(list)
    for row in item_rows:
        by_category[row["category_code"]].append(row["code"])
    for category, codes in by_category.items():
        unique_codes = sorted(set(codes))
        for index, first in enumerate(unique_codes):
            for second in unique_codes[index + 1 :]:
                if _same_code_prefix(first, second):
                    near_codes.append({"category": category, "first": first, "second": second})

    variant_issues: list[dict[str, object]] = []
    for row in item_rows:
        context = {
            "item_id": row["id"],
            "category": row["category_code"],
            "code": row["code"],
            "relative_path": row["relative_path"],
        }
        variant_issues.extend(
            _variant_issues(row["building"], issue_type="building", context=context)
        )
        variant_issues.extend(_variant_issues(row["code"], issue_type="code", context=context))

    return {
        "root_id": root_id,
        "summary": {
            "photos": len(photo_rows),
            "dirty_names": len(dirty_files),
            "safe_renames": sum(bool(row["safe"]) for row in rename_candidates),
            "duplicate_photo_groups": len(duplicate_photos),
            "duplicate_codes": len(duplicate_codes),
            "near_code_pairs": len(near_codes),
            "variant_issues": len(variant_issues),
            "hash_errors": len(hash_errors),
        },
        "dirty_files": dirty_files,
        "rename_candidates": rename_candidates,
        "duplicate_photos": duplicate_photos,
        "duplicate_codes": duplicate_codes,
        "near_codes": near_codes,
        "variant_issues": variant_issues,
        "hash_errors": hash_errors,
    }


def preview_renames(
    conn: sqlite3.Connection, root_id: int, candidate_ids: list[str]
) -> dict[str, object]:
    analysis = analyze_root(conn, root_id)
    candidates = {row["candidate_id"]: row for row in analysis["rename_candidates"]}
    selected: list[dict[str, object]] = []
    missing: list[str] = []
    for candidate_id in candidate_ids:
        row = candidates.get(candidate_id)
        if row is None:
            missing.append(candidate_id)
        else:
            selected.append(row)
    return {
        "root_id": root_id,
        "selected": selected,
        "missing_candidate_ids": missing,
        "safe_count": sum(bool(row["safe"]) for row in selected),
        "blocked_count": sum(not bool(row["safe"]) for row in selected),
    }


def _same_existing_file(first: Path, second: Path) -> bool:
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _rename_no_overwrite(source: Path, target: Path) -> None:
    same_file = _same_existing_file(source, target)
    if target.exists() and not same_file:
        raise OrganizerConflict("目標檔名已存在，不會覆蓋")
    if os.name == "nt":
        # On a case-insensitive Windows filesystem, a case-only rename such as
        # 編號.JPG -> 編號.jpg resolves both paths to the same existing file.
        # Move through a unique temporary name so the requested casing is
        # actually persisted while retaining the no-overwrite guarantee.
        if same_file and source.name != target.name:
            temporary = source.with_name(f".firelens-rename-{uuid.uuid4().hex}.tmp")
            while temporary.exists():
                temporary = source.with_name(f".firelens-rename-{uuid.uuid4().hex}.tmp")
            os.rename(source, temporary)
            try:
                if target.exists():
                    raise OrganizerConflict("目標檔名已存在，不會覆蓋")
                os.rename(temporary, target)
            except Exception:
                if temporary.exists() and not source.exists():
                    os.rename(temporary, source)
                raise
            return
        try:
            os.rename(source, target)
        except FileExistsError as exc:
            raise OrganizerConflict("目標檔名已存在，不會覆蓋") from exc
        return
    try:
        os.link(source, target)
        source.unlink()
    except FileExistsError as exc:
        raise OrganizerConflict("目標檔名已存在，不會覆蓋") from exc
    except OSError as exc:
        if target.exists() and source.exists():
            target.unlink(missing_ok=True)
        raise OrganizerError(f"檔案系統不支援安全改名：{exc}") from exc


def _item_id_for_parent(conn: sqlite3.Connection, root_id: int, relative_file: str) -> int:
    parent = Path(relative_file).parent.as_posix()
    row = conn.execute(
        "SELECT id FROM item WHERE root_id=? AND relative_path=?", (root_id, parent)
    ).fetchone()
    if row is None:
        raise OrganizerError("找不到改名檔案所屬的設備資料夾")
    return int(row["id"])


def _record_rename(
    conn: sqlite3.Connection,
    *,
    root_id: int,
    source_relative: str,
    target_relative: str,
    digest: str,
    reason: str,
) -> int:
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO rename_log(root_id, source_path, target_path, sha256)
            VALUES (?, ?, ?, ?)
            """,
            (root_id, source_relative, target_relative, digest),
        )
        conn.execute(
            """
            INSERT INTO audit_log(action, source_path, target_path, sha256, detail_json)
            VALUES ('rename_photo', ?, ?, ?, json_object('reason', ?))
            """,
            (source_relative, target_relative, digest, reason),
        )
    return int(cursor.lastrowid)


def execute_renames(
    conn: sqlite3.Connection, root_id: int, candidate_ids: list[str]
) -> dict[str, object]:
    root = _root_path(conn, root_id)
    preview = preview_renames(conn, root_id, candidate_ids)
    candidates = {row["candidate_id"]: row for row in preview["selected"]}
    executed: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []

    for candidate_id in candidate_ids:
        candidate = candidates.get(candidate_id)
        if candidate is None:
            failed.append({"candidate_id": candidate_id, "error": "候選已不存在，請重新分析"})
            continue
        if not candidate["safe"]:
            failed.append(
                {
                    "candidate_id": candidate_id,
                    "error": candidate["blocked_reason"] or "此候選不可安全改名",
                }
            )
            continue

        source_relative = str(candidate["source_relative"])
        target_relative = str(candidate["target_relative"])
        source = _safe_path(root, source_relative)
        target = _safe_file_path_preserve_name(root, target_relative)
        if source.parent != target.parent:
            failed.append({"candidate_id": candidate_id, "error": "只允許同資料夾改名"})
            continue
        try:
            if not source.is_file() or source.is_symlink():
                raise OrganizerError("來源檔案不存在或不是一般檔案")
            digest = sha256_file(source)
            if digest != candidate["sha256"]:
                raise OrganizerConflict("來源檔案內容已變更，請重新分析")
            item_id = _item_id_for_parent(conn, root_id, source_relative)
            _rename_no_overwrite(source, target)
            try:
                if sha256_file(target) != digest:
                    raise OrganizerError("改名後 SHA-256 驗證失敗")
                refresh_item_index(conn, item_id, {target.name: digest})
                log_id = _record_rename(
                    conn,
                    root_id=root_id,
                    source_relative=source_relative,
                    target_relative=target_relative,
                    digest=digest,
                    reason=str(candidate["reason"]),
                )
            except Exception as exc:
                if target.is_file():
                    _rename_no_overwrite(target, source)
                    if sha256_file(source) != digest:
                        raise OrganizerError("改名失敗，且原檔還原驗證失敗") from exc
                with suppress(Exception):
                    refresh_item_index(conn, item_id, {source.name: digest})
                if isinstance(exc, OrganizerError):
                    raise
                raise OrganizerError(f"改名後續處理失敗：{exc}") from exc
            executed.append(
                {
                    "candidate_id": candidate_id,
                    "rename_log_id": log_id,
                    "source_relative": source_relative,
                    "target_relative": target_relative,
                    "sha256": digest,
                }
            )
        except (OrganizerError, OSError, ValueError) as exc:
            failed.append({"candidate_id": candidate_id, "error": str(exc)})

    return {"executed": executed, "failed": failed}


def rename_history(conn: sqlite3.Connection, root_id: int) -> list[dict[str, object]]:
    _root_path(conn, root_id)
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, root_id, created_at, source_path, target_path, sha256, reverted_at
            FROM rename_log WHERE root_id=? ORDER BY id DESC
            """,
            (root_id,),
        )
    ]


def undo_rename(conn: sqlite3.Connection, root_id: int, log_id: int) -> dict[str, object]:
    root = _root_path(conn, root_id)
    row = conn.execute(
        """
        SELECT id, root_id, source_path, target_path, sha256, reverted_at
        FROM rename_log WHERE id=? AND root_id=?
        """,
        (log_id, root_id),
    ).fetchone()
    if row is None:
        raise OrganizerError("找不到指定改名紀錄")
    if row["reverted_at"]:
        raise OrganizerConflict("此改名紀錄已還原")

    source_relative = row["source_path"]
    target_relative = row["target_path"]
    source = _safe_file_path_preserve_name(root, source_relative)
    target = _safe_file_path_preserve_name(root, target_relative)
    if source.parent != target.parent:
        raise OrganizerError("還原只允許同資料夾檔名")
    if source.exists() and not _same_existing_file(source, target):
        raise OrganizerConflict("原檔名目前已存在，無法還原以免覆蓋")
    if not target.is_file() or target.is_symlink():
        raise OrganizerConflict("改名後檔案不存在或不是一般檔案")
    digest = sha256_file(target)
    if not row["sha256"] or digest != row["sha256"]:
        raise OrganizerConflict("檔案內容與改名紀錄 SHA-256 不一致，已停止還原")

    item_id = _item_id_for_parent(conn, root_id, source_relative)
    _rename_no_overwrite(target, source)
    try:
        if sha256_file(source) != digest:
            raise OrganizerError("還原後 SHA-256 驗證失敗")
        refresh_item_index(conn, item_id, {source.name: digest})
        with conn:
            cursor = conn.execute(
                """
                UPDATE rename_log SET reverted_at=CURRENT_TIMESTAMP
                WHERE id=? AND reverted_at IS NULL
                """,
                (log_id,),
            )
            if cursor.rowcount != 1:
                raise OrganizerConflict("改名紀錄狀態已改變，請重新整理")
            conn.execute(
                """
                INSERT INTO audit_log(action, source_path, target_path, sha256, detail_json)
                VALUES ('undo_rename', ?, ?, ?, json_object('rename_log_id', ?))
                """,
                (target_relative, source_relative, digest, log_id),
            )
    except Exception as exc:
        if source.is_file():
            _rename_no_overwrite(source, target)
            if sha256_file(target) != digest:
                raise OrganizerError("還原後續處理失敗，且改名狀態恢復驗證失敗") from exc
        with suppress(Exception):
            refresh_item_index(conn, item_id, {target.name: digest})
        raise

    result = conn.execute(
        """
        SELECT id, root_id, created_at, source_path, target_path, sha256, reverted_at
        FROM rename_log WHERE id=?
        """,
        (log_id,),
    ).fetchone()
    assert result is not None
    return dict(result)

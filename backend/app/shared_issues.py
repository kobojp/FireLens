"""Google Drive Desktop folder-sync journal for user-approved issue metadata only.

No shared SQLite, no operations on photos/ledger, and no silent concurrent overwrites.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from .config import get_app_data_dir, get_backup_dir

_SYNC_DIR = "FireLens-共享異常資料"
_LIMIT = 10000
_LOCK = RLock()
_EVENT_RE = re.compile(r"^[0-9a-f]{32}\.json$")
_NAMESPACE = uuid.UUID("83b68c1e-343b-4ef3-adf9-9ed20e2e5da4")


class SyncError(ValueError):
    pass


def _json(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _hash(data: object) -> str:
    return hashlib.sha256(_json(data)).hexdigest()


def _atomic(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + secrets.token_hex(16) + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive and path.exists():
            if path.read_bytes() != data:
                raise SyncError("同步事件識別碼發生衝突，禁止覆蓋")
            return
        # Event file names are unguessable UUID4. A device should never reuse
        # an existing name, and pre-existing events are never overwritten.
        if exclusive:
            if path.exists():
                if path.read_bytes() != data:
                    raise SyncError("同步事件識別碼發生衝突，禁止覆蓋")
            else:
                # Google Drive Desktop virtual drives may not support hard links.
                # UUID4 filenames are unique; never overwrite an existing event.
                temporary.rename(path)
                if path.read_bytes() != data:
                    raise SyncError("同步資料寫入後驗證失敗")
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load(path: Path) -> dict:
    if path.stat().st_size > 262144:
        raise SyncError("共享資料檔超出大小上限")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise SyncError("共享資料不是 JSON 物件")
    return obj


def _root(conn: sqlite3.Connection, root_id: int) -> Path:
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        raise SyncError("找不到照片根目錄")
    path = Path(str(row["path"])).expanduser()
    if not path.is_dir():
        raise SyncError("Google Drive 同步根目錄離線，保留本機資料")
    if path.is_symlink():
        raise SyncError("不可在符號連結根目錄啟用共用")
    return path


def _base(root: Path) -> Path:
    key = hashlib.sha256(str(root.absolute()).casefold().encode()).hexdigest()[:20]
    return get_app_data_dir() / "shared-issues" / key


def _state(root: Path) -> dict:
    path = _base(root) / "state.json"
    if not path.exists():
        return {
            "known": [],
            "applied": {},
            "label_map": {},
            "last_read": None,
            "manual_review": False,
        }
    return _load(path)


def _save_state(root: Path, state: dict) -> None:
    _atomic(_base(root) / "state.json", _json(state))


def _config() -> dict:
    path = get_app_data_dir() / "shared-issues" / "enabled.json"
    return _load(path) if path.exists() else {}


def _enabled(conn: sqlite3.Connection, root_id: int) -> bool:
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    return row is not None and _config().get(str(root_id)) == str(row["path"])


def _id() -> str:
    path = get_app_data_dir() / "shared-issues" / "device.json"
    if path.exists():
        return str(_load(path)["id"])
    value = uuid.uuid4().hex
    _atomic(path, _json({"id": value}))
    return value


def _events(root: Path) -> dict[str, dict]:
    directory = root / _SYNC_DIR / "events"
    if not directory.is_dir():
        raise SyncError("共享事件資料夾消失或離線，停止同步並保留本機資料")
    if directory.is_symlink():
        raise SyncError("共享事件目錄不可為符號連結")
    result: dict[str, dict] = {}
    files = list(directory.iterdir())
    # Windows and Google Drive Desktop may create desktop.ini in this folder.
    # Ignore ONLY this known metadata file; never ignore unexpected JSON,
    # directories, symlinks/reparse points, or malformed event files.
    events_count = 0
    for path in files:
        if path.name.casefold() == "desktop.ini" and path.is_file() and not path.is_symlink():
            continue
        if path.name.startswith(".") and path.suffix == ".tmp" and path.is_file():
            continue  # uncommitted atomic temporary file
        if not _EVENT_RE.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            raise SyncError(
                "共享事件目錄存在非同步資料檔案（已排除 Windows desktop.ini），停止同步"
            )
        events_count += 1
        if events_count > _LIMIT:
            raise SyncError("共享事件超過安全上限，請匯出封存後再處理")
        try:
            payload = _load(path)
            digest = payload.pop("sha256")
            if payload.get("v") != 1 or payload.get("id") != path.stem or digest != _hash(payload):
                raise ValueError("invalid hash or version")
            if payload.get("kind") not in {"label", "issue"}:
                raise ValueError("invalid kind")
            if not isinstance(payload.get("key"), str) or not 1 <= len(payload["key"]) <= 1024:
                raise ValueError("invalid key")
            parents = payload.get("parents")
            if not isinstance(parents, list) or any(
                not isinstance(i, str) or not re.fullmatch(r"[0-9a-f]{32}", i) for i in parents
            ):
                raise ValueError("invalid parents")
            result[path.stem] = payload
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SyncError("共享事件格式／完整性異常，停止同步且不改本機資料") from exc
    return result


def _heads(events: dict[str, dict], key: str) -> list[dict]:
    rows = [e for e in events.values() if e["key"] == key]
    parent_ids = {parent for e in rows for parent in e["parents"]}
    return sorted((e for e in rows if e["id"] not in parent_ids), key=lambda e: e["id"])


def _safe_event(path: Path, event: dict) -> None:
    data = {**event, "sha256": _hash(event)}
    raw = _json(data)
    if len(raw) > 32768:
        raise SyncError("同步事件過大")
    _atomic(path, raw, exclusive=True)


def _emit(root: Path, state: dict, kind: str, key: str, value: object) -> str:
    events = _events(root) if (root / _SYNC_DIR / "events").is_dir() else {}
    # Known file history is also needed when offline; no shared files overwritten.
    for filename in (_base(root) / "outbox").glob("*.json"):
        entry = _load(filename)
        if entry.get("id") and entry.get("sha256") == _hash(
            {k: v for k, v in entry.items() if k != "sha256"}
        ):
            entry.pop("sha256")
            events[entry["id"]] = entry
    parents = [item["id"] for item in _heads(events, key)]
    if not parents and state.get("applied", {}).get(key):
        # Continue the last VERIFIED local lineage while Drive is offline.
        parents = [state["applied"][key]]
    event_id = uuid.uuid4().hex
    event = {
        "v": 1,
        "id": event_id,
        "device": _id(),
        "kind": kind,
        "key": key,
        "value": value,
        "parents": parents,
        "at": datetime.now(UTC).isoformat(),
    }
    _safe_event(_base(root) / "outbox" / f"{event_id}.json", event)
    return event_id


def _guid(label_name: str) -> str:
    return uuid.uuid5(_NAMESPACE, label_name.strip().casefold()).hex


def _backup(root: Path, conn: sqlite3.Connection, root_id: int, *, reason: str) -> str:
    labels = [
        dict(r)
        for r in conn.execute("SELECT id,name,sort_order,active FROM issue_label ORDER BY id")
    ]
    items = [
        dict(r)
        for r in conn.execute(
            (
                "SELECT item_relative_path,category_code,device_code,label_id "
                "FROM item_issue WHERE root_id=? ORDER BY item_relative_path"
            ),
            (root_id,),
        )
    ]
    body = {
        "v": 1,
        "root_id": root_id,
        "at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "labels": labels,
        "items": items,
    }
    backup_id = uuid.uuid4().hex
    backup_dir = (
        get_backup_dir()
        / "shared-issues"
        / hashlib.sha256(str(root.absolute()).encode()).hexdigest()[:20]
    )
    _atomic(
        backup_dir / f"{backup_id}.json", _json({**body, "sha256": _hash(body)}), exclusive=True
    )
    return backup_id


def _backup_dir(root: Path) -> Path:
    return (
        get_backup_dir()
        / "shared-issues"
        / hashlib.sha256(str(root.absolute()).encode()).hexdigest()[:20]
    )


def configure(conn: sqlite3.Connection, root_id: int, enabled: bool) -> dict:
    with _LOCK:
        row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
        if row is None:
            raise SyncError("找不到照片根目錄")
        config = _config()
        if not enabled:
            config.pop(str(root_id), None)
            _atomic(get_app_data_dir() / "shared-issues" / "enabled.json", _json(config))
            return status(conn, root_id)
        root = _root(conn, root_id)
        if (root / _SYNC_DIR).is_symlink():
            raise SyncError("共享異常資料目錄不得為符號連結")
        (root / _SYNC_DIR / "events").mkdir(parents=True, exist_ok=True)
        config[str(root_id)] = str(row["path"])
        _atomic(get_app_data_dir() / "shared-issues" / "enabled.json", _json(config))
        state = _state(root)
        if not state.get("initialized"):
            # Bootstrap current local records once, with no parents, so remote
            # divergent states remain visible as conflict instead of overwrite.
            _backup(root, conn, root_id, reason="首次啟用前")
            for label in conn.execute(
                "SELECT id,name,sort_order,active FROM issue_label ORDER BY id"
            ):
                guid = _guid(str(label["name"]))
                state["label_map"][guid] = int(label["id"])
                _emit(
                    root,
                    state,
                    "label",
                    "label:" + guid,
                    {
                        "name": str(label["name"]),
                        "active": int(label["active"]),
                        "sort_order": int(label["sort_order"]),
                    },
                )
            for item in conn.execute(
                (
                    "SELECT item_relative_path,category_code,device_code,label_id "
                    "FROM item_issue WHERE root_id=?"
                ),
                (root_id,),
            ):
                label = conn.execute(
                    "SELECT name FROM issue_label WHERE id=?", (item["label_id"],)
                ).fetchone()
                if label:
                    _emit(
                        root,
                        state,
                        "issue",
                        "issue:"
                        + str(item["category_code"])
                        + ":"
                        + str(item["item_relative_path"]),
                        {
                            "path": item["item_relative_path"],
                            "category": item["category_code"],
                            "code": item["device_code"],
                            "label_guid": _guid(str(label["name"])),
                        },
                    )
            state["initialized"] = True
            _save_state(root, state)
        return status(conn, root_id)


def status(conn: sqlite3.Connection, root_id: int) -> dict:
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        raise SyncError("找不到根目錄")
    active = _enabled(conn, root_id)
    root = Path(str(row["path"]))
    state = _state(root)
    pending = len(list((_base(root) / "outbox").glob("*.json")))
    return {
        "enabled": active,
        "root_id": root_id,
        "pending": pending,
        "last_read": state.get("last_read"),
        "last_device_read": state.get("last_read"),
        "warning": "使用 Google Drive 桌面版同步；本機讀寫不代表已上傳雲端",
        "manual_review": bool(state.get("manual_review")),
        "shared_folder": str(root / _SYNC_DIR) if active else "",
        "state": "disabled"
        if not active
        else "review_required"
        if state.get("manual_review")
        else "offline"
        if not root.is_dir()
        else "pending"
        if pending
        else "local_read",
    }


def record_label(conn: sqlite3.Connection, label_id: int) -> None:
    with _LOCK:
        label = conn.execute(
            "SELECT id,name,active,sort_order FROM issue_label WHERE id=?",
            (label_id,),
        ).fetchone()
        if label is None:
            return
        for key, path in _config().items():
            root_id = int(key)
            if not _enabled(conn, root_id):
                continue
            root = Path(path)
            state = _state(root)
            guid = next(
                (k for k, v in state.get("label_map", {}).items() if v == label_id),
                _guid(str(label["name"])),
            )
            state["label_map"][guid] = label_id
            _emit(
                root,
                state,
                "label",
                "label:" + guid,
                {
                    "name": str(label["name"]),
                    "active": int(label["active"]),
                    "sort_order": int(label["sort_order"]),
                },
            )
            _save_state(root, state)


def record_item(conn: sqlite3.Connection, item_id: int, label_id: int | None) -> None:
    with _LOCK:
        row = conn.execute(
            "SELECT i.root_id,i.relative_path,i.code,c.code AS category_code FROM item i "
            "JOIN category c ON c.id=i.category_id WHERE i.id=?",
            (item_id,),
        ).fetchone()
        if row is None or not _enabled(conn, int(row["root_id"])):
            return
        root_row = conn.execute("SELECT path FROM root WHERE id=?", (row["root_id"],)).fetchone()
        if root_row is None:
            return
        # Preserve the new event in LOCAL outbox even when Drive is offline.
        root = Path(str(root_row["path"]))
        state = _state(root)
        guid = None
        if label_id is not None:
            label = conn.execute("SELECT name FROM issue_label WHERE id=?", (label_id,)).fetchone()
            if label:
                guid = next(
                    (k for k, v in state.get("label_map", {}).items() if v == label_id),
                    _guid(str(label["name"])),
                )
                state["label_map"][guid] = label_id
        _emit(
            root,
            state,
            "issue",
            "issue:" + str(row["category_code"]) + ":" + str(row["relative_path"]),
            {
                "path": row["relative_path"],
                "category": row["category_code"],
                "code": row["code"],
                "label_guid": guid,
            },
        )
        _save_state(root, state)


def _validated_events(root: Path, state: dict) -> dict[str, dict]:
    current = _events(root)
    known = set(state.get("known", []))
    missing = known - set(current)
    if missing:
        raise SyncError(
            f"共享資料缺少 {len(missing)} 筆曾驗證事件，疑似雲端誤刪／版本退回；"
            "保留本機資料，請從歷史備份人工復原共享事件"
        )
    # Validate the full causal graph and payloads BEFORE archiving a remote
    # file as trustworthy for later recovery.
    _merged_view(current)
    # Preserve verified files in a local immutable archive for recovery.
    for event in current.values():
        _safe_event(_base(root) / "archive" / (event["id"] + ".json"), event)
    return current


def _value(event: dict) -> dict:
    value = event.get("value")
    if not isinstance(value, dict):
        raise SyncError("事件內容格式不正確")
    if event["kind"] == "label":
        if not isinstance(value.get("name"), str) or not 1 <= len(value["name"]) <= 80:
            raise SyncError("異常分類事件名稱無效")
        if type(value.get("active")) is not int or value["active"] not in (0, 1):
            raise SyncError("異常分類事件狀態無效")
        if type(value.get("sort_order")) is not int or not 0 <= value["sort_order"] <= 100000:
            raise SyncError("異常分類事件排序無效")
    else:
        if not isinstance(value.get("path"), str) or not 1 <= len(value["path"]) <= 512:
            raise SyncError("設備相對路徑無效")
        if (
            value["path"].startswith(("/", "\\"))
            or ".." in value["path"].replace("\\", "/").split("/")
            or "\x00" in value["path"]
            or ":" in value["path"]
        ):
            raise SyncError("設備相對路徑不安全")
        if value.get("category") not in ("extinguisher", "box", "lamp"):
            raise SyncError("設備類別無效")
        if not isinstance(value.get("code"), str) or not 1 <= len(value["code"]) <= 120:
            raise SyncError("設備編號格式無效")
        if value.get("label_guid") is not None and not re.fullmatch(
            r"[0-9a-f]{32}", str(value["label_guid"])
        ):
            raise SyncError("異常分類識別碼無效")
        if event["key"] != "issue:" + value["category"] + ":" + value["path"]:
            raise SyncError("事件設備識別不一致")
    return value


def _merged_view(events: dict[str, dict]) -> tuple[dict[str, dict], list[dict]]:
    # Reject incomplete Drive sync, fabricated parent links and invalid older
    # events, not only current heads. Otherwise a partial upload could be
    # treated as a new authoritative head.
    for event in events.values():
        _value(event)
        if not isinstance(event.get("device"), str) or not re.fullmatch(
            r"[0-9a-f]{32}", event["device"]
        ):
            raise SyncError("事件裝置識別碼不合法")
        for parent in event["parents"]:
            previous = events.get(parent)
            if previous is None:
                raise SyncError("事件繼承鏈不完整，可能尚未完成 Google Drive 同步")
            if parent == event["id"] or previous["key"] != event["key"]:
                raise SyncError("事件繼承鏈不安全，停止套用")
    effective: dict[str, dict] = {}
    conflicts: list[dict] = []
    for key in sorted(set(e["key"] for e in events.values())):
        heads = _heads(events, key)
        if not heads:
            raise SyncError("事件繼承關係不正確")
        for event in heads:
            _value(event)
        if len(heads) > 1 and any(h["value"] != heads[0]["value"] for h in heads[1:]):
            conflicts.append(
                {
                    "key": key,
                    "kind": heads[0]["kind"],
                    "candidates": [
                        {
                            "event_id": e["id"],
                            "device": e["device"],
                            "value": e["value"],
                            "at": e["at"],
                        }
                        for e in heads
                    ],
                }
            )
        else:
            effective[key] = heads[0]
    return effective, conflicts


def _apply(conn: sqlite3.Connection, root_id: int, state: dict, effective: dict[str, dict]) -> int:
    changed = 0
    # Label must exist locally before an issue can point at it.
    for kind in ("label", "issue"):
        for key, event in effective.items():
            if event["kind"] != kind or state["applied"].get(key) == event["id"]:
                continue
            value = _value(event)
            if kind == "label":
                guid = key.removeprefix("label:")
                label_id = state["label_map"].get(guid)
                existing = (
                    conn.execute("SELECT id FROM issue_label WHERE id=?", (label_id,)).fetchone()
                    if label_id
                    else None
                )
                if existing is None:
                    # Adopt an existing same-name label if possible: each
                    # machine's SQLite identity is private and not portable.
                    existing = conn.execute(
                        "SELECT id FROM issue_label WHERE name=? COLLATE NOCASE", (value["name"],)
                    ).fetchone()
                if existing is None:
                    cursor = conn.execute(
                        "INSERT INTO issue_label(name,sort_order,active) VALUES (?,?,?)",
                        (value["name"], value["sort_order"], value["active"]),
                    )
                    label_id = int(cursor.lastrowid)
                else:
                    label_id = int(existing["id"])
                    conn.execute(
                        "UPDATE issue_label SET name=?,active=?,sort_order=? WHERE id=?",
                        (value["name"], value["active"], value["sort_order"], label_id),
                    )
                state["label_map"][guid] = label_id
            else:
                guid = value["label_guid"]
                label_id = state["label_map"].get(guid) if guid else None
                if guid and label_id is None:
                    # Don't create an inconsistent relationship.
                    raise SyncError("設備異常所指分類未同步，保留本機資料")
                if guid:
                    conn.execute(
                        """
                        INSERT INTO item_issue(
                            root_id, item_relative_path, category_code, device_code, label_id
                        )
                        VALUES (?,?,?,?,?)
                        ON CONFLICT(root_id,item_relative_path)
                        DO UPDATE SET category_code=excluded.category_code,
                            device_code=excluded.device_code,label_id=excluded.label_id,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (root_id, value["path"], value["category"], value["code"], label_id),
                    )
                else:
                    conn.execute(
                        "DELETE FROM item_issue WHERE root_id=? AND item_relative_path=?",
                        (root_id, value["path"]),
                    )
            state["applied"][key] = event["id"]
            changed += 1
    return changed


def synchronize(conn: sqlite3.Connection, root_id: int) -> dict:
    with _LOCK:
        if not _enabled(conn, root_id):
            raise SyncError("尚未啟用此根目錄的共享異常同步")
        root = _root(conn, root_id)
        state = _state(root)
        if state.get("manual_review"):
            raise SyncError("本機剛執行復原，需確認同步方向後才可繼續")
        events = _validated_events(root, state)
        pending = _base(root) / "outbox"
        # Read and validate all pending before publishing anything.
        outgoing: list[tuple[Path, dict]] = []
        for entry in pending.glob("*.json"):
            event = _load(entry)
            digest = event.pop("sha256", None)
            if event.get("v") != 1 or digest != _hash(event):
                raise SyncError("本機待同步事件損壞，停止同步")
            _value(event)
            outgoing.append((entry, event))
            events[event["id"]] = event
        # Validate all remote + pending events before any new write.
        effective, conflicts = _merged_view(events)
        if len(events) > _LIMIT:
            raise SyncError("事件總數超過安全上限")
        for entry, event in outgoing:
            _safe_event(root / _SYNC_DIR / "events" / (event["id"] + ".json"), event)
            # Keep local archived copy before clearing outbox.
            _safe_event(_base(root) / "archive" / (event["id"] + ".json"), event)
            entry.unlink()
        # Backup before first application of new remote data.
        incoming = {key: e for key, e in effective.items() if state["applied"].get(key) != e["id"]}
        if incoming:
            _backup(root, conn, root_id, reason="套用新共享事件前")
            try:
                with conn:
                    changed = _apply(conn, root_id, state, effective)
            except (sqlite3.Error, SyncError) as exc:
                raise SyncError("共享異常套用失敗，已保留原本資料庫及歷史備份") from exc
        else:
            changed = 0
        state["known"] = sorted(events)
        state["last_read"] = datetime.now(UTC).isoformat()
        state["conflicts"] = conflicts
        _save_state(root, state)
        return {
            **status(conn, root_id),
            "applied": changed,
            "conflicts": conflicts,
            "verified_events": len(events),
        }


def conflicts(conn: sqlite3.Connection, root_id: int) -> list[dict]:
    if not _enabled(conn, root_id):
        return []
    root = _root(conn, root_id)
    events = _validated_events(root, _state(root))
    _, unresolved = _merged_view(events)
    return unresolved


def resolve(conn: sqlite3.Connection, root_id: int, key: str, event_id: str) -> dict:
    with _LOCK:
        if not _enabled(conn, root_id):
            raise SyncError("尚未啟用同步")
        root = _root(conn, root_id)
        state = _state(root)
        events = _validated_events(root, state)
        _, unresolved = _merged_view(events)
        conflict = next((c for c in unresolved if c["key"] == key), None)
        if conflict is None:
            raise SyncError("此項目目前沒有待處理的版本衝突")
        chosen = next(
            (events[e["event_id"]] for e in conflict["candidates"] if e["event_id"] == event_id),
            None,
        )
        if chosen is None:
            raise SyncError("選擇的版本不在目前待確認候選中")
        event = {
            "v": 1,
            "id": uuid.uuid4().hex,
            "device": _id(),
            "kind": chosen["kind"],
            "key": key,
            "value": chosen["value"],
            "parents": [c["event_id"] for c in conflict["candidates"]],
            "at": datetime.now(UTC).isoformat(),
        }
        _safe_event(_base(root) / "outbox" / (event["id"] + ".json"), event)
        return synchronize(conn, root_id)


def backups(conn: sqlite3.Connection, root_id: int) -> list[dict]:
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        raise SyncError("找不到根目錄")
    directory = _backup_dir(Path(str(row["path"])))
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True)[:100]:
        try:
            data = _load(path)
            digest = data.pop("sha256")
            if digest != _hash(data) or data["root_id"] != root_id:
                continue
            result.append(
                {
                    "id": path.stem,
                    "time": data["at"],
                    "reason": data["reason"],
                    "labels": len(data["labels"]),
                    "items": len(data["items"]),
                }
            )
        except (ValueError, KeyError, OSError):
            continue
    return result


def backup_preview(conn: sqlite3.Connection, root_id: int, backup_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", backup_id):
        raise SyncError("備份識別碼無效")
    row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
    if row is None:
        raise SyncError("找不到根目錄")
    # Local backup must stay restorable even if Google Drive is offline.
    root = Path(str(row["path"]))
    path = _backup_dir(root) / (backup_id + ".json")
    if not path.is_file():
        raise SyncError("找不到備份檔")
    data = _load(path)
    digest = data.pop("sha256", None)
    if digest != _hash(data) or data.get("root_id") != root_id:
        raise SyncError("備份完整性驗證失敗")
    current_items = {
        str(r["item_relative_path"]): int(r["label_id"])
        for r in conn.execute(
            "SELECT item_relative_path,label_id FROM item_issue WHERE root_id=?",
            (root_id,),
        )
    }
    backup_items = {str(r["item_relative_path"]): int(r["label_id"]) for r in data["items"]}
    added = sum(key not in current_items for key in backup_items)
    removed = sum(key not in backup_items for key in current_items)
    changed = sum(
        current_items[key] != backup_items[key]
        for key in current_items.keys() & backup_items.keys()
    )
    return {
        "id": backup_id,
        "time": data["at"],
        "reason": data["reason"],
        "labels": len(data["labels"]),
        "items": len(data["items"]),
        "current_items": len(current_items),
        "adding": added,
        "removing": removed,
        "changing": changed,
        "_data": data,
    }


def restore(conn: sqlite3.Connection, root_id: int, backup_id: str, confirm: bool) -> dict:
    with _LOCK:
        if not confirm:
            raise SyncError("復原前必須明確確認")
        preview = backup_preview(conn, root_id, backup_id)
        data = preview.pop("_data")
        row = conn.execute("SELECT path FROM root WHERE id=?", (root_id,)).fetchone()
        if row is None:
            raise SyncError("找不到根目錄")
        root = Path(str(row["path"]))
        _backup(root, conn, root_id, reason="手動復原前")
        with conn:
            for label in data["labels"]:
                if conn.execute("SELECT 1 FROM issue_label WHERE id=?", (label["id"],)).fetchone():
                    conn.execute(
                        "UPDATE issue_label SET name=?,active=?,sort_order=? WHERE id=?",
                        (label["name"], label["active"], label["sort_order"], label["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO issue_label(id,name,active,sort_order) VALUES (?,?,?,?)",
                        (label["id"], label["name"], label["active"], label["sort_order"]),
                    )
            conn.execute("DELETE FROM item_issue WHERE root_id=?", (root_id,))
            for item in data["items"]:
                conn.execute(
                    (
                        "INSERT INTO item_issue("
                        "root_id,item_relative_path,category_code,device_code,label_id"
                        ") VALUES (?,?,?,?,?)"
                    ),
                    (
                        root_id,
                        item["item_relative_path"],
                        item["category_code"],
                        item["device_code"],
                        item["label_id"],
                    ),
                )
        state = _state(root)
        state["manual_review"] = True
        _save_state(root, state)
        return {
            **preview,
            "restored_locally": True,
            "warning": "已復原本機資料，暫停共享同步以免遠端版本覆蓋，請先檢查衝突",
        }


def recover_missing_shared_events(conn: sqlite3.Connection, root_id: int, confirm: bool) -> dict:
    with _LOCK:
        if not confirm:
            raise SyncError("手動補回雲端誤刪資料需要明確確認")
        root = _root(conn, root_id)
        state = _state(root)
        current = _events(root)
        missing = set(state.get("known", [])) - set(current)
        if not missing:
            return {"restored": 0, "message": "共享事件未遺失"}
        archived = []
        for event_id in sorted(missing):
            path = _base(root) / "archive" / (event_id + ".json")
            if not path.is_file():
                raise SyncError("本機歷史封存不完整，不允許部分補回事件")
            payload = _load(path)
            digest = payload.pop("sha256", None)
            if payload.get("id") != event_id or digest != _hash(payload):
                raise SyncError("本機歷史事件校驗失敗，停止復原")
            archived.append(payload)
        _backup(root, conn, root_id, reason="補回共享誤刪事件前")
        for event in archived:
            _safe_event(root / _SYNC_DIR / "events" / (event["id"] + ".json"), event)
        return {
            "restored": len(archived),
            "message": "已將本機已驗證事件重新放回共享資料夾，仍需等待 Google Drive 真正同步",
        }


def resume_after_restore(conn: sqlite3.Connection, root_id: int, confirm: bool) -> dict:
    if not confirm:
        raise SyncError("必須確認繼續同步將以共用版本為準")
    root = _root(conn, root_id)
    state = _state(root)
    state["manual_review"] = False
    _save_state(root, state)
    return synchronize(conn, root_id)


def enabled_roots(conn: sqlite3.Connection) -> list[int]:
    """Autoload only explicitly enabled roots still bound to their original path."""
    result = []
    for root_id in _config():
        try:
            value = int(root_id)
        except (ValueError, TypeError):
            continue
        if _enabled(conn, value):
            result.append(value)
    return result


def record_renamed_item(
    conn: sqlite3.Connection, item_id: int, old_relative_path: str, old_code: str
) -> None:
    """Propagate an explicitly renamed marked folder without losing its label."""
    with _LOCK:
        row = conn.execute(
            "SELECT i.root_id, i.relative_path, i.code, c.code AS category_code, "
            "x.label_id FROM item i JOIN category c ON c.id=i.category_id "
            "LEFT JOIN item_issue x ON x.root_id=i.root_id AND "
            "x.item_relative_path=i.relative_path WHERE i.id=?",
            (item_id,),
        ).fetchone()
        if row is None or row["label_id"] is None or not _enabled(conn, int(row["root_id"])):
            return
        root = Path(
            str(
                conn.execute("SELECT path FROM root WHERE id=?", (row["root_id"],)).fetchone()[
                    "path"
                ]
            )
        )
        state = _state(root)
        key = "issue:" + str(row["category_code"]) + ":"
        # Explicit old-path clear; never change photos, clear other categories,
        # or guess whether an unrelated folder has the same name.
        _emit(
            root,
            state,
            "issue",
            key + old_relative_path,
            {
                "path": old_relative_path,
                "category": row["category_code"],
                "code": old_code,
                "label_guid": None,
            },
        )
        label_id = int(row["label_id"])
        label = conn.execute("SELECT name FROM issue_label WHERE id=?", (label_id,)).fetchone()
        if label is None:
            raise SyncError("更名後異常分類遺失，無法建立共享事件")
        guid = next(
            (k for k, v in state["label_map"].items() if v == label_id),
            _guid(str(label["name"])),
        )
        state["label_map"][guid] = label_id
        _emit(
            root,
            state,
            "issue",
            key + str(row["relative_path"]),
            {
                "path": row["relative_path"],
                "category": row["category_code"],
                "code": row["code"],
                "label_guid": guid,
            },
        )
        _save_state(root, state)

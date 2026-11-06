from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TRANSACTION_SCHEMA = 1
TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class UpdateProtocolError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def validate_transaction_id(value: str) -> str:
    value = value.strip().lower()
    if not TRANSACTION_ID_RE.fullmatch(value):
        raise UpdateProtocolError("更新 transaction id 不合法")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateProtocolError(f"無法讀取更新狀態：{exc}") from exc
    if not isinstance(payload, dict):
        raise UpdateProtocolError("更新狀態格式不正確")
    return payload


def atomic_write_handshake(path: Path, transaction_id: str, **fields: Any) -> None:
    atomic_write_json(
        path,
        {
            "schema": TRANSACTION_SCHEMA,
            "transaction_id": validate_transaction_id(transaction_id),
            "timestamp": utc_now(),
            **fields,
        },
    )


def validate_handshake(path: Path, transaction_id: str, expected_status: str) -> dict[str, Any]:
    payload = read_json(path)
    if payload.get("schema") != TRANSACTION_SCHEMA:
        raise UpdateProtocolError("更新握手格式不支援")
    if str(payload.get("transaction_id") or "") != validate_transaction_id(transaction_id):
        raise UpdateProtocolError("更新握手 transaction 不一致")
    if str(payload.get("status") or "") != expected_status:
        raise UpdateProtocolError("更新握手狀態不正確")
    return payload

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_private_key(private_key_file: Path | None) -> Ed25519PrivateKey:
    if private_key_file is not None:
        pem = private_key_file.read_bytes()
    else:
        encoded = os.environ.get("FIRELENS_UPDATE_PRIVATE_KEY_B64", "").strip()
        if not encoded:
            raise RuntimeError(
                "缺少 FIRELENS_UPDATE_PRIVATE_KEY_B64 GitHub Actions Secret，"
                "拒絕建立未簽章 Release。"
            )
        try:
            pem = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise RuntimeError("FIRELENS_UPDATE_PRIVATE_KEY_B64 不是合法 Base64") from exc

    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("更新私鑰不是 Ed25519 私鑰")
    return key


def sign_release(
    version: str,
    exe: Path,
    manifest_path: Path,
    signature_path: Path,
    private_key_file: Path | None = None,
) -> None:
    if not exe.is_file():
        raise RuntimeError(f"找不到 Release EXE：{exe}")
    expected_name = f"FireLens-{version}-windows-x64.exe"
    if exe.name != expected_name:
        raise RuntimeError(f"Release EXE 名稱必須是 {expected_name}")

    manifest = {
        "schema": 1,
        "version": version,
        "asset": exe.name,
        "sha256": _sha256(exe),
        "size": exe.stat().st_size,
    }
    payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    signature = _load_private_key(private_key_file).sign(payload)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(payload)
    signature_path.write_text(base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign FireLens update manifest")
    parser.add_argument("--version", required=True)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--private-key-file", type=Path)
    args = parser.parse_args()
    sign_release(
        args.version,
        args.exe,
        args.manifest,
        args.signature,
        args.private_key_file,
    )
    print(f"Signed update manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from desktop.update import UpdateError, update_capability, verify_manifest


def _signed_manifest(
    *,
    version: str = "1.2.0",
    asset: str = "FireLens-1.2.0-windows-x64.exe",
    sha256: str = "a" * 64,
    size: int = 123456,
) -> tuple[bytes, bytes, bytes]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    payload = (
        json.dumps(
            {
                "schema": 1,
                "version": version,
                "asset": asset,
                "sha256": sha256,
                "size": size,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    signature = base64.b64encode(private_key.sign(payload)) + b"\n"
    return payload, signature, public_key


def test_verify_signed_update_manifest() -> None:
    payload, signature, public_key = _signed_manifest()
    manifest = verify_manifest(payload, signature, public_key)
    assert manifest.version == "1.2.0"
    assert manifest.asset == "FireLens-1.2.0-windows-x64.exe"
    assert manifest.sha256 == "a" * 64
    assert manifest.size == 123456


def test_tampered_update_manifest_is_rejected() -> None:
    payload, signature, public_key = _signed_manifest()
    tampered = payload.replace(b'"size":123456', b'"size":123457')
    with pytest.raises(UpdateError, match="簽章驗證失敗"):
        verify_manifest(tampered, signature, public_key)


def test_manifest_asset_name_must_match_version() -> None:
    payload, signature, public_key = _signed_manifest(asset="FireLens.exe")
    with pytest.raises(UpdateError, match="執行檔名稱"):
        verify_manifest(payload, signature, public_key)


def test_update_capability_is_signed_and_dev_mode_is_not_installable() -> None:
    capability = update_capability()
    assert capability["enabled"] is True
    assert "Ed25519" in str(capability["reason"])
    assert capability["repository"] == "kobojp/FireLens"
    assert capability["installable"] is False

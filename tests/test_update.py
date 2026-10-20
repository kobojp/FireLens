from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import desktop.update as update
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


def test_download_update_reports_security_stages_and_reuses_valid_stage(
    monkeypatch, tmp_path: Path
) -> None:
    payload = b"verified-new-exe"
    manifest = update.ReleaseManifest(
        version="9.9.9",
        asset="FireLens-9.9.9-windows-x64.exe",
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
    )
    monkeypatch.setattr(
        update,
        "_verified_latest_release",
        lambda: (
            manifest,
            {manifest.asset: "https://github.com/kobojp/FireLens/releases/download/v9.9.9/x"},
            {"html_url": "https://github.com/kobojp/FireLens/releases/tag/v9.9.9", "body": ""},
            b"manifest",
            b"signature",
        ),
    )

    def fake_update_dir(version: str | None = None) -> Path:
        root = tmp_path / "updates"
        return root / f"v{version}" if version else root

    monkeypatch.setattr(update, "_update_dir", fake_update_dir)
    staged = fake_update_dir("9.9.9") / manifest.asset
    staged.parent.mkdir(parents=True)
    staged.write_bytes(payload)
    selftests: list[Path] = []
    monkeypatch.setattr(update, "_self_test_exe", lambda path: selftests.append(path))
    phases: list[str] = []

    result = update.download_update(
        "9.9.9",
        lambda phase, _completed, _total: phases.append(phase),
    )

    assert result["downloaded"] is True
    assert phases == [
        "verifying_signature",
        "verifying_manifest",
        "verifying_sha256",
        "self_test",
        "ready",
    ]
    assert selftests == [staged]


def test_download_asset_rejects_sha256_mismatch_and_removes_partial_file(
    monkeypatch, tmp_path: Path
) -> None:
    data = b"tampered-update"
    manifest = update.ReleaseManifest(
        version="9.9.9",
        asset="FireLens-9.9.9-windows-x64.exe",
        sha256="0" * 64,
        size=len(data),
    )

    class FakeResponse:
        def __init__(self) -> None:
            self.stream = io.BytesIO(data)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def geturl(self) -> str:
            return "https://github.com/kobojp/FireLens/fake.exe"

        def read(self, size: int) -> bytes:
            return self.stream.read(size)

    monkeypatch.setattr(update.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    target = tmp_path / manifest.asset
    with pytest.raises(UpdateError, match="SHA-256 驗證失敗"):
        update._download_asset("https://github.com/kobojp/FireLens/fake.exe", target, manifest)
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_schedule_install_rejects_tampered_staged_exe_before_backup(
    monkeypatch, tmp_path: Path
) -> None:
    manifest = update.ReleaseManifest(
        version="9.9.9",
        asset="FireLens-9.9.9-windows-x64.exe",
        sha256=hashlib.sha256(b"expected").hexdigest(),
        size=len(b"tampered"),
    )
    version_dir = tmp_path / "updates" / "v9.9.9"
    version_dir.mkdir(parents=True)
    (version_dir / update.MANIFEST_NAME).write_bytes(b"manifest")
    (version_dir / update.SIGNATURE_NAME).write_bytes(b"signature")
    (version_dir / manifest.asset).write_bytes(b"tampered")
    monkeypatch.setattr(
        update,
        "update_capability",
        lambda: {
            "installable": True,
            "install_reason": "ok",
        },
    )
    monkeypatch.setattr(
        update, "_update_dir", lambda version=None: version_dir if version else tmp_path / "updates"
    )
    monkeypatch.setattr(update, "verify_manifest", lambda *_args, **_kwargs: manifest)

    with pytest.raises(UpdateError, match="本機更新檔驗證失敗"):
        update.schedule_install("9.9.9")
    assert not list(version_dir.glob("*-backup.exe"))

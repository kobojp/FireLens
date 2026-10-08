from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from backend.app.config import get_app_data_dir
from desktop.version import __version__

REPOSITORY = "kobojp/FireLens"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAhsKxU08rOiLJZMhkg4UdMSLzeTmXMx2+SOWl+fcidRs=
-----END PUBLIC KEY-----
"""
MANIFEST_NAME = "update-manifest.json"
SIGNATURE_NAME = "update-manifest.sig"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 8 * 1024
MAX_EXE_BYTES = 250 * 1024 * 1024
_ALLOWED_HTTPS_HOSTS = {
    "api.github.com",
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
}
_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    asset: str
    sha256: str
    size: int


def _semver(version: str) -> tuple[int, int, int]:
    match = _VERSION_RE.fullmatch(version)
    if not match:
        raise UpdateError(f"版本格式不合法：{version}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def _update_dir(version: str | None = None) -> Path:
    root = get_app_data_dir() / "updates"
    return root / f"v{version}" if version else root


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json, application/octet-stream",
            "User-Agent": f"FireLens/{__version__}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _validate_https_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HTTPS_HOSTS:
        raise UpdateError("更新來源不是允許的 GitHub HTTPS 網址")


def _fetch_bytes(url: str, max_bytes: int, timeout: float = 20.0) -> bytes:
    _validate_https_url(url)
    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as response:
            _validate_https_url(response.geturl())
            data = response.read(max_bytes + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"無法連線更新伺服器：{exc}") from exc
    if len(data) > max_bytes:
        raise UpdateError("更新伺服器回應超過安全大小限制")
    return data


def _fetch_json(url: str) -> dict[str, object]:
    raw = _fetch_bytes(url, 2 * 1024 * 1024)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("更新伺服器回傳的 JSON 無法解析") from exc
    if not isinstance(data, dict):
        raise UpdateError("更新伺服器回傳格式不正確")
    return data


def verify_manifest(
    manifest_bytes: bytes,
    signature_bytes: bytes,
    public_key_pem: bytes = PUBLIC_KEY_PEM,
) -> ReleaseManifest:
    try:
        signature = base64.b64decode(signature_bytes.strip(), validate=True)
        key = serialization.load_pem_public_key(public_key_pem)
    except (ValueError, TypeError) as exc:
        raise UpdateError("更新簽章格式不正確") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise UpdateError("更新公鑰類型不正確")
    try:
        key.verify(signature, manifest_bytes)
    except InvalidSignature as exc:
        raise UpdateError("更新簽章驗證失敗，已拒絕此更新") from exc

    try:
        payload = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("更新 manifest 無法解析") from exc
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise UpdateError("不支援的更新 manifest 格式")

    version = str(payload.get("version") or "")
    _semver(version)
    asset = str(payload.get("asset") or "")
    expected_asset = f"FireLens-{version}-windows-x64.exe"
    if asset != expected_asset:
        raise UpdateError("更新 manifest 的執行檔名稱不符")
    sha256 = str(payload.get("sha256") or "").lower()
    if not _SHA256_RE.fullmatch(sha256):
        raise UpdateError("更新 manifest 的 SHA-256 不合法")
    size = payload.get("size")
    if not isinstance(size, int) or not 0 < size <= MAX_EXE_BYTES:
        raise UpdateError("更新 manifest 的檔案大小不合法")
    return ReleaseManifest(version=version, asset=asset, sha256=sha256, size=size)


def _release_assets(release: dict[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    assets = release.get("assets")
    if not isinstance(assets, list):
        return result
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        url = item.get("browser_download_url")
        if isinstance(name, str) and isinstance(url, str):
            _validate_https_url(url)
            result[name] = url
    return result


def _verified_latest_release() -> tuple[
    ReleaseManifest,
    dict[str, str],
    dict[str, object],
    bytes,
    bytes,
]:
    release = _fetch_json(LATEST_RELEASE_API)
    if release.get("draft") is True or release.get("prerelease") is True:
        raise UpdateError("最新版本不是正式穩定版")
    assets = _release_assets(release)
    manifest_url = assets.get(MANIFEST_NAME)
    signature_url = assets.get(SIGNATURE_NAME)
    if not manifest_url or not signature_url:
        raise UpdateError("最新 Release 缺少已簽章更新資訊")
    manifest_bytes = _fetch_bytes(manifest_url, MAX_MANIFEST_BYTES)
    signature_bytes = _fetch_bytes(signature_url, MAX_SIGNATURE_BYTES)
    manifest = verify_manifest(manifest_bytes, signature_bytes)
    if str(release.get("tag_name") or "") != f"v{manifest.version}":
        raise UpdateError("Release Tag 與已簽章版本不一致")
    if manifest.asset not in assets:
        raise UpdateError("Release 缺少 manifest 指定的 Windows EXE")
    return manifest, assets, release, manifest_bytes, signature_bytes


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _staged_exe(manifest: ReleaseManifest) -> Path:
    return _update_dir(manifest.version) / manifest.asset


def _staged_is_valid(manifest: ReleaseManifest) -> bool:
    path = _staged_exe(manifest)
    try:
        return (
            path.is_file()
            and path.stat().st_size == manifest.size
            and _sha256_file(path) == manifest.sha256
        )
    except OSError:
        return False


def update_capability() -> dict[str, object]:
    installable = os.name == "nt" and bool(getattr(sys, "frozen", False))
    return {
        "enabled": True,
        "reason": "已啟用 Ed25519 簽章驗證的 GitHub Releases 安全更新。",
        "repository": REPOSITORY,
        "installable": installable,
        "install_reason": (
            "可下載並自動安裝更新。"
            if installable
            else "目前是開發模式；可檢查更新，但只有打包後的 Windows EXE 可自動安裝。"
        ),
    }


def check_for_update(current_version: str = __version__) -> dict[str, object]:
    manifest, assets, release, _, _ = _verified_latest_release()
    current = _semver(current_version)
    latest = _semver(manifest.version)
    capability = update_capability()
    notes = str(release.get("body") or "")[:12000]
    return {
        "current_version": current_version,
        "latest_version": manifest.version,
        "available": latest > current,
        "signature_verified": True,
        "asset_name": manifest.asset,
        "asset_size": manifest.size,
        "downloaded": _staged_is_valid(manifest),
        "installable": capability["installable"],
        "install_reason": capability["install_reason"],
        "release_url": str(release.get("html_url") or f"https://github.com/{REPOSITORY}/releases"),
        "notes": notes,
        "asset_url": assets[manifest.asset],
    }


def _download_asset(url: str, target: Path, manifest: ReleaseManifest) -> None:
    _validate_https_url(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    total = 0
    try:
        with (
            urllib.request.urlopen(_request(url), timeout=60) as response,
            part.open("wb") as output,
        ):
            _validate_https_url(response.geturl())
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_EXE_BYTES or total > manifest.size:
                    raise UpdateError("下載的更新檔大小超過 manifest")
                digest.update(chunk)
                output.write(chunk)
        if total != manifest.size:
            raise UpdateError("下載的更新檔大小與 manifest 不一致")
        if digest.hexdigest() != manifest.sha256:
            raise UpdateError("下載的更新檔 SHA-256 驗證失敗")
        os.replace(part, target)
    except Exception:
        part.unlink(missing_ok=True)
        raise


def _self_test_exe(path: Path) -> None:
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
    selftest_dir = Path(tempfile.mkdtemp(prefix="FireLens-update-selftest-"))
    env = os.environ.copy()
    env["FIRELENS_DATA_DIR"] = str(selftest_dir)
    try:
        result = subprocess.run(
            [str(path), "--self-test"],
            check=False,
            timeout=60,
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"新版 EXE 自我測試無法完成：{exc}") from exc
    finally:
        shutil.rmtree(selftest_dir, ignore_errors=True)
    if result.returncode != 0:
        raise UpdateError(f"新版 EXE 自我測試失敗：exit code {result.returncode}")


def download_update(expected_version: str | None = None) -> dict[str, object]:
    manifest, assets, release, manifest_bytes, signature_bytes = _verified_latest_release()
    if expected_version and manifest.version != expected_version:
        raise UpdateError("檢查後最新版本已變更，請重新檢查更新")
    if _semver(manifest.version) <= _semver(__version__):
        raise UpdateError("目前沒有比已安裝版本更新的正式版本")

    version_dir = _update_dir(manifest.version)
    version_dir.mkdir(parents=True, exist_ok=True)
    target = _staged_exe(manifest)
    if not _staged_is_valid(manifest):
        _download_asset(assets[manifest.asset], target, manifest)
        _self_test_exe(target)
    (version_dir / MANIFEST_NAME).write_bytes(manifest_bytes)
    (version_dir / SIGNATURE_NAME).write_bytes(signature_bytes)

    capability = update_capability()
    return {
        "current_version": __version__,
        "latest_version": manifest.version,
        "available": True,
        "signature_verified": True,
        "asset_name": manifest.asset,
        "asset_size": manifest.size,
        "downloaded": True,
        "installable": capability["installable"],
        "install_reason": capability["install_reason"],
        "release_url": str(release.get("html_url") or ""),
        "notes": str(release.get("body") or "")[:12000],
    }


_APPLY_SCRIPT = r"""param(
    [int]$PidToWait,
    [string]$CurrentExe,
    [string]$NewExe,
    [string]$BackupExe,
    [string]$LogFile
)
$ErrorActionPreference = 'Stop'
function Write-UpdateLog([string]$Message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogFile -Value "$stamp $Message" -Encoding UTF8
}
try {
    $old = Get-Process -Id $PidToWait -ErrorAction SilentlyContinue
    if ($old) { $old.WaitForExit() }
    Start-Sleep -Milliseconds 500
    Copy-Item -LiteralPath $NewExe -Destination $CurrentExe -Force
    Write-UpdateLog 'new executable installed'
    $new = Start-Process -FilePath $CurrentExe -PassThru
    Start-Sleep -Seconds 10
    if ($new.HasExited -and $new.ExitCode -ne 0) {
        throw "new FireLens exited early with code $($new.ExitCode)"
    }
    Write-UpdateLog 'new FireLens launched successfully; backup retained for rollback'
}
catch {
    Write-UpdateLog "update failed: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath $BackupExe -Destination $CurrentExe -Force
        Start-Process -FilePath $CurrentExe | Out-Null
        Write-UpdateLog 'rollback completed'
    }
    catch {
        Write-UpdateLog "rollback failed: $($_.Exception.Message)"
    }
}
"""


def schedule_install(version: str) -> dict[str, object]:
    capability = update_capability()
    if not capability["installable"]:
        raise UpdateError(str(capability["install_reason"]))
    _semver(version)
    if _semver(version) <= _semver(__version__):
        raise UpdateError("只能安裝比目前版本新的更新")

    version_dir = _update_dir(version)
    manifest_path = version_dir / MANIFEST_NAME
    signature_path = version_dir / SIGNATURE_NAME
    if not manifest_path.is_file() or not signature_path.is_file():
        raise UpdateError("尚未下載並驗證此版本")
    manifest = verify_manifest(manifest_path.read_bytes(), signature_path.read_bytes())
    if manifest.version != version:
        raise UpdateError("本機更新資料版本不一致")
    staged = _staged_exe(manifest)
    if not _staged_is_valid(manifest):
        raise UpdateError("本機更新檔驗證失敗，請重新下載")
    _self_test_exe(staged)

    current_exe = Path(sys.executable).resolve()
    backup = version_dir / f"FireLens-{__version__}-backup.exe"
    try:
        shutil.copy2(current_exe, backup)
    except OSError as exc:
        raise UpdateError(f"無法建立舊版 EXE 備份：{exc}") from exc

    script_path = version_dir / "apply-update.ps1"
    script_path.write_text(_APPLY_SCRIPT, encoding="utf-8-sig")
    log_path = _update_dir() / "update.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    flags = int(getattr(subprocess, "DETACHED_PROCESS", 0)) | int(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-PidToWait",
                str(os.getpid()),
                "-CurrentExe",
                str(current_exe),
                "-NewExe",
                str(staged),
                "-BackupExe",
                str(backup),
                "-LogFile",
                str(log_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(f"無法啟動更新安裝程序：{exc}") from exc
    return {
        "scheduled": True,
        "version": version,
        "backup_path": str(backup),
        "log_path": str(log_path),
    }

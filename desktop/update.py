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
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from backend.app.config import get_app_data_dir
from desktop.update_protocol import (
    TRANSACTION_SCHEMA,
    UpdateProtocolError,
    atomic_write_handshake,
    atomic_write_json,
    read_json,
    sha256_file,
    utc_now,
    validate_handshake,
    validate_transaction_id,
)
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
UPDATER_EXE_NAME = "FireLensUpdater.exe"
UPDATER_PAYLOAD_DIR = "updater_payload"
UPDATER_HASH_NAME = "updater.sha256"
UPDATE_READY_TIMEOUT_SECONDS = 8.0


class UpdateError(RuntimeError):
    pass


UpdateProgressCallback = Callable[[str, int, int | None], None]


def _notify_progress(
    callback: UpdateProgressCallback | None,
    phase: str,
    completed: int = 0,
    total: int | None = None,
) -> None:
    if callback is not None:
        callback(phase, completed, total)


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
    return sha256_file(path)


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


def _download_asset(
    url: str,
    target: Path,
    manifest: ReleaseManifest,
    progress: UpdateProgressCallback | None = None,
) -> None:
    _validate_https_url(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    total = 0
    _notify_progress(progress, "downloading", 0, manifest.size)
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
                _notify_progress(progress, "downloading", total, manifest.size)
        if total != manifest.size:
            raise UpdateError("下載的更新檔大小與 manifest 不一致")
        _notify_progress(progress, "verifying_sha256", total, manifest.size)
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


def download_update(
    expected_version: str | None = None,
    progress: UpdateProgressCallback | None = None,
) -> dict[str, object]:
    _notify_progress(progress, "verifying_signature")
    manifest, assets, release, manifest_bytes, signature_bytes = _verified_latest_release()
    _notify_progress(progress, "verifying_manifest", 0, manifest.size)
    if expected_version and manifest.version != expected_version:
        raise UpdateError("檢查後最新版本已變更，請重新檢查更新")
    if _semver(manifest.version) <= _semver(__version__):
        raise UpdateError("目前沒有比已安裝版本更新的正式版本")

    version_dir = _update_dir(manifest.version)
    version_dir.mkdir(parents=True, exist_ok=True)
    target = _staged_exe(manifest)
    if not _staged_is_valid(manifest):
        _download_asset(assets[manifest.asset], target, manifest, progress)
    else:
        _notify_progress(progress, "verifying_sha256", manifest.size, manifest.size)
    _notify_progress(progress, "self_test", manifest.size, manifest.size)
    _self_test_exe(target)
    (version_dir / MANIFEST_NAME).write_bytes(manifest_bytes)
    (version_dir / SIGNATURE_NAME).write_bytes(signature_bytes)
    _notify_progress(progress, "ready", manifest.size, manifest.size)

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


def _bundle_root() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        raise UpdateError("目前執行環境沒有內嵌 updater payload")
    return Path(bundle).resolve()


def _updater_payload() -> tuple[Path, str]:
    payload_dir = _bundle_root() / UPDATER_PAYLOAD_DIR
    source = payload_dir / UPDATER_EXE_NAME
    hash_file = payload_dir / UPDATER_HASH_NAME
    try:
        expected = hash_file.read_text(encoding="ascii").strip().lower()
    except OSError as exc:
        raise UpdateError(f"無法讀取 updater 固定 SHA-256：{exc}") from exc
    if not _SHA256_RE.fullmatch(expected):
        raise UpdateError("內嵌 updater SHA-256 格式不正確")
    if not source.is_file() or _sha256_file(source) != expected:
        raise UpdateError("內嵌 FireLensUpdater.exe 完整性驗證失敗")
    return source, expected


def _materialize_updater() -> tuple[Path, str]:
    source, expected = _updater_payload()
    installed = Path(sys.executable).resolve().parent / UPDATER_EXE_NAME
    try:
        if installed.is_file() and _sha256_file(installed) == expected:
            return installed, expected
    except OSError:
        pass

    helper_dir = _update_dir() / "helper"
    helper_dir.mkdir(parents=True, exist_ok=True)
    target = helper_dir / f"FireLensUpdater-{expected[:16]}.exe"
    if target.is_file() and _sha256_file(target) == expected:
        return target, expected
    temp = target.with_suffix(".tmp.exe")
    try:
        shutil.copy2(source, temp)
        if _sha256_file(temp) != expected:
            raise UpdateError("解出的 FireLensUpdater.exe SHA-256 不一致")
        os.replace(temp, target)
    except OSError as exc:
        raise UpdateError(f"無法準備獨立更新器：{exc}") from exc
    finally:
        temp.unlink(missing_ok=True)
    if _sha256_file(target) != expected:
        raise UpdateError("獨立更新器落地後完整性驗證失敗")
    return target, expected


def _transaction_dir() -> Path:
    return _update_dir() / "transactions"


def _latest_transaction_pointer() -> Path:
    return _update_dir() / "latest-transaction.json"


def _transaction_state_path(transaction_id: str) -> Path:
    return _transaction_dir() / f"{validate_transaction_id(transaction_id)}.json"


def _write_latest_transaction(transaction_id: str, state_path: Path) -> None:
    atomic_write_json(
        _latest_transaction_pointer(),
        {
            "schema": TRANSACTION_SCHEMA,
            "transaction_id": transaction_id,
            "state_path": str(state_path),
            "updated_at": utc_now(),
        },
    )


def latest_update_transaction() -> dict[str, object] | None:
    pointer_path = _latest_transaction_pointer()
    if not pointer_path.is_file():
        return None
    try:
        pointer = read_json(pointer_path)
        transaction_id = validate_transaction_id(str(pointer.get("transaction_id") or ""))
        state_path = _transaction_state_path(transaction_id)
        state = read_json(state_path)
        if str(state.get("transaction_id") or "") != transaction_id:
            return None
    except (OSError, UpdateProtocolError):
        return None
    keys = (
        "transaction_id",
        "phase",
        "target_version",
        "current_version",
        "created_at",
        "updated_at",
        "completed_at",
        "error",
        "rollback_error",
        "backup_path",
        "log_file",
    )
    return {key: state.get(key) for key in keys}


def mark_update_healthy(transaction_id: str, state_path: str | Path) -> None:
    transaction_id = validate_transaction_id(transaction_id)
    expected_state_path = _transaction_state_path(transaction_id).resolve()
    provided = Path(state_path).resolve()
    if provided != expected_state_path:
        raise UpdateError("更新 HEALTHY 狀態檔路徑不合法")
    try:
        state = read_json(provided)
    except UpdateProtocolError as exc:
        raise UpdateError(str(exc)) from exc
    if str(state.get("transaction_id") or "") != transaction_id:
        raise UpdateError("更新 HEALTHY transaction 不一致")
    if str(state.get("target_version") or "") != __version__:
        raise UpdateError("目前版本與更新 transaction 目標版本不一致")
    current_exe = Path(str(state.get("current_exe") or "")).resolve()
    if current_exe != Path(sys.executable).resolve():
        raise UpdateError("目前 EXE 與更新 transaction 目標路徑不一致")
    healthy_file = Path(str(state.get("healthy_file") or "")).resolve()
    if healthy_file.parent != _transaction_dir().resolve():
        raise UpdateError("更新 HEALTHY 握手路徑不合法")
    atomic_write_handshake(
        healthy_file,
        transaction_id,
        status="healthy",
        version=__version__,
        pid=os.getpid(),
    )


def _create_transaction(
    *,
    manifest: ReleaseManifest,
    staged: Path,
    helper_sha256: str,
) -> tuple[str, Path, dict[str, object]]:
    transaction_id = uuid.uuid4().hex
    transaction_root = _transaction_dir()
    transaction_root.mkdir(parents=True, exist_ok=True)
    state_path = _transaction_state_path(transaction_id)
    ready_file = transaction_root / f"{transaction_id}.ready.json"
    healthy_file = transaction_root / f"{transaction_id}.healthy.json"
    current_exe = Path(sys.executable).resolve()
    backup = _update_dir(manifest.version) / f"FireLens-{__version__}-backup.exe"
    log_path = _update_dir() / "update.log"
    state: dict[str, object] = {
        "schema": TRANSACTION_SCHEMA,
        "transaction_id": transaction_id,
        "phase": "created",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "current_version": __version__,
        "target_version": manifest.version,
        "parent_pid": os.getpid(),
        "current_exe": str(current_exe),
        "staged_exe": str(staged.resolve()),
        "backup_exe": str(backup.resolve()),
        "backup_path": str(backup.resolve()),
        "expected_sha256": manifest.sha256,
        "helper_sha256": helper_sha256,
        "ready_file": str(ready_file.resolve()),
        "healthy_file": str(healthy_file.resolve()),
        "log_file": str(log_path.resolve()),
        "error": None,
    }
    if os.environ.get("FIRELENS_UPDATE_E2E") == "1":
        state.update(
            {
                "parent_timeout_seconds": 15,
                "replace_timeout_seconds": 4,
                "health_timeout_seconds": 12,
            }
        )
    atomic_write_json(state_path, state)
    _write_latest_transaction(transaction_id, state_path)
    return transaction_id, state_path, state


def _launch_updater_and_wait_ready(
    helper: Path,
    transaction_id: str,
    state_path: Path,
    ready_file: Path,
    timeout: float = UPDATE_READY_TIMEOUT_SECONDS,
) -> int:
    if (
        os.environ.get("FIRELENS_UPDATE_E2E") == "1"
        and os.environ.get("FIRELENS_UPDATER_FAULT") == "startup_failure"
    ):
        raise UpdateError("測試注入：獨立更新器無法啟動")
    flags = int(getattr(subprocess, "DETACHED_PROCESS", 0)) | int(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    try:
        process = subprocess.Popen(
            [str(helper), "--transaction", str(state_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(f"無法啟動獨立 FireLensUpdater：{exc}") from exc

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready_file.is_file():
            try:
                ready = validate_handshake(ready_file, transaction_id, "ready")
            except UpdateProtocolError as exc:
                raise UpdateError(f"獨立更新器 ready 握手失敗：{exc}") from exc
            updater_pid = ready.get("updater_pid")
            if not isinstance(updater_pid, int) or updater_pid <= 0 or process.poll() is not None:
                raise UpdateError("獨立更新器 ready 後已失效")
            # PyInstaller one-file runs a bootloader parent plus the Python
            # application child. Popen.pid is the bootloader PID while
            # os.getpid() reported by the helper is the child PID, so equality
            # is intentionally not required here.
            return updater_pid
        exit_code = process.poll()
        if exit_code is not None:
            raise UpdateError(f"獨立更新器尚未 ready 就結束：exit code {exit_code}")
        time.sleep(0.05)
    with suppress(OSError):
        process.terminate()
    raise UpdateError("獨立更新器啟動逾時；FireLens 保持目前版本並繼續執行")


def _schedule_verified_update(manifest: ReleaseManifest, staged: Path) -> dict[str, object]:
    helper, helper_sha256 = _materialize_updater()
    transaction_id, state_path, state = _create_transaction(
        manifest=manifest,
        staged=staged,
        helper_sha256=helper_sha256,
    )
    ready_file = Path(str(state["ready_file"]))
    try:
        updater_pid = _launch_updater_and_wait_ready(
            helper,
            transaction_id,
            state_path,
            ready_file,
        )
    except UpdateError as exc:
        state.update({"phase": "helper_start_failed", "updated_at": utc_now(), "error": str(exc)})
        atomic_write_json(state_path, state)
        raise
    return {
        "scheduled": True,
        "ready": True,
        "version": manifest.version,
        "transaction_id": transaction_id,
        "updater_pid": updater_pid,
        "backup_path": str(state["backup_path"]),
        "log_path": str(state["log_file"]),
        "state_path": str(state_path),
    }


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
    return _schedule_verified_update(manifest, staged)


def schedule_local_update_e2e(staged: Path) -> dict[str, object]:
    if os.environ.get("FIRELENS_UPDATE_E2E") != "1":
        raise UpdateError("本機 updater E2E 入口只允許在建置測試環境使用")
    if os.name != "nt" or not getattr(sys, "frozen", False):
        raise UpdateError("updater E2E 必須由打包後 Windows FireLens.exe 發起")
    staged = staged.resolve()
    if not staged.is_file():
        raise UpdateError("updater E2E 找不到 staged EXE")
    manifest = ReleaseManifest(
        version=__version__,
        asset=staged.name,
        sha256=_sha256_file(staged),
        size=staged.stat().st_size,
    )
    return _schedule_verified_update(manifest, staged)

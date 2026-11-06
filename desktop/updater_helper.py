from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time
from contextlib import suppress
from ctypes import wintypes
from pathlib import Path
from typing import Any

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

DEFAULT_PARENT_TIMEOUT = 90.0
DEFAULT_REPLACE_TIMEOUT = 30.0
DEFAULT_HEALTH_TIMEOUT = 60.0
POLL_INTERVAL = 0.2


class UpdaterError(RuntimeError):
    pass


def _as_path(payload: dict[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UpdaterError(f"更新狀態缺少 {key}")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise UpdaterError(f"更新路徑必須是絕對路徑：{key}")
    return path.resolve()


def _as_positive_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value <= 0:
        raise UpdaterError(f"更新狀態 {key} 不合法")
    return value


def _timeout(payload: dict[str, Any], key: str, default: float) -> float:
    if os.environ.get("FIRELENS_UPDATE_E2E") != "1":
        return default
    value = payload.get(key)
    if isinstance(value, (int, float)) and 0.5 <= float(value) <= default:
        return float(value)
    return default


def _write_log(path: Path, transaction_id: str, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = utc_now()
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{stamp} transaction={transaction_id} {message}\n")
        stream.flush()


def _update_state(state_path: Path, state: dict[str, Any], phase: str, **fields: Any) -> None:
    state.update({"phase": phase, "updated_at": utc_now(), **fields})
    atomic_write_json(state_path, state)


def _wait_for_process_exit(pid: int, timeout: float) -> bool:
    if os.name != "nt":
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return True
            time.sleep(POLL_INTERVAL)
        return False

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    error_invalid_parameter = 87
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == error_invalid_parameter:
            return True
        raise UpdaterError(f"無法監看舊 FireLens PID {pid}：Win32={error}")
    try:
        result = kernel32.WaitForSingleObject(handle, int(timeout * 1000))
        if result == wait_object_0:
            return True
        if result == wait_timeout:
            return False
        raise UpdaterError(f"等待舊 FireLens 結束失敗：Win32={result}")
    finally:
        kernel32.CloseHandle(handle)


def _replace_with_retry(source: Path, target: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(POLL_INTERVAL)
    raise UpdaterError(f"等待 FireLens.exe 解除鎖定逾時：{last_error}")


def _launch(path: Path, args: list[str]) -> subprocess.Popen[bytes]:
    flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return subprocess.Popen(
        [str(path), *args],
        cwd=str(path.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )


def _restore_backup(
    *,
    state_path: Path,
    state: dict[str, Any],
    log_path: Path,
    transaction_id: str,
    current_exe: Path,
    backup_exe: Path,
    original_sha256: str,
    replace_timeout: float,
) -> bool:
    try:
        if (
            os.environ.get("FIRELENS_UPDATE_E2E") == "1"
            and os.environ.get("FIRELENS_UPDATER_FAULT") == "rollback_fail"
        ):
            raise PermissionError("E2E injected rollback failure")
        if not backup_exe.is_file() or sha256_file(backup_exe) != original_sha256:
            raise UpdaterError("舊版備份不存在或 SHA-256 不符")
        rollback_temp = current_exe.with_name(f".{current_exe.name}.{transaction_id}.rollback")
        shutil.copy2(backup_exe, rollback_temp)
        _replace_with_retry(rollback_temp, current_exe, replace_timeout)
        if sha256_file(current_exe) != original_sha256:
            raise UpdaterError("rollback 後 FireLens.exe SHA-256 不符")
        _launch(current_exe, [])
        _write_log(log_path, transaction_id, "rollback completed and old FireLens relaunched")
        _update_state(state_path, state, "rolled_back", error=state.get("error"))
        return True
    except Exception as exc:
        _write_log(log_path, transaction_id, f"rollback failed: {exc}")
        _update_state(
            state_path,
            state,
            "rollback_failed",
            rollback_error=str(exc),
            backup_path=str(backup_exe),
        )
        return False


def run_transaction(state_path: Path) -> int:
    state_path = state_path.resolve()
    state = read_json(state_path)
    if state.get("schema") != TRANSACTION_SCHEMA:
        raise UpdaterError("不支援的更新 transaction 格式")
    transaction_id = validate_transaction_id(str(state.get("transaction_id") or ""))
    parent_pid = _as_positive_int(state, "parent_pid")
    current_exe = _as_path(state, "current_exe")
    staged_exe = _as_path(state, "staged_exe")
    backup_exe = _as_path(state, "backup_exe")
    ready_file = _as_path(state, "ready_file")
    healthy_file = _as_path(state, "healthy_file")
    log_path = _as_path(state, "log_file")
    expected_sha256 = str(state.get("expected_sha256") or "").lower()
    expected_version = str(state.get("target_version") or "")
    if len(expected_sha256) != 64:
        raise UpdaterError("更新 SHA-256 不合法")

    parent_timeout = _timeout(state, "parent_timeout_seconds", DEFAULT_PARENT_TIMEOUT)
    replace_timeout = _timeout(state, "replace_timeout_seconds", DEFAULT_REPLACE_TIMEOUT)
    health_timeout = _timeout(state, "health_timeout_seconds", DEFAULT_HEALTH_TIMEOUT)
    replaced = False
    original_sha256 = ""
    new_process: subprocess.Popen[bytes] | None = None

    _write_log(
        log_path, transaction_id, f"started updater_pid={os.getpid()} parent_pid={parent_pid}"
    )
    _update_state(state_path, state, "started", updater_pid=os.getpid(), error=None)
    atomic_write_handshake(
        ready_file,
        transaction_id,
        status="ready",
        updater_pid=os.getpid(),
    )
    _write_log(log_path, transaction_id, "ready handshake written")
    _update_state(state_path, state, "ready")

    try:
        if not _wait_for_process_exit(parent_pid, parent_timeout):
            raise UpdaterError("等待舊 FireLens 關閉逾時")
        _write_log(log_path, transaction_id, "parent exited")
        _update_state(state_path, state, "parent_exited")

        if (
            os.environ.get("FIRELENS_UPDATE_E2E") == "1"
            and os.environ.get("FIRELENS_UPDATER_FAULT") == "die_after_ready"
        ):
            raise UpdaterError("E2E injected helper failure after ready")

        if not staged_exe.is_file() or sha256_file(staged_exe) != expected_sha256:
            raise UpdaterError("staged EXE SHA-256 驗證失敗")
        if not current_exe.is_file():
            raise UpdaterError("目前 FireLens.exe 不存在")

        original_sha256 = sha256_file(current_exe)
        backup_exe.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_exe, backup_exe)
        if sha256_file(backup_exe) != original_sha256:
            raise UpdaterError("舊版 EXE 備份 SHA-256 驗證失敗")
        _write_log(log_path, transaction_id, f"backup complete sha256={original_sha256}")

        replacement = current_exe.with_name(f".{current_exe.name}.{transaction_id}.new")
        shutil.copy2(staged_exe, replacement)
        if sha256_file(replacement) != expected_sha256:
            replacement.unlink(missing_ok=True)
            raise UpdaterError("替換暫存 EXE SHA-256 驗證失敗")
        if os.environ.get("FIRELENS_UPDATE_E2E") == "1":
            fault = os.environ.get("FIRELENS_UPDATER_FAULT")
            if fault == "lock_timeout":
                raise UpdaterError("E2E injected EXE lock timeout")
            if fault == "replace_fail":
                raise PermissionError("E2E injected replace permission failure")
        _replace_with_retry(replacement, current_exe, replace_timeout)
        replaced = True
        if sha256_file(current_exe) != expected_sha256:
            raise UpdaterError("安裝後 FireLens.exe SHA-256 不符")
        _write_log(log_path, transaction_id, f"replace complete target_hash={expected_sha256}")
        _update_state(state_path, state, "replaced", target_sha256=expected_sha256)

        launch_args = [
            "--update-transaction",
            transaction_id,
            "--update-state",
            str(state_path),
        ]
        if os.environ.get("FIRELENS_UPDATE_E2E") == "1" and os.environ.get(
            "FIRELENS_UPDATER_FAULT"
        ) in {"new_crash", "rollback_fail"}:
            launch_args.append("--update-e2e-crash")
        new_process = _launch(current_exe, launch_args)
        _write_log(log_path, transaction_id, f"new launch pid={new_process.pid}")
        _update_state(state_path, state, "new_launched", new_pid=new_process.pid)

        deadline = time.monotonic() + health_timeout
        while time.monotonic() < deadline:
            if healthy_file.is_file():
                handshake = validate_handshake(healthy_file, transaction_id, "healthy")
                if str(handshake.get("version") or "") != expected_version:
                    raise UpdaterError("新版 HEALTHY 回報版本不一致")
                _write_log(log_path, transaction_id, "healthy handshake received")
                _update_state(
                    state_path,
                    state,
                    "success",
                    completed_at=utc_now(),
                    error=None,
                )
                staged_exe.unlink(missing_ok=True)
                return 0
            exit_code = new_process.poll()
            if exit_code is not None:
                raise UpdaterError(f"新版 FireLens 在 HEALTHY 前退出：exit code {exit_code}")
            time.sleep(POLL_INTERVAL)
        raise UpdaterError("新版 FireLens HEALTHY handshake 逾時")
    except Exception as exc:
        error = str(exc)
        if new_process is not None and new_process.poll() is None:
            try:
                new_process.terminate()
                new_process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                with suppress(OSError):
                    new_process.kill()
        state["error"] = error
        _write_log(log_path, transaction_id, f"update failed: {error}")
        _update_state(state_path, state, "error", error=error)
        if original_sha256 and (replaced or backup_exe.is_file()):
            _restore_backup(
                state_path=state_path,
                state=state,
                log_path=log_path,
                transaction_id=transaction_id,
                current_exe=current_exe,
                backup_exe=backup_exe,
                original_sha256=original_sha256,
                replace_timeout=replace_timeout,
            )
        else:
            try:
                if current_exe.is_file():
                    _launch(current_exe, [])
                    _write_log(
                        log_path, transaction_id, "old FireLens relaunched; replacement not started"
                    )
            except OSError as launch_exc:
                _write_log(log_path, transaction_id, f"old FireLens relaunch failed: {launch_exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="FireLensUpdater")
    parser.add_argument("--transaction", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        return run_transaction(args.transaction)
    except (UpdaterError, UpdateProtocolError, OSError, ValueError):
        # If the transaction itself cannot be read, stderr may be unavailable in
        # windowed mode; returning non-zero lets the parent detect startup failure.
        return 2


if __name__ == "__main__":
    sys.exit(main())

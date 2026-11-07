from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app.admin as admin
import desktop.update as update
import desktop.updater_helper as helper
from backend.app.main import create_app
from desktop.update import UpdateError
from desktop.update_protocol import (
    UpdateProtocolError,
    atomic_write_handshake,
    atomic_write_json,
    validate_handshake,
    validate_transaction_id,
)
from desktop.version import __version__


def test_transaction_id_and_handshake_support_unicode_paths(tmp_path: Path) -> None:
    transaction_id = "a" * 32
    assert validate_transaction_id(transaction_id.upper()) == transaction_id
    with pytest.raises(UpdateProtocolError, match="transaction id"):
        validate_transaction_id("not-a-transaction")

    handshake = tmp_path / "繁中 路徑" / "ready.json"
    atomic_write_handshake(
        handshake,
        transaction_id,
        status="ready",
        updater_pid=1234,
    )
    payload = validate_handshake(handshake, transaction_id, "ready")
    assert payload["updater_pid"] == 1234
    with pytest.raises(UpdateProtocolError, match="transaction"):
        validate_handshake(handshake, "b" * 32, "ready")


def test_mark_update_healthy_validates_transaction_and_current_exe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transaction_id = "c" * 32
    transaction_dir = tmp_path / "updates" / "transactions"
    state_path = transaction_dir / f"{transaction_id}.json"
    healthy = transaction_dir / f"{transaction_id}.healthy.json"
    fake_exe = tmp_path / "安裝 路徑" / "FireLens.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_bytes(b"exe")
    atomic_write_json(
        state_path,
        {
            "schema": 1,
            "transaction_id": transaction_id,
            "target_version": __version__,
            "current_exe": str(fake_exe),
            "healthy_file": str(healthy),
        },
    )
    monkeypatch.setattr(update, "_transaction_dir", lambda: transaction_dir)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    update.mark_update_healthy(transaction_id, state_path)
    payload = validate_handshake(healthy, transaction_id, "healthy")
    assert payload["version"] == __version__

    bad_state = transaction_dir / f"{'d' * 32}.json"
    with pytest.raises(UpdateError, match="狀態檔路徑"):
        update.mark_update_healthy(transaction_id, bad_state)


def test_launch_updater_requires_ready_handshake(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transaction_id = "e" * 32
    state_path = tmp_path / "transaction.json"
    ready_file = tmp_path / "ready.json"
    helper_exe = tmp_path / "FireLensUpdater.exe"
    helper_exe.write_bytes(b"helper")

    class FakeProcess:
        pid = 4321

        def poll(self):
            return None

        def terminate(self) -> None:
            return None

    monkeypatch.setattr(update.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())

    def write_ready() -> None:
        time.sleep(0.03)
        atomic_write_handshake(
            ready_file,
            transaction_id,
            status="ready",
            updater_pid=4321,
        )

    thread = threading.Thread(target=write_ready)
    thread.start()
    try:
        assert (
            update._launch_updater_and_wait_ready(
                helper_exe,
                transaction_id,
                state_path,
                ready_file,
                timeout=0.5,
            )
            == 4321
        )
    finally:
        thread.join()


def test_launch_updater_timeout_never_claims_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeProcess:
        pid = 9876
        terminated = False

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated = True

    process = FakeProcess()
    monkeypatch.setattr(update.subprocess, "Popen", lambda *_args, **_kwargs: process)
    with pytest.raises(UpdateError, match="啟動逾時"):
        update._launch_updater_and_wait_ready(
            tmp_path / "FireLensUpdater.exe",
            "f" * 32,
            tmp_path / "state.json",
            tmp_path / "missing.ready.json",
            timeout=0.05,
        )
    assert process.terminated is True


def test_helper_replace_retry_supports_unicode_and_reports_lock_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder = tmp_path / "繁中 空白 路徑"
    folder.mkdir()
    source = folder / "新版.tmp"
    target = folder / "FireLens.exe"
    source.write_bytes(b"new")
    target.write_bytes(b"old")
    helper._replace_with_retry(source, target, 0.5)
    assert target.read_bytes() == b"new"

    source.write_bytes(b"again")

    def always_locked(_source, _target):
        raise PermissionError("locked")

    monkeypatch.setattr(helper.os, "replace", always_locked)
    with pytest.raises(helper.UpdaterError, match="解除鎖定逾時"):
        helper._replace_with_retry(source, target, 0.01)


def test_helper_rejects_malformed_transaction(tmp_path: Path) -> None:
    state = tmp_path / "bad.json"
    state.write_text(json.dumps({"schema": 999}), encoding="utf-8")
    with pytest.raises(helper.UpdaterError, match="不支援"):
        helper.run_transaction(state)


def test_install_api_does_not_exit_when_updater_start_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        admin,
        "schedule_install",
        lambda _version: (_ for _ in ()).throw(UpdateError("獨立更新器啟動逾時")),
    )

    class ForbiddenTimer:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("updater READY 前不得建立退出 timer")

    monkeypatch.setattr(admin.threading, "Timer", ForbiddenTimer)
    with TestClient(create_app()) as client:
        response = client.post("/api/update/install", json={"version": "9.9.9"})
    assert response.status_code == 400
    assert "啟動逾時" in response.json()["detail"]


def test_install_api_schedules_exit_only_after_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        admin,
        "schedule_install",
        lambda version: {
            "scheduled": True,
            "ready": True,
            "version": version,
            "transaction_id": "1" * 32,
            "updater_pid": 2468,
            "backup_path": "backup",
            "log_path": "log",
            "state_path": "state",
        },
    )
    started: list[float] = []

    class FakeTimer:
        daemon = False

        def __init__(self, interval, _callback):
            self.interval = interval

        def start(self) -> None:
            started.append(self.interval)

    monkeypatch.setattr(admin.threading, "Timer", FakeTimer)
    with TestClient(create_app()) as client:
        response = client.post("/api/update/install", json={"version": "9.9.9"})
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert started == [0.75]


def test_atomic_json_retries_transient_windows_replace_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import desktop.update_protocol as protocol

    target = tmp_path / "state.json"
    protocol.atomic_write_json(target, {"phase": "old"})
    original_replace = protocol.os.replace
    calls = 0

    def intermittent_replace(source, destination) -> None:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise PermissionError(13, "simulated WinError 5 file lock")
        original_replace(source, destination)

    monkeypatch.setattr(protocol, "_is_temporary_windows_lock", lambda exc: True)
    monkeypatch.setattr(protocol.os, "replace", intermittent_replace)
    monkeypatch.setattr(protocol.time, "sleep", lambda seconds: None)
    protocol.atomic_write_json(target, {"phase": "success"})
    assert calls == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"phase": "success"}
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_json_nonretryable_error_keeps_old_and_removes_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import desktop.update_protocol as protocol

    target = tmp_path / "state.json"
    protocol.atomic_write_json(target, {"phase": "old"})
    calls = 0

    def forbidden_replace(source, destination) -> None:
        nonlocal calls
        calls += 1
        raise OSError(22, "invalid target")

    monkeypatch.setattr(protocol.os, "replace", forbidden_replace)
    monkeypatch.setattr(protocol, "_is_temporary_windows_lock", lambda exc: False)
    with pytest.raises(OSError):
        protocol.atomic_write_json(target, {"phase": "bad"})
    assert calls == 1
    assert json.loads(target.read_text(encoding="utf-8")) == {"phase": "old"}
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_json_persistent_lock_fails_without_overwriting_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import desktop.update_protocol as protocol

    target = tmp_path / "state.json"
    protocol.atomic_write_json(target, {"phase": "old"})
    calls = 0

    def always_locked(source, destination) -> None:
        nonlocal calls
        calls += 1
        raise PermissionError(13, "simulated persistent file lock")

    monkeypatch.setattr(protocol.os, "replace", always_locked)
    monkeypatch.setattr(protocol, "_is_temporary_windows_lock", lambda exc: True)
    monkeypatch.setattr(protocol, "REPLACE_RETRY_TIMEOUT", 0.0)
    with pytest.raises(PermissionError):
        protocol.atomic_write_json(target, {"phase": "new"})
    assert calls == 1
    assert json.loads(target.read_text(encoding="utf-8")) == {"phase": "old"}
    assert not list(tmp_path.glob(".*.tmp"))

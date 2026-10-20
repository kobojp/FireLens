from __future__ import annotations

import threading
import time

import pytest

from backend.app.update_jobs import UpdateJobBusy, UpdatePreparationManager
from desktop.update import UpdateError


def _wait_for_terminal(
    manager: UpdatePreparationManager, timeout: float = 2.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = manager.status()
        if state["ready"] is True or state["phase"] in {"error", "installing"}:
            return state
        time.sleep(0.01)
    raise AssertionError("update preparation did not finish")


def test_update_preparation_reports_progress_and_reuses_ready_download() -> None:
    calls = 0

    def downloader(version: str | None, progress) -> dict[str, object]:
        nonlocal calls
        calls += 1
        assert version == "1.6.0"
        progress("verifying_signature", 0, None)
        progress("verifying_manifest", 0, 100)
        progress("downloading", 50, 100)
        progress("verifying_sha256", 100, 100)
        progress("self_test", 100, 100)
        progress("ready", 100, 100)
        return {"latest_version": "1.6.0", "available": True}

    manager = UpdatePreparationManager(downloader)
    manager.start("1.6.0")
    ready = _wait_for_terminal(manager)
    assert ready["phase"] == "ready"
    assert ready["ready"] is True
    assert ready["percent"] == 100
    assert ready["update"] == {"latest_version": "1.6.0", "available": True}

    reused = manager.start("1.6.0")
    assert reused["phase"] == "ready"
    assert calls == 1, "取消最終確認後再次按安裝，不應強迫重新下載"


def test_update_preparation_blocks_concurrent_jobs() -> None:
    entered = threading.Event()
    release = threading.Event()

    def downloader(version: str | None, progress) -> dict[str, object]:
        entered.set()
        release.wait(2)
        progress("ready", 1, 1)
        return {"latest_version": version}

    manager = UpdatePreparationManager(downloader)
    manager.start("1.6.0")
    assert entered.wait(1)
    with pytest.raises(UpdateJobBusy, match="正在進行中"):
        manager.start("1.6.0")
    release.set()
    assert _wait_for_terminal(manager)["phase"] == "ready"


def test_update_preparation_can_retry_after_failure() -> None:
    calls = 0

    def downloader(version: str | None, progress) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            progress("verifying_sha256", 20, 20)
            raise UpdateError("下載的更新檔 SHA-256 驗證失敗")
        progress("ready", 20, 20)
        return {"latest_version": version}

    manager = UpdatePreparationManager(downloader)
    manager.start("1.6.0")
    failed = _wait_for_terminal(manager)
    assert failed["phase"] == "error"
    assert "SHA-256" in str(failed["error"])

    manager.start("1.6.0")
    assert _wait_for_terminal(manager)["phase"] == "ready"
    assert calls == 2


def test_mark_installing_changes_status_without_starting_another_job() -> None:
    manager = UpdatePreparationManager(lambda version, progress: {"latest_version": version})
    manager.mark_installing("1.6.0")
    state = manager.status()
    assert state["phase"] == "installing"
    assert state["version"] == "1.6.0"
    assert state["ready"] is False

from __future__ import annotations

import threading
from collections.abc import Callable
from copy import deepcopy

from desktop.update import UpdateError, UpdateProgressCallback, download_update

UpdateDownloader = Callable[[str | None, UpdateProgressCallback | None], dict[str, object]]

_PHASE_MESSAGES = {
    "idle": "尚未開始更新。",
    "verifying_signature": "正在驗證 Release 與 Ed25519 簽章…",
    "verifying_manifest": "正在核對版本、檔名與檔案大小…",
    "downloading": "正在下載新版 FireLens…",
    "verifying_sha256": "正在核對 SHA-256…",
    "self_test": "正在執行新版 EXE 自我測試…",
    "ready": "更新已完成安全驗證，等待確認重新啟動。",
    "installing": "正在安裝更新並重新啟動 FireLens…",
    "error": "更新準備失敗。",
}


class UpdateJobBusy(UpdateError):
    pass


class UpdatePreparationManager:
    def __init__(self, downloader: UpdateDownloader = download_update) -> None:
        self._downloader = downloader
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._state = self._initial_state()

    @staticmethod
    def _initial_state() -> dict[str, object]:
        return {
            "phase": "idle",
            "version": None,
            "message": _PHASE_MESSAGES["idle"],
            "bytes_downloaded": 0,
            "bytes_total": None,
            "percent": None,
            "error": None,
            "ready": False,
            "running": False,
            "update": None,
        }

    def status(self) -> dict[str, object]:
        with self._lock:
            return deepcopy(self._state)

    def start(self, version: str) -> dict[str, object]:
        version = version.strip()
        if not version:
            raise UpdateError("更新版本不可空白")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise UpdateJobBusy("更新下載與安全驗證正在進行中，請稍候")
            if self._state.get("ready") is True and self._state.get("version") == version:
                return deepcopy(self._state)
            self._state = {
                **self._initial_state(),
                "phase": "verifying_signature",
                "version": version,
                "message": _PHASE_MESSAGES["verifying_signature"],
                "running": True,
            }
            self._thread = threading.Thread(
                target=self._run,
                args=(version,),
                name="FireLensUpdatePrepare",
                daemon=True,
            )
            self._thread.start()
            return deepcopy(self._state)

    def _progress(self, phase: str, completed: int, total: int | None) -> None:
        with self._lock:
            if phase not in _PHASE_MESSAGES:
                phase = "verifying_manifest"
            percent = None
            if total is not None and total > 0:
                percent = min(100, max(0, round(completed / total * 100)))
            self._state.update(
                {
                    "phase": phase,
                    "message": _PHASE_MESSAGES[phase],
                    "bytes_downloaded": max(0, completed),
                    "bytes_total": total,
                    "percent": percent,
                    "error": None,
                    # The worker only becomes installable after download_update()
                    # returns successfully. A final callback can arrive just before
                    # its return value is stored, so do not expose a transient ready
                    # state without the verified update payload.
                    "ready": False,
                    "running": True,
                }
            )

    def _run(self, version: str) -> None:
        try:
            result = self._downloader(version, self._progress)
        except UpdateError as exc:
            self._fail(str(exc))
            return
        except Exception as exc:  # defensive boundary around background worker
            self._fail(f"更新準備發生未預期錯誤：{exc}")
            return
        with self._lock:
            self._state.update(
                {
                    "phase": "ready",
                    "message": _PHASE_MESSAGES["ready"],
                    "error": None,
                    "ready": True,
                    "running": False,
                    "update": result,
                }
            )

    def _fail(self, message: str) -> None:
        with self._lock:
            self._state.update(
                {
                    "phase": "error",
                    "message": _PHASE_MESSAGES["error"],
                    "error": message,
                    "ready": False,
                    "running": False,
                    "update": None,
                }
            )

    def mark_installing(self, version: str) -> None:
        with self._lock:
            self._state.update(
                {
                    "phase": "installing",
                    "version": version,
                    "message": _PHASE_MESSAGES["installing"],
                    "error": None,
                    "ready": False,
                    "running": False,
                }
            )

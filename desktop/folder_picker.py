"""A minimal, explicit Windows folder picker bridge.

A folder is returned only when the user presses Browse. No files are
created, scanned or imported; adding a root remains a separate API call.
"""

from __future__ import annotations

from typing import Any

from desktop.clipboard import ClipboardApi


class DesktopBridge(ClipboardApi):
    def __init__(self) -> None:
        self._window: Any | None = None

    def bind_window(self, window: Any) -> None:
        self._window = window

    def choose_root_folder(self) -> str | None:
        if self._window is None:
            raise RuntimeError("桌面視窗尚未就緒")
        import webview

        selected = self._window.create_file_dialog(webview.FileDialog.FOLDER, allow_multiple=False)
        if not selected:
            return None
        if len(selected) != 1 or not isinstance(selected[0], str):
            raise ValueError("請選擇一個照片根目錄")
        return selected[0]

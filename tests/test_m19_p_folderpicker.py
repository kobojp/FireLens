from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from backend.app.db import connect
from backend.app.settings import SettingsError, get_settings, save_settings
from desktop.folder_picker import DesktopBridge


def test_native_picker_requires_an_explicit_bound_window(monkeypatch):
    api = DesktopBridge()
    with pytest.raises(RuntimeError, match="尚未就緒"):
        api.choose_root_folder()

    folder_type = object()
    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=folder_type))
    )

    class Window:
        selection = (r"H:\\照片\\燈具更換照片",)
        calls = []

        def create_file_dialog(self, kind, **kwargs):
            self.calls.append((kind, kwargs))
            return self.selection

    window = Window()
    api.bind_window(window)
    assert api.choose_root_folder() == window.selection[0]
    assert window.calls == [(folder_type, {"allow_multiple": False})]
    window.selection = None
    assert api.choose_root_folder() is None
    window.selection = ()
    assert api.choose_root_folder() is None
    window.selection = ("a", "b")
    with pytest.raises(ValueError):
        api.choose_root_folder()


def test_new_pref_defaults_collapsed_without_overwriting_legacy(db_path):
    conn = connect(db_path)
    try:
        assert get_settings(conn)["new_item_panel_collapsed"] is True
        save_settings(conn, {"new_item_panel_open": True})
        assert get_settings(conn)["new_item_panel_collapsed"] is True
        save_settings(conn, {"new_item_panel_collapsed": False})
        conn.close()
        conn = connect(db_path)
        assert get_settings(conn)["new_item_panel_collapsed"] is False
        assert get_settings(conn)["new_item_panel_open"] is True
        for bad in ("true", 1, None):
            with pytest.raises(SettingsError):
                save_settings(conn, {"new_item_panel_collapsed": bad})
    finally:
        conn.close()

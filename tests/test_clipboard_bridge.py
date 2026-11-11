"""Desktop clipboard bridge tests use synthetic images only."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from desktop import clipboard


def test_clipboard_bridge_png_payload_does_not_touch_disk(monkeypatch):
    source = Image.new("RGB", (8, 6), "skyblue")
    monkeypatch.setattr(clipboard.ImageGrab, "grabclipboard", lambda: source)
    result = clipboard.ClipboardApi().read_clipboard_image()
    assert result is not None and result["mime"] == "image/png"
    with Image.open(io.BytesIO(base64.b64decode(result["base64"]))) as result_image:
        assert result_image.size == source.size


def test_clipboard_bridge_skips_files_and_empty_clipboard(monkeypatch):
    monkeypatch.setattr(clipboard.ImageGrab, "grabclipboard", lambda: ["C:/private.jpg"])
    assert clipboard.ClipboardApi().read_clipboard_image() is None
    monkeypatch.setattr(clipboard.ImageGrab, "grabclipboard", lambda: None)
    assert clipboard.ClipboardApi().read_clipboard_image() is None


def test_clipboard_bridge_enforces_max_dimensions(monkeypatch):
    monkeypatch.setattr(clipboard, "MAX_CLIPBOARD_PIXELS", 5)
    source = Image.new("RGB", (8, 6))
    with pytest.raises(ValueError, match="尺寸過大"):
        clipboard.clipboard_image_payload(source)

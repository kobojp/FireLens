"""Explicit Windows desktop clipboard bridge for the photo paste button.

Only pywebview exposes this API to the embedded FireLens window. The server
does not offer a clipboard endpoint, and nothing is read until the user clicks.
"""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageGrab

MAX_CLIPBOARD_BYTES = 100 * 1024 * 1024
MAX_CLIPBOARD_PIXELS = 50_000_000


def clipboard_image_payload(image: Image.Image | None) -> dict | None:
    """Encode an in-memory clipboard image; never write a temporary photo."""
    if image is None:
        return None
    if not isinstance(image, Image.Image):
        return None
    if image.width * image.height > MAX_CLIPBOARD_PIXELS:
        raise ValueError("剪貼簿圖片尺寸過大，請改用加入照片")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = buffer.getvalue()
    if not data or len(data) > MAX_CLIPBOARD_BYTES:
        raise ValueError("剪貼簿圖片超過 100 MB，請改用加入照片")
    return {"mime": "image/png", "base64": base64.b64encode(data).decode("ascii")}


class ClipboardApi:
    """pywebview JS API; avoid browser clipboard-read permissions."""

    def read_clipboard_image(self) -> dict | None:
        # Windows clipboard is accessed only from an explicit button click.
        image = ImageGrab.grabclipboard()
        return clipboard_image_payload(image if isinstance(image, Image.Image) else None)

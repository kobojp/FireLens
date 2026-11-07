"""Public Google Drive listing uses mocked network and never needs live credentials."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from backend.app import public_sheets
from backend.app.main import create_app

SHEET_ID = "abcDEFghiJKL12345678901234"


class MockResponse:
    def __init__(self, payload: dict[str, object]):
        self.stream = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.stream.close()

    def read(self, length: int) -> bytes:
        return self.stream.read(length)


def test_unconfigured_public_listing_is_explicit(monkeypatch) -> None:
    monkeypatch.delenv("FIRELENS_DRIVE_API_KEY", raising=False)
    result = public_sheets.list_public_sheets()
    assert result["configured"] is False
    assert result["sheets"] == []
    assert "API Key" in result["message"]


def test_public_drive_listing_filters_and_paginates(monkeypatch) -> None:
    monkeypatch.setenv("FIRELENS_DRIVE_API_KEY", "synthetic-test-key")
    requests = []

    def mocked_open(request, timeout):
        requests.append((request.full_url, timeout))
        parsed = urlparse(request.full_url)
        assert parsed.hostname == "www.googleapis.com"
        args = parse_qs(parsed.query)
        assert args["q"] == [f"'{public_sheets.FOLDER_ID}' in parents and trashed = false"]
        assert args["key"] == ["synthetic-test-key"]
        if "pageToken" not in args:
            return MockResponse(
                {
                    "files": [
                        {
                            "id": SHEET_ID,
                            "name": "2026年 滅火器更換",
                            "mimeType": public_sheets.SHEET_MIME,
                        },
                        {
                            "id": "somefolder123",
                            "name": "folder",
                            "mimeType": "application/vnd.google-apps.folder",
                        },
                        {"id": "../bad", "name": "bad", "mimeType": public_sheets.SHEET_MIME},
                    ],
                    "nextPageToken": "second",
                }
            )
        return MockResponse(
            {
                "files": [
                    {"id": SHEET_ID, "name": "duplicate", "mimeType": public_sheets.SHEET_MIME},
                    {
                        "id": "ZYXWVutsrq987654321",
                        "name": "<script>x</script>",
                        "mimeType": public_sheets.SHEET_MIME,
                    },
                ]
            }
        )

    monkeypatch.setattr(public_sheets.urllib.request, "urlopen", mocked_open)
    result = public_sheets.list_public_sheets()
    assert result["configured"] is True
    assert len(requests) == 2
    assert len(result["sheets"]) == 2
    assert result["sheets"][0]["id"] == SHEET_ID
    assert result["sheets"][0]["url"].startswith("https://docs.google.com/spreadsheets/d/")


def test_public_drive_errors_return_safe_api_response(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FIRELENS_DRIVE_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path / "test-db"))

    def forbidden(_request, timeout):
        raise urllib.error.HTTPError(
            "https://www.googleapis.com/drive/v3/files", 403, "forbidden", None, None
        )

    monkeypatch.setattr(public_sheets.urllib.request, "urlopen", forbidden)
    with TestClient(create_app()) as client:
        result = client.get("/api/public-sheets")
    # Public endpoint was intentionally retired once folder became restricted.
    assert result.status_code == 404
    assert "synthetic-test-key" not in result.text


def test_network_timeout_is_safe(monkeypatch) -> None:
    monkeypatch.setenv("FIRELENS_DRIVE_API_KEY", "synthetic-test-key")

    def timeout(_request, timeout):
        raise TimeoutError("timeout")

    monkeypatch.setattr(public_sheets.urllib.request, "urlopen", timeout)
    try:
        public_sheets.list_public_sheets()
        raise AssertionError("must fail")
    except public_sheets.PublicSheetError as exc:
        assert "網路" in str(exc)

"""Synthetic Google Sheets copy API tests: never touch the user's cloud data."""

from __future__ import annotations

import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from backend.app import private_drive
from backend.app.main import create_app

SHEET_ID = "1abcdefghijkLMNOPQrs234567890"


@pytest.fixture
def client_service(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    service = private_drive.PrivateDriveService()
    service._tokens = {
        "client_id": private_drive.CLIENT_ID,
        "access_token": "synthetic-private-token",
        "refresh_token": "synthetic-refresh",
        "scope": list(private_drive.SCOPES),
        "expires_at": time.time() + 3600,
    }
    requests = []

    def google(url, *, token=None, form=None, json_body=None, method="GET"):
        assert token == "synthetic-private-token"
        assert method == "GET" and json_body is None
        requests.append(url)
        if "/drive/v3/files/" + private_drive.FOLDER_ID in url:
            return {"id": private_drive.FOLDER_ID, "mimeType": "application/vnd.google-apps.folder"}
        if "/drive/v3/files?" in url:
            return {
                "files": [
                    {"id": SHEET_ID, "name": "模擬私人清冊", "mimeType": private_drive.SHEET_MIME}
                ]
            }
        if "/v4/spreadsheets/" in url and "/values/" not in url:
            return {
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 0,
                            "title": "一班",
                            "gridProperties": {"rowCount": 550, "columnCount": 30},
                        }
                    }
                ]
            }
        if "/values/" in url:
            query = urllib.parse.unquote(url)
            if "B1:B5" in query:
                return {"values": [["標題"], ["致-02-08"], [], ["致-02-12"], ["00123"]]}
            if "B201:B400" in query:
                return {"values": [["跨頁設備編號"], [], ["致-03-09"]]}
            return {"values": []}
        raise AssertionError(url)

    monkeypatch.setattr(private_drive, "_request_json", google)
    return service, requests


def test_copy_info_uses_restricted_sheet_metadata(client_service):
    service, requests = client_service
    assert service.copy_info(SHEET_ID, "一班") == {"row_count": 550}
    assert any("/drive/v3/files?" in url for url in requests)
    assert not any("/values/" in url for url in requests)


def test_copy_chunk_preserves_equipment_codes_and_blank_rows(client_service):
    service, requests = client_service
    result = service.copy_chunk(SHEET_ID, "一班", 1, 5, 2, 2)
    assert result["rows"] == [
        ["標題"],
        ["致-02-08"],
        [""],
        ["致-02-12"],
        ["00123"],
    ]
    assert any("B1:B5" in urllib.parse.unquote(url) for url in requests)
    assert not any("valueInputOption" in url for url in requests)


def test_copy_beyond_page_100_is_readonly_and_padded(client_service):
    service, _ = client_service
    result = service.copy_chunk(SHEET_ID, "一班", 201, 400, 2, 2)
    assert len(result["rows"]) == 200
    assert result["rows"][:4] == [["跨頁設備編號"], [""], ["致-03-09"], [""]]
    assert result["rows"][-1] == [""]


@pytest.mark.parametrize(
    "a,b,c,d",
    [
        (0, 3, 1, 1),
        (1, 201, 1, 1),
        (4, 2, 1, 1),
        (1, 1, 0, 1),
        (1, 1, 1, 31),
        (1, 1, 5, 4),
    ],
)
def test_out_of_bounds_cannot_request_google(client_service, a, b, c, d):
    service, requests = client_service
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service.copy_chunk(SHEET_ID, "一班", a, b, c, d)
    assert exc.value.status_code == 400
    assert requests == []


def test_copy_denies_wrong_sheet_and_tab(client_service):
    service, _ = client_service
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service.copy_chunk("1outsidesheet01234567890", "一班", 1, 5, 2, 2)
    assert exc.value.status_code == 403
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service.copy_chunk(SHEET_ID, "未知", 1, 5, 2, 2)
    assert exc.value.status_code == 403


def test_copy_info_needs_google_auth_and_secure_session(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIRELENS_DESKTOP_SECURE", "1")
    with TestClient(create_app()) as client:
        url = f"/api/private-drive/sheets/{SHEET_ID}/copy-info?tab=一班"
        assert client.get(url).status_code == 403
        assert client.get("/api/health").status_code == 200
        assert client.get(url, headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.get(url).status_code == 401
        assert (
            client.get(
                f"/api/private-drive/sheets/{SHEET_ID}/copy-chunk",
                params={
                    "tab": "一班",
                    "start_row": 1,
                    "end_row": 3,
                    "start_column": 2,
                    "end_column": 2,
                },
            ).status_code
            == 401
        )


def test_copy_rejects_malformed_google_matrix(monkeypatch, client_service):
    service, _ = client_service

    def broken(url, *, token=None):
        if "/values/" in url:
            return {"values": [["too", "many", "cells"]]}
        if "/drive/v3/files/" + private_drive.FOLDER_ID in url:
            return {"id": private_drive.FOLDER_ID, "mimeType": "application/vnd.google-apps.folder"}
        if "/drive/v3/files?" in url:
            return {
                "files": [{"id": SHEET_ID, "name": "測試", "mimeType": private_drive.SHEET_MIME}]
            }
        return {"sheets": [{"properties": {"title": "一班", "sheetId": 0}}]}

    monkeypatch.setattr(private_drive, "_request_json", broken)
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service.copy_chunk(SHEET_ID, "一班", 1, 1, 2, 2)
    assert exc.value.status_code == 502

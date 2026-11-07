"""Private Drive OAuth: all network responses synthetic; never touch user Drive."""

from __future__ import annotations

import time
import urllib.parse
import urllib.request

import pytest
from fastapi.testclient import TestClient

from backend.app import private_drive
from backend.app.main import create_app


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    return private_drive.PrivateDriveService()


def test_pkce_state_is_nonempty_and_random():
    first, challenge = private_drive._pkce()
    second, another = private_drive._pkce()
    assert first != second and challenge != another
    assert len(first) >= 43 and len(challenge) == 43


def test_no_account_cannot_read_private_data(service):
    with pytest.raises(private_drive.PrivateDriveError) as error:
        service.sheets()
    assert error.value.status_code == 401


def test_reject_missing_scopes_and_no_tokens(service):
    with pytest.raises(private_drive.PrivateDriveError) as error:
        service._receive_tokens(
            {
                "access_token": "synthetic",
                "refresh_token": "synthetic",
                "scope": private_drive.SCOPES[0],
            }
        )
    assert error.value.status_code == 403
    assert service.status()["authenticated"] is False


def test_login_callback_state_and_authorization_code(monkeypatch, service):
    urls = []
    monkeypatch.setattr(private_drive.webbrowser, "open", lambda url: urls.append(url) or True)

    def fake_google(url, *, token=None, form=None):
        assert url == private_drive.GOOGLE_TOKEN
        assert form and form["code"] == "mocked-code"
        assert len(form["code_verifier"]) >= 43
        return {
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "scope": " ".join(private_drive.SCOPES),
            "expires_in": 3600,
        }

    monkeypatch.setattr(private_drive, "_request_json", fake_google)
    assert service.login()["started"] is True
    parsed = urllib.parse.urlparse(urls[0])
    params = urllib.parse.parse_qs(parsed.query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["client_id"] == [private_drive.CLIENT_ID]
    wrong = params["redirect_uri"][0] + "?state=WRONG&code=mocked-code"
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(wrong, timeout=3)
    assert error.value.code == 400
    valid = (
        params["redirect_uri"][0]
        + "?"
        + urllib.parse.urlencode(
            {
                "state": params["state"][0],
                "code": "mocked-code",
            }
        )
    )
    with urllib.request.urlopen(valid, timeout=3) as response:
        assert b"FireLens" in response.read()
    assert service.status()["authenticated"] is True
    assert service.status()["login_state"] == "success"


def test_token_storage_windows_is_encrypted(monkeypatch, service):
    if private_drive.os.name != "nt":
        pytest.skip("Windows DPAPI storage only")
    service._receive_tokens(
        {
            "access_token": "synthetic-secret-access",
            "refresh_token": "synthetic-secret-refresh",
            "scope": " ".join(private_drive.SCOPES),
        }
    )
    raw = service._token_path.read_bytes()
    assert b"synthetic-secret" not in raw
    another = private_drive.PrivateDriveService()
    assert another.status()["authenticated"] is True
    monkeypatch.setattr(private_drive, "_request_json", lambda *a, **kw: {})
    result = another.logout()
    assert result["logged_out"] is True
    assert not another._token_path.exists()


def test_filtered_drive_list_read_only(monkeypatch, service):
    service._tokens = {
        "client_id": private_drive.CLIENT_ID,
        "access_token": "synthetic-access",
        "refresh_token": "synthetic-refresh",
        "expires_at": time.time() + 3600,
    }
    urls = []
    sid = "1abcdefghijkLMNOPQrs234567890"

    def request(url, *, token=None, form=None):
        assert token == "synthetic-access"
        urls.append(url)
        if "/drive/v3/files/" + private_drive.FOLDER_ID in url:
            return {"id": private_drive.FOLDER_ID, "mimeType": "application/vnd.google-apps.folder"}
        if "/drive/v3/files?" in url:
            return {
                "files": [
                    {"id": sid, "name": "僅授權的私人資料", "mimeType": private_drive.SHEET_MIME},
                    {"id": "others", "name": "non-sheet", "mimeType": "application/pdf"},
                ]
            }
        if "/values/" in url:
            return {"values": [["欄A", "<script>alert(1)</script>"], ["001", "=SUM(1,2)"]]}
        if "/v4/spreadsheets/" in url:
            return {"sheets": [{"properties": {"sheetId": 0, "title": "工作表1"}}]}
        raise AssertionError(url)

    monkeypatch.setattr(private_drive, "_request_json", request)
    assert service.sheets() == [{"id": sid, "name": "僅授權的私人資料"}]
    assert service.sheet_tabs(sid)[0]["title"] == "工作表1"
    result = service.values(sid, "工作表1")
    assert result["rows"][0][1] == "<script>alert(1)</script>"
    assert result["rows"][1][0] == "001"
    with pytest.raises(private_drive.PrivateDriveError):
        service.sheet_tabs("1unauthorized1234567890123")
    with pytest.raises(private_drive.PrivateDriveError):
        service.values(sid, "不存在")
    assert not any("token=" in url for url in urls)


def test_token_refresh_without_secret(monkeypatch, service):
    service._tokens = {
        "client_id": private_drive.CLIENT_ID,
        "access_token": "expired-access",
        "refresh_token": "synthetic-refresh",
        "expires_at": 0,
    }

    def fake_refresh(url, *, token=None, form=None):
        assert url == private_drive.GOOGLE_TOKEN
        assert form["client_id"] == private_drive.CLIENT_ID
        assert "client_secret" not in form
        return {"access_token": "fresh", "expires_in": 3600}

    monkeypatch.setattr(private_drive, "_request_json", fake_refresh)
    assert service._access() == "fresh"


def test_private_routes_require_login(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        assert client.get("/api/private-drive/status").status_code == 200
        assert client.get("/api/private-drive/sheets").status_code == 401
        assert (
            client.get("/api/private-drive/sheets/1abcdefghijkLMNOPQrs234567890/tabs").status_code
            == 401
        )
        assert client.get("/api/public-sheets").status_code == 404


def test_private_drive_get_requires_desktop_session_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIRELENS_DESKTOP_SECURE", "1")
    with TestClient(create_app()) as client:
        assert client.get("/api/private-drive/status").status_code == 403
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/private-drive/status").status_code == 200
        assert (
            client.get(
                "/api/private-drive/status", headers={"Origin": "https://untrusted.example"}
            ).status_code
            == 403
        )
        assert client.get("/api/private-drive/sheets").status_code == 401

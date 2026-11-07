"""Private Drive OAuth: all network responses synthetic; never touch user Drive."""

from __future__ import annotations

import io
import json
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


@pytest.mark.parametrize(
    ("google_code", "expected_text"),
    [
        ("invalid_grant", "授權碼已過期"),
        ("invalid_request", "交換要求格式有誤"),
        ("invalid_client", "用戶端無法識別"),
        ("unauthorized_client", "不允許使用這種登入流程"),
        ("invalid_scope", "授權範圍無效"),
    ],
)
def test_google_oauth_http400_shows_only_safe_error_code(monkeypatch, google_code, expected_text):
    def mocked_open(_request, timeout):
        response = json.dumps(
            {
                "error": google_code,
                "error_description": "DO_NOT_LEAK_CLIENT_TOKEN_CREDENTIALS",
                "authorization_code": "DO_NOT_LEAK_AUTH_CODE",
            }
        ).encode()
        raise urllib.error.HTTPError(
            private_drive.GOOGLE_TOKEN,
            400,
            "error",
            {},
            io.BytesIO(response),
        )

    monkeypatch.setattr(private_drive.urllib.request, "urlopen", mocked_open)
    with pytest.raises(private_drive.PrivateDriveError) as error:
        private_drive._request_json(
            private_drive.GOOGLE_TOKEN,
            form={"client_id": private_drive.CLIENT_ID, "code": "synthetic"},
        )
    assert error.value.status_code == 400
    assert google_code in str(error.value)
    assert expected_text in str(error.value)
    assert "DO_NOT_LEAK" not in str(error.value)


def test_google_oauth_unknown_or_oversized_response_sanitized(monkeypatch):
    for body in (
        b'{"error": "unknown_code", "error_description": "DO_NOT_LEAK"}',
        b"not-json-DO_NOT_LEAK",
        b"A" * 8000 + b"DO_NOT_LEAK",
    ):

        def mocked_open(_request, timeout, response_body=body):
            raise urllib.error.HTTPError(
                private_drive.GOOGLE_TOKEN, 400, "error", {}, io.BytesIO(response_body)
            )

        monkeypatch.setattr(private_drive.urllib.request, "urlopen", mocked_open)
        with pytest.raises(private_drive.PrivateDriveError) as error:
            private_drive._request_json(private_drive.GOOGLE_TOKEN, form={"code": "synthetic"})
        assert "HTTP 400" in str(error.value)
        assert "DO_NOT_LEAK" not in str(error.value)


def test_google_drive_http403_cannot_leak_raw_error(monkeypatch):
    def mocked_open(_request, timeout):
        raise urllib.error.HTTPError(
            "https://www.googleapis.com/drive/v3/files",
            403,
            "denied",
            {},
            io.BytesIO(b'{"error": "DO_NOT_LEAK_PRIVATE_SPREADSHEET_NAME"}'),
        )

    monkeypatch.setattr(private_drive.urllib.request, "urlopen", mocked_open)
    with pytest.raises(private_drive.PrivateDriveError) as error:
        private_drive._request_json(
            "https://www.googleapis.com/drive/v3/files", token="synthetic-access"
        )
    assert error.value.status_code == 403
    assert "資料讀取" in str(error.value)
    assert "DO_NOT_LEAK" not in str(error.value)


def test_google_callback_access_denied_gets_safe_diagnostic(monkeypatch, service):
    urls = []
    monkeypatch.setattr(private_drive.webbrowser, "open", lambda url: urls.append(url) or True)
    service.login()
    parsed = urllib.parse.urlparse(urls[0])
    params = urllib.parse.parse_qs(parsed.query)
    denied = (
        params["redirect_uri"][0]
        + "?"
        + urllib.parse.urlencode(
            {
                "state": params["state"][0],
                "error": "access_denied",
                "error_description": "DO_NOT_LEAK_USER_EMAIL",
            }
        )
    )
    with urllib.request.urlopen(denied, timeout=3) as response:
        body = response.read().decode()
    assert "access_denied" in body
    assert "DO_NOT_LEAK" not in body
    assert "access_denied" in service.status()["error"]
    assert service.status()["authenticated"] is False


def test_desktop_oauth_optional_secret_for_code_exchange(monkeypatch, service):
    from backend.app import private_drive as oauth

    urls = []
    captured_forms = []
    monkeypatch.setenv("FIRELENS_GOOGLE_CLIENT_SECRET", "synthetic-local-secret")
    monkeypatch.setattr(oauth.webbrowser, "open", lambda url: urls.append(url) or True)

    def mock_token(url, *, token=None, form=None):
        assert url == oauth.GOOGLE_TOKEN
        captured_forms.append(form)
        return {
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "scope": " ".join(oauth.SCOPES),
            "expires_in": 3600,
        }

    monkeypatch.setattr(oauth, "_request_json", mock_token)
    assert service.login()["started"] is True
    from urllib.parse import parse_qs, urlencode, urlparse

    params = parse_qs(urlparse(urls[0]).query)
    callback = (
        params["redirect_uri"][0]
        + "?"
        + urlencode(
            {
                "state": params["state"][0],
                "code": "synthetic-code",
            }
        )
    )
    with urllib.request.urlopen(callback, timeout=3) as response:
        assert b"FireLens" in response.read()
    assert service.status()["authenticated"] is True
    assert captured_forms[0]["client_secret"] == "synthetic-local-secret"
    assert service.status().get("client_secret") is None


def test_desktop_oauth_refresh_includes_optional_secret(monkeypatch, service):
    monkeypatch.setenv("FIRELENS_GOOGLE_CLIENT_SECRET", "local-secret-only")
    service._tokens = {
        "client_id": private_drive.CLIENT_ID,
        "access_token": "expired",
        "refresh_token": "synthetic",
        "expires_at": 0,
    }

    def mock_refresh(url, *, token=None, form=None):
        assert url == private_drive.GOOGLE_TOKEN
        assert form["grant_type"] == "refresh_token"
        assert form["client_secret"] == "local-secret-only"
        return {"access_token": "fresh", "expires_in": 3600}

    monkeypatch.setattr(private_drive, "_request_json", mock_refresh)
    assert service._access() == "fresh"


def test_desktop_oauth_secret_not_set_preserves_pkce(monkeypatch, service):
    monkeypatch.delenv("FIRELENS_GOOGLE_CLIENT_SECRET", raising=False)
    assert service._optional_client_secret() == {}
    monkeypatch.setenv("FIRELENS_GOOGLE_CLIENT_SECRET", "bad\nsecret")
    with pytest.raises(private_drive.PrivateDriveError):
        service._optional_client_secret()


def test_safe_missing_client_secret_diagnostic_does_not_leak_description(monkeypatch):
    import io
    import json

    body = json.dumps(
        {
            "error": "invalid_request",
            "error_description": "client_secret is missing. DO_NOT_LEAK",
        }
    ).encode()

    def reject(_request, timeout):
        raise urllib.error.HTTPError(private_drive.GOOGLE_TOKEN, 400, "error", {}, io.BytesIO(body))

    monkeypatch.setattr(private_drive.urllib.request, "urlopen", reject)
    with pytest.raises(private_drive.PrivateDriveError) as e:
        private_drive._request_json(private_drive.GOOGLE_TOKEN, form={"code": "fake"})
    assert "缺少 client_secret" in str(e.value)
    assert "DO_NOT_LEAK" not in str(e.value)


def test_desktop_client_secret_encrypted_settings_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    store = private_drive.DesktopOAuthSecretStore()
    assert store.configured() is False
    if private_drive.os.name != "nt":
        with pytest.raises(private_drive.PrivateDriveError):
            store.save("synthetic-not-real-secret")
        assert not store.path.exists()
        return
    store.save("synthetic-not-real-secret")
    assert store.configured() is True
    assert b"synthetic-not-real-secret" not in store.path.read_bytes()
    reloaded = private_drive.DesktopOAuthSecretStore()
    assert reloaded.get() == "synthetic-not-real-secret"
    reloaded.save("second-synthetic-secret")
    assert reloaded.get() == "second-synthetic-secret"
    assert b"second-synthetic-secret" not in reloaded.path.read_bytes()
    reloaded.clear()
    assert not reloaded.path.exists()
    assert reloaded.get() is None


def test_client_secret_rejects_invalid_values(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    store = private_drive.DesktopOAuthSecretStore()
    for bad in ("", " ", "secret\nnewline", " leading", "x" * 2049):
        with pytest.raises(private_drive.PrivateDriveError):
            store.save(bad)
    assert not store.path.exists()


def test_oauth_settings_api_never_echoes_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        status = client.get("/api/google-oauth-settings")
        assert status.status_code == 200
        assert status.json() == {"client_id": private_drive.CLIENT_ID, "configured": False}
        invalid = client.post("/api/google-oauth-settings", json={"client_secret": "bad\nvalue"})
        assert invalid.status_code == 400
        assert "bad\nvalue" not in invalid.text
        if private_drive.os.name != "nt":
            assert (
                client.post(
                    "/api/google-oauth-settings", json={"client_secret": "synthetic"}
                ).status_code
                == 503
            )
            return
        saved = client.post(
            "/api/google-oauth-settings",
            json={"client_secret": "synthetic-only-for-test"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["configured"] is True
        assert "synthetic-only-for-test" not in saved.text
        assert "synthetic-only-for-test" not in client.get("/api/google-oauth-settings").text
        assert client.delete("/api/google-oauth-settings").json()["configured"] is False


def test_oauth_settings_api_requires_desktop_cookie_for_get(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIRELENS_DESKTOP_SECURE", "1")
    with TestClient(create_app()) as client:
        assert client.get("/api/google-oauth-settings").status_code == 403
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/google-oauth-settings").status_code == 200
        assert (
            client.post(
                "/api/google-oauth-settings",
                json={"client_secret": "synthetic"},
                headers={"Origin": "https://untrusted.example"},
            ).status_code
            == 403
        )


def test_oauth_prefer_encrypted_user_setting_then_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIRELENS_GOOGLE_CLIENT_SECRET", "environment-synthetic")
    drive = private_drive.PrivateDriveService()
    assert drive._optional_client_secret() == {"client_secret": "environment-synthetic"}
    if private_drive.os.name == "nt":
        drive.save_client_secret("local-dpapi-synthetic")
        assert drive._optional_client_secret() == {"client_secret": "local-dpapi-synthetic"}
        drive.clear_client_secret()
    assert drive._optional_client_secret() == {"client_secret": "environment-synthetic"}

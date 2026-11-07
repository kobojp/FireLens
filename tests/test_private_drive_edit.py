"""Private Sheets editing uses synthetic Google responses only."""

import time
import urllib.parse
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import private_drive
from backend.app.main import create_app

SID = "1abcdefghijkLMNOPQrs234567890"


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    svc = private_drive.PrivateDriveService()
    svc._tokens = {
        "client_id": private_drive.CLIENT_ID,
        "access_token": "fake-access",
        "refresh_token": "fake-refresh",
        "expires_at": time.time() + 3600,
        "scope": list(private_drive.SCOPES),
    }
    return svc


@pytest.fixture
def mock_google(monkeypatch):
    events = []
    state = {"actual": "舊值", "write_status": 1, "denied": False}

    def google(url, *, token=None, form=None, json_body=None, method="GET"):
        assert token == "fake-access"
        if "/drive/v3/files/" + private_drive.FOLDER_ID in url:
            return {"id": private_drive.FOLDER_ID, "mimeType": "application/vnd.google-apps.folder"}
        if "/drive/v3/files?" in url:
            return {
                "files": [{"id": SID, "name": "測試試算表", "mimeType": private_drive.SHEET_MIME}]
            }
        if "/v4/spreadsheets/" in url and "/values/" not in url:
            return {"sheets": [{"properties": {"title": "工作表1", "sheetId": 0}}]}
        if "/values/" in url:
            if method == "PUT":
                events.append({"url": url, "body": json_body})
                if state["denied"]:
                    raise private_drive.PrivateDriveError("沒有編輯權限", 403)
                return {"updatedCells": state["write_status"]}
            return {"values": [[state["actual"]]]} if state["actual"] else {}
        raise AssertionError(url)

    monkeypatch.setattr(private_drive, "_request_json", google)
    return state, events


def test_readonly_scope_never_updates(service, mock_google):
    _, events = mock_google
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service.edit_cell(SID, "工作表1", 2, 3, "舊值", "新值")
    assert exc.value.status_code == 403
    assert not events
    assert service.status()["editable"] is False


def test_valid_edit_updates_one_cell_in_raw_mode(service, mock_google):
    _, events = mock_google
    service._tokens["scope"].append(private_drive.EDIT_SCOPE)
    done = service.edit_cell(SID, "工作表1", 2, 3, "舊值", "=HYPERLINK(test)")
    assert done["saved"] is True
    assert done["column"] == 3
    assert len(events) == 1
    assert "valueInputOption=RAW" in events[0]["url"]
    assert urllib.parse.unquote(events[0]["url"]).find("C2") >= 0
    assert events[0]["body"]["values"] == [["=HYPERLINK(test)"]]
    assert service.status()["editable"] is True


def test_external_update_rejected_without_put(service, mock_google):
    state, events = mock_google
    service._tokens["scope"].append(private_drive.EDIT_SCOPE)
    state["actual"] = "別人修改了"
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service.edit_cell(SID, "工作表1", 2, 3, "舊值", "新值")
    assert exc.value.status_code == 409
    assert not events


@pytest.mark.parametrize(
    "sid,tab,row,col",
    [
        ("../invalid", "工作表1", 2, 3),
        (SID, "不在清單", 2, 3),
        (SID, "工作表1", 0, 3),
        (SID, "工作表1", 2, 31),
    ],
)
def test_invalid_cell_rejected(service, mock_google, sid, tab, row, col):
    _, events = mock_google
    service._tokens["scope"].append(private_drive.EDIT_SCOPE)
    with pytest.raises(private_drive.PrivateDriveError):
        service.edit_cell(sid, tab, row, col, "", "X")
    assert not events


def test_google_editor_permission_denied(service, mock_google):
    state, _ = mock_google
    service._tokens["scope"].append(private_drive.EDIT_SCOPE)
    state["denied"] = True
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service.edit_cell(SID, "工作表1", 2, 3, "舊值", "新值")
    assert exc.value.status_code == 403


def test_no_ack_never_claims_saved(service, mock_google):
    state, _ = mock_google
    service._tokens["scope"].append(private_drive.EDIT_SCOPE)
    state["write_status"] = 0
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service.edit_cell(SID, "工作表1", 2, 3, "舊值", "新值")
    assert exc.value.status_code == 502


def test_edit_consent_does_not_invalidate_readonly_until_success(monkeypatch, service):
    urls = []
    monkeypatch.setattr(private_drive.webbrowser, "open", lambda u: urls.append(u) or True)
    service.login(edit=True)
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(urls[0]).query)
    assert private_drive.EDIT_SCOPE in params["scope"][0].split()
    assert set(private_drive.SCOPES) <= set(params["scope"][0].split())
    assert service.status()["authenticated"] is True
    assert service.status()["editable"] is False
    assert params["code_challenge_method"] == ["S256"]
    service._cancel.set()


def test_edit_route_is_blocked_for_unsigned_user(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("FIRELENS_DATA_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        assert (
            client.put(
                f"/api/private-drive/sheets/{SID}/cell",
                json={
                    "tab": "工作表1",
                    "row": 1,
                    "column": 1,
                    "expected": "",
                    "value": "X",
                },
            ).status_code
            == 403
        )
        assert (
            client.put(
                f"/api/private-drive/sheets/{SID}/cell",
                json={
                    "tab": "工作表1",
                    "row": 0,
                    "column": 1,
                    "expected": "",
                    "value": "X",
                },
            ).status_code
            == 422
        )


def test_edit_consent_success_requires_write_scope_and_preserves_old_token_on_failure(
    service,
):
    old = service._tokens["access_token"]
    with pytest.raises(private_drive.PrivateDriveError) as exc:
        service._receive_tokens(
            {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "scope": " ".join(private_drive.SCOPES),
            },
            required_scopes=private_drive.SCOPES + (private_drive.EDIT_SCOPE,),
        )
    assert exc.value.status_code == 403
    assert service._tokens["access_token"] == old
    assert service.status()["editable"] is False

    service._receive_tokens(
        {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "scope": " ".join(private_drive.SCOPES + (private_drive.EDIT_SCOPE,)),
            "expires_in": 3600,
        },
        required_scopes=private_drive.SCOPES + (private_drive.EDIT_SCOPE,),
    )
    assert service.status()["editable"] is True
    assert service._tokens["access_token"] == "new-access"

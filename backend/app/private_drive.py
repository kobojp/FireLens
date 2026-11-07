"""Google OAuth Desktop + restricted-folder, read-only Sheets access.

No Google credentials or sheet contents are logged or embedded in HTML.
Windows tokens are encrypted with current-user DPAPI, outside sync folders.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import suppress
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .config import get_app_data_dir
from .public_sheets import FOLDER_ID, SHEET_MIME

CLIENT_ID = "481719101354-7rc14eo53cdu7q6nrph423v2kv3lglim.apps.googleusercontent.com"
SCOPES = (
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
)
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,160}$")
MAX_API_BYTES = 1_500_000
MAX_SHEETS = 500


class PrivateDriveError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob_bytes(data: bytes) -> tuple[_Blob, object]:
    raw = ctypes.create_string_buffer(data)
    return _Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte))), raw


def _dpapi_transform(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise PrivateDriveError("OAuth 憑證持久儲存僅支援 Windows 使用者加密", 503)
    source, keep_alive = _blob_bytes(data)
    out = _Blob()
    crypt = ctypes.windll.crypt32
    if decrypt:
        ok = crypt.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(out)
        )
    else:
        ok = crypt.CryptProtectData(
            ctypes.byref(source), "FireLens Google OAuth", None, None, None, 0, ctypes.byref(out)
        )
    _ = keep_alive
    if not ok:
        raise PrivateDriveError("無法存取本機加密的 Google 登入資訊，請重新登入", 401)
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def _request_json(
    url: str, *, token: str | None = None, form: dict[str, str] | None = None
) -> dict[str, Any]:
    if not (
        url.startswith("https://oauth2.googleapis.com/")
        or url.startswith("https://www.googleapis.com/drive/v3/")
        or url.startswith("https://sheets.googleapis.com/v4/")
    ):
        raise PrivateDriveError("已拒絕非 Google 官方 API 位址", 400)
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read(MAX_API_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # Do not expose OAuth tokens or private Google response body in errors.
        messages = {
            400: "Google 拒絕此次要求，請重新登入或檢查同意範圍",
            401: "Google 登入已失效，請重新登入",
            403: "此帳號沒有存取權或 OAuth 權限尚未核准",
            404: "找不到授權資料夾或試算表",
            429: "Google API 查詢過於頻繁，請稍後再試",
        }
        raise PrivateDriveError(messages.get(exc.code, "Google API 查詢失敗"), exc.code) from exc
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        raise PrivateDriveError("無法連線 Google，請檢查網路後重試", 503) from exc
    if len(raw) > MAX_API_BYTES:
        raise PrivateDriveError("Google 回傳資料超過讀取上限", 413)
    if not raw and url == GOOGLE_REVOKE:
        return {}
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PrivateDriveError("Google 回傳的資料格式不正確", 502) from exc
    if not isinstance(result, dict):
        raise PrivateDriveError("Google 回傳的資料格式不正確", 502)
    return result


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


class PrivateDriveService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tokens: dict[str, Any] | None = None
        self._login_state = "idle"
        self._login_error = ""
        self._cancel: threading.Event | None = None
        self._server: HTTPServer | None = None
        self._started = 0.0
        self._token_path = get_app_data_dir() / "auth" / "google-oauth.dpapi"

    def _load(self) -> dict[str, Any] | None:
        if self._tokens:
            return self._tokens
        if not self._token_path.exists():
            return None
        try:
            payload = json.loads(_dpapi_transform(self._token_path.read_bytes(), decrypt=True))
            if payload.get("client_id") != CLIENT_ID:
                raise PrivateDriveError("Google OAuth 用戶端設定已變更，請重新登入", 401)
            self._tokens = payload
            return payload
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise PrivateDriveError("本機 Google 登入憑證無法讀取，請登出後重試", 401) from exc

    def _save(self, payload: dict[str, Any]) -> None:
        # Never store plaintext tokens. A failure to protect fails closed.
        if os.name == "nt":
            encrypted = _dpapi_transform(json.dumps(payload).encode("utf-8"), decrypt=False)
            try:
                self._token_path.parent.mkdir(parents=True, exist_ok=True)
                temp = self._token_path.with_name(f".{secrets.token_hex(8)}.tmp")
                try:
                    temp.write_bytes(encrypted)
                    os.replace(temp, self._token_path)
                finally:
                    temp.unlink(missing_ok=True)
            except OSError as exc:
                raise PrivateDriveError("Google 登入憑證無法安全儲存", 503) from exc
        self._tokens = payload

    def status(self) -> dict[str, object]:
        with self._lock:
            try:
                authenticated = bool(self._load())
                error = self._login_error
            except PrivateDriveError as exc:
                authenticated, error = False, str(exc)
            return {
                "authenticated": authenticated,
                "login_state": self._login_state,
                "error": error,
                "folder_id": FOLDER_ID,
                "scopes": list(SCOPES),
            }

    def login(self) -> dict[str, object]:
        with self._lock:
            if self._login_state == "pending":
                raise PrivateDriveError("Google 登入正在進行中，請完成或取消", 409)
            verifier, challenge = _pkce()
            state = secrets.token_urlsafe(32)
            cancelled = threading.Event()
            self._cancel = cancelled
            self._login_state, self._login_error = "pending", ""
            self._started = time.monotonic()
            service = self

            class CallbackHandler(BaseHTTPRequestHandler):
                def log_message(self, *args: object) -> None:
                    pass

                def do_GET(self) -> None:
                    path = urllib.parse.urlsplit(self.path)
                    if path.path != "/oauth/callback":
                        self.send_error(404)
                        return
                    args = urllib.parse.parse_qs(path.query, max_num_fields=8)
                    given_state = args.get("state", [""])[0]
                    if not secrets.compare_digest(given_state, state):
                        self.send_error(400, "Invalid OAuth state")
                        return
                    if cancelled.is_set():
                        self.send_error(410, "OAuth cancelled")
                        return
                    code = args.get("code", [""])[0]
                    error = args.get("error", [""])[0]
                    with service._lock:
                        if service._login_state != "pending":
                            self.send_error(409)
                            return
                        if error or not code:
                            service._login_state = "error"
                            service._login_error = "已取消 Google 授權或未取得授權碼"
                        else:
                            try:
                                tokens = _request_json(
                                    GOOGLE_TOKEN,
                                    form={
                                        "code": code,
                                        "client_id": CLIENT_ID,
                                        "redirect_uri": redirect_uri,
                                        "grant_type": "authorization_code",
                                        "code_verifier": verifier,
                                    },
                                )
                                service._receive_tokens(tokens)
                                service._login_state = "success"
                            except PrivateDriveError as exc:
                                service._login_state = "error"
                                service._login_error = str(exc)
                    message = (
                        "已完成授權，請返回 FireLens。"
                        if service._login_state == "success"
                        else "Google 授權未完成，請返回 FireLens 查看原因。"
                    )
                    body = (
                        "<!doctype html><html lang='zh-Hant'>"
                        "<meta charset='utf-8'><title>FireLens</title>"
                        f"<body><h2>{message}</h2></body></html>"
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            try:
                server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
                server.timeout = 1
            except OSError as exc:
                self._login_state = "error"
                raise PrivateDriveError("無法啟動本機 Google 授權回呼埠", 503) from exc
            self._server = server
            redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth/callback"
            auth_url = (
                GOOGLE_AUTH
                + "?"
                + urllib.parse.urlencode(
                    {
                        "client_id": CLIENT_ID,
                        "redirect_uri": redirect_uri,
                        "response_type": "code",
                        "scope": " ".join(SCOPES),
                        "access_type": "offline",
                        "prompt": "consent",
                        "state": state,
                        "code_challenge": challenge,
                        "code_challenge_method": "S256",
                    }
                )
            )

            def serve() -> None:
                try:
                    while not cancelled.is_set() and time.monotonic() - service._started < 180:
                        server.handle_request()
                        with service._lock:
                            if service._login_state != "pending":
                                break
                    with service._lock:
                        if service._login_state == "pending":
                            service._login_state = "error"
                            service._login_error = "Google 登入逾時，請重新操作"
                finally:
                    server.server_close()

            threading.Thread(target=serve, daemon=True, name="FireLensOAuthCallback").start()
            try:
                if not webbrowser.open(auth_url):
                    raise OSError("no system browser")
            except Exception as exc:
                cancelled.set()
                self._login_state = "error"
                self._login_error = "無法開啟系統瀏覽器"
                raise PrivateDriveError(self._login_error, 503) from exc
            return {"started": True, "message": "已於系統瀏覽器開啟 Google 登入，請完成授權"}

    def _receive_tokens(self, tokens: dict[str, Any]) -> None:
        required = set(SCOPES)
        granted = set(str(tokens.get("scope", "")).split())
        if not required.issubset(granted):
            raise PrivateDriveError("Google 未授予完整唯讀權限，請重新同意授權", 403)
        access = tokens.get("access_token")
        refresh = tokens.get("refresh_token")
        if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
            raise PrivateDriveError("Google 未提供完整登入憑證，請重新登入", 401)
        self._save(
            {
                "client_id": CLIENT_ID,
                "access_token": access,
                "refresh_token": refresh,
                "scope": sorted(granted),
                "expires_at": time.time() + max(0, int(tokens.get("expires_in", 3600))) - 60,
            }
        )

    def _access(self) -> str:
        with self._lock:
            tokens = self._load()
            if not tokens:
                raise PrivateDriveError("請先使用 Google 帳號登入", 401)
            if tokens.get("expires_at", 0) > time.time() and tokens.get("access_token"):
                return str(tokens["access_token"])
            try:
                fresh = _request_json(
                    GOOGLE_TOKEN,
                    form={
                        "grant_type": "refresh_token",
                        "client_id": CLIENT_ID,
                        "refresh_token": str(tokens["refresh_token"]),
                    },
                )
            except PrivateDriveError as exc:
                if exc.status_code in {400, 401}:
                    self._tokens = None
                    self._token_path.unlink(missing_ok=True)
                raise
            if not fresh.get("access_token"):
                raise PrivateDriveError("Google 續期失敗，請重新登入", 401)
            tokens = dict(tokens)
            tokens["access_token"] = fresh["access_token"]
            tokens["expires_at"] = time.time() + max(0, int(fresh.get("expires_in", 3600))) - 60
            self._save(tokens)
            return str(tokens["access_token"])

    def logout(self) -> dict[str, bool]:
        with self._lock:
            if self._cancel:
                self._cancel.set()
            self._login_state = "idle"
            refresh = (self._tokens or {}).get("refresh_token")
            if not refresh:
                with suppress(PrivateDriveError):
                    refresh = (self._load() or {}).get("refresh_token")
            self._tokens = None
            self._token_path.unlink(missing_ok=True)
        revoked = False
        if refresh:
            try:
                _request_json(GOOGLE_REVOKE, form={"token": str(refresh)})
                revoked = True
            except PrivateDriveError:
                pass
        return {"logged_out": True, "remote_revocation_confirmed": revoked}

    def sheets(self) -> list[dict[str, str]]:
        token = self._access()
        # Check folder can be accessed with this principal.
        folder_url = f"https://www.googleapis.com/drive/v3/files/{FOLDER_ID}?fields=id,mimeType"
        folder = _request_json(folder_url, token=token)
        if (
            folder.get("id") != FOLDER_ID
            or folder.get("mimeType") != "application/vnd.google-apps.folder"
        ):
            raise PrivateDriveError("目標資料夾無法存取", 403)
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        next_page = ""
        for _ in range(5):
            params = {
                "q": f"'{FOLDER_ID}' in parents and trashed = false",
                "fields": "nextPageToken,files(id,name,mimeType)",
                "pageSize": "100",
            }
            if next_page:
                params["pageToken"] = next_page
            result = _request_json(
                "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params),
                token=token,
            )
            if not isinstance(result.get("files"), list):
                raise PrivateDriveError("Google 檔案清單格式不正確", 502)
            for row in result["files"]:
                if not isinstance(row, dict) or row.get("mimeType") != SHEET_MIME:
                    continue
                sid = row.get("id")
                if not isinstance(sid, str) or not ID_RE.fullmatch(sid) or sid in seen:
                    continue
                seen.add(sid)
                items.append({"id": sid, "name": str(row.get("name", ""))[:200]})
                if len(items) >= MAX_SHEETS:
                    return items
            next_page = result.get("nextPageToken") or ""
            if not next_page:
                break
            if not isinstance(next_page, str) or len(next_page) > 2048:
                raise PrivateDriveError("Google 分頁回應不正確", 502)
        return items

    def sheet_tabs(self, sheet_id: str) -> list[dict[str, str | int]]:
        if not ID_RE.fullmatch(sheet_id):
            raise PrivateDriveError("無效的試算表編號")
        # Recheck membership and Google account access on every read, no raw-ID bypass.
        if sheet_id not in {item["id"] for item in self.sheets()}:
            raise PrivateDriveError("所選試算表不在已授權資料夾中", 403)
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}?fields=spreadsheetId,sheets(properties(title,sheetId,gridProperties(rowCount,columnCount)))"
        payload = _request_json(url, token=self._access())
        result = []
        for tab in payload.get("sheets", []):
            prop = tab.get("properties", {}) if isinstance(tab, dict) else {}
            title = prop.get("title")
            if isinstance(title, str) and 0 < len(title) <= 200:
                result.append({"id": int(prop.get("sheetId", 0)), "title": title})
        return result[:100]

    def values(self, sheet_id: str, tab_title: str, start_row: int = 1) -> dict[str, Any]:
        if not 1 <= start_row <= 100000:
            raise PrivateDriveError("起始列超出限制")
        tabs = self.sheet_tabs(sheet_id)
        if tab_title not in {str(tab["title"]) for tab in tabs}:
            raise PrivateDriveError("此試算表沒有指定工作表", 404)
        escaped_tab = tab_title.replace("'", "''")
        a1 = f"'{escaped_tab}'!A{start_row}:AD{start_row + 99}"
        range_encoded = urllib.parse.quote(a1, safe="")
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
            f"{range_encoded}?valueRenderOption=FORMATTED_VALUE"
        )
        result = _request_json(url, token=self._access())
        raw = result.get("values", [])
        if not isinstance(raw, list):
            raise PrivateDriveError("試算表內容格式不正確", 502)
        rows = [
            [str(value)[:2000] for value in row[:30]] for row in raw[:100] if isinstance(row, list)
        ]
        return {
            "rows": rows,
            "start_row": start_row,
            "next_row": start_row + 100 if len(rows) >= 100 else None,
        }

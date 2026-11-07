"""Read-only listing of publicly shared Google Sheets without user OAuth."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

FOLDER_ID = "1iEgsrIVmFdwC4sgLjDWOZZSfA9-xNgpU"
FOLDER_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,160}$")
MAX_PAGES = 5
PAGE_SIZE = 100


class PublicSheetError(ValueError):
    pass


def _public_sheet(row: object) -> dict[str, str] | None:
    if not isinstance(row, dict) or row.get("mimeType") != SHEET_MIME:
        return None
    sheet_id = row.get("id")
    name = row.get("name")
    if not isinstance(sheet_id, str) or not ID_PATTERN.fullmatch(sheet_id):
        return None
    if not isinstance(name, str):
        return None
    return {
        "id": sheet_id,
        "name": name[:250],
        "url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
        "embed_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?rm=minimal",
    }


def list_public_sheets() -> dict[str, object]:
    api_key = os.environ.get("FIRELENS_DRIVE_API_KEY", "").strip()
    base = {"folder_url": FOLDER_URL, "folder_id": FOLDER_ID}
    if not api_key:
        return {
            **base,
            "configured": False,
            "sheets": [],
            "message": "尚未設定 Google Drive API Key，無法自動列出試算表；"
            "可使用公開資料夾檢視或貼上試算表網址。",
        }
    if len(api_key) > 512 or any(ord(c) < 32 for c in api_key):
        raise PublicSheetError("Google Drive API Key 格式不正確")
    sheets: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    token: str | None = None
    for _ in range(MAX_PAGES):
        params = {
            "q": f"'{FOLDER_ID}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType)",
            "pageSize": str(PAGE_SIZE),
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "key": api_key,
        }
        if token:
            params["pageToken"] = token
        endpoint = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise PublicSheetError("Google Drive 回傳資料超過大小限制")
                result = json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise PublicSheetError(
                    "Google Drive 無法存取資料夾：請確認 API Key、Drive API 已啟用及公開權限"
                ) from exc
            if exc.code == 429:
                raise PublicSheetError("Google Drive 查詢已達速率限制，請稍後再試") from exc
            if exc.code == 404:
                raise PublicSheetError("找不到公開資料夾，請確認分享權限") from exc
            raise PublicSheetError(f"Google Drive 查詢失敗（HTTP {exc.code}）") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise PublicSheetError("無法連線 Google Drive，請檢查網路後重試") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PublicSheetError("Google Drive 回傳格式不正確") from exc
        if not isinstance(result, dict) or not isinstance(result.get("files"), list):
            raise PublicSheetError("Google Drive 回傳檔案清單格式不正確")
        for row in result["files"]:
            sheet = _public_sheet(row)
            if sheet and sheet["id"] not in seen_ids:
                sheets.append(sheet)
                seen_ids.add(sheet["id"])
        token = result.get("nextPageToken")
        if not token:
            return {**base, "configured": True, "sheets": sheets, "truncated": False}
        if not isinstance(token, str) or len(token) > 2048:
            raise PublicSheetError("Google Drive 分頁資訊不正確")
    return {**base, "configured": True, "sheets": sheets, "truncated": True}

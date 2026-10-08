# FireLens

FireLens 是一套以 Windows 桌面環境為主的消防設備照片管理工具，協助整理滅火器、放置盒與燈具更換照片，並搭配 Excel／文字清冊進行核對、補拍與命名整理。

## 主要功能

- 依「類別 → 年份 → 月份/批次 → 棟別 → 編號」瀏覽照片資料樹
- 快速新增月份、棟別與設備編號資料夾
- 拖放照片並依槽位自動命名
- 滅火器槽位：`編號`、`藥劑`、`完成`
- 放置盒／燈具槽位：`前`、`中`、`後`
- Excel／文字清冊核對與補拍清單
- 髒檔名、近似編號、重複照片與異體字檢查
- 批次改名預覽、執行與還原紀錄
- SQLite 本機索引、縮圖快取與離線工作區
- Windows pywebview / WebView2 桌面介面
- PyInstaller x64 打包

## 技術棧

- Python 3.12
- FastAPI
- SQLite
- Pillow / pillow-heif
- openpyxl
- React + Vite + TypeScript
- pywebview / Microsoft Edge WebView2
- PyInstaller
- `uv`（Python 套件管理）
- `npm`（前端套件管理）

## 開發環境

### Python

```powershell
uv sync --locked
```

### 前端

```powershell
cd frontend
npm ci
```

### 執行桌面版

```powershell
.\run-desktop.ps1
```

### 執行測試

```powershell
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest

cd frontend
npm test -- --run
npm run lint
npm run build
```

## Windows EXE 打包

在 Windows 11 x64 執行：

```powershell
.\packaging\build.ps1
```

建置腳本會依序執行前端測試、TypeScript、Ruff、pytest、Vite build、PyInstaller 與 EXE self-test。

## 資料安全

FireLens 將照片磁碟內容視為真相來源；掃描功能只建立索引，不應修改來源照片。匯入照片採複製方式，批次改名則提供預覽、衝突阻擋與還原紀錄。

本 repository **不包含任何真實現場照片、清冊、資料庫、實際網路磁碟路徑、憑證或私鑰**。請勿將這些內容提交到 Git。

## 發行版

Windows 可執行檔請從 GitHub Releases 下載。Release binary 不直接提交進 Git 歷史。
GitHub Actions 會監聽 `v*` 標籤。建立正式版本前，先確認 `desktop/version.py` 的版本號一致，再推送 Tag：

```powershell
git tag v1.2.0
git push origin v1.2.0
```

工作流程會在 `windows-latest` 上自動執行完整測試與 PyInstaller 打包、執行 `FireLens.exe --self-test`，接著建立 GitHub Release 並上傳：

- `FireLens-<版本>-windows-x64.exe`
- `SHA256SUMS.txt`

如果 Tag 與 `desktop/version.py` 版本不一致，Release 會直接停止，不會發布錯誤版本。

### 安全線上更新

FireLens v1.2.0 起內建 Windows 線上更新器。設定頁可手動檢查 GitHub Releases；有新版時會先下載到 `%LOCALAPPDATA%\\FireLens\\updates`，完成以下驗證後才允許安裝：

- Release 必須包含 `update-manifest.json` 與 `update-manifest.sig`
- manifest 必須通過 FireLens 內建 Ed25519 公鑰驗證
- EXE 檔名、版本、檔案大小與 SHA-256 必須完全符合已簽章 manifest
- 下載完成後先使用獨立暫存資料目錄執行新版 `--self-test`
- 安裝前備份目前 EXE；新版啟動失敗時更新程序會嘗試自動回滾

GitHub Actions 的簽章私鑰只可存放在 repository Actions Secret：

`FIRELENS_UPDATE_PRIVATE_KEY_B64`

私鑰不得提交到 Git。缺少此 Secret 時，Release workflow 會刻意失敗，避免發布 FireLens 無法驗證的未簽章更新。

## License

MIT License，詳見 [LICENSE](LICENSE)。


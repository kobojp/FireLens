# 滅火器燈具照片管理系統 任務文件

狀態：**M0～M16 功能開發完成，待使用者實機驗收**。目前版本 v1.7.0；本版本尚未正式 Release。歷史 v1.6.0 已正式發布至 GitHub Release。歷史 v1.5.0 已由使用者實機測試確認 OK 並正式發布至 GitHub Release。
M14 歷史開發版本：v1.6.0。
M15 歷史開發版本：v1.6.1（PATCH，修正線上更新器實機失敗）。

## 1. 目標

管理滅火器、放置盒、燈具三類更換照片：

1. 讀取並瀏覽照片資料夾樹，選定資料夾後把圖拖進去，自動命名並儲存。
2. 將整理好的照片與清冊（Excel／文字清單）核對，找出漏拍、缺漏與命名問題。
3. 資料在 Google Drive（`H:`），需本機快取；也可使用本機資料夾。

## 2. 已定案決策

| 項目 | 決定 |
|---|---|
| 技術 | Python 3.12、FastAPI、SQLite、Pillow、openpyxl；React＋Vite＋TypeScript；pywebview（WebView2）；PyInstaller x64 |
| 套件管理 | uv（Python）、npm（前端） |
| 形式 | Windows 桌面 exe，不做網頁版 |
| 清冊 | 只有滅火器有（Excel 或貼上文字）；放置盒、燈具無清冊，手動加入 |
| 更換週期 | 3 年，**本專案不做**週期計算 |
| 槽位 | 滅火器：編號、藥劑（別名：有效日期）、完成。放置盒、燈具：前、中、後（後＝完成） |
| 舊檔名 | 以同義詞表對應；批次修正為獨立功能，需預覽與確認 |
| 放置盒舊資料 | `新增N`、`編號`、`完成` 視為「舊制」，只顯示、不判缺漏；新資料用前、中、後 |
| 真相來源 | 磁碟為唯一真相；掃描索引可隨時重建；清冊、別名、改名紀錄、設定受保護 |
| 使用情境 | 單人單機（Drive 共用資料夾不做多人同步）；辦公室電腦（滑鼠、鍵盤為主，拖放優先；觸控不是設計重點） |
| 匯出 | 補拍清單輸出 CSV 與 xlsx |
| 介面 | 與 MatLens 區隔：三欄式（樹／槽位牆／資訊），不是表單彈窗型 |
| 參考專案 | MatLens（功能與流程）、滅火器照片核對（核對邏輯）；只參考，不整份複製 |

已定案：

- 應用名稱：FireLens
- GitHub repo：`kobojp/FireLens`；正式發佈使用 GitHub Actions、Ed25519 簽章 manifest 與 SHA-256 驗證的線上更新流程
- 色彩：安全紅橘＋深灰，含淺色與深色主題

## 3. 資料現況（來源：`H:\...\桃隆消防\滅火器更換照片`）

```text
{滅火器|放置盒|燈具}/2026年/{N月份更換|特例資料夾}/[棟別]/編號資料夾/照片.jpg
```

- 共 1380 張 jpg；滅火器約 427 筆，標準檔名為 `編號`、`藥劑`、`完成`。
- 放置盒檔名混用：`新增1`、`新增-1`、`編號`、`完成`。
- 燈具僅 2 筆，編號如 `D-05-04`、`L-08-01`，棟別層為「立體5樓」。
- 特例資料夾：`新增5P 二氧化碳(含放置盒)`、`5P 二氧化碳滅火器`、`壓力錶壞`。
- 髒檔名：`藥劑..jpg`、`成.jpg`、`‵藥劑.jpg`、`編號 (2).jpg`、純數字、`S__136200215.jpg`。
- `編輯.jpg`（4 筆）判定為「編號」打錯字，由整理工具建議更正，逐筆確認。
- `有效日期.jpg`（2 筆）已確認視為「藥劑」槽位別名。
- 異體字：`致德樓` 與 `致徳樓` 並存。
- 清冊樣本 `數據.xlsx`：499 筆，欄位為區段、設備名稱、型式規格、上次更換日；編號無重複；含非數字樓層（`1X`、`1M`、`RF`）。

棟別別名（M0 已確認）：

| Excel 區段 | 磁碟資料夾 |
|---|---|
| 第一門診／第二門診 | 一門診／二門診 |
| 致德樓 | 致德樓、致徳樓 |
| 單身宿舍大樓身障全棟含洗衣輔助 | 身障中心 |
| 區段含樓層（如 `動力中心1F`） | 棟別資料夾不含樓層 |

## 4. Python 與 uv 規則（必須遵守）

- Python 一律使用 uv：不得用全域 Python、`pip install` 或手動建立其他 venv。
- 版本以 `.python-version` 與 `pyproject.toml` 為準。
- 安裝依賴：`uv sync --locked`；新增依賴用 `uv add`，並同步提交 `pyproject.toml` 與 `uv.lock`。
- 執行指令：`uv run --locked ...`（pytest、ruff、uvicorn、桌面入口、打包腳本皆同）。
- 啟動腳本（`run.ps1`、`run-desktop.ps1`）與打包腳本也必須透過 uv 呼叫。
- 臨時檢視資料（如讀 Excel）用 `uvx --with <套件>`，不污染專案環境。

## 5. 不可違反的安全規則

- 匯入照片一律複製，不修改來源。
- 掃描只讀，不改名、不搬移、不刪除。
- 批次改名是唯一會動磁碟的功能：預覽、逐筆勾選、寫入還原紀錄、不覆蓋既有檔案，不提供刪除。
- 資料庫分兩類：「索引表」（照片、縮圖、掃描結果）可隨時重建；「使用者資料表」（清冊、別名、改名紀錄、設定）不得刪除或重建，除非使用者明確要求並確認備份。
- 開發與測試期間對 `H:` 真實資料一律只讀；寫入測試只在暫存或合成資料夾進行，真實照片不提交 Git。
- 寫入 Drive 採原子寫入：先寫暫存檔，成功後改名；寫完核對 SHA-256 才算完成，失敗要顯示並可重試。
- 每次匯入與改名寫入稽核紀錄（時間、來源、目標、雜湊），作為還原依據。
- Google Drive 串流佔位檔不讀取內容，標示「雲端未下載」。
- 辨識被改名的照片以 SHA-256 為準；多個候選時略過並回報，不猜測。
- Windows 正式安裝版資料庫位於 `{安裝路徑}\data\firelens.sqlite3`；預設安裝在 `%LOCALAPPDATA%\Programs\FireLens`。舊版 `%LOCALAPPDATA%\FireLens\firelens.sqlite3` 首次啟動時安全複製搬遷並保留原檔；schema 變更仍採增量、可重複執行。
- 內部服務僅綁定 loopback 隨機埠，保留 session cookie、Host、Origin 檢查。
- 不提交現場照片、案件資料、機器路徑、憑證或私鑰。

## 6. 資料模型（SQLite）

- `category`：類別、槽位定義（必拍／至少 N 張）、編號 regex、同義詞表。
- `root`：資料根目錄（Drive、本機）、是否雲端串流。
- `item`：編號資料夾（類別、年、月份、棟別、編號、路徑）。
- `photo`：檔案、槽位、大小、SHA-256、縮圖路徑、雲端未下載旗標。
- `ledger`／`ledger_row`：清冊版本與列。
- `alias_map`：棟別別名。
- `rename_log`：批次改名還原紀錄。
- `audit_log`：匯入與改名的稽核紀錄。
- `reshoot_mark`：核對頁「已補拍」軟標記（受保護，不由掃描重建）。
- `setting`：角色順序、快取、介面偏好。

可重建：`item`、`photo`。受保護：`ledger`、`ledger_row`、`alias_map`、`rename_log`、`audit_log`、`reshoot_mark`、`setting`、`category`。

## 6.1 自動命名規格

- 滅火器檔名：`編號.jpg`、`藥劑.jpg`、`完成.jpg`；放置盒、燈具：`前.jpg`、`中.jpg`、`後.jpg`。
- 副檔名統一小寫；HEIC 匯入時轉 JPG（保留原檔不動，轉換結果寫入目標資料夾）。
- 依 EXIF 方向校正，不改變原圖畫質。
- 撞名時不覆蓋，改提示使用者選擇「加序號」或「取消」。

## 7. 頁面

1. **瀏覽**：左樹（類別→年→月份→棟別→編號，節點顯示完成度）；中間槽位牆（拖入即自動命名複製、換圖、放大、縮放）；右側資訊（缺漏、疑似錯字、重複）。
2. **新增編號資料夾**：選類別、月份、棟別，輸入編號，依類別產生槽位。
3. **核對**：清冊管理（Excel／貼上、版本、別名對照）、結果表（可篩棟別、狀態、類別）、完成率與棟別進度、補拍清單（複製、CSV／Excel、列印、標記已補拍）。
4. **整理工具**：髒檔名清單（逐筆確認）、重複照片、重複與近似編號、異體字、批次改名與還原。
5. **設定**：根目錄、快取、同義詞表、角色順序。

## 8. 核對狀態

完整、缺某張（指明缺哪張）、無資料夾、空資料夾、0 byte、雲端未下載、命名不合規（附建議）、多餘資料夾（不在清冊）、編號重複、近似編號（如 `中-01-13` 與 `中-01-130`）。
放置盒與燈具無清冊，只檢查槽位是否齊全；放置盒舊制（`新增N`）只顯示、不判缺漏。

核對範圍：預設跨所有月份搜尋，結果標示「所在月份」；也可限定單一月份。特例資料夾（`5P 二氧化碳`、`壓力錶壞`、`新增5P 二氧化碳(含放置盒)`）不在清冊內，列為「特例」，不得報成「多餘資料夾」。

## 9. 專案結構與非功能需求

```text
滅火器燈具照片管理系統/
├─ backend/app/       FastAPI、SQLite、核對、掃描與儲存
├─ frontend/src/      React 介面
├─ desktop/           桌面入口、單一實例、版本（version.py 為唯一來源）
├─ packaging/         EXE／ZIP 建置
├─ tests/             後端測試（用合成資料夾）
├─ docs/              驗證紀錄
├─ AGENTS.md          專案規則（M1 建立）
└─ TASKS.md           本文件
```

- 效能：要能撐到數萬張；掃描增量且可取消；縮圖背景產生；清單用虛擬捲動。
- 備份：清冊、別名表、設定可匯出與匯入；資料庫更新前以 SQLite backup 快照。
- 日誌：寫入 `%LOCALAPPDATA%\<應用名>\logs\`；錯誤訊息使用繁體中文。
- 操作：鍵盤、滑鼠、觸控、拖放皆可用；互動元件提供 accessible name。
- 完成程式修改後，依全域 AGENTS.md 重建 graphify 圖。

## 10. 里程碑與任務

### M0 唯讀盤點（先做，不動任何資料）
- [x] 建立 `AGENTS.md`（沿用 MatLens 規則，加入 uv 與 Drive 安全規則）
- [x] 唯讀盤點報告：髒檔名、異體字、缺槽位數量、別名草稿
- [x] 使用者確認別名表與髒檔名建議（2026-10-05：項目 1～6 採建議；燈具舊制→前中後對應延後決定，不阻擋 M1）
- 驗收：報告與人工抽查一致；`H:` 資料無任何變動。

### M1 骨架與掃描
- [x] uv、npm 專案架構、lint、測試設定
- [x] SQLite 初始化與增量 schema
- [x] 根目錄管理與唯讀掃描（Drive、本機）
- [x] 樹狀瀏覽 API 與前端樹
- 驗收：能列出三類別所有層級；掃描不改任何檔案；重啟後資料仍在。

### M2 槽位與匯入
- [x] 類別與槽位定義、同義詞表
- [x] 槽位牆、拖入自動命名並複製
- [x] 預覽縮放、換圖、新增編號資料夾
- 驗收：來源檔案不變；命名符合規則；重複檔名不覆蓋。

### M3 核對
- [x] Excel 與貼上文字解析，編號 regex 放寬（`1X`、`1M`、`RF`）
- [x] 棟別別名對照（自動草稿加手動修正）
- [x] 狀態判定、完成率、補拍清單、匯出
- 驗收：以 `數據.xlsx` 與實際資料夾核對，結果與人工抽查一致。

### M4 整理工具
- [x] 髒檔名偵測與建議，逐筆確認
- [x] SHA-256 重複偵測、近似編號、異體字
- [x] 批次改名與還原
- 驗收：預覽與實際結果一致；還原可回到原狀。

### M5 快取與離線
- [x] Drive 索引快取、縮圖快取
- [x] 雲端未下載偵測（Windows 檔案屬性判定，不開啟／不強制下載佔位檔）
- [x] 離線工作區與重新連線同步
- 驗收：合成 Drive 斷線後仍可瀏覽索引與縮圖；離線匯入寫入本機 SHA-256 工作區，重新連線後安全同步；真實 1,314 張照片建立縮圖快取且來源指紋不變。

### M6 打包與發佈
- [x] PyInstaller 打包設定、Windows 安裝腳本、pywebview 桌面入口、單一實例
- [x] 線上更新：GitHub Releases 為正式來源；內建 Ed25519 公鑰驗證 `update-manifest.json`／`update-manifest.sig`，並核對版本、檔名、大小與 SHA-256
- [x] GitHub Actions 使用 `FIRELENS_UPDATE_PRIVATE_KEY_B64` Secret 簽章正式 Release；私鑰不提交 Git、程式與使用者端只保存公鑰
- [x] 更新下載後執行 EXE self-test；安裝前再次驗證簽章與 SHA-256，失敗時保留舊版並支援回滾
- [x] 打包後 self-test 與隔離 v4→v5 升級測試
- 驗收：Windows x64 `build.ps1` 建置與 EXE self-test 已通過；GitHub Actions `v1.2.0` Release 建置、簽章、上傳與建立 Release 全部成功；正式線上 manifest 已由 FireLens 內建公鑰驗證通過。

### M7 設定、備份與硬化
- [x] 設定頁：主題、縮圖品質、槽位顯示順序、根目錄顯示/雲端標記、檔名同義詞
- [x] 受保護資料 ZIP 備份與安全合併還原；還原前自動 SQLite snapshot，照片與可重建索引不納入
- [x] RotatingFileHandler 應用日誌、app info、單一版本來源同步
- [x] 大型資料樹搜尋：`useDeferredValue` 延後查詢＋分支裁切，降低搜尋時渲染量
- 驗收：設定重啟可保存；備份 SHA-256/路徑穿越防護與還原測試通過；Chrome 設定/搜尋 smoke 無 SEVERE 錯誤；真實照片與 `數據.xlsx` 指紋不變。

### M8 自動掃描與增量掃描（2026-10-15 完成）
背景：多台電腦共用同一個 Drive 資料夾時（A 電腦新增照片，B 電腦開啟軟體），B 的本機 SQLite 索引仍是舊資料，目前須手動按「掃描」。現行 `scan_root` 為全量重掃（先刪 `item` 再重建），與「掃描增量」規格不符。

需求：
- 啟動後在背景自動掃描目前選定的根目錄；UI 先顯示既有索引，掃描完成後自動刷新樹與槽位牆，並顯示「掃描中…」狀態。
- 自動掃描與手動掃描都可取消；掃描期間不阻擋瀏覽。
- 增量掃描：比對資料夾與檔案的 mtime／大小，只更新有變動的 `item`、`photo`；已刪除的項目與照片要移除；不變動的項目保留（含已算好的 SHA-256 與縮圖快取關聯）。
- 設定頁新增：「啟動時自動掃描」開關（預設開）、「距上次掃描超過 N 分鐘才自動掃描」（預設 5 分鐘）。手動按鈕不受門檻限制。
- 自動掃描與手動掃描一律唯讀；Drive 離線或根目錄不存在時，顯示繁體中文提示並保留舊索引，不清空資料。
- 雲端串流佔位檔維持標「雲端未下載」，不讀取內容、不強制下載。
- 同一根目錄同時只允許一個掃描；重複觸發時略過或回報「掃描進行中」。
- 只動可重建的 `item`、`photo`；不得觸碰受保護資料表。

任務：
- [x] 後端：掃描鎖與取消機制（同一根目錄單一掃描、可中止）
- [x] 後端：增量掃描（以路徑＋mtime＋大小比對，新增／更新／移除），保留既有 `sha256`
- [x] 後端：離線或根目錄不存在時不清空索引，回傳明確錯誤
- [x] 設定：新增 `auto_scan_on_start`、`auto_scan_min_interval_minutes`，增量 migration 並先做 SQLite 備份
- [x] 前端：啟動後依設定與 `last_scan_at` 門檻觸發背景掃描，掃描中狀態與取消按鈕，完成後刷新樹
- [x] 設定頁：自動掃描開關與間隔
- [x] 掃描摘要顯示新增／更新／移除數量
- 驗收：僅用合成資料測試；已驗證外部新增／刪除／改名可由增量掃描反映，未變動 `item`／`photo` 保留 id、SHA-256 與縮圖關聯；Drive/根目錄離線時舊索引不清空；同根目錄重複掃描會阻擋且掃描可取消；自動掃描 5 分鐘門檻有前端測試。SQLite v5→v6 migration 已驗證先建立 `.backup-v5` 且保留受保護設定資料。Ruff 全過、pytest 58 passed、Vitest 26 passed、TypeScript 與 Vite build 通過；Windows x64 EXE 重打包與 self-test 通過。

### M9 新增編號資料夾區塊預設展開（2026-10-15 完成）
背景：頂部「＋ 新增編號資料夾」表單（`App.tsx` 的 `showNewItem`，預設 `false`）預設收合。使用者的主要動作就是新增照片，卻不知道要先按「＋ 新增編號資料夾」才能建立編號資料夾，入口不明顯。

需求：
- 表單預設自動展開（有選定根目錄時），使用者開啟軟體即可看到類別、年份、月份／批次、棟別、編號與「建立資料夾」。
- 使用者按一次「新增編號資料夾」按鈕可收合隱藏；再按一次展開。
- 收合時要有提示，讓使用者知道這裡可新增資料夾，例如按鈕文字改為「＋ 新增編號資料夾（點此展開）」或旁邊顯示簡短說明；展開時按鈕顯示「收合」。提示文字使用繁體中文。
- 展開／收合狀態記住（存入應用設定或本機偏好），重啟後維持使用者上次的選擇；從未操作過則預設展開。
- 未選定根目錄時維持停用，並提示「請先選擇根目錄」。
- 按鈕需有 accessible name 與 `aria-expanded`，可用鍵盤操作。
- 不改變既有建立資料夾的行為、驗證與「記住上次類別／年份／月份／棟別」邏輯。

任務：
- [x] `showNewItem` 預設改為展開，並依儲存的偏好初始化
- [x] 收合按鈕文字與提示、`aria-expanded`、`aria-controls`
- [x] 展開狀態持久化（沿用 `setting`，增量欄位，不動受保護資料表結構）
- [x] 未選根目錄時的停用提示
- [x] 前端測試：預設展開、可收合、偏好重啟後保留
- 驗收：全新設定預設展開、收合偏好持久化與無根目錄提示均有 Vitest/後端設定持久化測試；既有快速建立選項記憶流程維持。Windows EXE build／self-test 已完成；Ruff、pytest 58 passed、Vitest 26 passed、TypeScript／frontend build 全部通過。

### M10 清冊管理（2026-10-16 完成）
背景：目前「清冊核對」的文字貼上／Excel 匯入會解析後寫入 SQLite 的 `ledger`、`ledger_row`，但文字來源只留下解析後資料與 SHA-256，無法重新打開查看當初完整貼上的原始內容；清冊也缺乏完整的管理入口。

需求：
- 將清冊從「一次性匯入」提升為可持續管理的資料：每次文字貼上或 Excel 匯入都建立一份可識別的清冊紀錄。
- 文字貼上來源必須完整保存原始貼上文字，之後可重新開啟查看；解析後的 `ledger_row` 繼續作為核對依據。
- 清冊列表顯示：名稱、來源類型（文字／Excel）、匯入時間、筆數；例如「2026/10 滅火器清冊 · 文字貼上 · 325 筆」。
- 清冊詳細頁提供「解析資料」與「原始內容」兩種檢視；文字來源可看到完整原始貼上內容，Excel 來源至少保留原始檔名、SHA-256 與解析後資料。
- 可重新命名既有清冊，不重新匯入、不影響 `ledger_row` 與核對結果。
- 可刪除舊清冊，但必須二次確認並清楚提示影響；只刪除該清冊及其關聯 `ledger_row`／補拍標記等資料，不得影響照片、根目錄或其他清冊。
- 核對畫面可直接選擇已保存的清冊，不需要每次重新貼上或重新上傳。
- 保留既有清冊資料與相容性；只能以增量 migration 擴充 `ledger`，不得刪除或重建 `ledger`／`ledger_row` 資料表。

任務：
- [x] SQLite：以增量 migration 擴充 `ledger`，加入文字原始內容與來源檔名等必要欄位；migration 前建立資料庫備份
- [x] 後端：清冊詳細內容 API，可讀取清冊 metadata、解析列與原始文字
- [x] 後端：清冊重新命名 API，保留原有 `ledger_id` 與解析資料
- [x] 後端：安全刪除單一清冊及關聯資料，二次確認由前端負責；不得動照片與其他清冊
- [x] 前端：新增「清冊管理」列表，顯示名稱、來源、匯入時間、筆數
- [x] 前端：清冊詳細頁可切換「解析資料／原始內容」
- [x] 前端：支援重新命名與刪除確認
- [x] 核對流程：直接選擇已保存清冊進行核對，保留既有貼上／Excel 匯入入口
- [x] 測試：既有舊版清冊 migration 後仍可使用；文字原始內容可完整重開；重新命名不改 rows；刪除只影響指定清冊
- 驗收：真實 SQLite 已驗證 v6→v7 migration 先建立 `.backup-v6`；文字清冊可保存完整原文、重啟後重開、改名保留 `ledger_id`／rows，刪除只影響指定清冊；Excel 保存來源檔名、SHA-256 與解析資料。1440×900 Chrome DevTools 合成資料 E2E 已實際進入「清冊管理」、開啟清冊並切換「原始內容」，確認原始 `中-01-80` 列可讀取。

### M11 既有照片拖曳歸槽／重新命名（2026-10-16 完成）
背景：未使用 FireLens 整理照片時，現場既有照片可能保留相機流水號或命名錯誤，例如設備資料夾內存在 `46459.jpg`，FireLens 只能把它列為「未對應／舊制照片」，使用者無法直接將它整理到正確槽位。

需求：
- 「未對應／舊制照片」可直接拖曳到上方正確槽位；例如將 `46459.jpg` 拖到「完成」，預覽確認後把原檔在同一設備資料夾內安全重新命名為 `完成.jpg`。
- 拖曳歸槽只做既有檔案的同資料夾 rename，不重新編碼、不複製影像內容、不改畫質。
- 照片提供「重新命名」操作，可手動修改檔名；並提供「設為編號／設為藥劑／設為完成」快速操作。
- 手動檔名只允許安全 basename，不得含路徑分隔符、`..`、Windows 禁用字元或改到設備資料夾外；副檔名預設維持原格式。
- 若目標檔名已存在，禁止直接覆蓋；必須顯示明確衝突提示並讓使用者取消或使用既有安全換圖／整理流程，不得靜默取代原照片。
- 每次歸槽／重新命名必須先顯示「原檔名 → 新檔名」預覽，成功後立即刷新槽位牆與未對應區。
- 所有 rename 寫入 `rename_log` 與 `audit_log`，並提供可復原能力；復原前再次檢查 SHA-256／路徑衝突，不能猜測或覆蓋。
- Drive 離線、雲端未下載或掃描進行中時，不允許直接 rename，顯示繁體中文原因。

任務：
- [x] 後端：既有照片 rename 預覽與執行 API，限制只能在同一設備資料夾內安全改名
- [x] 後端：目標檔名衝突檢查、SHA-256／路徑驗證、`rename_log`／`audit_log` 紀錄
- [x] 後端：既有照片 rename 復原流程與安全檢查
- [x] 前端：未對應照片可拖到槽位，拖放前後有明確視覺狀態與確認預覽
- [x] 前端：照片新增「重新命名」與「設為編號／藥劑／完成」快速操作
- [x] 前端：衝突、Drive 離線、雲端未下載、掃描中的阻擋提示
- [x] 完成 rename 後局部刷新 item／槽位牆，不要求全量重掃
- [x] 測試：正常歸槽、手動改名、目標撞名、非法檔名、復原、SHA 不符、Drive 離線等案例；只使用合成／副本資料
- 驗收：合成設備資料夾已驗證 `46459.jpg → 完成.jpg`，磁碟內容 SHA-256 不變且原 photo id 直接更新到「完成」槽位；`rename_log`／`audit_log` 有紀錄並可復原。撞名、非法路徑／Windows 禁用名稱、變更副檔名、預覽後 SHA 改變、雲端未下載、根目錄離線與掃描中均會阻擋。1440×900 Chrome DevTools 合成資料 E2E 已實際完成「設為完成 → 預覽 `46459.jpg → 完成.jpg` → 確認改名 → 復原」，且頁面水平寬度 `scrollWidth=clientWidth=1407`。

### M12 Windows 安裝精靈與資料庫安裝路徑整合（2026-10-20 完成）
背景：目前只有單一 `FireLens.exe` 與 PowerShell 複製式安裝腳本，缺少一般使用者熟悉的安裝精靈；資料庫則位於 `%LOCALAPPDATA%\FireLens`，使用者希望正式安裝後資料庫跟安裝路徑放在一起。

需求：
- 新增 Windows 安裝精靈，可選安裝位置、建立開始功能表捷徑，桌面捷徑為可選，安裝完成可直接啟動 FireLens。
- 預設採每使用者安裝到 `%LOCALAPPDATA%\Programs\FireLens`，不要求系統管理員權限；正式資料庫放在 `{app}\data\firelens.sqlite3`。
- 使用者自訂安裝位置時，資料庫仍跟隨該安裝目錄的 `data` 子資料夾；更新 FireLens EXE 不得覆蓋或刪除資料庫。
- 歷史 v1.4.0 單一 EXE 沒有安裝精靈標記；其內建 updater 仍可直接更新 raw EXE 到 v1.5.0，但更新後不得把舊 EXE 所在資料夾誤認為正式安裝位置。只有 Inno Setup 建立 `.firelens-installed` 標記後才啟用 `{app}\data` DB；未正式安裝前繼續使用舊 LocalAppData DB。
- v1.4.0 舊版若在 `%LOCALAPPDATA%\FireLens\firelens.sqlite3` 有既有資料，v1.5.0 首次啟動且新位置尚無 DB 時，自動以 SQLite backup API 複製到新位置並執行 `PRAGMA quick_check`；成功後使用新 DB，但保留舊 DB 作為回復來源。
- 若搬遷失敗，新位置不得留下半成品 DB，舊 DB 保持不變並顯示明確繁體中文錯誤。
- `FIRELENS_DATA_DIR` 測試／self-test 隔離機制優先權最高，不得因安裝路徑功能而寫入正式資料庫。
- GitHub Release 除既有 raw EXE、SHA256、manifest、signature 外，再發布 `FireLens-<版本>-setup.exe`；線上更新仍更新既有 EXE，不動 `data`。

任務：
- [x] `config.py`：正式 packaged Windows 版將 DB 定位到 `{exe_dir}\data\firelens.sqlite3`，保留 `FIRELENS_DATA_DIR` override
- [x] `db.py`：安全搬遷舊版 LocalAppData DB，來源保留、quick_check 驗證、失敗回滾
- [x] Inno Setup：新增現代安裝精靈，應用名稱／捷徑／自訂提示採繁體中文友善文字；開始功能表捷徑、可選桌面捷徑、每使用者預設安裝
- [x] build：Windows 正式 build 同時產生 EXE 與 setup.exe，任一失敗都不得宣稱完成
- [x] GitHub Actions：正式 Release 上傳 setup.exe，SHA256SUMS 同時涵蓋 raw EXE 與 setup.exe
- [x] app info／文件：能辨識安裝目錄與實際 DB 路徑，README 說明新安裝與舊資料搬遷
- [x] 測試：安裝 DB 路徑、override、舊 DB 搬遷、既有新 DB 不被舊 DB 覆寫、installer 規格
- [x] 歷史 v1.4.0 相容更新：未帶 installer marker 的 frozen/raw EXE 保持舊 LocalAppData DB；setup 安裝後才切換 `{app}\data` 並搬遷
- [x] build 安全：打包後 EXE self-test 強制使用臨時 `FIRELENS_DATA_DIR`，並等待 GUI EXE 真正結束後檢查 exit code；不得碰正式 LocalAppData／安裝目錄 DB
- 驗收：當時使用 Inno Setup 6.7.3 實際編譯 `FireLens-1.5.0-setup.exe`；完整 build 通過版本一致性、Ruff format/check、pytest 73 passed、Vitest 26 passed、TypeScript/Vite、PyInstaller 與等待 GUI 程序真正結束的 `FireLens.exe --self-test`。隔離相容驗證已確認歷史 v1.4.0-style raw EXE 無 installer marker 時 `install_dir=null` 且仍使用舊 `%LOCALAPPDATA%\FireLens\firelens.sqlite3`；執行 setup 後才切換 `{app}\data\firelens.sqlite3`，`PRAGMA quick_check=ok`、舊資料內容完整搬遷且原 DB 保留；解除安裝後 EXE 移除但 DB 保留。Graphify 已重建為 511 nodes / 1129 edges / 43 communities。

### M13 清冊簡化核對、匯入引導與完整繁中安裝精靈（2026-10-20 完成）

背景：現場真正需要的是「給 FireLens 一批應該存在照片的設備編號，系統直接告訴使用者哪些有、哪些沒有、缺哪一張」。現有清冊流程仍帶有「區段、型式規格、上次更換日」等不必要欄位，且安裝精靈的 Inno Setup 系統頁面仍未完整繁體中文化。

定案輸入格式：
- 最簡單的文字貼上可只有一欄完整設備編號，例如 `動-01-15`、`致-B1-67`、`中-B2-05`；沒有棟別樓層仍必須能完整分析與核對。
- 文字貼上也支援 Excel 複製出的 Tab 雙欄，例如 `致德樓8F<TAB>致-08-19`、`致德樓B1F<TAB>致-B1-67`、`中正樓B2F<TAB>中-B2-05`。
- Excel 的主要正式格式為「棟別樓層 + 完整設備編號」兩欄，例如 `致德樓8F | 致-08-19`；支援有標題與無標題。`棟別樓層` 選填，`設備編號` 必要。
- 有標題時需相容：`棟別樓層`／`區段`，以及 `設備編號`／`編號`／`滅火器編號`。Excel 其他欄位存在時可忽略，不得因多餘欄位匯入失敗。
- 不做「棟別樓層 + 尾碼」自動組合設備編號；第二欄本身就是完整設備編號。也不得由 `致-08-19` 擅自猜成「致德樓8F」。

清冊與核對規格：
- 設備編號是唯一必要的核對主鍵；棟別樓層只做顯示、分組、篩選與人工辨識，不能成為核對必要條件。
- UI 將「區段」改顯示為「棟別樓層」；資料庫既有 `section` 欄位可相容保留，不做破壞性改名。
- 新流程移除「型式規格」「上次更換日」的輸入、表格與核對用途；舊清冊已保存資料仍保留，不刪歷史欄位／`raw_json`。
- 文字與 Excel 匯入都先做預覽，至少顯示：總筆數、有效筆數、重複筆數、無法辨識筆數，再由使用者確認儲存。
- 安全輸入容錯：去前後空白、整理 Tab／多空白、英文字母大小寫正規化；不得擅自補零、改設備編號內容或猜測樓名。
- 同一清冊重複設備編號需明確標示；棟別樓層與設備編號前綴看似不一致時顯示非阻擋警告，不自動修正。
- 核對結果至少分類為「完整」「缺部分照片」「完全無照片」「找不到設備資料夾」「有未對應／舊制照片」。
- 支援一鍵只看缺失項目，並可依「棟別樓層」及缺少的槽位（例如缺完成、缺藥劑）篩選。
- 可匯出缺失清單，至少包含：設備編號、棟別樓層、缺少照片／狀態，方便交給同事補拍。
- 建立清冊時依年月／類別預填名稱建議，例如 `2026/10 滅火器清冊`，但允許使用者自由修改。
- 保留 M10 已完成的原始貼上內容、清冊重新開啟／重新命名／刪除／既有清冊核對能力。

引導與安裝：
- 第一次進入清冊核對時提供短版引導：①準備一行一個設備編號或雙欄資料 → ②貼上或匯入 Excel → ③確認解析預覽 → ④儲存並開始核對。
- 清冊頁永久提供「查看範例／使用教學」，範例同時展示單欄設備編號與「棟別樓層 + 設備編號」雙欄格式；可提供「下次不再自動顯示」。
- Inno Setup 安裝精靈需完整繁體中文化，包含歡迎頁、安裝位置、其他工作、上一頁／下一步／取消、準備安裝、安裝進度與完成頁；繁中語言資源納入 repository，不依賴開發機另外安裝 `ChineseTraditional.isl`。

任務：
- [x] 後端文字解析：單欄設備編號、Tab 雙欄棟別樓層＋設備編號、輸入正規化與錯誤列資訊
- [x] Excel 匯入：支援有／無標題、一欄／兩欄、欄名別名與忽略多餘欄位
- [x] 清冊資料相容：新流程以設備編號為主鍵、棟別樓層選填，舊 `section/specification/last_replacement_date/raw_json` 不破壞
- [x] 匯入預覽：有效／重複／無法辨識統計、重複列標示與棟別樓層不一致非阻擋警告
- [x] 清冊 UI：將「區段」顯示改為「棟別樓層」，移除新流程的「型式規格」「上次更換日」
- [x] 核對結果：新增完整／缺部分照片／完全無照片／找不到設備資料夾／未對應舊制照片分類
- [x] 核對篩選：只看缺失、依棟別樓層、依缺少槽位篩選
- [x] 匯出：產生缺失清單（設備編號、棟別樓層、缺少照片／狀態）
- [x] 清冊名稱建議：依年月／類別預填但可修改
- [x] 引導教學：首次短引導、下次不再自動顯示、永久「查看範例／使用教學」入口
- [x] Installer：將 Inno Setup 系統頁面與自訂提示完整繁體中文化，繁中語言資源隨專案版本控制
- [x] 測試：單欄／雙欄貼上、Excel 有／無標題、無棟別樓層、重複編號、前後空白、B1/B2、棟別樓層警告、舊清冊相容、核對分類／篩選／匯出與繁中 installer
- [x] 最終驗收：版本一致性、Ruff、pytest、Vitest、TypeScript/Vite、Windows EXE self-test、完整繁中 setup build、合成資料 E2E 與 Graphify 全部通過後才可標記 M13 完成
- 驗收：完整 Windows build 通過版本一致性、Ruff format/check、pytest 82 passed、Vitest 27 passed、TypeScript/Vite、PyInstaller 與等待 GUI 程序結束的 `FireLens.exe --self-test`。當時使用 Inno Setup 6.7.3，並以 repository 內 `packaging/lang/ChineseTraditional.isl` 成功產生完整繁中 setup，無缺漏語系 fallback 警告。1407×804 Chrome 合成資料 E2E 已實際完成「雙欄貼上 → 解析預覽 → 儲存並開始核對 → 分類結果 → 缺完成篩選」，顯示 4 筆中 2 筆完整、1 筆缺部分照片、1 筆找不到資料夾，且瀏覽器 console/network 無 FireLens 4xx/5xx 或 failed request。Graphify 已重建為 530 nodes / 1164 edges / 42 communities。
- Release：`v1.5.0` 已由 GitHub Actions run `39444235196` 正式建立，Release 資產包含 `FireLens-1.5.0-setup.exe`、`FireLens-1.5.0-windows-x64.exe`、`SHA256SUMS.txt`、`update-manifest.json`、`update-manifest.sig`；Release build／版本一致性／manifest 簽章／資產上傳步驟均成功。

### M14 一鍵式安全線上更新（歷史 v1.6.0）

背景：目前線上更新需要依序按「檢查更新」→「下載並驗證」→「安裝並重新啟動」。安全驗證流程已完整，但一般使用者操作步驟偏多。新版保留既有 Ed25519／SHA-256／EXE self-test 安全鏈，只簡化使用者操作，不降低任何驗證強度。

需求：
- 「檢查更新」仍保留；沒有新版時顯示「目前已是最新版本」。檢查到新版後，主要操作改為單一按鈕「下載並安裝 vX.Y.Z」。
- 使用者按一次「下載並安裝」後，FireLens 自動依序完成：下載 Release EXE → 驗證 Ed25519 manifest 簽章 → 核對版本／檔名／檔案大小／SHA-256 → 執行下載後 EXE self-test。
- 上述所有安全檢查成功後，才顯示一次最終確認：「更新已驗證完成，FireLens 將關閉並更新到 vX.Y.Z，完成後自動重新啟動。」使用者確認後才真正替換目前 EXE。
- 使用者取消最終確認時不得關閉程式或替換 EXE；已下載且驗證成功的更新檔可保留供本次程式執行期間再次安裝，不必強迫重新下載。
- 任一階段失敗時立即停止，不得進入安裝／替換流程；現有版本必須保持可正常啟動，並提供繁體中文的失敗階段、原因與「重試」入口。
- 更新過程顯示明確狀態，例如「下載中」「驗證簽章」「核對 SHA-256」「執行新版自我測試」「等待確認」「正在安裝並重新啟動」；能取得下載大小時顯示下載進度。
- 更新進行中禁止重複觸發第二個下載／安裝工作；按鈕需停用並顯示目前處理階段，避免併發更新造成暫存檔或 updater 衝突。
- 正式安裝版仍只替換 `{app}\FireLens.exe`；不得修改、刪除或搬移 `{app}\data\firelens.sqlite3`、其他 `{app}\data` 使用者資料、`.firelens-installed` 或安裝精靈資訊。
- 歷史 portable/raw EXE 與正式 Inno Setup 安裝版都要維持可更新；不得因 installer marker、DB 位置或 EXE 所在目錄不同而破壞既有相容更新路徑。
- 保留既有回滾／失敗保護：新版 EXE 啟動或替換驗證失敗時，舊版必須可恢復，不得留下半套更新狀態。
- 「查看 Release」連結保留，讓使用者仍可人工查看 GitHub Release；自動更新只接受既有內建公鑰驗證通過的正式 Release。

任務：
- [x] 前端：將新版可用時的兩段式「下載並驗證」＋「安裝並重新啟動」整合為單一「下載並安裝 vX.Y.Z」操作流程
- [x] 前端：新增更新狀態機與進度顯示，避免重複點擊／併發更新，錯誤訊息全部使用繁體中文
- [x] 前端：所有安全驗證完成後才顯示一次最終重新啟動確認；取消確認不得安裝或關閉 FireLens
- [x] 後端／updater：確認現有 download／schedule install 流程可安全串接；已驗證更新可於本次執行期間再次安裝，且安裝前仍再次驗證簽章、SHA-256 與 EXE self-test
- [x] 安全：確認任何下載、簽章、SHA-256、版本、檔名、大小或 EXE self-test 失敗，都不會替換目前版本，並可安全重試
- [x] 安裝版相容：驗證 `{app}\data`、`.firelens-installed` 與既有安裝資訊不受線上 EXE 更新影響
- [x] portable 相容：驗證沒有 installer marker 的 raw EXE 仍沿用既有 LocalAppData DB 邏輯並可完成一鍵更新
- [x] 測試：補齊 frontend 狀態流程、取消、重試、重複點擊、各驗證階段失敗、安裝版／portable 更新路徑測試
- [x] 打包驗收：以隔離暫存環境模擬「舊版 packaged EXE → 新版 EXE」完整更新與重新啟動，確認失敗回滾與資料庫內容／SHA 不變
- [x] 最終驗收：版本一致性、Ruff、pytest、Vitest、TypeScript/Vite、Windows EXE self-test、setup build、更新 E2E、實際打包 UI 啟動 smoke 與 Graphify 全部通過

驗收標準：使用者從「發現新版」開始只需按一次「下載並安裝」，等待自動安全驗證；全部通過後只再確認一次重新啟動，即可完成更新。任何驗證失敗或使用者取消都不得破壞目前可用版本或使用者資料。

- 驗收：完整 Windows build 通過版本一致性、Ruff format/check、pytest **90 passed**、Vitest **31 passed**、TypeScript/Vite、PyInstaller 與打包後 `FireLens.exe --self-test`；`packaging/update_e2e.py` 實際驗證 EXE 替換／重新啟動、失敗回滾，且 SQLite DB 與 `.firelens-installed` SHA-256 均保持不變；當時使用 Inno Setup 6.7.3 成功產生 `FireLens-1.6.0-setup.exe`；打包版 UI 隔離資料目錄啟動 smoke 通過；Graphify 已重建為 **569 nodes / 1231 edges / 47 communities**。
- Release：`v1.6.0` 已由 GitHub Actions run `39513769728` 正式建立，Tag 指向 `cb88036863ec6f8a6db796cd341619d3b8bc8db9`；Release 資產包含 `FireLens-1.6.0-setup.exe`、`FireLens-1.6.0-windows-x64.exe`、`SHA256SUMS.txt`、`update-manifest.json`、`update-manifest.sig`，Release build／版本一致性／manifest 簽章／資產上傳均成功。

### M15 線上更新器可靠性修復與真正端到端更新驗證（歷史 v1.6.1）

#### 實機事故與已確認證據

- 使用者在歷史正式安裝的 **FireLens v1.5.0** 內檢查到 v1.6.0 後，按下「安裝並重新啟動 v1.6.0」並確認；FireLens 關閉，但沒有自動重新啟動，使用者手動重新開啟後仍為歷史 v1.5.0。
- 實機正式安裝位置 `C:\Users\mike\AppData\Local\Programs\FireLens\FireLens.exe` 仍是舊檔，大小 **36,113,454 bytes**，沒有被 v1.6.0 正式 Release EXE 取代。
- `%LOCALAPPDATA%\FireLens\updates\v1.6.0` 已存在完整 staging：`FireLens-1.6.0-windows-x64.exe`（**36,260,379 bytes**）、`update-manifest.json`、`update-manifest.sig`、歷史 `FireLens-1.5.0-backup.exe`、`apply-update.ps1`。因此下載、簽章／檔案驗證、備份與更新腳本建立至少已走到 `schedule_install` 後段。
- `%LOCALAPPDATA%\FireLens\updates\update.log` **不存在**。當時歷史 PowerShell 腳本在成功複製後與 catch 失敗處才會寫 log，因此可確認故障發生在「腳本真正進入可記錄執行階段之前」；沒有足夠證據可武斷指定是 Windows detached process、PowerShell 參數／解析、端點防護或其他啟動競態中的哪一個單一 OS 近因。M15 已以 transaction log／READY handshake 補足可觀測性並消除「未確認 updater 可用就退出」的系統性根因。
- 歷史 v1.5.0 與歷史 v1.6.0 的 `schedule_install` 都採 `subprocess.Popen(powershell.exe ...)` 搭配 `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`，之後 API 以約 1.5 秒 timer 直接 `os._exit(0)` 關閉 FireLens。歷史 v1.6.0 雖加強腳本內的啟動健康檢查與 rollback，但**背景 updater 的啟動／存活握手機制仍與歷史 v1.5 同類型**，所以不能把這次問題視為歷史 v1.6 已確定排除。
- M14 的 `packaging/update_e2e.py` 是直接以 `subprocess.run(powershell.exe -File apply-update.ps1 ...)` 同步執行更新腳本，並使用不存在的假 PID；它證明「腳本已成功啟動後」的替換、重啟、rollback、DB／marker 保護，但**沒有覆蓋真正產品鏈 `FireLens.exe → schedule_install → detached updater → FireLens 自己退出 → updater 存活`**。這是本次實機才暴露出的驗收缺口。

#### 修正原則

- **不得先關閉 FireLens 再賭 updater 有成功存活。** FireLens 只有在獨立 updater 已啟動並完成明確 handshake 後，才允許進入關閉階段；handshake 失敗必須保持目前 FireLens 正常運作並直接顯示繁中錯誤。
- 優先改為真正獨立的 `FireLensUpdater.exe` helper，而不是把 PowerShell detached script 當唯一正式更新執行器。helper 必須能在主程式退出後獨立存活、等待原 PID 釋放 EXE、執行替換、驗證、啟動新版與 rollback。
- 正式安裝版可由 installer 安裝 updater helper；單一 portable/raw EXE 仍必須可更新，因此 helper 應能由主 EXE 內嵌資源安全解出到 `%LOCALAPPDATA%\FireLens\updates`，不能要求 portable 使用者自行放第二個檔案。
- 既有 v1.5.0／v1.6.0 已發布版本無法被未來程式碼「逆向修正」。若舊版再次遇到「按更新後關閉但仍停在舊版」，官方復原路徑必須明確指示直接執行最新版 `FireLens-<版本>-setup.exe`；安裝／升級不得刪除 `{app}\data`。
- 所有既有 Ed25519 manifest、版本／檔名／大小、SHA-256、下載後 EXE self-test、安裝前再次驗證都必須保留；M15 是可靠性修正，不得用降低驗證強度換取更新成功率。

#### 可靠更新交易流程

1. FireLens 完成既有下載與安全驗證後，建立唯一 `transaction_id` 與更新狀態檔，內容只保存版本、PID、目標路徑、階段、時間與錯誤，不保存私鑰或敏感資訊。
2. FireLens 啟動 `FireLensUpdater.exe`；updater **第一件事**就建立 log 並回報 `started/ready` handshake（例如命名事件、受限 localhost IPC 或原子 ready 檔）。
3. FireLens 等待有 timeout 的 handshake。只有確認 updater PID 存活且 handshake 對應相同 transaction 後，API 才回傳「可關閉更新」並排程主程式退出；失敗則終止本次更新、保持舊版運行。
4. updater 等待原 FireLens PID 真正退出，並以有限次數重試確認 `{app}\FireLens.exe` 已解除檔案鎖；逾時不得破壞目前 EXE。
5. updater 再次驗證 staged EXE SHA-256，備份目前 EXE，替換後立刻驗證**目標 `{app}\FireLens.exe` 本身**的 SHA-256 必須等於 manifest。
6. updater 啟動新版 FireLens 時帶一次性 `transaction_id`。新版不能只靠「程序 10 秒沒退出」當成功；必須在 FastAPI／桌面視窗完成可用啟動後回寫 `healthy` handshake。
7. updater 在 timeout 內收到新版 `healthy` 才標記成功；若新版無法啟動、提早退出、沒有 healthy handshake 或目標 hash 不符，立即恢復備份，再啟動舊版並記錄 rollback 結果。
8. 成功、失敗、rollback 都要留下可讀的 `%LOCALAPPDATA%\FireLens\updates\update.log` 與 machine-readable 狀態；下次啟動 FireLens 若偵測上一筆失敗，要顯示「上次更新未完成，目前仍安全使用 vX.Y.Z」與查看 log／重試入口。

#### 任務

- [x] 事故重現／根因確認：保留實機 staging／無 log 證據並以打包後程序鏈重現 updater 啟動邊界；確認**系統性根因是舊架構沒有 READY handshake 卻允許主程式無條件退出**。M15 首輪 packaged E2E 另抓到 PyInstaller one-file bootloader PID 與 Python helper PID 不同，已移除錯誤的 PID 相等假設；不武斷宣稱歷史 PowerShell 失敗的單一 OS 近因
- [x] Updater 架構：建立最小化 `FireLensUpdater.exe` helper，職責只包含 handshake、等待舊 PID、備份／替換／hash 驗證、啟動新版、健康確認、rollback 與 log
- [x] Helper 配布：Inno Setup 安裝版正確部署 updater；portable/raw EXE 可從受信任內嵌資源解出 helper，並對 helper 自身做 build-time 固定 SHA-256 驗證後才執行
- [x] 啟動握手：`schedule_install` 等待 transaction-bound updater `ready`；未取得 ready 時 API 回錯、禁止排程 `os._exit(0)`，舊 FireLens 保持執行
- [x] 關閉流程：移除「固定 1.5 秒後無條件退出」作為唯一同步機制；現在只有 updater ready → API 成功回應後才以短延遲釋放 HTTP 回應並受控退出
- [x] 替換安全：helper 以 Win32 process handle 等待舊 PID、有限重試 EXE lock、備份與替換前後核對 SHA-256；copy／replace／權限／鎖定錯誤進入明確失敗或 rollback
- [x] 新版健康握手：新版以 transaction token 啟動，pywebview DOM `loaded` 後才回報 `healthy`；不再用「程序存活 N 秒」作成功判斷
- [x] Rollback：新版 crash、healthy timeout 或安裝交易失敗可還原舊 EXE並重新啟動；rollback 注入失敗時保留 backup、state、log 與人工復原資訊
- [x] 更新狀態與診斷：新增原子 transaction state／latest pointer／`update.log`；實測 log 含 started、ready、parent exited、backup、replace target hash、new launch、healthy、error／rollback
- [x] 啟動後提示：`/api/app-info` 讀取上一筆更新狀態；失敗／rollback 在主畫面與設定頁顯示非阻擋繁中提示、目前版本、log 路徑與重試方式
- [x] 舊版過渡：README 明確說明歷史 v1.5.0／v1.6.0 若自動更新關閉後沒有重啟，使用最新 setup 直接覆蓋安裝即可，且 `{app}\data` 不會被刪除；正式 Release 說明須沿用此規則，不建議刪 DB 或解除安裝清資料
- [x] 單元測試：補齊 transaction id、ready／healthy handshake、timeout、繁中／空白路徑、target locked、helper startup failure、API 未 ready 不退出；既有 staged SHA mismatch 測試與真實故障注入 E2E 一併覆蓋 copy／replace／rollback 路徑
- [x] 真正 E2E：由打包後 `FireLens.exe --update-e2e-trigger` 自身觸發與 production 相同 scheduler/helper 交易，實測 `FireLens.exe → updater ready → FireLens 退出 → helper 存活 → EXE 替換 → 新版 UI DOM loaded → healthy` 全鏈
- [x] 安裝版 E2E：隔離 Inno Setup 安裝到含繁中／空白路徑，確認 setup 部署 helper，真正更新後 `{app}\data\firelens.sqlite3`、`.firelens-installed` 與 helper SHA／內容不變
- [x] Portable E2E：單一 raw EXE 在無 installer marker 下由內嵌 payload 解出 hash 驗證 helper 完成更新，並確認仍使用隔離 LocalAppData DB 且不建立 installer marker
- [x] 故障注入 E2E：實測 helper 無法啟動、READY 後死亡、EXE 鎖逾時、替換權限失敗、新版立即 crash、新版不回 healthy、rollback failure；可回滾情境均恢復可 self-test 舊版，rollback failure 保留可驗證 backup
- [x] CI／build：`packaging/build.ps1` 先建 `FireLensUpdater.exe`、固定 helper hash、再建主 EXE／setup，最後強制執行真實 packaged updater E2E；GitHub Actions Release 原本即呼叫此 build，因此 E2E 失敗會阻止發布
- [x] 版本：PATCH bump `1.6.0 → 1.6.1` 已同步 `desktop/version.py`、`pyproject.toml`、`uv.lock`、frontend fallback、TASKS、README Release 範例，版本一致性檢查通過
- [x] 最終驗收：Ruff、pytest、Vitest、TypeScript/Vite、Windows EXE self-test、繁中 setup、真實 updater E2E、安裝版／portable／rollback 故障注入、UI 實際啟動與 Graphify 全部通過

驗收標準：不能只證明「更新腳本單獨執行成功」。必須證明使用者在真正 FireLens UI 按下更新後，舊 FireLens 在 updater 已 ready 前絕不退出；退出後 updater 仍存活並成功替換 EXE，新版自動啟動且回報 healthy。任何故障都必須保持可啟動版本與使用者資料完整。

- M15 驗收：完整 Windows build 通過版本一致性、Ruff format/check、pytest **98 passed**、Vitest **31 passed**、TypeScript/Vite、PyInstaller `FireLensUpdater.exe`＋`FireLens.exe`、打包後 `FireLens.exe --self-test`、完整繁中 Inno Setup。`packaging/update_e2e.py` 已由 packaged FireLens 本身觸發 portable 與 installer 真實更新，並通過 READY／HEALTHY、DB／marker／helper 不變與 7 種故障注入；額外 packaged UI 隔離啟動 smoke exit code 0。Graphify 已重建為 **625 nodes / 1376 edges / 46 communities**。
- M15 當時最終工作樹本機產物 SHA-256：`FireLens.exe` = `43B70A77830538BB957CE1FFFD16D008F8746C3374D0386DB37DA718E2ED6515`；`FireLensUpdater.exe` = `AB6774945ABB3087305E3570AEB3DD3F4BCF31E3F4F85608AA57A7F7F143BE18`；`FireLens-1.6.1-setup.exe` = `26732A170C5AEE0CFD894A76A132C3F9C3E86C5CBAA73D8CE41A1E2B03DB824A`。歷史 v1.6.1 當時尚未建立 Git Tag 或 GitHub Release。

### M16 設備資料夾更名、清冊匯出修復與設備異常單選標記／統計（v1.7.0 已實作）

背景：使用者提供照片牆截圖，圈選設備編號標題（例如 `中-03-238`）。已在標題**右側**加入「更改名稱」，真正更改對應的實體設備資料夾名稱，不只改畫面文字、照片檔名或清冊名稱；並修復缺失清單匯出與新增單選設備異常／統計。所有測試只使用合成資料，不修改真實現場照片或清冊。

#### 已確認需求

- [x] UI：在照片牆頂部設備編號（`item.code`）右側新增「更改名稱」按鈕，與現有「刪除」明確區隔；未選擇設備時不顯示。
- [x] 互動：按下後開啟應用內對話框，預填原名稱；輸入新名稱時顯示 `舊名稱 → 新名稱`、相對路徑與受影響照片數量，使用者明確確認後才執行。
- [x] 實體更名：只將選取設備資料夾在**同一父資料夾**內重新命名；保留內部照片與子資料夾，不跨目錄搬移、不重新編碼、不修改照片檔名／內容。
- [x] 索引與 UI：實體更名後同步 `item.code`、`item.relative_path`、所屬 `photo.relative_path` 與縮圖關聯，更新左側資料樹／選取狀態／頂部名稱；重新掃描、切換設備與重啟後不得產生重複設備、舊路徑或無法載入照片。
- [x] 合法名稱：新名稱只能是單層安全 basename，拒絕空白、`.`／`..`、路徑分隔符、Windows 禁用字元／保留名稱、尾端空白／句點、跳出根目錄路徑；相同父層若已有同名目標（含 Windows 大小寫不敏感衝突）必須阻擋，禁止覆寫。
- [x] 操作前防護：確認選取資料夾與磁碟實際位置一致、來源不是符號連結／reparse point，且具備必要寫入權限；來源不存在、根目錄離線、掃描進行中或雲端串流狀態不安全時阻擋，不得為了改名強制下載 Google Drive placeholder。
- [x] 故障安全與稽核：任一步驟失敗不得顯示成功；實體更名與索引更新需一致性處理，必要時安全復原／重建索引。於 `audit_log` 記錄設備 ID、前後相對路徑、時間與結果；先評估既有 `rename_log` 是否適合資料夾交易，避免破壞照片改名／復原語意。
- [x] 清冊保護：設備資料夾名稱牽涉核對主鍵；更名可能使現有清冊的舊編號比對不到，確認前必須提示。不得擅自修改受保護的 `ledger`、`ledger_row` 或原始清冊文字，清冊自動同步須另行討論。
- [x] 測試驗收：只使用合成／暫存副本；覆蓋正常更名、撞名、非法名稱、權限拒絕、離線／掃描阻擋、索引更新失敗、繁中／空白路徑、多張照片、重啟與清冊核對；不得觸碰真實 `滅火器更換照片/` 與 `數據.xlsx`。實作時再依 AGENTS 執行升版、版本一致性、Ruff/pytest/Vitest、Windows build 和 UI 驗證。

#### 清冊核對匯出缺失 CSV／Excel：使用者實測問題

使用者原先實測：Windows 桌面版「清冊核對」的「匯出缺失 CSV／Excel」使用一般 `<a href>` 附件下載連結，按下後沒有可見反應。改版改用前端按鈕呼叫受保護的本機 `POST /api/reconcile/export/save`，由後端原子地儲存至 `Downloads/FireLens`（測試可使用 `FIRELENS_EXPORT_DIR` 隔離），回傳檔案位置及結果；保留原 `GET /api/reconcile/export` 供其他瀏覽器下載。無法事後確定歷史 WebView2 未下載的單一 OS 近因；但新流程已從打包後 GUI 真正點擊兩個按鈕並取得有效 CSV／XLSX。

- [x] 歷史匯出路徑檢查：原版僅用 `<a href>` 附件連結，沒有桌面版下載完成回饋；不假定已查明歷史 WebView2 的唯一 OS 近因。新版改成受保護本機 POST，並在真正 packaged Windows WebView2 畫面上依序點擊「清冊核對 → 開始核對 → 匯出缺失 CSV → 匯出缺失 Excel」，兩種檔案均在隔離資料夾實際產生且非空。
- [x] CSV 匯出修復：按下「匯出缺失 CSV」必須有明確下載／儲存行為，不得僅讓桌面 WebView 導航到 attachment URL；實際寫出 `.csv` 檔案，使用 Excel 開啟時繁體中文、設備編號與棟別樓層不得亂碼、截斷或自動改編號。
- [x] Excel 匯出修復：按下「匯出缺失 Excel」必須實際寫出可正常開啟的 `.xlsx`，包含正確欄名、設備編號、棟別樓層、缺失項目／狀態；不可輸出損壞的 XLSX 或只有顯示成功卻未產生檔案。
- [x] UI 互動與錯誤提示：桌面版已改為按一次即自動儲存至使用者下載目錄下的 `FireLens` 子資料夾（無另開「另存新檔」對話框）；顯示「正在匯出／已儲存檔名與路徑／失敗」狀態，可重試；錯誤不報成功。改用受保護本機 POST 儲存，避免 WebView2 一般超連結附件下載失效，保留 session／Host／Origin 檢查。
- [x] 匯出資料範圍核對：維持舊有 `export_reconciliation` 的「整份清冊／來源的缺失與待確認清單」語意，**不受目前畫面篩選條件影響**；保留缺部分照片、完全無照片、找不到設備資料夾、未對應舊制／待確認等既有分類，完整設備不列入缺失；零缺失時匯出只有標題列的有效檔案。若日後要只匯出畫面目前篩選結果，另開需求。
- [x] 安全與整合驗收：只用合成清冊／照片索引及暫存匯出目錄；驗證 CSV／XLSX 檔案實際存在、大小非零、內容與核對結果相符，繁中設備編號不被破壞；覆蓋無缺失、儲存路徑無法寫入時回報失敗的情境，並實際從 packaged Windows UI 點擊兩種匯出。採直接存入下載資料夾，沒有「取消另存新檔」對話框；不得修改真實清冊、照片或既有資料庫。

#### 設備異常單選標記與自訂分類統計（已實作）

使用者提供照片牆畫面，以紅框標示設備標題右側、既有「刪除」左側的空白區，要求為目前設備選擇現場異常分類，預設例子包括「瓶身超過10年」「無法辨識」「壓力錶故障」。**最新定案：每台設備同一時間最多只能選擇一個異常，也可不選；不提供「已改善」功能。** 使用者仍可自行建立多個異常名稱供選擇，並在另一處依分類統計設備數、列出實際設備清單。此處是**人工巡檢紀錄**，不因照片存在／缺失而自動判定，也不是既有清冊的補拍標記。

- [x] 照片牆操作區：在紅框位置加入可展開的「設備異常」**單選**控制（例如下拉選單或 radio），只能選一項；顯示目前選取的異常名稱，提供「無異常／清除選擇」恢復未標記狀態，不能擠壓「刪除」、設備編號或照片槽位。支援滑鼠、鍵盤及較窄視窗，所有標籤使用繁體中文。
- [x] 預設可選項目：至少「瓶身超過10年」「無法辨識」「壓力錶故障」。其中「瓶身超過10年」是使用者**手動勾選的判斷**，目前沒有瓶身出廠日期資料來源，不得自動推算使用年限。
- [x] 自訂標籤管理：使用者可建立任意多個合理長度的名稱、修改名稱、排序與停用；禁止空白與重複（含前後空白差異）。修改顯示名稱後既有標記應仍指向同一個標籤 ID；已被使用的標籤不得因刪除而無提示地抹除歷史紀錄。是否允許永久刪除／合併標籤，待使用者確認。
- [x] 設備單選標記：同一設備最多指定**一個**異常分類；若改選另一分類，必須取代舊分類而非累加；也可清除標記，一種異常可被多台設備選用。變更後立即更新 UI／統計，重新開啟程式或重新掃描仍保留。
- [x] 資料庫持久化：採新增受保護的自訂異常字典與**設備對異常的單一關聯**（具穩定標籤 ID、設備識別、建立／更新時間，並以資料庫唯一性約束確保單設備最多一筆目前異常），只做增量 migration＋備份。不得把紀錄只掛在可重建的 `item.id`，也不得重用受保護且具不同語意的 `reshoot_mark` 或覆蓋清冊資料。設備識別應考慮根目錄／類別／相對路徑與可能同編號跨月份存在的情況，避免標錯設備。
- [x] 與 M16 資料夾更名／掃描協作：若設備資料夾改名，異常標記必須跟著正確對應到新資料夾；改名失敗不可丟失標記。外部手動改名、設備消失、根目錄離線或索引暫時未建立時，不得默默刪除標記，需規劃「待確認／來源離線」呈現及重新關聯策略。
- [x] 上方導覽列新增「統計」分頁：**固定放在「清冊核對」右側、「整理工具」左側**，順序為「照片瀏覽｜清冊核對｜統計｜整理工具｜設定」；採用既有分頁樣式、選取狀態與鍵盤操作，窄視窗不可與其他分頁重疊。此分頁專門顯示設備異常分類統計，不混入「清冊核對」的缺照片結果。
- [x] 統計頁分類與清單：依使用者自訂異常名稱動態列出各異常設備數（如「瓶身超過10年：N 台」「無法辨識：N 台」「壓力錶故障：N 台」），並顯示目前已標記異常的去重設備總數；點進類別列出設備編號、棟別樓層、所在批次／根目錄與標記時間，可點擊設備返回「照片瀏覽」並選取對應設備。**每台設備只計入目前所選的一個分類**；切換分類時舊分類 -1、新分類 +1，清除則不計入任何異常。分類筆數相加應等於異常設備總數，不可重複計算設備。
- [x] 查詢與篩選：至少支援依異常分類、根目錄、棟別樓層、設備編號搜尋；分類新增／改名／停用後，統計與清單同步。是否加入 CSV／Excel 匯出異常清單、時間範圍等其他能力，先與使用者討論，不擅自當成已決定功能；**不設計「已改善」狀態或維修流程**。
- [x] 互動回饋與保護：標記成功／失敗有明確提示，不得 UI 已打勾但資料庫未保存；必要時記錄操作於 `audit_log`。掃描執行與離線情況如何允許標記（標記只改本機資料庫、不修改照片）需針對資料一致性決定；不可對現場照片檔案做任何更動。
- [x] 測試驗收：使用合成資料／暫存 SQLite，覆蓋**同設備只能單選、改選替換、清除選擇、資料庫唯一性約束、統計數正確轉移**、自訂標籤增改停用、同名防重、重啟、重新掃描、不同根目錄同設備編號、資料夾更名、離線、來源消失與資料庫 migration。必須實測打包 Windows UI，確認「統計」分頁位於「清冊核對」右側、標記持久化、分類數量正確且清單可返回照片瀏覽定位原設備，並遵守 AGENTS 的完整測試／升版規則。

#### 尚待確認的產品決策（先討論，勿自行拍板）

- 已採保守 MVP：所有根目錄共用一份異常分類字典，統計可按根目錄篩選；使用者未另外指定每個根目錄獨立分類。
- 已定案：「統計」為上方導覽列的獨立分頁，位置固定在「清冊核對」右側、「整理工具」左側，名稱使用「統計」，不放在「整理工具／資訊」內。
- 已定案：每台設備只能選一種異常或清除選擇；改選會直接取代舊分類，**不需要「已改善」功能**。如有操作稽核僅供診斷，不建立改善狀態、改善日期或維修工單。
- 本次不新增「設備異常統計清單」CSV／Excel 匯出（與已修復的「清冊缺失匯出」不同），使用者未提出確定需求；若未來需要，再另列里程碑。

#### 其餘需求待討論

- 本次 M16 只包含已確認的三大項目，不擴大到棟別／月份／年份資料夾批次改名、批次設備編號更名、清冊編號自動修正、已改善流程或異常統計匯出；後續需求另列新里程碑。

#### M16 實作與驗收紀錄

- SQLite 由 v7 增量升至 v8，舊版清冊與受保護資料表完整保留；新增 `issue_label` 及依 `root_id + item_relative_path` 識別設備的 `item_issue`，單設備最多一個標籤。異常紀錄不依賴可重建的 `item.id`，設備更名會同步更新異常關聯，來源消失／離線不會默默刪紀錄。
- 資料夾更名使用同層 `os.rename`，不編碼或修改照片；會同步設備與照片相對路徑／縮圖索引，寫入稽核，資料庫更新失敗時嘗試還原實體名稱。Google Drive 已連線且無雲端未下載照片時允許更名；離線、掃描中、保留名稱、撞名、佔位檔及待同步項目阻擋。清冊原始編號保持不變，UI 明確警告。
- 缺失清單匯出採 `/api/reconcile/export/save` 自動安全儲存至 `Downloads/FireLens`，顯示結果／完整路徑；不需仰賴 WebView2 附件下載。原 GET 匯出仍保留。使用者原本看到的兩個匯出按鈕現在有進度與錯誤回饋。
- 真正打包後 Windows 視窗測試：FireLens v1.7.0 UI 可開啟「統計」並載入「設備異常統計」；使用合成根目錄與清冊，直接按 UI 匯出 CSV（339 bytes）與 XLSX（5,373 bytes）皆成功。額外在隔離 pywebview／WebView2 操作真實 React 畫面，實測設備選取 →「更改名稱」→ 實體目錄更名成功、照片保留；再標記異常並確認 SQLite 保存，統計頁可列出更名後設備。沒有對任何現場根目錄操作。
- 完整 Windows build 已成功產生 `FireLens.exe`、`FireLensUpdater.exe` 與繁體中文 `FireLens-1.7.0-setup.exe`；打包後 self-test、portable／installer 真實 updater E2E、READY／HEALTHY、rollback／故障注入均通過；npm 正式執行依賴 `npm audit --omit=dev` 結果為 0 漏洞，npm 全依賴安裝時仍出現 1 項 high 等級開發依賴警告，不以 `npm audit fix --force` 擅自升級造成破壞。
- 本輪最終自動驗收：`packaging/check_version_consistency.py` PASS v1.7.0、Ruff format/check PASS、pytest **107 passed**（既有 1 項 Starlette/httpx deprecation warning）、Vitest **31 passed**、TypeScript／Vite PASS。Graphify 已重建為 **665 nodes / 1536 edges / 48 communities**，`graphify-out` 仍只留本機且受 `.gitignore` 排除。
- GitHub：此輪只保留本機開發成果，未 commit／push／建立 v1.7.0 Git Tag 或 Release；待使用者實機驗收後再決定發布。

## 11. 完成條件

- 使用者要求的流程可從介面完整操作。
- 重啟後應保存的資料仍存在。
- Ruff、pytest、Vitest、前端 build 通過。
- 有重要資料流程時，使用真實 SQLite 測試，不用替身取代。
- 影響桌面版或更新器時，打包 exe 自測通過。
- `packaging/check_version_consistency.py` 必須通過；目前版本、前端 fallback、套件版本、TASKS 狀態與 README 發版範例不得互相矛盾。
- 每輪開發完成後同步檢查 `AGENTS.md` 與更新 `TASKS.md`；若專案規則、架構、安全、測試、打包或發佈流程有變動，必須同步修正 `AGENTS.md`。
- 已完成任務必須在本文件標記為 `[x]` 並記錄必要的驗收結果；後續開發只從尚未完成的 `[ ]` 項目繼續，不得重複實作已完成或已取消的工作。
- 歷史 v1.4.0 當時最終本機驗收：`packaging/check_version_consistency.py` 通過；Ruff format/check 通過；pytest 65 passed；Vitest 26 passed；TypeScript 與 Vite build 通過；PyInstaller Windows x64 打包與 `FireLens.exe --self-test` 通過。Graphify 已重建為 497 nodes / 1109 edges / 41 communities。
- 歷史 v1.5.0 當時最終本機驗收：`packaging/check_version_consistency.py`、Ruff format/check、pytest 82 passed、Vitest 27 passed、TypeScript/Vite、PyInstaller、等待 GUI 程序完成並檢查真實 exit code 的 `FireLens.exe --self-test`、完整繁中 Inno Setup setup.exe build、歷史 v1.4.0 raw EXE 相容路徑、隔離安裝／資料庫搬遷／解除安裝保留 DB、M13 合成資料 E2E 與 Graphify 530 nodes / 1164 edges / 42 communities 均已通過。

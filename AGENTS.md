# FireLens 專案規則

開始任何修改前，先讀 `AGENTS.md` 與 `TASKS.md`；若衝突，以使用者最新指示與 `TASKS.md` 已定案需求為準。

## 文件與進度同步鐵律（強制）

1. 每次開始開發前，必須先閱讀 `AGENTS.md` 與 `TASKS.md`，確認目前規則、版本、待辦與已完成項目。`TASKS.md` 中已標記 `[x]` 的工作視為已完成，不得重複實作；只有在使用者明確要求修改、重構或修正回歸問題時才可重新處理。
2. 每一輪開發完成後，必須在同一輪工作內同步檢查並更新 `AGENTS.md` 與 `TASKS.md`。文件同步屬於完成條件的一部分，不得延後到之後再補。
3. `AGENTS.md` 用來保存長期有效的專案鐵律，包括架構、安全限制、資料處理規則、開發流程、測試方式、打包與發佈規範。只要實作使這些規則發生變動，就必須同步修正 `AGENTS.md`，並移除或改寫已過時的規則；不要把一次性的開發進度堆進 `AGENTS.md`。
4. `TASKS.md` 是專案進度與里程碑的唯一依據。新增、刪除、取消、變更或完成任何需求與任務時，都必須同步更新；完成項目必須改為 `[x]`，並在適合的位置簡要記錄實際完成內容與驗收結果。
5. 宣稱功能或里程碑「完成」之前，必須逐項核對 `TASKS.md`：不得出現「程式已完成但仍是 `[ ]`」、「需求已取消但仍列為待實作」、「舊版本／舊流程仍殘留在文件」等情況。文件與實作不一致時，視為尚未完成。
6. 後續開發一律從 `TASKS.md` 尚未完成的 `[ ]` 項目繼續；不得把已完成事項重新加入新的待辦或再次實作，以避免重工。若發現文件與程式現況不一致，先修正文檔再繼續開發。

## 開發前 TASKS 閘門（不可跳過）

1. **順序固定：讀取 AGENTS.md／TASKS.md → 先將新需求、範圍、例外情況、驗收標準及測試項目寫入 TASKS.md（未完成勾選 `[ ]`）→ 確認檔案寫入成功 → 才能修改功能程式碼。** 口頭討論完畢、使用者說「開始」也不能省略寫入步驟。
2. 每一個新功能、Bug、UI 調整、資料庫變更都適用。即使同輪直接開始開發，也要先完成 TASKS 寫入，再進行程式修改，不能在最後才補寫任務以追認。
3. 開發中新增或變更需求時先更新 TASKS.md，確認後再接續施工；已完成的步驟在測試後標記 `[x]`，未通過或未實機驗證的項目保持 `[ ]`，不得虛報完成。
4. 僅調整文件規範時不需要修改功能程式或升版。Git 提交及發布依使用者指示和現行版本規範執行。

## 版本管理鐵律（強制）

1. 每一輪功能開發、里程碑、Bug 修正或任何會改變使用者可觀察行為的修改完成時，必須在同一輪工作內先判斷是否需要升版；版本同步是完成條件的一部分，不得等到發佈前才補，也不得在版本仍停留於舊功能狀態時宣稱「完成」。
2. 版本號遵循 SemVer：向下相容的新功能、里程碑或新能力使用 **MINOR**（例如 `1.2.0 → 1.3.0`）；向下相容的 Bug 修正使用 **PATCH**（例如 `1.3.0 → 1.3.1`）；有破壞性相容變更才使用 **MAJOR**（例如 `1.x.x → 2.0.0`）。純文件、註解、格式整理，且完全不影響執行行為時可不升版。
3. 同一個尚未正式發佈的版本可以包含同一輪或連續開發完成的一組功能，不必每個 commit 都升一次；但一旦決定下一個正式版本，後續文件、打包與發佈都必須使用同一版本號，不可混用舊版號。
4. 升版時必須同步檢查並更新所有版本來源，至少包含 `desktop/version.py`、`pyproject.toml`、`uv.lock`、`TASKS.md` 的目前版本敘述，以及任何打包／Release／測試中直接寫死的版本字串；完成後要搜尋專案，確認沒有不該殘留的舊版本號。
5. 版本號更新後才進行最終驗收；至少重新執行 Ruff、pytest、Vitest、TypeScript／frontend build。若影響 Windows 桌面版、打包或更新流程，還必須重新建置 `FireLens.exe` 並執行打包後 self-test，確認視窗／app info 顯示的新版本一致。
6. 建立 Git Tag 或 GitHub Release 時，Tag、應用程式版本、Release 資產檔名、簽章 manifest 的版本必須完全一致；正式 Release 仍依既有 Ed25519 簽章更新流程執行。
7. 在最終回覆宣稱「完成」前，必須同時確認：程式已完成、測試已通過、`AGENTS.md`／`TASKS.md` 已同步、版本號已按本節規則處理。任一項未完成，就不得宣稱該功能或里程碑完成。
8. `packaging/check_version_consistency.py` 是強制版本一致性閘門。任何 commit 前、Windows build 前與 GitHub Release 前都必須通過；不得略過、註解或以手動判斷取代。它至少要核對 `desktop/version.py`、`pyproject.toml`、`uv.lock`、前端 fallback 版本、`TASKS.md` 目前版本與 README 發版範例。
9. 文件中的舊版本號必須能明確判斷是歷史紀錄，例如同一行標示「Release」、「當時」、「歷史」或「起」。未標示用途的舊版本號視為可能遺漏，版本一致性檢查必須失敗；未來規劃版本可標示「預計」，但當該版本已等於或低於目前版本時必須更新或移除「預計」。
10. 不要在完成項目／驗收文字中重複寫死「FireLens x.y.z」作為目前版本；目前版本只由版本來源與 `TASKS.md` 頂部狀態維護。歷史 Release 版本可保留，避免每次升版為了同步而改寫歷史事實。

## 專案目標與技術

FireLens 是 Windows 桌面照片管理工具，用來管理滅火器、放置盒、燈具更換照片，並以 Excel／文字清冊進行核對、補拍與整理。

- Python 3.12、FastAPI、SQLite、Pillow、openpyxl
- React、Vite、TypeScript
- pywebview（WebView2）、PyInstaller x64
- Python 套件管理只使用 `uv`；前端只使用 `npm`

## 最高優先安全規則

1. `滅火器更換照片/` 與 `數據.xlsx` 是真實測試資料，開發與測試期間一律唯讀。
2. 不得對真實資料改名、搬移、刪除、覆蓋、格式轉換、寫入中繼資料，或做任何會改變內容／mtime 的操作。
3. 寫入、匯入、改名、還原測試一律先複製最小必要資料到暫存／合成目錄，只操作副本。
4. 掃描功能必須唯讀；產品內批次改名必須有預覽、逐筆勾選、衝突阻擋與還原紀錄。
5. 不得刪除或重建受保護資料表：`ledger`、`ledger_row`、`alias_map`、`rename_log`、`audit_log`、`setting`、`category`、`reshoot_mark`、`offline_import_queue`、`issue_label`、`item_issue`，除非使用者明確要求並確認備份。
6. `item`、`photo` 是可重建索引；磁碟是照片狀態唯一真相來源。
7. Google Drive 串流佔位檔不可強制讀取／下載；應標記「雲端未下載」。
8. 寫入 Drive 必須採原子寫入：暫存檔 → rename → SHA-256 驗證；失敗不得顯示成功。
9. 不提交現場照片、清冊、機器實際路徑、憑證、私鑰或現場敏感資料到 Git。
10. 破壞性操作不得默認執行，先提供預覽與明確影響範圍。

## Python / uv

- 禁止 `pip install`、全域 Python 安裝依賴或手動建立其他 venv。
- 版本以 `.python-version`、`pyproject.toml` 為準。
- 安裝：`uv sync --locked`
- 新增依賴：`uv add <package>`，同步維護 `pyproject.toml`、`uv.lock`
- 執行：`uv run --locked ...`
- 臨時唯讀資料檢視可用 `uvx --with <package> ...`。
- `run.ps1`、`run-desktop.ps1` 與打包腳本都必須透過 uv 呼叫 Python。

## 預定結構

```text
backend/app/       FastAPI、SQLite、掃描、核對、儲存
frontend/src/      React UI
desktop/           桌面入口、單一實例、version.py
packaging/         EXE／ZIP 建置
tests/             後端與整合測試，只用合成／副本資料
docs/              驗證與盤點紀錄
AGENTS.md           本規則
TASKS.md            需求與里程碑
```

## M18 照片品質檢查：人工啟動、唯讀原圖、獨立覆核

- 主導覽「整理工具」右側是同層級「照片品質檢查」，不是整理工具子頁。照片品質異常可多張並存，不寫入既有 issue_label／item_issue 單選設備異常。
- 只由使用者點「開始掃描」觸發：預設增量，只分析新增／mtime 或大小變動照片；完整模式即使已有品質快取也強制重算。開啟頁面、切換分頁及「重新整理清單」只讀索引，不執行品質掃描。正式掃描先更新照片索引（使用既有安全掃描器），再分析本機可安全讀取的原圖；不與一般照片索引掃描併行，失敗與取消保留現有品質結果。
- photo_quality 以 root_id + relative_path 為鍵，記錄演算法版本、檔案大小／mtime、品質分數／狀態、人工覆核與覆核版本指紋；photo_quality_setting 保存各根目錄靈敏度。兩表由 additive SQLite schema 10 遷移建立，舊表及照片不得刪除；舊索引重建時仍沿用相對路徑匹配，照片版本／門檻不同時隱藏舊覆核並顯示未掃描。
- Pillow 只讀原始圖片於記憶體中按 EXIF 方向處理，再等比縮小工作副本分析 Laplacian 邊緣、紋理、亮度與原圖解析度。模糊輸出「高度疑似／可能／正常／無法判定」，不是自動合格判決；低紋理白牆與不同設備槽位應避免單閾值誤判。無法解碼報理由，雲端佔位檔、離線／符號連結／超大檔禁止強制讀取或下載。
- M18 採獨立低併發、可取消的背景掃描；不得修改照片內容、EXIF、mtime、名稱、既有設備異常或清冊。缺槽位與未辨識檔名另列；舊制放置盒不得被新制前中後規則誤判缺照。CSV／Excel 僅匯出文字中繼資料，避免公式注入，不含原圖或 OAuth 機密。
- 清晰度門檻只是候選初篩；真實醫院環境瓶身標籤／燈具／白牆與晃動精度須用授權照片副本校準。合成測試與 Windows 打包不等於現場模糊判讀驗收。
- 照片品質清單的滅火器檔名建議應重用 Organizer `_canonical_filename` 規則，不直接執行 Organizer 的全盤雜湊分析或任何 rename；同槽多圖只作人工核對提示，舊制放置盒不依新制槽位誤判。問題線索數不是去重後的照片數；所有新增異常類型應同步套用到篩選及 CSV/Excel 匯出，並維持手動品質掃描與設備異常單選隔離。
- 品質清單特例批次與 reconcile.SPECIAL_PERIODS 共用，不在特例中套用一般三槽位缺照、未辨識檔名或同槽多圖；特例本身不是品質異常，但原圖品質與人工覆核仍照常檢查。「特例資料夾」提供明確篩選，即使預設只顯示異常也允許使用者主動查看特例。棟別／編號異體字以 Organizer `_variant_issues` 提示，不自動改名；候選原因可安全匯出。
- 剪貼簿照片不得在 focus／mount／一般刷新時讀取 `navigator.clipboard.read()`。Windows pywebview 的明確「貼上照片」操作以 `js_api=ClipboardApi()` 取得 PIL 影像、限制 5000 萬像素與 100 MB PNG payload，僅回傳圖片位元組供前端既有預覽與確認，不提供任何讀剪貼簿後端 HTTP API、不落地寫原圖。一般瀏覽器只能透過原生 `paste` 事件 Ctrl+V 讀圖，按鈕改顯示置中的 FireLens 指引，不偽裝系統權限彈窗。Windows 圖形介面實際貼上仍需另行驗收。

## 照片瀏覽三欄獨立捲動

- 只有 `view === 'browse'` 時套用 `app-shell browse-layout` 的 `100dvh` 高度邊界；其他分頁仍照原本捲動。`.workspace` 必須 `min-height: 0`，資料樹／照片／資訊三欄的可見區各自捲動，禁止資料樹展開把整頁撐高；面板保留 `overscroll-behavior-y: contain`。
- 資料樹標題、筆數與搜尋欄固定；僅 `.tree-view` 滾動，保留鍵盤可聚焦、現有展開與選取狀態、`scrollIntoView` 定位；切換設備時照片面板回到頂部，但不得重設左樹捲動位置或照片資料。

## 資料與掃描

- 類別：滅火器、放置盒、燈具。
- 只將允許圖片副檔名視為照片；`desktop.ini` 等系統檔一律忽略。
- 副檔名比較不分大小寫。
- 滅火器槽位：`編號`、`藥劑`、`完成`；`有效日期` 已確認為 `藥劑` 別名；只做槽位辨識，不改真實檔名。
- 放置盒、燈具新制：`前`、`中`、`後`。
- 放置盒舊制 `新增N`／`新增-N`／`編號`／`完成` 只顯示，不依新制判缺漏。
- `5P 二氧化碳滅火器`、`壓力錶壞`、`新增5P 二氧化碳(含放置盒)` 是特例，不得直接判為多餘資料夾。
- 被改名照片以 SHA-256 辨識；多個候選時略過並回報，不猜測。
- 掃描採背景增量更新：以相對路徑、mtime 與檔案大小比對，只更新新增／變更／移除的 `item`、`photo`；未變動資料必須保留既有 id、SHA-256 與縮圖快取關聯。
- 同一根目錄同時間只允許一個掃描工作；自動掃描與手動掃描都必須可取消，掃描期間仍可瀏覽既有索引。
- 根目錄離線、不存在或無法讀取時不得清空既有索引；應保留舊快取並以繁體中文回報錯誤。
- 啟動時自動掃描預設開啟，預設最短間隔 5 分鐘；手動掃描不受自動掃描間隔限制。
- 掃描期間避免與寫入流程競爭：照片匯入、刪除、重新排序、建立資料夾與離線同步等寫入操作應暫停或明確阻擋；唯讀瀏覽不得被阻擋。

## 自動命名與匯入

- 滅火器：`編號.jpg`、`藥劑.jpg`、`完成.jpg`。
- 放置盒／燈具：`前.jpg`、`中.jpg`、`後.jpg`。
- 匯入一律複製，不修改來源。
- HEIC 匯入轉 JPG，但原始 HEIC 保持不變。
- 依 EXIF 方向校正，不做不必要的畫質破壞。
- 撞名不得覆蓋，只允許加序號或取消。
- 匯入與改名必須寫 `audit_log`。
- 既有照片人工改名／拖曳歸槽只允許同一設備資料夾內 rename，不重新編碼、不複製影像；必須先預覽 `原檔名 → 新檔名` 並以 SHA-256 驗證內容未變。
- 既有照片 rename 的新檔名只允許安全 basename，不得包含路徑、Windows 禁用字元／保留名稱或變更圖片副檔名；目標已存在時一律阻擋，不得覆蓋。
- 既有照片 rename 必須寫入 `rename_log` 與 `audit_log` 並可安全復原；根目錄離線、照片為雲端未下載佔位檔或掃描進行中時不得執行 rename。
- 設備資料夾更名只能於同一父資料夾內更改安全 basename；必須先預覽並由使用者確認，不得覆蓋同名目標或重編碼照片。需同步 `item`、`photo` 及 `item_issue` 路徑並記錄 `audit_log`，失敗時盡可能回滾磁碟與索引。Google Drive 已連線且無未下載佔位照片時可以更名；離線、掃描中、佔位照片、符號連結／reparse point 或待同步離線匯入時應阻擋。

## SQLite

- Windows 正式安裝版的 DB 必須放在安裝目錄下的 `data\firelens.sqlite3`；預設安裝路徑為 `%LOCALAPPDATA%\Programs\FireLens`，因此一般使用者可直接寫入。原始碼開發／測試仍可使用 `FIRELENS_DATA_DIR` 隔離資料。
- 不得只因 `sys.frozen` 或 EXE 所在位置就判定為正式安裝版；必須存在由安裝精靈建立的 `.firelens-installed` 標記。從沒有安裝精靈的歷史 v1.4.0 單一 EXE 線上更新到 v1.5.0 時，若沒有標記，必須繼續使用舊 `%LOCALAPPDATA%\FireLens\firelens.sqlite3`，直到使用者真正執行 setup，避免在下載／桌面等可攜 EXE 目錄旁建立正式 DB。
- 從舊版 `%LOCALAPPDATA%\FireLens\firelens.sqlite3` 搬遷到安裝目錄時，只能做安全 SQLite snapshot/copy；新 DB 通過 `PRAGMA quick_check` 後才切換，舊 DB 必須保留，不得自動刪除，搬遷失敗不得破壞原資料。
- schema 只做增量、可重複執行 migration。
- schema 更新前建立 SQLite backup 快照。
- 重要資料流程測試使用真實 SQLite，不用 mock 取代資料庫行為。
- 清冊是受保護持久資料：文字貼上需保存完整原始文字；Excel 至少保存來源檔名、SHA-256 與解析列。清冊 schema 只能增量 migration，不得為新增欄位重建 `ledger`／`ledger_row`。
- 設備異常分類字典 `issue_label` 與當前異常 `item_issue` 是獨立持久資料，不能混入 `reshoot_mark` 或只依賴掃描可能重建的 `item.id`。一台設備在某根目錄／相對路徑下最多只能標記一項異常；改選取代、清除取消，不設「已改善」流程。分類名稱可自訂與停用，所有根目錄共用，統計依根目錄篩選；來源離線或設備索引消失不能自動刪除紀錄。
- 刪除清冊只允許刪除該清冊與其 `ledger_row`／`reshoot_mark` 關聯資料，不得影響照片、根目錄或其他清冊；重新命名清冊必須保留原 `ledger_id` 與解析列。

## 清冊核對規則

- **設備編號是照片核對的主鍵與唯一必要欄位**。`棟別樓層` 只用於顯示、分組、篩選與人工辨識，屬選填輔助資訊；不得把 `棟別樓層` 是否存在或是否完全一致變成能否核對照片的必要條件。
- 舊資料庫欄位 `section` 可為相容性保留，但新 UI 一律顯示為「棟別樓層」；不得只為改欄位名稱破壞性重建 `ledger`／`ledger_row`。
- 新清冊流程不再要求或顯示「型式規格」「上次更換日」；既有清冊已保存的舊欄位與 `raw_json` 必須保留相容，不得因新流程而刪除歷史資料。
- 文字貼上至少支援：單欄「一行一個完整設備編號」，以及 Tab 分隔雙欄「棟別樓層 + 完整設備編號」。Excel 至少支援同樣的單欄／雙欄資料，並相容有標題與無標題格式。
- Excel 標題需相容「棟別樓層／區段」與「設備編號／編號／滅火器編號」等既有名稱；其他多餘欄位不得阻擋匯入。沒有棟別樓層時仍必須可正常分析與核對。
- 匯入前可做安全正規化：移除前後空白、整理 Tab／多餘空白、英文字母大小寫正規化；不得擅自改寫設備編號的實質內容、補零、猜樓層或由代碼猜完整棟別名稱。
- 同一清冊的重複設備編號必須在正式匯入前提示；棟別樓層與設備編號看似不一致時只做非阻擋警告，由使用者判斷，不得自行修正或拒絕核對。
- 核對結果至少區分「完整」「缺部分照片」「完全無照片」「找不到設備資料夾」「有未對應／舊制照片」，並支援依棟別樓層與缺失類型篩選，以及匯出缺失清單。
- 清冊核對結果、統計、補拍清單與 CSV／Excel 缺失匯出只能包含目前清冊 `ledger_row` 的設備編號；不得將根目錄中未列入清冊的其他設備、其他月份或放置盒／燈具資料夾自動追加為清冊缺失。未列入清冊不等於找不到設備資料夾；照片瀏覽與異常統計維持獨立。
- 清冊缺失 CSV／Excel 匯出在 Windows 桌面版必須真正產生檔案並顯示位置／失敗原因，不得僅依賴 WebView2 對 `Content-Disposition: attachment` 連結的預設行為；匯出採安全、非覆寫的本機儲存方式。既有瀏覽器 GET 下載 API 仍保留。
- 清冊名稱可依年月／類別提出預填建議，但使用者可修改；第一次使用清冊功能需提供短引導，且之後必須能再次開啟「查看範例／使用教學」。

## M17 新增架構限制

- 核對必須由目前選取的清冊、類別（滅火器／放置盒／燈具）及選填月份共同限定。只有完整設備編號精確命中失敗時，才可忽略資料夾名稱末尾完整括號備註；不得用前綴模糊比對。多個候選不任意選定。
- 匯出檔案應由後端在受控本機目錄安全建立，開啟動作只接受本次後端產生的短期不透明 token，不接受使用者輸入路徑或 shell 指令。
- 照片樹新增檔案必須繼續使用既有安全儲存 API，不得繞過離線、權限、命名、掃描或同名防護。
- Google Drive 多人同步的異常標記需單獨事件紀錄、衝突偵測、本機多版本備份及恢復流程全部通過合成資料驗收後才允許接入真實同步根目錄；在此之前不得直接共享 SQLite 或覆寫雲端單一 JSON。

## 照片槽位操作工具列響應式規則

- PhotoTile 照片工具列永遠要讓所有操作（換圖／重新命名／移動交換／刪除，以及多圖排序）完整顯示，不可以把 flex 單排按鈕藏到 photo-tile 的 overflow:hidden 下；文字過長應換行而不是被裁切。
- 照片按鈕格線依**卡片自身容器寬度**在一、二、四欄間調整，照片槽位牆依**照片面板容器寬度**在三、二、一欄間切換；不能只依瀏覽器全視窗寬度做媒體查詢。縮放、深色模式和鍵盤操作要維持可用。
- UI 響應式修正不得影響既有破壞性操作確認或後端照片儲存／改名／交換行為；以靜態元件／樣式回歸測試及 Windows 實機點擊驗收區別完成程度。

## M17 照片槽位安全移動／交換與復原

- 照片槽位交換必須先依 photo_id + item_id + target_slot + 明確 target_photo_id 預覽，不能跨設備、根目錄或選錯照片；有多張目的照片時使用者需指定交換對象，不可自動猜測。
- 交換是同設備資料夾實體檔案的名稱交換／移動，保留原始位元組和副檔名，不允許靜默覆蓋，必須先比對來源與目的 SHA-256、檔名碰撞、雲端占位及是否掃描中；前端只有確認後才呼叫執行 API。
- 多步改名必須使用不覆蓋的暫存檔名與反向復原，更新 SQLite 索引、audit_log 與 slot_transfer_log；Schema v9 migration 必須於升級前備份舊資料庫，後續不可破壞性重建既有資料。
- 使用者可從本機交換紀錄復原，但復原前必須重驗原檔是否已由其他人修改／占用；Google Drive 桌面同步不是跨電腦交易鎖，正式多人協作安全性不能只靠本地 rollback 測試宣稱驗證。

## M17 Google Drive 限制存取與 OAuth 唯讀／編輯規則

- 上方「查看滅火器資料」頁籤僅允許 Google Desktop OAuth 使用者讀取限制存取的指定 Drive 資料夾，或經明確編輯授權後修改其中的試算表；舊公開 API Key／匿名 iframe 與手動網址存取已停用，絕不在授權失敗時自動退回公開模式。
- 使用 Google 官方桌面 OAuth 授權碼、PKCE S256、隨機 state 與系統瀏覽器 loopback callback；不使用內嵌 WebView 蒐集 Google 登入資訊，不需 Client Secret。已設定的 Client ID 為公開識別碼，Google 帳號密碼／Access Token／Refresh Token 絕不可寫入 Git、UI、一般日誌或同步資料夾。
- 為了「列出私人資料夾裡所有 Sheets」，預設唯讀使用 Google Drive `drive.metadata.readonly`（**restricted scope**）及 Sheets `spreadsheets.readonly`（sensitive scope），只顯示指定資料夾內有權限的清單。正式發佈前須確認同意畫面 Data Access scopes、測試使用者與 Google 驗證要求；若採 Google Picker／drive.file 改造也要先寫新 TASKS。
- 在本機讀取 Google API 僅限官方 HTTPS 網域、固定目標資料夾、有限的頁數／表格列數和大小；禁止任意 spreadsheet ID 繞過清單權限檢查。Google 表格內容以 React 純文字顯示，不能插入 HTML。
- 已完成 Google OAuth 登入時，進入「查看滅火器資料」頁籤應自動載入私人 Google Sheets 清單；OAuth 成功從未登入變為已登入時亦自動取得一次。禁止因編輯 scope 更新、狀態輪詢造成反覆刷新；自動清單更新只改清單，不可清除已選 Sheet/Tab、當前資料頁或未儲存編輯草稿。舊請求在登出或離開頁面後不得回寫畫面；手動重新整理保留作為故障重試。

- 編輯模式必須使用系統瀏覽器重新要求全部必要 OAuth scopes（包含 Sheets spreadsheets 寫入權限），並完成 PKCE/state 授權，取消／失敗不可刪除原唯讀 token。Google Desktop OAuth 官方不支援 incremental authorization，故實際需再次要求包含原唯讀與編輯的完整 scope 集，不能使用增量授權說法。只有 token 含寫入 scope 且 Google Drive ACL 允許時才可儲存。
- Google 私人試算表儲存限定單一儲存格、既有目標資料夾內 Sheet/Tab、A~AD 欄、1~100000 列、最多 2000 字元；必須先顯示草稿與二次確認，前端預設唯讀，後端寫入前再讀原值，不符回 409。使用 RAW 字串寫入避免公式執行；禁止靜默覆蓋。Google Sheets values.update 無跨使用者原子 CAS，極短時間競爭仍存在，必須提醒並要求重要資料使用 Google 版本歷史。
- 點選 Google 試算表儲存格後，草稿編輯器必須出現在使用者目前可見的視窗中央（可存取的 modal），不可置於獨立捲動的表格最底部導致看似不能編輯。二次確認原值／新值與離開草稿警示不可取消。
- 支援「使用 Google 試算表開啟」的原生網頁編輯替代方案：只允許使用後端確定屬於目標私人資料夾的試算表 ID 與工作表 gid，由本機 Python 在使用者操作後開啟固定 Google HTTPS docs.google.com 官方網址。禁止前端提交任意外部 URL、禁止將 OAuth Access Token/Client Secret 拼入 URL、禁止為此將私人 Sheet 公開發布，亦不允許繞過 WebView2 的 iframe／Google OAuth 安全限制。Google 官方式發布後嵌入的 iframe 是檢視版，不等於原生可編輯 Sheets。

- Sheets 編輯 API PUT 必須驗證桌面 session／Origin、Google OAuth 寫入 scope 和真實 Google ACL；403／409／502 不可宣稱成功，操作不得把 Token、Google 私人內容、原始 HTTP 回應寫入一般日誌。
- Google Sheets A～AD 欄標頭與多格選取／Ctrl+C 必須在唯讀及編輯模式都可使用，複製仍只需要既有 OAuth 唯讀 scope；整欄複製須依工作表 rowCount 分批從 Google API 讀取，禁止只複製當前 100 列或默默截斷。單次範圍上限 20000 列／100000 格、每批最多 200 列；超限／回應不完整／HTTP 錯誤／取消時不得將部分資料放進剪貼簿或回報成功。TSV 按 Tab 與換行分隔，多格內的 Tab／換行／引號需正確轉義，保留中間空白列和字串前置零、中文異體字，不記錄私人設備代碼；整欄可選含／不含第一列標題。剪貼簿寫入失敗保留本機暫存以利使用者再按複製，不可宣稱成功。


- OAuth Refresh Token 以 Windows 使用者 DPAPI 加密，儲存在使用者本機 LocalAppData，不與同步相片、SQLite 內容共享；登出立即清除本機存檔，遠端撤銷若因網路失敗須清楚提醒。Google 測試版授權可能有期限限制。
- Windows 正式桌面安全模式下，所有私人 Google API（讀取 GET 或寫入 POST）必須具備 FireLens 原有 HttpOnly session cookie，並拒絕非 loopback Origin；不以「GET 不修改資料」為由放寬私人資料存取。
- Google OAuth 失敗必須區分授權回呼／Token 授權碼交換／Token 續期／Drive 資料讀取階段。可顯示經程式碼白名單核准的官方 `error` 代碼及繁中建議，但不可把 Google `error_description`、原始 HTTP 回應、授權碼、Token、Cookie、私人文件名稱等傳入 UI、紀錄或錯誤堆疊訊息；只有 HTTP 400 不足以推論 OAuth 同意範圍或資料夾權限有誤。
- FireLens「設定 → Google OAuth 設定」支援 Client ID 唯讀、Client Secret 密碼欄、儲存／覆寫／清除，使用 Windows DPAPI 加密到目前使用者 LocalAppData 的獨立檔案（不放 SQLite／同步資料夾／前端 bundle）。GET 只回傳是否已設定，POST／DELETE 必須通過 desktop session 與 Origin 保護。OAuth 授權碼交換／Refresh Token 優先讀此設定，再退回相容性環境變數 `FIRELENS_GOOGLE_CLIENT_SECRET`；未設定仍可用 PKCE-only。Client Secret 並非真正安全的桌面端機密，絕不可回傳原文、存入 Git、一般日誌、回呼網址或前端設定。
- 任何「真實 Google 登入、私人資料夾列檔、讀取」之完成宣稱，都需本人 Windows 環境實機授權與驗收；合成 HTTP 測試只能證明程式邏輯，不代表真實帳號連線成功。

## M17 資料樹展開與新增資料夾定位規則

- 使用者手動展開／收合資料樹的狀態以**完整分類／年份／月份／棟別層級 path key** 記錄，避免重名月份／棟別互相污染；不同根目錄有獨立的展開狀態。
- 透過左側樹狀「＋」、右鍵選單、快速新增建立年份、月份、棟別或設備編號成功後，只展開新節點路徑上的必要祖先，定位並高亮新節點；不再呼叫全樹 expandAll。先前已展開的其他分支繼續展開，已收合的維持收合。失敗／取消時不得改動任何展開集合。
- 一般重新掃描／清單刷新只更新樹內容，不重設使用者既有展開狀態；搜尋時允許暫時展開符合搜尋的視覺分支，但不得永久寫入或覆蓋使用者的展開選擇。新增與折疊操作不得改動真實照片或設備資料。

## M17-K Windows 系統附屬檔與共享事件隔離

- Windows／Google Drive Desktop 可能在共享事件 events 目錄建立桌面系統設定檔 desktop.ini，允許只略過此明確已知的普通檔案（不分大小寫），不刪除、不移動、不修改其內容或時間戳，也不計入事件上限。
- events 目錄內其他未知檔案、子目錄、符號連結、格式異常的 UUID JSON 或 SHA-256／因果鏈失敗，仍停止匯入並保留本機異常與備份，不得把整個目錄的未知檔案一概略過。
- 對現場事件目錄只能用唯讀診斷；檔案讀取 Bug 必須先用合成資料測試，再進行 Windows 安裝版驗證。

## M17-J Google Drive 電腦版多人同步安全規則

- 共用異常必須明確選取根目錄並由使用者確認啟用；在照片根目錄另建 FireLens-共享異常資料/events，只存不可變 JSON 事件，嚴禁直接共用 SQLite／照片／清冊／憑證。
- 每台本機有獨立穩定 device_id。設備 key 是分類與根目錄內相對路徑，分類使用獨立穩定 GUID，不能以跨電腦不同的 item.id/label_id 比對。事件檔使用 UUID4、因果 parents、SHA256、原子寫入；每筆上限 32 KiB，最多 10000 筆。
- 離線寫入先保留本機 outbox；開機與約每兩分鐘讀取 Google Drive Desktop 同步資料夾。只證明本機讀取並驗證，不等於 Google 伺服器已上傳。
- 並行不同異常可安全合併；同設備／同分類有不同並行版本時不自動最後寫入者勝出，必須由使用者選擇，且保留歷史。未知、破損、誤刪、遺失已知事件、缺少 parent 或不可讀時停止套用且不清空本機設備異常。
- 首次啟用、每次採納新事件與手動復原前保留有 SHA256 校驗的不覆蓋歷史快照在 LOCALAPPDATA/FireLens/backups 或 FIRELENS_DATA_DIR/backups；復原需人工確認，復原後暫停同步直到人工確認。回補雲端被刪事件只在人工明確確認後使用本機已驗證 archive。
- 共享事件資料及本機備份不納入 Git、不寫入一般日誌；端點使用既有 Windows 桌面 cookie、Host、Origin 保護，實機雙 Windows＋Google Drive 的網路及同步延遲仍須另外驗收。

## M17 清冊核對分類隔離與月份範圍規則

- 「清冊與核對範圍」必須明確選擇照片根目錄、設備類別（滅火器／放置盒／燈具）、清冊、可選月份／批次；不允許跨設備類別搜尋、重複配對或將照片資料夾中不在清冊內的設備當作清冊缺失。預設類別滅火器、月份為「全部月份／批次」；每次更換類別或根目錄必須清除舊月份，不可沿用另一分類的批次。
- 可選月份清單取自目前 root_id 掃描／已登記的樹狀資料，只列出 category_code 對應的 period，不顯示其他類別批次；清單不存在時可以選「全部月份／批次」。不得僅依輸入文字或模糊關鍵字替代真正類別限制。
- 核對與缺失匯出 API 已使用 root_id + category_code + optional period 限縮，滅火器沿用編號／藥劑／完成槽位，盒／燈沿用前／中／後；清冊與既有 SQLite 不永久強制綁定類別。切換範圍或清冊後立即清除結果及開檔 token，以請求版本閘門拒絕舊核對／匯出回應覆蓋新的分類選擇；結果要明示實際核對的根目錄、設備類別、月份及清冊名稱。
- 只有合成 SQLite／照片副本可用來驗證三類同編號、不同月份、缺照片、清冊外設備及 CSV／XLSX 的分類一致性，不能讀寫使用者真實照片和清冊作修改測試；實際 Windows UI 的分類選單和匯出仍需使用者自行驗收。

## M17 異常統計匯出安全與一致性規則

- 異常統計 CSV／XLSX 匯出只取畫面所選根目錄、異常分類、棟別與搜尋關鍵字。前端匯出時凍結快照和可見筆數；後端 expected_row_count 在存檔前核對，不符回 409，不建立不一致檔案。切換篩選或刷新需讓舊匯出開檔能力失效。
- CSV 使用 UTF-8 BOM，XLSX 使用 openpyxl 並設標題、自動篩選與欄寬；防試算表公式注入並保留設備編號與中文。0 筆不匯出；使用安全匯出資料夾與隨機檔名，絕不覆蓋原檔或把敏感來源路徑寫入 Git。
- 開檔與 Explorer 功能只能使用本機 ExportRegistry 核發的最新不透明 token，不接受任意路徑。真實 Windows UI 與 Explorer 操作仍需實機驗收。

## M17 圖片剪貼簿匯入安全規則

- LINE 複製圖片貼上需先明確選定設備與槽位；不干擾文字輸入控制項的 Ctrl+V。非圖片剪貼簿不得寫入；圖片必須預覽確認後沿用既有安全照片匯入 API（不得由前端任意寫入檔案或覆蓋）。切換設備或根目錄時取消過期貼上。
- Chrome 與 Windows WebView2 的 Clipboard API 權限能力可能不同，沒有觀察過真實 LINE Windows 來源前，不得宣稱百分之百可貼或強制停用權限未知但可能可用的貼上按鈕。剪貼簿格式偵測只在安全許可時執行，離線與掃描安全規則沿用既有照片匯入流程。

## 桌面與服務安全

- FastAPI 內部服務只綁 loopback 隨機埠。
- 保留 session cookie、Host、Origin 檢查。
- SQLite 為各台 Windows 電腦本機索引，不允許多台電腦直接共同寫入同一 SQLite；Google Drive 共用異常紀錄需等到獨立事件合併、衝突偵測及多版本備份通過驗證後才可開啟。
- 錯誤訊息使用繁體中文；日誌寫 `%LOCALAPPDATA%\<應用名>\logs`。
- 線上更新 UI 可以簡化成一鍵流程，但不得降低安全鏈：正式 Release 必須通過 Ed25519 manifest 簽章、版本／檔名／大小、SHA-256 與下載後 EXE self-test；真正替換 EXE 前 `schedule_install` 還必須再次驗證本機 manifest 簽章、檔案 SHA-256 與 EXE self-test。
- 更新下載／驗證同時間只允許一個工作；任一階段失敗或使用者取消最終確認時不得關閉或替換目前 EXE。正式安裝版線上更新不得修改 `{app}\data`、`.firelens-installed` 或安裝資訊；沒有 installer marker 的 portable/raw EXE 仍維持既有 LocalAppData DB 相容路徑。
- 正式線上更新必須由獨立 `FireLensUpdater.exe` 執行替換；主程式只有在 transaction-bound `ready` handshake 驗證成功後才可退出，禁止恢復成「啟動背景程序後固定延遲、無條件 `os._exit`」的舊同步方式。PyInstaller one-file 的 bootloader PID 與 Python helper PID 可能不同，不得以兩者必須相等作為 READY 判定。
- updater 必須等待舊 FireLens PID／EXE lock、再次驗證 staged SHA-256、建立並驗證 backup、替換後驗證實際目標 EXE SHA-256；新版必須在桌面 UI DOM ready 後以相同 transaction 回報 `healthy`，不能只用「程序存活 N 秒」判定成功。新版 crash、HEALTHY timeout 或替換錯誤必須 rollback；rollback 失敗時保留 backup、transaction state 與 log 供人工復原。
- Installer 必須部署與主 EXE 相符的 `FireLensUpdater.exe`；portable/raw 單檔模式則由主 EXE 的受信任內嵌 payload 解出 helper，並先核對 build 時固定的 helper SHA-256 才能執行。helper 不作為獨立下載 Release 資產，也不得繞過既有 Ed25519 Release 驗證鏈。
- 更新器變更的正式驗收必須由**打包後 `FireLens.exe` 本身**發起完整更新交易，至少涵蓋 portable、Inno Setup 安裝版、READY/HEALTHY、rollback 與故障注入；直接單獨執行 helper／腳本只能算局部測試，不能宣稱線上更新 E2E 通過。
- 更新交易狀態 JSON 必須使用同一目錄暫存檔、fsync 後原子替換；Windows 如遇短暫共享鎖 WinError 5／32／33，允許在短期限時內重試 `os.replace`，非鎖定錯誤立刻失敗、超時保留原狀態與既有 rollback，禁止放寬 transaction ID、簽章、READY／HEALTHY 檢查。

## UI / UX

- 三欄式：樹狀瀏覽／槽位牆／資訊欄。
- 辦公室滑鼠鍵盤與拖放優先，同時保留基本鍵盤、觸控與 accessible name。
- 大量清單用虛擬捲動；縮圖背景產生；掃描可取消並支援增量。
- 「新增編號資料夾」在有根目錄且尚無使用者偏好時預設展開；展開／收合狀態要持久化，按鈕需提供明確繁體中文提示、`aria-expanded` 與 `aria-controls`。
- 破壞性或批次操作使用應用內確認介面。
- 上方導航列順序為「照片瀏覽｜清冊核對｜異常統計｜整理工具｜設定｜查看滅火器資料」；「查看滅火器資料」必須是設定右側獨立頁籤，不得放回設定頁內容；「異常統計」僅呈現設備異常分類及清單（每台只計一個分類），點設備可回到照片牆，不與清冊缺照片分類混淆。

## 開發工作方式

1. 先讀將修改的檔案與相依程式，再動手。
2. 只做目前里程碑範圍，不順手擴充無關功能。
3. 每項功能都要有可驗證條件；能寫測試就建立測試或最小驗證案例。
4. 迭代先跑最小測試；里程碑完成前跑 Ruff、pytest、Vitest、TypeScript／frontend build。
5. UI 變更要實際啟動並視覺驗證。
6. 影響桌面版、更新器或打包流程時，必須測試打包後 EXE。
7. 正式 Windows build 必須同時產生 Inno Setup 安裝精靈 `FireLens-<版本>-setup.exe`；安裝器預設採每使用者安裝、不要求系統管理員權限，建立開始功能表捷徑，桌面捷徑為可選，安裝／升級不得刪除 `{app}\data` 使用者資料。安裝精靈的系統頁面、按鈕與 FireLens 自訂提示都必須完整使用繁體中文；所需 Inno Setup 繁中語言資源應隨專案受版本控制，不得依賴開發電腦是否剛好安裝額外語言檔。
8. 打包後 `FireLens.exe --self-test` 必須強制使用臨時 `FIRELENS_DATA_DIR`，並以可等待 GUI subsystem 程序的方式（例如 `Start-Process -Wait -PassThru`）取得真正 exit code；不得因 raw EXE／安裝版判定差異而讀寫使用者真正的 LocalAppData 或 `{app}\data` DB，也不得在 EXE 尚未結束時誤判 self-test 通過。
9. 完成程式修改後依全域規則重建 graphify 圖。目前安裝的 Graphify CLI 沒有公開 `build/rebuild` 子命令；使用安裝套件的 `graphify.watch._rebuild_code(Path.cwd())` 對專案根目錄重建，並確認 `graphify-out/graph.json` 與 `graphify-out/GRAPH_REPORT.md` 都成功更新。Graphify 產物會包含本機絕對路徑，因此 `graphify-out/` 固定只留在本機並由 `.gitignore` 排除，禁止提交 Git。不得把重建失敗當成完成。
10. 未閱讀實際驗證輸出、且未同步完成 `AGENTS.md`／`TASKS.md` 前，不宣稱完成。

## M0 特別規則

- M0 只允許唯讀盤點真實資料，以及建立專案文件／報告。
- 別名與髒檔名只能產出草稿與建議，未經使用者確認不得套用到真實資料。
- M0 驗收前後比對照片資料 metadata fingerprint 與 `數據.xlsx` SHA-256，確認來源資料未改變。

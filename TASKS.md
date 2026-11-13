# 滅火器燈具照片管理系統 任務文件

狀態：**M18 照片品質檢查已開發並通過合成測試與 Windows 打包，待實際 Windows UI／現場影像門檻校準；M17 與其他歷史功能仍有部分實機驗收項目**。目前版本 v1.11.0（M19-D／M19-E／M19-F／M19-I MINOR 開發版，包含頁面狀態保留、貼上加速、大圖預覽、引導掃描及照片槽位標籤管理，尚未正式發佈；歷史 v1.10.1 僅為未發布開發版）；歷史 Release v1.10.0 已於 2026-11-13 由 GitHub Actions 正式發布（真實 WebView2／Google Drive 操作仍待實機驗收）；歷史 v1.9.0 已於 2026-11-12 由 GitHub Actions 正式發布為 Release（實機仍需驗收）；歷史 v1.8.0 已於 2026-11-08 由 GitHub Actions 正式發布。開發前還原點：Git commit 0f9bc7d / backup/pre-m17-20261107。歷史 v1.7.0 已正式發布至 GitHub Release。歷史 v1.6.0 與 v1.5.0 已正式發布至 GitHub Release。
M14 歷史開發版本：v1.6.0。
M15 歷史開發版本：v1.6.1（PATCH，修正線上更新器實機失敗）。

## M19-I 設定頁「各類別照片槽位」改為可操作標籤介面（2026-11-14，已實作並通過回歸，實機待驗收）

**使用者截圖與修正前需求**：原本 `frontend/src/SettingsView.tsx` 的「各類別照片槽位（可自訂）」、「槽位顯示順序」與「自訂槽位（選填）」分別是以頓號／逗號分隔的文字輸入框，如「編號、藥劑、完成」「前、中、後」。使用者希望**改為一個個獨立的標籤（Chip／Tag）管理**，不需要背分隔符號或手動修改整串文字。本功能已完成程式與自動化回歸：以每類別獨立 Chip 卡片取代文字串，保留既有三組設定語意、資料與原始照片，版本合併至尚未發布的 v1.11.0 MINOR；未經使用者指示不推送／Tag／發 Release。

- [x] **I-01 各設備類別改為標籤管理卡片**：在「設定 → 介面與快取 → 各類別照片槽位」針對滅火器、放置盒、燈具、水帶以及未來新建立的動態分類，各自顯示獨立卡片；既有「編號」「藥劑」「完成」或「前」「中」「後」以**可辨識的圓角標籤**呈現，帶拖曳把手、改名操作、移除（×）操作與末尾的「＋新增槽位」；按新增可直接輸入**單一名稱**並 Enter／按確認生成一枚標籤，Esc 取消，無須輸入「、」或「,」。可滑鼠拖曳排序，且提供鍵盤／上下移動按鈕，不依賴拖曳才能使用；完成後順序立即在草稿 UI 反映。新增、改名、移除、排序僅影響當前類別，不跨設備類別混用。
- [x] **I-02「槽位顯示順序」改成可拖曳排序標籤**：移除現有需整串輸入「編號、藥劑、完成」的文字框；改成**只排列已存在／合法的槽位標籤**，既有順序可拖曳或按左／右鍵調整，並在各類別卡片中同步展示照片牆順序預覽；不得藉由排序介面偷偷建立不存在的新槽位。排序時按實際照片牆顯示的合法必需槽位＋自訂槽位規則處理，新增／移除槽位後要同步校對其排序草稿，不可留失效名稱，也不能重複顯示同張照片。確認 `slot_order` 與各類別槽位 API 的先後儲存規則，避免前端兩份草稿互相覆蓋。
- [x] **I-03「自訂槽位（選填）」也使用標籤**：例如「側面」「壓力錶」「補充」等自訂槽位，可按「＋新增自訂槽位」輸入後生成可改名、移除、排序的標籤；與**參與缺漏判斷的基本槽位**在視覺上清楚區隔（例如不同標籤風格與說明），維持原本「自訂槽位不影響缺漏判定」的既有行為，不能把選填槽位誤算為缺照；既有自訂名稱應從設定直接載入成標籤，絕不可因初次載入將其清空。
- [x] **I-04 編輯安全性與儲存機制**：標籤的新增／改名／刪除／排序先在前端草稿中操作，沿用目前「儲存某類別照片槽位」與「儲存介面與快取設定」的既有責任，但需明確提示尚未儲存與提供取消變更／還原；儲存失敗不得把 UI 顯示為已成功。空白、重複、只含分隔符號、過長或不合法名稱即時驗證；同一類別在基本槽位與選填槽位之間有重名時先提示使用者，不要靜默建立混淆項目。**改名／刪除可能使舊照片被列為「未對應照片」**時，沿用既有安全確認機制，列出受影響槽位及可能影響，未確認不得儲存；絕不刪改原始照片、檔名、SHA-256 指紋或清冊資料。舊版以字串清單保存的資料應能無損轉成標籤 UI 並照原有後端資料格式儲存，避免破壞自訂類別及檔名同義詞對應。
- [x] **I-04a 同類別原子儲存（實作補充）**：現有 `update_category_slots()` 會順便重置同類別 `slot_order`，而一般 `saveSettings()` 另寫 `custom_slots`，不能只改 UI 後分兩次寫入而可能部分成功。擴充既有 `/api/categories/{code}/slots` 更新請求為可選 `slot_order`／`custom_slots`，在同一 SQLite 交易中完整驗證基本槽位、合法排序、選填槽位（含別名衝突），一起更新類別／設定／設備狀態；未傳新欄位時必須維持舊客戶端相容，失敗全部回滾。前端每類別一個「儲存槽位設定」按鈕，成功後重新讀取權威 category/settings；全域「儲存介面與快取設定」不得覆蓋尚未儲存的 Chip 草稿或剛儲存成功的新順序。補上 API 原子性、版本相容與 UI 儲存測試。
- [x] **I-05 自動化、Windows 打包與更新器驗證**：實作時先寫測試再施工／完成後完整回歸。測試滅火器與水帶各自新增／改名／移除／排序、同一槽位多張照片、基本與選填區分、重複／空白／無效名稱阻止、刷新後值持久、未儲存離開／API 失敗復原、圖片與未對應照片不被刪改、鍵盤操作與窄視窗 RWD；執行 Vitest、TypeScript／Vite、pytest、Ruff、format、版本一致性與 Windows EXE／繁中安裝程式及更新器 E2E，更新 README／AGENTS。本項只計自動化與封裝驗證；真實 WebView2／Google Drive 操作沒有執行，另由 I-06 保留 [ ]，不得將合成測試當實機驗收。

- [ ] **I-06 真實 Windows WebView2／Google Drive 人工驗收**：使用授權測試資料在 Windows 11 視窗中實際操作基本／選填 Chip 的滑鼠拖放、鍵盤移動、改名／移除確認、存檔、分類切換、縮放與深淺色；驗證關閉／重新開啟後設定持久、無誤刪原圖、未對應照片及缺照判定正確。合成測試、HTML 靜態輸出及打包 E2E 不等於此項實機驗收，未實際看見結果保持 `[ ]`。

**M19-I 自動化與打包驗證結果（2026-11-14，Windows 11）**：`frontend/src/SlotChipEditor.tsx` 新增可新增／改名／刪除／拖曳／箭頭排序的 Chip 元件，三種型態分別為 required／order／optional，附名稱／重名／別名校驗；`SettingsView.tsx` 分類獨立卡片與順序預覽、未儲存警示／還原、不同類別草稿在重新載入時保留。後端 `backend/app/settings.py` 與 `backend/app/admin.py` 於既有槽位 API 同交易驗證 `slots`、`slot_order`、`custom_slots`、照片槽位索引，拒絕失效排序／重名／未確認移除選填槽位，保留舊版不傳新欄位的相容行為。測試採**合成設備／照片**：新增 `tests/test_m19_slot_chips.py` 5 項（寫入／回讀、自訂槽位刪除二次確認、原圖位元組不變、失敗回滾、舊 API 相容）、`frontend/src/slotChips.test.tsx` 9 項（SSR 標籤輸出、欄位語意、排序純函數、非法名稱、儲存路徑和其他類別草稿不重置）；原有 M19 前端合約測試更新、未停用原測試。完整 **`uv run --locked pytest -q`：239 passed／1 項既有 Starlette 警告**，**`npm run test -- --run`：105 passed／25 個測試檔**，`uv run --locked ruff check .`、`uv run --locked ruff format --check .`（85 files）、`npm run build` TypeScript/Vite、`uv run --locked python packaging/check_version_consistency.py` 皆成功（**v1.11.0** 沿用未發布 MINOR，不重複升版）。Graphify `graphify.watch._rebuild_code` 成功：1,166 nodes／3,070 edges／74 communities，產物 `graphify-out` 不提交。Windows `powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build.ps1` **Exit Code 0**：`dist/FireLens.exe`、`dist/installer/FireLens-1.11.0-setup.exe` 成功建置、繁中 Inno Setup Verification successful、portable／installer／READY／HEALTHY／rollback／injected failures 更新器 E2E passed；此次本機 setup SHA-256 **D1D4D82BD006C2B4FAFB52120848398788A1FDF756455A55BE5257E331E84CA3**。未進行真實 WebView2 指標點擊／Google Drive/現場照片測試，**I-06 維持 [ ]**；本輪不推送 GitHub、不建 Tag、不發 Release。

## M19-H A／B 兩台電腦異常同步：合併透明化與實機驗收（2026-11-13，僅討論／寫 TASKS，尚未實作）

**使用者情境**：A 電腦有自己登錄的異常設備清單，B 電腦也有獨立清單且近期新增或修改紀錄；A 執行「異常同步」應保留 A 原本設備異常，同時取得 B 的更新，不能整份覆蓋。**現況經唯讀檢查**：`backend/app/shared_issues.py` 已採用每次變更獨立 UUID＋SHA256 事件、以 `category_code + item_relative_path` 為設備鍵、`_merged_view` 依事件繼承關係合併並偵測衝突、`_apply` 僅依有效事件逐筆 upsert/delete、套用前先本機備份；`tests/test_shared_issues.py` 已有雙用戶端合成測試。非同一設備的新增／異動可合併；同一設備各自並行不同值必須人工選版本，不能默默用最後修改時間覆蓋。**限制**：Google Drive 桌面版雲端上傳／下載完成不由 FireLens 控制，現在的「已讀取」只表示本機驗證，不能保證 B 的資料已傳到 A；尚未用兩台真實 Windows 電腦完整驗收。本次只增補驗收與可視化規格，**不要重做既有事件合併、不修改任何程式／版本／Git／Release**。

- [ ] **H-01 逐筆合併語意再驗證**：以 A 設備甲＝「瓶身超過10年」、B 設備乙＝「壓力錶故障」且雙方資料庫不同為例，A／B 同步後都應同時看到甲＋乙；B 隔日新增丙，A 再同步只新增丙、不清空甲，不以 B 缺少甲就視為甲已刪除。原本應用的設備異常**每台只能有一個異常**，同一台 B 提供較新且繼承 A 版本的單筆更新可正常更新，非全資料表覆蓋；需驗證兩台初次啟用前已有不同本機資料、交換順序、重啟及 B 資料尚未上傳的情況。
- [ ] **H-02 同設備衝突不得自動覆蓋**：A、B 在離線或未收到對方最新事件時，對同一設備登錄不同異常或其中一方清除異常，須顯示「版本衝突」並保留兩方歷史、裝置識別、編輯時間及分類名稱（UI 不能只露出難懂的 `label_guid`／JSON）；讓使用者明確選「採用 A／採用 B」，取消不變更該設備；解決後產生新事件並讓另一台同步取得一致結果。同一筆相同值更新與異常分類新增／更名／停用的跨機差異，也需驗證不會誤刪既有分類。
- [ ] **H-03 同步結果可視化（規劃新增 UI）**：在「統計／Google Drive 多人異常同步與本機備份」中，提供可理解的「本機異常總筆數」、「此次從共用事件新增 X／更新 Y／清除 Z／衝突 W」、「本機待上傳事件 N」、「上次**本機讀取**時間」及同步前後差異明細／來源裝置，讓 A 清楚看到 B 的哪些資料已合併；如果 B 尚未上傳、共享根目錄離線、事件缺漏或同步失敗，顯示醒目且正確的狀態，**不宣稱雲端同步完成**。高風險清除／衝突解決應先顯示影響設備再確認；與 M19-G 統一美化的置中 Dialog 規格共用。
- [ ] **H-03a「立即同步」結果摘要**：使用者在 A 電腦按「立即同步」後，畫面直接顯示「本次同步：新增 X 筆｜更新 Y 筆｜清除 Z 筆｜衝突 W 筆」，另列「本機異常設備總數 N 台」、「本機待上傳事件數 M」及同步時間。**新增／更新／清除以本次實際套用至本機 SQLite 的設備異常前後差異計數**，不是已讀取的事件數、分類數或歷史事件數；重複按「立即同步」而沒有新變更時必須顯示 0 筆，不能重複計數。
- [ ] **H-03b 可展開的設備明細**：摘要下增加「查看本次變更明細」，逐台列出設備類別、設備編號、棟別／位置、變更種類、同步前異常 → 同步後異常、來源裝置及事件日期；提供新增／更新／清除／衝突分類，方便 A 對照 B 本次更新的設備。若設備名稱或照片資料尚未同步，應保留可核對的安全設備識別，不以猜測補上名稱；沒有變動時顯示「本次沒有新的設備異常變更」。
- [ ] **H-03c 衝突與未完成同步的狀態區分**：同一設備 A／B 分歧且尚未解決，必須計入「待處理衝突 W 筆」，顯示衝突設備與雙方異常，不得把未套用的值算成「已更新」；事件檔損壞、同步中斷、根目錄離線、B 尚未上傳或 Drive Desktop 尚未下載時，顯示「本機已讀取／待雲端傳輸／同步未完成／需處理衝突」等可核實狀態，**不能因 A 按下立即同步便宣稱 B 已完成上傳或其他電腦已收到資料**。
- [ ] **H-03d 結果保留與驗收測試**：在同一個 FireLens 執行階段保留最近一次同步的摘要及明細；切換到其他分頁再返回仍可查看，下一次同步則以新一次結果取代並保留清楚時間標記（不把歷次數字累加）。以合成雙機資料測試 A 既有甲、B 新增乙丙、B 更新丁、衝突戊、未完成事件、再次同步零變更、按鈕重複點擊、切頁返回等情境；前後數量與明細一致才可標記完成。

- [ ] **H-04 資料安全、備份與防倒退驗收**：沿用既有 local outbox、不可變事件、SHA256、缺事件／事件繼承鏈驗證及操作前備份，不直接同步或覆蓋 SQLite，亦不更動照片、清冊、Google Drive 原圖。驗證 A／B 任一端離線時新增紀錄、回線後雙向合併；壞檔、誤刪、過期 Drive 快取、重複事件、同鍵不同值、分類衝突與人工還原後暫停同步，均不可把使用者未確認的資訊靜默丟棄；操作失敗應有可復原路徑。
- [ ] **H-05 合成及雙機實機驗收（實作階段）**：若經使用者授權開始實作，先檢視現有 `tests/test_shared_issues.py`、API 與 UI，補齊 A／B 初次各有不同設備、B 更新、A 合併、同設備分歧、相同內容、離線、備份與 UI 差異計數測試；執行 pytest／Vitest／Ruff／TypeScript/Vite／Windows EXE/installer 更新器 E2E。**兩台真實 Windows + Google Drive Desktop** 請用授權測試副本實際驗證不同網速和上傳延遲；人工測試未完成前，此項不可勾 [x]。本次仍是規格階段，全部維持 [ ]。

- [ ] **H-06 新增動態設備類別的同步相容性**：唯讀檢查發現現行 `shared_issues.py::_value()` 的共享事件格式只允許 `extinguisher`、`box`、`lamp` 三種 category，與 M19 新增的動態照片根資料夾類別（例如水帶 `folder_*`）不一致；若此類設備也能建立異常，`record_item()` 產生的事件可能在同步校驗時被拒絕。實作階段必須先用合成資料重現與判定支援範圍，再決定安全的版本化事件格式／跨機類別識別與 migration；未修正前不得宣稱所有自訂設備分類皆可多人異常同步，也不可放寬路徑、類別及資料完整性驗證。

## M19-G 操作介面易用性改善（2026-11-13，五項需求已確認，僅寫 TASKS，尚未實作）

**需求來源**：使用者先後提供「照片瀏覽」大圖預覽、確認視窗、清冊教學、清冊核對結果及重複掃描工具列截圖，要求一次整理成後續施工規格。**本階段只規劃，不修改 TypeScript／Python／CSS、版本、不執行測試／打包、不提交或推送 GitHub、不發 Release**。目前 v1.11.0 仍為未發布開發版；開始實作時依 `AGENTS.md` 的 TASKS-first／SemVer／自動測試規定施工。

- [ ] **G-01「照片瀏覽」大圖上一張／下一張（限定同一設備）**：在 `frontend/src/App.tsx` 現有照片牆 `preview-dialog` 上方標題／縮放工具列新增「← 上一張」、「下一張 →」與「目前第 N／共 M 張」；從任一「前／中／後」、「編號／藥劑／完成」或自訂槽位照片打開時，**照片集合僅限該次開啟的 root＋同一設備 item_id 的已載入照片**，不得切換到其他設備／左側資料樹的下一個編號，亦不得跨 root 或整個月份／清冊。順序依照片牆實際顯示順序：`orderedSlots`（包含自訂槽位）→ 各槽既有照片排序 → 未對應／舊制照片（依其實際展示順序）；相同槽位有多張照片也逐張切換；不重複列出同張照片。第一張禁用「上一張」，最後一張禁用「下一張」，只有一張時兩側皆禁用；可用鍵盤 ←／→、Esc，切換後更新檔名、圖片內容、序號，縮放預設重置為 100%（並還原位移，避免上一張的放大位置殘留），沿用原本可縮放的大視窗；手動換設備、刪除／移動／重新命名圖片、切根目錄時應安全清理失效預覽，不開啟任何檔案修改操作。**驗收例**：LB-02-03 有 `前.jpg`、`中.jpg`、`後.jpg` 時，依序前→中→後，最後一張不會跳到 LB-01-02 或其他設備。此項與 M19-F 的「品質檢查跨結果清單切換」是**不同的導航範圍**，勿誤用同一集合。
- [ ] **G-02 全站程式自有彈窗統一美化、畫面中央顯示**：清查前端 `window.confirm()`、`window.alert()`、`window.prompt()` 與現有 `prompt-dialog`／`preview-backdrop` 等**程式控制的**確認、警告、成功、輸入、刪除及不可逆操作；規劃共用、可重用的應用程式 Dialog 元件（統一圓角、間距、圖示、層級、按鈕大小、字級、深／淺色、RWD），固定覆蓋於**目前 FireLens 視窗正中央**且不隨頁面捲動。可預期的確認／輸入 UI 不再使用瀏覽器原生 `window.confirm`（因系統原生視窗無法可靠自訂置中與樣式）；但 Windows 作業系統檔案選擇器、權限、安全提示等非程式控制的原生對話框**不在此需求強制替換範圍**。危險操作使用清楚的危險色及「取消／確認刪除」等明確文字、取消為安全預設；支援 Escape、Tab 焦點陷阱、開啟時焦點及關閉後焦點還原、背景禁止點擊與捲動、重入時避免堆疊、可存取標籤。**驗收例**：清除 OAuth Secret、完整掃描確認、刪除照片、還原備份等應顯示一致的置中樣式，按取消不執行任何副作用。保留每個原對話框的後端安全驗證與原操作邏輯。
- [ ] **G-03「清冊教學」預設關閉**：`frontend/src/ReconcileView.tsx` 目前 `tutorialOpen` 初始依 `localStorage` 是否曾勾選「下次不再自動顯示」決定。改為**每次進入清冊核對及每次重新啟動程式均預設關閉**，包含首次使用者、沒有 localStorage 紀錄及舊版有／沒有勾選者；保留既有明確的「清冊教學」／「查看教學」按鈕，使用者主動按下才開啟、按關閉隨時關閉；過去「下次不再自動顯示」選項不應與新預設相矛盾，可移除或改成不會造成自動彈出的說明，不要無故刪除其他使用者設定。教學內容、清冊資料、搜尋／核對結果保持原樣；切換分頁不會自動開啟教學。**驗收例**：乾淨安裝、舊版升級、切分頁返回與程式重啟後教學皆為關閉，但手動仍可打開。
- [ ] **G-04「開始核對」完成後自動跳至結果**：`ReconcileView.tsx` 中按「開始核對」，或在匯入預覽按「儲存並開始核對」成功取得有效 `ReconcileResult` 並**完成 DOM 畫面渲染**後，自動以 `scrollIntoView` 或等效方式將主捲動區移到下方的「核對結果」區段（優先使結果篩選工具列／統計摘要可見，避免被固定頁首擋住）；應有固定目標 ref、`scroll-margin-top`、正常與 reduced-motion 捲動設定。只在**當次由使用者開始並成功完成的核對**觸發一次；核對失敗、取消、查詢已被更新的 stale response、切換分頁返回、改過濾條件或原本結果仍在時，不得無故跳動。應保持原本選取清冊、分類、月份、表格篩選、分頁、結果狀態，且不觸發額外重新核對。**驗收例**：點「開始核對」→ 載入完成後視線落在「核對結果」的查詢／篩選列；失敗則停留原處顯示錯誤。
- [ ] **G-05「重複圖片」掃描／整理按鈕一致美化**：`frontend/src/DuplicatePhotoPanel.tsx` 的「開始重複掃描」、「重新整理清單」、「取消掃描」，改採與現有 `quality-action quality-action-csv`／`quality-action-excel` 一致的按鈕系統，包含高度、字重、圓角、間距、圖示、焦點／hover／disabled／loading，避免目前掃描與整理按鈕看起來像未套樣式；建議「開始重複掃描」為醒目主操作（藍色系）、「重新整理清單」為次要操作（淺藍／中性色），「取消掃描」在執行中清楚可辨、平常停用或隱藏，CSV／Excel 保持既有辨識配色，不增加無必要視覺噪音。掃描中顯示「掃描中…」／進度與不可重複按下、刷新中可顯示「整理中…」，不得讓刷新意外觸發完整掃描；**M19-F 新手引導的高亮 `scan-guide-target` 必須保留最高優先級，不被新樣式蓋掉**。工具列在窄視窗自動換行、不裁切按鈕；深淺色主題對比清楚。**驗收例**：四組主要按鈕（掃描、整理、CSV、Excel）在正常／處理中／停用狀態都有一致而可辨的視覺風格。
- [ ] **G-06 自動化測試與 UI 驗收（實作階段）**：開發前依 `AGENTS.md` 先拆解、先更新 `TASKS.md` 再動碼；為五項功能新增／更新 Vitest 元件與互動測試（同設備邊界、跨槽與未對應圖、Dialog 居中／焦點／取消安全性、教學首次與返回關閉、核對完成／失敗時的捲動、掃描／整理按鈕狀態與引導高亮）；執行既有 Python pytest、Ruff、format、TypeScript、Vite 與版本一致性；Windows 11 EXE／繁中 setup 打包與自動更新 E2E 依專案規則驗證；Graphify／README／AGENTS 同步。對真實 Windows WebView2、Google Drive 與不同解析度操作，未親自驗收前不得宣稱完成或勾選實機驗收。此輪僅寫規格，以上全部維持 `[ ]`。

## M19-F 照片品質大圖預覽與重複掃描導覽（2026-11-13，合成測試與 Windows 打包完成，實機待驗收）

**修正前問題／目標**：原本「照片品質檢查 → 重複圖片」的預覽採小型白底 `prompt-dialog quality-preview`，與照片牆深色大圖可縮放預覽不一致，難以辨識瓶身標籤；也缺乏上一張／下一張連續檢視。貼上照片遇到 `photo_fingerprint` 索引不完整時，後端雖透過 HTTP 409 拒絕未經驗證的寫入，前端卻只顯示一般錯誤，使用者不知道需要前往「照片品質檢查 → 重複圖片 → 開始重複掃描」。本任務明確改善可發現性及操作效率，**不把手動掃描變成貼上時自動全庫掃描、不跳過跨設備重複安全檢查**。

- [x] **統一大圖檢視器**：在照片品質檢查的「品質圖片」與「重複圖片」清單，改用可共用的照片牆風格全螢幕深色 Modal（依視窗高度自適應），預設按 contain 顯示完整原圖、可調百分比縮放與捲動查看細節；上方顯示照片名稱及工具列，提供上一張／下一張按鈕、目前序號及關閉；支援鍵盤 ← →、Escape、合理的焦點管理／背景禁止捲動、窄視窗與深色／淺色主題可讀。上下張僅在**目前已載入清單**中依可見順序切換，不跨頁私自拉取所有原圖，也不修改圖片。保留設備編碼、槽位、相對路徑、原因及原始內容 URL；無有效圖片或失去篩選結果時安全關閉／重設。
- [x] **索引未完成的貼上引導**：針對後端的 `DuplicateIndexRequired` 產生穩定可辨識的 HTTP 409 結構 `code=duplicate_index_required`（不影響 `duplicate_photo` 既有二次確認），前端任何新增照片／拖曳／Ctrl+V／LINE 圖片匯入遇此情形顯示明確中文原因與「前往重複掃描」單一主要操作。保留當前目錄與待上傳照片的安全暫存狀態（至少不誤稱已儲存）；啟動互動式新手引導，定位「照片品質檢查」→「重複圖片」→「開始重複掃描（增量預設）」及完成狀態，明確提示掃描成功後回來重新貼上；可關閉／跳過與重試，不要每次無條件干擾已完成索引的正常貼上，不可自動執行大規模雜湊／下載 Drive 佔位。
- [x] **可靠性與回歸**：補足 HTTP 409 API 模式、正常重複警告、索引未建立／大量照片、離線根目錄、切 Root、掃描失敗或取消後操作的合成後端測試；新增前端大圖切換、縮放、鍵盤互動、條件切換與導覽步驟的測試，並實際執行 pytest／Vitest／Ruff check／format／TypeScript＋Vite／版本一致性與 Windows EXE＋繁中 installer 打包、portable/installer 自動更新 E2E。此 UI 大圖切換與引導屬新增能力，依 SemVer 將歷史未發布的 v1.10.1 PATCH 基線統一提升為 v1.11.0 MINOR 開發版；未獲授權不得推送 GitHub、Tag、Release。
- [ ] **Windows WebView2／真實 Drive UI 驗收**：使用授權測試圖片，在品質清單與重複清單操作縮放、上一張／下一張、鍵盤、不同尺寸；以索引不完整的測試 root 貼圖、依引導完成手動掃描，再返回貼圖成功或出現真正重複衝突，並檢查原始圖片與資料庫未意外變更。合成測試與打包不代表實機驗收，未親自看到結果維持 [ ]。

**M19-F 本輪自動驗證（2026-11-13，Windows 11）**：先依規則先寫 `TASKS.md` 並重新讀取確認，後續完成共享 `frontend/src/InspectorImageViewer.tsx`、品質與重複清單的已載入可見圖上一張／下一張、50%～400% 大圖縮放、鍵盤方向鍵／Escape、焦點與捲動鎖定恢復（包含保留背景元件 `isActive` 切頁清理）、窄視窗及暗色版面。貼圖由 `backend/app/storage.py` `DuplicateIndexConflict` → `backend/app/main.py` HTTP 409 `duplicate_index_required` → `frontend/src/App.tsx` 原始 File 記憶體暫存／三步教學／`DuplicatePhotoPanel.tsx` 高亮**人工觸發**的「開始重複掃描」，掃描成功返回原設備重試，沒有在貼圖時自動大規模掃描；真正 `duplicate_photo` 比對／二次確認保留。新增 `tests/test_m19_guided_scan.py` **2 passed**（合成未建指紋→409→手動增量掃描→成功再貼，以及已有重複仍 409），`frontend/src/inspectorGuide.test.tsx` **7 passed**（鍵盤／縮放控制、來源順序與邊界、互動引導、API 區分、隱藏頁面清理）；更新兩份既有前端檢查。完整 `uv run --locked pytest -q` **234 passed**（既有 1 項 Starlette 警告）；`npm run test -- --run` **96 passed（24 個測試檔）**；`uv run --locked ruff check .` 全通過、`uv run --locked ruff format --check .` **84 files** 通過、`npm run build` TypeScript＋Vite 通過；`uv run --locked python packaging/check_version_consistency.py` **v1.11.0 一致**。Graphify `graphify.watch._rebuild_code(Path.cwd())` 已重建並驗證 `graphify-out/graph.json`、`graphify-out/GRAPH_REPORT.md`，1,148 nodes／3,040 edges／75 communities，產物不提交。最新／最終 `powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build.ps1` **Exit Code 0**；`dist/FireLens.exe`、`dist/installer/FireLens-1.11.0-setup.exe` 實際建置成功、繁中 Inno Setup Verification successful、**portable／installer、READY／HEALTHY、rollback、injected failures 更新器 E2E passed**；最終本機 Setup SHA-256 `A6E36F8AC740A8F612447E7B9DA270D446E8384C4840631617C2C27F3331B2EC`。真實 Windows WebView2／Google Drive 人工大圖操作、貼圖導覽及原圖資料驗收尚未執行，另保留 [ ]；本輪未推送、Tag 或發布 Release。

## M19-E 貼上照片效能優化：SQLite 快速比對與非阻塞更新（2026-11-13，使用者已授權）

**修正前實際瓶頸**：原本每次 `import_photo()` → `preflight()` → `index_photos()` 會對整個 root 的每一張 `photo` 呼叫 `_safe_stat()`（即使已有快取）、再 `find_duplicates()` 全表查詢及掃描，Google Drive 虛擬磁碟尤其慢；前端 `upload()` 成功後串行等待 `refreshTree` + `refreshCacheState`，另外桌面剪貼簿會重新編碼 PNG＋Base64，儲存端重複計算 SHA-256。目標不犧牲跨設備完全相同提醒與文件安全，讓已完整索引 root 的單張加入不再做全 root 的檔案狀態檢查，並以實測合成資料比較快路徑延遲。

- [x] **SQLite O(log N) 重複查詢**：`preflight()` 改為先在 SQLite 以 `root_id + sha256` 現有 `idx_photo_fingerprint_digest` index 查詢**可能相同**的來源照片，只有命中才對候選檔執行 `_safe_stat()`／SHA-256 二次驗證。不得每張貼上全表 `_photos()`、逐一 `lstat()` 或讀取所有照片。不改變來源格式與 HTTP 409 `duplicate_photo`、仍要儲存明確確認、重新命名／覆蓋／替換邏輯及 root/exclusion/path validation；新增 SQLite explain query plan 測試。
- [x] **完整度與增量索引可靠性**：先用 SQLite 輕量 SQL 查 root 目前資料表是否有未索引、演算法／size／mtime 失效照片；不能將索引未完整視為「無重複」。未初始化／小型索引可限量初次自動補建一次，其他情境明示手動掃描必要，且不因檢查而自動下載 Google Drive placeholder。新圖安全寫入／換圖成功後即更新當張 `photo_fingerprint`，刪除／其他入口更新需防止舊指紋造成誤報；可保留背景「手動增量／完整掃描」負責總管直接複製與跨程式修改的照片。離線佇列依原規則重複預檢，失敗時不靜默寫入。
- [x] **縮短照片匯入與 UI 等待**：診斷剪貼簿 PNG／Base64 與 `_save_stage`、`fsync`／`sha256_file` 重新讀取成本，只消除可證明多餘的運算，不得刪掉必要寫入後驗證、原子性與 rollback。貼上成功後先更新目前設備及結束 busy，根目錄資料樹與快取狀態非同步更新且不得被下一次選設備／切 root 時的舊請求覆蓋；確保離線佇列顯示正確及背景錯誤處理。加入使用者可在診斷中看到的逐階段毫秒計時（例如圖片轉換、預檢 SQL、候選驗證、寫入、UI 補刷新），預設不在 console 洩漏照片資料／路徑或敏感 token。
- [x] **自動化及合成效能實測**：用合成 SQLite＋照片執行無重複／跨設備重複／候選內容不同／同檔名不同內容／index 未完成與損壞／手動重掃／Google Drive 離線與排除資料夾／加入、替換、刪除、離線佇列完整回歸；測試以 monkeypatch 保證**已有索引**貼上時 `_safe_stat` 僅針對命中候選且 `index_photos` 不重掃；對數千張合成索引在 Windows 11 比較前後耗時，記錄測試環境、樣本量、相對及絕對數據，不得虛報「1 秒內」。完整 `pytest`／Vitest／Ruff／format／Vite／版本檢查／Windows EXE/setup＋packaged E2E；同步 AGENTS／README／TASKS。此開發仍屬尚未正式 Release 的 v1.10.1 PATCH，若功能變更需另判 SemVer，不自行 push/tag/release。
- [ ] **真實 Windows／Google Drive 驗收**：在授權測試副本用 100／1,000／10,000 張圖片、LINE 剪貼簿、WebView2、雲端佔位與離線同步實測貼上到完成的秒數；合成 benchmark 不取代這項驗收，禁止對現場照片動破壞性測試。

**M19-E 實際自動驗證（2026-11-13，Windows 11）**： `uv run --locked pytest -q` **232 passed**（1 項既有 Starlette 警告）； `npm run test -- --run` **89 passed**（23 個測試檔）； `uv run --locked ruff check .`、`uv run --locked ruff format --check .`（83 files）、 `npm run build` TypeScript/Vite、`uv run --locked python packaging/check_version_consistency.py` v1.10.1 均通過。 新增 `tests/test_m19_fast_paste.py` 4 項，驗證完整索引時不逐張 stat／hash、不呼叫全庫索引、命中才核實、首次少量索引及新增／刪除立即維護指紋、候選不安全時阻擋； SQLite `EXPLAIN QUERY PLAN` 確認 `idx_photo_fingerprint_digest`、`idx_photo_relative_path` 雙索引。 另新增 `frontend/src/fastPaste.test.ts` 4 項，測非阻塞背景刷新、避免過期根目錄覆寫、時序診斷及無損剪貼簿 PNG；API 與透明 RGBA 回歸亦通過。 **合成效能實測**：同一 Windows 11，4,002 筆索引新版無命中中位數約 **3.1～5.0 ms**；舊式逐張檔案 metadata 巡查的本機近似測試中位數約 **739～1,086 ms**。 此為合成 SQLite／本機檔案 metadata 路徑比較，部分舊式巡查目標不存在，**不是** v1.10.0 完整貼上時間，也不代表真實 Google Drive／LINE 已測出這種速度。 Graphify `_rebuild_code` 已重建（1,134 nodes／2,984 edges／73 communities），`graphify-out` 未加入 Git。 Windows `powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build.ps1` **Exit Code 0**，`dist/FireLens.exe`、`dist/installer/FireLens-1.10.1-setup.exe` 建置完成，繁中 Inno Setup 驗證成功； 打包後 portable／installer 更新器 READY／HEALTHY、rollback、故障注入 E2E 全通過。 安裝包 SHA-256：`DAC5A3F95AE1A982EDCBC62C0B79148397EC301F0E68653E688A6DAB531F6F4E`。 真實 Windows WebView2、Google Drive 大型同步目錄與 LINE 剪貼簿貼上延遲仍未實機測量，保留 [ ]。

## M19-D「前往照片牆」後返回原工作頁保留查詢（2026-11-13，使用者實機回報）

**問題／原因**：從「照片品質檢查」或「清冊核對」點設備「前往照片牆」切換到 `browse`，`App.tsx` 的大條件式渲染將原頁元件卸載；再返回時 `PhotoQualityView`／`ReconcileView` 的本地 `useState`（品質分類、模式／重複照片子頁、搜尋、篩選、分頁、掃描結果與清冊選取／分析結果）被重新初始化。一般上方標籤切換即使外觀看似沒有重置，也不得依賴目前的卸載行為。目標是在**同一個 FireLens 執行階段中**保留已打開的工作頁狀態，直到使用者自行改條件／按重新掃描；本次不是跨關閉程式永久保存，也不能把舊查詢錯誤套到不同根目錄／清冊。

- [x] **頁面保活與導覽**：調整 `App.tsx` 將「照片品質檢查」與「清冊核對」改為首次進入才掛載、離開後仍保留元件實體但不可見（hidden/inert 或等效方案）；保留既有 `onOpenItem` 指向設備照片牆、其他功能頁顯示及焦點/鍵盤操作；不可無端啟動從未開啟的品質分析或清冊請求。重複圖片 `DuplicatePhotoPanel` 的子分頁與掃描狀態亦需保留。
- [x] **查詢狀態與結果保留**：品質頁保留 root、品質／重複子分頁、搜尋、分類、月份、棟別、問題篩選、排序、縮圖尺寸、頁碼和已載入的列表；清冊頁保留 root、已選清冊、月份／分類／棟別篩選、缺照條件、表單草稿及上次分析結果。從任一結果「前往照片牆」後回到原頁不要求重新點「分析／查詢／掃描」。只有原始資料明確更換、刪除或使用者手動刷新時才依原有規則重新分析，不能將過期資料錯誤顯示為最新。
- [x] **自動化測試與回歸**：新增前端導覽／元件掛載回歸測試，驗證首次進入、切 browse、返回品質與清冊、重複圖片子分頁，保留 filters/results 與狀態、隱藏頁面不能操作與不會重複初始化；執行 Vitest、TypeScript/Vite、pytest、Ruff、版本一致性，依 Windows 桌面 UI 變更重打包 EXE／繁中 setup、portable／installer 更新器自測。歷史 Release v1.10.0 已發布，本次相容 Bugfix 依 PATCH 升為 v1.10.1 開發版；同步 `desktop/version.py`／`pyproject.toml`／`uv.lock`／前端 fallback、README／AGENTS／TASKS。未經授權不得 Push、Tag、Release。
- [ ] **Windows WebView2 實機驗收**：用授權測試資料，實際在品質／重複／清冊中設定查詢 → 前往照片牆 → 返回，確認原查詢、滾動與結果沒有重置；另測不同 root、極大量資料、背景掃描、縮放及深淺模式。未操作實機不勾選此項。

**M19-D 自動化驗證證據（2026-11-13）**：`frontend/src/RetainedView.tsx` 使用已造訪頁面保留及 `hidden`／`inert`／`aria-hidden` 隱藏；`frontend/src/retainedView.test.tsx` 新增 4 項 SSR／掛載契約測試，涵蓋先進入頁面、切 browse、返回原頁、品質子分頁及清冊結果，不誤稱已執行真正的 WebView2 滑鼠端到端測試。完整 `npm run test -- --run` **85 passed**、`npm run build` TypeScript/Vite 通過；`uv run --locked pytest -q` **227 passed**（1 項既有 Starlette deprecation warning）、`uv run --locked ruff check .` PASS、`uv run --locked ruff format --check .` 82 files PASS、`uv run --locked python packaging/check_version_consistency.py` v1.10.1 一致。依 AGENTS 規則重建 Graphify：`graphify-out/graph.json` 及 `GRAPH_REPORT.md` 皆成功（1,117 nodes、2,949 edges），產物僅本機、未提交。Windows `powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build.ps1` **Exit Code 0**，繁中 `dist/installer/FireLens-1.10.1-setup.exe` 建置成功、Inno Setup Verification successful；正式打包後 portable／installer 更新器 READY／HEALTHY、rollback、故障注入 E2E passed；本機 setup SHA-256=`F8CE4F401A5F3EAEDE9950A67A07B39BAA742A64069DE8BC53140B89D8F29E3C`。真正 Windows WebView2、現場 Google Drive 資料及人工換頁操作仍屬待驗收；本輪不 Push、不 Tag、不 Release。

## 歷史 Release v1.10.0 正式發佈作業（2026-11-13，使用者已明確授權）

**歷史 Release 目標**：將已完成自動回歸／Windows 打包的 M19-C 與 M19-B 等開發提交推送 `https://github.com/kobojp/FireLens` 的 `main`，以現有 `.github/workflows/release-windows.yml` 的 Tag 觸發 GitHub Actions，產出 v1.10.0 正式 Windows EXE、繁中 setup、SHA256SUMS.txt 與 Ed25519 簽名更新清單；只發布此版本，不觸及真實照片、Google 機密或未授權服務。人工 Google Drive／WebView2 驗收仍獨立未完成。

- [x] **歷史 Release 發佈前檢查**：確認 Git 主線乾淨、最新工作未遺失，遠端與 Tag 不衝突；核對 `desktop/version.py`、`pyproject.toml`、`uv.lock`、README／TASKS／workflow 版本；實際執行 `packaging/check_version_consistency.py --tag v1.10.0`、所需測試／打包或已有可核對的當輪 E2E 證據。檢查 Actions 使用的 `FIRELENS_UPDATE_PRIVATE_KEY_B64` secret 名稱存在（不讀取密值），確保 CI 能簽 Ed25519 manifest。
- [x] **GitHub main 推送**：僅提交本次發版規劃文件及已驗證程式碼，確認無真實照片、金鑰、Token、資料庫或 build 輸出進入提交；`git push origin main` 後驗證遠端 SHA 等於本機提交。
- [x] **v1.10.0 Tag 與 Actions 發佈**：只在預檢通過且 Tag 未存在時建立精確 `v1.10.0` 標籤並推送，讓 Windows Release workflow 自動 Build／Test／Sign／Create Release；記下 Actions run URL、狀態、Tag 指向與實際資產。任何 CI 失敗必須如實紀錄，不得冒稱發佈成功。
- [x] **發佈後驗證與文件同步**：透過 GitHub CLI／官方 release API 確認 v1.10.0 為已發布狀態、5 項資產（portable x64 EXE、setup、SHA256SUMS、update-manifest.json、update-manifest.sig）均存在且版本一致，校驗公開 SHA256／簽章更新流程，更新 TASKS 頂部的「正式 Release」狀態與實際結果；同步 README／AGENTS 規則（若有變更），最後提交與推送文件。無法完成的部分保持 [ ]，不把合成驗證當實機驗收。

**歷史 Release 本次預檢證據**：本機 `main` 起始為 `6d0c51e`，比 `origin/main` 領先 4 個提交；遠端無 `v1.10.0` Tag，GitHub 無同名 Release。`uv run --locked python packaging/check_version_consistency.py --tag v1.10.0` 通過；GitHub Actions 工作流程 `release-windows.yml` 為 `active`、`FIRELENS_UPDATE_PRIVATE_KEY_B64` secret 名稱存在（未讀取密值）、`git diff --check` 通過；前輪 M19-C 已實際通過 Python 227、Vitest 81、Ruff、TS/Vite 與 Windows 打包／portable＋installer 更新器 E2E。當輪本機檢查 `dist/FireLens.exe`、`dist/installer/FireLens-1.10.0-setup.exe` 存在，後者 SHA256 為 `7BD2544B2FB871F6D8B8535FECB1877690BD42B1B66BE66A96321A7EEA727319`；GitHub CI 已於 v1.10.0 Tag 事件重新編譯、驗證及簽名；正式 Release 的 SHA256 以 CI 上傳檔案為準。

**正式發布驗證結果（2026-11-13 07:34，台灣時間）**：`main` 發版提交 `f3b3bea5a9c06e1c39dffe0ba2f4df19aacda3b0` 已推至 GitHub；註解 Tag `v1.10.0` 指向同一提交（Tag object `a2133d713199c999dc8dc5e0b00a23abaa7a5983`）；GitHub Actions Run <https://github.com/kobojp/FireLens/actions/runs/43329200196> `completed/success`，包括 Windows Build、安裝包、更新器 E2E、SHA256SUMS 產生、Ed25519 manifest 簽章、資產上傳及 Create Release。Release <https://github.com/kobojp/FireLens/releases/tag/v1.10.0> 已發布（`isDraft=false`、`isPrerelease=false`，公開上架時間 2026-11-12T23:34:17Z）。五項資產均存在：`FireLens-1.10.0-windows-x64.exe`、`FireLens-1.10.0-setup.exe`、`SHA256SUMS.txt`、`update-manifest.json`、`update-manifest.sig`。從 Release 下載後，使用產品內建 `desktop.update.verify_manifest` 與 Ed25519 公鑰驗證**簽章通過**；下載的三項 metadata 檔案 SHA256 與 GitHub 資產 digest 一致；manifest `version=1.10.0`、EXE 檔名、大小及 SHA256 與 SHA256SUMS 和 GitHub asset digest 相同。正式雲端 setup SHA256=`187a1c9fb2b029b1934e116de8e802e2f600f77b15f83382b59bd0a254389455`、portable SHA256=`6d0bd15f3bc4a7d87893ad3f08ccd93591844e16158c9fa69b224e6d4c9f8e59`。本機與雲端安裝包雜湊可能因不同建置環境不同，以正式 GitHub Release 為準。真實 Google Drive／WebView2 手動驗收仍列未完成。

## 永久開發鐵律：自動化測試與完成認定（2026-11-12）

- [x] 在 `AGENTS.md` 新增「每一項功能／Bug 修復／UI／API／資料庫修改都必須有對應的自動化測試」永久規則；遵守先寫 TASKS 後實作的順序，功能完成不等於測試完成。
- [x] 明訂階段性測試與最終回歸驗證：新增／更新必要的 pytest、Vitest、API／SQLite／合成情境測試，實際執行並核對輸出；相關失敗不得宣稱通過或將功能勾 `[x]`，須修正後重跑。版本、前端建置及 Windows 打包測試依改動範圍執行。
- [x] 明訂證據與實機驗收分離：在 `TASKS.md` 紀錄測試指令、實際結果（通過數／失敗原因）及未測項目；沒有親自執行的測試不得標「已驗證」。所有適用的自動測試通過後，才可勾選已驗收的程式任務；Windows WebView2、真實 Google Drive 等實機操作仍單列 `[ ]`，不得拿合成測試冒充真人驗收。本次僅改文件、不改程式或版本、不 Push／Tag／Release。

## M19-C 全根目錄跨設備重複圖片偵測（2026-11-13，合成驗證通過，實機待驗收）

**問題與目標**：修正前的重複圖片判斷只檢查「同一設備資料夾」，把「三-07-25」照片加入另一台設備（例如「水帶／F-19-13」）不會提示；使用檔案總管直接複製後再掃描，也不會提醒。本任務擴充成**同一照片根目錄內，跨設備、棟別、月份及類別**的重複檢查，保留既有同設備防護，不跨不同根目錄比對。

- [x] **持久化 SHA-256 增量索引**：確認現有 photo 索引資料欄位，設計 SQLite 圖片雜湊索引及必要 migration。以安全相對路徑、檔案大小、mtime_ns 與雜湊演算法版本判定快取有效性；新增／變更重算、刪除／移動清除舊索引。預設增量掃描，另提供強制全量重建；不得只看檔名、設備編號或尺寸，也不得依靠已過期雜湊報告無重複。索引不保存圖片位元組。
- [x] **新增圖片的跨設備即時預檢**：所有加入圖片入口（按鈕、拖放、Ctrl+V／LINE、換圖及直接 API）在寫入前計算實際輸出檔案的 SHA-256，比對所選根目錄的全部有效照片索引；命中時先核對安全本機來源，避免舊索引誤報。沿用同設備 409 保護，跨設備命中也必須由後端攔截並回傳重複來源；不可僅用前端提示。若索引未建完，必須明示「待檢查」或要求先完成安全掃描，不能假裝沒有重複。
- [x] **重複警告與確認視窗**：置中比較「已有圖片／準備新增圖片」，顯示類別、月份、棟別、設備編號、槽位、檔名與安全相對路徑；多筆命中列出數量與全部來源，提供「查看原照片」「取消儲存（預設）」「仍要儲存」。只有明確確認才容許保存另一份並產生安全新檔名，不得覆寫、刪除、移動原圖。設備切換、取消、重入或離線期間確認不得錯誤套用到另一設備；保留不含原圖內容的必要稽核紀錄。
- [x] **手動全資料庫重複掃描**：整合在「照片品質檢查」既有主頁，新增「重複圖片」篩選與依 SHA-256 分組的結果卡；預設手動增量掃描，可選完整重新分析。提供已處理／總數、進度、取消、錯誤、沿用快取、重複群組與涉及設備數、縮圖與「前往照片牆」；CSV／Excel 可匯出完整匹配清單而非僅當頁 40 筆。使用 Windows 檔案總管直接跨設備複製照片後，下一次手動掃描也必須能找出重複。
- [x] **Drive 與安全限制**：不觸發 Google Drive 雲端佔位檔下載；離線、無權限、檔案不可讀時記為「未檢查／待同步」，不能當成無重複。排除系統目錄、使用者自訂排除目錄、符號連結及 reparse point，只檢查所選根目錄內的安全圖片。不將影像或雜湊傳到外部、不自動更名刪除、避免大量照片雜湊阻塞 UI；離線佇列同樣必須確保重複檢查及人工確認語意。
- [x] **精確重複與相似照片分期**：第一階段只做 SHA-256「檔案內容完全相同」；若重新壓縮、裁切、調色、修改 metadata 導致位元組不同，不得宣稱完全相同。第二階段另規劃感知雜湊／視覺相似度並由人工確認，本次不實作第二階段。
- [x] **已完成自動測試與回歸**：以合成照片和 SQLite 驗證「三-07-25 → 水帶 F-19-13」跨設備、跨月份／類別同位元組重複；測同設備、不同內容同檔名、同大小不同內容、移動／刪除／變更、索引失效、尚未索引、重複命中多台、取消／仍存、API 409、檔案總管直接複製後掃描、品質頁分組與 CSV／Excel 全量匯出、雲端佔位／排除與大量圖片增量效能。確認不變更任何原圖及既有清冊／設備異常。執行 Ruff、pytest、Vitest、TypeScript/Vite、版本一致性與 Windows EXE／setup 打包和更新器自測，並同步 AGENTS／README／TASKS；未驗證項目保持未完成。
- [ ] **實機驗收與發版約束**：在 Windows WebView2 及授權的 Google Drive Desktop 測試副本檢查警告、圖片對照、直接總管複製、手動重複掃描、取消／強制儲存、離線情境及資料保留。合成測試不能代替實機驗收；歷史 Release v1.10.0 原開發版，實作時依 SemVer 和專案版本規則驗證。沒有使用者明確授權不得 Push、Tag 或 Release。

**歷史 Release M19-C 已實際執行的自動驗證（2026-11-13）**：`uv run --locked pytest -q` **227 passed**（1 項既有 Starlette deprecation warning）；`npm run test -- --run` **81 passed**；`uv run --locked ruff check .` 通過、`uv run --locked ruff format --check .` 82 files 通過、`npm run build` TypeScript＋Vite 通過、`uv run --locked python packaging/check_version_consistency.py` v1.10.0 一致。新增 `tests/test_m19_cross_duplicates.py` 7 項專項測試及 `frontend/src/duplicateDetection.test.tsx` 4 項前端測試（包含跨類別三-07-25 → F-19-13、DB migration schema 12、增量／刪除／不完整／雲端佔位、46 組跨頁 CSV 匯出及完整確認視窗 UI 合成渲染）；Windows `powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build.ps1` Exit Code 0；成功產生 `dist/FireLens.exe` 與 `dist/installer/FireLens-1.10.0-setup.exe`；Inno Setup Verification successful、portable／installer READY／HEALTHY、更新器 rollback／injected failures E2E 通過。安裝檔 SHA-256：`7BD2544B2FB871F6D8B8535FECB1877690BD42B1B66BE66A96321A7EEA727319`。真實 Drive／WebView2 仍為待驗收，不得宣稱通過。

- [ ] **額外實機與長時間效能驗證**：大型真實 Drive 目錄（含大量圖片、混合上線佔位）實測耗時／增量索引準確度、Windows WebView2 確認對話框操作、圖片預覽／深色模式／縮放、端到端離線佇列人工處理；本輪合成測試與 packaged E2E 不代表上述已驗收。

## M19-B 所有照片類別預設三槽與自定義（2026-11-12，實機回報）

- [x] **修正水帶及將來動態類別**：修正先前把動態類別建立為單槽 `照片` 的設計；新偵測類別預設 `前／中／後`，已有動態類別（包括已掃描 `水帶`）安全轉換舊 `照片` 預設，重新掃描後 `前.jpg`、`中.jpg`、`後.jpg` 各自進入槽位。保留原圖／檔名／mtime、既有設備索引與異常紀錄，不碰現場 Drive。
- [x] **各類別自訂槽位**：設定頁每個設備類別提供可編輯槽位清單，可增加、刪除、調整順序和命名；設定持久化到 SQLite，每個類別獨立。更新既有類別 `category.slots_json`，保護保留槽位照片：移除／改名槽位後實體照片不得刪除或更名，未匹配的圖轉「未對應／舊制照片」，需明顯說明影響並要求確認；至少保留一槽，禁止重複、不安全檔名字元及同義詞碰撞。預設滅火器=編號／藥劑／完成，其餘（放置盒、燈具及新分類）=前／中／後，使用者可再自訂。
- [x] **全鏈整合**：掃描 `_slot_for`／`_status_for`、資料樹、照片牆（新增照片、拖放、Ctrl+V、換圖）、品質檢查卡及缺槽計算採各類別真實設定而非寫死三類，保存後刷新類別、樹與當前設備，避免舊的 `slot_order`／`custom_slots` 導致失效。原滅火器有效日期同義詞及放置盒舊制需保留相容。
- [x] **合成驗收及 Windows 打包**：新增 `tests/test_m19_category_slots.py`，已驗證舊版 SQLite schema 10 的 `水帶` 單槽安全升級至 schema 11；`前.jpg`／`中.jpg`／`後.jpg` 正確分槽、設備 ID 和原圖位元組保留、品質檢查缺槽正確、所有既有類別可自訂、含同義詞衝突／非法輸入保護、槽位改名需再次確認且舊圖片保留未對應、Settings API 新增／移除與持久化。前端測試包含自訂欄位與確認流程。Ruff check／format PASS，pytest **219 passed**、Vitest **77 passed**、TypeScript/Vite build、版本一致性 v1.10.0 PASS。Windows `packaging/build.ps1` Exit Code 0，成功建置 `dist/FireLens.exe`、`dist/installer/FireLens-1.10.0-setup.exe`，打包後 portable／installer READY／HEALTHY、rollback／故障注入 E2E 通過。AGENTS／README／TASKS 已同步；尚未發布的 v1.10.0 繼續沿用，不推送 GitHub／Tag／Release。
- [ ] **實機驗收**：在真正 Windows WebView2／Google Drive Desktop 對 `水帶` 執行重新掃描，確認既有前／中／後照片顯示、各種視窗縮放、槽位自訂與重新啟動設定保留。只在合法授權測試資料上進行，合成測試和打包成功不代表實機已通過。

## M19 動態資料夾與重複圖片提醒（2026-11-12，使用者實機截圖）

- [x] **掃描根目錄自動發現類別**：修正前 scanner 只掃固定「滅火器／放置盒／燈具」，所以 Google Drive 根目錄新增「水帶」看不到。將可讀取的根目錄一級子資料夾動態辨識為照片類別，維持原三類原本欄位／槽位，歷史 M19 首版曾採通用單一「照片」槽位，後續 M19-B 已修正為新類別預設「前／中／後」並可自訂，不會把水帶當滅火器。需核對 category DB、tree、item API、前端選擇和新增資料夾的相容性。根目錄重新掃描後出現、移走後只更新可重建索引，不改動原圖與清冊。
- [x] **預設排除系統目錄與可設定例外**：預設隱藏 `FireLens-共享異常資料` 等程式系統／隱藏目錄，不能讓照片掃描碰共用異常事件；在「設定」提供可編輯的排除根目錄一級資料夾名稱清單（支援新增／刪除），忽略大小寫、路徑穿越／斜線與特殊名稱無效，保存在 SQLite 設定，更新後重掃生效。不能掃描 symlink/reparse point 與雲端離線佔位檔；不可直接下載 Google Drive 雲端照片。
- [x] **新增照片相同內容偵測**：在全部新增照片入口（拖放、加入照片、剪貼簿 Ctrl+V、照片替換可合理處理）以圖片內容而非僅檔名比對同設備已有的圖片。若已存在則不立即寫入，顯示圖片相同、所在設備與檔名及「取消／仍要儲存」選擇；確認後才允許保存另一份，不覆寫原圖。後端必須防止略過前端的直接 API 寫入，至少同一設備以內容 SHA256 驗證；保留現有格式／命名與離線寫入保護，避免因索引舊 SHA 或占位檔誤報。記錄稽核不含敏感圖像內容。
- [x] **合成驗收與 Windows 打包**：合成根目錄涵蓋新增「水帶」、預設共享異常目錄、自訂排除和重新掃描索引；合成圖片以真實 SQLite 與 API 測試相同內容被 409 阻擋、使用者確認才允許第二份、不同圖片正常、設定非法路徑拒絕、原三類既有匯入及離線佇列回歸。Ruff check／format PASS；pytest **214 passed**、Vitest **76 passed**、TypeScript／Vite、v1.10.0 版本一致性 PASS。Windows `packaging/build.ps1` Exit Code 0，產生 `dist/FireLens.exe` 和 `dist/installer/FireLens-1.10.0-setup.exe`，portable／installer READY／HEALTHY、rollback／故障注入 E2E passed。已同步 AGENTS／README／TASKS。版本 v1.10.0 仍是開發版，不 Push／Tag／Release。
- [ ] **真正 Windows UI／Google Drive 驗收**：用已授權照片副本確認 `水帶` 在實際 Google Drive Desktop 根目錄出現，系統與自訂排除資料夾不進入索引；在 WebView2 測試各種新增圖片入口、重複確認、縮放和退出重開設定持久化。合成測試及打包成功不等於實機測試通過。

## 永久開發鐵律：先寫 TASKS，後實作（2026-11-12）

- [x] 將「任何實作開始前必須先更新 `TASKS.md`」提升為 `AGENTS.md` 最優先、無例外的開發閘門：先讀 `AGENTS.md` 與 `TASKS.md`，再將需求目標、修改範圍、例外與風險、驗收／測試項目以 `[ ]` 記錄於 `TASKS.md`，親自確認寫入成功後，才准修改任何功能程式、UI、測試、設定、資料庫、API、打包或部署／發布相關實作。
- [x] 規定使用者說「開始／繼續／直接做／一次完成」均不可跳過 TASKS 閘門；正在實作時出現新需求，須先補 TASKS 再動工；未成功寫入時不得先改程式或事後補記。已規劃的既有 `[ ]` 任務可沿用，但必須先確認內容涵蓋本次範圍。
- [x] 施工完成後逐項依實測結果把 `[ ]` 改為 `[x]`，未驗收維持 `[ ]`，同步 `AGENTS.md` 的長期規則與 TASKS 紀錄；本次僅文件規範，不修改功能或版本、不觸發 Release。

## M18 正式 GitHub Release v1.9.0（2026-11-12）

- [x] 使用者明確要求 v1.9.0 正式 Release：已讀發版規範，`main` 與 `origin/main` 同步且工作區乾淨；`python packaging/check_version_consistency.py --tag v1.9.0` 通過。GitHub 尚無同名 Tag／Release；Actions Secret `FIRELENS_UPDATE_PRIVATE_KEY_B64` 已確認存在（只核對名稱，不讀取密鑰）。
- [x] 歷史 Release 發版前將 `TASKS.md` 施工紀錄提交與推送 `main`：提交 b61ea94；建立並推送 annotated Tag `v1.9.0`，指向 b61ea94。`.github/workflows/release-windows.yml` 成功觸發 Windows 建置與繁中安裝精靈發版。
- [x] GitHub Actions 發版 run `43125331526` 結果 success（2026-11-12），版本驗證、Windows EXE/installer 打包後 E2E、簽章、artifact 上傳、Release 建立均成功。正式 Latest Release： https://github.com/kobojp/FireLens/releases/tag/v1.9.0 ，非 Draft／非 Prerelease。已查證五個 Release 資產：`FireLens-1.9.0-windows-x64.exe`、`FireLens-1.9.0-setup.exe`、`SHA256SUMS.txt`、`update-manifest.json`、`update-manifest.sig`（Ed25519 簽章）；正式 Release assets 與 GitHub latest API 一致。
- [ ] 在實際 Windows FireLens 從舊版執行線上更新、確認自動重啟與使用者資料保留；同時補做 M18 品質掃描 UI／真實匯出以及 125%／150% 縮放實機驗收。正式發布不代表這些驗收已通過。

## M17 正式 GitHub Release v1.8.0（2026-11-08）

- [x] 將本機 feature/m17-improvements 安全快轉至 main，推送 origin/main：提交 518f562；GitHub 專案 kobojp/FireLens。
歷史開發紀錄：- [x] 發版前 Python 193 passed、Vitest 58 passed、Ruff check/format、TypeScript/Vite 與 packaging/check_version_consistency.py --tag v1.8.0 全部通過。
- [x] 發版前確認 FIRELENS_UPDATE_PRIVATE_KEY_B64 為 GitHub Actions Secret（僅檢查是否存在、不讀取內容），且 Git 無追蹤 .dpapi／.env／SQLite／真實照片或清冊資料。
- [x] 推送 v1.8.0 Git Tag，GitHub Actions run 42494489173 結果 success；Windows EXE + 繁中 installer、Ed25519 update-manifest.json/update-manifest.sig、SHA256SUMS.txt、五個 Release 資產均成功上傳；正式 Latest Release： https://github.com/kobojp/FireLens/releases/tag/v1.8.0 。
- [ ] 真實 Windows 歷史 v1.7.0 → v1.8.0 線上更新及兩台 Google Drive Desktop 異常同步／衝突／備份復原，仍需使用者實機驗收（正式發布不等於實機操作已通過）。

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
| 使用情境 | 歷史 M0 單人單機（M17-J 起可自行啟用 Drive Desktop 事件式異常資料同步，不直接共用 SQLite）；辦公室電腦（滑鼠、鍵盤為主，拖放優先；觸控不是設計重點） |
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
- 日誌：寫入 `%LOCALAPPDATA%\<應用名>\logs`；錯誤訊息使用繁體中文。
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

### M16 設備資料夾更名、清冊匯出修復與設備異常單選標記／統計（歷史 v1.7.0 已實作）

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
- 真正打包後 Windows 視窗測試：歷史 FireLens v1.7.0 UI 可開啟「統計」並載入「設備異常統計」；使用合成根目錄與清冊，直接按 UI 匯出 CSV（339 bytes）與 XLSX（5,373 bytes）皆成功。額外在隔離 pywebview／WebView2 操作真實 React 畫面，實測設備選取 →「更改名稱」→ 實體目錄更名成功、照片保留；再標記異常並確認 SQLite 保存，統計頁可列出更名後設備。沒有對任何現場根目錄操作。
- 完整 Windows build 已成功產生 `FireLens.exe`、`FireLensUpdater.exe` 與繁體中文歷史 Release 安裝檔 `FireLens-1.7.0-setup.exe`；打包後 self-test、portable／installer 真實 updater E2E、READY／HEALTHY、rollback／故障注入均通過；npm 正式執行依賴 `npm audit --omit=dev` 結果為 0 漏洞，npm 全依賴安裝時仍出現 1 項 high 等級開發依賴警告，不以 `npm audit fix --force` 擅自升級造成破壞。
- 歷史 v1.7.0 當時最終自動驗收：`packaging/check_version_consistency.py` PASS v1.7.0、Ruff format/check PASS、pytest **107 passed**（既有 1 項 Starlette/httpx deprecation warning）、Vitest **31 passed**、TypeScript／Vite PASS。Graphify 已重建為 **665 nodes / 1536 edges / 48 communities**，`graphify-out` 仍只留本機且受 `.gitignore` 排除。
- GitHub：歷史 v1.7.0 已於 2026-11-07 正式 commit／push 並透過 GitHub Actions 發布；當時安裝檔已可下載。

### M17 清冊核對只顯示匯入設備（歷史 v1.7.1 預備版本）

使用者回報核對畫面出現「清冊外」且顯示「找不到設備資料夾」，雖實際照片目錄存在。確認定案：**核對以匯入清冊為唯一範圍，提供哪些編號就顯示哪些結果**；資料來源存在但未列入清冊，不能算作缺失，其他設備照常保留於照片瀏覽與異常統計。

- [x] 移除在核對結果自動追加的清冊外滅火器、特例資料夾及放置盒／燈具設備列。
- [x] 核對狀態、棟別進度、分類數量、補拍文字、CSV 與 Excel 只依清冊設備列產出。
- [x] 移除核對列表中的誤導性「清冊外」提示，照片目錄資料不刪除。
- [x] 回歸測試：使用合成照片與 SQLite，清冊外／特例／其他類別不進核對或匯出，清冊真正缺設備才顯示找不到；既有單欄／雙欄及月份篩選測試通過。
- [x] 歷史 v1.7.1 當時自動驗收：v1.7.1 版本一致性、Ruff、pytest 107 passed、Vitest 31 passed、TypeScript／Vite、Windows EXE 與繁中 setup 正式 build、打包後 self-test、portable／installer 更新 E2E、rollback 故障注入皆通過；Graphify 成功重建 665 nodes／1535 edges／48 communities。仍待使用者實機核對畫面確認。
- 發版：歷史 v1.7.1 未建立 Release，目前在後續開發分支。

### M17-K 修正 Windows desktop.ini 誤觸共享事件格式阻擋（2026-11-08）

使用者 Windows 11 實際操作回報「共享資料夾包含不認識的檔案，停止同步」。使用唯讀檢查本機已啟用 root 1 的 FireLens-共享異常資料/events，確認只有 Windows 系統檔 desktop.ini。既有 events 解析對所有不符 UUID4 JSON 的檔案均拒絕，導致正常 Windows metadata 被錯誤阻擋；不可刪除現場 desktop.ini、雲端事件、照片、清冊或受保護 SQLite。

- [x] 同步事件讀取器僅跳過已知 Windows 系統附屬檔 desktop.ini（大小寫不敏感、確定為一般檔案）；未知副檔名、無關 JSON、子目錄／連結、格式錯誤 UUID 事件與 SHA256 失敗仍停止同步。
- [x] 事件數量上限只統計真正的事件及異常未知檔，desktop.ini 不計入；不讀取或改動 Windows metadata 內容。
- [x] 使用合成資料驗證 desktop.ini 共存時可同步；無關未知檔仍安全阻擋，受損事件仍拒絕且本機異常不清空。
- [x] Ruff check/format、pytest、Vitest、TS/Vite、版本一致性、Windows build+繁中 installer/更新器 E2E，AGENTS／README／TASKS 同步與本機 commit；不推 GitHub 或 Release，實際 Google Drive 多機驗收仍保留待驗收。

驗證結果：唯讀查到 root 1 的共享 events 目錄存在 Windows 系統檔 desktop.ini（未修改）。只跳過明確普通檔案 desktop.ini，未知檔與損壞 JSON 仍拒絕；合成同步 9 passed、完整 Python 193 passed、前端 Vitest 58 passed、Ruff check/format／TypeScript／Vite／版本一致性 v1.8.0 PASS。Windows packaging/build.ps1 Exit Code 0，繁中 FireLens-1.8.0-setup.exe、portable／installer updater READY/HEALTHY、rollback／故障注入 E2E PASS。不推 GitHub/Release；Google Drive 實際上傳與兩台電腦 UI 仍待驗收。

- [ ] 使用者 Windows 安裝新版後點「立即同步」，觀察正常 desktop.ini 不再誤擋及 Google Drive 真正上傳狀態。

### M17-I＋M17-J 合併施工驗證（2026-11-08）

歷史開發紀錄：本輪實際驗證：M17-I 原有括號備註匹配沿用，新增 4 項合成 SQLite／CSV／XLSX 回歸；M17-J 加入共享事件 journal、兩個模擬 Windows 用戶端、異常分類與單設備標記同步、手動衝突解決、離線 outbox、雲端事件缺失檢出與本機 archive 人工補回、備份預覽／復原、資料夾更名路徑遷移、啟用 API 和 UI。完整 pytest **192 passed**、Vitest **58 passed**、Ruff check/format、TS/Vite、版本一致性 **v1.8.0** PASS。Windows packaging/build.ps1 Exit Code 0，繁中 FireLens-1.8.0-setup.exe、portable/installer 更新器、READY/HEALTHY、rollback、故障注入 E2E PASS。合成測試無法證明 Google Drive 官方實際上傳／下載已完成。


使用者要求一次完成第 4 項「設備編號異常備註匹配」與第 5 項「Google Drive 多人同步與備份」。施工前已確認 M17 階段 A 存在尾端括號安全匹配與測試，不重造既有功能；多人異常同步尚未實作。程式與合成兩機測試通過不等於真實 Google Drive 多電腦驗收通過。

#### 第 4 項：備註匹配驗收

- [x] 維持先精確再尾端半形／全形括號註記匹配；只顯示清冊內設備、不前綴誤配、不跨類別／月份、不以註記判缺照片，不改清冊及照片檔。
- [x] 多候選及跨月份重複不自動選一個；精確原名與註記版並存時精確優先，UI、補拍清單、CSV／XLSX 顯示實際資料夾名稱與匹配方法。
- [x] 合成 SQLite 與各種匹配／非匹配／歧義案例完整回歸，核對已存在實作並同步歷史 TASKS。

#### 第 5 項：Google Drive 同步異常紀錄與防誤刪

- [x] 只在使用者主動啟用並指定根目錄後，在照片根目錄下建立獨立 FireLens-共享異常資料；不修改照片、清冊、不在 Drive 共用 SQLite。沿用既有異常單選與分類。
- [x] 每台電腦有穩定 device_id，每次變更產生不可變且獨立 UUID 事件檔，原子暫存寫入再 rename、SHA-256 校驗、格式版本及大小上限與重複事件去除。
- [x] 設備鍵採分類加相對路徑的穩定識別，不依賴 SQLite item.id；同步異常分類使用穩定 ID、不使用各電腦各自的 label_id 直接合併。
- [x] 启動後與手動同步讀取共享事件；離線、破損、回退、誤刪不能清空本機資料或自動覆寫遠端，沒有 Google Drive 完成同步證據時不報同步完成。
- [x] 本機每次成功套用新事件先建立不覆蓋歷史備份（版本、時間、SHA-256），放 FIRELENS_DATA_DIR/backups 或 LOCALAPPDATA/FireLens/backups 而非安裝目錄；提供備份清單與復原前預覽和人工復原。
- [x] 不同設備並行變更可合併，同設備並行修改或分類更名／停用衝突要人工確認，絕不靠時間戳靜默最後寫入者勝出；提供狀態、離線、衝突、最後同步時間及人工操作 UI。
- [x] 合成兩台客戶端及共享資料夾測試：不同設備、同設備衝突、分類變更、離線重連、重複、破損、刪除、回退、備份復原與重啟；只寫暫存資料。
- [x] Ruff、pytest、Vitest、TS/Vite、版本一致性、Windows EXE／繁中 installer、更新器 E2E，更新 AGENTS／README／TASKS 與本機 Git commit。不推 GitHub/Release，真實多 Windows＋Google Drive UI 另行驗收。

- [ ] 真實兩台 Windows 與 Google Drive 實機驗收待完成，合成兩機測試不代表 Google 官方同步已確認。
- [ ] 共享事件備份的自動保留天數及封存清理策略尚未定案；目前禁止自動刪除，超量安全停止。

### M17 歷史規格：設備編號尾端異常備註匹配（M17-A 已實作，M17-I 已回歸）

使用者提供實例：清冊設備編號為 `致-08-66`，照片實體資料夾可能為 `致-08-66(失壓)`。現行核對以完整 `item.code` 對 `ledger_row.device_no` 比對，導致存在照片仍可能顯示找不到設備資料夾。此需求先記錄，使用者表示還有其他問題要討論；**本階段只討論、不修改匹配程式與既有資料、不發布**。

擬採規則（正式實作前連同後續問題一起確認）：

- [x] 保留「清冊提供哪些設備，就只顯示那些設備」的 M17 規則；本次僅改善既有清冊列如何找到照片資料夾，不將其他設備加進核對結果。
- [x] 匹配優先順序：先完全相同編號；若找不到，再比對資料夾名稱尾端完整括號內的附註（半形 `()`、全形 `（）`），例如 `致-08-66(失壓)` 與 `致-08-66（壓力錶故障）` 候選。不得做不受控的前綴／模糊比對（`致-08-660`、`致-08-67(失壓)` 不得匹配 `致-08-66`）。
- [x] 若唯一匹配可核對照片槽位，清冊設備編號保持原值；UI 提示實際資料夾名稱、附註文字與「以尾端備註匹配」，不得把「失壓」直接當成缺照片。
- [x] 若多個可能候選、跨月份存在重複編號、或同時有原名與註記版，維持安全的明確匹配優先及待人工確認提示，不能任意選一個；不修改實體資料夾名稱、清冊原文或照片內容。
- [x] 同步檢查核對摘要、棟別／月份篩選、補拍清單與 CSV／Excel 匯出，確保匹配結果及實際名稱、提示一致；使用合成 SQLite／照片測試正常、無匹配、重複、多種括號、錯誤前綴與不變更來源資料。
- [x] 等使用者提出其他待討論問題並統一定案後，再決定實作範圍、測試、已決定升至目前開發版本。


### M17 歷史規格：清冊核對依設備類別獨立選擇搜尋資料夾（已實作與測試，待 Windows UI 驗收）

使用者提供「清冊與核對範圍」截圖：目前只有「照片根目錄／清冊版本／月份・批次」，實際建立的照片分類包含 **滅火器、放置盒、燈具**，三種設備更換月份、批次及照片槽位不同，必須由使用者明確選擇要核對哪一類，不能固定查滅火器或混合三類搜尋。此處是原始需求規格；後端分類範圍與前端設備選擇器此前已完成，本輪 M17-H 補強了分類專用月份選單、過期結果防護與合成測試。括號備註匹配屬另一優先項目，不在本輪更動。

#### 已確認的需求與擬定規格

- [x] 在「清冊與核對範圍」新增明確的「設備類別／搜尋資料夾」選擇器：**滅火器、放置盒、燈具**，預設可沿用現有滅火器流程，實際預設值與記憶選擇方式待定。
- [x] 選擇滅火器時，僅搜尋所選照片根目錄下的滅火器分類；選擇放置盒時僅搜尋放置盒；選擇燈具時僅搜尋燈具。不得跨類別誤配相同編號，也不得因未選類別就混算三類。
- [x] 選擇設備類別後，核對結果、總筆數、缺失統計、棟別樓層、補拍清單以及 CSV／Excel 匯出都只以**選定清冊內設備**和**選定類別**為範圍；照片目錄額外的設備仍不列入清冊核對，不刪除任何照片或清冊。
- [x] 月份／批次應只在所選類別下生效：例如滅火器在 10 月更換，放置盒在 11 月更換，燈具在其他批次更換；各自查詢不互相影響。保留留空時跨該類別所有月份／批次的行為。
- [x] 實際核對照片所需槽位需按類別判斷：滅火器「編號／藥劑／完成」；放置盒、燈具「前／中／後」；沿用各分類既有規則，不以滅火器槽位判斷燈具。
- [x] 切換類別、根目錄、清冊或月份／批次時，清除過期的核對畫面／匯出狀態，防止拿上一次類別的結果誤匯出；重新開始核對後顯示本次使用的類別、清冊及範圍。
- [x] API 與後端改為接收並驗證設備類別，資料查詢以 root_id + category_code + optional period 限定，保留清冊設備編號為核對主鍵；舊清冊、既有資料庫及照片不可破壞。
- [x] 合成資料驗收：真實合成 SQLite/照片索引涵蓋三類同編號、不同月份、缺照片、無資料夾、跨批次與清冊外設備；核對清單與 CSV/XLSX 的分類範圍一致，不跨類別或月份誤配。
- [ ] Windows 實機 UI 待驗收：安裝新版後實際選滅火器／放置盒／燈具、切換各自月份與清冊，確認畫面／缺失匯出一致；不能以合成測試代替實機。
- [x] 使用者已明確要求按既定優先順序繼續；本輪執行三類獨立搜尋，不建立 Git Tag 或 Release。

#### 待決定事項

- 清冊目前未綁定設備類別：是否讓每份清冊永久記錄類別（例如「放置盒 11 月清冊」），並在選取清冊時自動切換類別；或每次由使用者手動選擇？此處先不自行決定。
- [x] 本輪採用依所選根目錄及設備類別的月份／批次下拉選單（另可選全部月份），不需手動輸入。
- 若放置盒與燈具的清冊格式、命名規則不同於滅火器，需另以使用者現場範例確認，不能擅自假定所有編號格式一致。

### M17-H 第 3 優先：清冊核對三種類別獨立搜尋與月份範圍 UX 補強（2026-11-08）

使用者已要求繼續依凍結順序施工。本次核對現況：ReconcileView 已有滅火器／放置盒／燈具選擇器、POST /api/reconcile 已依 root_id/category_code/period 限縮；切換類別仍可能殘留上一類手動月份、選擇器未提供分類可用批次清單、核對／匯出非同步請求有過期回應覆蓋風險。**僅補強已存在的第 3 優先，沒有使用者額外授權不得更動設備編號括號匹配與多人同步。** 舊清冊暫不強制綁定類別；放置盒／燈具可手動選既有清冊，不擅自改資料模型。

- [x] 使用目前選定 root_id 的既有 API tree 讀取類別與可用月份／批次，三類分別列出；類別或根目錄變更時同步切換批次選單，預設「全部月份／批次」。既有已選清冊 ID 維持獨立選取，切換分類不會把滅火器的 10 月誤帶到燈具 11 月。
- [x] 清冊範圍 UI 明確標示「照片根目錄／設備類別／月份批次／清冊」，核對成功後顯示當次實際類別和批次。所有切換類別、根目錄、清冊、月份／批次或匯入清冊的狀況必須清除舊核對結果、補拍列表與匯出 token，請求進行中鎖定表單或以 request generation 防止舊回應覆寫。
- [x] 保留已存在的後端 root_id + category_code + period 唯讀設備查詢、按類別照片槽位判定（滅火器編號／藥劑／完成；盒／燈前／中／後）、清冊內設備為主、清冊外不計入以及 CSV／XLSX 匯出範圍；使用測試釐清是否存在跨類別、跨月份或相同設備編號誤配並只修正測試證實的問題。
- [x] 合成 SQLite 與三分類照片驗證：三類同設備編號、10／11／12 月份、缺照片／無資料夾／清冊外設備，核對與 CSV／XLSX 只包含選定分類清冊內資料；前端 Vitest 驗證分類月份、空清單、未支援類別與不同根目錄／清冊範圍比較、非同步舊結果拒絕。

- [x] 開發與打包測試：Python pytest 180 passed、前端 Vitest 58 passed、Ruff check/format、TypeScript/Vite、版本一致性 v1.8.0 通過；Windows packaging/build.ps1 Exit Code 0、繁中 installer、portable/installer updater READY／HEALTHY、rollback 及故障注入 E2E 通過。納入尚未正式 Release 的 v1.8.0，AGENTS／README／TASKS 已同步，本機 Git commit 待建立；不推送 GitHub，不碰現場資料。
- [ ] 使用者 Windows 實機驗收：逐類別切換月份、清冊核對、核對完成率、各類別缺失照片槽位、補拍清單與 CSV／Excel 匯出及開啟檔案；不宣稱尚未觀察的 UI 已完成驗收。

### M17 歷史規格：Drive Desktop 多人共用異常與備份（M17-J 合成驗證，待實機）

**使用者已確認資料環境**：共用的「滅火器更換照片」根目錄是 Google Drive 電腦版同步到 Windows 檔案總管的資料夾。不同 Windows 電腦的 FireLens 應共用瓶身超過10年、無法辨識、壓力錶故障等異常單選標記、自訂分類及統計；啟動時讀取雲端資料、檔案變更即備份至本機，雲端遭誤刪時能恢復。此輪只記錄規格，不修改程式。

#### 已確認的目標

- [x] 共享資料置於使用者選取的 Google Drive「滅火器更換照片」根目錄下的獨立資料夾，與照片分開。電腦 A 修改，電腦 B 待同步完成後可讀取相同異常標記與統計。
- [x] 啟動 FireLens 時讀取並驗證共享資料，偵測 Google Drive 同步檔案變更；離線時使用最後已驗證的本機快取，明確顯示已同步、等待同步、離線或衝突及最近同步時間。
- [x] 每次取得新的有效共享資料版本，建立本機不覆蓋的歷史快照備份並記錄 SHA-256、時間及版本；使用者希望放在安裝目錄內，須評估安裝版 {app}\data 升級與權限、portable 差異，必要時改存 %LOCALAPPDATA%\FireLens\backups 並顯示路徑。
- [x] 雲端檔案刪除、空白、JSON 破損、版本退回、衝突或尚未下載時不得把本機資料清空，也不得自動覆寫雲端；保持最後有效快照及備份，提示使用者處理。
- [x] 提供本機備份版本清單、設備異常筆數差異預覽、校驗與手動復原；復原前重新核對遠端狀態、先保留復原前版本，避免多台電腦競相還原。
- [x] Google Drive 同步磁碟不提供可靠跨電腦資料庫交易鎖：禁止多台電腦直接寫共用 SQLite 或同時覆蓋單一 JSON。優先評估每次變更獨立事件 JSON（唯一事件 ID、裝置 ID、設備穩定識別、操作版本）＋快照與合併機制。
- [x] 每台設備仍最多一個目前異常。不同電腦同時修改同設備不得靜默互相覆蓋；自訂異常分類的新增、更名、停用也要同步，保留完整操作者衝突決策與稽核的擴充空間。
- [x] 與多個根目錄、設備類別、同編號不同月份及資料夾更名相容；共享設備識別不只依賴可重建 item.id，不能因資料夾暫時離線而刪除異常紀錄。
- [x] 安全檢查：資料格式版本、內容大小、SHA-256、原子寫檔、備份保留數量與清理策略；避免重複事件和無限備份循環。不得改動真實照片與清冊。
- [x] 以兩個模擬 Windows 用戶端與合成雲端同步目錄測試：不同設備並行修改、同設備衝突、分類變更、離線重連、延遲同步、誤刪／空檔／破損、備份復原、升級後資料保留。

#### 待與使用者確認

- 異常分類是所有共用根目錄一套，還是每個根目錄獨立？
- 同設備兩人同時修改時是要求人工確認，還是採明確可稽核的合併規則？
- 共享資料實際目錄、備份位置、保留天數／份數、是否記錄操作者名稱及復原權限。
- 待使用者其他需求一併確認後才決定實作方案，不編譯、不推送、不發布。

- [ ] 真實 Google Drive Desktop 多電腦驗收：官方傳輸完成、ACL、延遲、佔位檔、雲端回退復原和 Windows UI 尚待實際操作。

### M17 待實作：照片資料夾樹直接新增子資料夾（使用者已同意 UX 方案）

使用者提供樹狀目錄紅色標記示意：在「滅火器／放置盒／燈具 → 年份 → 月份／批次 → 棟別 → 設備編號」各層節點旁提供就地新增入口，減少移動至其他面板的操作。使用者已同意以下互動設計；**本輪只記錄 TASKS，不修改程式、版本或發布**。

- [ ] 資料夾樹的可新增節點，滑鼠移入該列時才顯示右側「＋」；鍵盤聚焦亦應可操作，提供可辨識的 title／aria-label。另支援右鍵選單「新增…」，避免常駐過多按鈕造成視覺雜亂。
- [ ] 依所選節點層級決定新增類型與一致的繁體中文文案：選「滅火器／放置盒／燈具」→「新增年份」／欄位「年份」；選「2026年」→「新增月份／批次」／欄位「月份或批次名稱」；選「11月份更換」→「新增棟別」／欄位「棟別名稱」；選「中正樓」→「新增設備編號」／欄位「設備編號」。設備編號葉節點不再提供新增子資料夾，維持照片管理操作。
- [ ] 按「＋」或右鍵「新增…」後，彈出應用內視窗：標題由層級自動帶入，顯示「新增位置」完整父目錄路徑、單一明確名稱欄位、格式範例／必要提示，以及「取消」「新增資料夾」按鈕；視窗不得讓使用者不知會新增至哪個分類、月份或棟別。
- [ ] 建立前驗證資料夾名稱：必填、同層已存在（含 Windows 大小寫不敏感撞名）、保留名稱、非法字元、尾端空格或句點、長度及路徑安全，顯示可理解的繁體中文錯誤；不自動覆蓋或改動既有資料夾。
- [ ] 新增成功後立即刷新樹狀索引、自動展開父層、滾動定位並選取新資料夾；失敗則保留輸入內容與目前展開狀態，顯示具體原因。
- [ ] Google Drive 離線、雲端未下載、目錄無寫入權限、掃描中或同步狀態不安全時遵循專案現有安全策略，不誤建空目錄或失去同步；所有入口共用既有的安全新增 API／驗證邏輯，不另建平行流程。
- [ ] 保留既有「快速新增資料夾」面板作為大量建立入口；樹上的「＋」、右鍵選單與既有面板共用核心新增流程，避免資料格式及防呆規則不一致。
- [ ] 回歸測試：滅火器／放置盒／燈具各層正確新增、同名及非法名稱阻擋、離線／唯讀阻擋、取消無副作用、建立後展開定位、鍵盤可操作、右鍵行為、既有快速新增不退化；Windows UI 實際驗證，測試資料須為合成目錄。
- [ ] 與 M17 其他待辦（括號異常備註核對、三類獨立搜尋、Google Drive 異常同步及備份）一起統一排程，使用者尚有需求要討論；目前不建立 Git Tag 或 Release。

### M17 待實作：匯出缺失 CSV／Excel 後直接開啟檔案或所在資料夾（使用者已提出）

使用者截圖顯示清冊核對匯出成功後，畫面目前僅呈現綠色「已儲存...位置：C:\\Users\\...\\Downloads\\FireLens\\...csv」文字。要求成功通知旁加入可點擊的 **「開啟檔案」** 與 **「開啟所在資料夾」** 操作，CSV 與 Excel 都應適用。本階段只記錄，不修改程式碼或發布。

- [ ] 匯出 CSV 或 Excel 成功時，訊息區顯示檔名／完整儲存路徑、檔案大小，以及緊鄰的「開啟檔案」「開啟所在資料夾」兩個按鈕；不需使用者複製或貼上路徑。
- [ ] 「開啟檔案」使用 Windows 預設關聯程式開啟此次成功匯出的 CSV／XLSX；「開啟所在資料夾」使用 Windows 檔案總管開啟父目錄，最好直接選取該檔案（Explorer /select）。
- [ ] 保留現有原子寫入與不覆蓋匯出模式。新按鈕只能針對最後一次由 FireLens 成功儲存並驗證的檔案，不接受前端任意提供的絕對路徑、shell 指令或可執行檔。
- [ ] 本機開啟能力限定 Windows 桌面模式：在後端或受信任桌面橋接層實作受控 API，依已記錄匯出檔案驗證存在、限制副檔名 csv／xlsx、核對允許匯出目錄及正規化路徑，避免命令注入與任意檔案開啟；用安全的 subprocess 參數陣列或 Windows Shell API，不插入 shell 字串。
- [ ] 開啟失敗（檔案已移動／刪除、無預設應用程式、權限不足、Explorer 無法啟動）顯示繁體中文原因，保留原始路徑可複製；不得把「已儲存」誤顯示為「已開啟」。
- [ ] 重新匯出、切換清冊、照片根目錄、設備類別或月份批次時，清除過期的匯出檔案操作，避免開啟上一次核對結果；匯出失敗時不顯示新檔案操作。
- [ ] 支援鍵盤焦點、螢幕閱讀器標籤與按鈕禁用狀態；瀏覽器模式維持原 GET 下載行為，沒有 Windows 桌面橋接時不顯示無效的本機開啟按鈕。
- [ ] 以隔離測試匯出目錄測試 CSV 與 XLSX、打開檔案、Explorer 選取檔案、檔案不存在及惡意路徑拒絕；Windows pywebview 打包後 UI 必須實際點擊驗證，不使用真實現場資料。
- [ ] 與 M17 其他需求一併規劃實作，暫不重編、不 Git commit/push/release。

### M17 待實作：照片檔名辨識清單式管理與說明視窗（規格討論）

使用者指出現有「檔名同義詞」三欄 JSON 文字輸入不適合一般人，建議改名「照片檔名辨識設定」，以滅火器／放置盒／燈具分類切換的清單管理。右上角新增「？使用說明」按鈕，按下跳出小視窗解釋用途與範例。現階段只記錄不實作。

- [ ] 清單列顯示「照片實際檔名（不需副檔名）」→「對應照片用途（從當前類別合法槽位選擇）」，提供新增、修改、移除；預設保留既有規則並相容目前 JSON 儲存格式，不破壞已儲存設定。
- [ ] 右上角「？使用說明」彈出小視窗，簡短解釋：有效日期.jpg → 藥劑、更換完成.jpg → 完成；只是辨識照片用途，不會重命名原始照片。
- [ ] 新增規則時阻擋重複檔名、無效名稱與跨槽位歧義；提供「測試辨識」輸入檔名即顯示命中用途／未匹配，操作錯誤訊息繁體中文。
- [ ] 視窗支援 X、Esc、焦點與鍵盤操作；完整 Windows 深色／淺色模式可讀性均需測試。使用合成資料確認原 JSON 資料升級、儲存及重啟後保持一致。

### M17 待修復：清冊「查看範例／使用教學」改真正的彈出視窗

使用者表示按下後沒有明顯反應。程式檢查發現 ReconcileView.tsx 已有 tutorialOpen 狀態，但教學目前在頁面控制項上方以一般區塊呈現，不是置中彈窗，容易看不出點擊效果；實際點擊是否還有故障需 Windows UI 驗證。

- [ ] 將「查看範例／使用教學」改為真正的置中模態對話框，開啟時在目前視窗立即可見，不因頁面捲動而顯示在畫面外。
- [ ] 教學涵蓋單欄／雙欄 Excel 或文字、設備類別選擇、月份批次、核對結果分類、缺失匯出，並提供可複製的合成清冊範例。
- [ ] 首次教學自動顯示與「下次不再自動顯示」偏好仍保留，但右上角手動查看必須永遠可開啟；支援 X、Esc、焦點管理與關閉後回到觸發按鈕。
- [ ] 與檔名辨識「使用說明」共用一致的對話框視覺與無障礙模式；在 Windows pywebview 實際點擊測試、深淺色模式及小視窗尺寸驗證。

### M17 待修復：完整改善 FireLens 深色模式的對比與按鈕配色

使用者提供照片牆深色模式截圖：照片槽位標題（編號／藥劑／完成）呈現深灰近乎不可讀；照片卡片、檔名、次要提示與按鈕淺色底／深色背景不協調；「換圖／重新命名／刪除」的窄按鈕會擠壓斷行。需系統化修正，不只套幾條臨時 CSS。程式檢查發現 styles.css 有 html[data-theme=dark] 與 prefers-color-scheme 媒體查詢兩組局部覆蓋，許多子元件仍沿用淺色固定顏色。

- [ ] 建立統一的淺／深色主題 tokens：頁面、面板、卡片、輸入欄位、邊框、主文字、次文字、禁用文字、主要／次要／危險按鈕、hover／focus／selected／error／success，避免某頁局部硬編碼造成色彩落差。
- [ ] 深色照片牆將「編號／藥劑／完成」槽位標題及相簿檔名使用高對比亮色主文字；「1張／缺照片」、拖放提示、詳細資訊等使用足夠可讀的次要文字，禁止深灰字配深灰底。
- [ ] 重新設計深色模式下「加入照片」「換圖」「重新命名」「刪除」「更改名稱」、異常下拉選單、狀態提示：同一色系與明確視覺層級，危險操作用不刺眼但可辨識的警示色，hover／focus／disabled 都清楚。
- [ ] 調整照片卡片操作區的排列、按鈕最小寬度與文字不合理直排／擠壓問題，兼顧不同 Windows 視窗寬度、150% 縮放與中文長字串。
- [ ] 逐頁檢查照片瀏覽、清冊核對、統計、整理工具、設定與新增／改名／教學彈窗；system 自動深色和明確 dark 設定必須一致，light 模式不能被回歸影響。
- [ ] 設定目標：正常文字 WCAG AA 對比至少 4.5:1，大字及主要 UI 視覺至少 3:1（適用時）；進行實際打包版 pywebview 深色／淺色截圖比對、鍵盤焦點／選取／停用狀態與回歸測試。
- [ ] 本需求只記錄並與其他 M17 規格一起實作；尚未編譯、commit、push 或 Release。

### M17 歷史需求：異常統計 CSV／Excel 匯出（階段 A 已開發，本輪補強）

使用者提供「統計／設備異常統計」頁面截圖，要求導航列「統計」改成更清楚的「異常統計」，並在異常設備清單提供 **匯出 CSV、匯出 Excel**，成功後與清冊缺失匯出相同顯示「開啟檔案」「開啟所在資料夾」。此段是原始需求紀錄；階段 A 已有功能，本輪補強篩選與匯出一致性，不推送或發布。

- [x] 導覽列「統計」改為「異常統計」，功能頁標題沿用「設備異常統計」，保持語意一致；如有教學／提示／無障礙名稱同步調整，不改變既有分類與統計資料。
- [x] 在「異常設備清單」篩選與重新整理旁新增「匯出 CSV」「匯出 Excel」按鈕，清楚呈現進度、成功檔名與大小、儲存路徑、失敗原因；兩種格式可直接由 Excel 開啟。
- [x] **匯出內容與目前清單一致**：根目錄、點選的異常分類卡片、棟別樓層、關鍵字搜尋等條件全部套用後，依畫面排序產出當下符合條件的異常設備，不把未顯示、未標記或其他根目錄資料混入；匯出前顯示筆數，0 筆時提示無資料，避免誤會匯出全體。
- [x] 匯出欄位至少包含「設備編號、異常分類、棟別樓層、月份／批次、根目錄、標記時間、照片來源／相對路徑」，也可補年份、來源同步狀態以支援多人共用；照片操作按鈕不可輸出成無效的 UI 文字。欄位順序需一致，CSV 使用 UTF-8 BOM；Excel 為有效 xlsx 且標題、欄寬與篩選可讀。
- [x] 共用清冊匯出的安全本機儲存機制：預設存到 Downloads/FireLens，檔名採「FireLens-異常設備清單-時間戳-隨機值.csv／xlsx」，不覆蓋既有檔案、原子寫入；重用受控開檔/Explorer 能力，不另造不一致的匯出邏輯。
- [x] 匯出成功訊息旁提供「開啟檔案」與「開啟所在資料夾」兩按鈕，Windows 預設程式開啟 CSV／Excel，Explorer 定位檔案；檔案不存在、無預設程式或權限失敗時顯示錯誤。不得接受未驗證的任意路徑或執行檔。
- [x] 切換根目錄、分類、棟別、搜尋條件或資料刷新後，清除過期匯出操作，避免開啟不符合目前畫面的舊檔案；必要時匯出時鎖定所用篩選快照，防止前後端結果不一致。
- [ ] 與 Google Drive 多人共用異常紀錄方案相容：匯出只取當下已驗證且已顯示的統計資料，若同步尚未完成／離線，清楚標示資料時間及同步狀態，不假稱最新。
- [x] 合成測試包含篩選與排序、UTF-8 BOM、中文設備編號、公式注入、XLSX 標題與欄寬、0 筆、儲存與開檔 token 安全、預期筆數不同時 HTTP 409 且不留下檔案。
- [ ] Windows 桌面實際點擊 CSV／Excel 匯出與「開啟檔案／開啟所在資料夾」仍待使用者實機驗收。
- [x] 此為歷史「先記錄」需求，目前已進入第 2 優先驗收／補強階段；不推送 GitHub 或 Release。

### M17-G 第 2 優先：異常統計 CSV／Excel 匯出核對與補強（2026-11-08）

依使用者「繼續」及五項優先順序，第 2 項為異常統計 CSV／Excel 匯出。**施工前發現階段 A 已有功能碼**（StatisticsView 匯出按鈕、POST /api/issues/export/save、export_issue_rows、ExportRegistry 與合成測試），不得重造 API／UI 或改動已完成的功能。此次以差異驗收及修補為主，不開始第 3～5 項。

- [x] 修正統計匯出與 UI 篩選一致性及競態：按匯出時鎖定根目錄／異常分類／棟別樓層／關鍵字和畫面筆數快照。後端比較預期筆數，差異時在寫入前回報 409，不留下過時的匯出檔；前端若使用者在等待期間改變篩選、重新整理或改異常分類，不得顯示舊結果可開啟的按鈕，也不得把舊匯出標為目前清單。
- [x] 核對 CSV UTF-8 BOM 與 Excel XLSX 有效欄位、筆數、順序、中文設備名稱、保留文字設備編號以及公式注入防護；匯出只依既有一設備一異常與篩選順序，不把照片操作按鈕當內容，0 筆時禁用或清楚提示。
- [x] 共用既有安全 Downloads/FireLens 匯出與不透明 open_token 開檔能力；對不存在檔、任意 token、變更過期、Windows Explorer／預設程式錯誤具體回報。不得直接接受前端路徑，不觸碰現場照片／清冊，不推送個資或憑證。
歷史開發紀錄：- [x] 使用合成統計及隔離 API 資料庫測試：CSV/XLSX 中文與欄位順序、前置零設備編號、Excel 字串格式與公式注入、篩選後 2 筆、0 筆阻擋、HTTP 409 不產生檔案及開檔 token。Python pytest 179 passed、Vitest 48 passed、Ruff check/format、TypeScript/Vite、版本一致性 v1.8.0 全部通過。
- [x] Windows packaging/build.ps1 Exit Code 0，繁中 FireLens-1.8.0-setup.exe、Windows EXE 及 updater portable/installed READY／HEALTHY／rollback／故障注入 E2E 均通過；AGENTS/README/TASKS 已同步，待本機 Git commit。不 push／Release，維持未正式發布的 v1.8.0 版本。
- [ ] 使用者在 Windows 真正點擊異常統計的 CSV／Excel 匯出，確認檔案能以關聯應用程式開啟、檔案總管可正常開啟所在資料夾；模擬 API/自動更新 E2E 不代表實際 Windows UI 已驗收。

歷史開發紀錄：### M17 階段 A 實作紀錄（目前 v1.8.0 開發分支，尚未驗收／發布）

- [x] 施工前以 Git commit `0f9bc7d`、本機 tag `backup/pre-m17-20261107` 建立還原點，並切換至 `feature/m17-improvements` 分支。
- [x] 清冊核對後端新增滅火器／放置盒／燈具類別條件，保留只顯示匯入清冊列；尾端括號備註安全匹配並保留原資料夾名稱，跨類別及多候選不會自動亂配。補上合成 SQLite 測試。
- [x] 清冊教學改模態視窗、檔名辨識改清單編輯與說明視窗、異常統計改名、暗色 UI 初步改善；前端 TypeScript/Vite 建置通過，尚待實際 Windows UI 驗證。
- [x] 異常統計新增 CSV/XLSX 匯出與篩選；清冊及異常匯出共用安全儲存與以不透明 token 開啟檔案／資料夾，完成合成檔案與錯誤路徑測試。
- [x] 樹狀資料夾新增懸停「＋」、右鍵操作及依層級建立視窗，並新增年份 API 與資料夾 catalog；沿用月份、棟別、設備新增 API。新測試對年份隔離資料夾驗證通過。
- [ ] Windows pywebview 實機 UI 驗證：模態焦點／Esc、樹狀右鍵與新增路徑、深淺色對比、兩類匯出後真實開檔／Explorer。
- [ ] Google Drive 同步多人異常紀錄與本機多版本備份、雲端誤刪恢復：**尚未接入現場同步，避免未處理衝突就上線**，需先完成合成多用戶端事件合併與復原測試。
- 歷史公開資料夾 API Key／iframe 需求：**已由使用者取消**，改以 M17 階段 D「限制存取 + Google OAuth」取代。
歷史開發紀錄：- [x] 已執行版本一致性 v1.8.0 PASS、Ruff check PASS（排序修正後）、pytest 111 passed、Vitest 31 passed、TypeScript/Vite PASS、Windows EXE 與繁中 FireLens-1.8.0-setup.exe 正式 build Exit Code 0；打包後 self-test、portable/installer READY/HEALTHY、rollback/故障注入 E2E 均 PASS。
- [ ] 尚待 Windows 實際操作 UI 完整驗收，及 Google Drive 兩項功能；未推送 GitHub 或 Release。
- 原有各小節保留完整需求與驗收範圍，其「待實作／只討論」文字為原始需求記錄；以上階段紀錄為最新施工事實，只有完成測試及實機驗收後才可勾選剩餘項目。

### M17 待實作：照片槽位間左右拖曳交換（含檔名、安全確認與復原）

使用者提供照片槽位牆截圖：同一設備下「編號／藥劑／完成」可能把照片放錯槽位，希望直接把照片左右拖曳到正確欄位，**連同照片檔名所代表的槽位一起調整**，拖放後先跳出「確認交換照片」對話框，只有確認才動實體檔案。此項為 M11「未對應照片拖曳歸槽」以外的新能力；不得把已完成的 M11 重新實作。使用者本輪僅要求寫 TASKS，尚未動程式。

- [ ] 在同一設備的照片牆支援由「編號」拖曳到「藥劑」、由「藥劑」拖到「完成」等任兩個合法槽位；來源與目標明顯高亮、顯示預計放置位置及正確移動／交換提示，未確認不得執行寫入。
- [ ] 目的槽位**已有照片**時預設為「交換」：同時將來源與目標兩張照片對調槽位，並安全互換其槽位檔名（如 `編號.jpg` ↔ `藥劑.jpg`），確保核對所見的照片與名稱一致；不得只交換畫面上的縮圖或僅修改資料庫欄位。
- [ ] 目的槽位**沒有照片**時為「移至槽位」：將原檔重新命名為目標槽位名稱，保留原副檔名及檔案內容，來源槽位改顯示缺照片。若命名碰撞或多張特殊命名，先預覽且阻擋不安全操作，不直接覆蓋。
- [ ] 交換前彈出置中「確認交換照片」視窗，同時顯示兩張縮圖、來源／目的槽位、原始檔名 → 預計新檔名、完整設備編號，以及「取消」「確認交換」；移至空槽時改「確認移動照片」。支援 X／Esc 取消，點擊取消或視窗外均不得變動檔案。
- [ ] 因槽位可能有多張照片、照片副檔名不同或已使用 `藥劑-1.jpg` 等名稱，必須以**拖曳的單張照片**為交換單位，保留其他未選照片的名稱與排序；重複名稱與槽位單張限制依現有規則正確驗證，無法安全判定時顯示原因並取消，不自行決定覆蓋哪張。
- [ ] 僅允許同一設備資料夾且同一設備類別的合法槽位間操作；跨設備、跨根目錄、跨月份與未對應舊照直接交換時一律拒絕或走既有 M11 歸槽流程，不得造成跨設備混用。放置盒、燈具（前／中／後）亦支援。
- [ ] 後端新增「交換／移動預覽 → 使用者確認 → 安全執行」API；執行前驗證 photo_id、item_id、來源目標合法性、檔案存在與 SHA-256、檔名碰撞、雲端占位未下載、目錄是否連線、掃描／整理工作是否進行中。不得讓前端自行指定任意絕對檔案路徑。
- [ ] 同名交換採安全暫存名稱與原子化／可回滾交易順序；任一步失敗立即還原兩張原始檔案及索引，保留原始位元組、不重新壓縮、不降低畫質，不留下孤兒暫存檔。Google Drive 尚未同步完成時顯示狀態與錯誤，不把尚未驗證成功當成完成。
- [ ] 成功後刷新兩側槽位、檔名、照片數量與缺照片狀態，核對結果需待重新核對時正確讀取；寫入稽核／rename 紀錄並提供安全復原，復原也要二次檢查來源與目的目前雜湊及衝突，不能覆蓋其他同事的新操作。
- [ ] 無法使用拖放時提供鍵盤或按鈕替代入口「移動／交換照片」，並保留既有「換圖」「重新命名」「刪除」「未對應照片拖曳歸槽」功能；桌面深淺色與不同視窗尺寸的拖放目標、確認視窗都清晰可用。
- [ ] 合成測試至少涵蓋：編號↔藥劑交換、藥劑→空的完成槽位、前↔後交換、多張照片只交換指定的一張、不同副檔名、名稱衝突、跨設備拒絕、離線／占位阻擋、掃描中阻擋、取消完全不變、故障注入與 rollback、復原、檔案 SHA-256 不變；並完成 Windows 實際拖放與對話框操作驗收。
- [ ] 這是新增的待辦，不在本次僅寫文件的工作中編譯、commit、push 或建立 Release；排入後續 v1.8.0 開發驗收範圍，依 AGENTS.md 版本管理規則處理。

### M17 待實作：LINE 電腦版複製圖片後直接貼上照片槽位（Ctrl+V／貼上按鈕）

使用者現場流程：在 LINE Windows 電腦版查看滅火器照片，右鍵選「複製」，切換 FireLens 的設備照片牆，直接對「編號／藥劑／完成」其中一個指定槽位按 `Ctrl+V` 或點「貼上照片」，不再先另存檔、再按「加入照片」。放置盒／燈具的「前／中／後」亦需支援。**此功能與既有拖曳／檔案選取不同。現已開發 Browser Clipboard API MVP，待 Windows LINE 實機驗證。**

- [ ] 每個照片槽位在「＋加入照片」旁新增 **「貼上照片」** 按鈕；當 Windows 剪貼簿存在可使用的圖片內容時顯示可點擊狀態，沒有圖片時停用並呈灰色。不能只因剪貼簿有一般文字、網址就啟用。
- [ ] 支援滑鼠先點選槽位再按 `Ctrl+V` 貼入；貼上必須對應**目前指定的設備與槽位**。沒有明確槽位時提示「請先選擇要貼上的照片槽位」，不可猜測將照片放到編號或藥劑；在輸入框內的 `Ctrl+V` 保留一般文字貼上，不攔截。
- [ ] 點擊「貼上照片」或快捷鍵時讀取當下剪貼簿，偵測有效圖片資料／LINE 提供的影像檔案清單（可能是 bitmap、PNG/DIB、檔案路徑或其他 Windows 剪貼簿格式）；實作前先在**真實 LINE 電腦版 + Windows 11 pywebview** 驗證「複製」究竟提供哪些格式，不得假定所有版本均可用 `navigator.clipboard.read()`。對於只複製文字／無圖片／無權限應明確提示，不當作圖片儲存。
- [ ] 「貼上照片」的啟用狀態在 FireLens 視窗重新取得焦點、選擇設備／槽位及剪貼簿變化時更新；Windows 桌面環境可採受控原生剪貼簿格式檢測，避免頻繁複製整張圖片或強制彈出權限提示。純瀏覽器版無法可靠主動讀取狀態時使用漸進式降級，不謊稱能全面自動偵測。
- [ ] 讀到圖片後先開「確認貼上照片」預覽視窗，顯示縮圖、設備編號、目標槽位、檢測到的圖片格式／大小與預計儲存檔名（例如 `編號.jpg`）；選「取消」不得產生照片或更動剪貼簿。確認才使用現有 `api.importPhoto` 的安全匯入路徑，沿用自動命名、照片槽位索引、重掃與離線佇列機制。
- [ ] 目標槽位已有照片時遵守現有單張／多張限制：允許加第二張時明確告知新檔名；不允許增加時提示使用「換圖」或確認替換**指定**照片，不能直接覆蓋原檔，也不得把剪貼簿貼上當成無條件覆蓋。
- [ ] 僅接受專案支援的影像格式與大小，剪貼簿若為 DIB/bitmap 等非原生儲存格式，應以可靠轉碼流程保留照片方向與畫質、提供正確副檔名；防止損毀內容、惡意路徑、過大圖片或資料無法讀取；不得因貼上照片刪除 LINE 原圖。
- [ ] 貼上操作期間若切換設備、根目錄或類別，確認視窗必須鎖定原始目標並重新驗證，避免將 A 設備照片錯放到 B 設備；掃描中、繁忙、權限不足、未下載 Google Drive 占位、離線情況沿用原有安全判斷，若既有離線匯入佇列可安全使用需明確顯示待同步狀態。
- [ ] 保留既有「加入照片」「拖曳圖片」「換圖」「重新命名」等功能；鍵盤焦點、按鈕 disabled、拖曳交互與深淺色模式須一致，不新增多餘操作步驟。
- [ ] 使用合成剪貼簿圖片與 Windows LINE 實機測試：有圖片／純文字／空剪貼簿、PNG/JPEG/DIB、Ctrl+V 指定槽位、三類設備、已有照片單張／多張、取消不寫入、檔名衝突、Google Drive 離線、安全權限及切換設備後不誤貼；並驗證真實 pywebview 上按鈕狀態可用。
- [x] MVP：React 槽位可被選取，新增「貼上照片」、Ctrl+V 讀取 PNG／JPEG／HEIC／HEIF 圖片；文字／空剪貼簿不寫入；確認預覽後透過現有安全 `api.importPhoto` 複製匯入，取消不寫入。圖片大小上限 100 MB，設備／根目錄切換會清除預覽。
歷史開發紀錄：- [x] 基本前端合成測試：clipboardImage 3 項通過；Vitest 全量 34 passed，TypeScript/Vite build PASS，版本檢查 v1.8.0 PASS。
歷史開發紀錄：- [x] Windows 正式建置 PASS（2026-11-07）：FireLens.exe 與繁中 FireLens-1.8.0-setup.exe，Exit Code 0；包含打包後 self-test、portable/installer 更新 E2E、READY／HEALTHY、rollback 與故障注入；Ruff PASS、Python 111 passed、Vitest 34 passed。
- [ ] Windows 11 實機 LINE → FireLens WebView2：確認 Ctrl+V、按鈕剪貼簿權限、圖片格式、檔案預覽／實際成功匯入及視窗交互；尚未看到實際輸出，不得宣稱實機通過。
- [ ] Windows 剪貼簿狀態確定性：Clipboard API 權限拒絕／不支援時目前採漸進退化（狀態未知時不禁用按鈕，沒有支援圖片時才灰色）；若 WebView2 無法可靠辨識 LINE 來源，另實作 Windows 原生橋接與格式相容、DIB 轉換及針對性測試。
- [ ] 貼上多照片與槽位衝突的視覺及 Windows UI 驗收、打包後 EXE self-test；未 GitHub push 或 Release。

### 開發流程確認（2026-11-07）

- [x] 使用者再次明確要求：**新功能必須先寫入 TASKS.md，確認任務與驗收條件，才可以修改程式。** 已在 `AGENTS.md` 增列開發前強制閘門。
- [ ] 後續每項新需求嚴格依「先 TASKS → 後施工 → 測試 → 回寫 TASKS」執行，不得用事後補寫取代前置規劃。

### M17 階段 B 施工單（2026-11-07，先寫 TASKS 再開發）

本輪從尚未完成的「照片槽位間左右拖曳交換」開始，範圍限制同一 item、單張來源圖片與明確選定的目標槽位，不碰真實 Google Drive；已有 M11 未對應照片歸槽流程不重做。歷史章節的「尚未實作」為原始需求，請以本施工單驗收實情為準。

- [x] 實作受控的「預覽移動／交換」資料模型與後端 API，只接受 photo_id、指定 slot、可選 target_photo_id；區分空槽移動與有照片交換，禁止跨設備、不合法槽位、名稱碰撞、佔位照片及離線。
- [x] 實作雙照片安全交換與失敗回滾：保留原始副檔名及位元內容，以暫存路徑交換實際檔名；執行前再次驗證 SHA-256／預覽識別碼，失敗不留下混亂索引；稽核並提供安全復原或明確限制。
- [x] 在照片牆加入明確的拖曳目標、確認對話框與取消；多張照片必須指定要交換哪張，不能隨機選；不修改 M11 舊制照片歸槽。
- [x] 用合成 SQLite/檔案測試空槽移動、雙向交換、衝突、不同副檔名、取消、SHA-256 改變、掃描/離線防護及故障回滾。
- [x] SQLite 由 v8→v9 增量 migration 與升級前備份，建立 `slot_transfer_log`；歷史紀錄可在重新開啟設備後找到未復原的交換，復原前比對兩張 SHA-256 與原始檔名是否衝突，重複復原拒絕。
- [x] 合成失敗注入與保護驗證：空槽移動、雙照交換、不同副檔名、錯誤設備、SHA-256 變更拒絕、Google Drive 占位標記、掃描中保護、第二步 rename 故障回滾、回復原狀與 migration v8→v9 保留資料。
- [x] 已通過 Ruff、pytest、Vitest、TypeScript／Vite、版本一致性；Windows `packaging/build.ps1` 最終 Exit Code 0，EXE／繁中 setup 及 portable／installed 更新 E2E 成功。
- [ ] 尚待 pywebview 實機拖曳與 Google Drive 多人協作驗證；完成前不推送正式 Release。
- [ ] 實機補驗收：UI 槽位多照片選擇、交換前兩張縮圖預覽、深淺色與 Esc／鍵盤，Windows 真正拖曳、Drive 同步時的跨電腦衝突；合成測試不等於 Google Drive 多人同時安全交易。

### M17 階段 B 補充缺陷：Windows 更新交易狀態 JSON 偶發 WinError 5（先記錄後施工）

2026-11-07 正式 Windows build 第二輪：EXE 與繁中 setup 編譯完成，但 installed update E2E 在 `desktop/update_protocol.py:atomic_write_json` 的 `os.replace(temp, transaction.json)` 遇到 `[WinError 5] 存取被拒`，交易進入 `rolled_back`，整體 build Exit Code 1。這可能是 Windows 檔案讀取器、更新器或安全軟體對 JSON 的短暫檔案鎖，不可未驗證就視為無害。**此施工單先於任何更新器修改寫入，僅修復狀態 JSON 原子替換的短暫競爭；不得降低 READY／HEALTHY 與 rollback 保護。**

- [x] `atomic_write_json` 僅針對 Windows 短暫共享鎖錯誤（WinError 5／32／33，或對應 errno）在短時間內限次／限時重試 `os.replace`；其他錯誤立即拋出，維持先寫暫存、fsync、成功後原子替換、失敗清理 tmp。
- [x] 單元測試：第一次替換遇 WinError 5、之後成功；持續錯誤超時後安全失敗；非鎖定類錯誤不重試、不產生半寫 JSON；重試過程不變更 transaction id／安全檢核。
- [x] 重跑 `packaging/build.ps1`，必須看到真實 packaged `FireLens.exe` 啟動的 portable + Inno Setup installed READY／HEALTHY 與 rollback／故障注入 E2E 全部成功，且整體 Exit Code 0，才能標記完成。
- [x] 初次重跑曾在 installed update 交易發生 WinError 5 並回滾；加入受限 retry 後再次重跑，真實打包 E2E PASS、最終 Exit Code 0；正式 GitHub push／Release 仍未執行。

### M17 後續安全與相容性查核

- [ ] 正式發布前檢查前端 npm audit 回報的 1 項 high severity 開發依賴漏洞及 Node 版本相容性；不得直接使用 npm audit fix --force 破壞 lockfile，需先辨識受影響套件、是否進入發佈 bundle，再規劃修補與回歸測試。

### M17 階段 C 歷史紀錄（公開試算表清單，現由私人 OAuth 取代）

使用者要在「設定」右側加入「查看滅火器更換資料」，來源為 https://drive.google.com/drive/folders/1iEgsrIVmFdwC4sgLjDWOZZSfA9-xNgpU?usp=drive_link，可從公開雲端資料夾挑選試算表、在應用內嵌閱讀，不需 OAuth／登入。官方 Drive 文件確認公開資料夾列檔仍需 **Google Cloud Drive API Key**（非 Google 帳號 OAuth）；尚未提供 Key。採可用的分階段唯讀方案：有金鑰列清單／選取／內嵌，沒金鑰可內嵌公開資料夾檢視及手動輸入試算表網址並顯示設定說明；不可假裝免金鑰也可透過 API 列清單。此施工單必須先寫入 TASKS 再改程式。

- [x] 建立唯讀 Google 公開試算表代理：固定／安全設定指定 folder ID，後端對 Google Drive v3 `files.list` 用 `q="'<id>' in parents and trashed=false"` + API Key、限制 Google 官方 HTTPS 主機、timeout、頁數／筆數上限、過濾 Google Sheet MIME、清理不可信名稱／ID；不存使用者 Google 密碼、不用 OAuth。
- [x] 歷史階段 C 原先在設定頁加入「查看滅火器更換資料」面板（後於階段 C 修正依使用者指定移至設定右側獨立頁籤），預設使用提供的公開資料夾，顯示「重新整理清單」、清單選取、目前試算表標題、嵌入 iframe；提供「外部開啟」與「Google Drive 資料夾」入口，避免禁止 iframe／登入要求時無法查看。
- [x] API Key 由本機環境變數 `FIRELENS_DRIVE_API_KEY`（或安全設定）提供；沒有金鑰時清楚提示「清單需要 API Key」，提供資料夾嵌入及手動貼入 Google Sheets URL 的唯讀後備方案。URL 僅接受 sheets.google.com／docs.google.com/spreadsheets/d/ 合法 ID，防止任意 URL iframe、XSS、外部網域代理。
- [x] API 使用明確狀態（未設金鑰、空清單、權限拒絕、Google API 速率限制、網路逾時）及無快取敏感資訊；非 2xx 不可宣稱查詢成功，介面不得因第三方拒絕 iframe 而當成已驗證。
- [x] 合成 HTTP 回應測試：公開資料夾多頁、只有 Sheets、惡意 ID 與名稱、無 Key、403／404／429／逾時；前端正常清單選擇／網址解析測試、深淺色排版與連結安全。
歷史開發紀錄：- [x] 程式驗證：Ruff PASS、pytest 125 passed、Vitest 36 passed、TypeScript／Vite PASS、v1.8.0 一致性 PASS。
- [x] Windows EXE／繁中 setup 正式建置及更新器 portable／installed E2E（READY／HEALTHY、rollback、故障注入）全部通過，packaging/build.ps1 Exit Code 0。
- 歷史公開資料夾測試驗收：**已取消**，改驗證限制存取 OAuth 私人清單及表格讀取。
- 歷史公開 API Key／iframe 實機待驗：**已取消**，不再是當前驗收條件。

### M17 階段 C 歷史頁籤修正（位置保留，內容改用 OAuth）

使用者最新截圖圈出上方導覽列「設定」右側空白，明確要求不是放在設定頁裡，名稱改為「查看滅火器資料」。本任務在改程式碼前先寫 TASKS。原有 Google Drive 唯讀列檔／手動 Sheets URL／內嵌及外部開啟能力要完整移至獨立頁，不能重做後端、不能留重複入口。
- [x] 導覽列在「設定」右側新增「查看滅火器資料」頁籤，點擊後直接看到原先 Google Drive 公開試算表查看介面；「設定」恢復純系統設定，不放此功能。
- [x] 抽出獨立 React View，完整保留公開資料夾、試算表下拉、手動 URL、唯讀 iframe 與外部開啟、安全 URL 過濾，排版支援較窄視窗及深淺色；不得把 Google Key 或 token 顯示在前端。
- [x] 釐清 Google 登入 OAuth 與 API Key：OAuth Windows 桌面需 Google Cloud OAuth Client ID、同意畫面、Google Drive API，仍非「免設定 API」；若未提供合法 client 設定，先保留現有公開唯讀方案，不虛構登入入口。後續如要 OAuth，另寫獨立施工單，採只讀最小 scope、系統瀏覽器 PKCE／loopback、權杖安全儲存及登出。
- [x] Ruff、pytest（125 passed）、Vitest（36 passed）、TypeScript/Vite、版本一致性、Windows EXE／繁中 setup、更新器 portable／installer E2E 全部通過，packaging/build.ps1 Exit Code 0；文件已同步。
- 歷史 iframe 真實權限驗收：**已取消**，改為階段 D Google OAuth 實機驗收。

### M17 階段 D 新需求：限制存取 Google Drive + Google OAuth 2.0 私人試算表（2026-11-07）

使用者已親自在 Google Drive 將資料夾 `1iEgsrIVmFdwC4sgLjDWOZZSfA9-xNgpU` 改為「限制存取」，不希望未受邀者看到消防更換紀錄。**先在 TASKS 記錄此次需求與風險，才開始開發，原有公開 API Key 清單和匿名 iframe 機制不再適合作為正式私人存取流程。** 已存在的「查看滅火器資料」獨立頂部分頁保留；此段記錄原始需求；程式實作與未驗收項目請見下方本輪施工單。

- [ ] Google Cloud 配置：建立/選擇專案、啟用 Drive API 與 Sheets API、完成 OAuth 同意畫面（internal/external 依使用者 Google 帳號與組織限制判斷），建立 **Desktop app OAuth Client ID**；Client ID 可列於非敏感設定，但不可將 refresh/access token 寫入 Git 或一般明文設定。使用者需在 Google 同意頁自行授權，不得要求提供帳密。
- [x] Windows OAuth 登入：系統預設瀏覽器開啟授權碼流程 + PKCE（S256）+ 本機 loopback callback／state／nonce 或符合官方桌面應用規範的回呼；短時憑證、取消授權、拒絕、逾時、離線和多視窗併發均安全處理，不用 pywebview iframe 蒐集 Google 密碼。
- [x] 權限最小化：預設唯讀，優先評估 `drive.file` 搭配 Google Picker 的檔案選取能力；若需求必須直接列出受邀私人資料夾所有試算表，依 Google 官方 scope 定義評估 `drive.metadata.readonly`／`drive.readonly` 以及 Sheets 的唯讀 scope、Google 敏感／受限制權限驗證成本；沒有適用 scope 不得擅自擴大授權。
- [x] 登入後僅對已授權帳號及目標資料夾執行分頁列檔；遭 401／403／404、權限被撤銷、token 過期時即時拒絕並提供重新登入／刷新；不得退回公開清單或將未授權的私人 Sheet 網址曝露給其他人。
- [x] 不依賴私人 Sheets iframe 登入狀態（WebView2 第三方 Cookie／X-Frame-Options 可能限制），應以 Google Sheets API 唯讀取值並由 React 繪製表格；欄列上限、分頁、公式/超連結防注入、載入與錯誤提示、完整資料不意外寫入日誌。
- [x] 安全儲存憑證：優先 Windows Credential Manager／DPAPI 以使用者身分加密，明確登出／撤銷與清除快取；每人獨立帳號與憑證，不與其他 Windows 使用者或 Google Drive 同步資料夾共享。
- [ ] 驗收：僅受邀 Google 帳號可登入讀取；非授權帳號、已移除權限者無法列檔/讀值；token 續期、取消、登出、多帳號、無網路；以合成 HTTP + Windows 實機流程測試；完成前不得宣稱已安全連線至私人資料夾。
- [x] 修改時沿用 `AGENTS.md` 先 TASKS 後施工規範，完成後執行 Ruff、pytest、Vitest、Vite、版本一致性、Windows EXE／setup 和更新器 E2E；同步文件，經使用者驗收才正式推送 Release。
- [x] **施工前必要依賴（Desktop Client ID 已取得）**：取得使用者自行建立的 Google Cloud OAuth Desktop Client ID／應用程式同意畫面狀態；在缺少配置前可用合成憑證開發與測試流程，但**不得**聲稱真實 Google OAuth 已完成，也不要求使用者傳送 Client Secret 或任何 Token 至聊天室。

### M17 階段 D 本輪施工單（已取得 Desktop OAuth Client ID，2026-11-07）
本節的 [x] 表示**程式與合成自動驗證通過**，不代表真實帳號已完成 OAuth 授權。Google Cloud Drive/Sheets API 啟用、同意畫面權限與真實登入仍待使用者端確認。


- [x] 使用固定 Desktop Client ID（非秘密、禁止寫入 Token），於 Windows 系統瀏覽器執行 OAuth 授權碼 + PKCE S256 + 隨機 state + 本機 IPv4 loopback 回呼，取消、逾時與重複登入安全處理；不能要求 Client Secret、不可透過內嵌 WebView 收集 Google 密碼。
- [x] 限制存取資料夾的授權狀態、Sheets 清單／工作表／有限範圍值的只讀 API；Google Drive Metadata readonly 和 Google Sheets readonly scope 需在同意畫面宣告，並註明 Drive metadata 是 restricted scope。對 401/403/404、撤銷與離線顯示安全錯誤，不得匿名退回舊公開端點。
- [x] Windows DPAPI 使用者綁定加密 token 儲存與安全清除；登出時撤銷權杖（網路失敗時仍清除本機），不得存於 Git、資料夾同步區或回傳 UI。
- [x] 上方獨立「查看滅火器資料」分頁改為登入／登出、試算表下拉、工作表選取、React 唯讀表格；移除公開資料夾 iframe/匿名模式與 API Key 提示，且 API 不接受任意私人 Sheet ID；所有表格內容當文字顯示，限制欄列與回應大小。
- [x] 合成 OAuth/Token/Drive/Sheets HTTP 錯誤、狀態比對、PKCE、資料範圍、未授權阻擋、token 存取與 logout 測試；再跑 Ruff、pytest、Vitest、TS/Vite、版本一致性及 Windows 打包／更新器 E2E。
歷史開發紀錄：- [x] 本輪合成驗證：Windows DPAPI 加密檔不含明文 Token、callback state 及 PKCE 隨機挑戰、OAuth scope 不足拒絕、過期 Token 更新、未登入/跨來源/缺桌面 cookie 被拒、受限資料夾列檔與 Sheets API 值讀取；Python 134 passed、Vitest 36 passed、Ruff 和 TypeScript/Vite PASS、v1.8.0 版本一致性 PASS。
- [x] Windows EXE／繁中 setup／更新器 portable 和 installed E2E／READY、HEALTHY、rollback、故障注入通過，packaging/build.ps1 Exit Code 0；Graphify 重建 796 nodes／1886 edges／55 communities，產物只保留本機不納入 Git。
- [ ] 真實 Google OAuth 登入與限制資料夾實機權限驗證由使用者在自己的 Windows 登入授權；未親自驗證前不標為已驗證、不推 GitHub Release。若 Google OAuth 測試應用 7 天重新授權或權限驗證限制，必須清楚顯示。

### M17 階段 D 補充安全閘門（私人試算表本機讀取保護）

- [x] 在 Windows 正式桌面安全模式下，所有 `/api/private-drive/` GET／POST 都需要既有 HttpOnly 桌面 session cookie，且不接受非 loopback Origin；不能因 GET 原本不屬於修改操作就允許未持有工作階段的程序讀取私人 Sheet。
- [x] 合成安全測試驗證無 cookie 私人 API 拒絕、已有桌面 session 可查看登入狀態、未登入時仍不能讀取 Sheets；不影響一般 `/api/health`／初始化頁面建立 session 的流程。

### M17-D OAuth 實機失敗修正（2026-11-07）

使用者真實登入回報：Google 系統瀏覽器完成回呼，但 FireLens 顯示「Google 拒絕此次要求，請重新登入或檢查同意範圍」，回呼頁只顯示授權未完成。原始後端 `_request_json` 把 Google HTTP 400 全映射為同一錯誤，不保留 Google 官方 `error` 代碼；因此不能推定是同意範圍或資料夾權限。已確認 Google Desktop OAuth 官方 code+PKCE 的 `client_secret` 為選填，不應要求使用者提供密碼。

- [x] 在不回傳 OAuth code、token、Cookie、`error_description` 或 Google 原始回應的前提下，安全讀取 Google token 端點回應中的白名單錯誤代碼（`invalid_grant`、`invalid_client`、`invalid_request`、`unauthorized_client`、`invalid_scope` 等），UI 顯示「失敗階段（授權碼交換／同意授權／續期）＋可執行原因＋安全錯誤代碼」。無法辨識時維持通用繁中提示。
- [x] 分開處理系統瀏覽器回呼中的 `error=access_denied`、`state` 驗證、Token API 錯誤；不得用寬鬆提示宣稱認證成功，亦不得繞過 PKCE、取消或超時檢核。必要時在回呼頁顯示安全、不含憑證的失敗原因。
- [x] 以合成 Google HTTP 400/401/403、惡意或錯誤 JSON、HTTPError 安全處理、沒有 error code 的回應測試；不得記錄敏感登入網址或任何原始 response body。
- [x] 重新執行 Ruff／pytest／Vitest／TS-Vite／版本一致性與 Windows 打包／更新器 E2E；同步 AGENTS/README/TASKS，本機 Git checkpoint，不推送 GitHub Release。真實 Google 登入與私人資料夾權限驗證需使用者以自己帳號重新授權，未驗證仍保留未完成。
- [x] 已觀察：OAuth 專項 17 passed，完整 Python 142 passed、Vitest 36 passed、Ruff / TypeScript-Vite / 版本一致性 PASS；Windows `packaging/build.ps1` Exit Code 0，EXE／繁中 setup／更新器 E2E（portable／installed／READY／HEALTHY／rollback／故障注入）通過；Graphify 更新 801 nodes／1892 edges／56 communities。
- [ ] 等待使用者安裝新建置並再次完成真實 Google OAuth，回報 **安全錯誤代碼**（例如 invalid_grant／invalid_client／invalid_request），才能鎖定 Google HTTP 400 的確切根因；不能把合成測試誤認成真實登入通過。


### M17-D OAuth invalid_request 再排查（2026-11-07，先 TASKS 後實作）

使用者實機再次回報 `OAuth 授權碼交換／續期失敗（invalid_request）`。FireLens 現有授權碼交換包含 `client_id`、`code`、`redirect_uri`、`grant_type`、`code_verifier`，未傳 `client_secret`。Google 官方 Desktop OAuth 文件稱 `client_secret` 選填；2026 年 Google 開發者論壇有同型 Desktop + PKCE + loopback 交換得到 `invalid_request`、詳細原因為 `client_secret is missing` 的案例。**此為高度相似線索，非本次 Google 回應已證明的根因**。桌面 Secret 不能視為機密防線，亦不可要求使用者貼到聊天室或 Git。

- [x] 增加安全的 *本機可選* Desktop OAuth Client Secret 配置（只從 Windows 本機環境變數或不加入 Git 的使用者設定讀取），存在時於授權碼交換／Refresh Token 送 `client_secret`，未設定仍保留官方 PKCE-only 流程；嚴禁將值輸出 UI／日誌／git 或 Google callback URL。
- [x] 只針對 Google 官方回應的 `invalid_request` 及其 `error_description` 安全白名單辨識 `client_secret is missing` 等具體缺參數原因；只顯示固定翻譯與安全建議，不顯示 Google 原始描述、token、授權碼。
- [x] 合成測試：不提供 Secret 仍走 PKCE、不洩漏；有 Secret 時 Token 交換與刷新含設定值；無 Secret 的 Google 欠缺參數提示會引導本機設定；無關或惡意描述不能直接顯示。
- [x] Ruff、pytest（146 passed）、Vitest（36 passed）、TypeScript/Vite、版本一致性 PASS；Windows EXE／繁中 setup 與更新器 portable／installed READY／HEALTHY／rollback／故障注入 E2E 皆通過，packaging/build.ps1 Exit Code 0。文件已同步，待本機 Git commit；不 push/release。
- [ ] 使用者在 Windows 本機選擇是否設定 FIRELENS_GOOGLE_CLIENT_SECRET 並重新嘗試 Google OAuth。只有實際授權與讀取私人資料夾成功後，才可驗收此功能；未重試前仍保留原始根因的不確定性。

### M17-D 新增設定頁 OAuth Client Secret（2026-11-07，先 TASKS 再施工）

使用者確認：在 FireLens「設定 → Google OAuth 設定」填寫、修改、清除 Client Secret，免 PowerShell 環境變數步驟。Client ID 使用既有公開識別碼；Secret 只在本人 Windows 輸入，不傳至聊天室、Git 或同步區。

- [x] 建立 Windows 每位使用者專屬 DPAPI 加密 Client Secret 儲存，位於 LocalAppData 獨立檔案，原子寫入，不與 Token 共存；解密/寫入失敗不可退回明文。
- [x] 新增受 desktop session 與 Origin 防護的 GET 狀態、POST 儲存、DELETE 清除 API。GET 僅回傳 configured/Client ID，不得回傳原 Secret；驗證空值、長度、控制字元與未授權。
- [x] 在「設定」頁新增 Google OAuth 設定卡片，Client ID 唯讀、Client Secret 密碼型輸入、儲存/清除按鈕與狀態；儲存後清空輸入，永不顯示已儲存值。
- [x] OAuth 授權碼交換/Refresh Token 優先從加密儲存讀取，然後是舊環境變數，未設定保留 PKCE-only，不放寬安全檢查。
- [x] 合成測試及 Windows DPAPI 測試：儲存/覆寫/清除/重開、檔案不含明文、API 無明文、未授權拒絕、非法值拒絕、OAuth 交換與續期取值正確。
- [x] Ruff、pytest、Vitest、TypeScript-Vite、版本檢查與 Windows 安裝包/更新器 E2E，AGENTS/README/TASKS 同步，將建立本機 Git 還原點，不推送 Release；真正 Google OAuth 仍需使用者驗收。

已確認：Python pytest 151 passed、前端 Vitest 36 passed、Ruff／TypeScript-Vite／版本一致性 PASS；Windows 安裝檔和更新器 portable／installed READY／HEALTHY／rollback／故障注入 E2E 全部通過，packaging/build.ps1 Exit Code 0。真正 Google OAuth 登入與私人資料夾授權讀取仍待使用者在新版 FireLens 驗收。

### M17-E Google 試算表「唯讀／編輯」切換（2026-11-07，先 TASKS 再開發）

使用者明確要求能編輯 Google 試算表且可切換唯讀／編輯。必須保留限制存取 Google Drive 身分授權，預設唯讀、編輯需使用者明確點選；Google Drive「檢視者」不能因前端切換而取得寫入權限；編輯權限由 Google OAuth scope 與檔案 ACL 共同決定。這個施工單先寫入 TASKS.md，讀回確認後才能改功能程式。

- [x] OAuth 編輯模式重新授權：原有 drive.metadata.readonly + spreadsheets.readonly 保持預設唯讀；使用者選擇「編輯」時才以系統瀏覽器 PKCE/state 重新授權 `spreadsheets` 寫入 scope。不可宣稱已具權限直到 Google 回傳確認；讀取模式仍可用舊憑證，取消/失敗不能覆蓋已成功登入的唯讀 Token。顯示目前登入 Token 是否具編輯 scope，且不存取其他未授權資料夾。
- [x] 後端只允許被指定受限資料夾列出的 Sheet + 現有 Tab，寫入 API 只接受單一範圍中有限的儲存格，使用者明確確認後才呼叫 Sheets values.update；必須檢查授權 scope 且 Google ACL 拒絕時回報 403。禁止任意 spreadsheet ID/網址、任意 A1 範圍及過量寫入。
- [x] 保護既有雲端資料：前端編輯內容只在本機草稿，不自動同步；按「儲存變更」先顯示儲存格原值/新值及二次確認。後端在寫入前重新讀取同一儲存格，與前端最初讀取值核對；不一致 409 拒絕並要求重新整理，避免覆蓋他人更新。Google Sheets API 不提供 values.update 的原子 compare-and-swap，因此跨使用者極短時間競爭仍不可保證，必須在 UI/文件明確揭露。
- [x] React 「唯讀／編輯」切換：未取得寫入 scope 時引導重新授權（只在使用者明確點選時），可編輯限目前頁面 100 列×30 欄；未儲存修改、模式切換/翻頁/切 Sheet/登出前要確認避免草稿遺失。保留純文字顯示、禁止公式注入（預設以 RAW 寫入），Google 權限失敗時不可標示儲存成功。
- [x] 合成 Google OAuth+Sheets API 測試：readonly token 禁止 PUT、編輯 scope/檔案檢視者拒絕、錯誤 sheet/tab ID、衝突 409、正常保存與 Google 4xx/5xx、超過範圍拒絕、API 不能回傳 Token/Secret，並驗證現有桌面 session/Origin 防護；前端測試及全量 Ruff/pytest/Vitest/Vite。
- [x] 版本判定：功能納入尚未正式 Release 的 M17 v1.8.0 開發版本，同版多階段驗收依 AGENTS.md 第 3 條允許，正式 Release 前保持版本來源同步；Windows EXE/繁中 setup + portable/installer 更新 E2E／READY／HEALTHY／rollback／故障注入皆通過，build.ps1 Exit Code 0；已同步 AGENTS/README/TASKS，將建立本機 Git commit，不推送 GitHub/Release。
歷史開發紀錄：- [x] 本輪合成測試：Python pytest 163 passed、Vitest 36 passed、Ruff PASS、TypeScript/Vite PASS、版本一致性 v1.8.0 PASS；Google editor scope、Google ACL 403、衝突 409、單格 RAW 寫入與授權失敗不覆寫舊唯讀 Token 均已測試。
- [ ] **真實 Google 寫入驗收**：在使用者自己的 Windows 上，先準備一份不含現場資料的測試試算表，確認該 Google 帳號是「編輯者」，於 FireLens 主動切至編輯、完成完整 OAuth 授權、修改測試儲存格再讀回；僅實機驗證後才可標記完成。

### M17-E 實機回報：編輯框不可見與原生 Google Sheets 操作（2026-11-07）

使用者截圖顯示已進 FireLens 編輯模式，儲存格被虛線按鈕包住，但點擊後的草稿輸入區位於 70vh 高度的內部表格捲動容器**底部**，未隨儲存格點擊出現在可視範圍，造成使用者覺得無法編輯。使用者也要求了解為何不「嵌入」原生 Google Sheets：Google 官方「發布到網路後嵌入」僅為檢視，無法編輯且對限制存取資料有曝露風險；Google OAuth 登入限制內嵌 WebView2。**不發布到網路，不繞過 X-Frame-Options，不嘗試注入 Google OAuth Token 到 iframe。**

- [x] 修正編輯 UX：點選儲存格立即在 viewport 中央開啟可輸入的對話框（原值、文字輸入、取消、儲存），獨立於 70vh 內部表格捲動；保留二次確認原值/新值、RAW 文字寫入、409 原值衝突、403 Google ACL 及離開未儲存草稿提示，完整鍵盤／焦點操作。
- [x] 選取已驗證的資料夾內試算表後顯示「使用 Google 試算表開啟」：於使用者明確點擊時開啟系統預設瀏覽器中的 Google 官方 docs.google.com/spreadsheets/d/<已選 Sheet ID>/edit#gid=<已選 Tab ID>。只使用後端已列出的 ID 且以嚴格格式檢查，不接受任意 URL 或自訂域名；瀏覽器由 Google Cookie 決定是否登入及是否具有編輯 ACL，FireLens 不傳任何 OAuth Token／Client Secret。
- [x] 更新 README、AGENTS/TASKS（公開 iframe 與原生 Sheets 差異和資料隱私）；合成測試、Ruff、pytest、Vitest、TS/Vite、版本一致性、Windows EXE／繁中 installer／更新器 E2E；本機 Git checkpoint，不推送 Release。實際瀏覽器登入與真實 Google Sheets 寫入僅由使用者實機測試。
歷史開發紀錄：- [x] 本輪合成驗證：Python pytest 165 passed、前端 Vitest 36 passed、Ruff/TS/Vite 與版本一致性 v1.8.0 PASS。Windows packaging/build.ps1 Exit Code 0，繁中 dist/installer/FireLens-1.8.0-setup.exe 及 portable/installer 更新器 READY/HEALTHY、rollback 與故障注入 E2E 均通過；原生 Sheets 開啟的資料夾成員、gid 和本機 session/Origin 拒絕由合成測試驗證。
- [ ] 待使用者實機驗收：新版 FireLens 點儲存格確認中央編輯視窗顯示，二次確認並對測試 Sheet 成功儲存；點使用 Google 試算表開啟，確認 Google 登入與完整編輯功能。未實測前不宣稱真實 Google 編輯成功。


### M17-E Google 試算表清單自動載入（2026-11-07）

使用者明確反映：進入「查看滅火器資料」時每次還要手動按「重新整理試算表清單」很麻煩。預期已登入時直接看到「選擇試算表（N 份）」；剛從 Google 瀏覽器完成登入後也能自動載入。

- [x] React 頁籤初始化取得 Google 授權狀態，若已登入即自動向既有受限制資料夾清單 API 載入 Sheets；未登入不請求清單，成功登入時只載入一次，OAuth 編輯 scope 更新/狀態輪詢不得重複請求。
- [x] 自動載入不得重設已選取的試算表、工作表、正在檢視的資料或未儲存編輯草稿；手動「重新整理」仍保留明確重選流程，防止過期請求在登出後覆寫清單。載入中顯示清楚提示，出錯可由手動按鈕重試。
- [x] 前端型別/邏輯測試、Python pytest、Ruff、Vitest、TypeScript/Vite、版本一致性與 Windows EXE/繁中 installer/更新器 E2E；同步 README/TASKS/AGENTS（若長期規則需修訂），本機 Git commit，不推送 GitHub。真實 Google 連線仍需使用者實機驗證。
歷史開發紀錄：- [x] 已觀察：Vitest 39 passed（含本輪自動載入成功／失敗／登出後過期回應 3 項）、Python pytest 165 passed、Ruff PASS、TS/Vite build PASS、版本一致性 v1.8.0 PASS；Windows packaging/build.ps1 Exit Code 0、EXE／繁中 installer／更新器 portable/installed READY／HEALTHY、rollback、故障注入 E2E 通過。
- [ ] 真實 Google 雲端實機驗收：安裝本輪新版後，在已登入狀態進入「查看滅火器資料」，確認無須按「重新整理」便顯示目前有權限的試算表數量與清單；登出/重新登入後也自動載入，且編輯草稿不因清單更新遺失。未測前不宣稱真實 Google 清單驗收完成。


### M17-F Google Sheets 整欄複製／多格選取（2026-11-08，合成測試與 Windows 打包已完成，待實機操作驗收）

**使用者實際需求：** 在「查看滅火器資料」中，像 Excel／Google Sheets 一樣，一次選取一整欄（例如 B 欄設備編號：致-02-08、致-02-09、致-02-12 等）並按 Ctrl+C 複製，避免逐格點選。**2026-11-08 使用者已明確指示「繼續開發」；本輪依優先順序只實作 M17-F 整欄複製／多格選取，不進行其餘四項、不修改真實 Google Sheets。**

- [x] 在目前表格加入 Excel 式 A～AD 欄標頭；點欄標頭高亮選取整欄，顯示已選範圍／筆數，支援按鈕「複製所選欄位」與鍵盤 Ctrl+C；唯讀／編輯模式均可用，複製不需 Sheets 寫入權限。
- [x] 支援單格／多格連續範圍選取（包含 Shift 擴展選取）；以 TSV（欄與欄 Tab 分隔、列與列換行）複製，可直接貼入 Excel、Google Sheets 或 FireLens 清冊輸入框。
- [x] **整欄複製要涵蓋該工作表實際資料範圍，而不是只複製目前畫面 100 列**；讀取前可見範圍和預估筆數，採有限批次取得全部資料，避免 UI 卡死或 Google API 超額。不在查詢中修改雲端資料。
- [x] 明確區分「含第一列標題／不含標題」；保留範圍內空白列的位置，不自動去重、排序或改寫設備編號（例如前置零、連字號、中文異體字）。
- [x] 成功複製後顯示「已複製 N 列／M 欄」與 A1 範圍；Clipboard 拒絕、網路錯誤、中途取消或只取得部分資料時，必須提示失敗，不能顯示成功；不把設備編號寫入一般日誌或 Git。
- [ ] 進一步的**整欄貼上／批次寫入**列為後續獨立討論項目，未經使用者確認，不得與本輪複製功能一同實作。
歷史開發紀錄：- [x] 合成與回歸驗證：跨 100/200 列分批讀取、空白列、中英與前置零設備編號、整欄選取、Shift 多格與逆序範圍、A～AD 欄名、TSV 引號／換行／Tab、未授權 session/Google 帳號拒絕、單次超限、Google 回傳不完整、取消後不寫入剪貼簿；Python pytest **177 passed**，前端 Vitest **48 passed**，Ruff check/format、TS/Vite 及版本一致性 v1.8.0 PASS。
歷史開發紀錄：- [x] Windows 安裝版驗證：packaging/build.ps1 Exit Code 0，FireLens.exe、繁中 FireLens-1.8.0-setup.exe、portable/installed 自動更新 READY／HEALTHY／rollback／故障注入 E2E 全數通過。保留 v1.8.0 未正式發布開發版，無需再次升版。
- [ ] **實機操作待驗收**：由使用者在 Windows WebView2 + 真實 Google 帳號選 B 欄（超過 100 列）、按 Ctrl+C 後貼到 Excel／清冊核對，驗證完整筆數、空白列、編輯模式 Ctrl/Shift 選取，以及 Clipboard API 失敗時的重試。未觀察前不標為實機通過。

### M17 開發優先順序（使用者確認，2026-11-07）

此順序為使用者確認的施工安排；**2026-11-08 已明確核准先執行第 1 項 M17-F**。後續第 2～5 項仍需個別確認／另輪施工，不得自行一次全部執行；不得改動既有已完成項目的勾選狀態。

1. **Google Sheets 整欄複製／多格選取**：先解決清冊設備編號整欄複製、跨頁與 Ctrl+C 效率問題（見本節 M17-F）。
2. **異常統計 CSV／Excel 匯出**：以畫面篩選結果產出可交付的異常設備清單（既有 M17 待辦）。
3. **清冊核對三種設備獨立搜尋**：滅火器／放置盒／燈具各自指定搜尋資料夾與核對範圍（既有 M17 待辦）。
4. **設備編號異常備註匹配**：處理尾端括號備註等差異，避免清冊漏配／誤配（既有 M17 待辦）。
5. **Google Drive 多人同步與備份**：最後進行，先確認衝突處理與誤刪復原，不影響現場資料（既有 M17 待辦）。

### M17 待修復 Bug：新增資料夾後資料樹不應全部展開（2026-11-08）

使用者提供左側「資料樹」截圖並回報：使用「新增資料夾」後，程式會自動展開所有年份、月份、棟別和設備編號，造成原先已收合的資料夾全部被打開，使用效率降低。**期望行為：保留原本各節點的展開／收合狀態，只將新建立資料夾所屬的必要祖先節點展開，並定位與選取新節點；其餘無關分支一律維持原狀。** 2026-11-08 使用者已再指示「繼續開發」，本輪明確修正此項資料樹 Bug；不得改動照片或其他功能。

- [x] 找出新增年份、月份／批次、棟別、設備編號成功後資料樹重新載入時，全樹展開的原因（例如 expanded keys 被重設、根目錄或樹狀索引被視為新節點、預設展開全部）。不要單純取消所有自動展開，避免新節點被藏起來。
- [x] 建立資料夾前保留當前資料樹展開集合；成功後只補入新節點路徑上必要的祖先（類別 → 年份 → 月份／批次 → 棟別），並選取、捲動到新建節點。原已展開的其他分支照常展開、原已收合的其他分支保持收合，不能自動全部展開。
- [x] 同時適用滅火器／放置盒／燈具及使用資料夾樹「＋」、右鍵「新增…」、快速新增等既有入口；取消、同名衝突、非法名稱、權限或離線失敗時，不改變原本展開狀態。
- [x] 一般重新整理、重新掃描與新增成功後的資料樹更新需避免不必要的全樹展開；多個根目錄切換時不得把其他根目錄的展開狀態錯套進來。只記錄 UI 狀態，不改動磁碟上既有照片／資料夾。
歷史開發紀錄：- [x] 合成測試與回歸：6 項新增 Vitest 測試涵蓋目標父路徑、保留其他展開／收合、年份／月份／棟別／設備四層、三類分支、同名不同年份、不同根目錄狀態隔離及失敗／取消不變。Vitest 54 passed、Python pytest 179 passed、Ruff check PASS、TS/Vite PASS、版本一致性 v1.8.0 PASS。Windows packaging/build.ps1 Exit Code 0，繁中 installer、portable/installed 更新器、READY／HEALTHY、rollback 與故障注入 E2E 全通過。
- [ ] **Windows 實機 UI 待驗收**：以合成目錄或非正式資料，在 pywebview 測試樹上「＋」／右鍵／快速新增、滑鼠展開／收合、建立後自動定位新節點、切換根目錄與搜尋後恢復展開狀態、取消／失敗不變；不得以純 Vitest/打包成功替代實機點擊驗收。

### M18 已開發、待實機驗收：照片異常卡片總覽＋模糊照片自動掃描（2026-11-10）

使用者提供其他程式的卡片式照片巡覽截圖：資料來源／材料／棟別／縮圖大小／重新整理／整理前自動掃描，以及一台設備一張卡片、前中後照片並排。希望 FireLens 快速列出照片有問題的設備，另能自動掃描模糊不清的照片。使用者已定案：在**主導覽列「整理工具」右側新增同層級獨立標籤「照片品質檢查」**，不可作為整理工具內的子分頁；獨立頁面可重用既有照片索引、縮圖、照片牆和整理工具的分析函式，但不改 OrganizerView 原有職責。使用者已於 2026-11-11 授權開始 M18 實作；先實作獨立主標籤、持久品質紀錄、手動增量／完整掃描、照片異常清單／人工覆核與匯出，不推送 GitHub 或建立 Release。

重要分界：現有設備異常 issue_label、item_issue（瓶身超過十年／壓力錶壞等）仍維持每台只能標一個；照片品質異常（模糊、缺照、拍攝錯誤等）是獨立類別，一台可有多張照片、各自不同原因，不可占用設備異常欄位或覆蓋現有資料。

#### M18-A 卡片式照片問題總覽

- [x] 在主導覽「整理工具」右側新增獨立「照片品質檢查」標籤與頁面（切換時保留其他主功能原有狀態）：一台設備一張卡，顯示完整設備編號、棟別樓層、類別、年月批次、照片更新日期，以及原槽位的照片縮圖。滅火器為編號／藥劑／完成，放置盒／燈具為前／中／後；缺照明確顯示空槽位，多張照片同槽位仍可查看。
- [x] 篩選照片來源根目錄、設備類別、棟別、月份、設備編號關鍵字、問題類型與人工覆核狀態，調整縮圖大小、選擇僅異常或全部設備、排序，並統計設備數／異常照片數／需人工確認數，避免多照片重算設備數。
- [x] 卡片提供查看／放大原圖、跳回照片牆、標記已人工確認、排除誤判、列入待補拍；所有照片操作尊重既有縮圖快取與讀取安全限制。錯誤設備或拍錯內容初版由人工標記，不能把影像模糊分數當成內容辨識。
- [ ] 與現有整理工具之髒檔名、缺槽位、錯誤辨識和無法讀取資料整合，但不混入既有設備異常單選；結果保存應採根目錄＋相對路徑＋檔案版本指紋（大小、mtime、必要時 hash），索引 photo.id 重建後不應錯配。照片換新後舊人工判斷需標示待重新確認。
- [x] 使用分頁或虛擬捲動載入大量卡片，提供載入／掃描進度、取消與錯誤重試；不得因巡覽強迫 Google Drive 串流占位檔下載。

#### M18-B 模糊／不清楚照片品質掃描

- [x] **使用者已確認預設手動觸發，不自動掃描**。照片品質檢查頁提供來源根目錄、設備類別、年月範圍，以及掃描模式單選／下拉：「增量掃描（預設，只分析新增或內容已變動的照片）」與「完整重新掃描（強制重新分析範圍內全部可讀照片，不沿用舊品質分數）」；兩種模式都須由使用者按「開始掃描」才執行，打開頁面、切換標籤、按一般重新整理均不可自動掃描。
- [x] 先評估 Pillow 與新增 OpenCV 的 Windows 安裝包成本，使用原圖適當等比縮放工作副本（不可用已模糊的 UI 縮圖直接評分），以 Laplacian variance、邊緣密度、紋理、解析度及曝光統計產生候選分數，必要時方向性邊緣提示晃動；依分類與槽位調校，不可單靠一組全域閾值武斷判定。
- [x] 顯示高度疑似模糊／可能模糊／正常／無法判定四級及理由，額外指出過暗、過曝、解析度不足、無法解碼等。低紋理白牆、燈具遠拍、瓶身標籤和近距離照片需降低誤判；拍錯設備／設備內容不符初版人工判定，不聲稱 AI 已認識設備。
- [x] 背景低優先掃描、批次與增量快取，顯示已掃描、跳過、疑似異常、剩餘工作及取消／續掃；增量掃描依根目錄、相對路徑、檔案大小、mtime 與演算法版本比對，未變更者直接使用既有結果；完整掃描即使快取有效也重新計算，但不刪除人工確認、也不改原圖。檔案損壞／根目錄離線／Drive 占位未下載／權限不足應標記略過，不得清空舊結果或強制雲端下載。支援 EXIF 方向、JPG／PNG／目前可解碼格式且掃描一律唯讀不重存照片。
- [x] 可設定偵測門檻、檢視單張分數與判斷理由；人工標記「正常／誤判／待補拍」獨立保存。重新掃描、照片更換、演算法版本升級後舊分數需失效或重新評估，絕不自動刪照片或更改設備異常。
- [x] 匯出目前篩選的異常照片 CSV／Excel：設備編號、根目錄、分類、年月、棟別、槽位、檔名、品質問題、分數、人工覆核與安全相對路徑。不包含照片位元組、OAuth 或私人 Drive 連線資訊。

- [x] 驗證模式切換 UX：首次開啟固定「增量掃描」且沒有背景工作；只有點「開始掃描」才掃，切到「完整重新掃描」有明確提示掃描量較大並重新計算全部目標照片；切回增量模式恢復正常版本指紋比較。完整掃描不得因為品質分快取已存在而跳過計算。
- [x] 增量掃描驗收：第一次掃 100 張 → 第二次全部未變更時 0 張重新分析、100 張沿用結果；新增 2 張且修改 1 張時只分析 3 張；完整掃描同範圍則重新分析全部 102 張（修改 1 張不會增加照片總數）。失效的舊演算法結果視為需要重算，以上筆數以合成影像為測試資料。
- [x] 導覽驗收：主導覽「整理工具」與「照片品質檢查」為左右相鄰、同層級的兩個標籤，非 OrganizerView 內部頁籤；不同視窗寬度與深色模式可正常顯示且支援鍵盤操作。

#### M18-C 測試、驗收及待確認

- [ ] 用合成／授權副本建立清楚、輕微／嚴重失焦、晃動、白牆低紋理、燈具遠拍、瓶身文字、過暗／過曝、尺寸不足、損壞檔案的測試集；量測誤報、漏報，針對槽位調參，不能憑空承諾辨識準確率。
- [ ] 測試重複掃描、同圖不同檔、照片改名／替換、索引重建、同槽多圖、離線、Google Drive 串流占位、取消、大量設備與快取失效；開發測試不得動現場照片、清冊或舊 SQLite 受保護資料。
- [x] 後端使用隔離 SQLite、暫存合成圖測試分數及覆核持久化；前端 Vitest 驗證篩選、卡片槽位、虛擬清單／分頁、原圖查看、人工標記與匯出一致性。
- [x] 已先讀 AGENTS／TASKS，並採 SQLite additive schema 10（保留原資料且遷移前備份）；Ruff check／format PASS、pytest **204 passed**、Vitest **64 passed**、TypeScript/Vite PASS、v1.9.0 版本一致性 PASS；Windows packaging/build.ps1 **Exit Code 0**，生成繁中 FireLens-1.9.0-setup.exe 與 FireLens.exe，portable／安裝版更新器 READY／HEALTHY、rollback／故障注入 E2E 通過。AGENTS／README／TASKS 已同步，實際 Windows UI／真實照片門檻待驗收；本輪不推 GitHub／Release。
- [x] 已確認：主導覽「整理工具」右側獨立標籤；手動掃描為唯一預設；增量掃描為預設模式、完整掃描可由使用者切換並手動啟動。其餘「人工拍錯設備／內容錯誤」與偵測門檻仍待實作時校準；不因此啟用自動掃描。

M18 合成及 Windows 打包開發紀錄：主導覽新增獨立標籤；API /api/quality/ 與 DB schema 10 的兩個新增資料表；影像分析使用現有 Pillow（暫不新增 OpenCV / GPU 模型），Laplacian 分數 + 亮暗、紋理、尺寸做候選篩選；可手動增量或完整重掃（先讀取現有安全索引）、背景進度與取消、按根目錄儲存靈敏度、按照片版本保存人工覆核、分頁篩選排序、CSV／Excel 匯出。新增 100 張→新增 2 張／修改 1 張僅重新分析 3 張，完整重掃 102 張；合成 HTTP／SQLite、低紋理、模糊、曝光、解碼及舊制放置盒測試通過。實機 Windows WebView2 與真實照片閾值校準仍未完成，不得宣稱品質判讀準確率。

- [ ] **M18 異常清單缺失進階整合**：目前可顯示圖片清晰度、曝光／解析度、無法解碼、缺照片、未辨識檔名；整理工具其他異常命名候選與同槽多圖問題仍需整合及測試。部分照片若未產生縮圖，僅以原圖預覽核對。
- [ ] **M18 待實機驗收**：Windows 桌面在 100/125/150% 縮放測試新導覽、照片清單大量捲動、原圖預覽、Ctrl/鍵盤、分類／年月／人工覆核篩選、手動增量與完整掃描、匯出開檔；真正 Google Drive 佔位檔及斷線需另外驗證。
- [ ] **M18 門檻與拍攝內容辨識後續**：以使用者授權的消防設備真實照片副本校正各槽位失焦與晃動準確率，統計誤報／漏報；相似設備、拍錯設備不應僅靠模糊分數自動判錯。
- [ ] **M18 整理工具候選深化**：目前已接共享照片索引的缺槽位、無法辨識檔名與解碼異常；如需將 Organizer 的其他錯名候選、特殊資料夾情境完整映射，另行確認後補上，不與設備異常單選混用。

### M18-D 異常清單補齊（2026-11-11，先 TASKS 後程式）

- [x] 照片品質卡片重用 Organizer 的檔名標準化候選辨識（僅計算、不做 rename/sha256 全盤掃描），對可修正錯名顯示建議檔名與原因；未對應照片維持人工確認。合成測試驗證 `編輯.jpg` 建議改為 `編號.jpg`，未直接改原圖。
- [x] 同一設備／合法槽位有多張照片時顯示「同槽多圖」提示並可篩選；不將多圖直接判為拍錯或自動刪除，舊制放置盒不誤報。增加「檔名疑似錯誤／同槽多圖」篩選與匯出說明。
- [ ] 特例資料夾及 Organizer 其他候選情境仍待完整對應與合成驗證；既有舊制放置盒不應套用新制缺槽位／多圖規則，需補相關防回歸案例。
- [x] 合成 SQLite/影像測試：新增檔名錯誤候選、同槽多圖、篩選及 CSV 匯出測試，確認既有 `item_issue` 不受影響；pytest **205 passed**、Vitest **64 passed**、Ruff check／format、TypeScript／Vite build、版本一致性 v1.9.0 均通過。Windows `packaging/build.ps1` Exit Code 0，產生 `dist/FireLens.exe`、`dist/installer/FireLens-1.9.0-setup.exe`，portable／installer 更新器 READY／HEALTHY、rollback／故障注入 E2E 通過；已同步 AGENTS／README／TASKS。實際 Windows WebView2 UI／特殊資料夾完整驗收未完成，不推送 GitHub／Release。

### M18-E 特例資料夾及整理候選整合（2026-11-11）

- [x] 與清冊核對共用 `SPECIAL_PERIODS`，在品質卡片辨識 `5P 二氧化碳滅火器`、`壓力錶壞`、`新增5P 二氧化碳(含放置盒)` 特例批次；顯示「特例資料夾」標記且不依一般槽位缺照／未對應／同槽多圖誤報（影像本身模糊、曝光與人工覆核仍可檢查）。舊制放置盒維持現行保護。
- [x] 與 Organizer 既有 `_variant_issues` 共用 Unicode／異體字提示（棟別及設備編號），避免僅因異體字暗中更名；新增可篩選「名稱異體字」及「特例資料夾」條件，特例分類不等於品質不良，不可單獨納入預設只顯示異常。
- [x] 品質卡片、`problem_only`、CSV／Excel 匯出含新增候選提示與安全原因；維持資料唯讀、照片掃描手動觸發、設備異常單選隔離。特例標記適用所有類別，不能將非特殊月份的正常照片隱藏。修復前端對特例／舊制假性缺照文案。
- [x] 合成測試包含全部三種特例、正常月份、異體字、既有舊制放置盒及 CSV／Excel；本輪全專案 **pytest 207 passed**、**Vitest 65 passed**、Ruff check／format、TypeScript／Vite、版本一致性 v1.9.0 PASS。Windows `packaging/build.ps1` Exit Code 0，生成 `dist/FireLens.exe` 與 `dist/installer/FireLens-1.9.0-setup.exe`；實際打包更新器 portable／installer READY／HEALTHY、rollback／故障注入 E2E passed。現場 Windows WebView2 UI、Google Drive 真實同步及現場影像門檻仍須另行驗收；不 Push／Tag／Release。

### M18-UI-BUG 照片槽位工具列響應式排版（2026-11-10）

使用者截圖：滅火器「編號／藥劑／完成」三欄照片卡片的「換圖／重新命名／移動／交換／刪除」按鈕過寬，右側「刪除」被裁切無法正常操作。診斷：PhotoTile 的 photo-actions 內聯固定 flex 未換行，photo-tile overflow:hidden；slot-wall 為固定最小欄寬，無容器尺寸降欄規則。**只改 UI 排版，不改按鈕綁定、刪除確認、照片或資料庫**。v1.8.0 已正式發布，本輪 Bug 修正使用 歷史 PATCH v1.8.1 作為當時開發版本，未經指示不推 GitHub/Release。

- [x] PhotoTile 操作區移除造成單排溢出的內聯 style，保留「換圖／重新命名／移動／交換／刪除」及多圖前後移動按鈕，用可換行的 CSS grid：窄卡兩欄、非常窄一欄，足夠寬可增加欄數，所有按鈕顯示完整且可點選，不出現水平裁切；檔名長時省略顯示但 title 仍完整。
- [x] 照片槽位牆依 photo-panel 可用寬度自動三欄／兩欄／單欄，不讓卡片寬度超出面板；同時測試「編號／藥劑／完成」及「前／中／後」、多張照片多個按鈕、深淺色、Windows 125%／150% 縮放、鍵盤 Tab 與 Enter；不依靠整個畫面水平捲動才能按刪除。
- [x] 回歸測試包含 PhotoTile 工具列 JSX 不使用 inline flex、按鈕齊全、照片容器及槽位牆容器查詢降欄。Python pytest 193 passed、Vitest 60 passed、Ruff check/format、TypeScript/Vite、歷史 v1.8.1 版本一致性 PASS；Windows packaging/build.ps1 Exit Code 0、繁中 歷史 FireLens-1.8.1-setup.exe、portable/installer 更新器 READY/HEALTHY、rollback/故障注入 E2E 通過。AGENTS／README／TASKS 已同步，本機 Git 提交待建立；沒有 push／Release。
- [ ] Windows WebView2 實機畫面驗收：三個照片槽位在不同視窗寬度、125%／150% 顯示縮放與深淺色下，完整看到換圖／重新命名／移動交換／刪除，點擊「刪除」仍出現原有確認；鍵盤 Tab 及 Enter 可操作。單元與 CSS 結構測試不代表實機排版檢查已完成。

### M18-F Windows 剪貼簿圖片貼上權限提示優化（2026-11-11）

- [x] 移除視窗 focus 探測與 `navigator.clipboard.read()` 主動讀取；頁面載入、切換視窗及一般重新整理均不會主動要求瀏覽器剪貼簿讀取權限。
- [x] Windows pywebview「貼上照片」按鈕改採 `js_api=ClipboardApi()` 原生圖片橋接，繞過瀏覽器 `clipboard-read` 權限窗；一般瀏覽器維持 Ctrl+V `paste` 事件、按鈕改顯示 FireLens 自有置中引導。照片取得後仍由既有置中預覽確認，禁止未確認自動寫入。
- [x] 只在使用者按貼上後讀取，PNG 回傳大小上限 100 MB、圖片尺寸上限 5000 萬像素；非影像／空剪貼簿不匯入，無 HTTP 讀剪貼簿 API、無臨時原圖存檔；新合成 Python／Vitest 測試通過。全專案 pytest **210 passed**、Vitest **67 passed**、Ruff check/format、TypeScript／Vite、v1.9.0 版本一致性全部 PASS；Windows `packaging/build.ps1` Exit Code 0，成功產生 `dist/FireLens.exe`、`dist/installer/FireLens-1.9.0-setup.exe`，portable／installer READY／HEALTHY、rollback／故障注入 E2E passed；AGENTS／README／TASKS 已同步。本版本尚未正式發佈，不推 GitHub／Release。
- [ ] 真實 Windows 桌面 WebView2 使用 LINE 圖片實際測試按鈕／Ctrl+V、空剪貼簿、置中提示與原圖預覽；打包 self-test 並不代表已完成真人 UI 點擊驗收。

### M18-G 資料樹獨立捲動與照片工作區定位（2026-11-11，使用者截圖）

- [x] **照片瀏覽限定三欄獨立捲動**：原 `.app-shell` 只有 `min-height:100vh`，長樹撐高整頁；照片瀏覽模式套用 `.app-shell.browse-layout` 的 `100dvh` 與 workspace `min-height:0`，三欄各自有獨立 `overflow-y:auto`／`overscroll-behavior-y:contain`，不影響其他主標籤頁捲動。
- [x] **左側資料樹固定操作區**：「資料樹／筆數」與搜尋欄固定頂部，僅 `.tree-view` 可獨立滾動、保留原有樹展開／搜尋／選取與 `scrollIntoView` 定位；可用鍵盤聚焦設備清單且有聚焦外框。
- [x] **右側新選取回頂端**：`photoPanelRef` 切換設備時將照片面板 `scrollTop=0`，左側既有捲動位置不重設；右側照片與資訊欄各自可捲動。已新增 3 項 Vitest/CSS 靜態佈局回歸測試，含非照片瀏覽頁隔離；Windows 100/125/150%、短視窗與實際滑鼠滾輪仍須實機視覺驗收。
- [x] **合成驗收／打包**：僅修改 UI 佈局／必要 DOM，沒有觸碰照片、SQLite 或資料樹演算法。新增 Vitest/CSS 回歸測試；本輪 Ruff check/format、pytest **210 passed**、Vitest **70 passed**、TypeScript／Vite、v1.9.0 版本一致性 PASS。Windows `packaging/build.ps1` Exit Code 0，產生 `dist/FireLens.exe` 與 `dist/installer/FireLens-1.9.0-setup.exe`，portable／installer READY／HEALTHY、rollback／故障注入 E2E 通過；AGENTS／README／TASKS 已同步，未 Push／Release。
- [ ] **真實 Windows UI 驗收**：需在實際 WebView2 視窗確認不同長度資料樹滑輪與觸控板、左欄捲到底、右側切換設備回頂、鍵盤 Tab／方向鍵、100%／125%／150% 縮放、窄／短視窗、深淺模式與各種通知列，不得以 CSS/Vitest 自動測試取代實機視覺驗收。

### M18-H 照片品質檢查匯出修復、操作按鈕與掃描進度 UI（2026-11-11，使用者兩張截圖）

- [x] **CSV／Excel 匯出實作**：原品質頁直接使用 HTML 附件連結，Windows pywebview/WebView2 可能無反應。Windows 桌面模式新增 `/api/quality/{root_id}/export/save` 並共用現有 `ExportRegistry.save`，具成功／失敗回饋、檔名／儲存路徑、開啟檔案／資料夾；一般瀏覽器沿用 GET 匯出 API 以 Blob 下載。保留全部篩選條件且不受畫面每頁 40 台限制；合成資料驗證 46 台設備跨頁匯出、UTF-8 BOM、XLSX、空清單、不支援格式與錯誤類別，既有公式注入測試保留。
- [x] **匯出／照片牆按鈕美化**：CSV／Excel 增加清楚的品牌色區分、下載符號、loading／disabled／hover／focus 與自適應換行；卡片「前往照片牆」改成深藍完整寬度導覽按鈕和箭頭，保留原 `onOpenItem(rootId,item.id)`。深色模式和縮放的 CSS 結構完成，實機可視性待驗收。
- [x] **掃描進度與 ETA**：後端品質掃描加 `started_at`、`analysis_started_at` 時戳；前端按實際分析速率、已完成／總數推算剩餘時間，索引／初期樣本不足顯示「計算中」，完成／取消／失敗停止倒數。新增百分比進度條、索引階段動畫與 reduced-motion 保護、分階段狀態及掃描摘要；Vitest 覆蓋正常／索引／少量／零張／超量／取消／失敗。
- [x] **統計資訊視覺優化**：設備總數、異常設備、問題線索改成 3 張大字數字卡片；掃描階段字體 17px、進度百分比 27px、統計 28px，依寬度縮欄並增加深色模式與成功／失敗訊息對比；不放大照片細項而影響清單密度。
- [x] **合成與打包驗收**：使用合成 SQLite／FastAPI 客戶端驗證 CSV/XLSX 檔案實際存取、篩選及 46 台跨頁全量匯出、空清單、無效格式和類別，以及公式注入既有測試；ETA／進度前端測試涵蓋索引、低樣本、進行中、完成、取消、錯誤、0 張。Ruff check／format PASS、pytest **211 passed**、Vitest **74 passed**、TypeScript／Vite build 與 v1.9.0 版本一致性 PASS。Windows `packaging/build.ps1` Exit Code 0，產生 `dist/FireLens.exe` 與 `dist/installer/FireLens-1.9.0-setup.exe`，打包後 portable／installer READY／HEALTHY、rollback／故障注入 E2E 通過。AGENTS／README／TASKS 已同步，不 Push／Tag／Release。
- [ ] **真實 Windows WebView2 驗收**：仍需人工在 Windows 桌面版點擊 CSV／Excel，確認本機儲存路徑、開啟檔案／資料夾、錯誤回饋與縮放；確認約 2000 張照片的掃描進度條／ETA、深淺色、不同視窗大小，以及 LINE／Google Drive 來源情境。合成測試與打包不代表 GUI 驗收通過。

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

import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import {
  preparedForVersion,
  UPDATE_POLL_INTERVAL_MS,
  updateActionLabel,
  updateFailureMessage,
  updatePhaseLabel,
  updateProgressText,
} from './updateFlow'
import type {
  AppInfo,
  AppSettings,
  CategoryDefinition,
  RootRecord,
  UpdatePreparationStatus,
  UpdateStatus,
  OAuthClientSettings,
} from './types'

type Props = {
  roots: RootRecord[]
  categories: CategoryDefinition[]
  settings: AppSettings | null
  appInfo: AppInfo | null
  onSettingsChanged: (settings: AppSettings) => void
  onRootsChanged: () => Promise<void>
  onCategoriesChanged: () => Promise<void>
}

function humanBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

export function SettingsView({
  roots,
  categories,
  settings,
  appInfo,
  onSettingsChanged,
  onRootsChanged,
  onCategoriesChanged,
}: Props) {
  const [draft, setDraft] = useState<AppSettings | null>(settings)
  const [rootDrafts, setRootDrafts] = useState<Record<number, { label: string; is_cloud_stream: boolean }>>({})
  const [aliasDrafts, setAliasDrafts] = useState<Record<string, Record<string, string>>>({})
  const [aliasCategory, setAliasCategory] = useState('extinguisher')
  const [newAliasName, setNewAliasName] = useState('')
  const [newAliasSlot, setNewAliasSlot] = useState('')
  const [aliasHelpOpen, setAliasHelpOpen] = useState(false)
  const [testFilename, setTestFilename] = useState('')
  const [excludeDraft, setExcludeDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null)
  const [updateProgress, setUpdateProgress] = useState<UpdatePreparationStatus | null>(null)
  const [updateBusy, setUpdateBusy] = useState(false)
  const [oauthSettings, setOauthSettings] = useState<OAuthClientSettings | null>(null)
  const [oauthSecretDraft, setOauthSecretDraft] = useState('')
  const [oauthBusy, setOauthBusy] = useState(false)
  const [oauthMessage, setOauthMessage] = useState('')
  const [oauthError, setOauthError] = useState('')



  useEffect(() => setDraft(settings), [settings])
  useEffect(() => {
    let mounted = true
    void api.oauthClientSettings().then((result) => {
      if (mounted) setOauthSettings(result)
    }).catch((err) => {
      if (mounted) setOauthError(err instanceof Error ? err.message : '無法取得 Google OAuth 設定')
    })
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    setRootDrafts(Object.fromEntries(roots.map((root) => [root.id, {
      label: root.label,
      is_cloud_stream: Boolean(root.is_cloud_stream),
    }])))
  }, [roots])
  useEffect(() => {
    setAliasDrafts(Object.fromEntries(categories.map((category) => [
      category.code,
      { ...category.filename_aliases },
    ])))
  }, [categories])

  const backupUrl = useMemo(() => api.backupUrl(), [])
  const lastUpdateFailed = appInfo?.last_update && [
    'error', 'rolled_back', 'rollback_failed', 'helper_start_failed',
  ].includes(appInfo.last_update.phase ?? '')

  async function saveOauthSecret() {
    if (!oauthSecretDraft || oauthBusy) return
    setOauthBusy(true); setOauthError(''); setOauthMessage('')
    try {
      setOauthSettings(await api.saveOauthClientSecret(oauthSecretDraft))
      setOauthSecretDraft('')
      setOauthMessage('Google OAuth Client Secret 已加密保存於目前 Windows 使用者。')
    } catch (err) {
      setOauthError(err instanceof Error ? err.message : 'Google OAuth 設定儲存失敗')
    } finally { setOauthBusy(false) }
  }

  async function clearOauthSecret() {
    if (oauthBusy || !window.confirm('確定清除本機保存的 Google OAuth Client Secret？不會刪除 Google Drive 資料。')) return
    setOauthBusy(true); setOauthError(''); setOauthMessage('')
    try {
      setOauthSettings(await api.clearOauthClientSecret())
      setOauthSecretDraft('')
      setOauthMessage('已清除本機儲存的 Google OAuth Client Secret。')
    } catch (err) {
      setOauthError(err instanceof Error ? err.message : '清除 Google OAuth 設定失敗')
    } finally { setOauthBusy(false) }
  }

  async function saveGeneral() {
    if (!draft) return
    setBusy(true); setError(''); setMessage('')
    try {
      const updated = await api.saveSettings(draft)
      onSettingsChanged(updated)
      setMessage('設定已儲存。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存設定失敗')
    } finally { setBusy(false) }
  }

  async function saveRoot(rootId: number) {
    const current = rootDrafts[rootId]
    if (!current) return
    setBusy(true); setError(''); setMessage('')
    try {
      await api.updateRootSettings(rootId, current.label, current.is_cloud_stream)
      await onRootsChanged()
      setMessage('根目錄設定已儲存；路徑本身沒有被修改。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存根目錄設定失敗')
    } finally { setBusy(false) }
  }

  async function saveAliases(code: string) {
    setBusy(true); setError(''); setMessage('')
    try {
      const aliases = aliasDrafts[code] ?? {}
      const legalSlots = categories.find((c) => c.code === code)?.slots ?? []
      if (Object.values(aliases).some((slot) => !legalSlots.includes(slot))) throw new Error('辨識用途不符合此設備類別的照片槽位')
      await api.updateCategoryAliases(code, aliases)
      await onCategoriesChanged()
      setMessage('檔名同義詞已儲存。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存同義詞失敗')
    } finally { setBusy(false) }
  }

  async function restore(file: File) {
    if (!window.confirm('還原只合併受保護設定/清冊/紀錄，不會修改照片。執行前會建立 SQLite 快照。確定繼續？')) return
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.restoreBackup(file)
      await Promise.all([onRootsChanged(), onCategoriesChanged()])
      const latest = await api.settings()
      onSettingsChanged(latest)
      setMessage(`備份還原完成；還原前 SQLite 快照：${result.snapshot_path}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '備份還原失敗')
    } finally { setBusy(false) }
  }

  async function checkUpdate() {
    setUpdateBusy(true); setError(''); setMessage('')
    try {
      const status = await api.checkUpdate()
      setUpdateStatus(status)
      if (!status.available) setUpdateProgress(null)
      setMessage(status.available ? `發現新版 FireLens v${status.latest_version}` : '目前已是最新版本。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '檢查更新失敗')
    } finally { setUpdateBusy(false) }
  }

  async function installVerifiedUpdate(version: string) {
    setUpdateBusy(true); setError(''); setMessage('')
    setUpdateProgress((current) => current ? {
      ...current,
      phase: 'installing',
      message: '正在安裝更新並重新啟動 FireLens…',
      ready: false,
      running: false,
      error: null,
    } : current)
    try {
      const result = await api.installUpdate(version)
      setMessage(result.ready
        ? '獨立更新器已就緒，FireLens 即將安全關閉、更新並重新啟動。'
        : '更新器尚未就緒；FireLens 不會關閉。')
    } catch (err) {
      const latestProgress = await api.updateProgress().catch(() => null)
      if (latestProgress) setUpdateProgress(latestProgress)
      setError(err instanceof Error ? err.message : '安裝更新失敗')
      setUpdateBusy(false)
    }
  }

  async function downloadAndInstallUpdate() {
    if (!updateStatus?.available || !updateStatus.installable || updateBusy) return
    const version = updateStatus.latest_version
    setUpdateBusy(true); setError(''); setMessage('')
    try {
      let progress = updateProgress
      if (!preparedForVersion(progress, version)) {
        progress = await api.prepareUpdate(version)
        setUpdateProgress(progress)
        while (!progress.ready && progress.phase !== 'error') {
          await new Promise((resolve) => window.setTimeout(resolve, UPDATE_POLL_INTERVAL_MS))
          progress = await api.updateProgress()
          setUpdateProgress(progress)
        }
      }

      if (!progress || progress.phase === 'error') {
        throw new Error(progress ? updateFailureMessage(progress) : '更新準備失敗，請重試')
      }
      if (progress.update) setUpdateStatus(progress.update)

      setMessage(`v${version} 已完成簽章、SHA-256 與 EXE self-test 安全驗證。`)
      const confirmed = window.confirm(
        `更新已驗證完成，FireLens 將關閉並更新到 v${version}，完成後自動重新啟動。確定繼續？`,
      )
      if (!confirmed) {
        setMessage(`已取消安裝 v${version}；已驗證更新仍保留，可稍後繼續安裝。`)
        setUpdateBusy(false)
        return
      }
      await installVerifiedUpdate(version)
    } catch (err) {
      setError(err instanceof Error ? err.message : '下載並安裝更新失敗')
      setUpdateBusy(false)
    }
  }

  if (!draft) return <section className="settings-page"><p>讀取設定中…</p></section>

  return (
    <section className="settings-page" aria-label="FireLens 設定">
      {error && <div className="error-banner" role="alert">{error}</div>}
      {message && <div className="success-banner" role="status">{message}</div>}

      <section className="panel-card settings-card google-oauth-settings">
        <div className="panel-title"><h2>Google OAuth 設定</h2><span>Windows 本機加密保存</span></div>
        <p className="help-text">設定後即可在「查看滅火器資料」使用 Google 帳號登入，不必再設定 PowerShell 環境變數。Client Secret 僅儲存在目前 Windows 使用者的本機加密檔案，不會寫進 GitHub。</p>
        {oauthError && <p className="error-banner" role="alert">{oauthError}</p>}
        {oauthMessage && <p className="success-banner" role="status">{oauthMessage}</p>}
        <div className="settings-grid">
          <label>OAuth Client ID
            <input type="text" readOnly value={oauthSettings?.client_id ?? '讀取中…'} />
          </label>
          <label>OAuth Client Secret（{oauthSettings?.configured ? '已設定' : '未設定'}）
            <input type="password" autoComplete="new-password" value={oauthSecretDraft}
              onChange={(event) => setOauthSecretDraft(event.target.value)}
              placeholder="輸入新的 Desktop OAuth Client Secret" disabled={oauthBusy} />
          </label>
        </div>
        <div className="google-oauth-buttons">
          <button type="button" className="primary-button" onClick={() => void saveOauthSecret()}
            disabled={oauthBusy || !oauthSecretDraft.trim()}>加密儲存</button>
          <button type="button" className="secondary-button" onClick={() => void clearOauthSecret()}
            disabled={oauthBusy || !oauthSettings?.configured}>清除已存設定</button>
        </div>
        <p className="help-text">儲存後不會再顯示 Client Secret。下次登入會自動使用已保存的設定；若未設定，仍可採用舊環境變數或 PKCE-only。</p>
      </section>

      <section className="panel-card settings-card">
        <div className="panel-title"><h2>介面與快取</h2><span>持久化設定</span></div>
        <div className="settings-grid">
          <label>介面主題
            <select value={draft.theme} onChange={(event) => setDraft({ ...draft, theme: event.target.value as AppSettings['theme'] })}>
              <option value="system">跟隨系統</option><option value="light">淺色</option><option value="dark">深色</option>
            </select>
          </label>
          <label>縮圖 JPEG 品質：{draft.thumbnail_quality}
            <input type="range" min="60" max="95" value={draft.thumbnail_quality} onChange={(event) => setDraft({ ...draft, thumbnail_quality: Number(event.target.value) })} />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={draft.auto_scan_on_start}
              onChange={(event) => setDraft({ ...draft, auto_scan_on_start: event.target.checked })}
            />
            啟動時自動掃描
          </label>
          <label>自動掃描最短間隔（分鐘）
            <input
              type="number"
              min="1"
              max="1440"
              value={draft.auto_scan_min_interval_minutes}
              disabled={!draft.auto_scan_on_start}
              onChange={(event) => setDraft({
                ...draft,
                auto_scan_min_interval_minutes: Math.max(1, Math.min(1440, Number(event.target.value) || 1)),
              })}
            />
          </label>
        </div>
        <p className="help-text">自動掃描預設開啟，預設至少相隔 5 分鐘才再次觸發；手動「重新掃描」不受此門檻限制。</p>
        <h3>排除根目錄資料夾</h3>
        <p className="help-text">只設定根目錄第一層名稱。系統自動排除 FireLens-共享異常資料與 Windows 系統資料夾；儲存後重新掃描生效，不會刪除實體資料夾。</p>
        <div className="settings-grid">
          <label>新增排除名稱
            <input aria-label="新增排除資料夾名稱" value={excludeDraft}
              onChange={(event) => setExcludeDraft(event.target.value)}
              placeholder="例如：暫存照片" />
          </label>
          <button type="button" className="secondary-button"
            disabled={!excludeDraft.trim() || busy}
            onClick={() => {
              if (!draft) return
              const name = excludeDraft.trim()
              if (!name || draft.excluded_root_folders.some((value) => value.toLowerCase() === name.toLowerCase())) return
              setDraft({ ...draft, excluded_root_folders: [...draft.excluded_root_folders, name] })
              setExcludeDraft('')
            }}>加入排除清單</button>
        </div>
        <div className="settings-list">
          {draft.excluded_root_folders.map((name) => (
            <div key={name} className="settings-row">
              <span>{name}</span>
              <button type="button" className="secondary-button" onClick={() => setDraft({
                ...draft, excluded_root_folders: draft.excluded_root_folders.filter((item) => item !== name),
              })}>移除排除</button>
            </div>
          ))}
        </div>
        <h3>槽位顯示順序</h3>
        <div className="settings-grid">
          {categories.map((category) => (
            <label key={category.code}>{category.name}
              <input
                aria-label={`${category.name}槽位顯示順序`}
                value={(draft.slot_order[category.code] ?? category.slots).join('、')}
                onChange={(event) => setDraft({
                  ...draft,
                  slot_order: {
                    ...draft.slot_order,
                    [category.code]: event.target.value.split(/[、,，]/).map((part) => part.trim()).filter(Boolean),
                  },
                })}
              />
            </label>
          ))}
        </div>
        <h3>自訂槽位（選填）</h3>
        <p className="help-text">以逗號或頓號分隔。新增後即可在照片牆看見該槽位，不影響缺漏判定。</p>
        <div className="settings-grid">
          {categories.map((category) => (
            <label key={`custom_${category.code}`}>{category.name} 自訂槽位
              <input
                aria-label={`${category.name}自訂槽位`}
                value={(draft.custom_slots?.[category.code] ?? []).join('、')}
                onChange={(event) => setDraft({
                  ...draft,
                  custom_slots: {
                    ...draft.custom_slots,
                    [category.code]: event.target.value.split(/[、,，]/).map((part) => part.trim()).filter(Boolean),
                  },
                })}
              />
            </label>
          ))}
        </div>
        <button className="primary-button" type="button" disabled={busy} onClick={() => void saveGeneral()}>儲存介面與快取設定</button>
      </section>

      <section className="panel-card settings-card">
        <div className="panel-title"><h2>照片根目錄</h2><span>{roots.length}</span></div>
        <p className="help-text">只可修改顯示名稱與「雲端串流」標記；此頁不提供刪除或改路徑。</p>
        <div className="settings-list">
          {roots.map((root) => {
            const current = rootDrafts[root.id] ?? { label: root.label, is_cloud_stream: Boolean(root.is_cloud_stream) }
            return <div className="settings-row" key={root.id}>
              <label>名稱<input value={current.label} onChange={(event) => setRootDrafts({ ...rootDrafts, [root.id]: { ...current, label: event.target.value } })} /></label>
              <label className="check-label"><input type="checkbox" checked={current.is_cloud_stream} onChange={(event) => setRootDrafts({ ...rootDrafts, [root.id]: { ...current, is_cloud_stream: event.target.checked } })} />Google Drive／雲端串流</label>
              <code title={root.path}>{root.path}</code>
              <button type="button" disabled={busy} onClick={() => void saveRoot(root.id)}>儲存</button>
            </div>
          })}
        </div>
      </section>

      <section className="panel-card settings-card">
        <div className="panel-title">
          <h2>照片檔名辨識設定</h2>
          <button type="button" className="secondary-button" onClick={() => setAliasHelpOpen(true)}>？使用說明</button>
        </div>
        <p className="help-text">讓不同檔名對應到相同照片用途；只影響辨識結果，不會重新命名原始照片。</p>
        <div className="alias-category-tabs" role="group" aria-label="設備類別">
          {categories.map((category) => (
            <button type="button" key={category.code} className={aliasCategory === category.code ? 'active' : ''}
              onClick={() => { setAliasCategory(category.code); setNewAliasName(''); setNewAliasSlot(''); setTestFilename('') }}>
              {category.name}
            </button>
          ))}
        </div>
        {categories.filter((c) => c.code === aliasCategory).map((category) => (
          <div key={category.code} className="alias-rules">
            <div className="alias-rule-header"><b>照片檔名</b><b>辨識為</b><span>操作</span></div>
            {Object.entries(aliasDrafts[category.code] ?? {}).map(([name, slot]) => (
              <div className="alias-rule" key={name}>
                <span title={name}>{name}</span>
                <select aria-label={name + ' 對應用途'} value={slot} onChange={(event) => setAliasDrafts((current) => ({
                  ...current, [category.code]: { ...current[category.code], [name]: event.target.value },
                }))}>
                  {category.slots.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
                <button type="button" disabled={busy} aria-label={'移除 ' + name}
                  onClick={() => setAliasDrafts((current) => {
                    const next = { ...current[category.code] }
                    delete next[name]
                    return { ...current, [category.code]: next }
                  })}>移除</button>
              </div>
            ))}
            <div className="alias-rule">
              <input aria-label="新增照片檔名" value={newAliasName} maxLength={100}
                onChange={(event) => setNewAliasName(event.target.value)} placeholder="例如：有效日期（不含 .jpg）" />
              <select aria-label="新增照片對應用途" value={newAliasSlot || category.slots[0] || ''}
                onChange={(event) => setNewAliasSlot(event.target.value)}>
                {category.slots.map((slot) => <option key={slot} value={slot}>{slot}</option>)}
              </select>
              <button type="button" disabled={busy || !newAliasName.trim() || !!aliasDrafts[category.code]?.[newAliasName.trim()]}
                onClick={() => {
                  const name = newAliasName.trim().replace(/\.(jpg|jpeg|png|heic|heif)$/i, '')
                  if (!name || /[\/]/.test(name) || aliasDrafts[category.code]?.[name]) {
                    setError('請輸入有效且未重複的照片檔名')
                    return
                  }
                  setAliasDrafts((current) => ({
                    ...current, [category.code]: { ...(current[category.code] ?? {}), [name]: newAliasSlot || category.slots[0] },
                  }))
                  setNewAliasName('')
                }}>新增</button>
            </div>
            <label className="alias-test">測試辨識
              <input value={testFilename} onChange={(event) => setTestFilename(event.target.value)}
                placeholder="輸入照片檔名，例如 有效日期.jpg" />
              <span>{testFilename.trim()
                ? (aliasDrafts[category.code]?.[testFilename.trim().replace(/\.[^.]+$/, '')] || '未命中自訂同義詞')
                : '輸入檔名即可檢查'}
              </span>
            </label>
            <button type="button" disabled={busy} onClick={() => void saveAliases(category.code)}>儲存 {category.name} 辨識規則</button>
          </div>
        ))}
        {aliasHelpOpen && (
          <div className="preview-backdrop" onMouseDown={() => setAliasHelpOpen(false)}
            onKeyDown={(event) => { if (event.key === 'Escape') setAliasHelpOpen(false) }}>
            <section className="prompt-dialog" role="dialog" aria-modal="true" aria-label="照片檔名辨識使用說明"
              onMouseDown={(event) => event.stopPropagation()}>
              <div className="prompt-header">照片檔名辨識說明</div>
              <div className="prompt-body">
                <p>不同同事可能使用不同照片檔名；在這裡將名稱對應到正確用途，FireLens 核對照片時便能自動辨識。</p>
                <p>例如：有效日期.jpg → 藥劑；更換完成.jpg → 完成。</p>
                <p>這些規則只影響照片分類，不會修改或刪除原始檔案。</p>
              </div>
              <div className="prompt-footer">
                <button type="button" autoFocus onClick={() => setAliasHelpOpen(false)}>我知道了</button>
              </div>
            </section>
          </div>
        )}
      </section>

      <section className="panel-card settings-card">
        <div className="panel-title"><h2>受保護資料備份</h2><span>不含照片索引</span></div>
        <p className="help-text">備份包含設定、根目錄設定、清冊、別名、改名/稽核紀錄、已補拍標記與未同步離線照片；不包含可重建的 item/photo 索引，也不會碰照片根目錄。</p>
        <div className="backup-actions">
          <a className="download-button" href={backupUrl}>下載受保護資料備份 ZIP</a>
          <label className="secondary-button">還原備份 ZIP
            <input className="sr-only" type="file" accept=".zip,application/zip" disabled={busy} onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void restore(file)
              event.currentTarget.value = ''
            }} />
          </label>
        </div>
      </section>

      {appInfo && <section className="panel-card settings-card">
        <div className="panel-title"><h2>線上更新</h2><span>Ed25519 安全簽章</span></div>
        {lastUpdateFailed && <div className="warning-banner" role="status">
          <b>上次更新未完成，目前仍安全使用 v{appInfo.version}。</b>
          <span>{appInfo.last_update?.error || '更新器已回滾或未完成。'}</span>
          {appInfo.last_update?.log_file && <code>{appInfo.last_update.log_file}</code>}
          <span>可重新「檢查更新」後再試；若歷史版本自動更新後沒有重啟，可直接用最新 setup 覆蓋安裝，不會刪除 data。</span>
        </div>}
        <p className="help-text">
          目前版本 v{appInfo.version}。FireLens 只接受由內建公鑰驗證通過的 GitHub Release；下載後還會再次核對 SHA-256 並執行 EXE self-test。
        </p>
        <div className="backup-actions">
          <button type="button" className="secondary-button" disabled={updateBusy || !appInfo.online_update_enabled} onClick={() => void checkUpdate()}>
            {updateBusy ? '處理中…' : '檢查更新'}
          </button>
          {updateStatus?.available && (
            <button
              type="button"
              className="primary-button"
              disabled={updateBusy || !updateStatus.installable}
              onClick={() => void downloadAndInstallUpdate()}
            >
              {updateBusy && updateProgress
                ? updatePhaseLabel(updateProgress.phase)
                : updateActionLabel(updateProgress, updateStatus.latest_version)}
            </button>
          )}
        </div>
        {!appInfo.online_update_enabled && <p className="help-text">{appInfo.online_update_reason}</p>}
        {updateStatus?.available && !updateStatus.installable && <p className="help-text">{updateStatus.install_reason}</p>}
        {updateProgress && updateProgress.phase !== 'idle' && <div className="update-progress" role="status" aria-live="polite">
          <div className="settings-row">
            <b>{updatePhaseLabel(updateProgress.phase)}</b>
            <span>{updateProgressText(updateProgress)}</span>
          </div>
          {updateProgress.phase === 'downloading' && updateProgress.percent !== null && (
            <progress value={updateProgress.percent} max={100} aria-label="更新下載進度" />
          )}
        </div>}
        {updateStatus && <div className="settings-list">
          <div className="settings-row">
            <b>{updateStatus.available ? `有新版 v${updateStatus.latest_version}` : `最新版本 v${updateStatus.latest_version}`}</b>
            <span>{updateStatus.signature_verified ? '✓ 簽章已驗證' : '簽章未驗證'}</span>
            <span>{humanBytes(updateStatus.asset_size)}</span>
            <a href={updateStatus.release_url} target="_blank" rel="noreferrer">查看 Release</a>
          </div>
          <p className="help-text">{updateStatus.install_reason}</p>
          {updateStatus.notes && <p className="help-text" style={{ whiteSpace: 'pre-wrap' }}>{updateStatus.notes}</p>}
        </div>}
      </section>}

      {appInfo && <section className="panel-card settings-card">
        <div className="panel-title"><h2>應用程式資訊</h2><span>v{appInfo.version}</span></div>
        <dl className="path-list">
          <div><dt>資料庫 schema</dt><dd>{appInfo.schema_version}</dd></div>
          <div><dt>資料目錄</dt><dd><code>{appInfo.data_dir}</code></dd></div>
          <div><dt>快取</dt><dd><code>{appInfo.cache_dir}</code>（{humanBytes(appInfo.cache_size_bytes)}）</dd></div>
          <div><dt>日誌</dt><dd><code>{appInfo.log_file}</code>（{humanBytes(appInfo.log_size_bytes)}）</dd></div>
          <div><dt>備份快照</dt><dd><code>{appInfo.backup_dir}</code></dd></div>
          <div><dt>線上更新</dt><dd>{appInfo.online_update_enabled ? appInfo.online_update_install_reason : appInfo.online_update_reason}</dd></div>
          <div><dt>更新來源</dt><dd><code>{appInfo.online_update_repository}</code></dd></div>
        </dl>
      </section>}
    </section>
  )
}

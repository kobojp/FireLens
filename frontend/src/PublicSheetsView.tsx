import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { PrivateDriveStatus, PrivateSheet, PrivateTab, PrivateValues } from './types'

export function PublicSheetsView() {
  const [status, setStatus] = useState<PrivateDriveStatus | null>(null)
  const [sheets, setSheets] = useState<PrivateSheet[]>([])
  const [tabs, setTabs] = useState<PrivateTab[]>([])
  const [selectedSheet, setSelectedSheet] = useState('')
  const [selectedTab, setSelectedTab] = useState('')
  const [data, setData] = useState<PrivateValues | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<'read' | 'edit'>('read')
  const [requestedEdit, setRequestedEdit] = useState(false)
  const [draft, setDraft] = useState<{
    row: number, column: number, expected: string, value: string
  } | null>(null)
  const [saveConfirm, setSaveConfirm] = useState(false)


  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api.privateDriveStatus())
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法確認 Google 登入狀態')
    }
  }, [])

  useEffect(() => { void refreshStatus() }, [refreshStatus])

  useEffect(() => {
    if (status?.login_state !== 'pending') return
    const poll = window.setInterval(() => void refreshStatus(), 1500)
    return () => window.clearInterval(poll)
  }, [status?.login_state, refreshStatus])

  useEffect(() => {
    if (requestedEdit && status?.editable) {
      setMode('edit')
      setRequestedEdit(false)
    }
  }, [requestedEdit, status?.editable])

  useEffect(() => {
    if (!status?.authenticated) {
      setSheets([])
      setTabs([])
      setSelectedSheet('')
      setSelectedTab('')
      setData(null)
      setDraft(null)
      setSaveConfirm(false)
      setRequestedEdit(false)
      setMode('read')
    }
  }, [status?.authenticated])

  function discardAllowed() {
    return !draft || draft.value === draft.expected ||
      window.confirm('有未儲存的儲存格修改，確定放棄草稿？')
  }

  async function chooseMode(next: 'read' | 'edit') {
    if (next === mode) return
    if (busy || !discardAllowed()) return
    if (next === 'read') {
      setMode('read')
      setDraft(null)
      setSaveConfirm(false)
      setRequestedEdit(false)
      return
    }
    if (!status?.editable) {
      setRequestedEdit(true)
      setError('')
      setBusy(true)
      try {
        await api.privateDriveLogin(true)
        await refreshStatus()
      } catch (err) {
        setRequestedEdit(false)
        setError(err instanceof Error ? err.message : '無法開始 Google 編輯授權')
      } finally { setBusy(false) }
      return
    }
    setMode('edit')
  }

  function selectCell(row: number, column: number, expected: string) {
    if (mode !== 'edit' || busy || !discardAllowed()) return
    setDraft({ row, column, expected, value: expected })
    setSaveConfirm(false)
  }

  async function saveCell() {
    if (!draft || draft.value === draft.expected || busy || !selectedSheet || !selectedTab) return
    setBusy(true)
    setError('')
    try {
      const changed = await api.editPrivateCell(selectedSheet, {
        tab: selectedTab, row: draft.row, column: draft.column,
        expected: draft.expected, value: draft.value,
      })
      if (!changed.saved) throw new Error('Google 未確認已儲存，請重新載入核對')
      setSaveConfirm(false)
      setDraft(null)
      // Google already acknowledged the write: do not report it as failed if a reload fails.
      try {
        setData(await api.privateDriveValues(selectedSheet, selectedTab, data?.start_row ?? 1))
      } catch {
        setData(null)
        setError('Google 已確認儲存，但重新讀取失敗。請按工作表選單重新載入核對內容。')
      }
    } catch (err) {
      setSaveConfirm(false)
      setError(err instanceof Error ? err.message : '儲存未獲確認，請先核對 Google 表格再重試')
    } finally { setBusy(false) }
  }


  async function login() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.privateDriveLogin()
      await refreshStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google 登入無法開始')
    } finally { setBusy(false) }
  }

  async function logout() {
    if (busy || !discardAllowed()) return
    setBusy(true)
    setError('')
    try {
      const result = await api.privateDriveLogout()
      await refreshStatus()
      if (!result.remote_revocation_confirmed) {
        setError('本機已登出，但 Google 遠端撤銷可能未完成；必要時請至 Google 帳號安全性頁面撤銷 FireLens。')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '登出失敗')
    } finally { setBusy(false) }
  }

  async function loadSheets() {
    if (busy || !discardAllowed()) return
    setDraft(null)
    setBusy(true)
    setError('')
    try {
      setSheets(await api.privateDriveSheets())
      setTabs([])
      setSelectedSheet('')
      setSelectedTab('')
      setData(null)
    } catch (err) { setError(err instanceof Error ? err.message : '無法載入私人試算表') }
    finally { setBusy(false) }
  }

  async function chooseSheet(id: string) {
    if (busy || !discardAllowed()) return
    setDraft(null)
    setSelectedSheet(id)
    setSelectedTab('')
    setTabs([])
    setData(null)
    if (!id) return
    setBusy(true)
    setError('')
    try {
      const response = await api.privateDriveTabs(id)
      setTabs(response)
    } catch (err) { setError(err instanceof Error ? err.message : '無法讀取工作表清單') }
    finally { setBusy(false) }
  }

  async function loadValues(sheet: string, tab: string, row = 1) {
    if (!sheet || !tab || busy || !discardAllowed()) return
    setDraft(null)
    setBusy(true)
    setError('')
    setData(null)
    try { setData(await api.privateDriveValues(sheet, tab, row)) }
    catch (err) { setError(err instanceof Error ? err.message : '無法載入試算表資料') }
    finally { setBusy(false) }
  }

  return (
    <section className="settings-page private-drive-page" aria-label="查看滅火器資料">
      <section className="panel-card settings-card private-drive-card">
        <div className="panel-title">
          <h2>查看滅火器資料</h2>
          <span>Google Drive 私人資料夾 · {mode === 'read' ? '唯讀' : '編輯'}</span>
        </div>
        <p className="help-text">資料夾已設為限制存取。只有 Google Drive 授權的帳號才能查看更換紀錄；登入會在系統瀏覽器完成，FireLens 不會取得你的 Google 密碼。</p>
        {error && <p className="error-banner" role="alert">{error}</p>}
        {status?.error && <p className="warning-banner" role="status">{status.error}</p>}
        <div className="private-drive-auth">
          {!status?.authenticated && (
            <button type="button" className="primary-button"
              disabled={busy || status?.login_state === 'pending'}
              onClick={() => void login()}>
              {status?.login_state === 'pending' ? '請在系統瀏覽器完成 Google 授權…' : '使用 Google 帳號登入'}
            </button>
          )}
          {status?.login_state === 'pending' && (
            <button type="button" onClick={() => void logout()} disabled={busy}>取消登入</button>
          )}
          {status?.authenticated && <>
            <strong>Google 已授權 · {status.editable ? '具編輯授權' : '唯讀授權'}</strong>
            <button type="button" disabled={busy} onClick={() => void loadSheets()}>重新整理試算表清單</button>
            <button type="button" disabled={busy} onClick={() => void logout()}>登出 Google</button>
          </>}
        </div>
        {status?.authenticated && (
          <>
            <div className="private-sheet-mode" role="group" aria-label="試算表操作模式">
              <button type="button" className={mode === 'read' ? 'active' : ''}
                aria-pressed={mode === 'read'} disabled={busy}
                onClick={() => void chooseMode('read')}>唯讀</button>
              <button type="button" className={mode === 'edit' ? 'active' : ''}
                aria-pressed={mode === 'edit'} disabled={busy || status.login_state === 'pending'}
                onClick={() => void chooseMode('edit')}>編輯</button>
              {status.login_state === 'pending' && <span role="status">請在瀏覽器完成 Google 編輯授權…</span>}
            </div>
            <p className="help-text">預設唯讀。切到編輯會要求 Google 試算表編輯授權，實際寫入仍以 Google Drive 的檔案權限為準；若帳號只有「檢視者」權限，Google 會拒絕儲存。僅允許目前頁面單格修改，儲存前會再次檢查原值。</p>
            <p className="help-text">只顯示指定資料夾中、此帳號有權限讀取的 Google 試算表。首次登入請按「重新整理試算表清單」。</p>
            <label className="public-sheet-selector">選擇試算表（{sheets.length} 份）
              <select value={selectedSheet} disabled={busy}
                onChange={(event) => void chooseSheet(event.target.value)}>
                <option value="">請選擇</option>
                {sheets.map((sheet) => <option key={sheet.id} value={sheet.id}>{sheet.name}</option>)}
              </select>
            </label>
            {!!selectedSheet && (
              <label className="public-sheet-selector">工作表
                <select value={selectedTab} disabled={busy}
                  onChange={(event) => {
                    if (!discardAllowed()) return
                    setDraft(null)
                    setSelectedTab(event.target.value)
                    void loadValues(selectedSheet, event.target.value)
                  }}>
                  <option value="">請選擇工作表</option>
                  {tabs.map((tab) => <option value={tab.title} key={tab.id}>{tab.title}</option>)}
                </select>
              </label>
            )}
            {busy && <p role="status">正在讀取資料…</p>}
            {data && (
              <div className="private-sheet-table-wrap">
                <table className="private-sheet-table">
                  <tbody>
                    {(data.rows.length ? data.rows : mode === 'edit' ? [[]] : []).map((row, idx) => (
                      <tr key={idx}>
                        <th scope="row">{data.start_row + idx}</th>
                        {Array.from({ length: mode === 'edit' ? 30 : row.length }, (_, column) => {
                          const value = row[column] ?? ''
                          return <td key={column}>
                          {mode === 'edit' ? (
                            <button type="button" className="private-sheet-cell-edit"
                              onClick={() => selectCell(data.start_row + idx, column + 1, value)}
                              disabled={busy} title="點擊修改此儲存格">{value || '　'}</button>
                          ) : value}
                        </td>
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {data.rows.length === 0 && <p className="help-text">這個範圍沒有資料。</p>}
                {mode === 'edit' && draft && (
                  <div className="private-cell-editor" role="region" aria-label="編輯儲存格">
                    <strong>編輯儲存格：第 {draft.row} 列，第 {draft.column} 欄</strong>
                    <div className="private-cell-original">原始內容：{draft.expected || '（空白）'}</div>
                    <textarea rows={3} maxLength={2000} value={draft.value}
                      disabled={busy} aria-label="新儲存格內容"
                      onChange={(event) => setDraft({ ...draft, value: event.target.value })}/>
                    <div className="google-oauth-buttons">
                      <button type="button" disabled={busy || draft.value === draft.expected}
                        onClick={() => setSaveConfirm(true)}>儲存變更…</button>
                      <button type="button" disabled={busy}
                        onClick={() => { setDraft(null); setSaveConfirm(false) }}>取消編輯</button>
                    </div>
                    <p className="help-text">資料以文字 RAW 模式儲存；Google 不會將輸入的 = 開頭內容自動執行為公式。</p>
                  </div>
                )}
                <div className="private-sheet-pagination">
                  <button type="button" disabled={busy || data.start_row === 1}
                    onClick={() => void loadValues(selectedSheet, selectedTab, Math.max(1, data.start_row - 100))}>上一頁</button>
                  <span>第 {data.start_row} 列起，每頁最多 100 列 × 30 欄</span>
                  <button type="button" disabled={busy || data.next_row === null}
                    onClick={() => void loadValues(selectedSheet, selectedTab, data.next_row!)}>下一頁</button>
                </div>
              </div>
            )}
          </>
        )}
        {saveConfirm && draft && (
          <div className="preview-backdrop" onMouseDown={() => !busy && setSaveConfirm(false)}>
            <section className="prompt-dialog" role="dialog" aria-modal="true" aria-label="確認修改 Google 試算表"
              onMouseDown={(event) => event.stopPropagation()}>
              <div className="prompt-header">確認修改 Google 試算表</div>
              <div className="prompt-body">
                <p>工作表：<b>{selectedTab}</b>，第 {draft.row} 列，第 {draft.column} 欄</p>
                <p>原值：<b>{draft.expected || '（空白）'}</b></p>
                <p>新值：<b>{draft.value || '（清空）'}</b></p>
                <p>確認後會嘗試直接儲存到 Google 試算表，無法直接復原。若他人已更新原值，FireLens 會拒絕覆蓋；但 Google Sheets API 不保證跨使用者同時修改的原子性。</p>
              </div>
              <div className="prompt-footer">
                <button type="button" onClick={() => setSaveConfirm(false)} disabled={busy}>取消</button>
                <button type="button" className="primary-button" onClick={() => void saveCell()}
                  disabled={busy || draft.value === draft.expected}>確認儲存</button>
              </div>
            </section>
          </div>
        )}
        <p className="help-text">Google 測試版 OAuth 授權可能需定期重新登入；若出現未驗證應用程式警告，請確認你在 Google Cloud 測試使用者名單，並只授權自己建立的 FireLens。</p>
      </section>
    </section>
  )
}

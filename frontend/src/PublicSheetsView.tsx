import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { loadPrivateSheetListOnce } from './privateSheetAutoLoad'
import {
  boundsFor, boundsLabel, columnName, inSelection, tsvFromRows,
  trimTrailingBlankRows, loadCopyRows,
} from './sheetCopy'
import type { SheetSelection } from './sheetCopy'

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
  const [openBrowserBusy, setOpenBrowserBusy] = useState(false)
  const [autoLoadingSheets, setAutoLoadingSheets] = useState(false)
  const [selection, setSelection] = useState<SheetSelection | null>(null)
  const [copyTotalRows, setCopyTotalRows] = useState<number | null>(null)
  const [includeHeader, setIncludeHeader] = useState(false)
  const [copyBusy, setCopyBusy] = useState(false)
  const [copyProgress, setCopyProgress] = useState('')
  const [copyNotice, setCopyNotice] = useState('')
  const [preparedCopy, setPreparedCopy] = useState<{
    text: string, label: string, rows: number, columns: number
  } | null>(null)
  const copyGeneration = useRef(0)




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

  // Each time the tab mounts with an authenticated session, or OAuth login
  // transitions from logged out to logged in, fetch the private folder once.
  // Edits to OAuth scope or background status polling must not refetch.
  // Auto-refresh updates only the listing and preserves selected Sheet/Tab,
  // current page and unsaved cell drafts.
  useEffect(() => {
    if (!status?.authenticated) {
      setAutoLoadingSheets(false)
      return
    }
    return loadPrivateSheetListOnce(
      () => api.privateDriveSheets(),
      (nextSheets) => { setSheets(nextSheets); setError('') },
      (err) => setError(err instanceof Error ? err.message : '無法自動載入試算表，可按重新整理重試'),
      setAutoLoadingSheets,
    )
  }, [status?.authenticated])

  useEffect(() => {
    copyGeneration.current++
    setCopyTotalRows(null)
    setSelection(null)
    setPreparedCopy(null)
    setCopyBusy(false)
    setCopyProgress('')
    setCopyNotice('')
    if (!selectedSheet || !selectedTab || !status?.authenticated) return
    let active = true
    void api.privateDriveCopyInfo(selectedSheet, selectedTab)
      .then((info) => { if (active) setCopyTotalRows(info.row_count) })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : '無法取得工作表總列數')
      })
    return () => { active = false; copyGeneration.current++ }
  }, [selectedSheet, selectedTab, status?.authenticated])

  useEffect(() => () => { copyGeneration.current++ }, [])

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
      copyGeneration.current++
      setSelection(null)
      setPreparedCopy(null)
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

  function selectCopyColumn(column: number) {
    copyGeneration.current++
    setSelection({ kind: 'column', column })
    setPreparedCopy(null)
    setCopyBusy(false)
    setCopyProgress('')
    setCopyNotice('')
  }

  function selectCopyCell(row: number, column: number, shift: boolean) {
    copyGeneration.current++
    setSelection((previous) => {
      if (shift && previous?.kind === 'range') {
        return { ...previous, endRow: row, endColumn: column }
      }
      if (shift && previous?.kind === 'column') {
        return { kind: 'range', anchorRow: data?.start_row ?? row,
          anchorColumn: previous.column, endRow: row, endColumn: column }
      }
      return { kind: 'range', anchorRow: row, anchorColumn: column,
        endRow: row, endColumn: column }
    })
    setPreparedCopy(null)
    setCopyBusy(false)
    setCopyProgress('')
    setCopyNotice('')
  }

  async function writeCopyToClipboard(text: string): Promise<void> {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text)
        return
      } catch {
        // Windows WebView2 may restrict the async API after network access.
      }
    }
    const field = document.createElement('textarea')
    field.value = text
    field.readOnly = true
    field.setAttribute('aria-hidden', 'true')
    field.style.position = 'fixed'
    field.style.opacity = '0'
    document.body.appendChild(field)
    try {
      field.focus()
      field.select()
      if (!document.execCommand('copy')) {
        throw new Error('Windows 剪貼簿拒絕存取，請按「再次複製」重試')
      }
    } finally { field.remove() }
  }

  async function copySelectedRange() {
    if (!selection || !selectedSheet || !selectedTab || copyBusy || copyTotalRows === null) return
    const job = ++copyGeneration.current
    setCopyBusy(true)
    setCopyNotice('')
    setPreparedCopy(null)
    try {
      const bounds = boundsFor(selection, copyTotalRows, includeHeader)
      const width = bounds.endColumn - bounds.startColumn + 1
      const totalRows = Math.max(0, bounds.endRow - bounds.startRow + 1)
      if (totalRows === 0) throw new Error('此欄沒有可複製的資料列')
      const allRows = await loadCopyRows(
        bounds,
        async (startRow, endRow) => {
          const chunk = await api.privateDriveCopyChunk(
            selectedSheet, selectedTab, startRow, endRow,
            bounds.startColumn, bounds.endColumn,
          )
          return chunk.rows
        },
        () => job !== copyGeneration.current,
        (loaded, total) => setCopyProgress('已讀取 ' + loaded + '／' + total + ' 列'),
      )
      const rows = selection.kind === 'column' ? trimTrailingBlankRows(allRows) : allRows
      if (rows.length === 0) throw new Error('選取範圍沒有資料')
      const content = tsvFromRows(rows)
      if (content.length > 6_000_000) throw new Error('複製內容太大，請縮小選取範圍')
      const last = bounds.startRow + rows.length - 1
      const label = boundsLabel({ ...bounds, endRow: last })
      const prepared = { text: content, label, rows: rows.length, columns: width }
      if (job !== copyGeneration.current) throw new Error('複製已取消')
      setPreparedCopy(prepared)
      try {
        await writeCopyToClipboard(content)
        if (job === copyGeneration.current) {
          setCopyNotice('已複製 ' + rows.length + ' 列／' + width + ' 欄（' + label + '）')
        }
      } catch {
        setCopyNotice('資料已完整讀取，但 Windows 剪貼簿拒絕存取，請按「再次複製」。')
      }
    } catch (err) {
      if (job === copyGeneration.current) {
        setCopyNotice(err instanceof Error ? err.message : '複製失敗，沒有寫入剪貼簿')
      }
    } finally {
      if (job === copyGeneration.current) {
        setCopyBusy(false)
        setCopyProgress('')
      }
    }
  }

  async function retryPreparedCopy() {
    if (!preparedCopy) return
    try {
      await writeCopyToClipboard(preparedCopy.text)
      setCopyNotice('已複製 ' + preparedCopy.rows + ' 列／' +
        preparedCopy.columns + ' 欄（' + preparedCopy.label + '）')
    } catch {
      setCopyNotice('剪貼簿仍無法寫入，請檢查 Windows 剪貼簿權限後再試。')
    }
  }

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'c' ||
        !selection || draft || saveConfirm || !status?.authenticated) return
      const target = event.target
      if (target instanceof HTMLElement &&
        target.closest('input,textarea,select,[contenteditable="true"]')) return
      event.preventDefault()
      if (preparedCopy) void retryPreparedCopy()
      else void copySelectedRange()
    }
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  })

  function selectCell(row: number, column: number, expected: string) {
    if (mode !== 'edit' || busy || !discardAllowed()) return
    setDraft({ row, column, expected, value: expected })
    setSaveConfirm(false)
  }

  async function openInGoogleSheets() {
    if (busy || openBrowserBusy || !selectedSheet || !discardAllowed()) return
    const tabId = tabs.find((tab) => tab.title === selectedTab)?.id ?? null
    setOpenBrowserBusy(true)
    setError('')
    try {
      await api.openPrivateSheetInBrowser(selectedSheet, tabId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法開啟 Google 試算表')
    } finally { setOpenBrowserBusy(false) }
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
            <button type="button" disabled={busy || autoLoadingSheets}
              onClick={() => void loadSheets()}>重新整理試算表清單</button>
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
            <p className="help-text">登入後會自動取得指定私人資料夾的試算表清單；切回此頁也會自動刷新，無需按重新整理。</p>
            {autoLoadingSheets && <p role="status">正在自動載入 Google 試算表清單…</p>}
            <label className="public-sheet-selector">選擇試算表（{sheets.length} 份）
              <select value={selectedSheet} disabled={busy || autoLoadingSheets && sheets.length === 0}
                onChange={(event) => void chooseSheet(event.target.value)}>
                <option value="">請選擇</option>
                {sheets.map((sheet) => <option key={sheet.id} value={sheet.id}>{sheet.name}</option>)}
              </select>
            </label>
            {!!selectedSheet && (
              <div className="private-sheets-native-actions">
                <button type="button" className="primary-button" onClick={() => void openInGoogleSheets()}
                  disabled={busy || openBrowserBusy}>
                  {openBrowserBusy ? '開啟中…' : '使用 Google 試算表開啟'}
                </button>
                <span>在系統瀏覽器以原生 Google Sheets 編輯；不需要公開檔案。</span>
              </div>
            )}
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
              <div className="private-sheet-copy-tools">
                <div className="private-sheet-copy-head">
                  <strong>整欄複製／多格選取</strong>
                  <span>點 A～AD 欄標頭選整欄，點格子再 Shift＋點選範圍，按 Ctrl+C 複製。</span>
                </div>
                <div className="private-sheet-copy-actions">
                  <label className="private-sheet-copy-check">
                    <input type="checkbox" checked={includeHeader}
                      onChange={(event) => { setIncludeHeader(event.target.checked); setPreparedCopy(null); setCopyNotice('') }} />
                    整欄複製包含第 1 列標題
                  </label>
                  <button type="button" disabled={!selection || !copyTotalRows || copyBusy}
                    onClick={() => void copySelectedRange()}>複製所選範圍</button>
                  {preparedCopy && (
                    <button type="button" disabled={copyBusy} onClick={() => void retryPreparedCopy()}>
                      再次複製
                    </button>
                  )}
                  {copyBusy && <button type="button" onClick={() => {
                    copyGeneration.current++
                    setCopyBusy(false)
                    setCopyProgress('')
                    setPreparedCopy(null)
                    setCopyNotice('已取消複製，未寫入剪貼簿')
                  }}>取消複製</button>}
                </div>
                <p className="help-text" role="status">
                  {selection
                    ? (selection.kind === 'column'
                      ? columnName(selection.column) + ' 欄，最多 ' + (copyTotalRows ?? '計算中') + ' 列'
                      : columnName(Math.min(selection.anchorColumn, selection.endColumn)) +
                        Math.min(selection.anchorRow, selection.endRow) + ':' +
                        columnName(Math.max(selection.anchorColumn, selection.endColumn)) +
                        Math.max(selection.anchorRow, selection.endRow))
                    : '請點選欄標頭或儲存格。'}
                  {copyProgress && ' · ' + copyProgress}
                </p>
                {copyNotice && <p role="status" className="private-sheet-copy-result">{copyNotice}</p>}
              </div>
            )}
            {data && (
              <div className="private-sheet-table-wrap">
                <table className="private-sheet-table">
                  <thead>
                    <tr>
                      <th scope="col">列</th>
                      {Array.from({ length: 30 }, (_, column) => (
                        <th scope="col" key={column + 1}
                          className={selection?.kind === 'column' && selection.column === column + 1 ? 'private-copy-selected' : ''}>
                          <button type="button" className="private-copy-column"
                            aria-label={'選取整個 ' + columnName(column + 1) + ' 欄'}
                            aria-pressed={selection?.kind === 'column' && selection.column === column + 1}
                            onClick={() => selectCopyColumn(column + 1)}>{columnName(column + 1)}</button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(data.rows.length ? data.rows : mode === 'edit' ? [[]] : []).map((row, idx) => (
                      <tr key={idx}>
                        <th scope="row">{data.start_row + idx}</th>
                        {Array.from({ length: 30 }, (_, column) => {
                          const value = row[column] ?? ''
                          const rowIndex = data.start_row + idx
                          const selected = inSelection(selection, rowIndex, column + 1)
                          return <td key={column} className={selected ? 'private-copy-selected' : ''}>
                            <button type="button" className={
                              'private-sheet-cell-edit private-sheet-copy-cell'
                            } disabled={busy}
                              title={mode === 'edit'
                                ? '點擊編輯；按 Ctrl 或 Shift 點擊選取複製範圍'
                                : '點擊選取儲存格；按 Shift 點擊選取範圍'}
                              aria-label={columnName(column + 1) + rowIndex + ': ' + (value || '空白')}
                              aria-pressed={selected}
                              onClick={(event) => {
                                if (mode === 'edit' && !event.shiftKey && !event.ctrlKey) {
                                  selectCell(rowIndex, column + 1, value)
                                } else {
                                  selectCopyCell(rowIndex, column + 1, event.shiftKey)
                                }
                              }}>{value || '　'}</button>
                          </td>
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {data.rows.length === 0 && <p className="help-text">這個範圍沒有資料。</p>}
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
        {mode === 'edit' && draft && !saveConfirm && (
          <div className="preview-backdrop private-editor-backdrop"
            onMouseDown={() => { if (!busy && discardAllowed()) setDraft(null) }}>
            <section className="prompt-dialog private-editor-dialog" role="dialog"
              aria-modal="true" aria-label="編輯 Google 試算表儲存格"
              onMouseDown={(event) => event.stopPropagation()}>
              <div className="prompt-header">編輯儲存格：第 {draft.row} 列，第 {draft.column} 欄</div>
              <div className="prompt-body private-editor-body">
                <p>工作表：<b>{selectedTab}</b></p>
                <p className="private-cell-original">原值：{draft.expected || '（空白）'}</p>
                <label htmlFor="private-cell-draft-input">新儲存格內容</label>
                <textarea id="private-cell-draft-input" autoFocus rows={5} maxLength={2000}
                  value={draft.value} disabled={busy}
                  onChange={(event) => setDraft({ ...draft, value: event.target.value })}/>
                <p className="help-text">採用 RAW 文字模式，等號開頭內容不會作為公式執行。修改後請確認儲存。</p>
              </div>
              <div className="prompt-footer">
                <button type="button" disabled={busy}
                  onClick={() => { if (discardAllowed()) setDraft(null) }}>取消</button>
                <button type="button" className="primary-button"
                  disabled={busy || draft.value === draft.expected}
                  onClick={() => setSaveConfirm(true)}>儲存變更…</button>
              </div>
            </section>
          </div>
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

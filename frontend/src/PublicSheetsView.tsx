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
    if (!status?.authenticated) {
      setSheets([])
      setTabs([])
      setSelectedSheet('')
      setSelectedTab('')
      setData(null)
    }
  }, [status?.authenticated])

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
    if (busy) return
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
    if (busy) return
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
    if (!sheet || !tab || busy) return
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
          <span>Google Drive 私人資料夾 · 唯讀</span>
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
            <strong>Google 已授權 · 私人唯讀模式</strong>
            <button type="button" disabled={busy} onClick={() => void loadSheets()}>重新整理試算表清單</button>
            <button type="button" disabled={busy} onClick={() => void logout()}>登出 Google</button>
          </>}
        </div>
        {status?.authenticated && (
          <>
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
                    {data.rows.map((row, idx) => (
                      <tr key={idx}>
                        <th scope="row">{data.start_row + idx}</th>
                        {row.map((value, column) => <td key={column}>{value}</td>)}
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
        <p className="help-text">Google 測試版 OAuth 授權可能需定期重新登入；若出現未驗證應用程式警告，請確認你在 Google Cloud 測試使用者名單，並只授權自己建立的 FireLens。</p>
      </section>
    </section>
  )
}

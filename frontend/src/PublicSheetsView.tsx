import { useState } from 'react'
import { api } from './api'
import { extractSheetId, PUBLIC_FOLDER_EMBED, PUBLIC_FOLDER_URL, sheetEmbedUrl, sheetUrl } from './publicSheets'
import type { PublicSheetListing } from './types'

export function PublicSheetsView() {
  const [sheetListing, setSheetListing] = useState<PublicSheetListing | null>(null)
  const [sheetLoading, setSheetLoading] = useState(false)
  const [sheetError, setSheetError] = useState('')
  const [sheetUrlDraft, setSheetUrlDraft] = useState('')
  const [selectedSheet, setSelectedSheet] = useState<{ id: string, name: string } | null>(null)
  const [showPublicFolder, setShowPublicFolder] = useState(false)

  async function loadPublicSheets() {
    setSheetLoading(true)
    setSheetError('')
    try {
      const listing = await api.publicSheets()
      setSheetListing(listing)
    } catch (err) {
      setSheetError(err instanceof Error ? err.message : '無法讀取公開試算表清單')
    } finally { setSheetLoading(false) }
  }

  function useSheetLink() {
    const id = extractSheetId(sheetUrlDraft)
    if (!id) {
      setSheetError('請貼上有效的 Google 試算表連結，格式為 https://docs.google.com/spreadsheets/d/...')
      return
    }
    setSheetError('')
    setSelectedSheet({ id, name: '手動指定的 Google 試算表' })
    setShowPublicFolder(false)
  }

  return (
    <section className="settings-page" aria-label="查看滅火器資料">
      <section className="panel-card settings-card public-sheets-card">
        <div className="panel-title">
          <h2>查看滅火器更換資料</h2><span>Google Drive 公開試算表（唯讀）</span>
        </div>
        <p className="help-text">不需登入 Google 帳號；公開資料夾可直接查看。自動列出試算表需要在本機設定 Google Drive API Key，分享網址本身不等於 API 授權。</p>
        <div className="public-sheet-actions">
          <button type="button" className="secondary-button" disabled={sheetLoading}
            onClick={() => void loadPublicSheets()}>{sheetLoading ? '查詢中…' : '重新整理試算表清單'}</button>
          <button type="button" className="secondary-button"
            onClick={() => { setShowPublicFolder(true); setSelectedSheet(null) }}>瀏覽公開資料夾</button>
          <a href={PUBLIC_FOLDER_URL} target="_blank" rel="noopener noreferrer">在瀏覽器開啟 Google Drive</a>
        </div>
        {sheetError && <p role="alert" className="error-banner">{sheetError}</p>}
        {sheetListing && !sheetListing.configured && (
          <div className="warning-banner" role="status">
            {sheetListing.message}
            <span>Windows 可設定環境變數 <code>FIRELENS_DRIVE_API_KEY</code> 後重新啟動 FireLens，以開啟自動清單功能。</span>
          </div>
        )}
        {sheetListing?.configured && (
          <label className="public-sheet-selector">選擇雲端試算表（{sheetListing.sheets.length} 份）
            <select value={selectedSheet?.id ?? ''}
              onChange={(event) => {
                const found = sheetListing.sheets.find((entry) => entry.id === event.target.value)
                setSelectedSheet(found ? { id: found.id, name: found.name } : null)
                setShowPublicFolder(false)
              }}>
              <option value="">請選擇試算表</option>
              {sheetListing.sheets.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
            </select>
            {sheetListing.truncated && <span>資料夾項目較多，清單只顯示前 500 筆掃描範圍。</span>}
            {sheetListing.sheets.length === 0 && <span>資料夾中沒有可公開讀取的 Google 試算表。</span>}
          </label>
        )}
        <div className="public-sheet-link-input">
          <label>或直接貼上 Google 試算表網址
            <input type="url" value={sheetUrlDraft} onChange={(event) => setSheetUrlDraft(event.target.value)}
              placeholder="https://docs.google.com/spreadsheets/d/..." />
          </label>
          <button type="button" onClick={useSheetLink} disabled={!sheetUrlDraft.trim()}>查看試算表</button>
        </div>
        {selectedSheet && sheetUrl(selectedSheet.id) && (
          <div className="public-sheet-preview">
            <div className="public-sheet-preview-title">
              <b>{selectedSheet.name}</b>
              <a href={sheetUrl(selectedSheet.id)!} target="_blank" rel="noopener noreferrer">在瀏覽器開啟試算表</a>
            </div>
            <iframe title={'Google 試算表：' + selectedSheet.name} src={sheetEmbedUrl(selectedSheet.id)!}
              referrerPolicy="no-referrer" loading="lazy" allowFullScreen />
            <p className="help-text">若 Google 拒絕內嵌、顯示登入畫面或空白，請點「在瀏覽器開啟試算表」。</p>
          </div>
        )}
        {showPublicFolder && (
          <div className="public-sheet-preview">
            <b>Google Drive 公開資料夾</b>
            <iframe title="滅火器更換資料公開資料夾" src={PUBLIC_FOLDER_EMBED}
              referrerPolicy="no-referrer" loading="lazy" />
            <p className="help-text">此畫面是 Google 提供的資料夾嵌入檢視；若瀏覽器阻擋，請使用上方連結開啟。</p>
          </div>
        )}
      </section>

    </section>
  )
}

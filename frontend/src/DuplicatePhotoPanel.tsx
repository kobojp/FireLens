import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { InspectorImageViewer } from './InspectorImageViewer'
import type {
  CategoryDefinition, DuplicateGallery, DuplicateJob, RootRecord,
} from './types'

type Props = {
  rootId: number | null
  roots: RootRecord[]
  onOpenItem: (rootId: number, itemId: number) => void
  isActive?: boolean
  guideTicket?: number | null
  onGuideFinish?: () => void
  onGuideCancel?: () => void
}

export function DuplicatePhotoPanel({
  rootId, roots, onOpenItem, isActive = true, guideTicket, onGuideFinish, onGuideCancel,
}: Props) {
  const [categories, setCategories] = useState<CategoryDefinition[]>([])
  const [category, setCategory] = useState('')
  const [query, setQuery] = useState('')
  const [full, setFull] = useState(false)
  const [offset, setOffset] = useState(0)
  const [gallery, setGallery] = useState<DuplicateGallery | null>(null)
  const [job, setJob] = useState<DuplicateJob | null>(null)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<number | null>(null)
  const [guideStarted, setGuideStarted] = useState(false)
  const scanButtonRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (guideTicket == null) return
    setGuideStarted(false)
    setFull(false)
    scanButtonRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [guideTicket])
  const [exporting, setExporting] = useState<'csv' | 'xlsx' | null>(null)
  const [saved, setSaved] = useState<{
    filename: string; path: string; open_token: string
  } | null>(null)
  const [exportMessage, setExportMessage] = useState('')
  useEffect(() => { setPreview(null) }, [rootId, category, query, offset])

  useEffect(() => { if (!isActive) setPreview(null) }, [isActive])

  const params = useMemo(() => new URLSearchParams({
    category, query, limit: '20', offset: String(offset),
  }), [category, query, offset])

  useEffect(() => {
    void api.categories().then(setCategories).catch(() => undefined)
  }, [])

  const refresh = useCallback(async () => {
    if (rootId === null) return
    try {
      setGallery(await api.duplicateGallery(rootId, params))
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法讀取重複清單')
    }
  }, [rootId, params])

  useEffect(() => {
    let alive = true
    if (rootId === null) return
    void api.duplicateGallery(rootId, params).then(value => {
      if (alive) setGallery(value)
    }).catch(err => { if (alive) setError(String(err)) })
    void api.duplicateScanStatus(rootId).then(value => {
      if (alive) setJob(value)
    }).catch(() => undefined)
    return () => { alive = false }
  }, [rootId, params])

  useEffect(() => {
    if (rootId === null || job?.state !== 'running') return
    const poll = window.setInterval(() => {
      void api.duplicateScanStatus(rootId).then(value => {
        setJob(value)
        if (value.state !== 'running') void refresh()
      }).catch(err => setError(String(err)))
    }, 800)
    return () => window.clearInterval(poll)
  }, [rootId, job?.state, refresh])

  async function startScan() {
    if (rootId === null) return
    if (full && !window.confirm('完整模式會重新讀取所有安全本機圖片並計算 SHA-256，確定開始？')) return
    setError('')
    try {
      setJob(await api.duplicateScan(rootId, full))
      if (guideTicket != null) setGuideStarted(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '重複掃描無法開始')
    }
  }

  async function browserDownload(format: 'csv' | 'xlsx') {
    if (rootId === null) return
    const params = new URLSearchParams({ fmt: format, category, query })
    const response = await fetch(`/api/duplicates/${rootId}/export?${params}`)
    if (!response.ok) throw new Error('下載失敗：HTTP ' + response.status)
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = `FireLens-duplicates.${format}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 10000)
  }

  async function exportResults(format: 'csv' | 'xlsx') {
    if (rootId === null || exporting) return
    setExporting(format)
    setSaved(null)
    setExportMessage('')
    try {
      if ('pywebview' in window) {
        const output = await api.duplicateSaveExport(rootId, format, category, query)
        setSaved(output)
        setExportMessage('匯出成功：' + output.filename)
      } else {
        await browserDownload(format)
        setExportMessage('已送出下載：FireLens-duplicates.' + format)
      }
    } catch (err) {
      setExportMessage('匯出失敗：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setExporting(null)
    }
  }

  const root = roots.find(r => r.id === rootId)
  const percent = job?.state === 'running' && job.total > 0
    ? Math.round(job.done / job.total * 100)
    : job?.state === 'completed' ? 100 : null

  const images = (gallery?.groups ?? []).flatMap(group => group.photos.map(photo => ({
    id: photo.photo_id, filename: photo.filename,
    title: `${photo.category} · ${photo.code} · ${photo.filename}`,
    subtitle: `${photo.year}／${photo.period} · ${photo.building} · ${photo.slot || '未對應'}`,
    path: photo.relative_path,
    src: `/api/photos/${photo.photo_id}/content?v=${photo.mtime_ns}`,
  })))
  const visiblePreviewId = isActive && images.some(image => image.id === preview) ? preview : null

  const guideComplete = guideTicket != null && guideStarted && job?.state === 'completed'
  const guideRunning = guideTicket != null && guideStarted && job?.state === 'running'

  return (
    <section className="duplicates-panel" aria-label="跨設備重複圖片檢查">
      <p className="help-text">同一照片根目錄跨設備、跨月份與類別，以 SHA-256 比對內容完全相同的圖片。檢查不會修改或刪除原始照片，Google Drive 未下載照片會略過。</p>
      {guideTicket != null && (
        <aside className="scan-guide-banner" role="status" aria-live="polite" aria-label="重複掃描操作引導">
          <div className="scan-guide-heading">
            <strong>🧭 任務引導：建立重複照片索引</strong>
            <button type="button" onClick={onGuideCancel}>關閉引導</button>
          </div>
          <ol>
            <li className="scan-guide-completed">第 1 步：已進入「照片品質檢查 → 重複圖片」</li>
            <li className={guideStarted ? 'scan-guide-completed' : 'scan-guide-current'}>
              第 2 步：{guideStarted ? '已按下開始掃描' : '請按下面發光框的「開始重複掃描」按鈕（增量模式）'}
            </li>
            <li className={guideComplete ? 'scan-guide-completed' : guideRunning ? 'scan-guide-current' : ''}>
              第 3 步：{guideComplete ? '掃描完成，可以返回照片牆重新嘗試貼上' :
                guideRunning ? '掃描進行中，請等待完成，勿關閉程式' : '掃描完成後再返回照片牆'}
            </li>
          </ol>
          {guideComplete && <button type="button" className="scan-guide-finish"
            onClick={onGuideFinish}>完成任務，返回照片牆重新貼上 →</button>}
          {guideStarted && ['failed', 'cancelled', 'error'].includes(job?.state ?? '') && (
            <p className="quality-flag">掃描未完成：請查看下方錯誤／取消原因，重新按「開始重複掃描」。</p>
          )}
          <p className="help-text">未完成掃描前，原本的照片不會被偷偷儲存，也不會自動下載雲端佔位檔。</p>
        </aside>
      )}
      <div className="quality-toolbar">
        <label>設備類別
          <select value={category} onChange={e => { setCategory(e.target.value); setOffset(0) }}>
            <option value="">所有類別</option>
            {categories.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
        </label>
        <label>設備編號搜尋
          <input value={query} placeholder="例如：三-07-25" onChange={e => {
            setQuery(e.target.value); setOffset(0)
          }} />
        </label>
        <label>掃描模式
          <select value={full ? 'full' : 'incremental'} disabled={job?.state === 'running'}
            onChange={e => setFull(e.target.value === 'full')}>
            <option value="incremental">增量掃描（預設）</option>
            <option value="full">完整重新掃描</option>
          </select>
        </label>
        <button type="button" ref={scanButtonRef}
          className={guideTicket != null && !guideStarted ? 'scan-guide-target' : undefined}
          onClick={() => void startScan()}
          disabled={rootId === null || job?.state === 'running'}>開始重複掃描</button>
        <button type="button" disabled={job?.state !== 'running' || rootId === null}
          onClick={() => { if (rootId !== null) void api.duplicateCancel(rootId).then(setJob) }}>
          取消掃描
        </button>
        <button type="button" onClick={() => void refresh()}>重新整理清單</button>
        <div className="quality-export-actions" role="group" aria-label="匯出重複圖片清單">
          <button type="button" className="quality-action quality-action-csv"
            disabled={rootId === null || Boolean(exporting)} onClick={() => void exportResults('csv')}>
            {exporting === 'csv' ? 'CSV 匯出中…' : '匯出 CSV'}
          </button>
          <button type="button" className="quality-action quality-action-excel"
            disabled={rootId === null || Boolean(exporting)} onClick={() => void exportResults('xlsx')}>
            {exporting === 'xlsx' ? 'Excel 匯出中…' : '匯出 Excel'}
          </button>
        </div>
      </div>
      {job && job.state !== 'idle' && (
        <div className="quality-progress" role="status" aria-live="polite">
          <div className="quality-progress-heading">
            <strong>{job.state === 'running'
              ? job.phase === 'indexing' ? '更新照片索引…' : '正在比對 SHA-256…'
              : job.state === 'completed' ? '重複檢查完成'
                : job.state === 'cancelled' ? '已取消掃描' : '掃描失敗'}</strong>
            <strong>{percent === null ? '處理中' : `${percent}%`}</strong>
          </div>
          <div className="quality-progress-track" role="progressbar" aria-label="重複照片掃描進度"
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined}>
            <div style={{ width: `${percent ?? 0}%` }} />
          </div>
          <div className="quality-progress-details">
            <span>完成 <b>{job.done}</b>／{job.total} 張</span>
            <span>新計算 {job.analyzed} · 沿用 {job.cached} · 未檢查 {job.skipped}</span>
          </div>
          {job.error && <p className="quality-flag">{job.error}</p>}
        </div>
      )}
      {error && <p role="alert" className="error-banner">{error}</p>}
      {exportMessage && (
        <div className="quality-export-result" role="status">
          <strong>{exportMessage}</strong>
          {saved && <div className="quality-export-open">
            <span>{saved.path}</span>
            <button type="button" onClick={() => void api.openExport(saved.open_token, 'file').catch(e => setError(String(e)))}>開啟檔案</button>
            <button type="button" onClick={() => void api.openExport(saved.open_token, 'folder').catch(e => setError(String(e)))}>開啟所在資料夾</button>
          </div>}
        </div>
      )}
      <div className="quality-stats" aria-label="重複照片統計">
        <div><span>重複群組</span><strong>{gallery?.total ?? 0} <small>組</small></strong></div>
        <div><span>涉及設備</span><strong>{gallery?.total_devices ?? 0} <small>台</small></strong></div>
        <div><span>重複照片</span><strong>{gallery?.total_photos ?? 0} <small>張</small></strong></div>
      </div>
      {!!(gallery?.pending || gallery?.skipped) && (
        <p className="quality-flag" role="status">
          此來源仍有 {gallery.pending} 張待建立／更新指紋、{gallery.skipped} 張雲端未下載或無法安全讀取；結果不代表這些照片沒有重複。請執行手動重複掃描。
        </p>
      )}
      <p className="help-text">目前來源：{root?.label ?? '尚未選擇'}；每一組可檢查所有來源照片。完全相同不代表一定放錯，請人工判斷。</p>
      <div className="duplicates-group-list">
        {(gallery?.groups ?? []).map((group, index) => (
          <article className="quality-card" key={group.sha256}>
            <header>
              <strong>重複群組 #{offset + index + 1}</strong>
              <span>{group.count} 張照片 · {group.device_count} 台設備</span>
              <small>SHA-256：{group.sha256.slice(0, 24)}…</small>
            </header>
            <div className="duplicates-photo-grid">
              {group.photos.map(photo => (
                <div className="duplicates-photo" key={photo.photo_id}>
                  <button type="button" className="duplicates-image-button"
                    onClick={() => setPreview(photo.photo_id)} title={'放大 ' + photo.filename}>
                    <img loading="lazy" alt={photo.filename}
                      src={`/api/photos/${photo.photo_id}/thumbnail?v=${photo.mtime_ns}`} />
                  </button>
                  <strong>{photo.category} · {photo.code}</strong>
                  <small>{photo.year}／{photo.period} · {photo.building}</small>
                  <small>{photo.slot || '未對應'}／{photo.filename}</small>
                  <small title={photo.relative_path}>{photo.relative_path}</small>
                  <button type="button" onClick={() => {
                    if (rootId !== null) onOpenItem(rootId, photo.item_id)
                  }}>前往照片牆</button>
                </div>
              ))}
            </div>
          </article>
        ))}
        {!gallery?.groups.length && (
          <p className="help-text">目前沒有已確認的重複群組。若尚未掃描或存在待檢查照片，不代表全部沒有重複。</p>
        )}
      </div>
      <div className="quality-pagination">
        <button type="button" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>上一頁</button>
        <span>{gallery?.total ? offset + 1 : 0}–{Math.min(offset + 20, gallery?.total ?? 0)}／{gallery?.total ?? 0}</span>
        <button type="button" disabled={offset + 20 >= (gallery?.total ?? 0)}
          onClick={() => setOffset(offset + 20)}>下一頁</button>
      </div>
      <InspectorImageViewer images={images} activeId={visiblePreviewId}
        onSelect={setPreview} onClose={() => setPreview(null)} />
    </section>
  )
}

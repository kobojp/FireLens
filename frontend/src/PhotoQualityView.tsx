import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { qualityProgress } from './qualityProgress'
import { DuplicatePhotoPanel } from './DuplicatePhotoPanel'
import { InspectorImageViewer } from './InspectorImageViewer'
import { api } from './api'
import { qualityPeriodsFromTree } from './qualityPeriods'
import { useAppConfirmation } from './useAppConfirmation'
import type { QualityGallery, QualityItem, QualityJob, QualityPhoto, RootRecord, TreeNode } from './types'
const CATEGORY = [
  { value: '', label: '全部設備' },
  { value: 'extinguisher', label: '滅火器' },
  { value: 'box', label: '放置盒' },
  { value: 'lamp', label: '燈具' },
]

const STATUS: Record<string, string> = {
  high: '高度疑似模糊',
  possible: '疑似品質不良',
  uncertain: '無法判定',
  normal: '正常',
  unscanned: '尚未檢查',
}

export function PhotoQualityView({
  roots, defaultRootId, onOpenItem, isActive = true, guideTicket, guidedRootId, onGuideFinish, onGuideCancel,
}: {
  roots: RootRecord[]
  defaultRootId: number | null
  onOpenItem: (rootId: number, itemId: number) => void
  isActive?: boolean
  guideTicket?: number | null
  guidedRootId?: number | null
  onGuideFinish?: () => void
  onGuideCancel?: () => void
}) {
  const [rootId, setRootId] = useState<number | null>(defaultRootId)
  const [mode, setMode] = useState<'quality' | 'duplicates'>('quality')
  const [category, setCategory] = useState('')
  const [period, setPeriod] = useState('')
  const [periodTree, setPeriodTree] = useState<{ rootId: number; nodes: TreeNode[] } | null>(null)
  const [periodTreeLoading, setPeriodTreeLoading] = useState(false)
  const [periodTreeError, setPeriodTreeError] = useState('')
  const [building, setBuilding] = useState('')
  const [query, setQuery] = useState('')
  const [problemOnly, setProblemOnly] = useState(true)
  const [full, setFull] = useState(false)
  const { confirmAction, cancelConfirmation, confirmationDialog } = useAppConfirmation()
  useEffect(() => cancelConfirmation(), [rootId, mode, cancelConfirmation])
  const [offset, setOffset] = useState(0)
  const [gallery, setGallery] = useState<QualityGallery | null>(null)
  const [job, setJob] = useState<QualityJob | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [savingSensitivity, setSavingSensitivity] = useState(false)
  const [startingScan, setStartingScan] = useState(false)
  const [cancellingScan, setCancellingScan] = useState(false)
  const [manualRefreshing, setManualRefreshing] = useState(false)
  const actionLocks = useRef({ save: false, start: false, cancel: false, refresh: false })
  const [busyPhotoId, setBusyPhotoId] = useState<number | null>(null)
  const [preview, setPreview] = useState<number | null>(null)
  const [thumbSize, setThumbSize] = useState(180)
  const [qualityFilter, setQualityFilter] = useState('')
  const [reviewFilter, setReviewFilter] = useState('')
  const [sortBy, setSortBy] = useState('latest')
  const [sensitivity, setSensitivity] = useState(1)
  const [savedSensitivity, setSavedSensitivity] = useState(1)
  const [exporting, setExporting] = useState<'csv' | 'xlsx' | null>(null)
  const [exportResult, setExportResult] = useState<{ filename: string; path: string; open_token: string } | null>(null)
  const [exportMessage, setExportMessage] = useState('')
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000)


  useEffect(() => {
    if (guideTicket == null || guidedRootId == null) return
    setRootId(guidedRootId)
    setMode('duplicates')
    setOffset(0)
  }, [guideTicket, guidedRootId])

  useEffect(() => {
    if (roots.length && !roots.some((r) => r.id === rootId)) {
      setRootId(roots[0].id)
    }
  }, [roots, rootId])

  useEffect(() => {
    if (rootId === null) return
    let active = true
    setPeriodTreeLoading(true)
    setPeriodTreeError('')
    void api.tree(rootId).then((nodes) => {
      if (!active) return
      setPeriodTree({ rootId, nodes })
      setPeriodTreeLoading(false)
    }).catch((err) => {
      if (!active) return
      setPeriodTreeError(err instanceof Error ? err.message : '無法載入月份／批次')
      setPeriodTreeLoading(false)
    })
    return () => { active = false }
  }, [rootId])

  const periodOptions = useMemo(() => periodTree?.rootId === rootId
    ? qualityPeriodsFromTree(periodTree.nodes, category) : [], [periodTree, rootId, category])
  const periodOptionsReady = periodTree?.rootId === rootId
  useEffect(() => {
    if (periodOptionsReady && period && !periodOptions.includes(period)) {
      setPeriod('')
      setOffset(0)
    }
  }, [periodOptionsReady, periodOptions, period])

  // A preview belongs only to its current root, mode and filtered page.
  useEffect(() => { setPreview(null) }, [rootId, mode, category, period, building, query,
    qualityFilter, reviewFilter, sortBy, problemOnly, offset])

  useEffect(() => { if (!isActive) setPreview(null) }, [isActive])

  const params = useMemo(() => new URLSearchParams({
    category, period, building, query, problem_only: String(problemOnly),
    status_filter: qualityFilter, review_filter: reviewFilter, sort_by: sortBy,
    offset: String(offset), limit: '40',
  }), [category, period, building, query, problemOnly, qualityFilter, reviewFilter, sortBy, offset])

  const refresh = useCallback(async () => {
    if (rootId === null) return
    setLoading(true)
    try {
      setGallery(await api.qualityGallery(rootId, params))
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取品質清單失敗')
    } finally {
      setLoading(false)
    }
  }, [rootId, params])

  useEffect(() => {
    let active = true
    if (rootId === null) return
    void api.qualitySettings(rootId).then((result) => {
      if (active) {
        setSensitivity(result.sensitivity)
        setSavedSensitivity(result.sensitivity)
      }
    }).catch(() => undefined)
    void api.qualityGallery(rootId, params).then((value) => {
      if (active) setGallery(value)
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : '載入失敗')
    })
    void api.qualityScanStatus(rootId).then((value) => {
      if (active) setJob(value)
    }).catch(() => undefined)
    return () => { active = false }
  }, [rootId, params])

  useEffect(() => {
    if (rootId === null || job?.state !== 'running') return
    const timer = window.setInterval(() => {
      void api.qualityScanStatus(rootId).then((result) => {
        setJob(result)
        if (result.state !== 'running') void refresh()
      }).catch((err) => setError(err instanceof Error ? err.message : '掃描狀態錯誤'))
    }, 800)
    return () => window.clearInterval(timer)
  }, [job?.state, rootId, refresh])

  useEffect(() => {
    if (job?.state !== 'running') return
    const timer = window.setInterval(() => setNowSeconds(Date.now() / 1000), 1000)
    return () => window.clearInterval(timer)
  }, [job?.state])

  async function saveSettings() {
    if (rootId === null || actionLocks.current.save || sensitivity === savedSensitivity || job?.state === 'running') return
    actionLocks.current.save = true
    setSavingSensitivity(true)
    setError('')
    try {
      const saved = await api.saveQualitySettings(rootId, sensitivity)
      setSavedSensitivity(saved.sensitivity)
      setOffset(0)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法儲存偵測靈敏度')
    } finally {
      actionLocks.current.save = false
      setSavingSensitivity(false)
    }
  }

  async function startScan() {
    if (rootId === null || actionLocks.current.start || sensitivity !== savedSensitivity || job?.state === 'running') return
    if (full && !(await confirmAction(
      '完整重新掃描會重新分析此範圍全部照片，確定開始？', '完整照片品質掃描',
    ))) return
    actionLocks.current.start = true
    setStartingScan(true)
    setError('')
    try {
      setJob(await api.qualityScan(rootId, full, category, period))
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法開始掃描')
    } finally {
      actionLocks.current.start = false
      setStartingScan(false)
    }
  }

  async function cancelScan() {
    if (rootId === null || job?.state !== 'running' || actionLocks.current.cancel) return
    actionLocks.current.cancel = true
    setCancellingScan(true)
    try { setJob(await api.cancelQualityScan(rootId)) }
    catch (err) { setError(err instanceof Error ? err.message : '取消掃描失敗') }
    finally { actionLocks.current.cancel = false; setCancellingScan(false) }
  }

  async function refreshList() {
    if (rootId === null || actionLocks.current.refresh) return
    actionLocks.current.refresh = true
    setManualRefreshing(true)
    try { await refresh() }
    finally { actionLocks.current.refresh = false; setManualRefreshing(false) }
  }

  async function saveReview(photo: QualityPhoto, value: string) {
    setBusyPhotoId(photo.id)
    try {
      await api.reviewQualityPhoto(photo.id, value)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '標記失敗')
    } finally {
      setBusyPhotoId(null)
    }
  }

  async function downloadInBrowser(format: 'csv' | 'xlsx'): Promise<void> {
    if (rootId === null) throw new Error('請先選擇照片來源')
    const params = new URLSearchParams({
      fmt: format, category, period, building, query,
      problem_only: String(problemOnly), status_filter: qualityFilter,
      review_filter: reviewFilter, sort_by: sortBy,
    })
    const response = await fetch(`/api/quality/${rootId}/export?${params}`)
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(typeof body?.detail === 'string' ? body.detail : `下載失敗：HTTP ${response.status}`)
    }
    const objectUrl = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = `FireLens-photo-quality.${format}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10000)
  }

  async function saveExport(format: 'csv' | 'xlsx') {
    if (rootId === null || exporting) return
    setExporting(format)
    setExportResult(null)
    setExportMessage('')
    try {
      if (!('pywebview' in window)) {
        await downloadInBrowser(format)
        setExportMessage(`已送出下載：FireLens-photo-quality.${format}`)
      } else {
        const saved = await api.saveQualityExport(rootId, {
          format, category, period, building, query, problem_only: problemOnly,
          status_filter: qualityFilter, review_filter: reviewFilter, sort_by: sortBy,
        })
        setExportResult(saved)
        setExportMessage(`匯出成功：${saved.filename}`)
      }
    } catch (err) {
      setExportMessage(`匯出失敗：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setExporting(null)
    }
  }

  const progress = job ? qualityProgress(job, nowSeconds) : null

  const filteredCards = gallery?.items ?? []
  // Photo order exactly follows the thumbnails shown in the current filtered page.
  const qualityImages = filteredCards.flatMap(item => item.slots.flatMap(slot =>
    item.photos.filter(photo => (photo.display_slot ?? photo.slot) === slot).map(photo => ({
      id: photo.id, filename: photo.filename, title: `${item.category} · ${item.code} · ${photo.filename}`,
      subtitle: `${item.year}／${item.period} · ${item.building} · ${slot} · ${photo.reason || '尚未掃描'} · 分數 ${photo.score ?? '—'}`,
      path: photo.relative_path, src: api.photoUrl(photo),
    })),
  ))
  const visiblePreviewId = isActive && qualityImages.some(image => image.id === preview) ? preview : null

  if (mode === 'duplicates') {
    return (
      <section className="panel quality-page">
        <div className="panel-title">
          <h2>照片品質檢查</h2>
          <span>跨設備完全相同圖片的手動偵測，保留原始檔案</span>
        </div>
        <div className="quality-mode-switch" role="group" aria-label="照片品質檢查功能">
          <button type="button" disabled={guideTicket != null}
            onClick={() => setMode('quality')}>圖片品質與缺槽位</button>
          <button type="button" aria-current="page" className="active">重複圖片</button>
        </div>
        <div className="quality-controls">
          <label>照片來源
            <select value={rootId ?? ''} disabled={guideTicket != null} onChange={e => {
              setRootId(Number(e.target.value)); setOffset(0)
            }}>
              {roots.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </label>
        </div>
        <DuplicatePhotoPanel roots={roots} rootId={rootId} onOpenItem={onOpenItem}
          isActive={isActive} guideTicket={guideTicket} onGuideFinish={onGuideFinish}
          onGuideCancel={onGuideCancel} />
      </section>
    )
  }

  return (
    <section className="panel quality-page">
      <div className="panel-title">
        {confirmationDialog}
        <h2>照片品質檢查</h2>
        <span>只分析圖片品質，不修改原圖，也不改設備異常紀錄</span>
      </div>
      <div className="quality-mode-switch" role="group" aria-label="照片品質檢查功能">
        <button type="button" aria-current="page" className="active">圖片品質與缺槽位</button>
        <button type="button" onClick={() => setMode('duplicates')}>重複圖片</button>
      </div>
      <div className="quality-controls">
        <label>照片來源
          <select value={rootId ?? ''} onChange={(e) => {
            setRootId(Number(e.target.value)); setPeriod(''); setOffset(0)
          }}>
            {roots.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
        </label>
        <label>設備類別
          <select value={category} onChange={(e) => { setCategory(e.target.value); setOffset(0) }}>
            {CATEGORY.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </label>
        <label>月份／批次
          <select value={period} disabled={periodTreeLoading || !periodOptionsReady}
            onChange={(e) => { setPeriod(e.target.value); setOffset(0) }}>
            <option value="">全部月份／批次</option>
            {periodOptions.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        {periodTreeError && <span className="quality-period-error" role="alert">月份／批次讀取失敗：{periodTreeError}（原有結果保留）</span>}
        <label>棟別
          <input value={building} onChange={(e) => { setBuilding(e.target.value); setOffset(0) }} placeholder="全部棟別" />
        </label>
        <label>設備編號
          <input value={query} onChange={(e) => { setQuery(e.target.value); setOffset(0) }} placeholder="搜尋設備編號" />
        </label>
        <label>縮圖大小
          <input type="range" min="110" max="320" value={thumbSize}
            onChange={(e) => setThumbSize(Number(e.target.value))} />
        </label>
      </div>
      <div className="quality-toolbar">
        <div className="quality-parameter-group" role="group" aria-label="掃描參數">
          <label>掃描方式
            <select value={full ? 'full' : 'incremental'}
              onChange={(e) => setFull(e.target.value === 'full')} disabled={job?.state === 'running'}>
              <option value="incremental">增量掃描（預設，只掃新照片／已變動）</option>
              <option value="full">完整重新掃描（重新分析全部）</option>
            </select>
          </label>
          <label>模糊偵測靈敏度（{sensitivity.toFixed(1)}）
            <input type="range" min="0.5" max="1.5" step="0.1" value={sensitivity}
              onChange={(e) => setSensitivity(Number(e.target.value))} />
          </label>
          <button type="button" className="quality-action quality-action-save"
            disabled={rootId === null || sensitivity === savedSensitivity || job?.state === 'running' || savingSensitivity}
            onClick={() => void saveSettings()}>{savingSensitivity ? '儲存中…' : '儲存靈敏度'}</button>
        </div>
        <div className="quality-operation-group" role="group" aria-label="掃描操作">
          <button type="button" className="quality-action quality-action-scan"
            disabled={rootId === null || sensitivity !== savedSensitivity || job?.state === 'running' || startingScan || savingSensitivity}
            onClick={() => void startScan()}>{startingScan || job?.state === 'running' ? '掃描中…' : '開始掃描'}</button>
          <button type="button" className="quality-action quality-action-cancel"
            disabled={job?.state !== 'running' || rootId === null || cancellingScan}
            onClick={() => void cancelScan()}>{cancellingScan ? '取消中…' : '取消掃描'}</button>
          <button type="button" className="quality-action quality-action-refresh"
            disabled={rootId === null || manualRefreshing || loading}
            onClick={() => void refreshList()}>{manualRefreshing ? '整理中…' : '重新整理清單'}</button>
        </div>
        <label><input type="checkbox" checked={problemOnly}
          onChange={(e) => { setProblemOnly(e.target.checked); setOffset(0) }} /> 只顯示異常設備</label>
        <label>品質
          <select value={qualityFilter} onChange={(e) => { setQualityFilter(e.target.value); setOffset(0) }}>
            <option value="">全部</option>
            <option value="missing">缺照片</option>
            <option value="unmapped">未辨識照片用途</option>
            <option value="dirty_name">檔名疑似錯誤</option>
            <option value="multi_slot">同槽多圖</option>
            <option value="variant_name">名稱異體字</option>
            <option value="special">特例資料夾</option>
            {Object.entries(STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <label>排序
          <select value={sortBy} onChange={(e) => { setSortBy(e.target.value); setOffset(0) }}>
            <option value="latest">年月批次</option>
            <option value="code">設備編號</option>
            <option value="severity">異常最多優先</option>
          </select>
        </label>
        <label>人工覆核
          <select value={reviewFilter}
            onChange={(e) => { setReviewFilter(e.target.value); setOffset(0) }}>
            <option value="">全部</option>
            <option value="pending">未覆核</option>
            <option value="confirmed">已確認問題</option>
            <option value="ignore">排除誤判</option>
            <option value="reshoot">待補拍</option>
            <option value="wrong_content">拍攝內容錯誤</option>
          </select>
        </label>
        <div className="quality-export-actions" role="group" aria-label="匯出品質清單">
          <button type="button" className="quality-action quality-action-csv" disabled={rootId === null || Boolean(exporting)}
            onClick={() => void saveExport('csv')}><span aria-hidden="true">↓</span> {exporting === 'csv' ? 'CSV 匯出中…' : '匯出 CSV'}</button>
          <button type="button" className="quality-action quality-action-excel" disabled={rootId === null || Boolean(exporting)}
            onClick={() => void saveExport('xlsx')}><span aria-hidden="true">↓</span> {exporting === 'xlsx' ? 'Excel 匯出中…' : '匯出 Excel'}</button>
        </div>
      </div>
      {job && job.state !== 'idle' && progress && (
        <section className="quality-progress" role="status" aria-live="polite">
          <div className="quality-progress-heading">
            <strong>{progress.phase}</strong>
            <strong className="quality-progress-percent">{progress.percent === null ? '處理中' : `${progress.percent}%`}</strong>
          </div>
          <div className="quality-progress-track" role="progressbar" aria-label="照片品質掃描進度"
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress.percent ?? undefined}
            aria-valuetext={progress.percent === null ? progress.phase : `${progress.percent}%`}>
            <div style={{ width: `${progress.percent ?? 0}%` }} />
          </div>
          <div className="quality-progress-details">
            <span>完成 <b>{job.done.toLocaleString()}</b> / {job.total.toLocaleString()} 張</span>
            <span>預估剩餘：<b>{progress.remaining}</b></span>
            <span>新分析 {job.analyzed} · 沿用 {job.cached} · 跳過 {job.skipped} · 疑似問題 {job.flagged}</span>
          </div>
          {job.error && <p className="quality-flag">{job.error}</p>}
        </section>
      )}
      {error && <p role="alert" className="error-banner">{error}</p>}
      {exportMessage && <div className={`quality-export-result${exportMessage.startsWith("匯出失敗") ? " quality-export-error" : ""}`} role="status">
        <strong>{exportMessage}</strong>
        {exportResult && <div className="quality-export-open">
          <span>{exportResult.path}</span>
          <button type="button" onClick={() => void api.openExport(exportResult.open_token, 'file').catch((err) => setError(String(err)))}>開啟檔案</button>
          <button type="button" onClick={() => void api.openExport(exportResult.open_token, 'folder').catch((err) => setError(String(err)))}>開啟所在資料夾</button>
        </div>}
      </div>}
      <div className="quality-stats" aria-label="照片品質檢查統計">
        <div><span>設備總數</span><strong>{(gallery?.total_devices ?? 0).toLocaleString()} <small>台</small></strong></div>
        <div><span>異常設備</span><strong>{(gallery?.total ?? 0).toLocaleString()} <small>台</small></strong></div>
        <div><span>問題線索</span><strong>{(gallery?.flagged_photos ?? 0).toLocaleString()} <small>項</small></strong></div>
      </div>
      <p className="help-text">{loading ? '讀取中… ' : ''}低紋理、暗光及模糊結果均需人工確認。</p>
      <div className="quality-gallery" style={{ '--quality-thumb': `${thumbSize}px` } as React.CSSProperties}>
        {filteredCards.map((item) => (
          <article key={item.id} className="quality-card">
            <header>
              <strong>{item.building} · {item.code}</strong>
              <span>{item.year}／{item.period} · {item.category}</span>
              <small>問題線索 {item.problems} 項 · 缺槽位 {item.missing_slots.length} 個</small>
              {item.special && <small>特例資料夾：依特例規則顯示，不判一般槽位缺照</small>}
              {item.name_variants?.map((variant, index) => <small key={index} className="quality-flag">{variant.type === "building" ? "棟別" : "設備編號"}異體字：{variant.value} → {variant.suggestion}（{variant.reason}）</small>)}
              {!!item.duplicate_slots?.length && <small className="quality-flag">同槽多圖：{item.duplicate_slots.join("、")}（請人工核對）</small>}
            </header>
            <div className="quality-slots">
              {item.slots.map((slot) => (
                <div key={slot} className="quality-slot">
                  <strong>{slot}</strong>
                  {item.missing_slots.includes(slot) && <p className="quality-flag">缺照片</p>}
                  {item.photos.filter((photo) => (photo.display_slot ?? photo.slot) === slot).map((photo) => (
                    <div key={photo.id} className="quality-photo">
                      <button type="button" onClick={() => setPreview(photo.id)} title={'放大 ' + photo.filename}>
                        <img loading="lazy" src={api.thumbnailUrl(photo)} alt={photo.filename} />
                      </button>
                      <small title={photo.filename}>{photo.filename}</small>
                      <small>更新：{new Date(photo.mtime_ns / 1_000_000).toLocaleDateString('zh-TW')}</small>
                      <span className={photo.status === 'high' ? 'quality-flag' : ''}>
                        {STATUS[photo.status] ?? '尚未檢查'}
                        {photo.review && ' · ' + photo.review}
                      </span>
                      {photo.filename_issue && <small className="quality-flag">未辨識照片用途</small>}
                      {photo.suggested_filename && <small className="quality-flag">檔名疑似錯誤：建議 {photo.suggested_filename}（{photo.filename_reason}）</small>}
                      {photo.multi_slot && <small className="quality-flag">同槽多圖，請核對是否重複或誤放</small>}
                      {photo.cloud_placeholder === 1 && <small>Google Drive 尚未下載，品質掃描已跳過</small>}
                      {photo.reason && <small>{photo.reason}</small>}
                      <select aria-label={photo.filename + ' 人工覆核'}
                        disabled={busyPhotoId === photo.id} value={photo.review || ''}
                        onChange={(e) => void saveReview(photo, e.target.value)}>
                        <option value="">尚未覆核</option>
                        <option value="confirmed">已確認問題</option>
                        <option value="ignore">排除誤判</option>
                        <option value="reshoot">待補拍</option>
                        <option value="wrong_content">拍攝內容錯誤</option>
                      </select>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <button type="button" className="quality-action quality-open-wall"
              onClick={() => { if (rootId !== null) onOpenItem(rootId, item.id) }}>前往照片牆 <span aria-hidden="true">→</span></button>
          </article>
        ))}
        {!filteredCards.length && <p>目前篩選範圍沒有符合的設備。</p>}
      </div>
      <div className="quality-pagination">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 40))}>上一頁</button>
        <span>{gallery?.total ? offset + 1 : 0}–{Math.min(offset + 40, gallery?.total ?? 0)}／{gallery?.total ?? 0}</span>
        <button type="button" disabled={offset + 40 >= (gallery?.total ?? 0)} onClick={() => setOffset(offset + 40)}>下一頁</button>
      </div>
      <InspectorImageViewer images={qualityImages} activeId={visiblePreviewId}
        onSelect={setPreview} onClose={() => setPreview(null)} />
    </section>
  )
}

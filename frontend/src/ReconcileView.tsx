import { ModalBackdrop } from './AppDialog'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { filterReconcileRows } from './reconcile'
import { createReconcileRequestGuard, DEVICE_CATEGORY_LABELS, isDeviceCategory, periodsForCategory } from './reconcileScope'
import type { DeviceCategory } from './reconcileScope'
import { LedgerManager } from './LedgerManager'
import { AppConfirmDialog } from './AppConfirmDialog'
import { isLedgerNameConflict, ledgerNameInUse } from './ledgerNameNotice'
import { LedgerPasteSheet, blankLedgerRows, serializeLedgerRows, filledLedgerCount } from './LedgerPasteSheet'
import type { LedgerPasteRow } from './LedgerPasteSheet'
import type {
  AliasRecord,
  LedgerImportPreview,
  LedgerRecord,
  AppSettings,
  ReconcileResult,
  RootRecord,
  TreeNode,
} from './types'

const STATUS_LABELS: Record<string, string> = {
  complete: '完整',
  missing_photo: '缺照片',
  no_folder: '無資料夾',
  empty_folder: '空資料夾',
  zero_byte: '0 byte',
  cloud_not_downloaded: '雲端未下載',
  invalid_naming: '命名異常',
  duplicate_number: '重複編號',
  near_number: '近似編號',
  legacy: '舊制／待確認（只顯示）',
  special: '特例',
}

const CATEGORY_LABELS: Record<string, string> = {
  extinguisher: '滅火器',
  box: '放置盒',
  lamp: '燈具',
}

const CLASSIFICATION_LABELS: Record<string, string> = {
  complete: '完整',
  partial_missing: '缺部分照片',
  no_photos: '完全無照片',
  no_folder: '找不到設備資料夾',
  unmapped_legacy: '有未對應／舊制照片',
}


function suggestedLedgerName(now = new Date()) {
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${now.getFullYear()}/${month} 滅火器清冊`
}

type PendingImport = {
  kind: 'text' | 'excel'
  preview: LedgerImportPreview
  file?: File
}

type Props = {
  roots: RootRecord[]
  defaultRootId: number | null
  isActive?: boolean
  settings?: AppSettings | null
}

export function ReconcileView({ roots, defaultRootId, isActive = true, settings }: Props) {
  const [rootId, setRootId] = useState<number | null>(defaultRootId)
  const [ledgers, setLedgers] = useState<LedgerRecord[]>([])
  const [ledgerId, setLedgerId] = useState<number | null>(null)
  const [period, setPeriod] = useState('')
  const [categoryCode, setCategoryCode] = useState<DeviceCategory>('extinguisher')
  const [result, setResult] = useState<ReconcileResult | null>(null)
  const [classificationFilter, setClassificationFilter] = useState('')
  const [sectionFilter, setSectionFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [missingOnly, setMissingOnly] = useState(false)
  const [missingSlot, setMissingSlot] = useState('')
  const [textName, setTextName] = useState(() => suggestedLedgerName())
  const [pasteRows, setPasteRows] = useState<LedgerPasteRow[]>(() => blankLedgerRows())
  const [pasteUndo, setPasteUndo] = useState<LedgerPasteRow[][]>([])
  const [confirmClear, setConfirmClear] = useState(false)
  const textLedger = useMemo(() => serializeLedgerRows(pasteRows), [pasteRows])
  const [pendingImport, setPendingImport] = useState<PendingImport | null>(null)
  const [tutorialOpen, setTutorialOpen] = useState(false)
  const [aliases, setAliases] = useState<AliasRecord[]>([])
  const [aliasSource, setAliasSource] = useState('')
  const [aliasTarget, setAliasTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [duplicateNameNotice, setDuplicateNameNotice] = useState<string | null>(null)
  const [nameWasEdited, setNameWasEdited] = useState(false)
  const [importMessage, setImportMessage] = useState('')
  const ledgerNameRef = useRef<HTMLInputElement>(null)
  const [exporting, setExporting] = useState<'csv' | 'xlsx' | null>(null)
  const [exportMessage, setExportMessage] = useState('')
  const [exportToken, setExportToken] = useState('')
  const [scopeTree, setScopeTree] = useState<TreeNode[]>([])
  const [loadingScopeTree, setLoadingScopeTree] = useState(false)
  const resultRequestVersion = useRef(createReconcileRequestGuard())
  const reconcileBusyVersion = useRef<number | null>(null)
  const [reconcilingId, setReconcilingId] = useState<number | null>(null)
  const treeRequestVersion = useRef(0)
  const resultTarget = useRef<HTMLElement>(null)
  const scrollResult = useRef<ReconcileResult | null>(null)
  useEffect(() => {
    if (!isActive) { setTutorialOpen(false); scrollResult.current = null }
  }, [isActive])
  useEffect(() => {
    if (!result || scrollResult.current !== result) return
    scrollResult.current = null
    if (!isActive) return
    resultTarget.current?.scrollIntoView({ block: 'start',
      behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }, [result, isActive])

  function clearStaleResults() {
    resultRequestVersion.current.invalidate()
    scrollResult.current = null
    setResult(null)
    setClassificationFilter('')
    setSectionFilter('')
    setCategoryFilter('')
    setMissingOnly(false)
    setMissingSlot('')
    setExportMessage('')
    setExportToken('')
  }


  useEffect(() => {
    setRootId((current) => current ?? defaultRootId ?? roots[0]?.id ?? null)
  }, [defaultRootId, roots])

  useEffect(() => {
    const request = ++treeRequestVersion.current
    setScopeTree([])
    if (rootId === null) return
    let active = true
    setLoadingScopeTree(true)
    void api.tree(rootId).then((tree) => {
      if (active && request === treeRequestVersion.current) setScopeTree(tree)
    }).catch((err) => {
      if (active && request === treeRequestVersion.current) {
        setError(err instanceof Error ? err.message : '讀取分類月份失敗')
      }
    }).finally(() => {
      if (active && request === treeRequestVersion.current) setLoadingScopeTree(false)
    })
    return () => { active = false; treeRequestVersion.current++ }
  }, [rootId])

  useEffect(() => () => {
    resultRequestVersion.current.invalidate()
    treeRequestVersion.current++
  }, [])

  const categoryPeriods = useMemo(
    () => periodsForCategory(scopeTree, categoryCode),
    [scopeTree, categoryCode],
  )

  async function refreshLedgers(preferredId?: number | null) {
    const next = await api.ledgers()
    setLedgers(next)
    setLedgerId((current) => {
      if (preferredId !== undefined && preferredId !== null && next.some((row) => row.id === preferredId)) return preferredId
      if (current !== null && next.some((row) => row.id === current)) return current
      return next[0]?.id ?? null
    })
  }

  async function refreshAliases() {
    setAliases(await api.aliases())
  }

  useEffect(() => {
    void refreshLedgers().catch((err) => setError(err instanceof Error ? err.message : '讀取清冊失敗'))
    void refreshAliases().catch((err) => setError(err instanceof Error ? err.message : '讀取別名失敗'))
  }, [])

  const ledgerNameUsed = ledgerNameInUse(textName, ledgers)

  function showDuplicateNameNotice() {
    setError('')
    setDuplicateNameNotice(textName.trim())
  }

  function closeDuplicateNameNotice() {
    setDuplicateNameNotice(null)
    // Acknowledging this unchanged name must not reopen the dialog on next blur.
    setNameWasEdited(false)
    // Restore focus after the dialog unmount cleanup returns focus to its trigger.
    window.setTimeout(() => ledgerNameRef.current?.focus(), 0)
  }

  function changePasteRows(next: LedgerPasteRow[]) {
    setPasteUndo(history => [...history.slice(-29), pasteRows])
    setPasteRows(next)
    if (pendingImport?.kind === 'text') setPendingImport(null)
    setError('')
  }

  function undoPasteRows() {
    const previous = pasteUndo[pasteUndo.length - 1]
    if (!previous) return
    setPasteUndo(history => history.slice(0, -1))
    setPasteRows(previous)
    if (pendingImport?.kind === 'text') setPendingImport(null)
  }

  async function previewExcel(file: File) {
    setBusy(true)
    setError('')
    try {
      const preview = await api.previewExcelLedger(file)
      setPendingImport({ kind: 'excel', preview, file })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Excel 預覽失敗')
    } finally {
      setBusy(false)
    }
  }

  async function previewText() {
    if (ledgerNameUsed) { showDuplicateNameNotice(); return }
    if (!textLedger.trim() || !textName.trim()) {
      setError('請輸入清冊名稱及清冊內容')
      return
    }
    setBusy(true)
    setError('')
    try {
      const preview = await api.previewTextLedger(textName.trim(), textLedger)
      setPendingImport({ kind: 'text', preview })
    } catch (err) {
      setError(err instanceof Error ? err.message : '文字清冊預覽失敗')
    } finally {
      setBusy(false)
    }
  }

  async function confirmImport() {
    if (!pendingImport || busy) return
    if (ledgerNameUsed) { showDuplicateNameNotice(); return }
    if (!textName.trim()) { setError('請輸入清冊名稱'); return }
    const version = resultRequestVersion.current.next()
    setBusy(true)
    setError('')
    try {
      const name = textName.trim() || suggestedLedgerName()
      const created = pendingImport.kind === 'text'
        ? await api.importTextLedger(name, textLedger)
        : await api.importExcelLedger(pendingImport.file!, name)
      if (!resultRequestVersion.current.isCurrent(version)) { await refreshLedgers(); return }
      setTextName('')
      setNameWasEdited(false)
      setDuplicateNameNotice(null)
      setPendingImport(null)
      setError('')
      setImportMessage(`已儲存清冊「${name}」；以下可查看核對結果。`)
      scrollResult.current = null
      setResult(null)
      setExportMessage('')
      setExportToken('')
      await refreshLedgers(created.id)
      if (rootId !== null) {
        const next = await api.reconcile(rootId, created.id, period || undefined, categoryCode)
        if (resultRequestVersion.current.isCurrent(version)) {
          scrollResult.current = next
          setResult(next)
          setClassificationFilter('')
          setSectionFilter('')
          setCategoryFilter('')
          setMissingOnly(false)
          setMissingSlot('')
        }
      }
      setPendingImport(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '清冊匯入失敗'
      if (isLedgerNameConflict(err)) showDuplicateNameNotice()
      else setError(message)
    } finally {
      setBusy(false)
    }
  }

  async function runReconcile(clickedLedgerId: number | null = ledgerId) {
    if (rootId === null || clickedLedgerId === null || busy || exporting !== null || loadingScopeTree ||
        reconcileBusyVersion.current !== null || !ledgers.some(row => row.id === clickedLedgerId)) return
    const version = resultRequestVersion.current.next()
    reconcileBusyVersion.current = version
    setReconcilingId(clickedLedgerId)
    setLedgerId(clickedLedgerId)
    setBusy(true)
    setError('')
    scrollResult.current = null
    setResult(null)
    setExportMessage('')
    setExportToken('')
    try {
      const next = await api.reconcile(rootId, clickedLedgerId, period || undefined, categoryCode)
      if (!resultRequestVersion.current.isCurrent(version)) return
      scrollResult.current = next
          setResult(next)
      setClassificationFilter('')
      setSectionFilter('')
      setCategoryFilter('')
      setMissingOnly(false)
      setMissingSlot('')
    } catch (err) {
      if (resultRequestVersion.current.isCurrent(version)) {
        setError(err instanceof Error ? err.message : '核對失敗')
      }
    } finally {
      if (reconcileBusyVersion.current === version) {
        reconcileBusyVersion.current = null
        setReconcilingId(null)
        setBusy(false)
      }
    }
  }

  async function saveAlias() {
    if (!aliasSource.trim() || !aliasTarget.trim()) return
    setBusy(true)
    setError('')
    try {
      await api.saveAlias(aliasSource, aliasTarget)
      setAliasSource('')
      setAliasTarget('')
      await refreshAliases()
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存別名失敗')
    } finally {
      setBusy(false)
    }
  }


  async function toggleReshot(category: string, deviceNo: string, marked: boolean) {
    if (!result) return
    setError('')
    try {
      await api.setReshotMark(result.root_id, result.ledger_id, category, deviceNo, marked)
      setResult((current) => current ? {
        ...current,
        rows: current.rows.map((row) =>
          row.category === category && row.device_no === deviceNo
            ? { ...row, marked_reshot: marked }
            : row,
        ),
      } : current)
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新補拍標記失敗')
    }
  }

  async function copyReshoot() {
    if (!result?.reshoot_text) return
    try {
      await navigator.clipboard.writeText(result.reshoot_text)
    } catch {
      setError('無法寫入剪貼簿，請確認瀏覽器權限')
    }
  }

  async function saveMissingExport(format: 'csv' | 'xlsx') {
    if (!result || exporting) return
    setError('')
    setExportMessage('')
    setExportToken('')
    const version = resultRequestVersion.current.next()
    setExporting(format)
    try {
      const saved = await api.saveReconcileExport(
        result.root_id, result.ledger_id, format, result.period ?? undefined, result.category_code ?? categoryCode,
      )
      if (!resultRequestVersion.current.isCurrent(version)) return
      if (!saved.saved || saved.size === 0) throw new Error('匯出未產生有效檔案')
      setExportMessage(`已儲存 ${saved.filename}（${saved.size} bytes），位置：${saved.path}`)
      setExportToken(saved.open_token)
    } catch (err) {
      if (resultRequestVersion.current.isCurrent(version)) {
        setError(err instanceof Error ? err.message : '匯出失敗，請重新操作')
      }
    } finally {
      setExporting(null)
    }
  }

  function closeTutorial() {
    setTutorialOpen(false)
  }

  const sections = useMemo(
    () => Array.from(new Set(
      (result?.rows ?? [])
        .filter((row) => row.kind === 'ledger' && row.section)
        .map((row) => row.section),
    )).sort(),
    [result],
  )

  const filteredRows = useMemo(
    () => filterReconcileRows(
      result?.rows ?? [], classificationFilter, sectionFilter, categoryFilter, missingOnly, missingSlot,
    ),
    [result, classificationFilter, sectionFilter, categoryFilter, missingOnly, missingSlot],
  )

  return (
    <section className="reconcile-page" aria-label="照片清冊核對">
      {error && <div className="error-banner" role="alert">{error}</div>}
      {importMessage && <p className="stats-message" role="status">{importMessage}</p>}
      {duplicateNameNotice !== null && (
        <AppConfirmDialog title="清冊名稱已存在" cancelLabel={null} confirmLabel="確認"
          onCancel={closeDuplicateNameNotice} onConfirm={closeDuplicateNameNotice}>
          <p>清冊名稱「<strong>{duplicateNameNotice}</strong>」已被使用，請更換一個名稱。</p>
          <p className="help-text">為保護既有資料，FireLens 不會覆蓋或刪除已儲存的清冊。</p>
        </AppConfirmDialog>
      )}

      {tutorialOpen && (
        <ModalBackdrop onCancel={closeTutorial} className="preview-backdrop" onMouseDown={closeTutorial} onKeyDown={(event) => { if (event.key === 'Escape') closeTutorial() }}>
          <section className="panel-card reconcile-tutorial" role="dialog" aria-modal="true" aria-label="清冊使用教學" onMouseDown={(event) => event.stopPropagation()}>
            <div className="panel-title"><h2>清冊核對快速教學</h2><button type="button" aria-label="關閉教學" onClick={closeTutorial}>×</button></div>
          <ol>
            <li>準備一行一個完整設備編號，或「棟別樓層 + 設備編號」兩欄資料。</li>
            <li>直接貼上文字，或選擇 .xlsx Excel 清冊。</li>
            <li>先看解析預覽，確認有效、重複與無法辨識的資料。</li>
            <li>選擇滅火器、放置盒或燈具，可設定月份／批次限制搜尋範圍。</li>
            <li>儲存清冊後按「開始核對」，系統只核對清冊內的設備，並將結果分成完整、缺照片及找不到資料夾等狀態。</li>
            <li>確認結果後，可匯出 CSV 或 Excel 缺失清單。</li>
          </ol>
          <div className="tutorial-examples">
            <div><b>單欄</b><pre>動-01-15{`\n`}致-B1-67{`\n`}中-B2-05</pre></div>
            <div><b>雙欄</b><pre>致德樓8F{`\t`}致-08-19{`\n`}中正樓B2F{`\t`}中-B2-05</pre></div>
          </div>
          <div className="tutorial-actions">
            <button type="button" onClick={() => void navigator.clipboard.writeText('致德樓8F\t致-08-19\n中正樓B2F\t中-B2-05').catch(() => setError('複製範例失敗'))}>複製雙欄範例</button>
            <span>教學只在您主動開啟時顯示。</span>
            <button type="button" onClick={closeTutorial}>我知道了</button>
          </div>
          </section>
        </ModalBackdrop>
      )}

      <section className="reconcile-controls panel-card">
        <div className="panel-title">
          <h2>清冊與核對範圍</h2>
          <button type="button" className="text-button" onClick={() => { setTutorialOpen(true) }}>查看範例／使用教學</button>
        </div>
        <div className="control-grid">
          <label>照片根目錄
            <select value={rootId ?? ''} disabled={busy || exporting !== null}
              onChange={(event) => { clearStaleResults(); setRootId(Number(event.target.value)); setPeriod('') }}>
              {roots.map((root) => <option key={root.id} value={root.id}>{root.label}</option>)}
            </select>
          </label>
          <label>設備類別／搜尋資料夾
            <select value={categoryCode} disabled={busy || exporting !== null}
              onChange={(event) => {
                if (!isDeviceCategory(event.target.value)) return
                clearStaleResults()
                setCategoryCode(event.target.value)
                setPeriod('')
              }}>
              <option value="extinguisher">滅火器</option>
              <option value="box">放置盒</option>
              <option value="lamp">燈具</option>
            </select>
          </label>
          <label>清冊版本
            <select value={ledgerId ?? ''} disabled={busy || exporting !== null}
              onChange={(event) => { clearStaleResults(); setLedgerId(Number(event.target.value)) }}>
              {ledgers.length === 0 && <option value="">尚未匯入</option>}
              {ledgers.map((ledger) => (
                <option key={ledger.id} value={ledger.id}>{ledger.name} · {ledger.row_count} 筆</option>
              ))}
            </select>
          </label>
          <label>月份／批次（依設備類別）
            <select value={period} disabled={busy || exporting !== null || loadingScopeTree}
              onChange={(event) => { clearStaleResults(); setPeriod(event.target.value) }}>
              <option value="">全部月份／批次</option>
              {categoryPeriods.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <button type="button" className="primary-button" disabled={busy || exporting !== null || rootId === null || ledgerId === null || loadingScopeTree} onClick={() => void runReconcile()}>
            {busy ? '處理中…' : '開始核對'}
          </button>
        </div>
        <p className="help-text" role="status">
          目前搜尋：{roots.find((root) => root.id === rootId)?.label ?? '未選根目錄'} ／
          {DEVICE_CATEGORY_LABELS[categoryCode]} ／ {period || '全部月份／批次'}。
          {loadingScopeTree
            ? ' 正在載入此類別可用的月份／批次…'
            : categoryPeriods.length === 0
              ? ' 此類別目前沒有已掃描的月份；仍可跨月份核對清冊。'
              : ' 可用月份只從目前根目錄及此設備類別列出。'}
        </p>
      </section>

      <LedgerManager
        ledgers={ledgers}
        selectedId={ledgerId}
        onReconcile={(id) => { void runReconcile(id) }}
        reconcileDisabled={busy || exporting !== null || rootId === null || loadingScopeTree}
        reconcilingLedgerId={reconcilingId}
        onSelect={(id) => { clearStaleResults(); setLedgerId(id) }}
        onChanged={async (preferredId) => { clearStaleResults(); await refreshLedgers(preferredId); setError(''); setDuplicateNameNotice(null) }}
        defaultCollapsed={settings?.ledger_list_collapsed ?? false}
        pageSize={settings?.ledger_page_size ?? 5}
        onError={setError}
      />

      <section className="reconcile-import-grid ledger-sources-grid">
        <section className="panel-card">
          <div className="panel-title"><h2>匯入 Excel</h2></div>
          <label className="file-drop compact">
            選擇 .xlsx 清冊
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={busy || !textName.trim()}
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void previewExcel(file)
                event.currentTarget.value = ''
              }}
            />
          </label>
          <small>與下方表格共用「清冊名稱」；設備編號必填，棟別樓層可省略。</small>
        </section>
        <section className="panel-card alias-card">
          <div className="panel-title"><h2>棟別別名</h2><span>{aliases.length}</span></div>
          <div className="alias-add">
            <input value={aliasSource} onChange={(event) => setAliasSource(event.target.value)} placeholder="清冊別名" aria-label="別名來源" />
            <span>→</span>
            <input value={aliasTarget} onChange={(event) => setAliasTarget(event.target.value)} placeholder="照片資料夾名稱" aria-label="別名目標" />
            <button type="button" onClick={() => void saveAlias()} disabled={busy || !aliasSource.trim() || !aliasTarget.trim()}>儲存</button>
          </div>
          <div className="alias-list">
            {aliases.map((alias) => <span key={alias.id}>{alias.source_value} → {alias.target_value}</span>)}
          </div>
        </section>
      </section>

      <section className="panel-card ledger-paste-card" aria-label="貼上文字清冊表格區">
        <div className="ledger-paste-head">
          <div><h2>貼上文字清冊｜表格編輯</h2>
            <p className="help-text">獨立大型工作區，複製 Excel／Google 試算表的棟別樓層與設備編號，直接貼入下方儲存格。</p>
          </div>
          <span className="help-text">最多 10,000 列 · 先預覽再儲存</span>
        </div>
        <label className="ledger-paste-name">清冊名稱（文字與 Excel 共用，不可重複）
          <input ref={ledgerNameRef} aria-label="清冊名稱" aria-invalid={ledgerNameUsed} maxLength={200} value={textName}
            disabled={busy} placeholder="例如：2026/11 滅火器清冊"
            onBlur={() => { if (nameWasEdited && ledgerNameUsed && !duplicateNameNotice) showDuplicateNameNotice() }}
            onChange={(event) => {
              setTextName(event.target.value)
              setNameWasEdited(true)
              setDuplicateNameNotice(null)
              setImportMessage('')
              if (error.includes('清冊名稱')) setError('')
              if (pendingImport?.kind === 'text') setPendingImport(null)
            }} />
        </label>
        <div className="ledger-paste-toolbar">
          <small>已填 {filledLedgerCount(pasteRows)} 筆（可逐格修改，不會自動儲存）</small>
          <div>
            <button type="button" disabled={busy || !pasteUndo.length} onClick={undoPasteRows}>↶ 復原</button>
            <button type="button" disabled={busy || !filledLedgerCount(pasteRows)} onClick={() => setConfirmClear(true)}>清空表格</button>
          </div>
        </div>
        {confirmClear && <div className="danger-confirm" role="alert">
          <b>確定清空目前貼上的表格嗎？</b>
          <span>不會刪除已儲存的清冊，仍可按「復原」回到清空前。</span>
          <div className="ledger-confirm-actions">
            <button type="button" onClick={() => setConfirmClear(false)}>取消</button>
            <button type="button" className="danger-button" onClick={() => {
              changePasteRows(blankLedgerRows()); setConfirmClear(false)
            }}>確認清空</button>
          </div>
        </div>}
        <LedgerPasteSheet rows={pasteRows} disabled={busy}
          onChange={changePasteRows} onUndo={undoPasteRows} onError={setError} />
        <div className="ledger-paste-footer">
          <span>格式範例：致德樓8F　致-08-19 ／ 單欄：動-01-15</span>
          <button type="button" className="primary-button" onClick={() => void previewText()}
            disabled={busy || !textLedger.trim() || !textName.trim()}>
            {busy ? '正在解析…' : '解析預覽'}
          </button>
        </div>
      </section>

      {pendingImport && (
        <section className="panel-card import-preview" aria-label="清冊匯入預覽">
          <div className="panel-title"><h2>匯入預覽</h2><span>{pendingImport.kind === 'excel' ? 'Excel' : '文字'}</span></div>
          <div className="preview-stats">
            <span>總筆數 <b>{pendingImport.preview.total_rows}</b></span>
            <span>有效 <b>{pendingImport.preview.valid_count}</b></span>
            <span>重複 <b>{pendingImport.preview.duplicate_count}</b></span>
            <span>無法辨識 <b>{pendingImport.preview.invalid_count}</b></span>
          </div>
          <p className="help-text">無法辨識的列不會儲存；重複編號與棟別樓層提示不會阻擋匯入，請先人工確認。</p>
          <div className="ledger-table-wrap">
            <table className="ledger-table">
              <thead><tr><th>來源列</th><th>棟別樓層</th><th>設備編號</th><th>結果／提醒</th></tr></thead>
              <tbody>{pendingImport.preview.rows.map((row) => (
                <tr key={row.source_row} className={!row.valid ? 'preview-invalid' : row.duplicate ? 'preview-warning' : ''}>
                  <td>{row.source_row}</td>
                  <td>{row.section || '—'}</td>
                  <td><b>{row.device_no || '—'}</b></td>
                  <td>{row.error || row.warnings.join('；') || '可匯入'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="preview-actions">
            <button type="button" onClick={() => setPendingImport(null)} disabled={busy}>取消</button>
            <button type="button" className="primary-button" onClick={() => void confirmImport()} disabled={busy || pendingImport.preview.valid_count === 0 || !textName.trim()}>儲存並開始核對</button>
          </div>
        </section>
      )}

      {result && (
        <>
          <p className="help-text" role="status">
            本次核對範圍：{roots.find((root) => root.id === result.root_id)?.label ?? '照片根目錄'} ／
            {DEVICE_CATEGORY_LABELS[result.category_code as DeviceCategory] ?? result.category_code} ／
            {result.period || '全部月份／批次'} ／
            清冊「{result.ledger_name}」，共 {result.total} 筆。僅核對此清冊內設備。
          </p>
          <section className="reconcile-summary reconcile-result-target" ref={resultTarget} aria-label="核對結果摘要">
            <div className="summary-main"><strong>{result.completion_rate}%</strong><span>清冊完成率</span><small>{result.complete} / {result.total}</small></div>
            {Object.entries(result.classification_counts).map(([classification, count]) => (
              <div key={classification} className={`summary-status status-${classification}`}>
                <strong>{count}</strong><span>{CLASSIFICATION_LABELS[classification] ?? classification}</span>
              </div>
            ))}
          </section>

          <section className="panel-card progress-card">
            <div className="panel-title"><h2>棟別樓層進度</h2></div>
            <div className="building-progress">
              {result.building_progress.map((row) => (
                <div key={row.building}><b>{row.building}</b><span>{row.complete}/{row.total}</span><strong>{row.rate}%</strong></div>
              ))}
            </div>
          </section>

          <section className="panel-card result-card reconcile-result-target" aria-label="核對結果區段">
            <div className="result-toolbar">
              <label>核對結果
                <select value={classificationFilter} onChange={(event) => setClassificationFilter(event.target.value)}>
                  <option value="">全部</option>
                  {Object.keys(result.classification_counts).map((classification) => <option key={classification} value={classification}>{CLASSIFICATION_LABELS[classification] ?? classification}</option>)}
                </select>
              </label>
              <label>棟別樓層
                <select value={sectionFilter} onChange={(event) => setSectionFilter(event.target.value)}>
                  <option value="">全部</option>
                  {sections.map((section) => <option key={section} value={section}>{section}</option>)}
                </select>
              </label>
              <label>缺少照片
                <select value={missingSlot} onChange={(event) => setMissingSlot(event.target.value)}>
                  <option value="">全部</option>
                  {(categoryCode === 'extinguisher' ? ['編號', '藥劑', '完成'] : ['前', '中', '後'])
                    .map((slot) => <option key={slot} value={slot}>缺{slot}</option>)}
                </select>
              </label>

              <label className="missing-only-check"><input type="checkbox" checked={missingOnly} onChange={(event) => setMissingOnly(event.target.checked)} /> 只看缺失</label>
              <span>{filteredRows.length} 筆結果</span>
              <button type="button" onClick={() => void copyReshoot()}>複製補拍清單</button>
              <button type="button" onClick={() => window.print()}>列印</button>
              <button type="button" className="download-button" disabled={exporting !== null} onClick={() => void saveMissingExport('csv')}>
                {exporting === 'csv' ? '正在匯出 CSV…' : '匯出缺失 CSV'}
              </button>
              <button type="button" className="download-button" disabled={exporting !== null} onClick={() => void saveMissingExport('xlsx')}>
                {exporting === 'xlsx' ? '正在匯出 Excel…' : '匯出缺失 Excel'}
              </button>
            </div>
            {exportMessage && <div className="export-feedback" role="status">
              <p className="stats-message export-success">{exportMessage}</p>
              {exportToken && <>
                <button type="button" onClick={() => void api.openExport(exportToken, 'file').catch((err) => setError(String(err)))}>開啟檔案</button>
                <button type="button" onClick={() => void api.openExport(exportToken, 'folder').catch((err) => setError(String(err)))}>開啟所在資料夾</button>
              </>}
            </div>}
            <div className="result-table-wrap">
              <table className="result-table">
                <thead><tr><th>類別</th><th>設備編號</th><th>棟別樓層</th><th>核對結果</th><th>缺少照片</th><th>找到月份</th><th>實際棟別</th><th>提示</th><th>補拍</th></tr></thead>
                <tbody>
                  {filteredRows.map((row, index) => {
                    const periods = row.found.map((item) => item.period).join('、')
                    const buildingsFound = row.found.map((item) => item.building).join('、')
                    const suggestions = row.naming_suggestions.map((item) => `${item.filename} → ${item.suggestion}`).join('；')
                    const near = row.near_candidates.length ? `近似：${row.near_candidates.join('、')}` : ''
                    const mismatch = row.building_match === false ? '棟別樓層與實際照片棟別不一致' : ''
                    const rawStatus = row.classification === 'complete' ? '' : (STATUS_LABELS[row.status] ?? row.status)
                    const hint = [suggestions, near, mismatch, rawStatus].filter(Boolean).join('；')
                    return (
                      <tr
                        key={`${row.kind}:${row.category}:${row.device_no}:${row.row_no ?? index}`}
                        className={row.marked_reshot ? 'marked-reshot' : ''}
                      >
                        <td>{CATEGORY_LABELS[row.category] ?? row.category}</td>
                        <td><b>{row.device_no}</b>{row.matched_by_note && row.matched_folder_name && <small title="以尾端備註匹配">　↳ {row.matched_folder_name}</small>}</td>
                        <td>{row.section || '—'}</td>
                        <td><span className={`status-pill status-${row.classification}`}>{CLASSIFICATION_LABELS[row.classification] ?? row.classification}</span></td>
                        <td>{row.missing_slots.join('、') || '—'}</td>
                        <td>{periods || '—'}</td>
                        <td>{buildingsFound || '—'}</td>
                        <td>{hint || '—'}</td>
                        <td>
                          {row.classification === 'complete' || row.kind === 'special' ? '—' : (
                            <label className="reshot-check">
                              <input
                                type="checkbox"
                                checked={row.marked_reshot}
                                onChange={(event) => void toggleReshot(
                                  row.category, row.device_no, event.target.checked,
                                )}
                              />
                              已補拍
                            </label>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </section>
  )
}

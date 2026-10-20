import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { filterReconcileRows } from './reconcile'
import { LedgerManager } from './LedgerManager'
import type {
  AliasRecord,
  LedgerImportPreview,
  LedgerRecord,
  ReconcileResult,
  RootRecord,
} from './types'

const STATUS_LABELS: Record<string, string> = {
  complete: '完整',
  missing_photo: '缺照片',
  no_folder: '無資料夾',
  empty_folder: '空資料夾',
  zero_byte: '0 byte',
  cloud_not_downloaded: '雲端未下載',
  invalid_naming: '命名異常',
  extra_folder: '清冊外資料夾',
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

const TUTORIAL_KEY = 'firelens.reconcile.tutorial.dismissed.v1'

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
}

export function ReconcileView({ roots, defaultRootId }: Props) {
  const [rootId, setRootId] = useState<number | null>(defaultRootId)
  const [ledgers, setLedgers] = useState<LedgerRecord[]>([])
  const [ledgerId, setLedgerId] = useState<number | null>(null)
  const [period, setPeriod] = useState('')
  const [result, setResult] = useState<ReconcileResult | null>(null)
  const [classificationFilter, setClassificationFilter] = useState('')
  const [sectionFilter, setSectionFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [missingOnly, setMissingOnly] = useState(false)
  const [missingSlot, setMissingSlot] = useState('')
  const [textName, setTextName] = useState(() => suggestedLedgerName())
  const [textLedger, setTextLedger] = useState('')
  const [pendingImport, setPendingImport] = useState<PendingImport | null>(null)
  const [tutorialOpen, setTutorialOpen] = useState(
    () => typeof window !== 'undefined' && window.localStorage.getItem(TUTORIAL_KEY) !== '1',
  )
  const [tutorialDontShow, setTutorialDontShow] = useState(false)
  const [aliases, setAliases] = useState<AliasRecord[]>([])
  const [aliasSource, setAliasSource] = useState('')
  const [aliasTarget, setAliasTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setRootId((current) => current ?? defaultRootId ?? roots[0]?.id ?? null)
  }, [defaultRootId, roots])

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
    if (!textLedger.trim()) return
    setBusy(true)
    setError('')
    try {
      const preview = await api.previewTextLedger(textName.trim() || suggestedLedgerName(), textLedger)
      setPendingImport({ kind: 'text', preview })
    } catch (err) {
      setError(err instanceof Error ? err.message : '文字清冊預覽失敗')
    } finally {
      setBusy(false)
    }
  }

  async function confirmImport() {
    if (!pendingImport) return
    setBusy(true)
    setError('')
    try {
      const name = textName.trim() || suggestedLedgerName()
      const created = pendingImport.kind === 'text'
        ? await api.importTextLedger(name, textLedger)
        : await api.importExcelLedger(pendingImport.file!, name)
      await refreshLedgers()
      setLedgerId(created.id)
      if (rootId !== null) {
        const next = await api.reconcile(rootId, created.id, period.trim() || undefined)
        setResult(next)
        setClassificationFilter('')
        setSectionFilter('')
        setCategoryFilter('')
        setMissingOnly(false)
        setMissingSlot('')
      } else {
        setResult(null)
      }
      setPendingImport(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '清冊匯入失敗')
    } finally {
      setBusy(false)
    }
  }

  async function runReconcile() {
    if (rootId === null || ledgerId === null) return
    setBusy(true)
    setError('')
    try {
      const next = await api.reconcile(rootId, ledgerId, period.trim() || undefined)
      setResult(next)
      setClassificationFilter('')
      setSectionFilter('')
      setCategoryFilter('')
      setMissingOnly(false)
      setMissingSlot('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '核對失敗')
    } finally {
      setBusy(false)
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

  function closeTutorial() {
    if (tutorialDontShow) window.localStorage.setItem(TUTORIAL_KEY, '1')
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

      {tutorialOpen && (
        <section className="panel-card reconcile-tutorial" aria-label="清冊使用教學">
          <div className="panel-title"><h2>清冊核對快速教學</h2><span>M13</span></div>
          <ol>
            <li>準備一行一個完整設備編號，或「棟別樓層 + 設備編號」兩欄資料。</li>
            <li>直接貼上文字，或選擇 .xlsx Excel 清冊。</li>
            <li>先看解析預覽，確認有效、重複與無法辨識的資料。</li>
            <li>儲存清冊後按「開始核對」，FireLens 會依設備編號找照片並列出缺漏。</li>
          </ol>
          <div className="tutorial-examples">
            <div><b>單欄</b><pre>動-01-15{`\n`}致-B1-67{`\n`}中-B2-05</pre></div>
            <div><b>雙欄</b><pre>致德樓8F{`\t`}致-08-19{`\n`}中正樓B2F{`\t`}中-B2-05</pre></div>
          </div>
          <div className="tutorial-actions">
            <label><input type="checkbox" checked={tutorialDontShow} onChange={(event) => setTutorialDontShow(event.target.checked)} /> 下次不再自動顯示</label>
            <button type="button" onClick={closeTutorial}>我知道了</button>
          </div>
        </section>
      )}

      <section className="reconcile-controls panel-card">
        <div className="panel-title">
          <h2>清冊與核對範圍</h2>
          <button type="button" className="text-button" onClick={() => { setTutorialDontShow(false); setTutorialOpen(true) }}>查看範例／使用教學</button>
        </div>
        <div className="control-grid">
          <label>照片根目錄
            <select value={rootId ?? ''} onChange={(event) => setRootId(Number(event.target.value))}>
              {roots.map((root) => <option key={root.id} value={root.id}>{root.label}</option>)}
            </select>
          </label>
          <label>清冊版本
            <select value={ledgerId ?? ''} onChange={(event) => setLedgerId(Number(event.target.value))}>
              {ledgers.length === 0 && <option value="">尚未匯入</option>}
              {ledgers.map((ledger) => (
                <option key={ledger.id} value={ledger.id}>{ledger.name} · {ledger.row_count} 筆</option>
              ))}
            </select>
          </label>
          <label>月份/批次（選填）
            <input value={period} onChange={(event) => setPeriod(event.target.value)} placeholder="留空＝跨所有月份" />
          </label>
          <button type="button" className="primary-button" disabled={busy || rootId === null || ledgerId === null} onClick={() => void runReconcile()}>
            {busy ? '處理中…' : '開始核對'}
          </button>
        </div>
        <p className="help-text">預設跨所有月份尋找相同編號；只有填入月份/批次時才限制單一批次。</p>
      </section>

      <LedgerManager
        ledgers={ledgers}
        selectedId={ledgerId}
        onSelect={(id) => { setLedgerId(id); setResult(null) }}
        onChanged={async (preferredId) => { await refreshLedgers(preferredId); setResult(null) }}
        onError={setError}
      />

      <section className="reconcile-import-grid">
        <section className="panel-card">
          <div className="panel-title"><h2>匯入 Excel</h2></div>
          <input value={textName} onChange={(event) => setTextName(event.target.value)} aria-label="清冊名稱" placeholder="清冊名稱" />
          <label className="file-drop compact">
            選擇 .xlsx 清冊
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void previewExcel(file)
                event.currentTarget.value = ''
              }}
            />
          </label>
          <small>設備編號為唯一必要欄位；棟別樓層可省略。支援有／無標題的一欄或兩欄資料，多餘欄位會忽略。</small>
        </section>

        <section className="panel-card">
          <div className="panel-title"><h2>貼上文字清冊</h2></div>
          <input value={textName} onChange={(event) => setTextName(event.target.value)} aria-label="文字清冊名稱" />
          <textarea
            value={textLedger}
            onChange={(event) => setTextLedger(event.target.value)}
            placeholder={'動-01-15\n動-03-08\n\n或直接從 Excel 複製兩欄：\n致德樓8F\t致-08-19\n中正樓B2F\t中-B2-05'}
            aria-label="貼上文字清冊"
          />
          <button type="button" className="secondary-action" onClick={() => void previewText()} disabled={busy || !textLedger.trim()}>解析預覽</button>
        </section>

        <section className="panel-card alias-card">
          <div className="panel-title"><h2>棟別別名</h2><span>{aliases.length}</span></div>
          <div className="alias-add">
            <input value={aliasSource} onChange={(event) => setAliasSource(event.target.value)} placeholder="清冊名稱" aria-label="別名來源" />
            <span>→</span>
            <input value={aliasTarget} onChange={(event) => setAliasTarget(event.target.value)} placeholder="照片資料夾名稱" aria-label="別名目標" />
            <button type="button" onClick={() => void saveAlias()} disabled={busy || !aliasSource.trim() || !aliasTarget.trim()}>儲存</button>
          </div>
          <div className="alias-list">
            {aliases.map((alias) => <span key={alias.id}>{alias.source_value} → {alias.target_value}</span>)}
          </div>
        </section>
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
            <button type="button" className="primary-button" onClick={() => void confirmImport()} disabled={busy || pendingImport.preview.valid_count === 0}>儲存並開始核對</button>
          </div>
        </section>
      )}

      {result && (
        <>
          <section className="reconcile-summary">
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

          <section className="panel-card result-card">
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
                  <option value="編號">缺編號</option>
                  <option value="藥劑">缺藥劑</option>
                  <option value="完成">缺完成</option>
                </select>
              </label>
              <label>類別
                <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
                  <option value="">全部</option>
                  <option value="extinguisher">滅火器</option>
                  <option value="box">放置盒</option>
                  <option value="lamp">燈具</option>
                </select>
              </label>
              <label className="missing-only-check"><input type="checkbox" checked={missingOnly} onChange={(event) => setMissingOnly(event.target.checked)} /> 只看缺失</label>
              <span>{filteredRows.length} 筆結果</span>
              <button type="button" onClick={() => void copyReshoot()}>複製補拍清單</button>
              <button type="button" onClick={() => window.print()}>列印</button>
              <a className="download-button" href={api.reconcileExportUrl(result.root_id, result.ledger_id, 'csv', result.period ?? undefined)}>匯出缺失 CSV</a>
              <a className="download-button" href={api.reconcileExportUrl(result.root_id, result.ledger_id, 'xlsx', result.period ?? undefined)}>匯出缺失 Excel</a>
            </div>
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
                        <td><b>{row.device_no}</b>{row.kind === 'extra' && <small>清冊外</small>}</td>
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

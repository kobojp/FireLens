import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { filterReconcileRows } from './reconcile'
import type { AliasRecord, LedgerRecord, ReconcileResult, RootRecord } from './types'

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
  const [statusFilter, setStatusFilter] = useState('')
  const [buildingFilter, setBuildingFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [textName, setTextName] = useState('貼上清冊')
  const [textLedger, setTextLedger] = useState('')
  const [aliases, setAliases] = useState<AliasRecord[]>([])
  const [aliasSource, setAliasSource] = useState('')
  const [aliasTarget, setAliasTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setRootId((current) => current ?? defaultRootId ?? roots[0]?.id ?? null)
  }, [defaultRootId, roots])

  async function refreshLedgers() {
    const next = await api.ledgers()
    setLedgers(next)
    setLedgerId((current) => current ?? next[0]?.id ?? null)
  }

  async function refreshAliases() {
    setAliases(await api.aliases())
  }

  useEffect(() => {
    void refreshLedgers().catch((err) => setError(err instanceof Error ? err.message : '讀取清冊失敗'))
    void refreshAliases().catch((err) => setError(err instanceof Error ? err.message : '讀取別名失敗'))
  }, [])

  async function importExcel(file: File) {
    setBusy(true)
    setError('')
    try {
      const created = await api.importExcelLedger(file)
      await refreshLedgers()
      setLedgerId(created.id)
      setResult(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Excel 匯入失敗')
    } finally {
      setBusy(false)
    }
  }

  async function importText() {
    if (!textLedger.trim()) return
    setBusy(true)
    setError('')
    try {
      const created = await api.importTextLedger(textName.trim() || '貼上清冊', textLedger)
      await refreshLedgers()
      setLedgerId(created.id)
      setResult(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '文字清冊匯入失敗')
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
      setStatusFilter('')
      setBuildingFilter('')
      setCategoryFilter('')
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

  const buildings = useMemo(
    () => result?.building_progress.map((row) => row.building) ?? [],
    [result],
  )

  const filteredRows = useMemo(
    () => filterReconcileRows(
      result?.rows ?? [], statusFilter, buildingFilter, categoryFilter,
    ),
    [result, statusFilter, buildingFilter, categoryFilter],
  )

  return (
    <section className="reconcile-page" aria-label="照片清冊核對">
      {error && <div className="error-banner" role="alert">{error}</div>}

      <section className="reconcile-controls panel-card">
        <div className="panel-title"><h2>清冊與核對範圍</h2><span>M3</span></div>
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

      <section className="reconcile-import-grid">
        <section className="panel-card">
          <div className="panel-title"><h2>匯入 Excel</h2></div>
          <label className="file-drop compact">
            選擇 .xlsx 清冊
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void importExcel(file)
                event.currentTarget.value = ''
              }}
            />
          </label>
          <small>必須包含：區段、設備名稱、型式規格、上次更換日。</small>
        </section>

        <section className="panel-card">
          <div className="panel-title"><h2>貼上文字清冊</h2></div>
          <input value={textName} onChange={(event) => setTextName(event.target.value)} aria-label="文字清冊名稱" />
          <textarea
            value={textLedger}
            onChange={(event) => setTextLedger(event.target.value)}
            placeholder={'區段\t設備名稱\t型式規格\t上次更換日\n第一門診1X\t一-1X-01\t10P\t2023/09/01'}
            aria-label="貼上文字清冊"
          />
          <button type="button" className="secondary-action" onClick={() => void importText()} disabled={busy || !textLedger.trim()}>匯入文字</button>
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

      {result && (
        <>
          <section className="reconcile-summary">
            <div className="summary-main"><strong>{result.completion_rate}%</strong><span>清冊完成率</span><small>{result.complete} / {result.total}</small></div>
            {Object.entries(result.counts).map(([status, count]) => (
              <div key={status} className={`summary-status status-${status}`}>
                <strong>{count}</strong><span>{STATUS_LABELS[status] ?? status}</span>
              </div>
            ))}
          </section>

          <section className="panel-card progress-card">
            <div className="panel-title"><h2>棟別進度</h2></div>
            <div className="building-progress">
              {result.building_progress.map((row) => (
                <div key={row.building}><b>{row.building}</b><span>{row.complete}/{row.total}</span><strong>{row.rate}%</strong></div>
              ))}
            </div>
          </section>

          <section className="panel-card result-card">
            <div className="result-toolbar">
              <label>狀態
                <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">全部</option>
                  {Object.keys(result.counts).map((status) => <option key={status} value={status}>{STATUS_LABELS[status] ?? status}</option>)}
                </select>
              </label>
              <label>棟別
                <select value={buildingFilter} onChange={(event) => setBuildingFilter(event.target.value)}>
                  <option value="">全部</option>
                  {buildings.map((building) => <option key={building} value={building}>{building}</option>)}
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
              <span>{filteredRows.length} 筆結果</span>
              <button type="button" onClick={() => void copyReshoot()}>複製補拍清單</button>
              <button type="button" onClick={() => window.print()}>列印</button>
              <a className="download-button" href={api.reconcileExportUrl(result.root_id, result.ledger_id, 'csv', result.period ?? undefined)}>CSV</a>
              <a className="download-button" href={api.reconcileExportUrl(result.root_id, result.ledger_id, 'xlsx', result.period ?? undefined)}>Excel</a>
            </div>
            <div className="result-table-wrap">
              <table className="result-table">
                <thead><tr><th>類別</th><th>設備編號</th><th>區段</th><th>狀態</th><th>缺少</th><th>找到月份</th><th>實際棟別</th><th>提示</th><th>補拍</th></tr></thead>
                <tbody>
                  {filteredRows.map((row, index) => {
                    const periods = row.found.map((item) => item.period).join('、')
                    const buildingsFound = row.found.map((item) => item.building).join('、')
                    const suggestions = row.naming_suggestions.map((item) => `${item.filename} → ${item.suggestion}`).join('；')
                    const near = row.near_candidates.length ? `近似：${row.near_candidates.join('、')}` : ''
                    return (
                      <tr
                        key={`${row.kind}:${row.category}:${row.device_no}:${row.row_no ?? index}`}
                        className={row.marked_reshot ? 'marked-reshot' : ''}
                      >
                        <td>{CATEGORY_LABELS[row.category] ?? row.category}</td>
                        <td><b>{row.device_no}</b>{row.kind === 'extra' && <small>清冊外</small>}</td>
                        <td>{row.section || '—'}</td>
                        <td><span className={`status-pill status-${row.status}`}>{STATUS_LABELS[row.status] ?? row.status}</span></td>
                        <td>{row.missing_slots.join('、') || '—'}</td>
                        <td>{periods || '—'}</td>
                        <td>{buildingsFound || '—'}</td>
                        <td>{suggestions || near || '—'}</td>
                        <td>
                          {row.status === 'complete' || row.status === 'legacy' || row.status === 'special' ? '—' : (
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

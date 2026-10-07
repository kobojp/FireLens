import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { previewCanExecute, safeCandidateIds, toggleCandidate } from './organizer'
import type {
  OrganizerAnalysis,
  RenameHistoryRecord,
  RenamePreview,
  RootRecord,
} from './types'

type Props = {
  roots: RootRecord[]
  defaultRootId: number | null
}

export function OrganizerView({ roots, defaultRootId }: Props) {
  const [rootId, setRootId] = useState<number | null>(defaultRootId)
  const [analysis, setAnalysis] = useState<OrganizerAnalysis | null>(null)
  const [history, setHistory] = useState<RenameHistoryRecord[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [preview, setPreview] = useState<RenamePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    setRootId((current) => current ?? defaultRootId ?? roots[0]?.id ?? null)
  }, [defaultRootId, roots])

  async function loadHistory(id: number) {
    setHistory(await api.organizerHistory(id))
  }

  async function analyze() {
    if (rootId === null) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const next = await api.organizer(rootId)
      setAnalysis(next)
      setSelected([])
      setPreview(null)
      await loadHistory(rootId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '整理分析失敗')
    } finally {
      setBusy(false)
    }
  }

  async function previewSelected() {
    if (rootId === null || selected.length === 0) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setPreview(await api.previewRenames(rootId, selected))
    } catch (err) {
      setError(err instanceof Error ? err.message : '改名預覽失敗')
    } finally {
      setBusy(false)
    }
  }

  async function executeSelected() {
    if (rootId === null || !previewCanExecute(preview)) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await api.executeRenames(rootId, selected)
      if (result.failed.length) {
        setMessage(`已改名 ${result.executed.length} 筆；${result.failed.length} 筆已安全略過。`)
      } else {
        setMessage(`已安全改名 ${result.executed.length} 筆。`)
      }
      const next = await api.organizer(rootId)
      setAnalysis(next)
      setSelected([])
      setPreview(null)
      await loadHistory(rootId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '批次改名失敗')
    } finally {
      setBusy(false)
    }
  }

  async function undo(logId: number) {
    if (rootId === null) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await api.undoRename(rootId, logId)
      setMessage('已依 SHA-256 驗證並還原檔名。')
      setAnalysis(await api.organizer(rootId))
      await loadHistory(rootId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '還原失敗')
    } finally {
      setBusy(false)
    }
  }

  const safeIds = useMemo(
    () => safeCandidateIds(analysis?.rename_candidates ?? []),
    [analysis],
  )
  const allSafeSelected = safeIds.length > 0 && safeIds.every((id) => selected.includes(id))

  return (
    <section className="organizer-page" aria-label="照片整理工具">
      {error && <div className="error-banner" role="alert">{error}</div>}
      {message && <div className="success-banner" role="status">{message}</div>}

      <section className="panel-card organizer-controls">
        <div className="panel-title"><h2>整理工具</h2><span>M4</span></div>
        <div className="organizer-control-row">
          <label>照片根目錄
            <select value={rootId ?? ''} onChange={(event) => {
              setRootId(Number(event.target.value))
              setAnalysis(null)
              setSelected([])
              setPreview(null)
            }}>
              {roots.map((root) => <option key={root.id} value={root.id}>{root.label}</option>)}
            </select>
          </label>
          <button type="button" className="primary-button" onClick={() => void analyze()} disabled={busy || rootId === null}>
            {busy ? '處理中…' : '重新分析'}
          </button>
        </div>
        <p className="help-text">分析本身只讀照片；只有你逐筆勾選、看過預覽並按下執行後才會改檔名。永不刪除或覆蓋照片。</p>
      </section>

      {analysis && (
        <>
          <section className="organizer-summary">
            <div><strong>{analysis.summary.dirty_names}</strong><span>髒檔名</span></div>
            <div><strong>{analysis.summary.safe_renames}</strong><span>可安全改名</span></div>
            <div><strong>{analysis.summary.duplicate_photo_groups}</strong><span>重複照片群</span></div>
            <div><strong>{analysis.summary.duplicate_codes}</strong><span>重複編號</span></div>
            <div><strong>{analysis.summary.near_code_pairs}</strong><span>近似編號</span></div>
            <div><strong>{analysis.summary.variant_issues}</strong><span>異體字</span></div>
          </section>

          <section className="panel-card organizer-section">
            <div className="panel-title"><h2>髒檔名與批次改名</h2><span>{analysis.dirty_files.length}</span></div>
            <div className="organizer-actions">
              <button type="button" onClick={() => setSelected(allSafeSelected ? [] : safeIds)} disabled={safeIds.length === 0 || busy}>
                {allSafeSelected ? '取消選取' : '全選安全項目'}
              </button>
              <span>已選 {selected.length} 筆</span>
              <button type="button" className="primary-button" onClick={() => void previewSelected()} disabled={selected.length === 0 || busy}>
                預覽選取項目
              </button>
            </div>
            <div className="organizer-table-wrap">
              <table className="organizer-table">
                <thead><tr><th>選取</th><th>設備</th><th>目前檔名</th><th>建議檔名</th><th>原因</th><th>狀態</th></tr></thead>
                <tbody>
                  {analysis.dirty_files.map((row) => (
                    <tr key={row.source_relative}>
                      <td><input type="checkbox" aria-label={`選取 ${row.source_name}`} checked={row.candidate_id ? selected.includes(row.candidate_id) : false} disabled={!row.safe || !row.candidate_id || busy} onChange={() => {
                        if (!row.candidate_id) return
                        setSelected((current) => toggleCandidate(current, row.candidate_id as string))
                        setPreview(null)
                      }} /></td>
                      <td><b>{row.code}</b><small>{row.building} / {row.period}</small></td>
                      <td>{row.source_name}</td>
                      <td>{row.target_name ?? "需人工確認"}</td>
                      <td>{row.reason}</td>
                      <td>{row.safe ? <span className="safe-label">可改名</span> : <span className="blocked-label">{row.blocked_reason}</span>}</td>
                    </tr>
                  ))}
                  {analysis.dirty_files.length === 0 && <tr><td colSpan={6}>沒有偵測到髒檔名。</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          {preview && (
            <section className="panel-card rename-preview" aria-label="批次改名預覽">
              <div className="panel-title"><h2>執行前預覽</h2><span>{preview.selected.length} 筆</span></div>
              <p>安全 {preview.safe_count} 筆／阻擋 {preview.blocked_count} 筆／已失效 {preview.missing_candidate_ids.length} 筆</p>
              <ul>
                {preview.selected.map((row) => <li key={row.candidate_id}><code>{row.source_relative}</code> → <code>{row.target_name}</code>{!row.safe && `（${row.blocked_reason}）`}</li>)}
              </ul>
              <div className="danger-confirm">
                <b>這是唯一會修改照片目錄的 M4 動作。</b>
                <span>只改檔名，不刪除、不覆蓋；每筆會寫入還原紀錄。</span>
                <button type="button" className="primary-button" onClick={() => void executeSelected()} disabled={!previewCanExecute(preview) || busy}>確認執行所選改名</button>
              </div>
            </section>
          )}

          <section className="organizer-grid">
            <section className="panel-card organizer-section">
              <div className="panel-title"><h2>SHA-256 重複照片</h2><span>{analysis.duplicate_photos.length}</span></div>
              {analysis.duplicate_photos.map((group) => (
                <details key={group.sha256}><summary>{group.count} 張 · {group.sha256.slice(0, 12)}…</summary>
                  <ul>{group.photos.map((photo) => <li key={photo.relative_path}>{photo.code} · {photo.filename}<small>{photo.relative_path}</small></li>)}</ul>
                </details>
              ))}
              {analysis.duplicate_photos.length === 0 && <p className="muted">未發現內容完全相同的照片。</p>}
            </section>

            <section className="panel-card organizer-section">
              <div className="panel-title"><h2>重複／近似編號</h2><span>{analysis.duplicate_codes.length + analysis.near_codes.length}</span></div>
              {analysis.duplicate_codes.map((row) => <p key={`${row.category}:${row.code}`}><b>重複：</b>{row.code}（{row.count} 個資料夾）</p>)}
              {analysis.near_codes.map((row) => <p key={`${row.category}:${row.first}:${row.second}`}><b>近似：</b>{row.first} ↔ {row.second}</p>)}
              {analysis.duplicate_codes.length + analysis.near_codes.length === 0 && <p className="muted">未發現重複或高信心近似編號。</p>}
            </section>

            <section className="panel-card organizer-section">
              <div className="panel-title"><h2>異體字／Unicode</h2><span>{analysis.variant_issues.length}</span></div>
              {analysis.variant_issues.map((row, index) => <p key={`${row.relative_path}:${row.type}:${index}`}><b>{row.value}</b> → {row.suggestion}<small>{row.reason} · {row.relative_path}</small></p>)}
              {analysis.variant_issues.length === 0 && <p className="muted">未發現已知異體字問題。</p>}
            </section>
          </section>

          <section className="panel-card organizer-section">
            <div className="panel-title"><h2>改名紀錄與 Undo</h2><span>{history.length}</span></div>
            <div className="organizer-table-wrap history-table">
              <table className="organizer-table">
                <thead><tr><th>時間</th><th>原檔名</th><th>改名後</th><th>SHA-256</th><th>狀態</th><th>操作</th></tr></thead>
                <tbody>
                  {history.map((row) => (
                    <tr key={row.id}>
                      <td>{row.created_at}</td><td>{row.source_path}</td><td>{row.target_path}</td><td><code>{row.sha256?.slice(0, 12)}…</code></td>
                      <td>{row.reverted_at ? `已還原 ${row.reverted_at}` : '可還原'}</td>
                      <td><button type="button" onClick={() => void undo(row.id)} disabled={busy || Boolean(row.reverted_at)}>Undo</button></td>
                    </tr>
                  ))}
                  {history.length === 0 && <tr><td colSpan={6}>尚無改名紀錄。</td></tr>}
                </tbody>
              </table>
            </div>
            <p className="help-text">Undo 會先確認目標檔仍存在、原檔名未被占用，且 SHA-256 與改名當下完全一致；任一條件不符就停止。</p>
          </section>
        </>
      )}
    </section>
  )
}

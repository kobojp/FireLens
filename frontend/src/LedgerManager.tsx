import { useEffect, useState } from 'react'
import { ModalBackdrop } from './AppDialog'
import { api } from './api'
import type { LedgerDetail, LedgerRecord } from './types'

type Props = {
  ledgers: LedgerRecord[]
  selectedId: number | null
  onSelect: (ledgerId: number) => void
  onReconcile?: (ledgerId: number) => void
  reconcileDisabled?: boolean
  reconcilingLedgerId?: number | null
  onChanged: (preferredId?: number | null) => Promise<void>
  onError: (message: string) => void
  defaultCollapsed?: boolean
  pageSize?: 5 | 10 | 20
}

function sourceLabel(ledger: LedgerRecord) {
  return ledger.source_type === 'text' ? '文字貼上' : 'Excel'
}

export function LedgerManager({
  ledgers, selectedId, onSelect, onReconcile, reconcileDisabled = false, reconcilingLedgerId = null,
  onChanged, onError, defaultCollapsed = false, pageSize = 5,
}: Props) {
  const [detail, setDetail] = useState<LedgerDetail | null>(null)
  const [view, setView] = useState<'parsed' | 'raw'>('parsed')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<LedgerRecord | null>(null)
  const [busy, setBusy] = useState(false)
  const actionBusy = busy || reconcilingLedgerId !== null
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  const [page, setPage] = useState(0)
  const pageCount = Math.max(1, Math.ceil(ledgers.length / pageSize))
  const currentPage = Math.min(page, pageCount - 1)
  const visibleLedgers = ledgers.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
  useEffect(() => { setCollapsed(defaultCollapsed) }, [defaultCollapsed])
  useEffect(() => { setPage(0) }, [pageSize])
  useEffect(() => {
    const target = ledgers.findIndex(ledger => ledger.id === selectedId)
    if (target >= 0) setPage(Math.floor(target / pageSize))
  }, [selectedId, pageSize])
  useEffect(() => { if (page >= pageCount) setPage(pageCount - 1) }, [page, pageCount])

  async function openLedger(ledgerId: number) {
    setBusy(true)
    onError('')
    try {
      const next = await api.ledger(ledgerId)
      setDetail(next)
      setView('parsed')
      onSelect(ledgerId)
    } catch (err) {
      onError(err instanceof Error ? err.message : '讀取清冊內容失敗')
    } finally {
      setBusy(false)
    }
  }

  async function saveRename(ledgerId: number) {
    if (!editName.trim()) return
    setBusy(true)
    onError('')
    try {
      const updated = await api.renameLedger(ledgerId, editName.trim())
      if (detail?.id === ledgerId) setDetail(updated)
      setEditingId(null)
      await onChanged(ledgerId)
    } catch (err) {
      onError(err instanceof Error ? err.message : '重新命名清冊失敗')
    } finally {
      setBusy(false)
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    const deletedId = deleteTarget.id
    setBusy(true)
    onError('')
    try {
      await api.deleteLedger(deletedId)
      if (detail?.id === deletedId) setDetail(null)
      setDeleteTarget(null)
      await onChanged(null)
    } catch (err) {
      onError(err instanceof Error ? err.message : '刪除清冊失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel-card ledger-manager" aria-label="清冊管理">
      <div className="panel-title">
        <div><h2>清冊管理</h2><small>已保存 {ledgers.length} 份清冊，可直接重新使用。</small></div>
        <button type="button" className="ledger-manager-toggle" aria-expanded={!collapsed}
          onClick={() => setCollapsed(value => !value)}>
          {collapsed ? "展開清冊清單" : "收合清冊清單"}
        </button>
      </div>
      {collapsed ? (
        <p className="help-text" role="status">清冊清單已收合，仍保留目前選取的清冊與核對結果。</p>
      ) : ledgers.length === 0 ? (
        <p className="muted">尚未保存清冊。可從下方匯入 Excel 或貼上文字。</p>
      ) : (
        <>
        <div className="ledger-list ledger-manager-compact">
          {visibleLedgers.map((ledger) => (
            <div key={ledger.id} className={`ledger-row ${selectedId === ledger.id ? 'selected' : ''}`}>
              <div className="ledger-main">
                {editingId === ledger.id ? (
                  <input
                    value={editName}
                    onChange={(event) => setEditName(event.target.value)}
                    aria-label={`重新命名 ${ledger.name}`}
                    autoFocus
                  />
                ) : <b>{ledger.name}</b>}
                <small>{sourceLabel(ledger)} · {ledger.row_count} 筆 · {ledger.imported_at}</small>
                {ledger.source_filename && <small>來源檔案：{ledger.source_filename}</small>}
              </div>
              <div className="ledger-actions">
                {editingId === ledger.id ? (
                  <>
                    <button type="button" onClick={() => void saveRename(ledger.id)} disabled={busy || !editName.trim()}>儲存</button>
                    <button type="button" onClick={() => setEditingId(null)} disabled={busy}>取消</button>
                  </>
                ) : (
                  <>
                    {onReconcile && <button type="button" className="ledger-reconcile-action"
                      disabled={actionBusy || reconcileDisabled}
                      onClick={() => onReconcile(ledger.id)}>
                      {reconcilingLedgerId === ledger.id ? '核對中…' : '開始核對'}
                    </button>}
                    <button type="button" onClick={() => void openLedger(ledger.id)} disabled={busy}>開啟</button>
                    <button type="button" onClick={() => { setEditingId(ledger.id); setEditName(ledger.name) }} disabled={actionBusy}>重新命名</button>
                    <button type="button" className="danger-button" onClick={() => setDeleteTarget(ledger)} disabled={actionBusy}>刪除</button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
        <nav className="ledger-manager-pagination" aria-label="清冊管理分頁">
          <button type="button" disabled={currentPage === 0 || busy}
            onClick={() => setPage(currentPage - 1)}>上一頁</button>
          <span>第 {currentPage + 1}／{pageCount} 頁 · 共 {ledgers.length} 筆 · 每頁 {pageSize} 筆</span>
          <button type="button" disabled={currentPage === pageCount - 1 || busy}
            onClick={() => setPage(currentPage + 1)}>下一頁</button>
        </nav>
        </>
      )}

      {deleteTarget && (
        <ModalBackdrop className="preview-backdrop" onCancel={() => { if (!busy) setDeleteTarget(null) }}>
          <section className="prompt-dialog" role="alertdialog" aria-modal="true" aria-label="確認刪除清冊">
            <div className="prompt-header">確認刪除清冊</div>
            <div className="prompt-body">
              <b>確認刪除「{deleteTarget.name}」？</b>
              <p>會刪除這份清冊的 {deleteTarget.row_count} 筆解析資料與相關補拍標記，不會刪除任何照片。此動作無法復原。</p>
            </div>
            <div className="prompt-footer">
              <button type="button" data-dialog-cancel onClick={() => setDeleteTarget(null)} disabled={busy}>取消</button>
              <button type="button" className="danger-button" onClick={() => void confirmDelete()} disabled={busy}>永久刪除</button>
            </div>
          </section>
        </ModalBackdrop>
      )}

      {detail && (
        <section className="ledger-detail">
          <div className="ledger-detail-head">
            <div><b>{detail.name}</b><small>{sourceLabel(detail)} · {detail.row_count} 筆</small></div>
            <div className="ledger-tabs" role="tablist" aria-label="清冊內容檢視">
              <button type="button" className={view === 'parsed' ? 'active' : ''} onClick={() => setView('parsed')}>解析資料</button>
              <button type="button" className={view === 'raw' ? 'active' : ''} onClick={() => setView('raw')}>原始內容</button>
            </div>
          </div>
          {view === 'parsed' ? (
            <div className="ledger-table-wrap">
              <table className="ledger-table">
                <thead><tr><th>#</th><th>棟別樓層</th><th>設備編號</th></tr></thead>
                <tbody>{detail.rows.map((row) => (
                  <tr key={row.id}><td>{row.row_no}</td><td>{row.section || '—'}</td><td>{row.device_no}</td></tr>
                ))}</tbody>
              </table>
            </div>
          ) : detail.source_type === 'text' ? (
            <pre className="ledger-raw">{detail.source_text ?? '舊版清冊未保存原始貼上內容。'}</pre>
          ) : (
            <div className="ledger-source-meta">
              <p><b>原始檔名：</b>{detail.source_filename || '舊版匯入未記錄'}</p>
              <p><b>SHA-256：</b><code>{detail.source_sha256 || '未記錄'}</code></p>
              <p className="muted">Excel 原始檔本體不存入資料庫；FireLens 保存來源檔名、SHA-256 與解析後資料。</p>
            </div>
          )}
        </section>
      )}
    </section>
  )
}

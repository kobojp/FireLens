import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { IssueLabel, IssueStatistics, RootRecord } from './types'

type Props = {
  roots: RootRecord[]
  onOpenItem: (rootId: number, itemId: number) => void
  onLabelsChanged: () => void
}

export function StatisticsView({ roots, onOpenItem, onLabelsChanged }: Props) {
  const [stats, setStats] = useState<IssueStatistics | null>(null)
  const [rootId, setRootId] = useState('')
  const [labelId, setLabelId] = useState('')
  const [building, setBuilding] = useState('')
  const [query, setQuery] = useState('')
  const [newName, setNewName] = useState('')
  const [editLabel, setEditLabel] = useState<IssueLabel | null>(null)
  const [editName, setEditName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [exportResult, setExportResult] = useState<{ filename: string, path: string, size: number, open_token: string } | null>(null)
  const [exporting, setExporting] = useState<'csv' | 'xlsx' | null>(null)

  async function refresh(selectedRoot = rootId) {
    setStats(await api.issueStatistics(selectedRoot ? Number(selectedRoot) : undefined))
  }

  useEffect(() => {
    void refresh(rootId).catch((err) => setError(err instanceof Error ? err.message : '讀取統計失敗'))
    // refresh on root selection and remount, without polling real photo files
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootId])

  async function saveIssueExport(format: 'csv' | 'xlsx') {
    if (exporting || rows.length === 0) return
    setExporting(format)
    setExportResult(null)
    setError('')
    try {
      const saved = await api.saveIssueExport(format, {
        root_id: rootId ? Number(rootId) : undefined,
        label_id: labelId ? Number(labelId) : undefined,
        building: building || undefined,
        query: query.trim() || undefined,
      })
      if (!saved.saved || !saved.size || saved.row_count !== rows.length) throw new Error('匯出筆數或檔案內容不符，請重新整理')
      setExportResult(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : '匯出失敗')
    } finally {
      setExporting(null)
    }
  }

  async function createLabel() {
    if (!newName.trim()) return
    setBusy(true)
    setError('')
    try {
      await api.createIssueLabel(newName)
      setNewName('')
      setMessage('已建立異常分類')
      await refresh()
      onLabelsChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增分類失敗')
    } finally {
      setBusy(false)
    }
  }

  async function saveLabel(patch: { name?: string; active?: boolean; sort_order?: number }, id: number) {
    setBusy(true)
    setError('')
    try {
      await api.editIssueLabel(id, patch)
      setEditLabel(null)
      setMessage('異常分類設定已儲存')
      await refresh()
      onLabelsChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新分類失敗')
    } finally {
      setBusy(false)
    }
  }

  const buildings = useMemo(
    () => Array.from(new Set((stats?.items ?? []).map((x) => x.building).filter((x): x is string => Boolean(x)))).sort(),
    [stats],
  )
  const rows = useMemo(() => (stats?.items ?? []).filter((row) => {
    if (labelId && row.label_id !== Number(labelId)) return false
    if (building && row.building !== building) return false
    if (query.trim() && ![row.device_code, row.root_name, row.item_relative_path]
      .join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())) return false
    return true
  }), [stats, labelId, building, query])

  return (
    <section className="reconcile-page issue-stats-page" aria-label="設備異常統計">
      <section className="panel-card">
        <div className="panel-title"><h2>設備異常統計</h2><span>每台設備最多一種異常</span></div>
        <label className="stats-root-select">根目錄
          <select value={rootId} onChange={(event) => { setRootId(event.target.value); setLabelId(''); setBuilding(''); setExportResult(null) }}>
            <option value="">全部根目錄</option>
            {roots.map((root) => <option key={root.id} value={root.id}>{root.label}</option>)}
          </select>
        </label>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {message && <p className="stats-message" role="status">{message}</p>}
        <div className="issue-stat-cards">
          <button className={labelId === '' ? 'active' : ''} type="button" onClick={() => { setLabelId(''); setExportResult(null) }}>
            <b>異常設備總數</b><strong>{stats?.total ?? 0} 台</strong>
          </button>
          {stats?.labels.map((label) => (
            <button
              key={label.id}
              className={labelId === String(label.id) ? 'active' : ''}
              type="button"
              onClick={() => { setLabelId(String(label.id)); setExportResult(null) }}
            >
              <b>{label.name}{!label.active && <small>（已停用）</small>}</b>
              <strong>{label.count ?? 0} 台</strong>
            </button>
          ))}
        </div>
      </section>

      <section className="panel-card">
        <div className="panel-title"><h2>異常設備清單</h2><span>{rows.length} 筆</span></div>
        <div className="issue-filters">
          <label>棟別樓層
            <select value={building} onChange={(event) => { setBuilding(event.target.value); setExportResult(null) }}>
              <option value="">全部</option>
              {buildings.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label>搜尋設備編號或來源
            <input value={query} onChange={(event) => { setQuery(event.target.value); setExportResult(null) }} placeholder="例如 中-03-238" />
          </label>
          <button type="button" onClick={() => { setExportResult(null); void refresh().catch((err) => setError(String(err))) }}>重新整理</button>
          <button type="button" disabled={exporting !== null || rows.length === 0} onClick={() => void saveIssueExport('csv')}>{exporting === 'csv' ? '匯出中…' : '匯出 CSV'}</button>
          <button type="button" disabled={exporting !== null || rows.length === 0} onClick={() => void saveIssueExport('xlsx')}>{exporting === 'xlsx' ? '匯出中…' : '匯出 Excel'}</button>
        </div>
        {exportResult && <div className="export-feedback" role="status">
          <p className="stats-message">已儲存 {exportResult.filename}（{exportResult.size} bytes），位置：{exportResult.path}</p>
          <button type="button" onClick={() => void api.openExport(exportResult.open_token, 'file').catch((err) => setError(String(err)))}>開啟檔案</button>
          <button type="button" onClick={() => void api.openExport(exportResult.open_token, 'folder').catch((err) => setError(String(err)))}>開啟所在資料夾</button>
        </div>}
        <div className="result-table-wrap">
          <table className="result-table">
            <thead><tr><th>設備編號</th><th>異常分類</th><th>棟別樓層</th><th>月份／批次</th><th>根目錄</th><th>標記時間</th><th>照片</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.root_id}:${row.item_relative_path}`}>
                  <td><b>{row.device_code}</b></td>
                  <td>{stats?.labels.find((x) => x.id === row.label_id)?.name ?? '—'}</td>
                  <td>{row.building ?? '來源未連線／待重新關聯'}</td>
                  <td>{row.period ?? '—'}</td>
                  <td>{row.root_name}</td>
                  <td>{row.updated_at}</td>
                  <td>{row.item_id
                    ? <button type="button" onClick={() => onOpenItem(row.root_id, row.item_id!)}>查看照片</button>
                    : <span>來源未找到</span>}
                  </td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={7}>沒有符合條件的異常設備</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel-card">
        <div className="panel-title"><h2>自訂異常分類</h2><span>所有根目錄共用分類名稱</span></div>
        <div className="issue-label-add">
          <input aria-label="新增異常名稱" value={newName} maxLength={80} onChange={(event) => setNewName(event.target.value)} placeholder="輸入異常名稱，例如 瓶身損傷" />
          <button type="button" disabled={busy || !newName.trim()} onClick={() => void createLabel()}>新增分類</button>
        </div>
        <div className="issue-label-list">
          {stats?.labels.map((label) => (
            <div key={label.id} className="issue-label-row">
              <strong>{label.name}</strong>
              <small>{label.count ?? 0} 台{label.active ? '' : ' · 已停用'}</small>
              <button type="button" disabled={busy} onClick={() => { setEditLabel(label); setEditName(label.name) }}>改名稱</button>
              <button type="button" disabled={busy} onClick={() => void saveLabel({ active: !label.active }, label.id)}>{label.active ? '停用' : '啟用'}</button>
              <button type="button" disabled={busy} onClick={() => void saveLabel({ sort_order: Math.max(0, label.sort_order - 1) }, label.id)}>上移</button>
            </div>
          ))}
        </div>
      </section>
      {editLabel && (
        <div className="preview-backdrop" onMouseDown={() => setEditLabel(null)}>
          <section className="prompt-dialog" role="dialog" aria-modal="true" aria-label="修改異常名稱" onMouseDown={(event) => event.stopPropagation()}>
            <div className="prompt-header">修改異常分類名稱</div>
            <div className="prompt-body">
              <input autoFocus value={editName} maxLength={80} onChange={(event) => setEditName(event.target.value)} aria-label="新異常名稱" />
              <p>修改名稱不會刪除已有設備標記。</p>
            </div>
            <div className="prompt-footer">
              <button type="button" onClick={() => setEditLabel(null)}>取消</button>
              <button type="button" disabled={busy || !editName.trim()} onClick={() => void saveLabel({ name: editName }, editLabel.id)}>儲存名稱</button>
            </div>
          </section>
        </div>
      )}
    </section>
  )
}

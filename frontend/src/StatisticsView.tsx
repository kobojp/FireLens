import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import type { IssueLabel, IssueStatistics, RootRecord, SharedIssueStatus, SharedIssueBackup, SharedIssueConflict } from './types'

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
  const exportRequestVersion = useRef(0)
  const refreshRequestVersion = useRef(0)
  const [refreshing, setRefreshing] = useState(false)
  const [syncRootId, setSyncRootId] = useState<number | null>(null)
  const [syncStatus, setSyncStatus] = useState<SharedIssueStatus | null>(null)
  const [syncBackups, setSyncBackups] = useState<SharedIssueBackup[]>([])
  const [syncConflicts, setSyncConflicts] = useState<SharedIssueConflict[]>([])
  const [syncBusy, setSyncBusy] = useState(false)
  const [syncError, setSyncError] = useState('')
  const [syncMessage, setSyncMessage] = useState('')



  useEffect(() => {
    if (roots.length && !roots.some((root) => root.id === syncRootId)) {
      setSyncRootId(roots[0].id)
    }
  }, [roots, syncRootId])

  async function refreshSharedIssueSync(selectedRoot = syncRootId) {
    if (selectedRoot === null) return
    const next = await api.sharedIssueStatus(selectedRoot)
    setSyncStatus(next)
    if (next.enabled && next.state !== 'offline') {
      const [history, pending] = await Promise.all([
        api.sharedIssueBackups(selectedRoot),
        api.sharedIssueConflicts(selectedRoot),
      ])
      setSyncBackups(history)
      setSyncConflicts(pending)
    } else {
      setSyncBackups([])
      setSyncConflicts([])
    }
  }

  useEffect(() => {
    setSyncStatus(null)
    setSyncBackups([])
    setSyncConflicts([])
    setSyncMessage('')
    setSyncError('')
    if (syncRootId === null) return
    let active = true
    void api.sharedIssueStatus(syncRootId)
      .then((result) => { if (active) setSyncStatus(result) })
      .catch((err) => { if (active) setSyncError(err instanceof Error ? err.message : '讀取同步狀態失敗') })
    return () => { active = false }
  }, [syncRootId])

  useEffect(() => {
    if (!syncRootId || !syncStatus?.enabled) return
    // Poll the local API only. The server checks the Drive Desktop folder
    // independently; we never claim confirmed upload to Google servers.
    void refreshSharedIssueSync(syncRootId).catch((err) => setSyncError(
      err instanceof Error ? err.message : '讀取共用資料失敗',
    ))
    const poll = window.setInterval(() => {
      void refreshSharedIssueSync(syncRootId).catch((err) => setSyncError(
        err instanceof Error ? err.message : '共用資料暫時不可讀',
      ))
    }, 60000)
    return () => window.clearInterval(poll)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syncRootId, syncStatus?.enabled])

  async function sharedAction(task: () => Promise<unknown>, message: string) {
    if (syncRootId === null || syncBusy) return
    setSyncBusy(true)
    setSyncError('')
    setSyncMessage('')
    try {
      await task()
      await refreshSharedIssueSync(syncRootId)
      await refresh()
      onLabelsChanged()
      setSyncMessage(message)
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : '同步操作失敗')
      void api.sharedIssueStatus(syncRootId).then(setSyncStatus).catch(() => undefined)
    } finally {
      setSyncBusy(false)
    }
  }

  function invalidateExport() {
    exportRequestVersion.current++
    setExportResult(null)
  }


  async function refresh(selectedRoot = rootId) {
    const version = ++refreshRequestVersion.current
    invalidateExport()
    setRefreshing(true)
    setError('')
    try {
      const response = await api.issueStatistics(selectedRoot ? Number(selectedRoot) : undefined)
      if (version === refreshRequestVersion.current) setStats(response)
    } finally {
      if (version === refreshRequestVersion.current) setRefreshing(false)
    }
  }

  useEffect(() => {
    void refresh(rootId).catch((err) => setError(err instanceof Error ? err.message : '讀取統計失敗'))
    // refresh on root selection and remount, without polling real photo files
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootId])

  async function saveIssueExport(format: 'csv' | 'xlsx') {
    if (exporting || refreshing || rows.length === 0) return
    const version = ++exportRequestVersion.current
    const visibleCount = rows.length
    setExporting(format)
    setExportResult(null)
    setError('')
    try {
      const saved = await api.saveIssueExport(format, {
        root_id: rootId ? Number(rootId) : undefined,
        label_id: labelId ? Number(labelId) : undefined,
        building: building || undefined,
        query: query.trim() || undefined,
        expected_row_count: visibleCount,
      })
      if (version !== exportRequestVersion.current) return
      if (!saved.saved || !saved.size || saved.row_count !== visibleCount) {
        throw new Error('匯出筆數或檔案內容不符，請重新整理')
      }
      setExportResult(saved)
      setMessage('成功匯出 ' + visibleCount + ' 筆異常設備')
    } catch (err) {
      if (version === exportRequestVersion.current) {
        setError(err instanceof Error ? err.message : '匯出失敗')
      }
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

  useEffect(() => () => {
    exportRequestVersion.current++
    refreshRequestVersion.current++
  }, [])

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
          <select value={rootId} disabled={exporting !== null} onChange={(event) => {
              invalidateExport()
              setStats(null)
              setRootId(event.target.value)
              setLabelId('')
              setBuilding('')
            }}>
            <option value="">全部根目錄</option>
            {roots.map((root) => <option key={root.id} value={root.id}>{root.label}</option>)}
          </select>
        </label>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {message && <p className="stats-message" role="status">{message}</p>}
        <div className="issue-stat-cards">
          <button className={labelId === '' ? 'active' : ''} type="button" disabled={exporting !== null} onClick={() => { invalidateExport(); setLabelId('') }}>
            <b>異常設備總數</b><strong>{stats?.total ?? 0} 台</strong>
          </button>
          {stats?.labels.map((label) => (
            <button
              key={label.id}
              className={labelId === String(label.id) ? 'active' : ''}
              type="button"
              disabled={exporting !== null} onClick={() => { invalidateExport(); setLabelId(String(label.id)) }}
            >
              <b>{label.name}{!label.active && <small>（已停用）</small>}</b>
              <strong>{label.count ?? 0} 台</strong>
            </button>
          ))}
        </div>
      </section>

      <section className="panel-card shared-issue-panel">
        <div className="panel-title">
          <h2>Google Drive 多人異常同步與本機備份</h2>
          <span>每台設備只能有一種異常，衝突需人工選擇</span>
        </div>
        <p className="help-text">
          透過 Windows Google Drive 電腦版的照片根目錄共用獨立事件檔，不同步 SQLite，
          不更動照片及清冊。啟用後本機會在啟動及約每兩分鐘讀取共用資料。
          <b>「已讀取」僅代表本機已驗證，無法保證 Google Drive 已完成上傳。</b>
        </p>
        <label>共用照片根目錄
          <select value={syncRootId ?? ''} disabled={syncBusy}
            onChange={(event) => setSyncRootId(event.target.value ? Number(event.target.value) : null)}>
            {roots.map((root) => <option key={root.id} value={root.id}>{root.label}</option>)}
          </select>
        </label>
        {syncStatus && <p className="help-text" role="status">
          狀態：{syncStatus.enabled
            ? syncStatus.state === 'review_required' ? '本機復原後暫停同步，需人工確認'
              : syncStatus.state === 'offline' ? '共用資料夾離線'
                : syncStatus.pending ? '待同步事件：' + syncStatus.pending + ' 筆'
                  : '已在本機讀取／待 Google Drive 傳送'
            : '未啟用'}。
          {syncStatus.last_read ? ' 最近本機讀取：' + syncStatus.last_read : ' 尚無成功讀取紀錄。'}
          {syncStatus.enabled ? ' 共用資料位置：' + syncStatus.shared_folder : ''}
        </p>}
        {syncError && <p className="error-banner" role="alert">{syncError}</p>}
        {syncMessage && <p role="status" className="stats-message">{syncMessage}</p>}
        <div className="shared-issue-actions">
          <button type="button" disabled={syncBusy || syncRootId === null} onClick={() => {
            if (syncRootId === null || !window.confirm(
              syncStatus?.enabled
                ? '停用這台電腦的共享同步？共享事件及本機紀錄都不會刪除。'
                : '確定啟用多人共享？將於選定照片根目錄建立 FireLens-共享異常資料，並保留本機備份。其他電腦必須指定相同的 Google Drive 同步根目錄。',
            )) return
            void sharedAction(
              () => api.configureSharedIssues(syncRootId, !syncStatus?.enabled),
              syncStatus?.enabled ? '已停用本機共用同步，原始資料保留' : '已啟用共用同步，請檢查並執行同步',
            )
          }}>{syncBusy ? '處理中…' : syncStatus?.enabled ? '停用此根目錄同步' : '啟用此根目錄同步'}</button>
          <button type="button" disabled={syncBusy || !syncStatus?.enabled}
            onClick={() => {
              if (syncRootId !== null) void sharedAction(
                () => api.runSharedIssueSync(syncRootId),
                '已驗證本機共享事件，請留意 Google Drive 雲端上傳狀態',
              )
            }}>立即同步</button>
          <button type="button" disabled={syncBusy || !syncStatus?.enabled}
            onClick={() => void refreshSharedIssueSync().catch((err) =>
              setSyncError(err instanceof Error ? err.message : '讀取狀態失敗'))}>查看備份／衝突</button>
          {syncStatus?.manual_review && <button type="button" disabled={syncBusy} onClick={() => {
            if (syncRootId !== null && window.confirm(
              '本機剛從備份復原。繼續同步會以共用事件版本為準，可能再次改變本機異常紀錄。確定繼續？',
            )) void sharedAction(() => api.resumeSharedIssues(syncRootId), '已重新開始同步')
          }}>確認並恢復同步</button>}
          {syncStatus?.enabled && <button type="button" disabled={syncBusy} onClick={() => {
            if (syncRootId !== null && window.confirm(
              '僅當 Google Drive 共享事件被刪除或版本退回才使用。將已驗證的本機事件封存重新放回共用資料夾，確定執行？',
            )) void sharedAction(
              () => api.recoverMissingSharedEvents(syncRootId), '已嘗試人工補回共享事件，請再次同步',
            )
          }}>修復雲端誤刪事件</button>}
        </div>
        {syncConflicts.length > 0 && (
          <div className="shared-issue-conflicts">
            <h3>待人工選擇的版本衝突：{syncConflicts.length} 項</h3>
            {syncConflicts.map((conflict) => <div className="panel-card" key={conflict.key}>
              <strong>{conflict.kind === 'label' ? '異常分類' : '設備異常'}：{conflict.key}</strong>
              <p className="help-text">兩台電腦對同一項目有不同版本。請選擇要保留的版本，不會自動覆蓋。</p>
              {conflict.candidates.map((candidate) => (
                <div className="shared-issue-candidate" key={candidate.event_id}>
                  <span>{candidate.at} · 裝置 {candidate.device.slice(0, 8)} · {JSON.stringify(candidate.value)}</span>
                  <button type="button" disabled={syncBusy} onClick={() => {
                    if (syncRootId !== null && window.confirm('確定選擇此版本，保留其他版本於歷史事件中？')) {
                      void sharedAction(
                        () => api.resolveSharedIssue(syncRootId, conflict.key, candidate.event_id),
                        '已保存人工衝突選擇',
                      )
                    }
                  }}>採用此版本</button>
                </div>
              ))}
            </div>)}
          </div>
        )}
        {syncStatus?.enabled && <section className="shared-issue-backups">
          <h3>本機歷史備份（最多顯示 100 份）</h3>
          {syncBackups.map((backup) => <div key={backup.id} className="shared-issue-backup-row">
            <span>{backup.time} · {backup.reason} · {backup.items} 台異常／{backup.labels} 個分類</span>
            <button type="button" disabled={syncBusy} onClick={() => {
              if (syncRootId === null) return
              void api.previewSharedIssueBackup(syncRootId, backup.id)
                .then((preview) => setSyncMessage(
                  '備份預覽：' + preview.time + '；備份 ' + preview.items +
                  ' 台／目前 ' + (preview.current_items ?? '—') + ' 台；復原會新增 ' +
                  (preview.adding ?? 0) + ' 台、移除 ' + (preview.removing ?? 0) +
                  ' 台、變更 ' + (preview.changing ?? 0) + ' 台異常；分類 ' + preview.labels + ' 個。',
                )).catch((err) => setSyncError(String(err)))
            }}>預覽</button>
            <button type="button" disabled={syncBusy} onClick={() => {
              if (syncRootId === null || !window.confirm(
                '確定只復原本機到這個時間點？會先備份目前本機資料並暫停同步，不會自動覆蓋 Google Drive 共用事件。',
              )) return
              void sharedAction(
                () => api.restoreSharedIssueBackup(syncRootId, backup.id),
                '本機異常已復原，同步暫停，請確認資料再決定是否繼續',
              )
            }}>復原本機</button>
          </div>)}
          {!syncBackups.length && <p className="help-text">尚未產生本機歷史備份。</p>}
        </section>}
      </section>

      <section className="panel-card">
        <div className="panel-title"><h2>異常設備清單</h2><span>{rows.length} 筆</span></div>
        <p className="help-text" role="status">
          目前篩選符合 {rows.length} 筆異常設備；CSV／Excel 僅匯出此清單。
          {exporting ? ' 正在儲存，已暫時鎖定篩選條件。' : refreshing ? ' 正在更新統計資料…' : ''}
        </p>
        <div className="issue-filters">
          <label>棟別樓層
            <select value={building} disabled={exporting !== null} onChange={(event) => { invalidateExport(); setBuilding(event.target.value) }}>
              <option value="">全部</option>
              {buildings.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label>搜尋設備編號或來源
            <input value={query} disabled={exporting !== null} onChange={(event) => { invalidateExport(); setQuery(event.target.value) }} placeholder="例如 中-03-238" />
          </label>
          <button type="button" disabled={exporting !== null} onClick={() => void refresh().catch((err) => setError(String(err)))}>重新整理</button>
          <button type="button" disabled={exporting !== null || refreshing || rows.length === 0} onClick={() => void saveIssueExport('csv')}>{exporting === 'csv' ? '匯出中…' : '匯出 CSV'}</button>
          <button type="button" disabled={exporting !== null || refreshing || rows.length === 0} onClick={() => void saveIssueExport('xlsx')}>{exporting === 'xlsx' ? '匯出中…' : '匯出 Excel'}</button>
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
          <button type="button" disabled={busy || exporting !== null || !newName.trim()} onClick={() => void createLabel()}>新增分類</button>
        </div>
        <div className="issue-label-list">
          {stats?.labels.map((label) => (
            <div key={label.id} className="issue-label-row">
              <strong>{label.name}</strong>
              <small>{label.count ?? 0} 台{label.active ? '' : ' · 已停用'}</small>
              <button type="button" disabled={busy || exporting !== null} onClick={() => { setEditLabel(label); setEditName(label.name) }}>改名稱</button>
              <button type="button" disabled={busy || exporting !== null} onClick={() => void saveLabel({ active: !label.active }, label.id)}>{label.active ? '停用' : '啟用'}</button>
              <button type="button" disabled={busy || exporting !== null} onClick={() => void saveLabel({ sort_order: Math.max(0, label.sort_order - 1) }, label.id)}>上移</button>
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

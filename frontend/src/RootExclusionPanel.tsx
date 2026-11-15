import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import type { RootExclusionInfo, RootRecord } from './types'

export function RootExclusionPanel({ roots }: { roots: RootRecord[] }) {
  const [rootId, setRootId] = useState<number | null>(roots[0]?.id ?? null)
  const [results, setResults] = useState<Record<number, RootExclusionInfo>>({})
  const [drafts, setDrafts] = useState<Record<number, string[]>>({})
  const dirty = useRef(new Set<number>())
  const [reloadKey, setReloadKey] = useState(0)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (roots.length && !roots.some(root => root.id === rootId)) setRootId(roots[0].id)
    if (!roots.length) setRootId(null)
  }, [roots, rootId])

  useEffect(() => {
    if (rootId === null) return
    let current = true
    setLoading(true); setError('')
    void api.rootExclusionList(rootId).then(result => {
      if (!current) return
      setResults(prev => ({ ...prev, [rootId]: result }))
      if (!dirty.current.has(rootId)) setDrafts(prev => ({ ...prev, [rootId]: result.saved }))
      setLoading(false)
    }).catch(err => {
      if (!current) return
      setError(err instanceof Error ? err.message : '讀取資料夾失敗')
      setLoading(false)
    })
    return () => { current = false }
  }, [rootId, reloadKey])

  const info = rootId === null ? null : results[rootId] ?? null
  const selected = rootId === null ? [] : drafts[rootId] ?? info?.saved ?? []
  const unsaved = rootId !== null && dirty.current.has(rootId)
  const visible = useMemo(() => [...(info?.folders ?? [])]
    .filter(row => row.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()))
    .sort((a, b) => {
      const aChecked = a.locked || selected.some(n => n.toLocaleLowerCase() === a.name.toLocaleLowerCase())
      const bChecked = b.locked || selected.some(n => n.toLocaleLowerCase() === b.name.toLocaleLowerCase())
      return Number(bChecked) - Number(aChecked) || a.name.localeCompare(b.name, 'zh-Hant', { numeric: true })
    }), [info, selected, search])

  function change(name: string, checked: boolean) {
    if (rootId === null) return
    const other = selected.filter(n => n.toLocaleLowerCase() !== name.toLocaleLowerCase())
    dirty.current.add(rootId)
    setDrafts(prev => ({ ...prev, [rootId]: checked ? [...other, name] : other }))
    setMessage('')
  }

  async function save() {
    if (rootId === null || !info || !unsaved || saving || loading || error) return
    const target = rootId
    setSaving(true)
    try {
      const result = await api.saveRootExclusions(target, selected)
      dirty.current.delete(target)
      setDrafts(prev => ({ ...prev, [target]: result.saved }))
      setResults(prev => prev[target]
        ? { ...prev, [target]: { ...prev[target], saved: result.saved } } : prev)
      setMessage('排除設定已儲存，重新掃描後生效；不會刪除實體照片或資料夾。')
      setReloadKey(v => v + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存排除設定失敗')
    } finally { setSaving(false) }
  }

  return <section className="settings-subsection root-exclusion-panel" aria-label="排除掃描資料夾">
    <h3>排除掃描資料夾</h3>
    <p className="help-text">僅排除所選照片根目錄的第一層資料夾；勾選不會刪除照片，儲存後請手動重新掃描。</p>
    <div className="root-exclusion-toolbar">
      <label>照片根目錄
        <select value={rootId ?? ''} disabled={saving} onChange={e => {
          setRootId(Number(e.target.value)); setSearch(''); setError(''); setMessage('')
        }}>{roots.map(root => <option key={root.id} value={root.id}>{root.label}</option>)}</select>
      </label>
      <label>搜尋資料夾
        <input value={search} placeholder="搜尋現有名稱（只篩選）" onChange={e => setSearch(e.target.value)} />
      </label>
      <button className="secondary-button" type="button" disabled={rootId === null || loading || saving}
        onClick={() => setReloadKey(v => v + 1)}>{loading ? '讀取中…' : '重新整理清單'}</button>
    </div>
    {rootId === null && <p className="help-text">請先加入照片根目錄。</p>}
    {error && <p role="alert" className="error-banner">{error}；已保存設定未變更。</p>}
    {info && <div className="root-exclusion-list" aria-label="目前第一層資料夾">
      {visible.map(folder => {
        const checked = folder.locked || selected.some(name => name.toLocaleLowerCase() === folder.name.toLocaleLowerCase())
        return <label key={folder.name} className="root-exclusion-row">
          <input type="checkbox" checked={checked} disabled={folder.locked || saving || loading || Boolean(error)}
            onChange={e => change(folder.name, e.target.checked)} />
          <span>{folder.name}</span>
          <small>{folder.locked ? '系統保護／不可更改' : !folder.present ? '目前未發現（保留排除）' : checked ? '排除掃描' : '允許掃描'}</small>
        </label>
      })}
      {visible.length === 0 && <p className="help-text">{search ? '沒有符合的資料夾' : '此根目錄沒有可選資料夾'}</p>}
    </div>}
    {unsaved && <p role="status" className="slot-unsaved">● 此根目錄有尚未儲存的變更</p>}
    {message && <p role="status" className="stats-message">{message}</p>}
    <button type="button" className="primary-button" onClick={() => void save()}
      disabled={!info || rootId === null || !unsaved || saving || loading || Boolean(error)}>
      {saving ? '儲存中…' : '儲存排除設定'}
    </button>
  </section>
}

import { useEffect, useState } from 'react'
import { api } from './api'
import { confirmDialog } from './AppDialog'
import type { RootRecord } from './types'

/** Schema 14 exclusions belong to a single root; never save a global replacement. */
export function RootExclusionSettings({ roots }: { roots: RootRecord[] }) {
  const [rootId, setRootId] = useState<number | null>(roots[0]?.id ?? null)
  const [names, setNames] = useState<string[] | null>(null)
  const [draft, setDraft] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => {
    if (!roots.some(root => root.id === rootId)) setRootId(roots[0]?.id ?? null)
  }, [roots, rootId])
  useEffect(() => {
    let active = true
    setNames(null); setDirty(false); setDraft(''); setError(''); setMessage('')
    if (rootId === null) return
    void api.rootExclusions(rootId).then(value => { if (active) setNames(value.names) })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : '排除設定讀取失敗') })
    return () => { active = false }
  }, [rootId])
  async function save() {
    if (rootId === null || names === null || saving) return
    setSaving(true); setError(''); setMessage('')
    try {
      const result = await api.saveRootExclusions(rootId, names)
      setNames(result.names); setDirty(false)
      setMessage('此根目錄的排除設定已儲存，下次安全掃描生效。原始資料夾未變更。')
    } catch (err) { setError(err instanceof Error ? err.message : '排除設定儲存失敗') }
    finally { setSaving(false) }
  }
  return <section aria-label="各根目錄排除設定">
    <h3>排除根目錄資料夾</h3>
    <p className="help-text">各根目錄獨立保存第一層資料夾名稱；新根目錄不繼承其他根目錄的排除設定。系統資料夾仍強制排除，不會刪除原圖或資料夾。</p>
    <label>設定哪個根目錄的排除清單
      <select aria-label="排除設定根目錄" value={rootId ?? ''} disabled={saving} onChange={async event => {
        const id = Number(event.target.value)
        if (dirty && !await confirmDialog('此根目錄的排除草稿尚未儲存，確定放棄並切換根目錄？')) return
        setRootId(id)
      }}>
        {roots.map(root => <option key={root.id} value={root.id}>{root.label}</option>)}
      </select>
    </label>
    {!roots.length && <p>請先加入照片根目錄。</p>}
    {error && <p role="alert" className="error-banner">{error}</p>}
    {message && <p role="status">{message}</p>}
    <div className="settings-grid">
      <label>新增排除名稱<input aria-label="新增排除資料夾名稱" value={draft} disabled={names === null || saving}
        onChange={event => setDraft(event.target.value)} placeholder="例如：暫存照片" /></label>
      <button type="button" disabled={!draft.trim() || names === null || saving} onClick={() => {
        const name = draft.trim()
        if (names?.some(value => value.toLowerCase() === name.toLowerCase())) { setError('排除名稱重複'); return }
        setNames([...(names ?? []), name]); setDraft(''); setDirty(true)
      }}>加入排除清單</button>
    </div>
    {(names ?? []).map(name => <div className="settings-row" key={name}><span>{name}</span>
      <button type="button" disabled={saving} onClick={() => { setNames(names!.filter(value => value !== name)); setDirty(true) }}>移除排除</button>
    </div>)}
    {dirty && <p role="status">排除清單尚未儲存</p>}
    <button type="button" disabled={!dirty || saving || names === null} onClick={() => void save()}>
      {saving ? '儲存中…' : '儲存此根目錄排除設定'}
    </button>
  </section>
}

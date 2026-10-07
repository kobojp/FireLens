import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { photosForSlot, slotAllowsAdditional, unmappedPhotos } from './slots'
import { countByStatus, countItems } from './tree'
import { TreeView } from './TreeView'
import { ReconcileView } from './ReconcileView'
import { OrganizerView } from './OrganizerView'
import { SettingsView } from './SettingsView'
import { filterTree } from './treeSearch'
import { normalizeQuickCreate, quickCreateOptions } from './quickCreate'
import type {
  CategoryDefinition,
  ItemDetail,
  ItemFolderCreate,
  PhotoRecord,
  RootRecord,
  RootStatus,
  OfflineQueueEntry,
  AppSettings,
  AppInfo,
  ScanSummary,
  TreeNode,
} from './types'
import './styles.css'

const ACCEPTED_IMAGES = '.jpg,.jpeg,.png,.heic,.heif,image/jpeg,image/png,image/heic,image/heif'

function PhotoTile({
  photo,
  slot,
  isFirst,
  isLast,
  onPreview,
  onReplace,
  onDelete,
  onMoveLeft,
  onMoveRight,
}: {
  photo: PhotoRecord
  slot: string
  isFirst?: boolean
  isLast?: boolean
  onPreview: (photo: PhotoRecord) => void
  onReplace: (slot: string, photoId: number, file: File) => void
  onDelete?: (photo: PhotoRecord) => void
  onMoveLeft?: (photoId: number) => void
  onMoveRight?: (photoId: number) => void
}) {
  return (
    <article className="photo-tile">
      <button
        className="photo-preview-button"
        type="button"
        onClick={() => onPreview(photo)}
        aria-label={`放大預覽 ${photo.filename}`}
      >
        <img src={api.thumbnailUrl(photo)} alt={photo.filename} loading="lazy" />
      </button>
      <div className="photo-meta">
        <b title={photo.filename}>{photo.filename}</b>
        <div className="photo-actions" style={{ display: 'flex', gap: '4px' }}>
          {onMoveLeft && !isFirst && (
            <button type="button" className="icon-button" onClick={() => onMoveLeft(photo.id)} title="向前移">◀</button>
          )}
          {onMoveRight && !isLast && (
            <button type="button" className="icon-button" onClick={() => onMoveRight(photo.id)} title="向後移">▶</button>
          )}
          <label className="secondary-button" style={{ margin: 0 }}>
            換圖
            <input
              className="sr-only"
              type="file"
              accept={ACCEPTED_IMAGES}
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) onReplace(slot, photo.id, file)
                event.currentTarget.value = ''
              }}
            />
          </label>
          {onDelete && (
            <button type="button" className="danger-button" onClick={() => onDelete(photo)}>刪除</button>
          )}
        </div>
      </div>
    </article>
  )
}

function SlotCard({
  item,
  slot,
  disabled,
  onImport,
  onPreview,
  onReplace,
  onDelete,
  onReorder,
  onError,
}: {
  item: ItemDetail
  slot: string
  disabled: boolean
  onImport: (slot: string, file: File) => void
  onPreview: (photo: PhotoRecord) => void
  onReplace: (slot: string, photoId: number, file: File) => void
  onDelete: (photo: PhotoRecord) => void
  onReorder: (slot: string, photoIds: number[]) => void
  onError: (message: string) => void
}) {
  const photos = photosForSlot(item, slot)
  const canAdd = slotAllowsAdditional(item, slot)

  function acceptDrop(event: React.DragEvent<HTMLElement>) {
    event.preventDefault()
    if (disabled) return
    const file = event.dataTransfer.files?.[0]
    if (!file) return
    if (!canAdd) {
      onError(`${slot}槽位已有照片，請使用換圖功能`)
      return
    }
    onImport(slot, file)
  }

  function moveLeft(id: number) {
    const idx = photos.findIndex((p) => p.id === id)
    if (idx > 0) {
      const newOrder = photos.map((p) => p.id)
      const temp = newOrder[idx]
      newOrder[idx] = newOrder[idx - 1]
      newOrder[idx - 1] = temp
      onReorder(slot, newOrder)
    }
  }

  function moveRight(id: number) {
    const idx = photos.findIndex((p) => p.id === id)
    if (idx < photos.length - 1) {
      const newOrder = photos.map((p) => p.id)
      const temp = newOrder[idx]
      newOrder[idx] = newOrder[idx + 1]
      newOrder[idx + 1] = temp
      onReorder(slot, newOrder)
    }
  }

  return (
    <section
      className={`slot-card ${photos.length ? 'filled' : 'empty'}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={acceptDrop}
      aria-label={`${slot}照片槽位`}
    >
      <div className="slot-heading">
        <div>
          <span className="slot-name">{slot}</span>
          <small>{photos.length ? `${photos.length} 張` : '缺照片'}</small>
        </div>
        {canAdd && (
          <label className="add-photo-button" aria-disabled={disabled}>
            ＋ 加入照片
            <input
              className="sr-only"
              type="file"
              accept={ACCEPTED_IMAGES}
              disabled={disabled}
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) onImport(slot, file)
                event.currentTarget.value = ''
              }}
            />
          </label>
        )}
      </div>
      {photos.length === 0 ? (
        <div className="drop-hint">拖曳照片到這裡<br /><small>會自動命名並安全複製</small></div>
      ) : (
        <div className="slot-photos">
          {photos.map((photo, index) => (
            <PhotoTile
              key={photo.id}
              photo={photo}
              slot={slot}
              isFirst={index === 0}
              isLast={index === photos.length - 1}
              onPreview={onPreview}
              onReplace={onReplace}
              onDelete={onDelete}
              onMoveLeft={photos.length > 1 ? moveLeft : undefined}
              onMoveRight={photos.length > 1 ? moveRight : undefined}
            />
          ))}
        </div>
      )}
      {!canAdd && <p className="slot-note">單槽位已有照片；要更換請使用「換圖」。</p>}
    </section>
  )
}

export default function App() {
  const [roots, setRoots] = useState<RootRecord[]>([])
  const [rootId, setRootId] = useState<number | null>(null)
  const [categories, setCategories] = useState<CategoryDefinition[]>([])
  const [nodes, setNodes] = useState<TreeNode[]>([])
  const [selected, setSelected] = useState<TreeNode | null>(null)
  const [item, setItem] = useState<ItemDetail | null>(null)
  const [scanSummary, setScanSummary] = useState<ScanSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [newRootPath, setNewRootPath] = useState('')
  const [showNewItem, setShowNewItem] = useState(false)
  const [showNewPeriod, setShowNewPeriod] = useState(false)
  const [showNewBuilding, setShowNewBuilding] = useState(false)
  const [newPeriodName, setNewPeriodName] = useState('')
  const [newBuildingName, setNewBuildingName] = useState('')
  const [newItem, setNewItem] = useState<Omit<ItemFolderCreate, 'root_id'>>({
    category_code: 'extinguisher',
    year: `${new Date().getFullYear()}年`,
    period: '',
    building: '',
    code: '',
  })
  const [preview, setPreview] = useState<PhotoRecord | null>(null)
  const [photoToDelete, setPhotoToDelete] = useState<PhotoRecord | null>(null)
  const [folderToDelete, setFolderToDelete] = useState<ItemDetail | null>(null)
  const [folderDeleteInput, setFolderDeleteInput] = useState('')
  const [zoom, setZoom] = useState(1)
  const [view, setView] = useState<'browse' | 'reconcile' | 'organizer' | 'settings'>('browse')
  const [rootStatusInfo, setRootStatusInfo] = useState<RootStatus | null>(null)
  const [offlineQueue, setOfflineQueue] = useState<OfflineQueueEntry[]>([])
  const [cacheMessage, setCacheMessage] = useState('')
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [quickCreateHydrated, setQuickCreateHydrated] = useState(false)
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null)
  const [treeQuery, setTreeQuery] = useState('')
  const deferredTreeQuery = useDeferredValue(treeQuery)

  const statusCounts = useMemo(() => countByStatus(nodes), [nodes])
  const extras = item ? unmappedPhotos(item) : []
  const filteredNodes = useMemo(() => filterTree(nodes, deferredTreeQuery), [nodes, deferredTreeQuery])
  const newItemOptions = useMemo(() => quickCreateOptions(nodes, newItem), [
    nodes,
    newItem.category_code,
    newItem.year,
    newItem.period,
  ])
  const orderedSlots = useMemo(() => {
    if (!item) return []
    const preferred = appSettings?.slot_order[item.category_code]
    const base = preferred && preferred.length === item.slots.length ? preferred : item.slots
    const custom = item.custom_slots || []
    return [...base, ...custom]
  }, [item, appSettings])

  async function refreshRoots() {
    try {
      const next = await api.listRoots()
      setRoots(next)
      setRootId((current) => current ?? next[0]?.id ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取根目錄失敗')
    }
  }

  async function refreshTree(id: number) {
    const next = await api.tree(id)
    setNodes(next)
  }

  async function refreshCacheState(id: number) {
    const [status, queue] = await Promise.all([api.rootStatus(id), api.offlineQueue(id)])
    setRootStatusInfo(status)
    setOfflineQueue(queue)
  }

  async function syncOffline() {
    if (rootId === null) return
    setBusy(true)
    setError('')
    setCacheMessage('')
    try {
      const result = await api.syncOffline(rootId)
      await Promise.all([refreshTree(rootId), refreshCacheState(rootId)])
      setCacheMessage(`離線同步完成：成功 ${result.synced.length} 筆，待處理 ${result.failed.length} 筆。`)
      if (item?.id) setItem(await api.item(item.id).catch(() => item))
    } catch (err) {
      setError(err instanceof Error ? err.message : '離線同步失敗')
      await refreshCacheState(rootId).catch(() => undefined)
    } finally {
      setBusy(false)
    }
  }

  async function buildThumbnailCache() {
    if (rootId === null) return
    setBusy(true)
    setError('')
    setCacheMessage('')
    try {
      const result = await api.cacheThumbnails(rootId)
      await refreshCacheState(rootId)
      setCacheMessage(`縮圖快取完成：新增 ${result.created} 張，失敗 ${result.failed} 張。`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '建立縮圖快取失敗')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void refreshRoots()
    void api.categories().then(setCategories).catch((err) => {
      setError(err instanceof Error ? err.message : '讀取類別設定失敗')
    })
    void api.settings().then((settings) => {
      setAppSettings(settings)
      setNewItem((current) => ({ ...current, ...settings.quick_create }))
      setQuickCreateHydrated(true)
    }).catch((err) => {
      setError(err instanceof Error ? err.message : '讀取應用設定失敗')
    })
    void api.appInfo().then(setAppInfo).catch(() => undefined)
  }, [])

  useEffect(() => {
    const theme = appSettings?.theme ?? 'system'
    if (theme === 'system') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
  }, [appSettings?.theme])

  useEffect(() => {
    if (!quickCreateHydrated || nodes.length === 0) return
    setNewItem((current) => ({ ...current, ...normalizeQuickCreate(nodes, current) }))
  }, [nodes, quickCreateHydrated])

  useEffect(() => {
    if (!appSettings || !quickCreateHydrated) return
    const quickCreate = {
      category_code: newItem.category_code,
      year: newItem.year,
      period: newItem.period,
      building: newItem.building,
    }
    if (
      appSettings.quick_create.category_code === quickCreate.category_code
      && appSettings.quick_create.year === quickCreate.year
      && appSettings.quick_create.period === quickCreate.period
      && appSettings.quick_create.building === quickCreate.building
    ) return
    const timeout = window.setTimeout(() => {
      void api.saveSettings({ ...appSettings, quick_create: quickCreate })
        .then(setAppSettings)
        .catch((err) => setError(err instanceof Error ? err.message : '記錄快速建立設定失敗'))
    }, 250)
    return () => window.clearTimeout(timeout)
  }, [
    appSettings,
    newItem.category_code,
    newItem.year,
    newItem.period,
    newItem.building,
  ])

  useEffect(() => {
    setSelected(null)
    setItem(null)
    if (rootId === null) {
      setNodes([])
      return
    }
    setError('')
    void refreshTree(rootId).catch((err) => {
      setError(err instanceof Error ? err.message : '讀取樹狀資料失敗')
    })
    void refreshCacheState(rootId).catch((err) => {
      setError(err instanceof Error ? err.message : '讀取快取狀態失敗')
    })
  }, [rootId])

  async function addRoot() {
    const path = newRootPath.trim()
    if (!path) return
    setBusy(true)
    setError('')
    try {
      const created = await api.addRoot(path)
      setNewRootPath('')
      await refreshRoots()
      setRootId(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增根目錄失敗')
    } finally {
      setBusy(false)
    }
  }

  async function scan() {
    if (rootId === null) return
    setBusy(true)
    setError('')
    try {
      setScanSummary(await api.scanRoot(rootId))
      await refreshTree(rootId)
      await refreshCacheState(rootId)
      setSelected(null)
      setItem(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '掃描失敗')
    } finally {
      setBusy(false)
    }
  }

  async function selectItem(node: TreeNode) {
    setSelected(node)
    setItem(null)
    if (node.id === undefined) return
    try {
      setItem(await api.item(node.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取照片資料失敗')
    }
  }

  async function upload(slot: string, file: File, replacePhotoId?: number) {
    if (!item || rootId === null) return
    setBusy(true)
    setError('')
    try {
      const updated = await api.importPhoto(item.id, slot, file, replacePhotoId)
      setItem(updated)
      await refreshTree(rootId)
      await refreshCacheState(rootId)
      if (updated.offline_queued) {
        setCacheMessage('根目錄目前離線；照片已安全存入本機離線工作區，重新連線後可同步。')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '照片匯入失敗')
    } finally {
      setBusy(false)
    }
  }

  async function confirmDeleteItemFolder() {
    if (!folderToDelete || rootId === null) return
    
    setBusy(true)
    setError('')
    try {
      await api.deleteItem(folderToDelete.id)
      await refreshTree(rootId)
      setSelected(null)
      setItem(null)
      setFolderToDelete(null)
      setFolderDeleteInput('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除資料夾失敗')
    } finally {
      setBusy(false)
    }
  }

  async function confirmDeletePhoto() {
    if (!photoToDelete || rootId === null) return
    setBusy(true)
    setError('')
    try {
      const updated = await api.deletePhoto(photoToDelete.id)
      setItem(updated)
      await refreshTree(rootId)
      await refreshCacheState(rootId)
      setPhotoToDelete(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除照片失敗')
    } finally {
      setBusy(false)
    }
  }

  async function reorderSlotPhotos(slot: string, photoIds: number[]) {
    if (!item || rootId === null) return
    setBusy(true)
    setError('')
    try {
      const updated = await api.reorderPhotos(item.id, slot, photoIds)
      setItem(updated)
      await refreshTree(rootId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '調整順序失敗')
    } finally {
      setBusy(false)
    }
  }

  async function createNumberFolder() {
    if (rootId === null) return
    setBusy(true)
    setError('')
    try {
      const created = await api.createItem({ root_id: rootId, ...newItem })
      await refreshTree(rootId)
      setSelected({
        type: 'item',
        key: String(created.id),
        id: created.id,
        label: created.code,
        status: created.status,
        photo_count: created.photo_count,
      })
      setItem(created)
      setNewItem((current) => ({ ...current, code: '' }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增編號資料夾失敗')
    } finally {
      setBusy(false)
    }
  }

  async function createPeriod() {
    if (rootId === null || !newItem.year.trim() || !newPeriodName.trim()) return
    setBusy(true)
    setError('')
    setCacheMessage('')
    try {
      const created = await api.createPeriodFolder({
        root_id: rootId,
        category_code: newItem.category_code,
        year: newItem.year,
        period: newPeriodName.trim(),
      })
      await refreshTree(rootId)
      setNewItem((current) => ({ ...current, period: created.period, building: '' }))
      setNewPeriodName('')
      setShowNewPeriod(false)
      setCacheMessage(`${created.created ? '已建立' : '已登記'}月份/批次：${created.period}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增月份/批次失敗')
    } finally {
      setBusy(false)
    }
  }

  async function createBuilding() {
    if (rootId === null || !newItem.year.trim() || !newItem.period.trim() || !newBuildingName.trim()) return
    setBusy(true)
    setError('')
    setCacheMessage('')
    try {
      const created = await api.createBuildingFolder({
        root_id: rootId,
        category_code: newItem.category_code,
        year: newItem.year,
        period: newItem.period,
        building: newBuildingName.trim(),
      })
      await refreshTree(rootId)
      setNewItem((current) => ({ ...current, building: created.building ?? newBuildingName.trim() }))
      setNewBuildingName('')
      setShowNewBuilding(false)
      setCacheMessage(`${created.created ? '已建立' : '已登記'}棟別：${created.building}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增棟別失敗')
    } finally {
      setBusy(false)
    }
  }

  function openPreview(photo: PhotoRecord) {
    setPreview(photo)
    setZoom(1)
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <strong>FireLens</strong>
          <span>照片管理、核對與離線工作 · v{appInfo?.version ?? '1.1.0'}</span>
        </div>
        <div className="root-controls">
          <label htmlFor="root-select">根目錄</label>
          <select id="root-select" value={rootId ?? ''} onChange={(event) => setRootId(Number(event.target.value))}>
            {roots.length === 0 && <option value="">尚未設定</option>}
            {roots.map((root) => <option key={root.id} value={root.id}>{root.label}</option>)}
          </select>
          <button type="button" onClick={() => void scan()} disabled={rootId === null || busy}>
            {busy ? '處理中…' : '重新掃描'}
          </button>
          {rootStatusInfo && (
            <span className={`connection-badge ${rootStatusInfo.connected ? 'online' : 'offline'}`}>
              {rootStatusInfo.connected ? '已連線' : '離線快取'}
              {rootStatusInfo.pending_imports > 0 ? ` · 待同步 ${rootStatusInfo.pending_imports}` : ''}
            </span>
          )}
        </div>
      </header>

      <nav className="mode-tabs" aria-label="FireLens 功能">
        <button type="button" className={view === 'browse' ? 'active' : ''} onClick={() => setView('browse')}>照片瀏覽</button>
        <button type="button" className={view === 'reconcile' ? 'active' : ''} onClick={() => setView('reconcile')}>清冊核對</button>
        <button type="button" className={view === 'organizer' ? 'active' : ''} onClick={() => setView('organizer')}>整理工具</button>
        <button type="button" className={view === 'settings' ? 'active' : ''} onClick={() => setView('settings')}>設定</button>
      </nav>

      {view === 'browse' ? (
        <>
      <section className="root-add" aria-label="照片根目錄工具列">
        <label htmlFor="new-root">新增根目錄</label>
        <input
          id="new-root"
          value={newRootPath}
          onChange={(event) => setNewRootPath(event.target.value)}
          placeholder="輸入照片根目錄路徑"
          disabled={busy}
        />
        <button type="button" onClick={() => void addRoot()} disabled={busy || !newRootPath.trim()}>加入</button>
        <button type="button" className="outline-button" onClick={() => setShowNewItem((value) => !value)} disabled={rootId === null}>
          ＋ 新增編號資料夾
        </button>
        <button type="button" className="outline-button" onClick={() => void buildThumbnailCache()} disabled={busy || rootId === null || rootStatusInfo?.connected === false}>建立縮圖快取</button>
        <button type="button" className="outline-button" onClick={() => void syncOffline()} disabled={busy || rootId === null || !rootStatusInfo?.connected || rootStatusInfo.pending_imports === 0}>同步離線照片</button>
      </section>

      {showNewItem && (
        <section className="new-item-form" aria-label="新增編號資料夾">
          <label>類別
            <select value={newItem.category_code} onChange={(event) => setNewItem((current) => ({
              ...current,
              ...normalizeQuickCreate(nodes, {
                category_code: event.target.value,
                year: current.year,
                period: current.period,
                building: current.building,
              }),
            }))}>
              {categories.map((category) => <option key={category.code} value={category.code}>{category.name}</option>)}
            </select>
          </label>
          <label>年份
            <select value={newItem.year} onChange={(event) => setNewItem((current) => ({
              ...current,
              ...normalizeQuickCreate(nodes, {
                category_code: current.category_code,
                year: event.target.value,
                period: '',
                building: current.building,
              }),
            }))}>
              {newItemOptions.years.length === 0 && <option value="">尚無可用年份</option>}
              {newItemOptions.years.map((year) => <option key={year} value={year}>{year}</option>)}
            </select>
          </label>
          <div className="new-item-field">
            <label>月份/批次
              <div className="select-action">
                <select value={newItem.period} onChange={(event) => setNewItem((current) => ({
                  ...current,
                  ...normalizeQuickCreate(nodes, {
                    category_code: current.category_code,
                    year: current.year,
                    period: event.target.value,
                    building: current.building,
                  }),
                }))}>
                  {newItemOptions.periods.length === 0 && <option value="">尚無可用月份/批次</option>}
                  {newItemOptions.periods.map((period) => <option key={period} value={period}>{period}</option>)}
                </select>
                <button type="button" className="mini-add-button" onClick={() => setShowNewPeriod((value) => !value)} disabled={busy || !newItem.year.trim()}>＋</button>
              </div>
            </label>
            {showNewPeriod && (
              <div className="inline-folder-create">
                <input value={newPeriodName} onChange={(event) => setNewPeriodName(event.target.value)} placeholder="例：11月份更換" />
                <button type="button" onClick={() => void createPeriod()} disabled={busy || !newPeriodName.trim()}>新增</button>
              </div>
            )}
          </div>
          <div className="new-item-field">
            <label>棟別
              <div className="select-action">
                <select value={newItem.building} onChange={(event) => setNewItem({ ...newItem, building: event.target.value })}>
                  {newItemOptions.buildings.length === 0 && <option value="">尚無可用棟別</option>}
                  {newItemOptions.buildings.map((building) => <option key={building} value={building}>{building}</option>)}
                </select>
                <button type="button" className="mini-add-button" onClick={() => setShowNewBuilding((value) => !value)} disabled={busy || !newItem.period.trim()}>＋</button>
              </div>
            </label>
            {showNewBuilding && (
              <div className="inline-folder-create">
                <input value={newBuildingName} onChange={(event) => setNewBuildingName(event.target.value)} placeholder="例：中正樓" />
                <button type="button" onClick={() => void createBuilding()} disabled={busy || !newBuildingName.trim()}>新增</button>
              </div>
            )}
          </div>
          <label>編號
            <input autoFocus placeholder="例：中-01-01" value={newItem.code} onChange={(event) => setNewItem({ ...newItem, code: event.target.value })} />
          </label>
          <button
            type="button"
            onClick={() => void createNumberFolder()}
            disabled={busy || !newItem.year.trim() || !newItem.period.trim() || !newItem.building.trim() || !newItem.code.trim()}
          >
            建立資料夾
          </button>
          <small>月份與棟別右側「＋」可直接建立新的實體資料夾；類別、年份、月份與棟別會記住上次選擇，連續建立時只要輸入編號。</small>
        </section>
      )}

      {error && <div className="error-banner" role="alert">{error}</div>}
      {cacheMessage && <div className="success-banner" role="status">{cacheMessage}</div>}

      <section className="workspace">
        <aside className="panel tree-panel" aria-label="照片資料夾樹">
          <div className="panel-title"><h2>資料樹</h2><span>{countItems(filteredNodes)} / {countItems(nodes)} 筆</span></div>
          <input className="tree-search" type="search" value={treeQuery} onChange={(event) => setTreeQuery(event.target.value)} placeholder="搜尋棟別、月份或設備編號" aria-label="搜尋照片資料樹" />
          <TreeView nodes={filteredNodes} selectedId={selected?.id ?? null} onSelectItem={(node) => void selectItem(node)} expandAll={Boolean(deferredTreeQuery.trim())} />
        </aside>

        <section className="panel photo-panel" aria-label="照片槽位牆">
          <div className="panel-title">
            <div><h2>{item?.code ?? '照片槽位'}</h2>{item && <small>{item.category_name} · {item.building}</small>}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {item && (
                <button type="button" className="danger-button" onClick={() => setFolderToDelete(item)} disabled={busy}>
                  刪除
                </button>
              )}
              <span>{item ? item.status : 'M2'}</span>
            </div>
          </div>
          {!item && <div className="empty-state"><b>選擇左側編號</b><p>選定設備後，可直接把照片拖到「編號／藥劑／完成」或「前／中／後」槽位。</p></div>}
          {item && (
            <>
              <div className="slot-wall">
                {orderedSlots.map((slot) => (
                  <SlotCard
                    key={slot}
                    item={item}
                    slot={slot}
                    disabled={busy}
                    onImport={(targetSlot, file) => void upload(targetSlot, file)}
                    onPreview={openPreview}
                    onReplace={(targetSlot, photoId, file) => void upload(targetSlot, file, photoId)}
                    onDelete={(photo) => setPhotoToDelete(photo)}
                    onReorder={(targetSlot, photoIds) => void reorderSlotPhotos(targetSlot, photoIds)}
                    onError={setError}
                  />
                ))}
              </div>
              {extras.length > 0 && (
                <section className="unmapped-section">
                  <h3>未對應／舊制照片 <span>{extras.length}</span></h3>
                  <div className="unmapped-list">
                    {extras.map((photo) => (
                      <button key={photo.id} type="button" onClick={() => openPreview(photo)} className="unmapped-photo">
                        <img src={api.photoUrl(photo)} alt="" loading="lazy" />
                        <span>{photo.filename}</span>
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </section>

        <aside className="panel info-panel" aria-label="掃描資訊">
          <div className="panel-title"><h2>資訊</h2></div>
          <dl className="stats">
            <div><dt>項目</dt><dd>{countItems(nodes)}</dd></div>
            <div><dt>完整</dt><dd>{statusCounts.complete ?? 0}</dd></div>
            <div><dt>部分</dt><dd>{statusCounts.partial ?? 0}</dd></div>
            <div><dt>舊制</dt><dd>{statusCounts.legacy ?? 0}</dd></div>
            <div><dt>空資料夾</dt><dd>{statusCounts.empty ?? 0}</dd></div>
          </dl>
          {item && (
            <div className="item-info">
              <b>{item.code}</b>
              <p>{item.year} / {item.period}</p>
              <p>{item.building}</p>
              <p>{item.photo_count} 張照片</p>
            </div>
          )}
          {rootStatusInfo && (
            <div className="scan-summary">
              <b>{rootStatusInfo.connected ? '根目錄已連線' : '目前使用離線快取'}</b>
              <p>{rootStatusInfo.cached_items} 個索引項目 / {rootStatusInfo.cached_photos} 張照片</p>
              <p>{rootStatusInfo.cached_thumbnails} 張縮圖快取 / {rootStatusInfo.cloud_placeholders} 張雲端未下載</p>
              {offlineQueue.filter((row) => row.state !== 'synced').length > 0 && (
                <p>離線工作區待同步 {offlineQueue.filter((row) => row.state !== 'synced').length} 筆</p>
              )}
            </div>
          )}
          {scanSummary && <div className="scan-summary"><b>最近掃描</b><p>{scanSummary.items} 個項目 / {scanSummary.photos} 張照片</p></div>}
          <div className="notice"><b>寫入保護</b><p>匯入使用暫存檔 → 原子換名 → SHA-256 驗證；既有檔名不會被直接覆蓋。</p></div>
          <div className="notice"><b>來源照片不變</b><p>拖入的原始照片只讀取內容，FireLens 只在目標設備資料夾建立副本。</p></div>
        </aside>
      </section>

      {preview && (
        <div className="preview-backdrop" role="presentation" onMouseDown={() => setPreview(null)}>
          <section className="preview-dialog" role="dialog" aria-modal="true" aria-label={`預覽 ${preview.filename}`} onMouseDown={(event) => event.stopPropagation()}>
            <div className="preview-toolbar">
              <b>{preview.filename}</b>
              <label>縮放
                <input type="range" min="0.5" max="3" step="0.1" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} />
                <span>{Math.round(zoom * 100)}%</span>
              </label>
              <button type="button" onClick={() => setPreview(null)} aria-label="關閉照片預覽">關閉</button>
            </div>
            <div className="preview-canvas">
              <img src={api.photoUrl(preview)} alt={preview.filename} style={{ transform: `scale(${zoom})` }} />
            </div>
          </section>
        </div>
      )}
        </>
      ) : view === 'reconcile' ? (
        <ReconcileView roots={roots} defaultRootId={rootId} />
      ) : view === 'organizer' ? (
        <OrganizerView roots={roots} defaultRootId={rootId} />
      ) : (
        <SettingsView
          roots={roots}
          categories={categories}
          settings={appSettings}
          appInfo={appInfo}
          onSettingsChanged={setAppSettings}
          onRootsChanged={async () => { await refreshRoots(); if (rootId) await refreshCacheState(rootId).catch(() => undefined) }}
          onCategoriesChanged={async () => { setCategories(await api.categories()) }}
        />
      )}

      {folderToDelete && (
        <div className="preview-backdrop" onClick={() => { setFolderToDelete(null); setFolderDeleteInput('') }}>
          <div className="prompt-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="prompt-header">刪除資料夾</div>
            <div className="prompt-body">
              <p>請輸入資料夾名稱 <strong>{folderToDelete.code}</strong> 確認刪除：</p>
              <p style={{ marginTop: '8px', color: '#b34526', fontSize: '13px' }}>注意：這會將此資料夾與內部照片一併徹底刪除！</p>
              <input 
                className="prompt-input" 
                autoFocus
                placeholder={folderToDelete.code}
                value={folderDeleteInput} 
                onChange={e => setFolderDeleteInput(e.target.value)} 
              />
            </div>
            <div className="prompt-footer">
              <button type="button" onClick={() => { setFolderToDelete(null); setFolderDeleteInput('') }}>取消</button>
              <button 
                type="button" 
                className="danger" 
                onClick={() => void confirmDeleteItemFolder()} 
                disabled={busy || folderDeleteInput !== folderToDelete.code}
              >確定</button>
            </div>
          </div>
        </div>
      )}

      {photoToDelete && (
        <div className="preview-backdrop" onClick={() => setPhotoToDelete(null)}>
          <div className="prompt-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="prompt-header">刪除照片</div>
            <div className="prompt-body">
              <p>確定要刪除照片 <strong>{photoToDelete.filename}</strong> 嗎？</p>
              <p style={{ marginTop: '8px', color: '#b34526', fontSize: '13px' }}>此操作會直接刪除磁碟檔案且無法還原！</p>
            </div>
            <div className="prompt-footer">
              <button type="button" onClick={() => setPhotoToDelete(null)}>取消</button>
              <button type="button" className="danger" onClick={() => void confirmDeletePhoto()} disabled={busy}>確定</button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}

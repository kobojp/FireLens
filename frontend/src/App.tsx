import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { initialNewItemPanelOpen, newItemPanelButtonText } from './newItemPanel'
import { photosForSlot, slotAllowsAdditional, unmappedPhotos } from './slots'
import { fromPaste, hasDesktopClipboardBridge, readDesktopClipboardImage } from './clipboardImage'
import { scanSummaryText, shouldAutoScan } from './scanPolicy'
import {
  branchPathKey, countByStatus, countItems, itemBranchPath,
  revealCreatedBranch, toggleTreeBranch,
} from './tree'
import { TreeView } from './TreeView'
import type { TreeCreatePath } from './TreeView'
import { ReconcileView } from './ReconcileView'
import { OrganizerView } from './OrganizerView'
import { PhotoQualityView } from './PhotoQualityView'
import { SettingsView } from './SettingsView'
import { PublicSheetsView } from './PublicSheetsView'
import { StatisticsView } from './StatisticsView'
import { filterTree } from './treeSearch'
import { normalizeQuickCreate, quickCreateOptions } from './quickCreate'
import type {
  CategoryDefinition,
  ItemDetail,
  ItemFolderCreate,
  IssueLabel,
  PhotoRenamePreview,
  PhotoSlotTransferPreview,
  PhotoRecord,
  RootRecord,
  RootStatus,
  OfflineQueueEntry,
  AppSettings,
  AppInfo,
  ScanJobStatus,
  ScanSummary,
  TreeNode,
} from './types'
import './styles.css'

const ACCEPTED_IMAGES = '.jpg,.jpeg,.png,.heic,.heif,image/jpeg,image/png,image/heic,image/heif'
const INTERNAL_PHOTO_DRAG_TYPE = 'application/x-firelens-photo-id'

type RenameDialogState = {
  photo: PhotoRecord
  targetFilename: string
  reason: string
  preview: PhotoRenamePreview | null
}

function PhotoTile({
  photo,
  slot,
  isFirst,
  isLast,
  onPreview,
  onReplace,
  onRename,
  onDelete,
  onMoveLeft,
  onMoveRight,
  onTransfer,
  canDrag,
}: {
  photo: PhotoRecord
  slot: string
  isFirst?: boolean
  isLast?: boolean
  onPreview: (photo: PhotoRecord) => void
  onReplace: (slot: string, photoId: number, file: File) => void
  onRename?: (photo: PhotoRecord) => void
  onDelete?: (photo: PhotoRecord) => void
  onMoveLeft?: (photoId: number) => void
  onMoveRight?: (photoId: number) => void
  onTransfer?: (photo: PhotoRecord) => void
  canDrag?: boolean
}) {
  return (
    <article className="photo-tile" draggable={canDrag}
      onDragStart={(event) => {
        if (!canDrag) { event.preventDefault(); return }
        event.dataTransfer.setData(INTERNAL_PHOTO_DRAG_TYPE, String(photo.id))
        event.dataTransfer.effectAllowed = 'move'
      }}>
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
        <div className="photo-actions" role="group" aria-label={`${photo.filename} 照片操作`}>
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
          {onRename && (
            <button type="button" className="secondary-button" onClick={() => onRename(photo)}>重新命名</button>
          )}
          {onTransfer && <button type="button" className="secondary-button"
            onClick={() => onTransfer(photo)}>移動／交換</button>}
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
  onAssignExisting,
  onRename,
  onTransfer,
  onError,
  onChooseSlot,
  onPasteImage,
  selectedForPaste,
  clipboardAvailable,
}: {
  item: ItemDetail
  slot: string
  disabled: boolean
  onImport: (slot: string, file: File) => void
  onPreview: (photo: PhotoRecord) => void
  onReplace: (slot: string, photoId: number, file: File) => void
  onDelete: (photo: PhotoRecord) => void
  onReorder: (slot: string, photoIds: number[]) => void
  onAssignExisting: (slot: string, photoId: number) => void
  onRename: (photo: PhotoRecord) => void
  onTransfer: (photo: PhotoRecord) => void
  onError: (message: string) => void
  onChooseSlot: (slot: string) => void
  onPasteImage: (slot: string) => void
  selectedForPaste: boolean
  clipboardAvailable: boolean | null
}) {
  const photos = photosForSlot(item, slot)
  const canAdd = slotAllowsAdditional(item, slot)
  const [dragActive, setDragActive] = useState(false)

  function acceptDrop(event: React.DragEvent<HTMLElement>) {
    event.preventDefault()
    setDragActive(false)
    if (disabled) return
    const existingPhotoId = Number(event.dataTransfer.getData(INTERNAL_PHOTO_DRAG_TYPE))
    if (Number.isInteger(existingPhotoId) && existingPhotoId > 0) {
      onAssignExisting(slot, existingPhotoId)
      return
    }
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
      className={`slot-card ${photos.length ? 'filled' : 'empty'} ${dragActive ? 'drag-target' : ''} ${selectedForPaste ? 'paste-selected' : ''}`}
      onClick={() => onChooseSlot(slot)}
      onDragEnter={(event) => { event.preventDefault(); if (!disabled) setDragActive(true) }}
      onDragOver={(event) => { event.preventDefault(); if (!disabled) setDragActive(true) }}
      onDragLeave={() => setDragActive(false)}
      onDrop={acceptDrop}
      aria-label={`${slot}照片槽位`}
    >
      <div className="slot-heading">
        <div>
          <span className="slot-name">{slot}</span>
          <small>{photos.length ? `${photos.length} 張` : '缺照片'}</small>
        </div>
        <div className="slot-heading-actions">
        <button type="button" className="paste-photo-button"
          onClick={() => { onChooseSlot(slot); onPasteImage(slot) }}
          disabled={disabled || !canAdd}
          title="貼上剪貼簿圖片（Windows 桌面版直接貼上，瀏覽器請按 Ctrl+V）"
        >貼上照片</button>
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
              onRename={onRename}
              onTransfer={!disabled && !photo.cloud_placeholder ? onTransfer : undefined}
              canDrag={!disabled && !photo.cloud_placeholder}
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
  const [showNewItem, setShowNewItem] = useState(initialNewItemPanelOpen(undefined))
  const [treeCreatePath, setTreeCreatePath] = useState<TreeCreatePath | null>(null)
  const [treeCreateName, setTreeCreateName] = useState('')
  // Each photo root has independent, persistent expanded/collapsed branches.
  const [expandedByRoot, setExpandedByRoot] = useState<Record<number, string[]>>({})
  const [treeReveal, setTreeReveal] = useState<{ rootId: number, path: string } | null>(null)
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
  const [pasteSlot, setPasteSlot] = useState<string | null>(null)
  const [clipboardAvailable, setClipboardAvailable] = useState<boolean | null>(null)
  const [showPasteHelp, setShowPasteHelp] = useState(false)
  const [pendingPaste, setPendingPaste] = useState<{ rootId: number, itemId: number, slot: string, file: File, previewUrl: string } | null>(null)
  const [duplicateUpload, setDuplicateUpload] = useState<{ itemId: number; slot: string; file: File; replacePhotoId?: number; reason: string } | null>(null)
  const [photoToDelete, setPhotoToDelete] = useState<PhotoRecord | null>(null)
  const [renameDialog, setRenameDialog] = useState<RenameDialogState | null>(null)
  const [lastTransfer, setLastTransfer] = useState<{ rootId: number, itemId: number, logId: number } | null>(null)
  const [slotTransfer, setSlotTransfer] = useState<{
    source: PhotoRecord
    targetSlot: string
    targetPhotoId: number | null
    preview: PhotoSlotTransferPreview | null
  } | null>(null)
  const [lastRename, setLastRename] = useState<{
    logId: number; itemId: number; rootId: number; source: string; target: string
  } | null>(null)
  const [folderToDelete, setFolderToDelete] = useState<ItemDetail | null>(null)
  const [folderDeleteInput, setFolderDeleteInput] = useState('')
  const [folderRename, setFolderRename] = useState<ItemDetail | null>(null)
  const [newFolderName, setNewFolderName] = useState('')
  const [issueLabels, setIssueLabels] = useState<IssueLabel[]>([])
  const [issueSelection, setIssueSelection] = useState<number | null>(null)
  const [zoom, setZoom] = useState(1)
  const [view, setView] = useState<'browse' | 'reconcile' | 'statistics' | 'organizer' | 'quality' | 'settings' | 'publicSheets'>('browse')
  const [rootStatusInfo, setRootStatusInfo] = useState<RootStatus | null>(null)
  const [offlineQueue, setOfflineQueue] = useState<OfflineQueueEntry[]>([])
  const [cacheMessage, setCacheMessage] = useState('')
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [quickCreateHydrated, setQuickCreateHydrated] = useState(false)
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null)
  const [scanJob, setScanJob] = useState<ScanJobStatus | null>(null)
  const [treeQuery, setTreeQuery] = useState('')
  const activeRootRef = useRef<number | null>(null)
  const selectedItemIdRef = useRef<number | null>(null)
  const photoPanelRef = useRef<HTMLElement>(null)
  const pendingStatsNavigation = useRef<{ rootId: number; itemId: number } | null>(null)
  const scanMonitorToken = useRef(0)
  const autoScanAttempted = useRef(new Set<number>())
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
  useEffect(() => { setSlotTransfer(null) }, [item?.id, rootId])

  useEffect(() => {
    const selected = item
    if (!selected || rootId === null) { setLastTransfer(null); return }
    let active = true
    setLastTransfer(null)
    void api.recentSlotTransfers(selected.id).then((rows) => {
      if (!active) return
      const latest = rows.find((row) => !row.reverted_at)
      setLastTransfer(latest ? { rootId: latest.root_id, itemId: selected.id, logId: latest.id } : null)
    }).catch((err) => { if (active) setError(err instanceof Error ? err.message : '無法載入照片交換紀錄') })
    return () => { active = false }
  }, [item?.id, rootId])


  const orderedSlots = useMemo(() => {
    if (!item) return []
    const preferred = appSettings?.slot_order[item.category_code]
    const base = preferred && preferred.length === item.slots.length ? preferred : item.slots
    const custom = item.custom_slots || []
    return [...base, ...custom]
  }, [item, appSettings])
  const scanRunning = rootId !== null && scanJob?.root_id === rootId && scanJob.state === 'running'

  useEffect(() => {
    setIssueSelection(null)
    if (!item) return
    let active = true
    void api.itemIssue(item.id)
      .then((issue) => { if (active) setIssueSelection(issue.label_id) })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : '讀取設備異常失敗') })
    return () => { active = false }
  }, [item?.id, item?.relative_path])

  async function refreshRoots() {
    try {
      const next = await api.listRoots()
      setRoots(next)
      setRootId((current) => current ?? next[0]?.id ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取根目錄失敗')
    }
  }

  async function refreshIssueLabels() {
    setIssueLabels(await api.issueLabels())
  }

  async function changeIssue(value: string) {
    if (!item) return
    setBusy(true)
    setError('')
    try {
      const next = await api.setItemIssue(item.id, value ? Number(value) : null)
      setIssueSelection(next.label_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存異常標記失敗')
    } finally {
      setBusy(false)
    }
  }

  async function confirmFolderRename() {
    if (!folderRename || rootId === null || scanRunning) return
    setBusy(true)
    setError('')
    try {
      await api.renameItemFolder(folderRename.id, newFolderName)
      const updated = await api.item(folderRename.id)
      setItem(updated)
      setSelected((current) => current ? { ...current, label: updated.code } : current)
      await refreshTree(rootId)
      setFolderRename(null)
      setCacheMessage(`資料夾已更名為 ${updated.code}；照片內容保持不變。`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '資料夾更名失敗')
    } finally {
      setBusy(false)
    }
  }

  async function refreshTree(id: number) {
    const [next, definitions] = await Promise.all([api.tree(id), api.categories()])
    setNodes(next)
    setCategories(definitions)
  }

  async function refreshCacheState(id: number) {
    const [status, queue] = await Promise.all([api.rootStatus(id), api.offlineQueue(id)])
    setRootStatusInfo(status)
    setOfflineQueue(queue)
  }

  async function syncOffline() {
    if (rootId === null) return
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再同步離線照片。')
      return
    }
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
    void refreshIssueLabels().catch((err) => setError(err instanceof Error ? err.message : '讀取異常分類失敗'))
    void api.categories().then(setCategories).catch((err) => {
      setError(err instanceof Error ? err.message : '讀取類別設定失敗')
    })
    void api.settings().then((settings) => {
      setAppSettings(settings)
      setNewItem((current) => ({ ...current, ...settings.quick_create }))
      setShowNewItem(initialNewItemPanelOpen(settings.new_item_panel_open))
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
    selectedItemIdRef.current = item?.id ?? null
  }, [item?.id])

  useEffect(() => {
    activeRootRef.current = rootId
    scanMonitorToken.current += 1
    setSelected(null)
    setItem(null)
    if (rootId === null) {
      setNodes([])
      setScanJob(null)
      return
    }
    setError('')
    void refreshTree(rootId).catch((err) => {
      setError(err instanceof Error ? err.message : '讀取樹狀資料失敗')
    })
    void refreshCacheState(rootId).catch((err) => {
      setError(err instanceof Error ? err.message : '讀取快取狀態失敗')
    })
    void api.scanStatus(rootId).then((status) => {
      if (activeRootRef.current !== rootId) return
      setScanJob(status)
      if (status.state === 'running') void monitorScan(rootId)
    }).catch(() => undefined)
  }, [rootId])

  useEffect(() => {
    const target = pendingStatsNavigation.current
    if (!target || view !== 'browse' || target.rootId !== rootId) return
    let active = true
    void api.item(target.itemId).then((detail) => {
      if (!active) return
      setItem(detail)
      setSelected({ type: 'item', id: detail.id, key: `item:${detail.id}`, label: detail.code })
      pendingStatsNavigation.current = null
    }).catch((err) => { if (active) setError(err instanceof Error ? err.message : '開啟設備失敗') })
    return () => { active = false }
  }, [rootId, view])

  useEffect(() => {
    if (rootId === null || !appSettings || !rootStatusInfo) return
    if (rootStatusInfo.root_id !== rootId || autoScanAttempted.current.has(rootId)) return
    autoScanAttempted.current.add(rootId)
    if (!appSettings.auto_scan_on_start || !rootStatusInfo.connected) return
    if (shouldAutoScan(rootStatusInfo.last_scan_at, appSettings.auto_scan_min_interval_minutes)) {
      void startScan(true)
    }
  }, [
    rootId,
    rootStatusInfo?.root_id,
    rootStatusInfo?.connected,
    rootStatusInfo?.last_scan_at,
    appSettings?.auto_scan_on_start,
    appSettings?.auto_scan_min_interval_minutes,
  ])

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

  async function monitorScan(id: number) {
    const token = ++scanMonitorToken.current
    while (activeRootRef.current === id && scanMonitorToken.current === token) {
      await new Promise((resolve) => window.setTimeout(resolve, 300))
      if (activeRootRef.current !== id || scanMonitorToken.current !== token) return
      try {
        const status = await api.scanStatus(id)
        if (activeRootRef.current !== id || scanMonitorToken.current !== token) return
        setScanJob(status)
        if (status.state === 'running') continue
        if (status.state === 'completed' && status.summary) {
          setScanSummary(status.summary)
          await Promise.all([refreshTree(id), refreshCacheState(id)])
          const selectedId = selectedItemIdRef.current
          if (selectedId !== null) {
            try {
              setItem(await api.item(selectedId))
            } catch {
              setSelected(null)
              setItem(null)
            }
          }
          setCacheMessage(`掃描完成：${scanSummaryText(status.summary)}`)
        } else if (status.state === 'cancelled') {
          setCacheMessage('掃描已取消；原有索引保持不變。')
        } else if (status.state === 'error') {
          setError(status.error || '掃描失敗')
        }
        return
      } catch (err) {
        setError(err instanceof Error ? err.message : '讀取掃描狀態失敗')
        return
      }
    }
  }

  async function startScan(automatic = false) {
    const id = rootId
    if (id === null) return
    setError('')
    if (!automatic) setCacheMessage('')
    try {
      const current = await api.scanStatus(id)
      const status = current.state === 'running' ? current : await api.startScan(id)
      if (activeRootRef.current !== id) return
      setScanJob(status)
      setCacheMessage(automatic ? '背景掃描中…可繼續瀏覽照片。' : '掃描中…可繼續瀏覽照片。')
      void monitorScan(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '啟動掃描失敗')
    }
  }

  async function cancelScan() {
    const id = rootId
    if (id === null) return
    try {
      const status = await api.cancelScan(id)
      setScanJob(status)
      if (status.state === 'running') setCacheMessage('正在取消掃描…')
    } catch (err) {
      setError(err instanceof Error ? err.message : '取消掃描失敗')
    }
  }

  async function toggleNewItemPanel() {
    if (rootId === null) return
    const next = !showNewItem
    setShowNewItem(next)
    if (!appSettings) return
    try {
      const updated = await api.saveSettings({ ...appSettings, new_item_panel_open: next })
      setAppSettings(updated)
    } catch (err) {
      setShowNewItem(!next)
      setError(err instanceof Error ? err.message : '記錄新增資料夾展開狀態失敗')
    }
  }

  async function selectItem(node: TreeNode) {
    // A new selection should reveal the photo heading even when the previous item was scrolled.
    if (photoPanelRef.current) photoPanelRef.current.scrollTop = 0
    setSelected(node)
    setItem(null)
    if (node.id === undefined) return
    try {
      setItem(await api.item(node.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取照片資料失敗')
    }
  }

  function stageClipboardImage(slot: string, file: File) {
    if (!item || rootId === null || busy || scanRunning) return
    if (!orderedSlots.includes(slot)) { setError('請先選擇有效的照片槽位'); return }
    if (file.size > 100 * 1024 * 1024) { setError('剪貼簿圖片超過 100 MB'); return }
    setPendingPaste((old) => {
      if (old) URL.revokeObjectURL(old.previewUrl)
      return { rootId, itemId: item.id, slot, file, previewUrl: URL.createObjectURL(file) }
    })
    setError('')
  }

  async function pasteFromButton(slot: string) {
    if (!hasDesktopClipboardBridge()) {
      setShowPasteHelp(true)
      return
    }
    try {
      const file = await readDesktopClipboardImage()
      if (!file) { setError('剪貼簿沒有可使用的圖片，請先在 LINE 複製圖片'); return }
      stageClipboardImage(slot, file)
    } catch (error) {
      setError(error instanceof Error ? error.message : '無法讀取剪貼簿，請嘗試 Ctrl+V')
    }
  }

  function closePaste() {
    setPendingPaste((old) => {
      if (old) URL.revokeObjectURL(old.previewUrl)
      return null
    })
  }

  async function confirmPaste() {
    const pending = pendingPaste
    if (!pending || !item || rootId !== pending.rootId || item.id !== pending.itemId ||
      !orderedSlots.includes(pending.slot) || busy || scanRunning) {
      setError('設備或槽位已變更，請重新選取後貼上')
      closePaste()
      return
    }
    closePaste()
    await upload(pending.slot, pending.file)
  }

  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      if (view !== 'browse' || !item || busy || scanRunning || pendingPaste) return
      const target = event.target
      if (target instanceof HTMLElement &&
          (target.closest('input,textarea,select,[contenteditable="true"]') ||
           (target.closest('[role="dialog"]') && !showPasteHelp))) return
      const file = fromPaste(event.clipboardData?.items ?? null)
      if (!file) return
      event.preventDefault()
      setClipboardAvailable(true)
      setShowPasteHelp(false)
      if (!pasteSlot || !orderedSlots.includes(pasteSlot)) {
        setError('請先點選「編號／藥劑／完成」或「前／中／後」槽位，再按 Ctrl+V')
        return
      }
      stageClipboardImage(pasteSlot, file)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [view, item, pasteSlot, busy, scanRunning, pendingPaste, orderedSlots, rootId, showPasteHelp])

  useEffect(() => { setPasteSlot(null); setClipboardAvailable(null); closePaste() }, [item?.id, rootId, view])

  async function upload(slot: string, file: File, replacePhotoId?: number, allowDuplicate = false) {
    if (!item || rootId === null) return
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再匯入照片。')
      return
    }
    setBusy(true)
    setError('')
    try {
      const updated = await api.importPhoto(item.id, slot, file, replacePhotoId, allowDuplicate)
      setItem(updated)
      await refreshTree(rootId)
      await refreshCacheState(rootId)
      if (updated.offline_queued) {
        setCacheMessage('根目錄目前離線；照片已安全存入本機離線工作區，重新連線後可同步。')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '照片匯入失敗'
      if (!allowDuplicate && message.startsWith('相同圖片已存在：')) {
        setDuplicateUpload({ itemId: item.id, slot, file, replacePhotoId, reason: message })
      } else {
        setError(message)
      }
    } finally {
      setBusy(false)
    }
  }

  async function confirmDeleteItemFolder() {
    if (!folderToDelete || rootId === null) return
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再刪除資料夾。')
      return
    }
    
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
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再刪除照片。')
      return
    }
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
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再調整照片順序。')
      return
    }
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

  function openManualRename(photo: PhotoRecord) {
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再重新命名照片。')
      return
    }
    if (rootStatusInfo?.connected === false) {
      setError('照片根目錄目前離線，無法重新命名既有照片。')
      return
    }
    setRenameDialog({
      photo,
      targetFilename: photo.filename,
      reason: '人工重新命名',
      preview: null,
    })
  }

  async function preparePhotoRename(photo: PhotoRecord, targetFilename: string, reason: string) {
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再重新命名照片。')
      return
    }
    if (rootStatusInfo?.connected === false) {
      setError('照片根目錄目前離線，無法重新命名既有照片。')
      return
    }
    setBusy(true)
    setError('')
    try {
      const next = await api.previewPhotoRename(photo.id, targetFilename, reason)
      setRenameDialog({
        photo,
        targetFilename: next.target_name,
        reason,
        preview: next,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法預覽照片改名')
    } finally {
      setBusy(false)
    }
  }

  async function previewTransfer(source: PhotoRecord, slot: string, targetId: number | null) {
    if (!item || busy || scanRunning) return
    setSlotTransfer({ source, targetSlot: slot, targetPhotoId: targetId, preview: null })
    setError('')
    try {
      const preview = await api.previewSlotTransfer(source.id, slot, targetId)
      if (preview.item_id !== item.id) throw new Error('設備已切換，請重新選擇')
      setSlotTransfer((current) => current?.source.id === source.id &&
        current.targetSlot === slot && current.targetPhotoId === targetId
        ? { ...current, preview } : current)
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法預覽交換照片')
    }
  }

  function chooseTransferTarget(photo: PhotoRecord, targetSlot?: string) {
    if (!item || !photo.slot || busy || scanRunning) return
    const target = targetSlot ?? orderedSlots.find((slot) => slot !== photo.slot)
    if (!target || target === photo.slot) return
    const candidates = item.photos.filter((candidate) => candidate.slot === target)
    setSlotTransfer({ source: photo, targetSlot: target, targetPhotoId: null, preview: null })
    if (candidates.length <= 1) void previewTransfer(photo, target, candidates[0]?.id ?? null)
  }

  function assignExistingToSlot(slot: string, photoId: number) {
    const photo = item?.photos.find((candidate) => candidate.id === photoId)
    if (!photo) {
      setError('找不到拖曳的照片，請重新整理後再試。')
      return
    }
    if (photo.slot) {
      if (photo.slot === slot) return
      chooseTransferTarget(photo, slot)
      return
    }
    void preparePhotoRename(photo, `${slot}${photo.extension}`, `拖曳歸槽：${slot}`)
  }

  async function confirmSlotTransfer() {
    const current = slotTransfer
    if (!current?.preview || !item || current.preview.item_id !== item.id ||
      busy || scanRunning) return
    setBusy(true)
    setError('')
    try {
      const result = await api.executeSlotTransfer(current.preview)
      setItem(result.item)
      if (rootId !== null) {
        setLastTransfer({ rootId, itemId: result.item.id, logId: result.transfer_log_id })
        await refreshTree(rootId)
      }
      setSlotTransfer(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '交換照片失敗')
    } finally {
      setBusy(false)
    }
  }

  async function undoLastSlotTransfer() {
    if (!lastTransfer || busy || scanRunning) return
    if (rootId !== lastTransfer.rootId || item?.id !== lastTransfer.itemId) {
      setLastTransfer(null)
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = await api.undoSlotTransfer(lastTransfer.rootId, lastTransfer.logId)
      setItem(result.item)
      await refreshTree(lastTransfer.rootId)
      setLastTransfer(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法安全復原照片交換')
    } finally {
      setBusy(false)
    }
  }

  async function confirmPhotoRename() {
    const current = renameDialog
    if (!current?.preview?.safe || !current.preview.sha256 || rootId === null) return
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再重新命名照片。')
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = await api.renamePhoto(
        current.photo.id,
        current.preview.target_name,
        current.preview.sha256,
        current.reason,
      )
      setItem(result.item)
      await Promise.all([refreshTree(rootId), refreshCacheState(rootId)])
      setLastRename({
        logId: result.rename_log_id,
        itemId: result.item_id,
        rootId: result.root_id,
        source: result.source_name,
        target: result.target_name,
      })
      setCacheMessage(`已重新命名：${result.source_name} → ${result.target_name}`)
      setRenameDialog(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '照片重新命名失敗')
    } finally {
      setBusy(false)
    }
  }

  async function undoLastPhotoRename() {
    if (!lastRename) return
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再復原改名。')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.undoRename(lastRename.rootId, lastRename.logId)
      if (item?.id === lastRename.itemId) setItem(await api.item(lastRename.itemId))
      if (rootId === lastRename.rootId) {
        await Promise.all([refreshTree(rootId), refreshCacheState(rootId)])
      }
      setCacheMessage(`已復原：${lastRename.target} → ${lastRename.source}`)
      setLastRename(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '復原照片改名失敗')
    } finally {
      setBusy(false)
    }
  }

  function treeCategoryKeys(): string[] {
    return nodes.filter((node) => node.type === 'category')
      .map((node) => branchPathKey([node]))
  }

  function focusCreatedTreePath(
    targetRootId: number, path: Pick<TreeNode, 'type' | 'key'>[],
  ) {
    const defaults = treeCategoryKeys()
    setExpandedByRoot((previous) => ({
      ...previous,
      [targetRootId]: revealCreatedBranch(previous[targetRootId], defaults, path),
    }))
    setTreeReveal({ rootId: targetRootId, path: branchPathKey(path) })
  }

  function toggleExpandedTreePath(targetRootId: number, pathKey: string) {
    const defaults = treeCategoryKeys()
    setExpandedByRoot((previous) => ({
      ...previous,
      [targetRootId]: toggleTreeBranch(previous[targetRootId], defaults, pathKey),
    }))
  }

  const TREE_CREATE_LABELS: Record<string, string> = {
    category: '新增年份',
    year: '新增月份／批次',
    period: '新增棟別',
    building: '新增設備編號',
  }

  async function createFolderFromTree() {
    if (!treeCreatePath || rootId === null) return
    const last = treeCreatePath[treeCreatePath.length - 1]
    const name = treeCreateName.trim()
    if (!last || !name) return
    if (busy || scanRunning) {
      setError('掃描或其他操作進行中，無法建立資料夾')
      return
    }
    const category = treeCreatePath[0]?.key ?? ''
    const year = treeCreatePath[1]?.label ?? ''
    const period = treeCreatePath[2]?.label ?? ''
    const building = treeCreatePath[3]?.label ?? ''
    setBusy(true)
    setError('')
    try {
      let createdPath: Pick<TreeNode, 'type' | 'key'>[]
      if (last.type === 'category') {
        await api.createYearFolder({ root_id: rootId, category_code: category, year: name })
        createdPath = [...treeCreatePath, { type: 'year', key: name }]
      } else if (last.type === 'year') {
        await api.createPeriodFolder({ root_id: rootId, category_code: category, year, period: name })
        createdPath = [...treeCreatePath, { type: 'period', key: name }]
      } else if (last.type === 'period') {
        await api.createBuildingFolder({ root_id: rootId, category_code: category, year, period, building: name })
        createdPath = [...treeCreatePath, { type: 'building', key: name }]
      } else if (last.type === 'building') {
        const created = await api.createItem({
          root_id: rootId, category_code: category, year, period, building, code: name,
        })
        setSelected({ type: 'item', id: created.id, key: String(created.id), label: created.code })
        setItem(created)
        createdPath = [...treeCreatePath, { type: 'item', key: String(created.id) }]
      } else {
        throw new Error('此層級不能建立子資料夾')
      }
      focusCreatedTreePath(rootId, createdPath)
      await refreshTree(rootId)
      setTreeCreatePath(null)
      setTreeCreateName('')
      setCacheMessage(`已建立資料夾：${name}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增資料夾失敗')
    } finally {
      setBusy(false)
    }
  }

  async function createNumberFolder() {
    if (rootId === null) return
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再建立資料夾。')
      return
    }
    setBusy(true)
    setError('')
    try {
      const created = await api.createItem({ root_id: rootId, ...newItem })
      focusCreatedTreePath(
        rootId,
        itemBranchPath(
          newItem.category_code, newItem.year, newItem.period,
          newItem.building, created.id,
        ),
      )
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
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再建立月份／批次。')
      return
    }
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
      focusCreatedTreePath(rootId, [
        { type: 'category', key: newItem.category_code },
        { type: 'year', key: newItem.year },
        { type: 'period', key: created.period },
      ])
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
    if (scanRunning) {
      setError('掃描進行中，請等待完成或先取消掃描再建立棟別。')
      return
    }
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
      focusCreatedTreePath(rootId, [
        { type: 'category', key: newItem.category_code },
        { type: 'year', key: newItem.year },
        { type: 'period', key: newItem.period },
        { type: 'building', key: created.building ?? newBuildingName.trim() },
      ])
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
    <main className={`app-shell${view === 'browse' ? ' browse-layout' : ''}`}>
      <header className="topbar">
        <div>
          <strong>FireLens</strong>
          <span>照片管理、核對與離線工作 · v{appInfo?.version ?? '1.10.0'}</span>
        </div>
        <div className="root-controls">
          <label htmlFor="root-select">根目錄</label>
          <select id="root-select" value={rootId ?? ''} onChange={(event) => setRootId(Number(event.target.value))}>
            {roots.length === 0 && <option value="">尚未設定</option>}
            {roots.map((root) => <option key={root.id} value={root.id}>{root.label}</option>)}
          </select>
          <button type="button" onClick={() => void startScan(false)} disabled={rootId === null || scanRunning}>
            {scanRunning ? '掃描中…' : '重新掃描'}
          </button>
          {scanRunning && <button type="button" className="outline-button" onClick={() => void cancelScan()}>取消掃描</button>}
          {rootStatusInfo && (
            <span className={`connection-badge ${rootStatusInfo.connected ? 'online' : 'offline'}`}>
              {rootStatusInfo.connected ? '已連線' : '離線快取'}
              {rootStatusInfo.pending_imports > 0 ? ` · 待同步 ${rootStatusInfo.pending_imports}` : ''}
            </span>
          )}
        </div>
      </header>
      {appInfo?.last_update && ['error', 'rolled_back', 'rollback_failed', 'helper_start_failed'].includes(appInfo.last_update.phase ?? '') && (
        <div className="warning-banner" role="status">
          上次更新未完成，目前仍安全使用 v{appInfo.version}。請到「設定 → 線上更新」查看紀錄並重試。
        </div>
      )}

      <nav className="mode-tabs" aria-label="FireLens 功能">
        <button type="button" className={view === 'browse' ? 'active' : ''} onClick={() => setView('browse')}>照片瀏覽</button>
        <button type="button" className={view === 'reconcile' ? 'active' : ''} onClick={() => setView('reconcile')}>清冊核對</button>
        <button type="button" className={view === 'statistics' ? 'active' : ''} onClick={() => setView('statistics')}>異常統計</button>
        <button type="button" className={view === 'organizer' ? 'active' : ''} onClick={() => setView('organizer')}>整理工具</button>
        <button type="button" className={view === 'quality' ? 'active' : ''} onClick={() => setView('quality')}>照片品質檢查</button>
        <button type="button" className={view === 'settings' ? 'active' : ''} onClick={() => setView('settings')}>設定</button>
        <button type="button" className={view === 'publicSheets' ? 'active' : ''} onClick={() => setView('publicSheets')}>查看滅火器資料</button>
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
        <button
          type="button"
          className="outline-button"
          onClick={() => void toggleNewItemPanel()}
          disabled={rootId === null}
          aria-expanded={rootId !== null ? showNewItem : false}
          aria-controls="new-item-form"
          aria-label={newItemPanelButtonText(showNewItem, rootId !== null)}
        >
          {newItemPanelButtonText(showNewItem, rootId !== null)}
        </button>
        <button type="button" className="outline-button" onClick={() => void buildThumbnailCache()} disabled={busy || rootId === null || rootStatusInfo?.connected === false}>建立縮圖快取</button>
        <button type="button" className="outline-button" onClick={() => void syncOffline()} disabled={busy || scanRunning || rootId === null || !rootStatusInfo?.connected || rootStatusInfo.pending_imports === 0}>同步離線照片</button>
      </section>

      {rootId !== null && showNewItem && (
        <section id="new-item-form" className="new-item-form" aria-label="新增編號資料夾">
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
                <button type="button" className="mini-add-button" onClick={() => setShowNewPeriod((value) => !value)} disabled={busy || scanRunning || !newItem.year.trim()}>＋</button>
              </div>
            </label>
            {showNewPeriod && (
              <div className="inline-folder-create">
                <input value={newPeriodName} onChange={(event) => setNewPeriodName(event.target.value)} placeholder="例：11月份更換" />
                <button type="button" onClick={() => void createPeriod()} disabled={busy || scanRunning || !newPeriodName.trim()}>新增</button>
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
                <button type="button" className="mini-add-button" onClick={() => setShowNewBuilding((value) => !value)} disabled={busy || scanRunning || !newItem.period.trim()}>＋</button>
              </div>
            </label>
            {showNewBuilding && (
              <div className="inline-folder-create">
                <input value={newBuildingName} onChange={(event) => setNewBuildingName(event.target.value)} placeholder="例：中正樓" />
                <button type="button" onClick={() => void createBuilding()} disabled={busy || scanRunning || !newBuildingName.trim()}>新增</button>
              </div>
            )}
          </div>
          <label>編號
            <input autoFocus placeholder="例：中-01-01" value={newItem.code} onChange={(event) => setNewItem({ ...newItem, code: event.target.value })} />
          </label>
          <button
            type="button"
            onClick={() => void createNumberFolder()}
            disabled={busy || scanRunning || !newItem.year.trim() || !newItem.period.trim() || !newItem.building.trim() || !newItem.code.trim()}
          >
            建立資料夾
          </button>
          <small>月份與棟別右側「＋」可直接建立新的實體資料夾；類別、年份、月份與棟別會記住上次選擇，連續建立時只要輸入編號。</small>
        </section>
      )}

      {error && <div className="error-banner" role="alert">{error}</div>}
      {cacheMessage && <div className="success-banner" role="status">{cacheMessage}</div>}
      {lastRename && (
        <div className="success-banner rename-undo-banner" role="status">
          <span>最近改名：{lastRename.source} → {lastRename.target}</span>
          <button type="button" onClick={() => void undoLastPhotoRename()} disabled={busy || scanRunning}>復原</button>
        </div>
      )}

      <section className="workspace">
        <aside className="panel tree-panel" aria-label="照片資料夾樹">
          <div className="panel-title"><h2>資料樹</h2><span>{countItems(filteredNodes)} / {countItems(nodes)} 筆</span></div>
          <input className="tree-search" type="search" value={treeQuery} onChange={(event) => setTreeQuery(event.target.value)} placeholder="搜尋棟別、月份或設備編號" aria-label="搜尋照片資料樹" />
          <TreeView key={rootId ?? 'no-root'} nodes={filteredNodes}
            selectedId={selected?.id ?? null}
            onSelectItem={(node) => { setTreeReveal(null); void selectItem(node) }}
            expandAll={Boolean(deferredTreeQuery.trim())}
            expandedPaths={rootId === null ? undefined : expandedByRoot[rootId]}
            onToggle={(pathKey) => {
              if (rootId !== null) toggleExpandedTreePath(rootId, pathKey)
              setTreeReveal(null)
            }}
            revealPath={treeReveal?.rootId === rootId ? treeReveal.path : null}
            onCreate={(path) => {
              if (busy || scanRunning) { setError('掃描或其他操作進行中，無法建立資料夾'); return }
              setTreeCreatePath(path)
              setTreeCreateName('')
            }} />
        </aside>

        <section className="panel photo-panel" ref={photoPanelRef} aria-label="照片槽位牆">
          <div className="panel-title">
            <div className="folder-heading">
              <div className="folder-title-row">
                <h2>{item?.code ?? '照片槽位'}</h2>
                {item && (
                  <button type="button" className="secondary-button" onClick={() => { setFolderRename(item); setNewFolderName(item.code) }} disabled={busy || scanRunning || rootStatusInfo?.connected === false}>
                    更改名稱
                  </button>
                )}
              </div>
              {item && <small>{item.category_name} · {item.building}</small>}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {item && (
                <>
                  <label className="issue-select-control">設備異常
                    <select aria-label="設備異常單選" value={issueSelection ?? ''} onChange={(event) => void changeIssue(event.target.value)} disabled={busy}>
                      <option value="">無異常</option>
                      {issueLabels.filter((label) => label.active || label.id === issueSelection).map((label) => (
                        <option key={label.id} value={label.id}>{label.name}{!label.active ? '（已停用）' : ''}</option>
                      ))}
                    </select>
                  </label>
                  {lastTransfer?.rootId === rootId && lastTransfer?.itemId === item.id && (
                    <button type="button" className="secondary-button"
                      disabled={busy || scanRunning}
                      onClick={() => void undoLastSlotTransfer()}>復原上次照片交換</button>
                  )}
                  <button type="button" className="danger-button" onClick={() => setFolderToDelete(item)} disabled={busy || scanRunning}>
                    刪除
                  </button>
                </>
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
                    disabled={busy || scanRunning}
                    onImport={(targetSlot, file) => void upload(targetSlot, file)}
                    onPreview={openPreview}
                    onReplace={(targetSlot, photoId, file) => void upload(targetSlot, file, photoId)}
                    onDelete={(photo) => setPhotoToDelete(photo)}
                    onReorder={(targetSlot, photoIds) => void reorderSlotPhotos(targetSlot, photoIds)}
                    onAssignExisting={assignExistingToSlot}
                    onRename={openManualRename}
                    onTransfer={(photo) => chooseTransferTarget(photo)}
                    onError={setError}
                    selectedForPaste={pasteSlot === slot}
                    onChooseSlot={setPasteSlot}
                    onPasteImage={(value) => void pasteFromButton(value)}
                    clipboardAvailable={clipboardAvailable}
                  />
                ))}
              </div>
              {extras.length > 0 && (
                <section className="unmapped-section">
                  <h3>未對應／舊制照片 <span>{extras.length}</span></h3>
                  <p className="unmapped-help">可把照片直接拖到上方槽位，FireLens 會先顯示「原檔名 → 新檔名」確認，不會覆蓋既有照片。</p>
                  <div className="unmapped-list">
                    {extras.map((photo) => (
                      <article
                        key={photo.id}
                        className="unmapped-photo-card"
                        draggable={!busy && !scanRunning && rootStatusInfo?.connected !== false && !photo.cloud_placeholder}
                        onDragStart={(event) => {
                          event.dataTransfer.setData(INTERNAL_PHOTO_DRAG_TYPE, String(photo.id))
                          event.dataTransfer.effectAllowed = 'move'
                        }}
                      >
                        <button type="button" onClick={() => openPreview(photo)} className="unmapped-photo">
                          <img src={api.photoUrl(photo)} alt={photo.filename} loading="lazy" />
                          <span>{photo.filename}</span>
                        </button>
                        <div className="unmapped-actions">
                          <button type="button" onClick={() => openManualRename(photo)} disabled={busy || scanRunning}>重新命名</button>
                          {item.slots.map((slot) => (
                            <button
                              key={slot}
                              type="button"
                              onClick={() => void preparePhotoRename(photo, `${slot}${photo.extension}`, `快速歸槽：${slot}`)}
                              disabled={busy || scanRunning || rootStatusInfo?.connected === false || Boolean(photo.cloud_placeholder)}
                            >
                              設為{slot}
                            </button>
                          ))}
                        </div>
                      </article>
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
          {scanSummary && <div className="scan-summary"><b>最近掃描</b><p>{scanSummary.items} 個項目 / {scanSummary.photos} 張照片</p><p>{scanSummaryText(scanSummary)}</p></div>}
          <div className="notice"><b>寫入保護</b><p>匯入使用暫存檔 → 原子換名 → SHA-256 驗證；既有檔名不會被直接覆蓋。</p></div>
          <div className="notice"><b>來源照片不變</b><p>拖入的原始照片只讀取內容，FireLens 只在目標設備資料夾建立副本。</p></div>
        </aside>
      </section>

      {showPasteHelp && !pendingPaste && (
        <div className="preview-backdrop" role="presentation"
          onMouseDown={() => setShowPasteHelp(false)}
          onKeyDown={(event) => { if (event.key === 'Escape') setShowPasteHelp(false) }}>
          <section className="prompt-dialog paste-confirm-dialog" role="dialog" aria-modal="true"
            aria-label="貼上剪貼簿照片" onMouseDown={(event) => event.stopPropagation()}>
            <div className="prompt-header">貼上剪貼簿照片</div>
            <div className="prompt-body">
              <p>已選擇槽位：<b>{pasteSlot ?? '未選擇'}</b></p>
              <p>在 LINE 複製圖片後，回到 FireLens 按 <b>Ctrl+V</b>，即可預覽照片並確認貼上。</p>
              <p>瀏覽器為保護剪貼簿內容，不支援免授權的按鈕直接讀取；使用 Ctrl+V 不需要這個權限視窗。</p>
            </div>
            <div className="prompt-footer">
              <button type="button" autoFocus onClick={() => setShowPasteHelp(false)}>關閉</button>
            </div>
          </section>
        </div>
      )}

      {duplicateUpload && (
        <div className="preview-backdrop" role="presentation"
          onMouseDown={() => !busy && setDuplicateUpload(null)}>
          <section className="prompt-dialog paste-confirm-dialog" role="dialog" aria-modal="true"
            aria-label="確認儲存重複圖片" onMouseDown={(event) => event.stopPropagation()}>
            <div className="prompt-header">發現相同圖片</div>
            <div className="prompt-body">
              <p>{duplicateUpload.reason}</p>
              <p>設備：{item?.code} · 槽位：{duplicateUpload.slot}</p>
              <p>選擇取消可避免重複儲存。選擇仍要儲存會額外建立一張照片，不會覆蓋舊圖。</p>
            </div>
            <div className="prompt-footer">
              <button type="button" disabled={busy} onClick={() => setDuplicateUpload(null)}>取消</button>
              <button type="button" className="primary-button" disabled={busy || scanRunning}
                onClick={() => {
                  const pending = duplicateUpload
                  setDuplicateUpload(null)
                  if (item?.id !== pending.itemId) { setError('選取設備已變更，已取消'); return }
                  void upload(pending.slot, pending.file, pending.replacePhotoId, true)
                }}>仍要儲存</button>
            </div>
          </section>
        </div>
      )}

      {pendingPaste && (
        <div className="preview-backdrop" role="presentation" onMouseDown={() => !busy && closePaste()}
          onKeyDown={(event) => { if (event.key === 'Escape' && !busy) closePaste() }}>
          <section className="prompt-dialog paste-confirm-dialog" role="dialog" aria-modal="true"
            aria-label="確認貼上照片" onMouseDown={(event) => event.stopPropagation()}>
            <div className="prompt-header">確認貼上照片</div>
            <div className="prompt-body">
              <p>設備：<b>{item?.code}</b>　槽位：<b>{pendingPaste.slot}</b></p>
              <img className="paste-preview-image" src={pendingPaste.previewUrl} alt="待貼上的剪貼簿照片預覽" />
              <p>來源：剪貼簿圖片（{Math.ceil(pendingPaste.file.size / 1024)} KB）</p>
              <p>將依現有命名規則儲存到「{pendingPaste.slot}」，不覆蓋既有照片。</p>
            </div>
            <div className="prompt-footer">
              <button type="button" disabled={busy} onClick={closePaste}>取消</button>
              <button type="button" className="primary-button" disabled={busy || scanRunning}
                onClick={() => void confirmPaste()}>確認貼上</button>
            </div>
          </section>
        </div>
      )}

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

      {slotTransfer && item && (
        <div className="preview-backdrop" onMouseDown={() => !busy && setSlotTransfer(null)}
          onKeyDown={(event) => { if (event.key === 'Escape' && !busy) setSlotTransfer(null) }}>
          <section className="prompt-dialog slot-transfer-dialog" role="dialog" aria-modal="true"
            aria-label="確認照片移動或交換" onMouseDown={(event) => event.stopPropagation()}>
            <div className="prompt-header">確認照片移動／交換</div>
            <div className="prompt-body">
              <p>設備：<b>{item.code}</b></p>
              <p>來源：<b>{slotTransfer.source.slot}／{slotTransfer.source.filename}</b></p>
              <div className="transfer-images">
                <figure><img className="transfer-thumb" src={api.thumbnailUrl(slotTransfer.source)}
                  alt={slotTransfer.source.filename} /><figcaption>來源照片</figcaption></figure>
                {item.photos.find((photo) => photo.id === slotTransfer.targetPhotoId) && (
                  <figure><img className="transfer-thumb"
                    src={api.thumbnailUrl(item.photos.find((photo) => photo.id === slotTransfer.targetPhotoId)!)}
                    alt="欲交換的目的照片" /><figcaption>目的照片</figcaption></figure>
                )}
              </div>
              <label>移到槽位
                <select value={slotTransfer.targetSlot}
                  onChange={(event) => chooseTransferTarget(slotTransfer.source, event.target.value)}>
                  {orderedSlots.filter((slot) => slot !== slotTransfer.source.slot)
                    .map((slot) => <option key={slot} value={slot}>{slot}</option>)}
                </select>
              </label>
              {item.photos.filter((photo) => photo.slot === slotTransfer.targetSlot).length > 1 && (
                <label>選擇要交換的目的照片
                  <select value={slotTransfer.targetPhotoId ?? ''}
                    onChange={(event) => void previewTransfer(slotTransfer.source,
                      slotTransfer.targetSlot, Number(event.target.value))}>
                    <option value="">請選擇照片</option>
                    {item.photos.filter((photo) => photo.slot === slotTransfer.targetSlot)
                      .map((photo) => <option key={photo.id} value={photo.id}>{photo.filename}</option>)}
                  </select>
                </label>
              )}
              {slotTransfer.preview && (
                <div className="rename-preview-box safe">
                  <p>{slotTransfer.preview.mode === 'swap' ? '交換兩張照片' : '移至空槽位'}</p>
                  <p>{slotTransfer.preview.source_name} → {slotTransfer.preview.target_name}</p>
                  {slotTransfer.preview.target_source_name && <p>
                    {slotTransfer.preview.target_source_name} → {slotTransfer.preview.target_new_name}
                  </p>}
                  <small>執行前會再次驗證檔案內容及檔名，不會覆蓋其他照片。</small>
                </div>
              )}
            </div>
            <div className="prompt-footer">
              <button type="button" disabled={busy} onClick={() => setSlotTransfer(null)}>取消</button>
              <button type="button" className="primary-button" disabled={busy || !slotTransfer.preview}
                onClick={() => void confirmSlotTransfer()}>確認移動／交換</button>
            </div>
          </section>
        </div>
      )}

      {renameDialog && (
        <div className="preview-backdrop" onMouseDown={() => !busy && setRenameDialog(null)}>
          <section className="rename-dialog" role="dialog" aria-modal="true" aria-label={`重新命名 ${renameDialog.photo.filename}`} onMouseDown={(event) => event.stopPropagation()}>
            <div className="prompt-header">重新命名照片</div>
            <div className="prompt-body rename-dialog-body">
              <p>來源：<strong>{renameDialog.photo.filename}</strong></p>
              <label>新檔名
                <input
                  value={renameDialog.targetFilename}
                  onChange={(event) => setRenameDialog((current) => current ? {
                    ...current,
                    targetFilename: event.target.value,
                    preview: null,
                    reason: current.reason.startsWith('拖曳歸槽') || current.reason.startsWith('快速歸槽')
                      ? '人工重新命名'
                      : current.reason,
                  } : current)}
                  disabled={busy}
                />
              </label>
              <div className="rename-quick-actions">
                {item?.slots.map((slot) => (
                  <button
                    key={slot}
                    type="button"
                    onClick={() => void preparePhotoRename(
                      renameDialog.photo,
                      `${slot}${renameDialog.photo.extension}`,
                      `快速歸槽：${slot}`,
                    )}
                    disabled={busy || scanRunning}
                  >
                    設為{slot}
                  </button>
                ))}
              </div>
              {renameDialog.preview && (
                <div className={`rename-preview-box ${renameDialog.preview.safe ? 'safe' : 'blocked'}`}>
                  <b>{renameDialog.preview.source_name} → {renameDialog.preview.target_name}</b>
                  <span>{renameDialog.preview.safe ? '✓ 可安全改名；檔案內容不會重新編碼。' : `無法改名：${renameDialog.preview.blocked_reason}`}</span>
                </div>
              )}
            </div>
            <div className="prompt-footer">
              <button type="button" onClick={() => setRenameDialog(null)} disabled={busy}>取消</button>
              <button
                type="button"
                onClick={() => void preparePhotoRename(renameDialog.photo, renameDialog.targetFilename, renameDialog.reason)}
                disabled={busy || scanRunning || !renameDialog.targetFilename.trim()}
              >
                預覽改名
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => void confirmPhotoRename()}
                disabled={busy || !renameDialog.preview?.safe || !renameDialog.preview.sha256}
              >
                確認改名
              </button>
            </div>
          </section>
        </div>
      )}
        </>
      ) : view === 'reconcile' ? (
        <ReconcileView roots={roots} defaultRootId={rootId} />
      ) : view === 'statistics' ? (
        <StatisticsView
          roots={roots}
          onLabelsChanged={() => void refreshIssueLabels().catch((err) => setError(String(err)))}
          onOpenItem={(nextRootId, itemId) => {
            pendingStatsNavigation.current = { rootId: nextRootId, itemId }
            setRootId(nextRootId)
            setView('browse')
          }}
        />
      ) : view === 'organizer' ? (
        <OrganizerView roots={roots} defaultRootId={rootId} />
      ) : view === 'quality' ? (
        <PhotoQualityView roots={roots} defaultRootId={rootId}
          onOpenItem={(nextRootId, itemId) => {
            pendingStatsNavigation.current = { rootId: nextRootId, itemId }
            setRootId(nextRootId)
            setView('browse')
          }} />
      ) : view === 'publicSheets' ? (
        <PublicSheetsView />
      ) : (
        <SettingsView
          roots={roots}
          categories={categories}
          settings={appSettings}
          appInfo={appInfo}
          onSettingsChanged={setAppSettings}
          onRootsChanged={async () => { await refreshRoots(); if (rootId) await refreshCacheState(rootId).catch(() => undefined) }}
          onCategoriesChanged={async () => {
            setCategories(await api.categories())
            if (rootId !== null) await refreshTree(rootId)
            if (selected?.id !== undefined) setItem(await api.item(selected.id))
          }}
        />
      )}

      {treeCreatePath && (
        <div className="preview-backdrop" onMouseDown={() => !busy && setTreeCreatePath(null)}
          onKeyDown={(event) => { if (event.key === 'Escape' && !busy) setTreeCreatePath(null) }}>
          <section className="prompt-dialog" role="dialog" aria-modal="true"
            aria-label={TREE_CREATE_LABELS[treeCreatePath[treeCreatePath.length - 1].type] || '新增資料夾'}
            onMouseDown={(event) => event.stopPropagation()}>
            <div className="prompt-header">{TREE_CREATE_LABELS[treeCreatePath[treeCreatePath.length - 1].type]}</div>
            <div className="prompt-body">
              <p className="muted">新增位置：{treeCreatePath.map((n) => n.label).join(' / ')}</p>
              <label>{treeCreatePath[treeCreatePath.length - 1].type === 'category' ? '年份' :
                treeCreatePath[treeCreatePath.length - 1].type === 'year' ? '月份或批次名稱' :
                  treeCreatePath[treeCreatePath.length - 1].type === 'period' ? '棟別名稱' : '設備編號'}
                <input className="prompt-input" autoFocus value={treeCreateName} maxLength={120}
                  onChange={(event) => setTreeCreateName(event.target.value)}
                  onKeyDown={(event) => { if (event.key === 'Enter') void createFolderFromTree() }} />
              </label>
            </div>
            <div className="prompt-footer">
              <button type="button" disabled={busy} onClick={() => setTreeCreatePath(null)}>取消</button>
              <button className="primary-button" type="button" disabled={busy || !treeCreateName.trim()}
                onClick={() => void createFolderFromTree()}>新增資料夾</button>
            </div>
          </section>
        </div>
      )}

      {folderRename && (
        <div className="preview-backdrop" onMouseDown={() => !busy && setFolderRename(null)}>
          <section className="prompt-dialog" role="dialog" aria-modal="true" aria-label="更改設備資料夾名稱" onMouseDown={(event) => event.stopPropagation()}>
            <div className="prompt-header">更改設備資料夾名稱</div>
            <div className="prompt-body">
              <label>新資料夾名稱
                <input autoFocus className="prompt-input" value={newFolderName} maxLength={120} onChange={(event) => setNewFolderName(event.target.value)} disabled={busy} />
              </label>
              <p><strong>{folderRename.code}</strong> → <strong>{newFolderName || '（尚未輸入）'}</strong></p>
              <p className="muted">來源：{folderRename.relative_path}</p>
              <p className="muted">保留內部 {folderRename.photo_count} 張照片及所有子資料夾，只更動資料夾名稱。</p>
              <p className="warning-banner">提醒：既有清冊的設備編號不會自動修改，更名後可能需要重新核對。</p>
            </div>
            <div className="prompt-footer">
              <button type="button" onClick={() => setFolderRename(null)} disabled={busy}>取消</button>
              <button type="button" className="primary-button" onClick={() => void confirmFolderRename()} disabled={busy || scanRunning || !newFolderName.trim() || newFolderName === folderRename.code}>確認更名</button>
            </div>
          </section>
        </div>
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

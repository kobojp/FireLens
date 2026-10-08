import type {
  CategoryDefinition,
  ItemDetail,
  ItemFolderCreate,
  StructureFolderResult,
  OrganizerAnalysis,
  PhotoRecord,
  RenameExecutionResult,
  RenameHistoryRecord,
  RenamePreview,
  AliasRecord,
  LedgerRecord,
  ReconcileResult,
  RootRecord,
  ScanSummary,
  TreeNode,
  RootStatus,
  OfflineQueueEntry,
  ImportPhotoResult,
  AppSettings,
  AppInfo,
  BackupRestoreResult,
  UpdateStatus,
  UpdateInstallResult,
} from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

export const api = {
  settings: () => request<AppSettings>('/api/settings'),
  saveSettings: (settings: AppSettings) => request<AppSettings>('/api/settings', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  }),
  appInfo: () => request<AppInfo>('/api/app-info'),
  checkUpdate: () => request<UpdateStatus>('/api/update/check'),
  downloadUpdate: (version: string) => request<UpdateStatus>('/api/update/download', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version }),
  }),
  installUpdate: (version: string) => request<UpdateInstallResult>('/api/update/install', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version }),
  }),
  updateRootSettings: (rootId: number, label: string, isCloudStream: boolean) => request<RootRecord>(`/api/roots/${rootId}/settings`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label, is_cloud_stream: isCloudStream }),
  }),
  updateCategoryAliases: (code: string, aliases: Record<string, string>) => request<CategoryDefinition>(`/api/categories/${encodeURIComponent(code)}/aliases`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aliases }),
  }),
  backupUrl: () => '/api/settings/backup',
  restoreBackup: (file: File) => {
    const form = new FormData(); form.append('file', file)
    return request<BackupRestoreResult>('/api/settings/restore', { method: 'POST', body: form })
  },
  listRoots: () => request<RootRecord[]>('/api/roots'),
  addRoot: (path: string, label?: string) => request<RootRecord>('/api/roots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, label: label || undefined }),
  }),
  categories: () => request<CategoryDefinition[]>('/api/categories'),
  scanRoot: (rootId: number) => request<ScanSummary>(`/api/roots/${rootId}/scan`, { method: 'POST' }),
  tree: (rootId: number) => request<TreeNode[]>(`/api/roots/${rootId}/tree`),
  rootStatus: (rootId: number) => request<RootStatus>(`/api/roots/${rootId}/status`),
  offlineQueue: (rootId: number) => request<OfflineQueueEntry[]>(`/api/roots/${rootId}/offline-queue`),
  syncOffline: (rootId: number) => request<{ root_id: number; synced: number[]; failed: { id: number; error: string }[]; remaining: number }>(
    `/api/roots/${rootId}/offline-queue/sync`, { method: 'POST' },
  ),
  cacheThumbnails: (rootId: number) => request<{ root_id: number; created: number; failed: number }>(
    `/api/roots/${rootId}/cache/thumbnails`, { method: 'POST' },
  ),
  photos: (itemId: number) => request<PhotoRecord[]>(`/api/items/${itemId}/photos`),
  item: (itemId: number) => request<ItemDetail>(`/api/items/${itemId}`),
  deleteItem: (itemId: number) => request<{ status: string; deleted: boolean }>(`/api/items/${itemId}`, { method: 'DELETE' }),
  createItem: (payload: ItemFolderCreate) => request<ItemDetail>('/api/items', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  createPeriodFolder: (payload: Omit<ItemFolderCreate, 'building' | 'code'> & { period: string }) => request<StructureFolderResult>('/api/folders/period', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  createBuildingFolder: (payload: Omit<ItemFolderCreate, 'code'>) => request<StructureFolderResult>('/api/folders/building', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  importPhoto: (itemId: number, slot: string, file: File, replacePhotoId?: number) => {
    const form = new FormData()
    form.append('file', file)
    const query = replacePhotoId === undefined ? '' : `?replace_photo_id=${replacePhotoId}`
    return request<ImportPhotoResult>(`/api/items/${itemId}/slots/${encodeURIComponent(slot)}/photos${query}`, {
      method: 'POST',
      body: form,
    })
  },
  deletePhoto: (photoId: number) => request<ItemDetail>(`/api/photos/${photoId}`, { method: 'DELETE' }),
  reorderPhotos: (itemId: number, slot: string, photoIds: number[]) => request<ItemDetail>(`/api/items/${itemId}/slots/${encodeURIComponent(slot)}/reorder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ photo_ids: photoIds }),
  }),

  ledgers: () => request<LedgerRecord[]>('/api/ledgers'),
  importExcelLedger: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<LedgerRecord>('/api/ledgers/excel', { method: 'POST', body: form })
  },
  importTextLedger: (name: string, text: string) => request<LedgerRecord>('/api/ledgers/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, text }),
  }),
  aliases: () => request<AliasRecord[]>('/api/aliases'),
  saveAlias: (sourceValue: string, targetValue: string) => request<AliasRecord>('/api/aliases', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_value: sourceValue, target_value: targetValue, confirmed: true }),
  }),
  reconcile: (rootId: number, ledgerId: number, period?: string) => request<ReconcileResult>('/api/reconcile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ root_id: rootId, ledger_id: ledgerId, period: period || null }),
  }),
  setReshotMark: (rootId: number, ledgerId: number, categoryCode: string, deviceNo: string, marked: boolean) =>
    request<{ marked: boolean }>('/api/reconcile/reshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        root_id: rootId, ledger_id: ledgerId, category_code: categoryCode, device_no: deviceNo, marked,
      }),
    }),
  reconcileExportUrl: (rootId: number, ledgerId: number, format: 'csv' | 'xlsx', period?: string) => {
    const params = new URLSearchParams({ root_id: String(rootId), ledger_id: String(ledgerId), format })
    if (period) params.set('period', period)
    return `/api/reconcile/export?${params.toString()}`
  },
  organizer: (rootId: number) => request<OrganizerAnalysis>(`/api/organizer/${rootId}`),
  previewRenames: (rootId: number, candidateIds: string[]) => request<RenamePreview>(
    `/api/organizer/${rootId}/rename/preview`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_ids: candidateIds }),
    },
  ),
  executeRenames: (rootId: number, candidateIds: string[]) => request<RenameExecutionResult>(
    `/api/organizer/${rootId}/rename`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_ids: candidateIds }),
    },
  ),
  organizerHistory: (rootId: number) => request<RenameHistoryRecord[]>(`/api/organizer/${rootId}/history`),
  undoRename: (rootId: number, logId: number) => request<RenameHistoryRecord>(`/api/organizer/${rootId}/undo/${logId}`, { method: 'POST' }),
  photoUrl: (photo: PhotoRecord) => `/api/photos/${photo.id}/content?v=${photo.mtime_ns}`,
  thumbnailUrl: (photo: PhotoRecord) => `/api/photos/${photo.id}/thumbnail?v=${photo.mtime_ns}`,
}

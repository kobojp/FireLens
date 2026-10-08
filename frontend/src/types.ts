export type RootRecord = {
  id: number
  label: string
  path: string
  is_cloud_stream: number
  created_at: string
  last_scan_at: string | null
}

export type TreeNode = {
  type: 'category' | 'year' | 'period' | 'building' | 'item'
  key: string
  label: string
  children?: TreeNode[]
  id?: number
  status?: string
  photo_count?: number
}

export type PhotoRecord = {
  id: number
  filename: string
  relative_path: string
  extension: string
  slot: string | null
  size_bytes: number
  mtime_ns: number
  sha256?: string | null
  cloud_placeholder: number
}

export type CategoryDefinition = {
  code: string
  name: string
  slots: string[]
  filename_aliases: Record<string, string>
}

export type ItemDetail = {
  id: number
  root_id: number
  category_id: number
  category_code: string
  category_name: string
  year: string
  period: string
  building: string
  code: string
  relative_path: string
  status: string
  photo_count: number
  slots: string[]
  custom_slots: string[]
  filename_aliases: Record<string, string>
  photos: PhotoRecord[]
}

export type ScanSummary = {
  root_id: number
  items: number
  photos: number
  categories: Record<string, number>
}

export type ItemFolderCreate = {
  root_id: number
  category_code: string
  year: string
  period: string
  building: string
  code: string
}

export type StructureFolderResult = {
  root_id: number
  category_code: string
  year: string
  period: string
  building?: string
  relative_path: string
  created: boolean
}


export type LedgerRecord = {
  id: number
  name: string
  source_type: 'xlsx' | 'text'
  imported_at: string
  source_sha256: string | null
  row_count: number
}

export type AliasRecord = {
  id: number
  alias_type: string
  source_value: string
  target_value: string
  confirmed: number
}

export type ReconcileFound = {
  item_id: number
  year: string
  period: string
  building: string
  relative_path: string
  photo_count: number
  missing_slots: string[]
  naming_suggestions: { filename: string; suggestion: string }[]
  status: string
}

export type ReconcileRow = {
  kind: 'ledger' | 'extra' | 'special' | 'slot_only'
  category: 'extinguisher' | 'box' | 'lamp'
  row_no: number | null
  section: string
  expected_building: string
  device_no: string
  specification: string
  last_replacement_date: string
  status: string
  found: ReconcileFound[]
  missing_slots: string[]
  naming_suggestions: { filename: string; suggestion: string }[]
  near_candidates: string[]
  building_match?: boolean
  marked_reshot: boolean
}

export type ReconcileResult = {
  root_id: number
  ledger_id: number
  ledger_name: string
  period: string | null
  total: number
  complete: number
  completion_rate: number
  counts: Record<string, number>
  building_progress: { building: string; total: number; complete: number; rate: number }[]
  rows: ReconcileRow[]
  reshoot_text: string
}


export type OrganizerRenameCandidate = {
  candidate_id: string
  photo_id: number
  item_id: number
  category: string
  category_name: string
  code: string
  building: string
  period: string
  source_relative: string
  target_relative: string
  source_name: string
  target_name: string
  sha256: string
  reason: string
  safe: boolean
  blocked_reason: string | null
}

export type OrganizerDuplicatePhoto = {
  sha256: string
  count: number
  photos: {
    photo_id: number
    item_id: number
    category: string
    category_name: string
    code: string
    building: string
    period: string
    filename: string
    relative_path: string
  }[]
}

export type OrganizerDuplicateCode = {
  category: string
  category_name: string
  code: string
  count: number
  items: { item_id: number; building: string; period: string; relative_path: string }[]
}

export type OrganizerVariantIssue = {
  type: string
  value: string
  suggestion: string
  reason: string
  item_id: number
  category: string
  code: string
  relative_path: string
}

export type OrganizerDirtyFile = Omit<OrganizerRenameCandidate, 'candidate_id' | 'target_relative' | 'target_name'> & {
  candidate_id: string | null
  target_relative: string | null
  target_name: string | null
}

export type OrganizerAnalysis = {
  root_id: number
  summary: {
    photos: number
    dirty_names: number
    safe_renames: number
    duplicate_photo_groups: number
    duplicate_codes: number
    near_code_pairs: number
    variant_issues: number
    hash_errors: number
  }
  dirty_files: OrganizerDirtyFile[]
  rename_candidates: OrganizerRenameCandidate[]
  duplicate_photos: OrganizerDuplicatePhoto[]
  duplicate_codes: OrganizerDuplicateCode[]
  near_codes: { category: string; first: string; second: string }[]
  variant_issues: OrganizerVariantIssue[]
  hash_errors: { relative_path: string; error: string }[]
}

export type RenamePreview = {
  root_id: number
  selected: OrganizerRenameCandidate[]
  missing_candidate_ids: string[]
  safe_count: number
  blocked_count: number
}

export type RenameExecutionResult = {
  executed: {
    candidate_id: string
    rename_log_id: number
    source_relative: string
    target_relative: string
    sha256: string
  }[]
  failed: { candidate_id: string; error: string }[]
}

export type RenameHistoryRecord = {
  id: number
  root_id: number
  created_at: string
  source_path: string
  target_path: string
  sha256: string | null
  reverted_at: string | null
}


export type RootStatus = {
  root_id: number
  connected: boolean
  is_cloud_stream: boolean
  last_scan_at: string | null
  cached_items: number
  cached_photos: number
  cached_thumbnails: number
  cloud_placeholders: number
  pending_imports: number
}

export type OfflineQueueEntry = {
  id: number
  root_id: number
  item_relative_path: string
  slot: string
  source_name: string
  replace_relative_path: string | null
  expected_original_sha256: string | null
  sha256: string
  size_bytes: number
  state: 'pending' | 'error' | 'synced'
  last_error: string | null
  created_at: string
  synced_at: string | null
}

export type ImportPhotoResult = ItemDetail & {
  offline_queued?: boolean
  offline_queue_entry?: OfflineQueueEntry
}

export type AppSettings = {
  theme: 'system' | 'light' | 'dark'
  thumbnail_quality: number
  slot_order: Record<string, string[]>
  quick_create: {
    category_code: string
    year: string
    period: string
    building: string
  }
  custom_slots: Record<string, string[]>
}

export type AppInfo = {
  version: string
  schema_version: number
  data_dir: string
  database_path: string
  cache_dir: string
  thumbnail_dir: string
  offline_dir: string
  backup_dir: string
  log_dir: string
  log_file: string
  log_size_bytes: number
  cache_size_bytes: number
  online_update_enabled: boolean
  online_update_reason: string
  online_update_installable: boolean
  online_update_install_reason: string
  online_update_repository: string
}

export type UpdateStatus = {
  current_version: string
  latest_version: string
  available: boolean
  signature_verified: boolean
  asset_name: string
  asset_size: number
  downloaded: boolean
  installable: boolean
  install_reason: string
  release_url: string
  notes: string
  asset_url?: string
}

export type UpdateInstallResult = {
  scheduled: boolean
  version: string
  backup_path: string
  log_path: string
}

export type BackupRestoreResult = {
  restored: boolean
  snapshot_path: string
  counts: Record<string, number>
  source_app_version: string | null
}

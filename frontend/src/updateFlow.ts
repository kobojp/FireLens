import type { UpdatePreparationPhase, UpdatePreparationStatus } from './types'

export const UPDATE_POLL_INTERVAL_MS = 250

const PHASE_LABELS: Record<UpdatePreparationPhase, string> = {
  idle: '等待開始',
  verifying_signature: '驗證 Ed25519 簽章',
  verifying_manifest: '核對版本、檔名與大小',
  downloading: '下載新版',
  verifying_sha256: '核對 SHA-256',
  self_test: '執行新版自我測試',
  ready: '安全驗證完成，等待確認',
  installing: '正在安裝並重新啟動',
  error: '更新失敗',
}

export function updatePhaseLabel(phase: UpdatePreparationPhase): string {
  return PHASE_LABELS[phase]
}

export function preparedForVersion(status: UpdatePreparationStatus | null, version: string): boolean {
  return Boolean(status?.ready && status.phase === 'ready' && status.version === version)
}

export function updateActionLabel(status: UpdatePreparationStatus | null, version: string): string {
  if (preparedForVersion(status, version)) return `繼續安裝 v${version}`
  if (status?.phase === 'error' && status.version === version) return `重試下載並安裝 v${version}`
  return `下載並安裝 v${version}`
}

export function updateProgressText(status: UpdatePreparationStatus): string {
  if (status.phase === 'downloading' && status.bytes_total && status.bytes_total > 0) {
    const percent = status.percent ?? Math.round(status.bytes_downloaded / status.bytes_total * 100)
    return `${percent}%（${status.bytes_downloaded.toLocaleString()} / ${status.bytes_total.toLocaleString()} bytes）`
  }
  if (status.error) return status.error
  return status.message
}

export function updateFailureMessage(status: UpdatePreparationStatus): string {
  const reason = status.error || status.message || '未知原因'
  return `${updatePhaseLabel(status.phase)}：${reason}`
}

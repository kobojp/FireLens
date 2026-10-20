import { describe, expect, it } from 'vitest'
import type { UpdatePreparationStatus } from './types'
import {
  preparedForVersion,
  updateActionLabel,
  updateFailureMessage,
  updatePhaseLabel,
  updateProgressText,
} from './updateFlow'

function status(overrides: Partial<UpdatePreparationStatus> = {}): UpdatePreparationStatus {
  return {
    phase: 'downloading',
    version: '1.6.0',
    message: '正在下載新版 FireLens…',
    bytes_downloaded: 50,
    bytes_total: 100,
    percent: 50,
    error: null,
    ready: false,
    running: true,
    update: null,
    ...overrides,
  }
}

describe('one-click update flow', () => {
  it('shows every security stage in Traditional Chinese', () => {
    expect(updatePhaseLabel('verifying_signature')).toContain('Ed25519')
    expect(updatePhaseLabel('verifying_sha256')).toContain('SHA-256')
    expect(updatePhaseLabel('self_test')).toContain('自我測試')
    expect(updatePhaseLabel('installing')).toContain('重新啟動')
  })

  it('shows download progress when total bytes are known', () => {
    expect(updateProgressText(status())).toContain('50%')
  })

  it('reuses an already verified update after the final confirmation is cancelled', () => {
    const ready = status({ phase: 'ready', ready: true, running: false })
    expect(preparedForVersion(ready, '1.6.0')).toBe(true)
    expect(updateActionLabel(ready, '1.6.0')).toBe('繼續安裝 v1.6.0')
  })

  it('offers a retry label and includes the failed stage in the error', () => {
    const failed = status({ phase: 'error', running: false, error: 'SHA-256 驗證失敗' })
    expect(updateActionLabel(failed, '1.6.0')).toContain('重試')
    expect(updateFailureMessage(failed)).toContain('SHA-256 驗證失敗')
  })
})

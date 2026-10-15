import { describe, expect, it } from 'vitest'
import { scanSummaryText, shouldAutoScan } from './scanPolicy'

describe('auto scan policy', () => {
  it('scans when there is no previous scan', () => {
    expect(shouldAutoScan(null, 5, new Date('2026-10-15T12:00:00Z'))).toBe(true)
  })

  it('respects the minimum interval using SQLite UTC timestamps', () => {
    const now = new Date('2026-10-15T12:10:00Z')
    expect(shouldAutoScan('2026-10-15 12:07:00', 5, now)).toBe(false)
    expect(shouldAutoScan('2026-10-15 12:04:00', 5, now)).toBe(true)
  })

  it('formats added, updated and removed counts', () => {
    expect(scanSummaryText({
      added_items: 1, updated_items: 2, removed_items: 3,
      added_photos: 4, updated_photos: 5, removed_photos: 6,
    })).toContain('項目 +1 / 更新 2 / 移除 3')
  })
})

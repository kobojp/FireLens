function parseSqliteUtc(value: string): number {
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const withZone = /(?:Z|[+-]\d\d:\d\d)$/.test(normalized) ? normalized : `${normalized}Z`
  return Date.parse(withZone)
}

export function shouldAutoScan(
  lastScanAt: string | null,
  minIntervalMinutes: number,
  now: Date = new Date(),
): boolean {
  if (!lastScanAt) return true
  const parsed = parseSqliteUtc(lastScanAt)
  if (!Number.isFinite(parsed)) return true
  return now.getTime() - parsed >= minIntervalMinutes * 60_000
}

export function scanSummaryText(summary: {
  added_items: number
  updated_items: number
  removed_items: number
  added_photos: number
  updated_photos: number
  removed_photos: number
}): string {
  return `項目 +${summary.added_items} / 更新 ${summary.updated_items} / 移除 ${summary.removed_items}；照片 +${summary.added_photos} / 更新 ${summary.updated_photos} / 移除 ${summary.removed_photos}`
}

import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Node-only source contract checks
import { readFileSync } from 'node:fs'
import { BackupHistoryDisclosure } from './BackupHistoryDisclosure'
import { displaySlotsForItem, unmappedPhotos } from './slots'
import type { ItemDetail } from './types'

const stats = readFileSync(new URL('./StatisticsView.tsx', import.meta.url), 'utf8')
const browse = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const style = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
const lamp: ItemDetail = {
  id: 1, root_id: 2, category_id: 3, category_code: 'lamp', category_name: '燈具',
  year: '2026年', period: '11月', building: '中正樓', code: '中-01-01',
  relative_path: '燈具/2026年/11月/中正樓/中-01-01', status: 'complete',
  photo_count: 1, slots: ['前', '中', '後'], custom_slots: ['請修單'],
  filename_aliases: {},
  photos: [{ id: 77, filename: '表單.jpg', relative_path: '燈具/表單.jpg',
    extension: '.jpg', slot: null, size_bytes: 100, mtime_ns: 1, cloud_placeholder: 0 }],
}

describe('M19-S history disclosure', () => {
  it('defaults closed while displaying count and keeping content mounted inside native details', () => {
    const html = renderToStaticMarkup(
      <BackupHistoryDisclosure count={3} offline={false}>
        <button type="button">預覽</button>
        <button type="button">復原本機</button>
      </BackupHistoryDisclosure>,
    )
    expect(html).toContain('<details')
    expect(html).not.toContain('<details open')
    expect(html).toContain('<summary')
    expect(html).toContain('已載入 3 份')
    expect(html).toContain('最多顯示 100 份')
    expect(html).toContain('預覽')
    expect(html).toContain('復原本機')
    expect(style).toContain('.shared-issue-backup-summary:focus-visible')
  })

  it('does not display an invented zero when the shared folder is offline', () => {
    const html = renderToStaticMarkup(<BackupHistoryDisclosure count={0} offline><span>目前無法讀取</span></BackupHistoryDisclosure>)
    expect(html).toContain('共用資料夾離線')
    expect(html).not.toContain('已載入 0 份')
  })

  it('uses the selected-root key to reset disclosure, without triggering restore/scan on expand', () => {
    expect(stats).toContain('<BackupHistoryDisclosure key={syncRootId}')
    expect(stats).toContain('count={syncBackups.length}')
    expect(stats).toContain('offline={syncStatus.state')
    expect(stats).toContain('api.previewSharedIssueBackup(syncRootId, backup.id)')
    expect(stats).toContain('api.restoreSharedIssueBackup(selectedRoot, backup.id)')
    expect(stats).toContain("'無法取得復原預覽'")
    expect(stats).not.toContain('<h3>本機歷史備份（最多顯示 100 份）</h3>')
  })
})

describe('M19-R optional photo slot quick actions', () => {
  it('uses required plus optional slot names in the same ordering as the wall', () => {
    expect(displaySlotsForItem(lamp)).toEqual(['前', '中', '後', '請修單'])
    expect(displaySlotsForItem(lamp, ['後', '前', '中'])).toEqual(['後', '前', '中', '請修單'])
    expect(displaySlotsForItem({ ...lamp, custom_slots: [] })).toEqual(['前', '中', '後'])
    expect(displaySlotsForItem(null)).toEqual([])
  })

  it('keeps unmapped photos separate and exposes optional slot for quick safe rename', () => {
    expect(unmappedPhotos(lamp)[0]?.filename).toBe('表單.jpg')
    expect(browse).toContain('{orderedSlots.map((slot) => (')
    expect(browse).not.toContain('{item.slots.map((slot) => (')
    expect(browse).toContain('preparePhotoRename(photo, `${slot}${photo.extension}`, `快速歸槽：${slot}`)')
    expect(browse).toContain('disabled={busy || scanRunning || rootStatusInfo?.connected === false || Boolean(photo.cloud_placeholder)}')
    expect(browse).toContain('return displaySlotsForItem(item, appSettings?.slot_order[item.category_code])')
  })

  it('does not turn optional slots into required status', () => {
    const scanner = readFileSync(new URL('../../backend/app/scanner.py', import.meta.url), 'utf8')
    expect(scanner).toContain('if set(required) <= matched:')
    expect(scanner).toContain('custom_slots: tuple[str, ...] = ()')
  })
})

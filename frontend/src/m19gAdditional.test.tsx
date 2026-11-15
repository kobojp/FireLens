import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Source inspection assertions in Node Vitest
import { readFileSync } from 'node:fs'
import { adjacentPreviewPhoto, previewPhotosForItem } from './photoPreviewNavigation'
import { AppConfirmDialog } from './AppConfirmDialog'
import type { ItemDetail, PhotoRecord } from './types'

const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const settings = readFileSync(new URL('./SettingsView.tsx', import.meta.url), 'utf8')
const dialog = readFileSync(new URL('./AppConfirmDialog.tsx', import.meta.url), 'utf8')

function photo(id: number, slot: string | null): PhotoRecord {
  return { id, slot, filename: `photo-${id}.jpg`, relative_path: `device/photo-${id}.jpg`,
    extension: '.jpg', size_bytes: 128, mtime_ns: 1, cloud_placeholder: 0 }
}

function device(id: number, photos: PhotoRecord[]): ItemDetail {
  return { id, root_id: 1, category_id: 1, category_code: 'box',
    category_name: '放置盒', year: '2026年', period: '11月份更換',
    building: '中正樓', code: `LB-02-0${id}`, relative_path: 'box/2026年/11月份更換/中正樓',
    status: '完整', photo_count: photos.length, slots: ['前', '中', '後'],
    custom_slots: ['壓力錶'], filename_aliases: {}, photos }
}

describe('M19-G photo preview and verified update confirmation', () => {
  it('navigates only the selected device in visible slot order with multiple photos', () => {
    const own = device(3, [photo(2, '中'), photo(1, '前'), photo(3, '後'),
      photo(4, '前'), photo(5, '壓力錶'), photo(6, null)])
    const others = device(4, [photo(7, '前'), photo(8, '後')])
    const result = previewPhotosForItem(own, ['前', '中', '後', '壓力錶'])
    expect(result.map(x => x.id)).toEqual([1, 4, 2, 3, 5, 6])
    expect(previewPhotosForItem(others, ['前', '中', '後']).map(x => x.id)).toEqual([7, 8])
    expect(adjacentPreviewPhoto(result, 1, -1)).toBeNull()
    expect(adjacentPreviewPhoto(result, 1, 1)?.id).toBe(4)
    expect(adjacentPreviewPhoto(result, 4, 1)?.id).toBe(2)
    expect(adjacentPreviewPhoto(result, 6, 1)).toBeNull()
    expect(adjacentPreviewPhoto(result, 7, 1)).toBeNull()
    expect(previewPhotosForItem(null, ['前'])).toEqual([])
  })

  it('does not duplicate a photo whose slot appears twice in configured ordering', () => {
    const result = previewPhotosForItem(device(3, [photo(10, '前'), photo(11, null)]), ['前', '前', '中'])
    expect(result.map(x => x.id)).toEqual([10, 11])
  })

  it('shows previous, next and count; resets zoom and closes preview when changing devices', () => {
    const viewer = readFileSync(new URL('./InspectorImageViewer.tsx', import.meta.url), 'utf8')
    const modal = readFileSync(new URL('./AppDialog.tsx', import.meta.url), 'utf8')
    expect(app).toContain('photosInDisplayOrder(item, orderedSlots)')
    expect(app).toContain('useEffect(() => { setPreview(null) }, [rootId, item])')
    expect(viewer).toContain('adjacentImage(images, current.id,')
    expect(viewer).toContain('setZoom(1)')
    expect(viewer).toContain('← 上一張')
    expect(viewer).toContain('下一張 →')
    expect(viewer).toContain('activeIndex + 1')
    expect(viewer).toContain('disabled={previous === null}')
    expect(viewer).toContain('disabled={next === null}')
    expect(modal).toContain("event.key === 'Escape'")
    expect(viewer).toContain("event.key === 'ArrowLeft'")
  })

  it('renders a centered safe update confirmation with two independent actions', () => {
    const html = renderToStaticMarkup(<AppConfirmDialog title="準備安裝更新"
      cancelLabel="取消／稍後更新" confirmLabel="立即安裝並重新啟動"
      onCancel={() => undefined} onConfirm={() => undefined}>
      <p>v1.12.1 簽章已驗證</p>
    </AppConfirmDialog>)
    expect(html).toContain('role="dialog"')
    expect(html).toContain('aria-modal="true"')
    expect(html).toContain('準備安裝更新')
    expect(html).toContain('取消／稍後更新')
    expect(html).toContain('立即安裝並重新啟動')
    expect(html).toContain('v1.12.1')
    expect(readFileSync(new URL('./AppDialog.tsx', import.meta.url), 'utf8')).toContain("event.key === 'Escape'")
    expect(readFileSync(new URL('./AppDialog.tsx', import.meta.url), 'utf8')).toContain("event.key === 'Tab'")
    expect(readFileSync(new URL('./AppDialog.tsx', import.meta.url), 'utf8')).toContain("document.body.style.overflow = 'hidden'")
    expect(readFileSync(new URL('./AppDialog.tsx', import.meta.url), 'utf8')).toContain('previous.focus()')
  })

  it('does not trigger installation until explicit confirmation after verification', () => {
    const start = settings.indexOf('async function downloadAndInstallUpdate()')
    const workflow = settings.slice(start, settings.indexOf('if (!draft) return', start))
    expect(workflow).not.toContain('window.confirm(')
    expect(workflow).toContain('setPendingInstallVersion(version)')
    expect(settings).toContain('preparedForVersion(updateProgress, version)')
    expect(settings).toContain('installConfirmationBusy.current = true')
    expect(settings).toContain('try { await installVerifiedUpdate(version) }')
    expect(settings).toContain('onConfirm={() => { void confirmVerifiedInstall() }}')
    expect(settings).toContain('onCancel={cancelVerifiedInstall}')
  })
})

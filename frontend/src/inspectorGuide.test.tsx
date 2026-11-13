import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Node-only source contract tests
import { readFileSync } from 'node:fs'
import { api, ApiError } from './api'
import { adjacentImage, InspectorImageViewer, type InspectorImage } from './InspectorImageViewer'
import { DuplicatePhotoPanel } from './DuplicatePhotoPanel'
import type { RootRecord } from './types'

const images: InspectorImage[] = [
  { id: 1, filename: '前.jpg', title: '水帶 · 水-01 · 前.jpg', subtitle: '倉庫 · 前', path: '水帶/水-01/前.jpg', src: '/api/photos/1/content' },
  { id: 2, filename: '中.jpg', title: '水帶 · 水-01 · 中.jpg', subtitle: '倉庫 · 中', path: '水帶/水-01/中.jpg', src: '/api/photos/2/content' },
  { id: 3, filename: '後.jpg', title: '水帶 · 水-01 · 後.jpg', subtitle: '倉庫 · 後', path: '水帶/水-01/後.jpg', src: '/api/photos/3/content' },
]
const roots: RootRecord[] = [{
  id: 1, label: '合成測試根目錄', path: '/synthetic',
  is_cloud_stream: 0, created_at: '2026-01-01', last_scan_at: null,
}]
const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const quality = readFileSync(new URL('./PhotoQualityView.tsx', import.meta.url), 'utf8')
const duplicatePanel = readFileSync(new URL('./DuplicatePhotoPanel.tsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

describe('M19-F fullscreen inspector and guided scan', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('navigates only visible images and has safe first/last boundaries', () => {
    expect(adjacentImage(images, 2, -1)).toBe(1)
    expect(adjacentImage(images, 2, 1)).toBe(3)
    expect(adjacentImage(images, 1, -1)).toBeNull()
    expect(adjacentImage(images, 3, 1)).toBeNull()
    expect(adjacentImage(images, 999, 1)).toBeNull()
    expect(adjacentImage([], 1, 1)).toBeNull()
  })

  it('renders the photo-wall-style large viewer with zoom, navigation and original source', () => {
    const html = renderToStaticMarkup(
      <InspectorImageViewer images={images} activeId={2}
        onSelect={() => undefined} onClose={() => undefined} />,
    )
    expect(html).toContain('role="dialog"')
    expect(html).toContain('aria-modal="true"')
    expect(html).toContain('上一張')
    expect(html).toContain('下一張')
    expect(html).toContain('2／3')
    expect(html).toContain('圖片縮放')
    expect(html).toContain('100%')
    expect(html).toContain('水帶/水-01/中.jpg')
    expect(html).toContain('/api/photos/2/content')
    expect(styles).toContain('height: min(1050px, 96dvh)')
    expect(styles).toContain('inspector-lightbox-canvas')
    expect(renderToStaticMarkup(
      <InspectorImageViewer images={images} activeId={99}
        onSelect={() => undefined} onClose={() => undefined} />,
    )).toBe('')
  })

  it('shares the viewer in both inspector modes with page-specific ordered photos', () => {
    expect(quality).toContain('<InspectorImageViewer images={qualityImages}')
    expect(duplicatePanel).toContain('<InspectorImageViewer images={images}')
    expect(quality).toContain('item.slots.flatMap(slot')
    expect(duplicatePanel).toContain('(gallery?.groups ?? []).flatMap')
  })

  it('renders the three-step quest and visible highlighted scan button without auto-start', () => {
    const html = renderToStaticMarkup(
      <DuplicatePhotoPanel rootId={1} roots={roots} guideTicket={7}
        onOpenItem={() => undefined} onGuideFinish={() => undefined}
        onGuideCancel={() => undefined} />,
    )
    expect(html).toContain('重複掃描操作引導')
    expect(html).toContain('第 1 步')
    expect(html).toContain('第 2 步')
    expect(html).toContain('第 3 步')
    expect(html).toContain('scan-guide-target')
    expect(html).toContain('開始重複掃描')
    expect(html).toContain('增量掃描（預設）')
    expect(styles).toContain('.scan-guide-target')
    expect(duplicatePanel).toContain('onClick={() => void startScan()}')
    expect(duplicatePanel).toContain('if (guideTicket != null) setGuideStarted(true)')
  })

  it('keeps failed paste bytes in memory and navigates to the correct root for manual scanning', () => {
    expect(app).toContain('setIndexRequired({')
    expect(app).toContain("err.details?.code === 'duplicate_index_required'")
    expect(app).toContain('setScanGuideTicket(++nextGuideTicket.current)')
    expect(app).toContain("setView('quality')")
    expect(app).toContain('pendingStatsNavigation.current = { rootId: pending.rootId, itemId: pending.itemId }')
    expect(app).toContain('void upload(pending.slot, pending.file, pending.replacePhotoId)')
    expect(app).toContain('照片尚未儲存，不是貼上成功')
    expect(quality).toContain("setMode('duplicates')")
    expect(quality).toContain('setRootId(guidedRootId)')
    expect(app).toContain('onGuideFinish={returnFromGuidedScan}')
  })

  it('releases a previously open lightbox when the retained tab becomes hidden', () => {
    expect(app).toContain("isActive={view === 'quality'}")
    expect(quality).toContain('if (!isActive) setPreview(null)')
    expect(duplicatePanel).toContain('if (!isActive) setPreview(null)')
    expect(quality).toContain('isActive && qualityImages.some')
    expect(duplicatePanel).toContain('isActive && images.some')
  })

  it('decodes stable index-required HTTP 409 separately from a true duplicate', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: {
        code: 'duplicate_index_required', message: '請先執行手動重複掃描',
      } }),
    }))
    await expect(api.categories()).rejects.toMatchObject({
      status: 409, details: { code: 'duplicate_index_required', message: '請先執行手動重複掃描' },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: {
        code: 'duplicate_photo', message: '相同圖片已存在', matches: [],
      } }),
    }))
    try {
      await api.categories()
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect((error as ApiError).details).toMatchObject({ code: 'duplicate_photo', matches: [] })
    }
  })
})

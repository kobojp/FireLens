import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Node fs import for source contracts verified in Vitest
import { readFileSync } from 'node:fs'
import { DuplicatePhotoPanel } from './DuplicatePhotoPanel'
import { PhotoQualityView } from './PhotoQualityView'

const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8')
const panel = readFileSync(new URL('./DuplicatePhotoPanel.tsx', import.meta.url), 'utf8')
const view = readFileSync(new URL('./PhotoQualityView.tsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

const roots = [{
  id: 1, label: '合成測試來源', path: '/synthetic/photos',
  is_cloud_stream: 0, created_at: '2026-01-01', last_scan_at: null,
}]

describe('M19-C exact duplicates user workflow', () => {
  it('renders an independent duplicate checking panel with manual incremental scan', () => {
    const html = renderToStaticMarkup(
      <DuplicatePhotoPanel roots={roots} rootId={1} onOpenItem={() => undefined} />,
    )
    expect(html).toContain('跨設備')
    expect(html).toContain('開始重複掃描')
    expect(html).toContain('增量掃描（預設）')
    expect(html).toContain('完整重新掃描')
    expect(html).toContain('取消掃描')
    expect(html).toContain('匯出 CSV')
    expect(html).toContain('匯出 Excel')
  })

  it('integrates into quality inspector but never automatically starts scanning', () => {
    const html = renderToStaticMarkup(
      <PhotoQualityView roots={roots} defaultRootId={1} onOpenItem={() => undefined} />,
    )
    expect(html).toContain('重複圖片')
    expect(view).toContain("setMode('duplicates')")
    expect(view).toContain('<DuplicatePhotoPanel roots={roots}')
    expect(panel).toContain('onClick={() => void startScan()}')
    expect(api).toContain("duplicateScan: (rootId: number, full: boolean)")
    expect(api).toContain("duplicateGallery: (rootId: number, params: URLSearchParams)")
  })

  it('uses a structured HTTP 409 conflict and displays both images before approval', () => {
    expect(api).toContain("detail.code === 'duplicate_photo'")
    expect(api).toContain('details: DuplicateErrorInfo | null')
    expect(app).toContain('duplicateUpload.matches.map(match')
    expect(app).toContain('duplicate-compare-grid')
    expect(app).toContain('準備新增的照片')
    expect(app).toContain('查看原照片')
    expect(app).toContain('void upload(pending.slot, pending.file, pending.replacePhotoId, true)')
  })

  it('keeps source metadata and responsive quality table styling', () => {
    expect(panel).toContain("photo.relative_path")
    expect(panel).toContain("photo.item_id")
    expect(panel).toContain("setPreview(photo.photo_id)")
    expect(panel).toContain("<InspectorImageViewer images={images}")
    expect(panel).toContain('重複群組')
    expect(css).toContain('.duplicates-photo-grid')
    expect(css).toContain('html[data-theme="dark"] .duplicates-photo')
  })
})

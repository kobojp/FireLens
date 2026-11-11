import { describe, expect, it } from 'vitest'
// @ts-expect-error Node fs used by Vitest source inspection only.
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf-8')
const view = readFileSync(new URL('./PhotoQualityView.tsx', import.meta.url), 'utf-8')
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf-8')
const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf-8')

describe('M18 photo quality page decisions', () => {
  it('is a separate top-level tab immediately right of organizer', () => {
    const organizer = app.indexOf('>整理工具</button>')
    const quality = app.indexOf('>照片品質檢查</button>')
    const settings = app.indexOf('>設定</button>')
    expect(organizer).toBeGreaterThan(0)
    expect(quality).toBeGreaterThan(organizer)
    expect(settings).toBeGreaterThan(quality)
    expect(app).toContain('view === \'quality\' ? (')
    expect(app).toContain('<PhotoQualityView roots={roots}')
  })

  it('defaults to manual incremental scan and never runs scan from an effect', () => {
    expect(view).toContain('const [full, setFull] = useState(false)')
    expect(view).toContain('<option value="incremental">增量掃描')
    expect(view).toContain('<option value="full">完整重新掃描')
    expect(view).toContain('onClick={() => void startScan()}')
    expect(api).toContain("qualityScan: (rootId: number, full: boolean")
    expect(api).toMatch(/qualityScan:[\s\S]*?method: 'POST'/)
    expect(view).toContain('api.qualityScan(rootId, full, category, period)')
  })

  it('supports quality and manual review filters plus matching export scope', () => {
    expect(view).toContain('qualityFilter, reviewFilter, sortBy')
    expect(view).toContain('status_filter: qualityFilter, review_filter: reviewFilter')
    expect(view).toContain('api.reviewQualityPhoto(photo.id, value)')
    expect(view).toContain('<option value="reshoot">待補拍</option>')
    expect(view).toContain('<option value="wrong_content">拍攝內容錯誤</option>')
    expect(view).toContain("saveExport('csv')")
    expect(view).toContain("saveExport('xlsx')")
    expect(view).toContain("api.saveQualityExport(rootId")
    expect(view).toContain("api.openExport(exportResult.open_token, 'folder')")
    expect(view).toContain('onOpenItem(rootId, item.id)')
  })

  it('exposes special folder and variant-name diagnostics without automatic renames', () => {
    expect(view).toContain('<option value="special">特例資料夾</option>')
    expect(view).toContain('<option value="variant_name">名稱異體字</option>')
    expect(view).toContain('item.special &&')
    expect(view).toContain('item.name_variants?.map(')
    expect(view).toContain('item.missing_slots.includes(slot)')
    expect(view).toContain('status_filter: qualityFilter')
  })

  it('renders scan progress, ETA, statistic panels and card navigation', () => {
    expect(view).toContain('qualityProgress(job, nowSeconds)')
    expect(view).toContain('role="progressbar"')
    expect(view).toContain('quality-progress-percent')
    expect(view).toContain('預估剩餘')
    expect(view).toContain('quality-stats')
    expect(view).toContain('quality-action quality-open-wall')
    expect(css).toContain('.quality-export-actions')
    expect(css).toContain('.quality-progress-track')
  })

  it('renders fixed image slots, responsive card gallery and accessible original preview', () => {
    expect(view).toContain('item.slots.map((slot)')
    expect(view).toContain('display_slot ?? photo.slot')
    expect(view).toContain('preview &&')
    expect(view).toContain('api.photoUrl(preview)')
    expect(css).toContain('.quality-gallery')
    expect(css).toContain('.quality-slots')
    expect(view).toContain('上一頁')
    expect(view).toContain('下一頁')
  })
})

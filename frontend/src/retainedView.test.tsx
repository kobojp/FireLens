import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { RetainedView, initialVisitedTabs, withVisitedTab } from './RetainedView'
// @ts-expect-error Node source inspection for parent view mounting contract.
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const quality = readFileSync(new URL('./PhotoQualityView.tsx', import.meta.url), 'utf8')
const reconcile = readFileSync(new URL('./ReconcileView.tsx', import.meta.url), 'utf8')

describe('M19-D return from equipment photo wall keeps workspace state', () => {
  it('mounts each page after its first visit and retains it across browse', () => {
    const first = initialVisitedTabs
    expect(first).toEqual({ quality: false, reconcile: false })
    const visitedQuality = withVisitedTab(first, 'quality')
    const onPhotoWall = withVisitedTab(visitedQuality, 'browse')
    const visitedReconcile = withVisitedTab(onPhotoWall, 'reconcile')
    expect(onPhotoWall).toBe(visitedQuality)
    expect(withVisitedTab(visitedReconcile, 'browse')).toBe(visitedReconcile)
    expect(withVisitedTab(visitedReconcile, 'quality')).toBe(visitedReconcile)
    expect(visitedReconcile).toEqual({ quality: true, reconcile: true })
  })

  it('hides inactive panels from keyboard access without removing their previous inputs', () => {
    const hidden = renderToStaticMarkup(
      <RetainedView visible={false}><input name="search" defaultValue="三-07-25" /></RetainedView>,
    )
    expect(hidden).toContain('hidden=""')
    expect(hidden).toContain('inert=""')
    expect(hidden).toContain('aria-hidden="true"')
    expect(hidden).toContain('display:none')
    expect(hidden).toContain('value="三-07-25"')
    const shown = renderToStaticMarkup(
      <RetainedView visible={true}><input name="search" defaultValue="三-07-25" /></RetainedView>,
    )
    expect(shown).toContain('display:contents')
    expect(shown).not.toContain('hidden=""')
    expect(shown).toContain('value="三-07-25"')
  })

  it('uses single persistent component instances rather than remounting in route branches', () => {
    expect((app.match(/<ReconcileView\b/g) ?? []).length).toBe(1)
    expect((app.match(/<PhotoQualityView\b/g) ?? []).length).toBe(1)
    expect(app).toContain("visitedTabs.reconcile || view === 'reconcile'")
    expect(app).toContain("visitedTabs.quality || view === 'quality'")
    expect(app).toContain("<RetainedView visible={view === 'reconcile'}>")
    expect(app).toContain("<RetainedView visible={view === 'quality'}>")
    expect(app).toContain("setVisitedTabs((previous) => withVisitedTab(previous, view))")
    expect(app).toContain('pendingStatsNavigation.current = { rootId: nextRootId, itemId }')
  })

  it('retains quality filters, duplicate subtab, ledger selection and results in kept-alive instances', () => {
    for (const field of ['query', 'category', 'period', 'building', 'mode', 'offset', 'gallery', 'job']) {
      expect(quality).toContain(`const [${field}, set`)
    }
    expect(quality).toContain('<DuplicatePhotoPanel')
    for (const field of ['ledgerId', 'classificationFilter', 'missingOnly', 'result', 'textLedger']) {
      expect(reconcile).toContain(`const [${field}, set`)
    }
  })
})

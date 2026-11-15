import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Node-only source contract checks
import { readFileSync } from 'node:fs'
import { PhotoQualityView } from './PhotoQualityView'
import { qualityPeriodsFromTree } from './qualityPeriods'
import type { TreeNode } from './types'

const view = readFileSync(new URL('./PhotoQualityView.tsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
const tree: TreeNode[] = [
  { type: 'category', key: 'extinguisher', label: '滅火器', children: [
    { type: 'year', key: '2026年', label: '2026年', children: [
      { type: 'period', key: '10月份更換', label: '10月份更換' },
      { type: 'period', key: '2月份更換', label: '2月份更換' },
    ] },
    { type: 'year', key: '2025年', label: '2025年', children: [
      { type: 'period', key: '10月份更換', label: '10月份更換' },
    ] },
  ] },
  { type: 'category', key: 'lamp', label: '燈具', children: [
    { type: 'year', key: '2026年', label: '2026年', children: [
      { type: 'period', key: '特別批次 B', label: '特別批次 B' },
    ] },
  ] },
]

describe('M19-O quality period selector', () => {
  it('deduplicates and naturally sorts across years for one category', () => {
    expect(qualityPeriodsFromTree(tree, 'extinguisher')).toEqual(['2月份更換', '10月份更換'])
    expect(qualityPeriodsFromTree(tree, 'lamp')).toEqual(['特別批次 B'])
  })

  it('merges all categories without inventing months and supports empty roots', () => {
    expect(qualityPeriodsFromTree(tree, '')).toEqual(['2月份更換', '10月份更換', '特別批次 B'])
    expect(qualityPeriodsFromTree([], '')).toEqual([])
    expect(qualityPeriodsFromTree(tree, 'box')).toEqual([])
  })

  it('renders a disabled initial dropdown pending tree and no arbitrary text input', () => {
    const html = renderToStaticMarkup(<PhotoQualityView roots={[]} defaultRootId={null}
      onOpenItem={() => undefined} />)
    expect(html).toContain('全部月份／批次')
    expect(html).toContain('<select')
    expect(view).not.toContain('placeholder="全部月份"')
    expect(view).toContain('qualityPeriodsFromTree(periodTree.nodes, category)')
    expect(view).toContain('setPeriod(\'\'); setOffset(0)')
    expect(view).toContain('api.qualityScan(rootId, full, category, period)')
  })

  it('ignores old tree response on root change and does not scan merely for period options', () => {
    expect(view).toContain('let active = true')
    expect(view).toContain('if (!active) return')
    expect(view).toContain('api.tree(rootId)')
    expect(view).toContain('if (periodOptionsReady && period && !periodOptions.includes(period))')
    expect(view).toContain('setPeriodTreeError(')
    expect(view).toContain('原有結果保留')
  })
})

describe('M19-N quality scan toolbar', () => {
  it('reuses common quality button palette with semantic groups', () => {
    const html = renderToStaticMarkup(<PhotoQualityView roots={[]} defaultRootId={null}
      onOpenItem={() => undefined} />)
    for (const value of ['quality-action-save', 'quality-action-scan', 'quality-action-cancel',
      'quality-action-refresh', 'quality-parameter-group', 'quality-operation-group']) {
      expect(html).toContain(value)
      expect(css).toContain(value)
    }
    expect(html).toContain('開始掃描')
    expect(view).toContain("? '掃描中…' : '開始掃描'")
  })

  it('guards async double clicks, keeps scan confirmation, and refresh never starts scan', () => {
    expect(view).toContain('actionLocks.current.save')
    expect(view).toContain('actionLocks.current.start')
    expect(view).toContain('actionLocks.current.cancel')
    expect(view).toContain('actionLocks.current.refresh')
    expect(view).toContain("sensitivity !== savedSensitivity || job?.state === 'running'")
    expect(view).toContain('if (full && !(await confirmAction(')
    const refresh = view.slice(view.indexOf('async function refreshList()'), view.indexOf('async function saveReview('))
    expect(refresh).toContain('await refresh()')
    expect(refresh).not.toContain('api.qualityScan(')
    expect(view).toContain('disabled={rootId === null || manualRefreshing || loading}')
    expect(view).toContain("cancellingScan ? '取消中…' : '取消掃描'")
  })
})

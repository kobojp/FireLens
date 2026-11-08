import { describe, expect, it } from 'vitest'
import { createReconcileRequestGuard, isDeviceCategory, periodsForCategory, sameReconcileScope } from './reconcileScope'
import type { TreeNode } from './types'

const tree: TreeNode[] = [
  { type: 'category', key: 'extinguisher', label: '滅火器', children: [
    { type: 'year', key: '2026年', label: '2026年', children: [
      { type: 'period', key: '10月份更換', label: '10月份更換' },
      { type: 'period', key: '11月份更換', label: '11月份更換' },
    ] },
    { type: 'year', key: '2025年', label: '2025年', children: [
      { type: 'period', key: '10月份更換', label: '10月份更換' },
    ] },
  ] },
  { type: 'category', key: 'box', label: '放置盒', children: [
    { type: 'year', key: '2026年', label: '2026年', children: [
      { type: 'period', key: '11月份更換', label: '11月份更換' },
    ] },
  ] },
  { type: 'category', key: 'lamp', label: '燈具', children: [
    { type: 'year', key: '2026年', label: '2026年', children: [
      { type: 'period', key: '1月份更換', label: '1月份更換' },
    ] },
  ] },
]

describe('reconciliation category-specific search scopes', () => {
  it('only lists periods for the chosen category, deduplicating years', () => {
    expect(periodsForCategory(tree, 'extinguisher')).toEqual(['10月份更換', '11月份更換'])
    expect(periodsForCategory(tree, 'box')).toEqual(['11月份更換'])
    expect(periodsForCategory(tree, 'lamp')).toEqual(['1月份更換'])
  })
  it('allows missing categories and empty trees without inventing periods', () => {
    expect(periodsForCategory([], 'lamp')).toEqual([])
    expect(periodsForCategory(tree.filter((n) => n.key !== 'box'), 'box')).toEqual([])
  })
  it('rejects unsupported device types, prevents cross-category request scopes', () => {
    expect(isDeviceCategory('box')).toBe(true)
    expect(isDeviceCategory('extinguisher')).toBe(true)
    expect(isDeviceCategory('lamp')).toBe(true)
    expect(isDeviceCategory('other')).toBe(false)
    const scope = { rootId: 1, ledgerId: 2, category: 'extinguisher' as const, period: '10月份更換' }
    expect(sameReconcileScope(scope, { ...scope })).toBe(true)
    expect(sameReconcileScope(scope, { ...scope, category: 'box' })).toBe(false)
    expect(sameReconcileScope(scope, { ...scope, period: '11月份更換' })).toBe(false)
    expect(sameReconcileScope(scope, { ...scope, rootId: 3 })).toBe(false)
    expect(sameReconcileScope(scope, { ...scope, ledgerId: 4 })).toBe(false)
  })
  it('invalidates stale reconciliation and export responses on scope change', async () => {
    const guard = createReconcileRequestGuard()
    const old = guard.next()
    guard.invalidate()
    const latest = guard.next()
    const received: string[] = []
    await Promise.resolve().then(() => {
      if (guard.isCurrent(old)) received.push('outdated')
      if (guard.isCurrent(latest)) received.push('current')
    })
    expect(received).toEqual(['current'])
    guard.invalidate()
    expect(guard.isCurrent(latest)).toBe(false)
  })

})

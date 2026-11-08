import type { TreeNode } from './types'

export type DeviceCategory = 'extinguisher' | 'box' | 'lamp'
export const DEVICE_CATEGORY_LABELS: Record<DeviceCategory, string> = {
  extinguisher: '滅火器', box: '放置盒', lamp: '燈具',
}

export function isDeviceCategory(value: string): value is DeviceCategory {
  return value === 'extinguisher' || value === 'box' || value === 'lamp'
}

/** Periods belong only to the currently selected category and root tree. */
export function periodsForCategory(nodes: readonly TreeNode[], category: DeviceCategory): string[] {
  const names = new Set<string>()
  for (const node of nodes) {
    if (node.type !== 'category' || node.key !== category) continue
    for (const year of node.children ?? []) {
      if (year.type !== 'year') continue
      for (const period of year.children ?? []) {
        if (period.type === 'period') names.add(period.key)
      }
    }
  }
  return Array.from(names).sort((a, b) => a.localeCompare(b, 'zh-Hant', { numeric: true }))
}

export function sameReconcileScope(
  a: { rootId: number | null, ledgerId: number | null, category: DeviceCategory, period: string },
  b: { rootId: number | null, ledgerId: number | null, category: DeviceCategory, period: string },
): boolean {
  return a.rootId === b.rootId && a.ledgerId === b.ledgerId &&
    a.category === b.category && a.period === b.period
}

/** Ignore old response after scope/ledger changes or departure. */
export function createReconcileRequestGuard() {
  let generation = 0
  return {
    next: () => ++generation,
    invalidate: () => { generation++ },
    isCurrent: (value: number) => value === generation,
  }
}

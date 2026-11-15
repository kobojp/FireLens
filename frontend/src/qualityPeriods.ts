import type { TreeNode } from './types'
import { isDeviceCategory, periodsForCategory } from './reconcileScope'

/** Root-scoped safe tree index, not an on-demand scan. */
export function qualityPeriodsFromTree(nodes: readonly TreeNode[], category: string): string[] {
  if (category && isDeviceCategory(category)) return periodsForCategory(nodes, category)
  const names = new Set<string>()
  for (const node of nodes) {
    if (node.type !== 'category' || (category && node.key !== category)) continue
    for (const year of node.children ?? []) {
      if (year.type !== 'year') continue
      for (const period of year.children ?? []) {
        if (period.type === 'period') names.add(period.key)
      }
    }
  }
  return Array.from(names).sort((a, b) => a.localeCompare(b, 'zh-Hant', { numeric: true }))
}

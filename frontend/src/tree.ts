import type { TreeNode } from './types'

export function countItems(nodes: TreeNode[]): number {
  return nodes.reduce((total, node) => {
    if (node.type === 'item') return total + 1
    return total + countItems(node.children ?? [])
  }, 0)
}

export function countByStatus(nodes: TreeNode[]): Record<string, number> {
  const counts: Record<string, number> = {}
  const visit = (node: TreeNode) => {
    if (node.type === 'item') {
      const status = node.status ?? 'unknown'
      counts[status] = (counts[status] ?? 0) + 1
      return
    }
    node.children?.forEach(visit)
  }
  nodes.forEach(visit)
  return counts
}

/** Full hierarchical key prevents collisions between periods of different years. */
export function branchPathKey(path: Pick<TreeNode, 'type' | 'key'>[]): string {
  return path.map((node) => node.type + ':' + encodeURIComponent(node.key)).join('/')
}

/** Only expand the path to the folder that was created, preserving all other choices. */
export function revealCreatedBranch(
  previous: readonly string[] | undefined,
  categoryKeys: readonly string[],
  createdPath: Pick<TreeNode, 'type' | 'key'>[],
): string[] {
  const next = new Set(previous ?? categoryKeys)
  for (let depth = 1; depth <= createdPath.length; depth++) {
    if (createdPath[depth - 1].type !== 'item') {
      next.add(branchPathKey(createdPath.slice(0, depth)))
    }
  }
  return [...next]
}

export function toggleTreeBranch(
  previous: readonly string[] | undefined,
  categoryKeys: readonly string[],
  pathKey: string,
): string[] {
  const next = new Set(previous ?? categoryKeys)
  if (next.has(pathKey)) next.delete(pathKey)
  else next.add(pathKey)
  return [...next]
}

/** Used for quick-create flows, where the path is known before a tree refresh. */
export function itemBranchPath(
  category: string, year: string, period: string, building: string, id: number,
): Pick<TreeNode, 'type' | 'key'>[] {
  return [
    { type: 'category', key: category },
    { type: 'year', key: year },
    { type: 'period', key: period },
    { type: 'building', key: building },
    { type: 'item', key: String(id) },
  ]
}

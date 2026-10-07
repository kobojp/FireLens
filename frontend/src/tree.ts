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

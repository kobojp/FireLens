import type { TreeNode } from './types'

export function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  const normalized = query.trim().toLocaleLowerCase('zh-Hant')
  if (!normalized) return nodes

  function visit(node: TreeNode, ancestors: string[]): TreeNode | null {
    const own = node.label.toLocaleLowerCase('zh-Hant').includes(normalized)
    const pathMatch = [...ancestors, node.label]
      .join(' / ')
      .toLocaleLowerCase('zh-Hant')
      .includes(normalized)
    const children = (node.children ?? [])
      .map((child) => visit(child, [...ancestors, node.label]))
      .filter((child): child is TreeNode => child !== null)
    if (own || pathMatch || children.length > 0) {
      return children.length > 0 ? { ...node, children } : { ...node }
    }
    return null
  }

  return nodes
    .map((node) => visit(node, []))
    .filter((node): node is TreeNode => node !== null)
}

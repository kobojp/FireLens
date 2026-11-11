import { useEffect, useRef } from 'react'
import { branchPathKey } from './tree'
import type { TreeNode } from './types'

export type TreeCreatePath = TreeNode[]

type Props = {
  nodes: TreeNode[]
  selectedId: number | null
  onSelectItem: (node: TreeNode) => void
  onCreate?: (path: TreeCreatePath) => void
  expandAll?: boolean
  expandedPaths?: readonly string[]
  onToggle?: (pathKey: string) => void
  revealPath?: string | null
}

function statusMark(status?: string): string {
  switch (status) {
    case 'complete': return '●'
    case 'legacy': return '◐'
    case 'empty': return '○'
    case 'partial': return '◒'
    default: return '·'
  }
}

const ADD_LABELS: Record<string, string> = {
  category: '新增年份',
  year: '新增月份／批次',
  period: '新增棟別',
  building: '新增設備編號',
}

function Branch({
  node, selectedId, onSelectItem, expandAll, expandedPaths, onToggle, onCreate, parents, revealPath,
}: { node: TreeNode, parents: TreeCreatePath } & Omit<Props, 'nodes'>) {
  const path = [...parents, node]
  const pathKey = branchPathKey(path)
  if (node.type === 'item') {
    return (
      <button data-tree-path={pathKey} className={`tree-item ${node.id === selectedId ? 'selected' : ''}`}
        onClick={() => onSelectItem(node)} aria-pressed={node.id === selectedId}>
        <span aria-hidden="true">{statusMark(node.status)}</span>
        <span>{node.label}</span>
        <small>{node.photo_count ?? 0}</small>
      </button>
    )
  }
  const open = expandAll || (
    expandedPaths ? expandedPaths.includes(pathKey) : node.type === 'category'
  )
  return (
    <details data-tree-path={pathKey} open={open}
      className={`tree-branch ${node.type}${revealPath === pathKey ? ' tree-newly-created' : ''}`}>
      <summary aria-current={revealPath === pathKey ? 'location' : undefined}
        onClick={(event) => {
        if ((event.target as HTMLElement).closest('button')) return
        event.preventDefault()
        if (!expandAll) onToggle?.(pathKey)
      }} onContextMenu={(event) => {
        if (!onCreate) return
        event.preventDefault()
        onCreate(path)
      }}>
        <span>{node.label}</span>
        {onCreate && <button type="button" className="tree-add-button" title={ADD_LABELS[node.type]}
          aria-label={`${node.label}：${ADD_LABELS[node.type]}`}
          onClick={(event) => { event.preventDefault(); event.stopPropagation(); onCreate(path) }}>＋</button>}
      </summary>
      <div className="tree-children">
        {node.children?.map((child) => (
          <Branch key={`${child.type}:${child.key}`} node={child} parents={path}
            selectedId={selectedId} onSelectItem={onSelectItem} expandAll={expandAll}
            expandedPaths={expandedPaths} onToggle={onToggle} revealPath={revealPath}
            onCreate={onCreate} />
        ))}
      </div>
    </details>
  )
}

export function TreeView({
  nodes, selectedId, onSelectItem, onCreate, expandAll = false,
  expandedPaths, onToggle, revealPath,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!revealPath) return
    const element = Array.from(
      containerRef.current?.querySelectorAll<HTMLElement>('[data-tree-path]') ?? [],
    ).find((node) => node.dataset.treePath === revealPath)
    if (element) element.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [nodes, revealPath, expandedPaths])
  if (nodes.length === 0) return <p className="muted">尚無掃描結果</p>
  return (
    <div className="tree-view" ref={containerRef} tabIndex={0} role="region" aria-label="可捲動設備清單">
      {nodes.map((node) => (
        <Branch key={`${node.type}:${node.key}`} node={node} parents={[]}
          selectedId={selectedId} onSelectItem={onSelectItem}
          expandAll={expandAll} expandedPaths={expandedPaths}
          onToggle={onToggle} revealPath={revealPath} onCreate={onCreate} />
      ))}
    </div>
  )
}

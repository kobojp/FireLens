import type { TreeNode } from './types'

type Props = {
  nodes: TreeNode[]
  selectedId: number | null
  onSelectItem: (node: TreeNode) => void
  expandAll?: boolean
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

function Branch({ node, selectedId, onSelectItem, expandAll }: { node: TreeNode } & Omit<Props, 'nodes'>) {
  if (node.type === 'item') {
    const selected = node.id === selectedId
    return (
      <button
        className={`tree-item ${selected ? 'selected' : ''}`}
        onClick={() => onSelectItem(node)}
        aria-pressed={selected}
      >
        <span aria-hidden="true">{statusMark(node.status)}</span>
        <span>{node.label}</span>
        <small>{node.photo_count ?? 0}</small>
      </button>
    )
  }

  return (
    <details open={expandAll || node.type === 'category'} className={`tree-branch ${node.type}`}>
      <summary>{node.label}</summary>
      <div className="tree-children">
        {node.children?.map((child) => (
          <Branch key={`${child.type}:${child.key}`} node={child} selectedId={selectedId} onSelectItem={onSelectItem} expandAll={expandAll} />
        ))}
      </div>
    </details>
  )
}

export function TreeView({ nodes, selectedId, onSelectItem, expandAll = false }: Props) {
  if (nodes.length === 0) return <p className="muted">尚無掃描結果</p>
  return (
    <div className="tree-view">
      {nodes.map((node) => (
        <Branch key={`${node.type}:${node.key}`} node={node} selectedId={selectedId} onSelectItem={onSelectItem} expandAll={expandAll} />
      ))}
    </div>
  )
}

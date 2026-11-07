import type { TreeNode } from './types'

export type TreeCreatePath = TreeNode[]

type Props = {
  nodes: TreeNode[]
  selectedId: number | null
  onSelectItem: (node: TreeNode) => void
  onCreate?: (path: TreeCreatePath) => void
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

const ADD_LABELS: Record<string, string> = {
  category: '新增年份',
  year: '新增月份／批次',
  period: '新增棟別',
  building: '新增設備編號',
}

function Branch({
  node, selectedId, onSelectItem, expandAll, onCreate, parents,
}: { node: TreeNode, parents: TreeCreatePath } & Omit<Props, 'nodes'>) {
  if (node.type === 'item') {
    return (
      <button className={`tree-item ${node.id === selectedId ? 'selected' : ''}`}
        onClick={() => onSelectItem(node)} aria-pressed={node.id === selectedId}>
        <span aria-hidden="true">{statusMark(node.status)}</span>
        <span>{node.label}</span>
        <small>{node.photo_count ?? 0}</small>
      </button>
    )
  }
  const path = [...parents, node]
  return (
    <details open={expandAll || node.type === 'category' ? true : undefined} className={`tree-branch ${node.type}`}>
      <summary onContextMenu={(event) => {
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
            selectedId={selectedId} onSelectItem={onSelectItem} expandAll={expandAll} onCreate={onCreate} />
        ))}
      </div>
    </details>
  )
}

export function TreeView({ nodes, selectedId, onSelectItem, onCreate, expandAll = false }: Props) {
  if (nodes.length === 0) return <p className="muted">尚無掃描結果</p>
  return (
    <div className="tree-view">
      {nodes.map((node) => (
        <Branch key={`${node.type}:${node.key}`} node={node} parents={[]}
          selectedId={selectedId} onSelectItem={onSelectItem} expandAll={expandAll} onCreate={onCreate} />
      ))}
    </div>
  )
}

import { describe, expect, it } from 'vitest'
import type { TreeNode } from './types'
import { filterTree } from './treeSearch'

const nodes: TreeNode[] = [
  {
    type: 'category', key: 'ext', label: '滅火器', children: [
      {
        type: 'year', key: '2026', label: '2026年', children: [
          {
            type: 'period', key: '10', label: '10月份更換', children: [
              {
                type: 'building', key: 'a', label: '中正樓', children: [
                  { type: 'item', key: '1', id: 1, label: '中-01-01' },
                  { type: 'item', key: '2', id: 2, label: '中-01-02' },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
]

describe('filterTree', () => {
  it('returns original tree for blank query', () => {
    expect(filterTree(nodes, '')).toBe(nodes)
  })

  it('keeps only matching item branches', () => {
    const result = filterTree(nodes, '01-02')
    const items = result[0].children![0].children![0].children![0].children!
    expect(items.map((item) => item.id)).toEqual([2])
  })

  it('matches ancestor labels such as building', () => {
    const result = filterTree(nodes, '中正樓')
    const items = result[0].children![0].children![0].children![0].children!
    expect(items).toHaveLength(2)
  })
})
